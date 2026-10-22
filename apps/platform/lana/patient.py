"""Turn a cohort record into the patient facts the evaluator reads.

Each fact carries a Biomarker Status, a source and, where it matters, a date:
    REAL:<study>   copied from the public cBioPortal record
    SIM            simulated, because no public colorectal dataset has it (ECOG, labs, imaging,
                   prior lines, infection screens). The UI always shows this tag.
"""
from __future__ import annotations

import hashlib
import random
from datetime import date, timedelta

REF_DATE = date(2026, 10, 17)  # the demo's "today"; recency windows are measured from here
ULN = {"bilirubin": 1.2, "creatinine": 1.2, "ast": 40.0, "alt": 40.0}  # assumed upper limits of normal


def rng_for(pid: str) -> random.Random:
    return random.Random(int(hashlib.sha256(pid.encode()).hexdigest()[:12], 16))


def _fact(value, status="done", source="SIM", detail=None, when: date | None = None) -> dict:
    return {
        "value": value,
        "status": status,
        "source": source,
        "detail": detail,
        "date": when.isoformat() if when else None,
    }


def _days_ago(r: random.Random, lo: int, hi: int) -> date:
    return REF_DATE - timedelta(days=r.randint(lo, hi))


def build_facts(rec: dict) -> dict[str, dict]:
    """Facts for one patient. Deterministic for a given record."""
    r = rng_for(rec["id"])
    src = f"REAL:{rec['study']}"
    f: dict[str, dict] = {}

    # --- real demographics and staging -----------------------------------------------------
    f["age"] = _fact(rec["age"], "done" if rec["age"] is not None else "not_done", src)
    f["sex"] = _fact(rec["sex"], "done" if rec["sex"] else "not_done", src)
    f["stage_iv"] = _fact(bool(rec["stage_iv"]), "done", src, rec.get("stage_raw") or None)

    # --- real biomarkers, with real Biomarker Status ---------------------------------------
    bm = rec["biomarkers"]
    for gene, key in [("kras", "KRAS"), ("nras", "NRAS"), ("braf", "BRAF"), ("her2", "ERBB2"), ("msi", "MSI"), ("pik3ca", "PIK3CA")]:
        b = bm[key]
        f[gene] = _fact(b.get("result"), b["status"], src, b.get("variant"))
        f[gene]["variant"] = b.get("variant")
        f[gene]["panel"] = rec["panel"]
    f["tmb"] = _fact(rec.get("tmb"), "done" if rec.get("tmb") is not None else "not_done", src)

    # --- imaging (partly real) ---------------------------------------------------------------
    mets = rec["metastasis_sites"]
    f["metastasis_sites"] = _fact(mets, "done" if mets else "not_done", src)
    if "brain" in mets:
        f["brain_mets"] = _fact(True, "done", src, "brain metastasis recorded")
    elif r.random() < 0.72:
        f["brain_mets"] = _fact(False, "done", "SIM", "brain MRI negative", _days_ago(r, 3, 40))
    else:
        f["brain_mets"] = _fact(None, "not_done", "SIM", "no brain imaging on record")
    f["measurable"] = _fact(True, "done", "SIM", "RECIST target lesion", _days_ago(r, 2, 34)) if r.random() < 0.9 else _fact(None, "not_done", "SIM", "no baseline CT on record")

    # --- fitness (simulated) -----------------------------------------------------------------
    if r.random() < 0.9:
        f["ecog"] = _fact(r.choices([0, 1, 2, 3], [0.38, 0.45, 0.14, 0.03])[0], "done", "SIM", None, _days_ago(r, 0, 40))
    else:
        f["ecog"] = _fact(None, "not_done", "SIM", "ECOG not documented")

    # --- treatment history (simulated, anchored on the real chemo flag) ------------------------
    base = 1 if str(rec.get("chemo_exposed", "")).lower() in {"yes", "true"} else 0
    lines = max(0, min(4, base + r.choices([0, 1, 2], [0.45, 0.4, 0.15])[0] - (1 if rec["stage_iv"] and base == 0 and r.random() < 0.35 else 0)))
    f["prior_lines"] = _fact(lines, "done", "SIM", "lines of systemic therapy for metastatic disease")

    # --- labs (simulated; some missing, some stale) --------------------------------------------
    def lab(name: str, value: float, ndigits: int, lo_days=0, hi_days=36, missing=0.06) -> dict:
        if r.random() < missing:
            return _fact(None, "not_done", "SIM", "not on record")
        return _fact(round(value, ndigits), "done", "SIM", None, _days_ago(r, lo_days, hi_days))

    f["anc"] = lab("anc", max(0.6, r.gauss(4.0, 1.6)), 1)
    f["platelets"] = lab("platelets", max(60, r.gauss(260, 85)), 0)
    f["hemoglobin"] = lab("hemoglobin", max(7.0, r.gauss(11.6, 1.7)), 1)
    f["creatinine"] = lab("creatinine", max(0.4, r.gauss(0.9, 0.25)), 2)
    f["crcl"] = lab("crcl", max(25, r.gauss(82, 24)), 0)
    f["bilirubin"] = lab("bilirubin", max(0.2, r.gauss(0.7, 0.45)), 2)
    f["ast"] = lab("ast", max(10, r.gauss(34, 22)), 0)
    f["alt"] = lab("alt", max(8, r.gauss(31, 22)), 0)
    # derived ULN multiples used by trial criteria
    for name, num, uln in [("bilirubin_uln", "bilirubin", ULN["bilirubin"]), ("creatinine_uln", "creatinine", ULN["creatinine"])]:
        n = f[num]
        f[name] = {**n, "value": None if n["value"] is None else round(n["value"] / uln, 2)}
    ast, alt = f["ast"], f["alt"]
    if ast["value"] is None or alt["value"] is None:
        f["transaminase_uln"] = _fact(None, "not_done", "SIM", "AST/ALT not on record")
    else:
        f["transaminase_uln"] = {**ast, "value": round(max(ast["value"] / ULN["ast"], alt["value"] / ULN["alt"]), 2), "date": min(ast["date"], alt["date"])}

    # --- infection screens and consent (simulated) ---------------------------------------------
    for name in ("hiv", "hbv", "hcv"):
        if r.random() < 0.62:
            f[name] = _fact("negative" if r.random() > 0.015 else "positive", "done", "SIM", "screening test", _days_ago(r, 20, 300))
        else:
            f[name] = _fact(None, "not_done", "SIM", "no screening on record")
    f["consent"] = _fact(True, "done", "SIM", "consent to share data recorded") if r.random() < 0.85 else _fact(None, "not_done", "SIM", "consent not yet recorded")
    return f


def summary_segments(rec: dict, facts: dict[str, dict]) -> list[dict]:
    """The patient description as [{t: text, src: REAL|SIM}] so the UI can colour each phrase by source."""
    segs: list[dict] = []

    def add(text: str, src: str = "REAL") -> None:
        segs.append({"t": text, "src": src})

    age = facts["age"]["value"]
    add(f"{age}-year-old {rec['sex'] or 'patient'}" if age else f"Adult {rec['sex'] or 'patient'}")
    add(" with ", "-")
    add("metastatic colorectal adenocarcinoma" if rec["stage_iv"] else "colorectal adenocarcinoma")
    if rec["metastasis_sites"]:
        add(", metastases to " + ", ".join(x.replace("_", " ") for x in rec["metastasis_sites"]))
    if rec["side"]:
        add(f", {rec['side']}-sided primary")

    def describe(gene: str, label: str) -> str:
        b = facts[gene]
        if b["status"] != "done":
            return f"{label} not available ({b['status'].replace('_', ' ')})"
        res = b["value"]
        if gene == "msi":
            return "MSI-high / dMMR" if res == "msi_high" else "microsatellite stable"
        if gene == "her2":
            return "HER2 amplified" if res == "amplified" else "HER2 not amplified"
        if res == "mutant":
            return f"{label} {b['variant']} mutation"
        if res == "non_v600_mutant":
            return f"{label} non-V600 mutation ({b['variant']})"
        return f"{label} wild-type"

    for gene, label in (("kras", "KRAS"), ("nras", "NRAS"), ("braf", "BRAF"), ("msi", "MSI"), ("her2", "HER2")):
        add(", " + describe(gene, label), "REAL")
    if facts["ecog"]["value"] is not None:
        add(f", ECOG performance status {facts['ecog']['value']}", "SIM")
    add(f", {facts['prior_lines']['value']} prior lines of systemic therapy", "SIM")
    add(".", "-")
    return segs


def summary_text(rec: dict, facts: dict[str, dict]) -> str:
    """A plain-English patient description, the text that is embedded for trial retrieval."""
    return "".join(s["t"] for s in summary_segments(rec, facts))
