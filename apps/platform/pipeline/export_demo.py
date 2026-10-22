"""Run the engine for the demo patients and export everything the web app shows.

Output (web/data/): patients.json, matches/<id>.json, trials.json (map), benchmarks.json
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lana import embed  # noqa: E402
from lana.engine import Engine  # noqa: E402
from lana.patient import REF_DATE, build_facts, summary_segments  # noqa: E402

PROC = ROOT / "data" / "processed"
WEB = ROOT / "web" / "data"
(WEB / "matches").mkdir(parents=True, exist_ok=True)
MATCH_LOG = ROOT / "data" / "match_log.jsonl"  # per-patient match times, read by pipeline/eval_retrieval.py
TZ = timezone(timedelta(hours=7))

STUDY_URL = {
    "crc_msk_2017": "https://www.cbioportal.org/study/summary?id=crc_msk_2017",
    "crc_msk_2026": "https://www.cbioportal.org/study/summary?id=crc_msk_2026",
    "crc_sysucc_2022": "https://www.cbioportal.org/study/summary?id=crc_sysucc_2022",
    "coadread_tcga_pan_can_atlas_2018": "https://www.cbioportal.org/study/summary?id=coadread_tcga_pan_can_atlas_2018",
}
STUDY_SHORT = {"crc_msk_2017": "MSK-17", "crc_msk_2026": "MSK-26", "crc_sysucc_2022": "SYSUCC", "coadread_tcga_pan_can_atlas_2018": "TCGA"}


def pseudo(pid: str) -> str:
    h = hashlib.sha256(("lana:" + pid).encode()).hexdigest()
    return "LN-" + h[:4].upper()


def choose(cohort: list[dict]) -> list[dict]:
    rnd = random.Random(2026)
    pool = [r for r in cohort if r["stage_iv"]]
    taken: set[str] = set()

    def pick(pred, n, need_age=True):
        c = [r for r in pool if pred(r) and r["id"] not in taken and (r["age"] is not None or not need_age)]
        rnd.shuffle(c)
        out = c[:n]
        taken.update(r["id"] for r in out)
        return out

    bm = lambda r, g: r["biomarkers"][g]  # noqa: E731
    out = []
    out += pick(lambda r: bm(r, "KRAS").get("variant") == "G12C", 3)
    out += pick(lambda r: bm(r, "BRAF").get("variant") == "V600E", 3)
    out += pick(lambda r: bm(r, "MSI")["result"] == "msi_high", 3)
    out += pick(lambda r: bm(r, "ERBB2")["result"] == "amplified", 3)
    out += pick(lambda r: bm(r, "KRAS")["result"] == "wild_type" and bm(r, "NRAS")["result"] == "wild_type" and bm(r, "BRAF")["result"] == "wild_type" and bm(r, "MSI")["result"] == "mss" and r["side"] == "left", 4)
    out += pick(lambda r: bm(r, "MSI")["status"] == "not_done" and r["study"] == "crc_msk_2017", 4)
    out += pick(lambda r: bm(r, "MSI")["status"] in ("failed", "insufficient"), 3, need_age=False)
    out += pick(lambda r: r["study"] == "crc_sysucc_2022", 6)
    out += pick(lambda r: r["study"] == "coadread_tcga_pan_can_atlas_2018", 3)
    out += pick(lambda r: r["study"] == "crc_msk_2017", 4)
    return out


def main() -> None:
    cohort = json.loads((PROC / "cohort.json").read_text())
    demo = choose(cohort)
    print(f"{len(demo)} demo patients", file=sys.stderr)
    engine = Engine(use_iris=True)

    embed.encode(["warm up"], max_len=64)  # load the model before timing anything
    embed.encode(["warm up " * 100], max_len=512)
    engine.match(demo[0], build_facts(demo[0]))
    patients, query_vecs = [], []
    t0 = time.time()
    for k, rec in enumerate(demo):
        facts = build_facts(rec)
        t = time.time()
        res = engine.match(rec, facts)
        res["iris_ms"] = round((time.time() - t) * 1000)
        pid = pseudo(rec["id"])
        res["patient_id"] = pid
        (WEB / "matches" / f"{pid}.json").write_text(json.dumps(res, ensure_ascii=False))
        with MATCH_LOG.open("a") as lf:
            lf.write(json.dumps({"ts": datetime.now(TZ).isoformat(timespec="seconds"), "kind": "export", "patient": pid, "ms": res["iris_ms"], "shortlist": res["shortlist_size"], "verdicts": res["all_verdicts"], "top": res["matches"][0]["nct_id"] if res["matches"] else None}) + "\n")
        qv = embed.encode([res["patient_text"]], max_len=256)[0]
        query_vecs.append(qv)
        real = sum(1 for f in facts.values() if str(f["source"]).startswith("REAL"))
        sim = sum(1 for f in facts.values() if f["source"] == "SIM")
        missing = sum(1 for f in facts.values() if f["status"] != "done")
        patients.append(
            {
                "id": pid,
                "source_id": rec["patient_id"],
                "sample_id": rec["sample_id"],
                "study": rec["study"],
                "study_short": STUDY_SHORT[rec["study"]],
                "study_label": rec["study_label"],
                "study_url": STUDY_URL[rec["study"]],
                "panel": rec["panel"],
                "age": rec["age"],
                "sex": rec["sex"],
                "race": rec["race"],
                "side": rec["side"],
                "stage_raw": rec["stage_raw"],
                "metastasis_sites": rec["metastasis_sites"],
                "summary": res["patient_text"],
                "summary_segments": summary_segments(rec, facts),
                "facts": facts,
                "counts": {"real": real, "sim": sim, "missing": missing, "facts": len(facts)},
                "verdicts": res["all_verdicts"],
                "top": [{"nct_id": m["nct_id"], "score": m["score"], "verdict": m["verdict"]} for m in res["matches"][:3]],
            }
        )
        print(f"  {k+1}/{len(demo)} {pid} {rec['id']} {res['iris_ms']} ms  top={res['matches'][0]['nct_id']} {res['matches'][0]['verdict']}", file=sys.stderr, flush=True)
    (WEB / "patients.json").write_text(json.dumps(patients, ensure_ascii=False))
    print(f"matched all in {time.time()-t0:.0f}s", file=sys.stderr)

    # ---- embedding map ------------------------------------------------------------------------
    import umap
    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import TfidfVectorizer

    ids = list(engine.trials)
    H = engine.seg_head[[engine.seg_index[n] for n in ids]]
    reducer = umap.UMAP(n_neighbors=18, min_dist=0.25, metric="cosine", random_state=7)
    xy = reducer.fit_transform(H)
    pxy = reducer.transform(np.array(query_vecs))
    km = KMeans(n_clusters=9, n_init=10, random_state=7).fit(H)
    titles = [engine.trials[n]["title"] + " " + " ".join(i for i in engine.trials[n]["interventions"] if i) for n in ids]
    generic = ["colorectal", "cancer", "colon", "study", "trial", "patients", "treatment", "versus", "plus", "combination", "phase", "randomized", "compared", "participants", "cancers", "adult", "adults", "metastatic", "advanced", "carcinoma", "disease", "mcrc", "crc", "using", "efficacy", "safety", "evaluating", "evaluate", "open", "label", "ii", "iii", "iv", "tumors", "solid", "line"]
    tf = TfidfVectorizer(stop_words=list(__import__("sklearn.feature_extraction.text", fromlist=["ENGLISH_STOP_WORDS"]).ENGLISH_STOP_WORDS) + generic, max_features=4000, ngram_range=(1, 2), min_df=3)
    M = tf.fit_transform(titles)
    terms = np.array(tf.get_feature_names_out())
    overall = np.asarray(M.mean(axis=0)).ravel()
    clusters = []
    for c in range(9):
        rows = np.where(km.labels_ == c)[0]
        w = np.asarray(M[rows].mean(axis=0)).ravel() - overall
        clusters.append({"id": c, "n": int(len(rows)), "terms": [str(x) for x in terms[np.argsort(-w)[:4]]]})
    lo, hi = xy.min(axis=0), xy.max(axis=0)
    norm = lambda a: ((a - lo) / (hi - lo)).tolist()  # noqa: E731
    trials_out = []
    for i, n in enumerate(ids):
        t = engine.trials[n]
        trials_out.append({"id": n, "t": t["title"], "ph": "/".join(p.replace("PHASE", "") for p in t["phase"]) or "NA", "sp": t["sponsor"], "st": t["status"], "th": bool(t["thai_sites"]), "ns": t["n_sites"], "c": int(km.labels_[i]), "x": round(norm(xy[i:i+1])[0][0], 4), "y": round(norm(xy[i:i+1])[0][1], 4)})
    pmap = {p["id"]: [round(v, 4) for v in norm(pxy[k:k+1])[0]] for k, p in enumerate(patients)}
    (WEB / "trials.json").write_text(json.dumps({"trials": trials_out, "clusters": clusters, "patients": pmap}, ensure_ascii=False))

    # ---- benchmarks and data inventory --------------------------------------------------------
    fit = json.loads((ROOT / "models" / "trial_fit_metrics.json").read_text())
    comp = json.loads((ROOT / "models" / "completion_metrics.json").read_text())
    cohort_by = Counter(r["study"] for r in cohort)
    inventory = [
        {"id": "crc_msk_2017", "name": "MSK metastatic colorectal (Yaeger 2018)", "kind": "REAL", "n": cohort_by["crc_msk_2017"], "what": "age, sex, MSI, KRAS/NRAS/BRAF/ERBB2/PIK3CA, metastasis sites, panel", "url": STUDY_URL["crc_msk_2017"], "via": "cBioPortal public API"},
        {"id": "crc_msk_2026", "name": "MSK colorectal (2026 release)", "kind": "REAL", "n": cohort_by["crc_msk_2026"], "what": "sex, stage, MSI call incl. failed / insufficient, mutations, metastatic site", "url": STUDY_URL["crc_msk_2026"], "via": "cBioPortal public API"},
        {"id": "crc_sysucc_2022", "name": "SYSUCC ChangKang (Asian cohort)", "kind": "REAL", "n": cohort_by["crc_sysucc_2022"], "what": "age, sex, stage, MSI/MMR, mutations (whole-exome)", "url": STUDY_URL["crc_sysucc_2022"], "via": "cBioPortal public API"},
        {"id": "tcga", "name": "TCGA PanCancer Atlas colorectal", "kind": "REAL", "n": cohort_by["coadread_tcga_pan_can_atlas_2018"], "what": "age, sex, stage, MSI score (MANTIS), mutations, copy number", "url": STUDY_URL["coadread_tcga_pan_can_atlas_2018"], "via": "cBioPortal public API"},
        {"id": "ctgov", "name": "ClinicalTrials.gov: recruiting colorectal trials", "kind": "REAL", "n": len(engine.trials), "what": "title, phase, sponsor, sites, full eligibility text", "url": "https://clinicaltrials.gov/", "via": "ClinicalTrials.gov API v2"},
        {"id": "trec", "name": "TREC Clinical Trials 2021 + 2022", "kind": "REAL", "n": fit["n_train_pairs"] + fit["n_test_pairs"], "what": "synthetic patient topics with assessor labels (eligible / excluded / not relevant)", "url": "https://www.trec-cds.org/", "via": "trec.nist.gov"},
        {"id": "sim", "name": "Simulated overlay", "kind": "SIM", "n": None, "what": "ECOG, labs with dates, imaging, prior lines, infection screens, consent: no public colorectal dataset has these", "url": None, "via": "seeded generator"},
    ]
    (WEB / "benchmarks.json").write_text(json.dumps({"generated": date.today().isoformat(), "reference_date": REF_DATE.isoformat(), "trial_fit": fit, "completion": comp, "inventory": inventory, "n_chunks": int(len(json.loads((PROC / "chunks.json").read_text()))), "n_trials": len(ids), "n_criteria": int(sum(len(v) for v in engine.criteria.values())), "n_assessable": int(sum(1 for v in engine.criteria.values() for c in v if c["assessable"]))}, ensure_ascii=False))
    print("export done")


if __name__ == "__main__":
    main()
