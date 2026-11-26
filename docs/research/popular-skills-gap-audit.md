# Popular Agent-Skills Ecosystem Gap Audit (2026-11-25)

Observed on 2026-11-25 via GitHub REST APIs across the top-starred open agent-skill repositories. All shipped additions in `plugins/deepmodebot/` are clean-room MIT implementations and deterministic Python verifiers; upstream repositories are cited here for capability comparison and license boundaries only.

## Surveyed repositories

| Repository | Stars (2026-11-25) | License | Scope & coverage status in `deepmodebot` |
|---|---:|---|---|
| `obra/superpowers` | 326.7k | MIT | 15 workflow skills (`brainstorming`, `writing-plans`, `subagent-driven-development`, `systematic-debugging`, `test-driven-development`, `using-git-worktrees`, `verification-before-completion`, `requesting/receiving-code-review`). Covered by `grill`, `product-lens`, `spec`, `tickets`, `phased-build`, `bug-fix`, `tdd`, `contain`, `pr-review`, and `pr-conversation`. |
| `mattpocock/skills` | 321.9k | MIT | 39 skills pinned in `evals/workflows/sources/mattpocock.json` (`6f7f7831a6`): all 27 plugin-listed skills mapped. |
| `anthropics/skills` | 200.6k | Custom / Mixed | 20 skills; top non-UI gap was document engineering (`xlsx`, `pptx`, `docx`, `pdf`) → closed via clean-room `skill://office-documents` + `doc_audit.py`. `mcp-builder`, `frontend-design`, `webapp-testing`, and `skill-creator` are covered by `agent-harnesses`, `frontend-ui`, `create-verification-skill`, and `authoring-a-skill`. |
| `garrytan/gstack` | 142.7k | MIT | 70 skills; core build/review/ship/browser/retro flows were already covered, while `modernize`, `canary`, `document-release`, `plan-devex-review`/`devex-review`, and `plan-ceo-review`/`office-hours` exposed concrete lifecycle gaps → closed via `modernize-pr`, `release-and-canary`, `devex-review`, and `product-lens`. |
| `addyosmani/agent-skills` | 120.5k | MIT | 26 engineering skills; `deprecation-and-migration`, `observability-and-instrumentation`, and `api-and-interface-design` gaps → closed via `expand-contract`, `release-and-canary`, and `devex-review`. |
| `pbakaus/impeccable` | 117.0k | Apache-2.0 | Design vocabulary & anti-AI-slop critique → covered by `skill://frontend-ui` (`02-review-rubric.md`, `03-ai-tells.md`, `ui_audit.py`). |
| `cloudflare/security-audit-skill` | 78.4k | MIT | Multi-phase diff security audit → already integrated in `assets/security-audit/audit-pr.sh`, now paired with fast cross-platform `static_sec_audit.py` (`deepmodebot gate sec`) so Windows and non-`claude` environments get deterministic CI/crypto/sink checks in `<1s`. |
| `vercel-labs/agent-skills` | 34.9k | Unspecified | React/Next.js composition, View Transitions, and Core Web Vitals → covered by `skill://frontend-ui` + `skill://seo-and-geo`. |
| `AgriciDaniel/claude-seo` | 32.5k | MIT | 40 SEO/GEO/schema/agentic-browsing skills → closed via clean-room `skill://seo-and-geo` + `seo_audit.py` (`deepmodebot gate seo`). |
| `openai/skills` | 29.1k | Mixed | 44 `.curated`/`.system` skills (`cli-creator`, `security-threat-model`, `security-ownership-map`, `security-best-practices`, `playwright`, `pdf`) → covered by `devex-review`, `security-audit`, `variant-analysis`, `visual-e2e`, and `office-documents`. |
| `cursor/plugins` (`pstack`) | — | MIT | 84 shipped workflows (`v0.15.48`, `b1fbf4b60a`) → **100% mapped** and structurally enforced in `evals/workflows/run.py` and `scripts/check.py`. |
| `google/elephant-goldfish-model` | 23.0k | Apache-2.0 | Drift reporting and review loops → covered by `self-grill`, `modernize-pr`, `maintain-verification-skill`, and `maintain-formal-verification-skill`. |
| `trailofbits/skills` | 8.4k | CC-BY-SA-4.0 | **Reference-only (ShareAlike license — zero prose or code copied).** High-level public security concepts (variant analysis, mutation/property testing, GitHub Actions workflow hardening, constant-time MAC comparisons) informed clean-room MIT `variant-analysis.md`, `mutation-testing.md`, and `static_sec_audit.py`. |

## Summary of capabilities added in this upgrade

1. **`skill://seo-and-geo` (`plugins/deepmodebot/skills/seo-and-geo/`):** Technical SEO, Core Web Vitals (`LCP`/`INP`/`CLS`), Schema.org JSON-LD, GEO/AEO citation formatting, `/llms.txt`, AI search vs training crawler `robots.txt` rules, Lighthouse Agentic Browsing readiness, and zero-dependency `scripts/seo_audit.py` (`deepmodebot gate seo`).
2. **`skill://office-documents` (`plugins/deepmodebot/skills/office-documents/`):** Spreadsheet formula modeling (`.xlsx`), widescreen presentation geometry (`.pptx`), semantic Word documents (`.docx`), PDF generation/form-filling (`.pdf`), and zero-dependency OOXML/PDF formula & broken-relationship auditor `scripts/doc_audit.py` (`deepmodebot gate docs`).
3. **Cross-platform static security & CI workflow gate (`assets/security-audit/static_sec_audit.py`, `deepmodebot gate sec`):** Catches `pull_request_target` untrusted checkouts, `${{ ... }}` GitHub Actions script injection, unpinned third-party actions, timing-unsafe HMAC comparisons, unsafe `yaml.load`/`pickle`, and SQL f-strings in `<1s` on Windows, macOS, and Linux.
4. **Seven new techniques (`references/techniques/`):**
   - `variant-analysis`: `(Source, Missing Guard, Sink)` generalization, sibling entry-point matrix, AST/taint sweep, and CI rule promotion.
   - `mutation-testing`: isolated semantic mutant survival measurement + property-based/fuzz invariant hardening.
   - `expand-contract`: zero-downtime 4-phase DB/API migration (expand, dual-write + backfill, shadow-read parity, sunset + contract).
   - `modernize-pr`: aging branch/PR trunk-drift audit (`MODERNIZE` / `SALVAGE-SLICE` / `CLOSE`).
   - `release-and-canary`: pre-ship 4-question telemetry, numeric canary rollback thresholds, and post-ship doc/changelog sync.
   - `devex-review`: cold-start onboarding stopwatch, dual human/agent CLI (`--json`/`--dry-run`/non-TTY/exit-code) audit, and actionable errors.
   - `product-lens`: painkiller-vs-vitamin check, 60-second time-to-value audit, 5→10-star inversion, and Cut/Keep/Amplify scope table.
