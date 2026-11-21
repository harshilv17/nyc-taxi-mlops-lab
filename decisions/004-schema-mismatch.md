# 004: What counts as a schema mismatch

Stage: S1 · Date: 2026-11-21 · Author: harshilv17 · Drafted by agent: yes

> **TODO (author):** only "Choice" comes from my decisions (A1, B2, C1). "Rejected alternative" and "Why" were guessed by the agent, so replace them with what I actually weighed before relying on this record.

## Choice

The blocking `schema_contract` check on `trip_files` compares a landed file's Parquet footer with `contracts/trips.schema.yaml` position by position, before anything is copied:

- **Column count** must equal the contract's. Parquet COPY maps columns by position and fails on a different count, so this isn't negotiable.
- **Names** must match, ignoring case. `airport_fee` passes for `Airport_fee`; a real rename, or two columns trading places, fails.
- **Types** must be equal, or narrower than the contract's: a file's `INT32` fits a contract `INT64` column. A wider type (`INT64` in an `INT32` column) or any other change fails. The allowed pairs are one constant, `NARROWER_OK`, in `schema_check.py`.
- A failure lists **every** difference it finds, not just the first.

## Rejected alternative

Exact types (a file's type must equal the contract's, no widening). It is simpler and stricter, and it never lets a type through that I haven't looked at. I rejected it because a harmless change, like a column becoming `INT64` where the table is already `BIGINT`, would block a whole month for no real risk, and I'd rather define one narrow, explicit "safe" case than treat every type change as an incident.

Also considered: ignoring names and checking only types and count (rejected because COPY maps by position, so two same-typed columns swapping places would load shifted data without any error), and stopping at the first difference (rejected because a drifted file may have several problems, and one run should show them all).

## Why

- Positional COPY never sees names, so the name check is the only thing that catches a swap or a rename with unchanged types.
- Case-insensitive names follow the contract's own note: TLC renamed `airport_fee` to `Airport_fee` in 2023, which positional COPY doesn't care about.
- Widening is allowed in one direction only, because the target column's type comes from the contract. A narrower file value fits it; a wider one could overflow.
- Evidence at the time: all four landed files (2024-01 to 2024-04, 2.96 to 3.58 million rows each) match the contract exactly, so the rule is about future files and gameday's drifted ones, not about today's data.

## What would show this was wrong

- Redshift's Parquet COPY rejects an `INT32` file column into a `BIGINT` table column. I haven't verified that it accepts it. If it doesn't, `NARROWER_OK` should be emptied.
- A month passes the check and still loads wrong or fails in COPY, which would mean the rule lets something through that it shouldn't.
- A month is blocked for a difference that turns out to be harmless, which would mean the rule is too strict.
- The contract has to evolve (for example when TLC adds a column, gameday E4a). That is a decision to record and defend, not a fix to this check.
