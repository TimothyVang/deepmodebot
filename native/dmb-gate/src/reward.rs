use crate::util::{json_escape, parallel_map, sha256_hex};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RewardFinding {
    pub severity: &'static str,
    pub rule: &'static str,
    pub file: String,
    pub line: usize,
    pub message: String,
    pub fix: &'static str,
}

const MIN_FLOOR_EPSILON: f64 = 1e-4;

fn metric_min_floor(metric: &str) -> f64 {
    match metric {
        "iou" | "ssim" | "dice" | "f1" | "auc" | "accuracy" | "acc" | "precision" | "recall"
        | "fidelity" | "similarity" | "coverage" | "pass_rate" | "win_rate" => 0.50,
        "clip" | "clip_score" | "ap" | "map" | "bleu" | "rouge" => 0.15,
        "psnr" => 10.0,
        "protrusion" => 0.02,
        "score" | "confidence" | "symmetry" => 0.05,
        _ => MIN_FLOOR_EPSILON,
    }
}
const BARE_LOWER_METRICS: &[&str] = &[
    "iou",
    "ssim",
    "psnr",
    "clip_score",
    "dice",
    "f1",
    "auc",
    "bleu",
    "rouge",
    "accuracy",
    "precision",
    "recall",
    "fidelity",
    "similarity",
    "coverage",
    "pass_rate",
    "win_rate",
    "score",
    "confidence",
    "protrusion",
    "symmetry",
];

const QUAL_LOWER_METRICS: &[&str] = &[
    "iou",
    "ssim",
    "psnr",
    "clip",
    "clip_score",
    "dice",
    "f1",
    "auc",
    "ap",
    "map",
    "bleu",
    "rouge",
    "accuracy",
    "acc",
    "precision",
    "recall",
    "fidelity",
    "similarity",
    "coverage",
    "pass_rate",
    "win_rate",
    "score",
    "confidence",
    "protrusion",
    "symmetry",
];

const BARE_UPPER_METRICS: &[&str] = &[
    "mse",
    "mae",
    "rmse",
    "lpips",
    "chamfer",
    "hausdorff",
    "drift",
    "tolerance",
    "holes",
    "non_manifold",
];

const QUAL_UPPER_METRICS: &[&str] = &[
    "mse",
    "mae",
    "rmse",
    "lpips",
    "chamfer",
    "hausdorff",
    "drift",
    "tolerance",
    "holes",
    "non_manifold",
    "err",
    "error",
    "loss",
    "tol",
    "epsilon",
    "eps",
];

const SKIP_FLAGS: &[&str] = &[
    "--skip-gate",
    "--skip-gates",
    "--skip-verify",
    "--skip-validation",
    "--skip-reference",
    "--skip-fidelity",
    "--bypass-gate",
    "--pass-if-no-tests",
    "--passWithNoTests",
];

const PRIMITIVE_CALLS: &[&str] = &[
    "bpy.ops.mesh.primitive_cube_add",
    "bpy.ops.mesh.primitive_cone_add",
    "bpy.ops.mesh.primitive_cylinder_add",
    "bpy.ops.mesh.primitive_uv_sphere_add",
    "bpy.ops.mesh.primitive_ico_sphere_add",
    "bpy.ops.mesh.primitive_torus_add",
    "bpy.ops.mesh.primitive_monkey_add",
    "bpy.ops.mesh.primitive_plane_add",
    "bpy.ops.mesh.primitive_grid_add",
    "trimesh.creation.box(",
    "trimesh.creation.cone(",
    "trimesh.creation.cylinder(",
    "trimesh.creation.icosphere(",
    "trimesh.creation.uv_sphere(",
    "trimesh.creation.capsule(",
    "trimesh.creation.annulus(",
    "create_cube(",
    "create_cone(",
    "create_cylinder(",
    "create_uv_sphere(",
    "create_icosphere(",
];

fn git(root: &Path, args: &[&str]) -> Option<(bool, String)> {
    let out = Command::new("git")
        .arg("-c")
        .arg("core.quotePath=false")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .ok()?;
    Some((
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
    ))
}

fn is_test_file(rel: &str) -> bool {
    let low = rel.to_ascii_lowercase();
    low.starts_with("tests/")
        || low.starts_with("test/")
        || low.starts_with("spec/")
        || low.starts_with("__tests__/")
        || low.starts_with("evals/")
        || low.contains("/tests/")
        || low.contains("/test/")
        || low.contains("/spec/")
        || low.contains("/__tests__/")
        || low.contains("/evals/")
        || low.starts_with("test_")
        || low.contains("/test_")
        || low.contains("_test.")
        || low.contains(".test.")
        || low.contains(".spec.")
}

fn is_gate_or_eval_file(rel: &str) -> bool {
    let low = rel.to_ascii_lowercase();
    low.starts_with("gate/")
        || low.starts_with("gates/")
        || low.starts_with("eval/")
        || low.starts_with("evals/")
        || low.starts_with("bench/")
        || low.starts_with("benchmarks/")
        || low.starts_with("validators/")
        || low.contains("/gate/")
        || low.contains("/gates/")
        || low.contains("/eval/")
        || low.contains("/evals/")
        || low.contains("/bench/")
        || low.contains("/benchmarks/")
        || low.contains("/validators/")
        || ["gate.", "eval.", "bench.", "validator.", "fidelity.", "metric.", "scorer."]
            .iter()
            .any(|s| low.contains(s))
}

fn is_scanner_or_comment(ext: &str, line: &str) -> bool {
    let s = line.trim();
    if s.is_empty() || ext == "md" {
        return true;
    }
    for meta in [
        "re.compile(",
        "Regex::new",
        "THRESHOLD_ZERO_RE",
        "CLI_MIN_VAL_RE",
        "SKIP_GATE_RE",
        "PRIMITIVE_STANDIN_RE",
        "PRIMITIVE_CALLS",
        "SKIP_FLAGS",
        "HARDCODED_PASS_RE",
        "TEST_SKIP_RE",
        "TEST_SKIP_DECORATOR_RE",
        "REWARD_HACK_CMD_RE",
        "\"rule\":",
        "rule: \"",
        "Zeroed quality threshold",
        "Zero, negative, or near-zero quality threshold",
        "Goodhart / Anti-Reward-Hacking",
        "`--min-",
    ] {
        if line.contains(meta) {
            return true;
        }
    }
    if matches!(ext, "py" | "sh" | "yml" | "yaml" | "toml")
        && s.starts_with('#')
        && !s.starts_with("#[")
    {
        return true;
    }
    if matches!(ext, "js" | "mjs" | "cjs" | "ts" | "tsx" | "jsx" | "rs" | "go")
        && s.starts_with("//")
    {
        return true;
    }
    false
}

fn parse_leading_f64(raw: &str) -> Option<f64> {
    let t = raw
        .trim_start()
        .trim_start_matches([',', ' ', '\t'])
        .trim_start_matches(['"', '\''])
        .trim_start();
    let low = t.to_ascii_lowercase();
    for (tok, v) in [
        ("-infinity", f64::NEG_INFINITY),
        ("+infinity", f64::INFINITY),
        ("infinity", f64::INFINITY),
        ("-inf", f64::NEG_INFINITY),
        ("+inf", f64::INFINITY),
        ("inf", f64::INFINITY),
        ("-nan", f64::NAN),
        ("+nan", f64::NAN),
        ("nan", f64::NAN),
    ] {
        if let Some(rest) = low.strip_prefix(tok) {
            if rest.is_empty() || (!rest.as_bytes()[0].is_ascii_alphanumeric() && rest.as_bytes()[0] != b'_') {
                return Some(v);
            }
        }
    }
    let bytes = t.as_bytes();
    let mut i = 0;
    if i < bytes.len() && (bytes[i] == b'-' || bytes[i] == b'+') {
        i += 1;
    }
    let mut digits_seen = 0usize;
    while i < bytes.len() && (bytes[i].is_ascii_digit() || bytes[i] == b'_') {
        if bytes[i].is_ascii_digit() {
            digits_seen += 1;
        }
        i += 1;
    }
    if i < bytes.len() && bytes[i] == b'.' {
        i += 1;
        while i < bytes.len() && (bytes[i].is_ascii_digit() || bytes[i] == b'_') {
            if bytes[i].is_ascii_digit() {
                digits_seen += 1;
            }
            i += 1;
        }
    }
    if digits_seen == 0 {
        return None;
    }
    if i < bytes.len() && (bytes[i] == b'e' || bytes[i] == b'E') {
        let exp_pos = i;
        i += 1;
        if i < bytes.len() && (bytes[i] == b'+' || bytes[i] == b'-') {
            i += 1;
        }
        let exp_digits = i;
        while i < bytes.len() && (bytes[i].is_ascii_digit() || bytes[i] == b'_') {
            i += 1;
        }
        if i == exp_digits {
            i = exp_pos;
        }
    }
    if i < bytes.len() && (bytes[i].is_ascii_alphanumeric() || bytes[i] == b'_') {
        return None;
    }
    let cleaned: String = t[..i].chars().filter(|c| *c != '_').collect();
    cleaned.parse::<f64>().ok()
}

fn prefix_metric_floor(tok: &str) -> Option<f64> {
    let norm = tok.replace('-', "_");
    if QUAL_LOWER_METRICS.contains(&norm.as_str()) {
        return Some(metric_min_floor(&norm));
    }
    if norm.is_empty() {
        return None;
    }
    let mut best: Option<f64> = None;
    for m in QUAL_LOWER_METRICS {
        if m.starts_with(&norm) {
            let f = metric_min_floor(m);
            best = Some(best.map_or(f, |b| b.max(f)));
        }
    }
    best
}

pub fn has_threshold_zero_or_skip(line: &str) -> bool {
    let low = line.to_ascii_lowercase();
    for flag_pref in ["--min-", "--gate-min-"] {
        let mut cfrom = 0;
        while let Some(rel) = low[cfrom..].find(flag_pref) {
            let pos = cfrom + rel;
            let name_start = pos + flag_pref.len();
            cfrom = name_start;
            if pos > 0
                && (low.as_bytes()[pos - 1].is_ascii_alphanumeric()
                    || low.as_bytes()[pos - 1] == b'_')
            {
                continue;
            }
            let name_len = low[name_start..]
                .bytes()
                .take_while(|b| b.is_ascii_alphanumeric() || *b == b'-' || *b == b'_')
                .count();
            if name_len == 0 {
                continue;
            }
            let tok = &low[name_start..name_start + name_len];
            let Some(floor) = prefix_metric_floor(tok) else {
                continue;
            };
            let tail = low[name_start + name_len..].trim_start_matches(['"', '\'']);
            if let Some(rest) = tail
                .strip_prefix('=')
                .or_else(|| tail.strip_prefix(','))
                .or_else(|| tail.strip_prefix(' '))
                .or_else(|| tail.strip_prefix('\t'))
            {
                if let Some(val) = parse_leading_f64(rest) {
                    if !val.is_finite() || val < floor {
                        return true;
                    }
                }
            }
        }
    }
    for bare_pref in ["--min", "--mi", "--gate-min", "--gate-mi"] {
        let mut bfrom = 0;
        while let Some(rel) = low[bfrom..].find(bare_pref) {
            let pos = bfrom + rel;
            let end = pos + bare_pref.len();
            bfrom = end;
            if pos > 0
                && (low.as_bytes()[pos - 1].is_ascii_alphanumeric()
                    || low.as_bytes()[pos - 1] == b'_')
            {
                continue;
            }
            if end < low.len()
                && (low.as_bytes()[end].is_ascii_alphanumeric()
                    || low.as_bytes()[end] == b'-'
                    || low.as_bytes()[end] == b'_')
            {
                continue;
            }
            let tail = low[end..].trim_start_matches(['"', '\'']);
            if let Some(rest) = tail
                .strip_prefix('=')
                .or_else(|| tail.strip_prefix(','))
                .or_else(|| tail.strip_prefix(' '))
                .or_else(|| tail.strip_prefix('\t'))
            {
                if let Some(val) = parse_leading_f64(rest) {
                    if !val.is_finite() || val < 0.50 {
                        return true;
                    }
                }
            }
        }
    }
    for m in QUAL_LOWER_METRICS {
        let floor = metric_min_floor(m);
        for pref in ["min_", "minimum_"] {
            let kw = format!("{}{}", pref, m);
            let mut from = 0;
            while let Some(rel) = low[from..].find(&kw) {
                let pos = from + rel;
                let end = pos + kw.len();
                from = end;
                let prev_ok = pos == 0
                    || (!low.as_bytes()[pos - 1].is_ascii_alphanumeric()
                        && low.as_bytes()[pos - 1] != b'_');
                let next_ok = end >= low.len()
                    || (!low.as_bytes()[end].is_ascii_alphanumeric()
                        && low.as_bytes()[end] != b'_');
                if !prev_ok || !next_ok {
                    continue;
                }
                let rest = low[end..].trim_start_matches(['"', '\'']).trim_start();
                if let Some(val_part) = rest
                    .strip_prefix('=')
                    .filter(|s| !s.starts_with('='))
                    .or_else(|| rest.strip_prefix(':'))
                {
                    if let Some(val) = parse_leading_f64(val_part) {
                        if !val.is_finite() || val < floor {
                            return true;
                        }
                    }
                }
            }
        }
    }
    for flag in SKIP_FLAGS {
        if line.contains(flag) {
            return true;
        }
    }
    if low.contains("git commit") && (low.contains(" --no-verify") || low.contains(" -n ")) {
        return true;
    }
    for (flag_kw, bad_val) in [
        ("--require-spark-receipt", "false"),
        ("--gate-mode", "off"),
        ("--measured-gates", "off"),
        ("--skip-heavy-renders", "true"),
        ("--check-360", "false"),
    ] {
        if let Some(pos) = low.find(flag_kw) {
            let tail = low[pos + flag_kw.len()..].trim_start_matches(['"', '\'']);
            if let Some(rest) = tail
                .strip_prefix('=')
                .or_else(|| tail.strip_prefix(','))
                .or_else(|| tail.strip_prefix(' '))
            {
                let val = rest.trim_start_matches([' ', '"', '\'']);
                if val.starts_with(bad_val) {
                    return true;
                }
            }
        }
    }
    for kw in ["skip_reference", "skip_validation", "skip_fidelity", "bypass_gate"] {
        if let Some(pos) = low.find(kw) {
            let rest = low[pos + kw.len()..].trim_start();
            if let Some(v) = rest.strip_prefix('=').or_else(|| rest.strip_prefix(':')) {
                let vt = v.trim_start();
                if vt.starts_with("true") || vt.starts_with('1') {
                    return true;
                }
            }
        }
    }
    for kw in ["check_reference", "verify_reference", "enforce_provenance"] {
        if let Some(pos) = low.find(kw) {
            let rest = low[pos + kw.len()..].trim_start();
            if let Some(v) = rest.strip_prefix('=').or_else(|| rest.strip_prefix(':')) {
                let vt = v.trim_start();
                if vt.starts_with("false") || vt.starts_with('0') {
                    return true;
                }
            }
        }
    }
    false
}

pub fn has_test_skip(line: &str) -> bool {
    let indent = line.bytes().take_while(|b| *b == b' ').count();
    let t = line.trim_start();
    if t.starts_with('"') || t.starts_with('\'') {
        return false;
    }
    if t.starts_with("#[ignore") || t.starts_with("# [ignore") {
        return true;
    }
    for pat in ["@pytest.mark.skip", "@unittest.skip"] {
        if let Some(after) = t.strip_prefix(pat) {
            if !after.starts_with("If") && !after.starts_with("Unless") && !after.starts_with("if")
            {
                return true;
            }
        }
    }
    if indent <= 4 && (t.starts_with("pytest.skip(") || t.starts_with("unittest.skip(")) {
        return true;
    }
    for pat in ["it.skip(", "test.skip(", "describe.skip("] {
        if let Some(after) = t.strip_prefix(pat) {
            let arg = after.trim_start();
            if arg.is_empty()
                || arg.starts_with(')')
                || arg.starts_with('\'')
                || arg.starts_with('"')
                || arg.starts_with('`')
            {
                return true;
            }
        }
    }
    false
}

pub fn find_rs_cfg_test_line(txt: &str) -> Option<usize> {
    let lines: Vec<&str> = txt.lines().collect();
    for (idx, fl) in lines.iter().enumerate() {
        if fl.trim().starts_with("#[cfg(test)]") {
            let mut j = idx + 1;
            while j < lines.len() {
                let nxt = lines[j].trim();
                if nxt.is_empty() || nxt.starts_with("//") || nxt.starts_with("#[") {
                    j += 1;
                    continue;
                }
                if nxt.starts_with("mod ")
                    || nxt.starts_with("pub mod ")
                    || nxt.starts_with("pub(crate) mod ")
                {
                    return Some(idx + 1);
                }
                break;
            }
        }
    }
    None
}

pub fn has_primitive_standin(line: &str) -> bool {
    PRIMITIVE_CALLS.iter().any(|p| line.contains(p))
}

pub fn has_hardcoded_pass(line: &str) -> bool {
    let low = line.to_ascii_lowercase();
    if !low.contains("return") || !low.contains('{') || !low.contains("1.0") {
        return false;
    }
    let has_pass_key = [
        "\"pass\"",
        "'pass'",
        "\"passed\"",
        "'passed'",
        "\"ok\"",
        "'ok'",
        "\"verdict\"",
        "'verdict'",
    ]
    .iter()
    .any(|k| low.contains(k));
    let has_metric_key = [
        "\"iou\"",
        "'iou'",
        "\"ssim\"",
        "'ssim'",
        "\"psnr\"",
        "'psnr'",
        "\"score\"",
        "'score'",
        "\"fidelity\"",
        "'fidelity'",
    ]
    .iter()
    .any(|k| low.contains(k));
    let has_pass_val = low.contains("true") || low.contains("\"pass\"") || low.contains("'pass'");
    has_pass_key && has_metric_key && has_pass_val
}

fn match_ident_bound(low: &str, cand: &str, allow_assign: bool) -> Option<f64> {
    let mut from = 0;
    while let Some(rel) = low[from..].find(cand) {
        let pos = from + rel;
        let end = pos + cand.len();
        from = end;
        let prev_ok = pos == 0
            || (!low.as_bytes()[pos - 1].is_ascii_alphanumeric()
                && low.as_bytes()[pos - 1] != b'_'
                && low.as_bytes()[pos - 1] != b'.');
        let next_ok = end >= low.len()
            || (!low.as_bytes()[end].is_ascii_alphanumeric() && low.as_bytes()[end] != b'_');
        if !prev_ok || !next_ok {
            continue;
        }
        let rest = low[end..].trim_start();
        let ineq = rest
            .strip_prefix(">=")
            .or_else(|| rest.strip_prefix("<="))
            .or_else(|| rest.strip_prefix('>'))
            .or_else(|| rest.strip_prefix('<'));
        if let Some(vs) = ineq {
            if let Some(val) = parse_leading_f64(vs) {
                return Some(val);
            }
        } else if allow_assign {
            let assign = rest
                .strip_prefix('=')
                .filter(|s| !s.starts_with('='))
                .or_else(|| rest.strip_prefix(':'));
            if let Some(vs) = assign {
                if let Some(val) = parse_leading_f64(vs) {
                    return Some(val);
                }
            }
        }
    }
    None
}

fn extract_metric_bounds(
    lines: &[String],
    upper: bool,
    is_test_or_gate: bool,
) -> BTreeMap<String, f64> {
    let mut map = BTreeMap::new();
    let qual_metrics = if upper { QUAL_UPPER_METRICS } else { QUAL_LOWER_METRICS };
    let bare_metrics = if upper { BARE_UPPER_METRICS } else { BARE_LOWER_METRICS };
    let cli_prefix = if upper { "max" } else { "min" };

    for line in lines {
        if is_scanner_or_comment("py", line) {
            continue;
        }
        let low = line.to_ascii_lowercase();
        if upper {
            if let Some(pos) = low.find("--tolerance") {
                let rest = low[pos + "--tolerance".len()..].trim_start_matches(['"', '\'']);
                if let Some(vp) = rest
                    .strip_prefix('=')
                    .or_else(|| rest.strip_prefix(','))
                    .or_else(|| rest.strip_prefix(' '))
                {
                    if let Some(val) = parse_leading_f64(vp) {
                        map.insert("tolerance".to_string(), val);
                    }
                }
            }
            if let Some(val) = match_ident_bound(&low, "tolerance", true) {
                map.insert("tolerance".to_string(), val);
            }
        }
        for m in qual_metrics {
            let cli = format!("--{}-{}", cli_prefix, m.replace('_', "-"));
            if let Some(pos) = low.find(&cli) {
                let rest = low[pos + cli.len()..].trim_start_matches(['"', '\'']);
                if let Some(vpart) = rest
                    .strip_prefix('=')
                    .or_else(|| rest.strip_prefix(','))
                    .or_else(|| rest.strip_prefix(' '))
                {
                    if let Some(val) = parse_leading_f64(vpart) {
                        map.insert(format!("{}_{}", cli_prefix, m), val);
                    }
                }
            }
            let qual_forms: Vec<String> = if upper {
                vec![
                    format!("max_{}", m),
                    format!("maximum_{}", m),
                    format!("{}_threshold", m),
                    format!("{}_max", m),
                    format!("{}_ceiling", m),
                    format!("{}_limit", m),
                ]
            } else {
                vec![
                    format!("min_{}", m),
                    format!("minimum_{}", m),
                    format!("{}_threshold", m),
                    format!("{}_min", m),
                    format!("{}_floor", m),
                ]
            };
            for qcand in qual_forms {
                if let Some(val) = match_ident_bound(&low, &qcand, true) {
                    map.insert(qcand, val);
                }
            }
        }
        for bm in bare_metrics {
            if let Some(val) = match_ident_bound(&low, bm, is_test_or_gate) {
                map.entry((*bm).to_string()).or_insert(val);
            }
        }
    }
    map
}

pub fn scan_hunk_weakening(
    rel: &str,
    hunks: &[(Vec<String>, Vec<(usize, String)>)],
    is_test_or_gate: bool,
    out: &mut Vec<RewardFinding>,
) {
    for (rem, add) in hunks {
        if rem.is_empty() || add.is_empty() {
            continue;
        }
        let ln = add[0].0;
        let add_only: Vec<String> = add.iter().map(|(_, s)| s.clone()).collect();
        let old_low = extract_metric_bounds(rem, false, is_test_or_gate);
        let new_low = extract_metric_bounds(&add_only, false, is_test_or_gate);
        for (k, old_v) in &old_low {
            if let Some(new_v) = new_low.get(k) {
                if *old_v > 0.0 && *new_v < *old_v {
                    out.push(RewardFinding {
                        severity: "P0",
                        rule: "reward-hack-assertion-weakened",
                        file: rel.to_string(),
                        line: ln,
                        message: format!(
                            "Quality/fidelity lower bound `{}` weakened from `{}` to `{}`.",
                            k, old_v, new_v
                        ),
                        fix: "Restore the original acceptance threshold and fix the implementation to meet it.",
                    });
                }
            }
        }
        let old_up = extract_metric_bounds(rem, true, is_test_or_gate);
        let new_up = extract_metric_bounds(&add_only, true, is_test_or_gate);
        for (k, old_v) in &old_up {
            if let Some(new_v) = new_up.get(k) {
                if *new_v > *old_v {
                    out.push(RewardFinding {
                        severity: "P0",
                        rule: "reward-hack-assertion-weakened",
                        file: rel.to_string(),
                        line: ln,
                        message: format!(
                            "Error/defect upper bound `{}` relaxed from `{}` to `{}`.",
                            k, old_v, new_v
                        ),
                        fix: "Keep the stricter defect/tolerance bound and fix the underlying output.",
                    });
                }
            }
        }
    }
}

pub fn diff_file_hunks(
    root: &Path,
    rel: &str,
    staged: bool,
    base: Option<&str>,
) -> (Vec<(usize, String)>, Vec<(Vec<String>, Vec<(usize, String)>)>) {
    let full = root.join(rel);
    let Ok(meta) = fs::symlink_metadata(&full) else {
        return (Vec::new(), Vec::new());
    };
    if meta.file_type().is_symlink() || !meta.is_file() || meta.len() > 1_048_576 {
        return (Vec::new(), Vec::new());
    }
    let has_head = git(root, &["rev-parse", "--verify", "HEAD"])
        .map(|(ok, _)| ok)
        .unwrap_or(false);
    let tracked = git(root, &["ls-files", "--error-unmatch", "--", rel])
        .map(|(ok, _)| ok)
        .unwrap_or(false);
    if (!has_head || !tracked) && !staged {
        let Ok(txt) = fs::read_to_string(&full) else {
            return (Vec::new(), Vec::new());
        };
        let added: Vec<(usize, String)> = txt
            .lines()
            .enumerate()
            .map(|(i, l)| (i + 1, l.to_string()))
            .collect();
        return (added.clone(), vec![(Vec::new(), added)]);
    }
    let args: Vec<&str> = if staged {
        vec!["diff", "--cached", "-U0", "--", rel]
    } else if let Some(b) = base {
        vec!["diff", b, "-U0", "--", rel]
    } else {
        vec!["diff", "HEAD", "-U0", "--", rel]
    };
    let Some((true, diff)) = git(root, &args) else {
        return (Vec::new(), Vec::new());
    };
    let mut added = Vec::new();
    let mut hunks = Vec::new();
    let mut cur_rem = Vec::new();
    let mut cur_add = Vec::new();
    let mut cur_line: usize = 0;
    for raw in diff.lines() {
        if let Some(rest) = raw.strip_prefix("@@ ") {
            if !cur_rem.is_empty() || !cur_add.is_empty() {
                hunks.push((cur_rem, cur_add));
                cur_rem = Vec::new();
                cur_add = Vec::new();
            }
            if let Some(plus_idx) = rest.find('+') {
                let num: String = rest[plus_idx + 1..]
                    .chars()
                    .take_while(|c| c.is_ascii_digit())
                    .collect();
                cur_line = num.parse::<usize>().unwrap_or(0);
            }
        } else if raw.starts_with('-') && !raw.starts_with("---") {
            cur_rem.push(raw[1..].to_string());
        } else if raw.starts_with('+') && !raw.starts_with("+++") {
            let s = raw[1..].to_string();
            added.push((cur_line, s.clone()));
            cur_add.push((cur_line, s));
            cur_line += 1;
        }
    }
    if !cur_rem.is_empty() || !cur_add.is_empty() {
        hunks.push((cur_rem, cur_add));
    }
    (added, hunks)
}

pub fn scan_file_reward_hacks(
    rel: &str,
    added: &[(usize, String)],
    hunks: &[(Vec<String>, Vec<(usize, String)>)],
    allow_primitives: bool,
    include_primitives: bool,
    rs_cfg_test_line: Option<usize>,
    out: &mut Vec<RewardFinding>,
) {
    let norm_rel = rel.replace('\\', "/");
    let ext = Path::new(&norm_rel)
        .extension()
        .and_then(|e| e.to_str())
        .map(|s| s.to_ascii_lowercase())
        .unwrap_or_default();
    if ext == "md"
        || norm_rel.ends_with("assets/reward-guard/reward_guard.py")
        || norm_rel.ends_with("assets/reward-guard/test_reward_guard.py")
        || norm_rel.ends_with("native/dmb-gate/src/reward.rs")
        || norm_rel.ends_with("scripts/antigravity-guard.mjs")
        || norm_rel.ends_with("assets/contain/claude_guard.py")
        || norm_rel.ends_with("assets/contain/test_contain.py")
        || norm_rel.ends_with("assets/contain/test_antigravity_guard.py")
        || norm_rel.ends_with("assets/git-guardrails/git-guard-patterns.txt")
        || norm_rel.ends_with("assets/git-guardrails/git-guard.ts")
        || norm_rel.ends_with("assets/git-guardrails/git-guard.sh")
        || norm_rel.ends_with("assets/git-guardrails/test_git_guard.py")
    {
        return;
    }
    let test_file = is_test_file(&norm_rel);
    let gate_file = is_gate_or_eval_file(&norm_rel);
    for (ln, line) in added {
        if is_scanner_or_comment(&ext, line) {
            continue;
        }
        let in_test_ctx = test_file || rs_cfg_test_line.map(|cfg_ln| *ln >= cfg_ln).unwrap_or(false);
        if in_test_ctx && has_test_skip(line) {
            out.push(RewardFinding {
                severity: "P1",
                rule: "reward-hack-test-skip",
                file: rel.to_string(),
                line: *ln,
                message: "Unconditional test skip added (`skip` / `#[ignore]`) silences a failing check.".to_string(),
                fix: "Fix the failing behavior instead of skipping the test.",
            });
        }
        if in_test_ctx {
            continue;
        }
        if has_threshold_zero_or_skip(line) {
            out.push(RewardFinding {
                severity: "P0",
                rule: "reward-hack-threshold-zero",
                file: rel.to_string(),
                line: *ln,
                message: "Sub-floor quality threshold (e.g. `--min-iou < 0.50` / `min_*` below metric floor) or gate/reference skip flag bypasses real evaluation.".to_string(),
                fix: "Score directly against the reference artwork/contract above the metric floor (`>= 0.50` for IoU/SSIM/F1/fidelity) and remove skip flags.",
            });
        }
        if include_primitives && !allow_primitives && has_primitive_standin(line) {
            out.push(RewardFinding {
                severity: "P1",
                rule: "reward-hack-primitive-standin",
                file: rel.to_string(),
                line: *ln,
                message: "Local procedural primitive geometry (`cube`/`cone`/`sphere`/`cylinder`) added in production/pipeline code.".to_string(),
                fix: "Produce the asset via the real upstream generator/solver with a provenance receipt, or pass `--allow-primitives` for genuine CAD/procedural geometry.",
            });
        }
        if has_hardcoded_pass(line) {
            out.push(RewardFinding {
                severity: "P1",
                rule: "reward-hack-hardcoded-pass",
                file: rel.to_string(),
                line: *ln,
                message: "Hardcoded pass/perfect-metric return literal spoofs gate evaluation.".to_string(),
                fix: "Compute the metric from real rendered/runtime output against the reference input.",
            });
        }
    }
    let filtered_hunks: Vec<(Vec<String>, Vec<(usize, String)>)> = hunks
        .iter()
        .filter_map(|(rem, add)| {
            let kept: Vec<(usize, String)> = add
                .iter()
                .filter(|(ln, _)| rs_cfg_test_line.map(|cfg_ln| *ln < cfg_ln).unwrap_or(true))
                .cloned()
                .collect();
            if kept.is_empty() {
                None
            } else {
                Some((rem.clone(), kept))
            }
        })
        .collect();
    scan_hunk_weakening(rel, &filtered_hunks, test_file || gate_file, out);
}

fn read_json_string(s: &str) -> Option<(String, usize)> {
    let rest = s.strip_prefix('"')?;
    let mut out = String::new();
    let mut chars = rest.char_indices();
    while let Some((idx, ch)) = chars.next() {
        if ch == '"' {
            return Some((out, idx + 2));
        }
        if ch == '\\' {
            let (_, esc) = chars.next()?;
            match esc {
                '"' | '\\' | '/' => out.push(esc),
                'n' => out.push('\n'),
                'r' => out.push('\r'),
                't' => out.push('\t'),
                'u' => {
                    let mut hex = String::with_capacity(4);
                    for _ in 0..4 {
                        let (_, hc) = chars.next()?;
                        hex.push(hc);
                    }
                    if let Ok(cp) = u32::from_str_radix(&hex, 16) {
                        if let Some(uc) = char::from_u32(cp) {
                            out.push(uc);
                        }
                    }
                }
                other => out.push(other),
            }
        } else {
            out.push(ch);
        }
    }
    None
}

fn parse_json_string_map(txt: &str, section_key: &str) -> Vec<(String, String)> {
    let mut pairs = Vec::new();
    let needle = format!("\"{}\"", section_key);
    let Some(pos) = txt.find(&needle) else {
        return pairs;
    };
    let after_key = txt[pos + needle.len()..].trim_start();
    let Some(after_colon) = after_key.strip_prefix(':') else {
        return pairs;
    };
    let obj_start = after_colon.trim_start();
    let Some(mut cur) = obj_start.strip_prefix('{') else {
        return pairs;
    };
    loop {
        cur = cur.trim_start();
        if let Some(rest) = cur.strip_prefix(',') {
            cur = rest.trim_start();
        }
        if cur.starts_with('}') || cur.is_empty() {
            break;
        }
        let Some((k, klen)) = read_json_string(cur) else {
            break;
        };
        cur = cur[klen..].trim_start();
        let Some(after_c) = cur.strip_prefix(':') else {
            break;
        };
        cur = after_c.trim_start();
        let Some((v, vlen)) = read_json_string(cur) else {
            break;
        };
        cur = &cur[vlen..];
        pairs.push((k, v));
    }
    pairs
}

fn check_contract_locks(root: &Path, out: &mut Vec<RewardFinding>) {
    let rg_dir = root.join(".scratch").join("reward-guard");
    let Ok(entries) = fs::read_dir(&rg_dir) else {
        return;
    };
    for entry in entries.flatten() {
        let sdir = entry.path();
        if !sdir.is_dir() {
            continue;
        }
        let slug = sdir
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("contract");
        let lock_path = sdir.join("contract-lock.json");
        let db_path = sdir.join("reward-guard.db");
        if db_path.is_file() && !lock_path.is_file() {
            out.push(RewardFinding {
                severity: "P0",
                rule: "reward-hack-contract-tampered",
                file: format!(".scratch/reward-guard/{}/contract-lock.json", slug),
                line: 1,
                message: format!("Contract lock file for `{}` was deleted while SQLite contract exists.", slug),
                fix: "Restore contract-lock.json or re-lock only with explicit operator --force.",
            });
            continue;
        }
        let Ok(txt) = fs::read_to_string(&lock_path) else {
            continue;
        };
        for section in ["gates", "references"] {
            for (rel_p, expected_sha) in parse_json_string_map(&txt, section) {
                if expected_sha.len() == 64 {
                    let live_sha = fs::read(root.join(&rel_p))
                        .map(|b| sha256_hex(&b))
                        .unwrap_or_else(|_| "MISSING".to_string());
                    if live_sha != expected_sha {
                        out.push(RewardFinding {
                            severity: "P0",
                            rule: "reward-hack-contract-tampered",
                            file: rel_p.clone(),
                            line: 1,
                            message: format!(
                                "Locked contract file `{}` was modified or deleted (`{}` != `{}`).",
                                rel_p,
                                &live_sha[..live_sha.len().min(10)],
                                &expected_sha[..10]
                            ),
                            fix: "Revert edits to locked gate/test/reference files so the builder never weakens its own oracle.",
                        });
                    }
                }
            }
        }
    }
}

fn norm_rel_arg(raw: &str) -> String {
    let mut s = raw.trim().replace('\\', "/");
    while let Some(rest) = s.strip_prefix("./") {
        s = rest.to_string();
    }
    s.trim_start_matches('/').to_string()
}

fn discover_scratch_scripts(root: &Path) -> Vec<String> {
    let scratch = root.join(".scratch");
    if !scratch.is_dir() {
        return Vec::new();
    }
    let skip_top = [
        "reward-guard",
        "self-grill",
        "evidence",
        "goals",
        "gen-ui",
        "agents-md-backup",
        "quota-guard",
    ];
    let mut found = Vec::new();
    let mut stack = vec![(scratch.clone(), true)];
    while let Some((dir, is_top)) = stack.pop() {
        let Ok(entries) = fs::read_dir(&dir) else {
            continue;
        };
        for entry in entries.flatten() {
            let p = entry.path();
            let Ok(meta) = fs::symlink_metadata(&p) else {
                continue;
            };
            if meta.file_type().is_symlink() {
                continue;
            }
            let name = entry.file_name().to_string_lossy().to_string();
            if meta.is_dir() {
                let low = name.to_ascii_lowercase();
                if (is_top && skip_top.contains(&name.as_str()))
                    || low.starts_with("check-")
                    || low.starts_with("npm-test-")
                    || low.starts_with("init-cli-test-")
                    || low.starts_with("panel-")
                    || low.contains("test")
                {
                    continue;
                }
                stack.push((p, false));
            } else if meta.is_file() && meta.len() > 0 && meta.len() <= 262_144 {
                let ext = p
                    .extension()
                    .and_then(|e| e.to_str())
                    .map(|s| s.to_ascii_lowercase())
                    .unwrap_or_default();
                if matches!(ext.as_str(), "py" | "sh" | "js" | "mjs" | "cjs" | "ts") {
                    if let Ok(rel) = p.strip_prefix(root) {
                        found.push(rel.to_string_lossy().replace('\\', "/"));
                        if found.len() >= 100 {
                            return found;
                        }
                    }
                }
            }
        }
    }
    found.sort();
    found
}

fn changed_files(
    root: &Path,
    staged: bool,
    explicit: &[String],
    base: Option<&str>,
    include_scratch: bool,
) -> Vec<String> {
    if !explicit.is_empty() {
        let mut set = BTreeSet::new();
        for raw in explicit {
            for part in raw.split(',') {
                let n = norm_rel_arg(part);
                if !n.is_empty() {
                    set.insert(n);
                }
            }
        }
        return set.into_iter().collect();
    }
    let mut set = BTreeSet::new();
    let has_head = git(root, &["rev-parse", "--verify", "HEAD"])
        .map(|(ok, _)| ok)
        .unwrap_or(false);
    if staged {
        if let Some((true, out)) =
            git(root, &["diff", "--cached", "--name-only", "--diff-filter=ACMR"])
        {
            for l in out.lines().map(str::trim).filter(|l| !l.is_empty()) {
                set.insert(l.to_string());
            }
        }
    } else {
        if let Some(b) = base {
            if let Some((true, out)) = git(root, &["diff", b, "--name-only", "--diff-filter=ACMR"])
            {
                for l in out.lines().map(str::trim).filter(|l| !l.is_empty()) {
                    set.insert(l.to_string());
                }
            }
        } else if has_head {
            if let Some((true, out)) =
                git(root, &["diff", "HEAD", "--name-only", "--diff-filter=ACMR"])
            {
                for l in out.lines().map(str::trim).filter(|l| !l.is_empty()) {
                    set.insert(l.to_string());
                }
            }
        }
        if let Some((true, out)) = git(root, &["ls-files", "--others", "--exclude-standard"]) {
            for l in out.lines().map(str::trim).filter(|l| !l.is_empty()) {
                set.insert(l.to_string());
            }
        }
    }
    let mut clean: BTreeSet<String> = set
        .into_iter()
        .filter(|f| !f.starts_with(".scratch/") && !f.starts_with(".worktrees/"))
        .collect();
    if include_scratch && !staged {
        for sf in discover_scratch_scripts(root) {
            clean.insert(sf);
        }
    }
    clean.into_iter().collect()
}

pub fn run(args: &[String]) -> ExitCode {
    let mut root = PathBuf::from(".");
    let mut base_ref: Option<String> = None;
    let mut staged = false;
    let mut allow_primitives = false;
    let mut include_scratch = true;
    let mut advisory = false;
    let mut as_json = false;
    let mut explicit_files: Vec<String> = Vec::new();
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "scan" => i += 1,
            "--root" if i + 1 < args.len() => {
                root = PathBuf::from(&args[i + 1]);
                i += 2;
            }
            "--base" if i + 1 < args.len() => {
                base_ref = Some(args[i + 1].clone());
                i += 2;
            }
            "--staged" => {
                staged = true;
                i += 1;
            }
            "--allow-primitives" => {
                allow_primitives = true;
                i += 1;
            }
            "--no-scratch" => {
                include_scratch = false;
                i += 1;
            }
            "--advisory" => {
                advisory = true;
                i += 1;
            }
            "--json" => {
                as_json = true;
                i += 1;
            }
            "--files" => {
                i += 1;
                while i < args.len() && !args[i].starts_with("--") {
                    explicit_files.push(args[i].clone());
                    i += 1;
                }
            }
            other => {
                eprintln!("dmb-gate reward error: unknown or forbidden argument `{}` (self-reported `record-judge` is banned; use `run-judge`).", other);
                return ExitCode::from(2);
            }
        }
    }

    let root = fs::canonicalize(&root).unwrap_or(root);
    let changed = changed_files(&root, staged, &explicit_files, base_ref.as_deref(), include_scratch);
    let per_file = parallel_map(&changed, |rel| {
        let mut local = Vec::new();
        let (mut added, hunks) = diff_file_hunks(&root, rel, staged, base_ref.as_deref());
        let full_txt = fs::read_to_string(root.join(rel)).ok();
        let rs_cfg_ln = if rel.ends_with(".rs") {
            full_txt.as_deref().and_then(find_rs_cfg_test_line)
        } else {
            None
        };
        if added.is_empty() && !explicit_files.is_empty() {
            if let Some(txt) = &full_txt {
                added = txt
                    .lines()
                    .enumerate()
                    .map(|(idx, s)| (idx + 1, s.to_string()))
                    .collect();
            }
        }
        if !added.is_empty() || !hunks.is_empty() {
            scan_file_reward_hacks(rel, &added, &hunks, allow_primitives, true, rs_cfg_ln, &mut local);
        }
        local
    });

    let mut findings: Vec<RewardFinding> = per_file.into_iter().flatten().collect();
    check_contract_locks(&root, &mut findings);

    let p0 = findings.iter().filter(|f| f.severity == "P0").count();
    let p1 = findings.iter().filter(|f| f.severity == "P1").count();
    let p2 = findings.iter().filter(|f| f.severity == "P2").count();
    let ok = p0 == 0 && p1 == 0;

    if as_json {
        let items: Vec<String> = findings
            .iter()
            .map(|f| {
                format!(
                    "{{\"severity\":{},\"rule\":{},\"file\":{},\"line\":{},\"message\":{},\"fix\":{}}}",
                    json_escape(f.severity),
                    json_escape(f.rule),
                    json_escape(&f.file),
                    f.line,
                    json_escape(&f.message),
                    json_escape(&f.fix)
                )
            })
            .collect();
        println!(
            "{{\"ok\":{},\"engine\":\"rust-parallel\",\"files_checked\":{},\"counts\":{{\"P0\":{},\"P1\":{},\"P2\":{}}},\"findings\":[{}]}}",
            ok,
            changed.len(),
            p0,
            p1,
            p2,
            items.join(",")
        );
    } else {
        println!(
            "dmb-gate reward [{}]: {} file(s) — P0:{} P1:{} P2:{}",
            if ok { "OK" } else { "BLOCKED" },
            changed.len(),
            p0,
            p1,
            p2
        );
        for f in &findings {
            println!(
                "  {}:{} [{}:{}] {} -> {}",
                f.file, f.line, f.severity, f.rule, f.message, f.fix
            );
        }
    }

    if ok || advisory {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(1)
    }
}
