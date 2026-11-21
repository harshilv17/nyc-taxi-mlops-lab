# 005: COPY vs Spectrum, and the keys of ingest.raw_trips

Stage: S1 · Date: 2026-11-21 · Author: harshilv17 · Drafted by agent: yes

> **TODO (author):** "Choice" is what I decided. "Rejected alternative" and "Why" are left for me to write in my own words before relying on this record.

## Choice

- **COPY, not Spectrum:** each month's Parquet file is loaded into the Redshift table `ingest.raw_trips`. The files are not queried in place.
- **`DISTSTYLE EVEN`** (distribution, option D1).
- **`SORTKEY (source_file)`** (sort, option S1).
- **Idempotent reload by delete then insert**, in one transaction: the month is copied into a temp table, then that month's rows are deleted from `raw_trips` and inserted from the temp table, so a failed COPY rolls the delete back.

Implemented in `pipelines/src/labpipes/sql/raw_trips.sql` and `defs/raw_trips.py`.

## Rejected alternative

_To be written by the author._

## Why

_To be written by the author._

Facts from the time of the decision:

- **Data:** four landed files, 2024-01 to 2024-04, 209 MB of Parquet, 2.96 to 3.58 million rows each (13.07 million in total).
- **Cluster:** one `ra3.large` node, so distribution has no cross-node data to move.
- **How the table is read:** `stg_trips.sql` (given) reads `ingest.raw_trips` with `where source_file = '<file>'`, one month at a time, and a reload deletes by the same column.
- **Profile of the files** (from the Parquet columns, before loading): rows are not in pickup-time order (about 56% of neighbouring rows go forward in time); 9 to 23 rows per file have a pickup date outside the file's month; pickup zones are spread over 254 to 260 values, the busiest at 4.6% to 4.9% of rows and the top 10 at 37% to 39%.
- **After loading:** `ingest.raw_trips` is 1,688 MB on the cluster (1.7 GB for 209 MB of Parquet), with `EVEN` distribution and `source_file` as the sort key. `stg_trips` is 650 MB.
- **Reload overhead:** right after reloading 2024-01 a second time, `svv_table_info` showed 5.93 million rows for `raw_trips` against 2.96 million real ones, because rows deleted by a reload stay counted until a vacuum. Later, after all four months had been reloaded, it showed 13,069,067, exactly the real count, so Redshift's automatic vacuum had cleaned them up. `select count(*)` was exact throughout.
- **Time:** the four whole `ingest_month` runs (all five assets, the checks, and two runs at a time) took 125, 137, 166 and 165 seconds. That is not the COPY alone.
- **Not tried:** Spectrum. I did not create an external table or measure a query against the files in place, so I have no numbers for it.

## What would show this was wrong

_To be written by the author._
