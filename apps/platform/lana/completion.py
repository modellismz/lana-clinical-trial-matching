"""Biomarker completion model: predict a missing biomarker result from the ones that are known.

Trained on real colorectal patients (cBioPortal). When a trial needs a result that is `not done`,
`pending`, `failed` or `insufficient`, the platform estimates how likely that result is to satisfy the
criterion, so a coordinator can see "likely to pass" before ordering the test. It never turns an
Unknown into Met or Not met; it only adds a probability next to it.
"""
from __future__ import annotations

import numpy as np

TARGETS = ["msi", "her2", "kras", "nras", "braf", "pik3ca"]
# positive class for each target
POSITIVE = {"msi": "msi_high", "her2": "amplified", "kras": "mutant", "nras": "mutant", "braf": "mutant", "pik3ca": "mutant"}
COLS = ["kras", "nras", "braf", "her2", "msi", "pik3ca", "side", "male", "age", "tmb", "stage_iv", "asian"]
STUDY_ASIAN = {"crc_sysucc_2022"}


def _bin(fact_status: str, result, positive: str):
    if fact_status != "done" or result is None:
        return np.nan
    return 1.0 if result == positive else 0.0


def row_from_record(rec: dict) -> dict[str, float]:
    bm = rec["biomarkers"]
    return {
        "kras": _bin(bm["KRAS"]["status"], bm["KRAS"]["result"], "mutant"),
        "nras": _bin(bm["NRAS"]["status"], bm["NRAS"]["result"], "mutant"),
        "braf": _bin(bm["BRAF"]["status"], bm["BRAF"]["result"], "mutant") if bm["BRAF"]["result"] != "non_v600_mutant" else 0.0,
        "her2": _bin(bm["ERBB2"]["status"], bm["ERBB2"]["result"], "amplified"),
        "msi": _bin(bm["MSI"]["status"], bm["MSI"]["result"], "msi_high"),
        "pik3ca": _bin(bm["PIK3CA"]["status"], bm["PIK3CA"]["result"], "mutant"),
        "side": {"left": 1.0, "right": 0.0}.get(rec.get("side"), np.nan),
        "male": {"male": 1.0, "female": 0.0}.get(rec.get("sex"), np.nan),
        "age": float(rec["age"]) if rec.get("age") is not None else np.nan,
        "tmb": float(rec["tmb"]) if rec.get("tmb") is not None else np.nan,
        "stage_iv": 1.0 if rec.get("stage_iv") else 0.0,
        "asian": 1.0 if rec["study"] in STUDY_ASIAN or "asian" in (rec.get("race") or "").lower() else 0.0,
    }


def row_from_facts(facts: dict[str, dict], rec: dict) -> dict[str, float]:
    """Same feature row, built from a patient's facts (so what the UI shows is what the model sees)."""
    pos = POSITIVE
    r = {}
    for g in ("kras", "nras", "braf", "her2", "msi", "pik3ca"):
        f = facts[g]
        v = _bin(f["status"], f["value"], pos[g])
        if g == "braf" and f["status"] == "done" and f["value"] == "non_v600_mutant":
            v = 0.0
        r[g] = v
    r["side"] = {"left": 1.0, "right": 0.0}.get(rec.get("side"), np.nan)
    r["male"] = {"male": 1.0, "female": 0.0}.get(rec.get("sex"), np.nan)
    r["age"] = float(facts["age"]["value"]) if facts["age"]["value"] is not None else np.nan
    r["tmb"] = float(facts["tmb"]["value"]) if facts["tmb"]["value"] is not None else np.nan
    r["stage_iv"] = 1.0 if facts["stage_iv"]["value"] else 0.0
    r["asian"] = 1.0 if rec["study"] in STUDY_ASIAN or "asian" in (rec.get("race") or "").lower() else 0.0
    return r


def matrix(rows: list[dict[str, float]], drop: str | None = None) -> np.ndarray:
    cols = [c for c in COLS if c != drop]
    return np.array([[r[c] for c in cols] for r in rows], dtype="float64")
