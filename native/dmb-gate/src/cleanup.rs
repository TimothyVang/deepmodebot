use crate::util::{json_escape, normalize_rel, parallel_map};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

const CACHE_DIRS: &[&str] = &["__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"];

#[derive(Clone, Debug)]
struct Target {
    path: PathBuf,
    is_dir: bool,
    bytes: u64,
}

fn dir_size(path: &Path) -> u64 {
    let mut total = 0u64;
    let mut stack = vec![path.to_path_buf()];
    while let Some(d) = stack.pop() {
        let Ok(rd) = fs::read_dir(&d) else {
            continue;
        };
        for entry in rd.flatten() {
            let Ok(ft) = entry.file_type() else {
                continue;
            };
            if ft.is_symlink() {
                continue;
            }
            if ft.is_dir() {
                stack.push(entry.path());
            } else if ft.is_file() {
                total += entry.metadata().map(|m| m.len()).unwrap_or(0);
            }
        }
    }
    total
}

fn find_bytecode_targets(root: &Path) -> Vec<Target> {
    let mut top_entries = Vec::new();
    if let Ok(rd) = fs::read_dir(root) {
        for e in rd.flatten() {
            let name = e.file_name();
            let ns = name.to_string_lossy();
            if ns == ".git" || ns == "node_modules" || ns == "target" {
                continue;
            }
            top_entries.push(e.path());
        }
    }
    let per_branch = parallel_map(&top_entries, |start| {
        let mut found = Vec::new();
        let Ok(meta) = fs::symlink_metadata(start) else {
            return found;
        };
        if meta.file_type().is_symlink() {
            return found;
        }
        if meta.is_file() {
            if start.extension().and_then(|e| e.to_str()) == Some("pyc") {
                found.push(Target {
                    path: start.clone(),
                    is_dir: false,
                    bytes: meta.len(),
                });
            }
            return found;
        }
        let mut stack = vec![start.clone()];
        while let Some(dir) = stack.pop() {
            let name = dir
                .file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .unwrap_or_default();
            if CACHE_DIRS.iter().any(|c| *c == name.as_str()) {
                found.push(Target {
                    bytes: dir_size(&dir),
                    path: dir,
                    is_dir: true,
                });
                continue;
            }
            let Ok(rd) = fs::read_dir(&dir) else {
                continue;
            };
            for entry in rd.flatten() {
                let p = entry.path();
                let Ok(ft) = entry.file_type() else {
                    continue;
                };
                if ft.is_symlink() {
                    continue;
                }
                if ft.is_dir() {
                    let cn = entry.file_name();
                    let cs = cn.to_string_lossy();
                    if cs != ".git" && cs != "node_modules" && cs != "target" {
                        stack.push(p);
                    }
                } else if ft.is_file() && p.extension().and_then(|e| e.to_str()) == Some("pyc") {
                    found.push(Target {
                        bytes: entry.metadata().map(|m| m.len()).unwrap_or(0),
                        path: p,
                        is_dir: false,
                    });
                }
            }
        }
        found
    });
    let mut out: Vec<Target> = per_branch.into_iter().flatten().collect();
    out.sort_by(|a, b| a.path.cmp(&b.path));
    out
}

pub fn run(args: &[String]) -> ExitCode {
    let mut root = PathBuf::from(".");
    let mut apply = false;
    let mut as_json = false;

    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--root" if i + 1 < args.len() => {
                root = PathBuf::from(&args[i + 1]);
                i += 2;
            }
            "--apply" => {
                apply = true;
                i += 1;
            }
            "--dry-run" => {
                apply = false;
                i += 1;
            }
            "--json" => {
                as_json = true;
                i += 1;
            }
            _ => i += 1,
        }
    }

    let root = fs::canonicalize(&root).unwrap_or(root);
    let targets = find_bytecode_targets(&root);
    let total_bytes: u64 = targets.iter().map(|t| t.bytes).sum();

    let mut removed = 0usize;
    if apply {
        for t in &targets {
            if !t.path.starts_with(&root) {
                continue;
            }
            let res = if t.is_dir {
                fs::remove_dir_all(&t.path)
            } else {
                fs::remove_file(&t.path)
            };
            if res.is_ok() {
                removed += 1;
            }
        }
    }

    if as_json {
        let items: Vec<String> = targets
            .iter()
            .map(|t| {
                format!(
                    "{{\"path\":{},\"bytes\":{}}}",
                    json_escape(&normalize_rel(&root, &t.path)),
                    t.bytes
                )
            })
            .collect();
        println!(
            "{{\"engine\":\"rust-parallel\",\"apply\":{},\"count\":{},\"removed\":{},\"bytes\":{},\"targets\":[{}]}}",
            apply,
            targets.len(),
            removed,
            total_bytes,
            items.join(",")
        );
    } else {
        println!(
            "dmb-gate cleanup ({}): {} cache target(s), {:.2} KB{}",
            if apply { "apply" } else { "dry-run" },
            targets.len(),
            (total_bytes as f64) / 1024.0,
            if apply {
                format!(", removed {}", removed)
            } else {
                String::new()
            }
        );
    }
    ExitCode::SUCCESS
}
