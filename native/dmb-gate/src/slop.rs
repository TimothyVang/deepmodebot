use crate::util::{glob_match, json_escape, parallel_map};
use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};
use std::thread;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Finding {
    pub severity: &'static str,
    pub rule: &'static str,
    pub file: String,
    pub line: usize,
    pub message: String,
    pub fix: &'static str,
}

const GUARDRAIL_CONFIGS: &[&str] = &[
    ".deepmodebot/ci.yml",
    ".deepmodebot/policy.xml",
    ".github/dependabot.yml",
    "ruff.toml",
    ".ruff.toml",
    "pyproject.toml",
    "tsconfig.json",
    "biome.json",
    "eslint.config.js",
    "eslint.config.mjs",
    ".eslintrc.json",
    ".prettierrc",
    ".pre-commit-config.yaml",
    "lefthook.yml",
];

fn git(root: &Path, args: &[&str]) -> Option<(bool, String)> {
    let out = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .ok()?;
    Some((
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
    ))
}

fn changed_files(root: &Path, staged: bool, explicit: &[String]) -> Vec<String> {
    if !explicit.is_empty() {
        let mut set = BTreeSet::new();
        for raw in explicit {
            for part in raw.split(',') {
                let mut n = part.trim().replace('\\', "/");
                while let Some(rest) = n.strip_prefix("./") {
                    n = rest.to_string();
                }
                let n = n.trim_start_matches('/').to_string();
                if !n.is_empty() {
                    set.insert(n);
                }
            }
        }
        return set.into_iter().collect();
    }
    let mut set = BTreeSet::new();
    let has_head = git(root, &["rev-parse", "--verify", "HEAD"])
        .map(|(ok, _)| ok)
        .unwrap_or(false);
    if staged {
        if let Some((true, out)) =
            git(root, &["diff", "--cached", "--name-only", "--diff-filter=ACMR"])
        {
            for l in out.lines().map(str::trim).filter(|l| !l.is_empty()) {
                set.insert(l.to_string());
            }
        }
    } else {
        if has_head {
            if let Some((true, out)) =
                git(root, &["diff", "HEAD", "--name-only", "--diff-filter=ACMR"])
            {
                for l in out.lines().map(str::trim).filter(|l| !l.is_empty()) {
                    set.insert(l.to_string());
                }
            }
        } else if let Some((true, out)) = git(root, &["ls-files"]) {
            for l in out.lines().map(str::trim).filter(|l| !l.is_empty()) {
                set.insert(l.to_string());
            }
        }
        if let Some((true, out)) = git(root, &["ls-files", "--others", "--exclude-standard"]) {
            for l in out.lines().map(str::trim).filter(|l| !l.is_empty()) {
                set.insert(l.to_string());
            }
        }
    }
    set.into_iter().collect()
}

fn added_lines_for_file(root: &Path, rel: &str, staged: bool) -> Vec<(usize, String)> {
    let full = root.join(rel);
    let Ok(meta) = fs::symlink_metadata(&full) else {
        return Vec::new();
    };
    if meta.file_type().is_symlink() || !meta.is_file() || meta.len() > 1_048_576 {
        return Vec::new();
    }
    let has_head = git(root, &["rev-parse", "--verify", "HEAD"])
        .map(|(ok, _)| ok)
        .unwrap_or(false);
    let tracked = git(root, &["ls-files", "--error-unmatch", "--", rel])
        .map(|(ok, _)| ok)
        .unwrap_or(false);
    if (!has_head || !tracked) && !staged {
        let Ok(txt) = fs::read_to_string(&full) else {
            return Vec::new();
        };
        return txt
            .lines()
            .enumerate()
            .map(|(i, l)| (i + 1, l.to_string()))
            .collect();
    }
    let args: Vec<&str> = if staged {
        vec!["diff", "--cached", "-U0", "--", rel]
    } else {
        vec!["diff", "HEAD", "-U0", "--", rel]
    };
    let Some((true, diff)) = git(root, &args) else {
        return Vec::new();
    };
    let mut out = Vec::new();
    let mut cur_line: usize = 0;
    for raw in diff.lines() {
        if let Some(rest) = raw.strip_prefix("@@ ") {
            if let Some(plus_idx) = rest.find('+') {
                let after = &rest[plus_idx + 1..];
                let num: String = after.chars().take_while(|c| c.is_ascii_digit()).collect();
                if let Ok(n) = num.parse::<usize>() {
                    cur_line = n;
                }
            }
        } else if raw.starts_with('+') && !raw.starts_with("+++") {
            out.push((cur_line, raw[1..].to_string()));
            cur_line += 1;
        }
    }
    out
}

fn is_test_file(rel: &str) -> bool {
    let low = rel.to_ascii_lowercase();
    low.starts_with("tests/")
        || low.starts_with("test/")
        || low.starts_with("spec/")
        || low.starts_with("__tests__/")
        || low.contains("/tests/")
        || low.contains("/test/")
        || low.contains("/spec/")
        || low.contains("/__tests__/")
        || low.starts_with("test_")
        || low.contains("/test_")
        || low.contains("_test.")
        || low.contains(".test.")
        || low.contains(".spec.")
}

fn is_alnum_run(s: &str, min_len: usize) -> bool {
    s.len() >= min_len
        && s.bytes()
            .take(min_len)
            .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
}

fn has_secret(line: &str) -> Option<(&'static str, &'static str)> {
    let trim = line.trim();
    if trim.starts_with("re.compile(") || trim.contains("SECRET_PATTERNS") {
        return None;
    }
    if line.contains("-----BEGIN ") && line.contains("PRIVATE KEY-----") {
        let idx = line.find("-----BEGIN ").unwrap_or(0);
        let before = line[..idx].trim_end();
        if !before.ends_with('"') && !before.ends_with('\'') && !before.ends_with("r\"") {
            return Some(("secret-private-key", "Private key PEM block detected."));
        }
    }
    if let Some(pos) = line.find("AKIA") {
        let tail = &line[pos + 4..];
        if tail.len() >= 16
            && tail
                .bytes()
                .take(16)
                .all(|b| b.is_ascii_uppercase() || b.is_ascii_digit())
        {
            return Some(("secret-aws-key", "Hardcoded AWS access key detected."));
        }
    }
    for (prefix, min_len, rule, msg) in [
        ("ghp_", 30usize, "secret-github-token", "Hardcoded GitHub PAT detected."),
        ("github_pat_", 20, "secret-github-token", "Hardcoded GitHub PAT detected."),
        ("sk-ant-", 20, "secret-anthropic-key", "Hardcoded Anthropic API key detected."),
        ("sk-proj-", 20, "secret-openai-key", "Hardcoded OpenAI API key detected."),
        ("AIza", 35, "secret-google-key", "Hardcoded Google API key detected."),
        ("sk_live_", 16, "secret-stripe-key", "Hardcoded Stripe live key detected."),
    ] {
        if let Some(pos) = line.find(prefix) {
            let tail = &line[pos + prefix.len()..];
            if is_alnum_run(tail, min_len) {
                return Some((rule, msg));
            }
        }
    }
    None
}

fn contains_unquoted(line: &str, needle: &str) -> bool {
    let mut start = 0;
    while let Some(rel) = line[start..].find(needle) {
        let idx = start + rel;
        let prev = line[..idx].chars().next_back();
        let next = line[idx + needle.len()..].chars().next();
        let quoted = matches!(prev, Some('"' | '\'' | '`'))
            && matches!(next, Some('"' | '\'' | '`'));
        if !quoted {
            return true;
        }
        start = idx + needle.len();
    }
    false
}
fn is_js_ident_byte(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b == b'_' || b == b'$'
}

fn scrub_js_code_line(line: &str) -> String {
    let bytes = line.as_bytes();
    let mut out = String::with_capacity(line.len());
    let mut quote: Option<u8> = None;
    let mut i = 0;
    while i < bytes.len() {
        let b = bytes[i];
        if let Some(q) = quote {
            if b == b'\\' && i + 1 < bytes.len() {
                out.push_str("  ");
                i += 2;
                continue;
            }
            if b == q {
                out.push(b as char);
                quote = None;
            } else {
                out.push(' ');
            }
            i += 1;
            continue;
        }
        if b == b'/' && i + 1 < bytes.len() && bytes[i + 1] == b'/' {
            break;
        }
        if b == b'/' && i + 1 < bytes.len() && bytes[i + 1] == b'*' {
            if let Some(rel_end) = line[i + 2..].find("*/") {
                let span = rel_end + 4;
                for _ in 0..span {
                    out.push(' ');
                }
                i += span;
                continue;
            } else {
                break;
            }
        }
        if matches!(b, b'\'' | b'"' | b'`') {
            quote = Some(b);
            out.push(b as char);
            i += 1;
            continue;
        }
        let ch = line[i..].chars().next().unwrap_or(' ');
        out.push(ch);
        i += ch.len_utf8();
    }
    out
}

fn has_exact_word(haystack: &str, word: &str) -> bool {
    let bytes = haystack.as_bytes();
    let mut from = 0;
    while let Some(rel) = haystack[from..].find(word) {
        let pos = from + rel;
        let end = pos + word.len();
        from = end;
        let prev_ok = pos == 0 || !is_js_ident_byte(bytes[pos - 1]);
        let next_ok = end >= bytes.len() || !is_js_ident_byte(bytes[end]);
        if prev_ok && next_ok {
            return true;
        }
    }
    false
}

fn has_client_env_secret(line: &str) -> bool {
    let bytes = line.as_bytes();
    for prefix in ["NEXT_PUBLIC_", "VITE_", "EXPO_PUBLIC_", "NUXT_PUBLIC_"] {
        let mut from = 0;
        while let Some(rel) = line[from..].find(prefix) {
            let pos = from + rel;
            from = pos + prefix.len();
            if pos > 0 && is_js_ident_byte(bytes[pos - 1]) {
                continue;
            }
            let ident: String = line[pos..]
                .chars()
                .take_while(|c| c.is_ascii_alphanumeric() || *c == '_' || *c == '$')
                .collect();
            if ident
                .bytes()
                .all(|b| b.is_ascii_uppercase() || b.is_ascii_digit() || b == b'_')
                && ["SECRET", "PRIVATE_KEY", "SERVICE_ROLE", "DATABASE_URL", "WEBHOOK_SECRET"]
                    .iter()
                    .any(|suf| ident.contains(suf))
            {
                return true;
            }
        }
    }
    false
}

fn has_llm_browser_key(js: &str) -> bool {
    let needle = "dangerouslyAllowBrowser";
    let bytes = js.as_bytes();
    let mut from = 0;
    while let Some(rel) = js[from..].find(needle) {
        let pos = from + rel;
        let end = pos + needle.len();
        from = end;
        if pos > 0 && is_js_ident_byte(bytes[pos - 1]) {
            continue;
        }
        let rest = js[end..].trim_start();
        let Some(after_colon) = rest.strip_prefix(':') else { continue };
        let val = after_colon.trim_start();
        if let Some(after_true) = val.strip_prefix("true") {
            if !after_true.bytes().next().map(is_js_ident_byte).unwrap_or(false) {
                return true;
            }
        }
    }
    false
}

fn has_legacy_implements_do(js: &str) -> bool {
    let bytes = js.as_bytes();
    let mut from = 0;
    while let Some(rel) = js[from..].find("class") {
        let pos = from + rel;
        let end = pos + "class".len();
        from = end;
        if pos > 0 && is_js_ident_byte(bytes[pos - 1]) {
            continue;
        }
        if !matches!(bytes.get(end), Some(b' ' | b'\t')) {
            continue;
        }
        let header_end = js[end..].find('{').map(|i| end + i).unwrap_or(js.len());
        let header = &js[end..header_end];
        let hbytes = header.as_bytes();
        let mut hfrom = 0;
        while let Some(irel) = header[hfrom..].find("implements") {
            let ipos = hfrom + irel;
            let iend = ipos + "implements".len();
            hfrom = iend;
            let prev_ok = ipos == 0 || !is_js_ident_byte(hbytes[ipos - 1]);
            let next_ok = matches!(hbytes.get(iend), Some(b' ' | b'\t'));
            if prev_ok && next_ok && has_exact_word(&header[iend..], "DurableObject") {
                return true;
            }
        }
    }
    false
}

fn has_workers_ctx_destructure(js: &str) -> bool {
    let bytes = js.as_bytes();
    for kw in ["const", "let", "var"] {
        let mut from = 0;
        while let Some(rel) = js[from..].find(kw) {
            let pos = from + rel;
            let end = pos + kw.len();
            from = end;
            if pos > 0 && is_js_ident_byte(bytes[pos - 1]) {
                continue;
            }
            if end < bytes.len() && is_js_ident_byte(bytes[end]) {
                continue;
            }
            let rest = js[end..].trim_start();
            let Some(after_open) = rest.strip_prefix('{') else { continue };
            let Some(close_idx) = after_open.find('}') else { continue };
            let inner = &after_open[..close_idx];
            if !has_exact_word(inner, "waitUntil") {
                continue;
            }
            let after_brace = after_open[close_idx + 1..].trim_start();
            let Some(after_eq) = after_brace.strip_prefix('=') else { continue };
            if after_eq.starts_with('=') {
                continue;
            }
            let rhs = after_eq.trim_start();
            if let Some(after_ctx) = rhs.strip_prefix("ctx") {
                if !after_ctx.bytes().next().map(is_js_ident_byte).unwrap_or(false) {
                    return true;
                }
            }
        }
    }
    false
}

pub fn scan_added_lines(rel: &str, lines: &[(usize, String)], out: &mut Vec<Finding>) {
    let ext = Path::new(rel)
        .extension()
        .and_then(|e| e.to_str())
        .map(|s| s.to_ascii_lowercase())
        .unwrap_or_default();
    let test_file = is_test_file(rel);
    let mut in_cfg_test = false;
    for (ln, line) in lines {
        if ext == "rs" && line.trim().starts_with("#[cfg(test)]") {
            in_cfg_test = true;
        }
        if let Some((rule, msg)) = has_secret(line) {
            out.push(Finding {
                severity: "P0",
                rule,
                file: rel.to_string(),
                line: *ln,
                message: msg.to_string(),
                fix: "Remove key material and rotate; load from env or secret manager.",
            });
        }
        if (ext == "yml" || ext == "yaml")
            && rel.starts_with(".github/workflows/")
            && line.contains("uses:")
            && (line.contains("@main") || line.contains("@master"))
        {
            out.push(Finding {
                severity: "P1",
                rule: "supply-chain-unpinned-action",
                file: rel.to_string(),
                line: *ln,
                message: "GitHub Action pinned to mutable @main/@master branch.".to_string(),
                fix: "Pin to full 40-char commit SHA with version comment.",
            });
        }
        if test_file || in_cfg_test {
            continue;
        }
        if ext == "py"
            && (contains_unquoted(line, "# noqa")
                || contains_unquoted(line, "# type: ignore")
                || contains_unquoted(line, "# pyright: ignore"))
        {
            out.push(Finding {
                severity: "P1",
                rule: "suppression-comment",
                file: rel.to_string(),
                line: *ln,
                message: "Inline Python lint/type suppression added.".to_string(),
                fix: "Fix root cause instead of suppressing.",
            });
        }
        if matches!(ext.as_str(), "ts" | "tsx" | "js" | "jsx" | "mjs")
            && (contains_unquoted(line, "@ts-ignore")
                || contains_unquoted(line, "@ts-expect-error")
                || contains_unquoted(line, "eslint-disable"))
        {
            out.push(Finding {
                severity: "P1",
                rule: "suppression-comment",
                file: rel.to_string(),
                line: *ln,
                message: "Inline JS/TS lint/type suppression added.".to_string(),
                fix: "Fix root cause instead of suppressing.",
            });
        }
        if matches!(ext.as_str(), "ts" | "tsx")
            && (contains_unquoted(line, " as any")
                || contains_unquoted(line, " as unknown as "))
        {
            out.push(Finding {
                severity: "P1",
                rule: "ts-unsafe-cast",
                file: rel.to_string(),
                line: *ln,
                message: "Unsafe TypeScript cast added.".to_string(),
                fix: "Use a type guard or validated schema.",
            });
        }
        if ext == "rs" && contains_unquoted(line, ".unwrap()") {
            out.push(Finding {
                severity: "P1",
                rule: "rust-prod-unwrap",
                file: rel.to_string(),
                line: *ln,
                message: "Unwrap call in non-test Rust code.".to_string(),
                fix: "Propagate with `?` or handle explicitly.",
            });
        }
        if ext == "go" && contains_unquoted(line, "_ = err") {
            out.push(Finding {
                severity: "P1",
                rule: "go-ignored-err",
                file: rel.to_string(),
                line: *ln,
                message: "Swallowed Go error (`_ = err`).".to_string(),
                fix: "Check and return or handle `err`.",
            });
        }
        if has_client_env_secret(line) {
            out.push(Finding {
                severity: "P0",
                rule: "client-env-secret",
                file: rel.to_string(),
                line: *ln,
                message: "Client-exposed env prefix names a secret/private/DB credential.".to_string(),
                fix: "Keep secrets in server-only env vars behind a server route or Action.",
            });
        }
        let js_code = if matches!(ext.as_str(), "js" | "mjs" | "cjs" | "ts" | "tsx" | "jsx" | "svelte" | "vue") {
            scrub_js_code_line(line)
        } else {
            String::new()
        };
        if !js_code.is_empty() && has_llm_browser_key(&js_code) {
            out.push(Finding {
                severity: "P0",
                rule: "llm-browser-key-exposure",
                file: rel.to_string(),
                line: *ln,
                message: "`dangerouslyAllowBrowser: true` exposes provider API keys in client bundles.".to_string(),
                fix: "Proxy LLM SDK calls through a server route or Durable Object.",
            });
        }
        if matches!(ext.as_str(), "js" | "mjs" | "ts" | "tsx") && has_legacy_implements_do(&js_code) {
            out.push(Finding {
                severity: "P1",
                rule: "workers-legacy-implements-do",
                file: rel.to_string(),
                line: *ln,
                message: "Legacy `implements DurableObject` omits `this.ctx` and `this.env`.".to_string(),
                fix: "Import `DurableObject` from `cloudflare:workers` and use `extends DurableObject<Env>`.",
            });
        }
        if matches!(ext.as_str(), "js" | "mjs" | "ts" | "tsx") && has_workers_ctx_destructure(&js_code) {
            out.push(Finding {
                severity: "P1",
                rule: "workers-ctx-destructure",
                file: rel.to_string(),
                line: *ln,
                message: "Destructuring `waitUntil` from `ctx` throws `Illegal invocation` at runtime.".to_string(),
                fix: "Call `ctx.waitUntil(...)` directly on `ctx`.",
            });
        }
        if matches!(ext.as_str(), "js" | "mjs" | "cjs" | "ts" | "tsx" | "jsx")
            && (contains_unquoted(line, ".innerHTML =")
                || contains_unquoted(line, "dangerouslySetInnerHTML")
                || contains_unquoted(line, "eval("))
        {
            out.push(Finding {
                severity: "P1",
                rule: "security-unsafe-sink",
                file: rel.to_string(),
                line: *ln,
                message: "Unsafe dynamic sink (`eval`/`innerHTML`/`dangerouslySetInnerHTML`)."
                    .to_string(),
                fix: "Use textContent or sanitized DOM nodes.",
            });
        }
    }
    if ext == "yml" || ext == "yaml" {
        let norm = rel.replace('\\', "/");
        if norm == ".github/dependabot.yml" || norm == ".github/dependabot.yaml" {
            for (ln, line) in lines {
                let eco_line = line
                    .trim_start()
                    .trim_start_matches('-')
                    .trim_start()
                    .starts_with("package-ecosystem:");
                if eco_line {
                    let full = lines
                        .iter()
                        .map(|(_, s)| s.as_str())
                        .collect::<Vec<_>>()
                        .join("\n");
                    if !full.contains("cooldown:") {
                        out.push(Finding {
                            severity: "P2",
                            rule: "supply-chain-dependabot-cooldown",
                            file: rel.to_string(),
                            line: *ln,
                            message: "Dependabot config adds ecosystem without `cooldown` window.".to_string(),
                            fix: "Add `cooldown: { default-days: 7 }` to mitigate freshly published package compromises.",
                        });
                    }
                    break;
                }
            }
        }
    }
}

fn scan_python_structural(
    rel: &str,
    txt: &str,
    added: &[(usize, String)],
    out: &mut Vec<Finding>,
) {
    let added_lines: BTreeSet<usize> = added.iter().map(|(ln, _)| *ln).collect();
    let is_test = is_test_file(rel);
    let all_lines: Vec<&str> = txt.lines().collect();

    if !is_test {
        for &ln in &added_lines {
            if ln == 0 || ln > all_lines.len() {
                continue;
            }
            let line = all_lines[ln - 1];
            let code = line.split('#').next().unwrap_or("");
            if let Some(pos) = code.find("subprocess.run(") {
                let mut depth = 0i32;
                let mut call_buf = String::new();
                for j in (ln - 1)..all_lines.len().min(ln + 25) {
                    let seg = if j == ln - 1 { &all_lines[j][pos..] } else { all_lines[j] };
                    let seg_clean = seg.split('#').next().unwrap_or("");
                    call_buf.push_str(seg_clean);
                    call_buf.push(' ');
                    for ch in seg_clean.chars() {
                        if ch == '(' {
                            depth += 1;
                        } else if ch == ')' {
                            depth -= 1;
                        }
                    }
                    if depth <= 0 {
                        break;
                    }
                }
                if !call_buf.contains("timeout=") && !call_buf.contains("timeout =") && !call_buf.contains("**") {
                    out.push(Finding {
                        severity: "P1",
                        rule: "safety-subprocess-timeout",
                        file: rel.to_string(),
                        line: ln,
                        message: "`subprocess.run()` called without `timeout=`.".to_string(),
                        fix: "Pass an explicit `timeout=` bound so child commands cannot hang forever.",
                    });
                }
            }
        }
        return;
    }

    let mut i = 0;
    while i < all_lines.len() {
        let raw = all_lines[i];
        let trimmed = raw.trim_start();
        let def_rest = trimmed
            .strip_prefix("def ")
            .or_else(|| trimmed.strip_prefix("async def "));
        if let Some(drest) = def_rest {
            if drest.starts_with("test_") {
                let fname: String = drest
                    .chars()
                    .take_while(|c| c.is_ascii_alphanumeric() || *c == '_')
                    .collect();
                let def_ind = raw.len() - trimmed.len();
                let start_ln = i + 1;
                let mut j = i + 1;
                let mut body_lines: Vec<(usize, &str)> = Vec::new();
                while j < all_lines.len() {
                    let bl = all_lines[j];
                    let bc = bl.split('#').next().unwrap_or("").trim();
                    if bc.is_empty() {
                        j += 1;
                        continue;
                    }
                    let b_ind = bl.len() - bl.trim_start().len();
                    if b_ind <= def_ind {
                        break;
                    }
                    body_lines.push((j + 1, bc));
                    j += 1;
                }
                let end_ln = body_lines.last().map(|(l, _)| *l).unwrap_or(start_ln);
                let touched = (start_ln..=end_ln).any(|l| added_lines.contains(&l));
                if touched {
                    if body_lines.is_empty()
                        || body_lines.iter().all(|(_, s)| *s == "pass" || *s == "...")
                    {
                        out.push(Finding {
                            severity: "P1",
                            rule: "test-theater-empty",
                            file: rel.to_string(),
                            line: start_ln,
                            message: format!("Empty test `{}` proves nothing.", fname),
                            fix: "Assert real observable behavior or delete the placeholder test.",
                        });
                    } else {
                        let mut has_oracle = false;
                        for (bln, bs) in &body_lines {
                            if *bs == "assert True" || bs.starts_with("assert True,") {
                                has_oracle = true;
                                out.push(Finding {
                                    severity: "P1",
                                    rule: "test-theater-tautology",
                                    file: rel.to_string(),
                                    line: *bln,
                                    message: format!("`assert True` in `{}` is a tautology.", fname),
                                    fix: "Assert a real output/state invariant that fails if the fix is reverted.",
                                });
                            } else if bs.starts_with("assert ")
                                || bs.contains(".assert")
                                || bs.contains("raises(")
                                || bs.contains(".fail(")
                                || bs.contains("verify(")
                                || bs.contains("check(")
                            {
                                has_oracle = true;
                            }
                        }
                        if !has_oracle {
                            out.push(Finding {
                                severity: "P1",
                                rule: "test-theater-no-assert",
                                file: rel.to_string(),
                                line: start_ln,
                                message: format!("Test `{}` has zero assertions.", fname),
                                fix: "Add concrete behavioral assertions or delete the dead test.",
                            });
                        }
                    }
                }
                i = j;
                continue;
            }
        }
        i += 1;
    }
}

fn parse_xml_attr(tag: &str, key: &str) -> Option<String> {
    let needle = format!("{}=\"", key);
    let idx = tag.find(&needle)?;
    let rest = &tag[idx + needle.len()..];
    let end = rest.find('"')?;
    Some(rest[..end].to_string())
}

fn check_policy_xml(root: &Path, changed: &[String], out: &mut Vec<Finding>) {
    let policy_path = root.join(".deepmodebot/policy.xml");
    let Ok(xml) = fs::read_to_string(&policy_path) else {
        return;
    };
    let mut forbids: Vec<(String, String, String)> = Vec::new();
    for line in xml.lines() {
        let trim = line.trim();
        if trim.starts_with("<file ") {
            if let Some(p) = parse_xml_attr(trim, "path") {
                let target = root.join(&p);
                if let Ok(meta) = fs::metadata(&target) {
                    if let Some(mb) = parse_xml_attr(trim, "max-bytes")
                        .and_then(|v| v.parse::<u64>().ok())
                    {
                        if meta.len() > mb {
                            out.push(Finding {
                                severity: "P1",
                                rule: "budget-max-bytes",
                                file: p.clone(),
                                line: 1,
                                message: format!("{} is {} B > budget {} B.", p, meta.len(), mb),
                                fix: "Trim file or split into references.",
                            });
                        }
                    }
                    if let Some(ml) = parse_xml_attr(trim, "max-lines")
                        .and_then(|v| v.parse::<usize>().ok())
                    {
                        if let Ok(txt) = fs::read_to_string(&target) {
                            let lc = txt.lines().count();
                            if lc > ml {
                                out.push(Finding {
                                    severity: "P1",
                                    rule: "budget-max-lines",
                                    file: p.clone(),
                                    line: 1,
                                    message: format!("{} is {} L > budget {} L.", p, lc, ml),
                                    fix: "Trim file to stay within policy.xml budget.",
                                });
                            }
                        }
                    }
                }
            }
        } else if trim.starts_with("<forbid ") {
            if let (Some(f), Some(t)) = (parse_xml_attr(trim, "from"), parse_xml_attr(trim, "to")) {
                let reason = parse_xml_attr(trim, "reason")
                    .unwrap_or_else(|| format!("{} must not import {}", f, t));
                forbids.push((f, t, reason));
            }
        }
    }
    if forbids.is_empty() {
        return;
    }
    let per_file = parallel_map(changed, |rel| {
        let mut local = Vec::new();
        let active: Vec<&(String, String, String)> = forbids
            .iter()
            .filter(|(f, _, _)| glob_match(f, rel))
            .collect();
        if active.is_empty() {
            return local;
        }
        let Ok(txt) = fs::read_to_string(root.join(rel)) else {
            return local;
        };
        for (idx, line) in txt.lines().enumerate() {
            let t = line.trim();
            let imp = if let Some(rest) = t.strip_prefix("import ") {
                Some(rest.split_whitespace().next().unwrap_or("").replace('.', "/"))
            } else if let Some(rest) = t.strip_prefix("from ") {
                Some(rest.split_whitespace().next().unwrap_or("").replace('.', "/"))
            } else {
                None
            };
            if let Some(target_mod) = imp {
                for (_, to_pat, reason) in &active {
                    if glob_match(to_pat, &target_mod) {
                        local.push(Finding {
                            severity: "P1",
                            rule: "arch-boundary",
                            file: rel.clone(),
                            line: idx + 1,
                            message: format!(
                                "Forbidden import `{}` violates policy.xml ({}).",
                                target_mod, reason
                            ),
                            fix: "Route through an allowed interface/service layer.",
                        });
                    }
                }
            }
        }
        local
    });
    for chunk in per_file {
        out.extend(chunk);
    }
}

fn tool_exists(name: &str) -> bool {
    Command::new(name)
        .arg("--version")
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

fn run_parallel_linters(root: &Path, changed: &[String]) -> (Vec<&'static str>, Vec<Finding>) {
    let py_files: Vec<String> = changed
        .iter()
        .filter(|f| f.ends_with(".py") && root.join(f).is_file())
        .cloned()
        .collect();
    let js_files: Vec<String> = changed
        .iter()
        .filter(|f| (f.ends_with(".js") || f.ends_with(".mjs")) && root.join(f).is_file())
        .cloned()
        .collect();
    let sh_files: Vec<String> = changed
        .iter()
        .filter(|f| f.ends_with(".sh") && root.join(f).is_file())
        .cloned()
        .collect();

    let mut active_linters = Vec::new();
    let mut findings = Vec::new();

    thread::scope(|s| {
        let py_h = if !py_files.is_empty() && tool_exists("ruff") {
            active_linters.push("ruff");
            Some(s.spawn(|| {
                let mut f = Vec::new();
                let mut cmd = Command::new("ruff");
                cmd.arg("check")
                    .arg("--select")
                    .arg("E9,F63,F7,F82,F401")
                    .arg("--output-format")
                    .arg("concise")
                    .current_dir(root);
                for p in &py_files {
                    cmd.arg(p);
                }
                if let Ok(out) = cmd.output() {
                    if !out.status.success() {
                        let txt = String::from_utf8_lossy(&out.stdout);
                        for line in txt.lines() {
                            let parts: Vec<&str> = line.splitn(4, ':').collect();
                            if parts.len() == 4 {
                                let ln = parts[1].trim().parse::<usize>().unwrap_or(1);
                                f.push(Finding {
                                    severity: "P1",
                                    rule: "ruff",
                                    file: parts[0].replace('\\', "/"),
                                    line: ln,
                                    message: parts[3].trim().to_string(),
                                    fix: "Fix ruff diagnostic on changed Python file.",
                                });
                            }
                        }
                    }
                }
                f
            }))
        } else {
            None
        };

        let js_h = if !js_files.is_empty() && tool_exists("node") {
            active_linters.push("node-check");
            Some(s.spawn(|| {
                let mut f = Vec::new();
                for p in &js_files {
                    if let Ok(out) = Command::new("node")
                        .arg("--check")
                        .arg(root.join(p))
                        .output()
                    {
                        if !out.status.success() {
                            let msg = String::from_utf8_lossy(&out.stderr)
                                .lines()
                                .next()
                                .unwrap_or("Syntax error")
                                .to_string();
                            f.push(Finding {
                                severity: "P0",
                                rule: "node-syntax",
                                file: p.clone(),
                                line: 1,
                                message: msg,
                                fix: "Fix JS syntax error.",
                            });
                        }
                    }
                }
                f
            }))
        } else {
            None
        };

        let sh_h = if !sh_files.is_empty() && tool_exists("shellcheck") {
            active_linters.push("shellcheck");
            Some(s.spawn(|| {
                let mut f = Vec::new();
                let mut cmd = Command::new("shellcheck");
                cmd.arg("-f").arg("gcc").arg("-S").arg("error").current_dir(root);
                for p in &sh_files {
                    cmd.arg(p);
                }
                if let Ok(out) = cmd.output() {
                    if !out.status.success() {
                        let txt = String::from_utf8_lossy(&out.stdout);
                        for line in txt.lines() {
                            let parts: Vec<&str> = line.splitn(4, ':').collect();
                            if parts.len() == 4 {
                                let ln = parts[1].trim().parse::<usize>().unwrap_or(1);
                                f.push(Finding {
                                    severity: "P1",
                                    rule: "shellcheck",
                                    file: parts[0].replace('\\', "/"),
                                    line: ln,
                                    message: parts[3].trim().to_string(),
                                    fix: "Fix shellcheck error.",
                                });
                            }
                        }
                    }
                }
                f
            }))
        } else {
            None
        };

        if let Some(h) = py_h {
            findings.extend(h.join().unwrap_or_default());
        }
        if let Some(h) = js_h {
            findings.extend(h.join().unwrap_or_default());
        }
        if let Some(h) = sh_h {
            findings.extend(h.join().unwrap_or_default());
        }
    });

    (active_linters, findings)
}

pub fn run(args: &[String]) -> ExitCode {
    let mut root = PathBuf::from(".");
    let mut staged = false;
    let mut allow_config = false;
    let mut no_linters = false;
    let mut as_json = false;
    let mut explicit_files: Vec<String> = Vec::new();

    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--root" if i + 1 < args.len() => {
                root = PathBuf::from(&args[i + 1]);
                i += 2;
            }
            "--staged" => {
                staged = true;
                i += 1;
            }
            "--allow-config-change" => {
                allow_config = true;
                i += 1;
            }
            "--no-linters" => {
                no_linters = true;
                i += 1;
            }
            "--json" => {
                as_json = true;
                i += 1;
            }
            "--files" => {
                i += 1;
                while i < args.len() && !args[i].starts_with("--") {
                    explicit_files.push(args[i].clone());
                    i += 1;
                }
            }
            _ => {
                i += 1;
            }
        }
    }
    let root = fs::canonicalize(&root).unwrap_or(root);
    let changed = changed_files(&root, staged, &explicit_files);

    // Parallel diff & line scanning across all changed files
    let per_file_findings = parallel_map(&changed, |rel| {
        let mut local = Vec::new();
        if !allow_config && GUARDRAIL_CONFIGS.contains(&rel.as_str()) {
            local.push(Finding {
                severity: "P1",
                rule: "config-tamper",
                file: rel.clone(),
                line: 1,
                message: format!("Guardrail config `{}` modified without opt-in.", rel),
                fix: "Fix code instead of loosening guardrails, or pass --allow-config-change.",
            });
        }
        let added = added_lines_for_file(&root, rel, staged);
        if !added.is_empty() {
            scan_added_lines(rel, &added, &mut local);
        }
        let (mut r_added, r_hunks) = crate::reward::diff_file_hunks(&root, rel, staged, None);
        if r_added.is_empty() && !added.is_empty() {
            r_added = added.clone();
        }
        if !r_added.is_empty() || !r_hunks.is_empty() {
            let rs_cfg_ln = if rel.ends_with(".rs") {
                fs::read_to_string(root.join(rel))
                    .ok()
                    .and_then(|t| crate::reward::find_rs_cfg_test_line(&t))
            } else {
                None
            };
            let mut r_findings = Vec::new();
            crate::reward::scan_file_reward_hacks(rel, &r_added, &r_hunks, true, false, rs_cfg_ln, &mut r_findings);
            for rf in r_findings {
                local.push(Finding {
                    severity: rf.severity,
                    rule: rf.rule,
                    file: rf.file,
                    line: rf.line,
                    message: rf.message,
                    fix: rf.fix,
                });
            }
        }
        if (rel == ".github/dependabot.yml" || rel == ".github/dependabot.yaml") && !added.is_empty() {
            if let Ok(dep_txt) = fs::read_to_string(root.join(rel)) {
                if dep_txt.contains("cooldown:") {
                    local.retain(|f| f.rule != "supply-chain-dependabot-cooldown");
                } else if !local.iter().any(|f| f.rule == "supply-chain-dependabot-cooldown") {
                    local.push(Finding {
                        severity: "P2",
                        rule: "supply-chain-dependabot-cooldown",
                        file: rel.clone(),
                        line: 1,
                        message: "`.github/dependabot.yml` has no `cooldown:` window.".to_string(),
                        fix: "Add `cooldown: { default-days: 7 }` to reduce zero-day supply-chain exposure.",
                    });
                }
            }
        }
        if rel.ends_with(".py") && !added.is_empty() {
            if let Ok(py_txt) = fs::read_to_string(root.join(rel)) {
                scan_python_structural(rel, &py_txt, &added, &mut local);
            }
        }
        let is_ui = Path::new(rel)
            .extension()
            .and_then(|e| e.to_str())
            .map(|s| crate::ui::UI_EXTS.contains(&s.to_ascii_lowercase().as_str()))
            .unwrap_or(false);
        if is_ui {
            if let Ok(txt) = fs::read_to_string(root.join(rel)) {
                for uf in crate::ui::scan_ui(rel, &txt) {
                    if uf.severity == "P0" || uf.severity == "P1" {
                        local.push(Finding {
                            severity: uf.severity,
                            rule: uf.rule,
                            file: uf.file,
                            line: uf.line,
                            message: uf.message.to_string(),
                            fix: "Fix UI token/a11y/motion violation per frontend-ui.",
                        });
                    }
                }
            }
        }
        local
    });

    let mut findings: Vec<Finding> = per_file_findings.into_iter().flatten().collect();
    check_policy_xml(&root, &changed, &mut findings);

    let linters = if no_linters {
        Vec::new()
    } else {
        let (names, l_findings) = run_parallel_linters(&root, &changed);
        findings.extend(l_findings);
        names
    };

    findings.sort_by(|a, b| {
        a.severity
            .cmp(b.severity)
            .then_with(|| a.file.cmp(&b.file))
            .then_with(|| a.line.cmp(&b.line))
            .then_with(|| a.rule.cmp(b.rule))
    });

    let p0 = findings.iter().filter(|f| f.severity == "P0").count();
    let p1 = findings.iter().filter(|f| f.severity == "P1").count();
    let p2 = findings.iter().filter(|f| f.severity == "P2").count();
    let ok = p0 == 0 && p1 == 0;

    if as_json {
        let items: Vec<String> = findings
            .iter()
            .map(|f| {
                format!(
                    "{{\"severity\":{},\"rule\":{},\"file\":{},\"line\":{},\"message\":{},\"fix\":{}}}",
                    json_escape(f.severity),
                    json_escape(f.rule),
                    json_escape(&f.file),
                    f.line,
                    json_escape(&f.message),
                    json_escape(f.fix)
                )
            })
            .collect();
        let l_json: Vec<String> = linters.iter().map(|l| json_escape(l)).collect();
        println!(
            "{{\"ok\":{},\"engine\":\"rust-parallel\",\"files_checked\":{},\"linters\":[{}],\"counts\":{{\"P0\":{},\"P1\":{},\"P2\":{}}},\"findings\":[{}]}}",
            ok,
            changed.len(),
            l_json.join(","),
            p0,
            p1,
            p2,
            items.join(",")
        );
    } else {
        println!(
            "dmb-gate slop [{}]: {} file(s), linters=[{}] — P0:{} P1:{} P2:{}",
            if ok { "OK" } else { "BLOCKED" },
            changed.len(),
            linters.join(", "),
            p0,
            p1,
            p2
        );
        for f in &findings {
            println!(
                "  {}:{} [{}:{}] {} -> {}",
                f.file, f.line, f.severity, f.rule, f.message, f.fix
            );
        }
    }
    if ok {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(1)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dependabot_yaml_list_item_and_dotfile_explicit_files() {
        let mut out = Vec::new();
        let lines = vec![
            (1, "version: 2".to_string()),
            (2, "updates:".to_string()),
            (3, "  - package-ecosystem: \"npm\"".to_string()),
        ];
        scan_added_lines(".github/dependabot.yml", &lines, &mut out);
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].rule, "supply-chain-dependabot-cooldown");

        let explicit = vec![".github/dependabot.yml,./src/a.py".to_string()];
        let norm = changed_files(Path::new("."), false, &explicit);
        assert_eq!(norm, vec![".github/dependabot.yml", "src/a.py"]);
    }
}
