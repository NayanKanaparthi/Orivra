"""Closed vocabularies of the response envelope (AD D.2, contract R-02/R-04/R-08)."""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class Role(StrEnum):
    """Contract R-02, the closed seven-value set. PART-07 scores all seven."""

    MATCHED = "matched"
    CONTEXT = "context"
    PARENT = "parent"
    CHILD = "child"
    REQUESTED = "requested"
    STUB = "stub"
    DERIVED = "derived"


class Depth(StrEnum):
    """Contract R-04. `raw` is never inline and is not independently requestable (D.1)."""

    STUB = "stub"
    SNIPPET = "snippet"
    BODY_CLEAN = "body_clean"
    BODY_FULL = "body_full"
    RAW = "raw"


class Outcome(StrEnum):
    """OD-2. The response's own account of what happened, never an inference for the caller."""

    ANSWERED = "answered"
    NOT_FOUND = "not_found"
    INCONCLUSIVE = "inconclusive"


class NotTriedWhy(StrEnum):
    """AD D.2's `not_tried[].why`: why a rung this ladder has did not run.

    **Round 15 left a question here and round 22 rules on it, so the reasoning is written
    down rather than implied by the code.** The published vocabulary is
    `not_applicable | budget | cap | timeout | error`, and it has no value for the commonest
    non-blocking case of all: *the policy declined to run this rung because a D.3 stopping
    rule had already settled the query on evidence found.* Round 15 used `not_applicable`
    for it and never emitted `not_found`, so OD-2's machine-checkable rule was never
    violated - the vocabulary was wrong without anything going red, which is the exact shape
    of defect this project keeps producing.

    **The ruling: `not_applicable` is the wrong word, and `stopped_on_evidence` is added.**
    Three reasons, in the order they decide it.

    1. *`not_applicable` states something false.* Its meaning is "this rung could not have
       helped this query" - that is what a caller reads it as, and it is why it is the one
       value compatible with `not_found`. L5 after D.3 rule 1 stopped the ladder is not a
       rung that could not have helped; it is a rung nobody needed. The two are different
       facts about the mailbox, and writing the second under the first's name is a claim
       wider than the code, in a field a caller branches on.
    2. *The two have different remedies, which is this project's test for whether a
       distinction is real.* `not_applicable` has no affordance and can have none: no budget
       reaches a rung that does not apply. `stopped_on_evidence` has one - WS-15's
       `force_rungs`, which "can only add rungs" - so a caller who does not trust the stop
       can get the rung run. A vocabulary that cannot tell "there is nothing more" from
       "there is more and you may have it" is a vocabulary that loses the affordance.
    3. *It is safe against OD-2 twice over, and the code enforces the second one.* A D.3 stop
       rule fires only on non-zero evidence (rules 1 and 1b need `exact_signal_match` with
       at least one hit; rule 2 needs `hit_count in [1,5]`; rule 3 needs
       `sufficiency == sufficient`), so `not_found`'s own second conjunct - "and no evidence
       was found" - is already false wherever this value can appear. Rather than rest on
       that argument, `stopped_on_evidence` joins the set below, so a response carrying one
       is refused `not_found` mechanically. The cost of the belt-and-braces is nil: no
       response that could honestly say `not_found` can carry this value.

    So: one value that permits `not_found`, and five that forbid it - four because the rung
    *could not be reached*, and one because the query was *already answered*.
    """

    #: The rung could not have helped this query at all: nothing to decompose, no unresolved
    #: parent to chase, no identifier to probe. No budget reaches it, so it carries no
    #: affordance. **This is the only value compatible with `outcome: not_found`.**
    NOT_APPLICABLE = "not_applicable"
    #: The rung was applicable and was not run because a D.3 stopping rule had already
    #: settled the query on evidence found. Carries a `force_rungs` affordance. See the
    #: ruling in this class's docstring; this member is an implementer's addition to AD
    #: D.2's published list, argued there and recorded as such in
    #: `docs/reviews/ROUND_22/IMPLEMENTER.md`.
    STOPPED_ON_EVIDENCE = "stopped_on_evidence"
    BUDGET = "budget"
    CAP = "cap"
    TIMEOUT = "timeout"
    ERROR = "error"


#: AD D.2's published `not_tried[].why` values, verbatim, so the addition above is visible
#: as an addition rather than absorbed into the enum.
PUBLISHED_NOT_TRIED: Final[frozenset[NotTriedWhy]] = frozenset(
    {
        NotTriedWhy.NOT_APPLICABLE,
        NotTriedWhy.BUDGET,
        NotTriedWhy.CAP,
        NotTriedWhy.TIMEOUT,
        NotTriedWhy.ERROR,
    }
)

#: The `not_tried` reasons that forbid `outcome: not_found` (OD-2). Derived as the
#: complement of `not_applicable` rather than listed, so a value added later forbids
#: `not_found` until somebody argues that it should not - which is the safe default and the
#: opposite of the one a hand-written list produces (the same derivation
#: `DECLARED_GAP_LINKAGES` uses, for the same reason).
BLOCKING_NOT_TRIED: Final[frozenset[NotTriedWhy]] = frozenset(NotTriedWhy) - {
    NotTriedWhy.NOT_APPLICABLE
}


class RecheckedOperator(StrEnum):
    """AD D.9's closed local re-check subset, as a wire vocabulary.

    **A closed enum rather than a string tuple, and that is a retention decision.** This
    list reaches the wire inside `RecencyContext`, and a `tuple[str, ...]` there would be a
    parameter caller-derived or mail-derived text could travel through - exactly what
    R-SEC-032 closed for every other reason parameter. There are four members because D.9
    names four operator families and says the subset is closed; a fifth is an architecture
    amendment, not a refactor.
    """

    PARTICIPANT = "from/to/cc"
    DATE = "after/before"
    HAS_ATTACHMENT = "has:attachment"
    LABEL = "label:"


class WithheldCap(StrEnum):
    """The caps that can convert a hit into a withheld record (AD A.7a table)."""

    MAX_HIT_THREADS = "max_hit_threads"
    #: L4 recovered more sibling threads than `max_source_threads` (AD D.6, C-02e). The
    #: hits in them are withheld with a thread-map affordance, never dropped.
    MAX_SOURCE_THREADS = "max_source_threads"
    MAX_POOL_THREADS = "max_pool_threads"
    MAX_POOL_MESSAGES = "max_pool_messages"
    #: **An implementer's addition to A.7a's table, argued rather than assumed.** A.7a names
    #: `max_pool_threads` for "a D.5 step-(b) probe returned IDs in threads the pool cap
    #: excluded" - the threads the pool never *read*. It has no name for the other half of
    #: the same rung: a thread the pool did read, scored, and whose messages the shortlist
    #: did not select. Those ids are in `H` (the probe admitted them) and are not disclosed
    #: (D.5: "the pool creates no source, no mini-map and no stub rows"), so without a cap
    #: name they would be a withholding the response could not account for - and the
    #: certificate refuses that, which is how this gap was found.
    #:
    #: Its remedy is **not** a wider `k`: `max_rerank_pairs` is the shortlist size PF-4
    #: measured the cross-encoder against, and raising it past the measurement would spend a
    #: latency bound to recover one thread. The remedy is the thread map, which returns that
    #: thread's content directly - a concrete executable call (R-07) rather than a dial.
    MAX_RERANK_PAIRS = "max_rerank_pairs"
    MAX_RECENCY_FETCH = "max_recency_fetch"
    #: **The second implementer's addition to A.7a's table** (the first is
    #: `MAX_RERANK_PAIRS` above), and the same kind of gap. `history.list` admits every
    #: `messagesAdded` id into `H` under clause H-hist, so a candidate LR fetched and the
    #: closed local re-check found to *contradict* a constraint the query stated is
    #: retrieved, not disclosed, and owed an account. A.7a has no name for it: it is not a
    #: cap - nothing was bounded - and reporting it under `max_recency_fetch` would say the
    #: fetch bound stopped a message the fetch bound did not stop.
    #:
    #: Its remedy is a direct read of that message, which is a concrete executable call
    #: (R-07) and is the honest one: the server is not refusing to show it, it is declining
    #: to attribute it to a query whose constraints it fails.
    RECENCY_RECHECK_EXCLUDED = "recency_recheck_excluded"
    MAX_QUOTA_UNITS = "max_quota_units"
    MAX_API_CALLS = "max_api_calls"
    MAX_SERVER_MS = "max_server_ms"
    MAX_SEMANTIC_MS = "max_semantic_ms"
    DISCLOSED_TOKEN_CEILING = "disclosed_token_ceiling"
    #: A run that stands for another **page** of a thread map, or for the unrequested part
    #: of a thread an explicit read is inside (navigation redesign, 2026-09-14). Not a cap
    #: that fired: the response was planned as a page from the start, and the members are one
    #: continuation away. Named so a reader can tell a page boundary from a ceiling that bit.
    MAP_PAGE = "map_page"
    PARTIAL_SOURCE_FAILURE = "partial_source_failure"


class WithheldGranularity(StrEnum):
    """At what granularity a withholding is accounted for on the wire.

    **The rule (round 29, R-MCP-033): a withheld record is written at the granularity of the
    call that recovers it.** A message the caller can pass to `mailweave_get_messages` is worth
    naming one by one. A message inside a thread that was never mapped is not: the only call
    that reaches it is `mailweave_thread_map` on its thread, so forty-five records pointing at
    the same three thread maps say nothing three records with exact counts do not, and they say
    it in twenty-three thousand characters.

    This does not weaken R-06, which governs *"wherever the map is present"*: where a map
    exists the rows stay rows. Grouping applies only where no map exists to carry a stub.
    """

    #: One record per message, naming the id. The recovery call names messages.
    MESSAGE = "message"
    #: One record per (thread, cap), carrying an exact count. The recovery call names a thread.
    THREAD = "thread"

    @classmethod
    def of(cls, tool: ToolName) -> WithheldGranularity:
        """Read the granularity off the recovery call itself.

        The rule is "the granularity of the call that recovers it", so the call decides, and
        the decision is one comparison rather than a table of caps that has to be kept in
        step with the affordances those caps offer. A thread map returns a thread; everything
        else this surface offers - an unabridged read, a wider search, a message expansion -
        is answered per message or per request, and a group would attach a count to a call
        that cannot use one.

        The first version of this keyed on the cap name instead, and it was wrong within an
        hour: `max_api_calls` withholdings travel the same sweep as `max_hit_threads` ones and
        carry a *search-budget* affordance, not a map, so grouping them by thread would have
        offered a thread map nobody had said would help.
        """
        return cls.THREAD if tool is ToolName.THREAD_MAP else cls.MESSAGE


class BudgetCapName(StrEnum):
    """Values `budget_caps_hit` may carry (AD A.7 cap table + D.11 governor codes)."""

    MAX_QUOTA_UNITS = "max_quota_units"
    MAX_API_CALLS = "max_api_calls"
    MAX_HTTP_REQUESTS = "max_http_requests"
    MAX_PAGES_PER_QUERY = "max_pages_per_query"
    MAX_HIT_THREADS = "max_hit_threads"
    MAX_SOURCE_THREADS = "max_source_threads"
    MAX_POOL_THREADS = "max_pool_threads"
    MAX_POOL_MESSAGES = "max_pool_messages"
    MAX_RERANK_PAIRS = "max_rerank_pairs"
    MAX_RELAX_PROBES = "max_relax_probes"
    MAX_RECENCY_FETCH = "max_recency_fetch"
    MAX_BODY_FETCHES = "max_body_fetches"
    MAX_SERVER_MS = "max_server_ms"
    MAX_SEMANTIC_MS = "max_semantic_ms"
    DISCLOSED_TOKEN_CEILING = "disclosed_token_ceiling"
    PROCESS_QUOTA_WAIT = "process_quota_wait"
    PROCESS_QUOTA_REFUSED = "process_quota_refused"


class ToolName(StrEnum):
    """The four compile-time-constant tools of AD D.1. An affordance names one of these."""

    SEARCH = "mailweave_search"
    THREAD_MAP = "mailweave_thread_map"
    GET_MESSAGES = "mailweave_get_messages"
    GET_ATTACHMENT = "mailweave_get_attachment"


class Trust(StrEnum):
    """Contract R-09 provenance labelling."""

    UNTRUSTED_THIRD_PARTY = "untrusted_third_party"
    UNTRUSTED_SELF_AUTHORED = "untrusted_self_authored"


class ContentSource(StrEnum):
    GMAIL_BODY = "gmail_body"
    GMAIL_SNIPPET = "gmail_snippet"
    #: A header value, fenced like any other mail-derived string (INJ-01). Added with the
    #: row-level identity block: a display name and an `Authentication-Results` record are
    #: both strings that came out of a header, and calling either of them a body would be
    #: this response misstating where its own text came from.
    GMAIL_HEADER = "gmail_header"


class Sufficiency(StrEnum):
    """AD A.8's per-rung evidence verdict. Deliberately NOT the same field as `outcome`."""

    SUFFICIENT = "sufficient"
    AMBIGUOUS = "ambiguous"
    INSUFFICIENT = "insufficient"


class Completeness(StrEnum):
    """Contract R-08 / T-3: MailWeave never asserts absolute completeness."""

    AS_REPORTED_BY_SOURCE = "as_reported_by_source"


class EmptyDiagnosisStatus(StrEnum):
    """ADV-105's three states are (status, restores) pairs; see `EmptyDiagnosis`."""

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class Linkage(StrEnum):
    """How one message's reply parent was determined, or which gap stands in its place (AD D.6).

    A closed vocabulary rather than a prose label, for the reason `MailboxProvenance` is a
    field rather than a mention (OD-5): a caller has to be able to branch on "this message
    was not linked" without reading a sentence. Two members are links; the rest are
    **declared gaps**, and every one of them names what was missing rather than what was
    guessed.

    `NO_REPLY_HEADERS` carries AD D.6's published string verbatim. The word *date-adjacent*
    in it describes where such a message is **displayed** - in `internalDate` order, next to
    its neighbours - and never a parent it was given: C-02a's whole point is that an orphan
    is declared, never silently re-parented.
    """

    #: The parent is named by this message's own `In-Reply-To` and is in this thread.
    IN_REPLY_TO = "in-reply-to"
    #: The parent is named by this message's own `References` and is in this thread.
    REFERENCES = "references"
    #: The message carries neither reply header. The thread's genuine root and a message
    #: Gmail filed here by subject are the same message by RFC headers, and MailWeave does
    #: not invent a distinction the headers do not make; a caller that wants one reads
    #: `position == 0`.
    NO_REPLY_HEADERS = "date-adjacent (no RFC reply headers)"
    #: AD D.4a: no `Message-ID` was observed *and* the message names no parent, so nothing
    #: structural is known about it in either direction.
    NO_MESSAGE_ID = "no Message-ID"
    #: A reply header was present and no `<msg-id>` could be extracted from it. Different
    #: from `NO_REPLY_HEADERS`: the sender said something about a parent and it was
    #: unreadable, which is a different defect with a different repair.
    UNPARSEABLE_REPLY_HEADERS = "reply headers carried no readable Message-ID"
    #: The named parent is a real `Message-ID` that no message of *this* thread carries.
    #: This is the input L4's structural expansion goes looking for.
    UNRESOLVED_PARENT = "named parent is not in this thread"
    #: Two messages of this thread carry the named `Message-ID`. Choosing either would be a
    #: guess wearing a link's clothes.
    AMBIGUOUS_PARENT = "named parent is carried by more than one message of this thread"
    #: This message's link closes a cycle. Which edge on the cycle is the false one is not
    #: knowable from the headers, so every edge on it is refused rather than one picked.
    REPLY_CYCLE = "reply headers form a cycle"
    #: This response observed no headers for this message at all, so it can neither link it
    #: nor declare it parentless. The third state, for the reason `MailboxProvenance` has
    #: one: "we did not see" is not "there was nothing".
    HEADERS_UNOBSERVED = "no reply headers were observed for this message"


#: The linkages that are **links**: a parent this thread holds, named by this child's own
#: RFC headers. Every other member of `Linkage` is a declared gap. Derived here rather than
#: listed at each use site, so a member added later is a gap until somebody says otherwise -
#: which is the safe default and the opposite of the one a per-site list produces.
RESOLVED_LINKAGES: Final[frozenset[Linkage]] = frozenset({Linkage.IN_REPLY_TO, Linkage.REFERENCES})

#: Every `Linkage` that is not a link. Stated as the complement so the two sets cannot drift
#: apart, which is what a second hand-written list of gap members would eventually do.
DECLARED_GAP_LINKAGES: Final[frozenset[Linkage]] = frozenset(Linkage) - RESOLVED_LINKAGES


class ParticipantRole(StrEnum):
    """What one address *did* in one message (contract C-02b, AD D.6, rubric STR-02).

    The distinction this enum exists for is the one STR-02 scores: **someone quoted in a
    thread did not write in it.** A retrieval system that answers "what did X say" with a
    message in which X is merely named answers "who decided this?" wrongly, which is the
    question the product is for.

    `AUTHOR` is the strongest claim here and it is the narrowest: the address appears in
    this message's own `From`, and `From` named exactly one address. Everything else is
    weaker, and the two weaker roles are kept apart from each other as well - a recipient is
    a routing fact Gmail states in a header, while a mention is a string found in text.
    """

    #: The address is the sole address of this message's `From`. This is authorship.
    AUTHOR = "author"
    #: `From` named this address **and others**. RFC 5322 permits a multi-mailbox `From`,
    #: and which of them held the pen is not something the headers say. Not authorship, and
    #: not silently promoted to it.
    COAUTHOR = "coauthor"
    #: The address is in `To` or `Cc`. Addressed, not authoring.
    RECIPIENT = "recipient"
    #: The address is in `Reply-To`. A routing directive the sender asserts, which is not a
    #: statement that this address wrote anything.
    REPLY_TO = "reply_to"
    #: The address appears in text that was observed for this message and in none of its
    #: address headers. This is hearsay: someone named, quoted or forwarded.
    MENTION = "mention"


class FillComponent(StrEnum):
    """AD A.9(3)'s five mechanical components of the E4 query-scored fill.

    The vocabulary lives here, with the other closed vocabularies of the response, and the
    **published weights** live in `mailweave.disclosure.weights` beside the reasoning for
    each one. The split is deliberate: a reason string a caller branches on is part of the
    wire schema, while a weight is policy, and a schema that imported a policy module would
    make the wire's vocabulary depend on how the policy is currently tuned.

    A component is a name for a mechanism, never for a judgement, which is what makes a
    filled row's `reason` mechanical under PART-07: `participant_match` says an address the
    query named appears in a header Gmail stated, and a caller can check that.
    """

    PARTICIPANT_MATCH = "participant_match"
    TERM_OVERLAP = "term_overlap"
    TEMPORAL_PROXIMITY = "temporal_proximity"
    POSITION_ADJACENCY = "position_adjacency"
    DECISION_CUE = "decision_cue"


class FloorRelation(StrEnum):
    """How an E2 floor member is attached to the evidence message it hangs off (A.9(2))."""

    #: The member is the evidence message's reply parent, by the evidence's own headers.
    PARENT = "parent"
    #: The member names the evidence message as its own reply parent.
    CHILD = "child"


class FloorDependence(StrEnum):
    """Why the evidence cannot be read without this floor member (OD-3's promotion rule).

    Three mechanical relations, and the rule that tests them in this order lives in
    `mailweave.disclosure.floor`. There is no member for "no dependence": that answer is the
    **absence** of a `FloorPromoted` reason, because a floor member the rule refused to
    promote is an ordinary reply parent or child and says exactly that.
    """

    #: The evidence message's own body carries quoted or forwarded spans, and this member is
    #: its reply parent: the evidence incorporates text this member wrote (A7).
    QUOTATION = "quotation"
    #: This member is a direct child of the evidence and carries a token of A.8a's published
    #: decision lexicon. T-CD2's shape: the quiet later reply that reverses.
    CONTRADICTION = "contradiction"
    #: This member satisfies a constraint of the query that the evidence message does not.
    #: Gmail evaluates `q` message-scoped (RO F2), so two messages can answer jointly.
    CONSTRAINT_CARRIER = "constraint_carrier"
