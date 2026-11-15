"""Consumer-visible reference discovery and cache migration regressions."""
import argparse
import contextlib
import datetime as dt
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "reference_catalog_test", ROOT / "plugins/deepmodebot/skills/deepmodebot/scripts/trending.py")
catalog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(catalog)


class ReferenceDiscoveryTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / ".scratch/tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.out = Path(temporary.name)
        clock = patch.object(catalog, "today", return_value=dt.date(2026, 11, 14))
        clock.start()
        self.addCleanup(clock.stop)
        self.reference = {
            "github_id": 1,
            "reviewed": "2026-11-14", "archive": "https://example.test/archive",
            "topics": ["doctor admin prototype"], "sources": ["https://example.test/source"],
            "caution": "Separate enterprise terms apply. " + "Check the intended use. " * 12
                       + "Do not use patient data in this prototype.",
        }

    def repository(self, name, repository_id=1):
        return {"full_name": name, "html_url": "https://github.com/" + name,
                "id": repository_id,
                "description": "A generic workflow component", "language": "Python",
                "license": {"spdx_id": "Apache-2.0"}, "stargazers_count": 10,
                "created_at": "2026-01-01T00:00:00Z", "pushed_at": "2026-11-14T00:00:00Z"}

    def entry(self, name, repository_id=1):
        return {**catalog.entry_from(self.repository(name, repository_id)), "first_seen": "2026-11-01",
                "stars_first_seen": 2, "last_seen": "2026-11-14", "seen_in": ["earlier-source"]}

    def write_catalog(self, value):
        (self.out / "catalog.json").write_text(json.dumps(value), encoding="utf-8")

    def test_same_day_published_revision_exposes_reference_only_match(self):
        previous = {"updated": "2026-11-14", "sources": {}, "repos": {}}
        self.write_catalog(previous)
        entry = self.entry("example/component")
        entry["reference"] = self.reference
        published = {**previous, "reference_revision": catalog.REFERENCE_REVISION,
                     "repos": {"example/component": entry}}
        output = io.StringIO()
        with patch.object(catalog, "PUBLISHED", "https://example.test/catalog.json"), \
                patch.object(catalog, "fetch", return_value=json.dumps(published)), \
                patch.object(catalog, "update", side_effect=AssertionError("unnecessary rebuild")), \
                contextlib.redirect_stdout(output):
            catalog.find(argparse.Namespace(out=self.out, terms=["doctor admin"], limit=20, no_refresh=False))
        self.assertIn("example/component", output.getvalue())
        self.assertIn(self.reference["caution"], output.getvalue())
        self.assertEqual(catalog.load_catalog(self.out / "catalog.json"), published)

    def test_redirected_alias_preserves_reference_cautions_and_observation_history(self):
        self.write_catalog({"updated": "2026-11-14", "sources": {},
                            "repos": {"old-owner/component": self.entry("old-owner/component")}})

        def source(found, token):
            repo = self.repository("new-owner/component")
            catalog.add(found, "new-owner/component", "reference-library", repo)
            found["new-owner/component"]["reference"] = self.reference
            catalog.add(found, "old-owner/component", "other-source", repo)

        with patch.object(catalog, "SOURCES", [("reference-library", source)]), \
                patch.object(catalog, "github_token", return_value=None), \
                contextlib.redirect_stdout(io.StringIO()):
            catalog.update(argparse.Namespace(out=self.out))
        result = catalog.load_catalog(self.out / "catalog.json")
        self.assertNotIn("old-owner/component", result["repos"])
        entry = result["repos"]["new-owner/component"]
        self.assertEqual(entry["reference"], self.reference)
        self.assertEqual(entry["first_seen"], "2026-11-01")
        self.assertEqual(entry["stars_first_seen"], 2)
        self.assertEqual(entry["seen_in"], ["earlier-source", "other-source", "reference-library"])
        self.assertIn(self.reference["caution"], (self.out / "README.md").read_text(encoding="utf-8"))

    def test_source_failure_keeps_reference_searchable_after_repository_rename(self):
        previous = self.entry("old-owner/component")
        previous["reference"] = self.reference
        self.write_catalog({"updated": "2026-11-14", "sources": {}, "reference_revision": "previous",
                            "repos": {"old-owner/component": previous}})

        def unavailable(found, token):
            raise ValueError("malformed reference JSON")

        def other_source(found, token):
            catalog.add(found, "old-owner/component", "other-source", self.repository("new-owner/component"))

        output = io.StringIO()
        with patch.object(catalog, "SOURCES", [("reference-library", unavailable), ("other-source", other_source)]), \
                patch.object(catalog, "github_token", return_value=None), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            catalog.update(argparse.Namespace(out=self.out))
            catalog.find(argparse.Namespace(out=self.out, terms=["doctor admin"], limit=20, no_refresh=True))
        self.assertIn("[new-owner/component]", output.getvalue())
        self.assertIn(self.reference["caution"], output.getvalue())
        self.assertTrue(catalog.is_stale(catalog.load_catalog(self.out / "catalog.json")))

    def test_failed_alias_enrichment_retains_saved_reference_and_requires_refresh(self):
        def source(found, token):
            catalog.add(found, "old-owner/component", "reference-library")
            found["old-owner/component"]["reference"] = self.reference

        output = io.StringIO()
        responses = [json.dumps(self.repository("new-owner/component")),
                     urllib.error.URLError("temporary enrichment failure")]
        with patch.object(catalog, "SOURCES", [("reference-library", source)]), \
                patch.object(catalog, "github_token", return_value=None), \
                patch.object(catalog, "fetch", side_effect=responses), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            catalog.update(argparse.Namespace(out=self.out))
            catalog.update(argparse.Namespace(out=self.out))
            catalog.find(argparse.Namespace(out=self.out, terms=["doctor admin"], limit=20, no_refresh=True))
        self.assertIn("[new-owner/component]", output.getvalue())
        self.assertIn(self.reference["caution"], output.getvalue())
        self.assertTrue(catalog.is_stale(catalog.load_catalog(self.out / "catalog.json")))


    def test_failed_reference_refresh_preserves_old_choices_but_prunes_other_observations(self):
        saved = self.entry("old-owner/component")
        saved["reference"] = self.reference
        expired = self.entry("other-owner/expired", 2)
        self.write_catalog({"updated": "2026-11-14", "sources": {},
                            "reference_revision": catalog.REFERENCE_REVISION,
                            "repos": {"old-owner/component": saved, "other-owner/expired": expired}})

        def unavailable(found, token):
            raise ValueError("reference collector unavailable")

        def other_source(found, token):
            catalog.add(found, "other-owner/current", "other-source", self.repository("other-owner/current", 3))

        output = io.StringIO()
        future = dt.date(2026, 11, 14) + dt.timedelta(days=catalog.KEEP_DAYS + 1)
        with patch.object(catalog, "today", return_value=future), \
                patch.object(catalog, "SOURCES", [("reference-library", unavailable), ("other-source", other_source)]), \
                patch.object(catalog, "github_token", return_value=None), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            catalog.update(argparse.Namespace(out=self.out))
            catalog.find(argparse.Namespace(out=self.out, terms=["doctor admin"], limit=20, no_refresh=True))
        retained = catalog.load_catalog(self.out / "catalog.json")
        self.assertIn("[old-owner/component]", output.getvalue())
        self.assertIn(self.reference["caution"], output.getvalue())
        self.assertEqual(retained["repos"]["old-owner/component"]["last_seen"], "2026-11-14")
        self.assertNotIn("other-owner/expired", retained["repos"])
        self.assertTrue(catalog.is_stale(retained))


    def test_inactive_reference_alias_retains_cautions_and_current_liveness(self):
        for flag in ("archived", "fork"):
            for reference_ready in (True, False):
                with self.subTest(flag=flag, reference_ready=reference_ready):
                    saved = self.entry("old-owner/component")
                    saved["reference"] = self.reference
                    self.write_catalog({"updated": "2026-11-14", "sources": {},
                                        "repos": {"old-owner/component": saved}})
                    inactive = self.repository("new-owner/component")
                    inactive[flag] = True
                    unrelated = self.repository("other-owner/inactive", 2)
                    unrelated[flag] = True

                    def reference_source(found, token):
                        if not reference_ready:
                            raise ValueError("reference collector unavailable")
                        catalog.add(found, "old-owner/component", "reference-library", inactive)
                        found["old-owner/component"]["reference"] = self.reference

                    def other_source(found, token):
                        if not reference_ready:
                            catalog.add(found, "old-owner/component", "other-source", inactive)
                        catalog.add(found, "other-owner/inactive", "other-source", unrelated)

                    output = io.StringIO()
                    future = dt.date(2026, 11, 14) + dt.timedelta(days=catalog.KEEP_DAYS + 1)
                    with patch.object(catalog, "today", return_value=future), \
                            patch.object(catalog, "SOURCES", [("reference-library", reference_source),
                                                            ("other-source", other_source)]), \
                            patch.object(catalog, "github_token", return_value=None), \
                            contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
                        catalog.update(argparse.Namespace(out=self.out))
                        catalog.find(argparse.Namespace(out=self.out, terms=["doctor admin"], limit=20, no_refresh=True))
                    current = catalog.load_catalog(self.out / "catalog.json")
                    self.assertIn("[new-owner/component]", output.getvalue())
                    self.assertIn("reference only: " + flag, output.getvalue())
                    self.assertIn(self.reference["caution"], output.getvalue())
                    self.assertNotIn("old-owner/component", current["repos"])
                    self.assertNotIn("other-owner/inactive", current["repos"])
                    self.assertIn("earlier-source", current["repos"]["new-owner/component"]["seen_in"])
                    self.assertEqual(catalog.is_stale(current), not reference_ready)


    def test_repeated_renames_use_repository_identity_to_preserve_one_history(self):
        saved = self.entry("old-owner/component")
        saved.pop("github_id")
        saved["reference"] = self.reference
        self.write_catalog({"updated": "2026-11-14", "sources": {},
                            "repos": {"old-owner/component": saved}})
        responses = iter([self.repository("middle-owner/component"),
                          self.repository("final-owner/component")])

        def source(found, token):
            catalog.add(found, "old-owner/component", "reference-library", next(responses))
            found["old-owner/component"]["reference"] = self.reference

        output = io.StringIO()
        with patch.object(catalog, "SOURCES", [("reference-library", source)]), \
                patch.object(catalog, "github_token", return_value=None), \
                contextlib.redirect_stdout(output):
            catalog.update(argparse.Namespace(out=self.out))
            catalog.update(argparse.Namespace(out=self.out))
            catalog.find(argparse.Namespace(out=self.out, terms=["doctor admin"], limit=20, no_refresh=True))
        current = catalog.load_catalog(self.out / "catalog.json")
        self.assertEqual(set(current["repos"]), {"final-owner/component"})
        final = current["repos"]["final-owner/component"]
        self.assertEqual(final["first_seen"], saved["first_seen"])
        self.assertEqual(final["stars_first_seen"], saved["stars_first_seen"])
        self.assertIn("earlier-source", final["seen_in"])
        self.assertIn(self.reference["caution"], output.getvalue())

    def test_reused_name_does_not_inherit_a_different_repositorys_history(self):
        saved = self.entry("owner/component", 1)
        self.write_catalog({"updated": "2026-11-14", "sources": {},
                            "repos": {"owner/component": saved}})

        def source(found, token):
            catalog.add(found, "owner/component", "reference-library", self.repository("owner/component", 2))
            found["owner/component"]["reference"] = {**self.reference, "github_id": 2}

        with patch.object(catalog, "SOURCES", [("reference-library", source)]), \
                patch.object(catalog, "github_token", return_value=None), \
                contextlib.redirect_stdout(io.StringIO()):
            catalog.update(argparse.Namespace(out=self.out))
        current = catalog.load_catalog(self.out / "catalog.json")["repos"]["owner/component"]
        self.assertEqual(current["first_seen"], "2026-11-14")
        self.assertEqual(current["stars_first_seen"], current["stars"])
        self.assertNotIn("earlier-source", current["seen_in"])

    def test_reused_name_only_keeps_independently_refreshed_cautions(self):
        for flag in (None, "archived", "fork"):
            for refreshed in (True, False):
                with self.subTest(flag=flag, refreshed=refreshed):
                    saved = self.entry("owner/component", 1)
                    saved["reference"] = self.reference
                    self.write_catalog({"updated": "2026-11-14", "sources": {},
                                        "repos": {"owner/component": saved}})
                    replacement = self.repository("owner/component", 2)
                    if flag:
                        replacement[flag] = True
                    new_reference = {**self.reference, "github_id": 2, "caution": "Independent new repository licensing scope."}

                    def reference_source(found, token):
                        if not refreshed:
                            raise ValueError("reference collector unavailable")
                        catalog.add(found, "owner/component", "reference-library", replacement)
                        found["owner/component"]["reference"] = new_reference

                    def other_source(found, token):
                        catalog.add(found, "owner/component", "other-source", replacement)

                    output = io.StringIO()
                    with patch.object(catalog, "SOURCES", [("reference-library", reference_source),
                                                          ("other-source", other_source)]), \
                            patch.object(catalog, "github_token", return_value=None), \
                            contextlib.redirect_stdout(output):
                        catalog.update(argparse.Namespace(out=self.out))
                        catalog.find(argparse.Namespace(out=self.out, terms=["doctor admin"], limit=20, no_refresh=True))
                    current = catalog.load_catalog(self.out / "catalog.json")
                    self.assertNotIn(self.reference["caution"], output.getvalue())
                    if refreshed:
                        self.assertEqual(current["repos"]["owner/component"]["reference"], new_reference)
                        self.assertIn(new_reference["caution"], output.getvalue())
                    elif flag:
                        self.assertNotIn("owner/component", current["repos"])
                    else:
                        self.assertNotIn("reference", current["repos"]["owner/component"])
                    self.assertEqual(catalog.is_stale(current), not refreshed)

    def test_static_reference_uses_reviewed_id_when_its_old_name_is_reused(self):
        for flag in (None, "archived", "fork"):
            with self.subTest(flag=flag):
                saved = self.entry("owner/original", 1)
                saved["reference"] = self.reference
                self.write_catalog({"updated": "2026-11-14", "sources": {},
                                    "repos": {"owner/original": saved}})
                library = self.out / "reference-library.json"
                library.write_text(json.dumps({"schemaVersion": 2, "reviewed": "2026-11-14",
                                               "archive": self.reference["archive"],
                                               "repos": {"owner/original": self.reference}}), encoding="utf-8")
                replacement = self.repository("owner/original", 2)
                original = self.repository("owner/renamed", 1)
                if flag:
                    original[flag] = True

                def other_source(found, token):
                    catalog.add(found, "owner/original", "other-source", replacement)

                def remote(url, token=None):
                    if url == "https://api.github.com/repositories/1":
                        return json.dumps(original)
                    if url == "https://api.github.com/repos/owner/original":
                        return json.dumps(replacement)
                    raise AssertionError("unexpected network request")

                output = io.StringIO()
                with patch.object(catalog, "REFERENCE_FILE", library), \
                        patch.object(catalog, "SOURCES", [("other-source", other_source),
                                                         ("reference-library", catalog.source_references)]), \
                        patch.object(catalog, "github_token", return_value=None), \
                        patch.object(catalog, "fetch", side_effect=remote), \
                        contextlib.redirect_stdout(output):
                    catalog.update(argparse.Namespace(out=self.out))
                    catalog.find(argparse.Namespace(out=self.out, terms=["doctor admin"], limit=20, no_refresh=True))
                current = catalog.load_catalog(self.out / "catalog.json")
                self.assertEqual(current["repos"]["owner/renamed"]["reference"], self.reference)
                self.assertEqual(current["repos"]["owner/renamed"]["first_seen"], saved["first_seen"])
                self.assertEqual(current["repos"]["owner/renamed"]["stars_first_seen"], saved["stars_first_seen"])
                self.assertNotIn("reference", current["repos"]["owner/original"])
                self.assertIn("[owner/renamed]", output.getvalue())
                self.assertNotIn("[owner/original]", output.getvalue())
                self.assertFalse(catalog.is_stale(current))

    def test_name_collision_order_preserves_renamed_original_during_outage(self):
        for flag in (None, "archived", "fork"):
            for replacement_first in (True, False):
                with self.subTest(flag=flag, replacement_first=replacement_first):
                    saved = self.entry("owner/original", 1)
                    saved["reference"] = self.reference
                    self.write_catalog({"updated": "2026-11-14", "sources": {},
                                        "repos": {"owner/original": saved}})
                    replacement = self.repository("owner/original", 2)
                    original = self.repository("owner/renamed", 1)
                    if flag:
                        original[flag] = True

                    def unavailable(found, token):
                        raise ValueError("reference collector unavailable")

                    def other_source(found, token):
                        observations = [replacement, original] if replacement_first else [original, replacement]
                        for repo in observations:
                            catalog.add(found, repo["full_name"], "other-source", repo)

                    output = io.StringIO()
                    with patch.object(catalog, "SOURCES", [("reference-library", unavailable),
                                                          ("other-source", other_source)]), \
                            patch.object(catalog, "github_token", return_value=None), \
                            contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
                        catalog.update(argparse.Namespace(out=self.out))
                        catalog.find(argparse.Namespace(out=self.out, terms=["doctor admin"], limit=20, no_refresh=True))
                    current = catalog.load_catalog(self.out / "catalog.json")
                    restored = current["repos"]["owner/renamed"]
                    self.assertEqual(restored["reference"], self.reference)
                    self.assertEqual(restored["first_seen"], saved["first_seen"])
                    self.assertEqual(restored["stars_first_seen"], saved["stars_first_seen"])
                    self.assertIn("earlier-source", restored["seen_in"])
                    self.assertNotIn("reference", current["repos"]["owner/original"])
                    self.assertIn(self.reference["caution"], output.getvalue())
                    self.assertIn("[owner/renamed]", output.getvalue())
                    self.assertNotIn("[owner/original]", output.getvalue())
                    self.assertTrue(catalog.is_stale(current))

    def test_reviewed_id_lookup_rejects_wrong_identity_and_private_metadata(self):
        library = self.out / "reference-library.json"
        library.write_text(json.dumps({"schemaVersion": 2, "reviewed": "2026-11-14",
                                       "archive": self.reference["archive"],
                                       "repos": {"owner/original": self.reference}}), encoding="utf-8")
        for private in (False, True):
            with self.subTest(private=private):
                self.write_catalog({"updated": None, "sources": {}, "repos": {}})
                response = self.repository("unrelated/replacement", 1 if private else 2)
                response["private"] = private
                output = io.StringIO()
                with patch.object(catalog, "REFERENCE_FILE", library), \
                        patch.object(catalog, "SOURCES", [("reference-library", catalog.source_references)]), \
                        patch.object(catalog, "github_token", return_value=None), \
                        patch.object(catalog, "fetch", return_value=json.dumps(response)), \
                        contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
                    catalog.update(argparse.Namespace(out=self.out))
                    catalog.find(argparse.Namespace(out=self.out, terms=["doctor admin"], limit=20, no_refresh=True))
                current = catalog.load_catalog(self.out / "catalog.json")
                self.assertEqual(current["repos"], {})
                self.assertTrue(catalog.is_stale(current))
                self.assertNotIn(self.reference["caution"], output.getvalue())
                self.assertNotIn("unrelated/replacement", output.getvalue())

    def test_authenticated_private_search_cannot_publish_metadata_through_ordinary_path(self):
        library = self.out / "reference-library.json"
        library.write_text(json.dumps({"schemaVersion": 2, "reviewed": "2026-11-14",
                                       "archive": self.reference["archive"],
                                       "repos": {"owner/original": self.reference}}), encoding="utf-8")
        private = self.repository("private-owner/secret-project", 1)
        private.update(private=True, description="confidential internal project")
        public = self.repository("public-owner/search-result", 2)

        def search(found, token):
            catalog.add(found, private["full_name"], "github-search:topic", private)
            catalog.add(found, public["full_name"], "github-search:topic", public)

        for cached in (None, "public", "previous-private"):
            for curated in (False, True):
                with self.subTest(cached=cached, curated=curated):
                    saved = self.entry(private["full_name"] if cached == "previous-private" else "owner/original")
                    if cached == "previous-private":
                        saved["description"] = private["description"]
                    if curated:
                        saved["reference"] = self.reference
                    self.write_catalog({"updated": "2026-11-14", "sources": {},
                                        "repos": {saved["name"].lower(): saved} if cached else {}})
                    sources = [("github-search", search)]
                    if curated:
                        sources.append(("reference-library", catalog.source_references))
                    output = io.StringIO()
                    with patch.object(catalog, "REFERENCE_FILE", library), \
                            patch.object(catalog, "SOURCES", sources), \
                            patch.object(catalog, "github_token", return_value="synthetic"), \
                            patch.object(catalog, "fetch", return_value=json.dumps(private)), \
                            contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
                        catalog.update(argparse.Namespace(out=self.out))
                        catalog.find(argparse.Namespace(out=self.out, terms=["secret-project"],
                                                        limit=20, no_refresh=True))
                    current = catalog.load_catalog(self.out / "catalog.json")
                    self.assertIn(public["full_name"], current["repos"])
                    artifacts = output.getvalue() + (self.out / "catalog.json").read_text(encoding="utf-8")
                    artifacts += (self.out / "README.md").read_text(encoding="utf-8")
                    self.assertNotIn(private["full_name"], artifacts)
                    self.assertNotIn(private["description"], artifacts)

    def test_malformed_metadata_ids_cannot_publish_or_resolve_curated_identity(self):
        library = self.out / "reference-library.json"
        library.write_text(json.dumps({"schemaVersion": 2, "reviewed": "2026-11-14",
                                       "archive": self.reference["archive"],
                                       "repos": {"owner/original": self.reference}}), encoding="utf-8")
        public = self.repository("public-owner/search-result", 2)
        for invalid_id in (True, 1.0, "1", None, 0, -1):
            for curated in (False, True):
                with self.subTest(invalid_id=invalid_id, curated=curated):
                    self.write_catalog({"updated": None, "sources": {}, "repos": {}})
                    malformed = self.repository("unrelated/replacement", invalid_id)

                    def search(found, token):
                        catalog.add(found, malformed["full_name"], "github-search:topic", malformed)
                        catalog.add(found, public["full_name"], "github-search:topic", public)

                    sources = [("github-search", search)]
                    if curated:
                        sources.append(("reference-library", catalog.source_references))
                    with patch.object(catalog, "REFERENCE_FILE", library), \
                            patch.object(catalog, "SOURCES", sources), \
                            patch.object(catalog, "github_token", return_value=None), \
                            patch.object(catalog, "fetch", return_value=json.dumps(malformed)), \
                            contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        catalog.update(argparse.Namespace(out=self.out))
                    current = catalog.load_catalog(self.out / "catalog.json")
                    self.assertEqual(set(current["repos"]), {public["full_name"]})
                    self.assertNotIn(self.reference["caution"], (self.out / "README.md").read_text(encoding="utf-8"))
                    if curated:
                        self.assertTrue(catalog.is_stale(current))

    def test_repeated_github_search_rows_preserve_every_private_identity(self):
        private_one = self.repository("collision/project", 1)
        private_one.update(private=True, description="private-sentinel-metadata")
        private_three = {**private_one, "id": 3}
        conflicting_public = {**private_one, "id": 2, "private": False}
        eligible = self.repository("public-owner/eligible", 4)
        for observations in ((private_one, private_three, conflicting_public),
                             (conflicting_public, private_three, private_one)):
            with self.subTest(final_private=observations[-1]["private"]):
                saved = {}
                for identity in (1, 3):
                    name = f"earlier/original-{identity}"
                    entry = self.entry(name, identity)
                    entry["description"] = private_one["description"]
                    entry["reference"] = {**self.reference, "github_id": identity}
                    saved[name] = entry
                self.write_catalog({"updated": "2026-11-14", "sources": {}, "repos": saved})
                responses = iter([[observations[0], eligible], [observations[1]], [observations[2]]])

                def remote(url, token=None):
                    return json.dumps({"items": next(responses, [])})

                output = io.StringIO()
                with patch.object(catalog, "SOURCES", [("github-search", catalog.source_github_search)]), \
                        patch.object(catalog, "WATCH_TOPICS", ["synthetic"]), \
                        patch.object(catalog, "github_token", return_value="synthetic"), \
                        patch.object(catalog, "fetch", side_effect=remote), \
                        contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
                    catalog.update(argparse.Namespace(out=self.out))
                    catalog.find(argparse.Namespace(out=self.out, terms=["sentinel"],
                                                    limit=20, no_refresh=True))
                current = catalog.load_catalog(self.out / "catalog.json")
                self.assertEqual(set(current["repos"]), {eligible["full_name"]})
                artifacts = output.getvalue() + (self.out / "catalog.json").read_text(encoding="utf-8")
                artifacts += (self.out / "README.md").read_text(encoding="utf-8")
                self.assertNotIn(private_one["description"], artifacts)

    def test_invalid_cached_reference_authority_is_rejected_without_or_with_refresh(self):
        for annotation_id, metadata_id in ((True, 1), (1.0, 1), ("1", 1), (2, 1),
                                           (0, 1), (-1, 1), (1, True), (1, 1.0)):
            for refresh in (False, True):
                with self.subTest(annotation_id=annotation_id, metadata_id=metadata_id, refresh=refresh):
                    saved = self.entry("owner/current")
                    saved["github_id"] = metadata_id
                    saved["reference"] = {**self.reference, "github_id": annotation_id,
                                          "topics": ["authority-marker"], "caution": "UNTRUSTED ID ANNOTATION"}
                    self.write_catalog({"updated": "2026-11-14", "sources": {},
                                        "reference_revision": catalog.REFERENCE_REVISION,
                                        "repos": {"owner/current": saved}})

                    def source(found, token):
                        catalog.add(found, "owner/current", "ordinary-search", self.repository("owner/current"))

                    output = io.StringIO()
                    with patch.object(catalog, "SOURCES", [("ordinary-search", source)]), \
                            patch.object(catalog, "github_token", return_value=None), \
                            contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
                        if refresh:
                            catalog.update(argparse.Namespace(out=self.out))
                        catalog.find(argparse.Namespace(out=self.out, terms=["authority-marker"],
                                                        limit=20, no_refresh=True))
                    current = catalog.load_catalog(self.out / "catalog.json")
                    if refresh or type(metadata_id) is int:
                        self.assertIn("owner/current", current["repos"])
                        self.assertNotIn("reference", current["repos"]["owner/current"])
                    else:
                        self.assertNotIn("owner/current", current["repos"])
                    self.assertTrue(catalog.is_stale(current))
                    self.assertNotIn("UNTRUSTED ID ANNOTATION", output.getvalue())
                    if refresh:
                        self.assertNotIn("UNTRUSTED ID ANNOTATION",
                                         (self.out / "README.md").read_text(encoding="utf-8"))

    def test_matching_publication_revision_cannot_authorize_malformed_cached_ids(self):
        for annotation_id in (True, 1.0, "1", 2):
            with self.subTest(annotation_id=annotation_id):
                saved = self.entry("owner/original")
                saved["reference"] = self.reference
                local = {"updated": "2026-11-13", "sources": {}, "repos": {"owner/original": saved}}
                self.write_catalog(local)
                before = (self.out / "catalog.json").read_bytes()
                remote_entry = self.entry("unrelated/replacement")
                remote_entry["reference"] = {**self.reference, "github_id": annotation_id,
                                             "caution": "UNTRUSTED ID ANNOTATION"}
                publication = {"updated": "2026-11-14", "sources": {},
                               "reference_revision": catalog.REFERENCE_REVISION,
                               "repos": {"unrelated/replacement": remote_entry}}
                with patch.object(catalog, "PUBLISHED", "https://example.test/catalog.json"), \
                        patch.object(catalog, "fetch", return_value=json.dumps(publication)):
                    self.assertFalse(catalog.fetch_published(self.out, local))
                self.assertEqual((self.out / "catalog.json").read_bytes(), before)

    def test_malformed_annotation_shapes_do_not_hide_remaining_search_results(self):
        valid = {**self.reference, "github_id": 2}
        malformed = ["not-an-object", [], True, False, 0, None, {},
                     {**valid, "reviewed": None}, {**valid, "topics": "doctor admin"},
                     {**valid, "topics": [1]}, {**valid, "caution": {"invalid": True}}]
        missing_date = dict(valid)
        missing_date.pop("reviewed")
        missing_caution = dict(valid)
        missing_caution.pop("caution")
        malformed += [missing_date, missing_caution]
        for bad_reference in malformed:
            with self.subTest(annotation=bad_reference):
                good = self.entry("owner/usable", 1)
                good["reference"] = self.reference
                bad = self.entry("owner/malformed", 2)
                bad["reference"] = bad_reference
                self.write_catalog({"updated": "2026-11-14", "sources": {},
                                    "reference_revision": catalog.REFERENCE_REVISION,
                                    "repos": {"owner/usable": good, "owner/malformed": bad}})
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    catalog.find(argparse.Namespace(out=self.out, terms=["doctor admin"],
                                                    limit=20, no_refresh=True))
                current = catalog.load_catalog(self.out / "catalog.json")
                self.assertNotIn("reference", current["repos"]["owner/malformed"])
                self.assertTrue(catalog.is_stale(current))
                self.assertIn("[owner/usable]", output.getvalue())
                self.assertIn(self.reference["caution"], output.getvalue())

    def test_newer_incompatible_publication_cannot_erase_saved_reference_on_api_failure(self):
        saved = self.entry("new-owner/component")
        saved["reference"] = self.reference
        self.write_catalog({"updated": "2026-11-14", "sources": {},
                            "reference_revision": catalog.REFERENCE_REVISION,
                            "repos": {"new-owner/component": saved}})
        incompatible = dict(saved)
        incompatible.pop("reference")
        published = {"updated": "2026-11-15", "sources": {},
                     "repos": {"new-owner/component": incompatible}}

        def source(found, token):
            catalog.add(found, "old-owner/component", "reference-library")
            found["old-owner/component"]["reference"] = self.reference

        def remote(url, token=None):
            if url == "https://example.test/catalog.json":
                return json.dumps(published)
            raise urllib.error.URLError("temporary enrichment failure")

        output = io.StringIO()
        with patch.object(catalog, "today", return_value=dt.date(2026, 11, 16)), \
                patch.object(catalog, "PUBLISHED", "https://example.test/catalog.json"), \
                patch.object(catalog, "SOURCES", [("reference-library", source)]), \
                patch.object(catalog, "github_token", return_value=None), \
                patch.object(catalog, "fetch", side_effect=remote), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            catalog.find(argparse.Namespace(out=self.out, terms=["doctor admin"], limit=20, no_refresh=False))
        self.assertIn("[new-owner/component]", output.getvalue())
        self.assertIn(self.reference["caution"], output.getvalue())


if __name__ == "__main__":
    unittest.main()
