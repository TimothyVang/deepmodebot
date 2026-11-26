use crate::util::{json_escape, normalize_rel, parallel_map, walk_files, SKIP_DIRS};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

pub const UI_EXTS: &[&str] = &["html", "htm", "css", "scss", "jsx", "tsx", "vue", "svelte"];

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct UiFinding {
    pub severity: &'static str,
    pub rule: &'static str,
    pub file: String,
    pub line: usize,
    pub message: &'static str,
}

fn strip_comments_preserve_lines(text: &str, strip_line_comments: bool) -> String {
    let bytes = text.as_bytes();
    let mut out = String::with_capacity(text.len());
    let mut i = 0;
    let mut in_block = false;
    while i < bytes.len() {
        if in_block {
            if i + 1 < bytes.len() && bytes[i] == b'*' && bytes[i + 1] == b'/' {
                in_block = false;
                out.push_str("  ");
                i += 2;
            } else {
                if bytes[i] == b'\n' {
                    out.push('\n');
                } else {
                    out.push(' ');
                }
                i += 1;
            }
        } else if i + 1 < bytes.len() && bytes[i] == b'/' && bytes[i + 1] == b'*' {
            in_block = true;
            out.push_str("  ");
            i += 2;
        } else if strip_line_comments
            && i + 1 < bytes.len()
            && bytes[i] == b'/'
            && bytes[i + 1] == b'/'
            && (i == 0 || bytes[i - 1] != b':')
        {
            while i < bytes.len() && bytes[i] != b'\n' {
                i += 1;
            }
        } else {
            let ch = text[i..].chars().next().unwrap_or(' ');
            out.push(ch);
            i += ch.len_utf8();
        }
    }
    out
}

fn extract_css_decl_values<'a>(low: &'a str, props: &[&str]) -> Vec<&'a str> {
    let mut vals = Vec::new();
    let bytes = low.as_bytes();
    for prop in props {
        let mut search_from = 0;
        while let Some(rel_pos) = low[search_from..].find(prop) {
            let pos = search_from + rel_pos;
            let after_prop = pos + prop.len();
            search_from = after_prop;
            if pos > 0 {
                let prev = bytes[pos - 1];
                if prev.is_ascii_alphanumeric() || prev == b'-' || prev == b'_' {
                    continue;
                }
            }
            let rest = low[after_prop..].trim_start();
            if !rest.starts_with(':') || rest.starts_with("::") {
                continue;
            }
            let after_colon = rest[1..].trim_start();
            if let Some(q) = after_colon.as_bytes().first().copied().filter(|b| *b == b'"' || *b == b'\'') {
                let inner = &after_colon[1..];
                let end = inner.find(q as char).unwrap_or(inner.len());
                vals.push(&inner[..end]);
            } else {
                let end = after_colon
                    .find(|c: char| matches!(c, ';' | '}' | '{' | '"' | '\'' | '>'))
                    .unwrap_or(after_colon.len());
                vals.push(after_colon[..end].trim());
            }
        }
    }
    vals
}

fn has_raw_tw_gray(line: &str) -> bool {
    for prefix in ["bg-", "text-", "border-"] {
        for pal in ["zinc-", "slate-", "gray-", "neutral-", "stone-"] {
            let needle = format!("{}{}", prefix, pal);
            if let Some(pos) = line.find(&needle) {
                let tail = &line[pos + needle.len()..];
                if tail.bytes().take(2).all(|b| b.is_ascii_digit()) && tail.len() >= 2 {
                    return true;
                }
            }
        }
    }
    false
}

fn has_tw_bg_black(raw: &str) -> bool {
    let needle = "bg-black";
    let bytes = raw.as_bytes();
    let mut from = 0;
    while let Some(rel) = raw[from..].find(needle) {
        let pos = from + rel;
        let end = pos + needle.len();
        from = end;
        let left_ok = pos > 0 && matches!(bytes[pos - 1], b' ' | b'\t' | b'"' | b'\'' | b'`');
        let right_ok = end < bytes.len() && matches!(bytes[end], b' ' | b'\t' | b'"' | b'\'' | b'`');
        if left_ok && right_ok {
            return true;
        }
    }
    false
}

fn has_layout_transition(low: &str) -> bool {
    const LAYOUT_PROPS: &[&str] = &[
        "width", "height", "top", "left", "right", "bottom",
        "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
        "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
    ];
    for decl in extract_css_decl_values(low, &["transition", "transition-property"]) {
        for tok in decl.split(|c: char| !c.is_ascii_alphabetic() && c != '-') {
            if LAYOUT_PROPS.contains(&tok) {
                return true;
            }
        }
    }
    false
}

fn has_transition_all(low: &str) -> bool {
    for decl in extract_css_decl_values(low, &["transition", "transition-property"]) {
        for tok in decl.split(|c: char| !c.is_ascii_alphabetic() && c != '-') {
            if tok == "all" {
                return true;
            }
        }
    }
    false
}

fn has_pure_black_bg_css(low: &str) -> bool {
    for decl in extract_css_decl_values(low, &["background", "background-color"]) {
        let bytes = decl.as_bytes();
        let mut from = 0;
        while let Some(rel) = decl[from..].find('#') {
            let pos = from + rel;
            let hex = &bytes[pos + 1..];
            let hex_len = hex.iter().take_while(|b| b.is_ascii_hexdigit()).count();
            if (hex_len == 3 || hex_len == 6) && hex[..hex_len].iter().all(|b| *b == b'0') {
                return true;
            }
            from = pos + 1 + hex_len.max(1);
        }
    }
    false
}

fn has_scale_zero(low: &str) -> bool {
    for decl in extract_css_decl_values(low, &["transform"]) {
        let bytes = decl.as_bytes();
        let mut from = 0;
        while let Some(rel) = decl[from..].find("scale(") {
            let pos = from + rel;
            from = pos + "scale(".len();
            if pos > 0 {
                let prev = bytes[pos - 1];
                if prev.is_ascii_alphanumeric() || prev == b'-' || prev == b'_' {
                    continue;
                }
            }
            let args = decl[from..].trim_start();
            if let Some(close) = args.find(')') {
                let inner = args[..close].trim();
                if inner == "0" || (inner.starts_with("0.") && inner[2..].bytes().all(|b| b == b'0')) {
                    return true;
                }
            }
        }
    }
    false
}

fn has_circular_checkbox(low: &str) -> bool {
    let mut from = 0;
    while let Some(rel_lt) = low[from..].find('<') {
        let start = from + rel_lt;
        let Some(rel_gt) = low[start..].find('>') else {
            break;
        };
        let tag = &low[start..=start + rel_gt];
        from = start + rel_gt + 1;
        let is_cb = (tag.starts_with("<input")
            && (tag.contains("type=\"checkbox\"") || tag.contains("type='checkbox'")))
            || tag.contains("role=\"checkbox\"")
            || tag.contains("role='checkbox'");
        if is_cb
            && (tag.contains("rounded-full")
                || tag.contains("border-radius: 50%")
                || tag.contains("border-radius:50%")
                || tag.contains("9999px"))
        {
            return true;
        }
    }
    false
}

fn has_non_empty_a11y_attr(attrs: &str) -> bool {
    for attr in ["aria-label", "aria-labelledby", "title"] {
        let mut from = 0;
        while let Some(rel) = attrs[from..].find(attr) {
            let pos = from + rel;
            let after = pos + attr.len();
            from = after;
            if pos > 0 {
                let prev = attrs.as_bytes()[pos - 1];
                if prev.is_ascii_alphanumeric() || prev == b'-' || prev == b'_' {
                    continue;
                }
            }
            let rest = attrs[after..].trim_start();
            let Some(after_eq) = rest.strip_prefix('=') else {
                continue;
            };
            let val = after_eq.trim_start();
            if let Some(q) = val.as_bytes().first().copied().filter(|b| *b == b'"' || *b == b'\'') {
                let inner = &val[1..];
                if let Some(end) = inner.find(q as char) {
                    if !inner[..end].trim().is_empty() {
                        return true;
                    }
                }
            } else if let Some(inner) = val.strip_prefix('{') {
                if let Some(end) = inner.find('}') {
                    let expr = inner[..end].trim();
                    if !expr.is_empty() && expr != "\"\"" && expr != "''" {
                        return true;
                    }
                }
            }
        }
    }
    false
}

fn strip_tag_pair(mut s: String, tag: &str) -> String {
    let open_pat = format!("<{}", tag);
    let close_pat = format!("</{}>", tag);
    while let Some(start) = s.find(&open_pat) {
        let after_name = start + open_pat.len();
        if let Some(next_b) = s.as_bytes().get(after_name).copied() {
            if next_b.is_ascii_alphanumeric() || next_b == b'-' {
                s.replace_range(start..after_name, " ");
                continue;
            }
        }
        if let Some(rel_end) = s[start..].find(&close_pat) {
            s.replace_range(start..start + rel_end + close_pat.len(), "");
        } else if let Some(rel_self) = s[start..].find("/>") {
            s.replace_range(start..start + rel_self + 2, "");
        } else {
            break;
        }
    }
    s
}

fn strip_all_tags(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    let mut in_tag = false;
    for ch in s.chars() {
        if ch == '<' {
            in_tag = true;
        } else if ch == '>' {
            in_tag = false;
        } else if !in_tag {
            out.push(ch);
        }
    }
    out
}

fn has_icon_tag(inner: &str) -> bool {
    for pat in ["<svg", "<i"] {
        let mut from = 0;
        while let Some(rel) = inner[from..].find(pat) {
            let after = from + rel + pat.len();
            from = after;
            if matches!(inner.as_bytes().get(after), Some(b' ' | b'\t' | b'>' | b'/')) {
                return true;
            }
        }
    }
    false
}

fn has_unlabeled_icon_button(low: &str) -> bool {
    let mut from = 0;
    while let Some(rel_b) = low[from..].find("<button") {
        let b_start = from + rel_b;
        let after_kw = b_start + "<button".len();
        if matches!(low.as_bytes().get(after_kw), Some(b) if b.is_ascii_alphanumeric() || *b == b'-') {
            from = after_kw;
            continue;
        }
        let tail = &low[b_start..];
        let Some(open_end) = tail.find('>') else {
            break;
        };
        let attrs = &tail[..open_end];
        let after_open = &tail[open_end + 1..];
        let Some(close_pos) = after_open.find("</button>") else {
            break;
        };
        from = b_start + open_end + 1 + close_pos + "</button>".len();
        if has_non_empty_a11y_attr(attrs) {
            continue;
        }
        let inner = after_open[..close_pos].trim();
        if !has_icon_tag(inner) {
            continue;
        }
        let without_icons = strip_tag_pair(strip_tag_pair(inner.to_string(), "svg"), "i");
        let visible_text = strip_all_tags(&without_icons);
        if visible_text.trim().is_empty() {
            return true;
        }
    }
    false
}

pub fn scan_ui(rel: &str, text: &str) -> Vec<UiFinding> {
    let mut out = Vec::new();
    let ext = Path::new(rel)
        .extension()
        .and_then(|e| e.to_str())
        .map(|s| s.to_ascii_lowercase())
        .unwrap_or_default();
    let is_markup = !matches!(ext.as_str(), "css" | "scss");
    let strip_line = matches!(ext.as_str(), "scss" | "jsx" | "tsx");
    let cleaned = strip_comments_preserve_lines(text, strip_line);
    let low_full = cleaned.to_ascii_lowercase();
    let allows_intrinsic = low_full.contains("interpolate-size");

    for (idx, raw) in cleaned.lines().enumerate() {
        let ln = idx + 1;
        let low = raw.to_ascii_lowercase();
        if has_transition_all(&low) {
            out.push(UiFinding {
                severity: "P1",
                rule: "ui-transition-all",
                file: rel.to_string(),
                line: ln,
                message: "`transition: all` animates layout properties; list explicit properties.",
            });
        } else if !allows_intrinsic && has_layout_transition(&low) {
            out.push(UiFinding {
                severity: "P1",
                rule: "ui-layout-transition",
                file: rel.to_string(),
                line: ln,
                message: "Avoid animating layout box properties (width/height/margin/padding/top/left); use transform/opacity.",
            });
        }
        if low.contains("ease-in") && !low.contains("ease-in-out") {
            out.push(UiFinding {
                severity: "P1",
                rule: "ui-ease-in",
                file: rel.to_string(),
                line: ln,
                message: "Avoid `ease-in` on UI transitions; use ease-out or spring curves.",
            });
        }
        if has_raw_tw_gray(raw) {
            out.push(UiFinding {
                severity: "P1",
                rule: "ui-raw-tailwind-gray",
                file: rel.to_string(),
                line: ln,
                message: "Raw Tailwind gray utility; use semantic surface/text/border tokens.",
            });
        }
        if is_markup {
            if has_circular_checkbox(&low) {
                out.push(UiFinding {
                    severity: "P1",
                    rule: "ui-circular-checkbox",
                    file: rel.to_string(),
                    line: ln,
                    message: "Checkboxes must stay rectangular/squircle; circular `rounded-full`/`50%` signifies single-select radios.",
                });
            }
            if has_unlabeled_icon_button(&low) {
                out.push(UiFinding {
                    severity: "P1",
                    rule: "ui-icon-button-unlabeled",
                    file: rel.to_string(),
                    line: ln,
                    message: "Icon-only `<button>` missing `aria-label`/`aria-labelledby` (and tooltip).",
                });
            }
        }
        if has_pure_black_bg_css(&low) || (is_markup && has_tw_bg_black(raw)) {
            out.push(UiFinding {
                severity: "P1",
                rule: "ui-pure-black-surface",
                file: rel.to_string(),
                line: ln,
                message: "Avoid `#000000` / `bg-black` dark surfaces (OLED scroll smearing); use brand-tinted dark tokens.",
            });
        }
        if has_scale_zero(&low) {
            out.push(UiFinding {
                severity: "P1",
                rule: "ui-scale-zero",
                file: rel.to_string(),
                line: ln,
                message: "Avoid `scale(0)` UI entries; start popovers/menus at `scale(0.95)` from trigger origin.",
            });
        }
        if low.contains("box-shadow:") && low.contains("rgba(0, 0, 0, 0.") {
            out.push(UiFinding {
                severity: "P2",
                rule: "ui-heavy-rgba-shadow",
                file: rel.to_string(),
                line: ln,
                message: "Heavy generic black shadow; prefer tinted layered elevation tokens.",
            });
        }
        if is_markup && low.contains("<img") && !low.contains("alt=") {
            out.push(UiFinding {
                severity: "P1",
                rule: "ui-img-missing-alt",
                file: rel.to_string(),
                line: ln,
                message: "`<img>` tag missing `alt` attribute.",
            });
        }
    }

    if matches!(ext.as_str(), "css" | "scss") && cleaned.len() > 200 {
        if (low_full.contains("@keyframes") || low_full.contains("transition:"))
            && !low_full.contains("prefers-reduced-motion")
        {
            out.push(UiFinding {
                severity: "P1",
                rule: "ui-missing-reduced-motion",
                file: rel.to_string(),
                line: 1,
                message: "Animated stylesheet has no `@media (prefers-reduced-motion: reduce)` rule.",
            });
        }
        if (low_full.contains("button") || low_full.contains(":hover"))
            && !low_full.contains(":focus-visible")
        {
            out.push(UiFinding {
                severity: "P1",
                rule: "ui-missing-focus-visible",
                file: rel.to_string(),
                line: 1,
                message: "Interactive stylesheet missing `:focus-visible` ring.",
            });
        }
    }

    if matches!(ext.as_str(), "html" | "htm") && low_full.contains("<html") {
        if !low_full.contains("lang=") {
            out.push(UiFinding {
                severity: "P1",
                rule: "ui-missing-lang",
                file: rel.to_string(),
                line: 1,
                message: "HTML document missing `lang` attribute on `<html>`.",
            });
        }
        if !low_full.contains("name=\"viewport\"") && !low_full.contains("name='viewport'") {
            out.push(UiFinding {
                severity: "P1",
                rule: "ui-missing-viewport",
                file: rel.to_string(),
                line: 1,
                message: "HTML document missing `<meta name=\"viewport\">`.",
            });
        }
    }

    out
}

pub fn run(args: &[String]) -> ExitCode {
    let mut target = PathBuf::from(".");
    let mut fail_on_p1 = true;
    let mut as_json = false;

    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--root" if i + 1 < args.len() => {
                target = PathBuf::from(&args[i + 1]);
                i += 2;
            }
            s if s.starts_with("--root=") => {
                target = PathBuf::from(&s["--root=".len()..]);
                i += 1;
            }
            "--fail-on-p1" => {
                fail_on_p1 = true;
                i += 1;
            }
            "--warn-only" => {
                fail_on_p1 = false;
                i += 1;
            }
            "--json" => {
                as_json = true;
                i += 1;
            }
            s if !s.starts_with("--") => {
                target = PathBuf::from(s);
                i += 1;
            }
            _ => i += 1,
        }
    }

    let root = fs::canonicalize(&target).unwrap_or(target);
    let files = if root.is_file() {
        vec![root.clone()]
    } else {
        walk_files(&root, Some(UI_EXTS), SKIP_DIRS)
    };
    let base = if root.is_file() {
        root.parent().unwrap_or(&root).to_path_buf()
    } else {
        root.clone()
    };

    let per_file = parallel_map(&files, |p| {
        let rel = normalize_rel(&base, p);
        let Ok(txt) = fs::read_to_string(p) else {
            return Vec::new();
        };
        scan_ui(&rel, &txt)
    });
    let mut findings: Vec<UiFinding> = per_file.into_iter().flatten().collect();
    findings.sort_by(|a, b| a.file.cmp(&b.file).then_with(|| a.line.cmp(&b.line)));

    let p0 = findings.iter().filter(|f| f.severity == "P0").count();
    let p1 = findings.iter().filter(|f| f.severity == "P1").count();
    let p2 = findings.iter().filter(|f| f.severity == "P2").count();

    if as_json {
        let items: Vec<String> = findings
            .iter()
            .map(|f| {
                format!(
                    "{{\"severity\":{},\"rule\":{},\"file\":{},\"line\":{},\"message\":{}}}",
                    json_escape(f.severity),
                    json_escape(f.rule),
                    json_escape(&f.file),
                    f.line,
                    json_escape(f.message)
                )
            })
            .collect();
        println!(
            "{{\"engine\":\"rust-parallel\",\"files\":{},\"ok\":{},\"counts\":{{\"P0\":{},\"P1\":{},\"P2\":{}}},\"findings\":[{}]}}",
            files.len(),
            p0 == 0 && (!fail_on_p1 || p1 == 0),
            p0,
            p1,
            p2,
            items.join(",")
        );
    } else {
        println!(
            "dmb-gate ui: scanned {} files — P0:{} P1:{} P2:{}",
            files.len(),
            p0,
            p1,
            p2
        );
        for f in &findings {
            println!("  {}:{} [{}:{}] {}", f.file, f.line, f.severity, f.rule, f.message);
        }
    }

    if p0 > 0 || (fail_on_p1 && p1 > 0) {
        ExitCode::from(1)
    } else {
        ExitCode::SUCCESS
    }
}
