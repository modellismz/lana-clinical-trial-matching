"""Embedding model wrapper. BAAI/bge-m3: multilingual (Thai and English), 1024-dim, normalised."""
from __future__ import annotations

import numpy as np

MODEL_NAME = "BAAI/bge-m3"
DIM = 1024
_model = None


def model(max_len: int = 256):
    global _model
    if _model is None:
        import torch
        from sentence_transformers import SentenceTransformer

        device = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
        _model = SentenceTransformer(MODEL_NAME, device=device)
    _model.max_seq_length = max_len
    return _model


def encode(texts: list[str], max_len: int = 256, batch_size: int = 48) -> np.ndarray:
    m = model(max_len)
    return m.encode(texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=len(texts) > 200).astype("float32")
