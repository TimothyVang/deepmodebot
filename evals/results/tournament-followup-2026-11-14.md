# Tournament pitch provenance and delivery constraints, 2026-11-14

Base: `da37f3b2d4ec1bfd3a0dffbd2da3528f885f7cf8`.

## F5: freeze judged pitches

`cmd_pitch` now rejects revisions once any match containing the entrant has a recorded verdict. The check runs inside the existing locked state transaction, before receipt validation or pitch mutation. A winning entrant remaining active no longer permits replacing its judged thesis. Unjudged proposals remain editable. No verdict invalidation or pitch-version migration is required.

The existing 12-entrant regression journey now revises an unjudged proposal, attempts a pod-winner replacement, and attempts a crowned-Champion replacement. It asserts the rejected writes leave bracket bytes unchanged and that rendering still presents the judged Champion's thesis beside its original ledger and checked receipts.

A separate real subprocess CLI journey exercised `init`, `pitch`, `rebut`, `judge`, `status` and `render` across 12 entrants and seven matches. Observed output:

```text
pitch: unjudged revision accepted
pitch: pod winner replacement rejected; bracket sha256 unchanged b40708e637e6fb624a75834834a3450fd7ab3b3f7c8178516c6cbafa46baea52
pitch: crowned champion replacement rejected; bracket sha256 unchanged bbcd60f0589e2b5329290f89cca0b48491670b41ac1e7ffb2904b558786cd164
render: original judged thesis and ledger preserved across 7 matches; 12 entrants
```

The rendered title remains `Revised before judging`, and the thesis remains `Revised unjudged thesis`; neither contains the attempted `Never judged replacement thesis`.

## F6: separate delivery intent from the choice gate

Tournament delivery detection now recognizes imperative build/implementation requests outside greenfield prompts. Explicit choose-first, approval, pause and no-code constraints retain the checkpoint even when eventual delivery intent is `execute`. Discovery-only requests remain `discover` with a checkpoint. Merely discussing what to build later, creating a proposal or delivering a research report does not authorize implementation.

Regression cases cover 15 prompts in both empty and populated roots. These test the helper's actual `intent` and `checkpoint_before_code`, not just its route name. Real `route --stdin --json` invocations produced:

| Original request | Intent | Checkpoint |
|---|---|---|
| Build me an AI app; run a tournament and let me choose before coding | execute | true |
| Rethink the architecture and implement it | execute | false |
| Run a tournament and build the winner | execute | false |
| Rethink the architecture and implement it; wait for my approval | execute | true |
| Run a tournament to decide what to build next | discover | true |
| Run a tournament; do not implement anything | discover | true |

This changes the deterministic helper, not the skill's existing discovery/build or explicit-approval policy. The classifier remains a lexical routing aid, not a general natural-language permission parser.

## Commands and retained artifacts

Doctor: `python .omp/skills/verify-deepmodebot/control.py doctor` returned `ready: true`, Python 3.13.14, Git, Node and omp available.

```text
python plugins/deepmodebot/skills/deepmodebot/assets/tournament/test_tournament.py -v
Ran 10 tests in 5.247s
OK

python scripts/eval_routing.py --model openai-codex/gpt-6.1-sol --out .scratch/tournament-review-followup/routing.json
route 24/24  size 24/24  both 24/24
```

Tests used `TMPDIR`, `TMP` and `TEMP` inside `.scratch/tmp`. The final repository gate also exercises the two additional report/proposal near-miss cases added after the focused run. The committed model-routing result is `evals/results/routing-followup-2026-11-14.json`.

Raw subprocess argv, stdin, exit, stdout and stderr remain in `.scratch/tournament-review-followup/cli-capture.json`. `smoke.txt` and `summary.json` record assertions. The disposable repo's `.scratch/tournaments/frozen-pitches/` retains `bracket.json` and `proposal.md`. Repository-gate output is retained in `.scratch/tournament-review-followup/check.txt`.

## Limits

The bracket smoke uses explicitly labeled synthetic fixture judgments, not model contenders or a new agent journey. It proves CLI state preservation, not proposal quality. The model-routing suite measures unchanged `SKILL.md` route/size selection, not the helper's new intent flags; the direct CLI captures and regression cases establish those flags. No technique prose, production app, deployment, GitHub surface or real-money operation changed.

## Repository gate

```text
python scripts/check.py
OK
```

The gate passed with all 15 delivery-constraint prompts and both post-verdict replacement checks included.

## F6 additional approval phrasing

Base: `3c234e39004f5750c400e7b36246269d1431b83b`.

The checkpoint matcher previously recognized requests to choose or approve, but missed the noun phrase `approval before coding`. It now recognizes approval, permission, consent and sign-off followed by `first` or `before` an implementation action. This covers the reported request without treating an approval feature name as an authorization gate.

Six added regression cases bring delivery-constraint coverage to 21 prompts in both empty and populated roots. Real `route --stdin --json` calls observed:

| Request suffix | Intent | Checkpoint |
|---|---|---|
| Build me an AI app; run a tournament, but get my approval before coding | execute | true |
| Build me an AI app; run a tournament; obtain my permission before implementing | execute | true |
| Rethink the architecture and implement it; my approval before coding is required | execute | true |
| Run a tournament and build the winner; get my sign-off before you code | execute | true |
| Run a tournament and build the winner; get my consent first | execute | true |
| Run a tournament and implement approval checks | execute | false |

A real synthetic CLI bracket completed `init`, 12 pitches, rebuttals, seven judgments, `status` and `render`. The original approval-before-coding request remained in the proposal, alongside its existing choose-first exception. This checks the CLI, not a new agent journey or proposal quality.

```text
python .omp/skills/verify-deepmodebot/control.py doctor
ready: true

python plugins/deepmodebot/skills/deepmodebot/assets/tournament/test_tournament.py -v
Ran 10 tests in 4.813s
OK

python scripts/eval_routing.py --model openai-codex/gpt-6.1-sol --out .scratch/approval-checkpoint/routing.json
route 24/24  size 24/24  both 24/24

python scripts/check.py
OK
```

Raw CLI arguments, stdin, exits, stdout and stderr remain in `.scratch/approval-checkpoint/cli.json`. The disposable bracket and proposal are under its `app/.scratch/tournaments/approval/`. Focused test, model-routing and repository-gate captures remain in `tests.txt`, `routing.json` and `check.txt` beside that app. Tests and CLI probes used project-local temporary directories. The model-routing suite measures unchanged skill route/size selection; direct CLI cases prove the new checkpoint behavior.
