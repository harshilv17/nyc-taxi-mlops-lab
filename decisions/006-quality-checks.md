# 006: Data-quality checks on stg_trips: what blocks, and every threshold

Stage: S1 · Date: 2026-11-21 · Author: harshilv17 · Drafted by agent: yes

> **TODO (author):** "Choice" is my table, as I decided it. "Rejected alternative" and "Why" are left for me to write in my own words before relying on this record.

## Choice

Sixteen checks on `stg_trips`, one scan per month. A failing **ERROR** rule blocks `zone_hour_stats`, so the mart isn't rebuilt with that month. A failing **WARN** rule shows on the check and the run still succeeds. A limit is crossed when the value is strictly above it (the row count must be inside its range).

| Check | Severity | Threshold |
|---|---|---|
| Monthly row count | ERROR | below 2M or above 5M rows |
| `passenger_count` null | WARN | > 15% |
| `ratecode_id` null | WARN | > 15% |
| Duration ≤ 0 min | ERROR | > 0.10% |
| Duration < 1 min | WARN | > 2.5% |
| Duration > 3 hours | WARN | > 0.20% |
| Dropoff before pickup | ERROR | > 200 rows |
| Unmatched zone IDs (not in `ingest.taxi_zones`) | ERROR | > 0 rows |
| Zone IDs 264 / 265 | WARN | > 2% |
| Distance ≤ 0 | WARN | > 4% |
| Distance > 100 miles | WARN | > 300 rows |
| Negative fare | WARN | > 3% |
| Passenger count = 0 | WARN | > 2.5% |
| Pickup outside the source month | WARN | > 100 rows |
| Exact duplicate rows (extra copies) | ERROR | > 10 rows |
| P99 trip duration | WARN | > 90 minutes |

## Rejected alternative

_To be written by the author._

## Why

_To be written by the author._

Facts from the time of the decision, measured in Redshift on the four real months (2024-01 to 2024-04), all of which pass every rule:

| Check | 2024-01 | 2024-02 | 2024-03 | 2024-04 |
|---|---|---|---|---|
| Rows | 2.96 M | 3.01 M | 3.58 M | 3.51 M |
| `passenger_count` and `ratecode_id` null | 4.7% | 6.2% | 11.9% | 11.6% |
| Duration ≤ 0 min | 0.029% | 0.027% | 0.031% | 0.031% |
| Duration < 1 min | 1.18% | 1.12% | 1.13% | 1.14% |
| Duration > 3 hours | 0.067% | 0.065% | 0.061% | 0.064% |
| Dropoff before pickup (rows) | 56 | 7 | 117 | 70 |
| Zone IDs 264 / 265 | 1.06% | 0.96% | 0.99% | 1.02% |
| Distance ≤ 0 | 2.04% | 2.27% | 2.43% | 1.30% |
| Distance > 100 miles (rows) | 59 | 71 | 122 | 150 |
| Negative fare | 1.26% | 1.35% | 1.63% | 1.64% |
| Passenger count = 0 | 1.06% | 1.13% | 1.13% | 1.13% |
| Pickup outside the month (rows) | 18 | 15 | 23 | 9 |
| Exact duplicate rows | 0 | 1 | 0 | 0 |
| P99 duration (min) | 60 | 62 | 67 | 68 |

Unmatched zone IDs were 0 in every month. The null rate of `passenger_count` and `ratecode_id` more than doubled between January and March with no sign of corruption, and the row count rose 19% from February to March.

## What would show this was wrong

_To be written by the author._
