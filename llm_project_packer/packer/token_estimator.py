"""Token estimation utilities.

Uses tiktoken's cl100k_base encoding when available, otherwise falls back to
a simple chars / 4 heuristic. The tool must work without tiktoken installed.
"""

from __future__ import annotations

from typing import Optional

_TIKTOKEN_ENCODER = None
_TIKTOKEN_AVAILABLE: Optional[bool] = None


def _load_encoder():
    """Lazily load tiktoken's cl100k_base encoder, caching the result."""
    global _TIKTOKEN_ENCODER, _TIKTOKEN_AVAILABLE
    if _TIKTOKEN_AVAILABLE is False:
        return None
    if _TIKTOKEN_ENCODER is not None:
        return _TIKTOKEN_ENCODER
    try:
        import tiktoken  # type: ignore

        _TIKTOKEN_ENCODER = tiktoken.get_encoding("cl100k_base")
        _TIKTOKEN_AVAILABLE = True
        return _TIKTOKEN_ENCODER
    except Exception:
        _TIKTOKEN_AVAILABLE = False
        return None


def estimate_tokens(text: str) -> int:
    """Return an estimated token count for ``text``.

    Uses tiktoken if installed; otherwise approximates ``len(text) / 4``.
    """
    if not text:
        return 0
    encoder = _load_encoder()
    if encoder is not None:
        try:
            return len(encoder.encode(text))
        except Exception:
            # Fall through to heuristic on any encoding error.
            pass
    # Heuristic: ~4 chars per token. Round up so empty-ish inputs still register.
    return max(1, (len(text) + 3) // 4)


def estimator_backend() -> str:
    """Return a short label describing which backend is in use."""
    return "tiktoken (cl100k_base)" if _load_encoder() is not None else "heuristic (chars/4)"
