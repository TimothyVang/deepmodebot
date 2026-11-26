#!/usr/bin/env python3
"""Quantitative frame-by-frame UI animation & motion-parity verifier (Python 3 stdlib + ffmpeg).

    python -B motion_diff.py <reference.mp4|webm|gif> <candidate.mp4|webm|gif> [--fps 25] [--mode motion|pixel] [--json]

Measures copy-independent motion physics inspired by NiazMorshed2007/reanimate (MIT):
- Trigger offset (auto-aligned on initial frames; flags > 0.08 s start lag)
- Motion window (start_s, end_s, duration_s, peak_s) & timing error (<= 0.08 s gate)
- Per-frame activity curve shape (ease-out front-loaded vs ease-in-out bell vs ease-in tail-loaded vs linear) & RMSE (<= 0.08 gate)
- At-rest stability (<= 0.5% changed pixels at rest; optional <= 2% mean pixel mismatch in --mode pixel)
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def decode_video_gray(path: Path, fps: float = 25.0, width: int = 320, height: int = 180) -> list[bytes]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required on PATH to decode video files")
    vf = f"fps={fps},scale={width}:{height}:flags=bilinear,format=gray"
    proc = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(path), "-vf", vf, "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"],
        capture_output=True,
        creationflags=CREATE_NO_WINDOW,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed on {path}: {proc.stderr.decode('utf-8', 'replace').strip()}")
    frame_bytes = width * height
    raw = proc.stdout
    count = len(raw) // frame_bytes
    return [raw[i * frame_bytes : (i + 1) * frame_bytes] for i in range(count)]


def _frame_diff_fraction(a: bytes, b: bytes, pixel_tol: int = 6) -> float:
    if not a or len(a) != len(b):
        return 1.0
    changed = sum(1 for x, y in zip(a, b) if abs(x - y) > pixel_tol)
    return changed / len(a)


def _activity_series(frames: list[bytes], pixel_tol: int = 6) -> list[float]:
    if len(frames) < 2:
        return []
    return [_frame_diff_fraction(frames[i - 1], frames[i], pixel_tol) for i in range(1, len(frames))]


def _classify_easing(window_activity: list[float]) -> str:
    if not window_activity or sum(window_activity) <= 1e-9:
        return "static"
    n = len(window_activity)
    total = sum(window_activity)
    centroid = sum((i + 0.5) / n * v for i, v in enumerate(window_activity)) / total
    peak_idx = max(range(n), key=lambda i: window_activity[i])
    peak_pos = (peak_idx + 0.5) / n
    mean_v = total / n
    cv = math.sqrt(sum((v - mean_v) ** 2 for v in window_activity) / n) / max(mean_v, 1e-9)
    if cv < 0.22:
        return "linear"
    if centroid < 0.43 or peak_pos <= 0.30:
        return "ease-out"
    if centroid > 0.57 or peak_pos >= 0.70:
        return "ease-in"
    return "ease-in-out"


def _resample_curve(values: list[float], bins: int = 20) -> list[float]:
    if not values:
        return [0.0] * bins
    total = sum(values)
    if total <= 1e-9:
        return [0.0] * bins
    norm = [v / total for v in values]
    n = len(norm)
    out: list[float] = []
    for b in range(bins):
        lo = (b / bins) * n
        hi = ((b + 1) / bins) * n
        acc = 0.0
        for idx in range(int(math.floor(lo)), min(n, int(math.ceil(hi)))):
            overlap = max(0.0, min(hi, idx + 1.0) - max(lo, float(idx)))
            acc += norm[idx] * overlap
        out.append(acc)
    return out


def _motion_window(activity: list[float], fps: float, noise_floor: float = 0.002) -> dict:
    active = [i for i, v in enumerate(activity) if v > noise_floor]
    if not active:
        return {
            "start_frame": 0,
            "end_frame": 0,
            "start_s": 0.0,
            "end_s": 0.0,
            "duration_s": 0.0,
            "peak_s": 0.0,
            "easing_family": "static",
            "curve_20": [0.0] * 20,
        }
    s_idx, e_idx = active[0], active[-1]
    sub = activity[s_idx : e_idx + 1]
    p_idx = s_idx + max(range(len(sub)), key=lambda i: sub[i])
    return {
        "start_frame": s_idx + 1,
        "end_frame": e_idx + 1,
        "start_s": round(s_idx / fps, 4),
        "end_s": round((e_idx + 1) / fps, 4),
        "duration_s": round((e_idx - s_idx + 1) / fps, 4),
        "peak_s": round((p_idx + 0.5) / fps, 4),
        "easing_family": _classify_easing(sub),
        "curve_20": _resample_curve(sub, 20),
    }


def analyze_frames(
    ref_frames: list[bytes],
    cand_frames: list[bytes],
    fps: float = 25.0,
    mode: str = "motion",
    timing_tol_s: float = 0.08,
    curve_rmse_tol: float = 0.08,
    rest_tol: float = 0.005,
    mean_pixel_tol: float = 0.02,
    max_pixel_tol: float = 0.05,
) -> dict:
    if len(ref_frames) < 2 or len(cand_frames) < 2:
        raise ValueError("need at least 2 frames in both reference and candidate")

    ref_act = _activity_series(ref_frames)
    cand_act = _activity_series(cand_frames)
    ref_win = _motion_window(ref_act, fps)
    cand_win = _motion_window(cand_act, fps)

    offset_s = round(cand_win["start_s"] - ref_win["start_s"], 4)
    start_err_s = abs(offset_s)
    end_err_s = round(abs(cand_win["end_s"] - ref_win["end_s"]), 4)
    dur_err_s = round(abs(cand_win["duration_s"] - ref_win["duration_s"]), 4)
    peak_err_s = round(abs(cand_win["peak_s"] - ref_win["peak_s"]), 4)

    rc, cc = ref_win["curve_20"], cand_win["curve_20"]
    curve_rmse = round(math.sqrt(sum((a - b) ** 2 for a, b in zip(rc, cc)) / len(rc)), 4)

    paired = min(len(ref_frames), len(cand_frames))
    per_frame_mismatch = [_frame_diff_fraction(ref_frames[i], cand_frames[i]) for i in range(paired)]
    rest_indices = [
        i for i in range(paired)
        if (i == 0 or (i - 1 < len(ref_act) and ref_act[i - 1] <= 0.002 and i - 1 < len(cand_act) and cand_act[i - 1] <= 0.002))
    ]
    rest_self_jitter = [
        cand_act[i] for i in range(min(len(ref_act), len(cand_act))) if ref_act[i] <= 0.002
    ]
    rest_jitter = round(max(rest_self_jitter) if rest_self_jitter else 0.0, 4)
    rest_pixel_mismatch = round(
        sum(per_frame_mismatch[i] for i in rest_indices) / len(rest_indices) if rest_indices else 0.0, 4
    )
    mean_mismatch = round(sum(per_frame_mismatch) / len(per_frame_mismatch), 4)
    max_mismatch = round(max(per_frame_mismatch), 4)

    failures: list[str] = []
    if start_err_s > timing_tol_s:
        failures.append(f"start timing offset {offset_s:+.3f}s exceeds ±{timing_tol_s:.2f}s")
    if dur_err_s > timing_tol_s:
        failures.append(f"duration error {dur_err_s:.3f}s exceeds {timing_tol_s:.2f}s")
    if ref_win["easing_family"] != cand_win["easing_family"]:
        failures.append(f"easing family mismatch: ref={ref_win['easing_family']} vs cand={cand_win['easing_family']}")
    if curve_rmse > curve_rmse_tol:
        failures.append(f"activity curve RMSE {curve_rmse:.4f} exceeds {curve_rmse_tol:.4f}")
    if rest_jitter > rest_tol:
        failures.append(f"candidate moves while reference is at rest (jitter={rest_jitter:.4f} > {rest_tol:.4f})")
    if mode == "pixel":
        if rest_pixel_mismatch > rest_tol:
            failures.append(f"at-rest pixel mismatch {rest_pixel_mismatch:.4f} exceeds {rest_tol:.4f}")
        if mean_mismatch > mean_pixel_tol:
            failures.append(f"mean pixel mismatch {mean_mismatch:.4f} exceeds {mean_pixel_tol:.4f}")
        if max_mismatch > max_pixel_tol:
            failures.append(f"worst-frame pixel mismatch {max_mismatch:.4f} exceeds {max_pixel_tol:.4f}")

    return {
        "ok": len(failures) == 0,
        "mode": mode,
        "fps": fps,
        "offset_s": offset_s,
        "timing_errors_s": {
            "start": round(start_err_s, 4),
            "end": end_err_s,
            "duration": dur_err_s,
            "peak": peak_err_s,
        },
        "reference": {k: v for k, v in ref_win.items() if k != "curve_20"},
        "candidate": {k: v for k, v in cand_win.items() if k != "curve_20"},
        "activity_curve_rmse": curve_rmse,
        "rest_jitter": rest_jitter,
        "pixel_mismatch": {
            "rest": rest_pixel_mismatch,
            "mean": mean_mismatch,
            "max": max_mismatch,
        },
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify UI animation timing, easing family, and frame parity.")
    parser.add_argument("reference", help="Reference video/WebM/GIF path.")
    parser.add_argument("candidate", help="Candidate clone video/WebM/GIF path.")
    parser.add_argument("--fps", type=float, default=25.0)
    parser.add_argument("--mode", choices=("motion", "pixel"), default="motion")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    ref_frames = decode_video_gray(Path(args.reference), fps=args.fps)
    cand_frames = decode_video_gray(Path(args.candidate), fps=args.fps)
    report = analyze_frames(ref_frames, cand_frames, fps=args.fps, mode=args.mode)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        verdict = "PASS" if report["ok"] else "FAIL"
        print(
            f"motion_diff [{verdict}]: ref={report['reference']['easing_family']} ({report['reference']['duration_s']}s) "
            f"vs cand={report['candidate']['easing_family']} ({report['candidate']['duration_s']}s) · "
            f"offset={report['offset_s']:+.3f}s · curve_rmse={report['activity_curve_rmse']:.4f}"
        )
        for f in report["failures"]:
            print(f"  - {f}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
