"""Fetch real colorectal cancer trials from the ClinicalTrials.gov API v2.

Output: data/processed/trials_raw.json
Keeps interventional trials that are recruiting or not yet recruiting and mention metastatic /
advanced / unresectable colorectal disease. The eligibility text is the registry text, unedited.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)
URL = "https://clinicaltrials.gov/api/v2/studies"
FIELDS = ",".join(
    [
        "NCTId",
        "BriefTitle",
        "OfficialTitle",
        "BriefSummary",
        "OverallStatus",
        "Phase",
        "Condition",
        "Keyword",
        "InterventionName",
        "LeadSponsorName",
        "EligibilityCriteria",
        "MinimumAge",
        "MaximumAge",
        "Sex",
        "LocationCountry",
        "LocationFacility",
        "LocationCity",
        "StartDate",
        "EnrollmentCount",
    ]
)


def get_json(client: httpx.Client, params: dict, tries: int = 8) -> dict:
    """GET with a pause between calls and exponential backoff on 429 / 5xx."""
    for attempt in range(tries):
        time.sleep(1.0)
        r = client.get(URL, params=params)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(min(60, 4 * 2**attempt))
            continue
        r.raise_for_status()
    r.raise_for_status()
    raise RuntimeError("unreachable")


def years(text: str | None) -> int | None:
    if not text:
        return None
    m = re.match(r"(\d+)\s*(Year|Month)", text)
    if not m:
        return None
    n = int(m.group(1))
    return n if m.group(2) == "Year" else n // 12


def main() -> None:
    client = httpx.Client(timeout=120)
    studies: dict[str, dict] = {}
    for cond in ["metastatic colorectal cancer", "advanced colorectal cancer", "colon cancer", "rectal cancer"]:
        token = None
        while True:
            params = {
                "query.cond": cond,
                "filter.overallStatus": "RECRUITING|NOT_YET_RECRUITING",
                "query.term": "AREA[StudyType]INTERVENTIONAL",
                "fields": FIELDS,
                "pageSize": 200,
            }
            if token:
                params["pageToken"] = token
            d = get_json(client, params)
            for s in d.get("studies", []):
                p = s["protocolSection"]
                nct = p["identificationModule"]["nctId"]
                studies[nct] = s
            token = d.get("nextPageToken")
            if not token:
                break
    print(f"fetched {len(studies)} candidate trials")

    keep = []
    for nct, s in studies.items():
        p = s["protocolSection"]
        idm, cond, elig = p["identificationModule"], p.get("conditionsModule", {}), p.get("eligibilityModule", {})
        text = " ".join(
            [
                idm.get("briefTitle", ""),
                idm.get("officialTitle", ""),
                " ".join(cond.get("conditions", [])),
                " ".join(cond.get("keywords", [])),
                p.get("descriptionModule", {}).get("briefSummary", ""),
            ]
        ).lower()
        if not re.search(r"colorectal|colon|rectal|rectum|crc", text):
            continue
        if not re.search(r"metasta|advanced|unresectable|stage iv|refractory", text):
            continue
        criteria = elig.get("eligibilityCriteria")
        if not criteria or len(criteria) < 200:
            continue
        locs = p.get("contactsLocationsModule", {}).get("locations", [])
        countries = sorted({loc.get("country") for loc in locs if loc.get("country")})
        thai = [
            {"facility": loc.get("facility"), "city": loc.get("city")}
            for loc in locs
            if loc.get("country") == "Thailand"
        ]
        keep.append(
            {
                "nct_id": nct,
                "title": idm.get("briefTitle"),
                "official_title": idm.get("officialTitle"),
                "summary": p.get("descriptionModule", {}).get("briefSummary", ""),
                "status": p.get("statusModule", {}).get("overallStatus"),
                "phase": p.get("designModule", {}).get("phases", []),
                "conditions": cond.get("conditions", []),
                "interventions": [i.get("name") for i in p.get("armsInterventionsModule", {}).get("interventions", [])],
                "sponsor": p.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name"),
                "eligibility_text": criteria,
                "min_age": years(elig.get("minimumAge")),
                "max_age": years(elig.get("maximumAge")),
                "sex": elig.get("sex"),
                "countries": countries,
                "n_sites": len(locs),
                "thai_sites": thai,
                "enrollment": p.get("designModule", {}).get("enrollmentInfo", {}).get("count"),
                "url": f"https://clinicaltrials.gov/study/{nct}",
            }
        )
    keep.sort(key=lambda t: t["nct_id"])
    (OUT / "trials_raw.json").write_text(json.dumps(keep, ensure_ascii=False))
    print(f"kept {len(keep)} trials; {sum(1 for t in keep if t['thai_sites'])} list a Thai site")


if __name__ == "__main__":
    main()
