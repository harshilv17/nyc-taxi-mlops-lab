# 003: Image tag scheme

Stage: S0 · Date: 2026-11-21 · Author: harshilv17 · Drafted by agent: yes

## Choice

Every build of `main` is pushed to GHCR under two tags: an immutable SHA tag, `sha-<first 7 characters of the commit>`, and a moving tag, `main`, that always points at the newest build. CD deploys by the SHA tag, never by `main`. A rollback means deploying an older SHA tag.

## Rejected alternative

`latest` alone, or the moving tag alone. It is the simplest scheme, and the deploy command never changes. I rejected it because the running container wouldn't say which commit it came from (`/version` would show `main`), and rolling back would mean moving the tag by hand to an older image, which would also stop it pointing at the newest build.

Also considered: semver release tags (needs a release step, and a tag doesn't tie to a commit by itself), and the bare git SHA without a moving tag (the same traceability, but no convenient pointer for people).

## Why

- A SHA tag ties each deployable image to exactly one commit, and the app already reports it: `/version` returns `git_sha` (baked in at build) and `image_tag` (from Compose).
- Deploying by SHA makes rollback exact and repeatable, because the previous image is still in GHCR under its own tag.
- `main` costs one extra tag at build time and gives people a readable "newest" pointer, as long as nothing deploys from it.
- The 7-character `sha-` form matches the tag format in the given platform workflow.

## What would show this was wrong

- A deploy or rollback pulls the wrong build, which would mean the moving tag is being used somewhere it shouldn't be.
- `/version` shows an `image_tag` that doesn't match the commit I think is live.
- Two commits share the same 7-character prefix, so the short SHA isn't unique enough and I'd need the full SHA.
- I need releases people can refer to by name, which would mean adding version tags.
