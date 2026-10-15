"""Triage every NoteNest feedback message into a validated JSON report."""

import json
import os
import sys
import time

from dotenv import load_dotenv
from openrouter import OpenRouter

PRIMARY_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
# Saved for a later phase. This script does not call it.
FALLBACK_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"

# Free models share a limit of about 20 requests per minute.
MIN_SECONDS_BETWEEN_CALLS = 3.5
MAX_RATE_LIMIT_RETRIES = 5
_last_call_time = 0.0

PROGRESS_FILE = "progress.json"
OUTPUT_FILE = "output.json"

STOP_WORDS = {
    "a", "an", "the", "and", "or", "to", "of", "in", "on", "for", "with",
    "my", "i", "it", "is", "are", "was", "were", "be", "this", "that",
    "just", "had", "have", "has", "pls", "please", "but", "so", "if",
    "when", "into", "from", "as", "at", "by", "do",
}

SYSTEM_PROMPT = """You classify one NoteNest user message and check for duplicates.

Choose one classification: bug, feature_request, or needs_info.
Choose severity from the product description: S1, S2, S3, or S4.
Feature requests and other non-bugs must use severity null.
Use needs_info only when the problem cannot be understood without more information.
A recognizable bug is still a bug when some reproduction steps are missing.
Do not invent facts, and do not treat the severity examples as facts about this message.
Customer frustration does not change severity.
S1 means the note itself was lost or overwritten, there is a security problem, or a crash blocks many users.
If the user still has the note and only an export or other output is incomplete, that is a broken feature, not lost notes.
A broken feature with an awkward workaround is not S1.

Call search_known_issues once before you answer. Do not guess ticket IDs.
possible_duplicate_issue must be one of the tool results, or JSON null.
duplicate_of_message must be one of the earlier feedback IDs, or JSON null.
Never use the current message ID as its own duplicate.
Use a short title taken from the message.
steps_to_reproduce must contain only steps the user described. Use [] when they did not give steps.
expected_behavior and actual_behavior must contain only what the message supports. Use "" when that is unknown.
Do not invent causes, versions, or product behavior.
Feature requests and needs_info use JSON null for severity.
needs_info must include a clarifying_question. Otherwise use JSON null.
Use JSON null, not the word null.

After the tool result, return one JSON object with the required report fields.
"""

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_known_issues",
        "description": (
            "Search existing NoteNest bug tickets for possible duplicates "
            "using a short description of the reported problem."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A short description of the reported problem.",
                }
            },
            "required": ["query"],
        },
    },
}

REPORT_FIELDS = [
    "message_id",
    "classification",
    "title",
    "steps_to_reproduce",
    "expected_behavior",
    "actual_behavior",
    "severity",
    "possible_duplicate_issue",
    "duplicate_of_message",
    "confidence",
    "clarifying_question",
]

REPORT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "message_id": {"type": "string"},
        "classification": {
            "type": "string",
            "enum": ["bug", "feature_request", "needs_info"],
        },
        "title": {"type": "string"},
        "steps_to_reproduce": {"type": "array", "items": {"type": "string"}},
        "expected_behavior": {"type": "string"},
        "actual_behavior": {"type": "string"},
        "severity": {
            "type": ["string", "null"],
            "enum": ["S1", "S2", "S3", "S4", None],
        },
        "possible_duplicate_issue": {"type": ["string", "null"]},
        "duplicate_of_message": {"type": ["string", "null"]},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "clarifying_question": {"type": ["string", "null"]},
    },
    "required": REPORT_FIELDS,
}

REPORT_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "notenest_bug_report",
        "strict": True,
        "schema": REPORT_SCHEMA,
    },
}


def load_product_description():
    with open("product_description.md", encoding="utf-8") as file:
        return file.read()


def load_known_issues():
    with open("known_issues.json", encoding="utf-8") as file:
        return json.load(file)


def load_feedback_messages():
    """Load every feedback message in the original file order."""
    with open("feedback.json", encoding="utf-8") as file:
        return json.load(file)


def load_progress():
    """Load reports saved by an earlier run, keyed by message ID."""
    if not os.path.exists(PROGRESS_FILE):
        return {}
    try:
        with open(PROGRESS_FILE, encoding="utf-8") as file:
            return {report["message_id"]: report for report in json.load(file)}
    except (json.JSONDecodeError, KeyError, TypeError):
        print(f"Ignoring unreadable {PROGRESS_FILE}; starting fresh.", file=sys.stderr)
        return {}


def save_progress(reports):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as file:
        json.dump(reports, file, indent=2, ensure_ascii=False)


def meaningful_words(text):
    cleaned = "".join(character.lower() if character.isalnum() else " " for character in text)
    return {
        word
        for word in cleaned.split()
        if len(word) > 2 and word not in STOP_WORDS
    }


def search_known_issues(query, known_issues):
    """Return up to 3 known issues that share meaningful words with the query."""
    query_words = meaningful_words(query)
    scored = []
    for issue in known_issues:
        issue_words = meaningful_words(f"{issue['title']} {issue['description']}")
        overlap = len(query_words & issue_words)
        if overlap >= 2:
            scored.append((overlap, issue))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "id": issue["id"],
            "title": issue["title"],
            "description": issue["description"],
            "severity": issue["severity"],
        }
        for _, issue in scored[:3]
    ]


def reply_text(result):
    content = result.choices[0].message.content if result.choices else None
    return content.strip() if isinstance(content, str) else ""


def is_rate_limit_error(error):
    status_code = getattr(error, "status_code", None)
    response = getattr(error, "response", None)
    response_status = getattr(response, "status_code", None)
    if status_code == 429 or response_status == 429:
        return True

    message = str(error).casefold()
    return "rate limit" in message or "rate_limit" in message


def send_chat_request(client, **request_options):
    """Send a request, spacing calls out and waiting when a rate limit is hit."""
    global _last_call_time
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        # Space out calls to stay under about 20 requests per minute.
        pause = MIN_SECONDS_BETWEEN_CALLS - (time.monotonic() - _last_call_time)
        if pause > 0:
            time.sleep(pause)

        try:
            _last_call_time = time.monotonic()
            return client.chat.send(model=PRIMARY_MODEL, **request_options)
        except Exception as error:
            is_daily_limit = "per-day" in str(error).casefold()
            if (
                not is_rate_limit_error(error)
                or is_daily_limit
                or attempt == MAX_RATE_LIMIT_RETRIES
            ):
                raise
            delay = 20 * (attempt + 1)
            print(
                f"Rate limit reached; waiting {delay}s before retrying.",
                file=sys.stderr,
            )
            time.sleep(delay)


def validate_report(report, feedback_id, known_issue_ids, previous_message_ids):
    """Check the model's JSON report. Raise ValueError when it is not acceptable."""
    if not isinstance(report, dict):
        raise ValueError(f"{feedback_id}: the report must be a JSON object.")

    actual_fields = set(report)
    expected_fields = set(REPORT_FIELDS)
    if actual_fields != expected_fields:
        missing = ", ".join(sorted(expected_fields - actual_fields)) or "none"
        extra = ", ".join(sorted(actual_fields - expected_fields)) or "none"
        raise ValueError(f"{feedback_id}: missing fields: {missing}. Extra fields: {extra}.")

    if report["message_id"] != feedback_id:
        raise ValueError(f"{feedback_id}: message_id is {report['message_id']!r}.")

    if not isinstance(report["classification"], str) or report["classification"] not in {
        "bug",
        "feature_request",
        "needs_info",
    }:
        raise ValueError(f"{feedback_id}: invalid classification {report['classification']!r}.")

    if not isinstance(report["title"], str) or not report["title"].strip():
        raise ValueError(f"{feedback_id}: title must be a nonempty string.")

    steps = report["steps_to_reproduce"]
    if not isinstance(steps, list) or any(not isinstance(step, str) for step in steps):
        raise ValueError(f"{feedback_id}: steps_to_reproduce must be an array of strings.")

    for field_name in ("expected_behavior", "actual_behavior"):
        if not isinstance(report[field_name], str):
            raise ValueError(f"{feedback_id}: {field_name} must be a string.")

    if report["severity"] is not None and not isinstance(report["severity"], str):
        raise ValueError(f"{feedback_id}: invalid severity {report['severity']!r}.")

    if report["severity"] not in {"S1", "S2", "S3", "S4", None}:
        raise ValueError(f"{feedback_id}: invalid severity {report['severity']!r}.")

    if report["classification"] == "bug" and report["severity"] is None:
        raise ValueError(f"{feedback_id}: a bug must have a severity.")

    if report["classification"] != "bug" and report["severity"] is not None:
        raise ValueError(f"{feedback_id}: only a bug can have a severity.")

    duplicate_issue = report["possible_duplicate_issue"]
    if duplicate_issue is not None and duplicate_issue not in known_issue_ids:
        raise ValueError(
            f"{feedback_id}: possible_duplicate_issue {duplicate_issue!r} "
            "was not returned by the search tool."
        )

    earlier_id = report["duplicate_of_message"]
    if earlier_id is not None and earlier_id not in previous_message_ids:
        raise ValueError(
            f"{feedback_id}: duplicate_of_message {earlier_id!r} "
            "is not an earlier feedback message."
        )

    if not isinstance(report["confidence"], str) or report["confidence"] not in {"low", "medium", "high"}:
        raise ValueError(f"{feedback_id}: invalid confidence {report['confidence']!r}.")

    question = report["clarifying_question"]
    if question is not None and not isinstance(question, str):
        raise ValueError(f"{feedback_id}: clarifying_question must be a string or null.")

    if report["classification"] == "needs_info" and not (isinstance(question, str) and question.strip()):
        raise ValueError(f"{feedback_id}: needs_info requires a clarifying question.")

    return report


def parse_report(text, feedback_id, known_issue_ids, previous_message_ids):
    if not text:
        raise ValueError(f"{feedback_id}: the model returned an empty report.")
    try:
        report = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"{feedback_id}: the model did not return valid JSON. {error}") from error
    return validate_report(report, feedback_id, known_issue_ids, previous_message_ids)


def request_report(client, messages):
    result = send_chat_request(
        client,
        messages=messages,
        response_format=REPORT_RESPONSE_FORMAT,
        stream=False,
        max_completion_tokens=700,
        reasoning_effort="none",
    )
    return reply_text(result)


def read_search_call(result, message_id):
    if not result.choices:
        raise RuntimeError(f"{message_id}: the model returned no choices.")

    tool_calls = result.choices[0].message.tool_calls or []
    if len(tool_calls) != 1:
        raise RuntimeError(
            f"{message_id}: expected one search_known_issues tool call, "
            f"got {len(tool_calls)}."
        )

    tool_call = tool_calls[0]
    tool_name = tool_call.function.name
    if tool_name != "search_known_issues":
        raise RuntimeError(f"{message_id}: the model called {tool_name}, not search_known_issues.")

    try:
        arguments = json.loads(tool_call.function.arguments)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{message_id}: the tool arguments were not valid JSON.") from error

    query = arguments.get("query") if isinstance(arguments, dict) else None
    if not isinstance(query, str) or not query.strip():
        raise RuntimeError(f"{message_id}: search_known_issues was called without a text query.")

    return tool_call, query.strip()


def triage_feedback(client, message, product_description, known_issues, earlier_messages):
    """Classify one message after the model searches known issues."""
    version = message["app_version"] or "not provided"
    if earlier_messages:
        earlier_text = "\n".join(
            f"- {item['id']}: {item['text']}" for item in earlier_messages
        )
    else:
        earlier_text = "None."

    user_prompt = f"""Product description:
{product_description}

Message ID: {message["id"]}
Platform: {message["platform"]}
App version: {version}
Text: {message["text"]}

Earlier feedback:
{earlier_text}
"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    first = send_chat_request(
        client,
        messages=messages,
        tools=[SEARCH_TOOL],
        tool_choice={"type": "function", "function": {"name": "search_known_issues"}},
        stream=False,
        max_completion_tokens=200,
        reasoning_effort="none",
    )
    tool_call, query = read_search_call(first, message["id"])
    matches = search_known_issues(query, known_issues)

    messages.append(
        {
            "role": "assistant",
            "content": reply_text(first) or None,
            "tool_calls": [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
            ],
        }
    )
    messages.append(
        {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": json.dumps(matches),
        }
    )
    messages.append(
        {
            "role": "user",
            "content": "Return the JSON report now. Do not call a tool.",
        }
    )
    match_ids = [match["id"] for match in matches]
    previous_ids = [earlier["id"] for earlier in earlier_messages]
    answer = request_report(client, messages)
    try:
        report = parse_report(answer, message["id"], match_ids, previous_ids)
    except ValueError as error:
        print(f"Retry: {error}", file=sys.stderr)
        messages.append({"role": "assistant", "content": answer})
        messages.append(
            {
                "role": "user",
                "content": (
                    "That report was invalid. Return one corrected JSON object. "
                    f"Problem: {error}"
                ),
            }
        )
        answer = request_report(client, messages)
        report = parse_report(answer, message["id"], match_ids, previous_ids)

    return query, matches, report


def main():
    load_dotenv()
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key or api_key == "your_key_here":
        print(
            "Missing OpenRouter API key. Copy .env.example to .env and add your key.",
            file=sys.stderr,
        )
        sys.exit(1)

    product_description = load_product_description()
    known_issues = load_known_issues()
    messages = load_feedback_messages()
    earlier_messages = []
    reports = []

    # Reports finished in earlier runs, so a crash never loses completed work.
    done = load_progress()

    try:
        with OpenRouter(api_key=api_key) as client:
            for index, message in enumerate(messages, start=1):
                if message["id"] in done:
                    reports.append(done[message["id"]])
                    earlier_messages.append(message)
                    print(f"Skipped {message['id']} (already done)", flush=True)
                    continue

                _, _, report = triage_feedback(
                    client,
                    message,
                    product_description,
                    known_issues,
                    earlier_messages,
                )
                reports.append(report)
                earlier_messages.append(message)
                save_progress(reports)
                print(f"Processed {message['id']} ({index}/{len(messages)})", flush=True)

        with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
            json.dump(reports, file, indent=2, ensure_ascii=False)
            file.write("\n")
    except Exception as error:
        print(f"The OpenRouter request failed: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()