"""S1: the schema_contract check on trip_files.

Compare the landed file's Parquet footer (the DataBucket resource reads it) with
contracts/trips.schema.yaml, before raw_trips copies anything. contracts/platform.yaml says this check
is blocking. Patterns: pipelines/reference/patterns.py.

What counts as a mismatch (decisions/004-schema-mismatch.md):
- column count: must equal the contract's (Parquet COPY maps by position and fails otherwise);
- names: compared position by position, ignoring case;
- types: equal, or narrower than the contract's (a file's INT32 fits the contract's INT64 column;
  never the other way round);
- every difference is reported, not just the first.
"""

import dagster as dg

from ..contracts import Column, trips_schema
from ..partitions import trip_months
from ..resources import DataBucket
from .trip_files import trip_files

# (type in the file, type in the contract) pairs that still load safely into the contract's column.
NARROWER_OK = {("INT32", "INT64")}


def mismatches(expected: list[Column], got: list[Column]) -> list[str]:
    """Every way `got` (a file's columns) differs from `expected` (the contract), as readable lines."""
    found = []
    if len(got) != len(expected):
        found.append(f"column count: file has {len(got)}, contract has {len(expected)}")
    for i, (want, have) in enumerate(zip(expected, got, strict=False)):
        if have.name.lower() != want.name.lower():
            found.append(f"column {i}: name {have.name!r}, contract has {want.name!r}")
        if have.type != want.type and (have.type, want.type) not in NARROWER_OK:
            found.append(f"column {i} ({want.name}): type {have.type}, contract has {want.type}")
    for extra in got[len(expected) :]:
        found.append(f"extra column not in the contract: {extra.name} ({extra.type})")
    for missing in expected[len(got) :]:
        found.append(f"column missing from the file: {missing.name} ({missing.type})")
    return found


@dg.asset_check(
    asset=trip_files,
    partitions_def=trip_months,
    blocking=True,
    description="The file's Parquet footer matches contracts/trips.schema.yaml.",
)
def schema_contract(context: dg.AssetCheckExecutionContext, data_bucket: DataBucket) -> dg.AssetCheckResult:
    footer = data_bucket.footer(context.partition_key)
    found = mismatches(trips_schema(), footer.columns)
    return dg.AssetCheckResult(
        passed=not found,
        severity=dg.AssetCheckSeverity.ERROR,
        description="matches the contract" if not found else f"{len(found)} difference(s): " + "; ".join(found),
        metadata={"differences": dg.MetadataValue.json(found), "num_differences": dg.MetadataValue.int(len(found))},
    )
