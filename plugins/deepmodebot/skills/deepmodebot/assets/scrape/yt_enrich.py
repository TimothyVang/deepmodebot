#!/usr/bin/env python3
"""Media-free YouTube enrichment CLI for the ai-video-learning skill.

Extracts richer signal from YouTube videos and channels using official APIs,
public feeds, static thumbnails, single-request watch-page metadata, companion
link mining, and official Gemini multimodal YouTube URL analysis—without
fetching googlevideo.com media streams or retrying on HTTP 403/429 denials.

Exit codes:
  0  Success
  1  Usage, missing dependency/env, or parse error
  3  Blocked (HTTP 403/429, API quota/forbidden, login wall, or bot challenge)
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
)

EXIT_OK = 0
EXIT_ERR = 1
EXIT_BLOCKED = 3

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
URL_RE = re.compile(r"https?://[^\s<>()\"'\]\\]+")
CHAPTER_LINE_RE = re.compile(
    r"(?m)^\s*(?:[-*•]\s*)?((?:\d{1,2}:)?\d{1,2}:\d{2})\s*(?:[-–—:|]\s*|\s+)(.+?)\s*$"
)

CANVAS_HOSTS = ("tldraw.com", "excalidraw.com", "figma.com", "miro.com", "whimsical.com")
SLIDE_HOSTS = ("speakerdeck.com", "slides.com", "slideshare.net", "docs.google.com")
PAPER_HOSTS = ("arxiv.org", "openreview.net", "aclanthology.org", "semanticscholar.org", "huggingface.co")
PODCAST_HOSTS = ("podcasts.apple.com", "open.spotify.com", "overcast.fm", "transistor.fm", "simplecast.com", "buzzsprout.com")
SOCIAL_HOSTS = ("x.com", "twitter.com", "linkedin.com", "bsky.app", "threads.net", "discord.gg", "discord.com")
IGNORE_HOSTS = ("youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com", "i.ytimg.com", "yt3.ggpht.com")


class BlockedError(Exception):
    """Raised immediately on HTTP 403/429, login wall, or bot challenge (never retried)."""

    def __init__(self, *, source_url: str | None, status: int | None, reason: str, evidence: str):
        super().__init__(evidence)
        self.payload = {
            "state": "blocked",
            "observed_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "source_url": source_url,
            "http_status": status,
            "reason": reason,
            "evidence": evidence,
            "action": "Stopped immediately without retry. Record blocked.json and wait for user clearance.",
        }


def parse_video_id(value: str) -> str:
    """Extract an 11-character YouTube video ID from a bare ID or URL."""
    s = value.strip()
    if VIDEO_ID_RE.match(s):
        return s
    parsed = urllib.parse.urlparse(s)
    host = parsed.netloc.lower()
    if host in ("youtu.be", "www.youtu.be"):
        cand = parsed.path.lstrip("/").split("/")[0]
        if VIDEO_ID_RE.match(cand):
            return cand
    if "youtube.com" in host:
        qs = urllib.parse.parse_qs(parsed.query)
        if "v" in qs and VIDEO_ID_RE.match(qs["v"][0]):
            return qs["v"][0]
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2 and parts[0] in ("shorts", "live", "embed", "v") and VIDEO_ID_RE.match(parts[1]):
            return parts[1]
    raise ValueError(f"Could not extract YouTube video ID from: {value}")


def http_get_once(url: str, *, headers: dict[str, str] | None = None, timeout: int = 25) -> tuple[int, str]:
    """Single HTTP GET with zero retries. Fails fast on 403/429."""
    req_headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            body = resp.read().decode("utf-8", errors="replace")
            if status in (403, 429):
                raise BlockedError(
                    source_url=url,
                    status=status,
                    reason=f"http_{status}",
                    evidence=f"Single GET returned HTTP {status}.",
                )
            return status, body
    except urllib.error.HTTPError as exc:
        err_body = ""
        try:
            err_body = exc.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            pass
        if exc.code in (403, 429):
            raise BlockedError(
                source_url=url,
                status=exc.code,
                reason=f"http_{exc.code}",
                evidence=f"Single GET returned HTTP {exc.code}: {err_body.strip() or exc.reason}",
            ) from exc
        raise RuntimeError(f"HTTP {exc.code} for {url}: {err_body.strip() or exc.reason}") from exc


def http_get_bytes_once(url: str, *, headers: dict[str, str] | None = None, timeout: int = 25) -> tuple[int, bytes | None]:
    """Single binary HTTP GET with zero retries. Returns (404, None) on 404; fails fast on 403/429."""
    req_headers = {"User-Agent": USER_AGENT}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            data = resp.read()
            if status in (403, 429):
                raise BlockedError(
                    source_url=url,
                    status=status,
                    reason=f"http_{status}",
                    evidence=f"Single binary GET returned HTTP {status}.",
                )
            return status, data
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return 404, None
        if exc.code in (403, 429):
            raise BlockedError(
                source_url=url,
                status=exc.code,
                reason=f"http_{exc.code}",
                evidence=f"Single binary GET returned HTTP {exc.code}: {exc.reason}",
            ) from exc
        raise RuntimeError(f"HTTP {exc.code} for {url}: {exc.reason}") from exc


def unwrap_youtube_redirect(url: str) -> str:
    """Unwrap youtube.com/redirect?q=... links to their destination URL."""
    cleaned = url.rstrip(".,;:!?)\"'")
    parsed = urllib.parse.urlparse(cleaned)
    if parsed.netloc.lower().endswith("youtube.com") and parsed.path == "/redirect":
        qs = urllib.parse.parse_qs(parsed.query)
        if "q" in qs and qs["q"]:
            return urllib.parse.unquote(qs["q"][0]).rstrip(".,;:!?)\"'")
    return cleaned


def classify_url(url: str) -> str | None:
    """Classify an external companion URL into a source bucket; returns None for YouTube-internal links."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if not host or any(host == h or host.endswith("." + h) for h in IGNORE_HOSTS):
        return None
    if host in ("github.com", "www.github.com", "gist.github.com", "gitlab.com"):
        return "github"
    if any(host == h or host.endswith("." + h) for h in CANVAS_HOSTS):
        return "canvas"
    if any(host == h or host.endswith("." + h) for h in SLIDE_HOSTS) or path.endswith((".pdf", ".pptx", ".key")):
        if host == "docs.google.com" and "/presentation/" not in path:
            return "docs_or_web"
        return "slides"
    if any(host == h or host.endswith("." + h) for h in PAPER_HOSTS):
        return "paper"
    if any(host == h or host.endswith("." + h) for h in PODCAST_HOSTS):
        return "podcast"
    if any(host == h or host.endswith("." + h) for h in SOCIAL_HOSTS):
        return "social"
    return "docs_or_web"


def extract_companion_links(texts: list[str], extra_urls: list[str] | None = None) -> dict[str, list[str]]:
    """Extract, unwrap, deduplicate, and categorize companion URLs from text and structured link lists."""
    buckets: dict[str, list[str]] = {
        "github": [],
        "slides": [],
        "canvas": [],
        "paper": [],
        "podcast": [],
        "docs_or_web": [],
        "social": [],
    }
    seen: set[str] = set()
    candidates: list[str] = list(extra_urls or [])
    for blob in texts:
        if blob:
            candidates.extend(URL_RE.findall(blob))
    for raw in candidates:
        url = unwrap_youtube_redirect(raw)
        if url in seen:
            continue
        bucket = classify_url(url)
        if bucket is None:
            continue
        seen.add(url)
        buckets[bucket].append(url)
    return {k: v for k, v in buckets.items() if v}


def parse_timestamp_seconds(ts: str) -> int | None:
    """Convert MM:SS or HH:MM:SS into integer seconds."""
    parts = ts.strip().split(":")
    if len(parts) not in (2, 3) or not all(p.isdigit() for p in parts):
        return None
    nums = [int(p) for p in parts]
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    return nums[0] * 3600 + nums[1] * 60 + nums[2]


def parse_chapters_from_description(description: str | None) -> list[dict[str, Any]]:
    """Parse creator timestamp chapters from a video description."""
    if not description:
        return []
    chapters: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for match in CHAPTER_LINE_RE.finditer(description):
        ts, title = match.group(1), match.group(2).strip()
        key = (ts, title)
        if key in seen:
            continue
        seen.add(key)
        chapters.append({"time": ts, "start_seconds": parse_timestamp_seconds(ts), "title": title})
    return chapters


def static_thumbnail_urls(video_id: str) -> dict[str, str]:
    """Standard static i.ytimg.com thumbnail and keyframe preview URLs (no media stream access)."""
    base = f"https://i.ytimg.com/vi/{video_id}"
    return {
        "maxres": f"{base}/maxresdefault.jpg",
        "sd": f"{base}/sddefault.jpg",
        "hq": f"{base}/hqdefault.jpg",
        "keyframe_1": f"{base}/hq1.jpg",
        "keyframe_2": f"{base}/hq2.jpg",
        "keyframe_3": f"{base}/hq3.jpg",
    }


def extract_json_var(html: str, var_name: str) -> dict[str, Any] | None:
    """Extract an embedded JSON object assigned to a JS variable in HTML."""
    m = re.search(r'(?:var |window\[")' + re.escape(var_name) + r'(?:"\])?\s*=\s*', html)
    if not m:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(html, m.end())
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def yt_text(node: Any) -> str | None:
    if not node:
        return None
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        if "simpleText" in node:
            return node["simpleText"]
        if "runs" in node:
            return "".join(r.get("text", "") for r in node.get("runs", []) if isinstance(r, dict))
    return None


def walk_key(obj: Any, key: str):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                yield v
            yield from walk_key(v, key)
    elif isinstance(obj, list):
        for item in obj:
            yield from walk_key(item, key)


# --- Subcommand: feed (Tier 0) ---

def cmd_feed(args: argparse.Namespace) -> dict[str, Any]:
    if bool(args.channel_id) == bool(args.playlist_id):
        raise ValueError("Specify exactly one of --channel-id or --playlist-id.")
    if args.channel_id:
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={urllib.parse.quote(args.channel_id)}"
    else:
        url = f"https://www.youtube.com/feeds/videos.xml?playlist_id={urllib.parse.quote(args.playlist_id)}"
    _, xml_text = http_get_once(url)
    root = ET.fromstring(xml_text)
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
        "media": "http://search.yahoo.com/mrss/",
    }
    entries = []
    for entry in root.findall("atom:entry", ns):
        vid = entry.findtext("yt:videoId", default="", namespaces=ns)
        title = entry.findtext("atom:title", default="", namespaces=ns)
        published = entry.findtext("atom:published", default="", namespaces=ns)
        updated = entry.findtext("atom:updated", default="", namespaces=ns)
        author = entry.findtext("atom:author/atom:name", default="", namespaces=ns)
        group = entry.find("media:group", ns)
        description = group.findtext("media:description", default="", namespaces=ns) if group is not None else ""
        thumb_el = group.find("media:thumbnail", ns) if group is not None else None
        stats_el = group.find("media:community/media:statistics", ns) if group is not None else None
        views = int(stats_el.attrib["views"]) if (stats_el is not None and "views" in stats_el.attrib) else None
        entries.append(
            {
                "id": vid,
                "url": f"https://www.youtube.com/watch?v={vid}" if vid else None,
                "title": title,
                "author": author,
                "published": published,
                "updated": updated,
                "views": views,
                "thumbnail": thumb_el.attrib.get("url") if thumb_el is not None else None,
                "description": description,
                "chapters": parse_chapters_from_description(description),
                "companion_links": extract_companion_links([description]),
            }
        )
    return {
        "state": "ok",
        "source_tier": "tier0_atom_feed",
        "source_url": url,
        "observed_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "feed_title": root.findtext("atom:title", default="", namespaces=ns),
        "entry_count": len(entries),
        "entries": entries,
    }


# --- Subcommand: oembed (Tier 0) ---

def cmd_oembed(args: argparse.Namespace) -> dict[str, Any]:
    vid = parse_video_id(args.video)
    watch_url = f"https://www.youtube.com/watch?v={vid}"
    url = f"https://www.youtube.com/oembed?url={urllib.parse.quote(watch_url, safe='')}&format=json"
    _, body = http_get_once(url)
    data = json.loads(body)
    return {
        "state": "ok",
        "source_tier": "tier0_oembed",
        "observed_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "id": vid,
        "url": watch_url,
        "title": data.get("title"),
        "author_name": data.get("author_name"),
        "author_url": data.get("author_url"),
        "thumbnail_url": data.get("thumbnail_url"),
        "thumbnail_width": data.get("thumbnail_width"),
        "thumbnail_height": data.get("thumbnail_height"),
        "static_thumbnails": static_thumbnail_urls(vid),
    }


# --- Subcommand: api-video & api-channel (Tier 1: Official YouTube Data API v3) ---

def require_youtube_api_key() -> str:
    key = os.environ.get("YOUTUBE_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("Missing YOUTUBE_API_KEY (or GOOGLE_API_KEY) environment variable.")
    return key


def yt_api_get(endpoint: str, params: dict[str, str]) -> dict[str, Any]:
    key = require_youtube_api_key()
    safe_params = dict(params)
    full_params = dict(params, key=key)
    safe_url = f"https://www.googleapis.com/youtube/v3/{endpoint}?{urllib.parse.urlencode(safe_params)}"
    full_url = f"https://www.googleapis.com/youtube/v3/{endpoint}?{urllib.parse.urlencode(full_params)}"
    try:
        _, body = http_get_once(full_url)
    except BlockedError as exc:
        exc.payload["source_url"] = safe_url  # Never leak API key into logs or blocked.json
        raise
    except RuntimeError as exc:
        raise RuntimeError(str(exc).replace(key, "<REDACTED>")) from exc
    return json.loads(body)


def cmd_api_video(args: argparse.Namespace) -> dict[str, Any]:
    video_ids = [parse_video_id(v) for v in args.videos]
    items_out: list[dict[str, Any]] = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        resp = yt_api_get(
            "videos",
            {
                "part": "snippet,contentDetails,statistics,topicDetails,liveStreamingDetails",
                "id": ",".join(batch),
            },
        )
        for item in resp.get("items", []):
            vid = item["id"]
            snippet = item.get("snippet", {})
            details = item.get("contentDetails", {})
            stats = item.get("statistics", {})
            desc = snippet.get("description", "")
            record: dict[str, Any] = {
                "id": vid,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "title": snippet.get("title"),
                "channel_id": snippet.get("channelId"),
                "channel_title": snippet.get("channelTitle"),
                "published_at": snippet.get("publishedAt"),
                "duration_iso8601": details.get("duration"),
                "has_captions": details.get("caption") == "true",
                "tags": snippet.get("tags", []),
                "category_id": snippet.get("categoryId"),
                "topic_categories": item.get("topicDetails", {}).get("topicCategories", []),
                "live_streaming_details": item.get("liveStreamingDetails"),
                "views": int(stats["viewCount"]) if "viewCount" in stats else None,
                "likes": int(stats["likeCount"]) if "likeCount" in stats else None,
                "comment_count": int(stats["commentCount"]) if "commentCount" in stats else None,
                "description": desc,
                "chapters": parse_chapters_from_description(desc),
                "thumbnails": snippet.get("thumbnails", {}),
                "static_thumbnails": static_thumbnail_urls(vid),
            }
            comment_texts: list[str] = []
            if args.comments > 0:
                c_resp = yt_api_get(
                    "commentThreads",
                    {
                        "part": "snippet",
                        "videoId": vid,
                        "order": "relevance",
                        "maxResults": str(min(args.comments, 100)),
                        "textFormat": "plainText",
                    },
                )
                comments = []
                for c_item in c_resp.get("items", []):
                    top = c_item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                    text_val = top.get("textDisplay", "")
                    comment_texts.append(text_val)
                    comments.append(
                        {
                            "author": top.get("authorDisplayName"),
                            "author_channel_id": top.get("authorChannelId", {}).get("value"),
                            "is_channel_owner": top.get("authorChannelId", {}).get("value") == snippet.get("channelId"),
                            "published_at": top.get("publishedAt"),
                            "likes": top.get("likeCount"),
                            "text": text_val,
                        }
                    )
                record["top_comments"] = comments
            if args.captions_meta:
                # captions.list needs OAuth 2.0; an API key alone is refused. Record that and keep the video.
                try:
                    cap_resp = yt_api_get("captions", {"part": "snippet", "videoId": vid})
                except (BlockedError, RuntimeError) as exc:
                    cap_resp = {}
                    status = exc.payload.get("http_status") if isinstance(exc, BlockedError) else None
                    record["caption_tracks_error"] = (
                        f"captions.list refused the API key (HTTP {status or 'error'}); it requires OAuth 2.0")
                record["caption_tracks"] = [
                    {
                        "language": c.get("snippet", {}).get("language"),
                        "name": c.get("snippet", {}).get("name"),
                        "track_kind": c.get("snippet", {}).get("trackKind"),
                        "status": c.get("snippet", {}).get("status"),
                    }
                    for c in cap_resp.get("items", [])
                ]
            record["companion_links"] = extract_companion_links([desc, *comment_texts])
            items_out.append(record)
    return {
        "state": "ok",
        "source_tier": "tier1_youtube_data_api_v3",
        "observed_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "requested_count": len(video_ids),
        "returned_count": len(items_out),
        "items": items_out,
    }


def cmd_api_channel(args: argparse.Namespace) -> dict[str, Any]:
    ch_resp = yt_api_get("channels", {"part": "snippet,contentDetails,statistics", "id": args.channel_id})
    ch_items = ch_resp.get("items", [])
    if not ch_items:
        raise RuntimeError(f"Channel not found: {args.channel_id}")
    ch = ch_items[0]
    uploads_id = ch.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
    if not uploads_id:
        raise RuntimeError(f"No uploads playlist found for channel: {args.channel_id}")

    videos: list[dict[str, Any]] = []
    page_token: str | None = None
    while len(videos) < args.limit:
        page_size = min(50, args.limit - len(videos))
        params = {"part": "snippet,contentDetails", "playlistId": uploads_id, "maxResults": str(page_size)}
        if page_token:
            params["pageToken"] = page_token
        pl_resp = yt_api_get("playlistItems", params)
        for item in pl_resp.get("items", []):
            sn = item.get("snippet", {})
            cd = item.get("contentDetails", {})
            vid = cd.get("videoId") or sn.get("resourceId", {}).get("videoId")
            videos.append(
                {
                    "id": vid,
                    "url": f"https://www.youtube.com/watch?v={vid}" if vid else None,
                    "title": sn.get("title"),
                    "published_at": cd.get("videoPublishedAt") or sn.get("publishedAt"),
                    "position": sn.get("position"),
                }
            )
        page_token = pl_resp.get("nextPageToken")
        if not page_token:
            break
    return {
        "state": "ok",
        "source_tier": "tier1_youtube_data_api_v3_channel",
        "observed_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "channel_id": args.channel_id,
        "channel_title": ch.get("snippet", {}).get("title"),
        "uploads_playlist_id": uploads_id,
        "reported_video_count": ch.get("statistics", {}).get("videoCount"),
        "returned_count": len(videos),
        "videos": videos,
    }


# --- Subcommand: inspect (Tier 2: Single-GET Watch Page, zero retries, zero media playback) ---

def parse_watch_html(video_id: str, html: str, source_url: str) -> dict[str, Any]:
    """Parse rich metadata, chapters+thumbs, heatmap peaks, caption inventory, and links from one watch-page HTML."""
    initial_data = extract_json_var(html, "ytInitialData")
    player_resp = extract_json_var(html, "ytInitialPlayerResponse") or {}

    playability = player_resp.get("playabilityStatus", {})
    playability_status = playability.get("status")
    playability_reason = playability.get("reason") or ""

    if not initial_data:
        if "LOGIN_REQUIRED" in html or "Sign in to confirm" in html:
            raise BlockedError(
                source_url=source_url,
                status=200,
                reason="bot_or_login_wall",
                evidence="Watch page omitted ytInitialData and indicated a login/bot check.",
            )
        raise RuntimeError("Watch page HTML did not contain ytInitialData.")

    results_contents = (
        initial_data.get("contents", {})
        .get("twoColumnWatchNextResults", {})
        .get("results", {})
        .get("results", {})
        .get("contents", [])
    )
    prim = next((c["videoPrimaryInfoRenderer"] for c in results_contents if "videoPrimaryInfoRenderer" in c), {})
    sec = next((c["videoSecondaryInfoRenderer"] for c in results_contents if "videoSecondaryInfoRenderer" in c), {})

    # Description + structured redirect URLs
    desc_obj = sec.get("attributedDescription", {})
    description = desc_obj.get("content") or yt_text(sec.get("description")) or ""
    extra_urls: list[str] = []
    for cmd in walk_key(desc_obj, "urlEndpoint"):
        if isinstance(cmd, dict) and cmd.get("url"):
            u = cmd["url"]
            if u.startswith("/redirect"):
                u = "https://www.youtube.com" + u
            extra_urls.append(u)

    # Chapters + per-chapter thumbnails (i.ytimg.com)
    chapters: list[dict[str, Any]] = []
    seen_ch: set[tuple[str | None, str | None]] = set()
    for mm in walk_key(initial_data, "macroMarkersListItemRenderer"):
        if not isinstance(mm, dict):
            continue
        t_str = yt_text(mm.get("timeDescription"))
        title = yt_text(mm.get("title"))
        key = (t_str, title)
        if not t_str or key in seen_ch:
            continue
        seen_ch.add(key)
        thumbs = mm.get("thumbnail", {}).get("thumbnails", [])
        thumb_url = thumbs[-1].get("url") if thumbs else None
        chapters.append(
            {
                "time": t_str,
                "start_seconds": parse_timestamp_seconds(t_str),
                "title": title,
                "thumbnail": thumb_url,
            }
        )
    if not chapters:
        chapters = parse_chapters_from_description(description)

    # Most Replayed heatmap peaks (high-signal timestamps for diagrams/code/key points)
    heatmap_segments: list[dict[str, Any]] = []
    for hm in walk_key(initial_data, "heatMarkerRenderer"):
        if not isinstance(hm, dict):
            continue
        score = hm.get("intensityScoreNormalized")
        start_ms = hm.get("timeRangeStartMillis")
        dur_ms = hm.get("markerDurationMillis")
        if score is not None and start_ms is not None:
            heatmap_segments.append(
                {
                    "start_seconds": round(float(start_ms) / 1000.0, 1),
                    "duration_seconds": round(float(dur_ms or 0) / 1000.0, 1),
                    "intensity": round(float(score), 4),
                }
            )
    heatmap_peaks = sorted(
        [s for s in heatmap_segments if s["intensity"] >= 0.55],
        key=lambda x: x["intensity"],
        reverse=True,
    )[:8]

    # Microformat & videoDetails (exact ISO dates, length, tags, caption inventory)
    micro = player_resp.get("microformat", {}).get("playerMicroformatRenderer", {})
    vdetails = player_resp.get("videoDetails", {})
    owner = sec.get("owner", {}).get("videoOwnerRenderer", {})
    owner_name = yt_text(owner.get("title"))
    owner_channel_id = (
        owner.get("navigationEndpoint", {}).get("browseEndpoint", {}).get("browseId")
    )
    caption_tracks = []
    for tr in (
        player_resp.get("captions", {})
        .get("playerCaptionsTracklistRenderer", {})
        .get("captionTracks", [])
    ):
        caption_tracks.append(
            {
                "language_code": tr.get("languageCode"),
                "name": yt_text(tr.get("name")),
                "kind": tr.get("kind") or "manual",
                "is_translatable": bool(tr.get("isTranslatable")),
            }
        )
    if caption_tracks:
        caption_tracks_status = "present"
    elif playability_status and playability_status != "OK":
        caption_tracks_status = f"unknown_player_{playability_status.lower()}"
    elif not player_resp:
        caption_tracks_status = "unknown_no_player_response"
    else:
        caption_tracks_status = "absent"

    # Likes fallback: modern segmentedLikeDislikeButtonViewModel or legacy likeCountIfLikedNumber
    likes_val = next(walk_key(prim, "likeCountIfLikedNumber"), None)
    if likes_val is None:
        for like_vm in walk_key(prim, "likeButtonViewModel"):
            if isinstance(like_vm, dict):
                toggles = list(walk_key(like_vm, "defaultButtonViewModel"))
                for btn in toggles:
                    if isinstance(btn, dict):
                        txt = btn.get("buttonViewModel", {}).get("title")
                        if txt:
                            likes_val = txt
                            break
                if likes_val is not None:
                    break

    # Build suggested Gemini video_metadata windows from top heatmap peaks, falling back to chapters
    length_s = int(micro["lengthSeconds"]) if str(micro.get("lengthSeconds", "")).isdigit() else (
        int(vdetails["lengthSeconds"]) if str(vdetails.get("lengthSeconds", "")).isdigit() else None
    )
    suggested_windows: list[dict[str, Any]] = []
    for peak in heatmap_peaks[:4]:
        start_s = max(0, int(peak["start_seconds"]) - 15)
        end_s = int(peak["start_seconds"] + max(peak["duration_seconds"], 30)) + 15
        if length_s is not None:
            end_s = min(length_s, end_s)
        suggested_windows.append(
            {
                "start_offset": f"{start_s}s",
                "end_offset": f"{end_s}s",
                "fps": 1.0,
                "reason": f"Most Replayed peak (intensity={peak['intensity']})",
            }
        )
    if not suggested_windows and chapters:
        for idx, ch in enumerate(chapters):
            st = ch.get("start_seconds")
            if st is None:
                continue
            next_st = chapters[idx + 1].get("start_seconds") if idx + 1 < len(chapters) else length_s
            window: dict[str, Any] = {
                "start_offset": f"{st}s",
                "fps": 0.5,
                "reason": f"Chapter: {ch.get('title') or ch.get('time')}",
            }
            if next_st is not None and next_st > st:
                window["end_offset"] = f"{next_st}s"
            suggested_windows.append(window)

    resolved_channel_id = micro.get("externalChannelId") or vdetails.get("channelId") or owner_channel_id

    return {
        "state": "ok",
        "source_tier": "tier2_watch_page_single_get",
        "observed_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "title": yt_text(prim.get("title")) or vdetails.get("title") or yt_text(micro.get("title")),
        "channel_name": micro.get("ownerChannelName") or vdetails.get("author") or owner_name,
        "channel_id": resolved_channel_id,
        "channel_feed_url": (
            f"https://www.youtube.com/feeds/videos.xml?channel_id={resolved_channel_id}"
            if resolved_channel_id
            else None
        ),
        "date_text": yt_text(prim.get("dateText")),
        "publish_date": micro.get("publishDate"),
        "upload_date": micro.get("uploadDate"),
        "length_seconds": length_s,
        "category": micro.get("category"),
        "is_live_content": micro.get("isLiveContent", vdetails.get("isLiveContent")),
        "is_unlisted": micro.get("isUnlisted"),
        "views_text": yt_text(prim.get("viewCount", {}).get("videoViewCountRenderer", {}).get("viewCount")),
        "likes": likes_val,
        "player_playability": {"status": playability_status, "reason": playability_reason} if playability_status else None,
        "keywords": vdetails.get("keywords", []),
        "description": description,
        "chapters": chapters,
        "heatmap_segment_count": len(heatmap_segments),
        "heatmap_peaks": heatmap_peaks,
        "caption_tracks_status": caption_tracks_status,
        "caption_tracks": caption_tracks,
        "has_storyboards": bool(player_resp.get("storyboards")),
        "static_thumbnails": static_thumbnail_urls(video_id),
        "companion_links": extract_companion_links([description], extra_urls=extra_urls),
        "suggested_gemini_windows": suggested_windows,
    }


def cmd_inspect(args: argparse.Namespace) -> dict[str, Any]:
    vid = parse_video_id(args.video)
    url = f"https://www.youtube.com/watch?v={vid}&hl=en"
    _, html = http_get_once(url, headers={"Cookie": "SOCS=CAI"})
    return parse_watch_html(vid, html, url)


# --- Subcommand: gemini (Tier 4: Official Gemini API Multimodal Video Understanding) ---

DEFAULT_GEMINI_PROMPT = (
    "Analyze this public YouTube video segment as an engineering reference. Return structured Markdown with:\n"
    "1. Timestamped key claims and concrete workflows/commands spoken or shown on screen.\n"
    "2. On-screen text: slide titles, architecture diagram labels/arrows, code snippets, terminal commands, and URLs visible in browser bars or slides.\n"
    "3. Gaps or ambiguities where text was too small or cut off.\n"
    "Cite MM:SS timestamps for every item. Distinguish spoken assertions from text visibly shown on screen."
)


def cmd_gemini(args: argparse.Namespace) -> dict[str, Any]:
    vid = parse_video_id(args.video)
    watch_url = f"https://www.youtube.com/watch?v={vid}"
    video_meta: dict[str, Any] = {}
    if args.start:
        video_meta["start_offset"] = args.start if args.start.endswith("s") else f"{args.start}s"
    if args.end:
        video_meta["end_offset"] = args.end if args.end.endswith("s") else f"{args.end}s"
    if args.fps is not None:
        video_meta["fps"] = args.fps

    prompt_text = args.prompt or DEFAULT_GEMINI_PROMPT
    if args.dry_run:
        return {
            "state": "dry_run",
            "source_tier": "tier4_gemini_multimodal_youtube",
            "model": args.model,
            "file_uri": watch_url,
            "video_metadata": video_meta or None,
            "prompt": prompt_text,
            "api_key_present": bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
        }

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY (or GOOGLE_API_KEY) environment variable.")
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError("google-genai is not installed. Run: pip install google-genai") from exc

    client = genai.Client(api_key=api_key)
    part_kwargs: dict[str, Any] = {"file_data": types.FileData(file_uri=watch_url)}
    if video_meta:
        part_kwargs["video_metadata"] = types.VideoMetadata(**video_meta)

    try:
        response = client.models.generate_content(
            model=args.model,
            contents=types.Content(
                parts=[
                    types.Part(**part_kwargs),
                    types.Part(text=prompt_text),
                ]
            ),
        )
    except Exception as exc:
        msg = str(exc)
        if any(code in msg for code in ("403", "429", "RESOURCE_EXHAUSTED", "PERMISSION_DENIED")):
            raise BlockedError(
                source_url=watch_url,
                status=429 if ("429" in msg or "RESOURCE_EXHAUSTED" in msg) else 403,
                reason="gemini_api_blocked_or_quota",
                evidence=msg[:400],
            ) from exc
        raise

    return {
        "state": "ok",
        "source_tier": "tier4_gemini_multimodal_youtube",
        "observed_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "id": vid,
        "url": watch_url,
        "model": args.model,
        "video_metadata": video_meta or None,
        "text": response.text,
    }


# --- Subcommand: links (Tier 3 offline companion-link miner) ---

def cmd_links(args: argparse.Namespace) -> dict[str, Any]:
    texts: list[str] = []
    for p_str in args.files:
        path = Path(p_str)
        raw = path.read_text(encoding="utf-8", errors="replace")
        texts.append(raw)
    links = extract_companion_links(texts)
    return {
        "state": "ok",
        "source_tier": "tier3_companion_links_offline",
        "files_scanned": len(args.files),
        "total_links": sum(len(v) for v in links.values()),
        "companion_links": links,
    }


# --- Subcommand: channel-tabs (Tier 2: Tab-verified public initial HTML channel inventory) ---

def normalize_channel_base_url(raw: str) -> str:
    """Normalize a channel ID, @handle, or URL into https://www.youtube.com/<base>."""
    s = raw.strip().rstrip("/")
    if s.startswith("http://") or s.startswith("https://"):
        parsed = urllib.parse.urlparse(s)
        parts = [p for p in parsed.path.split("/") if p]
        if parts and parts[-1].lower() in ("videos", "shorts", "streams", "featured", "playlists", "community", "about"):
            parts = parts[:-1]
        if not parts:
            raise ValueError(f"Could not resolve channel path from URL: {raw}")
        return f"https://www.youtube.com/{'/'.join(parts)}"
    if s.startswith("@"):
        return f"https://www.youtube.com/{s}"
    if re.match(r"^UC[A-Za-z0-9_-]{20,}$", s):
        return f"https://www.youtube.com/channel/{s}"
    raise ValueError(f"Provide a UC... channel ID, @handle, or YouTube channel URL; got: {raw}")


def parse_channel_tab_html(html: str, requested_tab: str, source_url: str) -> dict[str, Any]:
    """Parse initial items from a YouTube channel tab HTML and verify which tab was actually selected."""
    initial_data = extract_json_var(html, "ytInitialData")
    if not initial_data:
        if "LOGIN_REQUIRED" in html or "Sign in to confirm" in html:
            raise BlockedError(
                source_url=source_url,
                status=200,
                reason="bot_or_login_wall",
                evidence=f"Channel tab /{requested_tab} omitted ytInitialData and indicated a login/bot check.",
            )
        raise RuntimeError(f"Channel tab /{requested_tab} HTML did not contain ytInitialData.")

    tabs = (
        initial_data.get("contents", {})
        .get("twoColumnBrowseResultsRenderer", {})
        .get("tabs", [])
    )
    selected_tab = None
    for t in tabs:
        tr = t.get("tabRenderer")
        if isinstance(tr, dict) and tr.get("selected"):
            selected_tab = tr
            break

    selected_title = selected_tab.get("title") if selected_tab else None
    selected_url = (
        selected_tab.get("endpoint", {})
        .get("commandMetadata", {})
        .get("webCommandMetadata", {})
        .get("url", "")
        if selected_tab
        else ""
    )
    expected_suffix = {"videos": "/videos", "shorts": "/shorts", "streams": "/streams"}.get(
        requested_tab, f"/{requested_tab}"
    )
    tab_verified = bool(
        selected_tab
        and (
            selected_url.rstrip("/").lower().endswith(expected_suffix)
            or (selected_title or "").strip().lower() in (requested_tab, "live" if requested_tab == "streams" else requested_tab)
        )
    )

    tab_content = selected_tab.get("content", {}) if selected_tab else {}
    has_continuation = any(True for _ in walk_key(tab_content, "continuationItemRenderer"))

    items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    # Modern 2026 channel grid items (lockupViewModel)
    for lv in walk_key(tab_content, "lockupViewModel"):
        if not isinstance(lv, dict):
            continue
        vid = lv.get("contentId")
        if not vid or not VIDEO_ID_RE.match(str(vid)) or vid in seen_ids:
            continue
        seen_ids.add(vid)
        lmeta = lv.get("metadata", {}).get("lockupMetadataViewModel", {})
        title = lmeta.get("title", {}).get("content")
        duration_text = None
        badge_styles: list[str] = []
        for badge in walk_key(lv.get("contentImage", {}), "thumbnailBadgeViewModel"):
            if isinstance(badge, dict):
                bs = str(badge.get("badgeStyle") or "")
                badge_styles.append(bs.upper())
                txt = badge.get("text")
                if txt and re.match(r"^(?:\d{1,2}:)?\d{1,2}:\d{2}$", str(txt).strip()):
                    duration_text = str(txt).strip()
                elif txt and str(txt).strip().upper() in ("LIVE", "UPCOMING", "PREMIERE"):
                    badge_styles.append(str(txt).strip().upper())

        views_text = None
        published_time_text = None
        meta_texts: list[str] = []
        for row in lmeta.get("metadata", {}).get("contentMetadataViewModel", {}).get("metadataRows", []):
            for part in row.get("metadataParts", []):
                ptxt = part.get("text", {}).get("content")
                alabel = part.get("accessibilityLabel") or ""
                if ptxt:
                    meta_texts.append(ptxt)
                    if "view" in alabel.lower() or "view" in ptxt.lower() or "watching" in ptxt.lower():
                        views_text = views_text or ptxt
                    elif "ago" in alabel.lower() or "ago" in ptxt.lower() or "scheduled" in ptxt.lower() or "streamed" in ptxt.lower():
                        published_time_text = published_time_text or ptxt
        if views_text is None and meta_texts:
            views_text = meta_texts[0]
        if published_time_text is None and len(meta_texts) > 1:
            published_time_text = meta_texts[1]

        joined_badges = " ".join(badge_styles)
        joined_meta = " ".join(meta_texts).upper()
        if "UPCOMING" in joined_badges or "PREMIERE" in joined_badges or "SCHEDULED" in joined_meta:
            status = "upcoming"
        elif "LIVE" in joined_badges or "WATCHING" in joined_meta:
            status = "live"
        elif requested_tab == "shorts":
            status = "short"
        else:
            status = "regular"

        items.append(
            {
                "id": vid,
                "url": f"https://www.youtube.com/shorts/{vid}" if status == "short" else f"https://www.youtube.com/watch?v={vid}",
                "tab": requested_tab,
                "title": title,
                "published_time_text": published_time_text,
                "duration_text": duration_text,
                "views_text": views_text,
                "status": status,
            }
        )

    # Standard videos / streams (videoRenderer)
    for vr in walk_key(tab_content, "videoRenderer"):
        if not isinstance(vr, dict):
            continue
        vid = vr.get("videoId")
        if not vid or vid in seen_ids:
            continue
        seen_ids.add(vid)
        overlays_text = " ".join(
            str(s) for s in walk_key(vr.get("thumbnailOverlays", []), "style")
        ).upper()
        badge_labels = " ".join(
            str(yt_text(b.get("metadataBadgeRenderer", {}).get("label")) or b.get("metadataBadgeRenderer", {}).get("style") or "")
            for b in vr.get("badges", [])
            if isinstance(b, dict)
        ).upper()
        if vr.get("upcomingEventData") or "UPCOMING" in overlays_text or "UPCOMING" in badge_labels:
            status = "upcoming"
        elif "LIVE" in overlays_text or "BADGE_STYLE_TYPE_LIVE_NOW" in badge_labels:
            status = "live"
        else:
            status = "regular"
        items.append(
            {
                "id": vid,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "tab": requested_tab,
                "title": yt_text(vr.get("title")),
                "published_time_text": yt_text(vr.get("publishedTimeText")),
                "duration_text": yt_text(vr.get("lengthText")),
                "views_text": yt_text(vr.get("viewCountText")) or yt_text(vr.get("shortViewCountText")),
                "status": status,
            }
        )

    # Shorts (shortsLockupViewModel and legacy reelItemRenderer)
    for sm in walk_key(tab_content, "shortsLockupViewModel"):
        if not isinstance(sm, dict):
            continue
        vid = (
            sm.get("onTap", {})
            .get("innertubeCommand", {})
            .get("reelWatchEndpoint", {})
            .get("videoId")
        )
        if not vid or vid in seen_ids:
            continue
        seen_ids.add(vid)
        ov = sm.get("overlayMetadata", {})
        items.append(
            {
                "id": vid,
                "url": f"https://www.youtube.com/shorts/{vid}",
                "tab": requested_tab,
                "title": ov.get("primaryText", {}).get("content") or sm.get("accessibilityText"),
                "published_time_text": None,
                "duration_text": None,
                "views_text": ov.get("secondaryText", {}).get("content"),
                "status": "short",
            }
        )
    for rr in walk_key(tab_content, "reelItemRenderer"):
        if not isinstance(rr, dict):
            continue
        vid = rr.get("videoId")
        if not vid or vid in seen_ids:
            continue
        seen_ids.add(vid)
        items.append(
            {
                "id": vid,
                "url": f"https://www.youtube.com/shorts/{vid}",
                "tab": requested_tab,
                "title": yt_text(rr.get("headline")),
                "published_time_text": None,
                "duration_text": None,
                "views_text": yt_text(rr.get("viewCountText")),
                "status": "short",
            }
        )

    ch_meta = initial_data.get("metadata", {}).get("channelMetadataRenderer", {})
    return {
        "requested_tab": requested_tab,
        "source_url": source_url,
        "channel_id": ch_meta.get("externalId"),
        "channel_title": ch_meta.get("title"),
        "selected_tab_title": selected_title,
        "selected_tab_url": selected_url,
        "tab_verified": tab_verified,
        "has_continuation": has_continuation,
        "item_count": len(items),
        "items": items if tab_verified else [],
        "unverified_fallback_count": 0 if tab_verified else len(items),
    }


def cmd_channel_tabs(args: argparse.Namespace) -> dict[str, Any]:
    base = normalize_channel_base_url(args.channel)
    tabs_req = [t.strip().lower() for t in args.tabs.split(",") if t.strip()]
    tab_results: dict[str, Any] = {}
    all_ids: list[str] = []
    seen: set[str] = set()
    channel_id = None
    channel_title = None
    for idx, tab in enumerate(tabs_req):
        if idx > 0 and args.delay > 0:
            time.sleep(args.delay)
        url = f"{base}/{tab}?hl=en"
        _, html = http_get_once(url, headers={"Cookie": "SOCS=CAI"})
        res = parse_channel_tab_html(html, tab, url)
        tab_results[tab] = res
        channel_id = channel_id or res.get("channel_id")
        channel_title = channel_title or res.get("channel_title")
        if res["tab_verified"]:
            for it in res["items"]:
                if it["id"] not in seen:
                    seen.add(it["id"])
                    all_ids.append(it["id"])
    return {
        "state": "ok",
        "source_tier": "tier2_channel_tabs_initial_html",
        "observed_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "channel_base_url": base,
        "channel_id": channel_id,
        "channel_title": channel_title,
        "channel_feed_url": (
            f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}" if channel_id else None
        ),
        "tabs": tab_results,
        "unique_verified_count": len(all_ids),
        "all_video_ids": all_ids,
    }


# --- Subcommand: batch (Resumable paced JSONL collector with instant blocked.json halt) ---

def load_video_ids_from_input(path: Path) -> list[str]:
    """Load deduplicated video IDs from JSON list, yt_enrich outputs, or newline text."""
    raw = path.read_text(encoding="utf-8").strip()
    candidates: list[str] = []
    if raw.startswith("{") or raw.startswith("["):
        data = json.loads(raw)
        if isinstance(data, list):
            for el in data:
                if isinstance(el, str):
                    candidates.append(el)
                elif isinstance(el, dict) and el.get("id"):
                    candidates.append(str(el["id"]))
        elif isinstance(data, dict):
            if isinstance(data.get("all_video_ids"), list):
                candidates.extend(str(x) for x in data["all_video_ids"])
            elif isinstance(data.get("entries"), list):
                candidates.extend(str(x["id"]) for x in data["entries"] if isinstance(x, dict) and x.get("id"))
            elif isinstance(data.get("videos"), list):
                candidates.extend(str(x["id"]) for x in data["videos"] if isinstance(x, dict) and x.get("id"))
            elif isinstance(data.get("items"), list):
                candidates.extend(str(x["id"]) for x in data["items"] if isinstance(x, dict) and x.get("id"))
            elif data.get("id"):
                candidates.append(str(data["id"]))
    else:
        for line in raw.splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                candidates.append(s)

    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        vid = parse_video_id(c)
        if vid not in seen:
            seen.add(vid)
            out.append(vid)
    return out


def load_done_ids(jsonl_path: Path) -> set[str]:
    done: set[str] = set()
    if not jsonl_path.exists():
        return done
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            if rec.get("state") == "ok" and rec.get("id"):
                done.add(rec["id"])
        except json.JSONDecodeError:
            continue
    return done


def cmd_batch(args: argparse.Namespace) -> dict[str, Any]:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    items_path = out_dir / "items.jsonl"
    blocked_path = out_dir / "blocked.json"
    if os.path.lexists(blocked_path):
        # Do not let a caller's --out overwrite the original stop evidence.
        if args.out and Path(args.out).resolve() == blocked_path.resolve():
            args.out = None
        raise BlockedError(
            source_url=None,
            status=None,
            reason="existing_stop",
            evidence=f"{blocked_path} already records a stop; no collection started.",
        )

    all_ids = load_video_ids_from_input(Path(args.input_file))
    if args.limit is not None and args.limit > 0:
        all_ids = all_ids[: args.limit]
    done = load_done_ids(items_path)
    todo = [vid for vid in all_ids if vid not in done]

    has_api_key = bool(os.environ.get("YOUTUBE_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    mode = args.mode
    if mode == "auto":
        mode = "api" if has_api_key else "inspect"

    fetched_ok = 0
    fetched_err = 0

    def record_blocked(exc: BlockedError, vid: str | None) -> None:
        payload = dict(exc.payload)
        payload.update(
            {
                "source_id": vid,
                "mode": mode,
                "selected_count": len(all_ids),
                "previously_done": len(done),
                "fetched_ok_this_run": fetched_ok,
                "remaining_count": max(0, len(todo) - fetched_ok - fetched_err),
                "items_jsonl": str(items_path),
            }
        )
        blocked_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        exc.payload = payload

    with items_path.open("a", encoding="utf-8") as fh:
        if mode == "api":
            for i in range(0, len(todo), 50):
                batch_ids = todo[i : i + 50]
                ns = argparse.Namespace(
                    videos=batch_ids,
                    comments=args.comments,
                    captions_meta=args.captions_meta,
                )
                try:
                    resp = cmd_api_video(ns)
                except BlockedError as exc:
                    record_blocked(exc, batch_ids[0] if batch_ids else None)
                    raise
                returned_map = {it["id"]: it for it in resp.get("items", [])}
                obs = resp["observed_utc"]
                for vid in batch_ids:
                    if vid in returned_map:
                        rec = dict(returned_map[vid])
                        rec["state"] = "ok"
                        rec["source_tier"] = "tier1_youtube_data_api_v3"
                        rec["observed_utc"] = obs
                        fetched_ok += 1
                    else:
                        rec = {
                            "state": "unavailable",
                            "source_tier": "tier1_youtube_data_api_v3",
                            "observed_utc": obs,
                            "id": vid,
                            "url": f"https://www.youtube.com/watch?v={vid}",
                            "error": "Video ID not returned by YouTube Data API v3 videos.list (deleted, private, or invalid).",
                        }
                        fetched_err += 1
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    fh.flush()
        else:
            for idx, vid in enumerate(todo):
                if idx > 0 and args.delay > 0:
                    time.sleep(args.delay + random.uniform(0.0, args.jitter))
                try:
                    rec = cmd_inspect(argparse.Namespace(video=vid))
                    fetched_ok += 1
                except BlockedError as exc:
                    record_blocked(exc, vid)
                    raise
                except Exception as exc:
                    rec = {
                        "state": "error",
                        "source_tier": "tier2_watch_page_single_get",
                        "observed_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                        "id": vid,
                        "url": f"https://www.youtube.com/watch?v={vid}",
                        "error": str(exc),
                    }
                    fetched_err += 1
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()

    return {
        "state": "ok",
        "source_tier": "tier1_youtube_data_api_v3" if mode == "api" else "tier2_watch_page_single_get",
        "observed_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "mode": mode,
        "items_jsonl": str(items_path),
        "selected_count": len(all_ids),
        "previously_done": len(done),
        "fetched_ok": fetched_ok,
        "fetched_non_ok": fetched_err,
    }


# --- Subcommand: thumbs (Media-free i.ytimg.com cover, keyframes & chapter stills) ---

def _load_records_for_thumbs(target: str) -> list[dict[str, Any]]:
    p = Path(target)
    if p.exists() and p.is_file():
        raw = p.read_text(encoding="utf-8").strip()
        if p.suffix.lower() == ".jsonl":
            return list(reduce_items_jsonl(p).values())
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("id"):
            return [data]
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            return [it for it in data["items"] if isinstance(it, dict) and it.get("id")]
        if isinstance(data, list):
            return [{"id": parse_video_id(x)} if isinstance(x, str) else x for x in data]
    vid = parse_video_id(target)
    return [{"id": vid, "static_thumbnails": static_thumbnail_urls(vid), "chapters": []}]


def cmd_thumbs(args: argparse.Namespace) -> dict[str, Any]:
    records = _load_records_for_thumbs(args.target)
    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, Any]] = []

    for rec in records:
        vid = rec["id"]
        vdir = out_root / vid
        vdir.mkdir(parents=True, exist_ok=True)
        static = rec.get("static_thumbnails") or static_thumbnail_urls(vid)
        saved_files: list[dict[str, Any]] = []

        # Cover: try maxres -> sd -> hq
        cover_path = vdir / "cover.jpg"
        if not cover_path.exists():
            for cand_name in ("maxres", "sd", "hq"):
                cand_url = static.get(cand_name)
                if not cand_url:
                    continue
                status, data = http_get_bytes_once(cand_url)
                if status == 200 and data:
                    cover_path.write_bytes(data)
                    saved_files.append(
                        {
                            "kind": "cover",
                            "variant": cand_name,
                            "file": cover_path.name,
                            "source_url": cand_url,
                            "bytes": len(data),
                            "sha256": hashlib.sha256(data).hexdigest(),
                        }
                    )
                    break
                if args.delay > 0:
                    time.sleep(args.delay)
        else:
            b = cover_path.read_bytes()
            saved_files.append(
                {"kind": "cover", "variant": "cached", "file": cover_path.name, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
            )

        # Static automatic keyframes (hq1, hq2, hq3)
        for kf in ("keyframe_1", "keyframe_2", "keyframe_3"):
            kf_url = static.get(kf)
            if not kf_url:
                continue
            kf_path = vdir / f"{kf}.jpg"
            if not kf_path.exists():
                if args.delay > 0:
                    time.sleep(args.delay)
                status, data = http_get_bytes_once(kf_url)
                if status == 200 and data:
                    kf_path.write_bytes(data)
                    saved_files.append(
                        {
                            "kind": "keyframe",
                            "file": kf_path.name,
                            "source_url": kf_url,
                            "bytes": len(data),
                            "sha256": hashlib.sha256(data).hexdigest(),
                        }
                    )
            else:
                b = kf_path.read_bytes()
                saved_files.append(
                    {"kind": "keyframe", "file": kf_path.name, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
                )

        # Per-chapter thumbnails from inspect output
        for idx, ch in enumerate(rec.get("chapters") or [], 1):
            t_url = ch.get("thumbnail")
            if not t_url:
                continue
            st = ch.get("start_seconds")
            t_tag = f"{st // 60:02d}m{st % 60:02d}s" if isinstance(st, int) else f"ch{idx:02d}"
            ch_path = vdir / f"chapter_{idx:02d}_{t_tag}.jpg"
            if not ch_path.exists():
                if args.delay > 0:
                    time.sleep(args.delay)
                status, data = http_get_bytes_once(t_url)
                if status == 200 and data:
                    ch_path.write_bytes(data)
                    saved_files.append(
                        {
                            "kind": "chapter",
                            "chapter_index": idx,
                            "time": ch.get("time"),
                            "start_seconds": st,
                            "title": ch.get("title"),
                            "file": ch_path.name,
                            "source_url": t_url,
                            "bytes": len(data),
                            "sha256": hashlib.sha256(data).hexdigest(),
                        }
                    )
            else:
                b = ch_path.read_bytes()
                saved_files.append(
                    {
                        "kind": "chapter",
                        "chapter_index": idx,
                        "time": ch.get("time"),
                        "start_seconds": st,
                        "title": ch.get("title"),
                        "file": ch_path.name,
                        "bytes": len(b),
                        "sha256": hashlib.sha256(b).hexdigest(),
                    }
                )

        manifest = {
            "id": vid,
            "observed_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "source_tier": "tier2_static_i_ytimg_thumbnails",
            "file_count": len(saved_files),
            "files": saved_files,
        }
        (vdir / "thumbs_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        summaries.append({"id": vid, "dir": str(vdir), "file_count": len(saved_files)})

    return {
        "state": "ok",
        "source_tier": "tier2_static_i_ytimg_thumbnails",
        "observed_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "videos_processed": len(summaries),
        "total_images": sum(s["file_count"] for s in summaries),
        "videos": summaries,
    }


# --- Subcommand: render (Contract-compliant videos/*.md, index.md, verified index.csv) ---

def reduce_items_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    """Reduce items.jsonl to one record per ID, preserving the latest successful record over later failed retries."""
    by_id: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        vid = rec.get("id")
        if not vid:
            continue
        prev = by_id.get(vid)
        if prev is None or rec.get("state") == "ok" or prev.get("state") != "ok":
            by_id[vid] = rec
    return by_id


def parse_iso_date(rec: dict[str, Any]) -> str:
    """Return YYYY-MM-DD if known from ISO or YouTube human date text; otherwise empty string."""
    for key in ("publish_date", "published_at", "published", "upload_date"):
        val = rec.get(key)
        if isinstance(val, str) and re.match(r"^\d{4}-\d{2}-\d{2}", val):
            return val[:10]
    dt_txt = rec.get("date_text") or ""
    m = re.search(r"([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})", dt_txt)
    if m:
        try:
            return dt.datetime.strptime(m.group(1), "%b %d, %Y").strftime("%Y-%m-%d")
        except ValueError:
            pass
    return ""


def slugify(text_val: str | None, max_len: int = 60) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (text_val or "video").lower()).strip("-")
    return (s[:max_len].rstrip("-")) or "video"


def parse_views_int(rec: dict[str, Any]) -> str:
    if isinstance(rec.get("views"), int):
        return str(rec["views"])
    vt = rec.get("views_text") or ""
    digits = re.sub(r"[^\d]", "", vt)
    return digits if digits else ""


def format_mmss(seconds: int | float | None) -> str:
    if seconds is None:
        return ""
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def load_transcript_items(transcripts_dir: Path | None, vid: str) -> list[dict[str, Any]]:
    if not transcripts_dir:
        return []
    p = transcripts_dir / f"{vid}.json"
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    if isinstance(data, dict) and isinstance(data.get("segments"), list):
        return [{"t": format_mmss(seg.get("start")), "x": seg.get("text", "")} for seg in data["segments"]]
    return []


def cmd_render(args: argparse.Namespace) -> dict[str, Any]:
    items_path = Path(args.items)
    if items_path.suffix.lower() == ".jsonl":
        records_map = reduce_items_jsonl(items_path)
    else:
        raw = json.loads(items_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and raw.get("id"):
            records_map = {raw["id"]: raw}
        elif isinstance(raw, dict) and isinstance(raw.get("items"), list):
            records_map = {it["id"]: it for it in raw["items"] if isinstance(it, dict) and it.get("id")}
        elif isinstance(raw, dict) and isinstance(raw.get("entries"), list):
            records_map = {it["id"]: dict(it, state="ok") for it in raw["entries"] if isinstance(it, dict) and it.get("id")}
        else:
            raise ValueError(f"Unsupported items format in {items_path}")

    out_dir = Path(args.out_dir)
    videos_dir = out_dir / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)
    transcripts_dir = Path(args.transcripts_dir) if args.transcripts_dir else None
    diagrams_dir = Path(args.diagrams_dir) if args.diagrams_dir else None

    rows: list[dict[str, str]] = []
    sorted_recs = sorted(
        records_map.values(),
        key=lambda r: (parse_iso_date(r) or "0000-00-00", r.get("id", "")),
        reverse=True,
    )

    for rec in sorted_recs:
        vid = rec["id"]
        url = rec.get("url") or f"https://www.youtube.com/watch?v={vid}"
        title = rec.get("title") or vid
        iso_date = parse_iso_date(rec)
        fname = f"{iso_date or 'undated'}_{vid}_{slugify(title)}.md"
        rel_file = f"videos/{fname}"

        chapters = rec.get("chapters") or []
        peaks = rec.get("heatmap_peaks") or []
        links = rec.get("companion_links") or {}
        comments = rec.get("top_comments") or []
        transcript = load_transcript_items(transcripts_dir, vid)

        thumb_manifest_path = (diagrams_dir / vid / "thumbs_manifest.json") if diagrams_dir else None
        thumb_count = 0
        thumb_files: list[dict[str, Any]] = []
        if thumb_manifest_path and thumb_manifest_path.exists():
            tm = json.loads(thumb_manifest_path.read_text(encoding="utf-8"))
            thumb_files = tm.get("files", [])
            thumb_count = len(thumb_files)

        md_lines = [
            f"# {title}",
            "",
            f"- **Video ID:** `{vid}`",
            f"- **URL:** {url}",
            f"- **Channel:** {rec.get('channel_name') or rec.get('channel_title') or rec.get('author') or ''}",
            f"- **Published:** {iso_date or rec.get('date_text') or 'unknown'}",
            f"- **Fetched (UTC):** {rec.get('observed_utc') or ''}",
            f"- **State:** `{rec.get('state') or 'unknown'}` ({rec.get('source_tier') or ''})",
            f"- **Views / Likes:** {rec.get('views_text') or parse_views_int(rec) or 'unknown'} / {rec.get('likes') if rec.get('likes') is not None else 'unknown'}",
            f"- **Caption inventory:** `{rec.get('caption_tracks_status') or ('present' if rec.get('has_captions') else 'unknown')}`",
            "",
        ]
        if chapters:
            md_lines.append("## Chapters")
            md_lines.append("")
            for ch in chapters:
                st = ch.get("start_seconds")
                deep = f"{url}&t={st}s" if isinstance(st, int) else url
                md_lines.append(f"- [{ch.get('time') or format_mmss(st)}]({deep}) — {ch.get('title') or ''}")
            md_lines.append("")
        if peaks:
            md_lines.append("## Most Replayed Heatmap Peaks")
            md_lines.append("")
            for pk in peaks:
                st = int(pk["start_seconds"])
                md_lines.append(f"- [{format_mmss(st)}]({url}&t={st}s) — intensity `{pk['intensity']}` ({pk['duration_seconds']}s)")
            md_lines.append("")
        if links:
            md_lines.append("## Companion Links")
            md_lines.append("")
            for bucket, urls in links.items():
                md_lines.append(f"### {bucket}")
                for u in urls:
                    md_lines.append(f"- {u}")
            md_lines.append("")
        if thumb_files:
            md_lines.append("## Downloaded Static Stills")
            md_lines.append("")
            for tf in thumb_files:
                label = tf.get("title") or tf.get("kind")
                ts_part = f" ({tf['time']})" if tf.get("time") else ""
                md_lines.append(f"- `{tf['file']}` — {label}{ts_part}")
            md_lines.append("")
        if rec.get("description"):
            md_lines.extend(["## Description", "", rec["description"], ""])
        if comments:
            md_lines.append("## Top / Pinned Comments")
            md_lines.append("")
            for cm in comments:
                badge = " **(Channel Owner)**" if cm.get("is_channel_owner") else ""
                md_lines.append(f"- **{cm.get('author') or 'unknown'}**{badge} ({cm.get('likes') or 0} likes): {cm.get('text', '').strip()}")
            md_lines.append("")
        if transcript:
            md_lines.append("## Transcript")
            md_lines.append("")
            for item in transcript:
                if "chapter" in item:
                    md_lines.append(f"\n### {item['chapter']}\n")
                else:
                    t_str = item.get("t") or ""
                    st = parse_timestamp_seconds(t_str) if t_str else None
                    prefix = f"[{t_str}]({url}&t={st}s)" if st is not None else (f"`{t_str}`" if t_str else "")
                    md_lines.append(f"- {prefix} {item.get('x', '').strip()}")
            md_lines.append("")

        (videos_dir / fname).write_text("\n".join(md_lines), encoding="utf-8")

        rows.append(
            {
                "date": iso_date,
                "id": vid,
                "title": title,
                "channel": str(rec.get("channel_name") or rec.get("channel_title") or rec.get("author") or ""),
                "length_s": str(rec["length_seconds"]) if rec.get("length_seconds") is not None else "",
                "views": parse_views_int(rec),
                "likes": str(rec["likes"]) if rec.get("likes") is not None else "",
                "metadata_state": str(rec.get("state") or ""),
                "caption_status": str(rec.get("caption_tracks_status") or ("present" if rec.get("has_captions") else "")),
                "chapters": str(len(chapters)) if chapters else "",
                "heatmap_peaks": str(len(peaks)) if peaks else "",
                "comments": str(len(comments)) if comments else "",
                "companion_links": str(sum(len(v) for v in links.values())) if links else "",
                "thumbs": str(thumb_count) if thumb_count else "",
                "transcript_segments": str(len(transcript)) if transcript else "",
                "review_state": "unread",
                "fetched_at": str(rec.get("observed_utc") or ""),
                "url": url,
                "file": rel_file,
            }
        )

    # Write index.csv with csv.DictWriter and reopen to validate row widths
    fieldnames = [
        "date", "id", "title", "channel", "length_s", "views", "likes",
        "metadata_state", "caption_status", "chapters", "heatmap_peaks",
        "comments", "companion_links", "thumbs", "transcript_segments",
        "review_state", "fetched_at", "url", "file",
    ]
    csv_path = out_dir / "index.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as cf:
        writer = csv.DictWriter(cf, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    with csv_path.open("r", encoding="utf-8", newline="") as cf:
        csv_rows = list(csv.reader(cf))
    if not csv_rows or len(csv_rows[0]) != len(fieldnames):
        raise RuntimeError("index.csv header validation failed.")
    for line_no, r in enumerate(csv_rows[1:], 2):
        if len(r) != len(fieldnames):
            raise RuntimeError(f"index.csv row {line_no} field count mismatch: {len(r)} != {len(fieldnames)}")

    # Write index.md
    idx_lines = [
        "# Video Index",
        "",
        f"Rendered {len(rows)} items from `{items_path.name}` at `{dt.datetime.now(dt.timezone.utc).isoformat()}`.",
        "",
        "| Date | ID | Title | Metadata | Chapters | Peaks | Links | Thumbs | Transcript | Review |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        safe_title = r["title"].replace("|", "\\|")
        idx_lines.append(
            f"| {r['date'] or 'unknown'} | `{r['id']}` | [{safe_title}]({r['file']}) | "
            f"`{r['metadata_state']}` | {r['chapters'] or '—'} | {r['heatmap_peaks'] or '—'} | "
            f"{r['companion_links'] or '—'} | {r['thumbs'] or '—'} | {r['transcript_segments'] or '—'} | `{r['review_state']}` |"
        )
    idx_path = out_dir / "index.md"
    idx_path.write_text("\n".join(idx_lines) + "\n", encoding="utf-8")

    return {
        "state": "ok",
        "source_tier": "offline_render",
        "observed_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "rendered_count": len(rows),
        "index_md": str(idx_path),
        "index_csv": str(csv_path),
        "csv_verified_rows": len(csv_rows) - 1,
        "videos_dir": str(videos_dir),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Media-free YouTube scraping, enrichment, and rendering CLI (official APIs, feeds, tab-verified inventory, resumable JSONL batch, static thumbs, links, Gemini YouTube URL)."
    )
    parser.add_argument("--out", help="Optional path to write JSON output instead of stdout.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_feed = sub.add_parser("feed", help="Tier 0: Fetch official YouTube Atom/RSS feed (latest 15 items, zero auth).")
    p_feed.add_argument("--channel-id", help="YouTube channel ID (UC...).")
    p_feed.add_argument("--playlist-id", help="YouTube playlist ID (PL... or UU...).")
    p_feed.set_defaults(func=cmd_feed)

    p_oembed = sub.add_parser("oembed", help="Tier 0: Fetch official YouTube oEmbed JSON (zero auth).")
    p_oembed.add_argument("video", help="YouTube video URL or 11-char video ID.")
    p_oembed.set_defaults(func=cmd_oembed)

    p_api_vid = sub.add_parser("api-video", help="Tier 1: Official YouTube Data API v3 videos.list (+ optional top/pinned comments).")
    p_api_vid.add_argument("videos", nargs="+", help="One or more YouTube URLs or video IDs (batched up to 50/call).")
    p_api_vid.add_argument("--comments", type=int, default=0, help="Fetch up to N top/relevant comments per video (0=skip).")
    p_api_vid.add_argument("--captions-meta", action="store_true", help="Also try captions.list for caption track metadata (needs OAuth; an API key alone is refused and recorded as caption_tracks_error).")
    p_api_vid.set_defaults(func=cmd_api_video)

    p_api_ch = sub.add_parser("api-channel", help="Tier 1: Official YouTube Data API v3 channel uploads inventory.")
    p_api_ch.add_argument("--channel-id", required=True, help="YouTube channel ID (UC...).")
    p_api_ch.add_argument("--limit", type=int, default=50, help="Maximum videos to return (default 50).")
    p_api_ch.set_defaults(func=cmd_api_channel)

    p_tabs = sub.add_parser("channel-tabs", help="Tier 2: Tab-verified public channel inventory (/videos, /shorts, /streams) from initial HTML.")
    p_tabs.add_argument("channel", help="Channel UC... ID, @handle, or YouTube channel URL.")
    p_tabs.add_argument("--tabs", default="videos,shorts,streams", help="Comma-separated tabs to probe (default: videos,shorts,streams).")
    p_tabs.add_argument("--delay", type=float, default=2.0, help="Seconds to wait between tab requests (default: 2.0).")
    p_tabs.set_defaults(func=cmd_channel_tabs)

    p_inspect = sub.add_parser("inspect", help="Tier 2: Single anonymous watch-page GET for rich metadata, chapters+thumbs, heatmap peaks, links, caption inventory.")
    p_inspect.add_argument("video", help="YouTube video URL or 11-char video ID.")
    p_inspect.set_defaults(func=cmd_inspect)

    p_batch = sub.add_parser("batch", help="Resumable paced JSONL collector (auto-uses Data API v3 when YOUTUBE_API_KEY is set, else sequential inspect; writes blocked.json on 403/429).")
    p_batch.add_argument("input_file", help="Path to JSON list, channel-tabs/feed/api-channel JSON, or newline video ID/URL file.")
    p_batch.add_argument("--out-dir", required=True, help="Directory to append items.jsonl (and write blocked.json if halted).")
    p_batch.add_argument("--mode", choices=("auto", "api", "inspect"), default="auto", help="Collection backend (default: auto).")
    p_batch.add_argument("--delay", type=float, default=2.5, help="Base seconds between inspect requests (default: 2.5).")
    p_batch.add_argument("--jitter", type=float, default=1.0, help="Random extra jitter seconds for inspect requests (default: 1.0).")
    p_batch.add_argument("--comments", type=int, default=0, help="In API mode, also fetch up to N top/pinned comments per video.")
    p_batch.add_argument("--captions-meta", action="store_true", help="In API mode, also try captions.list (needs OAuth; an API key alone is recorded as caption_tracks_error).")
    p_batch.add_argument("--limit", type=int, help="Optional cap on number of videos to process.")
    p_batch.set_defaults(func=cmd_batch)

    p_thumbs = sub.add_parser("thumbs", help="Tier 2: Download media-free i.ytimg.com cover, keyframes (hq1-3), and chapter thumbnails with SHA-256 manifest.")
    p_thumbs.add_argument("target", help="Video ID/URL, inspect JSON, or items.jsonl file.")
    p_thumbs.add_argument("--out-dir", required=True, help="Output directory (creates <out-dir>/<video_id>/).")
    p_thumbs.add_argument("--delay", type=float, default=0.5, help="Seconds between image downloads (default: 0.5).")
    p_thumbs.set_defaults(func=cmd_thumbs)

    p_render = sub.add_parser("render", help="Render videos/*.md, index.md, and validated index.csv from items.jsonl (+ optional transcripts & thumbs).")
    p_render.add_argument("--items", required=True, help="Path to items.jsonl or single video/feed JSON.")
    p_render.add_argument("--out-dir", required=True, help="Output directory for videos/, index.md, and index.csv.")
    p_render.add_argument("--transcripts-dir", help="Optional directory containing <video_id>.json transcripts.")
    p_render.add_argument("--diagrams-dir", help="Optional directory containing <video_id>/thumbs_manifest.json.")
    p_render.set_defaults(func=cmd_render)

    p_gemini = sub.add_parser("gemini", help="Tier 4: Official Gemini API multimodal analysis of a public YouTube URL (no local download).")
    p_gemini.add_argument("video", help="Public YouTube video URL or 11-char video ID.")
    p_gemini.add_argument("--start", help="Optional start_offset in seconds, e.g. 120s.")
    p_gemini.add_argument("--end", help="Optional end_offset in seconds, e.g. 420s.")
    p_gemini.add_argument("--fps", type=float, help="Optional frame sampling rate (e.g. 0.25 for slides, 1.0 for code demos).")
    p_gemini.add_argument("--model", default="gemini-2.5-flash", help="Gemini model name (default: gemini-2.5-flash).")
    p_gemini.add_argument("--prompt", help="Custom extraction prompt.")
    p_gemini.add_argument("--dry-run", action="store_true", help="Print the planned request payload without calling the API.")
    p_gemini.set_defaults(func=cmd_gemini)

    p_links = sub.add_parser("links", help="Tier 3: Extract and categorize companion URLs from local JSON/Markdown files.")
    p_links.add_argument("files", nargs="+", help="Local files to scan for companion links.")
    p_links.set_defaults(func=cmd_links)

    return parser


def emit_json(payload: dict[str, Any], out_path: str | None) -> None:
    rendered = json.dumps(payload, indent=2, ensure_ascii=False)
    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.func(args)
        emit_json(result, args.out)
        return EXIT_OK
    except BlockedError as exc:
        emit_json(exc.payload, args.out)
        return EXIT_BLOCKED
    except Exception as exc:
        emit_json({"state": "error", "error": str(exc)}, args.out)
        return EXIT_ERR


if __name__ == "__main__":
    sys.exit(main())
