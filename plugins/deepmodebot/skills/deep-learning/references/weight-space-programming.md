# Weight-Space Programming (READ / FIX / WRITE Without Gradient Descent)

Distilled from `ulkuderner/weight-space-programming` (MIT) and Takehi, Teoh, Zhang & Khattab, *"Sparks of Weight-Space Programming"* (MIT CSAIL, Nov 2026; experiment logs `RikiyaT/lm_understand-logs`, CC BY 4.0), alongside foundational weight-space theory.

## Protocol Contract

| Level | Forward Passes Allowed | Use When |
|---|---|---|
| `strict` | None, or fixed logged pass budget | Reproducing interpretability claims or blind weight reading |
| `standard` | Budgeted passes (default 25) via `Budget` | Surgical fixes where every evaluation is a scarce measurement |
| `practical` | Unlimited evaluation runs, still zero gradient descent | Engineering and unit-testing hand-compiled neural networks |

Four non-negotiable rules at every level:
1. **No training.** No backprop, autograd, optimizers, or iterative loss minimization. Closed-form linear algebra (SVD, difference of means, least-squares solve) is allowed.
2. **Budgeted evaluation.** Run checkpoints only through logged evaluators wrapped with `Budget.spend` (refund failed passes via `Budget.refund`).
3. **Targeted edits only.** Keep embeddings, output heads, and final norms frozen (`forbidden=[...]`) unless the task explicitly targets them. `EditSession` rejects whole-tensor rescaling.
4. **Mechanism + evidence.** Every edit records target tensor, exact changed weight count (`ses.manifest_text()`), causal mechanism, norm-matched random control, and held-out paired gain (`gain > 2 * SE`).

## Quick Start (`scripts/wsp.py`, NumPy-only)

```bash
python -B scripts/wsp.py path/to/model.safetensors > .scratch/wsp_inventory.txt
```
```python
from wsp import (
    load_weights, summarize, EditSession, Budget,
    unit_direction, top_writers, ablate_direction, random_control, paired_stats,
)
W = load_weights("model.safetensors")  # .safetensors, .npz, .npy, .pt/.bin, .json
ses = EditSession(W, ".scratch/wsp_work", forbidden=["lm_head.weight", "model.norm.weight"])
budget = Budget(".scratch/wsp_work", total=25)
```

Tensor layout rule: PyTorch `nn.Linear.weight` is `[out, in]` (`layout="out_in"`, where column `j` is what input unit `j` writes); plain NumPy `x @ W` MLPs are `[in, out]` (`layout="in_out"`). Always verify bf16 round-trip survival (`ses.stat(name)["changed"]`).

## Mode 1: READ (Infer Function From Raw Weights)

Always compare every statistic against a null model (random tensor of matching shape/scale or sibling checkpoints):
1. **Global inventory:** `summarize(W)` reports shape, mean, std, `|max|`, zero %, and `eff_rank` (participation ratio $(\sum s_i^2)^2 / \sum s_i^4$).
2. **Input edge (Layer 1):** `group_mass(W1, groups)` and `ascii_grid(row_norms, (H, W))` reveal which input channels and spatial regions drive the network (e.g., Breakout agent channel concentrates on the bottom paddle row).
3. **Output edge (Last layer):** `spectrum(W_last)` and reshaped output rows expose geometric primitives or class separation (e.g., DDPM output rows trace shape outlines directly).
4. **Transformer circuits:** `qk_ov(Wq, Wk, Wv, Wo)` + `rank_compositions(heads, "K")` vs `baseline_composition(d_model, head_dim)` + `copying_score(OV)`. A previous-token head K-composing into a positive-eigenvalue OV head identifies an induction head.
5. **Known limit:** Pure weight inspection failed on behavioral traits like sycophancy (0/4); use attention-pattern-only probes on synthetic prompts when protocol permits.

## Mode 2: FIX (Minimal Causal Repair)

1. **Diagnose:** Run one generation pass on practice items (never test set); bucket failures (wrong answer, no answer, looping/cutoff).
2. **Matched-context localization:** Take the *same* input with one failing continuation and one productive continuation. Extract activations via one teacher-forced pass; compute `u = unit_direction(acts_fail, acts_ok)` and `writers = top_writers(W_down, u, k=64)`.
3. **Dose-response + random control:** Apply `ablate_direction(W, u, alpha, units=writers)` across `alpha = 1, 2, 4, 6` and verify failing log-prob drops more than productive log-prob while `random_control(u)` does not reproduce the gain.
4. **Three surgical repair primitives:**
   - *Direction ablation:* $W' = W - \alpha u (m \odot (u^T W))$ on top-$k$ writers (paper Exp. 8: 64 MLP `down_proj` columns in 2 layers, 0.016% of weights, lifted MATH-500 from 7.9% to 48.1%).
   - *Head switch-off:* `ablate_units(W_o, head_cols, scale=0.0)`.
   - *Bypass sub-circuit:* `bypass_unit(W_in, b_in, W_out, unit, read, bias, write)` injects hand-written neurons active only in the failure regime (paper Exp. 4: 0% to 100% over 1,024 episodes editing 3.5% of weights).
5. **Paired confirmation:** Evaluate base vs edited on identical held-out items/seeds (`paired_stats`), accept only if `gain > 2 * se`, and export sparse diff via `ses.export_diff("edit.npz")`.
6. **Hard limit:** Edits remove obstacles (looping, broken heads, local minima); they cannot create missing capability (Gemma 3 270M showed <1 pt movement).

## Mode 3: WRITE (Compile Algorithms Directly Into Weights)

1. **Symbolic spec first:** Write explicit feature detectors, multi-step propagation rules, and priority-weighted action scores.
2. **ReLU/tanh gate primitives** (use crisp weights $\approx \pm 10$, leave unused units exact `0`):
   - `AND(x_1..x_k)`: weights `+1`, bias `-(k - 1)`.
   - `OR(x_1..x_k)`: weights `+1`, bias `0` (clamped downstream).
   - `NOT(x)`: weight `-1`, bias `+1`.
   - `Threshold(x > t)`: weight `+1`, bias `-t`.
   - `Comparator(a > b)`: `ReLU(a - b)`.
   - `Signed pass-through`: `h+ / h-` twin units (`ReLU(x)` and `ReLU(-x)`).
3. **Generate programmatically:** One Python builder per layer calling `bypass_unit` / `ses.save_edit`; verify symbolically and empirically against RL baselines (paper Exp. 5-6: hand-compiled MinAtar Breakout scored 517 vs PPO-500M's 25; 1.48M-weight 9x9 Go beat equal-size 20M-game PPO).

## Foundational Weight-Space & Compiled-Network Papers

- **RASP** (`arXiv:2106.06981`, Weiss et al. 2021) — Formal programming language that compiles sequence algorithms into transformer attention/MLP primitives.
- **Tracr** (`arXiv:2301.05062`, Lindner et al. 2023; `google-deepmind/tracr`) — End-to-end compiler turning RASP programs into exact transformer weights for mechanistic ground truth.
- **HyperNetworks** (`arXiv:1609.09106`, Ha et al. 2016) — A smaller network generates weights for a larger target network, coupling weight space with functional structure.
- **Git Re-Basin** (`arXiv:2209.04836`, Ainsworth et al. 2022) — Linear mode connectivity via neuron permutation matching across independently trained models.
- **Task Arithmetic** (`arXiv:2212.04089`, Ilharco et al. 2022) — Adding/negating weight-space task vectors ($\tau = \theta_{\text{ft}} - \theta_{\text{pre}}$) edits capabilities compositionally.
- **Neural Tangent Kernel** (`arXiv:1806.07572`, Jacot et al. 2018) — Infinite-width linearized weight-space dynamics governing gradient flow and generalization.
