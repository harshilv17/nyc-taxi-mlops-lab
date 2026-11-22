# 014: Series budget

Stage: S5 · Date: 2026-11-22 · Author: harshilv17 · Drafted by agent: yes

> **TODO (author):** "Choice" is what I decided. "Rejected alternative", "Why" and "What would show this was wrong" are for me to write.

## Choice

- **Option B2, drop the noise** (`observability/alloy/budget.alloy`):
  - host: drop `node_(scrape|xfs|netstat|sockstat|timex|softnet|nf|schedstat|cooling)_.*`; keep cpu, memory, disk, filesystem, network, pressure and the rest;
  - containers: drop `container_fs_.*`; drop the labels `id`, `image` and `container_label_.*` (they change on every deploy; `name` doesn't, and keeps series apart);
  - services: drop `(python|go|process|scrape)_.*` and `.*_created`; keep `lab_*`, `traefik_*` and `up`.
- **Headroom:** stay at or under **5,000** active series (50% of the free tier's 10,000) for the rest of the day, including S6's LLM host.

## Rejected alternative

_To be written by the author._

## Why

_To be written by the author._

Facts from the time of drafting:

- **No rules (2026-11-22 11:16):** 3,252 series in Grafana (Alloy: app 1,817, platform 1,451). By job: cadvisor 894 + 806, unix 656 + 637, traefik 118, app 101, serving 40. Biggest families: `container_fs_*` 1,124, `node_network_*` 459, `container_memory_*` 195, `node_scrape_*` 184.
- **What reads what:** the given dashboard queries `lab_*`, `traefik_service_requests_total`, `node_cpu_seconds_total`, `container_memory_working_set_bytes`. Nothing in the repo queried the dropped families.
- **Per-deploy labels:** cAdvisor's `id` (container id), `image` (tag) and 19 `container_label_*` Compose labels, of which `config_hash`, `com_docker_compose_image` (digest), `replace`, `lab_static_config` and `image_version` change on a redeploy. Checked before dropping: no two series become identical without `id` and `image` (grouped per metric name).
- **With the rules (11:23):** Alloy app 873, platform 668.
- **Burst of deploys:** CD gained `workflow_dispatch` and `--force-recreate` (so a deploy of the same image is still a new container). Three dispatched deploys in a row (runs 45017550275, 45017598401, 45017655659; green, blue, green, all fb18b6f): Grafana 1,696 before (11:29), 1,695 after (11:32). Status run 45017807012: Alloy active series app 1,181, platform 668, `samples_failed` 0.
- **Options laid out:** B1, keep only what a panel or SLO queries (est. 350–450 for two hosts); B2; B3, drop only the per-deploy labels and `container_fs_*` (est. ~2,100). Headroom: ≤ 2,500, ≤ 5,000, ≤ 7,500.
- **S6:** no Alloy config for the LLM host yet; the same pattern as the other two hosts would add an estimated 650–800 series with these rules.

## What would show this was wrong

_To be written by the author._
