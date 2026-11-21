# 002: Runner credentials

Stage: S0 · Date: 2026-11-21 · Author: harshilv17 · Drafted by agent: yes

## Choice

The self-hosted runner on the app host uses the host's instance profile (`LabInstanceProfile`, which carries `LabRole`) for any AWS access. No AWS keys or session tokens are stored in GitHub secrets. Image pulls and pushes use `GITHUB_TOKEN`.

## Rejected alternative

Static Learner Lab session credentials (access key, secret key, session token) copied into GitHub repository secrets and injected into the deploy workflow. It would let the same workflow work on any runner, including GitHub-hosted ones. I rejected it because of the points below.

## Why

- The repo is public. Credentials in GitHub secrets are one workflow mistake or log leak away from exposure, and they would carry `LabRole` permissions.
- Learner Lab session credentials expire when the lab session ends, so deploys would break until I refreshed the secrets by hand after every restart.
- The instance profile gives the runner temporary credentials that rotate automatically, with nothing stored in GitHub and nothing to refresh.
- The host module already attaches `LabInstanceProfile`, so this needs no extra setup.
- Trade-off I accept: any job that runs on this host can use the host's `LabRole` permissions. I limit that by never triggering self-hosted workflows from `pull_request` or `pull_request_target`, and by requiring approval for all external contributors on fork PRs (`make check` enforces the first rule).

## What would show this was wrong

- A job on the runner uses `LabRole` in a way I didn't intend, or an unapproved workflow ran on the host.
- I need separate permissions for different jobs, which one shared instance profile can't give.
- CD has to run somewhere other than the app host, so there is no instance profile to rely on.
- The metadata service is unreachable from a deploy container (the hop limit is 2 on these hosts), and jobs fail to get credentials.
