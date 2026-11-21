"""The trips sensor: new files become partitions and runs, an unchanged file is skipped, a changed one reruns."""

import json

import dagster as dg
import pytest
from fakes import fake_bucket

from labpipes.contracts import trips_schema
from labpipes.defs.sensor import ingest_month, trip_files_sensor
from labpipes.partitions import trip_months


def files(**etags):
    return fake_bucket({m.replace("_", "-"): (etag, trips_schema()) for m, etag in etags.items()})


def evaluate(instance, bucket, cursor=None):
    ctx = dg.build_sensor_context(instance=instance, cursor=cursor, resources={"data_bucket": bucket})
    return trip_files_sensor(ctx)


@pytest.fixture
def instance():
    with dg.DagsterInstance.ephemeral() as i:
        yield i


def test_new_files_become_partitions_and_runs(instance):
    out = evaluate(instance, files(**{"2024_01": "a", "2024_02": "b"}))
    assert [(r.partition_key, r.run_key) for r in out.run_requests] == [("2024-01", "2024-01:a"), ("2024-02", "2024-02:b")]
    (req,) = out.dynamic_partitions_requests
    assert req.partitions_def_name == trip_months.name and req.partition_keys == ["2024-01", "2024-02"]
    assert json.loads(out.cursor) == {"2024-01": "a", "2024-02": "b"}


def test_nothing_new_is_skipped(instance):
    cursor = json.dumps({"2024-01": "a"})
    out = evaluate(instance, files(**{"2024_01": "a"}), cursor)
    assert isinstance(out, dg.SkipReason)


def test_a_changed_file_reruns_its_month_without_a_new_partition(instance):
    instance.add_dynamic_partitions(trip_months.name, ["2024-01", "2024-02"])
    cursor = json.dumps({"2024-01": "a", "2024-02": "b"})
    out = evaluate(instance, files(**{"2024_01": "a2", "2024_02": "b"}), cursor)
    assert [(r.partition_key, r.run_key) for r in out.run_requests] == [("2024-01", "2024-01:a2")]
    assert out.dynamic_partitions_requests == []
    assert json.loads(out.cursor) == {"2024-01": "a2", "2024-02": "b"}


def test_a_lost_cursor_does_not_readd_existing_partitions(instance):
    instance.add_dynamic_partitions(trip_months.name, ["2024-01"])
    out = evaluate(instance, files(**{"2024_01": "a", "2024_02": "b"}))
    (req,) = out.dynamic_partitions_requests
    assert req.partition_keys == ["2024-02"]
    assert len(out.run_requests) == 2


def test_the_job_runs_from_trip_files_to_the_mart(monkeypatch):
    for k in ("REDSHIFT_CLUSTER_ID", "REDSHIFT_DATABASE", "REDSHIFT_DB_USER", "LAB_DATA_BUCKET", "LAB_ARTIFACT_BUCKET", "MLFLOW_TRACKING_URI", "LLM_HOST"):
        monkeypatch.setenv(k, "x")
    from labpipes.definitions import defs

    job = defs.resolve_job_def("ingest_month")
    keys = {k.to_user_string() for k in job.asset_layer.executable_asset_keys}
    assert keys == {"taxi_zones", "trip_files", "raw_trips", "stg_trips", "zone_hour_stats"}
    assert "trip_files_sensor" in {s.name for s in defs.sensors or []}
    assert ingest_month.name == "ingest_month"


def test_a_drifted_file_stops_the_run_before_anything_is_copied():
    from fakes import LOG, fake_redshift, schema_2025

    from labpipes.defs.marts import zone_hour_stats
    from labpipes.defs.raw_trips import raw_trips
    from labpipes.defs.schema_check import schema_contract
    from labpipes.defs.staging import stg_trips
    from labpipes.defs.trip_files import trip_files
    from labpipes.defs.zones import taxi_zones

    bucket = fake_bucket({"2025-01": ("a", schema_2025())})  # cbd_congestion_fee appended: the contract has 19 columns
    defs = dg.Definitions(
        assets=[taxi_zones, trip_files, raw_trips, stg_trips, zone_hour_stats],
        asset_checks=[schema_contract],
        jobs=[ingest_month],
        resources={"redshift": fake_redshift(), "data_bucket": bucket},
    )
    with dg.DagsterInstance.ephemeral() as instance:
        instance.add_dynamic_partitions(trip_months.name, ["2025-01"])
        result = defs.resolve_job_def("ingest_month").execute_in_process(
            partition_key="2025-01", instance=instance, raise_on_error=False
        )
    done = {e.asset_key.to_user_string() for e in result.get_asset_materialization_events()}
    assert not result.success
    assert "trip_files" in done and not done & {"raw_trips", "stg_trips", "zone_hour_stats"}
    assert not any("copy raw_stage" in s or "ingest.raw_trips" in s for s in LOG)  # nothing reached Redshift for the file
