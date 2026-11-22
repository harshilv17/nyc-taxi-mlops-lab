# 018: Database role scope

Stage: S7 · Date: 2026-11-22 · Author: harshilv17 · Drafted by agent: yes

> **TODO (author):** "Choice" is what I decided. "Rejected alternative", "Why" and "What would show this was wrong" are for me to write.

## Choice

The MCP server's Redshift user is **`lab_ro`** (`mcp/db-user.sql`, run once as `labadmin`): no password (it connects with IAM temporary credentials through the Data API), `usage` on schema `marts`, `select` on `marts.zone_hour_stats`, and default privileges so `select` on tables `labadmin` creates later in `marts`. Nothing on `ingest` or `staging`, and no write or create privilege anywhere.

## Rejected alternative

_To be written by the author._

## Why

_To be written by the author._

Facts from the time of drafting:

- **What `lab_ro` could and couldn't do (each tried as `lab_ro` through the Data API, 2026-11-22):**

| Attempt | Result |
|---|---|
| `select count(*) from marts.zone_hour_stats` | FINISHED (5,801 rows) |
| `insert into marts.zone_hour_stats ...` | permission denied for relation zone_hour_stats |
| `delete from marts.zone_hour_stats` | permission denied for relation zone_hour_stats |
| `drop table marts.zone_hour_stats` | permission denied for relation zone_hour_stats |
| `create table marts.x (a int)` | permission denied for schema marts |
| `select count(*) from ingest.taxi_zones` | permission denied for schema ingest |
| `select count(*) from staging.stg_trips` | permission denied for schema staging |
| `create user evil password disable` | must be superuser or have CREATE USER system privilege |

- **Mart refresh:** `zone_hour_stats.sql` is `delete` + `insert` into a table created with `CREATE TABLE IF NOT EXISTS` (`contracts/marts.sql`), so it neither drops the table nor resets its grants. After running those statements as `labadmin` (`refreshed_at` 12:48:58 UTC), `lab_ro` still read 5,801 rows.
- **Status check:** the MCP server's `/healthz?db=1` (run 45024329931, MCP workflow) reported `{"read_marts": true, "write_marts": false, "use_ingest": false, "create_in_marts": false}`.
- **Setup used `labadmin`:** creating the user and grants ran as `labadmin` through the Data API, once; the MCP server runs only as `lab_ro` (`MCP_DB_USER`).
- **Not covered by these tests:** a read through the Data API's cluster-level access (any caller with `redshift-data:ExecuteStatement` on `LabRole` can name any `--db-user`, so `LabRole` itself is not limited to `lab_ro`).

## What would show this was wrong

_To be written by the author._
