use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::thread;

pub const SKIP_DIRS: &[&str] = &[
    ".git",
    ".worktrees",
    ".scratch",
    "node_modules",
    "target",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_cache",
    ".next",
];

pub fn worker_count(items: usize) -> usize {
    if items <= 1 {
        return 1;
    }
    let cpus = thread::available_parallelism().map(|n| n.get()).unwrap_or(4);
    cpus.min(items).max(1)
}

pub fn parallel_map<T, R, F>(items: &[T], f: F) -> Vec<R>
where
    T: Sync,
    R: Send,
    F: Fn(&T) -> R + Sync,
{
    if items.is_empty() {
        return Vec::new();
    }
    let n_threads = worker_count(items.len());
    if n_threads == 1 {
        return items.iter().map(f).collect();
    }
    let next = AtomicUsize::new(0);
    let mut slots: Vec<Option<R>> = (0..items.len()).map(|_| None).collect();
    let f_ref = &f;
    let next_ref = &next;
    let buckets: Vec<Vec<(usize, R)>> = thread::scope(|s| {
        let mut handles = Vec::with_capacity(n_threads);
        for _ in 0..n_threads {
            handles.push(s.spawn(move || {
                let mut local = Vec::new();
                loop {
                    let idx = next_ref.fetch_add(1, Ordering::Relaxed);
                    if idx >= items.len() {
                        break;
                    }
                    local.push((idx, f_ref(&items[idx])));
                }
                local
            }));
        }
        handles
            .into_iter()
            .map(|h| h.join().unwrap_or_default())
            .collect()
    });
    for chunk in buckets {
        for (idx, val) in chunk {
            slots[idx] = Some(val);
        }
    }
    slots.into_iter().flatten().collect()
}

pub fn normalize_rel(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}

pub fn walk_files(root: &Path, exts: Option<&[&str]>, skip_dirs: &[&str]) -> Vec<PathBuf> {
    let mut out = Vec::new();
    let mut stack = vec![root.to_path_buf()];
    while let Some(dir) = stack.pop() {
        let Ok(entries) = fs::read_dir(&dir) else {
            continue;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            let Ok(ft) = entry.file_type() else {
                continue;
            };
            if ft.is_symlink() {
                continue;
            }
            let name = entry.file_name();
            let name_s = name.to_string_lossy();
            if ft.is_dir() {
                if !skip_dirs.iter().any(|s| *s == name_s.as_ref()) {
                    stack.push(path);
                }
                continue;
            }
            if !ft.is_file() {
                continue;
            }
            if let Some(allowed) = exts {
                let ext = path
                    .extension()
                    .and_then(|e| e.to_str())
                    .map(|s| s.to_ascii_lowercase())
                    .unwrap_or_default();
                if !allowed.iter().any(|a| *a == ext.as_str()) {
                    continue;
                }
            }
            out.push(path);
        }
    }
    out.sort();
    out
}

pub fn glob_match(pattern: &str, text: &str) -> bool {
    let p: Vec<char> = pattern.replace('\\', "/").chars().collect();
    let t: Vec<char> = text.replace('\\', "/").chars().collect();
    fn rec(p: &[char], t: &[char], pi: usize, ti: usize) -> bool {
        if pi == p.len() {
            return ti == t.len();
        }
        if p[pi] == '*' {
            let mut npi = pi;
            while npi < p.len() && p[npi] == '*' {
                npi += 1;
            }
            if npi == p.len() {
                return true;
            }
            for k in ti..=t.len() {
                if rec(p, t, npi, k) {
                    return true;
                }
            }
            return false;
        }
        if ti < t.len() && (p[pi] == '?' || p[pi] == t[ti]) {
            return rec(p, t, pi + 1, ti + 1);
        }
        false
    }
    rec(&p, &t, 0, 0)
}

pub fn json_escape(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    out.push('"');
    for ch in s.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => {
                out.push_str(&format!("\\u{:04x}", c as u32));
            }
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

pub fn sha256_hex(data: &[u8]) -> String {
    const K: [u32; 64] = [
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4,
        0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe,
        0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f,
        0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
        0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
        0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
        0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116,
        0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
        0xc67178f2,
    ];
    let mut h: [u32; 8] = [
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab,
        0x5be0cd19,
    ];
    let bit_len = (data.len() as u64) * 8;
    let mut buf = Vec::with_capacity(((data.len() + 9 + 63) / 64) * 64);
    buf.extend_from_slice(data);
    buf.push(0x80);
    while (buf.len() % 64) != 56 {
        buf.push(0);
    }
    buf.extend_from_slice(&bit_len.to_be_bytes());
    for chunk in buf.chunks_exact(64) {
        let mut w = [0u32; 64];
        for i in 0..16 {
            w[i] = u32::from_be_bytes([
                chunk[4 * i],
                chunk[4 * i + 1],
                chunk[4 * i + 2],
                chunk[4 * i + 3],
            ]);
        }
        for i in 16..64 {
            let s0 = w[i - 15].rotate_right(7) ^ w[i - 15].rotate_right(18) ^ (w[i - 15] >> 3);
            let s1 = w[i - 2].rotate_right(17) ^ w[i - 2].rotate_right(19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16]
                .wrapping_add(s0)
                .wrapping_add(w[i - 7])
                .wrapping_add(s1);
        }
        let [mut a, mut b, mut c, mut d, mut e, mut f, mut g, mut hh] = h;
        for i in 0..64 {
            let s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
            let ch = (e & f) ^ ((!e) & g);
            let t1 = hh
                .wrapping_add(s1)
                .wrapping_add(ch)
                .wrapping_add(K[i])
                .wrapping_add(w[i]);
            let s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
            let maj = (a & b) ^ (a & c) ^ (b & c);
            let t2 = s0.wrapping_add(maj);
            hh = g;
            g = f;
            f = e;
            e = d.wrapping_add(t1);
            d = c;
            c = b;
            b = a;
            a = t1.wrapping_add(t2);
        }
        h[0] = h[0].wrapping_add(a);
        h[1] = h[1].wrapping_add(b);
        h[2] = h[2].wrapping_add(c);
        h[3] = h[3].wrapping_add(d);
        h[4] = h[4].wrapping_add(e);
        h[5] = h[5].wrapping_add(f);
        h[6] = h[6].wrapping_add(g);
        h[7] = h[7].wrapping_add(hh);
    }
    let mut hex = String::with_capacity(64);
    for word in h {
        hex.push_str(&format!("{:08x}", word));
    }
    hex
}
