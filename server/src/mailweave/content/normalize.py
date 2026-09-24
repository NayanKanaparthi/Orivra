"""NFKC, whitespace collapse and recorded truncation (AD D.4a 7, D.4 budget ladder)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_WS_RUN = re.compile(r"[ \t\f\v ]+")
_BLANK_RUNS = re.compile(r"\n{3,}")
_TRAILING_WS = re.compile(r"[ \t]+\n")


@dataclass(frozen=True)
class Normalised:
    text: str
    removed_chars: int
    changed: bool


def normalise(text: str) -> Normalised:
    """NFKC, then whitespace collapse. No lowercasing: that is model-dependent."""
    folded = unicodedata.normalize("NFKC", text)
    collapsed = _WS_RUN.sub(" ", folded)
    collapsed = _TRAILING_WS.sub("\n", collapsed)
    collapsed = _BLANK_RUNS.sub("\n\n", collapsed).strip()
    removed = max(0, len(text) - len(collapsed))
    return Normalised(text=collapsed, removed_chars=removed, changed=collapsed != text)


def count_tokens(text: str) -> int:
    """Whitespace token count.

    This is the *reduction accounting* unit, not the disclosure tokenizer: DISC-04's
    budget is measured with a pinned tokenizer that belongs to a later workstream, and
    inventing one here would create a de facto bar. Whitespace tokens are stated as such
    everywhere they are reported.
    """
    return len(text.split())


@dataclass(frozen=True)
class HeadTruncation:
    text: str
    kept_tokens: int
    removed_chars: int
    truncated: bool


def head_truncate(text: str, max_tokens: int) -> HeadTruncation:
    """Keep the first `max_tokens` whitespace tokens; report what that cost.

    Head truncation is A.9a step 3/4; the caller decides *when* it fires, this function
    only makes the removal countable.
    """
    if max_tokens < 0:
        raise ValueError("max_tokens must be non-negative")
    tokens = text.split()
    if len(tokens) <= max_tokens:
        return HeadTruncation(text=text, kept_tokens=len(tokens), removed_chars=0, truncated=False)
    kept = " ".join(tokens[:max_tokens])
    return HeadTruncation(
        text=kept,
        kept_tokens=max_tokens,
        removed_chars=len(text) - len(kept),
        truncated=True,
    )
