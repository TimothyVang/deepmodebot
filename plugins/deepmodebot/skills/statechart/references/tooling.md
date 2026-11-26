# Tooling and proof

The compiler is optional. Loading the plugin does not run it, install a runtime, or start any automation.
On POSIX systems run `sh <skill dir>/scripts/statechart` (selects Node 22.18–22.x or 23.6+, Bun 1.1.5+, or Deno 2+).
On native Windows run `node --disable-warning=ExperimentalWarning <skill dir>/scripts/statechart.ts` with Node 22.18–22.x or 23.6+ (cleanup uses `janitor.ts` and `kill.ts`, and TLC `\r\n` line endings parse natively).
The commands below assume a repository-root working directory. Resolve `skill` to the installed skill directory when outside this checkout.

## Install the model checker explicitly

Prefer an existing trusted Java 11+ and TLC installation. Set `TLA2TOOLS` to the absolute JAR path and `JAVA` to the Java binary if it is not on PATH.
To obtain the compiler's pinned TLC without using mise:

```sh
mkdir -p .scratch/statechart-tools .scratch/statechart/tmp
curl --fail --location --output .scratch/statechart-tools/tla2tools.jar \
  https://github.com/tlaplus/tlaplus/releases/download/v1.7.4/tla2tools.jar
printf '%s  %s\n' \
  936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88 \
  .scratch/statechart-tools/tla2tools.jar | sha256sum --check -
export TLA2TOOLS="$PWD/.scratch/statechart-tools/tla2tools.jar"
export TMPDIR="$PWD/.scratch/statechart/tmp"
```

On macOS use `shasum -a 256 -c`; on Windows PowerShell verify with `(Get-FileHash .scratch\statechart-tools\tla2tools.jar -Algorithm SHA256).Hash`.
Stop if checksum verification fails. The JAR is downloaded tooling, not a vendored plugin asset.
Without `TLA2TOOLS`, the compiler asks mise for checksum-pinned TLC 1.7.4 and `java@temurin-25`; that path can download tools on first invocation.
The Java major version is pinned, not an exact Java patch build. Record `java -version` with evidence.

## Live model-checking scenario

The shipped media-player model lets someone increase the volume while playback is stopped.
Its `LoudWhenStopped` invariant fails after one action. The fixed model guards that action.
These are synthetic models, not evidence about any real media-player application.

```sh
skill="$PWD/plugins/deepmodebot/skills/statechart"
node --disable-warning=ExperimentalWarning "$skill/scripts/statechart.ts" \
  "$skill/scripts/test/corpus/MediaPlayer/MediaPlayer.tla" \
  --view "$skill/scripts/test/corpus/MediaPlayer/view.mjs" \
  --out "$PWD/.scratch/statechart/media-broken"
# Expected exit 1: model violation; inspect report.md, chart.mmd, and tlc.out.
node --disable-warning=ExperimentalWarning "$skill/scripts/statechart.ts" \
  "$skill/scripts/test/corpus/MediaPlayerFixed/MediaPlayerFixed.tla" \
  --view "$skill/scripts/test/corpus/MediaPlayerFixed/view.mjs" \
  --out "$PWD/.scratch/statechart/media-fixed"
# Expected exit 0: the bounded fixed model passes; chart.mmd still exists.
```

Each output directory must be new or empty. Use a fresh name on later runs; never overwrite evidence.
Exit `0` means TLC passed the supplied configuration; `1` means a rule broke; `2` means execution failed.
Signals SIGINT/SIGTERM return `130`/`143`. Only successful checks and genuine violations publish output.
A passing abstract model does not prove that production code implements it.

## Render an SVG

Install `pele@1.9.0` with `npm install --prefix .scratch/statechart-tools --no-audit --no-fund --save-exact pele@1.9.0`.
Load `pele` from that prefix with Node's `createRequire`, then call `render` on the generated Mermaid text.
Follow `references/render.md` for the size limits and the CSS that preserves bug marks in dark and light themes.
Write the returned `svg` beside `chart.mmd` as `chart.svg`; retain the Mermaid source and report even if rendering fails.
Pele is rendering only: the compiler and model checker do not depend on it.

## Maintainer tests

The source-pinned compiler includes its original parser, lowering, graph, CLI, rendering, and differential tests and synthetic corpus.
For the deterministic parser/pipeline/chart suite (no npm install or TLC required; also executed by the repository check gate when Node is available):

```sh
node --disable-warning=ExperimentalWarning --test \
  plugins/deepmodebot/skills/statechart/scripts/test/pipeline.test.ts \
  plugins/deepmodebot/skills/statechart/scripts/test/messages.test.ts \
  plugins/deepmodebot/skills/statechart/scripts/test/chart.test.ts
```

The full `npm test --prefix plugins/deepmodebot/skills/statechart/scripts` needs Node's native TypeScript support and `fast-check@4.5.3` from that package's development dependencies.
Set `TLA2TOOLS` and a working Java/Javac for live TLC and Java-oracle coverage; tests otherwise skip some live checks.
Rendering tests install `pele@1.9.0`, `mermaid@11.16.0`, and `jsdom@26.1.0` into a cache and need network access.
Set `XDG_CACHE_HOME` to an absolute directory under `.scratch/` to keep that cache local.
Report skipped tests and runtime/tool versions rather than treating a partial suite as complete coverage.
