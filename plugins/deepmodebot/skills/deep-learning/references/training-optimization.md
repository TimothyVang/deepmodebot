# Deep Learning Optimization, Scaling Dynamics & Systems

Optimizers, hyperparameter transfer, generalization phenomena, low-level GPU/Rust ML frameworks, and numerical debugging for neural networks.

## Optimizers & Schedules

| Optimizer | Best For | Core Mechanism & Defaults | Reference |
|---|---|---|---|
| **AdamW** | Default baseline across CNNs, ViTs, RL, diffusion | Decoupled weight decay ($\theta \leftarrow (1-\lambda\eta)\theta - \eta \hat m / (\sqrt{\hat v}+\epsilon)$); never decay biases or 1D norm weights | `arXiv:1711.05101`, `1412.6980` |
| **Muon** | Hidden 2D weight matrices in deep networks | Orthogonalizes momentum update via Newton-Schulz iterations; pair with AdamW for 1D params, embeddings, and heads | `KellerJordan/Muon` |
| **SAM** | Small/medium vision or tabular datasets prone to sharp minima | Minimizes worst-case loss in $\rho$-ball ($\max_{\|\epsilon\|\le\rho} L(\theta+\epsilon)$); 2x step cost, stronger generalization | `arXiv:2010.01412` |
| **Optax** | Custom JAX gradient pipelines | Composable `chain(clip_by_global_norm, scale_by_adam, add_decayed_weights)` | `google-deepmind/optax` |

Schedule rule: linear warmup (1-5% of steps) -> cosine decay to 1-10% of peak LR (or Warmup-Stable-Decay / WSD for open-ended runs). Always clip global gradient norm (`1.0` standard; `0.5` for RL).

## Scaling Theory & Training Dynamics

- **muP — Maximal Update Parametrization (`arXiv:2203.03466`):** Standard initialization breaks optimal LR when scaling model width. Under muP, tune LR/init on a cheap proxy width (e.g., $d=256$) and transfer zero-shot to wide models ($d=4096+$) by scaling hidden LRs as $1/\text{width}$ and output head weights as $1/\text{width}$.
- **Neural Tangent Kernel (`arXiv:1806.07572`):** Distinguishes the *lazy/kernel* regime (features barely move) from the *rich/feature-learning* regime (where deep nets actually learn representations). Verify feature movement by tracking $\Delta W / \|W\|_F$.
- **Deep Double Descent (`arXiv:1912.02292`):** Test error rises near the interpolation threshold (model capacity $\approx$ dataset size/noise), then drops again in the overparameterized regime. Do not mistake interpolation-peak error for monotone overfitting.
- **Grokking (`arXiv:2201.02177`):** On algorithmic/structured tasks, validation accuracy can jump from chance to ~100% long after 100% training accuracy once weight decay prunes memorization circuits into generalizing circuits. Weight decay + sufficient post-memorization steps are the trigger.

## Precision, Memory & Hardware Efficiency

- **Mixed Precision (`arXiv:1710.03740`):** Default to **BF16** on Ampere+ GPUs (same exponent range as FP32, no loss scaler required). Use FP16 only on older hardware with dynamic `GradScaler`. Keep master weights, optimizer moments, and reductions (norms/softmax/losses) in FP32.
- **IO-Aware Attention (`arXiv:2205.14135`):** FlashAttention tiles $Q, K, V$ in GPU SRAM, eliminating $O(N^2)$ HBM materialization — exact math, 2-4x faster, linear memory. Never materialize $N \times N$ attention matrices manually.
- **Distributed Memory (`arXiv:1910.02054`, ZeRO / FSDP):** Partition optimizer states (Stage 1: 4x savings), gradients (Stage 2: 8x), and parameters (Stage 3 / FSDP: linear in GPUs) before resorting to pipeline parallelism. Combine with activation checkpointing (`torch.utils.checkpoint`) when activations dominate VRAM.
- **Custom Kernels & Lean Runtimes:**
  - `triton-lang/triton` — Write fused GPU kernels in Python (softmax, layernorm, custom SSM scans, sparse ops) at near-CUDA speed.
  - `jax-ml/jax` + `google/flax` + `patrick-kidger/equinox` — Pure functional autodiff, `jit`/`vmap`/`pmap`/`shard_map`, ideal for RL and scientific ML.
  - `pytorch/torchtitan` — Clean PyTorch-native distributed training recipes (FSDP2, TP, FP8, `torch.compile`).
  - `tracel-ai/burn` and `huggingface/candle` — Zero-Python, low-RAM Rust deep learning & inference frameworks (CPU/CUDA/WGPU/Metal).
  - `tinygrad/tinygrad` — Minimalist lazy-evaluated tensor compiler (~few thousand LOC) for understanding/customizing kernels.

## Numerical Debugging Playbook (Fast Root-Cause Order)

1. **Overfit one batch first:** If the model cannot reach ~0 loss on 8-32 samples in 200 steps, stop — you have a data/label alignment, mask, loss-sign, or gradient-flow bug.
2. **Gradient flow audit:** Check per-layer `grad.norm()` and `% zero grads` on step 1 and step 50; dead layers reveal broken residual scaling, vanishing activations, or detached tensors.
3. **NaN/Inf bisection:** Enable `torch.autograd.set_detect_anomaly(True)` on 1 step; top culprits are `log(0)`, `sqrt(0)` backward (`1 / (2*sqrt(x))` -> `inf` at 0 — always add `eps` *inside* `sqrt`), or unclipped `exp()`.
4. **Data pipeline check:** Profile GPU utilization (`nvtop` / `torch.profiler`); if GPU util < 80%, fix `DataLoader` (`pin_memory=True`, `persistent_workers=True`, pre-tokenized/sharded memmap or WebDataset) before buying faster GPUs.
