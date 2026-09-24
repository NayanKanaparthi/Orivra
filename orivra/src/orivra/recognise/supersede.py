"""Finding the clauses that *state* a supersession, so the gates have something to gate.

`recognise.stated` holds the four gates an `obs.said.*` edge must pass - span match, clause
clearance, unique target, named asserter - and nothing was calling them, because nothing found
a candidate clause to run them over. This is that half.

**Deterministic and narrow, on purpose.** Plan §4.5: inferred edges come from a deterministic
rule set and embedding similarity; LLM claim extraction is behind an explicit opt-in with the
span-match validator. What is here is the rule set: a small set of verbs a writer uses when
replacing a prior decision, matched as whole words over the message's own text, with the
object phrase taken as the reference. No model, no scoring, no cleverness - a regex that finds
"X supersedes Y" is not deciding anything, it is nominating a clause for four gates that will
usually refuse it.

**What it does not do is the important part.** Matching a cue is not evidence of a
relationship. The clause could be negated, hypothetical, hedged, quoted from someone else, or
name a document this response does not hold; every one of those is a gate in
`recognise.stated`, and this module's output goes straight into them rather than around them.
The count of clauses this finds and the count of edges that result are different numbers, and
on most corpora the second is much smaller.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

#: The verbs, as whole words. Present tense and progressive, because that is how a writer
#: states a replacement in the message that performs it: "this supersedes", "we are replacing".
#: Past tense is deliberately absent - "we superseded the draft" reports a prior event rather
#: than performing one, and reading a report as a performance is how a graph acquires an edge
#: for a decision that happened somewhere it cannot see.
SUPERSEDE_VERBS: Final[tuple[str, ...]] = (
    "supersedes",
    "superseding",
    "replaces",
    "replacing",
    "withdraws",
    "withdrawing",
    "revokes",
    "revoking",
    "overrides",
    "overriding",
)

#: How much text after the verb may be the reference. A reference is a noun phrase - "the July
#: 3 pricing draft" - and a window this size holds one comfortably while refusing to swallow a
#: following sentence, which would hand the resolver a reference nobody wrote.
_REFERENCE_CHARS: Final[int] = 90

_VERB = re.compile(
    r"\b(?P<verb>" + "|".join(SUPERSEDE_VERBS) + r")\b(?P<rest>[^.!?;\n]*)",
    re.IGNORECASE,
)

#: Leading words a reference starts with and does not need. Stripped so "the July 3 draft" and
#: "July 3 draft" resolve alike; the resolver folds and matches on keys, and a leading article
#: is not one.
_LEADING = re.compile(r"^(?:the|our|that|this|a|an|its|their)\s+", re.IGNORECASE)


@dataclass(frozen=True)
class Nomination:
    """One clause that *might* state a supersession, with the offsets the gates need.

    "Might" is the whole of it. This carries no judgement about whether the relationship
    holds - `recognise.stated.check` decides that, and refuses most of these.
    """

    #: Offsets into the message text, for `match_span` to verify against the body itself.
    start: int
    end: int
    #: The exact substring at those offsets. Carried so the span gate compares a quotation
    #: against the source rather than trusting an offset pair.
    quoted: str
    #: The noun phrase after the verb, which the target gate resolves against candidates.
    referring_text: str
    verb: str


def nominate(text: str) -> tuple[Nomination, ...]:
    """Every clause in `text` whose shape is a stated supersession.

    Offsets are into `text` exactly as given, because the span gate re-reads them against the
    body and an offset computed over a normalised copy is an offset into a document nobody
    holds - which is the 46-character class of bug the adapter already records.
    """
    found: list[Nomination] = []
    for match in _VERB.finditer(text):
        rest = match.group("rest")
        reference = _LEADING.sub("", rest.strip())[:_REFERENCE_CHARS].strip()
        if not reference:
            # A verb with nothing after it names nothing. There is no target to resolve and
            # therefore no edge to draw, inferred or otherwise.
            continue
        start, end = match.start(), match.end()
        found.append(
            Nomination(
                start=start,
                end=end,
                quoted=text[start:end],
                referring_text=reference,
                verb=match.group("verb").lower(),
            )
        )
    return tuple(found)


__all__ = ["SUPERSEDE_VERBS", "Nomination", "nominate"]
