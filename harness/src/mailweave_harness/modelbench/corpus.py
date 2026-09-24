"""Deterministic synthetic text at realistic pool-row lengths, carrying no mail content.

PF-4 measures embedding cost at "real body/snippet lengths" (AD F). It must do that without
reading anyone's mail: a benchmark that needs the owner's inbox to produce a number is a
benchmark that cannot run on a clean machine, and OD-4 would have something to say about
persisting what it read.

So the texts are generated from a seeded RNG over a neutral word list, at the two length
distributions the pool actually sees:

  * **snippet rows** - `subject + participants + Gmail snippet`, which is what D.5's
    optimistic branch embeds now that PF-2 settled the snippet question;
  * **body-head rows** - `subject + participants + first 400 chars of cleaned body`, D.5's
    fallback branch, kept because the fallback is still the branch a future PF-2 result
    could select.

Length is what costs time in a transformer, not meaning, so synthetic text of the right
length is a sound instrument for latency. It is **not** a sound instrument for quality, and
this module says so rather than letting a later reader assume otherwise: H1/H2/H3 measure
quality on F1-F17 against the real corpus.
"""

from __future__ import annotations

import random
from typing import Final

#: Neutral, domain-free vocabulary. Deliberately not mail-like: nothing here should read as
#: a plausible subject line if it ever lands in a log.
_WORDS: Final[tuple[str, ...]] = (
    "alpha",
    "bravo",
    "charlie",
    "delta",
    "echo",
    "foxtrot",
    "golf",
    "hotel",
    "india",
    "juliet",
    "kilo",
    "lima",
    "mike",
    "november",
    "oscar",
    "papa",
    "quebec",
    "romeo",
    "sierra",
    "tango",
    "uniform",
    "victor",
    "whiskey",
    "xray",
    "yankee",
    "zulu",
    "north",
    "south",
    "east",
    "west",
    "upper",
    "lower",
    "inner",
    "outer",
    "forward",
    "reverse",
    "steady",
    "rolling",
    "narrow",
    "broad",
    "shallow",
    "deep",
    "bright",
    "quiet",
    "sudden",
    "gradual",
    "constant",
    "variable",
)

#: Observed shapes. A Gmail snippet is capped near 200 characters; D.4a's body head is 400.
SNIPPET_CHARS: Final[int] = 200
BODY_HEAD_CHARS: Final[int] = 400
#: Subject plus participant addresses, which every pool row carries whichever branch is live.
PREAMBLE_CHARS: Final[int] = 120


def _text(rng: random.Random, chars: int) -> str:
    parts: list[str] = []
    length = 0
    while length < chars:
        word = rng.choice(_WORDS)
        parts.append(word)
        length += len(word) + 1
    return " ".join(parts)[:chars]


def pool_rows(count: int, *, seed: int = 20260911, body_head: bool = False) -> list[str]:
    """`count` rows at the live branch's length, reproducible from `seed`.

    Same seed, same texts, so two arms of PF-4b are measured on identical input rather than
    on two samples that merely came from the same distribution.
    """
    rng = random.Random(seed)
    width = BODY_HEAD_CHARS if body_head else SNIPPET_CHARS
    return [f"{_text(rng, PREAMBLE_CHARS)} | {_text(rng, width)}" for _ in range(count)]


def rerank_pairs(count: int, *, seed: int = 20260911) -> tuple[str, list[str]]:
    """One query and `count` candidates, at the length a shortlist row actually carries."""
    rng = random.Random(seed + 1)
    query = _text(rng, 60)
    return query, [_text(rng, BODY_HEAD_CHARS) for _ in range(count)]
