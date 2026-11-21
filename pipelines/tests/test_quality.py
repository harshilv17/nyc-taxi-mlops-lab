"""stg_trips quality checks: the author's thresholds (decisions/006-quality-checks.md) against the real
months, the edges of each limit, and what blocks and what only warns inside the ingest job."""

import dagster as dg
import pytest
from fakes import FakeRedshift, fake_bucket

from labpipes.contracts import trips_schema
from labpipes.defs.features import trip_features
from labpipes.defs.marts import zone_hour_stats
from labpipes.defs.quality import ERROR, RULES, WARN, evaluate, stg_trips_quality
from labpipes.defs.raw_trips import raw_trips
from labpipes.defs.schema_check import schema_contract
from labpipes.defs.sensor import ingest_month
from labpipes.defs.staging import stg_trips
from labpipes.defs.trip_files import trip_files
from labpipes.defs.zones import taxi_zones
from labpipes.partitions import trip_months

# What the four real months measured in Redshift (S1): every one passes every rule.
REAL = {
    "2024-01": dict(rows=2964624, passenger_null=140162, ratecode_null=140162, duration_nonpositive=870, duration_under_1_min=35121, duration_over_3_hours=1983, dropoff_before_pickup=56, unmatched_zones=0, unknown_zones=31527, distance_nonpositive=60371, distance_over_100=59, fare_negative=37448, passengers_zero=31465, pickup_outside_month=18, p99_duration=60.0, duplicate_rows=0),
    "2024-02": dict(rows=3007526, passenger_null=185610, ratecode_null=185610, duration_nonpositive=803, duration_under_1_min=33744, duration_over_3_hours=1948, dropoff_before_pickup=7, unmatched_zones=0, unknown_zones=28974, distance_nonpositive=68225, distance_over_100=71, fare_negative=40655, passengers_zero=34094, pickup_outside_month=15, p99_duration=62.0, duplicate_rows=1),
    "2024-03": dict(rows=3582628, passenger_null=426190, ratecode_null=426190, duration_nonpositive=1128, duration_under_1_min=40659, duration_over_3_hours=2172, dropoff_before_pickup=117, unmatched_zones=0, unknown_zones=35374, distance_nonpositive=87168, distance_over_100=122, fare_negative=58464, passengers_zero=40372, pickup_outside_month=23, p99_duration=67.0, duplicate_rows=0),
    "2024-04": dict(rows=3514289, passenger_null=408576, ratecode_null=408576, duration_nonpositive=1089, duration_under_1_min=40234, duration_over_3_hours=2263, dropoff_before_pickup=70, unmatched_zones=0, unknown_zones=35759, distance_nonpositive=45813, distance_over_100=150, fare_negative=57568, passengers_zero=39591, pickup_outside_month=9, p99_duration=68.0, duplicate_rows=0),
}
GOOD = REAL["2024-01"]


def failed(metrics):
    return {r.check_name for r in evaluate(metrics) if not r.passed}


@pytest.mark.parametrize("month", REAL)
def test_every_real_month_passes_every_rule(month):
    assert failed(REAL[month]) == set()


@pytest.mark.parametrize(
    ("rule", "change"),
    [
        ("monthly_row_count", dict(rows=1_999_999)),
        ("monthly_row_count", dict(rows=5_000_001)),
        ("passenger_count_null", dict(passenger_null=int(0.151 * GOOD["rows"]))),
        ("ratecode_id_null", dict(ratecode_null=int(0.151 * GOOD["rows"]))),
        ("duration_nonpositive", dict(duration_nonpositive=int(0.0011 * GOOD["rows"]))),
        ("duration_under_1_min", dict(duration_under_1_min=int(0.026 * GOOD["rows"]))),
        ("duration_over_3_hours", dict(duration_over_3_hours=int(0.0021 * GOOD["rows"]))),
        ("dropoff_before_pickup", dict(dropoff_before_pickup=201)),
        ("unmatched_zone_ids", dict(unmatched_zones=1)),
        ("zone_ids_264_265", dict(unknown_zones=int(0.021 * GOOD["rows"]))),
        ("distance_nonpositive", dict(distance_nonpositive=int(0.041 * GOOD["rows"]))),
        ("distance_over_100_miles", dict(distance_over_100=301)),
        ("negative_fare", dict(fare_negative=int(0.031 * GOOD["rows"]))),
        ("passenger_count_zero", dict(passengers_zero=int(0.026 * GOOD["rows"]))),
        ("pickup_outside_source_month", dict(pickup_outside_month=101)),
        ("exact_duplicate_rows", dict(duplicate_rows=11)),
        ("p99_trip_duration", dict(p99_duration=90.5)),
    ],
)
def test_each_rule_fires_just_past_its_limit_and_only_that_rule(rule, change):
    assert failed({**GOOD, **change}) == {rule}


def test_a_value_exactly_at_a_limit_passes():
    at_limit = {**GOOD, "dropoff_before_pickup": 200, "distance_over_100": 300, "pickup_outside_month": 100, "duplicate_rows": 10, "p99_duration": 90.0, "rows": 2_000_000}
    assert failed(at_limit) == set()


def test_an_empty_month_fails_the_row_count_without_dividing_by_zero():
    assert "monthly_row_count" in failed({k: 0 for k in GOOD})


def test_errors_block_and_warnings_do_not():
    specs = {s.name: s for s in stg_trips_quality.check_specs}
    assert len(specs) == len(RULES) == 16
    assert {n for n, s in specs.items() if s.blocking} == {r.name for r in RULES if r.severity == ERROR}
    assert {n for n, s in specs.items() if s.blocking} == {
        "monthly_row_count", "duration_nonpositive", "dropoff_before_pickup", "unmatched_zone_ids", "exact_duplicate_rows"
    }
    assert sum(r.severity == WARN for r in RULES) == 11


class QualityRedshift(FakeRedshift):
    """Answers the quality queries with canned metrics; everything else as FakeRedshift."""

    metrics: dict = {}
    dups: int = 0

    def query(self, sql: str) -> list[dict]:
        if "percentile_cont" in sql:
            return [self.metrics]
        if "duplicate_rows" in sql:
            return [{"duplicate_rows": self.dups}]
        return super().query(sql)


def run_job(metrics, dups=0):
    defs = dg.Definitions(
        assets=[taxi_zones, trip_files, raw_trips, stg_trips, zone_hour_stats, trip_features],
        asset_checks=[schema_contract, stg_trips_quality],
        jobs=[ingest_month],
        resources={
            "redshift": QualityRedshift(cluster_id="lab", database="lab", db_user="labadmin", metrics=metrics, dups=dups),
            "data_bucket": fake_bucket({"2024-01": ("a", trips_schema())}),
        },
    )
    with dg.DagsterInstance.ephemeral() as instance:
        instance.add_dynamic_partitions(trip_months.name, ["2024-01"])
        result = defs.resolve_job_def("ingest_month").execute_in_process(
            partition_key="2024-01", instance=instance, raise_on_error=False
        )
    done = {e.asset_key.to_user_string() for e in result.get_asset_materialization_events()}
    checks = {e.check_name: e for e in result.get_asset_check_evaluations()}
    return result, done, checks


def test_a_good_month_runs_through_to_the_mart_with_every_check_passing():
    result, done, checks = run_job(GOOD)
    assert result.success and "zone_hour_stats" in done
    assert len(checks) == 17 and all(c.passed for c in checks.values())  # schema_contract plus the 16 quality checks


def test_an_error_rule_blocks_the_mart():
    result, done, checks = run_job({**GOOD, "rows": 1_000_000})  # below the 2,000,000 floor
    assert not result.success
    assert "stg_trips" in done and "zone_hour_stats" not in done
    assert not checks["monthly_row_count"].passed


def test_a_warn_rule_shows_up_but_does_not_block_the_mart():
    result, done, checks = run_job({**GOOD, "passenger_null": int(0.2 * GOOD["rows"])})
    assert result.success and "zone_hour_stats" in done
    assert not checks["passenger_count_null"].passed
    assert checks["passenger_count_null"].severity == WARN
