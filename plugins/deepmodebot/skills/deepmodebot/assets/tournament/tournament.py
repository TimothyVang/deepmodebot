#!/usr/bin/env python3
"""Intent and vagueness auto-router plus 12-agent tournament bracket engine for deepmodebot.

    python tournament.py route --stdin [--root <repo>] [--has-factory] [--empty-dir] [--json] <<'EOF'
    python tournament.py init --root <repo> --slug <slug> --prompt-stdin [--entrants 12|8|4] [--force] [--json] <<'EOF'
    python tournament.py pitch --dir <dir> --entrant <id> --title <t> --thesis <t> --gap-kind <kind> --receipt <r>
    python tournament.py rebut --dir <dir> --entrant <id> --match <id> --target <id> --attack <t> --receipt <r>
    python tournament.py dropout --dir <dir> --entrant <id> --reason <why>
    python tournament.py judge --dir <dir> --match <id> --winner <id> --judge-model <m> --verified-receipt <r> --rationale <w>
    python tournament.py status --dir <dir> [--json]
    python tournament.py render --dir <dir> [--out <path>]

Pitches may be revised only before the entrant's first judged match.
Tournament routes preserve build intent; explicit choice or no-code constraints keep the checkpoint.
"""
import argparse
import contextlib
import ipaddress
import json
import os
import re
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

LENSES = (
    ("seam-archaeologist", "pod-a", "architecture",
     "Audit module depth, coupling seams, and git churn hotspots for structural blind spots."),
    ("data-state-architect", "pod-a", "architecture",
     "Audit domain types, state ownership, invariants, consistency, and schema gaps."),
    ("contract-boundary-auditor", "pod-a", "architecture",
     "Audit API, CLI, protocol, and trust boundaries, idempotency, and error contracts."),
    ("sota-paper-researcher", "pod-b", "research",
     "Search primary papers, specs, and algorithmic advances that leapfrog incremental fixes."),
    ("oss-prior-art-hunter", "pod-b", "research",
     "Search newest open-source repos, libraries, and shipped systems to adopt or adapt."),
    ("eval-oracle-scientist", "pod-b", "research",
     "Design falsifiable benchmarks, ground-truth oracles, and failure metrics missing today."),
    ("premise-attacker", "pod-c", "hybrid",
     "Challenge XY framing in the prompt and identify changes that remove the problem class."),
    ("adjacent-capability-scout", "pod-c", "hybrid",
     "Identify missing capabilities one step upstream or downstream that unlock the real goal."),
    ("workflow-ux-strategist", "pod-c", "hybrid",
     "Audit end-to-end human and agent workflow friction, feedback latency, and approval gates."),
    ("radical-simplifier", "pod-d", "architecture",
     "Apply the deletion test to collapse layers, wrappers, and state instead of adding glue."),
    ("scale-cost-analyst", "pod-d", "hybrid",
     "Stress-test throughput, tail latency, token or compute cost, caching, and IO bottlenecks."),
    ("failure-security-redteam", "pod-d", "architecture",
     "Probe adversarial inputs, race conditions, partial failures, credentials, and blast radius."),
)

EIGHT_IDS = (
    "seam-archaeologist", "data-state-architect",
    "sota-paper-researcher", "oss-prior-art-hunter",
    "premise-attacker", "adjacent-capability-scout",
    "radical-simplifier", "failure-security-redteam",
)

FOUR_IDS = (
    "seam-archaeologist", "sota-paper-researcher",
    "premise-attacker", "radical-simplifier",
)

SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
BRAND_SLUG = "deepmodebot"
BRAND_DISPLAY = "Deepmodebot"
BRAND_TRIGGER = "@deepmodebot"

CONCRETE_ANCHOR_RE = re.compile(
    r"(`[^`]+`"
    r"|#\d+\b"
    r"|\bPR\s*#?\d+\b"
    r"|\bspec\s*#?\d+\b"
    r"|[A-Za-z0-9_./\\-]+\.(?:py|ts|tsx|js|jsx|mjs|cjs|rs|go|java|cs|rb|php|md|json|ya?ml|toml|sql|sh|html|css)\b"
    r"|\b(?:src|lib|app|packages|plugins|scripts|docs|tests|evals)/[A-Za-z0-9_./-]+"
    r"|/[A-Za-z0-9_-]+/[A-Za-z0-9_/-]+"
    r"|\bp9[059]\b|\b\d+\s*(?:ms|s|mb|gb|x)\b)",
    re.I,
)
ENV_ANCHOR_RE = re.compile(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b")

TOURNAMENT_EXPLICIT_RE = re.compile(
    r"(\btournament\b"
    r"|\barena\s+debate\b"
    r"|\bdebate\s+(?:research|architecture|design|system|ideas|the\s+best)\b"
    r"|\b(?:architecture|architectural|research)\s+(?:gaps?|blind\s*spots?)\b"
    r"|\bblind\s*spots?\b"
    r"|\bwhat\s+(?:are\s+we|is\s+this\s+repo)\s+missing\b"
    r"|\bpropose\s+the\s+best\s+(?:system|architecture|research|design|approach)\b"
    r"|\bbest\s+(?:sota\s+)?research\s+ideas?\b"
    r"|\bcompete\b.*\b(?:ideas?|agents?|proposals?|designs?)\b"
    r"|\bsota\s+(?:approach|architecture|methods?|ideas?|research)\b)",
    re.I,
)

OPEN_AMBITION_RE = re.compile(
    r"(\brethink\b"
    r"|\bre-?architect\b"
    r"|\bfrom\s+first\s+principles\b"
    r"|\bnext[- ]gen(?:eration)?\b"
    r"|\b10x\b"
    r"|\bmake\s+(?:it|this|our\s+[\w\s-]+?)\s+(?:way\s+|much\s+)?(?:better|smarter|stronger|faster|modern)\b"
    r"|\bupgrade\s+(?:our|the)\s+(?:architecture|system|agent|ai|stack|pipeline)\b"
    r"|\bfix\s+(?:our|the)\s+(?:whole\s+)?(?:architecture|system|design)\b"
    r"|\bhow\s+should\s+we\s+(?:evolve|redesign|rethink|architect)\b"
    r"|\bwhat\s+should\s+we\s+build\s+next\b"
    r"|\bfigure\s+out\s+the\s+best\s+(?:way|system|architecture|direction)\b"
    r"|\bexplore\s+(?:research|architectural|design)\s+(?:directions|ideas|options)\b)",
    re.I,
)

CONCRETE_ACTION_VERB_RE = re.compile(
    r"\b(add|create|implement|wire|store|expose|render|show|support|track|remember|allow|parse|validate|export"
    r"|send|delete|remove|update|change|sort|filter|replace|move|configure|set\s+up|enable|disable|hide|limit|block|log"
    r"|notify|sync|import|download|upload|convert|converts|compute|enforce)\b",
    re.I,
)

CONCRETE_SURFACE_RE = re.compile(
    r"\b(page|endpoint|button|toggle|table|cli|flag|modal|form|route|webhook|webhooks|test|tests|file|column|header|footer"
    r"|sidebar|menu|dialog|banner|card|list|row|field|input|dropdown|tab|api|command|hook|job|queue|email|emails"
    r"|invoice|invoices|order|orders|cart|session|login|checkout|billing|settings|profile|user|users|token|cache"
    r"|report|reports|rule|rules|siem|subscription|subscriptions)\b",
    re.I,
)

GREENFIELD_LEAD_RE = re.compile(
    r"^\s*(?:please\s+)?(?:start|build|create|make)\s+(?:me\s+)?(?:a|an)\s+(?:[\w-]+\s+){0,3}?(?:app|tool|cli|service|site)\b",
    re.I,
)

TOURNAMENT_BUILD_RE = re.compile(
    r"(?:^|[,;.!?]\s*|\b(?:and|then)\s+)"
    r"(?:(?:please|also)\s+)*"
    r"(?:(?:i\s+(?:want|need)\s+you\s+to|you\s+should)\s+)?"
    r"(?:build|implement|code)\b",
    re.I,
)

TOURNAMENT_CHECKPOINT_RE = re.compile(
    r"(\b(?:let|allow)\s+me\s+(?:choose|pick|select|approve)\b"
    r"|\b(?:ask|consult)\s+me\s+(?:first|before)\b"
    r"|\b(?:wait|pause|stop)\s+(?:for|until|at|before)\b"
    r"|\b(?:approval|permission|consent|sign[- ]?off)\s+"
    r"(?:first|before\s+(?:you\s+)?(?:code|coding|implementation|implementing|building|editing))\b"
    r"|\b(?:do\s+not|don't|don’t|never)\s+(?:\w+\s+){0,2}(?:build|code|implement|modify|edit)\b"
    r"|\b(?:no|without)\s+(?:code|coding|implementation|production\s+(?:edits|changes))\b"
    r"|\b(?:choose|pick|select|approve)\s+(?:first|before\s+(?:coding|implementation|building))\b"
    r"|\bonly\s+(?:propose|research|plan|discuss)\b)",
    re.I,
)

GRILL_RE = re.compile(
    r"(\bgrill\s+(?:me|this|my|our|with\s+docs)\b"
    r"|\brecord\s+the\s+decisions\b"
    r"|\bstress[- ]test\s+(?:this|my|our|the)\s+(?:plan|idea|design|spec|approach)\b"
    r"|\bpoke\s+holes\s+in\b"
    r"|^\s*(?:here(?:'s|\s+is)\s+(?:my|our|a)\s+)?draft\s+(?:plan|design|spec)\b"
    r"|\b(?:review|check|critique)\s+(?:my|our|this)\s+draft\s+(?:plan|design|spec)\b)",
    re.I,
)


def count_concrete_anchors(prompt: str) -> int:
    hits = {m.group(0).lower() for m in CONCRETE_ANCHOR_RE.finditer(prompt)}
    hits.update(m.group(0) for m in ENV_ANCHOR_RE.finditer(prompt))
    clause_markers = len(
        re.findall(r"(?::\s+\w|,\s+(?:handle|store|show|create|add|mark|and\s+\w+\s+the)\b)", prompt, re.I)
    )
    return len(hits) + (1 if clause_markers >= 2 else 0)


def classify_prompt(prompt: str, has_factory: bool = False, empty_dir: bool = False) -> dict:
    text = " ".join(prompt.strip().split())
    lower = text.lower()
    anchors = count_concrete_anchors(text)
    brand_names = "|".join(
        sorted({re.escape(BRAND_SLUG.lower()), re.escape(BRAND_DISPLAY.lower())}, key=len, reverse=True)
    )
    brand_triggers = "|".join(
        sorted({re.escape(BRAND_TRIGGER.lower()), re.escape("@" + BRAND_SLUG.lower())}, key=len, reverse=True)
    )

    def out(mode: str, intent: str, vagueness: str, reason: str, checkpoint: bool = False) -> dict:
        if mode == "tournament":
            build_requested = bool(GREENFIELD_LEAD_RE.search(text) or TOURNAMENT_BUILD_RE.search(text))
            intent = "execute" if build_requested else "discover"
            checkpoint = not build_requested or bool(TOURNAMENT_CHECKPOINT_RE.search(text))
        return {
            "mode": mode,
            "intent": intent,
            "vagueness": vagueness,
            "checkpoint_before_code": checkpoint,
            "anchors": anchors,
            "reason": reason,
        }

    if (
        re.search(r"^\s*review\s+(?:pr\s*#?\d+|#\d+|https?://\S+/pull/\d+)\b", lower)
        or re.search(r"^\s*(?:pr\s*#?\d+|https?://\S+/pull/\d+)\s*$", lower)
        or re.search(r"\breview\s+since\s+\S+|\breview\s+my\s+branch\b", lower)
    ):
        return out("pr-review", "audit", "low", "Explicit PR or branch review request.")

    if (
        re.search(r"\b(?:land|merge|finish)\b.*\b(?:on\s+your\s+own|no\s+human|bots\s+talk\s+it\s+out)\b", lower)
        or re.search(r"^\s*(?:land|merge|finish)\s+pr\s*#?\d+\b", lower)
        or (re.search(r"\bpr\s*#?\d+\b", lower) and re.search(r"\bland\s+it\b", lower))
    ):
        return out("pr-conversation", "execute", "low", "Autonomous PR landing request.")

    if re.search(
        r"\b(?:babysit|check\s+on)\s+pr\b|\bget\s+pr\s*#?\d+\s+green\b|\bpr\s*#?\d+\b.*\b(?:until\s+it'?s\s+green|when\s+it'?s\s+green)\b",
        lower,
    ):
        return out("babysit", "execute", "low", "PR babysitting and check resolution request.")

    if re.search(rf"(?<![\w.~/-])(?:{brand_triggers})\s+implement\b|\bbots\s+(?:plan|discuss|implement)\s+this\s+issue\b", lower):
        return out("issue-conversation", "execute", "low", "Bot issue conversation request.")

    if re.search(
        rf"\binstall\s+(?:{brand_names})\s+on\s+my\s+repos\b|\brun\s+the\s+bots\s+on\s+their\s+own\b"
        r"|\bai\s+review\s+on\s+my\s+own\s+subscription\b|\b(?:start|stop|opt\b.*\bout\s+of)\s+the\s+bots\b",
        lower,
    ):
        return out("github-app", "execute", "low", "GitHub App bot setup or control request.")

    if re.search(
        r"\b(?:set\b.*\bup|publish\b.*)\s+for\s+contributors\b|\bmake\s+(?:some\s+)?issues\s+(?:people|helpers)\s+can\s+pick\s+up\b",
        lower,
    ):
        return out("project-brief", "execute", "low", "Maintainer contributor-onboarding request.")

    if re.search(r"\bwhat\s+can\s+i\s+work\s+on\b|\bcontribute\s+to\b|\bhelp\s+(?:out\s+)?on\s+(?:this|the)\s+(?:repo|project)\b", lower):
        return out("contribute", "execute", "low", "Contributor task-picking request.")

    if (
        re.search(
            r"\brun\s+the\s+factory\b|\bwork\s+the\s+issue\s+queue\b|\bturn\s+issues\s+into\s+prs\b|\bset\s+up\s+a\s+software\s+factory\b",
            lower,
        )
        or (has_factory and "factory" in lower)
        or re.search(
            r"\b(?:drive|work)\s+the\s+(?:board|backlog)\b|\brun\s+this\s+project\s+autonomously\b"
            r"|\bkeep\s+going\s+on\s+the\s+roadmap\b|\bautopilot\b|\bstack\s+them,\s+don'?t\s+ship\b|\bbuild\s+the\s+stack,\s+i'?ll\s+land\s+it\b",
            lower,
        )
    ):
        return out("work-a-queue", "execute", "low", "Queue, factory, or backlog execution request.")

    if re.search(rf"\bset\s+up\s+(?:{brand_names})\b|\bconfigure\s+the\s+(?:tracker|labels)\b|\badd\s+a\s+glossary\s+and\s+adrs\b", lower):
        return out("setup", "execute", "low", "Repository tracker and conventions setup request.")

    if re.search(r"\btriage\b|\bwhat\s+needs\s+my\s+attention\b|\bis\s+#\d+\s+ready\s+for\s+an\s+agent\b|\bmove\s+#\d+\s+to\s+agent-ready\b", lower):
        return out("triage", "execute", "low", "Issue or PR triage request.")

    if GRILL_RE.search(text):
        return out("grill", "stress-test", "medium", "Plan or design stress-test request.")

    if re.search(r"\b(?:write|draft)\s+(?:the|a)\s+spec\b|\bturn\s+this\s+into\s+a\s+spec\b|\bspec\s+it\s+up\b", lower):
        return out("spec", "execute", "low", "Specification authoring request.")

    if re.search(r"\bbreak\s+this\s+into\s+tickets\b|\bsplit\s+the\s+spec\s+into\s+issues\b|\bmake\s+tickets\s+for\s+this\b", lower):
        return out("tickets", "execute", "low", "Ticket breakdown request.")

    if re.search(r"\b(?:implement|build)\s+(?:the\s+)?spec(?:\s*#?\d+)?\b|\bbuild\s+all\s+the\s+tickets\s+on\s+one\s+branch\b", lower):
        return out("phased-build", "execute", "low", "Spec implementation across tickets.")

    if re.search(r"\b(?:write|author|create|edit)\s+(?:me\s+)?a\s+skill\b|\bedit\s+skill\.md\b", lower):
        return out("authoring-a-skill", "execute", "low", "Skill authoring request.")

    if re.search(r"\b(?:write|edit|update)\s+(?:agents\.md|claude\.md|a\s+rule\s+file|a?\s*subagent\s+brief)\b", lower):
        return out("writing-for-agents", "execute", "low", "Agent instruction or brief authoring request.")

    if re.search(r"\b(?:write|improve)\s+your\s+own\s+(?:prompt|skill|goal|loop)\b|\bmake\s+yourself\s+able\s+to\b", lower):
        return out("self-authoring", "execute", "low", "Self-authoring workflow request.")

    if re.search(r"\bwhat\s+do\s+we\s+call\s+this\b|\badd\b.*\bto\s+the\s+glossary\b|\bwrite\s+an\s+adr\b", lower):
        return out("domain-model", "execute", "low", "Glossary or ADR domain-modeling request.")

    if re.search(r"\bresearch\b.*\bwrite\s+it\s+up\b|\bgather\s+the\s+docs\s+on\b", lower):
        return out("research", "question", "low", "Cited repository research note request.")

    if re.search(rf"\bwhich\s+flow\s+fits\b|\bwhat'?s\s+the\s+process\s+for\b|\bexplain\s+the\s+(?:{brand_names})\s+workflow\b", lower):
        return out("flows", "question", "low", "Workflow explanation request.")

    if re.search(r"\btdd\b|\btest-first\b|\bred-green-refactor\b|\bwrite\s+integration\s+tests\b", lower):
        return out("tdd", "execute", "low", "Test-first build or integration test request.")

    if re.search(
        r"\breview\s+the\s+architecture\b|\bwhere\s+should\s+we\s+refactor\b"
        r"|\bfind\s+deepening\s+opportunities\b|\bshallow\s+modules?\b|\bmake\s+the\s+codebase\s+easier\s+for\s+agents\b",
        lower,
    ):
        return out("architecture-review", "audit", "low", "Codebase structural refactoring scan.")

    if re.search(r"\bretro(?:spective)?\b|\bwhat\s+should\s+we\s+change\s+after\s+this\s+session\b", lower):
        return out("retro", "audit", "low", "Session retrospective request.")

    if re.search(r"\bmake\s+me\s+a\s+setup\s+script\b|\bwalk\s+me\s+through\s+setting\s+up\b|\bsteps\s+only\s+a\s+human\s+can\s+do\b", lower):
        return out("wizard", "execute", "low", "Guided human-step wizard request.")

    if re.search(r"\bteach\s+me\b.*\bover\s+the\s+next\b|\bmake\s+me\s+a\s+course\b|\bcontinue\s+my\s+course\b", lower):
        return out("course", "question", "low", "Multi-session learning course request.")

    if re.search(r"\bwrite\s+questions\s+for\s+the\s+client\b|\bmake\s+a\s+questionnaire\b", lower):
        return out("questionnaire", "question", "low", "Stakeholder questionnaire request.")

    if re.search(r"\bwait,\s+what\??|\bi'?m\s+lost\b|\bsay\s+that\s+again\s+simply\b|\btoo\s+dense\b", lower):
        return out("re-explain", "question", "low", "Plain-language re-explanation request.")

    if re.search(
        r"\bhand\s+this\s+off\b|\bwrite\s+a\s+handoff\b|\bcontinue\s+in\s+a\s+new\s+session\b|\bstart\s+a\s+background\s+agent\s+on\s+the\s+rest\b",
        lower,
    ):
        return out("handoff", "execute", "low", "Session handoff document request.")

    if re.search(r"\bblock\s+dangerous\s+git\b|\b(?:add|set\s+up)\s+git\s+safety\s+hooks\b|\bstop\s+the\s+agent\s+from\s+force-pushing\b", lower):
        return out("git-guardrails", "execute", "low", "Git safety hook setup request.")

    if re.search(
        r"\b(?:add|set\s+up)\s+pre-commit\s+hooks\b|\bset\s+up\s+(?:husky|lint-staged|lefthook|pre-commit)\b|\bformat\s+and\s+typecheck\s+on\s+commit\b",
        lower,
    ):
        return out("pre-commit", "execute", "low", "Pre-commit hook setup request.")

    if re.search(
        r"\bbe\s+my\s+chief\s+of\s+staff\b|\bgoing\s+to\s+bed\b|\bkeep\s+going\s+until\b|\bloop\s+until\b"
        r"|\bkeep\s+pushing\s+(?:it|this\s+goal)\s+forward\s+across\s+sessions\b|\bown\s+this\s+(?:goal|migration)\b",
        lower,
    ):
        return out("run-a-goal", "execute", "low", "Sustained autonomous goal execution request.")

    if re.search(r"\b(?:scrape|pull|archive)\b.*\b(?:page|video|channel|playlist)\b|\bget\s+his\s+diagram\b", lower):
        return out("scrape", "execute", "low", "Media or page archive request.")

    if re.search(r"\bwayfinder\b|\bchart\s+the\s+way\b|\bplan\s+this\s+migration\s+before\s+anyone\s+builds\b", lower):
        return out("wayfinder", "chart", "high", "Multi-session foggy route mapping request.")

    if re.search(
        r"\b(?:rename|extract|inline|dedupe)\b|\b(?:port|rewrite|migrate)\b.*\bto\s+another\s+language\b|\b(?:port|rewrite)\b.*\bpreserving\s+behavior\b",
        lower,
    ):
        return out("refactoring", "execute", "low", "Behavior-preserving structural change.")

    if re.search(r"\bsecurity-audit\b|\baudit\s+every\s+pr\b|\badd\s+a\s+security\s+gate\b|\bsecurity\s+audit\s+of\b", lower):
        return out("security-audit", "audit", "low", "Security audit request.")

    if re.search(r"\brun\s+pr-agent\b|\bwith\s+pr-agent\b", lower):
        return out("pr-agent", "audit", "low", "PR-Agent review pass request.")

    if re.search(r"\bis\s+there\s+a\s+(?:library|project|example)\s+for\b|\bfind\s+something\s+we\s+can\s+(?:fork|copy)\b", lower):
        return out("prior-art", "question", "low", "Prior-art search request.")

    if re.search(r"\binner[- ]loop\b|\b(?:ai\s+)?code\s+slop\b|\bblock\s+agent\s+slop\b", lower):
        return out("inner-loop", "audit" if re.search(r"\baudit\b", lower) else "execute", "low",
                   "Inner-loop gate hardening or audit request.")

    if re.search(r"\bwhat\s+stack\b|\bpick\s+(?:a|the)\s+stack\b", lower) and not GREENFIELD_LEAD_RE.search(text):
        return out("deep-stack", "question", "low", "Stack choice only, no build requested.")

    if re.search(
        r"\bend[- ]to[- ]end\b.*\b(?:product|project|app)\b|\b(?:product|project|app)\b.*\bend[- ]to[- ]end\b"
        r"|\bdon'?t\s+stop\s+at\s+(?:a|the)\s+(?:first\s+)?(?:slice|mvp)\b|\bidea\s+into\s+a\s+complete\b",
        lower,
    ):
        return out("end-to-end", "execute", "low", "Full-scope product delivery across every slice.")

    if TOURNAMENT_EXPLICIT_RE.search(text):
        vagueness = "high" if anchors == 0 else "medium"
        return out(
            "tournament",
            "discover",
            vagueness,
            "Prompt asks for tournament competition or architecture and research gap discovery.",
            checkpoint=True,
        )

    if OPEN_AMBITION_RE.search(text) and anchors <= 1:
        return out(
            "tournament",
            "discover",
            "high",
            "High-level open architectural or research ambition without concrete implementation anchors.",
            checkpoint=True,
        )

    if re.search(r"^(?:how|where|why|what|are\s+we\s+sure|explain\s+(?:how|why|the))\b", lower) and not re.search(
        r"\b(?:fix|build|implement|add|change|rethink|propose|make|create|remove|delete|update)\b", lower
    ):
        return out("investigation", "question", "low", "Read-only codebase question.")

    if re.search(r"\b(?:\d+(?:\.\d+)?x\s+slower|got\s+slower|slowness|p9[59]\s+went\s+from|latency\s+regression)\b", lower):
        return out("perf-issue", "execute", "low", "Measured performance regression.")

    gf_match = GREENFIELD_LEAD_RE.search(text)
    if gf_match and (empty_dir or re.search(r"\bnew\s+(?:app|tool|cli|service|site)\b", lower)):
        remainder = text[gf_match.end():].strip(" .,:;-")
        has_behavior = bool(
            remainder
            and (
                count_concrete_anchors(remainder) >= 1
                or CONCRETE_ACTION_VERB_RE.search(remainder)
                or re.search(r"\bthat\s+\w+|\bfor\s+\w+ing\b", remainder, re.I)
            )
        )
        if has_behavior:
            return out("prior-art", "execute", "low", "Greenfield app with concrete behaviors starts at prior-art.")
        return out(
            "tournament",
            "execute",
            "high",
            "Greenfield request has no concrete behaviors yet, so explore competing system shapes first.",
            checkpoint=False,
        )

    if re.search(
        r"\b(?:find\s+out\s+why\s+and\s+fix|wrong\s+total|is\s+wrong|typo|bug|crash(?:es|ed|ing)?|fail(?:s|ed|ing)"
        r"|throws?\b|broken|regression|error\b|500\b|redirect\s+loop|deadlock|race\s+condition|should\s+be)\b",
        lower,
    ) or (re.search(r"\bfix\b", lower) and not re.search(r"\bfix\s+(?:everything|it\s+all)\b", lower)):
        return out("bug-fix", "execute", "low", "Concrete defect reproduction and fix.")

    if anchors >= 1 or (CONCRETE_ACTION_VERB_RE.search(text) and CONCRETE_SURFACE_RE.search(text)):
        return out("feature", "execute", "low", "Concrete feature request with identifiable target behavior.")

    if CONCRETE_ACTION_VERB_RE.search(text):
        return out(
            "grill",
            "stress-test",
            "medium",
            "Goal names an action without concrete UI or API details, so resolve decisions before coding.",
            checkpoint=False,
        )

    return out(
        "tournament",
        "discover",
        "high",
        "Underspecified goal with no concrete file, symbol, or behavioral anchor.",
        checkpoint=True,
    )


def reject_unsafe_root(root_arg: Path) -> Path:
    if root_arg.is_symlink():
        raise SystemExit(f"project root cannot be a symlink: {root_arg}")
    resolved = root_arg.resolve()
    if not resolved.is_dir():
        raise SystemExit(f"project root does not exist: {resolved}")
    if resolved.parent == resolved:
        raise SystemExit(f"refusing filesystem root as project root: {resolved}")
    forbidden = {Path.home().resolve(), Path(tempfile.gettempdir()).resolve()}
    for extra in ("/tmp", "/var/tmp", "/private/tmp"):
        p = Path(extra)
        if p.exists():
            forbidden.add(p.resolve())
    if resolved in forbidden:
        raise SystemExit(f"refusing home or system temp directory as project root: {resolved}")
    return resolved


def ensure_contained(target: Path, root: Path) -> Path:
    resolved_root = reject_unsafe_root(root)
    if target.is_symlink():
        raise SystemExit(f"refusing symlink path: {target}")
    resolved_target = target.resolve()
    try:
        rel_parts = resolved_target.relative_to(resolved_root).parts
    except ValueError as err:
        raise SystemExit(f"path {resolved_target} escapes project root {resolved_root}") from err
    probe = resolved_root
    for part in rel_parts:
        probe = probe / part
        if probe.is_symlink():
            raise SystemExit(f"refusing symlink component inside root: {probe}")
    return resolved_target


def atomic_write_text(target: Path, content: str, root: Path) -> None:
    safe_target = ensure_contained(target, root)
    safe_parent = ensure_contained(safe_target.parent, root)
    safe_parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{safe_target.name}.", suffix=".tmp", dir=str(safe_parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        if safe_target.is_symlink():
            raise SystemExit(f"refusing symlink target: {safe_target}")
        deadline = time.monotonic() + 2.0
        while True:
            try:
                os.replace(tmp_path, safe_target)
                break
            except PermissionError:
                if os.name != "nt" or time.monotonic() >= deadline:
                    raise
                time.sleep(0.02)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp_path.unlink()
        raise


def ensure_scratch_gitignore(root: Path) -> Path:
    scratch = ensure_contained(root / ".scratch", root)
    scratch.mkdir(parents=True, exist_ok=True)
    gitignore = ensure_contained(scratch / ".gitignore", root)
    if not gitignore.exists():
        atomic_write_text(gitignore, "*\n", root)
    return scratch


class BracketLock:
    def __init__(self, lock_path: Path, wait_seconds: float = 10.0) -> None:
        self.lock_path = lock_path
        self.wait_seconds = wait_seconds
        self.fh = None

    def __enter__(self):
        if self.lock_path.is_symlink():
            raise SystemExit(f"refusing symlink lockfile: {self.lock_path}")
        self.fh = open(self.lock_path, "a+", encoding="utf-8")
        deadline = time.monotonic() + self.wait_seconds
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    self.fh.seek(0)
                    msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError:
                if time.monotonic() >= deadline:
                    self._close()
                    raise SystemExit(f"timed out waiting for tournament lock: {self.lock_path}") from None
                time.sleep(0.02)

    def _close(self) -> None:
        if self.fh is not None:
            with contextlib.suppress(OSError):
                if os.name == "nt":
                    import msvcrt

                    self.fh.seek(0)
                    msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
            self.fh.close()
            self.fh = None

    def __exit__(self, *exc) -> None:
        self._close()


def select_lenses(count: int) -> list[dict]:
    if count == 12:
        chosen = list(LENSES)
    elif count == 8:
        chosen = [row for row in LENSES if row[0] in EIGHT_IDS]
    elif count == 4:
        chosen = [row for row in LENSES if row[0] in FOUR_IDS]
    else:
        raise SystemExit("--entrants must be 12, 8, or 4")
    return [
        {"id": eid, "pod": pod, "default_gap_kind": kind, "mandate": mandate, "status": "active", "pitch": None, "grafts": []}
        for eid, pod, kind, mandate in chosen
    ]


def build_matches(entrants: list[dict]) -> list[dict]:
    n = len(entrants)
    ids = [e["id"] for e in entrants]
    if n == 12:
        return [
            {"id": "pod-a", "round": 1, "label": "Pod A (Architecture and boundaries)", "entrants": ids[0:3], "next_match": "sf-1", "rebuttals": [], "result": None},
            {"id": "pod-b", "round": 1, "label": "Pod B (SOTA research and prior art)", "entrants": ids[3:6], "next_match": "sf-1", "rebuttals": [], "result": None},
            {"id": "pod-c", "round": 1, "label": "Pod C (Premise and product strategy)", "entrants": ids[6:9], "next_match": "sf-2", "rebuttals": [], "result": None},
            {"id": "pod-d", "round": 1, "label": "Pod D (Subtraction, scale, and red-team)", "entrants": ids[9:12], "next_match": "sf-2", "rebuttals": [], "result": None},
            {"id": "sf-1", "round": 2, "label": "Semifinal 1 (Architecture vs research)", "entrants": [], "next_match": "final", "rebuttals": [], "result": None},
            {"id": "sf-2", "round": 2, "label": "Semifinal 2 (Premise vs resilience)", "entrants": [], "next_match": "final", "rebuttals": [], "result": None},
            {"id": "final", "round": 3, "label": "Championship final", "entrants": [], "next_match": None, "rebuttals": [], "result": None},
        ]
    if n == 8:
        return [
            {"id": "qf-1", "round": 1, "label": "Quarterfinal 1", "entrants": ids[0:2], "next_match": "sf-1", "rebuttals": [], "result": None},
            {"id": "qf-2", "round": 1, "label": "Quarterfinal 2", "entrants": ids[2:4], "next_match": "sf-1", "rebuttals": [], "result": None},
            {"id": "qf-3", "round": 1, "label": "Quarterfinal 3", "entrants": ids[4:6], "next_match": "sf-2", "rebuttals": [], "result": None},
            {"id": "qf-4", "round": 1, "label": "Quarterfinal 4", "entrants": ids[6:8], "next_match": "sf-2", "rebuttals": [], "result": None},
            {"id": "sf-1", "round": 2, "label": "Semifinal 1", "entrants": [], "next_match": "final", "rebuttals": [], "result": None},
            {"id": "sf-2", "round": 2, "label": "Semifinal 2", "entrants": [], "next_match": "final", "rebuttals": [], "result": None},
            {"id": "final", "round": 3, "label": "Championship final", "entrants": [], "next_match": None, "rebuttals": [], "result": None},
        ]
    return [
        {"id": "sf-1", "round": 1, "label": "Semifinal 1", "entrants": ids[0:2], "next_match": "final", "rebuttals": [], "result": None},
        {"id": "sf-2", "round": 1, "label": "Semifinal 2", "entrants": ids[2:4], "next_match": "final", "rebuttals": [], "result": None},
        {"id": "final", "round": 2, "label": "Championship final", "entrants": [], "next_match": None, "rebuttals": [], "result": None},
    ]


def validate_https_url(text: str) -> dict:
    parsed = urllib.parse.urlsplit(text)
    if parsed.scheme != "https" or not parsed.hostname or re.search(r"\s", text):
        raise SystemExit(f"URL receipt must be an https:// URL with a public host: {text!r}")
    host = parsed.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise SystemExit(f"URL receipt cannot target local or internal host: {host}")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and not ip.is_global:
        raise SystemExit(f"URL receipt cannot target non-public IP address: {host}")
    return {"kind": "url", "raw": text}


def validate_receipt(raw: str, root: Path) -> dict:
    text = raw.strip()
    if not text:
        raise SystemExit("receipt cannot be empty")
    if text.startswith("http://"):
        raise SystemExit("URL receipt must use https://, not http://")
    if text.startswith("https://"):
        return validate_https_url(text)
    if text.startswith("cmd:"):
        body = text[4:].strip()
        if "->" not in body:
            raise SystemExit("probe receipt must use 'cmd:<command> -> <observed output>'")
        cmd_part, out_part = [p.strip() for p in body.split("->", 1)]
        if not cmd_part or not out_part:
            raise SystemExit("probe receipt needs both command and observed output")
        return {"kind": "probe", "raw": text}
    match = re.match(r"^(.+?):(\d+)(?:-(\d+))?$", text)
    if not match:
        raise SystemExit(
            f"invalid receipt {text!r}: expected '<repo-rel-path>:<line>', 'https://...', or 'cmd:<cmd> -> <out>'"
        )
    rel_path, start_s, end_s = match.group(1), match.group(2), match.group(3)
    rel_obj = Path(rel_path)
    if rel_path.startswith(("/", "\\")) or rel_obj.is_absolute() or rel_obj.drive or ".." in rel_obj.parts:
        raise SystemExit(f"repo receipt must be a relative path inside root without '..': {rel_path}")
    candidate = ensure_contained(root / rel_obj, root)
    if not candidate.is_file():
        raise SystemExit(f"receipt file does not exist inside root: {rel_path}")
    line_count = max(1, len(candidate.read_bytes().splitlines()))
    start = int(start_s)
    end = int(end_s) if end_s else start
    if start < 1 or end < start or end > line_count:
        raise SystemExit(f"receipt line {start}-{end} out of range for {rel_path} ({line_count} lines)")
    return {"kind": "repo", "raw": text}


def load_state(tdir: Path) -> tuple[Path, Path, dict]:
    if tdir.is_symlink():
        raise SystemExit(f"refusing symlink tournament directory: {tdir}")
    resolved_dir = tdir.resolve()
    raw_state_path = resolved_dir / "bracket.json"
    if raw_state_path.is_symlink() or not raw_state_path.is_file():
        raise SystemExit(f"missing or unsafe tournament state: {raw_state_path}")
    state = json.loads(raw_state_path.read_text(encoding="utf-8"))
    slug = str(state.get("slug", ""))
    if not SLUG_RE.fullmatch(slug):
        raise SystemExit(f"invalid slug in tournament state: {slug!r}")
    root = reject_unsafe_root(Path(str(state.get("root", ""))))
    expected = ensure_contained(root / ".scratch" / "tournaments" / slug / "bracket.json", root)
    if raw_state_path != expected:
        raise SystemExit(f"tournament state {raw_state_path} does not match contained path {expected}")
    return expected, root, state


def save_state(state_path: Path, root: Path, state: dict) -> None:
    atomic_write_text(state_path, json.dumps(state, indent=2) + "\n", root)


@contextlib.contextmanager
def state_transaction(tdir_arg: str):
    tdir = Path(tdir_arg)
    if tdir.is_symlink():
        raise SystemExit(f"refusing symlink tournament directory: {tdir}")
    resolved_dir = tdir.resolve()
    if (
        not SLUG_RE.fullmatch(resolved_dir.name)
        or resolved_dir.parent.name != "tournaments"
        or resolved_dir.parent.parent.name != ".scratch"
    ):
        raise SystemExit(f"tournament directory must be <root>/.scratch/tournaments/<slug>: {resolved_dir}")
    inferred_root = reject_unsafe_root(resolved_dir.parent.parent.parent)
    lock_path = ensure_contained(resolved_dir / "bracket.lock", inferred_root)
    with BracketLock(lock_path):
        locked_path, locked_root, locked_state = load_state(tdir)
        yield locked_path, locked_root, locked_state
        save_state(locked_path, locked_root, locked_state)


def require_nonempty(value: str, flag: str) -> str:
    cleaned = (value or "").lstrip("\ufeff").strip()
    if not cleaned:
        raise SystemExit(f"{flag} must be non-empty")
    return cleaned


def read_prompt_arg(inline_value: str, use_stdin: bool, flag: str) -> str:
    raw = sys.stdin.read() if (use_stdin or inline_value == "-") else inline_value
    return require_nonempty(raw, flag)


def find_entrant(state: dict, entrant_id: str) -> dict:
    for entrant in state["entrants"]:
        if entrant["id"] == entrant_id:
            return entrant
    raise SystemExit(f"unknown entrant: {entrant_id}")


def find_match(state: dict, match_id: str) -> dict:
    for match in state["matches"]:
        if match["id"] == match_id:
            return match
    raise SystemExit(f"unknown match: {match_id}")


def unfinished_feeders(state: dict, match_id: str) -> list[str]:
    return [m["id"] for m in state["matches"] if m["next_match"] == match_id and m["result"] is None]


def propagate_forfeits(state: dict) -> None:
    changed = True
    while changed:
        changed = False
        for match in state["matches"]:
            if match["result"] is not None or unfinished_feeders(state, match["id"]):
                continue
            active = [eid for eid in match["entrants"] if find_entrant(state, eid)["status"] == "active"]
            if active:
                continue
            has_feeders = any(m["next_match"] == match["id"] for m in state["matches"])
            if (match["entrants"] or has_feeders) and all(
                find_entrant(state, eid)["status"] == "dropout" for eid in match["entrants"]
            ):
                match["result"] = {
                    "winner": None,
                    "losers": [],
                    "forfeit": True,
                    "judge_model": "forfeit",
                    "verified_receipt": None,
                    "rationale": "All entrants in match dropped out.",
                    "graft": None,
                }
                changed = True


def match_is_ready(state: dict, match: dict) -> bool:
    if match["result"] is not None or unfinished_feeders(state, match["id"]):
        return False
    active = [eid for eid in match["entrants"] if find_entrant(state, eid)["status"] == "active"]
    return len(active) >= 1 and all(find_entrant(state, eid)["pitch"] is not None for eid in active)


def fallback_runner_up(state: dict, champion_id: str) -> str | None:
    for match in reversed(state["matches"]):
        res = match["result"]
        if not res or res.get("forfeit"):
            continue
        for lid in res["losers"]:
            if lid != champion_id and find_entrant(state, lid)["pitch"] is not None:
                return lid
    return None


def detect_repo_signals(root_arg: str) -> tuple[bool, bool]:
    if not root_arg:
        return False, False
    rpath = Path(root_arg).resolve()
    if not rpath.is_dir():
        return False, False
    has_factory = (rpath / "factory.json").is_file()
    entries = [p.name for p in rpath.iterdir() if p.name not in {".scratch", ".DS_Store"}]
    empty_dir = len(entries) == 0
    return has_factory, empty_dir


def cmd_route(args: argparse.Namespace) -> int:
    prompt = read_prompt_arg(args.prompt, args.stdin, "prompt")
    auto_factory, auto_empty = detect_repo_signals(args.root)
    verdict = classify_prompt(
        prompt,
        has_factory=args.has_factory or auto_factory,
        empty_dir=args.empty_dir or auto_empty,
    )
    if args.json:
        print(json.dumps(verdict, indent=2))
    else:
        gate = "checkpoint" if verdict["checkpoint_before_code"] else "direct"
        print(f"mode={verdict['mode']} intent={verdict['intent']} vagueness={verdict['vagueness']} gate={gate}")
        print(f"reason: {verdict['reason']}")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    root = reject_unsafe_root(Path(args.root))
    if not SLUG_RE.fullmatch(args.slug):
        raise SystemExit("--slug must be kebab-case (a-z0-9 and '-')")
    prompt = read_prompt_arg(args.prompt, args.prompt_stdin, "--prompt")
    scratch = ensure_scratch_gitignore(root)
    tdir = ensure_contained(scratch / "tournaments" / args.slug, root)
    state_path = ensure_contained(tdir / "bracket.json", root)
    tdir.mkdir(parents=True, exist_ok=True)
    lock_path = ensure_contained(tdir / "bracket.lock", root)
    with BracketLock(lock_path):
        if state_path.exists() and not args.force:
            raise SystemExit(f"tournament already exists at {state_path} (pass --force to overwrite)")
        entrants = select_lenses(args.entrants)
        state = {
            "slug": args.slug,
            "root": str(root),
            "prompt": prompt,
            "entrant_count": len(entrants),
            "entrants": entrants,
            "matches": build_matches(entrants),
            "champion": None,
            "runner_up": None,
        }
        save_state(state_path, root, state)
    payload = {"dir": str(tdir), "entrant_count": len(entrants), "entrants": entrants, "matches": state["matches"]}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"initialized {len(entrants)}-entrant tournament at {tdir}")
    return 0


def cmd_pitch(args: argparse.Namespace) -> int:
    title = require_nonempty(args.title, "--title")
    thesis = require_nonempty(args.thesis, "--thesis")
    with state_transaction(args.dir) as (_, root, state):
        entrant = find_entrant(state, args.entrant)
        if entrant["status"] != "active":
            raise SystemExit(f"entrant {args.entrant} is {entrant['status']}")
        if any(match["result"] is not None and args.entrant in match["entrants"] for match in state["matches"]):
            raise SystemExit(f"entrant {args.entrant} has an already judged match; its pitch is frozen")
        receipts = [validate_receipt(r, root) for r in args.receipt]
        entrant["pitch"] = {
            "title": title,
            "thesis": thesis,
            "gap_kind": args.gap_kind,
            "receipts": receipts,
            "counter_risk": (args.counter_risk or "").strip(),
        }
    noun = "receipt" if len(receipts) == 1 else "receipts"
    print(f"recorded pitch for {args.entrant} ({len(receipts)} submitted {noun})")
    return 0


def cmd_rebut(args: argparse.Namespace) -> int:
    attack = require_nonempty(args.attack, "--attack")
    with state_transaction(args.dir) as (_, root, state):
        match = find_match(state, args.match)
        if match["result"] is not None:
            raise SystemExit(f"match {args.match} is already judged")
        pending = unfinished_feeders(state, args.match)
        if pending:
            raise SystemExit(f"match {args.match} waits on feeder matches: {', '.join(pending)}")
        for eid in (args.entrant, args.target):
            if eid not in match["entrants"]:
                raise SystemExit(f"{eid} is not in match {args.match}")
            ent = find_entrant(state, eid)
            if ent["status"] != "active":
                raise SystemExit(f"entrant {eid} is {ent['status']} and cannot participate in rebuttals")
            if ent["pitch"] is None:
                raise SystemExit(f"entrant {eid} has not submitted a pitch yet")
        if args.entrant == args.target:
            raise SystemExit("--entrant and --target must differ")
        receipt = validate_receipt(args.receipt, root)
        match["rebuttals"].append({
            "entrant": args.entrant,
            "target": args.target,
            "attack": attack,
            "receipt": receipt,
        })
    print(f"recorded rebuttal in {args.match}: {args.entrant} against {args.target}")
    return 0


def cmd_dropout(args: argparse.Namespace) -> int:
    reason = require_nonempty(args.reason, "--reason")
    with state_transaction(args.dir) as (_, _, state):
        if state["champion"] == args.entrant:
            raise SystemExit(f"cannot mark crowned champion {args.entrant} as dropout")
        entrant = find_entrant(state, args.entrant)
        if entrant["status"] != "active":
            raise SystemExit(f"entrant {args.entrant} is already {entrant['status']}")
        entrant["status"] = "dropout"
        entrant["dropout_reason"] = reason
        propagate_forfeits(state)
    print(f"marked {args.entrant} as dropout")
    return 0


def cmd_judge(args: argparse.Namespace) -> int:
    judge_model = require_nonempty(args.judge_model, "--judge-model")
    rationale = require_nonempty(args.rationale, "--rationale")
    with state_transaction(args.dir) as (_, root, state):
        match = find_match(state, args.match)
        if match["result"] is not None:
            raise SystemExit(f"match {args.match} is already judged")
        pending = unfinished_feeders(state, args.match)
        if pending:
            raise SystemExit(f"match {args.match} waits on feeder matches: {', '.join(pending)}")
        active = [eid for eid in match["entrants"] if find_entrant(state, eid)["status"] == "active"]
        if len(active) < 1:
            raise SystemExit(f"match {args.match} has no active entrants")
        unpitched = [eid for eid in active if find_entrant(state, eid)["pitch"] is None]
        if unpitched:
            raise SystemExit(f"match {args.match} has entrants without pitches: {', '.join(unpitched)}")
        if args.winner not in active:
            raise SystemExit(f"winner {args.winner} is not an active entrant in {args.match}")
        verified = validate_receipt(args.verified_receipt, root)
        losers = [eid for eid in active if eid != args.winner]
        graft_record = None
        if args.graft or args.graft_from:
            if not (args.graft and args.graft_from):
                raise SystemExit("--graft and --graft-from must be provided together")
            graft_text = require_nonempty(args.graft, "--graft")
            if args.graft_from not in losers:
                raise SystemExit(f"--graft-from {args.graft_from} is not an eliminated opponent in {args.match}")
            graft_record = {"from": args.graft_from, "match": args.match, "insight": graft_text}
            find_entrant(state, args.winner)["grafts"].append(graft_record)

        for lid in losers:
            find_entrant(state, lid)["status"] = "eliminated"

        match["result"] = {
            "winner": args.winner,
            "losers": losers,
            "judge_model": judge_model,
            "verified_receipt": verified,
            "rationale": rationale,
            "graft": graft_record,
        }
        if match["next_match"]:
            nxt = find_match(state, match["next_match"])
            if args.winner not in nxt["entrants"]:
                nxt["entrants"].append(args.winner)
        else:
            state["champion"] = args.winner
            state["runner_up"] = losers[0] if losers else fallback_runner_up(state, args.winner)

    print(f"match {args.match}: winner={args.winner} (advanced to {match['next_match'] or 'champion'})")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    _, _, state = load_state(Path(args.dir))
    pending_pitches = [e["id"] for e in state["entrants"] if e["status"] == "active" and e["pitch"] is None]
    ready_matches = [m["id"] for m in state["matches"] if match_is_ready(state, m)]
    summary = {
        "slug": state["slug"],
        "entrant_count": state["entrant_count"],
        "pending_pitches": pending_pitches,
        "ready_matches": ready_matches,
        "champion": state["champion"],
        "runner_up": state["runner_up"],
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(
            f"slug={summary['slug']} champion={summary['champion']} "
            f"pending_pitches={len(pending_pitches)} ready_matches={ready_matches}"
        )
    return 0


def render_markdown(state: dict) -> str:
    if not state["champion"]:
        raise SystemExit("cannot render proposal before Championship final is judged")
    champ = find_entrant(state, state["champion"])
    cp = champ["pitch"]
    lines = [
        f"# Tournament proposal: {cp['title']}",
        "",
        f"**Prompt:** {state['prompt']}",
        f"**Champion lens:** `{champ['id']}` ({cp['gap_kind']} gap)",
        "",
        "## Champion thesis",
        "",
        cp["thesis"],
        "",
        "### Submitted receipts (not independently verified)",
    ]
    for r in cp["receipts"]:
        lines.append(f"- [{r['kind']}] `{r['raw']}`")
    lines.extend(["", "### Judge-verified receipts"])
    for match in state["matches"]:
        result = match["result"]
        if result and result["winner"] == champ["id"] and result["verified_receipt"]:
            lines.append(f"- `{match['id']}` (judge `{result['judge_model']}`): `{result['verified_receipt']['raw']}`")
    if champ["grafts"]:
        lines.extend(["", "### Grafted insights from eliminated contenders"])
        for g in champ["grafts"]:
            lines.append(f"- From `{g['from']}` ({g['match']}): {g['insight']}")
    if cp.get("counter_risk"):
        lines.extend(["", f"**Primary risk to watch:** {cp['counter_risk']}"])

    final_res = find_match(state, "final")["result"]
    if state["runner_up"]:
        ru = find_entrant(state, state["runner_up"])
        rp = ru["pitch"]
        lines.extend([
            "",
            f"## Runner-up counter-thesis: {rp['title']} (`{ru['id']}`)",
            "",
            rp["thesis"],
            "",
            f"**Why Champion won the final:** {final_res['rationale']} "
            f"(judge `{final_res['judge_model']}`, checked `{final_res['verified_receipt']['raw']}`).",
        ])
    else:
        lines.extend([
            "",
            "## Runner-up counter-thesis",
            "",
            "No opposing finalist survived upstream dropouts.",
        ])

    lines.extend(["", "## Bracket ledger", ""])
    for m in state["matches"]:
        res = m["result"]
        if not res:
            continue
        if res.get("forfeit") or res["winner"] is None:
            lines.append(f"- **{m['label']} (`{m['id']}`)**: forfeited (all entrants dropped out).")
            continue
        graft_note = f", grafted from `{res['graft']['from']}`" if res["graft"] else ""
        outcome = (
            f"beat {', '.join(f'`{x}`' for x in res['losers'])}"
            if res["losers"]
            else "advanced unopposed"
        )
        lines.append(
            f"- **{m['label']} (`{m['id']}`)**: `{res['winner']}` {outcome} "
            f"(judge `{res['judge_model']}`, verified `{res['verified_receipt']['raw']}`{graft_note}). {res['rationale']}"
        )

    gate_prompt = (
        "Discovery-only requests: reply with **Champion**, **Runner-Up**, or a constraint adjustment before implementation."
        if state["runner_up"]
        else "Discovery-only requests: reply with **Champion** or a constraint adjustment before implementation."
    )
    gate_prompt += (
        " For an original build request, continue with Champion within the existing delivery scope"
        " unless the user asked to choose first."
    )
    lines.extend(["", "## Decision gate", "", gate_prompt])
    return "\n".join(lines) + "\n"


def cmd_render(args: argparse.Namespace) -> int:
    state_path, root, state = load_state(Path(args.dir))
    md = render_markdown(state)
    if args.out:
        raw_out = Path(args.out)
        candidate = raw_out if raw_out.is_absolute() else (root / raw_out)
    else:
        candidate = state_path.parent / "proposal.md"
    out_path = ensure_contained(candidate, root)
    atomic_write_text(out_path, md, root)
    print(md, end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="deepmodebot auto-router and tournament bracket engine")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_route = sub.add_parser("route", help="classify user prompt intent and vagueness")
    p_route.add_argument("prompt", nargs="?", default="")
    p_route.add_argument("--stdin", action="store_true")
    p_route.add_argument("--root", default="")
    p_route.add_argument("--has-factory", action="store_true")
    p_route.add_argument("--empty-dir", action="store_true")
    p_route.add_argument("--json", action="store_true")
    p_route.set_defaults(func=cmd_route)

    p_init = sub.add_parser("init", help="initialize a contained tournament bracket")
    p_init.add_argument("--root", required=True)
    p_init.add_argument("--slug", required=True)
    p_init.add_argument("--prompt", default="")
    p_init.add_argument("--prompt-stdin", action="store_true")
    p_init.add_argument("--entrants", type=int, default=12, choices=(4, 8, 12))
    p_init.add_argument("--force", action="store_true")
    p_init.add_argument("--json", action="store_true")
    p_init.set_defaults(func=cmd_init)

    p_pitch = sub.add_parser("pitch", help="record a receipt-backed entrant proposal")
    p_pitch.add_argument("--dir", required=True)
    p_pitch.add_argument("--entrant", required=True)
    p_pitch.add_argument("--title", required=True)
    p_pitch.add_argument("--thesis", required=True)
    p_pitch.add_argument("--gap-kind", required=True, choices=("architecture", "research", "hybrid"))
    p_pitch.add_argument("--receipt", action="append", required=True)
    p_pitch.add_argument("--counter-risk", default="")
    p_pitch.set_defaults(func=cmd_pitch)

    p_rebut = sub.add_parser("rebut", help="record an evidence-backed rebuttal inside a match")
    p_rebut.add_argument("--dir", required=True)
    p_rebut.add_argument("--match", required=True)
    p_rebut.add_argument("--entrant", required=True)
    p_rebut.add_argument("--target", required=True)
    p_rebut.add_argument("--attack", required=True)
    p_rebut.add_argument("--receipt", required=True)
    p_rebut.set_defaults(func=cmd_rebut)

    p_drop = sub.add_parser("dropout", help="mark an entrant as dropped out")
    p_drop.add_argument("--dir", required=True)
    p_drop.add_argument("--entrant", required=True)
    p_drop.add_argument("--reason", required=True)
    p_drop.set_defaults(func=cmd_dropout)

    p_judge = sub.add_parser("judge", help="record an independent judge verdict and advance winner")
    p_judge.add_argument("--dir", required=True)
    p_judge.add_argument("--match", required=True)
    p_judge.add_argument("--winner", required=True)
    p_judge.add_argument("--judge-model", required=True)
    p_judge.add_argument("--verified-receipt", required=True)
    p_judge.add_argument("--rationale", required=True)
    p_judge.add_argument("--graft-from", default="")
    p_judge.add_argument("--graft", default="")
    p_judge.set_defaults(func=cmd_judge)

    p_status = sub.add_parser("status", help="inspect bracket progress")
    p_status.add_argument("--dir", required=True)
    p_status.add_argument("--json", action="store_true")
    p_status.set_defaults(func=cmd_status)

    p_render = sub.add_parser("render", help="render final Champion and Runner-Up proposal")
    p_render.add_argument("--dir", required=True)
    p_render.add_argument("--out", default="")
    p_render.set_defaults(func=cmd_render)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
