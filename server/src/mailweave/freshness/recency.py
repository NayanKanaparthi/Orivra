"""LR, the recency reconciliation rung: `2 + 20n`, and what a surfaced message may claim.

**The rung exists because Gmail's index lags its own delivery.** A message that arrived
during a query's own round trip is in the mailbox and is not yet in the `q` index, so the
lexical ladder cannot see it however many pages it walks. `history.list(startHistoryId)`
does see it: it reports `messagesAdded` from a watermark forward, with id / threadId /
labelIds and **not** headers or bodies.

**Priced honestly, which A.7 originally was not.** `history.list` costs 2 u and returns
candidates that carry nothing to judge them by, so each one must be fetched at 20 u. The
real cost is `2 + 20n` with `n <= max_recency_fetch = 8` - at most 162 u - and A.7's former
flat "2 u" was wrong by up to two orders of magnitude. Candidates beyond the cap are
`withheld` records naming `max_recency_fetch`, never a silent truncation.

**What a surfaced message may claim about the query.** Only that it does not contradict the
constraints `freshness.recheck` can evaluate exactly. Free text is not re-checked and the
row says so, verbatim, in the string D.9 fixes; the role is `context`, never `matched`.
That is a correctness *and* a provenance rule: attributing an LR row to the user's `q`
would be this server asserting a Gmail match it never observed (R-03, T-RC3).

**The watermark moves after the walk, not before it** (amendment A10's ordering, applied
here). A watermark advanced before the walk would sit above changes the walk then never
looked at, and the next query would start from a place this one never reconciled - a gap
that is invisible because every individual response looks complete.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from mailweave.constants import MAX_RECENCY_FETCH
from mailweave.envelope.disposition import DispositionLedger
from mailweave.envelope.reasons import RungId
from mailweave.envelope.vocab import BudgetCapName, NotTriedWhy, ToolName, WithheldCap
from mailweave.envelope.wire import Affordance, NotTriedEntry
from mailweave.errors import MailweaveError
from mailweave.freshness.recheck import RecheckVerdict, recency_reason, recheck
from mailweave.freshness.watermark import Rebaseline, Watermark, WatermarkFile
from mailweave.gmail.client import GmailClient
from mailweave.gmail.models import Message
from mailweave.gmail.rates import GmailEndpoint
from mailweave.policy.account import force_rungs
from mailweave.policy.budget import BudgetAccountant, CapBreach
from mailweave.query.analysis import ParsedQuery


class RecencyState(StrEnum):
    """What LR did for this query."""

    RAN = "ran"
    #: No watermark for this mailbox yet, so there is no place to walk from. The first query
    #: of a new install is in this state and it is not a failure: the watermark is written
    #: at the end of it, and the next query has one.
    NO_WATERMARK = "no_watermark"
    #: Gmail 404'd the stored `historyId`: it is older than Gmail's retention. A **declared**
    #: re-baseline, reported in the response (D.9, RO F6).
    REBASELINED = "rebaselined"
    #: A cap stopped the walk or the fetches.
    BLOCKED = "blocked"
    #: The query names nothing LR could reconcile against.
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class SurfacedMessage:
    """One message LR fetched, with the verdict and the sentence it carries."""

    message: Message
    verdict: RecheckVerdict
    reason: str

    @property
    def id(self) -> str:
        return self.message.id

    @property
    def thread_id(self) -> str:
        return self.message.thread_id


@dataclass
class RecencyRun:
    """LR's account of itself for one query."""

    state: RecencyState
    why: str
    #: The watermark the walk started from, when there was one.
    started_from: Watermark | None = None
    #: What the walk ended at, so the caller can advance the watermark after the response.
    latest_history_id: str | None = None
    surfaced: tuple[SurfacedMessage, ...] = ()
    #: Candidates the walk found that `max_recency_fetch` would not let us fetch. In `H`
    #: already - `history_additions` records them - and owed a withheld record each.
    beyond_cap: tuple[str, ...] = ()
    #: Candidates fetched and re-checked into a contradiction. Not surfaced, still in `H`.
    contradicted: tuple[str, ...] = ()
    rebaseline: Rebaseline | None = None
    fetched: int = 0
    breach: CapBreach | None = None
    errors: tuple[str, ...] = ()
    quota_units: int = 0
    by_thread: Mapping[str, str] = field(default_factory=dict)

    @property
    def ran(self) -> bool:
        return self.state in {RecencyState.RAN, RecencyState.REBASELINED}

    @property
    def surfaced_ids(self) -> frozenset[str]:
        return frozenset(row.id for row in self.surfaced)

    @property
    def not_tried_why(self) -> NotTriedWhy | None:
        return {
            RecencyState.RAN: None,
            RecencyState.REBASELINED: None,
            RecencyState.NO_WATERMARK: NotTriedWhy.NOT_APPLICABLE,
            RecencyState.NOT_APPLICABLE: NotTriedWhy.NOT_APPLICABLE,
            RecencyState.BLOCKED: NotTriedWhy.BUDGET,
        }[self.state]

    def entry(self, *, query: str) -> NotTriedEntry | None:
        why = self.not_tried_why
        if why is None:
            return None
        if why is NotTriedWhy.NOT_APPLICABLE:
            return NotTriedEntry(rung=RungId.LR.value, why=why)
        affordance = (
            self.breach.affordance
            if self.breach is not None
            else force_rungs(RungId.LR, query=query)
        )
        return NotTriedEntry(rung=RungId.LR.value, why=why, affordance=affordance)


def recency_widening(query: str, *, fetches: int) -> Affordance:
    """A.7a's remedy for `max_recency_fetch`: the same search with a wider fetch bound."""
    return Affordance(
        tool=ToolName.SEARCH, args={"query": query, "budget": {"max_recency_fetch": fetches}}
    )


class RecencyRunner:
    """Executes LR against one Gmail client, one ledger and one watermark file."""

    def __init__(
        self,
        client: GmailClient,
        ledger: DispositionLedger,
        *,
        watermark: WatermarkFile,
        identity: str,
        accountant: BudgetAccountant | None = None,
        max_fetch: int = MAX_RECENCY_FETCH,
        label_ids: Mapping[str, str] | None = None,
    ) -> None:
        self._client = client
        self._ledger = ledger
        self._watermark = watermark
        self._identity = identity
        self._accountant = accountant
        self._max_fetch = max_fetch
        self._label_ids = dict(label_ids or {})

    def run(self, parsed: ParsedQuery) -> RecencyRun:
        """Walk history from the stored watermark, fetch what fits, re-check what we fetched."""
        if not parsed.constraints:
            return RecencyRun(
                state=RecencyState.NOT_APPLICABLE,
                why="the query names nothing to reconcile a new message against",
            )
        stored = self._watermark.load_for_identity(self._identity)
        if stored is None:
            return RecencyRun(
                state=RecencyState.NO_WATERMARK,
                why=(
                    "no watermark is stored for this mailbox yet, so there is no place to "
                    "walk history from; this response records one for the next query"
                ),
            )
        breach = self._spend(GmailEndpoint.HISTORY_LIST)
        if breach is not None:
            return RecencyRun(
                state=RecencyState.BLOCKED,
                why=f"the history walk was not sent: {breach.rendered()}",
                started_from=stored,
                breach=breach,
            )
        before = self._ledger.hit_ids
        try:
            walk = self._client.history_additions(self._ledger, start_history_id=stored.history_id)
        except MailweaveError as failure:
            return RecencyRun(
                state=RecencyState.BLOCKED,
                why=f"the history walk failed: {type(failure).__name__}",
                started_from=stored,
                errors=(type(failure).__name__,),
            )
        if walk.rebaseline_required:
            # **Declared, never silent** (D.9, RO F6). The stored place is older than Gmail's
            # retention; the response says so and the watermark is re-based to whatever this
            # query observes, which the caller does after the response is built.
            return RecencyRun(
                state=RecencyState.REBASELINED,
                why=(
                    "gmail no longer holds history from the stored watermark, so this "
                    "response could not reconcile recent arrivals and declares a re-baseline"
                ),
                started_from=stored,
                rebaseline=self._watermark.rebaseline(stored),
            )

        candidates = sorted(self._ledger.hit_ids - before)
        within, beyond = candidates[: self._max_fetch], candidates[self._max_fetch :]
        surfaced: list[SurfacedMessage] = []
        contradicted: list[str] = []
        fetched = 0
        errors: list[str] = []
        for message_id in within:
            breach = self._spend(GmailEndpoint.MESSAGES_GET)
            if breach is not None:
                # The rest become cap records like the ones beyond `max_recency_fetch`: the
                # ids are in `H` either way and the response owes an account of each.
                beyond = [*beyond, message_id]
                continue
            try:
                message = self._client.get_message(message_id, message_format="full")
            except MailweaveError as failure:
                errors.append(type(failure).__name__)
                continue
            fetched += 1
            verdict = recheck(message, parsed, label_ids=self._label_ids)
            if not verdict.passed:
                contradicted.append(message_id)
                continue
            surfaced.append(
                SurfacedMessage(
                    message=message,
                    verdict=verdict,
                    reason=recency_reason(stored.history_id, verdict),
                )
            )
        return RecencyRun(
            state=RecencyState.RAN,
            why=(
                f"history.list from {stored.history_id} reported {len(candidates)} additions; "
                f"{fetched} fetched at max_recency_fetch={self._max_fetch}"
            ),
            started_from=stored,
            latest_history_id=walk.latest_history_id,
            surfaced=tuple(surfaced),
            beyond_cap=tuple(beyond),
            contradicted=tuple(contradicted),
            fetched=fetched,
            breach=breach,
            errors=tuple(errors),
            # D.9's own arithmetic, reported rather than recomputed by a reader: 2 u for the
            # walk plus 20 u for each message it fetched.
            quota_units=2 + 20 * fetched,
            by_thread={row.id: row.thread_id for row in surfaced},
        )

    def _spend(self, endpoint: GmailEndpoint) -> CapBreach | None:
        if self._accountant is None:
            return None
        return self._accountant.check((endpoint,))


#: A.7a's cap name for a candidate the fetch bound would not reach.
RECENCY_CAP: WithheldCap = WithheldCap.MAX_RECENCY_FETCH

#: And the budget-key spelling of the same cap, for `budget_caps_hit`.
RECENCY_BUDGET_CAP: BudgetCapName = BudgetCapName.MAX_RECENCY_FETCH


__all__ = [
    "RECENCY_BUDGET_CAP",
    "RECENCY_CAP",
    "RecencyRun",
    "RecencyRunner",
    "RecencyState",
    "SurfacedMessage",
    "recency_widening",
]
