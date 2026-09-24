"""BM25, used only to state what the generated text is.

Two families are defined by a lexical relationship the corpus must actually have. F11's decoy
is worthless unless a lexical query reaches it *before* the evidence, and F17 is not adversarial
to query-aware selection unless the messages supporting the overturned answer outrank the reply
that overturns it. Both were asserted in prose and neither was true: the old corpus's F17
reversal was the top-scoring message in eight threads of eight (R-M2-047).

**What this is not.** A score computed here is a property of text the generator wrote against a
proxy query the generator wrote. It is not a measurement of MailWeave, it is not evidence that
any retrieval system ranks anything, and no number produced here may be used to adjust the
corpus in MailWeave's favour or against it. The corpus is built to a registered specification
and then left alone; the only permitted use of these scores is to fail generation when the
specification is not met.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Sequence

K1: float = 1.5
B: float = 0.75


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def scores(documents: Sequence[str], query: str) -> tuple[float, ...]:
    docs = [tokens(one) for one in documents]
    if not docs:
        return ()
    count = len(docs)
    average = sum(len(one) for one in docs) / count
    frequency: Counter[str] = Counter()
    for one in docs:
        frequency.update(set(one))
    terms = tokens(query)
    out: list[float] = []
    for one in docs:
        counts = Counter(one)
        total = 0.0
        for term in terms:
            if term not in counts:
                continue
            idf = math.log(1 + (count - frequency[term] + 0.5) / (frequency[term] + 0.5))
            weight = counts[term] * (K1 + 1) / (counts[term] + K1 * (1 - B + B * len(one) / average))
            total += idf * weight
        out.append(total)
    return tuple(out)


def rank_of(documents: Sequence[str], query: str, index: int) -> int:
    """1-based rank of `documents[index]`, ties broken against the document in question.

    Ties resolve pessimistically on purpose: a construction check asking whether the reversal is
    *not* the top hit should not be satisfied by a tie at the top.
    """
    values = scores(documents, query)
    target = values[index]
    better = sum(1 for position, value in enumerate(values) if value > target or
                 (value == target and position != index))
    return better + 1


__all__ = ["B", "K1", "rank_of", "scores", "tokens"]
