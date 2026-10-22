"""Criteria compiler: registry eligibility text -> structured, checkable criteria.

Rule-based on purpose. The text of every trial line is kept; a line is either compiled into a
structured test over a known patient fact, or marked `assessable: false` and sent to a human
reviewer. Nothing is guessed. In production an LLM would propose compilations and a clinician
would review each trial once; here the rules are the reviewed baseline.

A compiled criterion:
    {id, section, text, assessable, fact, test:{op, value}, polarity, kind, label}
`polarity` is "require" (patient must satisfy the test) or "exclude" (patient must NOT satisfy it).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ---- splitting ------------------------------------------------------------------------------

_BULLET = re.compile(r"^\s*(?:[*\-•·]|\d{1,2}[.)]|[a-z][.)])\s+")
_INCL = re.compile(r"inclusion criteria|key inclusion|main inclusion|eligibility criteria", re.I)
_EXCL = re.compile(r"exclusion criteria|key exclusion|main exclusion", re.I)


def split_criteria(text: str) -> list[tuple[str, str]]:
    """Return [(section, line)] with wrapped lines joined and headings removed."""
    section = "inclusion"
    out: list[tuple[str, str]] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            line = re.sub(r"\s+", " ", " ".join(current)).strip(" -*")
            if len(line) > 6:
                out.append((section, line))
            current.clear()

    for raw in text.replace("\r", "").split("\n"):
        stripped = raw.strip()
        if not stripped:
            flush()
            continue
        head = stripped.rstrip(":").strip()
        if len(head) < 60 and _EXCL.search(head) and not _BULLET.match(stripped):
            flush()
            section = "exclusion"
            continue
        if len(head) < 60 and _INCL.search(head) and not _BULLET.match(stripped):
            flush()
            section = "inclusion"
            continue
        if _BULLET.match(stripped):
            flush()
            current.append(_BULLET.sub("", stripped, count=1))
        else:
            current.append(stripped)
    flush()
    return out


# ---- patterns -------------------------------------------------------------------------------

NUM = r"(\d+(?:[.,]\d+)?)"
GE = r"(?:≥|>=|=>|>|greater than or equal to|greater than|at least|no less than|not less than|above)"
LE = r"(?:≤|<=|=<|<|less than or equal to|less than|no (?:greater|more) than|not (?:greater|more) than|below|within)"


def _f(x: str) -> float:
    return float(x.replace(",", ""))


@dataclass
class C:
    fact: str
    op: str
    value: object
    polarity: str
    kind: str
    label: str


def _ecog(low: str, section: str) -> list[C]:
    if "ecog" not in low and "performance status" not in low and "ps of" not in low:
        return []
    if "karnofsky" in low and "ecog" not in low:
        return []
    m = re.search(r"(?:ecog|performance status|\bps\b)[^0-9]{0,60}?([0-4])\s*(?:-|–|to|or|/)\s*([0-4])", low)
    if m and section == "inclusion":
        hi = max(int(m.group(1)), int(m.group(2)))
        return [C("ecog", "le", hi, "require", "fitness", f"ECOG ≤ {hi}")]
    m = re.search(rf"(?:ecog|performance status|\bps\b)[^0-9]{{0,60}}?{LE}\s*([0-4])", low)
    if m and section == "inclusion":
        return [C("ecog", "le", int(m.group(1)), "require", "fitness", f"ECOG ≤ {m.group(1)}")]
    m = re.search(rf"(?:ecog|performance status|\bps\b)[^0-9]{{0,60}}?{GE}\s*([0-4])", low)
    if m and section == "exclusion":
        return [C("ecog", "ge", int(m.group(1)), "exclude", "fitness", f"ECOG ≥ {m.group(1)}")]
    m = re.search(r"(?:ecog|performance status|\bps\b)[^0-9]{0,40}([0-4])\b", low)
    if m and section == "inclusion":
        return [C("ecog", "le", int(m.group(1)), "require", "fitness", f"ECOG ≤ {m.group(1)}")]
    return []


def _ras_braf(low: str, section: str) -> list[C]:
    out: list[C] = []
    if re.search(r"inhibitor|prior (?:treatment|therapy)|previous(?:ly)? (?:treated|received)|received (?:prior|any)|treated with", low):
        return out
    wt = re.search(r"wild[- ]?type|\bwt\b|without (?:a )?(?:k?ras|braf|nras)[^.;]{0,20}mutation|no (?:k?ras|nras|braf)[^.;]{0,20}mutation", low)
    if wt and re.search(r"\b(?:k?ras|nras|braf)\b", low) and section == "inclusion":
        genes = set()
        if re.search(r"\bkras\b|\bras\b|\brasi\b|ras genes", low):
            genes.add("kras")
        if re.search(r"\bnras\b|\bras\b|ras genes", low):
            genes.add("nras")
        if re.search(r"\bbraf\b", low):
            genes.add("braf")
        for g in sorted(genes):
            out.append(C(g, "eq", "wild_type", "require", "biomarker", f"{g.upper()} wild-type"))
        return out
    m = re.search(r"\bkras\b[^;]{0,30}?(?:p\.)?\b(g12c|g12d|g12v|g12r|g12a|g12s|g13d|q61|a146)", low)
    if m and not re.search(r"wild[- ]?type", low):
        variant = m.group(1).upper()
        pol = "require" if section == "inclusion" else "exclude"
        return [C("kras", "variant", variant, pol, "biomarker", f"KRAS {variant}")]
    m = re.search(r"\bbraf\b[^;]{0,30}?(?:p\.)?\bv600e?\b", low)
    if m and not re.search(r"wild[- ]?type", low):
        pol = "require" if section == "inclusion" else "exclude"
        return [C("braf", "variant", "V600E", pol, "biomarker", "BRAF V600E")]
    if re.search(r"\bkras\b[^.;]{0,25}mutat", low) and not re.search(r"wild", low) and section == "inclusion":
        return [C("kras", "eq", "mutant", "require", "biomarker", "KRAS mutation")]
    return out


def _her2(low: str, section: str) -> list[C]:
    if "her2" not in low and "erbb2" not in low and "her-2" not in low:
        return []
    neg = re.search(r"her-?2[^.;]{0,25}(?:negative|non-amplified|not amplified)|her-?2[- ]negative", low)
    pos = re.search(r"her-?2[^.;]{0,30}(?:positive|amplif|overexpress|3\+)|erbb2[^.;]{0,20}amplif|her-?2[- ]positive", low)
    if pos and not neg:
        pol = "require" if section == "inclusion" else "exclude"
        return [C("her2", "eq", "amplified", pol, "biomarker", "HER2 amplified / positive")]
    if neg and not pos:
        pol = "require" if section == "inclusion" else "exclude"
        return [C("her2", "eq", "not_amplified", pol, "biomarker", "HER2 negative")]
    return []


def _msi(low: str, section: str) -> list[C]:
    high = re.search(r"msi-?h|msi[- ]high|dmmr|mismatch repair[- ]deficien|microsatellite instability[- ]high|microsatellite instab", low)
    stable = re.search(r"\bmss\b|pmmr|microsatellite[- ]stable|mismatch repair[- ]proficient|mmr[- ]proficient", low)
    if high and stable:
        return []
    if high:
        pol = "require" if section == "inclusion" else "exclude"
        if re.search(r"non-?(?:msi|dmmr)|not (?:msi|dmmr)|without (?:msi|dmmr)", low):
            return []
        return [C("msi", "eq", "msi_high", pol, "biomarker", "MSI-H / dMMR")]
    if stable:
        pol = "require" if section == "inclusion" else "exclude"
        return [C("msi", "eq", "mss", pol, "biomarker", "MSS / pMMR")]
    return []


_NUMWORD = {"one": 1, "two": 2, "three": 3, "four": 4, "1": 1, "2": 2, "3": 3, "4": 4}


def _prior_lines(low: str, section: str) -> list[C]:
    if re.search(r"treatment[- ]na[iï]ve|no prior (?:systemic|chemo|anti)|no previous (?:systemic|chemo)|previously untreated|first[- ]line (?:treatment|therapy)[- ]?na|untreated for (?:metastatic|advanced)", low) and section == "inclusion":
        if re.search(r"adjuvant|neoadjuvant|except|other than", low):
            pass
        return [C("prior_lines", "le", 0, "require", "history", "No prior systemic therapy for metastatic disease")]
    m = re.search(r"(?:no more than|not more than|up to|maximum of|≤|<=|at most)\s*(one|two|three|four|[1-4])\s*(?:prior|previous)?\s*(?:lines?|regimens?)", low)
    if m and section == "inclusion":
        n = _NUMWORD[m.group(1)]
        return [C("prior_lines", "le", n, "require", "history", f"≤ {n} prior lines")]
    m = re.search(r"(?:at least|≥|>=|minimum of)\s*(one|two|three|[1-3])\s*(?:prior|previous)\s*(?:lines?|regimens?|systemic)", low)
    if m and section == "inclusion":
        n = _NUMWORD[m.group(1)]
        return [C("prior_lines", "ge", n, "require", "history", f"≥ {n} prior lines")]
    if re.search(r"(?:progress|relaps|refractory|intoleran)[^.;]{0,80}(?:fluoropyrimidine|oxaliplatin|irinotecan|standard (?:therapy|treatment|chemotherapy)|prior (?:line|therapy|treatment))", low) and section == "inclusion":
        return [C("prior_lines", "ge", 1, "require", "history", "≥ 1 prior line of therapy")]
    return []


def _labs(low: str, section: str) -> list[C]:
    out: list[C] = []
    if section != "inclusion":
        return out
    m = re.search(rf"(?:\banc\b|absolute neutrophil(?: count)?|neutrophil count)[^.;\d]{{0,40}}{GE}\s*{NUM}\s*(?:x|×)?\s*(10\s*\^?\s*9|10\*9|10³|10\^3|1,?000)?", low)
    if m:
        v = _f(m.group(1))
        if v >= 100:
            v = v / 1000
        out.append(C("anc", "ge", round(v, 2), "require", "lab", f"ANC ≥ {v:g} ×10⁹/L"))
    m = re.search(rf"platelet(?: count)?s?[^.;\d]{{0,40}}{GE}\s*{NUM}", low)
    if m:
        v = _f(m.group(1))
        if v >= 1000:
            v = v / 1000
        out.append(C("platelets", "ge", round(v, 1), "require", "lab", f"Platelets ≥ {v:g} ×10⁹/L"))
    m = re.search(rf"h(?:a)?emoglobin[^.;\d]{{0,40}}{GE}\s*{NUM}\s*(g/dl|g/l|mmol/l)?", low)
    if m:
        v = _f(m.group(1))
        unit = (m.group(2) or "").lower()
        if unit == "g/l" or v > 40:
            v = v / 10
        out.append(C("hemoglobin", "ge", round(v, 1), "require", "lab", f"Hemoglobin ≥ {v:g} g/dL"))
    either_or = re.search(r"creatinine[^.;]{0,70}\bor\b[^.;]{0,50}(?:clearance|\bcrcl\b|\begfr\b)|(?:clearance|\bcrcl\b|\begfr\b)[^.;]{0,70}\bor\b[^.;]{0,50}creatinine", low)
    m = None if either_or else re.search(rf"(?:creatinine clearance|\bcrcl\b|\begfr\b|glomerular filtration)[^.;\d]{{0,60}}{GE}\s*{NUM}", low)
    if either_or:
        pass
    elif m:
        v = _f(m.group(1))
        out.append(C("crcl", "ge", v, "require", "lab", f"Creatinine clearance ≥ {v:g} mL/min"))
    else:
        m = re.search(rf"serum creatinine[^.;\d]{{0,40}}{LE}\s*{NUM}\s*(?:x|×)?\s*(uln|mg/dl|upper)?", low)
        if m:
            v = _f(m.group(1))
            unit = (m.group(2) or "").lower()
            if unit in ("uln", "upper"):
                out.append(C("creatinine_uln", "le", v, "require", "lab", f"Creatinine ≤ {v:g} × ULN"))
            else:
                out.append(C("creatinine", "le", v, "require", "lab", f"Creatinine ≤ {v:g} mg/dL"))
    m = re.search(rf"(?:total )?bilirubin[^.;\d]{{0,40}}{LE}\s*{NUM}\s*(?:x|×)?\s*(uln|mg/dl|upper)?", low)
    if m:
        v = _f(m.group(1))
        unit = (m.group(2) or "").lower()
        if unit == "mg/dl":
            out.append(C("bilirubin", "le", v, "require", "lab", f"Bilirubin ≤ {v:g} mg/dL"))
        else:
            out.append(C("bilirubin_uln", "le", v, "require", "lab", f"Bilirubin ≤ {v:g} × ULN"))
    m = re.search(rf"(?:\bast\b|\balt\b|\bsgot\b|\bsgpt\b|aspartate|alanine)[^.;\d]{{0,60}}{LE}\s*{NUM}\s*(?:x|×)?\s*(?:uln|upper)", low)
    if m:
        v = _f(m.group(1))
        out.append(C("transaminase_uln", "le", v, "require", "lab", f"AST/ALT ≤ {v:g} × ULN"))
    return out


def _other(low: str, section: str) -> list[C]:
    out: list[C] = []
    if re.search(r"measurable disease|measurable lesion|recist", low) and section == "inclusion":
        out.append(C("measurable", "eq", True, "require", "imaging", "Measurable disease (RECIST 1.1)"))
    if re.search(r"brain metast|cns metast|central nervous system metast|leptomeningeal", low):
        if section == "exclusion" or re.search(r"no (?:known )?(?:active )?(?:brain|cns)|without (?:brain|cns)", low):
            out.append(C("brain_mets", "eq", True, "exclude", "imaging", "Active brain metastases"))
    allow = re.search(r"allowed|permitted|eligible|may be enrolled|acceptable|provided|undetectable|< ?1,?000|<\s*lower limit|stable", low)
    if re.search(r"\bhiv\b|human immunodeficiency", low) and section == "exclusion" and not allow:
        out.append(C("hiv", "eq", "positive", "exclude", "infection", "HIV infection"))
    if re.search(r"hepatitis b|\bhbv\b|\bhbsag\b", low) and section == "exclusion" and not allow:
        out.append(C("hbv", "eq", "positive", "exclude", "infection", "Active hepatitis B"))
    if re.search(r"hepatitis c|\bhcv\b", low) and section == "exclusion" and not allow:
        out.append(C("hcv", "eq", "positive", "exclude", "infection", "Active hepatitis C"))
    if re.search(r"informed consent", low) and section == "inclusion":
        out.append(C("consent", "eq", True, "require", "admin", "Written informed consent"))
    if re.search(r"(?:metastatic|unresectable|stage iv|advanced)[^.;]{0,60}(?:colorectal|colon|rectal|adenocarcinoma)|(?:colorectal|colon|rectal|adenocarcinoma)[^.;]{0,60}(?:metastatic|unresectable|stage iv|advanced)", low) and section == "inclusion":
        out.append(C("stage_iv", "eq", True, "require", "diagnosis", "Metastatic / unresectable disease"))
    m = re.search(rf"(?:age|aged|years of age|≥\s*18)[^.;\d]{{0,30}}{GE}\s*(\d{{2}})", low)
    if m and section == "inclusion":
        out.append(C("age", "ge", int(m.group(1)), "require", "demographic", f"Age ≥ {m.group(1)}"))
    return out


EXTRACTORS = [_ecog, _ras_braf, _her2, _msi, _prior_lines, _labs, _other]


def compile_trial(trial: dict) -> list[dict]:
    """Compile one registry record into a list of criteria dicts."""
    nct = trial["nct_id"]
    out: list[dict] = []
    n = 0
    if trial.get("min_age"):
        out.append(_mk(nct, n, "inclusion", f"Minimum age {trial['min_age']} (registry field)", C("age", "ge", trial["min_age"], "require", "demographic", f"Age ≥ {trial['min_age']}")))
        n += 1
    if trial.get("max_age"):
        out.append(_mk(nct, n, "inclusion", f"Maximum age {trial['max_age']} (registry field)", C("age", "le", trial["max_age"], "require", "demographic", f"Age ≤ {trial['max_age']}")))
        n += 1
    for section, line in split_criteria(trial["eligibility_text"]):
        low = line.lower().replace("\\~", "-").replace("~", "-").replace("\\", "")
        found: list[C] = []
        # a line that describes several cohorts at once cannot be turned into one test: leave it to a reviewer
        multi_cohort = len(re.findall(r"cohort|\bpart [a-d1-3]\b|\barm [a-d1-3]\b", low)) >= 2 or len(line) > 700
        for ex in ([] if multi_cohort else EXTRACTORS):
            found.extend(ex(low, section))
        # keep one criterion per (fact, test) per line
        seen = set()
        uniq = []
        for c in found:
            key = (c.fact, c.op, str(c.value), c.polarity)
            if key not in seen:
                seen.add(key)
                uniq.append(c)
        if not uniq:
            out.append(
                {
                    "id": f"{nct}:{n}",
                    "section": section,
                    "text": line[:500],
                    "assessable": False,
                    "fact": None,
                    "test": None,
                    "polarity": None,
                    "kind": "other",
                    "label": None,
                }
            )
            n += 1
            continue
        for c in uniq:
            out.append(_mk(nct, n, section, line[:500], c))
            n += 1
    return out


def _mk(nct: str, n: int, section: str, text: str, c: C) -> dict:
    polarity = c.polarity
    return {
        "id": f"{nct}:{n}",
        "section": section,
        "text": text,
        "assessable": True,
        "fact": c.fact,
        "test": {"op": c.op, "value": c.value},
        "polarity": polarity,
        "kind": c.kind,
        "label": c.label,
    }
