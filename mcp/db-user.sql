-- The MCP server's database user (S7, decision 018). Run once as labadmin, one statement per line:
--   jq -R -s -c 'split("\n") | map(select(length > 0 and (startswith("--") | not)))' mcp/db-user.sql
-- The user has no password: it connects with IAM temporary credentials through the Data API (--db-user).
-- It reads marts.zone_hour_stats and nothing else. The mart's refresh (pipelines/.../zone_hour_stats.sql)
-- is delete + insert into a CREATE TABLE IF NOT EXISTS table, so the grants below survive every refresh;
-- the default privileges also cover a mart table created later by labadmin.
create user lab_ro password disable
grant usage on schema marts to lab_ro
grant select on marts.zone_hour_stats to lab_ro
alter default privileges for user labadmin in schema marts grant select on tables to lab_ro
