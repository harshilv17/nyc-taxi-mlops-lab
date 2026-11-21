# 007: What stays in the notebook, and what moves into the pipeline

Stage: S2 · Date: 2026-11-21 · Author: harshilv17 · Drafted by agent: yes

> **TODO (author):** I haven't decided this yet. "Choice", "Rejected alternative", "Why" and "What would show this was wrong" are for me to write once I've used the notebook. Below is only what the repo does today.

## Choice

_To be written by the author._

## Rejected alternative

_To be written by the author._

## Why

_To be written by the author._

Facts from the time of drafting:

- **In the pipeline** (`pipelines/src/labpipes/defs/training.py`, the `train_model` job): extracting the window and holdout (`training_set`, UNLOAD to the artifact bucket), fitting v2 (`trained_model`), logging and registering it in MLflow with the contract's tags, evaluating it against the champion or the v1 baseline on the same holdout (`eval_report`), the blocking `beats_champion` gate, and setting `challenger`.
- **In the notebook** (`notebooks/explore.ipynb`, on the SageMaker instance `lab`): the backstory, a look at the data through the Redshift Data API, and the static median, v1 and v2 side by side on one holdout. It logs to its own MLflow experiment, `trip-duration-notebook`.
- **Rules the repo already sets:** only the pipeline registers model versions and sets `challenger`, and only behind the gate; a notebook never registers (`pipelines/AGENTS.md`, `contracts/mlflow.yaml`).
- **Shared code:** both use the same `tripmodel` package (`pipelines/src/tripmodel/`), so a model tried in the notebook is the model the pipeline trains.
- **Notebook clone:** SageMaker cloned the repo when the instance was created; newer commits need a `git pull` inside JupyterLab.

## What would show this was wrong

_To be written by the author._
