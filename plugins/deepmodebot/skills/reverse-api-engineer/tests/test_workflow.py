"""Adapter tests: stdlib only, no browser, model or external network."""

import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ASSETS = Path(__file__).resolve().parents[1] / "assets"
SPEC = importlib.util.spec_from_file_location("reverse_api_workflow", ASSETS / "workflow.py")
workflow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workflow)


def example_har():
    return {"log": {"entries": [{
        "request": {
            "method": "GET", "url": "http://127.0.0.1:8765/api/items?token=SYNTHETIC_QUERY#private",
            "headers": [{"name": "Authorization", "value": "SYNTHETIC_AUTH"}],
            "cookies": [{"name": "session", "value": "SYNTHETIC_COOKIE"}],
            "postData": {"mimeType": "application/json", "text": '{"password":"SYNTHETIC_PASSWORD"}'},
            "_extension": "SYNTHETIC_EXTENSION",
        },
        "response": {
            "status": 200, "statusText": "SYNTHETIC_STATUS", "redirectURL": "http://example.invalid/private",
            "headers": [{"name": "Set-Cookie", "value": "SYNTHETIC_SET_COOKIE"}],
            "cookies": [{"name": "session", "value": "SYNTHETIC_COOKIE"}],
            "content": {"mimeType": "application/json", "text": '{"items":[{"id":8,"name":"SYNTHETIC_NAME","active":true}],"next":null}'},
        },
        "serverIPAddress": "192.0.2.1", "comment": "SYNTHETIC_COMMENT",
    }]}}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[5] / ".scratch"
        scratch.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def test_origin_rejects_non_http_and_embedded_credentials(self):
        for url in ("file:///etc/passwd", "http://user:password@example.invalid", "not-a-url"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                workflow.origin(url)

    def test_default_port_is_same_origin(self):
        self.assertEqual(workflow.origin("https://example.invalid/path"), ("https", "example.invalid", 443))
        self.assertEqual(workflow.origin("https://EXAMPLE.invalid:443"), ("https", "example.invalid", 443))

    def test_capture_filter_blocks_other_origins_and_writes(self):
        allowed = {("http", "127.0.0.1", 8765)}
        self.assertTrue(workflow.request_allowed("http://127.0.0.1:8765/api/items", "GET", allowed))
        for url, method in (("http://127.0.0.1:8766/api/items", "GET"),
                            ("https://example.invalid/", "GET"),
                            ("http://127.0.0.1:8765/api/items", "POST"),
                            ("http://127.0.0.1:8765/api/items", "DELETE"),
                            ("file:///etc/passwd", "GET")):
            with self.subTest(url=url, method=method):
                self.assertFalse(workflow.request_allowed(url, method, allowed))

    def test_sanitizer_drops_credentials_metadata_and_values(self):
        result = workflow.sanitized_har(example_har())
        serialized = json.dumps(result)
        self.assertNotIn("SYNTHETIC", serialized)
        self.assertNotIn("192.0.2.1", serialized)
        entry = result["log"]["entries"][0]
        self.assertEqual(entry["request"]["url"], "http://127.0.0.1:8765/api/items?token=REDACTED")
        self.assertEqual(entry["request"]["headers"], [])
        self.assertEqual(entry["response"]["cookies"], [])
        self.assertEqual(json.loads(entry["response"]["content"]["text"]),
                         {"items": [{"id": 0, "name": "REDACTED", "active": False}], "next": None})
        self.assertEqual(json.loads(entry["request"]["postData"]["text"]), {"password": "REDACTED"})

    def test_non_json_and_encoded_bodies_are_omitted(self):
        for content in ({"mimeType": "text/html", "text": "SYNTHETIC_HTML"},
                        {"mimeType": "application/json", "text": "SYNTHETIC_INVALID"},
                        {"mimeType": "application/json", "encoding": "base64", "text": "e30="}):
            with self.subTest(content=content):
                har = example_har()
                har["log"]["entries"][0]["response"]["content"] = content
                self.assertNotIn("text", workflow.sanitized_har(har)["log"]["entries"][0]["response"]["content"])

    def test_empty_har_fails_observably(self):
        with self.assertRaisesRegex(ValueError, "no requests"):
            workflow.sanitized_har({"log": {"entries": []}})

    def test_sanitizer_does_not_mutate_raw_capture(self):
        document = example_har()
        original = json.dumps(document)
        workflow.sanitized_har(document)
        self.assertEqual(json.dumps(document), original)

    def test_private_output_refuses_overwrite(self):
        output = self.directory / "capture"
        workflow.private_directory(output)
        with self.assertRaises(FileExistsError):
            workflow.private_directory(output)
        target = output / "reviewed.har"
        workflow.write_private(target, {"safe": True})
        with self.assertRaises(FileExistsError):
            workflow.write_private(target, {"safe": False})
        self.assertEqual(json.loads(target.read_text()), {"safe": True})
        if __import__("os").name == "posix":
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertEqual(output.stat().st_mode & 0o777, 0o700)

    def test_review_hash_rejects_modified_har(self):
        target = self.directory / "reviewed.har"
        raw = json.dumps(workflow.sanitized_har(example_har())).encode()
        target.write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        self.assertEqual(workflow.reviewed_bytes(target, digest), raw)
        target.write_bytes(raw + b"\n")
        with self.assertRaisesRegex(ValueError, "does not match"):
            workflow.reviewed_bytes(target, digest)

    def test_matching_hash_cannot_bypass_cookie_or_header_gate(self):
        for message in ("request", "response"):
            for field, value in (("cookies", [{"name": "session", "value": "SYNTHETIC_COOKIE"}]),
                                 ("headers", [{"name": "Authorization", "value": "SYNTHETIC_AUTH"}])):
                with self.subTest(message=message, field=field):
                    document = workflow.sanitized_har(example_har())
                    document["log"]["entries"][0][message][field] = value
                    raw = json.dumps(document).encode()
                    target = self.directory / "reviewed.har"
                    target.write_bytes(raw)
                    with self.assertRaisesRegex(ValueError, "cookies and headers"):
                        workflow.reviewed_bytes(target, hashlib.sha256(raw).hexdigest())

    def test_matching_hash_cannot_bypass_url_credential_gate(self):
        document = workflow.sanitized_har(example_har())
        document["log"]["entries"][0]["request"]["url"] = "http://user:synthetic@example.invalid/"
        raw = json.dumps(document).encode()
        target = self.directory / "reviewed.har"
        target.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, "Credentials in URLs"):
            workflow.reviewed_bytes(target, hashlib.sha256(raw).hexdigest())

    def test_generation_requires_execution_consent_before_importing_engine(self):
        with self.assertRaisesRegex(ValueError, "allow-agent-execution"):
            workflow.generate(argparse.Namespace(allow_agent_execution=False))

    def test_all_ten_languages_have_real_upstream_prompts(self):
        source = ASSETS / "engine" / "src" / "reverse_api"
        module = ast.parse((source / "utils.py").read_text(encoding="utf-8"))
        mapping = next(ast.literal_eval(node.value) for node in module.body
                       if isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Name) and target.id == "OUTPUT_LANGUAGE_EXTENSIONS" for target in node.targets))
        self.assertEqual(set(workflow.LANGUAGES), set(mapping))
        self.assertEqual(len(mapping), 10)
        for language in workflow.LANGUAGES:
            self.assertGreater((source / "prompts" / "partials" / f"_language_{language}.md").stat().st_size, 100)


if __name__ == "__main__":
    unittest.main()
