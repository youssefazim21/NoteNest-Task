# Notes

## What works

The agent classifies one message at a time, calls `search_known_issues` for real, and returns an 11-field JSON report. Python checks the report before accepting it. Local tests cover invalid classifications, severities, missing fields, invented ticket IDs, bad duplicate links, and bad reproduction steps. Those tests do not call the model.

On the Phase 4 run, messages FB-01 through FB-13 were processed and each report passed validation. The terminal showed `Processed FB-13 (13/15)` before the failure.

## What does not work perfectly

The run stopped on FB-14 with:

`Rate limit exceeded: free-models-per-day.`

`output.json` was not written. The file is saved only after all 15 reports succeed, so the 13 finished reports were not kept. FB-14 and FB-15 were not classified in this run.

The configured fallback, `nvidia/nemotron-3-ultra-550b-a55b:free`, is also a free model. OpenRouter counts free-model requests together, so switching to it would not finish this run. I did not add automatic model switching.

The keyword search can miss a ticket when the model's query shares fewer than two meaningful words with the title and description. The model can also choose a debatable severity even when the JSON is valid. Severity has varied between runs for the same PDF-export report.

## Assumptions

- Messages are handled in the order they appear in `feedback.json`.
- A cross-message duplicate can only point at an earlier message.
- A known-issue duplicate can only point at a ticket returned for that message.
- Missing reproduction steps stay an empty list. Missing behavior stays an empty string.
- The primary free model is enough when the daily request budget still has room for about 30 calls.

## What I would do next

Rerun `python main.py` after the free daily limit resets. That is the smallest fix, and it needs no code change.

If the full run has to happen before the reset, use one paid model for the whole run. I would not add a router that tries several free models.

With more time I would print the chosen duplicate IDs during the run, keep a local checkpoint so a failed run can resume at the next message, and add a few more tests for empty titles and `needs_info` questions.

## AI tools

I used Cursor, with the Grok model, to write and revise this Python agent, the unit tests, and these notes. I ran the OpenRouter calls and the unit tests locally and used those results rather than filling in expected answers by hand.
