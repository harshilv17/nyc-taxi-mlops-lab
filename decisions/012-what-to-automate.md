# 012: What to automate after a session end, and what to leave as a step

Stage: S4 · Date: 2026-11-22 · Author: harshilv17 · Drafted by agent: yes

> **TODO (author):** "Choice" is what I decided. "Rejected alternative", "Why" and "What would show this was wrong" are for me to write.

## Choice

**Option A3, both, triggered by a person:**

- `scripts/restore.sh`, run by a person after Start Lab: starts RDS if stopped and resumes Redshift if paused, waits until both are available, runs the status workflow and `scripts/health.sh`.
- A boot-time systemd unit on the platform host (`deploy/platform-boot.sh`, `lab-platform-boot.service`): once RDS accepts TCP connections, restarts Dagster's code server, webserver and daemon if the code location isn't loaded; at most 3 restarts.
- **Trigger for starting paid resources:** only a person running `scripts/restore.sh`. The boot unit waits for RDS; it never starts it.
- **Never on their own:** stop, pause or delete anything; start the notebook; run terraform; move a model alias; restart containers without limit; touch MLflow or serving.
- **Left as steps:** Start Lab and the credentials (no API); the notebook.

## Rejected alternative

_To be written by the author._

## Why

_To be written by the author._

Facts from the restore on 2026-11-22 (runbooks/restore.md):

- **Start Lab 07:00:06, health.sh exit 0 at 07:19**: about 19 min, about 13 min after the start commands.
- **RDS** 2 min 49 s to started (07:05:56 → 07:08:45), `available` by 07:09:58; **Redshift** 2 min 44 s (07:06:07 → 07:08:51), started in parallel.
- **Came back by themselves:** hosts and runners at Start Lab; MLflow (`restart: unless-stopped`) and serving (retries `@champion` every 30 s): champion answering by 07:09:34.
- **Didn't:** Dagster. At 07:07:35, a minute before RDS was up, the code server's import gave up (`too many retries for DB connection`); its health check stayed `healthy`, and the webserver and daemon kept `Error loading repository location labpipes`. Found at 07:15 from the status run's "code location not loaded yet"; `docker restart` of the three containers fixed it in 19 s.
- **health.sh with a cancelled session** said `session OK`, printed no host lines and showed RDS, Redshift and the notebook as `absent`.
- **Options laid out:** A1, the laptop script only (also restarting Dagster over SSM); A2, the boot unit only, starting RDS and Redshift left as steps; A3, both. Triggers: a person runs it; the host starts RDS and Redshift at boot with LabRole; nothing starts them.

## What would show this was wrong

_To be written by the author._
