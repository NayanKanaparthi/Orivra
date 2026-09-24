"""A baseline that never reads the question.

**What this is for.** Five independent reads of the M2 corpus found, among other things, that
the answer is almost always the unhedged assertion naming the conversation's subject: two of 45
evidence messages carried a hedge, proposal, hearsay or reminder cue against 43 of 75
distractors, an odds ratio near 29. A solver built from that observation alone scored 24 of 39
with no query, no retrieval and no reranking. The response is not to keep grinding the corpus
until that number reaches zero - a generator that writes a decision differently from a remark
will always leave some signal - but to **measure it and publish it beside every other arm**, so
a number from the full system is read against what a system with no retrieval already gets.

**What this is not.** It is not a waiver. A failed content gate stays failed; this arm changes
what a passing number *means*, not whether the gate passed. It is also not evidence about
MailWeave: it never calls MailWeave.

**Frozen before the cases exist.** `VERSION` and the cue vocabularies below are fixed as of the
moment this file was written, which is before any of the diagnostic cases were authored. That
ordering is the whole point: a baseline tuned after seeing the cases would measure the tuning.
`tests/test_queryfree_baseline.py` pins the version and the vocabularies, so changing either is
a deliberate, visible act that invalidates comparisons made against the old one.

**The generous framing, stated plainly.** `select_within_thread` is handed the conversation the
answer is in. That is a large gift - the retrieval half of the problem is done for it - and it
is deliberate: the question this arm answers is "once the right conversation is in hand, how
much of the answer is in the *writing*?". A number from it is an upper bound on register
leakage, not a lower bound on any system's difficulty.

**The cues were harvested from this corpus.** They are not a general theory of email. This arm
therefore measures what a reader who has studied *this* corpus can do, which is the relevant
adversary for a synthetic benchmark and is not the same as what an untuned system would do.
Reported numbers must carry that qualification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Sequence

#: Bump on any change to the algorithm or the vocabularies below. Comparisons across versions
#: are not comparisons.
VERSION: Final[str] = "qf-1"

#: Cues that a sentence is *not* the settled position. Harvested from the M2 corpus.
HEARSAY: Final[tuple[str, ...]] = (
    "i spoke to", "told me", "second hand", "passing on what", "my note from a conversation",
    "said", "going from memory", "my note says",
)
PROPOSAL: Final[tuple[str, ...]] = (
    "proposing", "suggestion, not a decision", "could we go with", "putting", "tabling",
    "straw man", "open to being told no", "nothing is settled",
)
REMINDER: Final[tuple[str, ...]] = (
    "reminder", "for the agenda", "pack says", "the tracker still shows", "carrying",
    "board pack", "on the current sheet",
)
HEDGE: Final[tuple[str, ...]] = (
    "may be behind", "could be out of date", "not certain", "check before quoting",
    "have not checked", "should confirm", "old note", "indicative", "do not hold me to that",
    "unless corrected", "flagging in case", "may have moved", "i may not have the latest",
    "have not refreshed", "not pulled a fresh copy", "tell me if that is stale",
)
OBJECTION: Final[tuple[str, ...]] = (
    "i do not think", "would want to see the numbers", "not comfortable", "reads wrong to me",
    "pushing back", "i have a problem with that",
)
#: Cues that a sentence *is* the settled position.
ASSERTION: Final[tuple[str, ...]] = (
    "that is the position", "as agreed", "position:", "i have updated the record",
    "please quote that", "is the executed one", "went to signature", "we adopted",
)

#: Scores. Chosen once, from the odds ratios the fifth independent read measured, and frozen.
WEIGHTS: Final[dict[str, int]] = {
    "assertion": 2, "hearsay": -3, "proposal": -3, "objection": -3, "reminder": -2, "hedge": -1,
}

_VALUE = re.compile(
    r"\b\d{1,2} (?:January|February|March|April|May|June|July|August|September|October|"
    r"November|December) \d{4}\b|\b\d+\.\d+mm\b|\b[A-Z]\d{4}\b|\b\d{2,4}\b"
)


@dataclass(frozen=True)
class Candidate:
    """The only things this arm may look at. No role, no distractor flag, no answer key."""

    message_id: str
    position: int
    subject: str
    body: str
    epoch_ms: int


def _strip(body: str) -> str:
    return re.sub(r"\n-- \n.*$", "", body, flags=re.S).strip()


def subject_terms(subject: str) -> tuple[str, ...]:
    """Capitalised words in the subject line, which name what the conversation is about."""
    return tuple(
        one for one in re.findall(r"\b[A-Z][a-z]{2,}\b", subject)
        if one not in {"The", "Who", "What", "When", "Where", "Terms", "Budget", "Storage",
                       "Delegation", "Inspection", "Certificates", "Compliance", "Readings",
                       "Tolerance", "Dispatch", "Scheduling", "Indemnity", "Capacity",
                       "Throughput", "Attribution", "Handover", "Completing", "Transition",
                       "Allocation", "Spend", "Paperwork", "Record", "Sign", "Warehousing"}
    )


def cue_counts(text: str) -> dict[str, int]:
    lowered = text.lower()
    return {
        name: sum(1 for cue in cues if cue in lowered)
        for name, cues in (
            ("assertion", ASSERTION), ("hearsay", HEARSAY), ("proposal", PROPOSAL),
            ("objection", OBJECTION), ("reminder", REMINDER), ("hedge", HEDGE),
        )
    }


def score(candidate: Candidate, terms: Sequence[str]) -> float | None:
    """`None` when the message is not a candidate at all."""
    text = _strip(candidate.body)
    if terms and not any(one in text for one in terms):
        return None
    if not _VALUE.search(text):
        return None
    counts = cue_counts(text)
    return float(sum(WEIGHTS[name] * counts[name] for name in counts))


def select_within_thread(candidates: Sequence[Candidate]) -> str | None:
    """The message this baseline would answer with, given the conversation and no question.

    Ties break on recency, then on position, then on id - stated so the result is reproducible
    and so "latest wins" is visible as the tie-break rather than hidden as a heuristic.
    """
    if not candidates:
        return None
    terms = subject_terms(candidates[0].subject)
    scored = [
        (value, one) for one in candidates
        if (value := score(one, terms)) is not None
    ]
    if not scored:
        return None
    best = max(
        scored, key=lambda pair: (pair[0], pair[1].epoch_ms, pair[1].position,
                                 pair[1].message_id)
    )
    return best[1].message_id


def select_latest_value_bearing(candidates: Sequence[Candidate]) -> str | None:
    """The trivial contrast: the newest message carrying a value. No cues at all."""
    scored = [one for one in candidates if _VALUE.search(_strip(one.body))]
    if not scored:
        return None
    return max(scored, key=lambda one: (one.epoch_ms, one.position, one.message_id)).message_id


__all__ = [
    "ASSERTION", "HEARSAY", "HEDGE", "OBJECTION", "PROPOSAL", "REMINDER", "VERSION", "WEIGHTS",
    "Candidate", "cue_counts", "score", "select_latest_value_bearing", "select_within_thread",
    "subject_terms",
]
