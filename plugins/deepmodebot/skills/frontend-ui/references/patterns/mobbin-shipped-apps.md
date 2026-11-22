# Patterns from shipped apps & live sites (Mobbin)

Real, shipped products across **iOS Mobile**, **Web Apps**, and **Live Websites**, harvested from Mobbin (`mobbin.com`, checked 2026-11-21 across signed-in iOS/Web discovery, 8 unwalled mobile collections totaling 877 screens & 86 animation clips, all 59 Mobbin Design Glossary guides, and direct `1440px` + `390px` live DOM inspection of 24 Mobbin-featured sites/webapps). For motion & animation lessons, also read `references/patterns/mobbin-animations.md`.

## 1. Web app screen & flow facets

| Pattern (facet) | Total on Mobbin | Shipped examples | What it shows |
| --- | --- | --- | --- |
| Chat Bot (`screenPatterns.Chat+Bot`) | 524 web / 823 iOS | `Strut`, `Linear`, `ChatGPT`, `Claude`, `Gemini`, `Revolut` | **Strut:** 3-pane workspace with AI chat docked right and inline `"Create a doc"` reply action. **Linear:** calm empty-state home with centered composer + 3 capability cards (§4a). **iOS (`ChatGPT`, `Claude`, `Gemini`):** keyboard-pinned pill composer, vanishing starter chips, and distraction-free full-screen voice orb |
| Settings & Preferences (`screenPatterns.Settings+%26+Preferences`) | 3,202 screens | `Attio`, `Patreon`, `Monarch` | Left grouped settings nav + single narrow form column (`Patreon` puts one solid primary Save at the end; `Attio` groups profile fields in subtle cards) |
| Notifications (`screenPatterns.Notifications`) | 612 screens | `Bonsai`, `Deel` | **Bonsai:** dashboard right-hand activity rail. **Deel:** bell-anchored popover with tabs and inline per-item approve/dismiss actions |
| My Account & Profile (`screenPatterns.My+Account+%26+Profile`) | 369 screens | `Peerlist`, `Duolingo` | Compact identity header card followed by `2×2` tabular stat tiles (`Duolingo`) and grouped action rows |
| Charts (`screenPatterns.Charts`) | 1,404 screens | `beehiiv`, `Cake Equity`, `Monarch` | KPI summary strip → primary time-series or allocation chart → contextual activity rail |
| Side Navigation (`screenElements.Side+Navigation`) | 1,566 UI | `PandaDoc`, `OpenSea`, `Linear` | Workspace switcher at top, grouped nav sections, and optional `"Get started"` setup progress card (`n of m`) in rail; collapses to icon rail beside dense tables |
| Progress & Stepper (`Progress+Indicator`, `Stepper`) | 2,130 UI | `Zoom`, `Uniswap`, `Superpower` | Numbered vertical checkout/setup steppers (`Zoom`) and bounded liquidity/swap cards (`Uniswap`) |
| File Upload (`screenElements.File+Upload`) | 1,157 UI | `Shopify`, `VEED` | Inline dropzone on desktop forms (`Shopify`, `VEED`); **on mobile**, replace drag-and-drop boxes with a native Camera / Photos / Files action sheet |
| Onboarding & Setup (`Onboarding`, `Setting+Up`) | 1,450 flows | `Remote`, `Shopify`, `Aave`, `DoorDash` | **Web:** split-screen form + live product preview (`Remote`) or 1-question centered card (`Shopify`). **Mobile (`DoorDash`, `Aave`):** instant value visual + primary CTA + `"Browse first"` guest escape hatch |
| Filtering & Sorting (`Filtering+%26+Sorting`) | 2,016 flows | `Deel`, `Airbnb` | **Web:** multi-select checkbox popover anchored to `Filter`. **Mobile:** bottom sheet with live result count on the sticky primary button (`Show 42 stays`) |

## 2. Mobile (`iOS` / `Android`) UI architecture lessons

Distilled from **DoorDash, Aave, Headway, OpenTable, Airbnb, Luma, Opal, How We Feel, stoic., Superlist, Cash App, Monzo, Chase UK, Tesla, N26, Arc Search, and Claude/ChatGPT iOS**:

- **Thumb-zone hierarchy:** Anchor primary navigation (`Tab Bar`, `3–5` destinations max) and primary transactional CTAs (`48–56 px` tall pills) in the bottom third above `env(safe-area-inset-bottom)`. Keep top bars strictly for title, back chevron, and at most 1–2 secondary icon buttons.
- **Card density & glanceability:** Top consumer mobile apps (`DoorDash`, `Airbnb`, `Luma`, `Headway`) pair full-bleed imagery (`16–24 px` outer radius, concentric inner radii) with **at most 3 text lines per card** (primary title, muted metadata row `4.7 ★ · 20 min`, bold tabular price/CTA).
- **Dark-surface restraint (`Opal`, `Ladder`, `WHOOP`, `Cash App`, `Tesla`):** Use deep tinted charcoal or true OLED black (`#000` on workout/lock-screen glanceable views) with **one** focal 3D/data object and oversized tabular numerals—never competing neon cards.
- **Calm critical, offline & permission states (`Chase UK`, `N26`, `Kraken`, `Lyft`, `Slack`, `IKEA`):**
  - Keep cached content visible with a compact top banner (`Offline · Updated 4m ago`) instead of wiping the screen.
  - Permission prompts (Camera, Location, Notifications) explain the concrete user benefit first with a 1-tap `Open Settings` primary button and neutral `Not now` dismissal—never red error styling for declined optional permissions.
- **Honest paywalls & full-screen overlays (`Headway`, `Opal`, `Ladder`):** Always keep the `×` close button immediately legible (`>= 4.5:1` contrast, `44 px` hit target); camouflaging `×` into the header image is a dark pattern flagged by Mobbin's Full-Screen Overlay guide.

## 3. Component selection matrix (from all 59 Mobbin Glossary guides)

| User job | Mobile pick | Web pick | Hard rule / anti-pattern |
| --- | --- | --- | --- |
| **Top-level navigation (`3–5` areas)** | Bottom `Tab Bar` | Left `Side Navigation` or top bar | Never put `>5` items in a mobile Tab Bar (`>5` → `Drawer`); never put infrequent settings in a Tab Bar |
| **Supplementary context / filters** | `Bottom Sheet` (`peek` / `expanded` detents) | `Popover` (small) or side `Drawer` (tall) | Avoid Bottom Sheets when the task needs full-screen focus or constant back-and-forth toggling |
| **`3–5` quick actions on an item** | `Action Sheet` (tap) or `Context Menu` (long-press) | `Dropdown Menu` or right-click `Context Menu` | Never hide primary actions in a long-press menu; always include a separated `Cancel` on Action Sheets |
| **`2–4` equal, instant view switches** | `Segmented Control` (sliding pill) | `Tabs` or `Segmented Control` | Switch view **immediately** without a Save button; `5+` options → `Select` / `Combobox` |
| **Numeric input by range** | `Stepper` (`1–10`) or horizontal **tick ruler scrubber** (`10–500`) | `Stepper`, `Slider`, or numeric `<input>` | Avoid Steppers for large ranges (`100+`); avoid popping mobile OS keyboards when a scrubber or preset chips work |
| **Transient feedback** | Bottom/top `Snackbar` / `Toast` (`1` action max) | `Sonner` toast or inline checkmark (for Copy) | Never use Toasts for high-priority errors (`Dialog` / inline field error); max `1` `Banner` visible per screen |
| **Empty & first-run screens** | Purpose illustration/icon + 1-sentence reason + 1 primary CTA | Same, replacing empty table headers too | Distinguish *First-time use*, *No search results* (offer `Clear filters`), and *All caught up* |

## 4. Live-inspected Mobbin Websites & WebApps (24-site DOM & CSS audit)

When referencing a site or web app spotted on Mobbin, **visit the live URL directly at `1440×900` (desktop) and `390×844` (mobile)** to inspect real computed CSS, typography, and interactions. Measured across **Mercury, Ramp, Superpower, Linear, Stripe, Vercel, Raycast, Clerk, Resend, Attio, Luma, Contra, Monarch, VEED, Mintlify, Dovetail, Cosmos, Sana, Braintrust, n8n, Uniswap, Voicenotes, Ghost, and Antimetal**:

- **Responsive display scale (`0.50×–0.67×` mobile ratio, `0` horizontal overflow on `24/24` sites):** Desktop hero `h1` (`48–80 px`, leading `0.95–1.12`, tracking `-0.02em` to `-0.03em`) scales cleanly to `28–44 px` at `390 px` (`Mercury` `49→28 px`, `Ramp` `64→40 px`, `Linear` `64→38 px`, `Clerk` `56→32 px`, `Luma` `80→40 px`), with **`text-wrap: balance`** active on **`17/24` (`71%`)** sites.
- **Perceptual color & layered elevation (`11/24` shipping `oklch()` / `lab()`):** Modern web apps (`Vercel`, `Attio`, `Ramp`, `Mintlify`, `Cosmos`, `Braintrust`, `Uniswap`) pair `1 px` low-alpha borders with 3-step OKLCH shadows (`oklch(0 0 0 / 0.01..0.03)`) or `1 px` top inset highlights (`Superpower`) rather than heavy `rgba(0,0,0,0.15)` drop shadows.
- **Mobile-web header adaptation:** Desktop multi-group navbars collapse at mobile widths into a `48–74 px` bar with a `40–48 px` menu hit target opening `48 px`-tall full-width tap rows (`Mercury`) plus one visible primary pill CTA (`Contra`, `Sign up` `48 px` tall).
