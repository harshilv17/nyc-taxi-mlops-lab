"""S1: data-quality checks on stg_trips (nulls, ranges, duplicates, row counts).

Decision points: which checks block downstream and which only warn, and every threshold. Base them on
what real months look like (scripts/verify/results/tlc-stats-2024-01-04.md is the instructor's
baseline; measure your own in Redshift) and on what gameday's corrupt month would look like.

The rules below are the author's decisions (decisions/006-quality-checks.md), set against the four real
months 2024-01..04, which all pass every one. ERROR rules block: zone_hour_stats isn't rebuilt with a
month that fails one. WARN rules only show up on the check. One scan per month computes every metric.
"""

from dataclasses import dataclass
from typing import Callable

import dagster as dg

from ..partitions import check_month, trip_months
from ..resources import RedshiftData
from .staging import stg_trips

ERROR, WARN = dg.AssetCheckSeverity.ERROR, dg.AssetCheckSeverity.WARN


@dataclass(frozen=True)
class Rule:
    name: str
    severity: dg.AssetCheckSeverity
    measure: Callable[[dict], float]  # the metric the rule is about, from the month's metrics
    fails: Callable[[float], bool]
    limit: str  # what the threshold says, for the result description


def pct(key: str) -> Callable[[dict], float]:
    return lambda m: 100 * m[key] / max(m["rows"], 1)


def count(key: str) -> Callable[[dict], float]:
    return lambda m: m[key]


def above(limit: float) -> Callable[[float], bool]:
    return lambda v: v > limit


RULES = [
    Rule("monthly_row_count", ERROR, count("rows"), lambda v: not 2_000_000 <= v <= 5_000_000, "rows must be 2,000,000 to 5,000,000"),
    Rule("passenger_count_null", WARN, pct("passenger_null"), above(15), "% of rows, limit 15"),
    Rule("ratecode_id_null", WARN, pct("ratecode_null"), above(15), "% of rows, limit 15"),
    Rule("duration_nonpositive", ERROR, pct("duration_nonpositive"), above(0.10), "% of rows with duration <= 0 min, limit 0.10"),
    Rule("duration_under_1_min", WARN, pct("duration_under_1_min"), above(2.5), "% of rows under 1 min, limit 2.5"),
    Rule("duration_over_3_hours", WARN, pct("duration_over_3_hours"), above(0.20), "% of rows over 3 h, limit 0.20"),
    Rule("dropoff_before_pickup", ERROR, count("dropoff_before_pickup"), above(200), "rows, limit 200"),
    Rule("unmatched_zone_ids", ERROR, count("unmatched_zones"), above(0), "rows whose zone isn't in ingest.taxi_zones, limit 0"),
    Rule("zone_ids_264_265", WARN, pct("unknown_zones"), above(2), "% of rows with zone 264 or 265, limit 2"),
    Rule("distance_nonpositive", WARN, pct("distance_nonpositive"), above(4), "% of rows with distance <= 0, limit 4"),
    Rule("distance_over_100_miles", WARN, count("distance_over_100"), above(300), "rows, limit 300"),
    Rule("negative_fare", WARN, pct("fare_negative"), above(3), "% of rows with a negative fare, limit 3"),
    Rule("passenger_count_zero", WARN, pct("passengers_zero"), above(2.5), "% of rows with 0 passengers, limit 2.5"),
    Rule("pickup_outside_source_month", WARN, count("pickup_outside_month"), above(100), "rows picked up outside the file's month, limit 100"),
    Rule("exact_duplicate_rows", ERROR, count("duplicate_rows"), above(10), "extra copies of an identical row, limit 10"),
    Rule("p99_trip_duration", WARN, count("p99_duration"), above(90), "minutes, limit 90"),
]

METRICS_SQL = """
select count(*) as rows,
  sum(case when s.passenger_count is null then 1 else 0 end) as passenger_null,
  sum(case when s.ratecode_id is null then 1 else 0 end) as ratecode_null,
  sum(case when s.duration_min <= 0 then 1 else 0 end) as duration_nonpositive,
  sum(case when s.duration_min < 1 then 1 else 0 end) as duration_under_1_min,
  sum(case when s.duration_min > 180 then 1 else 0 end) as duration_over_3_hours,
  sum(case when s.dropoff_at < s.pickup_at then 1 else 0 end) as dropoff_before_pickup,
  sum(case when pz.location_id is null or dz.location_id is null then 1 else 0 end) as unmatched_zones,
  sum(case when s.pickup_zone_id in (264, 265) or s.dropoff_zone_id in (264, 265) then 1 else 0 end) as unknown_zones,
  sum(case when s.trip_distance <= 0 then 1 else 0 end) as distance_nonpositive,
  sum(case when s.trip_distance > 100 then 1 else 0 end) as distance_over_100,
  sum(case when s.fare_amount < 0 then 1 else 0 end) as fare_negative,
  sum(case when s.passenger_count = 0 then 1 else 0 end) as passengers_zero,
  sum(case when to_char(s.pickup_at, 'YYYY-MM') <> s.trip_month then 1 else 0 end) as pickup_outside_month,
  percentile_cont(0.99) within group (order by s.duration_min) as p99_duration
from staging.stg_trips s
left join ingest.taxi_zones pz on pz.location_id = s.pickup_zone_id
left join ingest.taxi_zones dz on dz.location_id = s.dropoff_zone_id
where s.trip_month = '{month}'
"""

DUPLICATES_SQL = """
select coalesce(sum(n - 1), 0) as duplicate_rows from (
  select count(*) as n from staging.stg_trips where trip_month = '{month}'
  group by vendor_id, pickup_at, dropoff_at, pickup_zone_id, dropoff_zone_id, passenger_count,
           trip_distance, fare_amount, total_amount
  having count(*) > 1)
"""


def month_metrics(redshift: RedshiftData, month: str) -> dict:
    """Every number the rules need for one month: one scan, plus one for duplicates."""
    month = check_month(month)  # goes into SQL text
    row = redshift.query(METRICS_SQL.format(month=month))[0]
    metrics = {k: float(v) if v is not None else 0.0 for k, v in row.items()}
    metrics["duplicate_rows"] = float(redshift.scalar(DUPLICATES_SQL.format(month=month)) or 0)
    return metrics


def evaluate(metrics: dict) -> list[dg.AssetCheckResult]:
    results = []
    for rule in RULES:
        value = rule.measure(metrics)
        failed = rule.fails(value)
        results.append(
            dg.AssetCheckResult(
                check_name=rule.name,
                asset_key=stg_trips.key,
                passed=not failed,
                severity=rule.severity,
                description=f"{value:,.3f}: {rule.limit}" + (" (FAILED)" if failed else ""),
                metadata={"value": dg.MetadataValue.float(float(value))},
            )
        )
    return results


@dg.multi_asset_check(
    specs=[
        dg.AssetCheckSpec(
            rule.name,
            asset=stg_trips,
            blocking=rule.severity == ERROR,  # ERROR rules stop zone_hour_stats; WARN rules only show up
            partitions_def=trip_months,
            description=rule.limit,
        )
        for rule in RULES
    ],
    name="stg_trips_quality",
)
def stg_trips_quality(context: dg.AssetCheckExecutionContext, redshift: RedshiftData):
    yield from evaluate(month_metrics(redshift, context.partition_key))
