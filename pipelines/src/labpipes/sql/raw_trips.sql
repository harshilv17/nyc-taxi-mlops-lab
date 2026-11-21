-- ingest.raw_trips for one month: the landed file, column for column, plus the file it came from.
-- Runs as one transaction, so a failed COPY rolls the delete back and a month is never half loaded.
-- Parquet COPY maps columns by position (the schema_contract check guards that), and the file has no
-- source_file column, so the month is copied into a temp table first and inserted with its file name.
-- Reloading a month deletes its rows before inserting them, so it never duplicates.
-- {columns}, {uri} and {file} are substituted after validation (batch statements take no parameters).
create schema if not exists ingest;
create table if not exists ingest.raw_trips (
  source_file varchar(64) not null,
  {columns}
) diststyle even sortkey (source_file);
create temp table raw_stage ({columns});
copy raw_stage from '{uri}' iam_role default format as parquet;
delete from ingest.raw_trips where source_file = '{file}';
insert into ingest.raw_trips select '{file}', * from raw_stage;
