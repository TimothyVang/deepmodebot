use crate::util::{json_escape, parallel_map};
use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

const MAX_SKILL_BYTES: usize = 24_000;

fn extract_backtick_refs(text: &str) -> Vec<String> {
    let mut out = Vec::new();
    let bytes = text.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'`' {
            let start = i + 1;
            let mut end = start;
            while end < bytes.len() && bytes[end] != b'`' && bytes[end] != b'\n' {
                end += 1;
            }
            if end < bytes.len() && bytes[end] == b'`' && end > start {
                let tok = &text[start..end];
                if !tok.contains(' ')
                    && !tok.contains('<')
                    && !tok.contains('*')
                    && (tok.starts_with("references/")
                        || tok.starts_with("scripts/")
                        || tok.starts_with("skill://"))
                {
                    out.push(tok.to_string());
                }
            }
            i = end + 1;
        } else {
            i += 1;
        }
    }
    out
}

pub fn check_one_skill(skill_dir: &Path, siblings: &HashSet<String>) -> Vec<String> {
    let mut problems = Vec::new();
    let name = skill_dir
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_else(|| skill_dir.display().to_string());
    let skill_md = skill_dir.join("SKILL.md");
    let Ok(text) = fs::read_to_string(&skill_md) else {
        problems.push(format!("{}: missing SKILL.md", name));
        return problems;
    };
    if text.len() > MAX_SKILL_BYTES {
        problems.push(format!(
            "{}: SKILL.md is {} bytes (> {} max)",
            name,
            text.len(),
            MAX_SKILL_BYTES
        ));
    }
    if !text.starts_with("---\n") && !text.starts_with("---\r\n") {
        problems.push(format!("{}: SKILL.md missing YAML frontmatter", name));
    } else {
        let rest = text
            .strip_prefix("---\r\n")
            .or_else(|| text.strip_prefix("---\n"))
            .unwrap_or("");
        if let Some(end) = rest.find("\n---") {
            let fm = &rest[..end];
            if !fm.lines().any(|l| l.starts_with("name:")) {
                problems.push(format!("{}: frontmatter missing `name:`", name));
            }
            if !fm.lines().any(|l| l.starts_with("description:")) {
                problems.push(format!("{}: frontmatter missing `description:`", name));
            }
        } else {
            problems.push(format!("{}: unclosed YAML frontmatter", name));
        }
    }
    for tok in extract_backtick_refs(&text) {
        if let Some(target) = tok.strip_prefix("skill://") {
            let mut parts = target.splitn(2, '/');
            let target_skill = parts.next().unwrap_or("");
            let sub = parts.next();
            if siblings.contains(target_skill) {
                if let Some(sub_path) = sub {
                    if let Some(parent) = skill_dir.parent() {
                        let full = parent.join(target_skill).join(sub_path);
                        if !full.exists() {
                            problems.push(format!("{}: missing sibling target `{}`", name, tok));
                        }
                    }
                }
            }
        } else if tok.ends_with(".md")
            || tok.ends_with(".py")
            || tok.ends_with(".sh")
            || tok.ends_with(".json")
            || tok.ends_with(".mjs")
        {
            if tok.starts_with("scripts/") && !skill_dir.join("scripts").is_dir() {
                continue;
            }
            if !skill_dir.join(&tok).exists() {
                problems.push(format!("{}: missing referenced file `{}`", name, tok));
            }
        }
    }
    problems
}

pub fn run(args: &[String]) -> ExitCode {
    let mut as_json = false;
    let mut dirs: Vec<PathBuf> = Vec::new();
    for a in args {
        if a == "--json" {
            as_json = true;
        } else if !a.starts_with("--") {
            dirs.push(PathBuf::from(a));
        }
    }
    if dirs.is_empty() {
        let default_parent = PathBuf::from("plugins/deepmodebot/skills");
        if let Ok(rd) = fs::read_dir(&default_parent) {
            for e in rd.flatten() {
                if e.path().is_dir() {
                    dirs.push(e.path());
                }
            }
        }
        dirs.sort();
    }

    let mut siblings: HashSet<String> = HashSet::new();
    for d in &dirs {
        if let Some(parent) = d.parent() {
            if let Ok(rd) = fs::read_dir(parent) {
                for e in rd.flatten() {
                    if e.path().is_dir() {
                        siblings.insert(e.file_name().to_string_lossy().into_owned());
                    }
                }
            }
        }
    }

    let per_skill = parallel_map(&dirs, |d| check_one_skill(d, &siblings));
    let problems: Vec<String> = per_skill.into_iter().flatten().collect();
    let ok = problems.is_empty();

    if as_json {
        let items: Vec<String> = problems.iter().map(|p| json_escape(p)).collect();
        println!(
            "{{\"engine\":\"rust-parallel\",\"skills\":{},\"ok\":{},\"problems\":[{}]}}",
            dirs.len(),
            ok,
            items.join(",")
        );
    } else if ok {
        println!("dmb-gate skill-check [OK]: {} skill(s) validated", dirs.len());
    } else {
        println!("dmb-gate skill-check [FAIL]: {} problem(s)", problems.len());
        for p in &problems {
            println!("  - {}", p);
        }
    }

    if ok {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(1)
    }
}
