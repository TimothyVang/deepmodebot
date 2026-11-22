## 1. Workflow: job → plan → diverge → build → motion pass → verify live → critique

1. **Start with the job.** Name who acts, what they're trying to do, the object, and what the system will change. List the reachable states before drawing pixels. [vercel-agents-design-guidance]
2. **Write a token plan before any code** [anthropic frontend-design skill]:
   - Color: OKLCH seeds (brand, neutral tint, each status) on one shared lightness scale, named by role (`bg-subtle`, `fg-muted`, `border-strong`), not by hue. Hex is only an sRGB fallback; see §6a. [youtube/_batch-visual-design]
   - Type: typefaces and the role of each.
   - Layout: a one-line concept plus an ASCII wireframe, including alignment.
   - Principles: what makes this UI specific.
3. **Check the plan against the brief.** For any part you would produce for *any* similar page, revise it and say what changed. [anthropic frontend-design skill]
4. **Extract reference style, bootstrap smartly, then diverge** [`aistudio.google.com/learn/ai-ui-design-google-ai-studio`]:
   - Before generating, answer emotional territory, anti-goals, references, and audience [youtube/v42opQpCy60]. Pull real shipped mobile & web references from `references/patterns/mobbin-shipped-apps.md` and `references/patterns/mobbin-animations.md`; when referencing a website or web app from Mobbin, **visit the live site directly at `1440×900` and `390×844`** to inspect its real computed CSS curves, typography scale, OKLCH tokens, and mobile touch UX rather than guessing from a static thumbnail. Upload 1+ screenshots (or extract a 5–6 sentence design-system spec first and map hex approximations into OKLCH role tokens) [youtube/AApjEHsMkTU].
   - For complex multimodal UIs facing a blank canvas, remix/clone a proven working reference applet first to inherit tested layout and state structure before adapting domain copy and tokens.
   - When an app works functionally but feels visually flat, generate 2–4 logic-preserving **Design Variations** behind a live picker along named axes (*Editorial & Refined*, *Technical & Systematic*, *Warm & Approachable*), strictly preserving forms, state, and handlers [.claude/skills/prototype; youtube/r2P1v64pM28].
   - Test-drive real Google Fonts pairings (`Space Grotesk`, `Playfair Display`, `DM Sans`, etc.) live on rendered headings and body copy before locking global typography tokens.
   - For agent features, prototype the agent's *behavior* in working code (sliders for tone, proactiveness, caution, and concision on the real system prompt) before polishing visuals [youtube/CiMVKnX-CNI].
5. **Build with real content and cohesive bespoke imagery.** Real copy and real data shapes [anthropic frontend-design skill]; never ship grey placeholder boxes or broken stock image URLs. Generate cohesive high-res hero/card assets upfront (`generate_image` / Nano Banana or project asset pipeline) with matched lighting and framing, then retouch lighting/backdrops or swap in local brand assets in place rather than regenerating the whole app [`aistudio.google.com/learn/ai-ui-design-google-ai-studio`].
6. **Separate the passes: build → direct DOM spacing pass → Annotate declutter pass → motion pass (`animate`) → critique** [youtube/Ysr7oNDajJI; `aistudio.google.com/learn/ai-ui-design-google-ai-studio`]:
   - Inspect individual DOM elements directly to dial in padding, margins, dimensions, and container proportions (e.g., `"70% width split"`) instead of guessing pixel tweaks in blind chat prompts.
   - Run a visual **Annotate declutter pass**: circle non-essential chips, redundant status badges, and overlapping boxes on a screenshot and strip them cleanly without breaking layout.
7. **Verify the rendered surface** in a browser, in two tiers [youtube/xOO8Wt_i72s]:
   - **After every UI change:** open each changed view, check it against the brief, take a 1440 px screenshot, read the console.
   - **Before a PR or a large refactor:** a phased review:
     - the live flow and every reachable state at 1440 / 768 / 375 px;
     - keyboard, focus, labels and contrast;
     - overflow and loading / empty / error;
     - the console.
   - Also check on a phone or at throttled frame rates.
   - Prefer the browser tool's accessibility snapshot to coordinate clicking; a poor snapshot is itself a finding.
   - Never claim visual quality from reading code. [vercel; anthropic harness; youtube/r2P1v64pM28]
   - **Agent UI is verified against scripted streams first:** `@shadcn/helpers/ai-sdk` `createChat()` replays approve, deny, error, preliminary, long-output and stopped states through the real `useChat`, with no model or network. Only then try a real model. [github/ai-ui/shadcn-ui-chatbot-template]
8. **Critique with a separate pass** that is told to be skeptical, scoring the §2 rubric. Self-grading skews positive. Motion reviews end in an explicit **Block** or **Approve**. [anthropic harness; .claude/skills/review-animations] Rendered video is critiqued with timestamped notes instead of scores (§5a).
