use crate::util::{json_escape, normalize_rel, parallel_map, walk_files, SKIP_DIRS};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};

const CODE_EXTS: &[&str] = &["py", "rs", "go", "ts", "tsx", "js", "mjs"];

#[derive(Clone, Debug)]
pub struct FileEntry {
    pub path: String,
    pub bytes: u64,
    pub lines: usize,
    pub symbols: Vec<String>,
}

pub fn extract_symbols(ext: &str, text: &str) -> Vec<String> {
    let mut syms = Vec::new();
    for line in text.lines() {
        let trim = line.trim();
        let sym = match ext {
            "py" if line.starts_with("def ") || line.starts_with("async def ") || line.starts_with("class ") => {
                let rest = trim
                    .trim_start_matches("async ")
                    .trim_start_matches("def ")
                    .trim_start_matches("class ");
                rest.split(['(', ':']).next().map(str::trim)
            }
            "rs" if trim.starts_with("pub fn ")
                || trim.starts_with("fn ")
                || trim.starts_with("pub struct ")
                || trim.starts_with("pub enum ") =>
            {
                let rest = trim
                    .trim_start_matches("pub ")
                    .trim_start_matches("async ")
                    .trim_start_matches("fn ")
                    .trim_start_matches("struct ")
                    .trim_start_matches("enum ");
                rest.split(['(', '<', '{', ' ']).next().map(str::trim)
            }
            "go" if line.starts_with("func ") || line.starts_with("type ") => {
                let rest = trim.trim_start_matches("func ").trim_start_matches("type ");
                let rest = if rest.starts_with('(') {
                    rest.split_once(')').map(|(_, r)| r.trim()).unwrap_or(rest)
                } else {
                    rest
                };
                rest.split(['(', '[', ' ']).next().map(str::trim)
            }
            "ts" | "tsx" | "js" | "mjs"
                if trim.starts_with("export function ")
                    || trim.starts_with("export async function ")
                    || trim.starts_with("export class ")
                    || trim.starts_with("function ") =>
            {
                let rest = trim
                    .trim_start_matches("export ")
                    .trim_start_matches("async ")
                    .trim_start_matches("function ")
                    .trim_start_matches("class ");
                rest.split(['(', '<', '{', ' ']).next().map(str::trim)
            }
            _ => None,
        };
        if let Some(name) = sym {
            if !name.is_empty() && syms.len() < 32 {
                syms.push(name.to_string());
            }
        }
    }
    syms
}

fn git_branch(root: &Path) -> String {
    Command::new("git")
        .args(["-C", &root.to_string_lossy(), "branch", "--show-current"])
        .output()
        .ok()
        .filter(|o| o.status.success())
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
        .unwrap_or_default()
}

pub fn run(args: &[String]) -> ExitCode {
    let mut root = PathBuf::from(".");
    let mut out_path: Option<PathBuf> = None;
    let mut as_json = false;
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--root" if i + 1 < args.len() => {
                root = PathBuf::from(&args[i + 1]);
                i += 2;
            }
            "--out" if i + 1 < args.len() => {
                out_path = Some(PathBuf::from(&args[i + 1]));
                i += 2;
            }
            "--json" => {
                as_json = true;
                i += 1;
            }
            _ => i += 1,
        }
    }
    let root = fs::canonicalize(&root).unwrap_or(root);
    let files = walk_files(&root, Some(CODE_EXTS), SKIP_DIRS);
    let entries: Vec<FileEntry> = parallel_map(&files, |p| {
        let rel = normalize_rel(&root, p);
        let ext = p
            .extension()
            .and_then(|e| e.to_str())
            .map(|s| s.to_ascii_lowercase())
            .unwrap_or_default();
        let bytes = fs::metadata(p).map(|m| m.len()).unwrap_or(0);
        let txt = if bytes <= 512_000 {
            fs::read_to_string(p).unwrap_or_default()
        } else {
            String::new()
        };
        let lines = txt.lines().count();
        let symbols = extract_symbols(&ext, &txt);
        FileEntry {
            path: rel,
            bytes,
            lines,
            symbols,
        }
    });

    let total_symbols: usize = entries.iter().map(|e| e.symbols.len()).sum();
    let branch = git_branch(&root);

    let json_entries: Vec<String> = entries
        .iter()
        .map(|e| {
            let syms: Vec<String> = e.symbols.iter().map(|s| json_escape(s)).collect();
            format!(
                "{{\"path\":{},\"bytes\":{},\"lines\":{},\"symbols\":[{}]}}",
                json_escape(&e.path),
                e.bytes,
                e.lines,
                syms.join(",")
            )
        })
        .collect();
    let payload = format!(
        "{{\"engine\":\"rust-parallel\",\"branch\":{},\"files\":{},\"symbols\":{},\"entries\":[{}]}}",
        json_escape(&branch),
        entries.len(),
        total_symbols,
        json_entries.join(",")
    );

    if let Some(op) = out_path {
        if let Some(parent) = op.parent() {
            let _ = fs::create_dir_all(parent);
        }
        let _ = fs::write(&op, &payload);
    }

    if as_json {
        println!("{}", payload);
    } else {
        println!(
            "dmb-gate map: branch={} files={} symbols={}",
            if branch.is_empty() { "detached" } else { &branch },
            entries.len(),
            total_symbols
        );
    }
    ExitCode::SUCCESS
}
