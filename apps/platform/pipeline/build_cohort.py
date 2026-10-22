"""Fetch real colorectal cancer cohorts from the public cBioPortal API and normalise them.

Output: data/processed/cohort.json  (one record per patient, ~9,000 patients)

Every biomarker carries a Biomarker Status (done / not_done / failed / insufficient) that is
derived from what the source really contains: gene-panel coverage, and the MSI call (an
"Inconclusive" or "Indeterminate" MSI call becomes `failed`, "Do not report" becomes `insufficient`).
Nothing here is simulated.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import httpx

BASE = "https://www.cbioportal.org/api"
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
RAW.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

STUDIES = {
    "crc_msk_2017": {
        "label": "MSK metastatic colorectal (Cancer Cell 2018)",
        "cna": "crc_msk_2017_gistic",
        "panel_attr": "GENE_PANEL",
    },
    "crc_msk_2026": {
        "label": "MSK colorectal (2026)",
        "cna": "crc_msk_2026_cna",
        "panel_attr": "GENE_PANEL",
    },
    "crc_sysucc_2022": {
        "label": "SYSUCC ChangKang project (Nat Commun 2022)",
        "cna": "crc_sysucc_2022_cna",
        "panel_attr": None,  # whole-exome: every gene is profiled
    },
    "coadread_tcga_pan_can_atlas_2018": {
        "label": "TCGA PanCancer Atlas colorectal",
        "cna": "coadread_tcga_pan_can_atlas_2018_gistic",
        "panel_attr": None,  # whole-exome
    },
}
GENES = {"KRAS": 3845, "NRAS": 4893, "BRAF": 673, "ERBB2": 2064, "PIK3CA": 5290}
KRAS_CODONS = {12, 13, 59, 61, 117, 146}
NRAS_CODONS = {12, 13, 59, 61, 117, 146}
CODING = {
    "Missense_Mutation",
    "Nonsense_Mutation",
    "Frame_Shift_Del",
    "Frame_Shift_Ins",
    "In_Frame_Del",
    "In_Frame_Ins",
    "Splice_Site",
}

client = httpx.Client(timeout=180, headers={"Accept": "application/json"})


def cached(name: str, fn):
    path = RAW / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text())
    data = fn()
    path.write_text(json.dumps(data))
    return data


def get(path: str, **params):
    r = client.get(f"{BASE}{path}", params=params)
    r.raise_for_status()
    return r.json()


def clinical(study: str, kind: str) -> dict[str, dict[str, str]]:
    rows = cached(
        f"{study}_clin_{kind}",
        lambda: get(f"/studies/{study}/clinical-data", clinicalDataType=kind, projection="SUMMARY", pageSize=2_000_000),
    )
    out: dict[str, dict[str, str]] = defaultdict(dict)
    key = "sampleId" if kind == "SAMPLE" else "patientId"
    for r in rows:
        out[r[key]][r["clinicalAttributeId"]] = r["value"]
    return out


def mutations(study: str, gene: str) -> list[dict]:
    pid = f"{study}_mutations"
    return cached(
        f"{study}_mut_{gene}",
        lambda: get(
            f"/molecular-profiles/{pid}/mutations",
            sampleListId=f"{study}_all",
            entrezGeneId=GENES[gene],
            projection="SUMMARY",
        ),
    )


def cna(study: str, profile: str, gene: str) -> list[dict]:
    return cached(
        f"{study}_cna_{gene}",
        lambda: get(
            f"/molecular-profiles/{profile}/molecular-data",
            sampleListId=f"{study}_all",
            entrezGeneId=GENES[gene],
        ),
    )


def panel_genes(panel_id: str) -> set[str]:
    d = cached(f"panel_{panel_id}", lambda: get(f"/gene-panels/{panel_id}"))
    return {g["hugoGeneSymbol"] for g in d["genes"]}


def codon(protein_change: str) -> int | None:
    m = re.search(r"(\d+)", protein_change or "")
    return int(m.group(1)) if m else None


def classify_gene(gene: str, muts: list[dict]) -> dict:
    """Turn a sample's mutation list for one gene into a result string."""
    muts = [m for m in muts if m.get("mutationType") in CODING]
    if gene == "KRAS" or gene == "NRAS":
        codons = KRAS_CODONS if gene == "KRAS" else NRAS_CODONS
        hot = [m for m in muts if m["mutationType"] == "Missense_Mutation" and codon(m["proteinChange"]) in codons]
        if hot:
            return {"result": "mutant", "variant": hot[0]["proteinChange"]}
        return {"result": "wild_type", "variant": None}
    if gene == "BRAF":
        v600 = [m for m in muts if m["proteinChange"] == "V600E"]
        if v600:
            return {"result": "mutant", "variant": "V600E"}
        other = [m for m in muts if m["mutationType"] == "Missense_Mutation"]
        if other:
            return {"result": "non_v600_mutant", "variant": other[0]["proteinChange"]}
        return {"result": "wild_type", "variant": None}
    if gene == "PIK3CA":
        hot = [m for m in muts if codon(m["proteinChange"]) in {542, 545, 1047} and m["mutationType"] == "Missense_Mutation"]
        return {"result": "mutant", "variant": hot[0]["proteinChange"]} if hot else {"result": "wild_type", "variant": None}
    return {"result": "wild_type", "variant": None}


def sides(value: str | None) -> str | None:
    if not value:
        return None
    v = value.lower()
    if "left" in v:
        return "left"
    if "right" in v:
        return "right"
    return None


def norm_sites(raw: str) -> list[str]:
    out = []
    low = raw.lower()
    for key, name in [
        ("liver", "liver"),
        ("lung", "lung"),
        ("lymph", "lymph_node"),
        ("periton", "peritoneum"),
        ("omentum", "peritoneum"),
        ("bone", "bone"),
        ("brain", "brain"),
        ("ovar", "ovary"),
    ]:
        if key in low and name not in out:
            out.append(name)
    return out


def build_study(study: str, cfg: dict) -> list[dict]:
    print(f"[{study}] clinical data", file=sys.stderr)
    pat = clinical(study, "PATIENT")
    smp = clinical(study, "SAMPLE")
    samples = cached(f"{study}_samples", lambda: get(f"/studies/{study}/samples", projection="SUMMARY", pageSize=100000))
    sample_patient = {s["sampleId"]: s["patientId"] for s in samples}

    # one sample per patient: keep the first by id, prefer a metastatic sample when the study labels it
    chosen: dict[str, str] = {}
    for sid in sorted(sample_patient):
        pid = sample_patient[sid]
        stype = (smp.get(sid, {}).get("SAMPLE_TYPE") or "").lower()
        if pid not in chosen or ("metast" in stype and "metast" not in (smp.get(chosen[pid], {}).get("SAMPLE_TYPE") or "").lower()):
            chosen[pid] = sid
    chosen_samples = set(chosen.values())

    muts = {g: defaultdict(list) for g in GENES}
    for gene in GENES:
        print(f"[{study}] mutations {gene}", file=sys.stderr)
        for m in mutations(study, gene):
            if m["sampleId"] in chosen_samples:
                muts[gene][m["sampleId"]].append(m)
    erbb2_cna = {r["sampleId"]: r["value"] for r in cna(study, cfg["cna"], "ERBB2") if r["sampleId"] in chosen_samples}

    panels: dict[str, set[str]] = {}
    records = []
    for pid, sid in chosen.items():
        sc = smp.get(sid, {})
        pc = pat.get(pid, {})
        panel_id = sc.get(cfg["panel_attr"]) if cfg["panel_attr"] else None
        if panel_id and panel_id not in panels:
            panels[panel_id] = panel_genes(panel_id)
        covered = panels.get(panel_id, set()) if panel_id else set(GENES)

        bm: dict[str, dict] = {}
        for gene in GENES:
            if gene in covered:
                res = classify_gene(gene, muts[gene].get(sid, []))
                if gene == "ERBB2":
                    amp = erbb2_cna.get(sid)
                    res = {"result": "amplified", "variant": "amplification"} if amp == 2 else {"result": "not_amplified", "variant": None}
                bm[gene] = {"status": "done", **res}
            else:
                bm[gene] = {"status": "not_done", "result": None, "variant": None}

        # MSI / MMR
        msi: dict
        raw = sc.get("MSI_STATUS") or sc.get("MSI_TYPE")
        mmr = sc.get("MMR")
        if study == "coadread_tcga_pan_can_atlas_2018":
            score = sc.get("MSI_SCORE_MANTIS")
            msi = {"status": "done", "result": "msi_high" if score and float(score) > 0.4 else "mss"} if score else {"status": "not_done", "result": None}
        elif raw in ("MSS", "Stable"):
            msi = {"status": "done", "result": "mss"}
        elif raw in ("MSI", "Instable"):
            msi = {"status": "done", "result": "msi_high"}
        elif raw in ("Inconclusive", "Indeterminate"):
            msi = {"status": "failed", "result": None}
        elif raw == "Do not report":
            msi = {"status": "insufficient", "result": None}
        elif mmr in ("pMMR", "dMMR"):
            msi = {"status": "done", "result": "msi_high" if mmr == "dMMR" else "mss"}
        else:
            msi = {"status": "not_done", "result": None}
        bm["MSI"] = msi

        age = pc.get("AGE") or pc.get("AGE_AT_DIAGNOSIS")
        stage_raw = sc.get("STAGE_AT_DIAGNOSIS") or pc.get("STAGE_HIGHEST_RECORDED") or pc.get("PATHOLOGICAL_STAGE") or pc.get("AJCC_PATHOLOGIC_TUMOR_STAGE") or ""
        stage_iv = bool(re.search(r"\bIV\b|stage 4", stage_raw, re.I))
        if sc.get("METASTASIS_AT_DIAGNOSIS") == "Yes":
            stage_iv = True
        if study == "crc_msk_2017":
            stage_iv = True  # a metastatic colorectal cancer cohort
        site_raw = (
            sc.get("METASTATIC_SITE")
            or sc.get("METASTATIC_BIOPSY_SITE")
            or ""
        )
        site_flags = [
            name
            for key, name in [
                ("METASTASES_SITE_FIRST_LIVER", "liver"),
                ("METASTASES_SITE_FIRST_LUNG", "lung"),
                ("METASTASES_SITE_FIRST_LN", "lymph_node"),
                ("METASTASES_SITE_FIRST_PERITONEUM_OMENTUM_ABDOMEN", "peritoneum"),
                ("METASTASES_SITE_FIRST_BONE", "bone"),
                ("METASTASES_SITE_FIRST_BRAIN", "brain"),
            ]
            if str(sc.get(key, "")).lower() in {"yes", "true", "1"}
        ]
        mets = sorted(set(norm_sites(site_raw) + site_flags))
        records.append(
            {
                "id": f"{study}:{pid}",
                "study": study,
                "study_label": cfg["label"],
                "patient_id": pid,
                "sample_id": sid,
                "age": int(float(age)) if age and re.match(r"^\d+(\.\d+)?$", age) else None,
                "sex": (pc.get("SEX") or "").lower() or None,
                "race": pc.get("RACE"),
                "stage_raw": stage_raw,
                "stage_iv": stage_iv,
                "side": sides(sc.get("PRIMARY_TUMOR_LOCATION")),
                "primary_site": sc.get("PRIMARY_SITE") or sc.get("TUMOR_SITE"),
                "metastasis_sites": mets,
                "sample_type": sc.get("SAMPLE_TYPE") or sc.get("SPECIMEN_TYPE"),
                "panel": panel_id or "whole-exome",
                "tmb": float(sc["TMB_NONSYNONYMOUS"]) if sc.get("TMB_NONSYNONYMOUS") not in (None, "") else None,
                "chemo_exposed": sc.get("CHEMO_EXP_SEQ_SPECIMEN"),
                "adjuvant_chemo": sc.get("ADJUVANT_CHEMOTHERAPY"),
                "os_status": pc.get("OS_STATUS"),
                "biomarkers": bm,
            }
        )
    print(f"[{study}] {len(records)} patients", file=sys.stderr)
    return records


def main() -> None:
    cohort: list[dict] = []
    for study, cfg in STUDIES.items():
        cohort.extend(build_study(study, cfg))
    # crc_msk_2026 re-releases most patients of crc_msk_2017; keep the 2017 record (it has age and more fields)
    seen = {r["patient_id"] for r in cohort if r["study"] == "crc_msk_2017"}
    before = len(cohort)
    cohort = [r for r in cohort if r["study"] != "crc_msk_2026" or r["patient_id"] not in seen]
    print(f"dropped {before - len(cohort)} duplicate MSK patients")
    (OUT / "cohort.json").write_text(json.dumps(cohort))
    print(f"wrote {len(cohort)} patients -> {OUT/'cohort.json'}")


if __name__ == "__main__":
    main()
