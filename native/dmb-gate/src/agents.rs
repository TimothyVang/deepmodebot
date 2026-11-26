use crate::util::json_escape;
use std::fs;
use std::path::PathBuf;
use std::process::ExitCode;

pub fn run(args: &[String]) -> ExitCode {
    let mut root = PathBuf::from(".");
    let mut as_json = false;
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "check" => i += 1,
            "--root" if i + 1 < args.len() => {
                root = PathBuf::from(&args[i + 1]);
                i += 2;
            }
            "--json" => {
                as_json = true;
                i += 1;
            }
            s if !s.starts_with("--") => {
                root = PathBuf::from(s);
                i += 1;
            }
            _ => i += 1,
        }
    }

    let root = fs::canonicalize(&root).unwrap_or(root);
    let agents_path = root.join("AGENTS.md");
    let claude_path = root.join("CLAUDE.md");
    let mut issues: Vec<String> = Vec::new();

    match fs::read_to_string(&agents_path) {
        Ok(txt) => {
            let lines = txt.lines().count();
            if lines > 200 {
                issues.push(format!("AGENTS.md has {} lines (> 200 budget)", lines));
            }
            if !txt.contains("<!-- deepmodebot:begin") || !txt.contains("<!-- deepmodebot:end -->") {
                issues.push("AGENTS.md missing managed deepmodebot block markers".to_string());
            }
        }
        Err(_) => issues.push("AGENTS.md is missing".to_string()),
    }

    match fs::read_to_string(&claude_path) {
        Ok(txt) => {
            if !txt.lines().any(|l| l.trim() == "@AGENTS.md") {
                issues.push("CLAUDE.md does not import @AGENTS.md".to_string());
            }
        }
        Err(_) => issues.push("CLAUDE.md is missing".to_string()),
    }

    let ok = issues.is_empty();
    if as_json {
        let items: Vec<String> = issues.iter().map(|s| json_escape(s)).collect();
        println!(
            "{{\"engine\":\"rust\",\"ok\":{},\"issues\":[{}]}}",
            ok,
            items.join(",")
        );
    } else if ok {
        println!("dmb-gate agents [OK]: AGENTS.md and CLAUDE.md in sync");
    } else {
        println!("dmb-gate agents [FAIL]:");
        for iss in &issues {
            println!("  - {}", iss);
        }
    }
    if ok {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(1)
    }
}
