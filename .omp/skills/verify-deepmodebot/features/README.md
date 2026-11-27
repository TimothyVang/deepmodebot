# Verification feature map

Run `python .omp/skills/verify-deepmodebot/control.py doctor` from the root first. Use disposable projects, explicit models and fresh run IDs. Runtime evidence must include the command, input/revision identity, output and resulting artifacts. Report blocked paths instead of substituting a mock or a structural check.

- [Local delivery](delivery.md): real coding-agent completion and checked-out behavior.
- [Review quality and safe context](review.md): sealed review input boundaries, findings and clean controls.
- [Workflow coverage](workflows.md): pinned inventories and executed agent journeys.
- [Repository discovery](repositories.md): dated reference choices, project-cache refresh, licensing cautions and startup-idea boundaries.
- [Windows process ownership](processes.md): real process trees, virtualenv context, bounded startup and deadline cleanup with held handles and drained pipes.
- [Goals and updates](goals-and-updates.md): real ACP goal consensus, quantitative artifacts and fork-preserving local synchronization.
- [Visual E2E and design evidence](visual-e2e.md): actual recording/replay, pinned-tab boundaries, three image-review contexts and portable/Penpot workflow evidence.

## Routing and tournament bracket

For changes to `/deep` routing (`SKILL.md`, `evals/routing/cases.json`, `scripts/eval_routing.py`) or `assets/tournament/tournament.py`:
Run `python plugins/deepmodebot/skills/deepmodebot/assets/tournament/test_tournament.py` with `TMPDIR`, `TMP` and `TEMP` inside `.scratch/tmp`.
Exercise a real 12-entrant bracket CLI flow (`init`, `pitch`, `rebut`, `judge`, `status`, `render`) inside a disposable repo under `.scratch/` and inspect the generated `proposal.md`.
Run `python scripts/eval_routing.py` (with an explicit `--model` when comparing revisions) so headless `omp -p` evaluates `SKILL.md` across `evals/routing/cases.json` and writes `evals/results/routing-<date>.json`.
Deterministic `tournament.py route` unit checks verify the helper classifier only; `scripts/eval_routing.py` measures single-turn model route selection from `SKILL.md` text, not full multi-agent tournament debate quality.
For technique or proposal-handoff changes, also run the full technique with real contender and independent judge agents on identical disposable starters before and after. Keep pinned procedure copies, prompts, raw events, brackets, proposals and app output. Verify that a discovery-only request waits for a choice, while an original build request presents the proposal and delivers Champion without another authorization.
Inspect proposal receipt sections: unchecked command and URL submissions stay outside judge-verified receipts. Exercise competing initializers under the same held `bracket.lock`, including an in-flight pitch and explicit `--force`; only an authorized replacement may discard earlier state.
Try revising an unjudged pitch, then replacing a pod winner and the crowned Champion. Only the unjudged revision may succeed; rejected replacements must leave the bracket and rendered thesis unchanged.
Exercise `route --stdin --json` with explicit choose-before-coding, approval and no-code constraints, plus non-greenfield requests to implement the winner. Include "get my approval before coding" and permission, consent and sign-off variants; an approval feature name alone must not add a gate. Check both `intent` and `checkpoint_before_code`; mentioning a possible future build is not an implementation request.

These entries cover the surfaces changed in this work. They do not claim production autostart, every harness, hosted competitors or all upstream workflows have been exercised.

## Reasoning gates

For changes to the reasoning gates in `plugins/deepmodebot/skills/deepmodebot/SKILL.md`, exercise the candidate skill with a bounded agent scenario involving conflicting source evidence and repeated unproductive work. Capture the prompt and response under `.scratch/evidence/` and check that the agent identifies the conflict, revisits the premise, and proposes a bounded next step without treating activity as progress. A structural skill check alone does not prove model compliance; report the scenario and its limits.

## Public evidence page

For changes to `docs/index.html`, serve only `docs/` on a loopback address in a named, owned service.
Open a managed browser with relay disabled. Follow the Evidence navigation link and inspect the section at wide and compact widths.
Check keyboard focus, overflow and evidence-link destinations without visiting external sites.
For PR-policy copy, inspect the visible conversation paragraph and FAQ structured data: exactly three valid responses, at least two passes, same head, no size exception, and no override of deterministic gates.
Save screenshots under `.scratch/evidence/`, then close the owned tab and service.
Local rendering and destination inspection do not prove that unpublished reports are available on the public site.
For evidence packaging changes, exercise the real `whitelabel.build` API with `media=False, check=False` into a new `.scratch/` directory, then validate copied E2E bundles using that distribution's own loader. Existing evidence paths and bytes must remain unchanged; these receipts are upstream observations, not proof of a rebranded run.

## Optional agent SDK workspace

Follow the SDK workspace entry in [agent-harnesses](../../../../plugins/deepmodebot/skills/agent-harnesses/SKILL.md) to copy the source-only kit into a fresh `.scratch/sdk-runtime/` and install its dependencies there.
Run the venv's `python -m pip check`, `python check_antigravity.py`, and `bun check.ts` from that workspace.
Expect Antigravity custom-tool dispatch, Codex native version output, omp in-memory message storage, and a Claude SDK native initialization handshake without sending a prompt.
Capture commands and outputs under `.scratch/evidence/`. Report platform, package versions, and any failures.
These checks do not verify model inference, provider authentication, Antigravity runtime startup, or permission enforcement during model turns.
Model-backed examples require separate approved provider/data/spend boundaries; do not silently turn a local installation check into an agent run.

## Plugin release upgrades

For a release bump, install the previous release through the real harness CLI in isolated state under `.scratch/`, then refresh its marketplace to the candidate revision and upgrade that existing installation.
Capture before/after versions, upgrade availability, CLI output and the runtime-linked plugin payload.
The [0.8.2 upgrade report](../../../../evals/results/release-0.8.2-upgrade-2026-11-14.md) records separate real omp and Claude Code upgrade runs, pinned inputs, isolation commands, observed output and limits.
The [0.8.3 upgrade report](../../../../evals/results/release-0.8.3-upgrade-2026-11-15.md) records a real isolated omp upgrade and all 244 runtime-linked plugin file hashes; other harnesses and remote/watcher fetching are not inferred.
Local marketplace snapshots prove local upgrades, not remote publication, watcher updates, session reloads or untested harnesses.

## Inner-loop audit and goal-loop gates

For changes to `plugins/deepmodebot/skills/deepmodebot/assets/loop/loop.py`, `inner-loop`, or `end-to-end`, run `loop.py audit --json` and `loop.py manifest <manifest.json>` on a disposable git repo under `.scratch/evidence/<slug>/`, then drive `loop.py run <goal.md>` with a live subscription harness (`omp`).
Verify `manifest` slice progression (`1/N` to `N/N`), `fast_check`, `forbid_slop` (suppressions, swallowed exceptions, and `TODO`/`NotImplementedError` stubs), `protect_configs`, and the acceptance `check` against actual candidate edits, keeping `trail.tsv` and per-iteration prompt and check logs under `.scratch/`.
Synthetic fake-harness unit tests in `test_loop.py` prove deterministic runner state machines, not live model compliance.

## Anti-reward-hacking gate (`reward_guard.py` and `dmb-gate reward`)

For changes to `plugins/deepmodebot/skills/deepmodebot/assets/reward-guard/reward_guard.py`, `native/dmb-gate/src/reward.rs`, or `no-reward-hacking.md`, run `python -B -m unittest discover -s plugins/deepmodebot/skills/deepmodebot/assets/reward-guard -p "test_*.py"` and `cargo test --manifest-path native/dmb-gate/Cargo.toml`.
Exercise a disposable git repo under `.scratch/evidence/<slug>/` where a planted shortcut (`--min-iou 0.0`, `primitive_cube_add`, `@pytest.mark.skip`, and a lowered `MIN_IOU` bound) fails both `reward_guard.py scan` and `dmb-gate reward`, and verify `lock-contract` → `record-provenance` → `record-judge` → `verdict --strict` rejects tampered gates, unapproved primitive producers, skipped reference inputs, and self-judged verdicts before passing on verified receipts.

## Completed-job cleanup

Exercise the bot's cleanup CLI with isolated `HOME`/`USERPROFILE` and local bare Git remotes, never the production cache. Preview must not delete; explicit apply must dispose eligible completed work and newly owned clones while preserving unfinished jobs, dirty/untracked files, unpushed commits, locked or foreign worktrees and changed clone metadata. Inspect real filesystem and Git state, not just exit codes. Cleanup failures must not turn completed jobs into retried jobs.

Use focused real-Git regression tests for deletion safety. A local lifecycle smoke does not prove hosted GitHub, production watcher, or every model's instruction compliance. Preserve required installation folders even when the harness calls their parent `cache`.

## Hidden Windows background helpers

Run doctor, then run `python -B -m unittest test_windows_job` from `assets/loop` with `TMP`, `TEMP` and `TMPDIR` pointing to a fresh repo-local scratch directory. The real Win32 probe checks both the command and supervisor have no console, while stderr, nonzero exits, stdin and process-tree deadlines remain intact.

Drive `loop.run_limited` from a consoleless Python process against the source and installed helper copies; record `GetConsoleWindow` inside both the supervisor and command rather than inferring visibility from creation flags or failed `AttachConsole` calls. Check captured helper launch paths with the Windows background-process regression. Do not start a production watcher or invoke real authentication. Interactive setup and explicitly requested user interfaces must remain available.

## App automation relay

Run `bun plugins/deepmodebot/skills/app-automation-relay/assets/relay_server.ts --self-test`. The live loopback exchange must reject an unauthenticated read and a stale action; the bounded wait must see the submitted state. A separate `--mcp` process must negotiate `server/discover` and read that same revision. This proves the transport and demo adapter, not native app compatibility or a latency target.
