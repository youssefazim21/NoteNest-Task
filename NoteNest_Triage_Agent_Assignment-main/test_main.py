"""Tests for local report validation. These do not call OpenRouter."""

import unittest
from unittest.mock import Mock, call

from main import FALLBACK_MODEL, PRIMARY_MODEL, send_chat_request, validate_report


def valid_report(**changes):
    report = {
        "message_id": "FB-01",
        "classification": "bug",
        "title": "PDF export drops the last pages",
        "steps_to_reproduce": ["Export a 40 page note to PDF"],
        "expected_behavior": "The PDF includes every page",
        "actual_behavior": "The last pages are missing",
        "severity": "S2",
        "possible_duplicate_issue": "NN-104",
        "duplicate_of_message": None,
        "confidence": "high",
        "clarifying_question": None,
    }
    report.update(changes)
    return report


class ValidateReportTests(unittest.TestCase):
    def test_valid_report_passes(self):
        report = valid_report()
        self.assertEqual(validate_report(report, "FB-01", ["NN-104"], []), report)

    def test_invalid_classification_and_severity_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_report(valid_report(classification="question"), "FB-01", ["NN-104"], [])
        with self.assertRaises(ValueError):
            validate_report(valid_report(severity="S9"), "FB-01", ["NN-104"], [])
        with self.assertRaises(ValueError):
            validate_report(
                valid_report(
                    message_id="FB-02",
                    classification="feature_request",
                    severity="S2",
                    possible_duplicate_issue=None,
                ),
                "FB-02",
                [],
                [],
            )

    def test_missing_required_field_is_rejected(self):
        report = valid_report()
        del report["confidence"]
        with self.assertRaises(ValueError):
            validate_report(report, "FB-01", ["NN-104"], [])

    def test_invented_known_issue_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_report(valid_report(possible_duplicate_issue="NN-999"), "FB-01", ["NN-104"], [])

    def test_self_and_future_duplicates_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_report(valid_report(duplicate_of_message="FB-01"), "FB-01", ["NN-104"], [])
        with self.assertRaises(ValueError):
            validate_report(valid_report(duplicate_of_message="FB-14"), "FB-01", ["NN-104"], [])

    def test_wrong_json_types_raise_value_error(self):
        for changes in (
            {"classification": ["bug"]},
            {"severity": ["S2"]},
            {"confidence": {"level": "high"}},
        ):
            with self.assertRaises(ValueError):
                validate_report(valid_report(**changes), "FB-01", ["NN-104"], [])

    def test_bug_with_null_severity_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_report(valid_report(severity=None), "FB-01", ["NN-104"], [])

    def test_invalid_reproduction_steps_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_report(valid_report(steps_to_reproduce=["Export the note", 2]), "FB-01", ["NN-104"], [])


class SendChatRequestTests(unittest.TestCase):
    def test_rate_limit_retries_with_fallback_model(self):
        client = Mock()
        response = object()
        client.chat.send.side_effect = [
            RuntimeError("Rate limit exceeded: free-models-per-min"),
            response,
        ]

        result = send_chat_request(client, messages=[])

        self.assertIs(result, response)
        self.assertEqual(
            client.chat.send.call_args_list,
            [
                call(model=PRIMARY_MODEL, messages=[]),
                call(model=FALLBACK_MODEL, messages=[]),
            ],
        )

    def test_non_rate_limit_error_is_not_retried(self):
        client = Mock()
        client.chat.send.side_effect = RuntimeError("Invalid API key")

        with self.assertRaisesRegex(RuntimeError, "Invalid API key"):
            send_chat_request(client, messages=[])

        client.chat.send.assert_called_once_with(model=PRIMARY_MODEL, messages=[])


if __name__ == "__main__":
    unittest.main()
