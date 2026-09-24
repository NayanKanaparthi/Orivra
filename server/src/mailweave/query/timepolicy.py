"""AD A.6a: one rule for time, stated once, and applied in every place that needs it.

Date handling was previously unspecified in four places that all depend on it - relative
date resolution, `after:`/`before:` boundaries, `internalDate` ordering and the freshness
stamps. A.6a's five rules, and where each lives:

1. **Reference zone.** The Gmail API exposes no account timezone, so relative expressions
   resolve in the **host's** IANA zone (`TZ`, falling back to `UTC`). `reference_zone`.
   The zone actually used is declared in `asked_for.parsed.timezone`; MailWeave never
   silently assumes the account's zone is the host's.
2. **Declared absolute window.** Every resolved reference is emitted twice - as the Gmail
   operator form, and as `window_utc` in RFC 3339 UTC. `TimeWindow.as_wire`.
3. **Boundary safety.** A *relative* window is widened by `DATE_MARGIN_DAYS` on each
   bounded side and the widening is declared. An **explicit user-supplied absolute date is
   not widened** - `TimeWindow.widened_days` is 0 for it, and
   `test_an_explicit_absolute_date_is_not_widened` executes that distinction.
4. **Comparisons are UTC-epoch.** `start_ms` / `end_ms` are integer epoch milliseconds and
   are the only comparison surface this module offers. There is no local-time arithmetic
   anywhere below the resolution step.
5. **Stamps** are RFC 3339 UTC with `Z`, which `_rfc3339` produces.

**What this module does not do.** It resolves the closed, published table of relative
expressions in `RELATIVE_EXPRESSIONS` and nothing else. An expression outside the table is
not resolved, not guessed at, and not reported as a date constraint - it stays a residual
free-text term. "last Tuesday" is in the table; "the week we shipped" is not and never will
be, because resolving it is not a deterministic operation.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from mailweave.constants import DATE_MARGIN_DAYS
from mailweave.query.operators import OperatorName, ParsedOperator

#: The zone used when `TZ` is unset or names a zone this host does not have. A.6a rule 1.
FALLBACK_ZONE: Final[str] = "UTC"

_GMAIL_DATE_RE: Final[re.Pattern[str]] = re.compile(r"\A(\d{4})/(\d{1,2})/(\d{1,2})\Z")
_EPOCH_SECONDS_RE: Final[re.Pattern[str]] = re.compile(r"\A\d{9,11}\Z")
_RELATIVE_AGE_RE: Final[re.Pattern[str]] = re.compile(r"\A(\d{1,4})([dmy])\Z")

#: Days per unit for Gmail's `newer_than:`/`older_than:` suffixes, which take d / m / y.
#: Gmail documents no exact month or year length for these, so the values below are the
#: conventional ones and are **declared** rather than assumed: a window built from them is
#: relative and is therefore widened by rule 3 like every other relative window.
_AGE_UNIT_DAYS: Final[Mapping[str, int]] = {"d": 1, "m": 30, "y": 365}


def reference_zone(environ: Mapping[str, str] | None = None) -> ZoneInfo:
    """A.6a rule 1: the host's IANA zone from `TZ`, falling back to UTC.

    A `TZ` naming a zone this host has no data for falls back rather than raising: the
    query is answerable in UTC and the zone actually used is declared in the response, so a
    misconfigured host produces a *declared* different window instead of a failure.
    """
    name = (environ if environ is not None else os.environ).get("TZ") or FALLBACK_ZONE
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(FALLBACK_ZONE)


def _rfc3339(moment: datetime) -> str:
    """A.6a rule 5: RFC 3339 UTC with a `Z`, never a `+00:00` spelling."""
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class TimeWindow:
    """A resolved date reference, in UTC, with how it was resolved carried beside it.

    `start` is inclusive and `end` is exclusive. Either may be `None`: `after:2026/05/01`
    bounds one side only, and inventing the other would be a window the user never asked
    for appearing in `asked_for.parsed.window_utc` as though they had.
    """

    start: datetime | None
    end: datetime | None
    widened_days: int
    source: str
    zone: str

    def __post_init__(self) -> None:
        if self.start is None and self.end is None:
            raise ValueError("a time window bounds at least one side")
        for name in ("start", "end"):
            moment: datetime | None = getattr(self, name)
            if moment is not None and moment.tzinfo is None:
                raise ValueError(f"{name} carries no UTC offset; A.6a rule 4 compares instants")
        if self.start is not None and self.end is not None and self.end < self.start:
            raise ValueError("a time window ends before it starts")

    @property
    def start_ms(self) -> int | None:
        """A.6a rule 4: integer epoch milliseconds, the only comparison surface offered."""
        return None if self.start is None else int(self.start.timestamp() * 1000)

    @property
    def end_ms(self) -> int | None:
        return None if self.end is None else int(self.end.timestamp() * 1000)

    def contains_ms(self, internal_date_ms: int) -> bool:
        """`window_containment` (AD A.8) for one `internalDate`, in epoch milliseconds."""
        if self.start_ms is not None and internal_date_ms < self.start_ms:
            return False
        return not (self.end_ms is not None and internal_date_ms >= self.end_ms)

    def as_wire(self) -> dict[str, str]:
        """A.6a rule 2's `window_utc`, carrying only the sides that are bounded."""
        rendered: dict[str, str] = {}
        if self.start is not None:
            rendered["start"] = _rfc3339(self.start)
        if self.end is not None:
            rendered["end"] = _rfc3339(self.end)
        return rendered

    def operators(self) -> tuple[ParsedOperator, ...]:
        """A.6a rule 2's other half: the same window as Gmail's date-valued operator form.

        Emitted in Gmail's `YYYY/MM/DD` spelling from the **UTC** instants, so the operator
        form and `window_utc` are two renderings of one value rather than two computations.
        """
        rendered: list[ParsedOperator] = []
        if self.start is not None:
            rendered.append(ParsedOperator(name=OperatorName.AFTER, value=_gmail_date(self.start)))
        if self.end is not None:
            rendered.append(ParsedOperator(name=OperatorName.BEFORE, value=_gmail_date(self.end)))
        return tuple(rendered)

    def widened(self, factor: int) -> TimeWindow:
        """AD A.7's L3 broadening: the same window, `factor` times as long, same centre.

        A one-sided window is extended on the side it has, because there is no centre to
        scale about; the extension is the same length the bounded side would have gained.
        """
        if factor < 1:
            raise ValueError("a broadening factor widens; it never narrows")
        if self.start is not None and self.end is not None:
            span = self.end - self.start
            growth = (span * (factor - 1)) / 2
            return TimeWindow(
                start=self.start - growth,
                end=self.end + growth,
                widened_days=self.widened_days,
                source=f"{self.source}+broadened_x{factor}",
                zone=self.zone,
            )
        step = timedelta(days=DATE_MARGIN_DAYS * factor)
        return TimeWindow(
            start=None if self.start is None else self.start - step,
            end=None if self.end is None else self.end + step,
            widened_days=self.widened_days,
            source=f"{self.source}+broadened_x{factor}",
            zone=self.zone,
        )


def _gmail_date(moment: datetime) -> str:
    utc = moment.astimezone(UTC)
    return f"{utc.year:04d}/{utc.month:02d}/{utc.day:02d}"


def _midnight(day: date, zone: ZoneInfo) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=zone)


def _quarter_start(day: date) -> date:
    return date(day.year, ((day.month - 1) // 3) * 3 + 1, 1)


def _month_start(day: date) -> date:
    return date(day.year, day.month, 1)


def _add_months(day: date, months: int) -> date:
    total = (day.year * 12 + day.month - 1) + months
    return date(total // 12, total % 12 + 1, 1)


#: The closed, published table of relative expressions this module resolves. A pattern is
#: matched against the query's residual free text, case-folded. Anything absent from this
#: table is **not** a date reference: it stays a free-text term (see the module docstring).
#:
#: Ordered longest-first where two patterns could both match, so `last week` is not read as
#: `week`. The order is part of the table, which is why it is a tuple.
RELATIVE_EXPRESSIONS: Final[tuple[str, ...]] = (
    "today",
    "yesterday",
    "this week",
    "last week",
    "this month",
    "last month",
    "this quarter",
    "last quarter",
    "this year",
    "last year",
    r"last (\d{1,3}) days",
    r"past (\d{1,3}) days",
    r"(\d{1,3}) days ago",
)

_COMPILED_RELATIVE: Final[tuple[tuple[str, re.Pattern[str]], ...]] = tuple(
    (spelling, re.compile(rf"(?<![a-z0-9]){spelling}(?![a-z0-9])"))
    for spelling in RELATIVE_EXPRESSIONS
)


@dataclass(frozen=True)
class RelativeMatch:
    """One relative expression found in the free text, with the span it occupied."""

    spelling: str
    text: str
    start: int
    end: int


def find_relative_expression(free_text: str) -> RelativeMatch | None:
    """The first expression of `RELATIVE_EXPRESSIONS` present in `free_text`, or nothing.

    First by the table's order, not by position in the string, so the resolution of a query
    is a function of the published table rather than of word order (ROUTE-03's
    reproducibility, applied to the parse rather than to the ladder).
    """
    folded = free_text.casefold()
    for spelling, pattern in _COMPILED_RELATIVE:
        found = pattern.search(folded)
        if found is not None:
            return RelativeMatch(
                spelling=spelling, text=found.group(0), start=found.start(), end=found.end()
            )
    return None


def resolve_relative(match: RelativeMatch, *, now: datetime, zone: ZoneInfo) -> TimeWindow:
    """Turn one table entry into a UTC window, widened by A.6a rule 3.

    `now` is a parameter rather than a call to the clock so that a resolution is a pure
    function of its inputs: a relative window that changes under a test's feet cannot be
    asserted, and a ladder whose executed `q` depends on the wall clock cannot be replayed
    (ROUTE-03).
    """
    local_now = now.astimezone(zone)
    today = local_now.date()
    spelling = match.spelling
    digits = re.search(r"\d+", match.text)
    if spelling == "today":
        start, end = today, today + timedelta(days=1)
    elif spelling == "yesterday":
        start, end = today - timedelta(days=1), today
    elif spelling in {"this week", "last week"}:
        monday = today - timedelta(days=today.weekday())
        offset = 0 if spelling == "this week" else 7
        start = monday - timedelta(days=offset)
        end = start + timedelta(days=7)
    elif spelling in {"this month", "last month"}:
        first = _month_start(today)
        start = first if spelling == "this month" else _add_months(first, -1)
        end = _add_months(start, 1)
    elif spelling in {"this quarter", "last quarter"}:
        first = _quarter_start(today)
        start = first if spelling == "this quarter" else _add_months(first, -3)
        end = _add_months(start, 3)
    elif spelling in {"this year", "last year"}:
        year = today.year if spelling == "this year" else today.year - 1
        start, end = date(year, 1, 1), date(year + 1, 1, 1)
    elif digits is not None and spelling.endswith("days ago"):
        start = today - timedelta(days=int(digits.group(0)))
        end = start + timedelta(days=1)
    elif digits is not None:
        start = today - timedelta(days=int(digits.group(0)))
        end = today + timedelta(days=1)
    else:  # pragma: no cover - unreachable while the table and this branch table agree
        raise ValueError(f"no resolver for relative expression {spelling!r}")
    margin = timedelta(days=DATE_MARGIN_DAYS)
    return TimeWindow(
        start=(_midnight(start, zone) - margin).astimezone(UTC),
        end=(_midnight(end, zone) + margin).astimezone(UTC),
        widened_days=DATE_MARGIN_DAYS,
        source=f"relative:{spelling}",
        zone=str(zone),
    )


def _operator_instant(value: str, *, zone: ZoneInfo, end_of_day: bool) -> datetime | None:
    match = _GMAIL_DATE_RE.match(value)
    if match is not None:
        year, month, day = (int(part) for part in match.groups())
        try:
            midnight = _midnight(date(year, month, day), zone)
        except ValueError:
            return None
        return (midnight + timedelta(days=1 if end_of_day else 0)).astimezone(UTC)
    if _EPOCH_SECONDS_RE.match(value) is not None:
        return datetime.fromtimestamp(int(value), tz=UTC)
    return None


def window_from_operators(
    operators: Iterable[ParsedOperator], *, now: datetime, zone: ZoneInfo
) -> TimeWindow | None:
    """The window the query's own date operators describe, or `None` if they describe none.

    **No window built here is widened, and that is A.6a rule 3 applied rather than waived**
    (R-RETR-011). Rule 3's margin exists because Gmail's `after:`/`before:` boundary zone is
    undocumented for our account, and it is applied where MailWeave *renders* the boundary
    itself - the `date_window` constraint a relative expression resolves to, which really is
    sent one day wider on each side. An operator the user wrote is carried into the `q`
    **verbatim** (LEX-02's fidelity half, asserted operator by operator at L1's executed
    `q`), so there is nothing here for a margin to widen: it would move only
    `asked_for.parsed.window_utc`, which is the response's statement of *what was searched*.
    That is what it used to do. `newer_than:7d` cut at one instant, `window_utc` declared a
    range a day wider on each side, and `asked_for.enforced` carried
    `date_window_widened:+/-1d` for a widening no probe performed - so a message inside the
    declared window and outside the executed one was never listed, never disclosed and never
    withheld, while the response said it had been searched for. A.6a rule 2 is the rule that
    settles it: "the reader can always see what was actually searched."

    Two families still meet here and they are still different, which is the other half of
    rule 3's point:

      * `after:` / `before:` carrying an explicit date or epoch are **absolute**: the user
        stated the boundary and MailWeave sends it unchanged;
      * `newer_than:` / `older_than:` are **relative** ages, resolved against `now` so the
        response can state the instant they cut at - and sent unchanged too, because the
        operator is what goes on the wire.

    A date operator whose value is neither shape (a typo, a spelling Gmail would refuse)
    contributes no bound. It is still an *enforced* operator - it goes onto the wire and
    Gmail judges it - but MailWeave does not claim a window it could not resolve.

    **A pair of operators describing an empty window is the same case**, and it is the one
    this function used to crash on: `newer_than:7d older_than:30d` is an ordinary thing to
    type and its two bounds cross, so building the `TimeWindow` raised a bare `ValueError`
    ("a time window ends before it starts") out of `analyse` - not a MailWeave error, not a
    declared inability, just an uncaught exception on a user's query. There is no window to
    claim, so none is claimed; both operators are still carried onto the wire verbatim and
    Gmail judges them, which is the rule one paragraph up applied to a pair rather than to a
    value. The ladder then answers the way it answers any zero-hit query: L2 drops one date
    operator and `empty_diagnosis` names the drop that restores results, which is a better
    answer than a refusal and is the reason this returns `None` rather than raising.
    Executed by `test_a_pair_of_date_operators_that_cross_resolves_to_no_window_not_a_crash`.

    Executed by `test_a_gmail_relative_age_operator_declares_the_instant_it_actually_cuts_at`
    and, for the family that is widened because it is rendered,
    `test_a_widened_relative_expression_sends_the_widened_bound_it_declares`.
    """
    start: datetime | None = None
    end: datetime | None = None
    relative = False
    sources: list[str] = []
    for operator in operators:
        if operator.negated:
            continue
        name = operator.name
        if name is OperatorName.AFTER:
            moment = _operator_instant(operator.value, zone=zone, end_of_day=False)
            if moment is not None:
                start = moment if start is None else max(start, moment)
                sources.append(f"operator:after:{operator.value}")
        elif name is OperatorName.BEFORE:
            moment = _operator_instant(operator.value, zone=zone, end_of_day=False)
            if moment is not None:
                end = moment if end is None else min(end, moment)
                sources.append(f"operator:before:{operator.value}")
        elif name in {OperatorName.NEWER_THAN, OperatorName.OLDER_THAN}:
            age = _RELATIVE_AGE_RE.match(operator.value.casefold())
            if age is None:
                continue
            days = int(age.group(1)) * _AGE_UNIT_DAYS[age.group(2)]
            boundary = now.astimezone(UTC) - timedelta(days=days)
            relative = True
            if name is OperatorName.NEWER_THAN:
                start = boundary if start is None else max(start, boundary)
            else:
                end = boundary if end is None else min(end, boundary)
            sources.append(f"operator:{name.value}:{operator.value}")
    if start is None and end is None:
        return None
    if start is not None and end is not None and end < start:
        return None
    # `relative` still decides nothing about the *bounds* - see the docstring - and is kept
    # because the source string it feeds is how a reader tells the two families apart.
    del relative
    return TimeWindow(
        start=start,
        end=end,
        widened_days=0,
        source="+".join(sources),
        zone=str(zone),
    )


def widening_declaration(window: TimeWindow | None) -> str | None:
    """A.6a rule 3's declaration, in the spelling the architecture writes it in.

    Returned as a string because it goes into `asked_for.enforced`, which the wire schema
    types as a tuple of strings; A.6a names that field explicitly. `None` when nothing was
    widened, so a response never carries a widening claim with no widening behind it.
    """
    if window is None or window.widened_days == 0:
        return None
    return f"date_window_widened:±{window.widened_days}d, timezone-boundary safety"


def strip_relative_expression(free_text: str, match: RelativeMatch | None) -> str:
    """The residual text with the resolved expression removed, so it is not searched twice.

    A resolved date reference has become an `after:`/`before:` pair; leaving its words in
    the free-text terms would additionally require the message body to contain the word
    "yesterday", which is a constraint the user did not state.
    """
    if match is None:
        return free_text
    folded = free_text.casefold()
    found = re.search(re.escape(match.text), folded)
    if found is None:  # pragma: no cover - the match came from this same string
        return free_text
    return f"{free_text[: found.start()]} {free_text[found.end() :]}".strip()
