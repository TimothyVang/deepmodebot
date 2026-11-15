# Tournament review fixes and agent journeys, 2026-11-14

## Changes

- F1: pitch receipts are submitted claims, not verified evidence. Pitch output and proposal headings now say so. A separate Champion section includes only decisive receipts recorded by judges for matches Champion won. The bracket ledger retains each round's checked receipt. The CLI validates receipt syntax and local line ranges; judges remain responsible for independent verification.
- F2: tournament preserves original delivery intent. Discovery-only requests and explicit choose-first requests pause; an original build request presents Champion and Runner-Up, then implements Champion within existing permissions. The skill, both command entry points, technique, route helper and rendered handoff agree. No publishing, deployment or spending permission is inferred.
- F3: two real, tool-enabled agents executed the technique on identical disposable starters, including real contender and independent judge calls, rebuttals, grafts and proposal rendering. This is downstream execution evidence, not a tool-free routing answer or a manually scripted bracket.
- F4: initialization takes the same `bracket.lock` as pitch transactions before checking existence or saving. Concurrent duplicate initialization cannot replace a bracket without `--force`. Explicit replacement waits for an active transaction too.

## Environment and identical input

Doctor: `python .omp/skills/verify-deepmodebot/control.py doctor` returned `ready: true`, Python 3.13.14, Git, Node and omp available. Actual CLI help reported omp 18.20.2.

Both original requests were `Build me an AI app.` Both disposable git repos contained identical `README.md`, `app.py` and `test_app.py` starters. The planted defect returned the last note regardless of the question. Existing acceptance required `backups` to return `Backups are in the vault.`, not `Lunch is at noon.`

Both runs used `openai-codex/gpt-6.1-sol`, high thinking, a 15-minute timeout and a usage cap of 12 including children. The same evaluation boundary restricted work to an offline, standard-library-only app with no installs, secrets, services, publishing or trading. It did not authorize skipping a proposal gate. The original build request, not an evaluator instruction to build the winner, determined the handoff.

The launcher copied each source skill into its arm before starting. It disabled installed skills, rules, context files, extensions and LSP, told the agent to read that local `SKILL.md`, and resolved its technique references to that pinned copy. This avoids accidentally exercising an installed release instead of the checkout. No plugin installation or discovery claim is made.

The executed `omp -p` options were:

```text
--mode json --no-session --no-context-files --no-rules --no-skills
--no-extensions --no-lsp --no-title --offline --no-pty --wait-async
--model openai-codex/gpt-6.1-sol --smol openai-codex/gpt-6.1-sol
--slow openai-codex/gpt-6.1-sol --thinking high --max-time 15m --max-cost 12
--tools read,write,edit,bash,grep,glob,task,wait,todo
```

Exact argv, complete prompt, raw NDJSON, stderr, exit, source copies and answers remain in `.scratch/tournament-review/{before,after}/`. `command.json` records the actual positional prompt. `source.json` fingerprints the procedure. Both parent processes exited 0; the before arm's app acceptance correctly exited 1.

## Before

Source base: `9b3c6b15a7c9d960eb977d6f8207e57565cb77b4`.

| Source | SHA-256 |
|---|---|
| `SKILL.md` | `4c3596b61abebb13715ff0649474a849c0901faed809d73dea357a0b74679147` |
| `references/techniques/tournament.md` | `bd585226109d325ee4e6af518c561dae32aa8e681469968ee4bdbdbc856b1fbb` |
| `assets/tournament/tournament.py` | `b43296ffe365d2d63cda00ee6f0dea7ad3c56668fc3e3869f4936037990f9260` |

Observed real delegation: 12 contender scouts plus seven separate judge scouts. The real CLI recorded 12 pitches, 12 pod rebuttals, four semifinal rebuttals and seven verdicts. No dropouts. Champion was `workflow-ux-strategist`; Runner-Up was `contract-boundary-auditor`. Final status had no pending pitches or ready matches.

The agent's final answer was `AI-app proposal ready; implementation awaits your choice.` It explicitly treated the original build request as insufficient authorization to continue. Production code stayed untouched.

Observed output from the agent's single acceptance run:

```text
python -m unittest -v
Ran 2 tests in 0.001s
FAILED (failures=1)
AssertionError: 'Lunch is at noon.' != 'Backups are in the vault.'

python app.py
Lunch is at noon.
```

Artifacts under `.scratch/tournament-review/before/app/.scratch/tournaments/offline-ai-app/`: `bracket.json`, `proposal.md`, `agents/`, round command logs, `receipt-review.md`, `execution.md`, `acceptance.log`, `starter-cli.log`, `final-status.json` and `decision-gate.json`.

## After

| Source | SHA-256 |
|---|---|
| `SKILL.md` | `641d3d5f59f738e69075e6a5441dd66741a2d52e351708eaad4f44a90156c8f9` |
| `references/techniques/tournament.md` | `996e71a47a11af618100e0e7f30c86c738a7f729504758cfbf8cd0162999cb4d` |
| `assets/tournament/tournament.py` | `de73cbc230d9e3c47c7abf86f992932cefea8d83b3b4d8ce3327541948d058f8` |

Observed real delegation: 12 pitch workers, 16 rebuttal workers and seven separate judges. These workers were instructed to be read-only, but used the general task role rather than the scout role. Parent raw events record each call with the exact requested model. The CLI recorded all 12 pitches, 12 pod rebuttals, four semifinal rebuttals and seven verdicts. No dropouts. Champion was `scale-cost-analyst`; Runner-Up was `oss-prior-art-hunter`.

The agent presented the proposal, stated `I'll now implement the requested build; no user decision is required.`, then edited only the disposable app's `app.py`, `test_app.py` and `README.md`. It delivered a stateless lexical note finder and UTF-8 file CLI, with whole-word matching, deterministic ties and no-match abstention. It did not claim generative AI or paraphrase understanding.

The agent ran acceptance once after implementation:

```text
python -m unittest -v
Ran 12 tests in 0.001s
OK
```

Its actual CLI smoke recorded six cases: relevant query, unmatched query, Unicode casefolding, empty file, missing file and invalid UTF-8. Successful cases exited 0; file errors exited 2 with actionable stderr. The author inspected the delivered implementation and independently ran its real CLI:

```text
cd .scratch/tournament-review/after/app
python app.py --notes .scratch/tournaments/offline-ai/notes.txt "Where are backups?"
Backups are in the vault.
```

Artifacts under `.scratch/tournament-review/after/app/.scratch/tournaments/offline-ai/`: `bracket.json`, `proposal.md`, `commands.jsonl`, original pitch/rebuttal/verdict artifacts, `acceptance.txt`, `smoke.json`, `implementation.md` and `delivery.json`. The proposal separates submitted receipts from the Champion's three judge-recorded receipts.

## Focused checks

```text
python plugins/deepmodebot/skills/deepmodebot/assets/tournament/test_tournament.py -v
Ran 9 tests in 5.140s
OK
```

`TMPDIR`, `TMP` and `TEMP` were inside `.scratch/tmp`. Coverage includes fabricated command/unchecked URL submissions excluded from verified proposal sections, original build intent in empty and populated roots, two competing initializers, an in-flight pitch transaction, and serialized explicit replacement.

A separate real subprocess CLI smoke held a pitch transaction open, launched initialization, observed it remain blocked, then released the transaction:

```text
force=False: init remains blocked while pitch transaction holds bracket.lock
force=False: duplicate refused; concurrent pitch preserved
force=True: init remains blocked while pitch transaction holds bracket.lock
force=True: explicit replacement succeeds only after transaction releases lock
```

A real four-entrant render smoke submitted `cmd:never-run -> fabricated claim` and `https://example.org/unchecked-claim`, then recorded independently inspected `receipt.txt:1` as the decisive receipt. Only the submitted section contained the fabricated claims. Neither submitted command nor URL was executed. Raw command/output captures remain in `.scratch/tournament-review/receipt-smoke.json`; lock smoke output is in `init-smoke.txt`.

```text
python scripts/eval_routing.py --model openai-codex/gpt-6.1-sol --out .scratch/tournament-review/routing-review.json
route 24/24  size 24/24  both 24/24
```

The model routing report is committed as `evals/results/routing-review-2026-11-14.json`. It measures routing only; it does not replace the journeys above.

The first `python scripts/check.py` failed because the rules before `## Routes` reached 20,029 bytes, exceeding 20,000. The revised discovery/build sentence was shortened without changing its handoff meaning. That final wording-only compression happened after both the pinned after journey and routing run; their source hashes above deliberately remain unchanged. Final gate capture: `.scratch/tournament-review/check-final.txt`.

## Limits

- One planted task, one model family and one attempt per arm. Different winners and delegation shapes do not establish a controlled quality, cost or speed improvement.
- Research lenses used repository evidence because public research was unavailable under the offline boundary. No SOTA or external prior-art superiority was measured.
- Judges were separate agents, not a different model family. Read-only worker mandates are not an OS sandbox. The parent recorded agent judgments through the CLI; the CLI itself does not attest claim truth.
- Both final rounds compared already-recorded theses through an independent judge; neither arm recorded an additional final-round rebuttal exchange. The technique requires the final comparison, not an extra rebuttal command.
- The delivered app is lexical retrieval, not a hosted or generative AI system. No external harness, deployment, plugin installation journey or real-money operation was exercised.
- Raw local artifacts remain under `.scratch/`, not in the published report. Before and after source snapshots, failed acceptance, and the first failed repository gate are retained.

## Final repository gate

```text
python scripts/check.py
OK
```

The final gate completed after the size correction and report addition. No GitHub writes or branch operations were performed.
