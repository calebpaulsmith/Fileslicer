"""Pluggable text embedders for the local hybrid RAG.

This module is deliberately self-contained (standard library only, no ``packer``
imports) so it can be copied verbatim into a generated ``mcp_server/`` directory
and imported there to embed queries at retrieval time.

Backends, resolved from a string spec:

- ``"hashing"`` (default) — a deterministic, offline feature-hashing embedder.
  No API key, no network, no extra dependency. Quality is lexical-only (it
  approximates bag-of-words overlap), so it is a *placeholder* that makes the
  hybrid plumbing work and keeps appeal text on the local machine. For real
  semantic retrieval, choose an API backend.
- ``"openai:<model>"`` — OpenAI embeddings (e.g. ``openai:text-embedding-3-small``).
  Lazily imports the ``openai`` package and reads ``OPENAI_API_KEY``. Sending
  text to OpenAI leaves the local machine — opt-in only.
- ``"voyage:<model>"`` — Voyage embeddings (e.g. ``voyage:voyage-3``). Lazily
  imports ``voyageai`` and reads ``VOYAGE_API_KEY``. Also sends text off-machine.
- ``"local:<model>"`` — local sentence-transformers (bge/e5), e.g.
  ``local:bge-small-en-v1.5`` or ``local:e5-base-v2``. Lazily imports
  ``sentence-transformers`` and runs inference on-machine (a one-time model
  download is required on first use). e5/bge models use asymmetric
  query/passage prefixes for retrieval quality.

Every backend's ``embed(texts, is_query=False)`` accepts ``is_query`` so query
embeddings can be treated differently from passage embeddings where the model
asks for it (e5/bge prefixes, Voyage ``input_type``).
"""

from __future__ import annotations

import hashlib
import math
import os
from typing import Dict, List, Optional, Sequence

DEFAULT_SPEC = "hashing"
_DEFAULT_HASHING_DIM = 256


class EmbedderError(RuntimeError):
    """Raised when an embedder cannot be constructed or used."""


class HashingEmbedder:
    """Deterministic, dependency-free feature-hashing embedder (offline).

    Each token is hashed to a dimension and a sign; the per-text vector is the
    L2-normalized sum. Cosine similarity then reflects token overlap. Weak but
    real, and it never leaves the machine.
    """

    backend = "hashing"

    def __init__(self, dim: int = _DEFAULT_HASHING_DIM) -> None:
        self.dim = int(dim)
        self.model = f"hashing-{self.dim}"

    @property
    def name(self) -> str:
        return f"hashing:{self.dim}"

    def _vector(self, text: str) -> List[float]:
        vec = [0.0] * self.dim
        for token in text.lower().split():
            digest = hashlib.md5(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def embed(self, texts: Sequence[str], is_query: bool = False) -> List[List[float]]:
        return [self._vector(t or "") for t in texts]


class OpenAIEmbedder:
    """OpenAI embeddings backend (lazy import, reads ``OPENAI_API_KEY``)."""

    backend = "openai"

    def __init__(self, model: str = "text-embedding-3-small", api_key: Optional[str] = None) -> None:
        self.model = model
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self._api_key:
            raise EmbedderError(
                "OPENAI_API_KEY is not set; cannot use the OpenAI embedder."
            )
        try:
            import openai  # noqa: F401
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise EmbedderError(
                "The 'openai' package is required for the OpenAI embedder "
                "(pip install openai)."
            ) from exc
        from openai import OpenAI

        self._client = OpenAI(api_key=self._api_key)
        self.dim = _OPENAI_DIMS.get(model, 1536)

    @property
    def name(self) -> str:
        return f"openai:{self.model}"

    def embed(self, texts: Sequence[str], is_query: bool = False) -> List[List[float]]:
        out: List[List[float]] = []
        for batch in _batched(list(texts), 128):
            resp = self._client.embeddings.create(model=self.model, input=batch)
            out.extend(item.embedding for item in resp.data)
        return out


class VoyageEmbedder:
    """Voyage embeddings backend (lazy import, reads ``VOYAGE_API_KEY``)."""

    backend = "voyage"

    def __init__(self, model: str = "voyage-3", api_key: Optional[str] = None) -> None:
        self.model = model
        self._api_key = api_key or os.environ.get("VOYAGE_API_KEY")
        if not self._api_key:
            raise EmbedderError(
                "VOYAGE_API_KEY is not set; cannot use the Voyage embedder."
            )
        try:
            import voyageai
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise EmbedderError(
                "The 'voyageai' package is required for the Voyage embedder "
                "(pip install voyageai)."
            ) from exc
        self._client = voyageai.Client(api_key=self._api_key)
        self.dim = _VOYAGE_DIMS.get(model, 1024)

    @property
    def name(self) -> str:
        return f"voyage:{self.model}"

    def embed(self, texts: Sequence[str], is_query: bool = False) -> List[List[float]]:
        out: List[List[float]] = []
        input_type = "query" if is_query else "document"
        for batch in _batched(list(texts), 128):
            resp = self._client.embed(batch, model=self.model, input_type=input_type)
            out.extend(resp.embeddings)
        return out


# Short name -> (HuggingFace repo, embedding dim). Unknown names are passed to
# sentence-transformers verbatim and the dim is read from the loaded model.
_LOCAL_MODELS = {
    "bge-small-en-v1.5": ("BAAI/bge-small-en-v1.5", 384),
    "bge-base-en-v1.5": ("BAAI/bge-base-en-v1.5", 768),
    "bge-large-en-v1.5": ("BAAI/bge-large-en-v1.5", 1024),
    "e5-small-v2": ("intfloat/e5-small-v2", 384),
    "e5-base-v2": ("intfloat/e5-base-v2", 768),
    "e5-large-v2": ("intfloat/e5-large-v2", 1024),
}
_DEFAULT_LOCAL_MODEL = "bge-small-en-v1.5"
_BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


def _local_family(model: str) -> str:
    name = model.lower()
    if "e5" in name:
        return "e5"
    if "bge" in name:
        return "bge"
    return ""


def _local_prefix(text: str, is_query: bool, family: str) -> str:
    """Apply the model family's asymmetric query/passage prefix for retrieval."""
    if family == "e5":
        return ("query: " if is_query else "passage: ") + text
    if family == "bge" and is_query:
        return _BGE_QUERY_INSTRUCTION + text
    return text


class SentenceTransformerEmbedder:
    """Local bge/e5 embeddings via sentence-transformers (on-machine inference)."""

    backend = "local"

    def __init__(self, model: str = _DEFAULT_LOCAL_MODEL) -> None:
        repo, dim = _LOCAL_MODELS.get(model, (model, 0))
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise EmbedderError(
                "The 'sentence-transformers' package is required for the local "
                "embedder (pip install sentence-transformers)."
            ) from exc
        self._model_obj = SentenceTransformer(repo)
        self.model = model
        self.dim = dim or int(self._model_obj.get_sentence_embedding_dimension())
        self._family = _local_family(model)

    @property
    def name(self) -> str:
        return f"local:{self.model}"

    def embed(self, texts: Sequence[str], is_query: bool = False) -> List[List[float]]:
        prepared = [_local_prefix(t or "", is_query, self._family) for t in texts]
        vectors = self._model_obj.encode(
            prepared, normalize_embeddings=True, convert_to_numpy=True
        )
        return [[float(x) for x in row] for row in vectors]


_OPENAI_DIMS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}
_VOYAGE_DIMS = {
    "voyage-3": 1024,
    "voyage-3-lite": 512,
    "voyage-3-large": 1024,
}


def _batched(items: List[str], size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def resolve_embedder(spec: Optional[str]) -> "HashingEmbedder | OpenAIEmbedder | VoyageEmbedder":
    """Build an embedder from a spec string (``backend`` or ``backend:model``).

    An empty/None spec, or ``"hashing"``, yields the offline hashing embedder.
    Unknown backends raise ``EmbedderError``.
    """
    spec = (spec or DEFAULT_SPEC).strip()
    if ":" in spec:
        backend, model = spec.split(":", 1)
    else:
        backend, model = spec, ""
    backend = backend.lower()
    if backend == "hashing":
        return HashingEmbedder(int(model) if model.isdigit() else _DEFAULT_HASHING_DIM)
    if backend == "openai":
        return OpenAIEmbedder(model or "text-embedding-3-small")
    if backend == "voyage":
        return VoyageEmbedder(model or "voyage-3")
    if backend in ("local", "st", "sentence-transformers"):
        return SentenceTransformerEmbedder(model or _DEFAULT_LOCAL_MODEL)
    raise EmbedderError(
        f"Unknown embedder backend {backend!r}. Use 'hashing', 'openai:<model>', "
        "'voyage:<model>', or 'local:<model>'."
    )


def embedder_meta(embedder) -> Dict[str, object]:
    """Return the JSON-serializable identity of an embedder (for storage)."""
    return {"backend": embedder.backend, "model": embedder.model, "dim": embedder.dim}


def build_embedder_from_meta(meta: Dict[str, object]):
    """Reconstruct the embedder described by :func:`embedder_meta` (used by the server)."""
    backend = str(meta.get("backend", "hashing"))
    model = str(meta.get("model", ""))
    if backend == "hashing":
        return HashingEmbedder(int(meta.get("dim", _DEFAULT_HASHING_DIM)))
    if backend == "openai":
        return OpenAIEmbedder(model or "text-embedding-3-small")
    if backend == "voyage":
        return VoyageEmbedder(model or "voyage-3")
    if backend == "local":
        return SentenceTransformerEmbedder(model or _DEFAULT_LOCAL_MODEL)
    raise EmbedderError(f"Unknown embedder backend {backend!r} in stored metadata.")
