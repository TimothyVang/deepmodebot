# Reinforcement Learning & World Models

Algorithm selection, mathematical primitives, failure diagnostics, and verified codebases for deep RL (control, games, robotics, multi-agent, offline RL, and world models).

## Algorithm Selector

| Regime | Default Pick | Runner-Up / Upgrade | Key Papers (arXiv) |
|---|---|---|---|
| Discrete actions, cheap sim, fast iteration | **PPO + GAE** (vectorized envs) | **Rainbow DQN / C51** (sample-efficient off-policy) | `1707.06347`, `1506.02438`, `1312.5602`, `1710.02298`, `1707.06887` |
| Continuous control, sample efficiency critical | **SAC** (max-entropy stochastic actor) | **TD3** (clipped double Q + delayed policy) | `1801.01290`, `1802.09477`, `1509.02971` |
| Pixel observations, sparse rewards, multi-domain sample efficiency | **DreamerV3** (latent RSSM world model) | **TD-MPC2** (continuous latent MPC) / **MuZero** (tree search) | `2301.04104`, `2310.16828`, `1911.08265`, `1803.10122` |
| Fixed offline dataset (no online env rollouts) | **IQL** (expectile regression, no OOD query) | **CQL** (conservative Q penalty) / **Decision Transformer** | `2110.06169`, `2006.04779`, `2106.01345` |
| Visuomotor robotics / multimodal action chunks | **Diffusion Policy** (action-sequence denoising) | **TD-MPC2** | `2303.04137` |
| Hard sparse-reward exploration | **PPO + RND** (random target prediction error) | DreamerV3 / curiosity bonuses | `1810.12894` |
| Interactive video-based world simulation | **Genie** (latent action world model) | **V-JEPA 2** (predictive video planning) | `2402.15391`, `2506.09985` |

## Core Mathematical & Implementation Invariants

- **Policy Gradients (TRPO `1502.05477` -> PPO `1707.06347` + GAE `1506.02438`):**
  - Always separate **termination** (true terminal state, bootstrap $V(s') = 0$) from **truncation** (time-limit cutoff, MUST bootstrap $V(s')$); conflating them breaks value estimation near horizon boundaries.
  - Normalize advantages per minibatch (`(A - mean) / (std + 1e-8)`), clip global grad norm (`0.5`), anneal LR linearly, and track empirical KL divergence (`approx_kl`) + clip fraction (`0.1-0.25` healthy; `>0.4` means LR/step too large).
  - Use orthogonal initialization (`gain=sqrt(2)` hidden, `0.01` policy head, `1.0` value head) for stable initial entropy.
- **Off-Policy Actor-Critic (DDPG `1509.02971` -> TD3 `1802.09477` -> SAC `1801.01290`):**
  - Twin critics (`min(Q1, Q2)`) suppress overestimation bias; update target networks with Polyak averaging ($\tau \approx 0.005$).
  - In SAC, auto-tune entropy temperature $\alpha$ toward target entropy $-\dim(\mathcal{A})$ and apply the tanh-squashing Jacobian log-prob correction (missing this causes silent policy collapse).
  - Never let replay buffer warmup drop below `1,000-10,000` transitions before starting critic updates; monitor Q-value drift for divergence.
- **Model-Based RL & World Models (World Models `1803.10122`, MuZero `1911.08265`, DreamerV3 `2301.04104`, TD-MPC2 `2310.16828`):**
  - DreamerV3 stabilizes across domains via symlog predictions ($\text{symlog}(x) = \text{sign}(x)\ln(|x|+1)$), two-hot discrete regression targets, percentile return normalization, and free-bits KL balancing.
  - TD-MPC2 plans in a learned decoder-free latent space with MPPI over short horizons — avoids wasting capacity reconstructing background pixels.
- **Offline RL (CQL `2006.04779`, IQL `2110.06169`, Decision Transformer `2106.01345`):**
  - Standard Q-learning explodes offline because Bellman backups query out-of-distribution (OOD) actions. IQL completely avoids OOD action queries via asymmetric expectile regression on $V(s)$ and advantage-weighted behavioral extraction.

## RL Debugging Checklist (Run In Order)

1. **Sanity env first:** Verify the algorithm solves `CartPole-v1` (discrete) or `Pendulum-v1` (continuous) in minutes before touching custom envs.
2. **Observation & reward scaling:** Running mean/std normalization (clipped to `[-10, 10]`) prevents gradient explosion; never normalize sparse terminal rewards with unstable variance.
3. **Seed variance:** Report IQM (interquartile mean) across $\ge 5$ random seeds — single-seed RL curves are noise.
4. **Throughput bottleneck:** CPU-bound Python envs starve GPUs. Move vectorization to `PufferLib`, `Brax`, `MuJoCo Playground`, or end-to-end JAX (`PureJaxRL`, `JaxMARL`) for $10^5-10^6$ steps/sec.
5. **Reward hacking audit:** Visually inspect rolled-out policy episodes; high scalar return frequently exploits physics glitches or terminal loops.

## Verified RL Repositories

| Repo | License | Best For |
|---|---|---|
| `vwxyzjn/cleanrl` | MIT-style | Single-file, readable, reproducible PyTorch RL baselines (PPO, SAC, TD3, DQN, C51) |
| `PufferAI/PufferLib` | MIT | High-throughput vectorized RL environments and C/PyTorch PPO training |
| `Farama-Foundation/Gymnasium` | MIT | Standard Python RL environment API (`step -> obs, reward, terminated, truncated, info`) |
| `pytorch/rl` (TorchRL) | MIT | Modular PyTorch RL primitives, TensorDict replay buffers, distributed collectors |
| `DLR-RM/stable-baselines3` | MIT | Battle-tested PyTorch RL baselines with evaluation callbacks |
| `google-deepmind/mujoco` | Apache-2.0 | Fast, accurate contact-rich physics engine (CPU + MJX GPU) |
| `google-deepmind/mujoco_playground` | Apache-2.0 | GPU-accelerated MuJoCo robotics & sim-to-real RL benchmarks |
| `google/brax` | Apache-2.0 | Massively parallel JAX differentiable rigid-body physics |
| `luchris429/purejaxrl` | Apache-2.0 | End-to-end JIT-compiled JAX RL loops (env + policy on one GPU/TPU) |
| `bold-lab-ai/JaxMARL` | Apache-2.0 | Multi-agent RL environments and algorithms compiled in JAX |
| `danijar/dreamerv3` | MIT | Official DreamerV3 world-model RL implementation |
| `nicklashansen/tdmpc2` | MIT | Official TD-MPC2 decoder-free latent world model + MPC |
| `real-stanford/diffusion_policy` | MIT | Official visuomotor Diffusion Policy codebase |
