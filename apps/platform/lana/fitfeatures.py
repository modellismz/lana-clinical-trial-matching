"""Feature construction for the trial-fit predictor (shared by training and serving)."""
from __future__ import annotations

import re

import numpy as np

FEATURES = ["cos_head", "cos_inc", "cos_exc", "inc_minus_exc", "age_ok", "sex_ok", "token_jaccard", "has_exclusion_text"]
_STOP = set("the a an of and or with in to for is was are were has have had patient year old man woman male female his her he she on at by from as that this it be".split())


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z\-]{3,}", text.lower()) if w not in _STOP}


def parse_age(text: str) -> int | None:
    m = re.search(r"(\d{1,3})[- ]year[- ]old", text, re.I) or re.search(r"\bage[d]? (\d{1,3})\b", text, re.I)
    return int(m.group(1)) if m else None


def parse_sex(text: str) -> str | None:
    low = text.lower()
    male = re.search(r"\b(man|male|boy|gentleman)\b", low)
    female = re.search(r"\b(woman|female|girl|lady)\b", low)
    if male and not female:
        return "MALE"
    if female and not male:
        return "FEMALE"
    return None


def features(q: np.ndarray, head: np.ndarray, inc: np.ndarray, exc: np.ndarray, patient_text: str, trial: dict) -> list[float]:
    c_head, c_inc, c_exc = float(q @ head), float(q @ inc), float(q @ exc)
    age = parse_age(patient_text)
    if age is None:
        age_ok = -1.0
    else:
        lo, hi = trial.get("min_age"), trial.get("max_age")
        age_ok = 0.0 if (lo is not None and age < lo) or (hi is not None and age > hi) else 1.0
    sex = parse_sex(patient_text)
    ts = trial.get("sex")
    sex_ok = -1.0 if sex is None else (0.0 if ts in ("MALE", "FEMALE") and ts != sex else 1.0)
    a, b = _tokens(patient_text), _tokens(" ".join([trial.get("title", ""), " ".join(trial.get("conditions", []))]))
    jac = len(a & b) / max(1, len(a | b))
    return [c_head, c_inc, c_exc, c_inc - c_exc, age_ok, sex_ok, jac, 1.0 if trial.get("exclusion") else 0.0]
