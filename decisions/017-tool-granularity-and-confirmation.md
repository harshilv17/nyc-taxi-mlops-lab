# 017: Tool granularity and confirmation

Stage: S7 · Date: 2026-11-22 · Author: harshilv17 · Drafted by agent: yes

> **TODO (author):** "Choice" is what I decided. "Rejected alternative", "Why" and "What would show this was wrong" are for me to write.

## Choice

- **The assistant may call all three tools** (`ALLOWED_TOOLS` in `app/src/rideapp/assistant.py`): `get_model_info`, `predict_duration`, `query_zone_stats`. All three are read-only.
- **No tool needs a person to confirm** before it runs.
- **Zone rule in `allow_tool_call` (option "word match"):** a call that names a zone (`pickup_zone`, `dropoff_zone`, `zone`) runs only if a word of 4+ letters from that zone's name is also a word of the rider's question; a zone with no such word must appear whole.

## Rejected alternative

_To be written by the author._

## Why

_To be written by the author._

Facts from the time of drafting:

- **Options laid out:** tools: all three; `predict_duration` + `get_model_info` (no warehouse access from the assistant); `predict_duration` only. Zone rule: tool name only; zone must be in the question; word match; exact name.
- **First rule tried, exact name in the question** (picked first): the question "How long from JFK Airport to Times Square at 5pm on a Friday?" got `predict_duration` called twice with `dropoff_zone` "Times Sq/Theatre District", both refused (`ok: false`, 0 ms of tool time), and the answer "I don't know" after 134.6 s of generation (trace 90556a09...).
- **With word match:** the same question: one `predict_duration` call, `ok: true`, 76 ms; the answer gave 64 minutes; 30.8 s of generation, embed 28 ms, retrieve 47 ms (trace 832c1064...).
- **Known gaps of word match:** a zone named only by a word of fewer than 4 letters (a rider who writes "JFK" matches nothing from "JFK Airport", whose only 4+ letter word is "airport"); generic words ("park", "district", "heights") are shared by many zones, so an injected zone sharing one with the question passes. Not yet tested against E3's injected wiki text.
- **What a tool can do:** `predict_duration` calls the champion's `/predict` (read-only); `query_zone_stats` runs one `select` on `marts.zone_hour_stats` as `lab_ro` with named parameters, the metric column taken from a fixed list; `get_model_info` reads the champion's `/model`. Decision 018 has the database privileges.
- **Confirmation:** `/assist` returns one answer per request (`contracts/assistant-openapi.yaml`), so a confirmation step would need a new request/response shape.
- **If a tool could write:** not decided here.

## What would show this was wrong

_To be written by the author._
