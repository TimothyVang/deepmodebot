use crate::util::{json_escape, normalize_rel, parallel_map, walk_files, SKIP_DIRS};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

const UI_EXTS: &[&str] = &["html", "htm", "css", "scss", "jsx", "tsx", "vue", "svelte"];

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct UiFinding {
    pub severity: &'static str,
    pub rule: &'static str,
    pub file: String,
    pub line: usize,
    pub message: &'static str,
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

fn has_layout_transition(low: &str) -> bool {
    let Some(pos) = low.find("transition:").or_else(|| low.find("transition-property:")) else {
        return false;
    };
    let decl = low[pos..].split(';').next().unwrap_or("");
    for prop in ["width", "height", "margin", "padding", "top", "left", "right", "bottom"] {
        for tok in decl.split(|c: char| !c.is_ascii_alphabetic() && c != '-') {
            if tok == prop {
                return true;
            }
        }
    }
    false
}

fn has_circular_checkbox(low: &str) -> bool {
    let is_cb = (low.contains("<input") && (low.contains("type=\"checkbox\"") || low.contains("type='checkbox'")))
        || low.contains("role=\"checkbox\"")
        || low.contains("role='checkbox'");
    is_cb && (low.contains("rounded-full") || low.contains("border-radius: 50%") || low.contains("border-radius:50%") || low.contains("9999px"))
}

fn has_unlabeled_icon_button(low: &str) -> bool {
    let Some(b_start) = low.find("<button") else {
        return false;
    };
    let tail = &low[b_start..];
    let Some(open_end) = tail.find('>') else {
        return false;
    };
    let attrs = &tail[..open_end];
    if attrs.contains("aria-label=") || attrs.contains("aria-labelledby=") || attrs.contains("title=") {
        return false;
    }
    let after_open = &tail[open_end + 1..];
    let Some(close_pos) = after_open.find("</button>") else {
        return false;
    };
    let inner = after_open[..close_pos].trim();
    inner.starts_with("<svg") && inner.ends_with("</svg>")
}

pub fn scan_ui(rel: &str, text: &str) -> Vec<UiFinding> {
    let mut out = Vec::new();
    let ext = Path::new(rel)
        .extension()
        .and_then(|e| e.to_str())
        .map(|s| s.to_ascii_lowercase())
        .unwrap_or_default();
    let low_full = text.to_ascii_lowercase();
    let allows_intrinsic = low_full.contains("interpolate-size");

    for (idx, raw) in text.lines().enumerate() {
        let ln = idx + 1;
        let low = raw.to_ascii_lowercase();
        if low.contains("transition:") && low.contains(" all") {
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
        if !matches!(ext.as_str(), "css" | "scss") {
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
        if (low.contains("background:") || low.contains("background-color:"))
            && (low.contains("#000;") || low.contains("#000000;") || low.ends_with("#000") || low.ends_with("#000000"))
        {
            out.push(UiFinding {
                severity: "P1",
                rule: "ui-pure-black-surface",
                file: rel.to_string(),
                line: ln,
                message: "Avoid `#000000` dark surfaces (OLED scroll smearing); use brand-tinted dark tokens.",
            });
        }
        if low.contains("transform:") && (low.contains("scale(0)") || low.contains("scale(0.0)")) {
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
        if !matches!(ext.as_str(), "css" | "scss") && low.contains("<img") && !low.contains("alt=") {
            out.push(UiFinding {
                severity: "P1",
                rule: "ui-img-missing-alt",
                file: rel.to_string(),
                line: ln,
                message: "`<img>` tag missing `alt` attribute.",
            });
        }
    }

    if matches!(ext.as_str(), "css" | "scss") && text.len() > 200 {
        if (low_full.contains("@keyframes") || low_full.contains("transition:"))
            && !low_full.contains("prefers-reduced-motion")
        {
            out.push(UiFinding {
                severity: "P1",
                rule: "ui-missing-reduced-motion",
                file: rel.to_string(),
                line: 1,
                message: "Stylesheet defines motion without `@media (prefers-reduced-motion: reduce)`.",
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
    let mut fail_on_p1 = false;
    let mut as_json = false;

    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--fail-on-p1" => {
                fail_on_p1 = true;
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
            "{{\"engine\":\"rust-parallel\",\"files\":{},\"counts\":{{\"P0\":{},\"P1\":{},\"P2\":{}}},\"findings\":[{}]}}",
            files.len(),
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

    if fail_on_p1 && (p0 > 0 || p1 > 0) {
        ExitCode::from(1)
    } else {
        ExitCode::SUCCESS
    }
}
