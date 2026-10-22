# Frozen local-model confirmation

This benchmark evaluates **patient–trial classification**, separately from the product's retrieval/ranking and biomarker models. It uses public synthetic profiles, not hospital patients or observed treatment outcomes.

## Results

| System | Accuracy | Macro-F1 | Eligible precision | Eligible recall | False eligible / 433 | Excluded → eligible / 201 |
|---|---:|---:|---:|---:|---:|---:|
| LANA adapted MedGemma 1.5 4B · selected source | 66.47% | 65.52% | 73.85% | 41.38% | 34 | 26 |
| GPT-6 Luna · direct high | 36.99% | 22.32% | 80.00% | 1.72% | 1 | 0 |
| GPT-5.6 Terra · direct high | 42.71% | 33.44% | 57.14% | 1.72% | 3 | 1 |
| Original 725 / vote · descriptive reference | 65.71% | 65.26% | 64.25% | 49.57% | 64 | 51 |

All arms have zero invalid outputs. LANA identifies 96/232 eligible **pairs**, compared with 4/232 for each control. These are not counts of distinct real patients. More retrieved positive opportunities come with more false-eligible predictions.

Compared with the original adapter, the new recipe reduces false eligibility from 64 to 34 while recall falls from 49.57% to 41.38%. Its accuracy/F1 differences versus that adapter are small (+0.75/+0.26 percentage points), descriptive, and not prespecified superiority endpoints.

![Quality and cost with different scopes disclosed.](../assets/06-benchmark-quality-cost.png)

## Cohort and task

- Source: official TREC Clinical Trials 2023 synthetic questionnaires, human relevance judgments and historical trial snapshots.
- All **665** qualified patient–trial pairs, **29** held-out profile IDs, **650** trial IDs and **8** disease templates are retained.
- Labels: nonrelevant (232), excluded (201), eligible (232). Invalid predictions, if present, remain in the denominator.
- The full canonical six-field clinical projection must fit a 2,304-token guard. No clinical source truncation is permitted.
- Cohort selection is class-stratified and context-qualified before inference; it is not a population-prevalence sample.
- Confirmation profile IDs and trial IDs/core texts were held out from optimisation. Questionnaire templates are shared with training; semantic/pretraining independence is not established.

This is a broad medical cohort with a sparse breast-cancer component, not a colorectal-specific validation set.

## Model, training and controls

**Local candidate:** `google/medgemma-1.5-4b-it`, fixed revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`, NF4 quantised linear layers with FP16 compute / FP32 residuals on an 8 GB RTX 2080 SUPER. Q/K/V/O LoRA uses rank 16, alpha 32, 136 modules and 8,912,896 trainable parameters.

The adapted checkpoint was trained with **1,706 human-labelled pairs from 68 profiles**, one epoch, learning rate 1e-5, risk coefficient 0.5 and margin 1. It is supervised QLoRA, **not a teacher-distilled or outcome-RL checkpoint**. Its hash is `d7b4b1e016ffe723566d318374e4858a5e564670aa318ae13b3dc5479f73e409`.

Source/mean/vote tied on the earlier 90-pair DEV aggregate; a fixed source-first tiebreak selected source before confirmation. Four uncached source/A/B/C views were physically computed, but the selected source-only arm equals the primary output. No incremental voting/agentic gain is established by this run. The model has no native `reasoning_effort` setting in this experiment, and no generated chain of thought was used.

**API controls:** only the recorded GPT-6 Luna and GPT-5.6 Terra direct high-effort requests, default tier, `store=false`, 8,192 completion-token cap. All systems received the same complete clinical source messages. Incorrect/invalid responses were not selectively retried; the confirmation has 1,330 API attempts and no transport retries.

This is an adapted-system versus direct-API comparison with unequal learning and compute budgets. It does not establish universal foundation-model superiority.

## Prespecified statistics

5,000 paired patient-profile cluster bootstrap resamples, seed `20261026`, fixed three-class macro-F1. Bonferroni adjustment covers four primary endpoints (accuracy/F1 versus each comparator). Each interval has nominal 98.75% coverage, providing a 95% family.

| LANA minus control | Metric | Difference, percentage points | Adjusted interval |
|---|---|---:|---:|
| Luna | Accuracy | +29.47 | [+22.65, +35.77] |
| Luna | Macro-F1 | +43.20 | [+35.84, +50.00] |
| Terra | Accuracy | +23.76 | [+16.64, +30.63] |
| Terra | Macro-F1 | +32.08 | [+24.62, +39.52] |

All four lower bounds exceed zero. The prespecified eight-template cluster sensitivity also has four positive lower bounds; it is not an additional independent confirmation. The public replay directly expands sampled rows and reproduces both sets of intervals.

## Recorded cost

| System | USD / 1,000 pair decisions | Scope |
|---|---:|---|
| LANA 4B | 0.01588905 | Gross warm-batch GPU electricity only; four uncached views |
| Luna | 0.18817872 | Hosted API token-usage estimate at archived rates |
| Terra | 3.07834737 | Hosted API token-usage estimate at archived rates |

These scopes differ; no equal-scope OPEX savings ratio is reported. The local measurement covers 1,177.2775 seconds / 2,660 forwards and 0.07044147 kWh, at an assumed $0.15/kWh and 100% sampled coverage. Wrapper/state/serialisation is included; model loading/switching, training/DEV/teacher, CPU/host, idle, hardware and operations are excluded. Whole-service local OPEX and single-view serving cost are unmeasured. API estimates are not invoices.

## Reproduce the calculations

Python 3.11+ standard library only. No API requests, GPU or model weights are needed.

```bash
python3 benchmarks/replay.py
python3 benchmarks/replay.py --bootstrap
```

The script checks the row hash, all 665 identities, class support, six arms, full confusion matrices, precision/recall, false eligibility and aggregate cost arithmetic. `--bootstrap` additionally recreates both 5,000-resample cluster analyses, including multiplicity adjustment.

Published artifacts: [prediction rows](results/confirmation-665/predictions.jsonl), [audit summary](results/confirmation-665/audit-summary.json), [manifest](results/confirmation-665/manifest.json), [curated protocol](results/confirmation-665/protocol.json), [analysis plan](results/confirmation-665/analysis-plan.json) and [plotted data](results/confirmation-665/chart-data.json).

The publication rows are a **post-evaluation join** of sealed predictions with gold labels. They are not a training/DEV split. Raw API responses, complete inference logs, training datasets and adapted weights are not bundled. Metric replay does not reproduce inference or independently verify the original raw-model execution. The source audit and raw-record hashes are retained for provenance; the [research kernel](../research/README.md) is hash-matched to the frozen protocol.

## Earlier findings retained

- An earlier 516-case six-label criterion test was negative: LANA F1 52.78%, Luna 60.42%, Terra 67.55%.
- An earlier 291-pair trial-level study had point wins, but adjusted Terra intervals included zero.
- A 1,116 new-trial replication had scoped accuracy/F1 wins and substantially more false eligibility, using previously evaluated profile IDs.
- Adaptive 192-pair DEV scores (69.27% accuracy / 68.92% F1) are development results with profile overlap in added training, not substitutes for the frozen confirmation.

These tasks/cohorts are not pooled. The fixed confirmation supports the stated task-specific accuracy/F1 comparison; it does not establish clinical safety, enrolment success, colorectal validity, causal agentic/RL gains, patient benefit or whole-platform data sovereignty.
