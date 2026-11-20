# Local delivery

A developer requests a feature in a local project and receives working changes in the starting tree, not a stranded worktree or an unfinished review.

## Sub-features

- Local medium edits avoid remote publishing while retaining behavior verification and diff review.
- Published changes still require exact-head review and merge gates.
- Separate run IDs preserve previous evidence; explicit models prevent silently changing the comparison.
- Blind packs exclude supplied instructions but retain candidate-authored helpers needed to exercise delivered code.
- Attempt reuse is refused for model runs and judges; raw failed or interrupted attempts remain evidence.
- Full-collection requests retain every discovered candidate until it is delivered, mapped to a proven duplicate, classified as a non-target, or individually blocked with evidence. A preview and a scope-narrowing question fail acceptance.

## How to get to it (user POV)

Install the plugin and invoke `/deep` in a local project, or reproduce a controlled task with `evals/outcome/run.py`.

## Driving it with control-deepmodebot

Preconditions: doctor passes; the selected model has a subscription login; the candidate and comparison commits exist.

Run `python .omp/skills/verify-deepmodebot/control.py run --id delivery-prepare outcome setup --task kitty --run-id delivery --ref <candidate-commit> --compare-ref <previous-commit> --per-variant 5`.
Run the printed workspaces with `control.py run --id delivery-agents outcome run --task kitty --run-id delivery --model <authorized-model> --max-cost 4 --max-time 20m`, then `control.py run --id delivery-results outcome collect --task kitty --run-id delivery` using the full helper path above.
Inspect every completed tree, final reply, hidden-check result, exit and contamination hit. A successful result passes the requested behavior and leaves it in the starting tree. Compare revisions and plain agent only under the same settings. The judge command requires two explicit `--judge-model` options.

For the full-scope contract, run the `full-gallery` workflow scenario with the candidate skill in a fresh project and an explicit approved model. Check the delivered gallery against every seeded source image, including the reference-assets folder and duplicate mapping. Inspect the final reply for premature clarification or an unsupported completion claim. Also run the `gallery-preview` near-miss to confirm an explicit two-image preview stays limited, and `gallery-permission` to confirm missing access is reported without fabricating an image or bypassing permissions. Retain prompts, tool events, outputs and the exact skill digest. These bounded scenarios do not prove universal model compliance or runtime stop-hook enforcement.

## Gotchas

The corpus is small and known during development. Concurrent host/provider load prevents a reliable speed claim from one batch. `process_finished` does not itself mean the feature is correct. Publishing gates need their own PR-head evidence; local task success does not prove them.
