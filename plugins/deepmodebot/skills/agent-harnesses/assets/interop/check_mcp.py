"""Inspect optional prerequisites and list MCP tools in both protocol eras; no model calls."""

import argparse
import asyncio
from importlib.metadata import version
from pathlib import Path
import secrets
import shutil
import sys

from delegate import ASSETS, child_environment, check_listing, owned_command
from mcp_bridge import project_root


async def inspect(root: Path) -> None:
    # Optional dependencies stay inside the explicit doctor path, never ordinary test collection.
    from a2a.client import A2ACardResolver, ClientConfig, create_client
    from a2a.types import Message, Part, SendMessageRequest
    from mcp import Client, StdioServerParameters
    from mcp.server import MCPServer

    expected = {"a2a-sdk": "1.3.0", "mcp": "2.3.0", "uvicorn": "0.54.0"}
    for package, pin in expected.items():
        installed = version(package)
        if installed != pin:
            raise RuntimeError(f"{package} version must be {pin}")
        print(f"{package} {installed}")
    if sys.version_info[:2] != (3, 13):
        raise RuntimeError("optional protocol workspace requires Python 3.13")
    if sys.prefix == sys.base_prefix:
        raise RuntimeError("run doctor from the optional project-local virtualenv")
    if not Path(sys.prefix).resolve().is_relative_to(root / ".scratch" / "agent-interop"):
        raise RuntimeError("virtualenv must be inside this project's .scratch/agent-interop")
    if not shutil.which("omp"):
        raise RuntimeError("omp is not on PATH; doctor does not install or sign in")
    for name in ("mcp_bridge.py", "a2a_worker.py", "policy.py", "requirements.txt"):
        if not (ASSETS / name).is_file():
            raise RuntimeError(f"versioned source kit is incomplete: {name}")
    # Exercise actual official stdio lifecycle/discovery without card fetch or inference.
    env = child_environment(secrets.token_urlsafe(32))
    command = owned_command([sys.executable, "-B", str(ASSETS / "mcp_bridge.py"),
                             "--root", str(root), "--a2a-url", "http://127.0.0.1:1/a2a"])
    params = StdioServerParameters(command=command[0], args=command[1:], cwd=str(root), env=env)
    for mode in ("auto", "legacy"):
        async with asyncio.timeout(20):
            async with Client(params, mode=mode, read_timeout_seconds=10) as client:
                check_listing(await client.list_tools())
                print(f"MCP {mode}: delegate_task listed (no tool call)")
    print("Prerequisites and MCP listing passed; OAuth, inference and A2A execution were not exercised.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    try:
        asyncio.run(inspect(project_root(args.root)))
        return 0
    except (RuntimeError, ValueError) as error:
        print(f"check_mcp: {error}; no model was called", file=sys.stderr)
        return 1
    except (Exception, KeyboardInterrupt):
        print("check_mcp: prerequisite or MCP listing failed; no model was called", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
