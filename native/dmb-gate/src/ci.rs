use crate::util::{glob_match, json_escape, normalize_rel, parallel_map, sha256_hex, walk_files, SKIP_DIRS};
use std::collections::{BTreeMap, HashMap, HashSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};
use std::thread;
use std::time::Instant;

#[derive(Clone, Debug)]
pub struct Step {
    pub name: String,
    pub run: String,
}

#[derive(Clone, Debug)]
pub struct Job {
    pub needs: Vec<String>,
    pub inputs: Vec<String>,
    pub steps: Vec<Step>,
}

#[derive(Clone, Debug)]
pub struct Workflow {
    pub name: String,
    pub jobs: BTreeMap<String, Job>,
}

fn unquote(s: &str) -> String {
    let t = s.trim();
    if t.len() >= 2 && ((t.starts_with('"') && t.ends_with('"')) || (t.starts_with('\'') && t.ends_with('\''))) {
        let inner = &t[1..t.len() - 1];
        if t.starts_with('"') {
            return inner.replace("\\\"", "\"").replace("\\\\", "\\");
        }
        return inner.to_string();
    }
    t.to_string()
}

pub fn parse_ci_yaml(text: &str) -> Workflow {
    let mut wf_name = "local-ci".to_string();
    let mut jobs: BTreeMap<String, Job> = BTreeMap::new();
    let mut in_jobs = false;
    let mut cur_job: Option<String> = None;
    let mut section: &str = "";
    let mut cur_step: Option<Step> = None;

    let flush_step = |jobs: &mut BTreeMap<String, Job>, cur_job: &Option<String>, cur_step: &mut Option<Step>| {
        if let (Some(jid), Some(st)) = (cur_job.as_ref(), cur_step.take()) {
            if !st.run.is_empty() {
                if let Some(j) = jobs.get_mut(jid) {
                    j.steps.push(st);
                }
            }
        }
    };

    for raw in text.lines() {
        let trimmed = raw.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        let indent = raw.len() - raw.trim_start().len();
        if indent == 0 {
            flush_step(&mut jobs, &cur_job, &mut cur_step);
            if let Some(rest) = trimmed.strip_prefix("name:") {
                wf_name = unquote(rest);
            } else if trimmed == "jobs:" {
                in_jobs = true;
            } else {
                in_jobs = false;
            }
            continue;
        }
        if !in_jobs {
            continue;
        }
        if indent == 2 && trimmed.ends_with(':') {
            flush_step(&mut jobs, &cur_job, &mut cur_step);
            let jid = trimmed.trim_end_matches(':').trim().to_string();
            jobs.insert(
                jid.clone(),
                Job {
                    needs: Vec::new(),
                    inputs: Vec::new(),
                    steps: Vec::new(),
                },
            );
            cur_job = Some(jid);
            section = "";
            continue;
        }
        let Some(jid) = cur_job.clone() else {
            continue;
        };
        if indent == 4 {
            flush_step(&mut jobs, &cur_job, &mut cur_step);
            if let Some(rest) = trimmed.strip_prefix("needs:") {
                section = "needs";
                let r = rest.trim();
                if r.starts_with('[') && r.ends_with(']') {
                    let inner = &r[1..r.len() - 1];
                    if let Some(j) = jobs.get_mut(&jid) {
                        for item in inner.split(',') {
                            let v = unquote(item);
                            if !v.is_empty() {
                                j.needs.push(v);
                            }
                        }
                    }
                } else if !r.is_empty() {
                    if let Some(j) = jobs.get_mut(&jid) {
                        j.needs.push(unquote(r));
                    }
                }
            } else if trimmed == "inputs:" {
                section = "inputs";
            } else if trimmed == "steps:" {
                section = "steps";
            } else {
                section = "";
            }
            continue;
        }
        if section == "needs" && trimmed.starts_with("- ") {
            if let Some(j) = jobs.get_mut(&jid) {
                j.needs.push(unquote(&trimmed[2..]));
            }
        } else if section == "inputs" && trimmed.starts_with("- ") {
            if let Some(j) = jobs.get_mut(&jid) {
                j.inputs.push(unquote(&trimmed[2..]));
            }
        } else if section == "steps" {
            if let Some(rest) = trimmed.strip_prefix("- ") {
                flush_step(&mut jobs, &cur_job, &mut cur_step);
                let mut st = Step {
                    name: String::new(),
                    run: String::new(),
                };
                if let Some(v) = rest.strip_prefix("name:") {
                    st.name = unquote(v);
                } else if let Some(v) = rest.strip_prefix("run:") {
                    st.run = unquote(v);
                }
                cur_step = Some(st);
            } else if let Some(st) = cur_step.as_mut() {
                if let Some(v) = trimmed.strip_prefix("name:") {
                    st.name = unquote(v);
                } else if let Some(v) = trimmed.strip_prefix("run:") {
                    st.run = unquote(v);
                }
            }
        }
    }
    flush_step(&mut jobs, &cur_job, &mut cur_step);
    Workflow {
        name: wf_name,
        jobs,
    }
}

pub fn topo_waves(jobs: &BTreeMap<String, Job>) -> Result<Vec<Vec<String>>, String> {
    let mut indeg: HashMap<String, usize> = HashMap::new();
    let mut rev: HashMap<String, Vec<String>> = HashMap::new();
    for (id, j) in jobs {
        indeg.entry(id.clone()).or_insert(0);
        for dep in &j.needs {
            if !jobs.contains_key(dep) {
                return Err(format!("job `{}` needs unknown job `{}`", id, dep));
            }
            *indeg.entry(id.clone()).or_insert(0) += 1;
            rev.entry(dep.clone()).or_default().push(id.clone());
        }
    }
    let mut waves: Vec<Vec<String>> = Vec::new();
    let mut done = 0usize;
    loop {
        let mut ready: Vec<String> = indeg
            .iter()
            .filter_map(|(k, &v)| if v == 0 { Some(k.clone()) } else { None })
            .collect();
        ready.sort();
        if ready.is_empty() {
            break;
        }
        for r in &ready {
            indeg.remove(r);
            done += 1;
            if let Some(children) = rev.get(r) {
                for c in children {
                    if let Some(cnt) = indeg.get_mut(c) {
                        *cnt = cnt.saturating_sub(1);
                    }
                }
            }
        }
        waves.push(ready);
    }
    if done != jobs.len() {
        return Err("cyclic job dependency in ci.yml".to_string());
    }
    Ok(waves)
}

pub fn merkle_job_hash(root: &Path, job: &Job, all_files: &[(String, PathBuf)]) -> String {
    let mut matched: Vec<&(String, PathBuf)> = Vec::new();
    for entry in all_files {
        if job.inputs.iter().any(|pat| glob_match(pat, &entry.0)) {
            matched.push(entry);
        }
    }
    let step_sig: String = job
        .steps
        .iter()
        .map(|s| format!("{}\0{}", s.name, s.run))
        .collect::<Vec<_>>()
        .join("\n");
    let file_hashes: Vec<String> = parallel_map(&matched, |(rel, path)| {
        let bytes = fs::read(path).unwrap_or_default();
        format!("{}:{}", rel, sha256_hex(&bytes))
    });
    let mut payload = String::new();
    payload.push_str(&root.to_string_lossy());
    payload.push('\n');
    payload.push_str(&step_sig);
    payload.push('\n');
    for fh in file_hashes {
        payload.push_str(&fh);
        payload.push('\n');
    }
    sha256_hex(payload.as_bytes())
}

fn load_cache(path: &Path) -> BTreeMap<String, String> {
    let mut map = BTreeMap::new();
    let Ok(txt) = fs::read_to_string(path) else {
        return map;
    };
    for line in txt.lines() {
        if let Some((k, v)) = line.split_once('=') {
            map.insert(k.trim().to_string(), v.trim().to_string());
        }
    }
    map
}

fn save_cache(path: &Path, cache: &BTreeMap<String, String>) {
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    let mut out = String::new();
    for (k, v) in cache {
        out.push_str(k);
        out.push('=');
        out.push_str(v);
        out.push('\n');
    }
    let _ = fs::write(path, out);
}

fn run_shell(root: &Path, cmd_str: &str) -> (bool, String) {
    let mut cmd = if cfg!(windows) {
        let mut c = Command::new("cmd");
        c.arg("/C").arg(cmd_str);
        c
    } else {
        let mut c = Command::new("sh");
        c.arg("-c").arg(cmd_str);
        c
    };
    cmd.current_dir(root)
        .env("PYTHONDONTWRITEBYTECODE", "1");
    match cmd.output() {
        Ok(out) => {
            let mut combined = String::from_utf8_lossy(&out.stdout).into_owned();
            let err = String::from_utf8_lossy(&out.stderr);
            if !err.is_empty() {
                if !combined.is_empty() {
                    combined.push('\n');
                }
                combined.push_str(&err);
            }
            (out.status.success(), combined)
        }
        Err(e) => (false, format!("spawn failed: {}", e)),
    }
}

#[derive(Clone, Debug)]
struct JobResult {
    id: String,
    status: &'static str,
    seconds: f64,
    hash: Option<String>,
    tail: String,
}

pub fn run(args: &[String]) -> ExitCode {
    let mut root = PathBuf::from(".");
    let mut cached = false;
    let mut as_json = false;
    let mut filter_jobs: HashSet<String> = HashSet::new();

    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "run" => i += 1,
            "--root" if i + 1 < args.len() => {
                root = PathBuf::from(&args[i + 1]);
                i += 2;
            }
            "--cached" => {
                cached = true;
                i += 1;
            }
            "--json" => {
                as_json = true;
                i += 1;
            }
            "--jobs" if i + 1 < args.len() => {
                for j in args[i + 1].split(',') {
                    if !j.trim().is_empty() {
                        filter_jobs.insert(j.trim().to_string());
                    }
                }
                i += 2;
            }
            _ => i += 1,
        }
    }

    let root = fs::canonicalize(&root).unwrap_or(root);
    let ci_file = root.join(".deepmodebot/ci.yml");
    let Ok(txt) = fs::read_to_string(&ci_file) else {
        eprintln!("dmb-gate ci: missing {}", ci_file.display());
        return ExitCode::from(1);
    };
    let mut wf = parse_ci_yaml(&txt);
    if !filter_jobs.is_empty() {
        wf.jobs.retain(|k, _| filter_jobs.contains(k));
        for j in wf.jobs.values_mut() {
            j.needs.retain(|d| filter_jobs.contains(d));
        }
    }
    let waves = match topo_waves(&wf.jobs) {
        Ok(w) => w,
        Err(e) => {
            eprintln!("dmb-gate ci: {}", e);
            return ExitCode::from(1);
        }
    };
    let t0 = Instant::now();
    let cache_path = root.join(".scratch/dmb-ci-cache.kv");
    let mut cache = if cached {
        load_cache(&cache_path)
    } else {
        BTreeMap::new()
    };

    let all_files: Vec<(String, PathBuf)> = if cached {
        walk_files(&root, None, SKIP_DIRS)
            .into_iter()
            .map(|p| (normalize_rel(&root, &p), p))
            .collect()
    } else {
        Vec::new()
    };

    let mut results: Vec<JobResult> = Vec::new();
    let mut failed = false;

    for wave in waves {
        if failed {
            for jid in wave {
                results.push(JobResult {
                    id: jid,
                    status: "skipped",
                    seconds: 0.0,
                    hash: None,
                    tail: String::new(),
                });
            }
            continue;
        }
        let cache_ref = &cache;
        let files_ref = &all_files;
        let root_ref = &root;
        let wf_ref = &wf;

        let wave_res: Vec<JobResult> = thread::scope(|s| {
            let mut handles = Vec::with_capacity(wave.len());
            for jid in wave {
                handles.push(s.spawn(move || {
                    let Some(job) = wf_ref.jobs.get(&jid) else {
                        return JobResult {
                            id: jid,
                            status: "failed",
                            seconds: 0.0,
                            hash: None,
                            tail: "missing job".into(),
                        };
                    };
                    let jt0 = Instant::now();
                    let h = if cached && !job.inputs.is_empty() {
                        Some(merkle_job_hash(root_ref, job, files_ref))
                    } else {
                        None
                    };
                    if let Some(digest) = &h {
                        if cache_ref.get(&jid) == Some(digest) {
                            return JobResult {
                                id: jid,
                                status: "cached",
                                seconds: 0.0,
                                hash: h,
                                tail: String::new(),
                            };
                        }
                    }
                    for step in &job.steps {
                        let (ok, output) = run_shell(root_ref, &step.run);
                        if !ok {
                            let tail = if output.len() > 600 {
                                output[output.len() - 600..].to_string()
                            } else {
                                output
                            };
                            return JobResult {
                                id: jid,
                                status: "failed",
                                seconds: jt0.elapsed().as_secs_f64(),
                                hash: None,
                                tail,
                            };
                        }
                    }
                    JobResult {
                        id: jid,
                        status: "passed",
                        seconds: jt0.elapsed().as_secs_f64(),
                        hash: h,
                        tail: String::new(),
                    }
                }));
            }
            handles
                .into_iter()
                .map(|h| {
                    h.join().unwrap_or(JobResult {
                        id: "unknown".into(),
                        status: "failed",
                        seconds: 0.0,
                        hash: None,
                        tail: "worker thread panicked".into(),
                    })
                })
                .collect()
        });

        for jr in wave_res {
            if jr.status == "failed" {
                failed = true;
            } else if let Some(d) = &jr.hash {
                cache.insert(jr.id.clone(), d.clone());
            }
            results.push(jr);
        }
    }

    if cached {
        save_cache(&cache_path, &cache);
    }

    let total_secs = t0.elapsed().as_secs_f64();
    if as_json {
        let jobs_json: Vec<String> = results
            .iter()
            .map(|r| {
                format!(
                    "{{\"id\":{},\"status\":{},\"seconds\":{:.3}}}",
                    json_escape(&r.id),
                    json_escape(r.status),
                    r.seconds
                )
            })
            .collect();
        println!(
            "{{\"ok\":{},\"engine\":\"rust-parallel\",\"workflow\":{},\"seconds\":{:.3},\"jobs\":[{}]}}",
            !failed,
            json_escape(&wf.name),
            total_secs,
            jobs_json.join(",")
        );
    } else {
        println!(
            "dmb-gate ci [{}]: {} ({:.2}s)",
            wf.name,
            if failed { "FAIL" } else { "OK" },
            total_secs
        );
        for r in &results {
            println!("  - {}: {} ({:.2}s)", r.id, r.status, r.seconds);
            if !r.tail.is_empty() {
                for l in r.tail.lines() {
                    println!("      {}", l);
                }
            }
        }
    }

    if failed {
        ExitCode::from(1)
    } else {
        ExitCode::SUCCESS
    }
}
