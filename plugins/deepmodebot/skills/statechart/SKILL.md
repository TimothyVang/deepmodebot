---
name: statechart
description: "Check a TLA+ model of a system that moves between states, such as a product flow, a protocol, or a service, and draw it as a Mermaid statechart. The report gives the shortest path to each state that breaks a rule. Use for /statechart, or to show a bug as a path through states."
---

# Statechart

The chart shows how a system moves between states, in the words of the person who reads it. That person, the reader, decides whether the behavior is right.

## Run

Work under the target repo's `.scratch/statechart/` (git-ignored). Write a TLA+ spec and its config.
Use the actual directory containing this skill, not a hard-coded plugin cache path. Then run:

```sh
<skill dir>/scripts/statechart SPEC.tla [--config FILE] [--view FILE] [--out DIR]
```

`scripts/statechart.ts` is TypeScript. On POSIX, `sh <skill dir>/scripts/statechart` picks Node 22.18–22.x or 23.6+, Bun 1.1.5+, or Deno 2+.
On native Windows, run `node --disable-warning=ExperimentalWarning <skill dir>/scripts/statechart.ts` with Node 22.18–22.x or 23.6+.
Keep temporary files local: create `.scratch/statechart/tmp` and set `TMPDIR` (`TEMP`/`TMP` on Windows) to its absolute path before running.
Use absolute paths for `TLA2TOOLS`, `JAVA`, and `--view` when supplying them.

TLC and Java are optional dependencies of this skill only; plugin installation does not install or execute them.
With `TLA2TOOLS` set to an existing `tla2tools.jar`, the command uses `JAVA` or `java` (Java 11+).
Otherwise the first invocation uses `mise` to install checksum-pinned TLC 1.7.4 and Temurin 25 and needs network access.
Read `references/tooling.md` for explicit setup, example runs, exit codes, and test dependencies.

Treat a view module and the TLA+ sources as executable input. Only run trusted, reviewed local files.
The command loads `--view` with the agent's filesystem and process permissions; it is not a sandbox.
Keep credentials, private production data, and authenticated browser traces out of model fixtures.

Use `skill://create-formal-verification-skill` (`../create-formal-verification-skill/SKILL.md`) to derive a model from code.
Use `skill://maintain-formal-verification-skill` (`../maintain-formal-verification-skill/SKILL.md`) when the code and model may have drifted.

## Write the spec

- Write each rule that the reader agrees to as an INVARIANT. A rule can be about a screen, a result, a stored value, or a message. If the model has no variable for a rule, add the variable. Never weaken a rule to make it hold.
- Write `Next` as a disjunction of the actions, such as `YouPressPlay \/ YouPressStop`. If you do not, TLC names every step `Next`.
- A state with no step out breaks `NoDeadlock`, also when it is a correct end state. When an INVARIANT or a PROPERTY already has that name, the rule is `CHECK_DEADLOCK`.
  Add to `Next` an action that is true only in the end states and changes nothing, such as `Done == phase \in {"paid", "failed"} /\ UNCHANGED vars`, and give it a label in `step()`.

## Pick the chart

You do the work that needs judgment: the words on each state and arrow, the phases and their colors, the title, and the report to the reader. Put your work in a view module, and give it with `--view`.

To show the reader's words, the view exports `state(vars)`. The value that `state()` returns picks the form:

- A string gives a flat chart: `export const state = (v) => (v.paid ? "Paid" : "Paying");`
- An array gives parent states: `export const state = (v) => v.main.split(".");`
- An object gives one parallel region for each key: `export const state = (v) => ({ Playback: v.playback, Volume: v.volume });`

Label each state with what the reader can see or cares about, such as "Paying" or "Lease held, write pending". Keep variable names out of labels. In `vars`, a TLA+ sequence is an object with keys from 1, so `v.pc[1]` is `pc[1]`. A set is an array.

The view can also export `step(action, from, to)`. It gets the TLC action name and the values before and after the step, and returns the arrow label.
Write each step label as the user sees it happen, such as "you press play" or "the connect fails". Do not name the code or the TLA+ action. Two actions that end the same in the chart get the same label, so they share one arrow.

When a step can occur only in some conditions, end its label with the condition in brackets, in the reader's words, such as `you press play [while the file loads]`.
In a regions chart, the command writes the condition on the other regions on the arrow (`[when Offline]`); your brackets replace it, so do not write brackets for a condition on another region.
When a value that no label shows decides where a step goes, name the result in the label, such as "the roster read fails".

The view can also export these:

- `group(vars)` returns the name of a phase. Each chart state gets the color of its group. When the model states behind one chart state are in different groups, that state gets no color.
- `colors` gives each group name a color class.
- `title` is a string that the chart shows at the top.

The command calls `state()` and `group()` at most once for each model state, and `step()` at most once for each step. The chart and the report both use those answers, so make each function depend only on its arguments.

The chart does not draw a step that stays in one label. Split a label when the reader must see such a step.

Aim for about 20 arrows or fewer. First return coarser labels from `state()`, giving one label to values that act the same and omitting details the reader does not need.
Keep each state of a bug path and keep each mark: merging a `breaks` state into `mayBreak` hides where a rule breaks, and merging two states that break different rules hides which rule breaks where.
If the chart is still too busy, return `null` from `step()` for steps the reader does not need, obeying these rules:

- Keep each chart state reachable by arrows from a start state.
- Keep at least one arrow out of each chart state that has a step out in the model.
- Hide all the steps of an arrow, or none of them. When you hide only some, its condition gets narrower.
- In the hand-off, say which steps the chart hides.

## Read the report

- In the chart, a state that breaks a rule has class `breaks`; when only some model states behind it break the rule, it has class `mayBreak`. The Legend names the rules of each mark.
  When two rules break on one mark, say in the hand-off which state breaks which rule. In a regions chart, a state gets a mark when every combination with it can break a rule, or all states in a breaking combination get marked when none would otherwise.
- TLC goes past a state that breaks a rule, so the chart shows the states after a bug. Keep constants small or add a CONSTRAINT so unbounded models terminate.
- With a VIEW or a SYMMETRY, TLC counts equivalent states as one state and draws that one state; an arrow can lead to it rather than the step's exact target, and the report says so.
- TLC checks rules in each state past a CONSTRAINT or ACTION_CONSTRAINT without exploring further or checking deadlock there; if a shortest bug path ends in such a state or excluded step, the chart draws that endpoint only.
- The command runs TLC with one worker, removing each broken rule and rerunning until none break. After the first break, reruns cap at 100,000 distinct states and list remaining rules under "Rules not checked" if hit.
  The bound module alters variable order, so a property counterexample can differ from an unbounded run.
- `tlc.out` holds TLC's output on the config as written (`tlc-RULE.out` when a later rerun found a rule's path). With `-XX:+UseParallelGC`, TLC's repeated first warning appears once in `tlc.out`.

## Show the chart

Show `chart.mmd` to the user as a `mermaid` code block. Up to 500 TLC states, the full chart is drawn; above 500, only bug paths are drawn (and no `chart.mmd` is written if no rule breaks, though `report.md` still records state counts).
Render SVG/image charts with Pele per `references/render.md` unless the user asks for another renderer.

## Hand off

Give each chart and its Mermaid text to the person who must decide. Add one line for each bug: the rule, the reader's sentence for that rule, and the path as the report numbers it. Say what the model leaves out, and give the command to regenerate into a new `--out` folder.

When the model describes code, replay each bug path against the real code as a test or live repro, one step per action. If a bug does not occur, treat the model as wrong until proven otherwise.

## Done when

The report and chart (or the stated size-budget reason for no chart) exist, each failed rule has a plain-language path, and the limits are explicit.
A model finding about code has been replayed against that code, or is labeled unconfirmed rather than a proven product bug.
