# correct

**Use when:** agents keep repeating the same mistakes in this repo, each time the operator corrects you, or during codebase gardening ("garden the codebase", "pattern buffer", "ban this anti-pattern"). Make each mistake impossible. The codebase is an agent's largest input: any workaround, deprecated API, or anti-pattern left behind gets copied by every future agent as the established pattern.

1. **Watch and buffer (the gardener loop).** Read recent commits, reverts, review comments, agent instruction files, and workaround comments. For recurring smells across many PRs, append findings to a lightweight pattern buffer before spawning fixes so you see the shared root cause instead of patching individual symptoms. A class counts once it happened twice; skip one-offs.
   Done when each class is listed with at least two cited occurrences.
2. **Change the bed at the highest level that works:**
   - **Architecture & directory boundaries:** one owner per state, one supported way per task, explicit boundary directories (e.g. main vs renderer, server vs client) enforced by dependency-graph/lint rules so wrong imports fail; ban nuanced foot-gun APIs (such as raw `useEffect` or imperative timers `setTimeout`/`requestAnimationFrame`/`requestIdleCallback`) in product code and confine them to framework internals; delete old weed examples so agents stop copying them.
   - **Types & deterministic lints:** make the bad state fail to compile; if it still compiles, add a lint/CI check whose error message tells the agent the exact file, type, or supported API to use instead; if legacy occurrences exist, ratchet CI to fail only when a change adds new ones.
   - **Tests & formal checks:** behavioral tests (never tautological tests) or `references/techniques/formal-verification.md` for concurrency/state invariants.
   - **Docs/agent rules last:** only for judgment calls that no deterministic check can express.
   - **Sampling review at high PR volume:** when PR volume outgrows line-by-line review, rigorously sample recent merged PRs to find shared shortcuts and upgrade the environment constraints above, not just one PR.
   - Done when each class has a chosen level and a reason no higher level works.
3. Fix the most frequent classes now, one unit per class (one commit each). Prove each new check fails on a real past mistake. Same command locally and in CI. Exceptions go on the offending line with reason, expiry, and a decision-trail row.
   Done when each fixed class has its own commit and a run showing its check failing on a past mistake.
4. Keep a rule table in the agent instruction file pairing each rule with its enforcer. On a correction: fix the mistake, add the rule; an existing unenforced rule is a repeat → enforce it at the highest level in the same change. Drop rules whose mistake can no longer happen.
   Done when every rule in the table names an enforcer, or is a judgment call marked as docs-only.

**Output:** each class with its evidence, the level picked, and why a higher level didn't work.

**Done when** every class found is fixed or listed as deferred, and the rule table matches the enforcers in the repo.
