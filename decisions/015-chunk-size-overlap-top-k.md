# 015: Chunk size, overlap and top-k

Stage: S6 · Date: 2026-11-22 · Author: harshilv17 · Drafted by agent: yes

> **TODO (author):** "Choice" is what I decided. "Rejected alternative", "Why" and "What would show this was wrong" are for me to write.

## Choice

- **Chunk size 250 tokens, overlap 50 tokens** (`CHUNK_MAX_TOKENS`, `CHUNK_OVERLAP_TOKENS` in `pipelines/src/labpipes/defs/rag.py`; `labpipes/chunking.py` estimates tokens as words x 1.3).
- **Top-k = 3** (`TOP_K` in `app/src/rideapp/assistant.py`): the three chunks nearest the question by cosine distance go into the prompt.

## Rejected alternative

_To be written by the author._

## Why

_To be written by the author._

Facts from the time of drafting (the wiki on 2026-11-22: 16 published pages):

- **Page sizes (estimated tokens):** min 62, median 94, max 181, total 1,546.
- **Chunks produced, by setting:**

| max / overlap | chunks | tokens per chunk (median / max) |
|---|---|---|
| 150 / 0 | 17 | 91 / 160 |
| 150 / 30 | 17 | 91 / 160 |
| 250 / 50 | 16 | 96 / 188 |
| 400 / 50 and 600 / 100 | 16 | 96 / 188 |

- At 250 or more every page is one chunk, so overlap changes nothing today; at 150 the longest page splits in two.
- **Prompt cost:** the LLM host reads the prompt at about 13 tokens/s and writes at about 7.5 tokens/s (stages/S6.md), which makes a ~96-token chunk about 7 s of prompt reading (the handout says about 11 s per chunk); an uncached answer with 4 excerpts takes 45-70 s; the request timeout is 150 s (`LLM_TIMEOUT_SECONDS`).
- **Options laid out:** chunks 250/0, 150/30, 250/50; top-k 2, 3, 5.

## What would show this was wrong

_To be written by the author._
