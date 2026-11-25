"""wsp.py - helpers for Weight-Space Programming (reading, fixing and writing neural network
weights by reasoning, without gradient descent).

numpy only. torch and safetensors are used if installed (for .pt/.bin/.safetensors files).

Sections
  1. Loading and inventory      load_weights, summarize, eff_rank, spectrum, group_mass, ascii_grid
  2. Transformer circuits       split_heads, qk_ov, composition, copying_score, rank_compositions
  3. Editing                    EditSession (guarded save_edit, manifest, diff export), ablate_direction,
                                ablate_units, unit_direction, random_control, bypass_unit
  4. Budget and measurement     Budget (forward-pass ledger), paired_stats, acc_se, note

Conventions
  * HF / torch nn.Linear weights are stored [out, in]: an OUTPUT direction of the layer lives in the
    row space (W[:, j] is what input unit j writes). Pass layout="out_in" (default).
  * Plain numpy MLPs written as x @ W are [in, out]: pass layout="in_out".
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import math
import os
from typing import Dict, Iterable, Optional, Sequence

import numpy as np

Array = np.ndarray


# --------------------------------------------------------------------------------------------
# 1. Loading and inventory
# --------------------------------------------------------------------------------------------
def load_weights(path: str) -> Dict[str, Array]:
    """Load a checkpoint as {name: float32 numpy array}.

    Supports: .safetensors, .npz, .npy, a directory of .npy / .safetensors files,
    .pt / .pth / .bin (torch state_dict), .json ({name: nested list}).
    """
    if os.path.isdir(path):
        out: Dict[str, Array] = {}
        for f in sorted(os.listdir(path)):
            p = os.path.join(path, f)
            if f.endswith(".npy"):
                out[f[:-4]] = np.load(p).astype(np.float32)
            elif f.endswith(".safetensors"):
                out.update(load_weights(p))
        if not out:
            raise ValueError(f"no .npy or .safetensors files in {path}")
        return out
    ext = os.path.splitext(path)[1].lower()
    if ext == ".npz":
        z = np.load(path)
        return {k: z[k].astype(np.float32) for k in z.files}
    if ext == ".npy":
        return {os.path.basename(path)[:-4]: np.load(path).astype(np.float32)}
    if ext == ".json":
        with open(path) as f:
            d = json.load(f)
        return {k: np.asarray(v, np.float32) for k, v in d.items()}
    if ext == ".safetensors":
        try:
            from safetensors.numpy import load_file
            return {k: v.astype(np.float32) for k, v in load_file(path).items()}
        except (ImportError, TypeError):
            # bf16 tensors cannot be loaded by safetensors.numpy; go through torch
            from safetensors.torch import load_file as tload
            return {k: v.float().numpy() for k, v in tload(path).items()}
    if ext in (".pt", ".pth", ".bin"):
        import torch
        sd = torch.load(path, map_location="cpu", weights_only=True)
        if hasattr(sd, "state_dict"):
            sd = sd.state_dict()
        if "state_dict" in sd:
            sd = sd["state_dict"]
        return {k: v.detach().float().numpy() for k, v in sd.items() if hasattr(v, "detach")}
    raise ValueError(f"unsupported checkpoint format: {path}")


def eff_rank(M: Array) -> float:
    """Participation ratio of squared singular values: (sum s^2)^2 / sum s^4. 1 = rank one."""
    s2 = spectrum(M) ** 2
    return float(s2.sum() ** 2 / max((s2 ** 2).sum(), 1e-30))


def spectrum(M: Array, k: Optional[int] = None) -> Array:
    """Singular values of a 2-D array (top k if given)."""
    M = np.asarray(M, np.float64)
    s = np.linalg.svd(M, compute_uv=False)
    return s[:k] if k else s


def summarize(W: Dict[str, Array], ranks: bool = True, max_svd: int = 4096) -> str:
    """One line per tensor: shape, mean, std, |max|, share of zeros, effective rank (2-D only)."""
    lines = [f"{'name':48s} {'shape':>16s} {'mean':>9s} {'std':>9s} {'absmax':>9s} {'zero%':>6s} {'effrank':>8s}"]
    total = 0
    for k, v in W.items():
        total += v.size
        er = ""
        if ranks and v.ndim == 2 and max(v.shape) <= max_svd:
            er = f"{eff_rank(v):8.1f}"
        lines.append(f"{k[:48]:48s} {str(tuple(v.shape)):>16s} {v.mean():9.4f} {v.std():9.4f} "
                     f"{np.abs(v).max():9.4f} {100 * (v == 0).mean():6.1f} {er:>8s}")
    lines.append(f"total parameters: {total:,}")
    return "\n".join(lines)


def group_mass(W1: Array, groups: Dict[str, Sequence[int]], layout: str = "in_out") -> Dict[str, float]:
    """L2 mass of the first-layer weights reading each input group (e.g. one input channel).

    Where a group's weights concentrate says what the network looks at (Experiment 1 trick)."""
    rows = W1 if layout == "in_out" else W1.T
    return {g: float(np.linalg.norm(rows[list(idx)])) for g, idx in groups.items()}


def ascii_grid(values: Sequence[float], shape: Sequence[int], chars: str = " .:-=+*#%@") -> str:
    """Render per-position magnitudes (e.g. row norms of one input channel) as an ASCII heat map."""
    v = np.abs(np.asarray(values, np.float64)).reshape(shape)
    v = v / (v.max() + 1e-12)
    idx = np.minimum((v * (len(chars) - 1)).round().astype(int), len(chars) - 1)
    return "\n".join("".join(chars[i] * 2 for i in row) for row in idx)


# --------------------------------------------------------------------------------------------
# 2. Transformer circuit analysis (row-vector convention: x is a row in the residual stream)
#    attention score(dst, src) = x_dst @ QK @ x_src.T ;  head output = x_src @ OV
# --------------------------------------------------------------------------------------------
def split_heads(W: Array, n_heads: int, axis: int) -> list:
    """Split a projection into per-head blocks along `axis` (the head-feature axis)."""
    return np.split(np.asarray(W), n_heads, axis=axis)


def qk_ov(Wq: Array, Wk: Array, Wv: Array, Wo: Array, layout: str = "out_in"):
    """Per-head d_model x d_model QK and OV matrices.

    layout="out_in" (torch): Wq/Wk/Wv are [head_dim, d_model], Wo is [d_model, head_dim].
    layout="in_out" (numpy): Wq/Wk/Wv are [d_model, head_dim], Wo is [head_dim, d_model].
    Grouped-query attention: pass the K/V block shared by this query head."""
    if layout == "out_in":
        Wq, Wk, Wv, Wo = Wq.T, Wk.T, Wv.T, Wo.T
    return Wq @ Wk.T, Wv @ Wo


def _comp(A: Array, B: Array) -> float:
    return float(np.linalg.norm(A @ B) / (np.linalg.norm(A) * np.linalg.norm(B) + 1e-30))


def composition(OV1: Array, QK2: Array, kind: str) -> float:
    """Elhage et al. composition score of an earlier head (OV1) into a later head.

    kind="K": the earlier head's output feeds the later head's KEYS (induction heads).
    kind="Q": feeds its QUERIES.  kind="V": feeds its values (pass OV2 as QK2)."""
    if kind == "K":
        return _comp(QK2, OV1.T)
    if kind == "Q":
        return _comp(OV1, QK2)
    if kind == "V":
        return _comp(OV1, QK2)
    raise ValueError(kind)


def baseline_composition(d_model: int, head_dim: int, n: int = 20, seed: int = 0) -> float:
    """Composition score of random low-rank matrices of the same shape: the null to compare with."""
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n):
        a = rng.standard_normal((d_model, head_dim)) @ rng.standard_normal((head_dim, d_model))
        b = rng.standard_normal((d_model, head_dim)) @ rng.standard_normal((head_dim, d_model))
        vals.append(_comp(a, b))
    return float(np.mean(vals))


def copying_score(OV: Array, E: Optional[Array] = None, U: Optional[Array] = None) -> float:
    """Eigenvalue positivity: sum(eig) / sum(|eig|) of E @ OV @ U (or OV alone).

    Near +1: the head copies what it attends to (copying / induction OV). Near -1: suppresses."""
    M = OV if E is None else E @ OV @ (U if U is not None else E.T)
    ev = np.linalg.eigvals(np.asarray(M, np.float64))
    return float(ev.real.sum() / (np.abs(ev).sum() + 1e-30))


def rank_compositions(heads: Dict[str, tuple], kind: str = "K", top: int = 10):
    """heads: {"layer.head": (layer_index, QK, OV)}. Rank every (earlier -> later) pair."""
    rows = []
    for a, (la, _, ov1) in heads.items():
        for b, (lb, qk2, ov2) in heads.items():
            if lb > la:
                rows.append((composition(ov1, ov2 if kind == "V" else qk2, kind), a, b))
    rows.sort(reverse=True)
    return rows[:top]


# --------------------------------------------------------------------------------------------
# 3. Editing
# --------------------------------------------------------------------------------------------
def _sha(a: Array) -> str:
    return hashlib.sha256(np.ascontiguousarray(a, np.float32).tobytes()).hexdigest()[:16]


class EditSession:
    """Guarded, auditable weight edits on top of a frozen base checkpoint.

    ses = EditSession(load_weights("model.safetensors"), "work", forbidden=["lm_head.weight"])
    W = ses.load("layers.15.mlp.down_proj.weight")
    ses.save_edit("layers.15.mlp.down_proj.weight", W_new, why="remove loop direction")
    print(ses.manifest_text())
    """

    def __init__(self, base: Dict[str, Array], workdir: str = "wsp_work",
                 forbidden: Iterable[str] = (), allow_scalar: bool = False):
        self.base = base
        self.workdir = workdir
        self.forbidden = set(forbidden)
        self.allow_scalar = allow_scalar
        self.edits: Dict[str, Array] = {}
        self.why: Dict[str, str] = {}
        os.makedirs(os.path.join(workdir, "edited"), exist_ok=True)
        for f in os.listdir(os.path.join(workdir, "edited")):      # resume a previous session
            if f.endswith(".npy") and f[:-4] in base:
                self.edits[f[:-4]] = np.load(os.path.join(workdir, "edited", f))

    def names(self):
        return list(self.base)

    def load_original(self, name: str) -> Array:
        return self.base[name].copy()

    def load(self, name: str) -> Array:
        return (self.edits.get(name, self.base[name])).copy()

    def save_edit(self, name: str, arr: Array, why: str = "") -> dict:
        if name not in self.base:
            raise KeyError(f"unknown tensor {name}")
        if name in self.forbidden:
            raise PermissionError(f"{name} is out of scope for edits")
        a = np.asarray(arr, np.float32)
        b = self.base[name]
        if a.shape != b.shape:
            raise ValueError(f"shape {a.shape} != {b.shape}")
        if not np.isfinite(a).all():
            raise ValueError("non-finite values")
        if not self.allow_scalar and np.any(b != 0):
            nz = b != 0
            ratio = a[nz] / b[nz]
            if np.allclose(ratio, ratio.flat[0], rtol=1e-5) and np.allclose(a[~nz], 0) \
                    and not np.isclose(ratio.flat[0], 1.0):
                raise PermissionError("whole-tensor scaling is a global knob, not a targeted edit")
        self.edits[name] = a
        self.why[name] = why
        np.save(os.path.join(self.workdir, "edited", name + ".npy"), a)
        return self.stat(name)

    def drop_edit(self, name: str):
        self.edits.pop(name, None)
        p = os.path.join(self.workdir, "edited", name + ".npy")
        if os.path.exists(p):
            os.remove(p)

    def stat(self, name: str) -> dict:
        a, b = self.edits[name], self.base[name]
        d = a - b
        return {"tensor": name, "changed": int((d != 0).sum()), "size": int(b.size),
                "rel_change": float(np.linalg.norm(d) / (np.linalg.norm(b) + 1e-30)),
                "sha_base": _sha(b), "sha_edit": _sha(a), "why": self.why.get(name, "")}

    def manifest(self) -> dict:
        per = [self.stat(n) for n in sorted(self.edits)]
        total = sum(v.size for v in self.base.values())
        changed = sum(p["changed"] for p in per)
        return {"tensors": per, "changed": changed, "total": total,
                "changed_share": changed / max(total, 1)}

    def manifest_text(self) -> str:
        m = self.manifest()
        lines = [f"{p['tensor']}: {p['changed']:,}/{p['size']:,} changed, rel {100 * p['rel_change']:.2f}% "
                 f"({p['why']})" for p in m["tensors"]]
        lines.append(f"TOTAL {m['changed']:,} of {m['total']:,} weights = {100 * m['changed_share']:.4f}%")
        return "\n".join(lines)

    def snapshot(self, tag: str) -> str:
        """Copy the current edit set to workdir/best_<tag>/ (keep good edits)."""
        d = os.path.join(self.workdir, f"best_{tag}")
        os.makedirs(d, exist_ok=True)
        for n, a in self.edits.items():
            np.save(os.path.join(d, n + ".npy"), a)
        with open(os.path.join(d, "manifest.json"), "w") as f:
            json.dump(self.manifest(), f, indent=1)
        return d

    def export_diff(self, path: str):
        """Sparse diff (indices + new values) for every edited tensor; dense if > 25% changed."""
        payload = {}
        for n, a in self.edits.items():
            d = (a != self.base[n]).ravel()
            if d.mean() > 0.25:
                payload[n + "::dense"] = a
            else:
                idx = np.flatnonzero(d)
                payload[n + "::idx"] = idx.astype(np.int64)
                payload[n + "::val"] = a.ravel()[idx]
        np.savez_compressed(path, **payload)
        with open(os.path.splitext(path)[0] + ".manifest.json", "w") as f:
            json.dump(self.manifest(), f, indent=1)

    def merged(self) -> Dict[str, Array]:
        out = dict(self.base)
        out.update(self.edits)
        return out


def apply_diff(base: Dict[str, Array], path: str) -> Dict[str, Array]:
    """Rebuild edited tensors from export_diff output."""
    z = np.load(path)
    out = dict(base)
    names = {k.split("::")[0] for k in z.files}
    for n in names:
        if n + "::dense" in z.files:
            out[n] = z[n + "::dense"]
        else:
            a = base[n].copy().ravel()
            a[z[n + "::idx"]] = z[n + "::val"]
            out[n] = a.reshape(base[n].shape)
    return out


def unit_direction(acts_a: Array, acts_b: Array) -> Array:
    """Difference of means (a - b) of two activation sets [n, d], as a unit vector.

    Use MATCHED contexts (same problem, failing vs productive continuation) so the direction is
    the behaviour, not difficulty or length."""
    u = np.asarray(acts_a, np.float64).mean(0) - np.asarray(acts_b, np.float64).mean(0)
    return (u / (np.linalg.norm(u) + 1e-30)).astype(np.float32)


def random_control(u: Array, seed: int = 0) -> Array:
    """A random unit vector orthogonal to u: the norm-matched control for a direction edit."""
    rng = np.random.default_rng(seed)
    r = rng.standard_normal(u.shape)
    u = u / np.linalg.norm(u)
    r -= (r @ u) * u
    return (r / np.linalg.norm(r)).astype(np.float32)


def ablate_direction(W: Array, u: Array, alpha: float = 1.0, units: Optional[Sequence[int]] = None,
                     layout: str = "out_in") -> Array:
    """Remove (alpha=1) or reverse (alpha>1) what W writes along output direction u.

    out_in: W is [d_out, n_in]; W' = W - alpha * u (u^T W)  (restricted to columns `units`).
    in_out: W is [n_in, d_out]; W' = W - alpha * (W u) u^T  (restricted to rows `units`).
    Exp. 8 (Qwen3.5-0.8B) used out_in on mlp.down_proj, 64 units per layer, alpha 6."""
    u = np.asarray(u, np.float32)
    u = u / np.linalg.norm(u)
    W = np.asarray(W, np.float32).copy()
    if layout == "out_in":
        proj = u @ W                                   # [n_in]: how much each unit writes along u
        mask = np.zeros_like(proj)
        mask[list(units) if units is not None else slice(None)] = 1.0
        W -= alpha * np.outer(u, proj * mask)
    else:
        proj = W @ u                                   # [n_in]
        mask = np.zeros_like(proj)
        mask[list(units) if units is not None else slice(None)] = 1.0
        W -= alpha * np.outer(proj * mask, u)
    return W


def top_writers(W: Array, u: Array, k: int, layout: str = "out_in") -> Array:
    """Indices of the k input units that write most strongly along u (by |projection|)."""
    u = u / np.linalg.norm(u)
    proj = (u @ W) if layout == "out_in" else (W @ u)
    return np.argsort(-np.abs(proj))[:k]


def ablate_units(W: Array, units: Sequence[int], layout: str = "out_in", scale: float = 0.0) -> Array:
    """Silence (scale 0) or rescale the outputs of given units / heads' columns."""
    W = np.asarray(W, np.float32).copy()
    if layout == "out_in":
        W[:, list(units)] *= scale
    else:
        W[list(units), :] *= scale
    return W


def bypass_unit(W_in: Array, b_in: Array, W_out: Array, unit: int, read: Dict[int, float],
                bias: float, write: Dict[int, float], layout: str = "in_out"):
    """Hand-write one hidden unit: h = act(sum read[i]*x_i + bias); its output adds write[j]*h.

    Used to add a small separate path (Experiment 4) or to build a network from scratch (5, 6).
    Returns edited copies (W_in, b_in, W_out)."""
    W_in, b_in, W_out = (np.asarray(a, np.float32).copy() for a in (W_in, b_in, W_out))
    if layout == "in_out":
        W_in[:, unit] = 0.0
        for i, w in read.items():
            W_in[i, unit] = w
        W_out[unit, :] = 0.0
        for j, w in write.items():
            W_out[unit, j] = w
    else:
        W_in[unit, :] = 0.0
        for i, w in read.items():
            W_in[unit, i] = w
        W_out[:, unit] = 0.0
        for j, w in write.items():
            W_out[j, unit] = w
    b_in[unit] = bias
    return W_in, b_in, W_out


# --------------------------------------------------------------------------------------------
# 4. Budget and measurement
# --------------------------------------------------------------------------------------------
class Budget:
    """Ledger of forward passes. Every run of the model must go through spend()."""

    def __init__(self, workdir: str, total: int):
        self.path = os.path.join(workdir, "budget.json")
        os.makedirs(workdir, exist_ok=True)
        if os.path.exists(self.path):
            with open(self.path) as f:
                self.state = json.load(f)
        else:
            self.state = {"total": total, "used": 0, "log": []}
            self._save()

    def _save(self):
        with open(self.path, "w") as f:
            json.dump(self.state, f, indent=1)

    @property
    def remaining(self) -> int:
        return self.state["total"] - self.state["used"]

    def spend(self, kind: str, note: str = "") -> int:
        if self.remaining <= 0:
            raise RuntimeError("forward-pass budget exhausted: make the final choice")
        self.state["used"] += 1
        self.state["log"].append({"k": self.state["used"], "kind": kind, "note": note,
                                  "t": _dt.datetime.now().isoformat(timespec="seconds")})
        self._save()
        return self.state["used"]

    def refund(self, reason: str):
        """A failed request does not count."""
        self.state["used"] -= 1
        self.state["log"].append({"refund": reason})
        self._save()


def acc_se(p: float, n: int) -> float:
    """Standard error of an accuracy p measured on n items (about 50/sqrt(n) points at p=0.5)."""
    return math.sqrt(max(p * (1 - p), 1e-12) / max(n, 1))


def paired_stats(original: Sequence[int], edited: Sequence[int]) -> dict:
    """Paired comparison on the SAME items (0/1 per item, or mean over samples per item)."""
    o = np.asarray(original, np.float64)
    e = np.asarray(edited, np.float64)
    if o.shape != e.shape:
        raise ValueError("pair the items: same problems, same order")
    d = e - o
    n = len(d)
    se = float(d.std(ddof=1) / math.sqrt(n)) if n > 1 else float("nan")
    rescues = int(((o < 0.5) & (e >= 0.5)).sum())
    losses = int(((o >= 0.5) & (e < 0.5)).sum())
    k, m = rescues, rescues + losses               # exact two-sided McNemar (sign) test
    p = 1.0
    if m:
        tail = sum(math.comb(m, i) for i in range(0, min(k, m - k) + 1)) / 2 ** m
        p = min(1.0, 2 * tail)
    return {"n": n, "original": float(o.mean()), "edited": float(e.mean()), "gain": float(d.mean()),
            "se": se, "z": float(d.mean() / se) if se and se == se and se > 0 else float("inf"),
            "rescues": rescues, "losses": losses, "mcnemar_p": p}


def note(workdir: str, text: str):
    """Append a dated line to workdir/notes.md (findings with numbers, edits tried, current best)."""
    os.makedirs(workdir, exist_ok=True)
    with open(os.path.join(workdir, "notes.md"), "a") as f:
        f.write(f"- {_dt.datetime.now():%Y-%m-%d %H:%M} {text}\n")


def cli():
    """wsp-inspect <checkpoint>: print the tensor inventory."""
    import sys
    if len(sys.argv) > 1:
        print(summarize(load_weights(sys.argv[1])))
    else:
        print(__doc__)


if __name__ == "__main__":
    cli()
