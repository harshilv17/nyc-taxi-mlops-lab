"""S2: training_set, trained_model, eval_report, the challenger gate and the challenger asset.

- training_set: UNLOAD a window of staging.trip_features (and the holdout month) to the artifact bucket.
  The zone-pair distance lookup (contracts/features.yaml, est_distance_miles) comes from the window only.
- trained_model: fit tripmodel.LightGBMModel (the given v2), log it to MLflow as a pyfunc with
  tripmodel.model_signature() and the tripmodel package bundled, register a version of the model named
  in contracts/mlflow.yaml, and tag it as that contract says.
- eval_report: tripmodel.evaluate the new version and the champion (or the v1 baseline before there is
  one) on the same holdout; log the metrics.
- A blocking check that guards a `challenger` asset, which sets the alias. The pipeline never moves
  `champion`.
Decision points: what stays in the notebook; the promotion metric and margin; the training window.

The author's decisions are the constants below. If MARGIN_MIN or LATENCY_BUDGET_MS is ever None, the gate
fails closed: train_model still trains, registers and measures, but sets no challenger.
"""

from pathlib import Path

import dagster as dg

from ..contracts import features_contract, mlflow_contract
from ..partitions import check_month
from ..resources import ArtifactBucket, MlflowTracking, RedshiftData

# Training window (decision W1, fixed months): train on these three months, evaluate on the next.
TRAIN_FIRST, TRAIN_LAST, HOLDOUT_MONTH = "2024-01", "2024-03", "2024-04"

# Promotion (decision M2): the new version's holdout MAE must be at least MARGIN_MIN minutes below the
# champion's (or the v1 baseline's), and its p95 single-row latency at most LATENCY_BUDGET_MS.
# None = not decided: the gate blocks. Set by the author from the first measured run (decisions/008):
# v2 was 0.319 min better than the v1 baseline on 2024-04, at 3.82 ms p95.
MARGIN_MIN: float | None = 0.20
LATENCY_BUDGET_MS: float | None = 25.0

FEATURE_COLUMNS = "pickup_zone_id, dropoff_zone_id, pickup_hour, pickup_dow, duration_min"


def latest(context, asset: str) -> dict:
    """The metadata of an asset's latest materialization, as plain values."""
    event = context.instance.get_latest_materialization_event(dg.AssetKey(asset))
    if event is None:
        raise dg.Failure(f"{asset} has not been materialized yet")
    return {k: v.value for k, v in event.asset_materialization.metadata.items()}


@dg.asset(deps=["trip_features"], group_name="model", kinds={"redshift", "s3"}, pool="redshift")
def training_set(context: dg.AssetExecutionContext, redshift: RedshiftData, artifacts: ArtifactBucket) -> dg.MaterializeResult:
    first, last, holdout = check_month(TRAIN_FIRST), check_month(TRAIN_LAST), check_month(HOLDOUT_MONTH)
    prefix = f"training/{context.run_id}/"  # a fresh prefix per run, so no file from an older UNLOAD is read

    def unload(select: str, part: str) -> str:
        return f"unload ('{select}') to '{artifacts.uri(prefix + part + '/')}' iam_role default format as parquet"

    window = f"trip_month between ''{first}'' and ''{last}''"
    redshift.execute(unload(f"select {FEATURE_COLUMNS} from staging.trip_features where {window}", "train"))
    redshift.execute(unload(f"select {FEATURE_COLUMNS} from staging.trip_features where trip_month = ''{holdout}''", "holdout"))
    # est_distance_miles: the zone pair's median distance over the window only, from valid trips.
    redshift.execute(unload(
        "select pickup_zone_id, dropoff_zone_id, median(trip_distance) as est_distance_miles from staging.stg_trips "
        f"where {window} and trip_distance > 0 and duration_min > 0 and duration_min <= 180 "
        "and pickup_zone_id between 1 and 263 and dropoff_zone_id between 1 and 263 group by 1, 2",
        "distances",
    ))
    counts = redshift.query(
        f"select sum(case when trip_month between '{first}' and '{last}' then 1 else 0 end) as train, "
        f"sum(case when trip_month = '{holdout}' then 1 else 0 end) as holdout from staging.trip_features"
    )[0]
    train_rows, holdout_rows = int(counts["train"] or 0), int(counts["holdout"] or 0)
    if not train_rows or not holdout_rows:
        raise dg.Failure(f"empty training set: {train_rows} training rows, {holdout_rows} holdout rows")
    return dg.MaterializeResult(metadata={
        "prefix": prefix,
        "training_window": f"{first}..{last}",
        "holdout_month": holdout,
        "train_rows": dg.MetadataValue.int(train_rows),
        "holdout_rows": dg.MetadataValue.int(holdout_rows),
    })


@dg.asset(deps=[training_set], group_name="model", kinds={"mlflow"})
def trained_model(context: dg.AssetExecutionContext, artifacts: ArtifactBucket, tracking: MlflowTracking) -> dg.MaterializeResult:
    import mlflow

    import tripmodel
    from tripmodel import LightGBMModel, model_signature

    ts = latest(context, "training_set")
    train = artifacts.read_parquet(ts["prefix"] + "train/")
    distances = artifacts.read_parquet(ts["prefix"] + "distances/")
    model = LightGBMModel().fit(train, distances)

    contract, client = mlflow_contract(), tracking.client()
    name = contract["registered_model"]
    with mlflow.start_run(run_name=f"train {ts['training_window']}") as run:
        mlflow.log_params({"training_window": ts["training_window"], "holdout_month": ts["holdout_month"],
                           "train_rows": len(train), **model.params})
        info = mlflow.pyfunc.log_model(
            name="model",
            python_model=model,
            signature=model_signature(),
            code_paths=[str(Path(tripmodel.__file__).parent)],  # serving loads it without the pipeline
            registered_model_name=name,
        )
    version = str(info.registered_model_version)
    import os

    for tag, value in {
        "training_window": ts["training_window"],
        "holdout_month": ts["holdout_month"],
        "features_version": str(features_contract()["version"]),
        "git_sha": os.environ.get("GIT_SHA", "unknown"),
    }.items():
        client.set_model_version_tag(name, version, tag, value)
    return dg.MaterializeResult(metadata={"version": dg.MetadataValue.int(int(version)), "run_id": run.info.run_id,
                                          "prefix": ts["prefix"]})


@dg.asset(deps=[trained_model], group_name="model", kinds={"mlflow"})
def eval_report(context: dg.AssetExecutionContext, redshift: RedshiftData, artifacts: ArtifactBucket,
                tracking: MlflowTracking) -> dg.MaterializeResult:
    import mlflow
    from mlflow.exceptions import MlflowException

    from tripmodel import BaselineModel, evaluate

    tm = latest(context, "trained_model")
    contract, client = mlflow_contract(), tracking.client()
    name = contract["registered_model"]
    holdout = artifacts.read_parquet(tm["prefix"] + "holdout/")
    boroughs = {int(r["location_id"]): r["borough"] for r in redshift.query("select location_id, borough from ingest.taxi_zones")}

    new = evaluate(mlflow.pyfunc.load_model(f"models:/{name}/{tm['version']}").predict, holdout, boroughs)
    try:
        champion = client.get_model_version_by_alias(name, "champion")
        comparator = f"champion v{champion.version}"
        old = evaluate(mlflow.pyfunc.load_model(f"models:/{name}@champion").predict, holdout, boroughs)
    except MlflowException as e:
        if e.error_code not in ("RESOURCE_DOES_NOT_EXIST", "INVALID_PARAMETER_VALUE"):
            raise  # MLflow unreachable is not "no champion"
        # Before there is a champion: the v1 baseline, fitted on the same window and evaluated the same way.
        train = artifacts.read_parquet(tm["prefix"] + "train/")
        distances = artifacts.read_parquet(tm["prefix"] + "distances/")
        baseline = BaselineModel().fit(train, distances)
        comparator = "v1 baseline"
        old = evaluate(lambda df: baseline.predict(None, df), holdout, boroughs)

    metrics = {k: v for k, v in new.items() if k in contract["metrics"]}
    metrics["champion_mae_min"] = old["mae_min"]
    for k, v in metrics.items():
        client.log_metric(tm["run_id"], k, v)
    for tag in ("mae_min", "p95_latency_ms", "champion_mae_min"):
        client.set_model_version_tag(name, str(tm["version"]), tag, f"{metrics[tag]:.4f}")
    return dg.MaterializeResult(metadata={
        "version": dg.MetadataValue.int(int(tm["version"])),
        "comparator": comparator,
        "mae_min": dg.MetadataValue.float(metrics["mae_min"]),
        "champion_mae_min": dg.MetadataValue.float(metrics["champion_mae_min"]),
        "improvement_min": dg.MetadataValue.float(metrics["champion_mae_min"] - metrics["mae_min"]),
        "p95_latency_ms": dg.MetadataValue.float(metrics["p95_latency_ms"]),
        "slices": dg.MetadataValue.json({k: round(v, 4) for k, v in new.items() if k.startswith("mae_min.")}),
        "comparator_slices": dg.MetadataValue.json({k: round(v, 4) for k, v in old.items() if k.startswith("mae_min.")}),
    })


def gate(report: dict) -> tuple[bool, str]:
    """M2 with a latency budget. Fails closed while either number is undecided."""
    gain = report["champion_mae_min"] - report["mae_min"]
    measured = (f"v{report['version']}: MAE {report['mae_min']:.3f} vs {report['comparator']} {report['champion_mae_min']:.3f} "
                f"(better by {gain:.3f} min), p95 latency {report['p95_latency_ms']:.2f} ms")
    if MARGIN_MIN is None or LATENCY_BUDGET_MS is None:
        return False, f"not decided yet: set MARGIN_MIN and LATENCY_BUDGET_MS in training.py. Measured {measured}"
    if gain < MARGIN_MIN:
        return False, f"not better by {MARGIN_MIN} min. {measured}"
    if report["p95_latency_ms"] > LATENCY_BUDGET_MS:
        return False, f"over the {LATENCY_BUDGET_MS} ms latency budget. {measured}"
    return True, f"better by at least {MARGIN_MIN} min and within {LATENCY_BUDGET_MS} ms. {measured}"


@dg.asset_check(asset=eval_report, blocking=True, description="Beats the champion (or the v1 baseline) by the margin, within the latency budget.")
def beats_champion(context: dg.AssetCheckExecutionContext) -> dg.AssetCheckResult:
    report = latest(context, "eval_report")
    passed, why = gate(report)
    return dg.AssetCheckResult(passed=passed, severity=dg.AssetCheckSeverity.ERROR, description=why,
                               metadata={"version": dg.MetadataValue.int(int(report["version"]))})


@dg.asset(deps=[eval_report], group_name="model", kinds={"mlflow"})
def challenger(context: dg.AssetExecutionContext, tracking: MlflowTracking) -> dg.MaterializeResult:
    """Sets `challenger` on the version eval_report just judged. Never touches `champion`."""
    report, tm = latest(context, "eval_report"), latest(context, "trained_model")
    passed, why = gate(report)  # again here, so materializing this asset alone can't skip the gate
    if not passed or int(report["version"]) != int(tm["version"]):
        raise dg.Failure(f"not setting challenger: {why}")
    name = mlflow_contract()["registered_model"]
    tracking.client().set_registered_model_alias(name, "challenger", str(tm["version"]))
    return dg.MaterializeResult(metadata={"version": dg.MetadataValue.int(int(tm["version"])), "why": why})


train_model = dg.define_asset_job(
    "train_model",
    selection=dg.AssetSelection.assets("training_set", "trained_model", "eval_report", "challenger"),
)
