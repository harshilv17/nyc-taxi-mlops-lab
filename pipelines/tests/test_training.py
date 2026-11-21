"""train_model end to end on fakes (synthetic trips, a local artifact folder, a SQLite MLflow): the gate
fails closed until the author sets the margin and latency budget, and only the gate sets `challenger`."""

import dagster as dg
import mlflow
import pytest
from fakes import LOG, LocalArtifacts, unloading_redshift
from mlflow import MlflowClient

from labpipes.contracts import mlflow_contract
from labpipes.defs import training
from labpipes.defs.training import beats_champion, challenger, eval_report, gate, train_model, trained_model, training_set
from labpipes.resources import MlflowTracking

NAME = mlflow_contract()["registered_model"]


@pytest.fixture
def lab(tmp_path):
    uri = f"sqlite:///{tmp_path}/mlflow.db"
    mlflow.set_tracking_uri(uri)
    mlflow.create_experiment(mlflow_contract()["experiment"], artifact_location=str(tmp_path / "mlruns"))
    resources = {
        "redshift": unloading_redshift(str(tmp_path / "s3")),
        "artifacts": LocalArtifacts(bucket="art", root=str(tmp_path / "s3")),
        "tracking": MlflowTracking(tracking_uri=uri),
    }
    defs = dg.Definitions(assets=[training_set, trained_model, eval_report, challenger], asset_checks=[beats_champion],
                          jobs=[train_model], resources=resources)
    with dg.DagsterInstance.ephemeral() as instance:
        def run():
            result = defs.resolve_job_def("train_model").execute_in_process(instance=instance, raise_on_error=False)
            checks = {e.check_name: e for e in result.get_asset_check_evaluations()}
            done = {e.asset_key.to_user_string() for e in result.get_asset_materialization_events()}
            return result, checks, done
        yield run, MlflowClient(uri)


def aliases(client):
    return {k: str(v) for k, v in client.get_registered_model(NAME).aliases.items()}


def test_undecided_numbers_train_and_measure_but_set_no_challenger(lab, monkeypatch):
    monkeypatch.setattr(training, "MARGIN_MIN", None)
    monkeypatch.setattr(training, "LATENCY_BUDGET_MS", None)
    run, client = lab
    result, checks, done = run()
    assert {"training_set", "trained_model", "eval_report"} <= done and "challenger" not in done
    assert not checks["beats_champion"].passed and "not decided yet" in checks["beats_champion"].description
    assert aliases(client) == {}
    v = client.get_model_version(NAME, "1")
    assert set(mlflow_contract()["version_tags"]) <= set(v.tags)  # every contract tag, even without a challenger
    assert v.tags["training_window"] == "2024-01..2024-03" and v.tags["holdout_month"] == "2024-04"


def test_a_version_that_clears_the_margin_becomes_challenger_and_never_champion(lab, monkeypatch):
    monkeypatch.setattr(training, "MARGIN_MIN", 0.0)
    monkeypatch.setattr(training, "LATENCY_BUDGET_MS", 10_000.0)
    run, client = lab
    result, checks, done = run()
    assert result.success and checks["beats_champion"].passed and "challenger" in done
    assert aliases(client) == {"challenger": "1"}
    run_id = client.get_model_version(NAME, "1").run_id
    logged = client.get_run(run_id).data.metrics
    assert {"mae_min", "p95_latency_ms", "champion_mae_min"} <= set(logged)
    assert logged["mae_min"] < logged["champion_mae_min"]  # v2 beats the v1 baseline on the synthetic trips


def test_a_margin_it_does_not_clear_blocks(lab, monkeypatch):
    monkeypatch.setattr(training, "MARGIN_MIN", 100.0)
    monkeypatch.setattr(training, "LATENCY_BUDGET_MS", 10_000.0)
    run, client = lab
    result, checks, done = run()
    assert not checks["beats_champion"].passed and "not better by 100.0 min" in checks["beats_champion"].description
    assert "challenger" not in done and aliases(client) == {}


def test_the_latency_budget_blocks_too(lab, monkeypatch):
    monkeypatch.setattr(training, "MARGIN_MIN", 0.0)
    monkeypatch.setattr(training, "LATENCY_BUDGET_MS", 0.0)
    run, client = lab
    result, checks, done = run()
    assert not checks["beats_champion"].passed and "latency budget" in checks["beats_champion"].description
    assert aliases(client) == {}


def test_the_window_and_holdout_are_what_get_unloaded(lab, monkeypatch):
    monkeypatch.setattr(training, "MARGIN_MIN", None)
    run, _ = lab
    run()
    unloads = [s for s in LOG if s.startswith("unload")]
    assert len(unloads) == 3
    assert "trip_month between ''2024-01'' and ''2024-03''" in unloads[0] and "/train/'" in unloads[0]
    assert "trip_month = ''2024-04''" in unloads[1] and "/holdout/'" in unloads[1]
    assert "median(trip_distance)" in unloads[2] and "''2024-04''" not in unloads[2]  # distances from the window only


def test_gate_rules():
    report = {"version": 3, "comparator": "v1 baseline", "mae_min": 3.80, "champion_mae_min": 3.96, "p95_latency_ms": 4.0}
    assert gate(report)[0] is False  # the module's real numbers are still undecided
    for margin, budget, ok in [(0.10, 10.0, True), (0.16, 10.0, True), (0.20, 10.0, False), (0.10, 3.9, False)]:
        training.MARGIN_MIN, training.LATENCY_BUDGET_MS = margin, budget
        try:
            assert gate(report)[0] is ok, (margin, budget)
        finally:
            training.MARGIN_MIN = training.LATENCY_BUDGET_MS = None
