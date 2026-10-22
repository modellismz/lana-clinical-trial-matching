# Publication validation

The publication checkout was validated independently of the original repository.

| Check | Result |
|---|---|
| Repository links / reviewed asset hashes | Passed |
| Registered kernel source hashes | All 15 files match the frozen protocol |
| Frozen prediction identities / support | All 665 pairs, 29 profiles, 650 trials, 8 templates |
| Six-arm metrics and confusion matrices | Exact count match; floating-point score tolerance 1e-15 |
| Patient-profile bootstrap | 5,000 paired resamples; all four adjusted intervals reproduced within 1e-14 |
| Template-cluster sensitivity | 5,000 paired resamples; all four adjusted intervals reproduced within 1e-14 |
| Aggregate cost arithmetic | Reproduced; local electricity and hosted API scopes remain distinct |
| Prototype rule tests | 10 passed |
| Exported browser/Python evaluator parity | 4,377 criteria checked; 0 mismatches |
| Publication contents | No credential files, model weights or raw private experiment archives included |

The CI workflow repeats the runnable checks. No new GPU inference, hosted-model benchmark, hospital connector deployment or clinical outcome study was run for this repository publication.

```bash
python3 scripts/check_repository.py
python3 benchmarks/replay.py --bootstrap
cd apps/platform
python3 -m pytest -q tests
node tests/parity.mjs
```

The rule-test command requires pytest. The static demo and benchmark replay need no third-party Python dependencies.
