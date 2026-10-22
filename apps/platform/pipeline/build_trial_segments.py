"""Embed head / inclusion / exclusion text of every colorectal trial, for the trial-fit predictor.

Output: data/processed/trial_segments.npz  (ids, head, inc, exc)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lana.criteria import split_criteria  # noqa: E402
from lana.embed import encode  # noqa: E402

PROC = ROOT / "data" / "processed"


def main() -> None:
    trials = json.loads((PROC / "trials_raw.json").read_text())
    ids = [t["nct_id"] for t in trials]
    heads, incs, excs = [], [], []
    for t in trials:
        heads.append(f"{t['title']}. Conditions: {', '.join(t['conditions'])}. {t['summary'][:900]}")
        parts = split_criteria(t["eligibility_text"])
        incs.append(" ".join(x for s, x in parts if s == "inclusion")[:2500] or t["title"])
        excs.append(" ".join(x for s, x in parts if s == "exclusion")[:2500] or "No exclusion criteria listed.")
    np.savez(
        PROC / "trial_segments.npz",
        ids=np.array(ids),
        head=encode(heads, max_len=256),
        inc=encode(incs, max_len=320),
        exc=encode(excs, max_len=320),
    )
    print("done", len(ids))


if __name__ == "__main__":
    main()
