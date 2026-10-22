# Contributing

Open an issue describing the problem, expected behaviour and whether it concerns the product, a dataset or an evaluation method. Use public/synthetic examples only.

For changes, keep one topic per branch and include the relevant checks. Preserve REAL/SIM and Unknown states; do not silently convert missing facts into negative observations. Changes to protocol interpretation need explicit examples and review.

Run `python3 scripts/check_repository.py`, `python3 benchmarks/replay.py`, the application rule tests and browser/Python parity check documented in the README/CI. Changes to statistical calculations should also run `python3 benchmarks/replay.py --bootstrap`.

Do not optimise on the published confirmation rows or replace results after selecting favourable cases. Report changed splits, invalid outputs and regressions. Keep proposed features distinct from implemented and measured behaviour.

Project licensing remains as stated in LICENSE; contributions do not change upstream model/data terms.
