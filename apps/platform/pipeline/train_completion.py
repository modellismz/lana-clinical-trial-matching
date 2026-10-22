"""Train and cross-validate the biomarker completion models on real colorectal cohorts.

Each model predicts one biomarker (positive result) from the others plus side, sex, age, TMB, stage
and ancestry. Random masking of the other biomarkers during training teaches it to cope with
missing inputs, as in a real record. Reported: 5-fold cross-validated AUROC, average precision, Brier
score, versus the prevalence baseline.
Output: data/models/completion_<target>.joblib, models/completion_metrics.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lana.completion import COLS, POSITIVE, TARGETS, matrix, row_from_record  # noqa: E402

PROC = ROOT / "data" / "processed"
MODELS = ROOT / "data" / "models"
MODELS.mkdir(parents=True, exist_ok=True)
(ROOT / "models").mkdir(exist_ok=True)
BIO = ["kras", "nras", "braf", "her2", "msi", "pik3ca"]


def mask_augment(X: np.ndarray, cols: list[str], rng: np.random.Generator, p: float = 0.3) -> np.ndarray:
    X = X.copy()
    for c in BIO:
        if c in cols:
            j = cols.index(c)
            X[rng.random(len(X)) < p, j] = np.nan
    return X


def main() -> None:
    cohort = json.loads((PROC / "cohort.json").read_text())
    rows = [row_from_record(r) for r in cohort]
    rng = np.random.default_rng(7)
    metrics = {"data": f"{len(cohort)} real colorectal patients from cBioPortal (MSK 2017/2026, SYSUCC 2022, TCGA)", "folds": 5, "targets": {}}
    for tgt in TARGETS:
        cols = [c for c in COLS if c != tgt]
        X = matrix(rows, drop=tgt)
        y_all = np.array([r[tgt] for r in rows])
        ok = ~np.isnan(y_all)
        Xk, yk = X[ok], y_all[ok].astype(int)
        oof = np.zeros(len(yk))
        for tr, te in StratifiedKFold(5, shuffle=True, random_state=7).split(Xk, yk):
            m = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.06, max_iter=200, l2_regularization=1.0, random_state=7)
            m.fit(mask_augment(Xk[tr], cols, rng), yk[tr])
            oof[te] = m.predict_proba(Xk[te])[:, 1]
        prev = float(yk.mean())
        # evaluate also with the other biomarkers masked, the worst case a coordinator faces
        metrics["targets"][tgt] = {
            "positive_class": POSITIVE[tgt],
            "n": int(len(yk)),
            "prevalence": round(prev, 4),
            "auroc": round(float(roc_auc_score(yk, oof)), 3),
            "average_precision": round(float(average_precision_score(yk, oof)), 3),
            "brier": round(float(brier_score_loss(yk, oof)), 4),
            "brier_prevalence_baseline": round(float(brier_score_loss(yk, np.full(len(yk), prev))), 4),
        }
        final = CalibratedClassifierCV(HistGradientBoostingClassifier(max_depth=3, learning_rate=0.06, max_iter=200, l2_regularization=1.0, random_state=7), method="isotonic", cv=3)
        final.fit(mask_augment(Xk, cols, rng), yk)
        joblib.dump({"model": final, "cols": cols}, MODELS / f"completion_{tgt}.joblib")
        print(tgt, metrics["targets"][tgt])
    # empirical KRAS variant shares among KRAS-mutant patients (for "KRAS G12C"-type criteria)
    from collections import Counter

    kv = Counter(r["biomarkers"]["KRAS"]["variant"] for r in cohort if r["biomarkers"]["KRAS"]["result"] == "mutant")
    tot = sum(kv.values())
    metrics["kras_variant_share"] = {k: round(v / tot, 4) for k, v in kv.most_common(12)}
    metrics["limitations"] = [
        "Cohorts are US (MSK, TCGA) and Chinese (SYSUCC); no Thai patients are included.",
        "Predicts a likely result; it is not a substitute for the test. The platform still marks the criterion Unknown.",
        "Cross-validation is internal; no external validation cohort.",
    ]
    (ROOT / "models" / "completion_metrics.json").write_text(json.dumps(metrics, indent=1))


if __name__ == "__main__":
    main()
