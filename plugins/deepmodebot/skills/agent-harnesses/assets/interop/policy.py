"""Dependency-free policy for the local, text-only interop boundary."""
import os
import re

MAX_TEXT_BYTES = 16384
MAX_OUTPUT_BYTES = 16384
MAX_BODY_BYTES = 32768
MAX_CALLS = 8
MODEL_TIMEOUT = 120
MAX_COST = 1
APPROVED_MODEL = "openai-codex/gpt-6.1-sol"


def validate_text(text: str) -> str:
    if not isinstance(text, str) or not text.strip() or "\0" in text:
        raise ValueError("expected nonempty text without NUL")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeError:
        raise ValueError("text must be valid UTF-8") from None
    if size > MAX_TEXT_BYTES:
        raise ValueError("text exceeds 16384 UTF-8 bytes")
    return text


def validate_endpoint(url: str) -> str:
    if not isinstance(url, str):
        raise ValueError("expected an exact literal-loopback RPC URL")
    match = re.fullmatch(r"http://127\.0\.0\.1:([1-9][0-9]{0,4})/a2a", url)
    if match is None or int(match[1]) > 65535:
        raise ValueError("expected http://127.0.0.1:PORT/a2a with an explicit valid port")
    return url


def capability_token() -> str:
    token = os.environ.get("DEEPMODE_INTEROP_TOKEN", "")
    if re.fullmatch(r"[A-Za-z0-9_-]{32,256}", token) is None:
        raise ValueError("DEEPMODE_INTEROP_TOKEN must be a fresh random URL-safe capability (32-256 characters)")
    return token


def validate_request(payload: object) -> str:
    """Reject unsupported wire fields before SDK context construction mutates message IDs.

    This is application validation only; the official SDK owns protocol decoding,
    dispatch, errors and response serialization.
    """
    if not isinstance(payload, dict) or set(payload) - {"jsonrpc", "id", "method", "params"}:
        raise ValueError("expected one JSON-RPC request")
    if payload.get("jsonrpc") != "2.0" or payload.get("method") != "SendMessage":
        raise ValueError("only A2A 1.0 SendMessage is supported")
    if type(payload.get("id")) not in (int, str):
        raise ValueError("a request ID is required")
    params = payload.get("params")
    if not isinstance(params, dict) or set(params) - {"message", "configuration"}:
        raise ValueError("unsupported SendMessage parameters")
    message = params.get("message")
    if not isinstance(message, dict) or set(message) - {"messageId", "role", "parts"}:
        raise ValueError("only a new standalone user message is supported")
    if message.get("role") != "ROLE_USER":
        raise ValueError("only ROLE_USER is supported")
    message_id = message.get("messageId")
    if not isinstance(message_id, str) or not message_id or len(message_id) > 128 or "\0" in message_id:
        raise ValueError("a bounded messageId is required")
    parts = message.get("parts")
    if not isinstance(parts, list) or len(parts) != 1:
        raise ValueError("exactly one text part is required")
    part = parts[0]
    if not isinstance(part, dict) or set(part) - {"text", "mediaType"}:
        raise ValueError("only text parts are supported")
    if part.get("mediaType", "text/plain") != "text/plain":
        raise ValueError("only text/plain is supported")
    text = validate_text(part.get("text"))
    config = params.get("configuration", {})
    if not isinstance(config, dict) or set(config) - {"acceptedOutputModes", "returnImmediately"}:
        raise ValueError("unsupported response configuration")
    if config.get("acceptedOutputModes", ["text/plain"]) != ["text/plain"]:
        raise ValueError("only text/plain output is supported")
    if config.get("returnImmediately", False) is not False:
        raise ValueError("asynchronous tasks are unsupported")
    return text
