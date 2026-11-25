#!/usr/bin/env python3
"""Contained A2UI v1.0 surface compiler, validator, and interactive HTML human cockpit generator.

    python gen_ui.py from-suggest --root <repo> [--slug suggest] [--limit 8] [--open] [--json]
    python gen_ui.py from-grill --root <repo> [--slug grill] [--base <ref>] [--spec-stdin] [--open] [--json]
    python gen_ui.py render --root <repo> --slug <slug> --stdin [--open] [--json]
    python gen_ui.py validate-a2ui --file <surface.a2ui.json> [--json]
"""
import argparse
import datetime as dt
import importlib.util
import json
import re
import sys
import webbrowser
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

SKILL_DIR = Path(__file__).resolve().parents[2]
ASSETS_DIR = SKILL_DIR / "assets"
CATALOG_ID = "https://a2ui.org/catalogs/deepmodebot-cockpit/v1/catalog.json"

SCRIPT_INJECTION_RE = re.compile(
    r"(?:<\s*/?\s*(?:script|iframe|object|embed)\b|javascript\s*:|vbscript\s*:|data\s*:\s*text/html|\bon[a-z]{2,20}\s*=)",
    re.I,
)

DEFAULT_CATALOG = {
    "protocolVersion": "1.0",
    "catalogId": CATALOG_ID,
    "components": {
        "SurfaceShell": {
            "type": "object",
            "description": "Top-level Operate-mode cockpit container with header telemetry and body sections.",
            "properties": {
                "title": {"type": ["string", "object"]},
                "subtitle": {"type": ["string", "object"]},
                "modeBadge": {"type": ["string", "object"]},
                "children": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "children"],
        },
        "MetricStrip": {
            "type": "object",
            "description": "Horizontal strip of key numeric or categorical repo/audit metrics.",
            "properties": {"children": {"type": "array", "items": {"type": "string"}}},
            "required": ["children"],
        },
        "MetricTile": {
            "type": "object",
            "description": "Single metric card bound to a label, value, and tone.",
            "properties": {
                "label": {"type": ["string", "object"]},
                "value": {"type": ["string", "number", "object"]},
                "tone": {"type": ["string", "object"]},
            },
            "required": ["label", "value"],
        },
        "Section": {
            "type": "object",
            "description": "Titled content group holding cards or rows.",
            "properties": {
                "heading": {"type": ["string", "object"]},
                "summary": {"type": ["string", "object"]},
                "children": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["heading", "children"],
        },
        "SuggestionCard": {
            "type": "object",
            "description": "Ranked /deep prompt card with priority, category, evidence list, and action trigger.",
            "properties": {
                "itemIndex": {"type": "integer"},
                "priority": {"type": ["string", "object"]},
                "kind": {"type": ["string", "object"]},
                "title": {"type": ["string", "object"]},
                "evidence": {"type": ["array", "object"]},
                "prompt": {"type": ["string", "object"]},
                "selected": {"type": ["boolean", "object"]},
                "action": {"type": "object"},
            },
            "required": ["priority", "kind", "title", "prompt"],
        },
        "DecisionCard": {
            "type": "object",
            "description": "Interactive decision-frontier node with options, recommended pick, rationale, and reversal path.",
            "properties": {
                "itemIndex": {"type": "integer"},
                "decisionId": {"type": "string"},
                "question": {"type": ["string", "object"]},
                "choice": {"type": ["string", "object"]},
                "options": {"type": ["array", "object"]},
                "why": {"type": ["string", "object"]},
                "reverse": {"type": ["string", "object"]},
                "action": {"type": "object"},
            },
            "required": ["decisionId", "question", "choice", "options"],
        },
        "FindingRow": {
            "type": "object",
            "description": "Audit or Prosecutor finding row with severity, kind, file location, and detail.",
            "properties": {
                "severity": {"type": ["string", "object"]},
                "category": {"type": ["string", "object"]},
                "location": {"type": ["string", "object"]},
                "detail": {"type": ["string", "object"]},
            },
            "required": ["severity", "location", "detail"],
        },
        "ActionButton": {
            "type": "object",
            "description": "Explicit user action trigger emitting a v1.0 renderer_to_agent action message.",
            "properties": {
                "child": {"type": "string"},
                "variant": {"type": "string"},
                "action": {"type": "object"},
            },
            "required": ["child", "action"],
        },
        "Text": {
            "type": "object",
            "description": "Plain text leaf component.",
            "properties": {"text": {"type": ["string", "object"]}},
            "required": ["text"],
        },
    },
}


def _load_sibling(name: str, rel_path: str):
    path = ASSETS_DIR / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def sanitize_slug(slug: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", (slug or "").strip()).strip(".-")
    if not cleaned:
        return "surface"
    return cleaned[:64]


def resolve_json_pointer(data: Any, pointer: str) -> tuple[bool, Any]:
    if pointer == "/":
        return True, data
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        return False, None
    cur = data
    for raw_part in pointer.lstrip("/").split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, dict):
            if part not in cur:
                return False, None
            cur = cur[part]
        elif isinstance(cur, list):
            if not part.isdigit():
                return False, None
            idx = int(part)
            if idx < 0 or idx >= len(cur):
                return False, None
            cur = cur[idx]
        else:
            return False, None
    return True, cur


def _matches_schema_type(val: Any, expected: str | list[str]) -> bool:
    allowed = [expected] if isinstance(expected, str) else list(expected)
    for t in allowed:
        if t == "string" and isinstance(val, str):
            return True
        if t == "boolean" and isinstance(val, bool):
            return True
        if t == "integer" and isinstance(val, int) and not isinstance(val, bool):
            return True
        if t == "number" and isinstance(val, (int, float)) and not isinstance(val, bool):
            return True
        if t == "array" and isinstance(val, list):
            return True
        if t == "object" and isinstance(val, dict):
            return True
    return False


def _scan_component_value_for_pointers_and_scripts(
    val: Any,
    comp_id: str,
    data_model: Any,
    errors: list[str],
) -> None:
    if isinstance(val, str):
        if SCRIPT_INJECTION_RE.search(val):
            errors.append(f"component '{comp_id}' contains forbidden executable/script pattern in string value")
        return
    if isinstance(val, dict):
        if set(val.keys()) == {"@path"}:
            ptr = val.get("@path")
            if not isinstance(ptr, str) or not ptr.startswith("/"):
                errors.append(f"component '{comp_id}' has invalid @path pointer {ptr!r} (must start with '/')")
            else:
                ok, _ = resolve_json_pointer(data_model, ptr)
                if not ok:
                    errors.append(f"component '{comp_id}' @path {ptr!r} does not resolve in updateDataModel")
            return
        for k, sub in val.items():
            if SCRIPT_INJECTION_RE.search(str(k)):
                errors.append(f"component '{comp_id}' has forbidden pattern in property key {k!r}")
            _scan_component_value_for_pointers_and_scripts(sub, comp_id, data_model, errors)
    elif isinstance(val, list):
        for item in val:
            _scan_component_value_for_pointers_and_scripts(item, comp_id, data_model, errors)


def validate_a2ui_bundle(bundle: dict) -> dict:
    errors: list[str] = []
    if not isinstance(bundle, dict):
        return {"valid": False, "errors": ["bundle root must be a JSON object"], "component_count": 0}
    if bundle.get("version") != "1.0":
        errors.append(f"bundle version must be '1.0', got {bundle.get('version')!r}")

    catalog = bundle.get("catalog")
    allowed_components: dict[str, Any] = {}
    catalog_id = ""
    if not isinstance(catalog, dict):
        errors.append("missing or invalid 'catalog' object")
    else:
        if catalog.get("protocolVersion") != "1.0":
            errors.append(f"catalog.protocolVersion must be '1.0', got {catalog.get('protocolVersion')!r}")
        catalog_id = str(catalog.get("catalogId") or "")
        if not catalog_id:
            errors.append("catalog.catalogId must be non-empty")
        comps = catalog.get("components")
        if not isinstance(comps, dict) or not comps:
            errors.append("catalog.components must be a non-empty object")
        else:
            allowed_components = comps

    messages = bundle.get("messages")
    if not isinstance(messages, list) or len(messages) < 3:
        errors.append("messages must be a list containing createSurface, updateComponents, and updateDataModel")
        return {"valid": False, "errors": errors, "component_count": 0}

    known_ops = {"createSurface", "updateComponents", "updateDataModel", "deleteSurface"}
    create_msg = None
    update_comp_msg = None
    update_data_msg = None
    for idx, msg in enumerate(messages):
        if not isinstance(msg, dict):
            errors.append(f"messages[{idx}] must be an object")
            continue
        if msg.get("version") != "1.0":
            errors.append(f"messages[{idx}].version must be '1.0', got {msg.get('version')!r}")
        msg_ops = [k for k in msg.keys() if k != "version"]
        unknown_ops = [k for k in msg_ops if k not in known_ops]
        if unknown_ops:
            errors.append(f"messages[{idx}] has unknown operation key(s): {unknown_ops}")
        if len(msg_ops) != 1:
            errors.append(f"messages[{idx}] must contain exactly one A2UI operation key, got {msg_ops}")
            continue
        op = msg_ops[0]
        if op == "createSurface":
            if create_msg is not None:
                errors.append("duplicate createSurface message in initial bundle")
            else:
                create_msg = msg["createSurface"]
        elif op == "updateComponents":
            if update_comp_msg is not None:
                errors.append("duplicate updateComponents message in initial bundle")
            else:
                update_comp_msg = msg["updateComponents"]
        elif op == "updateDataModel":
            if update_data_msg is not None:
                errors.append("duplicate updateDataModel message in initial bundle")
            else:
                update_data_msg = msg["updateDataModel"]

    if not isinstance(create_msg, dict):
        errors.append("missing createSurface message")
    if not isinstance(update_comp_msg, dict):
        errors.append("missing updateComponents message")
    if not isinstance(update_data_msg, dict):
        errors.append("missing updateDataModel message")
    if errors:
        return {"valid": False, "errors": errors, "component_count": 0}
    surface_id = create_msg.get("surfaceId")
    if not isinstance(surface_id, str) or not surface_id.strip():
        errors.append("createSurface.surfaceId must be a non-empty string")
    if create_msg.get("catalogId") != catalog_id:
        errors.append(f"createSurface.catalogId {create_msg.get('catalogId')!r} does not match catalog {catalog_id!r}")
    if update_comp_msg.get("surfaceId") != surface_id:
        errors.append("updateComponents.surfaceId does not match createSurface.surfaceId")
    if update_data_msg.get("surfaceId") != surface_id:
        errors.append("updateDataModel.surfaceId does not match createSurface.surfaceId")
    if update_data_msg.get("path") != "/":
        errors.append(f"initial updateDataModel.path must be '/', got {update_data_msg.get('path')!r}")

    data_model = update_data_msg.get("value")
    if not isinstance(data_model, dict):
        errors.append("updateDataModel.value must be a JSON object")
        data_model = {}

    raw_components = update_comp_msg.get("components")
    if not isinstance(raw_components, list) or not raw_components:
        errors.append("updateComponents.components must be a non-empty flat list")
        return {"valid": False, "errors": errors, "component_count": 0}

    by_id: dict[str, dict] = {}
    edges: dict[str, list[str]] = {}
    for idx, comp in enumerate(raw_components):
        if not isinstance(comp, dict):
            errors.append(f"components[{idx}] must be an object")
            continue
        cid = comp.get("id")
        ctype = comp.get("component")
        if not isinstance(cid, str) or not cid.strip():
            errors.append(f"components[{idx}] missing valid string 'id'")
            continue
        if cid in by_id:
            errors.append(f"duplicate component id {cid!r}")
            continue
        if not isinstance(ctype, str) or ctype not in allowed_components:
            errors.append(f"component '{cid}' uses uncataloged component type {ctype!r}")
        else:
            req_fields = allowed_components[ctype].get("required") or []
            for req in req_fields:
                if req not in comp:
                    errors.append(f"component '{cid}' ({ctype}) missing required property {req!r}")
        by_id[cid] = comp
        child_refs: list[str] = []
        if "child" in comp:
            if not isinstance(comp["child"], str) or not comp["child"]:
                errors.append(f"component '{cid}'.child must be a non-empty component id string")
            else:
                child_refs.append(comp["child"])
        if "children" in comp:
            if not isinstance(comp["children"], list) or not all(isinstance(x, str) and x for x in comp["children"]):
                errors.append(f"component '{cid}'.children must be a list of component id strings")
            else:
                child_refs.extend(comp["children"])
        edges[cid] = child_refs
        prop_defs = (allowed_components.get(comp.get("component"), {}) or {}).get("properties") or {}
        for prop_k, prop_v in comp.items():
            if prop_k in ("id", "component", "child", "children"):
                continue
            _scan_component_value_for_pointers_and_scripts(prop_v, cid, data_model, errors)
            if prop_k in prop_defs and "type" in prop_defs[prop_k]:
                expected_t = prop_defs[prop_k]["type"]
                if isinstance(prop_v, dict) and set(prop_v.keys()) == {"@path"} and isinstance(prop_v.get("@path"), str):
                    ok, resolved_v = resolve_json_pointer(data_model, prop_v["@path"])
                    if ok:
                        non_obj_types = [t for t in ([expected_t] if isinstance(expected_t, str) else expected_t) if t != "object"] or expected_t
                        if not _matches_schema_type(resolved_v, non_obj_types):
                            errors.append(f"component '{cid}'.{prop_k} @path target has invalid type {type(resolved_v).__name__} (expected { non_obj_types })")
                elif not _matches_schema_type(prop_v, expected_t):
                    errors.append(f"component '{cid}'.{prop_k} has invalid type {type(prop_v).__name__} (expected {expected_t})")
    if "root" not in by_id:
        errors.append("updateComponents.components must include an entry with id='root'")
    else:
        for cid, refs in edges.items():
            for ref in refs:
                if ref not in by_id:
                    errors.append(f"component '{cid}' references non-existent child id {ref!r}")

        state: dict[str, int] = {}
        reachable: set[str] = set()

        def dfs(node: str) -> None:
            state[node] = 1
            reachable.add(node)
            for nxt in edges.get(node, []):
                if nxt not in by_id:
                    continue
                st = state.get(nxt, 0)
                if st == 1:
                    errors.append(f"cycle detected in component graph involving '{node}' -> '{nxt}'")
                elif st == 0:
                    dfs(nxt)
            state[node] = 2

        dfs("root")
        orphans = sorted(set(by_id.keys()) - reachable)
        if orphans:
            errors.append(f"unreachable orphan component(s) not connected from 'root': {orphans}")

    return {
        "valid": len(errors) == 0,
        "surface_id": surface_id,
        "catalog_id": catalog_id,
        "component_count": len(by_id),
        "errors": errors,
    }


def compile_spec_to_a2ui(spec: dict, surface_id: str) -> dict:
    title = str(spec.get("title") or "Deepmodebot Visual Cockpit")
    subtitle = str(spec.get("subtitle") or "")
    mode_badge = str(spec.get("mode_badge") or "A2UI 1.0 · Operate")
    metrics = list(spec.get("metrics") or [])
    suggestions = list(spec.get("suggestions") or [])
    decisions = list(spec.get("decisions") or [])
    findings = list(spec.get("findings") or [])

    data_model: dict[str, Any] = {
        "meta": {
            "title": title,
            "subtitle": subtitle,
            "modeBadge": mode_badge,
            "generatedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "metrics": [
            {
                "label": str(m.get("label") or ""),
                "value": m.get("value", 0),
                "tone": str(m.get("tone") or "neutral"),
            }
            for m in metrics
        ],
        "suggestions": [
            {
                "priority": str(s.get("priority") or "P1"),
                "kind": str(s.get("kind") or "gap"),
                "title": str(s.get("title") or ""),
                "evidence": [str(e) for e in (s.get("evidence") or [])],
                "prompt": str(s.get("prompt") or ""),
                "selected": bool(s.get("selected", idx == 0)),
            }
            for idx, s in enumerate(suggestions)
        ],
        "decisions": [
            {
                "id": str(d.get("id") or f"d{idx + 1}"),
                "question": str(d.get("question") or ""),
                "choice": str(d.get("choice") or (d.get("options") or [""])[0]),
                "options": [str(o) for o in (d.get("options") or [])] or [str(d.get("choice") or "Proceed")],
                "why": str(d.get("why") or ""),
                "reverse": str(d.get("reverse") or ""),
            }
            for idx, d in enumerate(decisions)
        ],
        "findings": [
            {
                "severity": str(f.get("severity") or "P1"),
                "category": str(f.get("category") or "audit"),
                "location": str(f.get("location") or ""),
                "detail": str(f.get("detail") or ""),
            }
            for f in findings
        ],
    }

    components: list[dict[str, Any]] = []
    root_children: list[str] = []

    if data_model["metrics"]:
        metric_ids: list[str] = []
        for idx in range(len(data_model["metrics"])):
            mid = f"metric_{idx}"
            metric_ids.append(mid)
            components.append(
                {
                    "id": mid,
                    "component": "MetricTile",
                    "label": {"@path": f"/metrics/{idx}/label"},
                    "value": {"@path": f"/metrics/{idx}/value"},
                    "tone": {"@path": f"/metrics/{idx}/tone"},
                }
            )
        components.append({"id": "metrics_strip", "component": "MetricStrip", "children": metric_ids})
        root_children.append("metrics_strip")

    if data_model["decisions"]:
        dec_ids: list[str] = []
        for idx, dec in enumerate(data_model["decisions"]):
            did = f"decision_{idx}"
            dec_ids.append(did)
            components.append(
                {
                    "id": did,
                    "component": "DecisionCard",
                    "decisionId": dec["id"],
                    "question": {"@path": f"/decisions/{idx}/question"},
                    "choice": {"@path": f"/decisions/{idx}/choice"},
                    "options": {"@path": f"/decisions/{idx}/options"},
                    "why": {"@path": f"/decisions/{idx}/why"},
                    "reverse": {"@path": f"/decisions/{idx}/reverse"},
                    "action": {
                        "event": {
                            "name": "override_decision",
                            "context": {
                                "decisionId": dec["id"],
                                "choice": {"@path": f"/decisions/{idx}/choice"},
                            },
                        }
                    },
                }
            )
        components.append(
            {
                "id": "decisions_section",
                "component": "Section",
                "heading": "Converged Decisions & Trade-offs",
                "summary": "Agent-recommended choices pre-selected; click any option to override and export back.",
                "children": dec_ids,
            }
        )
        root_children.append("decisions_section")

    if data_model["suggestions"]:
        sug_ids: list[str] = []
        for idx in range(len(data_model["suggestions"])):
            sid = f"suggestion_{idx}"
            sug_ids.append(sid)
            components.append(
                {
                    "id": sid,
                    "component": "SuggestionCard",
                    "itemIndex": idx,
                    "priority": {"@path": f"/suggestions/{idx}/priority"},
                    "kind": {"@path": f"/suggestions/{idx}/kind"},
                    "title": {"@path": f"/suggestions/{idx}/title"},
                    "evidence": {"@path": f"/suggestions/{idx}/evidence"},
                    "prompt": {"@path": f"/suggestions/{idx}/prompt"},
                    "selected": {"@path": f"/suggestions/{idx}/selected"},
                    "action": {
                        "event": {
                            "name": "run_suggested_prompt",
                            "context": {
                                "priority": {"@path": f"/suggestions/{idx}/priority"},
                                "prompt": {"@path": f"/suggestions/{idx}/prompt"},
                            },
                        }
                    },
                }
            )
        components.append(
            {
                "id": "suggestions_section",
                "component": "Section",
                "heading": "Ranked Hardcore /deep Prompts",
                "summary": "Filter by priority or category, inspect file:line receipts, or combine multiple prompts.",
                "children": sug_ids,
            }
        )
        root_children.append("suggestions_section")

    if data_model["findings"]:
        find_ids: list[str] = []
        for idx in range(len(data_model["findings"])):
            fid = f"finding_{idx}"
            find_ids.append(fid)
            components.append(
                {
                    "id": fid,
                    "component": "FindingRow",
                    "severity": {"@path": f"/findings/{idx}/severity"},
                    "category": {"@path": f"/findings/{idx}/category"},
                    "location": {"@path": f"/findings/{idx}/location"},
                    "detail": {"@path": f"/findings/{idx}/detail"},
                }
            )
        components.append(
            {
                "id": "findings_section",
                "component": "Section",
                "heading": "Prosecutor & Diff Audit Evidence",
                "summary": "Verified file:line observations, risk signals, and deterministic gate checks.",
                "children": find_ids,
            }
        )
        root_children.append("findings_section")

    if not root_children:
        components.append({"id": "empty_note", "component": "Text", "text": "No findings, suggestions, or decisions in payload."})
        root_children.append("empty_note")

    components.append({"id": "export_btn_label", "component": "Text", "text": "Dispatch selection to agent"})
    components.append(
        {
            "id": "export_btn",
            "component": "ActionButton",
            "child": "export_btn_label",
            "variant": "primary",
            "action": {
                "event": {
                    "name": "submit_cockpit_selection",
                    "context": {
                        "suggestions": {"@path": "/suggestions"},
                        "decisions": {"@path": "/decisions"},
                    },
                }
            },
        }
    )
    root_children.append("export_btn")

    components.insert(
        0,
        {
            "id": "root",
            "component": "SurfaceShell",
            "title": {"@path": "/meta/title"},
            "subtitle": {"@path": "/meta/subtitle"},
            "modeBadge": {"@path": "/meta/modeBadge"},
            "children": root_children,
        },
    )

    return {
        "protocol": "A2UI",
        "version": "1.0",
        "catalog": DEFAULT_CATALOG,
        "messages": [
            {
                "version": "1.0",
                "createSurface": {
                    "surfaceId": surface_id,
                    "catalogId": CATALOG_ID,
                },
            },
            {
                "version": "1.0",
                "updateComponents": {
                    "surfaceId": surface_id,
                    "components": components,
                },
            },
            {
                "version": "1.0",
                "updateDataModel": {
                    "surfaceId": surface_id,
                    "path": "/",
                    "value": data_model,
                },
            },
        ],
    }


def safe_json_for_html_script(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, indent=2)
    return raw.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")

HTML_TEMPLATE = r"""<!doctype html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="color-scheme" content="dark light">
  <title>__PAGE_TITLE__</title>
  <style>
    :root, [data-theme="dark"] {
      color-scheme: dark;
      --bg-canvas: oklch(0.145 0.011 168);
      --bg-surface: oklch(0.185 0.012 168);
      --bg-elevated: oklch(0.225 0.013 168);
      --bg-subtle: oklch(0.125 0.010 168);
      --bg-dock: oklch(0.175 0.012 168 / 0.84);
      --fg-primary: oklch(0.935 0.009 92);
      --fg-secondary: oklch(0.75 0.010 140);
      --fg-muted: oklch(0.63 0.010 155);
      --border-subtle: oklch(0.95 0.008 168 / 0.09);
      --border-strong: oklch(0.95 0.008 168 / 0.18);
      --rim-light: inset 0 1px 0 oklch(1 0 0 / 0.065);
      --shadow-surface: 0 1px 2px oklch(0 0 0 / 0.28), 0 8px 24px oklch(0 0 0 / 0.18);
      --accent: oklch(0.79 0.068 164);
      --accent-hover: oklch(0.84 0.072 164);
      --accent-fg: oklch(0.15 0.015 168);
      --accent-soft: oklch(0.79 0.068 164 / 0.13);
      --status-p0-bg: oklch(0.32 0.085 24 / 0.55);
      --status-p0-fg: oklch(0.84 0.12 24);
      --status-p1-bg: oklch(0.33 0.075 76 / 0.55);
      --status-p1-fg: oklch(0.86 0.11 76);
      --status-p2-bg: oklch(0.31 0.055 215 / 0.55);
      --status-p2-fg: oklch(0.84 0.08 215);
      --status-ok-bg: oklch(0.31 0.065 156 / 0.55);
      --status-ok-fg: oklch(0.84 0.10 156);
      --radius-sm: 6px;
      --radius-md: 10px;
      --font-display: "Plus Jakarta Sans", "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      --font-sans: "Inter", "Figtree", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      --font-mono: "JetBrains Mono", "Cascadia Code", "DM Mono", ui-monospace, Menlo, Consolas, monospace;
    }
    [data-theme="light"] {
      color-scheme: light;
      --bg-canvas: oklch(0.965 0.007 92);
      --bg-surface: oklch(0.992 0.004 92);
      --bg-elevated: oklch(0.948 0.008 92);
      --bg-subtle: oklch(0.935 0.009 92);
      --bg-dock: oklch(0.985 0.005 92 / 0.86);
      --fg-primary: oklch(0.19 0.014 168);
      --fg-secondary: oklch(0.39 0.014 165);
      --fg-muted: oklch(0.52 0.012 162);
      --border-subtle: oklch(0.19 0.014 168 / 0.09);
      --border-strong: oklch(0.19 0.014 168 / 0.18);
      --rim-light: inset 0 1px 0 oklch(1 0 0 / 0.85);
      --shadow-surface: 0 1px 2px oklch(0 0 0 / 0.03), 0 4px 14px oklch(0 0 0 / 0.04);
      --accent: oklch(0.41 0.088 166);
      --accent-hover: oklch(0.36 0.092 166);
      --accent-fg: oklch(0.985 0.004 92);
      --accent-soft: oklch(0.41 0.088 166 / 0.10);
      --status-p0-bg: oklch(0.93 0.045 24);
      --status-p0-fg: oklch(0.42 0.14 24);
      --status-p1-bg: oklch(0.94 0.05 76);
      --status-p1-fg: oklch(0.43 0.12 76);
      --status-p2-bg: oklch(0.93 0.035 215);
      --status-p2-fg: oklch(0.40 0.10 215);
      --status-ok-bg: oklch(0.93 0.045 156);
      --status-ok-fg: oklch(0.38 0.11 156);
    }
    * { box-sizing: border-box; }
    ::selection { background: var(--accent-soft); color: var(--fg-primary); }
    body {
      margin: 0;
      background: var(--bg-canvas);
      color: var(--fg-primary);
      font-family: var(--font-sans);
      font-size: 15px;
      line-height: 1.55;
      -webkit-font-smoothing: antialiased;
      padding-bottom: 104px;
    }
    :focus-visible {
      outline: 2px solid var(--accent);
      outline-offset: 2px;
    }
    .shell {
      max-width: 1140px;
      margin: 0 auto;
      padding: 36px 24px 48px;
    }
    .topbar {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: flex-end;
      gap: 16px;
      padding-bottom: 24px;
      margin-bottom: 24px;
      border-bottom: 1px solid var(--border-subtle);
    }
    .title-group { min-width: 0; flex: 1 1 320px; }
    .title-group h1 {
      font-family: var(--font-display);
      font-size: clamp(1.5rem, 2.2vw, 1.9rem);
      font-weight: 650;
      letter-spacing: -0.03em;
      line-height: 1.15;
      text-wrap: balance;
      margin: 0 0 6px;
    }
    .title-group p {
      margin: 0;
      color: var(--fg-muted);
      font-size: 0.82rem;
      font-family: var(--font-mono);
      overflow-wrap: anywhere;
    }
    .toolbar {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      padding: 4px 9px;
      border-radius: 999px;
      font-size: 0.72rem;
      font-weight: 600;
      font-family: var(--font-mono);
      background: var(--accent-soft);
      color: var(--accent);
      letter-spacing: 0.01em;
    }
    .btn {
      min-height: 36px;
      padding: 7px 14px;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border-subtle);
      background: var(--bg-surface);
      color: var(--fg-primary);
      font-size: 0.83rem;
      font-weight: 550;
      cursor: pointer;
      box-shadow: var(--rim-light);
      transition: transform 110ms ease-out, background-color 140ms ease-out, border-color 140ms ease-out;
    }
    .btn:hover { background: var(--bg-elevated); border-color: var(--border-strong); }
    .btn:active { transform: scale(0.97); }
    .btn-primary {
      background: var(--accent);
      color: var(--accent-fg);
      border-color: transparent;
      font-weight: 650;
    }
    .btn-primary:hover { background: var(--accent-hover); border-color: transparent; }
    .metrics {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 1px;
      margin-bottom: 28px;
      background: var(--border-subtle);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-md);
      box-shadow: var(--rim-light), var(--shadow-surface);
      overflow: hidden;
    }
    .metric-tile {
      background: var(--bg-surface);
      padding: 16px 20px;
      position: relative;
    }
    .metric-tile .m-label {
      color: var(--fg-muted);
      font-size: 0.75rem;
      font-weight: 500;
      margin-bottom: 6px;
    }
    .metric-tile .m-val {
      font-size: 1.6rem;
      font-weight: 650;
      letter-spacing: -0.02em;
      line-height: 1.1;
      font-family: var(--font-mono);
      font-variant-numeric: tabular-nums;
    }
    .metric-tile[data-tone="warn"] .m-val { color: var(--status-p0-fg); }
    .metric-tile[data-tone="ok"] .m-val { color: var(--status-ok-fg); }
    .controls-bar {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 28px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border-subtle);
    }
    .pill-row { display: flex; flex-wrap: wrap; gap: 6px; }
    .pill {
      min-height: 34px;
      padding: 6px 13px;
      border-radius: 999px;
      border: 1px solid transparent;
      background: transparent;
      color: var(--fg-secondary);
      font-size: 0.8rem;
      font-weight: 550;
      cursor: pointer;
      transition: background-color 140ms ease-out, color 140ms ease-out, border-color 140ms ease-out;
    }
    .pill:hover { background: var(--bg-surface); color: var(--fg-primary); }
    .pill[aria-pressed="true"] {
      background: var(--accent-soft);
      color: var(--accent);
      border-color: oklch(from var(--accent) l c h / 0.35);
      font-weight: 650;
    }
    .search-input {
      min-height: 36px;
      min-width: 290px;
      padding: 7px 12px;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border-subtle);
      background: var(--bg-subtle);
      color: var(--fg-primary);
      font-size: 0.84rem;
      transition: border-color 140ms ease-out, background-color 140ms ease-out;
    }
    .search-input::placeholder { color: var(--fg-muted); }
    .search-input:focus { background: var(--bg-surface); border-color: var(--accent); }
    .card-check {
      width: 18px;
      height: 18px;
      margin: 2px 2px 2px 0;
      cursor: pointer;
      accent-color: var(--accent);
      flex-shrink: 0;
    }
    .section { margin-bottom: 36px; }
    .section-head { margin-bottom: 16px; }
    .section-head h2 {
      font-family: var(--font-display);
      font-size: 1.12rem;
      font-weight: 650;
      letter-spacing: -0.02em;
      margin: 0 0 3px;
    }
    .section-head p {
      margin: 0;
      font-size: 0.84rem;
      color: var(--fg-muted);
    }
    .stack { display: flex; flex-direction: column; gap: 14px; }
    .card {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-md);
      padding: 18px 20px;
      box-shadow: var(--rim-light), var(--shadow-surface);
      transition: border-color 150ms ease-out, background-color 150ms ease-out;
    }
    .card:hover { border-color: var(--border-strong); }
    .card[data-selected="true"] {
      border-color: oklch(from var(--accent) l c h / 0.55);
      box-shadow: inset 3px 0 0 var(--accent), var(--rim-light), var(--shadow-surface);
    }
    .card-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 14px;
      margin-bottom: 12px;
    }
    .card-title-row {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      min-width: 0;
    }
    .prio {
      font-family: var(--font-mono);
      font-size: 0.72rem;
      font-weight: 700;
      padding: 2px 7px;
      border-radius: 4px;
      letter-spacing: 0.02em;
    }
    .prio-P0 { background: var(--status-p0-bg); color: var(--status-p0-fg); }
    .prio-P1 { background: var(--status-p1-bg); color: var(--status-p1-fg); }
    .prio-P2 { background: var(--status-p2-bg); color: var(--status-p2-fg); }
    .kind-tag {
      font-family: var(--font-mono);
      font-size: 0.72rem;
      color: var(--fg-muted);
      padding: 2px 6px;
      background: var(--bg-subtle);
      border-radius: 4px;
    }
    .card h3 {
      margin: 0;
      font-size: 0.98rem;
      font-weight: 600;
      letter-spacing: -0.01em;
    }
    .evidence-list {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin: 0 0 12px;
      padding: 0;
      list-style: none;
    }
    .evidence-list li {
      font-family: var(--font-mono);
      font-size: 0.74rem;
      background: var(--bg-subtle);
      color: var(--fg-secondary);
      padding: 3px 8px;
      border-radius: 4px;
      max-width: 100%;
      overflow-wrap: anywhere;
    }
    .prompt-box {
      margin: 0;
      padding: 13px 15px;
      background: var(--bg-subtle);
      border-radius: var(--radius-sm);
      font-family: var(--font-mono);
      font-size: 0.8rem;
      line-height: 1.55;
      color: var(--fg-primary);
      white-space: pre-wrap;
      word-break: break-word;
    }
    .options-grid {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 12px 0;
    }
    .opt-btn {
      min-height: 36px;
      padding: 7px 14px;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border-subtle);
      background: var(--bg-subtle);
      color: var(--fg-secondary);
      font-size: 0.83rem;
      font-weight: 500;
      cursor: pointer;
      transition: background-color 130ms ease-out, border-color 130ms ease-out, color 130ms ease-out;
    }
    .opt-btn:hover { background: var(--bg-elevated); color: var(--fg-primary); }
    .opt-btn[aria-checked="true"] {
      background: var(--accent-soft);
      border-color: var(--accent);
      color: var(--accent);
      font-weight: 650;
    }
    .meta-note {
      font-size: 0.82rem;
      color: var(--fg-secondary);
      margin: 6px 0 0;
    }
    .finding-row {
      display: grid;
      grid-template-columns: auto auto minmax(0, 1fr) minmax(0, 2fr);
      gap: 12px;
      align-items: center;
      padding: 12px 16px;
      background: var(--bg-surface);
      border-bottom: 1px solid var(--border-subtle);
      font-size: 0.84rem;
    }
    .finding-row > * { min-width: 0; overflow-wrap: anywhere; }
    .finding-row .prio, .finding-row .kind-tag { justify-self: start; }
    .finding-row:first-child { border-radius: var(--radius-md) var(--radius-md) 0 0; }
    .finding-row:last-child { border-bottom: 0; border-radius: 0 0 var(--radius-md) var(--radius-md); }
    .finding-row:only-child { border-radius: var(--radius-md); }
    .dock {
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      background: var(--bg-dock);
      backdrop-filter: blur(16px) saturate(1.5);
      -webkit-backdrop-filter: blur(16px) saturate(1.5);
      border-top: 1px solid var(--border-strong);
      box-shadow: var(--rim-light);
      padding: 12px 24px calc(12px + env(safe-area-inset-bottom, 0px));
      z-index: 20;
    }
    .dock-inner {
      max-width: 1140px;
      margin: 0 auto;
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
    }
    .status-toast {
      font-size: 0.82rem;
      color: var(--fg-secondary);
      font-family: var(--font-mono);
    }
    @media (pointer: coarse), (max-width: 720px) {
      .btn, .pill, .opt-btn, .search-input { min-height: 44px; min-width: 44px; }
      .shell { padding: 20px 16px 40px; }
      .search-input { min-width: 0; width: 100%; }
      .card-top { flex-direction: column; align-items: stretch; }
      .finding-row { grid-template-columns: minmax(0, 1fr); gap: 6px; }
      .dock { padding: 12px 16px calc(12px + env(safe-area-inset-bottom, 0px)); }
    }
    @media (prefers-reduced-motion: reduce) {
      .btn, .pill, .opt-btn, .card, .search-input { transition: none; }
    }
  </style>
</head>
<body>
  <script id="a2ui-payload" type="application/a2ui+json">
__A2UI_JSON__
  </script>
  <main id="a2ui-root" class="shell" aria-live="polite"></main>
  <footer class="dock" role="region" aria-label="Agent dispatch bar">
    <div class="dock-inner">
      <div id="dock-summary" class="status-toast">Ready</div>
      <div class="toolbar">
        <button id="copy-combined-btn" type="button" class="btn btn-primary">Copy selected /deep prompt</button>
        <button id="copy-action-btn" type="button" class="btn">Copy A2UI 1.0 action JSON</button>
      </div>
    </div>
  </footer>
  <script>
    (() => {
      const raw = document.getElementById("a2ui-payload").textContent;
      const bundle = JSON.parse(raw);
      const createMsg = bundle.messages.find(m => m.createSurface).createSurface;
      const compList = bundle.messages.find(m => m.updateComponents).updateComponents.components;
      const dataModel = JSON.parse(JSON.stringify(bundle.messages.find(m => m.updateDataModel).updateDataModel.value));
      const compMap = new Map(compList.map(c => [c.id, c]));
      let activePrio = "ALL";
      let searchQuery = "";
      let lastActionMessage = null;

      function getPointer(obj, ptr) {
        if (ptr === "/") return obj;
        if (typeof ptr !== "string" || !ptr.startsWith("/")) return undefined;
        let cur = obj;
        for (const seg of ptr.slice(1).split("/")) {
          const key = seg.replace(/~1/g, "/").replace(/~0/g, "~");
          if (cur == null) return undefined;
          cur = Array.isArray(cur) ? cur[Number(key)] : cur[key];
        }
        return cur;
      }

      const FORBIDDEN_KEYS = new Set(["__proto__", "constructor", "prototype"]);
      function setPointer(obj, ptr, val) {
        if (typeof ptr !== "string" || !ptr.startsWith("/") || ptr === "/") return false;
        const parts = ptr.slice(1).split("/").map(s => s.replace(/~1/g, "/").replace(/~0/g, "~"));
        let cur = obj;
        for (let i = 0; i < parts.length - 1; i++) {
          if (cur == null || typeof cur !== "object" || FORBIDDEN_KEYS.has(parts[i])) return false;
          const k = Array.isArray(cur) ? Number(parts[i]) : parts[i];
          cur = cur[k];
        }
        const rawLeaf = parts[parts.length - 1];
        if (cur == null || typeof cur !== "object" || FORBIDDEN_KEYS.has(rawLeaf)) return false;
        const leaf = Array.isArray(cur) ? Number(rawLeaf) : rawLeaf;
        if (Array.isArray(cur) && (!Number.isInteger(leaf) || leaf < 0 || leaf >= cur.length)) return false;
        cur[leaf] = val;
        return true;
      }

      function resolveProp(prop) {
        if (prop && typeof prop === "object" && !Array.isArray(prop) && Object.keys(prop).length === 1 && "@path" in prop) {
          return getPointer(dataModel, prop["@path"]);
        }
        if (Array.isArray(prop)) return prop.map(resolveProp);
        if (prop && typeof prop === "object") {
          const out = {};
          for (const [k, v] of Object.entries(prop)) out[k] = resolveProp(v);
          return out;
        }
        return prop;
      }

      function emitAction(sourceId, actionSpec) {
        if (!actionSpec || !actionSpec.event) return null;
        const msg = {
          version: "1.0",
          action: {
            name: actionSpec.event.name,
            surfaceId: createMsg.surfaceId,
            sourceComponentId: sourceId,
            timestamp: new Date().toISOString(),
            context: resolveProp(actionSpec.event.context || {})
          }
        };
        lastActionMessage = msg;
        return msg;
      }

      function el(tag, attrs = {}, children = []) {
        const node = document.createElement(tag);
        for (const [k, v] of Object.entries(attrs)) {
          if (v === undefined || v === null) continue;
          if (k === "className") node.className = v;
          else if (k === "textContent") node.textContent = String(v);
          else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2).toLowerCase(), v);
          else node.setAttribute(k, String(v));
        }
        for (const ch of children) {
          if (ch == null) continue;
          node.appendChild(typeof ch === "string" ? document.createTextNode(ch) : ch);
        }
        return node;
      }

      async function copyText(text, label) {
        try {
          await navigator.clipboard.writeText(text);
          setToast(label);
        } catch (_err) {
          const ta = el("textarea", { style: "position:fixed;opacity:0" });
          ta.value = text;
          document.body.appendChild(ta);
          ta.select();
          document.execCommand("copy");
          ta.remove();
          setToast(label);
        }
      }

      function setToast(msg) {
        const dock = document.getElementById("dock-summary");
        if (dock) dock.textContent = msg;
      }

      function matchesFilter(textBlob, prio) {
        if (activePrio !== "ALL" && prio !== activePrio) return false;
        if (!searchQuery) return true;
        return textBlob.toLowerCase().includes(searchQuery.toLowerCase());
      }

      function renderNode(id) {
        const comp = compMap.get(id);
        if (!comp) return null;
        const type = comp.component;

        if (type === "Text") {
          return el("span", { textContent: resolveProp(comp.text) });
        }

        if (type === "MetricStrip") {
          return el("section", { className: "metrics", "aria-label": "Repository and audit metrics" }, (comp.children || []).map(renderNode));
        }

        if (type === "MetricTile") {
          const tone = resolveProp(comp.tone) || "neutral";
          return el("div", { className: "metric-tile", "data-tone": tone }, [
            el("div", { className: "m-label", textContent: resolveProp(comp.label) }),
            el("div", { className: "m-val", textContent: resolveProp(comp.value) })
          ]);
        }

        if (type === "Section") {
          const renderedChildren = (comp.children || []).map(renderNode).filter(Boolean);
          if (renderedChildren.length === 0) return null;
          return el("section", { className: "section" }, [
            el("div", { className: "section-head" }, [
              el("h2", { textContent: resolveProp(comp.heading) }),
              comp.summary ? el("p", { textContent: resolveProp(comp.summary) }) : null
            ]),
            el("div", { className: "stack" }, renderedChildren)
          ]);
        }

        if (type === "SuggestionCard") {
          const idx = comp.itemIndex;
          const prio = resolveProp(comp.priority);
          const kind = resolveProp(comp.kind);
          const title = resolveProp(comp.title);
          const evidence = resolveProp(comp.evidence) || [];
          const prompt = resolveProp(comp.prompt);
          const selected = Boolean(resolveProp(comp.selected));
          const blob = [prio, kind, title, prompt, ...evidence].join(" ");
          if (!matchesFilter(blob, prio)) return null;

          const selPtr = (comp.selected && typeof comp.selected === "object" && comp.selected["@path"])
            ? comp.selected["@path"]
            : ("/suggestions/" + idx + "/selected");
          const checkbox = el("input", {
            type: "checkbox",
            className: "card-check",
            "data-focus-key": "chk:" + id,
            "aria-label": "Select " + title,
            onChange: (e) => {
              setPointer(dataModel, selPtr, e.target.checked);
              renderSurface("chk:" + id);
            }
          });
          checkbox.checked = selected;

          return el("article", { className: "card", "data-selected": String(selected) }, [
            el("div", { className: "card-top" }, [
              el("div", { className: "card-title-row" }, [
                checkbox,
                el("span", { className: "prio prio-" + prio, textContent: prio }),
                el("span", { className: "kind-tag", textContent: kind }),
                el("h3", { textContent: title })
              ]),
              el("button", {
                type: "button",
                className: "btn",
                "data-focus-key": "btn:" + id,
                textContent: "Copy /deep prompt",
                onClick: () => {
                  emitAction(id, comp.action);
                  copyText(prompt, "Copied [" + prio + "] /deep prompt to clipboard");
                }
              })
            ]),
            evidence.length ? el("ul", { className: "evidence-list", "aria-label": "Evidence anchors" }, evidence.map(ev => el("li", { textContent: ev }))) : null,
            el("pre", { className: "prompt-box", textContent: prompt })
          ]);
        }

        if (type === "DecisionCard") {
          const choicePtr = (comp.choice && typeof comp.choice === "object" && comp.choice["@path"])
            ? comp.choice["@path"]
            : ("/decisions/" + (Number.isInteger(comp.itemIndex) ? comp.itemIndex : 0) + "/choice");
          const question = resolveProp(comp.question);
          const choice = resolveProp(comp.choice);
          const options = resolveProp(comp.options) || [];
          const why = resolveProp(comp.why);
          const reverse = resolveProp(comp.reverse);
          const searchBlob = [comp.decisionId || "", question, choice, why || "", reverse || "", ...options].join(" ").toLowerCase();
          if (searchQuery && !searchBlob.includes(searchQuery.toLowerCase())) return null;

          const selectOption = (opt, optIdx) => {
            setPointer(dataModel, choicePtr, opt);
            emitAction(id, comp.action);
            renderSurface("opt:" + id + ":" + optIdx);
          };

          return el("article", { className: "card", "data-selected": "true" }, [
            el("div", { className: "card-title-row" }, [
              el("span", { className: "kind-tag", textContent: comp.decisionId }),
              el("h3", { textContent: question })
            ]),
            el("div", {
              className: "options-grid",
              role: "radiogroup",
              "aria-label": question,
              onKeydown: (e) => {
                if (!["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(e.key) || !options.length) return;
                e.preventDefault();
                const curIdx = Math.max(0, options.indexOf(choice));
                const delta = (e.key === "ArrowRight" || e.key === "ArrowDown") ? 1 : -1;
                const nextIdx = (curIdx + delta + options.length) % options.length;
                selectOption(options[nextIdx], nextIdx);
              }
            }, options.map((opt, optIdx) => el("button", {
              type: "button",
              role: "radio",
              className: "opt-btn",
              "data-focus-key": "opt:" + id + ":" + optIdx,
              tabIndex: (opt === choice || (options.indexOf(choice) < 0 && optIdx === 0)) ? 0 : -1,
              "aria-checked": String(opt === choice),
              textContent: opt,
              onClick: () => selectOption(opt, optIdx)
            }))),
            why ? el("p", { className: "meta-note", textContent: "Why: " + why }) : null,
            reverse ? el("p", { className: "meta-note", textContent: "Reversal path: " + reverse }) : null
          ]);
        }

        if (type === "FindingRow") {
          const sev = resolveProp(comp.severity);
          const cat = resolveProp(comp.category);
          const loc = resolveProp(comp.location);
          const detail = resolveProp(comp.detail);
          if (!matchesFilter([sev, cat, loc, detail].join(" "), sev)) return null;
          return el("div", { className: "finding-row" }, [
            el("span", { className: "prio prio-" + (sev === "P0" || sev === "P1" || sev === "P2" ? sev : "P1"), textContent: sev }),
            el("span", { className: "kind-tag", textContent: cat }),
            el("code", { textContent: loc }),
            el("span", { textContent: detail })
          ]);
        }

        if (type === "ActionButton") {
          if (id === "export_btn") return null;
          const labelNode = comp.child ? renderNode(comp.child) : "Run action";
          const cls = comp.variant === "primary" ? "btn btn-primary" : "btn";
          return el("button", {
            type: "button",
            className: cls,
            "data-focus-key": "act:" + id,
            onClick: () => {
              const msg = emitAction(id, comp.action);
              if (msg) setToast("Dispatched A2UI action: " + msg.action.name);
            }
          }, [labelNode]);
        }

        if (type === "SurfaceShell") {
          const hasFilterable = Boolean(
            (dataModel.suggestions && dataModel.suggestions.length > 0) ||
            (dataModel.findings && dataModel.findings.length > 0) ||
            (dataModel.decisions && dataModel.decisions.length > 0)
          );
          const searchInput = el("input", {
            type: "search",
            id: "cockpit-search",
            "data-focus-key": "search",
            className: "search-input",
            placeholder: "Filter by file, rule, or keyword (/ to focus)",
            "aria-label": "Filter items",
            value: searchQuery,
            onInput: (e) => {
              searchQuery = e.target.value;
              renderBodyOnly();
            }
          });

          const header = el("header", { className: "topbar" }, [
            el("div", { className: "title-group" }, [
              el("h1", { textContent: resolveProp(comp.title) }),
              el("p", { textContent: resolveProp(comp.subtitle) })
            ]),
            el("div", { className: "toolbar" }, [
              el("span", { className: "badge", textContent: resolveProp(comp.modeBadge) }),
              el("button", {
                type: "button",
                className: "btn",
                "data-focus-key": "theme-toggle",
                textContent: "Toggle theme",
                onClick: () => {
                  const cur = document.documentElement.getAttribute("data-theme") || "dark";
                  document.documentElement.setAttribute("data-theme", cur === "dark" ? "light" : "dark");
                }
              })
            ])
          ]);

          const controls = hasFilterable ? el("div", { className: "controls-bar" }, [
            el("div", { className: "pill-row", role: "group", "aria-label": "Filter by priority" }, ["ALL", "P0", "P1", "P2"].map(p => el("button", {
              type: "button",
              className: "pill",
              "data-focus-key": "pill:" + p,
              "aria-pressed": String(activePrio === p),
              textContent: p === "ALL" ? "All priorities" : p,
              onClick: () => {
                activePrio = p;
                renderSurface("pill:" + p);
              }
            }))),
            searchInput
          ]) : null;

          const bodyContainer = el("div", { id: "cockpit-body" }, (comp.children || []).map(renderNode));
          return el("div", {}, [header, controls, bodyContainer]);
        }
        return null;
      }

      function renderBodyOnly() {
        const body = document.getElementById("cockpit-body");
        const rootComp = compMap.get("root");
        if (!body || !rootComp) return;
        body.replaceChildren(...(rootComp.children || []).map(renderNode).filter(Boolean));
        updateDockSummary();
      }

      function updateDockSummary() {
        const selectedSug = (dataModel.suggestions || []).filter(s => s.selected).length;
        const decCount = (dataModel.decisions || []).length;
        const parts = [];
        if (dataModel.suggestions && dataModel.suggestions.length) parts.push(selectedSug + " of " + dataModel.suggestions.length + " prompt(s) selected");
        if (decCount) parts.push(decCount + " decision(s) active");
        setToast(parts.join(" · ") || "A2UI 1.0 surface ready");
      }

      function buildCombinedPrompt() {
        const chosen = (dataModel.suggestions || []).filter(s => s.selected);
        const decs = dataModel.decisions || [];
        const lines = [];
        if (chosen.length === 1 && decs.length === 0) return chosen[0].prompt;
        if (chosen.length > 0) {
          lines.push("/deep [HARDCORE MODE] Execute the following selected full-scope deliverables end-to-end:");
          chosen.forEach((s, idx) => {
            lines.push((idx + 1) + ". [" + s.priority + "/" + s.kind + "] " + s.title + ": " + s.prompt.replace(/^\/deep\s+/i, ""));
          });
        }
        if (decs.length > 0) {
          lines.push("Locked decisions from cockpit:");
          decs.forEach(d => lines.push("- " + d.id + " (" + d.question + "): " + d.choice));
        }
        return lines.join("\n") || "/deep Inspect repository and propose next steps.";
      }

      function renderSurface(focusKey) {
        const prevKey = focusKey || (document.activeElement && document.activeElement.getAttribute && document.activeElement.getAttribute("data-focus-key"));
        const mount = document.getElementById("a2ui-root");
        mount.replaceChildren(renderNode("root"));
        updateDockSummary();
        if (prevKey) {
          const nextEl = mount.querySelector('[data-focus-key="' + CSS.escape(prevKey) + '"]');
          if (nextEl && typeof nextEl.focus === "function") nextEl.focus();
        }
      }

      document.getElementById("copy-combined-btn").addEventListener("click", () => {
        const exportComp = compMap.get("export_btn");
        if (exportComp) emitAction("export_btn", exportComp.action);
        copyText(buildCombinedPrompt(), "Copied combined /deep prompt to clipboard");
      });

      document.getElementById("copy-action-btn").addEventListener("click", () => {
        let msg = lastActionMessage;
        if (!msg) {
          const exportComp = compMap.get("export_btn");
          msg = exportComp ? emitAction("export_btn", exportComp.action) : {
            version: "1.0",
            action: {
              name: "submit_cockpit_selection",
              surfaceId: createMsg.surfaceId,
              sourceComponentId: "root",
              timestamp: new Date().toISOString(),
              context: dataModel
            }
          };
        }
        copyText(JSON.stringify(msg, null, 2), "Copied A2UI 1.0 renderer_to_agent action JSON");
      });

      window.addEventListener("keydown", (e) => {
        if (e.key === "/" && document.activeElement && document.activeElement.tagName !== "INPUT") {
          const inp = document.getElementById("cockpit-search");
          if (inp) {
            e.preventDefault();
            inp.focus();
          }
        }
      });

      renderSurface();
    })();
  </script>
</body>
</html>
"""


def render_html_cockpit(bundle: dict, page_title: str) -> str:
    safe_title = (
        page_title.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    embedded = safe_json_for_html_script(bundle)
    replacements = {
        "__PAGE_TITLE__": safe_title,
        "__A2UI_JSON__": embedded,
    }
    return re.sub(r"__PAGE_TITLE__|__A2UI_JSON__", lambda m: replacements[m.group(0)], HTML_TEMPLATE)


def _prune_old_gen_ui_surfaces(gen_base: Path, safe_root: Path, ensure_contained, keep: int = 8) -> None:
    if not gen_base.is_dir() or gen_base.is_symlink():
        return
    dirs = [d for d in gen_base.iterdir() if d.is_dir() and not d.is_symlink()]
    if len(dirs) <= keep:
        return
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    import shutil as _shutil
    for old_d in dirs[keep:]:
        ensure_contained(old_d, safe_root)
        _shutil.rmtree(old_d, ignore_errors=True)


def write_surface_artifacts(
    root: Path,
    slug: str,
    spec: dict,
    open_browser: bool = False,
) -> dict:
    self_grill = _load_sibling("genui_self_grill", "self-grill/self_grill.py")
    safe_root = self_grill.reject_unsafe_root(root)
    clean_slug = sanitize_slug(slug)
    gen_base = safe_root / ".scratch" / "gen-ui"
    out_dir = gen_base / clean_slug
    self_grill.ensure_contained(out_dir, safe_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    self_grill.ensure_contained(out_dir, gen_base)

    surface_id = f"deepmodebot-{clean_slug}-surface"
    bundle = compile_spec_to_a2ui(spec, surface_id=surface_id)
    validation = validate_a2ui_bundle(bundle)
    if not validation["valid"]:
        raise ValueError(f"generated A2UI bundle failed validation: {validation['errors']}")

    a2ui_path = out_dir / "surface.a2ui.json"
    html_path = out_dir / "index.html"
    self_grill.ensure_contained(a2ui_path, out_dir)
    self_grill.ensure_contained(html_path, out_dir)
    a2ui_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    html_text = render_html_cockpit(bundle, str(spec.get("title") or "Deepmodebot Visual Cockpit"))
    html_path.write_text(html_text, encoding="utf-8")
    _prune_old_gen_ui_surfaces(gen_base, safe_root, self_grill.ensure_contained, keep=8)
    opened = False
    if open_browser:
        try:
            opened = bool(webbrowser.open(html_path.resolve().as_uri()))
        except Exception:
            opened = False

    return {
        "valid": True,
        "protocol": "A2UI",
        "version": "1.0",
        "surface_id": surface_id,
        "slug": clean_slug,
        "component_count": validation["component_count"],
        "a2ui_path": str(a2ui_path),
        "html_path": str(html_path),
        "html_uri": html_path.resolve().as_uri(),
        "opened_browser": opened,
    }


def generate_from_suggest(
    root: Path,
    slug: str = "suggest",
    limit: int = 8,
    open_browser: bool = False,
    precomputed: dict | None = None,
) -> dict:
    prompt_tools = _load_sibling("genui_prompt_tools", "prompt-tools/prompt_tools.py")
    report = precomputed if precomputed is not None else prompt_tools.suggest_prompts(root, limit=limit)
    spec = {
        "title": f"Repo Gap, Overclaim & Hardcore Prompt Cockpit ({Path(report['root']).name})",
        "subtitle": report["root"],
        "mode_badge": "A2UI 1.0 · /suggest",
        "metrics": [
            {"label": "Code files", "value": report["code_file_count"], "tone": "neutral"},
            {"label": "Active diff", "value": report["diff_size"], "tone": "neutral"},
            {
                "label": "Overclaim hits",
                "value": report["overclaim_hits"],
                "tone": "warn" if report["overclaim_hits"] > 0 else "ok",
            },
            {
                "label": "Broken doc links",
                "value": report["broken_link_hits"],
                "tone": "warn" if report["broken_link_hits"] > 0 else "ok",
            },
            {"label": "Verify skills", "value": len(report["verify_skills"]), "tone": "ok" if report["verify_skills"] else "warn"},
            {"label": "Ranked prompts", "value": len(report["suggestions"]), "tone": "neutral"},
        ],
        "suggestions": report["suggestions"],
        "findings": [
            {
                "severity": "P1",
                "category": "core-module",
                "location": m["path"],
                "detail": f"{m['lines']} lines — top Hardcore Mode architectural ceiling candidate",
            }
            for m in report.get("core_modules", [])
        ],
    }
    ui_meta = write_surface_artifacts(Path(report["root"]), slug=slug, spec=spec, open_browser=open_browser)
    return {"suggest_report": report, "ui_surface": ui_meta}


def generate_from_grill(
    root: Path,
    slug: str = "grill",
    base: str | None = None,
    custom_spec: dict | None = None,
    open_browser: bool = False,
) -> dict:
    self_grill = _load_sibling("genui_self_grill_diff", "self-grill/self_grill.py")
    safe_root = self_grill.reject_unsafe_root(root)
    if custom_spec is not None:
        merged = dict(custom_spec)
        merged.setdefault("title", f"Decision & Plan Grill Cockpit ({safe_root.name})")
        merged.setdefault("subtitle", str(safe_root))
        merged.setdefault("mode_badge", "A2UI 1.0 · grill")
        return write_surface_artifacts(safe_root, slug=slug, spec=merged, open_browser=open_browser)

    diff = self_grill.inspect_diff(safe_root, base=base)
    findings: list[dict] = []
    for p in diff.get("sensitive_paths", []):
        findings.append({"severity": "P0", "category": "sensitive-path", "location": p, "detail": "Touches trust, auth, secret, or harness boundary"})
    for s in diff.get("toy_shortcuts", []):
        findings.append(
            {
                "severity": "P0" if s.get("critical") else "P1",
                "category": s["kind"],
                "location": f"{s['path']}:{s['line']}",
                "detail": s["text"],
            }
        )
    for w in diff.get("workaround_smells", []):
        findings.append(
            {
                "severity": "P1",
                "category": w["kind"],
                "location": f"{w['path']}:{w['line']}",
                "detail": w["text"],
            }
        )
    for c in diff.get("added_comments", [])[:15]:
        findings.append(
            {
                "severity": "P2",
                "category": "added-comment",
                "location": f"{c['path']}:{c['line']}",
                "detail": c["text"],
            }
        )
    spec = {
        "title": f"Self-Grill & Prosecutor Diff Cockpit ({safe_root.name})",
        "subtitle": str(safe_root),
        "mode_badge": "A2UI 1.0 · self-grill",
        "metrics": [
            {"label": "Measured size", "value": diff["measured_size"], "tone": "neutral"},
            {"label": "Changed files", "value": diff["file_count"], "tone": "neutral"},
            {"label": "Lines +/-", "value": f"+{diff['lines_added']}/-{diff['lines_deleted']}", "tone": "neutral"},
            {"label": "Sensitive paths", "value": len(diff["sensitive_paths"]), "tone": "warn" if diff["sensitive_paths"] else "ok"},
            {"label": "Toy shortcuts", "value": diff["toy_shortcut_count"], "tone": "warn" if diff["toy_shortcut_count"] else "ok"},
            {"label": "Added comments", "value": diff["added_comment_count"], "tone": "warn" if diff["added_comment_count"] else "ok"},
        ],
        "findings": findings,
    }
    return write_surface_artifacts(safe_root, slug=slug, spec=spec, open_browser=open_browser)


def cmd_from_suggest(args: argparse.Namespace) -> int:
    res = generate_from_suggest(Path(args.root), slug=args.slug, limit=args.limit, open_browser=args.open)
    if args.json:
        print(json.dumps(res["ui_surface"], indent=2))
    else:
        print(f"A2UI 1.0 surface: {res['ui_surface']['a2ui_path']}")
        print(f"Interactive HTML: {res['ui_surface']['html_path']}")
    return 0


def cmd_from_grill(args: argparse.Namespace) -> int:
    custom = json.loads(sys.stdin.read()) if args.spec_stdin else None
    res = generate_from_grill(Path(args.root), slug=args.slug, base=args.base, custom_spec=custom, open_browser=args.open)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"A2UI 1.0 surface: {res['a2ui_path']}")
        print(f"Interactive HTML: {res['html_path']}")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    spec = json.loads(sys.stdin.read())
    res = write_surface_artifacts(Path(args.root), slug=args.slug, spec=spec, open_browser=args.open)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"A2UI 1.0 surface: {res['a2ui_path']}")
        print(f"Interactive HTML: {res['html_path']}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    bundle = json.loads(Path(args.file).read_text(encoding="utf-8"))
    res = validate_a2ui_bundle(bundle)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        if res["valid"]:
            print(f"OK ({res['component_count']} components on {res['surface_id']})")
        else:
            for err in res["errors"]:
                print(f"ERROR: {err}", file=sys.stderr)
    return 0 if res["valid"] else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compile and validate A2UI v1.0 surfaces and interactive human cockpits.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_sug = sub.add_parser("from-suggest", help="Compile /suggest repo scan into A2UI v1.0 + interactive HTML cockpit.")
    p_sug.add_argument("--root", required=True)
    p_sug.add_argument("--slug", default="suggest")
    p_sug.add_argument("--limit", type=int, default=8)
    p_sug.add_argument("--open", action="store_true")
    p_sug.add_argument("--json", action="store_true")
    p_sug.set_defaults(func=cmd_from_suggest)

    p_gr = sub.add_parser("from-grill", help="Compile self-grill diff or custom decision spec into A2UI v1.0 + HTML cockpit.")
    p_gr.add_argument("--root", required=True)
    p_gr.add_argument("--slug", default="grill")
    p_gr.add_argument("--base", default=None)
    p_gr.add_argument("--spec-stdin", action="store_true")
    p_gr.add_argument("--open", action="store_true")
    p_gr.add_argument("--json", action="store_true")
    p_gr.set_defaults(func=cmd_from_grill)

    p_ren = sub.add_parser("render", help="Render an arbitrary cockpit JSON spec from stdin into A2UI v1.0 + HTML.")
    p_ren.add_argument("--root", required=True)
    p_ren.add_argument("--slug", required=True)
    p_ren.add_argument("--stdin", action="store_true")
    p_ren.add_argument("--open", action="store_true")
    p_ren.add_argument("--json", action="store_true")
    p_ren.set_defaults(func=cmd_render)

    p_val = sub.add_parser("validate-a2ui", help="Validate an A2UI v1.0 surface bundle for schema, DAG, pointers, and safety.")
    p_val.add_argument("--file", required=True)
    p_val.add_argument("--json", action="store_true")
    p_val.set_defaults(func=cmd_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
