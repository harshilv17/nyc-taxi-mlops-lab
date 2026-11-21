# 009: Training window

Stage: S2 · Date: 2026-11-21 · Author: harshilv17 · Drafted by agent: yes

> **TODO (author):** "Choice" is what I decided. "Rejected alternative", "Why" and "What would show this was wrong" are for me to write.

## Choice

**Option W1, fixed months:** train on **2024-01..2024-03**, evaluate on **2024-04**, the month after the window. The months are constants in `pipelines/src/labpipes/defs/training.py` (`TRAIN_FIRST`, `TRAIN_LAST`, `HOLDOUT_MONTH`); they don't move when a new month lands. The zone-pair distance lookup (`est_distance_miles`) is built from the window only.

## Rejected alternative

_To be written by the author._

## Why

_To be written by the author._

Facts from the time of the decision:

- **Months available:** 2024-01 to 2024-04 only, so testing on the month after the window allows at most three training months.
- **v1 baseline MAE by window** (computed in Redshift, on the same holdout rows the pipeline uses):

| Train on | Test on | v1 MAE | Static 12.25 MAE |
|---|---|---|---|
| 2024-01..03 | 2024-04 | 3.956 | 8.606 |
| 2024-02..03 | 2024-04 | 3.958 | 8.606 |
| 2024-03 | 2024-04 | 4.015 | 8.606 |
| 2024-01..02 | 2024-03 | 3.901 | 8.448 |
| 2024-01 | 2024-02 | 3.785 | 7.955 |

- **v2 on this window:** trained on 9,452,562 rows; April MAE 3.637 (v1: 3.956).
- **Elsewhere in the repo:** `drift.py` uses the three months before a month as its reference when there's no champion, and calls three months "training.py's default window"; once there is a champion it reads the champion's `training_window` tag instead.
- **Fixed, not a rule:** when a 2024-05 file lands, training keeps using 2024-01..03 and 2024-04 until the constants are edited.

## What would show this was wrong

_To be written by the author._
