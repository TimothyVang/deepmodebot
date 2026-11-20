import csv
import importlib.util
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

SCRIPT_PATH = Path(__file__).resolve().parent / "yt_enrich.py"
SPEC = importlib.util.spec_from_file_location("yt_enrich", SCRIPT_PATH)
yt = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(yt)


class TestYtEnrich(unittest.TestCase):
    def test_parse_video_id(self):
        for raw in (
            "L1OBRtfPS34",
            "https://www.youtube.com/watch?v=L1OBRtfPS34&t=42s",
            "https://youtu.be/L1OBRtfPS34",
            "https://www.youtube.com/shorts/L1OBRtfPS34",
            "https://www.youtube.com/live/L1OBRtfPS34?feature=share",
        ):
            self.assertEqual(yt.parse_video_id(raw), "L1OBRtfPS34")

    def test_redirect_unwrap_and_classification(self):
        links = yt.extract_companion_links(
            [
                "Code: https://www.youtube.com/redirect?q=https%3A%2F%2Fgithub.com%2Fowner%2Frepo&v=L1OBRtfPS34 "
                "Board: https://www.tldraw.com/f/abc123 "
                "Slides: https://speakerdeck.com/foo/bar "
                "Paper: https://arxiv.org/abs/2501.00001 "
                "Pod: https://podcasts.apple.com/us/podcast/test/id123 "
                "Ignore: https://www.youtube.com/watch?v=L1OBRtfPS34"
            ]
        )
        self.assertEqual(links["github"], ["https://github.com/owner/repo"])
        self.assertEqual(links["canvas"], ["https://www.tldraw.com/f/abc123"])
        self.assertEqual(links["slides"], ["https://speakerdeck.com/foo/bar"])
        self.assertEqual(links["paper"], ["https://arxiv.org/abs/2501.00001"])
        self.assertEqual(links["podcast"], ["https://podcasts.apple.com/us/podcast/test/id123"])
        self.assertNotIn("youtube.com", json.dumps(links))

    def test_fail_fast_403_no_retries_and_redacts_key(self):
        calls = []

        def fake_urlopen(req, timeout=25):
            calls.append(req.full_url)
            raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, io.BytesIO(b"quotaExceeded"))

        with mock.patch.dict(os.environ, {"YOUTUBE_API_KEY": "SUPER_SECRET_TEST_KEY"}), mock.patch.object(
            yt.urllib.request, "urlopen", side_effect=fake_urlopen
        ):
            with tempfile.TemporaryDirectory() as td:
                out = Path(td) / "blocked.json"
                rc = yt.main(["--out", str(out), "api-video", "L1OBRtfPS34"])
                self.assertEqual(rc, yt.EXIT_BLOCKED)
                self.assertEqual(len(calls), 1)
                raw = out.read_text(encoding="utf-8")
                self.assertNotIn("SUPER_SECRET_TEST_KEY", raw)
                data = json.loads(raw)
                self.assertEqual(data["state"], "blocked")
                self.assertEqual(data["http_status"], 403)

    def test_fail_fast_429_no_retries(self):
        calls = []

        def fake_urlopen(req, timeout=25):
            calls.append(req.full_url)
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, io.BytesIO(b"rate limited"))

        with mock.patch.object(yt.urllib.request, "urlopen", side_effect=fake_urlopen):
            with tempfile.TemporaryDirectory() as td:
                out = Path(td) / "blocked429.json"
                rc = yt.main(["--out", str(out), "oembed", "L1OBRtfPS34"])
                self.assertEqual(rc, yt.EXIT_BLOCKED)
                self.assertEqual(len(calls), 1)
                self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["http_status"], 429)

    def test_channel_tabs_lockup_and_fallback_rejection(self):
        fake_data = {
            "metadata": {"channelMetadataRenderer": {"externalId": "UC1234567890123456789012", "title": "TestChan"}},
            "contents": {
                "twoColumnBrowseResultsRenderer": {
                    "tabs": [
                        {
                            "tabRenderer": {
                                "title": "Videos",
                                "selected": True,
                                "endpoint": {"commandMetadata": {"webCommandMetadata": {"url": "/@test/videos"}}},
                                "content": {
                                    "richGridRenderer": {
                                        "contents": [
                                            {
                                                "richItemRenderer": {
                                                    "content": {
                                                        "lockupViewModel": {
                                                            "contentId": "L1OBRtfPS34",
                                                            "contentImage": {
                                                                "thumbnailViewModel": {
                                                                    "overlays": [
                                                                        {
                                                                            "thumbnailBottomOverlayViewModel": {
                                                                                "badges": [
                                                                                    {
                                                                                        "thumbnailBadgeViewModel": {
                                                                                            "text": "45:18",
                                                                                            "badgeStyle": "THUMBNAIL_OVERLAY_BADGE_STYLE_DEFAULT",
                                                                                        }
                                                                                    }
                                                                                ]
                                                                            }
                                                                        }
                                                                    ]
                                                                }
                                                            },
                                                            "metadata": {
                                                                "lockupMetadataViewModel": {
                                                                    "title": {"content": "Demo Talk"},
                                                                    "metadata": {
                                                                        "contentMetadataViewModel": {
                                                                            "metadataRows": [
                                                                                {
                                                                                    "metadataParts": [
                                                                                        {"text": {"content": "360K"}, "accessibilityLabel": "360 thousand views"},
                                                                                        {"text": {"content": "1mo ago"}, "accessibilityLabel": "1 month ago"},
                                                                                    ]
                                                                                }
                                                                            ]
                                                                        }
                                                                    },
                                                                }
                                                            },
                                                        }
                                                    }
                                                }
                                            },
                                            {"continuationItemRenderer": {"token": "abc"}},
                                        ]
                                    }
                                },
                            }
                        }
                    ]
                }
            },
        }
        html = f"<script>var ytInitialData = {json.dumps(fake_data)};</script>"
        ok = yt.parse_channel_tab_html(html, "videos", "https://www.youtube.com/@test/videos")
        self.assertTrue(ok["tab_verified"])
        self.assertTrue(ok["has_continuation"])
        self.assertEqual(ok["item_count"], 1)
        self.assertEqual(ok["items"][0]["duration_text"], "45:18")
        fb = yt.parse_channel_tab_html(html, "shorts", "https://www.youtube.com/@test/shorts")
        self.assertFalse(fb["tab_verified"])
        self.assertEqual(fb["items"], [])
        self.assertEqual(fb["unverified_fallback_count"], 1)

    def test_batch_resume_and_instant_403_halt(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            inp = td_path / "ids.json"
            inp.write_text(json.dumps(["aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"]), encoding="utf-8")
            (td_path / "items.jsonl").write_text(
                json.dumps({"id": "aaaaaaaaaaa", "state": "ok", "title": "Cached"}) + "\n", encoding="utf-8"
            )
            calls = []

            def fake_inspect(ns):
                calls.append(ns.video)
                if ns.video == "bbbbbbbbbbb":
                    raise yt.BlockedError(
                        source_url="https://www.youtube.com/watch?v=bbbbbbbbbbb",
                        status=403,
                        reason="http_403",
                        evidence="403 test",
                    )
                return {"id": ns.video, "state": "ok", "title": "Should never run"}

            with mock.patch.object(yt, "cmd_inspect", side_effect=fake_inspect):
                rc = yt.main(["batch", str(inp), "--out-dir", str(td_path), "--mode", "inspect", "--delay", "0", "--jitter", "0"])
                self.assertEqual(rc, yt.EXIT_BLOCKED)
                self.assertEqual(calls, ["bbbbbbbbbbb"])
                blocked = json.loads((td_path / "blocked.json").read_text(encoding="utf-8"))
                self.assertEqual(blocked["source_id"], "bbbbbbbbbbb")
                self.assertEqual(blocked["previously_done"], 1)
                self.assertEqual(blocked["remaining_count"], 2)

    def test_render_dedupes_to_last_ok_and_validates_csv(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            jsonl = td_path / "items.jsonl"
            rows = [
                {
                    "id": "L1OBRtfPS34",
                    "state": "ok",
                    "title": 'Good, "Quoted" Title',
                    "date_text": "Oct 11, 2026",
                    "views_text": "1,234 views",
                    "observed_utc": "2026-11-19T00:00:00Z",
                    "chapters": [{"time": "0:00", "start_seconds": 0, "title": "Intro"}],
                    "companion_links": {"github": ["https://github.com/a/b"]},
                },
                {"id": "L1OBRtfPS34", "state": "error", "error": "timeout"},
                {"id": "ZZZZZZZZZZZ", "state": "error", "title": None, "observed_utc": "2026-11-19T00:01:00Z"},
            ]
            jsonl.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            tdir = td_path / "transcripts"
            tdir.mkdir()
            (tdir / "L1OBRtfPS34.json").write_text(
                json.dumps({"items": [{"chapter": "Intro"}, {"t": "0:05", "x": "Hello world"}]}), encoding="utf-8"
            )
            out = td_path / "rendered"
            rc = yt.main(["render", "--items", str(jsonl), "--out-dir", str(out), "--transcripts-dir", str(tdir)])
            self.assertEqual(rc, 0)
            with (out / "index.csv").open("r", encoding="utf-8", newline="") as cf:
                csv_rows = list(csv.DictReader(cf))
            self.assertEqual(len(csv_rows), 2)
            good = next(r for r in csv_rows if r["id"] == "L1OBRtfPS34")
            self.assertEqual(good["metadata_state"], "ok")
            self.assertEqual(good["date"], "2026-10-11")
            self.assertEqual(good["views"], "1234")
            bad = next(r for r in csv_rows if r["id"] == "ZZZZZZZZZZZ")
            self.assertEqual(bad["date"], "")
            self.assertEqual(bad["views"], "")


    def test_captions_meta_without_oauth_keeps_the_video_and_records_why(self):
        def fake_get(endpoint, params):
            if endpoint == "captions":
                raise yt.BlockedError(source_url="https://www.googleapis.com/youtube/v3/captions", status=401,
                                      reason="http_401", evidence="Login Required")
            return {"items": [{"id": "L1OBRtfPS34", "snippet": {"title": "t", "description": ""},
                               "contentDetails": {"caption": "true"}, "statistics": {}}]}

        args = mock.Mock(videos=["L1OBRtfPS34"], comments=0, captions_meta=True)
        with mock.patch.object(yt, "yt_api_get", side_effect=fake_get):
            out = yt.cmd_api_video(args)
        self.assertEqual(out["returned_count"], 1)
        record = out["items"][0]
        self.assertEqual(record["caption_tracks"], [])
        self.assertIn("OAuth", record["caption_tracks_error"])
        self.assertIn("401", record["caption_tracks_error"])

if __name__ == "__main__":
    unittest.main()
