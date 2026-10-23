"""Unit tests for the criteria compiler and the evaluator: the part of Lana that decides Met / Not met / Unknown."""
from datetime import date
import json
from pathlib import Path

import pytest

from lana.criteria import compile_trial, split_criteria
from lana.evaluator import assess, evaluate_trial
from lana.patient import REF_DATE


def fact(value, status="done", d=None, variant=None, source="REAL:test"):
    return {"value": value, "status": status, "source": source, "date": d.isoformat() if d else None, "detail": None, "variant": variant}


def crit(fact_name, op, value, polarity="require", kind="biomarker"):
    return {"fact": fact_name, "test": {"op": op, "value": value}, "polarity": polarity, "kind": kind, "id": "t:0", "assessable": True, "label": fact_name, "text": "", "section": "inclusion"}


def test_split_criteria_sections_and_wrapped_lines():
    text = "Inclusion Criteria:\n\n* Age 18 or older\n* ECOG 0-1\n  with adequate organ function\n\nExclusion Criteria:\n\n* Active brain metastases\n"
    rows = split_criteria(text)
    assert rows[0] == ("inclusion", "Age 18 or older")
    assert rows[1][1].startswith("ECOG 0-1 with adequate")
    assert rows[2] == ("exclusion", "Active brain metastases")


def test_compile_biomarker_and_ecog():
    trial = {"nct_id": "NCT0", "min_age": 18, "max_age": None, "eligibility_text": "Inclusion Criteria:\n* KRAS G12C mutation\n* RAS and BRAF wild-type\n* ECOG performance status of 0 or 1\n* Hemoglobin >= 9 g/dL\nExclusion Criteria:\n* Active brain metastases\n* Prior treatment with a KRAS G12C inhibitor"}
    c = [x for x in compile_trial(trial) if x["assessable"]]
    facts = {(x["fact"], x["test"]["op"], str(x["test"]["value"]), x["polarity"]) for x in c}
    assert ("kras", "variant", "G12C", "require") in facts
    assert ("braf", "eq", "wild_type", "require") in facts
    assert ("ecog", "le", "1", "require") in facts
    assert ("hemoglobin", "ge", "9.0", "require") in facts
    assert ("brain_mets", "eq", "True", "exclude") in facts
    # a prior-inhibitor exclusion must not become a KRAS mutation test
    assert not any(x["polarity"] == "exclude" and x["fact"] == "kras" for x in c)


def test_not_done_is_unknown_never_negative():
    for status in ("not_done", "pending", "failed", "insufficient"):
        r = assess(crit("msi", "eq", "mss"), {"msi": fact(None, status)})
        assert r["status"] == "unknown", status


def test_met_and_not_met():
    assert assess(crit("kras", "variant", "G12C"), {"kras": fact("mutant", variant="G12C")})["status"] == "met"
    assert assess(crit("kras", "variant", "G12C"), {"kras": fact("mutant", variant="G12D")})["status"] == "not_met"
    assert assess(crit("braf", "eq", "wild_type"), {"braf": fact("non_v600_mutant", variant="K601E")})["status"] == "not_met"


def test_exclusion_polarity():
    c = crit("brain_mets", "eq", True, polarity="exclude", kind="imaging")
    d = REF_DATE
    assert assess(c, {"brain_mets": fact(False, d=d)})["status"] == "met"
    assert assess(c, {"brain_mets": fact(True, d=d)})["status"] == "not_met"


def test_stale_lab_is_unknown():
    c = crit("anc", "ge", 1.5, kind="lab")
    old = date.fromordinal(REF_DATE.toordinal() - 60)
    assert assess(c, {"anc": fact(3.0, d=old)})["status"] == "unknown"
    assert assess(c, {"anc": fact(3.0, d=REF_DATE)})["status"] == "met"
    assert assess(c, {"anc": fact(1.0, d=REF_DATE)})["status"] == "not_met"


def test_verdict_and_merge():
    rows = [crit("kras", "eq", "wild_type"), crit("kras", "eq", "wild_type"), crit("msi", "eq", "mss")]
    for i, r in enumerate(rows):
        r["id"] = f"t:{i}"
    out = evaluate_trial(rows, {"kras": fact("wild_type"), "msi": fact(None, "not_done")})
    assert out["counts"] == {"met": 1, "not_met": 0, "unknown": 1}
    assert out["verdict"] == "provisional"
    assert out["criteria"][0]["merged"] == 2


def test_abbreviations_need_word_boundaries():
    """'at least' must not trigger AST/ALT, 'performance' must not trigger ANC."""
    trial = {"nct_id": "NCT1", "min_age": None, "max_age": None, "eligibility_text": "Inclusion Criteria:\n* Life expectancy of at least 90 days\n* Good performance and clearance of prior toxicity"}
    assert not any(c["assessable"] for c in compile_trial(trial))


def test_multi_cohort_lines_go_to_reviewer():
    text = "Inclusion Criteria:\n* Cohort A: KRAS wild-type. Cohort B: KRAS G12C mutation. Cohort C: treatment-naive."
    trial = {"nct_id": "NCT2", "min_age": None, "max_age": None, "eligibility_text": text}
    assert not any(c["assessable"] for c in compile_trial(trial))


def test_creatinine_or_clearance_is_not_both():
    trial = {"nct_id": "NCT3", "min_age": None, "max_age": None, "eligibility_text": "Inclusion Criteria:\n* Creatinine <= ULN or creatinine clearance >= 80 mL/min"}
    assert not any(c["assessable"] and c["fact"] in ("crcl", "creatinine", "creatinine_uln") for c in compile_trial(trial))


@pytest.mark.parametrize("case", json.loads((Path(__file__).with_name("recency_cases.json")).read_text()), ids=lambda c: c["name"])
def test_recency_date_validation(case):
    c = crit("anc", "ge", 1.5, kind=case["kind"], polarity=case.get("polarity", "require"))
    f = fact(case.get("value", 3.0), status=case.get("status", "done"))
    if case.get("omit_date"):
        del f["date"]
    else:
        f["date"] = case["date"]
    result = assess(c, {"anc": f})
    assert result["status"] == case["expected"]
    assert result["evidence"]["source"] == "REAL:test"
    assert result["evidence"]["date"] == f.get("date")
    if case["expected"] == "unknown":
        assert result["reason"] and result["action"]
