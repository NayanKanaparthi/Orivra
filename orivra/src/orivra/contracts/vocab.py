"""Closed vocabularies of the source-independent layer (Orivra v1 plan §4).

Every enum here is closed for the same reason MailWeave's are (`envelope/vocab.py`): a
value a caller branches on must have a fixed set, and a set that grows silently is a
contract that changed without anyone reading it.

**Three of these vocabularies exist to keep facts apart that would otherwise look alike**,
and each is the subject of a stated rule rather than a naming convention:

* `Assertion` splits what the source's *data structures* say from what a *human wrote in
  the content*. A reply header is the first; "this supersedes the July draft" is the
  second. Both are `Origin.OBSERVED` - the source really does state them - and conflating
  them would let Orivra publish a human's claim in its own voice.
* `Relation` is namespaced, and the namespace is a property of the value, not a field
  beside it. `Relation.REPLY_TO.namespace` is `obs.meta` and nothing can set it to
  anything else, so "an inferred relation that presents itself as observed" is not a bug
  that can be written.
* `FreshnessState` exposes `servable`, and exactly one state is. Anywhere the cache is
  consulted the question "may this be served?" is answered by the vocabulary rather than
  by an `if` at the call site, because the call sites are where the exceptions creep in.
"""

from __future__ import annotations

from enum import StrEnum


class ConnectorId(StrEnum):
    """The sources Orivra can hold a reference into.

    Declared in full at v1's start rather than grown per milestone: the schemas below are
    unions over this set, and a union that changes shape when a connector lands is a
    migration in every stored record. M1 implements `GMAIL` only; the others are values a
    reference *could* carry and no adapter yet mints.
    """

    GMAIL = "gmail"
    DRIVE = "drive"
    SLACK = "slack"


class RefKind(StrEnum):
    """What a `SourceReference` points at.

    `FILE_REVISION` is separate from `FILE` because Drive's revision is independently
    addressable and independently permissioned; `SLACK_MESSAGE` is separate from `MESSAGE`
    because its identity is `(channel, ts)` and not an opaque id, which is a difference a
    reader of a reference needs to see.
    """

    MESSAGE = "message"
    THREAD = "thread"
    FILE = "file"
    FILE_REVISION = "file_revision"
    CHANNEL = "channel"
    CONVERSATION = "conversation"
    SLACK_MESSAGE = "slack_message"
    PERSON = "person"


class GraphReasonKind(StrEnum):
    """Reason kinds for nodes Orivra builds and MailWeave never returns a row for.

    **Namespaced, and that is the compatibility guarantee.** Every MailWeave `ReasonKind` is a
    bare identifier; every member here carries an `orivra.` prefix, so the two vocabularies
    cannot collide however either one grows, and a discriminated union over both stays
    unambiguous without either side knowing about the other.
    """

    PARTICIPANT_IN = "orivra.participant_in"


class NodeKind(StrEnum):
    """What an `EvidenceNode` is.

    `CLAIM` is the only kind that is always derived, always carries verbatim spans, and is
    refused when a span does not string-match its source. That is GraphRAG's covariate rule
    made mandatory rather than optional (plan §4.4).
    """

    MESSAGE = "message"
    THREAD = "thread"
    FILE = "file"
    FILE_REVISION = "file_revision"
    SLACK_MESSAGE = "slack_message"
    CONVERSATION = "conversation"
    PERSON = "person"
    CLAIM = "claim"


class Origin(StrEnum):
    """A **node's** origin: something a source held, or something Orivra constructed.

    `DERIVED` means the node was built here - a `CLAIM` extracted from a body, a `PERSON`
    resolved from addresses - and it then carries `derived_from[]` and a versioned method.
    """

    SOURCE_BACKED = "source_backed"
    DERIVED = "derived"


class EdgeOrigin(StrEnum):
    """An **edge's** origin, which is a different question from a node's and so a different
    vocabulary.

    A node is `SOURCE_BACKED` when the source held the row. An edge is `OBSERVED` when the
    source states the relation - whether in its data structures or in a human's words - and
    `INFERRED` when Orivra computed it. A source-stated claim sits on a source-backed node
    and produces an *observed* edge that is not a *metadata* fact, which is precisely the
    distinction `Assertion` carries and the reason these two enums are not one.

    Not a free field: `Relation` fixes it (see `Relation.origin`).
    """

    OBSERVED = "observed"
    INFERRED = "inferred"


class Assertion(StrEnum):
    """*Who* is asserting an observed relation, which is not the same question as whether
    the relation was observed.

    Correction of the first draft, which had one `observed` category and therefore let
    `supersedes_stated` sit beside `reply_to` as though both were facts of the same kind.

    `METADATA` - a fact of the source's own data structures: an `In-Reply-To` header, thread
    membership, a revision chain, channel membership. Read, not interpreted. **These are the
    only relations Orivra asserts on its own authority.**

    `SOURCE_STATED` - a claim a human made inside content Orivra is reading. The source
    really does state it, so the origin is `OBSERVED`; but Orivra reports *that the source
    asserts this*, never that Orivra verified it, and the edge names who said it
    (`asserted_by`). A span matching the source text proves the text exists; it does not
    prove the relationship is correct.

    `DERIVED` - Orivra's own inference. Always `Origin.INFERRED`, always carries a
    confidence and a versioned method, never presented as a fact of the source.
    """

    METADATA = "metadata"
    SOURCE_STATED = "source_stated"
    DERIVED = "derived"


class Namespace(StrEnum):
    """The three relation namespaces, as values rather than as a string convention."""

    OBS_META = "obs.meta"
    OBS_SAID = "obs.said"
    INF = "inf"


class Relation(StrEnum):
    """The closed relation set, namespaced in the value itself (plan §4.5).

    A relation's namespace decides its `Origin` and its `Assertion`, so `EvidenceEdge` reads
    them off the relation rather than accepting them as fields. That is what makes "an
    inferred relation presenting itself as observed" unconstructible instead of merely
    discouraged.

    **There is no `caused` relation in either namespace, and no rule promotes an inferred
    relation to an observed one.** Causation is not observable in mail, files or chat: the
    strongest honest statement is `POSSIBLY_EXPLAINS`, which is inferred, carries a
    confidence, and says so.
    """

    # -- observed / metadata: facts of the source's own data structures ------------------
    REPLY_TO = "obs.meta.reply_to"
    THREAD_MEMBER = "obs.meta.thread_member"
    FILE_REVISION_OF = "obs.meta.file_revision_of"
    SLACK_REPLY = "obs.meta.slack_reply"
    IN_CHANNEL = "obs.meta.in_channel"
    ATTACHMENT_OF = "obs.meta.attachment_of"
    AUTHORED_BY = "obs.meta.authored_by"
    SENT_TO = "obs.meta.sent_to"

    # -- observed / source-stated: claims a human made inside the content ----------------
    SUPERSEDES_STATED = "obs.said.supersedes_stated"
    MENTIONS = "obs.said.mentions"
    LINKS_TO = "obs.said.links_to"

    # -- inferred: Orivra's own, always with spans, confidence and a versioned method ----
    APPEARS_RELATED_TO = "inf.appears_related_to"
    SUPPORTS = "inf.supports"
    CONTRADICTS = "inf.contradicts"
    POSSIBLY_EXPLAINS = "inf.possibly_explains"
    POTENTIALLY_SUPERSEDES = "inf.potentially_supersedes"
    SAME_TOPIC_AS = "inf.same_topic_as"

    @property
    def namespace(self) -> Namespace:
        """The namespace this relation belongs to, read from its own value.

        Deliberately parsed rather than tabulated: a table can be given an entry a value
        does not have, and a value can be added without an entry. Parsing the value cannot
        disagree with the value.
        """
        head, _, _ = self.value.rpartition(".")
        return Namespace(head)

    @property
    def origin(self) -> EdgeOrigin:
        """`OBSERVED` for both observed namespaces, `INFERRED` for `inf.`."""
        return EdgeOrigin.INFERRED if self.namespace is Namespace.INF else EdgeOrigin.OBSERVED

    @property
    def assertion(self) -> Assertion:
        """Which of the three assertion kinds this relation is, fixed by its namespace."""
        match self.namespace:
            case Namespace.OBS_META:
                return Assertion.METADATA
            case Namespace.OBS_SAID:
                return Assertion.SOURCE_STATED
            case Namespace.INF:
                return Assertion.DERIVED

    @property
    def needs_asserted_by(self) -> bool:
        """Source-stated relations name who said them; nothing else does.

        A metadata relation has no asserter - the source's data structure is not a person -
        and an inferred one was asserted by Orivra, which the method already records.
        """
        return self.assertion is Assertion.SOURCE_STATED


class FreshnessState(StrEnum):
    """What the last verification of an item's version established.

    `GONE` and `ACCESS_LOST` are kept apart in the vocabulary and are **not** distinguished
    by Drive, whose change feed reports both as `removed: true` (plan §4.3). An adapter that
    cannot tell them apart says `GONE`, because "must not serve" is what both mean and
    claiming to know which would be a claim wider than the API.
    """

    FRESH = "fresh"
    STALE = "stale"
    UNVERIFIABLE = "unverifiable"
    GONE = "gone"
    ACCESS_LOST = "access_lost"

    @property
    def servable(self) -> bool:
        """Whether a cached item in this state may be served. Exactly one state may.

        A failed verification never serves the cached item: it degrades to a fresh source
        read, a resync, or an `inconclusive` outcome, in that order.
        """
        return self is FreshnessState.FRESH

    @property
    def degraded(self) -> bool:
        """Every state but `FRESH`. Each of these must carry a `why` (`FreshnessStatus`)."""
        return self is not FreshnessState.FRESH


class OmissionCause(StrEnum):
    """Why something the query reached is not in the response (plan §4.7).

    Generalises MailWeave's `WithheldCap` and `NotTriedWhy` across sources and adds the two
    causes a graph introduces: a branch the scorer pruned and a hop the budget stopped.
    """

    CAP = "cap"
    CEILING = "ceiling"
    PERMISSION = "permission"
    FRESHNESS_UNVERIFIABLE = "freshness_unverifiable"
    SOURCE_GONE = "source_gone"
    PRUNED = "pruned"
    NOT_TRIED = "not_tried"
    PARTIAL_SOURCE_FAILURE = "partial_source_failure"
    """The source answered, and answered incompletely.

    Added after a review found MailWeave's `partial_source_failure` being reported as
    `freshness_unverifiable` - which tells a caller that an item's *version could not be
    verified*, and sends them to re-verify something that was never fetched. Raising a cap,
    widening a ceiling, re-verifying a version and retrying a source are four different
    actions, and a vocabulary with three values for four conditions makes one of them wrong
    by construction.
    """

    @property
    def may_have_no_handle(self) -> bool:
        """The two causes for which no `ExpansionHandle` can exist, count still stated.

        A handle is a promise that following it reaches the thing. For a record the caller
        may not see, and for one the source no longer has, there is nothing to reach, and
        minting a handle that will always refuse would be a worse answer than none. Every
        other cause carries a handle, and `OmissionRecord` refuses one that does not.
        """
        return self in {OmissionCause.PERMISSION, OmissionCause.SOURCE_GONE}


class SourceState(StrEnum):
    """A connector's own condition during one query, as `orivra_sources` reports it."""

    READY = "ready"
    NOT_CONFIGURED = "not_configured"
    AUTH_REQUIRED = "auth_required"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class CandidateBasis(StrEnum):
    """Why two entities look alike. **None of these ever merges them** (plan §4.6)."""

    DISPLAY_NAME_MATCH = "display_name_match"
    DOMAIN_MATCH = "domain_match"
    CO_OCCURRENCE = "co_occurrence"
    EXPLICIT_LINK = "explicit_link"


class CandidateStatus(StrEnum):
    """A candidate's disposition. Only a source, never a score, can confirm one."""

    CANDIDATE = "candidate"
    CONFIRMED_BY_SOURCE = "confirmed_by_source"
    REJECTED = "rejected"


__all__ = [
    "Assertion",
    "CandidateBasis",
    "CandidateStatus",
    "ConnectorId",
    "EdgeOrigin",
    "FreshnessState",
    "Namespace",
    "NodeKind",
    "OmissionCause",
    "Origin",
    "RefKind",
    "Relation",
    "SourceState",
]
