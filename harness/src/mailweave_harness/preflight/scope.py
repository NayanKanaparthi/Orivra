"""Where a probe's listing walk looks, as one value rather than two agreeing settings.

`messages.list` has **two** ways of saying whether SPAM and TRASH are in scope: the
`includeSpamTrash` request parameter and the `in:` search operator inside `q`. They are
independent inputs to Gmail and nothing on Gmail's side makes them agree, so a probe that
asked to look everywhere in `q` while passing `includeSpamTrash=false` would be sampling a
mailbox
that neither setting describes - and PF-1's whole method is a comparison between two
endpoints "at the same includeSpamTrash setting", which is a comparison of nothing if the two
arms are not actually at the same setting.

**Where the operators are written (R-SEC-051).** Not here: they are
`mailweave.constants.ANYWHERE_OPERATOR` and friends, and this enum composes its two query
spellings out of them. Two reasons. The vocabulary is Gmail's, and the module every layer
already imports for Gmail's other shapes is where this project keeps one copy of a shape
(R-ARCH-031). And the *server* needs the same vocabulary now: `GmailClient._fetch_list_page`
refuses a query and a flag that disagree at the point the request parameters are built, which
is the only place the two settings actually meet, and which catches a spelling no AST sweep
can see - an f-string, a concatenation, or the flag simply omitted.

**Why this is an enum and not a helper that returns a string.** Round 12's part 1 wrote
`unfiltered_query(include_spam_trash: bool) -> str`, which is a function whose *caller* still
holds two things and has to pass each to the right place. The docstring made the safety claim
- that the two may not disagree - and nothing enforced it; every caller was trusted to pass
the same boolean twice. That is this project's most recurring defect wearing a different hat:
one shape validated, its peers trusted. Here the pair is a single value, `walk_mailbox` is the
only place that takes it apart, and `tests/test_standing_cycle_round12.py` fails the build if
any call site passes `include_spam_trash` as anything but `<scope>.include_spam_trash` beside
`query=<the same scope>.query`.

**[PREFLIGHT PF-20] What is guessed here, said rather than absorbed.** Whether either spelling
selects exactly the set an omitted `q` selects is settled by no Google document. One
difference is already known: a `q` sends the call through the search index while an omitted
`q` enumerates, and PF-freshness-raw exists precisely because those two are not the same
clock. The cost to a probe is bounded and directional - index lag can hide a message from the
listing arm and cannot invent one - so it can only conceal a real PF-1 failure, never
manufacture one, which is the bias PF-1 already declares and records.

**Why not an empty `q`.** `ScanScopeEntry.q` carries `min_length=1`, because `scan_scope` is
the response's account of which queries were actually *executed* and an entry with no query in
it states nothing. An empty default never produced a broad listing: it produced a
`pydantic.ValidationError` on the runner's first, unconditional Gmail call, whichever probe
was selected, every time (R-SEC-041).
"""

from __future__ import annotations

from enum import Enum

from mailweave.constants import ANYWHERE_OPERATOR, SPAM_OPERATOR, TRASH_OPERATOR


class MailboxScope(Enum):
    """The listing scopes a probe may walk. Both spellings of each, bound together.

    Both members are exercised end to end against the fake transport in
    `tests/test_preflight_runner_end_to_end.py`, at the wire rather than at this enum: the
    property that matters is what the two request parameters said *together*, and a test of
    this class alone would assert the pairing against the same table that defines it.
    """

    #: The default. What a mailbox owner means by "my mail": no spam, no trash.
    WITHOUT_SPAM_AND_TRASH = (f"-{SPAM_OPERATOR} -{TRASH_OPERATOR}", False)
    #: Everything Gmail will show, spam and trash included. PF-1's second arm: a thread whose
    #: replies were filtered into spam is a thread the two endpoints will disagree about
    #: unless both are told to look there.
    WHOLE_MAILBOX = (ANYWHERE_OPERATOR, True)

    def __init__(self, query: str, include_spam_trash: bool) -> None:
        self._query = query
        self._include_spam_trash = include_spam_trash

    @property
    def query(self) -> str:
        """The `q` operator spelling. Never used without `include_spam_trash` beside it."""
        return self._query

    @property
    def include_spam_trash(self) -> bool:
        """The `includeSpamTrash` request parameter that this `q` spelling must travel with."""
        return self._include_spam_trash
