mod agents;
mod ci;
mod cleanup;
mod guard;
mod map;
mod perf;
mod skill_check;
mod slop;
mod ui;
mod util;

use std::env;
use std::process::ExitCode;

fn print_help() {
    println!(
        "dmb-gate 0.3.0 — zero-dependency parallel Rust engine (9 tools)\n\
         Usage:\n\
           dmb-gate slop [--root DIR] [--staged] [--files ...] [--no-linters] [--allow-config-change] [--json]\n\
           dmb-gate ci [run] [--root DIR] [--cached] [--jobs a,b] [--json]\n\
           dmb-gate perf [--root DIR] [--files ...] [--fail-on-high] [--json]\n\
           dmb-gate ui [PATH] [--fail-on-p1] [--json]\n\
           dmb-gate cleanup [--root DIR] [--dry-run | --apply] [--json]\n\
           dmb-gate agents [check] [--root DIR] [--json]\n\
           dmb-gate skill-check [DIR ...] [--json]\n\
           dmb-gate map [--root DIR] [--out FILE] [--json]\n\
           dmb-gate guard [--root DIR] [--path TARGET]\n\
         (Omitting the subcommand defaults to `slop` for backwards compatibility.)"
    );
}

fn main() -> ExitCode {
    let args: Vec<String> = env::args().skip(1).collect();
    let Some(first) = args.first() else {
        return slop::run(&[]);
    };
    match first.as_str() {
        "-h" | "--help" | "help" => {
            print_help();
            ExitCode::SUCCESS
        }
        "-V" | "--version" => {
            println!("dmb-gate 0.3.0");
            ExitCode::SUCCESS
        }
        "slop" => slop::run(&args[1..]),
        "ci" => ci::run(&args[1..]),
        "perf" => perf::run(&args[1..]),
        "ui" => ui::run(&args[1..]),
        "cleanup" => cleanup::run(&args[1..]),
        "agents" => agents::run(&args[1..]),
        "skill-check" => skill_check::run(&args[1..]),
        "map" => map::run(&args[1..]),
        "guard" => guard::run(&args[1..]),
        _ => slop::run(&args),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sha256_matches_nist_vectors() {
        assert_eq!(
            util::sha256_hex(b""),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
        assert_eq!(
            util::sha256_hex(b"abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
    }

    #[test]
    fn parallel_map_preserves_order_across_threads() {
        let input: Vec<usize> = (0..256).collect();
        let out = util::parallel_map(&input, |x| x * x + 1);
        let expected: Vec<usize> = input.iter().map(|x| x * x + 1).collect();
        assert_eq!(out, expected);
    }

    #[test]
    fn slop_detects_real_issues_and_ignores_quoted_scanner_literals() {
        let mut out = Vec::new();
        let fake_aws = format!("TOKEN = '{}1234567890ABCDEF'", "AKIA");
        slop::scan_added_lines(
            "src/app.py",
            &[
                (1, fake_aws),
                (2, "x = 1  # noqa".to_string()),
                (3, format!("re.compile(r'{}PRIVATE KEY-----')", "-----BEGIN ")),
            ],
            &mut out,
        );
        assert!(out.iter().any(|f| f.rule == "secret-aws-key"));
        assert!(out.iter().any(|f| f.rule == "suppression-comment"));
        assert!(!out.iter().any(|f| f.rule == "secret-private-key"));

        let mut rs_out = Vec::new();
        slop::scan_added_lines(
            "src/lib.rs",
            &[
                (1, format!("let v = opt.{}();", "unwrap")),
                (2, "if line.contains(\".unwrap()\") {}".to_string()),
            ],
            &mut rs_out,
        );
        assert_eq!(rs_out.len(), 1);
        assert_eq!(rs_out[0].line, 1);
    }

    #[test]
    fn ci_yaml_parser_and_kahn_waves_order_dependencies() {
        let yaml = "\
name: demo
jobs:
  lint:
    inputs:
      - \"src/*.rs\"
    steps:
      - name: check
        run: echo lint
  unit:
    steps:
      - run: echo unit
  gate:
    needs: [lint, unit]
    steps:
      - run: echo gate
";
        let wf = ci::parse_ci_yaml(yaml);
        assert_eq!(wf.name, "demo");
        assert_eq!(wf.jobs.len(), 3);
        let waves = ci::topo_waves(&wf.jobs).expect("valid DAG");
        assert_eq!(waves, vec![vec!["lint", "unit"], vec!["gate"]]);
    }

    #[test]
    fn perf_and_ui_scanners_catch_real_antipatterns() {
        let perf_hits = perf::scan_text(
            "api/handler.py",
            "async def get_items(conn, ids):\n    time.sleep(1)\n    for i in ids:\n        conn.execute('SELECT 1')\n",
        );
        assert!(perf_hits.iter().any(|f| f.rule_id == "PERF-ASYNC-001"));
        assert!(perf_hits.iter().any(|f| f.rule_id == "PERF-DB-001"));

        let ui_hits = ui::scan_ui(
            "web/app.css",
            ".card { transition: all 200ms ease-in; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2); }\n.drawer { transition: margin-top 180ms ease-out; background: #000000 } .scale0 { transform: scale(0); }\n",
        );
        assert!(ui_hits.iter().any(|f| f.rule == "ui-transition-all"));
        assert!(ui_hits.iter().any(|f| f.rule == "ui-ease-in"));
        assert!(ui_hits.iter().any(|f| f.rule == "ui-heavy-rgba-shadow"));
        assert!(ui_hits.iter().any(|f| f.rule == "ui-layout-transition" && f.severity == "P1"));
        assert!(ui_hits.iter().any(|f| f.rule == "ui-pure-black-surface" && f.severity == "P1"));
        assert!(ui_hits.iter().any(|f| f.rule == "ui-scale-zero" && f.severity == "P1"));

        let tsx_hits = ui::scan_ui(
            "web/Toolbar.tsx",
            "<div className=\"bg-black\">\n<input type=\"checkbox\" className=\"rounded-full\" />\n<button className=\"icon\"><i className=\"lucide-x\"></i></button>\n<button aria-label=\"\"><svg viewBox=\"0 0 16 16\"></svg></button>\n</div>\n",
        );
        assert!(tsx_hits.iter().any(|f| f.rule == "ui-pure-black-surface" && f.line == 1));
        assert!(tsx_hits.iter().any(|f| f.rule == "ui-circular-checkbox" && f.line == 2));
        assert_eq!(tsx_hits.iter().filter(|f| f.rule == "ui-icon-button-unlabeled").count(), 2);

        let legit_tsx = ui::scan_ui(
            "web/Legit.tsx",
            "/* never use transition: width 200ms; background: #000000; transform: scale(0); */\n<button type=\"button\"><svg viewBox=\"0 0 16 16\"></svg> English (US) <svg viewBox=\"0 0 12 12\"></svg></button>\n<label><input type=\"checkbox\" className=\"rounded-sm\" /><span className=\"rounded-full\">12</span></label>\n<div style={{ transition: \"transform 150ms ease-out\", width: 260, top: 10 }}>Menu</div>\n",
        );
        assert!(legit_tsx.is_empty(), "unexpected findings: {:?}", legit_tsx);

        let legit_css = ui::scan_ui(
            "web/legit.css",
            ".badge-light { background: #ffffff; color: #000000; }\n.avatar:hover { filter: grayscale(0); transform: scale(0.98); }\n.btn { transition: transform 150ms ease-out } .card { padding: 16px; }\n.icon-mask { background: url(#⌘-gradient), url(#🚀-bg); }\n:focus-visible { outline: 2px solid var(--accent); }\n@media (prefers-reduced-motion: reduce) { .btn { transition: none; } }\n",
        );
        assert!(legit_css.is_empty(), "unexpected css findings: {:?}", legit_css);
    }

    #[test]
    fn glob_match_works_for_boundaries() {
        assert!(util::glob_match("ui/*", "ui/view.py"));
        assert!(util::glob_match("plugins/**/*.py", "plugins/a/b/c.py"));
        assert!(!util::glob_match("ui/*", "core/view.py"));
    }

    #[test]
    fn map_and_guard_work_deterministically() {
        let py_syms = map::extract_symbols("py", "def alpha():\n    pass\nclass Beta:\n    pass\n");
        assert_eq!(py_syms, vec!["alpha", "Beta"]);
        let rs_syms = map::extract_symbols("rs", "pub fn gamma() {}\npub struct Delta {}\n");
        assert_eq!(rs_syms, vec!["gamma", "Delta"]);
        let go_syms = map::extract_symbols("go", "func (s *Srv) Handle() {}\ntype Config struct {}\n");
        assert_eq!(go_syms, vec!["Handle", "Config"]);

        let root = std::path::Path::new("C:/repo");
        assert!(guard::is_allowed_write(root, std::path::Path::new("C:/repo/src/a.rs"), &[]));
        assert!(!guard::is_allowed_write(root, std::path::Path::new("C:/other/a.rs"), &[]));
        assert!(guard::is_allowed_write(
            root,
            std::path::Path::new("C:/other/a.rs"),
            &[std::path::PathBuf::from("C:/other")]
        ));
    }
}
