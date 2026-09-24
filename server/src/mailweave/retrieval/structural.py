"""L4: structural expansion out of one thread into the threads it points at (AD A.7, D.6).

**What this rung expands on is a fact, not a resemblance.** A message whose `In-Reply-To`
or `References` names a `Message-ID` that its own thread does not hold is telling us, in
its own headers, that a parent exists somewhere else - which is what a forward, a split
thread, a subject change or a cross-posted list produces. L4 goes and asks Gmail for that
exact message by `rfc822msgid:`, and each thread it finds becomes a separate `source` with
its own map, capped at `max_source_threads = 4` (C-02e, STR-05).

**What it deliberately does not do this round.** D.6 lists four sibling-discovery signals -
normalised subject, participant overlap, forward detection, additional lexical hits - and
only the first of them is *exact*. The other three are similarity judgements: two threads
whose subjects normalise alike, or that share a participant, may be unrelated, and a source
assembled from one of them would be MailWeave asserting a relationship nobody's headers
state. Those belong with ranking and the semantic rung, which have the machinery to score
and declare a soft relationship; an exact identifier lookup does not need it and must not
pretend to it. `not_tried` carries `structural_similarity` as `not_applicable` so the
absence is in the response rather than only in this docstring.

**Scope is preserved, like every probe this repository composes** (OD-5 point 3, A9-A2).
The `q` is built through `search_region_of`, the same one derivation `ExactOperatorRung` and
`BroadeningRung` read, so a query that named a region - positively or negatively - has that
region on its L4 probes too. It is not a rule this module applies; it is a function it
calls, which is what makes it hold for a region operator nobody has added yet.

**Every id these probes return is in `H`.** They are `messages.list` calls like any other
(I-1 clause 1, amendment A2), so the disposition ledger admits them, and a thread beyond
`max_source_threads` converts its hits into `withheld` records with a thread-map affordance
rather than dropping them. Nothing in this module does that accounting; `assemble` files the
cap note and `DispositionLedger.certify` computes the set.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from mailweave.constants import MAX_SOURCE_THREADS
from mailweave.envelope.reasons import RungId
from mailweave.query.analysis import ParsedQuery, constraints_carried_whole, search_region_of
from mailweave.retrieval.ladder import Probe, why_this_q_is_not_a_probe
from mailweave.structure.reply_tree import MSG_ID_RE

#: The longest `Message-ID` L4 will put into a `q`. `MSG_ID_RE` accepts up to 902
#: characters because that is what the header grammar allows and an extraction must not
#: silently drop a long one; a *query* is a different thing, and a 900-character operator
#: value is a request nobody can read in a trace and Gmail is not documented to accept. A
#: `Message-ID` over this length is skipped and declared, never truncated - a truncated
#: identifier is not the identifier, and `rfc822msgid:` is an exact-match operator.
MAX_PROBED_MESSAGE_ID_CHARS: Final[int] = 256

#: How many unresolved parents L4 will chase. Bounded by the number of sibling sources the
#: response may carry, because a probe whose thread could not be mapped anyway is quota
#: spent for a `withheld` record we can already write from the header alone.
MAX_STRUCTURAL_PROBES: Final[int] = MAX_SOURCE_THREADS


def is_probeable(message_id_header: str) -> bool:
    """Whether this `Message-ID` can be put into a Gmail `q` as an exact operator value.

    Three conditions and they are all about the *query*, not about the header: it is a
    whole `<msg-id>` token as `MSG_ID_RE` defines one, it is short enough to be a legible
    operator value, and it carries none of Gmail's own query punctuation. The last is the
    one that matters: a `Message-ID` containing a quote or a brace would change the shape
    of the query it is pasted into, so the probe would ask something other than what this
    function's caller believes it asked.
    """
    if len(message_id_header) > MAX_PROBED_MESSAGE_ID_CHARS:
        return False
    if MSG_ID_RE.fullmatch(message_id_header) is None:
        return False
    return not any(character in message_id_header for character in '"{}()')


@dataclass(frozen=True)
class StructuralProbe:
    """One L4 probe, with the row it is being run *for* travelling beside it.

    `for_child_id` is what makes the recovered message's reason mechanical: it is disclosed
    as `reply parent of <that child>` (contract R-03, C-02d), which names the relation used
    rather than asserting relevance. A probe that arrived without it would produce a source
    whose only account of itself is "L4 found it".
    """

    probe: Probe
    for_child_id: str
    message_id_header: str


@dataclass(frozen=True)
class StructuralPlan:
    """What L4 would do, and what it declined to do, for one query.

    `skipped` and `over_cap` are separate because they are different facts with different
    dispositions: a `Message-ID` this rung cannot put in a query is a permanent inability,
    while a parent past the probe cap is one this response ran out of budget for and a
    caller can ask for again.
    """

    probes: tuple[StructuralProbe, ...]
    #: `(child id, Message-ID)` pairs whose identifier cannot be probed at all.
    skipped: tuple[tuple[str, str], ...]
    #: `(child id, Message-ID)` pairs left unprobed by `MAX_STRUCTURAL_PROBES`.
    over_cap: tuple[tuple[str, str], ...]

    @property
    def applicable(self) -> bool:
        """Whether this rung had anything at all to do. Not the same as whether it ran."""
        return bool(self.probes or self.skipped or self.over_cap)


def plan_structural_expansion(
    parsed: ParsedQuery,
    unresolved: Sequence[tuple[str, str]],
    *,
    cap: int = MAX_STRUCTURAL_PROBES,
) -> StructuralPlan:
    """The L4 probes for a query and the unresolved parents its thread maps found.

    `unresolved` is `(child message id, the Message-ID that child named)`, which is what
    `ThreadStructure.unresolved_parent_ids` yields. Order is the caller's - `assemble`
    passes chronological order - and it is preserved, so which parents fall past the cap is
    a function of the thread rather than of a set's iteration order.

    One probe per distinct `Message-ID`: two children of one absent parent are one lookup,
    and the first child named becomes the one the recovered row's reason cites.
    """
    region = search_region_of(parsed.constraints)
    probes: list[StructuralProbe] = []
    skipped: list[tuple[str, str]] = []
    over_cap: list[tuple[str, str]] = []
    seen: set[str] = set()
    for child_id, message_id_header in unresolved:
        if message_id_header in seen:
            continue
        seen.add(message_id_header)
        if not is_probeable(message_id_header):
            skipped.append((child_id, message_id_header))
            continue
        if len(probes) >= cap:
            over_cap.append((child_id, message_id_header))
            continue
        query = " ".join((*region, f"rfc822msgid:{message_id_header}"))
        if why_this_q_is_not_a_probe(query) is not None:  # pragma: no cover - unreachable
            # An `rfc822msgid:` operator always names something to match, so no composed L4
            # query can be a listing. The check is here because it is the one place a rung
            # is allowed to learn that from, and a rung that assumed it would be the next
            # instance of a guard written for the case its author had in mind.
            skipped.append((child_id, message_id_header))
            continue
        probes.append(
            StructuralProbe(
                probe=Probe(
                    rung=RungId.L4,
                    query=query,
                    why=(
                        "structural expansion: this thread holds a reply whose own "
                        "In-Reply-To/References names a Message-ID no message of it "
                        "carries (AD D.6, C-02e)"
                    ),
                    # Derived from the `q` about to be sent, through the one function that
                    # knows the rule (OD-5 point 5). An L4 probe carries the query's region
                    # and nothing else of it, so what it enforces is whatever
                    # `constraints_carried_whole` reads out of the composed string - never a
                    # list this rung writes for itself.
                    enforced=constraints_carried_whole(query, parsed.constraints),
                ),
                for_child_id=child_id,
                message_id_header=message_id_header,
            )
        )
    return StructuralPlan(probes=tuple(probes), skipped=tuple(skipped), over_cap=tuple(over_cap))
