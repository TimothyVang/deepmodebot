# Neural Network Architectures (Non-LLM Deep Learning)

Architecture selection, inductive biases, and core structural mechanisms across vision, sequences, generative modeling, graphs, geometry, and scientific computing.

## Architecture Decision Matrix

| Modality / Problem | Primary Architecture | Key Inductive Bias / Tradeoff | Core Papers (arXiv) |
|---|---|---|---|
| Dense spatial / segmentation / denoising backbone | **U-Net** + ResNet blocks or **DiT** | Multi-scale skip connections preserve exact spatial alignment | `1505.04597`, `1512.03385` |
| Image/video representation (no labels) | **DINOv2** (discriminative SSL) / **I-JEPA** & **V-JEPA 2** (predictive latent) / **MAE** | Predict masked latents instead of pixels (avoids wasted high-frequency capacity) | `2304.07193`, `2301.08243`, `2506.09985`, `2111.06377`, `2002.05709` |
| Vision backbone (supervised / transfer) | **ViT** / ConvNeXt / `timm` models | Global self-attention scales with data; convs win on small datasets | `2010.11929`, `1512.03385` |
| 3D visual geometry & pose reconstruction | **VGGT** (Visual Geometry Grounded Transformer) | Direct feed-forward camera, depth, point-map & track estimation | `facebookresearch/vggt` |
| Long continuous/discrete sequences ($L \gg 8\text{k}$) | **Mamba / Mamba-2 (SSD)** or hybrid Attention+SSM | $O(L)$ scan with input-selective state transitions; exact duality with structured attention | `2312.00752`, `2405.21060` |
| Continuous generative modeling (images, audio, actions, molecules) | **Flow Matching / Rectified Flow** (default over DDPM) | Straight ODE trajectories need 1-10 NFE vs 50-1000 for DDPM; simpler velocity MSE loss | `2210.02747`, `2209.03003`, `2006.11239`, `1312.6114` |
| Sparse high-capacity scaling | **Mixture of Experts (Switch MoE)** | Conditional top-$k$ routing decouples parameter count from per-token FLOPs | `2101.03961` |
| Relational / graph-structured data | **GCN / GAT / Message-Passing GNN** | Permutation equivariance over nodes/edges; watch over-smoothing beyond 3-6 layers | `1609.02907`, `1710.10903`, `2104.13478` |
| 3D molecules, point clouds, physics | **E(n)-Equivariant GNN** | Exact rotation, translation & reflection equivariance without data augmentation | `2102.09844`, `2104.13478` |
| PDEs, fluid dynamics, continuous fields | **Fourier Neural Operator (FNO)** | Spectral convolution learns resolution-invariant mappings between function spaces | `2010.08895` |
| Associative memory & scientific symbolic curves | **Modern Hopfield** / **KAN** | Exponential memory capacity (equivalent to attention); learnable B-spline edges for low-dim science | `2008.02217`, `2404.19756` |

## Architectural Primitives & Failure Modes

- **Residual Connections & Normalization:**
  - Always use **Pre-Norm** (`x + f(Norm(x))`) with **RMSNorm** (`1910.07467`) or **LayerNorm** (`1607.06450`) for deep stacks; avoid **BatchNorm** (`1502.03167`) whenever batch sizes are small, sequence lengths vary, or train/eval distribution shifts occur (use GroupNorm/LayerNorm instead).
  - For very deep residual nets, scale residual branch projections by $1/\sqrt{2L}$ (or use QK-Norm in attention) to prevent logit growth and attention entropy collapse.
- **Self-Supervised Representation Learning (SSL):**
  - **Contrastive** (`SimCLR 2002.05709`) requires large negative batches and heavy augmentations; **Non-contrastive / JEPA** (`I-JEPA 2301.08243`, `V-JEPA 2 2506.09985`, `DINOv2 2304.07193`) avoids dimensional collapse via asymmetric predictor + stop-gradient EMA target encoder (`2209.15007`).
  - Always verify learned embeddings with **linear probing + k-NN accuracy** and check effective rank (`eff_rank`) of feature covariance to catch silent rank collapse early.
- **Flow Matching vs DDPM vs VAE vs GAN:**
  - Prefer **Conditional Flow Matching / Rectified Flow** (`2210.02747`, `2209.03003`) for new continuous generative models: linear interpolation $x_t = (1-t)x_0 + t x_1$ and velocity regression $\|v_\theta(x_t, t) - (x_1 - x_0)\|^2$ gives straight sampling paths and beats GAN mode collapse (`1406.2661`) and VAE blur (`1312.6114`).
  - Keep **VAEs** as continuous latent compressors (e.g., spatial latent autoencoders feeding latent diffusion/flow models or Dreamer-style world models).
- **State-Space Models (Mamba `2312.00752`, Mamba-2 `2405.21060`):**
  - Selective SSMs make $\Delta, B, C$ input-dependent so the model filters/resets state dynamically; Mamba-2's Structured State Space Duality (SSD) maps SSMs to block-matrix multiplications running on Tensor Cores. Pair SSM blocks with sparse attention layers when exact long-range associative recall matters.
- **Geometric & Operator Learning (`2104.13478`, `2102.09844`, `2010.08895`):**
  - Encode domain symmetries (translation, permutation, $SO(3)$/$E(n)$) into the layer equations rather than relying purely on augmentation; in GNNs, add residual connections + PairNorm/DropEdge to mitigate over-smoothing and over-squashing.

## Verified Architecture Repositories

- Vision & SSL: `huggingface/timm`, `facebookresearch/dinov2`, `facebookresearch/ijepa`, `facebookresearch/vjepa2`, `facebookresearch/vggt`
- SSM & Attention: `state-spaces/mamba`, `Dao-AILab/flash-attention`
- Diffusion & Flow: `huggingface/diffusers`
- Graphs & Neural Operators: `pyg-team/pytorch_geometric`, `neuraloperator/neuraloperator`
- Education / First Principles: `karpathy/micrograd`, `karpathy/nn-zero-to-hero`
