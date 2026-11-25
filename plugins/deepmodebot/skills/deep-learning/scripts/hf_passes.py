"""hf_passes.py - budgeted forward passes for Hugging Face causal LMs (the only way the model runs).

Two pass types, as in the Weight-Space Programming protocol (Experiment 8):
  generate(...)        the model answers prompts with the evaluation's sampling; graded if a grader is given
  teacher_forced(...)  the model reads fixed texts; returns token log-probs and hidden states / MLP inputs

Both spend one unit of the Budget (a failed call is refunded). Edits from an EditSession are applied
to a fresh copy of the base weights before each pass, so "original" and "edited" are always exact.

Requires: torch, transformers (and a GPU for anything above ~1B parameters).
"""
from __future__ import annotations

import json
import os
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

try:                                    # inside the wsp_local package
    from .wsp import Budget, EditSession, paired_stats
except ImportError:                     # standalone script next to wsp.py
    from wsp import Budget, EditSession, paired_stats


class HFModel:
    def __init__(self, model_id: str, dtype: str = "bfloat16", device: Optional[str] = None):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(model_id)
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=getattr(torch, dtype)).to(self.device)
        self.model.eval()
        self._orig = {k: v.detach().clone() for k, v in self.model.state_dict().items()}

    def state_numpy(self) -> Dict[str, np.ndarray]:
        """Base weights as float32 numpy (feed to EditSession)."""
        return {k: v.float().cpu().numpy() for k, v in self._orig.items()}

    def use(self, edits: Optional[Dict[str, np.ndarray]] = None):
        """Load original weights, then overwrite edited tensors (cast to the model dtype)."""
        sd = self.model.state_dict()
        with self.torch.no_grad():
            for k, v in self._orig.items():
                sd[k].copy_(v)
            for k, a in (edits or {}).items():
                sd[k].copy_(self.torch.from_numpy(a).to(sd[k].dtype))

    def chat(self, user: str, thinking: Optional[bool] = None) -> str:
        kw = {} if thinking is None else {"enable_thinking": thinking}
        return self.tok.apply_chat_template([{"role": "user", "content": user}], tokenize=False,
                                            add_generation_prompt=True, **kw)


def generate(m: HFModel, ses: EditSession, budget: Budget, prompts: Sequence[str],
             which: str = "both", grader: Optional[Callable[[int, str], int]] = None,
             n: int = 1, max_new_tokens: int = 4096, sampling: Optional[dict] = None,
             batch: int = 16, seed: int = 0, tag: str = "") -> dict:
    """which: "original", "edited" or "both" (paired, same seeds per item)."""
    torch = m.torch
    sampling = sampling or {"do_sample": True, "temperature": 0.6, "top_p": 0.95, "top_k": 20}
    k = budget.spend("generate", tag)
    try:
        out = {}
        for variant in (["original", "edited"] if which == "both" else [which]):
            m.use(ses.edits if variant == "edited" else None)
            texts, grades = [], []
            for i0 in range(0, len(prompts), batch):
                chunk = list(prompts[i0:i0 + batch])
                for s in range(n):
                    torch.manual_seed(seed + 1000 * s + i0)          # same seed for both variants
                    enc = m.tok(chunk, return_tensors="pt", padding=True).to(m.device)
                    with torch.no_grad():
                        g = m.model.generate(**enc, max_new_tokens=max_new_tokens,
                                             pad_token_id=m.tok.pad_token_id or m.tok.eos_token_id, **sampling)
                    for j, row in enumerate(g):
                        t = m.tok.decode(row[enc["input_ids"].shape[1]:], skip_special_tokens=True)
                        texts.append(t)
                        if grader:
                            grades.append(int(grader(i0 + j, t)))
            cut = float(np.mean([len(m.tok(t)["input_ids"]) >= max_new_tokens - 1 for t in texts]))
            out[variant] = {"texts": texts, "grades": grades, "cut_share": cut,
                            "acc": float(np.mean(grades)) if grades else None}
        if which == "both" and grader:
            out["paired"] = paired_stats(out["original"]["grades"], out["edited"]["grades"])
        _dump(ses.workdir, f"gen_{k}.json", out)
        m.use(None)
        return {kk: ({x: y for x, y in v.items() if x != "texts"} if isinstance(v, dict) else v)
                for kk, v in out.items()}
    except Exception as e:
        budget.refund(f"{type(e).__name__}: {e}")
        raise


def teacher_forced(m: HFModel, ses: EditSession, budget: Budget, texts: Sequence[str],
                   which: str = "original", layers: Sequence[int] = (), mlp_layers: Sequence[int] = (),
                   mlp_module: str = "mlp.down_proj", tag: str = "") -> dict:
    """Return per-token log-probs, residual stream after given layers, and MLP down_proj inputs.

    Saved to workdir/fwd_<k>/ as .npy (right-padded) plus meta.json."""
    torch = m.torch
    k = budget.spend("teacher_forced", tag)
    try:
        m.use(ses.edits if which == "edited" else None)
        caps: Dict[str, List[np.ndarray]] = {}
        hooks = []
        blocks = _find_blocks(m.model)
        for L in mlp_layers:
            mod = blocks[L]
            for part in mlp_module.split("."):
                mod = getattr(mod, part)
            hooks.append(mod.register_forward_hook(
                lambda _m, inp, _o, L=L: caps.setdefault(f"mlp_in_{L}", []).append(inp[0][0].float().cpu().numpy())))
        lps, hs = [], {L: [] for L in layers}
        for t in texts:
            enc = m.tok(t, return_tensors="pt").to(m.device)
            with torch.no_grad():
                o = m.model(**enc, output_hidden_states=bool(layers))
            logp = torch.log_softmax(o.logits[0, :-1].float(), -1)
            ids = enc["input_ids"][0, 1:]
            lps.append(logp.gather(1, ids[:, None])[:, 0].cpu().numpy())
            for L in layers:
                hs[L].append(o.hidden_states[L][0].float().cpu().numpy())
        for h in hooks:
            h.remove()
        d = os.path.join(ses.workdir, f"fwd_{k}")
        os.makedirs(d, exist_ok=True)
        np.save(os.path.join(d, "token_logprobs.npy"), _pad(lps))
        for L in layers:
            np.save(os.path.join(d, f"hidden_{L}.npy"), _pad(hs[L]))
        for name, arrs in caps.items():
            np.save(os.path.join(d, f"{name}.npy"), _pad(arrs))
        meta = {"texts": len(texts), "lengths": [len(x) for x in lps], "which": which}
        with open(os.path.join(d, "meta.json"), "w") as f:
            json.dump(meta, f)
        m.use(None)
        return {"dir": d, **meta, "mean_logprob": float(np.mean([x.mean() for x in lps]))}
    except Exception as e:
        budget.refund(f"{type(e).__name__}: {e}")
        raise


def _find_blocks(model):
    for path in ("model.layers", "model.language_model.layers", "transformer.h", "gpt_neox.layers"):
        mod = model
        try:
            for p in path.split("."):
                mod = getattr(mod, p)
            return mod
        except AttributeError:
            continue
    raise AttributeError("could not find the transformer blocks; pass them explicitly")


def _pad(arrs: List[np.ndarray]) -> np.ndarray:
    n = max(a.shape[0] for a in arrs)
    out = np.zeros((len(arrs), n) + arrs[0].shape[1:], np.float32)
    for i, a in enumerate(arrs):
        out[i, :a.shape[0]] = a
    return out


def _dump(workdir: str, name: str, obj):
    with open(os.path.join(workdir, name), "w") as f:
        json.dump(obj, f)
