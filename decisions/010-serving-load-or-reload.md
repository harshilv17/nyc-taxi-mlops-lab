# 010: Load at start-up or reload on alias change

Stage: S3 · Date: 2026-11-22 · Author: harshilv17 · Drafted by agent: yes

> **TODO (author):** "Choice" is what I decided. "Rejected alternative", "Why" and "What would show this was wrong" are for me to write.

## Choice

- **Option L2, reload:** after moving `champion`, `.github/workflows/promote.yaml` runs `deploy/web.sh reload champion` (POST `/reload` on serving-champion). The serving container keeps running; the old model answers until the new one has loaded. The job fails unless serving then reports the promoted version, and unless the public `/predict` answers with `alias: champion` and that version.
- **What may be promoted (option E2):** only the version holding `@challenger`, i.e. one the pipeline evaluated and that passed `beats_champion`. A version named in the run's input must be that one. The outgoing champion is recorded as tags on the new version (`replaced_champion`, `promoted_by`, `promoted_run`).

## Rejected alternative

_To be written by the author._

## Why

_To be written by the author._

Facts from the time of drafting:

- **Options laid out:** L1, recreate serving-champion so it loads `@champion` at start-up (while it loads, `/model` is 503, Traefik's health check drops it, and the app answers with the static median); L2, POST `/reload`.
- **The given serving code** loads at start-up and retries until the alias exists; once loaded it never changes on its own. `/reload` is serialized and swaps only after the new model has loaded.
- **First promotion (run 44994873846, 2026-11-22):** approved by harshilv17 in `production` after about 54 s of waiting; champion `none -> 2`; reload returned `{"version":"2","previous_version":null,"changed":true}` about 1.5 s after the alias moved; the public `/predict` answered `{"duration_minutes":63.95,"model":{"name":"trip-duration","version":"2","alias":"champion"}}` 2 s later. With no previous champion, riders got the static median until then under either option.
- **Model rollback:** under E2, promote.yaml can't point `champion` back at the `replaced_champion` version; a model rollback (S8) needs another path.

## What would show this was wrong

_To be written by the author._
