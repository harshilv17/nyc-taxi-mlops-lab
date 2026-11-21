# 003: Image tag scheme

Stage: S0 · Date: 2026-11-21 · Author: harshilv17 · Drafted by agent: yes

## Choice

Every build of `main` is pushed to GHCR under three tags on the same image:

- the full commit SHA, for example `app:3f5306c84b6943bbcf714d897b99d333e85b6dab`: immutable, and the only tag CD deploys;
- `sha-<first 7 characters>`, for example `app:sha-3f5306c`: the same image under a name people can read and type;
- `main`: a moving tag that always points at the newest build. Nothing deploys from it.

A rollback means deploying an older full-SHA tag, by re-running that commit's `cd` run. Because CD deploys by the full SHA, `/version` reports `image_tag` equal to `git_sha`.

## Rejected alternative

`latest` alone, or the moving tag alone. It is the simplest scheme, and the deploy command never changes. I rejected it because the running container wouldn't say which commit it came from (`/version` would show `main`), and rolling back would mean moving the tag by hand to an older image, which would also stop it pointing at the newest build.

Also considered: only `sha-<7>` (what this scheme started as: readable and the same format as the given platform workflow, but `image_tag` didn't match `git_sha` and 7 characters aren't guaranteed unique), only the full SHA (exact, but awkward for people to type), and semver release tags (needs a release step, and a version number doesn't tie to a commit by itself).

## Why

- The full-SHA tag ties each deployed image to exactly one commit, with no chance of a collision, and makes `image_tag == git_sha` a single equality check. The CD smoke test checks exactly that.
- The `sha-<7>` tag costs nothing extra (same image, one more name) and keeps a short handle for people, matching the format the given workflows use.
- Deploying by SHA makes rollback exact and repeatable, because the previous image is still in GHCR under its own tag.
- `main` gives a readable "newest" pointer, as long as nothing deploys from it.

## What would show this was wrong

- A deploy or rollback pulls the wrong build, which would mean the moving tag or the short tag is being used somewhere it shouldn't be.
- `/version` shows an `image_tag` that differs from `git_sha` (the CD smoke test fails on this).
- Three tags per image cause confusion in practice, for example someone rolls back by the short tag and it isn't what CD would have deployed.
- I need releases people can refer to by name, which would mean adding version tags.
