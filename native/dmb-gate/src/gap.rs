use crate::util::{json_escape, parallel_map, walk_files};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct GapFinding {
    pub severity: &'static str,
    pub rule: &'static str,
    pub file: String,
    pub line: usize,
    pub message: String,
    pub fix: String,
}

const SCAN_EXTS: &[&str] = &[
    "md", "py", "mjs", "cjs", "js", "ts", "tsx", "jsx", "sh", "rs", "go", "json", "yml", "yaml",
    "toml",
];

const JS_EXTS: &[&str] = &["ts", "tsx", "js", "jsx", "mjs", "cjs"];

fn is_test_rel(rel: &str) -> bool {
    let low = rel.to_ascii_lowercase();
    for seg in [
        "tests/", "test/", "spec/", "__tests__/", "evals/", "corpus/", "fixtures/",
    ] {
        if low.starts_with(seg) || low.contains(&format!("/{}", seg)) {
            return true;
        }
    }
    let file_name = low.rsplit('/').next().unwrap_or(&low);
    file_name.starts_with("test_")
        || file_name.contains("_test.")
        || file_name.contains(".test.")
        || file_name.contains(".spec.")
}

fn scrub_c_like_line(line: &str, keep_strings: bool) -> String {
    let bytes = line.as_bytes();
    let mut out = String::with_capacity(line.len());
    let mut quote: Option<u8> = None;
    let mut i = 0;
    while i < bytes.len() {
        let b = bytes[i];
        if let Some(q) = quote {
            if b == b'\\' && i + 1 < bytes.len() {
                if keep_strings {
                    out.push(b as char);
                    out.push(bytes[i + 1] as char);
                } else {
                    out.push_str("  ");
                }
                i += 2;
                continue;
            }
            if b == q {
                out.push(b as char);
                quote = None;
            } else if keep_strings {
                out.push(b as char);
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
            if let Some(end) = line[i + 2..].find("*/") {
                for _ in 0..(end + 4) {
                    out.push(' ');
                }
                i += end + 4;
                continue;
            }
            break;
        }
        if b == b'\'' || b == b'"' || b == b'`' {
            quote = Some(b);
            out.push(b as char);
            i += 1;
            continue;
        }
        out.push(b as char);
        i += 1;
    }
    out
}

fn extract_argparse_flags(txt: &str) -> BTreeSet<String> {
    let mut flags = BTreeSet::new();
    let mut rest = txt;
    while let Some(idx) = rest.find(".add_argument(") {
        let after = &rest[idx + ".add_argument(".len()..];
        let mut depth = 1i32;
        let mut end_idx = after.len();
        for (ci, ch) in after.char_indices() {
            if ch == '(' {
                depth += 1;
            } else if ch == ')' {
                depth -= 1;
                if depth == 0 {
                    end_idx = ci;
                    break;
                }
            }
        }
        let call_body = &after[..end_idx];
        let bytes = call_body.as_bytes();
        let mut k = 0;
        while k < bytes.len() {
            let q = bytes[k];
            if q == b'\'' || q == b'"' {
                let mut end_q = k + 1;
                while end_q < bytes.len() && bytes[end_q] != q {
                    if bytes[end_q] == b'\\' {
                        end_q += 1;
                    }
                    end_q += 1;
                }
                if end_q < bytes.len() {
                    let lit = &call_body[k + 1..end_q];
                    if lit.starts_with("--")
                        && lit.len() > 2
                        && lit[2..]
                            .bytes()
                            .all(|c| c.is_ascii_alphanumeric() || c == b'-')
                    {
                        flags.insert(lit.to_string());
                    }
                    k = end_q + 1;
                    continue;
                }
            }
            k += 1;
        }
        rest = &after[end_idx..];
    }
    if !flags.is_empty() {
        flags.insert("--help".to_string());
    }
    flags
}

fn discover_cli_subcommands(root: &Path) -> (BTreeSet<String>, BTreeSet<String>) {
    let mut gate_subs = BTreeSet::new();
    let mut net_subs = BTreeSet::new();

    if let Ok(txt) = fs::read_to_string(root.join("native/dmb-gate/src/main.rs")) {
        for line in txt.lines() {
            let t = line.trim();
            if let Some(rest) = t.strip_prefix('"') {
                if let Some(end_q) = rest.find('"') {
                    let cand = &rest[..end_q];
                    let after = rest[end_q + 1..].trim_start();
                    if after.starts_with("=>")
                        && !cand.is_empty()
                        && cand
                            .bytes()
                            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
                    {
                        gate_subs.insert(cand.to_string());
                    }
                }
            }
        }
    }

    if let Ok(txt) = fs::read_to_string(root.join("bin/deepmodebot.mjs")) {
        if let Some(start) = txt.find("const map = {") {
            let after = &txt[start + "const map = {".len()..];
            if let Some(end) = after.find("};") {
                for line in after[..end].lines() {
                    let t = line.trim();
                    if let Some(colon) = t.find(':') {
                        let key = t[..colon].trim();
                        if !key.is_empty()
                            && key
                                .bytes()
                                .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
                        {
                            gate_subs.insert(key.to_string());
                        }
                    }
                }
            }
        }
    }

    if let Ok(txt) = fs::read_to_string(root.join("native/dmb-net/main.go")) {
        for line in txt.lines() {
            let t = line.trim();
            if let Some(rest) = t.strip_prefix("case \"") {
                if let Some(end_q) = rest.find("\":") {
                    let cand = &rest[..end_q];
                    if !cand.is_empty()
                        && cand
                            .bytes()
                            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
                    {
                        net_subs.insert(cand.to_string());
                    }
                }
            }
        }
    }

    (gate_subs, net_subs)
}

fn scan_md_line_flags(
    rel: &str,
    line_no: usize,
    line: &str,
    argparse_by_name: &BTreeMap<String, Vec<(String, BTreeSet<String>)>>,
    out: &mut Vec<GapFinding>,
) {
    let bytes = line.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        if let Some(py_pos) = line[i..].find(".py") {
            let dot_idx = i + py_pos;
            let after_py = dot_idx + 3;
            let valid_end =
                after_py == bytes.len() || !(bytes[after_py].is_ascii_alphanumeric() || bytes[after_py] == b'_');
            if valid_end {
                let mut start = dot_idx;
                while start > 0
                    && (bytes[start - 1].is_ascii_lowercase()
                        || bytes[start - 1].is_ascii_digit()
                        || bytes[start - 1] == b'_')
                {
                    start -= 1;
                }
                let valid_start = start == 0
                    || matches!(
                        bytes[start - 1],
                        b' ' | b'\t' | b'"' | b'\'' | b'`' | b'/' | b'\\'
                    );
                if valid_start && start < dot_idx {
                    let sname = &line[start..after_py];
                    if let Some(entries) = argparse_by_name.get(sname) {
                        if entries.len() == 1 {
                            let rest = &line[after_py..];
                            let mut tail_end = rest.len();
                            for (ti, ch) in rest.char_indices() {
                                if matches!(ch, '`' | '|' | ';' | ')') {
                                    tail_end = ti;
                                    break;
                                }
                                if ch == '&' && rest[ti..].starts_with("&&") {
                                    tail_end = ti;
                                    break;
                                }
                            }
                            let tail = &rest[..tail_end];
                            if !tail.contains("--<") && !tail.contains("--{") {
                                let (srel, valid_flags) = &entries[0];
                                let tb = tail.as_bytes();
                                let mut p = 0;
                                while p + 2 < tb.len() {
                                    if tb[p] == b'-'
                                        && tb[p + 1] == b'-'
                                        && (p > 0 && tb[p - 1].is_ascii_whitespace())
                                        && tb[p + 2].is_ascii_lowercase()
                                    {
                                        let mut fe = p + 2;
                                        while fe < tb.len()
                                            && (tb[fe].is_ascii_lowercase()
                                                || tb[fe].is_ascii_digit()
                                                || tb[fe] == b'-')
                                        {
                                            fe += 1;
                                        }
                                        let boundary_ok = fe == tb.len()
                                            || tb[fe].is_ascii_whitespace()
                                            || matches!(tb[fe], b'=' | b'`' | b'"' | b'\'');
                                        if boundary_ok {
                                            let flg = &tail[p..fe];
                                            if !valid_flags.contains(flg) {
                                                out.push(GapFinding {
                                                    severity: "P1",
                                                    rule: "doc-script-flag-drift",
                                                    file: rel.to_string(),
                                                    line: line_no,
                                                    message: format!(
                                                        "Doc passes `{}` to `{}`, which does not define that flag.",
                                                        flg, srel
                                                    ),
                                                    fix: format!(
                                                        "Update `{}` or add `{}` to `{}`'s argparse definition.",
                                                        rel, flg, srel
                                                    ),
                                                });
                                            }
                                        }
                                        p = fe;
                                        continue;
                                    }
                                    p += 1;
                                }
                            }
                        }
                    }
                }
            }
            i = after_py;
        } else {
            break;
        }
    }
}

fn scan_md_cli_subcommands(
    rel: &str,
    line_no: usize,
    line: &str,
    gate_subs: &BTreeSet<String>,
    net_subs: &BTreeSet<String>,
    out: &mut Vec<GapFinding>,
) {
    for prefix in ["dmb-gate ", "deepmodebot gate "] {
        let mut start = 0;
        while let Some(pos) = line[start..].find(prefix) {
            let idx = start + pos;
            let prev_ok = idx == 0
                || !matches!(
                    line.as_bytes()[idx - 1],
                    b'/' | b'.' | b'-' | b'_' | b'a'..=b'z' | b'A'..=b'Z' | b'0'..=b'9'
                );
            let after = idx + prefix.len();
            if prev_ok && !gate_subs.is_empty() {
                let rest = line[after..].trim_start();
                let tok: String = rest
                    .chars()
                    .take_while(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || *c == '-' || *c == '|')
                    .collect();
                if !tok.is_empty() && rest.chars().next().map(|c| c.is_ascii_lowercase()).unwrap_or(false) {
                    for part in tok.split('|') {
                        if !part.is_empty() && part != "help" && !gate_subs.contains(part) {
                            out.push(GapFinding {
                                severity: "P1",
                                rule: "doc-cli-subcommand-drift",
                                file: rel.to_string(),
                                line: line_no,
                                message: format!("Doc references unknown dmb-gate subcommand `{}`.", part),
                                fix: "Update the documented gate subcommand or wire it into dmb-gate and bin/deepmodebot.mjs.".to_string(),
                            });
                        }
                    }
                }
            }
            start = after;
        }
    }

    let mut start = 0;
    while let Some(pos) = line[start..].find("dmb-net ") {
        let idx = start + pos;
        let prev_ok = idx == 0
            || !matches!(
                line.as_bytes()[idx - 1],
                b'/' | b'.' | b'-' | b'_' | b'a'..=b'z' | b'A'..=b'Z' | b'0'..=b'9'
            );
        let after = idx + "dmb-net ".len();
        if prev_ok && !net_subs.is_empty() {
            let rest = line[after..].trim_start();
            let tok: String = rest
                .chars()
                .take_while(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || *c == '-' || *c == '|')
                .collect();
            if !tok.is_empty() && rest.chars().next().map(|c| c.is_ascii_lowercase()).unwrap_or(false) {
                for part in tok.split('|') {
                    if !part.is_empty() && part != "help" && !net_subs.contains(part) {
                        out.push(GapFinding {
                            severity: "P1",
                            rule: "doc-cli-subcommand-drift",
                            file: rel.to_string(),
                            line: line_no,
                            message: format!("Doc references unknown dmb-net subcommand `{}`.", part),
                            fix: "Update the documented dmb-net subcommand or add it to native/dmb-net/main.go.".to_string(),
                        });
                    }
                }
            }
        }
        start = after;
    }
}

fn check_replaces_comment(
    rel: &str,
    line_no: usize,
    line: &str,
    live_paths: &BTreeSet<String>,
    live_basenames: &BTreeSet<String>,
    out: &mut Vec<GapFinding>,
) {
    let comment = if let Some(idx) = line.find("//") {
        &line[idx + 2..]
    } else if let Some(idx) = line.find('#') {
        &line[idx + 1..]
    } else {
        return;
    };
    let low = comment.to_ascii_lowercase();
    let Some(rpos) = low.find("replaces ") else {
        return;
    };
    let prev_ok = rpos == 0 || !low.as_bytes()[rpos - 1].is_ascii_alphanumeric();
    if !prev_ok {
        return;
    }
    let after = comment[rpos + "replaces ".len()..].trim_start();
    let cand: String = after
        .chars()
        .take_while(|c| c.is_ascii_alphanumeric() || matches!(c, '_' | '.' | '/' | '-'))
        .collect();
    let cand = cand.trim_end_matches('.').trim_start_matches("./");
    let valid_ext = ["py", "rs", "go", "ts", "js", "mjs", "sh"]
        .iter()
        .any(|ext| cand.ends_with(&format!(".{}", ext)));
    if !valid_ext {
        return;
    }
    let base = cand.rsplit('/').next().unwrap_or(cand);
    let still_live = live_paths.contains(cand)
        || (!cand.contains('/') && live_basenames.contains(base))
        || live_paths.iter().any(|p| p.ends_with(&format!("/{}", cand)));
    if still_live {
        out.push(GapFinding {
            severity: "P1",
            rule: "stale-replaces-claim",
            file: rel.to_string(),
            line: line_no,
            message: format!(
                "Comment claims to replace `{}`, which is still an active file in the repo.",
                cand
            ),
            fix: format!(
                "Migrate callers and delete `{}`, or clarify how this module complements `{}`.",
                cand, cand
            ),
        });
    }
}

fn is_js_teardown_prefix(prefix: &str) -> bool {
    for kw in ["finished", "unlink", "rm", "rmdir", "close", "abort", "cancel", "dispose"] {
        let mut start = 0;
        while let Some(pos) = prefix[start..].find(kw) {
            let idx = start + pos;
            let prev_ok = idx == 0 || !(prefix.as_bytes()[idx - 1].is_ascii_alphanumeric() || prefix.as_bytes()[idx - 1] == b'_');
            let after = idx + kw.len();
            let next_ok = after == prefix.len() || !(prefix.as_bytes()[after].is_ascii_alphanumeric() || prefix.as_bytes()[after] == b'_');
            if prev_ok && next_ok {
                return true;
            }
            start = after;
        }
    }
    false
}

fn has_js_empty_catch(scrubbed: &str) -> bool {
    let Some(pos) = scrubbed.find(".catch") else {
        return false;
    };
    if is_js_teardown_prefix(&scrubbed[..pos]) {
        return false;
    }
    let after = scrubbed[pos + 6..].trim_start();
    let Some(inner) = after.strip_prefix('(') else {
        return false;
    };
    let Some(brace_open) = inner.find('{') else {
        return false;
    };
    let between = inner[..brace_open].trim();
    let is_fn = between.contains("=>") || between.starts_with("function");
    if !is_fn {
        return false;
    }
    let after_open = inner[brace_open + 1..].trim_start();
    let Some(after_close) = after_open.strip_prefix('}') else {
        return false;
    };
    after_close.trim_start().starts_with(')')
}

fn has_js_stub_throw(with_str: &str) -> bool {
    let low = with_str.to_ascii_lowercase();
    let Some(pos) = low.find("throw new error") else {
        return false;
    };
    let after = low[pos + "throw new error".len()..].trim_start();
    let Some(inner) = after.strip_prefix('(') else {
        return false;
    };
    let inner = inner.trim_start();
    let Some(_q) = inner.bytes().next().filter(|b| *b == b'\'' || *b == b'"') else {
        return false;
    };
    let msg = &inner[1..];
    msg.starts_with("not implemented")
        || msg.starts_with("todo")
        || msg.starts_with("unimplemented")
}

fn indent_width(line: &str) -> usize {
    line.bytes()
        .take_while(|b| *b == b' ' || *b == b'\t')
        .map(|b| if b == b'\t' { 4 } else { 1 })
        .sum()
}

fn strip_py_comment(line: &str) -> &str {
    let bytes = line.as_bytes();
    let mut quote: Option<u8> = None;
    let mut i = 0;
    while i < bytes.len() {
        let b = bytes[i];
        if let Some(q) = quote {
            if b == b'\\' && i + 1 < bytes.len() {
                i += 2;
                continue;
            }
            if b == q {
                quote = None;
            }
            i += 1;
            continue;
        }
        if b == b'\'' || b == b'"' {
            quote = Some(b);
            i += 1;
            continue;
        }
        if b == b'#' {
            return line[..i].trim_end();
        }
        i += 1;
    }
    line.trim_end()
}

#[derive(Clone, Copy)]
enum PyScope {
    Class { is_abstract: bool },
    Func,
}

fn is_py_abstract_class_header(rest: &str) -> bool {
    let Some(open) = rest.find('(') else {
        return false;
    };
    let Some(close) = rest[open + 1..].rfind(')') else {
        return false;
    };
    let bases = &rest[open + 1..open + 1 + close];
    for part in bases.split(',') {
        let base_no_gen = part.split('[').next().unwrap_or("").trim();
        let tail = base_no_gen.rsplit('.').next().unwrap_or("").trim();
        if matches!(tail, "ABC" | "Protocol") {
            return true;
        }
    }
    false
}

fn find_py_def_header_colon(lines: &[&str], start: usize) -> Option<(usize, String)> {
    let mut sig_end = start;
    let mut paren_depth: i32 = 0;
    let mut saw_open_paren = false;
    let mut in_quote: Option<char> = None;
    while sig_end < lines.len() {
        let sc = strip_py_comment(lines[sig_end]);
        let mut escaped = false;
        for (bidx, ch) in sc.char_indices() {
            if let Some(q) = in_quote {
                if escaped {
                    escaped = false;
                } else if ch == '\\' {
                    escaped = true;
                } else if ch == q {
                    in_quote = None;
                }
                continue;
            }
            match ch {
                '\'' | '"' => in_quote = Some(ch),
                '(' | '[' | '{' => {
                    if ch == '(' {
                        saw_open_paren = true;
                    }
                    paren_depth += 1;
                }
                ')' | ']' | '}' => {
                    paren_depth -= 1;
                }
                ':' if saw_open_paren && paren_depth <= 0 => {
                    let inline_tail = sc[bidx + 1..].trim().to_string();
                    return Some((sig_end, inline_tail));
                }
                _ => {}
            }
        }
        sig_end += 1;
    }
    None
}

fn split_py_inline_stmts(inline_tail: &str) -> Vec<String> {
    let mut parts = Vec::new();
    let mut cur = String::new();
    let mut in_quote: Option<char> = None;
    let mut escaped = false;
    for ch in inline_tail.chars() {
        if let Some(q) = in_quote {
            cur.push(ch);
            if escaped {
                escaped = false;
            } else if ch == '\\' {
                escaped = true;
            } else if ch == q {
                in_quote = None;
            }
            continue;
        }
        match ch {
            '\'' | '"' => {
                in_quote = Some(ch);
                cur.push(ch);
            }
            ';' => {
                let t = cur.trim();
                if !t.is_empty() {
                    parts.push(t.to_string());
                }
                cur.clear();
            }
            _ => cur.push(ch),
        }
    }
    let tail = cur.trim();
    if !tail.is_empty() {
        parts.push(tail.to_string());
    }
    if let Some(first) = parts.first() {
        let is_str_doc = (first.starts_with('"') && first.ends_with('"') && first.len() >= 2)
            || (first.starts_with('\'') && first.ends_with('\'') && first.len() >= 2);
        if is_str_doc && first != "..." {
            parts.remove(0);
        }
    }
    parts
}

fn is_py_broad_except(clause: &str) -> bool {
    let trimmed = clause.trim();
    if trimmed == "except:" {
        return true;
    }
    let Some(rest) = trimmed.strip_prefix("except") else {
        return false;
    };
    if !rest.starts_with(char::is_whitespace) && !rest.starts_with('(') {
        return false;
    }
    let Some(body) = rest.trim().strip_suffix(':') else {
        return false;
    };
    let body = body.trim();
    if body.is_empty() {
        return true;
    }
    let expr = if let Some((before_as, after_as)) = body.rsplit_once(" as ") {
        let ident = after_as.trim();
        if !ident.is_empty() && ident.chars().all(|c| c.is_ascii_alphanumeric() || c == '_') {
            before_as.trim()
        } else {
            body
        }
    } else {
        body
    };
    let inner = expr
        .strip_prefix('(')
        .and_then(|s| s.strip_suffix(')'))
        .unwrap_or(expr);
    inner
        .split(',')
        .any(|item| matches!(item.trim(), "Exception" | "BaseException"))
}

fn scan_python_file_gaps(rel: &str, txt: &str, out: &mut Vec<GapFinding>) {
    let lines: Vec<&str> = txt.lines().collect();
    let n = lines.len();

    let mut scope_stack: Vec<(usize, PyScope)> = Vec::new();
    let mut pending_abstract_dec = false;
    let mut i = 0;

    while i < n {
        let raw = lines[i];
        let clean = strip_py_comment(raw);
        let trimmed = clean.trim();
        if trimmed.is_empty() {
            i += 1;
            continue;
        }
        let ind = indent_width(raw);
        scope_stack.retain(|(si, _)| *si < ind);

        if trimmed.starts_with('@') {
            if trimmed.contains("abstract") || trimmed.ends_with("overload") {
                pending_abstract_dec = true;
            }
            i += 1;
            continue;
        }

        if let Some(rest) = trimmed.strip_prefix("class ") {
            pending_abstract_dec = false;
            let is_abs = is_py_abstract_class_header(rest);
            scope_stack.push((ind, PyScope::Class { is_abstract: is_abs }));
            i += 1;
            continue;
        }

        if trimmed == "except:" || trimmed.starts_with("except:") {
            let inline_after = trimmed.strip_prefix("except:").unwrap_or("").trim();
            let bare_swallowed = if !inline_after.is_empty() {
                let parts = split_py_inline_stmts(inline_after);
                parts.len() == 1 && (parts[0] == "pass" || parts[0] == "...")
            } else {
                let mut j = i + 1;
                let mut body_lines = Vec::new();
                while j < n {
                    let b_clean = strip_py_comment(lines[j]);
                    let bt = b_clean.trim();
                    if bt.is_empty() {
                        j += 1;
                        continue;
                    }
                    if indent_width(lines[j]) <= ind {
                        break;
                    }
                    body_lines.push(bt);
                    j += 1;
                }
                body_lines.len() == 1 && (body_lines[0] == "pass" || body_lines[0] == "...")
            };
            if bare_swallowed {
                out.push(GapFinding {
                    severity: "P1",
                    rule: "swallowed-exception",
                    file: rel.to_string(),
                    line: i + 1,
                    message: "Bare `except: pass` silently swallows all errors including KeyboardInterrupt/SystemExit.".to_string(),
                    fix: "Catch a narrow exception type and handle, log, or re-raise it.".to_string(),
                });
            }
        }

        let def_rest = trimmed
            .strip_prefix("def ")
            .or_else(|| trimmed.strip_prefix("async def "));
        if let Some(drest) = def_rest {
            let parent_is_abstract = matches!(
                scope_stack.last(),
                Some((_, PyScope::Class { is_abstract: true }))
            );
            let is_abstract = pending_abstract_dec || parent_is_abstract;
            pending_abstract_dec = false;
            scope_stack.push((ind, PyScope::Func));

            let fname: String = drest
                .chars()
                .take_while(|c| c.is_ascii_alphanumeric() || *c == '_')
                .collect();
            let def_line = i + 1;

            let Some((sig_end, inline_tail)) = find_py_def_header_colon(&lines, i) else {
                i += 1;
                continue;
            };

            let mut stmts: Vec<(usize, usize, String)> = Vec::new();
            if !inline_tail.is_empty() {
                for part in split_py_inline_stmts(&inline_tail) {
                    stmts.push((sig_end + 1, ind + 4, part));
                }
            } else {
                let mut j = sig_end + 1;
                while j < n {
                    let bc = strip_py_comment(lines[j]);
                    let bt = bc.trim();
                    if bt.is_empty() {
                        j += 1;
                        continue;
                    }
                    let bind = indent_width(lines[j]);
                    if bind <= ind {
                        break;
                    }
                    if stmts.is_empty() && (bt.starts_with("\"\"\"") || bt.starts_with("'''")) {
                        let delim = &bt[..3];
                        if bt.len() >= 6 && bt[3..].contains(delim) {
                            j += 1;
                            continue;
                        }
                        j += 1;
                        while j < n && !lines[j].contains(delim) {
                            j += 1;
                        }
                        j += 1;
                        continue;
                    }
                    stmts.push((j + 1, bind, bt.to_string()));
                    j += 1;
                }
            }

            let is_exempt = (fname.starts_with("__") && fname.ends_with("__"))
                || matches!(fname.as_str(), "log_message" | "noop" | "_noop");

            if !is_abstract && !is_exempt && stmts.len() == 1 {
                let s0 = stmts[0].2.as_str();
                if s0 == "pass" || s0 == "..." {
                    out.push(GapFinding {
                        severity: "P1",
                        rule: "hollow-stub-body",
                        file: rel.to_string(),
                        line: def_line,
                        message: format!("Function `{}` has a hollow no-op body (`pass`/`...`).", fname),
                        fix: "Implement real behavior, mark `@abstractmethod` on a Protocol/ABC, or delete dead scaffolding.".to_string(),
                    });
                } else if s0 == "raise NotImplementedError" || s0.starts_with("raise NotImplementedError(") {
                    out.push(GapFinding {
                        severity: "P1",
                        rule: "hollow-stub-body",
                        file: rel.to_string(),
                        line: def_line,
                        message: format!(
                            "Function `{}` raises `NotImplementedError` outside an ABC/Protocol.",
                            fname
                        ),
                        fix: "Implement the function or move the interface contract onto an explicit `ABC`/`Protocol`.".to_string(),
                    });
                }
            }

            if !stmts.is_empty() && stmts[0].2 == "try:" {
                let try_ind = stmts[0].1;
                let top_clauses: Vec<(usize, &str)> = stmts
                    .iter()
                    .filter(|(_, bi, _)| *bi == try_ind)
                    .map(|(ln, _, txt_s)| (*ln, txt_s.as_str()))
                    .collect();
                let only_try_except = top_clauses.len() >= 2
                    && top_clauses[1..]
                        .iter()
                        .all(|(_, c)| c.starts_with("except ") || c.starts_with("except(") || *c == "except:");
                if only_try_except {
                    let mut all_broad_pass = true;
                    for (cl_idx, (cl_line, cl_txt)) in top_clauses.iter().enumerate().skip(1) {
                        if !is_py_broad_except(cl_txt) {
                            all_broad_pass = false;
                            break;
                        }
                        let next_top_line = top_clauses
                            .get(cl_idx + 1)
                            .map(|(nl, _)| *nl)
                            .unwrap_or(usize::MAX);
                        let handler_body: Vec<&str> = stmts
                            .iter()
                            .filter(|(ln, bi, _)| *ln > *cl_line && *ln < next_top_line && *bi > try_ind)
                            .map(|(_, _, t)| t.as_str())
                            .collect();
                        if handler_body.len() != 1
                            || (handler_body[0] != "pass" && handler_body[0] != "...")
                        {
                            all_broad_pass = false;
                            break;
                        }
                    }
                    if all_broad_pass {
                        out.push(GapFinding {
                            severity: "P1",
                            rule: "swallowed-exception",
                            file: rel.to_string(),
                            line: top_clauses[1].0,
                            message: format!(
                                "Function `{}` wraps its entire body in broad `except Exception: pass`.",
                                fname
                            ),
                            fix: "Catch narrow expected errors or surface/return structured failure state.".to_string(),
                        });
                    }
                }
            }

            i += 1;
            continue;
        }

        pending_abstract_dec = false;
        i += 1;
    }
}

fn check_cross_lang_parity(root: &Path, out: &mut Vec<GapFinding>) {
    let perf_py = root.join("plugins/deepmodebot/skills/deepmodebot/assets/perf-audit/perf_audit.py");
    let perf_rs = root.join("native/dmb-gate/src/perf.rs");
    if let (Ok(py_txt), Ok(rs_txt)) = (fs::read_to_string(&perf_py), fs::read_to_string(&perf_rs)) {
        for rule in [
            "db-n-plus-one-loop",
            "async-await-in-loop",
            "py-sync-in-async",
            "http-missing-timeout",
            "db-offset-pagination",
            "db-pool-per-request",
        ] {
            if py_txt.contains(rule) && !rs_txt.contains(rule) {
                out.push(GapFinding {
                    severity: "P1",
                    rule: "cross-lang-gate-drift",
                    file: "native/dmb-gate/src/perf.rs".to_string(),
                    line: 1,
                    message: format!(
                        "Rule `{}` exists in perf_audit.py but is missing in native/dmb-gate/src/perf.rs.",
                        rule
                    ),
                    fix: "Implement 1:1 rule parity across Python and Rust gates.".to_string(),
                });
            }
        }
    }

    let ui_py = root.join("plugins/deepmodebot/skills/frontend-ui/scripts/ui_audit.py");
    let ui_rs = root.join("native/dmb-gate/src/ui.rs");
    if let (Ok(py_txt), Ok(rs_txt)) = (fs::read_to_string(&ui_py), fs::read_to_string(&ui_rs)) {
        let pairs = [
            ("no-transition-all", "ui-transition-all"),
            ("no-layout-transition", "ui-layout-transition"),
            ("no-scale-zero-entry", "ui-scale-zero"),
            ("no-ease-in-ui", "ui-ease-in"),
            ("checkbox-not-circular", "ui-circular-checkbox"),
            ("icon-button-label", "ui-icon-button-unlabeled"),
            ("no-pure-black-surface", "ui-pure-black-surface"),
            ("no-100vw-overflow", "ui-100vw-overflow"),
            ("sticky-overflow-x-hidden", "ui-sticky-overflow-x-hidden"),
            ("no-zoom-disable", "ui-no-zoom-disable"),
            ("no-paste-block", "ui-no-paste-block"),
            ("no-fake-live-pulse", "ui-fake-live-pulse"),
        ];
        for (py_r, rs_r) in pairs {
            if py_txt.contains(py_r) && !rs_txt.contains(rs_r) {
                out.push(GapFinding {
                    severity: "P1",
                    rule: "cross-lang-gate-drift",
                    file: "native/dmb-gate/src/ui.rs".to_string(),
                    line: 1,
                    message: format!(
                        "Blocking UI rule `{}` in ui_audit.py has no Rust counterpart in native/dmb-gate/src/ui.rs.",
                        py_r
                    ),
                    fix: "Add matching rule coverage in native/dmb-gate/src/ui.rs.".to_string(),
                });
            }
        }
    }

    let reward_py = root.join("plugins/deepmodebot/skills/deepmodebot/assets/reward-guard/reward_guard.py");
    let reward_rs = root.join("native/dmb-gate/src/reward.rs");
    if let (Ok(py_txt), Ok(rs_txt)) = (fs::read_to_string(&reward_py), fs::read_to_string(&reward_rs)) {
        for rule in [
            "reward-hack-threshold-zero",
            "reward-hack-assertion-weakened",
            "reward-hack-test-skip",
            "reward-hack-primitive-standin",
            "reward-hack-hardcoded-pass",
            "reward-hack-contract-tampered",
        ] {
            if py_txt.contains(rule) && !rs_txt.contains(rule) {
                out.push(GapFinding {
                    severity: "P1",
                    rule: "cross-lang-gate-drift",
                    file: "native/dmb-gate/src/reward.rs".to_string(),
                    line: 1,
                    message: format!(
                        "Reward-guard rule `{}` exists in reward_guard.py but is missing in native/dmb-gate/src/reward.rs.",
                        rule
                    ),
                    fix: "Keep reward_guard.py and native/dmb-gate/src/reward.rs rule sets identical.".to_string(),
                });
            }
        }
    }
}

pub fn scan_repo_gaps(root: &Path) -> (usize, Vec<GapFinding>) {
    let has_plugins = root.join("plugins").is_dir();
    let files: Vec<PathBuf> = walk_files(root, None, crate::util::SKIP_DIRS);

    let loaded = parallel_map(&files, |p| {
        let meta = fs::symlink_metadata(p).ok()?;
        if meta.file_type().is_symlink() || !meta.is_file() || meta.len() > 512_000 {
            return None;
        }
        let rel_p = p.strip_prefix(root).ok()?;
        let rel = rel_p.to_string_lossy().replace('\\', "/");
        let is_test = is_test_rel(&rel);
        let fname = p
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("")
            .to_string();
        let ext = p
            .extension()
            .and_then(|s| s.to_str())
            .map(|s| s.to_ascii_lowercase())
            .unwrap_or_default();
        let want_text = SCAN_EXTS.contains(&ext.as_str())
            && (has_plugins || !matches!(ext.as_str(), "json" | "yml" | "yaml" | "toml"));
        let txt = if want_text {
            fs::read_to_string(p).ok()
        } else {
            None
        };
        Some((rel, fname, ext, is_test, txt))
    });

    let mut all_texts: BTreeMap<String, String> = BTreeMap::new();
    let mut live_paths: BTreeSet<String> = BTreeSet::new();
    let mut live_basenames: BTreeSet<String> = BTreeSet::new();
    let mut argparse_by_name: BTreeMap<String, Vec<(String, BTreeSet<String>)>> = BTreeMap::new();
    let mut asset_scripts: Vec<String> = Vec::new();

    for item in loaded.into_iter().flatten() {
        let (rel, fname, ext, is_test, txt_opt) = item;
        if !is_test {
            live_paths.insert(rel.clone());
            live_basenames.insert(fname.clone());
        }
        let Some(txt) = txt_opt else {
            continue;
        };
        if ext == "py" && !is_test {
            let parts: Vec<&str> = rel.split('/').collect();
            let is_skill_script = (parts.len() == 6
                && parts[0] == "plugins"
                && parts[2] == "skills"
                && parts[4] == "scripts")
                || (parts.len() == 7
                    && parts[0] == "plugins"
                    && parts[2] == "skills"
                    && parts[4] == "assets");
            if is_skill_script && fname != "__init__.py" {
                asset_scripts.push(rel.clone());
            }
            if txt.contains(".add_argument(")
                && !txt.contains("parse_known_args")
                && !txt.contains("REMAINDER")
                && !txt.contains("parse_intermixed_args")
            {
                let flags = extract_argparse_flags(&txt);
                if !flags.is_empty() {
                    argparse_by_name
                        .entry(fname)
                        .or_default()
                        .push((rel.clone(), flags));
                }
            }
        }
        all_texts.insert(rel, txt);
    }
    let files_checked = all_texts.len();
    let (gate_subs, net_subs) = discover_cli_subcommands(root);
    let entries: Vec<(String, String)> = all_texts
        .iter()
        .map(|(k, v)| (k.clone(), v.clone()))
        .collect();

    let per_file = parallel_map(&entries, |(rel, txt)| {
        let mut local = Vec::new();
        let ext = Path::new(rel)
            .extension()
            .and_then(|s| s.to_str())
            .map(|s| s.to_ascii_lowercase())
            .unwrap_or_default();
        let is_test = is_test_rel(rel);

        if ext == "md" {
            let fname = Path::new(rel)
                .file_name()
                .and_then(|s| s.to_str())
                .unwrap_or("");
            if rel.starts_with("docs/evidence/")
                || rel.starts_with("docs/research/")
                || rel.starts_with("evals/")
                || rel.starts_with("trending/")
                || fname.to_ascii_uppercase().starts_with("CHANGELOG")
            {
                return local;
            }
            for (idx, line) in txt.lines().enumerate() {
                scan_md_line_flags(rel, idx + 1, line, &argparse_by_name, &mut local);
                scan_md_cli_subcommands(rel, idx + 1, line, &gate_subs, &net_subs, &mut local);
            }
            return local;
        }

        if is_test {
            return local;
        }

        if matches!(ext.as_str(), "py" | "rs" | "go") || JS_EXTS.contains(&ext.as_str()) {
            for (idx, line) in txt.lines().enumerate() {
                check_replaces_comment(rel, idx + 1, line, &live_paths, &live_basenames, &mut local);
            }
        }

        if ext == "py" {
            scan_python_file_gaps(rel, txt, &mut local);
        } else if ext == "rs" {
            for (idx, line) in txt.lines().enumerate() {
                if line.trim_start().starts_with("#[cfg(test)]") {
                    break;
                }
                let scrubbed = scrub_c_like_line(line, false);
                if scrubbed.contains("todo!(") || scrubbed.contains("unimplemented!(") {
                    local.push(GapFinding {
                        severity: "P1",
                        rule: "hollow-stub-body",
                        file: rel.clone(),
                        line: idx + 1,
                        message: "Production Rust code leaves `todo!()` / `unimplemented!()` stub.".to_string(),
                        fix: "Implement the code path before shipping.".to_string(),
                    });
                }
            }
        } else if JS_EXTS.contains(&ext.as_str()) && !rel.starts_with("docs/assets/") {
            for (idx, line) in txt.lines().enumerate() {
                let scrubbed_no_str = scrub_c_like_line(line, false);
                let scrubbed_with_str = scrub_c_like_line(line, true);
                if has_js_empty_catch(&scrubbed_no_str) {
                    local.push(GapFinding {
                        severity: "P1",
                        rule: "swallowed-exception",
                        file: rel.clone(),
                        line: idx + 1,
                        message: "Empty `.catch(() => {})` silently drops rejected Promises.".to_string(),
                        fix: "Log, propagate, or surface structured error state instead of swallowing rejections.".to_string(),
                    });
                }
                if scrubbed_no_str.contains("throw new Error")
                    && has_js_stub_throw(&scrubbed_with_str)
                {
                    local.push(GapFinding {
                        severity: "P1",
                        rule: "hollow-stub-body",
                        file: rel.clone(),
                        line: idx + 1,
                        message: "Production JS/TS code throws a `not implemented` / `TODO` placeholder error.".to_string(),
                        fix: "Implement the real handler or remove the dead entrypoint.".to_string(),
                    });
                }
            }
        }

        local
    });

    let mut findings: Vec<GapFinding> = per_file.into_iter().flatten().collect();
    check_cross_lang_parity(root, &mut findings);

    for srel in &asset_scripts {
        let sname = Path::new(srel)
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("");
        let stem = Path::new(srel)
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("");
        let sdir = Path::new(srel)
            .parent()
            .map(|p| p.to_string_lossy().replace('\\', "/"))
            .unwrap_or_default();
        let sdir_prefix = format!("{}/", sdir);
        let mut referenced = false;
        for (orel, otxt) in &all_texts {
            if orel == srel {
                continue;
            }
            if orel.starts_with(&sdir_prefix) && is_test_rel(orel) {
                continue;
            }
            if otxt.contains(sname) || (orel.starts_with(&sdir_prefix) && otxt.contains(stem)) {
                referenced = true;
                break;
            }
        }
        if !referenced {
            findings.push(GapFinding {
                severity: "P2",
                rule: "unwired-script-asset",
                file: srel.clone(),
                line: 1,
                message: format!(
                    "Skill script `{}` is never referenced by any skill, command, CLI, or non-test module.",
                    srel
                ),
                fix: "Wire the script into its owning SKILL.md / reference workflow or remove dead code.".to_string(),
            });
        }
    }

    let sev_rank = |s: &str| match s {
        "P0" => 0usize,
        "P1" => 1,
        _ => 2,
    };
    findings.sort_by(|a, b| {
        sev_rank(a.severity)
            .cmp(&sev_rank(b.severity))
            .then_with(|| a.file.cmp(&b.file))
            .then_with(|| a.line.cmp(&b.line))
            .then_with(|| a.rule.cmp(b.rule))
    });

    (files_checked, findings)
}

pub fn run(args: &[String]) -> ExitCode {
    let mut root = PathBuf::from(".");
    let mut advisory = false;
    let mut as_json = false;
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "scan" | "--fail-on-p1" => i += 1,
            "--advisory" => {
                advisory = true;
                i += 1;
            }
            "--json" => {
                as_json = true;
                i += 1;
            }
            "--root" if i + 1 < args.len() => {
                root = PathBuf::from(&args[i + 1]);
                i += 2;
            }
            _ => i += 1,
        }
    }

    let root = fs::canonicalize(&root).unwrap_or(root);
    let (files_checked, findings) = scan_repo_gaps(&root);
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
                    json_escape(&f.fix)
                )
            })
            .collect();
        println!(
            "{{\"ok\":{},\"engine\":\"rust-parallel\",\"files_checked\":{},\"counts\":{{\"P0\":{},\"P1\":{},\"P2\":{}}},\"findings\":[{}]}}",
            ok,
            files_checked,
            p0,
            p1,
            p2,
            items.join(",")
        );
    } else {
        println!(
            "dmb-gate gap [{}]: {} file(s) — P0:{} P1:{} P2:{}",
            if ok { "OK" } else { "GAPS_FOUND" },
            files_checked,
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

    if advisory || ok {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(1)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn python_oneliner_tuple_except_and_nested_concrete_parity() {
        let src = "\
from typing import Protocol

def oneliner(): pass

def tuple_swallow():
    try:
        work()
    except (ValueError, Exception):
        pass

class SubProto(Protocol):
    def proto_method(self) -> int:
        ...

    class NestedConcrete:
        def concrete_stub(self):
            pass
";
        let mut out = Vec::new();
        scan_python_file_gaps("src/tricky.py", src, &mut out);
        let hits: Vec<(&str, usize, &str)> = out
            .iter()
            .map(|f| (f.rule, f.line, f.message.as_str()))
            .collect();
        assert!(
            hits.iter()
                .any(|(r, ln, m)| *r == "hollow-stub-body" && *ln == 3 && m.contains("oneliner")),
            "expected oneliner stub finding, got {:?}",
            hits
        );
        assert!(
            hits.iter()
                .any(|(r, ln, _)| *r == "swallowed-exception" && *ln == 8),
            "expected tuple broad except finding at line 8, got {:?}",
            hits
        );
        assert!(
            !hits.iter().any(|(_, _, m)| m.contains("proto_method")),
            "Protocol method must remain exempt, got {:?}",
            hits
        );
        assert!(
            hits.iter().any(|(r, ln, m)| *r == "hollow-stub-body"
                && *ln == 16
                && m.contains("concrete_stub")),
            "nested concrete class stub inside Protocol must be flagged, got {:?}",
            hits
        );
    }
}
