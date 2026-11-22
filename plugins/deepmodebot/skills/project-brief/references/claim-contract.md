# Claim and overlap contract

Shared contract used by `skill://project-brief`, `skill://contribute`, `scripts/pr-overlap.py`, and `scripts/sync-roadmap.py`. Don't invent variants.

## Labels

- `help wanted`: claimable task.
- `good first issue`: small, well-scoped task.
- `claimed`: optional, maintainer-set.

## Claim comment

One issue comment in this exact shape (marker line first, nothing else in the comment):

```text
<!-- deepmodebot:claim -->
Claimed by @<login> via /contribute
Plan: <one line>
Files: <comma-separated repo paths; a trailing "/" means a whole directory>
Expires: <YYYY-MM-DD, 7 days after posting>
```

- `<login>`: `gh api user -q .login`
- `Expires`: `python -c "import datetime as d;print(d.datetime.now(d.timezone.utc).date()+d.timedelta(days=7))"` (UTC).
- Your newest claim comment on an open issue is your claim: it replaces earlier ones and never changes anyone else's. To renew or change `Files`, post a new claim comment; don't edit the old one.

## Unclaim comment

To release, post a comment from the same account containing `<!-- deepmodebot:unclaim -->`:

```text
<!-- deepmodebot:unclaim -->
Released by @<login>: <one-line reason>
```

## Active claim & assignees

- **Active claim:** An author's newest claim comment on an open issue is active while `Expires` is today or later and that author has posted no later `<!-- deepmodebot:unclaim -->` comment. Every active claim counts; one person's claim, expiry, or withdrawal never changes another's.
- **Assignees:** An assignee also counts as a claim on the issue (not on any files), unless they posted a claim comment on it. Then only that comment counts: once it expires or is released, the assignment stops counting.
- **One issue = one branch = one PR.** The PR body says `Closes #N`.

## Overlap & `pr-overlap.py`

Two path sets overlap when a path is equal or one is a directory prefix (`dir/`) of the other. Paths are repo-relative with forward slashes.

Use the repo's `scripts/pr-overlap.py` when it exists, else the plugin's copy (`skill://project-brief/assets/pr-overlap.py`, or `<contribute base dir>/../project-brief/assets/pr-overlap.py` in Claude Code):

```bash
OVERLAP=scripts/pr-overlap.py; [ -f "$OVERLAP" ] || OVERLAP="skill://project-brief/assets/pr-overlap.py"
python "$OVERLAP" claims --repo R --json
python "$OVERLAP" check --repo R --files a,b,dir/ --exclude-issue N
```

- `check` exit codes: `0` no overlap, `3` overlap (read the table), `2` usage or `gh` error (fix it; an error is not a pass).
- Say which copy you used. Every `check` after claiming must pass `--exclude-issue N` (and `--exclude-pr <your PR>` once your PR exists), otherwise your own claim reports as overlap.
