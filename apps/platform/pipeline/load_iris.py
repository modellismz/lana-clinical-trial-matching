"""Create the Lana.Chunk table in InterSystems IRIS and load every trial chunk with its bge-m3 vector."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lana import irisdb  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "data" / "processed"


def main() -> None:
    chunks = json.loads((OUT / "chunks.json").read_text())
    vecs = np.load(OUT / "chunk_vectors.npy")
    conn = irisdb.connect()
    print(irisdb.version(conn))
    irisdb.create_schema(conn)
    t = time.time()
    irisdb.load_chunks(conn, chunks, vecs)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM Lana.Chunk")
    print(f"loaded {cur.fetchone()[0]} chunks in {time.time()-t:.0f}s")
    # sanity check: a chunk is its own nearest neighbour
    hit = irisdb.search(conn, vecs[5], top=3)
    print("self-query top hit sim:", round(hit[0]["sim"], 4), hit[0]["trial"])


if __name__ == "__main__":
    main()
