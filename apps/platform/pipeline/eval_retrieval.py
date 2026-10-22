"""Golden-set evaluation of the retrieval stage: patient text -> bge-m3 -> IRIS VECTOR_COSINE -> 40-trial shortlist.

The shortlist is a hard gate: a trial that misses it is never seen by the rules or either model. This
script measures how often the trials that should be in the shortlist actually are, writes the abridged
result for the Evaluation page, and keeps a run log so the page can show the schedule history.

Label layers (each tagged on the page):
    AUTO   trials whose registry title names the patient's actionable biomarker
           (KRAS G12C, BRAF V600E, MSI-H / dMMR, HER2, RAS wild-type). A sanity floor, not a clinical label.
    RULES  full mode only: trials the rule evaluator passes over the WHOLE registry
           (no criterion Not met, >= 1 biomarker criterion Met, coverage >= MIN_COVERAGE).
    HAND   data/golden/retrieval_golden.jsonl, reviewer-labelled pairs. Empty until a clinician fills it.

Modes:
    python pipeline/eval_retrieval.py              full: data/processed + IRIS. recall@10/20/40, MRR, rank in the 700-chunk pool
    python pipeline/eval_retrieval.py --snapshot   web/data only: the top 12 of each exported match. recall@12, hit@12

Output: web/data/evaluation.json, one line appended to data/eval_runs.jsonl.
Exit 1 when recall@40 (full mode) drops by more than GATE against the previous full run.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "data"
PROC = ROOT / "data" / "processed"
GOLDEN = ROOT / "data" / "golden" / "retrieval_golden.jsonl"
RUNS = ROOT / "data" / "eval_runs.jsonl"
MATCH_LOG = ROOT / "data" / "match_log.jsonl"
SCHEDULE = ROOT / "pipeline" / "eval_schedule.json"
WINDOW_DAYS = 7
GATE = 0.05
POOL_CHUNKS = 700
SHORTLIST = 40
TZ = timezone(timedelta(hours=7))  # Asia/Bangkok, no DST

# title patterns that name an actionable biomarker; (subgroup key, label, regex)
AUTO_RULES = [
    ("kras_g12c", "KRAS G12C", re.compile(r"\bG12C\b", re.I)),
    ("braf_v600e", "BRAF V600E", re.compile(r"\bV600E?\b", re.I)),
    ("msi_h", "MSI-H / dMMR", re.compile(r"MSI-?H\b|dMMR|microsatellite instability|mismatch[- ]repair[- ]deficien", re.I)),
    ("her2_amp", "HER2", re.compile(r"\bHER-?2\b|\bERBB2\b", re.I)),
    ("ras_wt", "RAS wild-type", re.compile(r"RAS[- ]?(wild[- ]?type|WT\b)|wild[- ]?type[- ]RAS", re.I)),
]
SUBGROUP_LABEL = {k: v for k, v, _ in AUTO_RULES}
SUBGROUP_LABEL.update({"kras_mut": "KRAS other", "mcrc": "no actionable biomarker"})


def subgroup(facts: dict) -> str:
    done = lambda f: facts[f]["status"] == "done"  # noqa: E731
    if done("kras") and facts["kras"].get("variant") == "G12C":
        return "kras_g12c"
    if done("braf") and facts["braf"].get("variant") == "V600E":
        return "braf_v600e"
    if done("msi") and facts["msi"]["value"] == "msi_high":
        return "msi_h"
    if done("her2") and facts["her2"]["value"] == "amplified":
        return "her2_amp"
    if done("kras") and facts["kras"]["value"] == "mutant":
        return "kras_mut"
    if done("kras") and done("nras") and done("braf") and facts["kras"]["value"] == "wild_type" and facts["nras"]["value"] == "wild_type" and facts["braf"]["value"] == "wild_type":
        return "ras_wt"
    return "mcrc"


def auto_golden(sub: str, titles: dict[str, str]) -> list[str]:
    rx = next((r for k, _, r in AUTO_RULES if k == sub), None)
    return sorted(n for n, t in titles.items() if rx and rx.search(t)) if rx else []


def hand_golden() -> tuple[dict[str, set[str]], dict[str, set[str]], int]:
    must: dict[str, set[str]] = {}
    must_not: dict[str, set[str]] = {}
    n = 0
    if GOLDEN.exists():
        for line in GOLDEN.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            n += 1
            (must if r.get("label", "must_shortlist") == "must_shortlist" else must_not).setdefault(r["patient"], set()).add(r["nct_id"])
    return must, must_not, n


def read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def append_jsonl(p: Path, row: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def q(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    return s[min(len(s) - 1, int(round(p * (len(s) - 1))))]


# ---- per-query scoring ------------------------------------------------------------------------------
def score_query(golden: set[str], ranked: list[str], ks: list[int]) -> dict:
    """ranked: trial ids in retrieval order. recall@k is capped: hits / min(|golden|, k)."""
    pos = {n: i + 1 for i, n in enumerate(ranked)}
    ranks = sorted(pos[n] for n in golden if n in pos)
    out = {"n_golden": len(golden), "first_rank": ranks[0] if ranks else None}
    for k in ks:
        hits = sum(1 for r in ranks if r <= k)
        out[f"recall@{k}"] = round(hits / min(len(golden), k), 3) if golden else None
        out[f"hit@{k}"] = bool(hits) if golden else None
    out["rr"] = round(1 / ranks[0], 3) if ranks else 0.0
    return out


def aggregate(rows: list[dict], ks: list[int]) -> dict:
    scored = [r for r in rows if r["n_golden"]]
    agg = {"n_queries": len(scored), "n_pairs": sum(r["n_golden"] for r in scored)}
    for k in ks:
        agg[f"recall@{k}"] = round(statistics.mean(r[f"recall@{k}"] for r in scored), 3) if scored else None
        agg[f"hit@{k}"] = round(sum(1 for r in scored if r[f"hit@{k}"]) / len(scored), 3) if scored else None
    agg["mrr"] = round(statistics.mean(r["rr"] for r in scored), 3) if scored else None
    fr = [r["first_rank"] for r in scored if r["first_rank"]]
    agg["median_first_rank"] = statistics.median(fr) if fr else None
    return agg


def by_subgroup(rows: list[dict], ks: list[int]) -> list[dict]:
    out = []
    for sub in dict.fromkeys(r["subgroup"] for r in rows):
        grp = [r for r in rows if r["subgroup"] == sub]
        a = aggregate(grp, ks)
        a.update({"subgroup": sub, "label": SUBGROUP_LABEL.get(sub, sub), "n_patients": len(grp)})
        out.append(a)
    return out


# ---- schedules ----------------------------------------------------------------------------------------
def cron_next(expr: str, after: datetime) -> datetime | None:
    """Next firing of a 5-field cron (minute hour dom month dow; '*' or a single number) after `after`."""
    f = expr.split()
    if len(f) != 5:
        return None
    ok = lambda spec, v: spec == "*" or int(spec) == v  # noqa: E731
    t = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    end = t + timedelta(days=400)
    while t < end:
        if ok(f[0], t.minute) and ok(f[1], t.hour) and ok(f[2], t.day) and ok(f[3], t.month) and ok(f[4], t.isoweekday() % 7):
            return t
        t += timedelta(minutes=1)
    return None


def schedules(now: datetime, runs: list[dict], export_ts: str | None) -> list[dict]:
    sch = json.loads(SCHEDULE.read_text())
    out = []
    for job in sch["jobs"]:
        last = None
        if job["log"] == "eval":
            ev = [r for r in runs if r.get("kind") == "eval"]
            last = ev[-1] if ev else None
        elif job["log"] == "export" and export_ts:
            last = {"ts": export_ts, "status": "ok"}
        else:
            hits = [r for r in runs if r.get("kind") == job["log"]]
            last = hits[-1] if hits else None
        nxt = cron_next(job["cron"], now) if job["cron"] else None
        status = "never run" if not last else last.get("status", "ok")
        if last and job["cron"] and nxt:
            due_since = nxt - {"daily": timedelta(days=1), "weekly": timedelta(weeks=1), "monthly": timedelta(days=31)}.get(job["cadence"], timedelta(days=1))
            if datetime.fromisoformat(last["ts"]) < due_since - timedelta(hours=1):
                status = "overdue"
        out.append({**{k: job[k] for k in ("id", "name", "what", "cadence", "cron", "target", "also_on")}, "last_run": last["ts"] if last else None, "last_detail": {k: v for k, v in (last or {}).items() if k not in ("ts", "kind")} if last else None, "next_run": nxt.isoformat(timespec="minutes") if nxt else None, "status": status})
    return out


# ---- matched times --------------------------------------------------------------------------------------
def matched_times(now: datetime, patients: list[dict]) -> tuple[list[dict], str | None]:
    """Every match in the window: the export run (per-patient iris_ms with the match file's time) + live API calls."""
    start = now - timedelta(days=WINDOW_DAYS)
    rows = []
    export_ts = None
    for p in patients:
        f = WEB / "matches" / f"{p['id']}.json"
        if not f.exists():
            continue
        ts = datetime.fromtimestamp(os.stat(f).st_mtime, TZ)
        m = json.loads(f.read_text())
        export_ts = max(export_ts or ts.isoformat(timespec="seconds"), ts.isoformat(timespec="seconds"))
        if ts >= start:
            rows.append({"ts": ts.isoformat(timespec="seconds"), "kind": "export", "patient": p["id"], "ms": m["iris_ms"], "shortlist": m["shortlist_size"], "verdicts": m["all_verdicts"], "top": m["matches"][0]["nct_id"] if m["matches"] else None})
    for r in read_jsonl(MATCH_LOG):
        ts = datetime.fromisoformat(r["ts"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=TZ)
        if ts >= start:
            rows.append({"ts": ts.isoformat(timespec="seconds"), "kind": r.get("kind", "live"), "patient": r["patient"], "ms": r["ms"], "shortlist": r.get("shortlist"), "verdicts": r.get("verdicts"), "top": r.get("top")})
    rows.sort(key=lambda r: r["ts"])
    return rows, export_ts


def summarize_times(rows: list[dict]) -> dict:
    ms = [r["ms"] for r in rows]
    days = {}
    for r in rows:
        d = days.setdefault(r["ts"][:10], [])
        d.append(r["ms"])
    return {
        "n": len(rows), "patients": len({r["patient"] for r in rows}), "runs": len({(r["kind"], r["ts"][:16]) for r in rows}),
        "median_ms": statistics.median(ms) if ms else None, "p95_ms": q(ms, 0.95), "max_ms": max(ms) if ms else None, "min_ms": min(ms) if ms else None,
        "by_kind": {k: sum(1 for r in rows if r["kind"] == k) for k in dict.fromkeys(r["kind"] for r in rows)},
        "by_day": [{"day": d, "n": len(v), "median_ms": statistics.median(v), "max_ms": max(v)} for d, v in sorted(days.items())],
    }


# ---- the two modes --------------------------------------------------------------------------------------
def run_snapshot(patients: list[dict], titles: dict[str, str]) -> tuple[list[dict], list[int], dict]:
    ks = [5, 12]
    must, must_not, _ = hand_golden()
    rows = []
    for p in patients:
        m = json.loads((WEB / "matches" / f"{p['id']}.json").read_text())
        ranked = [x["nct_id"] for x in m["matches"]]
        sub = subgroup(p["facts"])
        auto = set(auto_golden(sub, titles))
        golden = (auto | must.get(p["id"], set())) - must_not.get(p["id"], set())
        s = score_query(golden, ranked, ks)
        sims = {x["nct_id"]: x["retrieval"]["best_sim"] for x in m["matches"]}
        kinds = {x["nct_id"]: x["retrieval"]["best_kind"] for x in m["matches"]}
        rows.append({**s, "patient": p["id"], "subgroup": sub, "layers": {"auto": len(auto), "hand": len(must.get(p["id"], set()))},
                     "hits": [{"nct_id": n, "rank": ranked.index(n) + 1, "sim": sims[n], "kind": kinds[n]} for n in ranked if n in golden],
                     "misses": [{"nct_id": n, "title": titles.get(n, n), "rank": None, "pool": f"outside top {len(ranked)}"} for n in sorted(golden - set(ranked))],
                     "violations": [n for n in ranked if n in must_not.get(p["id"], set())],
                     "ranked_n": len(ranked)})
    config = {"mode": "snapshot", "ranked_depth": 12, "note": "Exported matches keep the top 12 after re-ranking by rules and both models, so this mode scores the final top 12, not the raw shortlist. Run without --snapshot (needs data/processed + IRIS) for the raw 40-trial shortlist and the 700-chunk pool."}
    return rows, ks, config


def run_full(patients: list[dict], titles: dict[str, str]) -> tuple[list[dict], list[int], dict]:
    sys.path.insert(0, str(ROOT))
    from lana import embed  # noqa: E402
    from lana.engine import MIN_COVERAGE, Engine  # noqa: E402
    from lana.evaluator import BIOMARKERS, evaluate_trial  # noqa: E402
    from lana.patient import build_facts, summary_text  # noqa: E402
    from lana import irisdb  # noqa: E402

    ks = [10, 20, SHORTLIST]
    eng = Engine(use_iris=True)
    cohort = {r["id"]: r for r in json.loads((PROC / "cohort.json").read_text())}
    must, must_not, _ = hand_golden()
    embed.encode(["warm up"], max_len=64)
    rows = []
    for p in patients:
        rec = cohort[f"{p['study']}:{p['source_id']}"]
        facts = build_facts(rec)
        text = summary_text(rec, facts)
        qv = embed.encode([text], max_len=256)[0]
        t = time.time()
        hits = irisdb.search(eng.conn, qv, top=POOL_CHUNKS)
        ms = round((time.time() - t) * 1000)
        pool_rank: dict[str, int] = {}
        for h in hits:  # first chunk hit per trial = its rank in the 700-chunk pool
            pool_rank.setdefault(h["trial"], len(pool_rank) + 1)
        short = eng.shortlist(qv, SHORTLIST)
        ranked = [d["trial"] for d in short]
        sub = subgroup(facts)
        auto = set(auto_golden(sub, titles))
        rules = set()
        for nct, crit in eng.criteria.items():
            ev = evaluate_trial(crit, facts)
            if ev["verdict"] != "ready":
                continue
            checked = sum(c.get("merged", 1) for c in ev["criteria"])
            cov = checked / max(1, checked + ev["needs_review"])
            if cov >= MIN_COVERAGE and any(c["status"] == "met" and c["fact"] in BIOMARKERS for c in ev["criteria"]):
                rules.add(nct)
        golden = (auto | rules | must.get(p["id"], set())) - must_not.get(p["id"], set())
        s = score_query(golden, ranked, ks)
        best = {d["trial"]: d["best"] for d in short}
        rows.append({**s, "patient": p["id"], "subgroup": sub, "layers": {"auto": len(auto), "rules": len(rules), "hand": len(must.get(p["id"], set()))},
                     "hits": [{"nct_id": n, "rank": ranked.index(n) + 1, "sim": round(best[n]["sim"], 3), "kind": best[n]["kind"]} for n in ranked if n in golden],
                     "misses": [{"nct_id": n, "title": titles.get(n, n), "rank": pool_rank.get(n), "pool": f"chunk rank {pool_rank[n]}" if n in pool_rank else f"outside top {POOL_CHUNKS} chunks"} for n in sorted(golden - set(ranked))],
                     "violations": [n for n in ranked if n in must_not.get(p["id"], set())],
                     "ranked_n": len(ranked), "iris_ms": ms})
        append_jsonl(MATCH_LOG, {"ts": datetime.now(TZ).isoformat(timespec="seconds"), "kind": "eval", "patient": p["id"], "ms": ms, "shortlist": len(ranked)})
    config = {"mode": "full", "ranked_depth": SHORTLIST, "pool_chunks": POOL_CHUNKS, "note": None}
    return rows, ks, config


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", action="store_true", help="score from web/data only (top 12), no IRIS or model needed")
    a = ap.parse_args()
    now = datetime.now(TZ)
    patients = json.loads((WEB / "patients.json").read_text())
    bench = json.loads((WEB / "benchmarks.json").read_text())
    titles = {t["id"]: t["t"] for t in json.loads((WEB / "trials.json").read_text())["trials"]}
    full = not a.snapshot and (PROC / "cohort.json").exists()
    if not a.snapshot and not full:
        print("data/processed missing: falling back to --snapshot", file=sys.stderr)
    rows, ks, config = run_full(patients, titles) if full else run_snapshot(patients, titles)
    agg = aggregate(rows, ks)
    subs = by_subgroup(rows, ks)
    scored = [r for r in rows if r["n_golden"]]
    hit_kind: dict[str, int] = {}
    for r in scored:
        for h in r["hits"]:
            hit_kind[h["kind"]] = hit_kind.get(h["kind"], 0) + 1
    misses = sorted((dict(m, patient=r["patient"], subgroup=r["subgroup"]) for r in scored for m in r["misses"]), key=lambda m: (m["rank"] is None, m["rank"] or 0))
    _, _, n_hand = hand_golden()
    runs = read_jsonl(RUNS)
    prev = next((r for r in reversed(runs) if r.get("kind") == "eval" and r.get("mode") == config["mode"]), None)
    key = f"recall@{ks[-1]}"
    gate = {"metric": key, "previous": prev[key] if prev else None, "current": agg[key], "threshold": GATE, "status": "ok"}
    if prev and prev.get(key) is not None and agg[key] is not None and prev[key] - agg[key] > GATE:
        gate["status"] = "regressed"
    run = {"ts": now.isoformat(timespec="seconds"), "kind": "eval", "mode": config["mode"], "n_queries": agg["n_queries"], "n_pairs": agg["n_pairs"], **{k: agg[k] for k in agg if k.startswith(("recall", "hit", "mrr"))}, "status": gate["status"]}
    append_jsonl(RUNS, run)
    runs.append(run)
    times, export_ts = matched_times(now, patients)
    out = {
        "generated": now.isoformat(timespec="seconds"),
        "window_days": WINDOW_DAYS,
        "config": {**config, "encoder": bench["trial_fit"].get("encoder", "BAAI/bge-m3"), "dim": 1024, "n_chunks": bench["n_chunks"], "n_trials": bench["n_trials"], "pool_chunks": POOL_CHUNKS, "shortlist": SHORTLIST, "query_max_len": 256, "store": "InterSystems IRIS · VECTOR_COSINE"},
        "golden": {
            "layers": [
                {"id": "AUTO", "name": "Title names the biomarker", "n_pairs": sum(r["layers"].get("auto", 0) for r in rows), "kind": "derived", "note": "KRAS G12C · BRAF V600E · MSI-H/dMMR · HER2 · RAS wild-type in the registry title"},
                {"id": "RULES", "name": "Rules pass over the whole registry", "n_pairs": sum(r["layers"].get("rules", 0) for r in rows), "kind": "derived", "note": "no Not met · ≥1 biomarker Met · coverage ≥ 0.4" + ("" if full else " · full mode only")},
                {"id": "HAND", "name": "Reviewer-labelled", "n_pairs": n_hand, "kind": "labelled", "note": "data/golden/retrieval_golden.jsonl"},
            ],
            "ks": ks, "summary": agg, "by_subgroup": subs, "hit_source": hit_kind,
            "no_reference": [r["patient"] for r in rows if not r["n_golden"]],
            "violations": [{"patient": r["patient"], "nct_id": n} for r in rows for n in r["violations"]],
            "misses": misses[:20], "n_misses": len(misses),
            "per_patient": [{k: r[k] for k in ("patient", "subgroup", "n_golden", "first_rank", "rr", "layers") if k in r} | {k: r[k] for k in r if k.startswith(("recall", "hit"))} | {"n_hits": len(r["hits"]), "n_misses": len(r["misses"])} for r in rows],
        },
        "gate": gate,
        "schedules": schedules(now, runs, export_ts),
        "runs": [r for r in runs if datetime.fromisoformat(r["ts"]) >= now - timedelta(days=WINDOW_DAYS)][-30:],
        "matched": times, "matched_summary": summarize_times(times),
    }
    (WEB / "evaluation.json").write_text(json.dumps(out, ensure_ascii=False, indent=0))
    print(f"[{config['mode']}] {agg['n_queries']} queries · {agg['n_pairs']} golden pairs · " + " · ".join(f"{k} {agg[k]}" for k in agg if k.startswith("recall")) + f" · MRR {agg['mrr']} · gate {gate['status']}", file=sys.stderr)
    if gate["status"] == "regressed":
        sys.exit(1)


if __name__ == "__main__":
    main()
