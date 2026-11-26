"""Unit tests for plugins/deepmodebot/skills/frontend-ui/scripts/motion_diff.py."""

import importlib.util
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent.parent
MOD_PATH = ROOT / "plugins/deepmodebot/skills/frontend-ui/scripts/motion_diff.py"
SPEC = importlib.util.spec_from_file_location("motion_diff_mod", MOD_PATH)
motion_diff = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = motion_diff
SPEC.loader.exec_module(motion_diff)


def render_box_sequence(positions: list[int], width: int = 100, height: int = 40, box_w: int = 20) -> list[bytes]:
    frames: list[bytes] = []
    for x0 in positions:
        buf = bytearray(width * height)
        clamped = max(0, min(width - box_w, x0))
        for y in range(10, 30):
            row = y * width
            for x in range(clamped, clamped + box_w):
                buf[row + x] = 240
        frames.append(bytes(buf))
    return frames


class MotionDiffTests(unittest.TestCase):
    def _ease_out_positions(self, start_frame: int = 3, move_frames: int = 10, total: int = 18) -> list[int]:
        pos: list[int] = []
        for f in range(total):
            if f < start_frame:
                pos.append(0)
            elif f >= start_frame + move_frames:
                pos.append(70)
            else:
                t = (f - start_frame + 1) / move_frames
                eased = 1.0 - (1.0 - t) ** 3
                pos.append(int(round(70 * eased)))
        return pos

    def _ease_in_positions(self, start_frame: int = 3, move_frames: int = 10, total: int = 18) -> list[int]:
        pos: list[int] = []
        for f in range(total):
            if f < start_frame:
                pos.append(0)
            elif f >= start_frame + move_frames:
                pos.append(70)
            else:
                t = (f - start_frame + 1) / move_frames
                eased = t ** 3
                pos.append(int(round(70 * eased)))
        return pos

    def test_matching_ease_out_animation_passes_motion_and_pixel_modes(self):
        ref = render_box_sequence(self._ease_out_positions())
        cand = render_box_sequence(self._ease_out_positions())
        res = motion_diff.analyze_frames(ref, cand, fps=25.0, mode="pixel")
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["reference"]["easing_family"], "ease-out")
        self.assertEqual(res["activity_curve_rmse"], 0.0)

    def test_catches_ease_in_against_ease_out_and_late_trigger_offset(self):
        ref = render_box_sequence(self._ease_out_positions(start_frame=2))
        wrong_curve = render_box_sequence(self._ease_in_positions(start_frame=2))
        res_curve = motion_diff.analyze_frames(ref, wrong_curve, fps=25.0, mode="motion")
        self.assertFalse(res_curve["ok"])
        self.assertEqual(res_curve["candidate"]["easing_family"], "ease-in")
        self.assertTrue(any("easing family mismatch" in f for f in res_curve["failures"]))

        late = render_box_sequence(self._ease_out_positions(start_frame=7))
        res_late = motion_diff.analyze_frames(ref, late, fps=25.0, mode="motion")
        self.assertFalse(res_late["ok"])
        self.assertTrue(any("start timing offset" in f for f in res_late["failures"]))


if __name__ == "__main__":
    unittest.main()
