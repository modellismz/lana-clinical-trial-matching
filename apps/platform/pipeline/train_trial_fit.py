"""Train and evaluate the trial-fit predictor on TREC Clinical Trials (train 2021, test 2022).

Question the model answers: given a patient description and a trial, is the patient ELIGIBLE?
Labels are TREC assessor judgments (2 eligible, 1 excluded, 0 not relevant). Features come from the
bge-m3 embeddings (patient vs trial head / inclusion / exclusion text) plus age and sex checks.

Evaluation uses topics the model never saw (2022). The sampled pool is balanced (<=15 pairs per
label per topic), so metrics describe ranking inside that pool, not full-collection retrieval.
Output: data/models/trial_fit.joblib, models/trial_fit_metrics.json (small, committed)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lana.embed import encode  # noqa: E402
from lana.fitfeatures import FEATURES, features  # noqa: E402

PROC = ROOT / "data" / "processed"
MODELS = ROOT / "data" / "models"
MODELS.mkdir(parents=True, exist_ok=True)
(ROOT / "models").mkdir(exist_ok=True)


def ndcg_at(scores: np.ndarray, gains: np.ndarray, k: int = 10) -> float:
    order = np.argsort(-scores)[:k]
    dcg = sum((2 ** gains[i] - 1) / np.log2(r + 2) for r, i in enumerate(order))
    ideal = np.sort(gains)[::-1][:k]
    idcg = sum((2 ** g - 1) / np.log2(r + 2) for r, g in enumerate(ideal))
    return dcg / idcg if idcg > 0 else float("nan")


def prec_at(scores: np.ndarray, rel: np.ndarray, k: int = 10) -> float:
    order = np.argsort(-scores)[:k]
    return float(rel[order].mean())


def main() -> None:
    data = json.loads((PROC / "trec_pairs.json").read_text())
    pairs, trials = data["pairs"], data["trials"]
    cache = PROC / "trec_embeddings.npz"
    topic_ids = sorted({p["topic"] for p in pairs})
    nct_ids = sorted(trials)
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        E_topic, E_head, E_inc, E_exc = z["topic"], z["head"], z["inc"], z["exc"]
    else:
        topic_text = {p["topic"]: p["topic_text"] for p in pairs}
        print("embedding topics", file=sys.stderr)
        E_topic = encode([topic_text[t] for t in topic_ids], max_len=512, batch_size=8)
        heads = [f"{trials[n]['title']}. Conditions: {', '.join(trials[n]['conditions'])}. {trials[n]['summary'][:900]}" for n in nct_ids]
        print("embedding trial heads", file=sys.stderr)
        E_head = encode(heads, max_len=256)
        print("embedding inclusion", file=sys.stderr)
        E_inc = encode([trials[n]["inclusion"][:2500] or trials[n]["title"] for n in nct_ids], max_len=320)
        print("embedding exclusion", file=sys.stderr)
        E_exc = encode([trials[n]["exclusion"][:2500] or "No exclusion criteria listed." for n in nct_ids], max_len=320)
        np.savez(cache, topic=E_topic, head=E_head, inc=E_inc, exc=E_exc)
    ti = {t: i for i, t in enumerate(topic_ids)}
    ni = {n: i for i, n in enumerate(nct_ids)}

    X, y, rel, gain, topic, split = [], [], [], [], [], []
    for p in pairs:
        t, n = ti[p["topic"]], ni[p["nct_id"]]
        X.append(features(E_topic[t], E_head[n], E_inc[n], E_exc[n], p["topic_text"], trials[p["nct_id"]]))
        y.append(1 if p["label"] == 2 else 0)
        rel.append(1 if p["label"] >= 1 else 0)
        gain.append(p["label"])
        topic.append(p["topic"])
        split.append(p["split"])
    X, y, rel, gain = np.array(X, dtype="float32"), np.array(y), np.array(rel), np.array(gain)
    topic, split = np.array(topic), np.array(split)
    tr, te = split == "train", split == "test"
    print(f"train {tr.sum()} pairs / {len(set(topic[tr]))} topics; test {te.sum()} pairs / {len(set(topic[te]))} topics", file=sys.stderr)

    model = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.06, max_iter=250, l2_regularization=1.0, random_state=7)
    model.fit(X[tr], y[tr])
    p_te = model.predict_proba(X[te])[:, 1]

    def per_topic(scores: np.ndarray) -> dict:
        nd, pr = [], []
        for t in sorted(set(topic[te])):
            m = topic[te] == t
            if gain[te][m].max() == 0:
                continue
            nd.append(ndcg_at(scores[m], gain[te][m]))
            pr.append(prec_at(scores[m], (gain[te][m] == 2).astype(int)))
        return {"ndcg@10": round(float(np.nanmean(nd)), 3), "p@10_eligible": round(float(np.mean(pr)), 3)}

    cos_head = X[te][:, FEATURES.index("cos_head")]
    cos_inc = X[te][:, FEATURES.index("cos_inc")]
    result = {
        "task": "Is the patient ELIGIBLE for the trial? (TREC label 2 vs 0/1)",
        "data": "TREC Clinical Trials, patient topics + assessor judgments; train 2021, test 2022 (different topics)",
        "pool": "Sampled, <=15 pairs per label per topic. Metrics describe ranking within this balanced pool.",
        "encoder": "BAAI/bge-m3 (1024-d, multilingual)",
        "model": "HistGradientBoosting, 8 features",
        "n_train_pairs": int(tr.sum()),
        "n_test_pairs": int(te.sum()),
        "n_train_topics": int(len(set(topic[tr]))),
        "n_test_topics": int(len(set(topic[te]))),
        "auroc_eligible": round(float(roc_auc_score(y[te], p_te)), 3),
        "average_precision_eligible": round(float(average_precision_score(y[te], p_te)), 3),
        "auroc_relevant": round(float(roc_auc_score(rel[te], p_te)), 3),
        "ranking": per_topic(p_te),
        "baselines": {
            "cosine(topic, trial head)": {"auroc_eligible": round(float(roc_auc_score(y[te], cos_head)), 3), **per_topic(cos_head)},
            "cosine(topic, inclusion text)": {"auroc_eligible": round(float(roc_auc_score(y[te], cos_inc)), 3), **per_topic(cos_inc)},
            "random": {"auroc_eligible": 0.5},
        },
        "features": FEATURES,
        "limitations": [
            "All-disease benchmark (not colorectal-specific, not Thai).",
            "Trial text is the current registry version, not the 2021 snapshot the assessors saw.",
            "Scores are not calibrated probabilities.",
            "TREC patients are synthetic case descriptions.",
        ],
    }
    # cross-check on colorectal-related test topics
    print(json.dumps(result, indent=1))
    joblib.dump(model, MODELS / "trial_fit.joblib")
    (ROOT / "models" / "trial_fit_metrics.json").write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
