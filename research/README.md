# Local MedGemma experiment source

`medgemma-kernel/` contains the **15-file local import closure** of `trec_format_engine_v1.py` and `trec_2023_projection.py`, copied unchanged from the frozen confirmation's registered source. Every file matches the hash recorded in [the protocol](../benchmarks/results/confirmation-665/protocol.json); [the kernel manifest](medgemma-kernel/source-manifest.json) provides the direct mapping.

This source exposes the actual model-loading, Q/K/V/O adapters, source projection, three-class decision scoring and risk-weighted objective. It also includes historical task/helper modules required by that import chain. Those historical helpers are not additional completed benchmark arms or recommended default execution commands.

## Frozen configuration

| Item | Value |
|---|---|
| Base | `google/medgemma-1.5-4b-it` |
| Base revision | `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b` |
| Adapted checkpoint SHA-256 | `d7b4b1e016ffe723566d318374e4858a5e564670aa318ae13b3dc5479f73e409` |
| Hardware | RTX 2080 SUPER, 8 GB |
| Runtime | Transformers, NF4 linear quantisation, FP16 compute / FP32 residuals |
| LoRA | Q/K/V/O; rank 16; alpha 32; 136 modules; 8,912,896 trainable parameters |
| Adaptation | 1,706 human-labelled pairs / 68 profiles; one epoch; learning rate 1e-5 |
| Risk objective | Coefficient 0.5; margin 1 |
| Context guard | 2,304 tokens for the canonical projection; no source truncation |
| Physical views | Source plus A/B/C untrusted-proposal views; four uncached forwards |
| Selected output | Source, fixed before confirmation |

The current checkpoint is supervised QLoRA. It is not a teacher-distilled, reinforcement-learned or clinically validated outcome model. Extra voting did not demonstrate a causal gain in this confirmation.

## Reproduction boundary

The gated base model, adapted checkpoint, optimiser states and complete training/raw-inference bundle are **not distributed** here. Loading a fresh base plus a newly initialised adapter does not reproduce the published result. Some inherited research helpers retain original experiment paths; they are archived source for inspection, not a turnkey training package or production service.

For an immediately runnable, no-GPU/no-API reproduction of the published **metrics**, use:

```bash
python3 benchmarks/replay.py --bootstrap
```

Inference reproduction requires authorised upstream model access, the exact adapted weights and source data, compatible CUDA dependencies and the recorded protocol. vLLM serving, Laya checks, Langfuse integration and outcome RL are separate proposed product work.
