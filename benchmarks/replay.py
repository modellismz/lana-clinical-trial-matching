"""Replay published frozen predictions and statistics. No model or API access."""
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parent / "results/confirmation-665"
MODELS = ["LANA", "gpt-6-luna", "gpt-5.6-terra"]


def score(matrix):
    n = sum(map(sum, matrix))
    assert n
    f1 = []
    for k in range(3):
        tp = matrix[k][k]
        fp = sum(matrix[j][k] for j in range(3) if j != k)
        fn = sum(matrix[k][j] for j in range(4) if j != k)
        f1.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0)
    tp = matrix[2][2]
    predicted = sum(row[2] for row in matrix)
    eligible = sum(matrix[2])
    noneligible = sum(map(sum, matrix[:2]))
    false_eligible = matrix[0][2] + matrix[1][2]
    return dict(n=n, accuracy=sum(matrix[k][k] for k in range(3)) / n,
                macro_f1=sum(f1) / 3, ineligible_to_eligible=false_eligible,
                excluded_to_eligible=matrix[1][2], invalid_outputs=sum(r[3] for r in matrix),
                eligible_precision=tp / predicted if predicted else 0.0,
                eligible_recall=tp / eligible if eligible else 0.0,
                noneligible_pairs=noneligible, false_eligible_rate=false_eligible / noneligible)


def percentile(values, q):
    ordered = sorted(values)
    index = q * (len(ordered) - 1)
    left = int(index)
    right = min(left + 1, len(ordered) - 1)
    return ordered[left] + (ordered[right] - ordered[left]) * (index - left)


def cluster_bootstrap(rows, key):
    groups = collections.defaultdict(list)
    for row in rows:
        groups[row[key]].append((row["gold"], [row["predictions"][m] for m in MODELS]))
    clusters = sorted(groups)
    rng = random.Random(20261026)
    deltas = {(m, k): [] for m in MODELS[1:] for k in ["accuracy", "macro_f1"]}
    for _ in range(5000):
        matrices = [[[0] * 4 for _ in range(3)] for _ in MODELS]
        for cluster in rng.choices(clusters, k=len(clusters)):
            for gold, predictions in groups[cluster]:
                for i, pred in enumerate(predictions):
                    matrices[i][gold][pred if pred >= 0 else 3] += 1
        scores = [score(m) for m in matrices]
        for i, model in enumerate(MODELS[1:], 1):
            for metric in ["accuracy", "macro_f1"]:
                deltas[model, metric].append(scores[0][metric] - scores[i][metric])
    tail = 0.05 / (2 * 4)
    return [dict(comparator=model, metric=metric,
                 adjusted_ci=[percentile(v, tail), percentile(v, 1 - tail)])
            for (model, metric), v in deltas.items()]


def read(name):
    return json.loads((ROOT / name).read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootstrap", action="store_true", help="Replay both 5,000-resample cluster analyses")
    args = parser.parse_args()
    manifest = read("manifest.json")
    raw = (ROOT / manifest["prediction_file"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == manifest["sha256"], "Prediction file changed"
    rows = [json.loads(line) for line in raw.decode().splitlines()]
    assert len(rows) == len({r["pair_id"] for r in rows}) == 665
    assert len({r["patient_id"] for r in rows}) == 29
    assert len({r["trial_id"] for r in rows}) == 650
    assert len({r["template"] for r in rows}) == 8
    assert collections.Counter(r["gold"] for r in rows) == {0: 232, 1: 201, 2: 232}
    audit = read("audit-summary.json")
    arms = set(audit["analysis"]["scores"])
    assert len(arms) == 6
    for row in rows:
        assert set(row["predictions"]) == arms
        assert all(type(p) is int and p in [-1, 0, 1, 2] for p in row["predictions"].values())
    for arm in sorted(arms):
        matrix = [[0] * 4 for _ in range(3)]
        for row in rows:
            pred = row["predictions"][arm]
            matrix[row["gold"]][pred if pred >= 0 else 3] += 1
        assert matrix == audit["analysis"]["confusion"][arm]
        result = score(matrix)
        for key, value in result.items():
            assert math.isclose(value, audit["analysis"]["scores"][arm][key], rel_tol=0, abs_tol=1e-15)
        print(f"{arm:27} accuracy={result['accuracy']:.8%} macro-F1={result['macro_f1']:.8%} false-eligible={result['ineligible_to_eligible']}/433")
    for arm, value in audit["local_cost"].items():
        cost = value["gpu_energy"]["kwh"] * value["tariff_usd_per_kwh_assumed"] / 665 * 1000
        assert math.isclose(cost, value["usd_per_1000_pair_decisions"], rel_tol=0, abs_tol=1e-14)
    for arm, value in audit["api_cost"].items():
        assert value["all_attempts"] == 665
        cost = value["recorded_estimate_usd"] / 665 * 1000
        assert math.isclose(cost, value["usd_per_1000_pair_decisions"], rel_tol=0, abs_tol=1e-14)
    print("All six matrices, scores and aggregate cost arithmetic match. Cost scopes differ; whole-service OPEX is unmeasured.")
    if args.bootstrap:
        for key, expected_key in [("patient_id", "primary_bootstrap"), ("template", "template_cluster_sensitivity")]:
            actual = cluster_bootstrap(rows, key)
            expected = audit["analysis"][expected_key]["intervals"]
            assert len(actual) == len(expected) == 4
            for a, b in zip(actual, expected):
                assert a["comparator"] == b["comparator"] and a["metric"] == b["metric"]
                assert all(math.isclose(x, y, rel_tol=0, abs_tol=1e-14) for x, y in zip(a["adjusted_ci"], b["adjusted_ci"]))
            print(f"{key}: 5,000 paired resamples and all four adjusted intervals reproduced.")


if __name__ == "__main__":
    main()
