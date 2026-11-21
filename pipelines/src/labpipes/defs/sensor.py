"""S1: the S3 sensor (and the job it starts).

Watch trips/ in the data bucket (DataBucket.trip_files). When a month's file appears or changes, add
the month to the trip_months partitions and request a run that goes from trip_files to zone_hour_stats.
Patterns: pipelines/reference/patterns.py.

The cursor remembers each month's ETag, so a file is ingested once and again only if its bytes change.
run_key is month + ETag: asking twice for the same file version is a no-op. The sensor starts stopped
(Dagster's default): turn it on in the UI, and it loads whatever is in trips/ (S1: 2024-01..04).
"""

import json

import dagster as dg

from ..partitions import trip_months
from ..resources import DataBucket

# One month, end to end. zone_hour_stats is unpartitioned and rebuilt in full, so it is in the run: a
# month that fails a blocking check upstream never reaches the mart. taxi_zones is small and reloaded.
ingest_month = dg.define_asset_job(
    "ingest_month",
    selection=dg.AssetSelection.assets("taxi_zones", "trip_files", "raw_trips", "stg_trips", "zone_hour_stats"),
)


@dg.sensor(job=ingest_month, minimum_interval_seconds=60)
def trip_files_sensor(context: dg.SensorEvaluationContext, data_bucket: DataBucket):
    seen: dict[str, str] = json.loads(context.cursor or "{}")  # month -> ETag already requested
    landed = {f.month: f.etag for f in data_bucket.trip_files()}
    new_or_changed = sorted(m for m, etag in landed.items() if seen.get(m) != etag)
    if not new_or_changed:
        return dg.SkipReason("no new or changed trip files")
    known = set(context.instance.get_dynamic_partitions(trip_months.name))
    new_partitions = [m for m in new_or_changed if m not in known]
    return dg.SensorResult(
        run_requests=[dg.RunRequest(partition_key=m, run_key=f"{m}:{landed[m]}") for m in new_or_changed],
        dynamic_partitions_requests=[trip_months.build_add_request(new_partitions)] if new_partitions else [],
        cursor=json.dumps({**seen, **{m: landed[m] for m in new_or_changed}}),
    )
