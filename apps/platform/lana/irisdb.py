"""InterSystems IRIS access: vector store for trial chunks, queried with VECTOR_COSINE."""
from __future__ import annotations

import os

import numpy as np

HOST = os.environ.get("LANA_IRIS_HOST", "127.0.0.1")
PORT = int(os.environ.get("LANA_IRIS_PORT", "1974"))
NAMESPACE = os.environ.get("LANA_IRIS_NAMESPACE", "USER")
USER = os.environ.get("LANA_IRIS_USER", "_SYSTEM")
PASSWORD = os.environ.get("LANA_IRIS_PASSWORD", "SYS")
DIM = 1024


def connect():
    import iris  # intersystems-irispython

    return iris.connect(HOST, PORT, NAMESPACE, USER, PASSWORD)


def vec_str(v: np.ndarray) -> str:
    return ",".join(f"{x:.6g}" for x in v)


def create_schema(conn) -> None:
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS Lana.Chunk")
    cur.execute(
        f"""CREATE TABLE Lana.Chunk (
            Id INTEGER PRIMARY KEY,
            Trial VARCHAR(20),
            Kind VARCHAR(12),
            Ref VARCHAR(40),
            Txt VARCHAR(4000),
            Vec VECTOR(FLOAT, {DIM}))"""
    )
    cur.execute("CREATE INDEX ChunkTrial ON Lana.Chunk (Trial)")
    conn.commit()


def load_chunks(conn, chunks: list[dict], vectors: np.ndarray, batch: int = 500) -> None:
    cur = conn.cursor()
    sql = f"INSERT INTO Lana.Chunk (Id, Trial, Kind, Ref, Txt, Vec) VALUES (?, ?, ?, ?, ?, TO_VECTOR(?, FLOAT, {DIM}))"
    for i in range(0, len(chunks), batch):
        rows = [
            (i + j, c["trial"], c["kind"], c["ref"] or "", c["text"][:4000], vec_str(vectors[i + j]))
            for j, c in enumerate(chunks[i : i + batch])
        ]
        cur.executemany(sql, rows)
        conn.commit()


def search(conn, query_vec: np.ndarray, top: int = 300) -> list[dict]:
    """Nearest chunks to the query by cosine similarity (computed inside IRIS)."""
    cur = conn.cursor()
    cur.execute(
        f"SELECT TOP {int(top)} Trial, Kind, Ref, Txt, VECTOR_COSINE(Vec, TO_VECTOR(?, FLOAT, {DIM})) AS Sim "
        "FROM Lana.Chunk ORDER BY Sim DESC",
        [vec_str(query_vec)],
    )
    return [{"trial": r[0], "kind": r[1], "ref": r[2], "text": r[3], "sim": float(r[4])} for r in cur.fetchall()]


def version(conn) -> str:
    cur = conn.cursor()
    cur.execute("SELECT $ZVERSION")
    return cur.fetchone()[0]
