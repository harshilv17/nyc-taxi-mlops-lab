"""The schema_contract check: what passes, what blocks, and that it reports everything it finds."""

import dagster as dg
from fakes import FakeBucket, schema_2023, schema_2025

from labpipes.contracts import Column, trips_schema
from labpipes.defs.schema_check import mismatches, schema_contract
from labpipes.defs.trip_files import trip_files
from labpipes.partitions import trip_months


def swap(cols, i, j):
    cols = list(cols)
    cols[i], cols[j] = cols[j], cols[i]
    return cols


def test_the_contract_matches_itself():
    assert mismatches(trips_schema(), trips_schema()) == []


def test_a_case_only_rename_passes():
    got = [Column(c.name.lower(), c.type) for c in trips_schema()]
    assert mismatches(trips_schema(), got) == []


def test_a_real_rename_or_a_swap_blocks():
    renamed = [Column("pickup_zone" if c.name == "PULocationID" else c.name, c.type) for c in trips_schema()]
    assert any("PULocationID" in m for m in mismatches(trips_schema(), renamed))
    assert mismatches(trips_schema(), swap(trips_schema(), 7, 8))  # PULocationID and DOLocationID trade places


def test_a_narrower_type_passes_a_wider_one_does_not():
    contract = trips_schema()
    i = next(i for i, c in enumerate(contract) if c.type == "INT64")  # passenger_count
    narrower = list(contract)
    narrower[i] = Column(contract[i].name, "INT32")
    assert mismatches(contract, narrower) == []
    j = next(j for j, c in enumerate(contract) if c.type == "INT32")  # VendorID
    wider = list(contract)
    wider[j] = Column(contract[j].name, "INT64")
    assert len(mismatches(contract, wider)) == 1


def test_an_extra_column_blocks_and_is_named():
    found = mismatches(trips_schema(), schema_2025())
    assert any("column count" in m for m in found) and any("cbd_congestion_fee" in m for m in found)


def test_a_missing_column_blocks_and_is_named():
    found = mismatches(trips_schema(), trips_schema()[:-1])
    assert any("Airport_fee" in m and "missing" in m for m in found)


def test_every_difference_is_reported_not_just_the_first():
    found = mismatches(trips_schema(), schema_2023())  # five type changes; the airport_fee casing is fine
    assert len(found) == 5 and not any("name" in m for m in found)


def run(month, files):
    """trip_files and its check for one month, on an ephemeral Dagster instance and a fake bucket."""
    bucket = FakeBucket(bucket="x", files=files)
    with dg.DagsterInstance.ephemeral() as instance:
        instance.add_dynamic_partitions(trip_months.name, [month])
        return dg.materialize(
            [trip_files, schema_contract],
            partition_key=month,
            resources={"data_bucket": bucket},
            instance=instance,
            raise_on_error=False,
        )


def test_the_check_is_blocking_and_a_drifted_file_fails_it():
    (spec,) = schema_contract.check_specs  # contracts/platform.yaml: blocking on trip_files
    assert (spec.name, spec.asset_key.to_user_string(), spec.blocking) == ("schema_contract", "trip_files", True)

    files = {
        "2024-01": ["a", [[c.name, c.type] for c in trips_schema()]],
        "2025-01": ["b", [[c.name, c.type] for c in schema_2025()]],
    }
    good = run("2024-01", files)
    assert good.success
    (ev,) = good.get_asset_check_evaluations()
    assert ev.passed

    bad = run("2025-01", files)
    (ev,) = bad.get_asset_check_evaluations()
    assert not ev.passed and "cbd_congestion_fee" in ev.description
