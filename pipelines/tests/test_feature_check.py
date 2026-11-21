"""The feature_contract check: exact columns, compatible types, zero-tolerance ranges, and that it blocks."""

import dagster as dg
import pytest
from fakes import FakeRedshift, fake_bucket

from labpipes.contracts import features_contract, trips_schema
from labpipes.defs.feature_check import feature_contract, range_problems, range_sql, structure_problems
from labpipes.defs.features import trip_features
from labpipes.defs.marts import zone_hour_stats
from labpipes.defs.raw_trips import raw_trips
from labpipes.defs.schema_check import schema_contract
from labpipes.defs.sensor import ingest_month
from labpipes.defs.staging import stg_trips
from labpipes.defs.trip_files import trip_files
from labpipes.defs.zones import taxi_zones
from labpipes.partitions import trip_months

C = features_contract()
GOOD = [
    ("trip_month", "character"), ("pickup_zone_id", "integer"), ("dropoff_zone_id", "integer"),
    ("pickup_hour", "smallint"), ("pickup_dow", "smallint"), ("duration_min", "double precision"),
]


def replace(table, name, new_type):
    return [(n, new_type if n == name else t) for n, t in table]


def test_the_real_table_shape_matches():
    assert structure_problems(C, GOOD) == []


def test_a_forbidden_column_is_named_as_such():
    found = structure_problems(C, [*GOOD, ("trip_distance", "double precision")])
    assert found == ["forbidden column present: trip_distance (known only after the trip)"]


def test_every_forbidden_column_is_caught():
    for name in C["forbidden"]:
        assert any(name in p and "forbidden" in p for p in structure_problems(C, [*GOOD, (name, "integer")]))


def test_a_harmless_extra_column_blocks_too():  # A1: exactly the contract's columns
    assert structure_problems(C, [*GOOD, ("row_id", "bigint")]) == ["extra column not in the contract: row_id"]


def test_a_missing_input_blocks():
    assert structure_problems(C, [c for c in GOOD if c[0] != "pickup_dow"]) == ["missing column: pickup_dow"]


def test_every_problem_is_reported():
    found = structure_problems(C, [("trip_month", "character"), ("pickup_zone_id", "integer"), ("tip_amount", "double precision")])
    assert len(found) == 5  # one forbidden column, and four missing: dropoff_zone_id, pickup_hour, pickup_dow, duration_min
    assert "forbidden column present: tip_amount (known only after the trip)" in found[0]


@pytest.mark.parametrize("new", ["integer", "bigint", "smallint"])
def test_any_integer_width_is_compatible(new):
    assert structure_problems(C, replace(GOOD, "pickup_hour", new)) == []


def test_other_families_are_not_compatible():
    assert structure_problems(C, replace(GOOD, "pickup_hour", "double precision")) == ["column pickup_hour: type double precision, contract has smallint"]
    assert structure_problems(C, replace(GOOD, "duration_min", "integer")) == ["column duration_min: type integer, contract has double precision"]
    assert structure_problems(C, replace(GOOD, "pickup_zone_id", "character varying")) != []


def test_the_range_query_follows_the_contract():
    sql = range_sql(C, "2024-01", {n for n, _ in GOOD})
    assert "where trip_month = '2024-01'" in sql
    assert "pickup_zone_id >= 1 and pickup_zone_id <= 263" in sql
    assert "pickup_dow >= 0 and pickup_dow <= 6" in sql
    assert "duration_min > 0 and duration_min <= 180" in sql  # the label's lower bound is exclusive
    assert "is null or not (" in sql
    with pytest.raises(ValueError):
        range_sql(C, "2024-01'; drop table x; --", {"pickup_hour"})


def test_a_range_query_skips_columns_that_are_not_there():
    sql = range_sql(C, "2024-01", {"pickup_hour", "duration_min"})
    assert "pickup_hour" in sql and "pickup_zone_id" not in sql
    assert range_sql(C, "2024-01", set()) is None


def test_one_bad_row_is_a_problem_and_zero_is_none():
    assert range_problems(C, {"rows": 5, "pickup_hour": 0, "duration_min": 0}) == []
    assert range_problems(C, {"rows": 5, "pickup_hour": 1}) == ["column pickup_hour: 1 row(s) outside [0, 23] or null"]
    assert range_problems(C, {"rows": 5, "duration_min": 3}) == ["column duration_min: 3 row(s) outside (0, 180] or null"]


class FeatureRedshift(FakeRedshift):
    """Answers the check's two queries (the table's columns, the range counts); the rest as FakeRedshift."""

    table: list = []
    counts: dict = {}

    def query(self, sql: str) -> list[dict]:
        if "svv_columns" in sql:
            return [{"column_name": n, "data_type": t} for n, t in self.table]
        if " as rows," in sql and "from staging.trip_features" in sql:
            return [{"rows": 1000, **{c["name"]: 0 for c in C["inputs"]}, "duration_min": 0, **self.counts}]
        return super().query(sql)


def run_job(table, counts=None):
    defs = dg.Definitions(
        assets=[taxi_zones, trip_files, raw_trips, stg_trips, zone_hour_stats, trip_features],
        asset_checks=[schema_contract, feature_contract],
        jobs=[ingest_month],
        resources={
            "redshift": FeatureRedshift(cluster_id="lab", database="lab", db_user="labadmin", table=table, counts=counts or {}),
            "data_bucket": fake_bucket({"2024-01": ("a", trips_schema())}),
        },
    )
    with dg.DagsterInstance.ephemeral() as instance:
        instance.add_dynamic_partitions(trip_months.name, ["2024-01"])
        result = defs.resolve_job_def("ingest_month").execute_in_process(partition_key="2024-01", instance=instance, raise_on_error=False)
    return result, {e.check_name: e for e in result.get_asset_check_evaluations()}


def test_the_check_is_blocking_and_a_good_month_passes_it():
    (spec,) = feature_contract.check_specs
    assert (spec.name, spec.asset_key.to_user_string(), spec.blocking) == ("feature_contract", "trip_features", True)
    result, checks = run_job(GOOD)
    assert result.success and checks["feature_contract"].passed


def test_a_leaked_column_fails_the_check_in_the_job():
    result, checks = run_job([*GOOD, ("fare_amount", "double precision")])
    assert not result.success
    assert not checks["feature_contract"].passed and "fare_amount" in checks["feature_contract"].description


def test_an_out_of_range_row_fails_the_check_in_the_job():
    result, checks = run_job(GOOD, {"pickup_hour": 1})
    assert not result.success and not checks["feature_contract"].passed
