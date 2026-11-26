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

pub fn scan_ui(rel: &str, text: &str) -> Vec<UiFinding> {
    let mut out = Vec::new();
    let ext = Path::new(rel)
        .extension()
        .and_then(|e| e.to_str())
        .map(|s| s.to_ascii_lowercase())
        .unwrap_or_default();
    let low_full = text.to_ascii_lowercase();

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
