"""The Lana engine: retrieve (IRIS Vector Search) -> evaluate (rules) -> predict (two models).

    patient facts --embed--> IRIS VECTOR_COSINE --> shortlist
    shortlist x rule evaluator --> Met / Not met / Unknown per criterion
    + trial-fit predictor (trained on TREC)  + biomarker completion models (trained on real cohorts)
    --> ranked Trial Matches with the next test to order

Nothing in this file decides eligibility with a model: the evaluator does; models only rank and
estimate how likely an Unknown is to resolve in the patient's favour.
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np

from . import completion, embed, irisdb
from .evaluator import BIOMARKERS, LABELS, evaluate_trial, next_tests
from .fitfeatures import features
from .patient import build_facts, summary_text

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
MODELS = ROOT / "data" / "models"
MIN_COVERAGE = 0.4  # share of protocol lines the rules must check before a trial can be "ready"


class Engine:
    def __init__(self, use_iris: bool = True):
        self.trials = {t["nct_id"]: t for t in json.loads((PROC / "trials_raw.json").read_text())}
        self.criteria = json.loads((PROC / "criteria_compiled.json").read_text())
        seg = np.load(PROC / "trial_segments.npz")
        self.seg_index = {n: i for i, n in enumerate(seg["ids"])}
        self.seg_head, self.seg_inc, self.seg_exc = seg["head"], seg["inc"], seg["exc"]
        self.fit = joblib.load(MODELS / "trial_fit.joblib")
        self.completion = {t: joblib.load(MODELS / f"completion_{t}.joblib") for t in completion.TARGETS}
        self.metrics_completion = json.loads((ROOT / "models" / "completion_metrics.json").read_text())
        self.kras_share = self.metrics_completion["kras_variant_share"]
        self.conn = irisdb.connect() if use_iris else None
        self._chunks = None
        self._chunk_vecs = None
        self.rng = np.random.default_rng(11)

    # ---- retrieval ---------------------------------------------------------------------------
    def shortlist(self, query_vec: np.ndarray, n: int = 40) -> list[dict]:
        if self.conn is not None:
            hits = irisdb.search(self.conn, query_vec, top=700)
        else:  # fallback used only when Docker is unavailable
            if self._chunks is None:
                self._chunks = json.loads((PROC / "chunks.json").read_text())
                self._chunk_vecs = np.load(PROC / "chunk_vectors.npy")
            sims = self._chunk_vecs @ query_vec
            idx = np.argsort(-sims)[:700]
            hits = [{"trial": self._chunks[i]["trial"], "kind": self._chunks[i]["kind"], "ref": self._chunks[i]["ref"], "text": self._chunks[i]["text"], "sim": float(sims[i])} for i in idx]
        by: dict[str, dict] = {}
        for h in hits:
            d = by.setdefault(h["trial"], {"trial": h["trial"], "best": h, "n_hits": 0, "top": []})
            d["n_hits"] += 1
            if len(d["top"]) < 3:
                d["top"].append(h)
        scored = sorted(by.values(), key=lambda d: -(d["best"]["sim"] + 0.01 * min(d["n_hits"], 10)))
        return scored[:n]

    # ---- completion model --------------------------------------------------------------------
    def _predict_target(self, target: str, X_rows: np.ndarray) -> np.ndarray:
        m = self.completion[target]
        cols = m["cols"]
        full = [c for c in completion.COLS]
        idx = [full.index(c) for c in cols]
        return m["model"].predict_proba(X_rows[:, idx])[:, 1]

    def pass_probability(self, rows: list[dict], facts: dict, rec: dict, n: int = 400) -> dict:
        """P(every unknown biomarker criterion is satisfied), by chained sampling from the completion models."""
        unknown = [r for r in rows if r["status"] == "unknown" and r["fact"] in BIOMARKERS]
        if any(r["status"] == "not_met" for r in rows):
            return {"p": 0.0, "modelled": [], "operational_unknown": sum(1 for r in rows if r["status"] == "unknown" and r["fact"] not in BIOMARKERS)}
        ops = sum(1 for r in rows if r["status"] == "unknown" and r["fact"] not in BIOMARKERS)
        if not unknown:
            return {"p": 1.0, "modelled": [], "operational_unknown": ops}
        base = completion.row_from_facts(facts, rec)
        X = np.tile(np.array([base[c] for c in completion.COLS], dtype="float64"), (n, 1))
        key = {"msi": "msi", "her2": "her2", "kras": "kras", "nras": "nras", "braf": "braf"}
        order = sorted({r["fact"] for r in unknown})
        samples: dict[str, np.ndarray] = {}
        for tgt in order:
            p = self._predict_target(key[tgt], X)
            draw = (self.rng.random(n) < p).astype(float)
            samples[tgt] = draw
            X[:, completion.COLS.index(key[tgt])] = draw
        ok = np.ones(n, dtype=bool)
        modelled = []
        for r in unknown:
            t, f = r["test"], r["fact"]
            pos = samples[f]  # 1 = positive class (mutant / amplified / msi_high)
            want_pos = {("msi", "msi_high"): True, ("msi", "mss"): False, ("her2", "amplified"): True, ("her2", "not_amplified"): False,
                        ("kras", "mutant"): True, ("kras", "wild_type"): False, ("nras", "wild_type"): False, ("nras", "mutant"): True,
                        ("braf", "wild_type"): False}.get((f, t["value"]))
            if t["op"] == "variant":
                share = 1.0 if f == "braf" else self.kras_share.get(t["value"], 0.05)
                cond = (pos == 1) & (self.rng.random(n) < share)
            elif want_pos is None:
                cond = np.ones(n, dtype=bool)
            else:
                cond = (pos == 1) if want_pos else (pos == 0)
            sat = cond if r["polarity"] == "require" else ~cond
            ok &= sat
            modelled.append({"criterion": r["id"], "fact": f, "p_satisfied": round(float(sat.mean()), 3)})
        return {"p": round(float(ok.mean()), 3), "modelled": modelled, "operational_unknown": ops}

    # ---- trial-fit ---------------------------------------------------------------------------
    def fit_prob(self, q: np.ndarray, patient_text: str, nct: str) -> float:
        i = self.seg_index[nct]
        t = self.trials[nct]
        meta = {"min_age": t["min_age"], "max_age": t["max_age"], "sex": t["sex"], "title": t["title"], "conditions": t["conditions"], "exclusion": True}
        x = np.array([features(q, self.seg_head[i], self.seg_inc[i], self.seg_exc[i], patient_text, meta)], dtype="float32")
        return float(self.fit.predict_proba(x)[0, 1])

    # ---- the match ---------------------------------------------------------------------------
    def match(self, rec: dict, facts: dict | None = None, top: int = 12, shortlist_n: int = 40) -> dict:
        facts = facts or build_facts(rec)
        text = summary_text(rec, facts)
        q_short = embed.encode([text], max_len=256)[0]
        q_long = embed.encode([text], max_len=512)[0]
        short = self.shortlist(q_short, shortlist_n)
        results = []
        for d in short:
            nct = d["trial"]
            ev = evaluate_trial(self.criteria[nct], facts)
            pp = self.pass_probability(ev["criteria"], facts, rec)
            fit = self.fit_prob(q_long, text, nct)
            checked = sum(c.get("merged", 1) for c in ev["criteria"])
            coverage = checked / max(1, checked + ev["needs_review"])
            # a trial whose protocol is mostly unchecked is not "ready": a reviewer still has most of it to read
            verdict = "provisional" if ev["verdict"] == "ready" and coverage < MIN_COVERAGE else ev["verdict"]
            t = self.trials[nct]
            results.append(
                {
                    "nct_id": nct,
                    "title": t["title"],
                    "phase": t["phase"],
                    "sponsor": t["sponsor"],
                    "status": t["status"],
                    "n_sites": t["n_sites"],
                    "thai_sites": t["thai_sites"],
                    "interventions": t["interventions"][:4],
                    "url": t["url"],
                    "retrieval": {"best_sim": round(d["best"]["sim"], 4), "best_text": d["best"]["text"][:240], "best_kind": d["best"]["kind"], "n_hits": d["n_hits"]},
                    "verdict": verdict,
                    "coverage": round(coverage, 3),
                    "counts": ev["counts"],
                    "needs_review": ev["needs_review"],
                    "criteria": [
                        {k: c[k] for k in ("id", "section", "text", "fact", "label", "status", "reason", "action", "evidence", "polarity", "test", "kind", "merged")}
                        for c in ev["criteria"]
                    ],
                    "next_tests": next_tests(ev["criteria"]),
                    "fit": round(fit, 3),
                    "pass": pp,
                    "score": round(fit * pp["p"] * (0.4 + 0.6 * coverage), 4),
                }
            )
        results.sort(key=lambda r: (-r["score"], -r["fit"]))
        # next best test across the non-blocked shortlist
        agg: dict[str, dict] = {}
        for r in results:
            if r["verdict"] == "blocked":
                continue
            for nt in r["next_tests"]:
                a = agg.setdefault(nt["fact"], {"fact": nt["fact"], "label": nt["label"], "action": nt["action"], "trials": []})
                a["trials"].append(r["nct_id"])
        for a in agg.values():
            a["group"] = "biomarker" if a["fact"] in BIOMARKERS else "record"
        tests = sorted(agg.values(), key=lambda a: (a["group"] != "biomarker", -len(a["trials"])))
        return {
            "patient_text": text,
            "query_sim_floor": 0.0,
            "shortlist_size": len(short),
            "matches": results[:top],
            "all_verdicts": {v: sum(1 for r in results if r["verdict"] == v) for v in ("ready", "provisional", "blocked")},
            "next_best_tests": tests[:6],
            "query_vector_head": [round(float(x), 4) for x in q_short[:8]],
        }
