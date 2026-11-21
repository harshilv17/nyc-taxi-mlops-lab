"""S2: the feature_contract check on trip_features.

contracts/features.yaml lists the model's inputs, label and the post-trip columns that must never be
inputs; contracts/mlflow.yaml says this check blocks. Decide what "matches" means: column names,
types, value ranges. Gameday E1 will test it.

What "matches" means (the author's choices: exact columns, compatible types, zero-tolerance ranges): the table's columns are exactly the contract's
(key, inputs, label: nothing missing, nothing extra, no forbidden column); types are compatible (any
integer width for an integer column, float for float, text for text); and no row of the month is
outside a range (zero tolerance: a null counts as outside). Every problem is reported, not just the first.
"""

import re

import dagster as dg

from ..contracts import features_contract
from ..partitions import check_month, trip_months
from ..resources import RedshiftData
from .features import trip_features

COLUMNS_SQL = (
    "select column_name, data_type from svv_columns "
    "where table_schema = '{schema}' and table_name = '{table}' order by ordinal_position"
)

# Type families: a column of one family may be any type in it. Anything else must match exactly.
FAMILIES = {
    "smallint": "integer", "integer": "integer", "bigint": "integer",
    "double precision": "float", "real": "float",
    "char": "text", "character": "text", "varchar": "text", "character varying": "text",
}


def family(sql_type: str) -> str:
    t = re.sub(r"\(.*?\)", "", sql_type.strip().lower())
    return FAMILIES.get(t, t)


def expected_columns(contract: dict) -> dict[str, dict]:
    """name -> contract entry, for the key(s), the inputs and the label (derived inputs aren't columns)."""
    return {c["name"]: c for c in [*contract["keys"], *contract["inputs"], contract["label"]]}


def structure_problems(contract: dict, table: list[tuple[str, str]]) -> list[str]:
    """Columns that are missing, extra, forbidden, or of an incompatible type."""
    want, have = expected_columns(contract), dict(table)
    forbidden = set(contract["forbidden"])
    found = []
    for name in sorted(have):
        if name in forbidden:
            found.append(f"forbidden column present: {name} (known only after the trip)")
        elif name not in want:
            found.append(f"extra column not in the contract: {name}")
    found += [f"missing column: {name}" for name in sorted(set(want) - set(have))]
    for name, c in want.items():
        if name in have and family(have[name]) != family(c["type"]):
            found.append(f"column {name}: type {have[name]}, contract has {c['type']}")
    return found


def ranged(contract: dict) -> list[dict]:
    return [c for c in [*contract["inputs"], contract["label"]] if "range" in c]


def in_range(c: dict) -> str:
    lo, hi = c["range"]
    return f"{c['name']} {'>' if c.get('exclusive_min') else '>='} {lo} and {c['name']} <= {hi}"


def range_sql(contract: dict, month: str, present: set[str]) -> str | None:
    """One scan of the month: how many rows are outside each range (null counts as outside)."""
    cols = [c for c in ranged(contract) if c["name"] in present]
    if not cols:
        return None
    sums = ", ".join(f"sum(case when {c['name']} is null or not ({in_range(c)}) then 1 else 0 end) as {c['name']}" for c in cols)
    return f"select count(*) as rows, {sums} from {contract['table']} where trip_month = '{check_month(month)}'"


def range_problems(contract: dict, counts: dict) -> list[str]:
    found = []
    for c in ranged(contract):
        n = int(counts.get(c["name"]) or 0)
        if n:
            lo, hi = c["range"]
            found.append(f"column {c['name']}: {n:,} row(s) outside {'(' if c.get('exclusive_min') else '['}{lo}, {hi}] or null")
    return found


@dg.asset_check(
    asset=trip_features,
    partitions_def=trip_months,
    blocking=True,
    description="staging.trip_features has exactly contracts/features.yaml's columns, and every row is in range.",
)
def feature_contract(context: dg.AssetCheckExecutionContext, redshift: RedshiftData) -> dg.AssetCheckResult:
    contract = features_contract()
    schema, table = contract["table"].split(".")
    columns = [(r["column_name"], r["data_type"]) for r in redshift.query(COLUMNS_SQL.format(schema=schema, table=table))]
    problems = structure_problems(contract, columns)
    rows = None
    sql = range_sql(contract, context.partition_key, {name for name, _ in columns})
    if sql:  # the columns that exist are range-checked even when the structure is already wrong
        counts = redshift.query(sql)[0]
        rows = int(counts["rows"])
        problems += range_problems(contract, counts)
    return dg.AssetCheckResult(
        passed=not problems,
        severity=dg.AssetCheckSeverity.ERROR,
        description="matches the contract" if not problems else f"{len(problems)} problem(s): " + "; ".join(problems),
        metadata={"problems": dg.MetadataValue.json(problems), "rows": dg.MetadataValue.int(rows or 0)},
    )
