# live-view

**Use when:** by default, on every task beyond a one-line answer: the human should *see* the work, not read a wall of text. It is automatic: never wait for a command or for the human to ask.
Skip it for a short answer, a one-line fix, or when no browser is available; plain Markdown is better there.

The live view is a local AG-UI 1.0 server (`assets/live-view/agui.mjs`) and a viewer page built from shadcn/ui's agent components (dark by default): plan checklist, progress, activity trace, messages, diagrams, tables, screenshots, proof lines with evidence, and questions the human answers in the page.
Everything stays on `127.0.0.1` behind a session token; it sends nothing anywhere else. Run every command from the project root: the session lives in `.scratch/live-view/` there.

1. **It opens itself.** In Claude Code the plugin's prompt hook (`assets/live-view/autostart.mjs`) starts the view on the first real prompt in a project, opens the browser once, and adds "deepmode live view is running: <url>" to your context. Then just use it.
   Elsewhere (omp, Codex, Antigravity), when real work starts and `.scratch/live-view/session.json` is missing or its `/health` fails, start `node "<this skill>/assets/live-view/agui.mjs" serve --open` as a background service yourself.
   The human turns it off with `DEEPMODE_LIVE_VIEW=off` or a `.scratch/live-view/off` file; respect both. It stops by itself after 12 idle hours.
   Done when the view is running and the human has its URL (from the hook or from you).
2. **Set the goal and plan.** `agui.mjs plan --goal "<one line>" "<step>" "<step>" …` (or a JSON file of `{id,title,status}`), then `agui.mjs status <id> active|done|blocked "<note>"` as you go.
   Steps are the plan the human approved or the one you chose; keep titles to outcomes ("Login works on mobile"), not actions ("edit auth.ts").
   Done when every step's status matches reality at each report point.
3. **Explain with visuals, not paragraphs.** One idea per visual, titled, at most a few lines of text beside it:
   - `visual mermaid <file|->` for flows, architecture, sequences, state machines, dependency graphs.
   - `visual table <file.json|.csv>` for comparisons, option trade-offs, test results, before/after numbers.
   - `visual image <file>` for screenshots of the real app; `visual code <file>` for the exact diff or output that matters; `visual markdown` for a short structured note.
   Prefer a diagram the human can check against the code over a description of it; label nodes with real file or service names.
   Done when each concept you would otherwise explain in prose has a visual or a reason it does not need one.
4. **Talk while you work.** `agui.mjs say "<markdown>"` for decisions, findings, and what changed, in the same plain short sentences as chat; `step start|finish "<name>"` brackets long operations.
   The terminal reply still carries the full report; the view is for seeing, not a second place to hide information.
5. **Ask in the page when the human must choose.** `agui.mjs ask "<question>" --choices "A|B|C"` blocks until they answer and prints `{"status":"resolved","payload":{"answer":…}}`, or `{"status":"cancelled"}` on skip or timeout.
   Put the options' trade-offs in a `visual table` first. Only real hard stops and genuine product forks are questions (SKILL.md Autonomy); everything else you decide and log. Cancelled means: take the smallest reversible option and say so.
   Done when every question has an answer or a logged decision.
6. **Prove it.** For each claim in the final report, `agui.mjs proof "<claim>" --evidence <screenshot|log file> --cmd "<command that produced it>"`.
   Evidence is the real artifact: a screenshot of the running app, test output, a measured number. Never a mock, never a summary you wrote.
   Done when every "works" or "fixed" claim in the report has a proof card.
7. **Finish.** `agui.mjs done "<one-line summary>"`, leave the server running while the human reads it, and stop it with `agui.mjs stop` when they are done or the session ends.
   The event log `.scratch/live-view/events.jsonl` is the decision trail (show-me-your-work).

**Protocol notes:** events follow AG-UI 1.0 (`https://docs.ag-ui.com/spec/1.0`): plan = `STATE_SNAPSHOT`/`STATE_DELTA`, progress = `STEP_*`, messages = `TEXT_MESSAGE_*`, visuals and proof = `ACTIVITY_SNAPSHOT` (`deepmode.visual`, `deepmode.proof`).
A question ends the run with `RUN_FINISHED` `outcome: {type:"interrupt"}`; the answer is the next run's `resume` (`status` `resolved` or `cancelled`). Any AG-UI client can read the stream at `POST /agui`.

**Done when** the human has seen the plan, the key visuals, every question has an answer or a logged decision, and every claim in the report has a proof card.
