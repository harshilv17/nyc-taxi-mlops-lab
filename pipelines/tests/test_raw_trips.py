"""raw_trips: one transaction that copies a month into a temp table, deletes the month, inserts it."""

import dagster as dg
import pytest
from fakes import LOG, FakeRedshift, fake_bucket, fake_redshift

from labpipes.contracts import redshift_columns, trips_schema
from labpipes.defs.raw_trips import raw_trips
from labpipes.partitions import source_file, trip_months
from labpipes.sql import statements


EXECUTES: list[int] = []  # statements per execute() call; module-level, because runs rebuild resources from config


class CountingRedshift(FakeRedshift):
    """Counts execute() calls: the Data API runs one call's statements as one transaction."""

    def execute(self, *sqls: str) -> str:
        EXECUTES.append(len(sqls))
        return super().execute(*sqls)


def run(month, redshift):
    bucket = fake_bucket({month: ("etag", trips_schema())})
    with dg.DagsterInstance.ephemeral() as instance:
        instance.add_dynamic_partitions(trip_months.name, [month])
        return dg.materialize(
            [raw_trips],
            partition_key=month,
            resources={"redshift": redshift, "data_bucket": bucket},
            instance=instance,
        )


def at(sqls, start):
    return next(i for i, s in enumerate(sqls) if s.startswith(start))


def test_the_sql_is_filled_and_ordered():
    sqls = statements(
        "raw_trips", columns=redshift_columns(trips_schema()), uri="s3://data/trips/yellow_tripdata_2024-01.parquet",
        file=source_file("2024-01"),
    )
    assert not any("{" in s for s in sqls)
    # copy into the temp table first, then delete the month, then insert it
    assert at(sqls, "create temp table") < at(sqls, "copy") < at(sqls, "delete") < at(sqls, "insert")
    ddl = next(s for s in sqls if s.startswith("create table"))
    assert "diststyle even" in ddl and "sortkey (source_file)" in ddl and "source_file varchar(64) not null" in ddl
    assert "iam_role default format as parquet" in sqls[at(sqls, "copy")]


def test_a_month_loads_in_one_transaction():
    rs = CountingRedshift(cluster_id="lab", database="lab", db_user="labadmin")
    LOG.clear()
    EXECUTES.clear()
    result = run("2024-01", rs)
    assert result.success
    assert EXECUTES == [6]  # schema, table, temp table, copy, delete, insert: one call
    (event,) = result.get_asset_materialization_events()
    meta = event.materialization.metadata
    assert meta["source_file"].value == "yellow_tripdata_2024-01.parquet"
    assert "file_rows" in meta and "rows" in meta


def test_reloading_a_month_deletes_before_it_inserts_each_time():
    rs = fake_redshift()
    run("2024-01", rs)
    run("2024-01", rs)
    deletes = [i for i, s in enumerate(LOG) if s.startswith("delete from ingest.raw_trips")]
    inserts = [i for i, s in enumerate(LOG) if s.startswith("insert into ingest.raw_trips")]
    assert len(deletes) == len(inserts) == 2
    assert all(d < i for d, i in zip(deletes, inserts, strict=True))
    assert all("yellow_tripdata_2024-01.parquet" in LOG[i] for i in deletes + inserts)


def test_a_bad_month_never_reaches_the_sql():
    with pytest.raises(ValueError):
        source_file("2024-01'; drop table ingest.raw_trips; --")
