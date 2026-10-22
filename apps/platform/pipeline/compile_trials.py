"""Compile every trial's eligibility text into structured criteria (fast; no embeddings).

Output: data/processed/criteria_compiled.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lana.criteria import compile_trial  # noqa: E402

PROC = ROOT / "data" / "processed"


def main() -> None:
    trials = json.loads((PROC / "trials_raw.json").read_text())
    compiled = {t["nct_id"]: compile_trial(t) for t in trials}
    (PROC / "criteria_compiled.json").write_text(json.dumps(compiled, ensure_ascii=False))
    total = sum(len(v) for v in compiled.values())
    ok = sum(1 for v in compiled.values() for c in v if c["assessable"])
    print(f"{len(compiled)} trials, {total} lines, {ok} compiled into tests ({ok / total:.0%})")


if __name__ == "__main__":
    main()
