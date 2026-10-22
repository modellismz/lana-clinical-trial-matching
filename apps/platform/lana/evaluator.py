"""Deterministic rule evaluator: patient facts x compiled criteria -> Met / Not met / Unknown.

The model never decides eligibility. A criterion is Unknown whenever the needed fact is missing,
is not a completed test (`done`), or is older than its recency window.
"""
from __future__ import annotations

from datetime import date

from .patient import REF_DATE

RECENCY_DAYS = {"lab": 28, "fitness": 28, "imaging": 42}
BIOMARKERS = {"kras", "nras", "braf", "her2", "msi"}
LABELS = {
    "kras": "KRAS", "nras": "NRAS", "braf": "BRAF", "her2": "HER2", "msi": "MSI / MMR", "ecog": "ECOG performance status",
    "anc": "ANC", "platelets": "Platelet count", "hemoglobin": "Hemoglobin", "crcl": "Creatinine clearance",
    "creatinine": "Serum creatinine", "creatinine_uln": "Serum creatinine", "bilirubin": "Bilirubin", "bilirubin_uln": "Bilirubin",
    "transaminase_uln": "AST / ALT", "measurable": "Baseline CT (RECIST)", "brain_mets": "Brain imaging", "hiv": "HIV screen",
    "hbv": "Hepatitis B screen", "hcv": "Hepatitis C screen", "consent": "Consent record", "age": "Age", "stage_iv": "Stage",
    "prior_lines": "Treatment history",
}
ACTION = {
    "not_done": "Order the test",
    "pending": "Chase the pending result",
    "failed": "Repeat the test (first attempt failed)",
    "insufficient": "Obtain more sample, or use a liquid biopsy",
}


def _compare(op: str, have, want) -> bool:
    if op == "ge":
        return have >= want
    if op == "le":
        return have <= want
    return have == want


def _satisfies(fact_name: str, fact: dict, test: dict) -> bool:
    op, want = test["op"], test["value"]
    val = fact["value"]
    if op == "variant":
        if fact_name == "braf":
            return val == "mutant" and fact.get("variant") == want
        return val == "mutant" and (fact.get("variant") or "").upper().startswith(want.upper())
    if fact_name == "kras" and op == "eq" and want == "mutant":
        return val == "mutant"
    return _compare(op, val, want)


def assess(criterion: dict, facts: dict[str, dict], today: date = REF_DATE) -> dict:
    """One criterion -> {status, reason, action, evidence}."""
    name = criterion["fact"]
    fact = facts.get(name)
    label = LABELS.get(name, name)
    if fact is None:
        return {"status": "unknown", "reason": f"{label} is not part of the record", "action": f"Record {label}", "evidence": None}
    if fact["status"] != "done":
        why = fact["status"].replace("_", " ")
        return {
            "status": "unknown",
            "reason": f"{label}: {why}",
            "action": ACTION.get(fact["status"], "Collect the data") if name in BIOMARKERS else f"Record {label}",
            "evidence": _evidence(name, fact),
        }
    window = RECENCY_DAYS.get(criterion["kind"])
    if window and fact.get("date"):
        age = (today - date.fromisoformat(fact["date"])).days
        if age > window:
            return {
                "status": "unknown",
                "reason": f"{label} is {age} days old (window {window})",
                "action": f"Repeat {label}",
                "evidence": _evidence(name, fact),
            }
    if fact["value"] is None:
        return {"status": "unknown", "reason": f"{label}: no value", "action": f"Record {label}", "evidence": _evidence(name, fact)}
    holds = _satisfies(name, fact, criterion["test"])
    ok = holds if criterion["polarity"] == "require" else not holds
    return {"status": "met" if ok else "not_met", "reason": None, "action": None, "evidence": _evidence(name, fact)}


def _evidence(name: str, fact: dict) -> dict:
    return {"fact": name, "value": fact["value"], "variant": fact.get("variant"), "status": fact["status"], "source": fact["source"], "date": fact.get("date"), "detail": fact.get("detail")}


def evaluate_trial(criteria: list[dict], facts: dict[str, dict]) -> dict:
    """Assess every assessable criterion once (identical tests are merged) and summarise."""
    seen: dict[tuple, dict] = {}
    rows = []
    review = 0
    for c in criteria:
        if not c["assessable"]:
            review += 1
            continue
        key = (c["fact"], c["test"]["op"], str(c["test"]["value"]), c["polarity"])
        if key in seen:
            seen[key]["merged"] += 1
            continue
        a = assess(c, facts)
        row = {**c, **a, "merged": 1}
        seen[key] = row
        rows.append(row)
    counts = {"met": 0, "not_met": 0, "unknown": 0}
    for r in rows:
        counts[r["status"]] += 1
    if counts["not_met"]:
        verdict = "blocked"
    elif counts["unknown"]:
        verdict = "provisional"
    else:
        verdict = "ready"
    return {"criteria": rows, "counts": counts, "needs_review": review, "verdict": verdict}


def next_tests(rows: list[dict]) -> list[dict]:
    """Group Unknown rows by the action that would resolve them."""
    groups: dict[str, dict] = {}
    for r in rows:
        if r["status"] != "unknown":
            continue
        g = groups.setdefault(r["fact"], {"fact": r["fact"], "label": LABELS.get(r["fact"], r["fact"]), "action": r["action"], "reason": r["reason"], "criteria": []})
        g["criteria"].append(r["id"])
    return sorted(groups.values(), key=lambda g: -len(g["criteria"]))
