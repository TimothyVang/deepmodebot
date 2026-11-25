---
name: deep-learning
description: "Non-LLM deep learning, RL, neural architectures, world models, geometric/SciML, optimization, and gradient-free weight-space programming."
metadata:
  as-of: "2026-11-24"
---

# Deep Learning, RL, Neural Networks & Weight-Space Programming

Non-LLM deep learning reference: neural architectures, reinforcement learning, world models, geometric/scientific ML, optimization dynamics, and direct weight-space programming. Every paper ID (`arXiv`) and GitHub repository in `references/` was verified against primary sources (`export.arxiv.org` and GitHub API) as of 2026-11-24.

## Route (read only the branch the task touches)

| Task | Read |
|---|---|
| Inspect, diagnose, surgically repair, or hand-compile neural network weights without gradient descent (`READ` / `FIX` / `WRITE`); circuit analysis (`QK`/`OV`, induction heads, direction ablation, bypass units); `scripts/wsp.py` | `references/weight-space-programming.md` |
| Reinforcement learning (DQN, PPO, SAC, TD3, MuZero, DreamerV3, TD-MPC2, Offline RL CQL/IQL, Diffusion Policy, RND exploration, vectorized GPU sims) | `references/reinforcement-learning.md` |
| Neural architectures (ResNet, U-Net, ViT, DINOv2, I-JEPA/V-JEPA 2, Mamba/Mamba-2 SSM, DDPM/Flow Matching/Rectified Flow, MoE, GCN/GAT/E(n)-GNN, Fourier Neural Operators, KAN, Modern Hopfield) | `references/neural-architectures.md` |
| Optimizers, scaling & GPU/Rust ML systems (AdamW, Muon, SAM, muP, NTK, Double Descent, Grokking, BF16/FP8 mixed precision, FlashAttention, ZeRO/FSDP, Triton, JAX/Optax, Burn/Candle/tinygrad) | `references/training-optimization.md` |
| Full scraped paper catalog (58 verified arXiv papers) and curated non-LLM DL/RL/ML GitHub repo index (37 verified repos with licenses & star counts) | `references/papers-and-repos.md` |

## Bundled Scripts (MIT, from `ulkuderner/weight-space-programming`)

- `scripts/wsp.py` — NumPy-only weight-space toolkit (`load_weights`, `summarize`, `eff_rank`, `group_mass`, `ascii_grid`, `qk_ov`, `composition`, `baseline_composition`, `copying_score`, `EditSession`, `unit_direction`, `top_writers`, `ablate_direction`, `random_control`, `bypass_unit`, `Budget`, `paired_stats`).
- `scripts/hf_passes.py` — Budgeted, logged `generate` / `teacher_forced` forward-pass evaluator for PyTorch/Transformers checkpoints (refunds failed passes; enforces no-training protocol).

## Hard Engineering Rules

1. **Measure before mutating.** Establish baseline metrics, parameter/FLOP/VRAM budgets, and a null control (random init, random orthogonal direction, or seeded baseline) before changing architecture, reward shaping, or weights.
2. **Isolate causes.** Change one variable at a time (learning rate, architecture, reward term, or single targeted weight tensor) and confirm on held-out seeds/environments with paired standard error (`gain > 2 * SE`).
3. **Never confuse LLM prompting with deep learning.** For LLM agent harnesses, RAG, or prompt orchestration, route to `skill://agent-harnesses` or `skill://domain-rules/references/ai-concepts.md`; this skill covers neural computation, RL, representation learning, and weight-space engineering.
4. **Prevent silent numerical failure.** Log grad norms, activation variance, NaN/Inf counts, and effective rank; prefer BF16 over FP16 when hardware supports it; use deterministic seeds for ablations.
5. **Respect licenses and attribution.** Bundled `scripts/wsp.py` and `scripts/hf_passes.py` are MIT-licensed (`LICENSE`, Caglar Ulkuderner); the adapted experiment catalogue follows CC BY 4.0 from Takehi, Teoh, Zhang & Khattab (MIT CSAIL, Nov 2026).
