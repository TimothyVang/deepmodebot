"""Install optional protocol SDKs into a fresh project-local ignored virtualenv."""

import argparse
from pathlib import Path
import subprocess
import sys
import venv

ASSETS = Path(__file__).resolve().parent


def workspace(root: Path) -> Path:
    if not root.is_absolute() or not root.is_dir():
        raise ValueError("--root must be an existing absolute project directory")
    root = root.resolve()
    # Resolve each existing ancestor, rejecting symlinks/junctions outside the root.
    target = root / ".scratch" / "agent-interop"
    if not target.resolve().is_relative_to(root):
        raise ValueError("scratch workspace resolves outside the project")
    # An existing workspace can contain user modifications or a parent-owned venv.
    # Never merge, clear, repair or reinstall into it.
    if target.exists() or target.is_symlink():
        raise FileExistsError(".scratch/agent-interop already exists; leave it unchanged")
    ignored = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "--quiet", "--no-index", ".scratch/agent-interop/.venv/"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=15, check=False,
    )
    if ignored.returncode != 0:
        raise ValueError("project must ignore .scratch/agent-interop before setup")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    try:
        if sys.version_info[:2] != (3, 13):
            raise ValueError("run setup with Python 3.13")
        requirements = ASSETS / "requirements.txt"
        expected = {"a2a-sdk[http-server]==1.3.0", "mcp==2.3.0", "uvicorn==0.54.0"}
        pins = {line.strip() for line in requirements.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")}
        if pins != expected:
            raise ValueError("interop requirements must contain exactly the reviewed SDK pins")
        root = Path(args.root)
        target = workspace(root)
        # Reserve atomically; a racing or partially installed workspace is never overwritten.
        target.mkdir(parents=True, exist_ok=False)
        environment = target / ".venv"
        venv.EnvBuilder(with_pip=True, clear=False, symlinks=False).create(environment)
        python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        subprocess.run([str(python), "-I", "-m", "pip", "--isolated", "--require-virtualenv", "install",
                        "--no-cache-dir", "-r", str(requirements)], cwd=str(target), check=True, timeout=600)
        print(f"Optional SDK workspace: {environment}")
        print(f"Invoke versioned source directly with {python}; do not copy individual interop scripts.")
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"setup_workspace: {error}", file=sys.stderr)
        print("Existing or partially created workspaces are left untouched; inspect before removing manually.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
