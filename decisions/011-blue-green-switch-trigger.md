# 011: What triggers the blue-green switch

Stage: S3 · Date: 2026-11-22 · Author: harshilv17 · Drafted by agent: yes

> **TODO (author):** "Choice" is what I decided. "Rejected alternative", "Why" and "What would show this was wrong" are for me to write.

## Choice

**Option T2, automatic after the existing checks:** `.github/workflows/cd.yaml` deploys each commit on main (after `ci` passes) to the idle colour and switches traffic to it with no human step, once every check below passes against that colour (pinned through Traefik with `X-Lab-Color`):

- `deploy/web.sh smoke`: `/version` reports this commit, and `/predict` answers;
- `/version`'s `image_tag` is this commit;
- `/predict` quotes a positive duration;
- `/predict` with an invalid zone (9999) is rejected with 422.

Only checks that already existed were used; none were added. Rolling back is `.github/workflows/rollback.yaml` (manual, `workflow_dispatch`), which smoke-tests the other colour and switches to it.

## Rejected alternative

_To be written by the author._

## Why

_To be written by the author._

Facts from the time of drafting:

- **Which colour is live** is kept in the `lab-traefik` Docker volume on the app host, not in the repo. `cd.yaml` and `rollback.yaml` share the concurrency group `app-colours`.
- **First deploy with the stack** (26f9abd): blue went live; green had nothing. The gap during Traefik's config change was not measured.
- **Second deploy** (af49fb6, CD 2026-11-22): blue -> green; traffic answered with the new commit 2 s after the switch was written.
- **Rollback** (run 44995160599): green -> blue (26f9abd) in 3.12 s, from writing the switch to `/version` answering with blue's tag (polled every 1 s).
- **What the checks don't cover:** model quality (serving is shared by both colours), latency, and anything other than one fixed trip.

## What would show this was wrong

_To be written by the author._
