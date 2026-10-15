"""Text embeddings for retrieval: an interface, the real local model, a test double, and a disk cache (D9)."""

import hashlib
import os
import re
from pathlib import Path
from typing import Protocol, Sequence

import numpy as np

from explainer import config


class Embedder(Protocol):
    name: str

    def embed_query(self, text: str) -> np.ndarray: ...

    def embed_passages(self, texts: Sequence[str]) -> np.ndarray: ...


def _normalise(vectors: np.ndarray) -> np.ndarray:
    # Unit-length vectors make cosine similarity a plain dot product.
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return vectors / np.where(norms == 0, 1, norms)


class FastEmbedEmbedder:
    """Open-weight bge-small model run locally via ONNX: no API calls, no data leaves the machine."""

    def __init__(self, model_name: str = config.EMBEDDING_MODEL, cache_dir: Path = config.MODEL_CACHE_DIR):
        # Imported here so unit tests, which use FakeEmbedder, never load ONNX or download the model.
        from fastembed import TextEmbedding

        self.name = model_name
        self._model = TextEmbedding(model_name=model_name, cache_dir=str(cache_dir))

    def embed_query(self, text: str) -> np.ndarray:
        # bge models embed queries and passages differently; mixing them up lowers retrieval quality.
        return _normalise(np.asarray(next(iter(self._model.query_embed([text]))), dtype=np.float32))

    def embed_passages(self, texts: Sequence[str]) -> np.ndarray:
        return _normalise(np.asarray(list(self._model.passage_embed(list(texts))), dtype=np.float32))


class FakeEmbedder:
    """Deterministic test double: a hashed bag of words, so texts that share words score higher."""

    def __init__(self, dim: int = 256, name: str = "fake-bag-of-words-256"):
        self.name = name
        self.dim = dim
        self.calls = 0  # lets tests prove that a code path never embeds anything

    def _vector(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dim, dtype=np.float32)
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            # sha256 rather than hash(): Python's hash() changes between runs.
            vector[int(hashlib.sha256(word.encode()).hexdigest()[:8], 16) % self.dim] += 1
        return vector

    def embed_query(self, text: str) -> np.ndarray:
        self.calls += 1
        return _normalise(self._vector(text))

    def embed_passages(self, texts: Sequence[str]) -> np.ndarray:
        self.calls += 1
        return _normalise(np.stack([self._vector(t) for t in texts]))


def cache_key(passages_path: Path, model_name: str) -> str:
    """Changes whenever the passages file or the model changes, so stale vectors are never reused."""
    digest = hashlib.sha256(passages_path.read_bytes())
    digest.update(b"\0" + model_name.encode())
    return digest.hexdigest()


def passage_vectors(ids: Sequence[str], texts: Sequence[str], embedder: Embedder,
                    passages_path: Path, cache_path: Path = config.EMBEDDINGS_CACHE) -> np.ndarray:
    """Return one vector per passage, from the cache file if it is still valid, else embed and save."""
    key = cache_key(passages_path, embedder.name)
    if cache_path.exists():
        # allow_pickle=False: a cache file must never be able to run code when loaded.
        with np.load(cache_path, allow_pickle=False) as cached:
            if str(cached["key"]) == key and cached["ids"].tolist() == list(ids):
                return cached["vectors"]
    vectors = embedder.embed_passages(texts)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temp file and rename, so a crash mid-write can't leave a half-written cache.
    tmp_path = cache_path.with_name(cache_path.stem + ".tmp.npz")
    np.savez(tmp_path, key=key, ids=np.array(list(ids)), vectors=vectors)
    os.replace(tmp_path, cache_path)
    return vectors
