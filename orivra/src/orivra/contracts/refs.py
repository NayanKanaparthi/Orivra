"""Where a thing lives, what could be seen when it was read, and how fresh that is.

Three schemas, in the order a retrieval produces them: a `PermissionContext` is established
by consent, a `ContentVersion` is read off the item, and a `FreshnessStatus` says what the
last verification of that version established. `SourceReference` carries all three plus the
identity, and it is the value every node, edge and omission record points through.

**Frozen, and refusing rather than warning.** These follow `envelope/wire.py`'s rules: a
model that cannot be constructed wrong is a contract, and one that logs a warning is a
suggestion.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from orivra.contracts.vocab import ConnectorId, FreshnessState, RefKind

#: Length of every stable digest published by this module. Half of SHA-256, hex - long
#: enough that a collision is not a practical concern for a cache-key dimension, short
#: enough to read in a trace. The same figure as `handles/digest.py` uses, for the same
#: reason: these appear side by side in a trace and a reader should not have to ask which
#: kind of digest each one is.
DIGEST_CHARS: Final[int] = 12


def _digest(*parts: str) -> str:
    """A stable digest over field-separated parts.

    `\\x1f` (unit separator) rather than a printable joiner: a separator that can occur
    inside a scope string or an account id makes `("a|b", "c")` and `("a", "b|c")` the same
    digest, which is how a permission hash comes to say two different contexts are one.
    """
    joined = "\x1f".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:DIGEST_CHARS]


class Frozen(BaseModel):
    """The base every contract model here extends. Declares no fields, so `SealedModel`'s
    no-extension rule is not in play - these are not wire models of the MailWeave envelope;
    they are the internal contracts Orivra passes between its own layers, and the models
    that reach a client are still MailWeave's.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class PermissionContext(Frozen):
    """What the caller could see when this was read (plan §4.2).

    Gmail has one shape today - one account, one scope set. Drive and Slack need more, and
    the field set here is the union rather than a per-source subclass, because a cache key
    and a trace both need one shape to compare across connectors.

    **A matching hash is not authorisation** (plan §5.3, owner correction #7). `hash` is a
    cache-key dimension: it answers "was this read under the same conditions?", which is a
    question about the past. It does not answer "may this caller see it now?", which is a
    question about the present and is answered only by a live check against the source.
    `covers` is likewise a *necessary* condition and never a sufficient one - it is used to
    reject early, never to admit.
    """

    connector: ConnectorId
    principal: str = Field(min_length=1, max_length=128)
    """The authorised user, workspace member or service account, **already hashed**.

    Never an address: a permission context appears in traces and cache keys, and an address
    there is a mailbox identity written into a file that outlives the query.
    """

    scope_set: tuple[str, ...] = Field(min_length=1)
    """The granted OAuth scopes, read back after consent rather than as requested.

    `auth/consent.py` already reads the granted set back, which is the only figure that
    means anything: a request for `gmail.readonly` that was granted something narrower must
    not produce a context claiming the wider scope.
    """

    capability: tuple[str, ...] = ()
    """Per-connector capability facts, as sorted `name=value` strings.

    Gmail contributes nothing here today. Drive contributes the `capabilities` booleans a
    `files.get` returns; Slack contributes the token kind and the channel memberships. A
    tuple of strings rather than a per-connector model because this participates in a
    digest, and a digest over a union type is a digest whose input shape can change without
    the value changing.
    """

    observed_at: datetime

    @model_validator(mode="after")
    def _scopes_and_capabilities_are_canonical(self) -> Self:
        """Sorted, de-duplicated, non-empty entries - because these feed a digest.

        Two consents granting the same scopes in a different order are the same permission
        context, and a digest that says otherwise silently halves the cache hit rate and,
        worse, makes `covers` order-dependent.
        """
        for name, values in (("scope_set", self.scope_set), ("capability", self.capability)):
            if any(not value or value.strip() != value for value in values):
                raise ValueError(
                    f"{name} carries an empty or untrimmed entry; these are digest inputs "
                    "and an entry whose whitespace varies is a context that varies"
                )
            if list(values) != sorted(set(values)):
                raise ValueError(
                    f"{name} must be sorted and de-duplicated: it is a digest input, and "
                    "two consents granting the same set in a different order are one "
                    "permission context"
                )
        if self.observed_at.tzinfo is None:
            raise ValueError(
                "observed_at carries no UTC offset; an instant without one is ambiguous by "
                "exactly the amount that matters to a permission claim"
            )
        return self

    @property
    def hash(self) -> str:
        """A stable digest of every field that changes what the caller could see.

        `observed_at` is **not** in it, deliberately: two reads a minute apart under the
        same grant are the same context, and including the instant would make every cache
        entry unique and the dimension useless.
        """
        return _digest(
            self.connector.value,
            self.principal,
            *self.scope_set,
            "|",
            *self.capability,
        )

    def covers(self, other: PermissionContext) -> bool:
        """Whether this context is at least as wide as `other`, on the same principal.

        Used to **reject** a cached entry read under a wider grant than the caller now
        holds. It is never used to admit one: see the class docstring. A different
        connector or principal is not comparable and is always false.
        """
        return (
            self.connector is other.connector
            and self.principal == other.principal
            and set(other.scope_set) <= set(self.scope_set)
            and set(other.capability) <= set(self.capability)
        )


class ContentVersion(Frozen):
    """The identity of one item's content at one moment (plan §4.3).

    The three sources disagree about what a version is, so the field set is the union and
    the adapter fills what its source has:

    * Gmail: `(message_id, history_id)`. Message content is immutable; `history_id` moves on
      a label change, which is a change to what the mailbox says about the message and not
      to the message.
    * Drive: `(file_id, version, modified_time, head_revision_id | None)`. `version` is
      monotonic for all file types; `head_revision_id` exists only for binary types.
    * Slack: `(channel, ts, edited_ts | None, deleted)`. Identity is `(channel, ts)`; an
      edit moves `edited_ts` and not `ts`.
    """

    connector: ConnectorId
    native_id: str = Field(min_length=1, max_length=512)
    revision: str | None = Field(default=None, max_length=512)
    """Gmail `historyId`; Drive `version`; Slack `edited_ts` - whatever moves when the
    source's view of this item changes."""

    head_revision_id: str | None = Field(default=None, max_length=512)
    """Drive only: the revision the file head currently points at."""

    modified_at: datetime | None = None
    deleted: bool = False

    @property
    def key(self) -> str:
        """This version as one comparable string, for a cache key and a trace."""
        return _digest(
            self.connector.value,
            self.native_id,
            self.revision or "",
            self.head_revision_id or "",
            self.modified_at.isoformat() if self.modified_at is not None else "",
            "deleted" if self.deleted else "",
        )


class ChangeMarker(Frozen):
    """Where a source's change feed was last read (plan §4.3).

    The three sources are documented to behave differently and the differences are
    load-bearing, so the validator refuses the combinations that would lose data:

    * Gmail: `history_id`. A 404 on `history.list` means the id is too old and the only
      correct response is a **full resync**, declared in the response.
    * Drive: `start_page_token`, which never expires, and is **per `driveId`** for shared
      drives - one token for the whole account would silently miss a shared drive.
    * Slack: a `(channel, oldest_ts, latest_ts)` window. **Slack cursors are not persisted**
      because they expire; a stored cursor is a marker that will fail exactly when it is
      needed, so the window is stored and re-walked instead.
    """

    connector: ConnectorId
    container: str | None = Field(default=None, max_length=512)
    """Drive `driveId`, Slack `channel`. `None` for Gmail, which has one feed per mailbox."""

    marker: str | None = Field(default=None, max_length=1024)
    """Gmail `historyId`, Drive `startPageToken`. `None` for Slack, which stores a window."""

    window_start: str | None = Field(default=None, max_length=64)
    window_end: str | None = Field(default=None, max_length=64)
    """Slack `oldest`/`latest` timestamps. Never a cursor."""

    @model_validator(mode="after")
    def _each_source_stores_what_that_source_documents(self) -> Self:
        if self.connector is ConnectorId.SLACK:
            if self.marker is not None:
                raise ValueError(
                    "a Slack ChangeMarker must not carry a cursor: Slack cursors expire, so "
                    "a persisted one fails exactly when it is next needed. Store the "
                    "(channel, oldest_ts, latest_ts) window and re-walk it"
                )
            if self.container is None or self.window_start is None or self.window_end is None:
                raise ValueError(
                    "a Slack ChangeMarker is (channel, oldest_ts, latest_ts) and all three "
                    "are required; a partial window cannot be re-walked"
                )
            return self
        if self.window_start is not None or self.window_end is not None:
            raise ValueError(
                f"{self.connector.value} has a cursor-style change feed and does not store a "
                "timestamp window; a window here would be re-walked as though it were one"
            )
        if self.marker is None:
            raise ValueError(
                f"{self.connector.value} ChangeMarker carries no marker; a feed position "
                "that is absent is a full resync and must be recorded as one, not as an "
                "empty marker that reads as position zero"
            )
        if self.connector is ConnectorId.GMAIL and self.container is not None:
            raise ValueError(
                "Gmail has one change feed per mailbox and no container; a container here "
                "would claim a per-label or per-thread feed that Gmail does not offer"
            )
        return self


class FreshnessStatus(Frozen):
    """What the last verification established, and what it walked from (plan §4.3).

    **A degraded state must say why.** `stale`, `unverifiable`, `gone` and `access_lost` are
    each a refusal to serve a cached item, and a refusal a reader cannot account for is one
    that will be argued with at the next call site. `fresh` carries no `why` for the same
    reason: a sentence explaining why something is fine is noise that trains readers to skip
    the field.
    """

    verified_at: datetime
    state: FreshnessState
    marker: ChangeMarker | None = None
    why: str | None = Field(default=None, max_length=400)

    @model_validator(mode="after")
    def _a_degraded_state_accounts_for_itself(self) -> Self:
        if self.state.degraded and not self.why:
            raise ValueError(
                f"freshness state {self.state.value!r} is a refusal to serve and carries no "
                "why; every degraded state states its cause once, in the sentence a reader "
                "will see"
            )
        if not self.state.degraded and self.why:
            raise ValueError(
                "a fresh FreshnessStatus carries a why; an explanation attached to the "
                "state that needs none trains readers to skip the field on the states that "
                "do not"
            )
        if self.verified_at.tzinfo is None:
            raise ValueError(
                "verified_at carries no UTC offset; a freshness stamp a reader cannot "
                "compare to the current time is a string in the shape of one"
            )
        return self

    @property
    def servable(self) -> bool:
        """Whether an item in this state may be served. Exactly one state may."""
        return self.state.servable


class SourceReference(Frozen):
    """Where a thing lives and how to get back to it (plan §4.1).

    Generalises the `(thread_id, message_id)` pair plus `map_id` that every v0.1 row and
    affordance carries. The rule inherited from AD A.9 is unchanged: provenance on every
    row, scope preserved, never widened. **A reference minted under one account and
    permission context is never presented under another**, which is what the validator
    below enforces rather than leaves to the caller.
    """

    connector: ConnectorId
    account: str = Field(min_length=1, max_length=128)
    """The account or workspace this was read from, hashed. Never the address itself."""

    kind: RefKind
    native_id: str = Field(min_length=1, max_length=512)
    handle: str | None = Field(default=None, max_length=4096)
    """A MailWeave HMAC handle (`handles/mint.py`) when re-derivation is needed to reach
    this. `None` is the honest value for a server holding no signing key."""

    version: ContentVersion
    permission: PermissionContext
    locator: str | None = Field(default=None, max_length=2048)
    """A URL a human can open. **Never used for retrieval** - retrieval goes through the
    adapter and the native id, and a stored URL that retrieval followed would be a second
    route to the data that no permission check covers."""

    @model_validator(mode="after")
    def _one_reference_speaks_for_one_connector_and_one_read(self) -> Self:
        if self.version.connector is not self.connector:
            raise ValueError(
                f"reference is {self.connector.value} and its version is "
                f"{self.version.connector.value}; a reference carrying another source's "
                "version would be re-verified against the wrong change feed"
            )
        if self.permission.connector is not self.connector:
            raise ValueError(
                f"reference is {self.connector.value} and its permission context is "
                f"{self.permission.connector.value}; that is a reference presented under a "
                "grant that was never checked against this source"
            )
        if self.version.native_id != self.native_id:
            raise ValueError(
                "the reference and its version name different items; a version belonging to "
                "another item would report this one fresh whenever that one had not moved"
            )
        return self

    @property
    def node_id(self) -> str:
        """The stable node identity this reference produces inside one query graph.

        `connector/kind/native_id` and nothing else: two reads of the same item at different
        versions are one node, and its freshness is a property of the node rather than of
        its identity. Making the version part of the identity would put the same message in
        a graph twice as soon as a label moved.
        """
        return f"{self.connector.value}/{self.kind.value}/{self.native_id}"

    def as_record(self) -> dict[str, str]:
        """The redacted form that may appear in a trace: identities and digests, no
        content, no address, no locator."""
        return {
            "connector": self.connector.value,
            "kind": self.kind.value,
            "node_id": self.node_id,
            "account": self.account,
            "version": self.version.key,
            "permission": self.permission.hash,
        }


__all__ = [
    "DIGEST_CHARS",
    "ChangeMarker",
    "ContentVersion",
    "FreshnessStatus",
    "Frozen",
    "PermissionContext",
    "SourceReference",
]
