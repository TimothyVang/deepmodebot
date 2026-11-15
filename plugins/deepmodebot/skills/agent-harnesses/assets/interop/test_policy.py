"""Stdlib-only security regressions; no SDK, network, credentials or models required."""
import copy
import os
import unittest
from unittest.mock import patch

from policy import (APPROVED_MODEL, MAX_BODY_BYTES, MAX_CALLS, MAX_COST, MAX_OUTPUT_BYTES,
                    MAX_TEXT_BYTES, MODEL_TIMEOUT, capability_token,
                    validate_endpoint, validate_request, validate_text)


def request():
    return {"jsonrpc": "2.0", "id": "local-request", "method": "SendMessage",
            "params": {"message": {"messageId": "m1", "role": "ROLE_USER",
                                   "parts": [{"text": "answer a bounded question", "mediaType": "text/plain"}]},
                       "configuration": {"acceptedOutputModes": ["text/plain"], "returnImmediately": False}}}


class PolicyTests(unittest.TestCase):
    def test_operator_limits(self):
        self.assertEqual((MAX_TEXT_BYTES, MAX_OUTPUT_BYTES, MAX_BODY_BYTES), (16384, 16384, 32768))
        self.assertEqual((MAX_CALLS, MODEL_TIMEOUT, MAX_COST), (8, 120, 1))
        self.assertEqual(APPROVED_MODEL, "openai-codex/gpt-6.1-sol")

    def test_text_limit_counts_utf8_not_characters(self):
        self.assertEqual(validate_text("é" * 8192), "é" * 8192)
        for value in ("é" * 8193, "x" * 16385, "", " \n\t", "x\0y", "\ud800", b"text", None, 1):
            with self.subTest(kind=type(value).__name__), self.assertRaises(ValueError):
                validate_text(value)

    def test_text_is_data_not_a_path_or_routing_option(self):
        text = "@~/.ssh/example https://example.invalid --model unapproved/model"
        self.assertEqual(validate_text(text), text)

    def test_exact_literal_loopback_endpoint(self):
        for port in (1, 18080, 65535):
            url = f"http://127.0.0.1:{port}/a2a"
            self.assertEqual(validate_endpoint(url), url)
        for url in ("http://localhost:80/a2a", "https://127.0.0.1:80/a2a", "http://127.0.0.1/a2a",
                    "http://127.0.0.1:0/a2a", "http://127.0.0.1:65536/a2a", "http://127.0.0.1:080/a2a",
                    "http://127.1:80/a2a", "http://[::1]:80/a2a", "http://127.0.0.1:80/a2a/",
                    "http://127.0.0.1:80/a2a?token=x", "http://127.0.0.1:80/a2a#fragment",
                    "http://user@127.0.0.1:80/a2a", "http://127.0.0.1:80/a2a\n", None):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_endpoint(url)

    def test_capability_is_required_and_never_in_error_text(self):
        # Deliberately invalid fixtures are not credentials.
        for value in ("", "short", "x" * 31, "x" * 257, "invalid+" * 8, "x" * 32 + "\n"):
            with patch.dict(os.environ, {"DEEPMODE_INTEROP_TOKEN": value}), self.assertRaises(ValueError) as caught:
                capability_token()
            if value:
                self.assertNotIn(value, str(caught.exception))
        with patch.dict(os.environ, {"DEEPMODE_INTEROP_TOKEN": "unit_test_fixture_not_secret_123456"}):
            self.assertEqual(capability_token(), "unit_test_fixture_not_secret_123456")

    def test_only_one_standalone_text_message(self):
        self.assertEqual(validate_request(request()), "answer a bounded question")
        for field, value in (("taskId", "foreign"), ("contextId", "foreign"),
                             ("referenceTaskIds", ["foreign"]), ("extensions", ["url"]),
                             ("metadata", {}), ("role", "ROLE_AGENT"), ("role", "user"),
                             ("messageId", "x" * 129), ("parts", []),
                             ("parts", [{"text": "one"}, {"text": "two"}]),
                             ("parts", [{"url": "file:///example"}]),
                             ("parts", [{"raw": "YQ=="}]),
                             ("parts", [{"data": {"command": "anything"}}]),
                             ("parts", [{"text": "x", "filename": "example.txt"}]),
                             ("parts", [{"text": "x", "metadata": {}}]),
                             ("parts", [{"text": "x", "mediaType": "text/html"}])):
            body = request()
            body["params"]["message"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_request(body)

    def test_reject_configuration_and_envelope_expansion(self):
        for config in ({"taskPushNotificationConfig": {"url": "http://example.invalid"}},
                       {"historyLength": 1}, {"returnImmediately": True},
                       {"acceptedOutputModes": ["application/json"]}, None):
            body = request()
            body["params"]["configuration"] = config
            with self.subTest(config=config), self.assertRaises(ValueError):
                validate_request(body)
        good = request()
        invalid = [None, [], [good], {**good, "method": "message/send"},
                   {**good, "method": "SendStreamingMessage"}, {**good, "id": None},
                   {**good, "id": True}, {**good, "jsonrpc": "1.0"}, {**good, "extra": True}]
        for field in ("metadata", "tenant", "extensions"):
            body = copy.deepcopy(good)
            body["params"][field] = {}
            invalid.append(body)
        for body in invalid:
            with self.subTest(body=body), self.assertRaises(ValueError):
                validate_request(body)


if __name__ == "__main__":
    unittest.main()
