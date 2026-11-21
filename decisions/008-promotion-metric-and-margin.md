# 008: Promotion metric and margin

Stage: S2 · Date: 2026-11-21 · Author: harshilv17 · Drafted by agent: yes

> **TODO (author):** the margin X and the latency budget are not decided yet, and "Rejected alternative", "Why" and "What would show this was wrong" are for me to write.

## Choice

- **Metric: option M2, an absolute margin.** A new version becomes `challenger` only if its holdout MAE is at least **X minutes** below the champion's, or below the v1 baseline's before there is a champion, measured on the same holdout.
- **And a latency budget:** its p95 single-row predict time must be at most **L ms**.
- **X = _not decided yet_, L = _not decided yet_.** They are `MARGIN_MIN` and `LATENCY_BUDGET_MS` in `pipelines/src/labpipes/defs/training.py`. While either is unset, the `beats_champion` gate fails closed: the pipeline still trains, registers and measures, but sets no `challenger`.

## Rejected alternative

_To be written by the author._

## Why

_To be written by the author._

Facts from the time of drafting: the first `train_model` run on the platform (v2 = model version 1, trained on 2024-01..03, 9,452,562 rows; tested on all of 2024-04, 3,476,146 rows):

| | v2 (version 1) | v1 baseline | Difference |
|---|---|---|---|
| MAE overall (min) | 3.637 | 3.956 | v2 better by 0.319 (8.1%) |
| Airport | 5.976 | 6.724 | 0.748 |
| Manhattan | 3.154 | 3.341 | 0.187 |
| Outer boroughs | 7.404 | 9.193 | 1.789 |
| Night | 2.618 | 2.872 | 0.254 |
| p95 single-row latency | 3.82 ms | | measured on the platform host |

Scales of noise, from the v1 baseline computed in Redshift: changing its training window from one month to three moved its April MAE by 0.06 min; the same v1 scored 3.785, 3.901 and 3.956 on February, March and April holdouts (a 0.17 min swing between months). The gate compares both models on the same holdout, so the month-to-month swing doesn't enter the comparison itself.

Before the margin was set, the gate reported: "not decided yet... Measured v1: MAE 3.637 vs v1 baseline 3.956 (better by 0.319 min), p95 latency 3.82 ms", and no `challenger` was set.

## What would show this was wrong

_To be written by the author._
