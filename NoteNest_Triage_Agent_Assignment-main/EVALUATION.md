# Evaluation

The full agent was started with `python main.py` on 12 October 2026. FB-01 through FB-13 each returned a report that passed `validate_report`. The next request, for FB-14, failed with:

`Rate limit exceeded: free-models-per-day.`

`output.json` was not created, because the program saves that file only after all 15 reports succeed. The finished reports were not printed, so their classification, severity, and duplicate fields are not available to score. I am not copying results from an earlier three-message run and calling them this run.

| Case | Expected | Actual | Result |
|---|---|---|---|
| FB-01 | Bug, severity S2, known issue NN-104, no earlier message | Processed, then discarded with the unfinished run | Not scored |
| FB-02 | Feature request, null severity, no known issue, no earlier message | Processed, then discarded with the unfinished run | Not scored |
| FB-05 and FB-06 | Offline data loss, known issue NN-110, FB-06 repeats FB-05 | Both processed, then discarded with the unfinished run | Not scored |
| FB-09 and FB-15 | Duplicate Android reminders, known issue NN-105, FB-15 repeats FB-09 | FB-09 was processed. FB-15 was not, because the run stopped at FB-14 | Not scored |
| FB-14 | PDF export bug, known issue NN-104, earlier message FB-01 | Not produced. The request hit the free daily limit | Not scored |

These expected values come from the feedback text, `known_issues.json`, and the severity scale. They were not written into the program as answers.

The pass/fail judgment for model quality has to wait for a complete `output.json`. A valid report can still contain a weak judgment, and that can only be checked from the saved fields.
