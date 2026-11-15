"""Run one real MCP -> A2A -> sealed subscription-agent exchange."""

import argparse
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import secrets
import signal
import sys

from mcp_bridge import project_root
from policy import APPROVED_MODEL, validate_endpoint, validate_text

ASSETS = Path(__file__).resolve().parent
STARTUP_TIMEOUT = 60
CALL_TIMEOUT = 135
# Intentionally preserve operator profile/approval selectors, never provider credentials,
# routing variables, PYTHONPATH, arbitrary OMP_* configuration, or inherited local bearer.
BASE_ENV_NAMES = {
    "APPDATA", "LOCALAPPDATA", "HOME", "HOMEDRIVE", "HOMEPATH", "USERPROFILE",
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
    "TEMP", "TMP", "TMPDIR", "USERNAME", "USER", "LOGNAME", "SHELL", "TERM",
    "PROCESSOR_ARCHITECTURE", "OMP_PROFILE", "PI_CONFIG_DIR", "OMP_CONFIG_DIR",
    "PI_APPROVAL_MODE", "OMP_APPROVAL_MODE",
}


def child_environment(token: str) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key.upper() in BASE_ENV_NAMES}
    env.update({"DEEPMODE_INTEROP_TOKEN": token, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"})
    return env


def owned_command(argv: list[str]) -> list[str]:
    """Assign the Windows child to the existing at-birth kill-on-close Job."""
    if sys.platform != "win32":
        return argv
    helper = ASSETS.parents[2] / "deepmodebot" / "assets" / "loop" / "windows_job.py"
    spec = importlib.util.spec_from_file_location("interop_windows_job", helper)
    if spec is None or spec.loader is None:
        raise RuntimeError("Windows process ownership helper is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.wrap_command(argv, shell=False)


async def close_worker(process) -> None:
    if sys.platform == "win32":
        if process.returncode is None:
            try:
                process.kill()  # Closing the supervisor's Job handle kills every descendant.
            except ProcessLookupError:
                pass
        await asyncio.wait_for(process.wait(), 10)
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        await asyncio.wait_for(process.wait(), 3)
    except TimeoutError:
        pass
    finally:
        # The supervisor may exit before its children; terminate the whole owned group.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    await asyncio.wait_for(process.wait(), 10)


async def read_ready(process) -> str:
    async with asyncio.timeout(STARTUP_TIMEOUT):
        line = await process.stdout.readline()
    if not line.startswith(b"INTEROP_READY ") or not line.endswith(b"\n"):
        raise RuntimeError("worker failed its bounded readiness handshake")
    try:
        ready = json.loads(line[len(b"INTEROP_READY "):])
        if set(ready) != {"url", "protocolVersion"} or ready["protocolVersion"] != "1.0":
            raise ValueError
        endpoint = validate_endpoint(ready["url"])
    except (TypeError, ValueError, KeyError):
        raise RuntimeError("worker returned invalid readiness metadata") from None
    if process.returncode is not None:
        raise RuntimeError("worker exited before delegation")
    return endpoint


def check_listing(listing) -> None:
    if getattr(listing, "is_error", False):
        raise RuntimeError("MCP tool listing failed")
    if getattr(listing, "next_cursor", None):
        raise RuntimeError("unexpected paginated MCP tool listing")
    tools = listing.tools
    if len(tools) != 1 or tools[0].name != "delegate_task":
        raise RuntimeError("bridge did not expose exactly delegate_task")
    schema = tools[0].input_schema
    if (schema.get("type") != "object" or schema.get("required") != ["text"]
            or set(schema.get("properties", {})) != {"text"}
            or schema["properties"]["text"].get("type") != "string"):
        raise RuntimeError("bridge tool schema does not match the text-only contract")


async def call_bridge(root: Path, endpoint: str, env: dict[str, str], text: str, mode: str = "auto") -> str:
    from mcp import Client, StdioServerParameters

    command = owned_command([sys.executable, "-B", str(ASSETS / "mcp_bridge.py"),
                             "--root", str(root), "--a2a-url", endpoint])
    params = StdioServerParameters(command=command[0], args=command[1:], cwd=str(root), env=env)
    # The SDK owns framing, discovery/legacy negotiation and child teardown. Listing
    # first supplies the modern schema header; no application inference retries exist.
    async with Client(params, read_timeout_seconds=CALL_TIMEOUT, mode=mode,
                      input_required_max_rounds=0) as client:
        check_listing(await client.list_tools())
        result = await client.call_tool("delegate_task", {"text": text})
        if result.is_error:
            raise RuntimeError("MCP delegation failed; no retry was attempted")
        if len(result.content) != 1 or result.content[0].type != "text":
            raise RuntimeError("MCP delegation returned unsupported content")
        return validate_text(result.content[0].text)


async def delegate(root: Path, model: str, text: str, mode: str = "auto") -> str:
    root = project_root(str(root))
    text = validate_text(text)
    if model != APPROVED_MODEL:
        raise ValueError("--model must be the fixed approved provider/model")
    token = secrets.token_urlsafe(32)
    env = child_environment(token)
    command = owned_command([sys.executable, "-B", str(ASSETS / "a2a_worker.py"),
                             "--root", str(root), "--model", model, "--port", "0"])
    spawning = asyncio.create_task(asyncio.create_subprocess_exec(
        *command, cwd=str(root), env=env, stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=None, limit=4096,
        **({"start_new_session": True} if sys.platform != "win32" else {}),
    ))
    try:
        process = await asyncio.shield(spawning)
    except asyncio.CancelledError:
        # A cancellation arriving during OS process creation must still obtain and
        # close the process handle before the controller exits.
        process = await spawning
        await close_worker(process)
        raise
    try:
        endpoint = await read_ready(process)
        async with asyncio.timeout(CALL_TIMEOUT + 10):
            return await call_bridge(root, endpoint, env, text, mode)
    finally:
        await close_worker(process)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--model", required=True, choices=[APPROVED_MODEL])
    parser.add_argument("--text", required=True)
    parser.add_argument("--mcp-mode", choices=["auto", "legacy"], default="auto",
                        help="official SDK discovery or legacy initialization (default: auto)")
    args = parser.parse_args()
    try:
        reply = asyncio.run(delegate(project_root(args.root), args.model, args.text, args.mcp_mode))
        print(reply, flush=True)
        return 0
    except KeyboardInterrupt:
        print("delegate: interrupted; owned child processes were closed", file=sys.stderr)
        return 130
    except Exception:
        # Do not print task-bearing SDK exceptions, provider details or bearer values.
        print("delegate: exchange failed; inspect SDK prerequisites, worker policy and OAuth eligibility; no retry", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
