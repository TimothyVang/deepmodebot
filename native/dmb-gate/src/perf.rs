use crate::util::{json_escape, normalize_rel, parallel_map, walk_files, SKIP_DIRS};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

const SCAN_EXTS: &[&str] = &[
    "py", "go", "rs", "cs", "fs", "ts", "tsx", "js", "jsx", "mjs", "java", "kt", "c", "cc",
    "cxx", "cpp", "h", "hpp", "zig", "sql",
];

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PerfFinding {
    pub rule_id: &'static str,
    pub severity: &'static str,
    pub file: String,
    pub line: usize,
    pub message: &'static str,
}

fn is_test_path(rel: &str) -> bool {
    let low = rel.to_ascii_lowercase();
    low.contains("/tests/")
        || low.contains("/test/")
        || low.starts_with("test_")
        || low.contains("/test_")
        || low.contains("_test.")
        || low.contains(".test.")
        || low.contains(".spec.")
}

pub fn scan_text(rel: &str, text: &str) -> Vec<PerfFinding> {
    let mut out = Vec::new();
    let ext = Path::new(rel)
        .extension()
        .and_then(|e| e.to_str())
        .map(|s| s.to_ascii_lowercase())
        .unwrap_or_default();

    let mut in_async_py = false;
    let mut async_indent = 0usize;
    let mut loop_indent: Option<usize> = None;

    for (idx, raw) in text.lines().enumerate() {
        let ln = idx + 1;
        let trim = raw.trim();
        if trim.is_empty() || trim.starts_with('#') || trim.starts_with("//") || trim.starts_with('*') {
            continue;
        }
        let low = trim.to_ascii_lowercase();
        let indent = raw.len() - raw.trim_start().len();

        // Line-based high-scale rules
        if ext == "go" && (trim.contains("gin-contrib/gzip") || trim.contains("gzip.Gzip(")) {
            out.push(PerfFinding {
                rule_id: "PERF-GO-001",
                severity: "high",
                file: rel.to_string(),
                line: ln,
                message: "gin-contrib/gzip allocates ~1 MB flate writer before DB wait; prefer gzhttp.",
            });
        }
        if ext == "py" && trim.contains("statement_cache_size=0") && !text.contains("name=") {
            out.push(PerfFinding {
                rule_id: "PERF-PY-001",
                severity: "high",
                file: rel.to_string(),
                line: ln,
                message: "asyncpg statement_cache_size=0 forces re-planning unless named prepared statements are used.",
            });
        }
        if matches!(ext.as_str(), "cs" | "fs")
            && trim.contains("new GZipStream(")
            && !trim.contains("leaveOpen")
        {
            out.push(PerfFinding {
                rule_id: "PERF-NET-001",
                severity: "high",
                file: rel.to_string(),
                line: ln,
                message: "GZipStream without leaveOpen: true closes backing MemoryStream.",
            });
        }
        if low.contains("pragma") && low.contains("mmap_size") && !low.contains("mmap_size = 0") && !low.contains("mmap_size=0") {
            out.push(PerfFinding {
                rule_id: "PERF-SQLITE-001",
                severity: "high",
                file: rel.to_string(),
                line: ln,
                message: "SQLite mmap_size > 0 adds WAL-index probe overhead; prefer mmap_size=0.",
            });
        }
        if low.contains("pragma") && low.contains("synchronous") && low.contains("full") {
            out.push(PerfFinding {
                rule_id: "PERF-SQLITE-002",
                severity: "medium",
                file: rel.to_string(),
                line: ln,
                message: "SQLite synchronous=FULL fsyncs every commit; use synchronous=NORMAL in WAL mode.",
            });
        }
        if low.contains("select ") && low.contains(" limit ") && low.contains(" offset ") {
            out.push(PerfFinding {
                rule_id: "PERF-DB-002",
                severity: "medium",
                file: rel.to_string(),
                line: ln,
                message: "SQL OFFSET pagination scans O(N) skipped rows; prefer keyset pagination.",
            });
        }
        if matches!(ext.as_str(), "cpp" | "cc" | "cxx" | "hpp" | "h")
            && trim.contains("std::unordered_map<")
        {
            out.push(PerfFinding {
                rule_id: "PERF-CPP-001",
                severity: "medium",
                file: rel.to_string(),
                line: ln,
                message: "std::unordered_map allocates per-node heap entries; prefer flat hash maps.",
            });
        }

        // Python structural hot-path checks (async blocking & N+1 / await-in-loop)
        if ext == "py" {
            if trim.starts_with("async def ") {
                in_async_py = true;
                async_indent = indent;
            } else if (trim.starts_with("def ") || trim.starts_with("class ")) && indent <= async_indent {
                in_async_py = false;
            }
            if trim.starts_with("for ") || trim.starts_with("while ") {
                loop_indent = Some(indent);
            } else if let Some(li) = loop_indent {
                if indent <= li {
                    loop_indent = None;
                }
            }
            if in_async_py && (trim.contains("time.sleep(") || trim.contains("requests.get(") || trim.contains("requests.post(")) {
                out.push(PerfFinding {
                    rule_id: "PERF-ASYNC-001",
                    severity: "high",
                    file: rel.to_string(),
                    line: ln,
                    message: "Blocking sync call inside `async def` stalls the event loop.",
                });
            }
            if loop_indent.is_some()
                && (trim.contains("cursor.execute(") || trim.contains("conn.execute("))
                && !trim.contains("executemany(")
            {
                out.push(PerfFinding {
                    rule_id: "PERF-DB-001",
                    severity: "high",
                    file: rel.to_string(),
                    line: ln,
                    message: "Database `.execute()` inside a loop risks N+1 query overhead; batch with `executemany` or `IN (...)`.",
                });
            }
        }
    }
    out
}

pub fn run(args: &[String]) -> ExitCode {
    let mut root = PathBuf::from(".");
    let mut fail_on_high = false;
    let mut as_json = false;
    let mut include_tests = false;
    let mut explicit_files: Vec<String> = Vec::new();

    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--root" if i + 1 < args.len() => {
                root = PathBuf::from(&args[i + 1]);
                i += 2;
            }
            "--fail-on-high" => {
                fail_on_high = true;
                i += 1;
            }
            "--json" => {
                as_json = true;
                i += 1;
            }
            "--include-tests" => {
                include_tests = true;
                i += 1;
            }
            "--files" => {
                i += 1;
                while i < args.len() && !args[i].starts_with("--") {
                    explicit_files.push(args[i].clone());
                    i += 1;
                }
            }
            _ => i += 1,
        }
    }
    let root = fs::canonicalize(&root).unwrap_or(root);
    let targets: Vec<PathBuf> = if !explicit_files.is_empty() {
        explicit_files
            .into_iter()
            .map(|f| {
                let p = PathBuf::from(&f);
                if p.is_absolute() {
                    p
                } else {
                    root.join(p)
                }
            })
            .filter(|p| p.is_file())
            .collect()
    } else {
        walk_files(&root, Some(SCAN_EXTS), SKIP_DIRS)
            .into_iter()
            .filter(|p| include_tests || !is_test_path(&normalize_rel(&root, p)))
            .collect()
    };

    let per_file = parallel_map(&targets, |p| {
        let rel = normalize_rel(&root, p);
        let Ok(txt) = fs::read_to_string(p) else {
            return Vec::new();
        };
        scan_text(&rel, &txt)
    });
    let mut findings: Vec<PerfFinding> = per_file.into_iter().flatten().collect();
    findings.sort_by(|a, b| a.file.cmp(&b.file).then_with(|| a.line.cmp(&b.line)));

    if as_json {
        let items: Vec<String> = findings
            .iter()
            .map(|f| {
                format!(
                    "{{\"rule_id\":{},\"severity\":{},\"file\":{},\"line\":{},\"message\":{}}}",
                    json_escape(f.rule_id),
                    json_escape(f.severity),
                    json_escape(&f.file),
                    f.line,
                    json_escape(f.message)
                )
            })
            .collect();
        println!(
            "{{\"engine\":\"rust-parallel\",\"files\":{},\"findings\":[{}]}}",
            targets.len(),
            items.join(",")
        );
    } else {
        println!(
            "dmb-gate perf: scanned {} files, {} findings",
            targets.len(),
            findings.len()
        );
        for f in &findings {
            println!(
                "  [{}] {} {}:{} - {}",
                f.severity.to_ascii_uppercase(),
                f.rule_id,
                f.file,
                f.line,
                f.message
            );
        }
    }

    if fail_on_high && findings.iter().any(|f| f.severity == "high") {
        ExitCode::from(1)
    } else {
        ExitCode::SUCCESS
    }
}
