"""Thailand population hotspots for the match page.

Output: web/data/thailand.json  (province geometry, modelled patient pools per biomarker subgroup, trial sites)

Everything here is MODELLED and tagged SIM. No Thai patient-level data exists in this MVP.
    pool(province, subgroup) = population x crude CRC incidence x regional factor x metastatic share
                               x mean time on systemic treatment x subgroup prevalence
Province populations are rounded 2023 civil-registration figures. Rates are published national/literature
figures, fixed below and written into the output so the UI can show them next to every number.
Geometry: github.com/apisit/thailand.json (public domain province outlines), simplified here.
"""
from __future__ import annotations

import json
import math
import re
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "thailand_provinces.json"
OUT = ROOT / "web" / "data" / "thailand.json"
GEO_URL = "https://raw.githubusercontent.com/apisit/thailand.json/master/thailand.json"

# name in the GeoJSON -> (ISO 3166-2, region, population in thousands, display name)
PROVINCES = {
    "Bangkok Metropolis": ("TH-10", "Central", 5471, "Bangkok"), "Samut Prakan": ("TH-11", "Central", 1360, None),
    "Nonthaburi": ("TH-12", "Central", 1300, None), "Pathum Thani": ("TH-13", "Central", 1210, None),
    "Phra Nakhon Si Ayutthaya": ("TH-14", "Central", 822, "Ayutthaya"), "Ang Thong": ("TH-15", "Central", 272, None),
    "Lop Buri": ("TH-16", "Central", 738, "Lopburi"), "Sing Buri": ("TH-17", "Central", 203, None),
    "Chai Nat": ("TH-18", "Central", 317, None), "Saraburi": ("TH-19", "Central", 640, None),
    "Chon Buri": ("TH-20", "East", 1600, None), "Rayong": ("TH-21", "East", 760, None),
    "Chanthaburi": ("TH-22", "East", 540, None), "Trat": ("TH-23", "East", 229, None),
    "Chachoengsao": ("TH-24", "East", 727, None), "Prachin Buri": ("TH-25", "East", 500, None),
    "Nakhon Nayok": ("TH-26", "Central", 262, None), "Sa Kaeo": ("TH-27", "East", 565, None),
    "Nakhon Ratchasima": ("TH-30", "Northeast", 2630, None), "Buri Ram": ("TH-31", "Northeast", 1580, None),
    "Surin": ("TH-32", "Northeast", 1390, None), "Si Sa Ket": ("TH-33", "Northeast", 1460, None),
    "Ubon Ratchathani": ("TH-34", "Northeast", 1870, None), "Yasothon": ("TH-35", "Northeast", 530, None),
    "Chaiyaphum": ("TH-36", "Northeast", 1120, None), "Amnat Charoen": ("TH-37", "Northeast", 377, None),
    "Bueng Kan": ("TH-38", "Northeast", 423, None), "Nong Bua Lam Phu": ("TH-39", "Northeast", 510, None),
    "Khon Kaen": ("TH-40", "Northeast", 1790, None), "Udon Thani": ("TH-41", "Northeast", 1570, None),
    "Loei": ("TH-42", "Northeast", 640, None), "Nong Khai": ("TH-43", "Northeast", 520, None),
    "Maha Sarakham": ("TH-44", "Northeast", 950, None), "Roi Et": ("TH-45", "Northeast", 1290, None),
    "Kalasin": ("TH-46", "Northeast", 970, None), "Sakon Nakhon": ("TH-47", "Northeast", 1150, None),
    "Nakhon Phanom": ("TH-48", "Northeast", 717, None), "Mukdahan": ("TH-49", "Northeast", 352, None),
    "Chiang Mai": ("TH-50", "North", 1790, None), "Lamphun": ("TH-51", "North", 400, None),
    "Lampang": ("TH-52", "North", 715, None), "Uttaradit": ("TH-53", "North", 440, None),
    "Phrae": ("TH-54", "North", 430, None), "Nan": ("TH-55", "North", 473, None),
    "Phayao": ("TH-56", "North", 460, None), "Chiang Rai": ("TH-57", "North", 1300, None),
    "Mae Hong Son": ("TH-58", "North", 287, None), "Nakhon Sawan": ("TH-60", "Central", 1030, None),
    "Uthai Thani": ("TH-61", "Central", 323, None), "Kamphaeng Phet": ("TH-62", "Central", 710, None),
    "Tak": ("TH-63", "West", 680, None), "Sukhothai": ("TH-64", "Central", 585, None),
    "Phitsanulok": ("TH-65", "Central", 846, None), "Phichit": ("TH-66", "Central", 527, None),
    "Phetchabun": ("TH-67", "Central", 975, None), "Ratchaburi": ("TH-70", "West", 870, None),
    "Kanchanaburi": ("TH-71", "West", 895, None), "Suphan Buri": ("TH-72", "Central", 840, None),
    "Nakhon Pathom": ("TH-73", "Central", 925, None), "Samut Sakhon": ("TH-74", "Central", 590, None),
    "Samut Songkhram": ("TH-75", "Central", 190, None), "Phetchaburi": ("TH-76", "West", 485, None),
    "Prachuap Khiri Khan": ("TH-77", "West", 553, None), "Nakhon Si Thammarat": ("TH-80", "South", 1550, None),
    "Krabi": ("TH-81", "South", 480, None), "Phangnga": ("TH-82", "South", 270, "Phang Nga"),
    "Phuket": ("TH-83", "South", 420, None), "Surat Thani": ("TH-84", "South", 1070, None),
    "Ranong": ("TH-85", "South", 194, None), "Chumphon": ("TH-86", "South", 512, None),
    "Songkhla": ("TH-90", "South", 1430, None), "Satun": ("TH-91", "South", 326, None),
    "Trang": ("TH-92", "South", 640, None), "Phatthalung": ("TH-93", "South", 523, None),
    "Pattani": ("TH-94", "South", 730, None), "Yala": ("TH-95", "South", 545, None),
    "Narathiwat": ("TH-96", "South", 810, None),
}

METHOD = {
    "tag": "SIM",
    "formula": "population × crude CRC incidence × regional factor × metastatic share × mean years on systemic treatment × subgroup prevalence",
    "population": "Thai civil registration 2023, rounded to the nearest thousand",
    "crude_incidence_per_100k": 24.0,          # GLOBOCAN 2022, Thailand, colorectum, crude rate, both sexes (approx.)
    "metastatic_share": 0.35,                  # synchronous + metachronous within the treated pool
    "treatment_years": 1.6,                    # mean time on systemic therapy
    "regional_factor": {"Bangkok": 1.3, "Central": 1.2, "East": 1.15, "North": 1.0, "West": 1.0, "Northeast": 0.9, "South": 0.8},  # illustrative; Thai registries report higher CRC rates in Bangkok/Central than the South
    "interval": "±35% of the point estimate",
    "confidence": "0.25 + 0.12·log10(pool+1), capped at 0.70; modelled rows never exceed 0.70",
}
SUBGROUPS = {
    "mcrc": {"label": "mCRC, all", "prevalence": 1.0},
    "ras_wt": {"label": "mCRC · RAS wild-type", "prevalence": 0.48},
    "kras_mut": {"label": "mCRC · KRAS mutant", "prevalence": 0.45},
    "kras_g12c": {"label": "mCRC · KRAS G12C", "prevalence": 0.03},
    "braf_v600e": {"label": "mCRC · BRAF V600E", "prevalence": 0.05},
    "msi_h": {"label": "mCRC · MSI-high", "prevalence": 0.045},
    "her2_amp": {"label": "mCRC · HER2 amplified", "prevalence": 0.035},
}
# Known Thai trial sites: facility name (as it appears in ClinicalTrials.gov) -> province, lat, lon
SITES = {
    "Siriraj Hospital": ("TH-10", 13.7589, 100.4858),
    "Ramathibodi Hospital": ("TH-10", 13.7676, 100.5253),
    "King Chulalongkorn Memorial Hospital": ("TH-10", 13.7326, 100.5366),
    "Chulabhorn Hospital": ("TH-10", 13.8773, 100.5742),
    "Rajavithi Hospital": ("TH-10", 13.7658, 100.5361),
    "National Cancer Institute": ("TH-10", 13.7656, 100.5323),
    "Phramongkutklao Hospital": ("TH-10", 13.7665, 100.5327),
    "Vajira Hospital": ("TH-10", 13.7797, 100.5082),
    "Bumrungrad International Hospital": ("TH-10", 13.7470, 100.5527),
    "Maharaj Nakorn Chiang Mai Hospital": ("TH-50", 18.7897, 98.9743),
    "Srinagarind Hospital": ("TH-40", 16.4685, 102.8285),
    "Songklanagarind Hospital": ("TH-90", 7.0066, 100.4983),
}
CITY_PROVINCE = {"bangkok": "TH-10", "chiang mai": "TH-50", "khon kaen": "TH-40", "hat yai": "TH-90", "songkhla": "TH-90", "nonthaburi": "TH-12", "pathum thani": "TH-13", "phitsanulok": "TH-65", "ubon ratchathani": "TH-34", "nakhon ratchasima": "TH-30"}


def fetch() -> dict:
    if not RAW.exists():
        RAW.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(GEO_URL, timeout=60) as r:
            RAW.write_bytes(r.read())
    return json.loads(RAW.read_text())


def dp(points: list, tol: float) -> list:
    """Douglas-Peucker on a closed ring (lon, lat)."""
    if len(points) < 4:
        return points
    def perp(p, a, b):
        ax, ay = a; bx, by = b; px, py = p
        dx, dy = bx - ax, by - ay
        if dx == dy == 0:
            return math.hypot(px - ax, py - ay)
        t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        return math.hypot(px - (ax + t * dx), py - (ay + t * dy))
    def rec(pts):
        if len(pts) < 3:
            return pts
        a, b = pts[0], pts[-1]
        i, dmax = 0, 0.0
        for k in range(1, len(pts) - 1):
            d = perp(pts[k], a, b)
            if d > dmax:
                i, dmax = k, d
        if dmax > tol:
            return rec(pts[: i + 1])[:-1] + rec(pts[i:])
        return [a, b]
    out = rec(points)
    return out if len(out) >= 4 else points


def ring_area(r: list) -> float:
    return abs(sum(r[i][0] * r[(i + 1) % len(r)][1] - r[(i + 1) % len(r)][0] * r[i][1] for i in range(len(r)))) / 2


def simplify(geom: dict, tol: float = 0.012) -> tuple[dict, list]:
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    outer = sorted(polys, key=lambda p: -ring_area(p[0]))
    keep = []
    for k, poly in enumerate(outer):
        if k and ring_area(poly[0]) < 0.004:   # drop specks, keep the mainland and real islands
            continue
        keep.append([[[round(x, 3), round(y, 3)] for x, y in dp(poly[0], tol)]])
    main = outer[0][0]
    cx = sum(p[0] for p in main) / len(main)
    cy = sum(p[1] for p in main) / len(main)
    return {"type": "MultiPolygon", "coordinates": keep}, [round(cx, 3), round(cy, 3)]


def sites_from_matches() -> dict:
    found: dict[str, dict] = {}
    for f in sorted((ROOT / "web" / "data" / "matches").glob("*.json")):
        for m in json.loads(f.read_text())["matches"]:
            for s in m.get("thai_sites", []):
                name = s.get("facility") or "Unnamed site"
                if name in found:
                    found[name]["trials"].add(m["nct_id"])
                    continue
                prov, lat, lon = SITES.get(name, (None, None, None))
                if prov is None:
                    prov = CITY_PROVINCE.get(str(s.get("city", "")).lower())
                    if prov:
                        lat, lon = CENTROIDS[prov]
                found[name] = {"facility": name, "city": s.get("city"), "province": prov, "lat": lat, "lon": lon, "located": name in SITES, "trials": {m["nct_id"]}}
    return {k: {**v, "trials": sorted(v["trials"])} for k, v in found.items()}


CENTROIDS: dict[str, tuple[float, float]] = {}


def main() -> None:
    geo = fetch()
    provinces, features = [], []
    for ft in geo["features"]:
        name = ft["properties"]["name"]
        iso, region, pop_k, display = PROVINCES[name]
        g, (cx, cy) = simplify(ft["geometry"])
        CENTROIDS[iso] = (cy, cx)
        pop = pop_k * 1000
        rf = METHOD["regional_factor"]["Bangkok" if iso == "TH-10" else region]
        base = pop * METHOD["crude_incidence_per_100k"] / 100_000 * rf * METHOD["metastatic_share"] * METHOD["treatment_years"]
        est = {}
        for key, sg in SUBGROUPS.items():
            n = base * sg["prevalence"]
            est[key] = {
                "n": round(n), "lo": round(n * 0.65), "hi": round(n * 1.35),
                "per_100k": round(n / pop * 100_000, 2),
                "conf": round(min(0.70, 0.25 + 0.12 * math.log10(n + 1)), 2),
            }
        provinces.append({"key": iso, "name": display or name, "region": region, "pop": pop, "centroid": [cx, cy], "regional_factor": rf, "est": est})
        features.append({"type": "Feature", "properties": {"key": iso}, "geometry": g})
    provinces.sort(key=lambda p: -p["est"]["mcrc"]["n"])
    out = {
        "generated": date.today().isoformat(),
        "tag": "SIM",
        "method": METHOD,
        "subgroups": SUBGROUPS,
        "geometry_source": GEO_URL,
        "sites": sites_from_matches(),
        "provinces": provinces,
        "geo": {"type": "FeatureCollection", "features": features},
    }
    OUT.write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    nv = sum(len(r) for f in features for poly in f["geometry"]["coordinates"] for r in poly)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(provinces)} provinces, {nv} vertices, {len(out['sites'])} sites, {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
