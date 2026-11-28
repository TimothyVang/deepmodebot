#!/usr/bin/env bash
# Git guard for Claude Code: a PreToolUse hook on the Bash tool.
# Reads the hook JSON on stdin; exit 2 blocks the call and sends stderr back to the agent.
# Test a command without the harness: git-guard.sh --check 'git reset --hard' (branch rules use the current directory).
# Patterns live in git-guard-patterns.txt beside this script.
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
patterns="$here/git-guard-patterns.txt"

extract_json_field() {
  # Parse the first JSON string value for a given key without jq or printf %b (avoids \c truncation and greedy .*).
  awk -v key="$1" '
    BEGIN { RS = "\0"; ORS = "" }
    {
      s = $0
      pat = "\"" key "\"[ \t\r\n]*:[ \t\r\n]*\""
      if (!match(s, pat)) exit 1
      rest = substr(s, RSTART + RLENGTH)
      n = length(rest)
      out = ""
      i = 1
      while (i <= n) {
        c = substr(rest, i, 1)
        if (c == "\"") {
          print out
          exit 0
        }
        if (c == "\\" && i < n) {
          i++
          e = substr(rest, i, 1)
          if (e == "n") out = out "\n"
          else if (e == "r") out = out "\r"
          else if (e == "t") out = out "\t"
          else if (e == "\"" || e == "\\" || e == "/") out = out e
          else out = out "\\" e
        } else {
          out = out c
        }
        i++
      }
      exit 1
    }
  '
}

resolve_cmd_dir() {
  local base="$1" line="$2" dir="$1" target=""
  # Follow simple `cd <dir> &&` or `cd <dir>;` before git, and `git -C <dir>`.
  if [[ "$line" =~ (^|[[:space:]\;\&\|\(])cd[[:space:]]+(\"?[^\";\&\|\)]+\"?|\x27[^\x27;\&\|\)]+\x27)[[:space:]]*(\&\&|\;) ]]; then
    target="${BASH_REMATCH[2]}"
    target="${target#\"}"; target="${target%\"}"
    target="${target#\'}"; target="${target%\'}"
    if [[ -n "$target" && "$target" != "-" ]]; then
      if [[ "$target" == /* || "$target" =~ ^[A-Za-z]:[\\/] ]]; then
        dir="$target"
      else
        dir="$dir/$target"
      fi
    fi
  fi
  if [[ "$line" =~ git[[:space:]].*-C[[:space:]]+(\"[^\"]+\"|\x27[^\x27]+\x27|[^[:space:]\;\&\|]+) ]]; then
    target="${BASH_REMATCH[1]}"
    target="${target#\"}"; target="${target%\"}"
    target="${target#\'}"; target="${target%\'}"
    if [[ -n "$target" ]]; then
      if [[ "$target" == /* || "$target" =~ ^[A-Za-z]:[\\/] ]]; then
        dir="$target"
      else
        dir="$dir/$target"
      fi
    fi
  fi
  printf '%s' "$dir"
}

work_dir="$PWD"
if [[ "${1:-}" == --check ]]; then
  command_text="${2:-}"
else
  input="$(cat)"
  if command -v jq >/dev/null 2>&1; then
    command_text="$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null)" || command_text="$input"
    hook_cwd="$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)" || hook_cwd=""
  else
    command_text="$(printf '%s' "$input" | extract_json_field command 2>/dev/null)" || command_text="$input"
    hook_cwd="$(printf '%s' "$input" | extract_json_field cwd 2>/dev/null)" || hook_cwd=""
  fi
  work_dir="${hook_cwd:-$PWD}"
fi

if [[ ! -r "$patterns" ]]; then
  echo "git guard: pattern file missing at $patterns; blocking until it is restored." >&2
  exit 2
fi
[[ -n "$command_text" ]] || exit 0
command_text="${command_text//$'\r'/}"         # normalize CRLF so \\\r\n continuations join cleanly
command_text="${command_text//$'\\\n'/ }"      # a backslash-newline continues the command on the next line
command_text="${command_text//$'\t'/ }"        # normalize tabs so portable space patterns match

block() {
  if [[ "$1" =~ (--|jest|vitest|playwright|insta|SNAPSHOT|go\ test|reward-guard|contract-lock|judge_verdicts|record-judge) ]] && [[ ! "$1" =~ ^git\ +(reset|clean|checkout|restore|stash|worktree|branch|filter|update-ref|reflog|gc|push) ]]; then
    echo "Blocked by anti-reward-hacking guard: \"$1\" weakens a verification gate, overwrites golden snapshots, skips checks, or tampers with provenance ledgers." >&2
  else
    {
      echo "Blocked by the git guard: \"$1\" can destroy work or rewrite shared history."
      echo "Use a safe form instead (git stash, a new branch, git push --force-with-lease to your own feature branch, a PR for the default branch),"
      echo "or ask the user to run it themselves."
    } >&2
  fi
  exit 2
}

scrubbed_text="$(printf '%s\n' "$command_text" | sed -E 's/(-m|--message)(=| +)("[^"]*"|'\''[^'\'']*'\'')/\1 ""/g' | grep -vE '^ *(grep|rg|echo|printf) +[^;&|<>()`$]*$' || true)"
clean_patterns="$(tr -d '\r' < "$patterns")"
active="$(printf '%s\n' "$clean_patterns" | grep -vE '^[[:space:]]*(#|@|$)' || true)"
if [[ -n "$active" && -n "$scrubbed_text" ]]; then
  hit="$(printf '%s\n' "$scrubbed_text" | grep -Eo -f <(printf '%s\n' "$active") | head -n 1 || true)"
  [[ -z "$hit" ]] || block "$hit"
  min_hit="$(printf '%s\n' "$scrubbed_text" | awk '
    BEGIN {
      split("iou ssim dice f1 auc accuracy acc precision recall fidelity similarity coverage pass-rate win-rate", m50, " ")
      for (i in m50) fl[m50[i]] = 0.50
      split("clip clip-score ap map bleu rouge", m15, " ")
      for (i in m15) fl[m15[i]] = 0.15
      fl["psnr"] = 10.0; fl["protrusion"] = 0.02; fl["score"] = 0.05; fl["confidence"] = 0.05; fl["symmetry"] = 0.05; fl["cov-fail-under"] = 50.0
    }
    {
      s = tolower($0)
      while (match(s, /(^|[ ;&|(])["'\'']?--((gate-)?mi(n(-[a-z0-9_-]*)?)?|cov-fail-under)["'\'']?( +|=)["'\'']? *[-+]?(inf(inity)?|nan|([0-9][0-9_]*\.?[0-9_]*|\.[0-9_]+)(e[-+]?[0-9_]+)?) *["'\'']?( |;|&|\||\)|$)/)) {
        seg = substr(s, RSTART, RLENGTH)
        s = substr(s, RSTART + RLENGTH - 1)
        val = seg
        sub(/^.*--((gate-)?mi(n(-[a-z0-9_-]*)?)?|cov-fail-under)["'\'']?( +|=)["'\'']? */, "", val)
        sub(/ *["'\'' ;&|)]*$/, "", val)
        if (seg ~ /--cov-fail-under/) {
          tok = "cov-fail-under"
        } else if (seg ~ /--(gate-)?min-[a-z0-9_-]+/) {
          tok = seg
          sub(/^.*--(gate-)?min-/, "", tok)
          sub(/["'\'']?( +|=).*$/, "", tok)
          gsub(/_/, "-", tok)
        } else {
          tok = ""
        }
        gsub(/_/, "", val)
        req = -1
        if (tok == "") { req = 0.50 }
        else if (tok == "p" || tok == "k" || tok == "port" || tok == "ports") { req = -1 }
        else if (tok in fl) { req = fl[tok] }
        else {
          for (k in fl) if (index(k, tok) == 1 && fl[k] > req) req = fl[k]
        }
        if (req >= 0) {
          if (val ~ /^[-+]?(inf(inity)?|nan)$/) { print seg; exit 0 }
          nv = val + 0.0
          if (nv != nv || nv + 1.0 == nv && (nv > 1e307 || nv < -1e307) || nv < req) { print seg; exit 0 }
        }
      }
    }
  ')"
  [[ -z "$min_hit" ]] || block "$min_hit"
fi

branch_rules="$(printf '%s\n' "$clean_patterns" | grep -E '^@branch ' || true)"
if [[ -n "$branch_rules" ]]; then
  while IFS= read -r cmd_line; do
    [[ -n "$cmd_line" ]] || continue
    while read -r _ branch_regex command_regex; do
      hit="$(printf '%s\n' "$cmd_line" | grep -Eo -e "$command_regex" | head -n 1 || true)"
      [[ -n "$hit" ]] || continue
      eff_dir="$(resolve_cmd_dir "$work_dir" "$cmd_line")"
      branch="$(git -C "$eff_dir" symbolic-ref --short -q HEAD 2>/dev/null || true)"
      if [[ -n "$branch" && "$branch" =~ ^($branch_regex)$ ]]; then
        block "$hit (on $branch)"
      fi
    done <<< "$branch_rules"
  done <<< "$command_text"
fi
exit 0
