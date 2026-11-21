"""S1: the raw_trips asset.

One partition per month (partitions.trip_months), depending on trip_files. COPY the month's file into
Redshift with the LabRole attached to the cluster (`iam_role default`), so that re-running a month never
duplicates its rows. The landing columns come from contracts/trips.schema.yaml
(contracts.redshift_columns). Decision points: COPY vs Spectrum; dist and sort keys.

Choices (decisions/): COPY, not Spectrum; DISTSTYLE EVEN and SORTKEY (source_file); a reload deletes the
month's rows and inserts them again, in one transaction (sql/raw_trips.sql).
"""

import dagster as dg

from ..contracts import redshift_columns, trips_schema
from ..partitions import source_file, trip_months
from ..resources import DataBucket, RedshiftData
from ..sql import statements


@dg.asset(partitions_def=trip_months, deps=["trip_files"], group_name="ingest", kinds={"redshift"}, pool="redshift")
def raw_trips(context: dg.AssetExecutionContext, redshift: RedshiftData, data_bucket: DataBucket) -> dg.MaterializeResult:
    month = context.partition_key
    file = source_file(month)  # validates the month before it goes into SQL
    # One execute() call is one transaction: temp table, COPY, delete the month, insert it.
    redshift.execute(
        *statements("raw_trips", columns=redshift_columns(trips_schema()), uri=data_bucket.trip_uri(month), file=file)
    )
    rows = redshift.scalar(f"select count(*) from ingest.raw_trips where source_file = '{file}'")
    return dg.MaterializeResult(
        metadata={
            "rows": dg.MetadataValue.int(int(rows)),
            "file_rows": dg.MetadataValue.int(data_bucket.footer(month).num_rows),  # what the file's footer says
            "source_file": file,
        }
    )
