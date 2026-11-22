# autoroute

**Use when:** starting any non-trivial task (automatically on model invocation or `/deep`), whenever a prompt is messy, compound, or spans multiple domains, or mid-task when new code evidence invalidates the original route. Never rely on regex matching alone to choose a workflow.

Regex cannot understand human phrasing, tone, frustration, skepticism, or compound goals. Instead, **deepmodebot uses the LLM itself** to read what the user typed against the live disk catalog (zero regex-prior anchoring in the prompt), then enforces **checks and balances** in code plus a bounded Round-2 LLM critic before executing.

## 3-stage LLM semantic auto-routing loop

1. **Stage 1: Build the live disk catalog & repo facts packet (zero regex bias).** Run:
   ```bash
   python -B "<this installed skill>/assets/autoroute/autoroute.py" menu --root "<project-root>" --stdin --json <<'EOF'
   <raw user prompt>
   EOF
   ```
   *(Headless / CLI callers without an active chat LLM can run `autoroute.py route --root "<project-root>" --stdin --harness auto --json` to invoke the user's logged-in subscription LLM `agy`/`claude`/`codex` directly through Stages 1–3, stripping API keys and never spending `omp` tokens.)*
   `menu` discovers every playbook, technique (all 52, including `gen-ui` and `video-forensics`), plugin sibling skill, and project-local skill directly from disk, collects live repo facts, and emits `llm_router_prompt` with **no regex mode guess** so the LLM judges purely from the user's words.
   Done when the live catalog and repo facts are in hand.

2. **Stage 2: Ask the LLM to decide semantically.** Using the full menu and repo facts (inline structured reasoning, or a fast read-only `scout` subagent on large/ambiguous asks), output a single JSON route decision:
   - `decoded_intent` and numbered `deliverables` (full scope; never drop compound clauses)
   - `primary_mode` and exact `route_file` from the live menu
   - `secondary_techniques` (e.g., `self-grill`, `no-comments`, `security-audit`, `why`, `how`, `formal-verification`) and `reference_skills` (`skill://frontend-ui`, `skill://secrets-and-auth`, `skill://software-architecture`, `skill://cloud-devsecops`, `skill://agent-harnesses`, `skill://domain-rules`, `skill://deep-stack`)
  - `size` (`S`/`M`/`L`/`none`), `self_grill` (`none`/`plan`/`checks`/`both`), `hardcore_mode` (default `true`; `false` only on explicit minimal/prototype opt-out), `hardcore_ceiling` (1-sentence first-principles engineering target), `confidence` (`0.0`–`1.0`), `runner_up`, `why_not_runner_up`, `needs_prompt_upgrade`, and `hard_stops`.
   Done when the JSON decision covers every deliverable and names why the runner-up lost.

3. **Stage 3: Enforce checks and balances (code gate + bounded critic).** Pipe the LLM's JSON decision into the deterministic verifier:
   ```bash
   python -B "<this installed skill>/assets/autoroute/autoroute.py" verify --root "<project-root>" --prompt "<raw prompt>" --decision-stdin --strict --json <<'EOF'
   <decision JSON>
   EOF
   ```
   The verifier enforces five gates:
   - **Disk & containment existence:** rejects any hallucinated `primary_mode`, `route_file`, `secondary_technique`, or `reference_skill` (including `skill://` subpaths or `..` escapes) not present on disk.
   - **Size & safety floor:** read-only/discovery modes must be `none`; any prompt or diff touching auth, secrets, permissions, migrations, payments, CI workflows, or agent config cannot be `S` and requires `self_grill` + security companions.
   - **Anti-blunder & Hardcore anti-sandbagging guards:** blocks lazy `tournament` dumping on concrete anchors without justification, flags shallow `feature`/`bug-fix` collapse when specialized playbooks fit (`perf-issue`, `runtime-forensics`, `trace-forensics`, `hillclimb`, `visual-parity`, `reference-rebuild`, `formal-verification`, `gen-ui`, `video-forensics`, `suggest`, `prompt-upgrade`, `no-comments`), and blocks disabling `hardcore_mode` or under-sizing multi-part/systems work to `S`.
  - **Required companions:** flags missing `reference_skills` or `self-grill`/`no-comments` on M/L code work (plus `architect` on multi-part hardcore L builds).
   - **Bounded critic pass (`--critic-round 2`):** if `status` is `CRITIC_REQUIRED` (confidence `< 0.80` or specialized-signal mismatch) or `REJECTED`, run one fresh adversarial critic pass using `critic_prompt`, revise the JSON with `"critic_reviewed": true`, and re-verify with `--critic-round 2` until `APPROVED` (exit 0). Round-1 `critic_reviewed: true` without `--critic-round 2` is rejected.
   Done when `verify --strict` returns `APPROVED` (exit 0) and you open `route_file` plus listed `reference_skills`.

## Mid-flight re-route (Stage 4)

Routing is not a one-shot guess. Whenever real code inspection contradicts the initial route (diff grows past S, touches a sensitive path, hits 2 failed attempts sharing a premise, or reveals 2+ competing architectural shapes), run:
```bash
python -B "<this installed skill>/assets/autoroute/autoroute.py" reroute --root "<project-root>" --current-mode "<mode>" --current-size "<size>" --failed-attempts <n> --json
```
Apply the recommended escalation (`S -> M/L`, `M -> L`, `architect`, `arena`, `attack-the-premise`, `security-audit`, `self-grill`, `no-comments`) and log one row in the decision trail; add `sme-review` when domain rules are unverified.

**Done when** `autoroute.py verify --strict` returns `APPROVED` (exit 0), the selected `route_file` and `reference_skills` are loaded, and any mid-flight scope or premise shift triggers `reroute`.
