"""Sample judged patient-trial pairs from TREC Clinical Trials 2021 (train) and 2022 (test).

TREC qrels label: 0 not relevant, 1 excluded (relevant but the patient is excluded), 2 eligible.
Trial text comes from the ClinicalTrials.gov API (the current registry version, not the 2021 snapshot).
Output: data/processed/trec_pairs.json
"""
from __future__ import annotations

import html
import json
import random
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "trec"
OUT = ROOT / "data" / "processed"
sys.path.insert(0, str(ROOT))
from lana.criteria import split_criteria  # noqa: E402

PER_LABEL = 15
URL = "https://clinicaltrials.gov/api/v2/studies"
FIELDS = "NCTId,BriefTitle,Condition,BriefSummary,EligibilityCriteria,MinimumAge,MaximumAge,Sex,InterventionName"


def topics(path: Path) -> dict[str, str]:
    xml = path.read_text()
    return {m.group(1): html.unescape(re.sub(r"\s+", " ", m.group(2))).strip() for m in re.finditer(r'<topic number="(\d+)">(.*?)</topic>', xml, re.S)}


def qrels(path: Path) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = defaultdict(dict)
    for line in path.read_text().splitlines():
        t, _, nct, lab = line.split()
        out[t][nct] = int(lab)
    return out


def years(text: str | None) -> int | None:
    m = re.match(r"(\d+)\s*(Year|Month)", text or "")
    return None if not m else (int(m.group(1)) if m.group(2) == "Year" else int(m.group(1)) // 12)


def fetch(ids: list[str], client: httpx.Client) -> dict[str, dict]:
    out = {}
    for i in range(0, len(ids), 80):
        batch = ids[i : i + 80]
        for attempt in range(8):
            time.sleep(1.0)
            r = client.get(URL, params={"filter.ids": ",".join(batch), "fields": FIELDS, "pageSize": 100})
            if r.status_code == 200:
                break
            time.sleep(min(60, 4 * 2**attempt))
        r.raise_for_status()
        for s in r.json().get("studies", []):
            p = s["protocolSection"]
            elig = p.get("eligibilityModule", {})
            parts = split_criteria(elig.get("eligibilityCriteria", ""))
            out[p["identificationModule"]["nctId"]] = {
                "nct_id": p["identificationModule"]["nctId"],
                "title": p["identificationModule"].get("briefTitle", ""),
                "conditions": p.get("conditionsModule", {}).get("conditions", []),
                "summary": p.get("descriptionModule", {}).get("briefSummary", ""),
                "interventions": [x.get("name") for x in p.get("armsInterventionsModule", {}).get("interventions", [])],
                "inclusion": " ".join(t for s_, t in parts if s_ == "inclusion"),
                "exclusion": " ".join(t for s_, t in parts if s_ == "exclusion"),
                "min_age": years(elig.get("minimumAge")),
                "max_age": years(elig.get("maximumAge")),
                "sex": elig.get("sex"),
            }
        print(f"  fetched {min(i+80, len(ids))}/{len(ids)}", file=sys.stderr, flush=True)
    return out


def main() -> None:
    rnd = random.Random(7)
    pairs = []
    for year, split in [("2021", "train"), ("2022", "test")]:
        tp, qr = topics(RAW / f"topics{year}.xml"), qrels(RAW / f"qrels{year}.txt")
        for topic, text in tp.items():
            by = defaultdict(list)
            for nct, lab in qr.get(topic, {}).items():
                by[lab].append(nct)
            for lab, ids in by.items():
                rnd.shuffle(ids)
                for nct in ids[:PER_LABEL]:
                    pairs.append({"split": split, "year": year, "topic": f"{year}-{topic}", "topic_text": text, "nct_id": nct, "label": lab})
    ids = sorted({p["nct_id"] for p in pairs})
    print(f"{len(pairs)} pairs, {len(ids)} trials to fetch", file=sys.stderr)
    trials = fetch(ids, httpx.Client(timeout=120))
    pairs = [p for p in pairs if p["nct_id"] in trials]
    (OUT / "trec_pairs.json").write_text(json.dumps({"pairs": pairs, "trials": trials}, ensure_ascii=False))
    print(f"kept {len(pairs)} pairs with trial text; {len(trials)} trials")


if __name__ == "__main__":
    main()
