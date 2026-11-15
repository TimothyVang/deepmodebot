# Verification feature map

Run `python .omp/skills/verify-deepmodebot/control.py doctor` from the root first. Use disposable projects, explicit models and fresh run IDs. Runtime evidence must include the command, input/revision identity, output and resulting artifacts. Report blocked paths instead of substituting a mock or a structural check.

- [Local delivery](delivery.md): real coding-agent completion and checked-out behavior.
- [Review quality and safe context](review.md): sealed review input boundaries, findings and clean controls.
- [Workflow coverage](workflows.md): pinned inventories and executed agent journeys.

These entries cover the surfaces changed in this work. They do not claim production autostart, every harness, hosted competitors or all upstream workflows have been exercised.

## Reasoning gates

For changes to the reasoning gates in `plugins/deepmodebot/skills/deepmodebot/SKILL.md`, exercise the candidate skill with a bounded agent scenario involving conflicting source evidence and repeated unproductive work. Capture the prompt and response under `.scratch/evidence/` and check that the agent identifies the conflict, revisits the premise, and proposes a bounded next step without treating activity as progress. A structural skill check alone does not prove model compliance; report the scenario and its limits.

## Public evidence page

For changes to `docs/index.html`, serve only `docs/` on a loopback address in a named, owned service.
Open a managed browser with relay disabled. Follow the Evidence navigation link and inspect the section at wide and compact widths.
Check keyboard focus, overflow and evidence-link destinations without visiting external sites.
Save screenshots under `.scratch/evidence/`, then close the owned tab and service.
Local rendering and destination inspection do not prove that unpublished reports are available on the public site.

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
Local marketplace snapshots prove local upgrades, not remote publication, watcher updates, session reloads or untested harnesses.
