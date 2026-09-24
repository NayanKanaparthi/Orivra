"""The Gmail REST surface and what each call is charged (AD A.5, A.5b, A.11).

Two things live here and nothing else: the endpoints this process is allowed to call, and
the **published** quota rate for each. They are together because they are the same table in
the architecture, and splitting them is how a seventh endpoint acquires a rate nobody
declared.

**Quota units are a diagnostic, never a headline** (ADV-211, AD A.11). No Gmail response
carries a quota figure, so every unit number this project states is a multiplication of a
published table by a call count - a self-report by construction. `RATE_CALIBRATION` says
where the numbers come from and that PF-3 has not run, and it travels with every meter
reading so a number cannot be quoted without its provenance.
"""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType
from typing import Final

from mailweave.envelope.disposition import ObservedEndpoint


class GmailEndpoint(StrEnum):
    """The endpoints WS-02 implements. A subset of AD A.5's six, and deliberately so.

    A.5 declares six; this round needs five. `users.labels.list` is not implemented because
    nothing consumes labels until the LR rung's client-side `label:` re-check (WS-12), and
    an endpoint with no caller is an endpoint whose response shape nobody has checked
    against reality. It stays in `constants.GMAIL_ENDPOINTS` - the CI path sweep's
    allowlist is the architecture's surface, not this round's - and is absent here.

    `users.messages.attachments.get` is removed from the release surface entirely (ADV-207)
    and will never appear here.
    """

    MESSAGES_LIST = "users.messages.list"
    MESSAGES_GET = "users.messages.get"
    THREADS_GET = "users.threads.get"
    HISTORY_LIST = "users.history.list"
    GET_PROFILE = "users.getProfile"


#: Published quota units per call (AD A.5). The first four are [VERIFIED RO F7]; the fifth
#: is [TBM - PF-3], carried from the published usage-limits table as a planning value.
#:
#: These are *inputs to a multiplication*, not measurements. PF-3 exists to replace them.
PUBLISHED_QUOTA_UNITS: Final[MappingProxyType[GmailEndpoint, int]] = MappingProxyType(
    {
        GmailEndpoint.MESSAGES_LIST: 5,
        GmailEndpoint.MESSAGES_GET: 20,
        GmailEndpoint.THREADS_GET: 40,
        GmailEndpoint.HISTORY_LIST: 2,
        GmailEndpoint.GET_PROFILE: 1,
    }
)

#: Which of the five rates rests on a measurement and which on a planning value, so a
#: reader of a meter reading can tell them apart without opening the architecture.
RATE_PROVENANCE: Final[MappingProxyType[GmailEndpoint, str]] = MappingProxyType(
    {
        GmailEndpoint.MESSAGES_LIST: "VERIFIED RO F7",
        GmailEndpoint.MESSAGES_GET: "VERIFIED RO F7",
        GmailEndpoint.THREADS_GET: "VERIFIED RO F7",
        GmailEndpoint.HISTORY_LIST: "VERIFIED RO F7",
        GmailEndpoint.GET_PROFILE: "TBM - PF-3; planning value from the published table",
    }
)

#: Carried on every meter reading. It is a sentence rather than a date because there is no
#: calibration date yet: PF-3 has not been run, and AD A.11 requires every published quota
#: figure to carry the calibration date it was derived under. When PF-3 runs, this string is
#: replaced by its date and the rates above are re-set from the measurement (AD A.5c).
RATE_CALIBRATION: Final[str] = (
    "uncalibrated: published table, PF-3 not yet run. Quota units are a diagnostic "
    "(AD A.11, ADV-211), never a headline; no Gmail response carries a quota figure."
)

#: The published per-minute per-user-per-project budget (RO F7), also uncalibrated. The
#: governor (A.5c) is WS-10's; this is here because PF-3 measures against it.
PUBLISHED_PER_MINUTE_UNITS: Final[int] = 6_000

#: Which endpoints put ids into `H`, and under which A.7a clause. The mapping is not
#: reversed from `ObservedEndpoint` by name-matching: it is written out, because a name
#: match would silently acquire a new member the moment either enum grows, and adding a
#: member to `ObservedEndpoint` is an architecture amendment (A2), not a refactor.
ID_YIELDING_ENDPOINTS: Final[MappingProxyType[GmailEndpoint, ObservedEndpoint]] = MappingProxyType(
    {
        GmailEndpoint.MESSAGES_LIST: ObservedEndpoint.MESSAGES_LIST,
        GmailEndpoint.HISTORY_LIST: ObservedEndpoint.HISTORY_LIST,
        GmailEndpoint.THREADS_GET: ObservedEndpoint.THREADS_GET,
    }
)

#: `users.messages.get` and `users.getProfile` are **not** id-yielding, and this is the
#: reasoning rather than an omission.
#:
#: A `messages.get` response names exactly one id: the one the caller passed in. It cannot
#: introduce an id into `H` that was not already there, because a caller can only reach it
#: with an id it already holds, and the only readable enumeration of ids in this system is
#: `DispositionLedger.hit_ids`. What it *can* do is answer with a **different** id than the
#: one requested, which is a response that does not describe the call that was made - so the
#: client refuses it rather than sealing it (see `client.get_message`).
#:
#: `getProfile` returns an address and three counts, and no message id at all.
NON_ID_YIELDING: Final[frozenset[GmailEndpoint]] = frozenset(
    {GmailEndpoint.MESSAGES_GET, GmailEndpoint.GET_PROFILE}
)
