"""The closed error vocabulary of AD D.11 and the exceptions that carry it.

D.11's partition rule: a condition that still permits a truthful partial answer is an
in-band field on a successful response; only a condition that makes the whole call
unanswerable is a tool error. `Surface` records which side of that partition a code
sits on, so the partition is data rather than a convention.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class Surface(StrEnum):
    """Where a D.11 code is allowed to appear."""

    TOOL_ERROR = "tool_error"
    IN_BAND = "in_band"
    STARTUP_FAILURE = "startup_failure"


class ErrorCode(StrEnum):
    """AD D.11, complete. Adding a member is a schema change with a version bump."""

    AUTH_REAUTH_REQUIRED = "auth_reauth_required"
    AUTH_PROFILE_UNDERIVABLE = "auth_profile_underivable"
    HANDLE_INVALID = "handle_invalid"
    HANDLE_KEY_ROTATED = "handle_key_rotated"
    HANDLE_EXPIRED = "handle_expired"
    HANDLE_STALE = "handle_stale"
    HANDLE_STALE_UNVERIFIABLE = "handle_stale_unverifiable"
    BUDGET_CLAMPED = "budget_clamped"
    BUDGET_EXHAUSTED = "budget_exhausted"
    PROCESS_QUOTA_WAIT = "process_quota_wait"
    PROCESS_QUOTA_REFUSED = "process_quota_refused"
    UPSTREAM_RATE_LIMITED = "upstream_rate_limited"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    PARTIAL_SOURCE_FAILURE = "partial_source_failure"
    SEMANTIC_UNAVAILABLE = "semantic_unavailable"
    SCAN_SCOPE_INCOMPLETE = "scan_scope_incomplete"
    UNDECODABLE_CONTENT = "undecodable_content"
    UNSUPPORTED_VIEW = "unsupported_view"


ERROR_SURFACE: Final[dict[ErrorCode, Surface]] = {
    ErrorCode.AUTH_REAUTH_REQUIRED: Surface.TOOL_ERROR,
    ErrorCode.AUTH_PROFILE_UNDERIVABLE: Surface.STARTUP_FAILURE,
    ErrorCode.HANDLE_INVALID: Surface.TOOL_ERROR,
    ErrorCode.HANDLE_KEY_ROTATED: Surface.TOOL_ERROR,
    ErrorCode.HANDLE_EXPIRED: Surface.TOOL_ERROR,
    ErrorCode.HANDLE_STALE: Surface.TOOL_ERROR,
    ErrorCode.HANDLE_STALE_UNVERIFIABLE: Surface.IN_BAND,
    ErrorCode.BUDGET_CLAMPED: Surface.IN_BAND,
    ErrorCode.BUDGET_EXHAUSTED: Surface.IN_BAND,
    ErrorCode.PROCESS_QUOTA_WAIT: Surface.IN_BAND,
    ErrorCode.PROCESS_QUOTA_REFUSED: Surface.IN_BAND,
    ErrorCode.UPSTREAM_RATE_LIMITED: Surface.IN_BAND,
    ErrorCode.UPSTREAM_UNAVAILABLE: Surface.TOOL_ERROR,
    ErrorCode.PARTIAL_SOURCE_FAILURE: Surface.IN_BAND,
    ErrorCode.SEMANTIC_UNAVAILABLE: Surface.IN_BAND,
    ErrorCode.SCAN_SCOPE_INCOMPLETE: Surface.IN_BAND,
    ErrorCode.UNDECODABLE_CONTENT: Surface.IN_BAND,
    ErrorCode.UNSUPPORTED_VIEW: Surface.TOOL_ERROR,
}

# Codes an `errors[]` entry on a successful response may carry (AD D.2 field note).
IN_BAND_CODES: Final[frozenset[ErrorCode]] = frozenset(
    code for code, surface in ERROR_SURFACE.items() if surface is Surface.IN_BAND
)


class MailweaveError(Exception):
    """Base class for every MailWeave-raised condition."""


class DispositionInvariantError(MailweaveError):
    """`H == disclosed union withheld` did not hold, or a residue had no cap record.

    This is an internal error, never a shipped response (AD A.7a). It exists so that a
    cap which forgets to record a dropped hit produces a failure instead of a silent loss.
    """


class ConfigError(MailweaveError):
    """Configuration is absent, malformed, or refuses to load safely."""


class TokenStoreError(MailweaveError):
    """The credential store is missing, unreadable, or over-permissive."""


class SecretDocumentMalformed(MailweaveError):
    """A secret-bearing document failed validation. The message names fields, never values.

    Raised by `validation.SecretBearingModel` in place of `pydantic.ValidationError`, whose
    default rendering quotes the input it refused - which for the credential file and the
    config file is the refresh token and the client secret (R-SEC-043). The loaders catch
    this and re-raise their own `TokenStoreError` / `ConfigError`; chaining *this* one is
    safe, because its message is already value-free.
    """


class AuthProfileUnderivable(MailweaveError):
    """`users.getProfile` failed, so the redaction profile cannot be derived (AD A.4).

    An underivable profile cannot be made safe by defaulting: the server refuses to start.
    """

    code = ErrorCode.AUTH_PROFILE_UNDERIVABLE


class EgressBlocked(MailweaveError):
    """An outbound request named a host outside the two-host runtime allowlist (AD D.8)."""


class QueryNotSearchable(MailweaveError):
    """The caller asked for nothing, so there is nothing to search **and nothing to report**.

    **This is now the narrowest class it can be, and round 17 narrowed it** (ROUTE-01). It
    was raised for every query no rung could turn into a probe, which covered a parse
    failure, a query naming only where to look, an unprovable `name:value` token and - once
    the tokeniser mistook a quoted phrase for one - an ordinary reply subject. Seventeen of
    fifty plausible queries came back as an exception with no envelope at all, which fails
    ROUTE-01's own sentence more completely than the bare empty payload it was written
    against. Those queries now get a structured report: `LadderRunner.run_parsed` returns a
    run in which every rung is `not_applicable` - the rare case where that is literally true
    of all five - and `assemble` builds the envelope A.2 and D.3 rule 6 require, carrying
    the parse, every token dropped and why, the rungs not tried, an `empty_diagnosis` and
    the affordances. Zero Gmail calls, exactly as before.

    **What still raises, and why a report here would be the dishonest answer.** An empty or
    whitespace-only query. There is no parse to show, no token to declare dropped, no
    constraint to relax and no rung whose non-application means anything, so every field of
    the report would describe a search that had no subject: `term_coverage` would read 1.0 -
    nothing was dropped, because nothing was asked - and `empty_diagnosis` would read
    `complete`, which together say "MailWeave looked and found nothing" about a question
    nobody asked. That is a nonexistence claim, which is the *other* thing ROUTE-01 forbids.

    The defect this class originally existed to prevent is unchanged and still
    unrepresentable: round 15 answered `mailweave_search("(rollout OR escalation)")` by
    putting a bare widening scope operator - `constants.ANYWHERE_OPERATOR`, written in one
    place and deliberately not spelled here - and `includeSpamTrash=true` on the wire, and
    reporting sixty threads of an untouched mailbox, spam included, as matches of a query
    none of whose content was executed, under `outcome: answered` and `term_coverage: 1.0`.
    Refusing to **send** that is not the same decision as refusing to **answer**, and round
    16 made them one decision.
    """


class ContentProcessingError(MailweaveError):
    """Content processing could not proceed at all (as distinct from a declared reduction)."""


class AnnotationContainmentError(ContentProcessingError):
    """An annotation of `body_clean` does not contain every character of its input.

    Amendment A7's gate, as an exception. The content pipeline annotates and never deletes,
    so an annotated body whose spans do not tile its text is not a degraded result to be
    reported - it is the one state A7 exists to make unreachable, and it fails loudly at
    construction rather than shipping a body that quietly lost a sentence.
    """


class ResponseCeilingExceeded(MailweaveError):
    """The assembled response exceeds its own declared ceiling and was not self-truncated.

    DISC-06 makes MailWeave the author of its own truncation. Shipping an oversized
    response would hand truncation to the host, so assembly fails instead.
    """


#: The five ways a `map_id` redemption can decline to serve (AD A.10, D.11). Derived from
#: `ERROR_SURFACE` by prefix rather than listed, so a sixth handle code added to the
#: vocabulary is a member of this set the moment it exists rather than the day somebody
#: remembers - which is the difference between a closed vocabulary and a list of the
#: members somebody thought of.
HANDLE_ERROR_CODES: Final[frozenset[ErrorCode]] = frozenset(
    code for code in ErrorCode if code.value.startswith("handle_")
)


class HandleRefused(MailweaveError):
    """A `map_id` was not honoured, in one of AD D.11's five handle classes.

    `code` is carried rather than encoded in the message, because the five classes have
    different causes and different remedies and a caller has to be able to branch on which:
    `handle_invalid` says the handle is not this server's, `handle_key_rotated` says the
    signing key was deliberately changed, `handle_expired` says the observation behind it has
    aged out, `handle_stale` says the mailbox moved, and `handle_stale_unverifiable` says the
    probe that would have told could not. Collapsing any two of them would report a cause
    that did not happen.

    `handle_stale_unverifiable` is `Surface.IN_BAND` and the other four are tool errors, so
    this exception is raised for the four and the fifth travels on a served response - which
    is why `Redemption` carries it as a field rather than this class carrying it as a
    variant.
    """

    def __init__(self, *, code: ErrorCode, message: str, affordance: object = None) -> None:
        if code not in HANDLE_ERROR_CODES:
            raise ValueError(f"{code.value} is not one of AD D.11's handle classes")
        super().__init__(message)
        self.code = code
        #: AD D.11's "the re-derivation call", when one can honestly be minted.
        #:
        #: **`None` for `handle_invalid` and `handle_key_rotated`, deliberately.** Both are
        #: decided while the payload is still *unverified* - the epoch has to be read before
        #: the signature is checked, because with the rotated key gone the signature cannot
        #: verify either way - so filling an affordance's arguments from it would put
        #: caller-supplied strings into a connector-voiced field. The message names the call
        #: instead. Typed as `object` because `Affordance` lives in `envelope.wire`, which
        #: imports this module: the annotation is the price of not inverting that.
        self.affordance = affordance


class ThreadStructureError(MailweaveError):
    """A thread's reply structure was asked for over input no structure can describe.

    Today the one such input is a message list carrying the same Gmail message id twice.
    Every guarantee `mailweave.structure.reply_tree` makes is *per message* - exactly one
    `Link`, one `linkage`, one parent - and two rows under one id have no single answer to
    any of them. Raised rather than deduplicated, on amendment A3's reasoning for positions:
    quietly collapsing two rows into one moves evidence just as silently as clamping a
    position does, and the caller that fetched them can say which disposition the thread
    should get (`assemble` withholds it whole, exactly as it does for the thread whose
    chronological order the observation declined to state).
    """
