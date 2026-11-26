use std::fs;
use std::io::{self, Read};
use std::path::{Path, PathBuf};
use std::process::ExitCode;

fn extract_json_str(json: &str, key: &str) -> Option<String> {
    let needle = format!("\"{}\"", key);
    let pos = json.find(&needle)?;
    let rest = &json[pos + needle.len()..];
    let colon = rest.find(':')?;
    let after = rest[colon + 1..].trim_start();
    if !after.starts_with('"') {
        return None;
    }
    let mut out = String::new();
    let mut chars = after[1..].chars();
    while let Some(c) = chars.next() {
        if c == '\\' {
            if let Some(esc) = chars.next() {
                match esc {
                    '\\' => out.push('\\'),
                    '"' => out.push('"'),
                    'n' => out.push('\n'),
                    _ => out.push(esc),
                }
            }
        } else if c == '"' {
            return Some(out);
        } else {
            out.push(c);
        }
    }
    None
}

fn load_extra_roots(root: &Path) -> Vec<PathBuf> {
    let mut out = Vec::new();
    let cfg = root.join(".deepmodebot.json");
    let Ok(txt) = fs::read_to_string(cfg) else {
        return out;
    };
    let Some(pos) = txt.find("\"extraWriteRoots\"") else {
        return out;
    };
    let rest = &txt[pos..];
    let Some(lb) = rest.find('[') else {
        return out;
    };
    let Some(rb) = rest[lb..].find(']') else {
        return out;
    };
    let arr = &rest[lb + 1..lb + rb];
    for part in arr.split(',') {
        let s = part.trim().trim_matches('"');
        if !s.is_empty() {
            let p = PathBuf::from(s);
            out.push(fs::canonicalize(&p).unwrap_or(p));
        }
    }
    out
}

fn normalize_path_for_prefix(p: &Path) -> String {
    let s = p.to_string_lossy().replace('\\', "/");
    let s = s.strip_prefix("//?/").unwrap_or(&s);
    if cfg!(windows) {
        s.to_ascii_lowercase()
    } else {
        s.to_string()
    }
}

pub fn is_allowed_write(root: &Path, target: &Path, extras: &[PathBuf]) -> bool {
    let abs = if target.is_absolute() {
        target.to_path_buf()
    } else {
        root.join(target)
    };
    let canon = fs::canonicalize(&abs).unwrap_or(abs);
    let target_s = normalize_path_for_prefix(&canon);

    let mut allowed = vec![fs::canonicalize(root).unwrap_or_else(|_| root.to_path_buf())];
    allowed.extend_from_slice(extras);

    for base in allowed {
        let base_s = normalize_path_for_prefix(&base);
        let base_trim = base_s.trim_end_matches('/');
        if target_s == base_trim || target_s.starts_with(&format!("{}/", base_trim)) {
            return true;
        }
    }
    false
}

pub fn run(args: &[String]) -> ExitCode {
    let mut root = PathBuf::from(".");
    let mut explicit_path: Option<String> = None;
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--root" if i + 1 < args.len() => {
                root = PathBuf::from(&args[i + 1]);
                i += 2;
            }
            "--path" if i + 1 < args.len() => {
                explicit_path = Some(args[i + 1].clone());
                i += 2;
            }
            _ => i += 1,
        }
    }
    let root = fs::canonicalize(&root).unwrap_or(root);
    let target_str = if let Some(p) = explicit_path {
        p
    } else {
        let mut buf = String::new();
        let _ = io::stdin().read_to_string(&mut buf);
        match extract_json_str(&buf, "file_path").or_else(|| extract_json_str(&buf, "path")) {
            Some(p) => p,
            None => return ExitCode::SUCCESS,
        }
    };

    let extras = load_extra_roots(&root);
    if is_allowed_write(&root, Path::new(&target_str), &extras) {
        ExitCode::SUCCESS
    } else {
        eprintln!(
            "dmb-gate guard [BLOCKED]: write to `{}` is outside project root `{}` (add to extraWriteRoots in .deepmodebot.json if intentional)",
            target_str,
            root.display()
        );
        ExitCode::from(2)
    }
}
