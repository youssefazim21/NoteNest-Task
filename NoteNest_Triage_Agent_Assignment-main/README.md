# Take-home assignment: Bug-report triage agent

Thanks for taking the time. This assignment is representative of the work: building small agents on OpenRouter, testing them, and writing clear bug reports.

**Time-box: 4 to 6 hours. There is no extra credit for doing more.** If you run out of time, stop and tell us what you would do next.

## Scenario

NoteNest is a fictional notes app. Users send messy feedback by email, chat, app-store reviews and social media. Your job is to build an agent that turns each message into a structured bug report.

Everything in this folder is fictional. You do not need any knowledge of our real products, and you will not receive any confidential material.

## Files

- `feedback.json`: 15 raw user messages.
- `known_issues.json`: 10 existing tickets.
- `product_description.md`: a one-page description of NoteNest and the severity scale.

## Task

Build an agent that uses a model through [OpenRouter](https://openrouter.ai). For each message in `feedback.json` it must produce a JSON object with these fields:

```json
{
  "message_id": "FB-00",
  "classification": "bug | feature_request | needs_info",
  "title": "short, specific title",
  "steps_to_reproduce": ["..."],
  "expected_behavior": "...",
  "actual_behavior": "...",
  "severity": "S1 | S2 | S3 | S4 | null",
  "possible_duplicate_issue": "NN-000 or null",
  "duplicate_of_message": "FB-00 or null",
  "confidence": "low | medium | high",
  "clarifying_question": "string or null"
}
```

Rules:
1. **Tool use.** The agent must find duplicates by calling a tool (function calling), for example `search_known_issues(query)`, that you implement over `known_issues.json`. It must not receive the full ticket list in its prompt.
2. **Do not guess.** If information is missing, set `classification` to `needs_info` and write a clarifying question.
3. **Not everything is a bug.** Some messages are not bugs.
4. **Messages can overlap.** Some messages describe the same problem.
5. **Structured output.** The output must be valid JSON for all 15 messages.

You can use any language. Any OpenRouter model that supports tool calling works. Free-tier models are fine. [If you cannot get access to a suitable model, tell us by Wednesday 10/14 and we will provide a spend-capped key.]

## Deliverables

1. A repo (GitHub link or zip) with a README containing run instructions.
2. `output.json`: your agent's output for all 15 messages.
3. A small evaluation: at least 5 test cases with expected results and your own pass/fail notes. Tell us how you decided what is correct.
4. A one-page note (`NOTES.md`): what works, what does not, what you would do next, and any assumption you made.
5. A short note on how you used AI tools (which ones and for what). Using them is allowed.
6. Be ready to present a 10 to 12 minute walkthrough on the call, including a live run.

## Fairness rules

- AI coding tools are allowed. You must be able to explain every part of your code.
- Be honest about limitations. A clear "this fails when..." scores better than a hidden failure.
- **Your work stays yours.** We will use your submission only to evaluate it. We will not use it in our products. Nothing in this assignment is assigned to us unless you later sign an employment contract and IP assignment for work done after you start.
- Please do not post this assignment or your solution publicly.

## Timeline

- Questions: send by **Wednesday 10/14**. We answer in writing, and answers go to everyone doing this assignment.
- Submission: **Friday 10/16, 6:00 PM Cairo time**. Need an extra day? Ask us.
- Walkthrough: **Saturday 10/17** on the call.

## How we score (100 points)

| Area | Points | What we look for |
|---|---|---|
| Works end to end | 30 | Valid output for all 15 messages; sensible severity and duplicate matching |
| Tool use and structured output | 20 | Duplicate search is a real tool call; schema is respected; errors are handled |
| Testing and evaluation | 20 | Meaningful test cases; honest results; clear reasoning about correctness |
| Presentation and communication | 20 | Clear README, clear walkthrough, direct answers to questions |
| Honesty about limits | 10 | You know where it fails and say so |

Good luck, and enjoy it.
