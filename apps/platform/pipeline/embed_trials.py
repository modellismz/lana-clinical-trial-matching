"""Embed every real trial (a head text + every eligibility line) with bge-m3.

Output: data/processed/chunks.json (metadata) and data/processed/chunk_vectors.npy (N x 1024, float32)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lana.criteria import compile_trial  # noqa: E402
from lana.embed import encode  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "data" / "processed"


def main() -> None:
    trials = json.loads((OUT / "trials_raw.json").read_text())
    chunks = []
    compiled = {}
    for t in trials:
        head = f"{t['title']}. Conditions: {', '.join(t['conditions'])}. Interventions: {', '.join(i for i in t['interventions'] if i)}. {t['summary'][:1200]}"
        chunks.append({"trial": t["nct_id"], "kind": "head", "ref": None, "text": head})
        cs = compile_trial(t)
        compiled[t["nct_id"]] = cs
        for c in cs:
            if c["text"].startswith(("Minimum age", "Maximum age")):
                continue
            chunks.append({"trial": t["nct_id"], "kind": c["section"], "ref": c["id"], "text": c["text"]})
    print(f"{len(chunks)} chunks from {len(trials)} trials", file=sys.stderr)
    order = np.argsort([len(c["text"]) for c in chunks])
    vecs = np.zeros((len(chunks), 1024), dtype="float32")
    batch = 2048
    for i in range(0, len(order), batch):
        idx = order[i : i + batch]
        vecs[idx] = encode([chunks[j]["text"] for j in idx], max_len=256)
        print(f"  {min(i + batch, len(order))}/{len(order)}", file=sys.stderr, flush=True)
    np.save(OUT / "chunk_vectors.npy", vecs)
    (OUT / "chunks.json").write_text(json.dumps(chunks, ensure_ascii=False))
    (OUT / "criteria_compiled.json").write_text(json.dumps(compiled, ensure_ascii=False))
    print("done")


if __name__ == "__main__":
    main()
