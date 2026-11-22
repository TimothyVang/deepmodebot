"""Record real `deepmodebot doctor` and `deepmodebot setup --dry-run` runs as docs/images/npm-setup.cast, then render npm-setup.gif.

    py -3 scripts/media/capture_npm.py [--brand brand/brand.json]

Needs the npm package installed globally (`npm i -g deepmodebot`) and agg on PATH. The home folder in the output is
shown as `~`, so no personal path ships; everything else is the commands' real output, unedited.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import brandlib  # noqa: E402
from install_gif import render  # noqa: E402

ROOT = HERE.parent.parent
COMMANDS = ["deepmodebot doctor", "deepmodebot setup --dry-run"]


def typed(events: list, t: float, prompt: str, command: str) -> float:
    events.append((round(t, 3), "o", prompt))
    t += 0.6
    for ch in command:
        events.append((round(t, 3), "o", ch))
        t += 0.045
    events.append((round(t + 0.3, 3), "o", "\r\n"))
    return t + 0.5


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--brand", default=str(ROOT / "brand/brand.json"))
    args = parser.parse_args()
    brand = brandlib.load(args.brand)
    exe = shutil.which(brand["slug"])
    if not exe:
        print(f"{brand['slug']} is not on PATH: npm i -g {brand['slug']}", file=sys.stderr)
        return 1
    home = str(Path.home())
    prompt = "\x1b[32m~\x1b[0m $ "
    events, t = [], 0.0
    for command in COMMANDS:
        t = typed(events, t, prompt, command)
        start = time.monotonic()
        run = subprocess.run([exe, *command.split()[1:]] if os.name != "nt" else command.replace(brand["slug"], f'"{exe}"', 1),
                             shell=os.name == "nt", capture_output=True, text=True, encoding="utf-8", errors="replace",
                             env=dict(os.environ, NO_COLOR="1"), timeout=600)
        elapsed = min(time.monotonic() - start, 2.5)
        out = (run.stdout + run.stderr).replace(home + os.sep, "~" + os.sep).replace(home, "~")
        out = out.replace(home.replace("\\", "/"), "~")
        lines = [ln for ln in out.splitlines() if ln.strip()]
        step = elapsed / max(len(lines), 1)
        for ln in lines:
            t += step
            events.append((round(t, 3), "o", ln + "\r\n"))
        t += 1.4
    events.append((round(t, 3), "o", prompt))
    events.append((round(t + 2.0, 3), "o", ""))
    cast = ROOT / "docs/images/npm-setup.cast"
    header = {"version": 2, "width": 96, "height": 18, "timestamp": int(time.time()), "env": {"TERM": "xterm-256color"}}
    with cast.open("w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(header) + "\n")
        for ev in events:
            f.write(json.dumps(list(ev)) + "\n")
    gif = render(brand, cast, ROOT / "docs/images/npm-setup.gif")
    print(f"wrote {cast.relative_to(ROOT)} and {gif.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
