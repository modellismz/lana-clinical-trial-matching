"""Optional live API + static site for the Lana MVP.

    uvicorn server.app:app --port 8010

GET  /api/health          engine and IRIS status
POST /api/match           {"patient_id": "LN-XXXX"} -> a fresh match computed now (IRIS Vector Search, rules, both models)
GET  /                    the static web app (web/)
"""
from __future__ import annotations

import json
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lana.engine import Engine  # noqa: E402
from lana.patient import build_facts  # noqa: E402

app = FastAPI(title="Lana platform MVP", version="0.1.0")
_engine: Engine | None = None
_lock = threading.RLock()
PATIENTS = {p["id"]: p for p in json.loads((ROOT / "web" / "data" / "patients.json").read_text())}
COHORT = {r["id"]: r for r in json.loads((ROOT / "data" / "processed" / "cohort.json").read_text())}
MATCH_LOG = ROOT / "data" / "match_log.jsonl"  # read by pipeline/eval_retrieval.py for the Evaluation page
TZ = timezone(timedelta(hours=7))


def log_match(res: dict, kind: str = "live") -> None:
    try:
        with MATCH_LOG.open("a") as f:
            f.write(json.dumps({"ts": datetime.now(TZ).isoformat(timespec="seconds"), "kind": kind, "patient": res["patient_id"], "ms": res["iris_ms"], "shortlist": res["shortlist_size"], "verdicts": res["all_verdicts"], "top": res["matches"][0]["nct_id"] if res["matches"] else None}) + "\n")
    except OSError:
        pass


def engine() -> Engine:
    global _engine
    with _lock:
        if _engine is None:
            _engine = Engine(use_iris=True)
        return _engine


@app.on_event("startup")
def warm_up() -> None:
    """Load the engine and the embedding model in the background so the first live click is fast."""
    def go() -> None:
        from lana import embed

        engine()
        embed.encode(["warm up"], max_len=64)
        embed.encode(["warm up " * 100], max_len=512)

    threading.Thread(target=go, daemon=True).start()


class MatchRequest(BaseModel):
    patient_id: str = Field(max_length=16)


@app.get("/api/health")
def health() -> dict:
    try:
        from lana import irisdb

        iris = irisdb.version(irisdb.connect())
    except Exception as e:  # noqa: BLE001
        iris = f"unavailable: {type(e).__name__}"
    return {"ok": True, "iris": iris, "patients": len(PATIENTS), "disclaimer": "Public records plus a simulated overlay. Not a medical device."}


@app.post("/api/match")
def match(req: MatchRequest) -> dict:
    p = PATIENTS.get(req.patient_id)
    if not p:
        raise HTTPException(404, "unknown patient")
    rec = COHORT[f"{p['study']}:{p['source_id']}"]
    t = time.time()
    with _lock:
        eng = engine()
        res = eng.match(rec, build_facts(rec))
    res["iris_ms"] = round((time.time() - t) * 1000)
    res["patient_id"] = req.patient_id
    log_match(res)
    return res


app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
