# Runbook: restore the lab after a session end

Owner: harshilv17 · Last run: 2026-11-22 · Time to restore last run: 19 min (Start Lab to health.sh exit 0)

## When to use it

"The app quotes the static median (`model: static-median`) instead of the champion", or the first thing in a new Learner Lab session: hosts were stopped at the 4-hour mark, RDS, Redshift and the notebook were stopped at end of day.

## Before you start

- Start Lab, then paste AWS Details → AWS CLI into `~/.aws/credentials`. Exporting in one terminal doesn't reach other shells. The old session's keys still pass `sts get-caller-identity` but every other call is denied (`voc-cancel-cred`).
- `gh` logged in; `infra/live` initialised (`terraform init -backend-config=backend.hcl`).

## Steps

Triage at 07:04 UTC (Start Lab at 07:00:06, the hosts' launch time). Times are from the fix command to the check passing.

| # | Check (command) | Healthy looks like | If not: fix (command) | Took | Automated? |
| --- | --- | --- | --- | --- | --- |
| 0 | `scripts/health.sh` with the old session's credentials | every line has a real state | Start Lab, new credentials into `~/.aws/credentials`. With cancelled keys health.sh said `session OK`, printed no host lines and showed rds/redshift/notebook as `absent` | ~4 min (07:00 → 07:04) | no |
| 1 | `scripts/health.sh` (rds) | `OK rds available` | `aws rds start-db-instance --db-instance-identifier lab` | 2 min 49 s to "DB instance started" (07:05:56 → 07:08:45); `available` by 07:09:58 | no |
| 2 | `scripts/health.sh` (redshift) | `OK redshift available` | `aws redshift resume-cluster --cluster-identifier lab` (in parallel with 1) | 2 min 44 s (07:06:07 → 07:08:51) | no |
| 3 | `scripts/health.sh` (predict) | `OK predict trip-duration champion 2` | was `WARN ... static-median (fallback)`. Nothing: MLflow (`restart: unless-stopped`) and serving (retries `@champion` every 30 s) came back by themselves once RDS was up | by 07:09:34, ≤ 50 s after RDS started | yes, by itself |
| 4 | `docker exec platform-webserver-1 python -m labpipes.status` on the platform host (SSM) | JSON status, not `code location not loaded yet` | Didn't come back by itself: at 07:07:35 the code server's import of `labpipes.definitions` gave up (`too many retries for DB connection`, RDS refusing connections), the container stayed `healthy` holding the error, and webserver and daemon cached `Error loading repository location labpipes`. Fix: `docker restart platform-code-1 && docker restart platform-webserver-1 platform-daemon-1` (via `aws ssm send-command`) | found 07:15, fixed 19 s (07:18:27 → 07:18:46) | no |
| 5 | `scripts/health.sh` (status) | `OK status Dagster answered the status run 0 min ago` | `gh workflow run status.yaml`. First run (07:10) timed out on row 4; second run 44997666145 green at 07:19, RDS and Redshift `available` | ~1 min | no |
| 6 | `curl localhost:3000/server_info`, `curl localhost:5001/health` on the laptop | 200 | SSM port-forwarding tunnels die when the host stops: `aws ssm start-session --target <platform_instance_id> --document-name AWS-StartPortForwardingSession --parameters portNumber=3000,localPortNumber=3000` (MLflow: `portNumber=5000,localPortNumber=5001`) | ~10 s | no (laptop-only convenience; riders don't need it) |

Restored at 07:19 (health.sh exit 0): about 19 min after Start Lab, about 13 min after the RDS and Redshift start commands.

Came back by themselves at Start Lab: the three hosts (`running`, same Elastic IPs), the app and platform runners (`online`), the app answering `/predict` (with the fallback). Notebook `Stopped` is OK: nothing but exploration needs it.

## Done when

- `curl -X POST http://<app_public_ip>/predict ...` answers with `"alias": "champion"`.
- `scripts/health.sh` exits 0.
- `gh workflow run status.yaml` is green and reports RDS and Redshift `available`.

## What we automated, and what we left as a step

[decisions/012](../decisions/012-what-to-automate.md). Tomorrow:

1. A person: Start Lab, paste the credentials into `~/.aws/credentials` (row 0). Learner Lab has no API for it.
2. A person runs `scripts/restore.sh`: rows 1, 2 and 5 (starts RDS and Redshift only if stopped or paused, waits, runs the status workflow and `health.sh`).
3. The platform host's boot unit, `lab-platform-boot.service` (`deploy/platform-boot.sh`, installed with `deploy/platform-boot.sh install`): row 4. It waits until RDS accepts connections, then restarts Dagster's code server, webserver and daemon if the code location isn't loaded, at most 3 times. Its log: `journalctl -u lab-platform-boot` on the host.
4. Row 3 needs nothing.

Left as steps: Start Lab and credentials (no API); the notebook (nothing but exploration needs it, and it costs while running).
