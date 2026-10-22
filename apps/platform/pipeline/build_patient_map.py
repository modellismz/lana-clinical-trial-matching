"""Build the home-page patient map: every real cohort patient as one node, linked to its most similar peers.

Input:  data/processed/cohort.json        (pipeline/build_cohort.py; 8,435 real de-identified patients)
        web/data/patients.json            (optional; marks the 36 demo patients so the map can link to them)
Output: web/data/patient_map.json

Similarity is a weighted cosine over the real facts a trial rule can read: RAS/RAF/HER2/PIK3CA/MSI result
*and* Biomarker Status (an untested gene is a feature of its own, never treated as negative), stage, metastasis
sites, primary side, sex, age decade, TMB band and source cohort. Patients with an identical profile share a
node cluster; the browser lays the graph out with a force simulation, so proximity on screen = similarity here.

Standard library only, so it runs without the model venv:  python3 pipeline/build_patient_map.py
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COHORT = ROOT / "data" / "processed" / "cohort.json"
WEB = ROOT / "web" / "data"
OUT = WEB / "patient_map.json"

STUDIES = [
    ("crc_msk_2017", "MSK-17", "MSK metastatic colorectal (Cancer Cell 2018)"),
    ("crc_msk_2026", "MSK-26", "MSK colorectal (2026)"),
    ("crc_sysucc_2022", "SYSUCC", "SYSUCC ChangKang project (Nat Commun 2022)"),
    ("coadread_tcga_pan_can_atlas_2018", "TCGA", "TCGA PanCancer Atlas colorectal"),
]
STUDY_IDX = {s[0]: i for i, s in enumerate(STUDIES)}
SITES = ["liver", "lung", "lymph_node", "peritoneum", "bone", "brain", "ovary"]

# biomarker code shared with web/js/pages/home.js
#   0 not done · 1 failed · 2 insufficient · 3 wild-type / negative · 4 mutant / positive · 5 BRAF non-V600
STATUS_CODE = {"not_done": 0, "failed": 1, "insufficient": 2}

GROUPS = [
    ("kras_g12c", "KRAS G12C", "#ffb547"),
    ("braf_v600e", "BRAF V600E", "#ff7fa3"),
    ("msi_h", "MSI-high", "#b49bff"),
    ("her2_amp", "HER2 amplified", "#55d6e8"),
    ("ras_mut", "Other RAS mutant", "#ff8e5e"),
    ("ras_wt", "RAS/RAF wild-type", "#52e0a1"),
    ("incomplete", "Incomplete testing", "#6e7f93"),
]
GROUP_IDX = {g[0]: i for i, g in enumerate(GROUPS)}

K_NEIGHBOURS = 6  # similar profiles each profile links to
MIN_SIM = 0.25  # weaker links are not drawn


def code(b: dict) -> int:
    if b["status"] != "done":
        return STATUS_CODE.get(b["status"], 0)
    r = b.get("result")
    if r in ("mutant", "amplified", "msi_high"):
        return 4
    if r == "non_v600_mutant":
        return 5
    return 3


def group(rec: dict) -> str:
    bm = rec["biomarkers"]
    done = lambda g: bm[g]["status"] == "done"  # noqa: E731
    if done("KRAS") and bm["KRAS"].get("variant") == "G12C":
        return "kras_g12c"
    if done("BRAF") and bm["BRAF"].get("variant") == "V600E":
        return "braf_v600e"
    if done("MSI") and bm["MSI"]["result"] == "msi_high":
        return "msi_h"
    if done("ERBB2") and bm["ERBB2"]["result"] == "amplified":
        return "her2_amp"
    if (done("KRAS") and bm["KRAS"]["result"] == "mutant") or (done("NRAS") and bm["NRAS"]["result"] == "mutant"):
        return "ras_mut"
    if done("KRAS") and done("NRAS") and done("BRAF") and bm["KRAS"]["result"] == "wild_type" and bm["NRAS"]["result"] == "wild_type" and bm["BRAF"]["result"] == "wild_type":
        return "ras_wt"
    return "incomplete"


# ---- feature vector -------------------------------------------------------------------------------
class Features:
    """Weighted binary features; each distinct (name, value) gets one bit."""

    def __init__(self) -> None:
        self.ids: dict[tuple, int] = {}
        self.weight: list[float] = []

    def bit(self, name: str, value, w: float) -> int:
        key = (name, value)
        if key not in self.ids:
            self.ids[key] = len(self.weight)
            self.weight.append(w)
        return 1 << self.ids[key]


def kras_class(b: dict) -> str:
    if b["status"] != "done":
        return b["status"]
    if b["result"] != "mutant":
        return "wt"
    v = b.get("variant") or ""
    return v if v in ("G12C", "G12D", "G12V", "G13D", "G12A", "G12S", "G12R", "Q61H", "A146T") else "other"


def profile(rec: dict, F: Features) -> int:
    bm = rec["biomarkers"]
    m = 0
    m |= F.bit("kras", kras_class(bm["KRAS"]), 3.0)
    m |= F.bit("nras", bm["NRAS"]["status"] if bm["NRAS"]["status"] != "done" else bm["NRAS"]["result"], 2.0)
    m |= F.bit("braf", bm["BRAF"]["status"] if bm["BRAF"]["status"] != "done" else bm["BRAF"]["result"], 3.0)
    m |= F.bit("her2", bm["ERBB2"]["status"] if bm["ERBB2"]["status"] != "done" else bm["ERBB2"]["result"], 2.0)
    m |= F.bit("msi", bm["MSI"]["status"] if bm["MSI"]["status"] != "done" else bm["MSI"]["result"], 3.0)
    m |= F.bit("pik3ca", bm["PIK3CA"]["status"] if bm["PIK3CA"]["status"] != "done" else bm["PIK3CA"]["result"], 1.0)
    m |= F.bit("stage_iv", bool(rec["stage_iv"]), 2.0)
    mets = rec["metastasis_sites"] or []
    for s in mets:
        if s in SITES:
            m |= F.bit("met", s, 1.0)
    if not mets:
        m |= F.bit("met", "none_recorded", 0.5)
    m |= F.bit("side", rec.get("side") or "unknown", 1.0)
    m |= F.bit("sex", rec.get("sex") or "unknown", 0.5)
    age = rec.get("age")
    m |= F.bit("age", (age // 10) if age is not None else "unknown", 1.0)
    tmb = rec.get("tmb")
    band = "nd" if tmb is None else "lt10" if tmb < 10 else "10to20" if tmb < 20 else "ge20"
    m |= F.bit("tmb", band, 1.0)
    m |= F.bit("study", rec["study"], 0.75)
    return m


def mets_mask(rec: dict) -> int:
    m = 0
    for i, s in enumerate(SITES):
        if s in (rec["metastasis_sites"] or []):
            m |= 1 << i
    return m


def node_of(rec: dict, gidx: int, demo: str | None) -> list:
    bm = rec["biomarkers"]
    sex = {"male": 0, "female": 1}.get(rec.get("sex") or "", -1)
    side = {"left": 0, "right": 1}.get(rec.get("side") or "", -1)
    tmb = rec.get("tmb")
    return [
        STUDY_IDX[rec["study"]],
        rec.get("age"),
        sex,
        1 if rec["stage_iv"] else 0,
        side,
        code(bm["KRAS"]),
        code(bm["NRAS"]),
        code(bm["BRAF"]),
        code(bm["ERBB2"]),
        code(bm["MSI"]),
        code(bm["PIK3CA"]),
        round(tmb, 1) if tmb is not None else None,
        mets_mask(rec),
        gidx,
        (bm["KRAS"].get("variant") if bm["KRAS"]["status"] == "done" and bm["KRAS"]["result"] == "mutant" else None),
        demo,
    ]


def main() -> None:
    if not COHORT.exists():
        sys.exit(f"missing {COHORT}: run `python3 pipeline/build_cohort.py` (make data) first")
    cohort = json.loads(COHORT.read_text())
    cohort.sort(key=lambda r: r["id"])
    demo_ids: dict[tuple[str, str], str] = {}
    pj = WEB / "patients.json"
    if pj.exists():
        for p in json.loads(pj.read_text()):
            demo_ids[(p["study"], p["source_id"])] = p["id"]

    F = Features()
    masks = [profile(r, F) for r in cohort]
    W = F.weight
    cache: dict[int, float] = {}

    # ---- unique profiles and their nearest neighbours ----------------------------------------------
    members: dict[int, list[int]] = defaultdict(list)
    for i, m in enumerate(masks):
        members[m].append(i)
    profiles = list(members)
    norm = {m: math.sqrt(sum(W[i] ** 2 for i in range(len(W)) if m >> i & 1)) for m in profiles}
    print(f"{len(cohort)} patients · {len(profiles)} distinct profiles · {len(W)} features", file=sys.stderr)

    sq_cache: dict[int, float] = {}

    def sq_sum(mask: int) -> float:
        s = sq_cache.get(mask)
        if s is None:
            s = sum(W[i] ** 2 for i in range(len(W)) if mask >> i & 1)
            sq_cache[mask] = s
        return s

    neigh: dict[int, list[tuple[int, float]]] = {}
    for a in profiles:
        best: list[tuple[float, int]] = []
        na = norm[a]
        for b in profiles:
            if b == a:
                continue
            inter = a & b
            if not inter:
                continue
            sim = sq_sum(inter) / (na * norm[b])  # cosine over weighted binary vectors
            if sim < MIN_SIM:
                continue
            if len(best) < K_NEIGHBOURS:
                best.append((sim, b))
                best.sort(reverse=True)
            elif sim > best[-1][0]:
                best[-1] = (sim, b)
                best.sort(reverse=True)
        neigh[a] = [(b, round(s, 3)) for s, b in best]

    # ---- expand to patient-level edges --------------------------------------------------------------
    rnd = random.Random(7)
    edges: dict[tuple[int, int], float] = {}

    def link(i: int, k: int, w: float) -> None:
        if i == k:
            return
        key = (i, k) if i < k else (k, i)
        if w > edges.get(key, 0.0):
            edges[key] = w

    for m, mem in members.items():
        n = len(mem)
        if n > 1:  # identical profiles: a ring plus a few chords so the blob holds together
            order = mem[:]
            rnd.shuffle(order)
            for t in range(n):
                link(order[t], order[(t + 1) % n], 1.0)
            for _ in range(n // 3):
                link(rnd.choice(order), rnd.choice(order), 1.0)
        for b, sim in neigh[m]:
            other = members[b]
            n_links = max(1, min(10, round(1.5 * math.sqrt(min(n, len(other))))))
            for _ in range(n_links):
                link(rnd.choice(mem), rnd.choice(other), sim)

    # ---- nodes -----------------------------------------------------------------------------------------
    groups = [group(r) for r in cohort]
    nodes = [node_of(r, GROUP_IDX[groups[i]], demo_ids.get((r["study"], r["patient_id"]))) for i, r in enumerate(cohort)]
    gcount = Counter(groups)
    scount = Counter(r["study"] for r in cohort)

    # ---- data availability (what a trial rule could actually read) -----------------------------------
    def share(pred) -> float:
        return round(sum(1 for r in cohort if pred(r)) / len(cohort), 4)

    availability = [
        {"id": "kras", "label": "KRAS", "done": share(lambda r: r["biomarkers"]["KRAS"]["status"] == "done")},
        {"id": "nras", "label": "NRAS", "done": share(lambda r: r["biomarkers"]["NRAS"]["status"] == "done")},
        {"id": "braf", "label": "BRAF", "done": share(lambda r: r["biomarkers"]["BRAF"]["status"] == "done")},
        {"id": "her2", "label": "HER2", "done": share(lambda r: r["biomarkers"]["ERBB2"]["status"] == "done")},
        {"id": "msi", "label": "MSI / MMR", "done": share(lambda r: r["biomarkers"]["MSI"]["status"] == "done"), "failed": share(lambda r: r["biomarkers"]["MSI"]["status"] in ("failed", "insufficient"))},
        {"id": "pik3ca", "label": "PIK3CA", "done": share(lambda r: r["biomarkers"]["PIK3CA"]["status"] == "done")},
        {"id": "tmb", "label": "TMB", "done": share(lambda r: r.get("tmb") is not None)},
        {"id": "age", "label": "Age", "done": share(lambda r: r.get("age") is not None)},
        {"id": "sex", "label": "Sex", "done": share(lambda r: bool(r.get("sex")))},
        {"id": "side", "label": "Primary side", "done": share(lambda r: bool(r.get("side")))},
        {"id": "mets", "label": "Metastasis sites", "done": share(lambda r: bool(r["metastasis_sites"]))},
    ]

    out = {
        "generated": date.today().isoformat(),
        "n": len(cohort),
        "n_profiles": len(profiles),
        "n_features": len(W),
        "k": K_NEIGHBOURS,
        "min_sim": MIN_SIM,
        "stage_iv": sum(1 for r in cohort if r["stage_iv"]),
        "studies": [{"id": s, "short": sh, "label": lb, "n": scount.get(s, 0)} for s, sh, lb in STUDIES],
        "groups": [{"id": g, "label": lb, "color": c, "n": gcount.get(g, 0)} for g, lb, c in GROUPS],
        "sites": SITES,
        "availability": availability,
        "columns": ["study", "age", "sex", "stage_iv", "side", "kras", "nras", "braf", "her2", "msi", "pik3ca", "tmb", "mets", "group", "kras_variant", "demo"],
        "nodes": nodes,
        "edges": [[a, b, w] for (a, b), w in sorted(edges.items())],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    digest = hashlib.sha256(OUT.read_bytes()).hexdigest()[:8]
    print(f"wrote {OUT.relative_to(ROOT)} · {len(nodes)} nodes · {len(edges)} edges · {OUT.stat().st_size/1e6:.1f} MB · {digest}", file=sys.stderr)
    for g in out["groups"]:
        print(f"  {g['label']:<20} {g['n']:>5}", file=sys.stderr)


if __name__ == "__main__":
    main()
