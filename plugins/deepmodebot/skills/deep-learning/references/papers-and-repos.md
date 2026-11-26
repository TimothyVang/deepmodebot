# Scraped Primary-Source Paper Catalog & Verified Deep Learning / RL Repositories

Every arXiv entry below was fetched and verified via `export.arxiv.org/api/query` and every GitHub repo via `gh api` on 2026-11-24. Scoped strictly to **Deep Learning, RL, Neural Networks, World Models, Geometric/Scientific ML & Weight-Space Programming** (no LLM-prompting wrappers).

## 1. Weight-Space Programming, Circuits & Generalization Theory (10 Papers)

| arXiv / Source | Date | Title & First Authors | Core Takeaway |
|---|---|---|---|
| [Sparks of WSP](https://rikiyat.github.io/blog/weight-space-programming/) | 2026-11 | Sparks of Weight-Space Programming (Takehi, Teoh, Zhang, Khattab — MIT CSAIL) | READ/FIX/WRITE neural weights via reasoning + budgeted passes without backprop |
| `arXiv:2106.06981` | 2021-06 | Thinking Like Transformers — RASP (Weiss, Goldberg, Yahav) | Formal sequence-processing language mapping algorithms to attention/MLP layers |
| `arXiv:2301.05062` | 2023-01 | Tracr: Compiled Transformers as a Laboratory for Interpretability (Lindner et al.) | Compiles RASP programs directly into ground-truth transformer weights |
| `arXiv:1609.09106` | 2016-09 | HyperNetworks (Ha, Dai, Le) | One neural network generates weights for another |
| `arXiv:2209.04836` | 2022-09 | Git Re-Basin: Merging Models modulo Permutation Symmetries (Ainsworth et al.) | Zero-barrier linear mode connectivity after aligning neuron permutations |
| `arXiv:2212.04089` | 2022-12 | Editing Models with Task Arithmetic (Ilharco et al.) | Weight-space task vectors compose, add, and negate learned skills |
| `arXiv:1806.07572` | 2018-06 | Neural Tangent Kernel: Convergence and Generalization (Jacot, Gabriel, Hongler) | Infinite-width linearized kernel dynamics of gradient descent |
| `arXiv:1912.02292` | 2019-12 | Deep Double Descent (Nakkiran, Kaplun, Bansal) | Test error peaks at interpolation threshold then drops with overparameterization |
| `arXiv:2201.02177` | 2022-01 | Grokking: Generalization Beyond Overfitting (Power, Burda, Edwards) | Delayed phase transition from memorization to generalizing circuits under weight decay |
| `arXiv:2203.03466` | 2022-03 | Tensor Programs V: muP Zero-Shot Hyperparameter Transfer (Yang, Hu, Babuschkin) | Width-invariant parametrization transfers optimal LRs from tiny proxy nets |

## 2. Reinforcement Learning & World Models (19 Papers)

| arXiv ID | Date | Title & First Authors | Core Takeaway |
|---|---|---|---|
| `arXiv:1312.5602` | 2013-12 | Playing Atari with Deep Reinforcement Learning — DQN (Mnih et al.) | Experience replay + target network stabilize off-policy deep Q-learning |
| `arXiv:1502.05477` | 2015-02 | Trust Region Policy Optimization — TRPO (Schulman et al.) | KL-constrained surrogate guarantees monotonic policy improvement |
| `arXiv:1506.02438` | 2015-06 | Generalized Advantage Estimation — GAE (Schulman et al.) | Exponentially weighted TD residuals balance advantage bias vs variance |
| `arXiv:1509.02971` | 2015-09 | Continuous Control with Deep RL — DDPG (Lillicrap et al.) | Deterministic actor-critic for continuous action spaces |
| `arXiv:1707.06347` | 2017-07 | Proximal Policy Optimization — PPO (Schulman et al.) | Clipped probability-ratio surrogate; universal first-order on-policy baseline |
| `arXiv:1707.06887` | 2017-07 | A Distributional Perspective on RL — C51 (Bellemare, Dabney, Munos) | Learn full return distribution instead of scalar expected Q-value |
| `arXiv:1710.02298` | 2017-10 | Rainbow: Combining Improvements in Deep RL (Hessel et al.) | Double + Dueling + Prioritized Replay + Multi-step + Noisy + C51 |
| `arXiv:1801.01290` | 2018-01 | Soft Actor-Critic — SAC (Haarnoja, Zhou, Abbeel) | Maximum-entropy off-policy actor-critic for robust continuous control |
| `arXiv:1802.09477` | 2018-02 | Addressing Function Approximation Error — TD3 (Fujimoto et al.) | Clipped double Q + delayed policy updates + target smoothing |
| `arXiv:1803.10122` | 2018-03 | World Models (Ha, Schmidhuber) | Train compact policies inside a learned VAE+MDN-RNN dream simulator |
| `arXiv:1810.12894` | 2018-10 | Exploration by Random Network Distillation — RND (Burda et al.) | Intrinsic bonus from predicting fixed random network solves Montezuma's Revenge |
| `arXiv:1911.08265` | 2019-11 | Mastering Atari, Go, Chess & Shogi — MuZero (Schrittwieser et al.) | MCTS planning over learned value/reward/policy latent dynamics |
| `arXiv:2006.04779` | 2020-06 | Conservative Q-Learning — CQL (Kumar, Zhou, Tucker) | Penalizes OOD action Q-values for safe offline RL |
| `arXiv:2106.01345` | 2021-06 | Decision Transformer (Chen, Lu, Rajeswaran) | Return-conditioned sequence modeling reframes offline RL without TD bootstrapping |
| `arXiv:2110.06169` | 2021-10 | Implicit Q-Learning — IQL (Kostrikov, Nair, Levine) | Expectile regression learns offline value functions without ever querying OOD actions |
| `arXiv:2301.04104` | 2023-01 | Mastering Diverse Domains through World Models — DreamerV3 (Hafner et al.) | Fixed-hyperparameter latent world model masters 150+ tasks incl. Minecraft diamonds |
| `arXiv:2303.04137` | 2023-03 | Diffusion Policy (Chi, Xu, Feng) | Conditional action-sequence denoising handles multimodal robotics control |
| `arXiv:2310.16828` | 2023-10 | TD-MPC2 (Hansen, Su, Wang) | Scalable decoder-free latent world model + MPPI continuous control |
| `arXiv:2402.15391` | 2024-02 | Genie: Generative Interactive Environments (Bruce et al.) | Unsupervised latent-action video world models |

## 3. Neural Architectures, SSL, Generative, Geometric & Scientific ML (28 Papers)

| arXiv ID | Date | Title & First Authors | Core Takeaway |
|---|---|---|---|
| `arXiv:1312.6114` | 2013-12 | Auto-Encoding Variational Bayes — VAE (Kingma, Welling) | Reparameterization trick for scalable variational latent generative models |
| `arXiv:1406.2661` | 2014-06 | Generative Adversarial Networks — GAN (Goodfellow et al.) | Minimax generator/discriminator implicit density learning |
| `arXiv:1502.03167` | 2015-02 | Batch Normalization (Ioffe, Szegedy) | Mini-batch activation standardization accelerates CNN convergence |
| `arXiv:1505.04597` | 2015-05 | U-Net (Ronneberger, Fischer, Brox) | Symmetric encoder-decoder with skip connections for dense prediction & diffusion |
| `arXiv:1512.03385` | 2015-12 | Deep Residual Learning — ResNet (He, Zhang, Ren) | Identity skip connections solve degradation in very deep networks |
| `arXiv:1607.06450` | 2016-07 | Layer Normalization (Ba, Kiros, Hinton) | Per-sample feature normalization independent of batch size |
| `arXiv:1609.02907` | 2016-09 | Graph Convolutional Networks — GCN (Kipf, Welling) | First-order spectral neighborhood aggregation on graphs |
| `arXiv:1706.03762` | 2017-06 | Attention Is All You Need — Transformer (Vaswani et al.) | Multi-head dot-product self-attention replaces recurrence |
| `arXiv:1710.10903` | 2017-10 | Graph Attention Networks — GAT (Velickovic et al.) | Learned anisotropic attention weights over graph neighborhoods |
| `arXiv:1910.07467` | 2019-10 | Root Mean Square Layer Normalization — RMSNorm (Zhang, Sennrich) | Drops mean-centering for faster, equally stable deep normalization |
| `arXiv:2002.05709` | 2020-02 | SimCLR (Chen, Kornblith, Norouzi) | Contrastive visual SSL with projection head + strong data augmentation |
| `arXiv:2006.11239` | 2020-06 | Denoising Diffusion Probabilistic Models — DDPM (Ho, Jain, Abbeel) | Iterative score/noise prediction yields high-fidelity mode-covering generation |
| `arXiv:2008.02217` | 2020-08 | Hopfield Networks is All You Need (Ramsauer et al.) | Continuous modern Hopfield update equals transformer attention |
| `arXiv:2010.08895` | 2020-10 | Fourier Neural Operator — FNO (Li, Kovachki et al.) | Frequency-domain operator learning solves parametric PDEs zero-shot across grids |
| `arXiv:2010.11929` | 2020-10 | Vision Transformer — ViT (Dosovitskiy et al.) | Patch-tokenized pure transformer scales vision representation learning |
| `arXiv:2101.03961` | 2021-01 | Switch Transformers — MoE (Fedus, Zoph, Shazeer) | Top-1 sparse expert routing scales capacity at constant FLOPs |
| `arXiv:2102.09844` | 2021-02 | E(n) Equivariant Graph Neural Networks (Satorras, Hoogeboom, Welling) | Simple coordinate/invariant message passing preserves $E(n)$ symmetry |
| `arXiv:2104.13478` | 2021-04 | Geometric Deep Learning Blueprint (Bronstein, Bruna, Cohen) | Unifies CNNs, GNNs, Transformers & equivariant nets via group symmetry |
| `arXiv:2111.06377` | 2021-11 | Masked Autoencoders — MAE (He et al.) | High-ratio (75%) patch masking enables scalable asymmetric vision pretraining |
| `arXiv:2209.03003` | 2022-09 | Rectified Flow (Liu, Gong, Liu) | Straightens ODE transport paths via reflow for few-step generation |
| `arXiv:2209.15007` | 2022-09 | Understanding Collapse in Non-Contrastive SSL (Li, Efros, Pathak) | Explains how predictor + stop-gradient + EMA prevent representation collapse |
| `arXiv:2210.02747` | 2022-10 | Flow Matching for Generative Modeling (Lipman, Chen, Ben-Hamu) | Simulation-free conditional vector-field regression generalizes diffusion |
| `arXiv:2301.08243` | 2023-01 | I-JEPA (Assran, Duval, Misra) | Predicts abstract target block representations in latent space, not pixels |
| `arXiv:2304.07193` | 2023-04 | DINOv2 (Oquab, Darcet, Moutakanni) | Curated data + discriminative self-distillation yields universal visual features |
| `arXiv:2312.00752` | 2023-12 | Mamba: Selective State Spaces (Gu, Dao) | Input-selective SSMs achieve linear-time sequence modeling with hardware scan |
| `arXiv:2404.19756` | 2024-04 | KAN: Kolmogorov-Arnold Networks (Liu, Wang, Vaidya) | Spline activations on edges improve interpretability on low-dim scientific tasks |
| `arXiv:2405.21060` | 2024-05 | Transformers are SSMs — Mamba-2 (Dao, Gu) | Structured State Space Duality unifies linear attention and selective SSMs |
| `arXiv:2506.09985` | 2025-06 | V-JEPA 2 (Assran, Bardes, Fan) | Self-supervised video world model enables prediction and zero-shot robot planning |

## 4. Optimization & Systems (6 Papers)

| arXiv ID | Date | Title & First Authors | Core Takeaway |
|---|---|---|---|
| `arXiv:1412.6980` | 2014-12 | Adam (Kingma, Ba) | First + second moment adaptive per-parameter learning rates |
| `arXiv:1710.03740` | 2017-10 | Mixed Precision Training (Micikevicius et al.) | FP16/BF16 Tensor Core compute with FP32 master weights halves VRAM |
| `arXiv:1711.05101` | 2017-11 | Decoupled Weight Decay — AdamW (Loshchilov, Hutter) | Decoupling $L_2$ decay from adaptive gradient denominator fixes generalization |
| `arXiv:1910.02054` | 2019-10 | ZeRO Memory Optimizations (Rajbhandari et al.) | Shards optimizer states, gradients & weights across data-parallel ranks |
| `arXiv:2010.01412` | 2020-10 | Sharpness-Aware Minimization — SAM (Foret et al.) | Flatter loss basins improve generalization and label-noise robustness |
| `arXiv:2205.14135` | 2022-05 | FlashAttention (Dao, Fu, Ermon) | IO-aware SRAM tiling delivers exact attention in $O(N)$ HBM memory |

## 5. Curated Non-LLM Deep Learning, RL & Weight-Space GitHub Repos (37 Verified)

| Repo | Stars (2026-11) | License | Domain |
|---|---|---|---|
| `jax-ml/jax` | 36.7k | Apache-2.0 | Functional autodiff + XLA JIT/vmap/shard_map |
| `huggingface/diffusers` | 35.0k | Apache-2.0 | Diffusion & flow-matching models (image/video/audio) |
| `tinygrad/tinygrad` | 34.0k | MIT | Minimalist lazy tensor compiler & accelerator backend |
| `karpathy/nn-zero-to-hero` | 26.0k | MIT | First-principles neural network & backprop curriculum |
| `Dao-AILab/flash-attention` | 25.3k | BSD-3-Clause | IO-aware exact CUDA/Triton attention kernels |
| `pyg-team/pytorch_geometric` | 24.2k | MIT | Graph Neural Networks & geometric deep learning |
| `huggingface/candle` | 21.4k | Apache-2.0 | Minimalist zero-Python Rust ML framework |
| `triton-lang/triton` | 20.6k | MIT | Python GPU kernel compiler |
| `karpathy/micrograd` | 19.1k | MIT | ~100-LOC scalar autograd engine |
| `state-spaces/mamba` | 19.0k | Apache-2.0 | Mamba / Mamba-2 Selective State Space Models |
| `google-deepmind/mujoco` | 18.5k | Apache-2.0 | Contact-rich physics engine (CPU + MJX GPU) |
| `tracel-ai/burn` | 16.3k | Apache-2.0 | Full Rust deep learning framework (CubeCL/CUDA/WGPU) |
| `facebookresearch/vggt` | 14.7k | Custom | CVPR 2025 Best Paper — 3D visual geometry transformer |
| `DLR-RM/stable-baselines3` | 14.0k | MIT | Reliable PyTorch RL baselines |
| `facebookresearch/dinov2` | 13.6k | Apache-2.0 | Self-supervised universal visual representations |
| `Farama-Foundation/Gymnasium` | 12.9k | MIT | Standard RL environment interface |
| `vwxyzjn/cleanrl` | 10.7k | MIT-style | Clean single-file PyTorch RL algorithms |
| `google/flax` | 7.4k | Apache-2.0 | Flexible neural network library for JAX |
| `PufferAI/PufferLib` | 6.9k | MIT | High-throughput vectorized RL engine |
| `pytorch/torchtitan` | 6.0k | BSD-3-Clause | PyTorch-native distributed training (FSDP2/FP8/compile) |
| `facebookresearch/vjepa2` | 4.9k | MIT | Self-supervised video world model for prediction & planning |
| `real-stanford/diffusion_policy` | 4.7k | MIT | Visuomotor robotics control via action diffusion |
| `danijar/dreamerv3` | 4.0k | MIT | Generalist latent world-model RL agent |
| `neuraloperator/neuraloperator` | 4.0k | MIT | Fourier & graph neural operators for PDEs |
| `pytorch/rl` | 3.6k | MIT | Modular TorchRL primitives & distributed collectors |
| `facebookresearch/ijepa` | 3.5k | Custom | Image Joint-Embedding Predictive Architecture |
| `google/brax` | 3.3k | Apache-2.0 | Massively parallel JAX rigid-body physics for RL |
| `patrick-kidger/equinox` | 3.0k | Apache-2.0 | PyTree neural nets + scientific computing in JAX |
| `KellerJordan/Muon` | 3.0k | MIT | Orthogonalized momentum optimizer for hidden matrices |
| `google-deepmind/optax` | 2.4k | Apache-2.0 | Composable gradient & optimizer transforms for JAX |
| `google-deepmind/mujoco_playground` | 2.3k | Apache-2.0 | GPU-accelerated MuJoCo robotics RL benchmarks |
| `RikiyaT/lm_understand-logs` | 1.3k | CC BY 4.0 | MIT CSAIL Weight-Space Programming experiment logs |
| `luchris429/purejaxrl` | 1.1k | Apache-2.0 | End-to-end JIT-compiled JAX RL training loops |
| `nicklashansen/tdmpc2` | 1.0k | MIT | Decoder-free latent world model + MPC control |
| `bold-lab-ai/JaxMARL` | 0.9k | Apache-2.0 | Multi-agent RL compiled in JAX |
| `google-deepmind/tracr` | 0.6k | Apache-2.0 | RASP-to-transformer weight compiler |
| `ulkuderner/weight-space-programming` | 0 | MIT | Weight-space READ/FIX/WRITE skill, MCP server, NumPy library |
