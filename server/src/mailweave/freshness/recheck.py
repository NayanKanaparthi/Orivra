"""The closed local re-check subset, and the free text it refuses to pretend about (AD D.9).

**Why this file is small on purpose.** T-RO3 names "reimplementing Gmail's query semantics"
as option (b)'s biggest hidden cost, and E.4 cites it to reject persistent indexes. A
recency rung that re-checked a message against the *whole* query would be paying exactly
that cost, incrementally, one operator at a time, and would be wrong in the direction
nobody notices: a message that fails a stemming rule we implemented slightly differently
from Gmail's is a false negative with a confident provenance string attached.

So the subset is closed, published, and small enough to be obviously exact:

    re-checked here     from / to / cc      normalised address equality
                        after / before      integer internalDate comparison (A.6a rule 4)
                        has:attachment      a scan of the payload's own parts
                        label:              labelIds, resolved once per process

    never re-checked    free-text terms, `subject:` term semantics, stemming, phrase
                        semantics, OR / negation grouping

**A message that survives this check has not been shown to match the query.** It has been
shown not to *contradict* the constraints we can evaluate exactly. Those are different
statements, and D.9 requires the second one be what the response says: a row LR surfaced
while any residual free-text term exists is `role: "context"` with a verbatim reason that
names what was re-checked and says the free-text terms were not - never attributed to the
user's query as a `q` match (R-03, T-RC3).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from mailweave.content.payload import Part
from mailweave.envelope.vocab import RecheckedOperator
from mailweave.gmail.models import Message
from mailweave.query.analysis import ParsedQuery, fold
from mailweave.query.operators import OperatorName
from mailweave.structure.participants import addresses_in_header

#: The operators this module can evaluate exactly. Defined in `envelope.vocab` because it
#: reaches the wire inside `RecencyContext`, and a vocabulary the response carries belongs
#: with the other vocabularies the response carries.
RecheckOperator = RecheckedOperator


#: The participant operators the re-check evaluates, in D.9's own order.
_PARTICIPANT_OPERATORS: Final[tuple[OperatorName, ...]] = (
    OperatorName.FROM,
    OperatorName.TO,
    OperatorName.CC,
)

#: The operator names D.9 lists as re-checked, keyed to the header or field each reads.
RECHECKED: Final[frozenset[OperatorName]] = frozenset(
    {
        OperatorName.FROM,
        OperatorName.TO,
        OperatorName.CC,
        OperatorName.AFTER,
        OperatorName.BEFORE,
        OperatorName.LABEL,
        OperatorName.HAS,
    }
)


@dataclass(frozen=True)
class RecheckVerdict:
    """Whether this message contradicts what we can check, and what was checked.

    `passed` false is a **contradiction**, which is a fact. `passed` true is the absence of
    one, which is weaker - see the module docstring, and see `reason` for the sentence the
    response actually carries.
    """

    passed: bool
    checked: tuple[RecheckedOperator, ...]
    #: Why it failed, when it did. Never a value from the message: R-SEC-043 forbids an
    #: error that echoes what it rejected, and this string reaches the trace.
    failed_on: RecheckedOperator | None = None
    #: Whether the query carries free text this check could not evaluate.
    residual_free_text: bool = False

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(operator.value for operator in self.checked)


def _addresses(message: Message, names: Sequence[str]) -> frozenset[str]:
    payload = message.payload
    if payload is None:
        return frozenset()
    found: set[str] = set()
    for name in names:
        # `(display name, address)`, in that order. Unpacking it backwards is how the E4
        # fill's participant component came to match against display names for a round.
        for _display, address in addresses_in_header(payload.header(name)):
            found.add(fold(address))
    return frozenset(found)


def _has_attachment(part: Part | None) -> bool:
    """A scan of the payload's own parts, which is what `has:attachment` means locally.

    A part with a filename is an attachment; a `multipart/*` container is walked. This
    reads structure the observation stated and never a header the sender controls as a
    claim about content - `Content-Disposition` says how to display a part, and a part with
    a filename is one whatever it says.
    """
    if part is None:
        return False
    if part.filename:
        return True
    return any(_has_attachment(child) for child in part.parts or ())


def recheck(
    message: Message,
    parsed: ParsedQuery,
    *,
    label_ids: Mapping[str, str] = {},
) -> RecheckVerdict:
    """Evaluate the closed subset against one message. Never evaluates anything else.

    `label_ids` maps a `label:` value to the Gmail label id it resolves to - the one
    `labels.list` lookup A.5 allows, done once per process by the caller rather than here,
    so this function makes no calls at all. A `label:` the map does not name is **not
    checked**, and its absence from `checked` is what stops the response from claiming it
    was: a re-check that silently skipped an operator it could not resolve would be a
    narrower check reported as the full one.
    """
    checked: list[RecheckedOperator] = []
    wanted_addresses: set[str] = set()
    for operator in parsed.operators:
        if operator.name in _PARTICIPANT_OPERATORS and not operator.negated:
            wanted_addresses.add(fold(operator.value))
    if wanted_addresses:
        checked.append(RecheckOperator.PARTICIPANT)
        present = _addresses(message, ("From", "To", "Cc"))
        if not (wanted_addresses & present):
            return RecheckVerdict(
                passed=False,
                checked=tuple(checked),
                failed_on=RecheckOperator.PARTICIPANT,
                residual_free_text=bool(parsed.search_terms or parsed.phrases),
            )

    window = parsed.window
    if window is not None and message.internal_date is not None:
        checked.append(RecheckOperator.DATE)
        stamp = int(message.internal_date)
        start, end = window.start_ms, window.end_ms
        if (start is not None and stamp < start) or (end is not None and stamp >= end):
            return RecheckVerdict(
                passed=False,
                checked=tuple(checked),
                failed_on=RecheckOperator.DATE,
                residual_free_text=bool(parsed.search_terms or parsed.phrases),
            )

    wants_attachment = any(
        operator.name is OperatorName.HAS
        and fold(operator.value) == "attachment"
        and not operator.negated
        for operator in parsed.operators
    )
    if wants_attachment:
        checked.append(RecheckOperator.HAS_ATTACHMENT)
        if not _has_attachment(message.payload):
            return RecheckVerdict(
                passed=False,
                checked=tuple(checked),
                failed_on=RecheckOperator.HAS_ATTACHMENT,
                residual_free_text=bool(parsed.search_terms or parsed.phrases),
            )

    wanted_labels = {
        label_ids[fold(operator.value)]
        for operator in parsed.operators
        if operator.name is OperatorName.LABEL
        and not operator.negated
        and fold(operator.value) in label_ids
    }
    if wanted_labels:
        checked.append(RecheckOperator.LABEL)
        # `label_ids is None` means the observation stated no labels, which is not the same
        # fact as a message with none (round 19, R-RETR-039). An unobserved label set cannot
        # contradict anything, so this is a pass with the operator **not** in `checked`.
        stated = message.label_ids
        if stated is None:
            checked.pop()
        elif not (wanted_labels & set(stated)):
            return RecheckVerdict(
                passed=False,
                checked=tuple(checked),
                failed_on=RecheckOperator.LABEL,
                residual_free_text=bool(parsed.search_terms or parsed.phrases),
            )

    return RecheckVerdict(
        passed=True,
        checked=tuple(checked),
        residual_free_text=bool(parsed.search_terms or parsed.phrases),
    )


def recency_reason(history_id: str, verdict: RecheckVerdict) -> str:
    """D.9's verbatim provenance string, built from what was actually checked.

    The sentence is fixed by the architecture and is reproduced here word for word, with
    two substitutions: the watermark the walk started from, and the list of constraints this
    message was re-checked against. It ends by saying the free-text terms were **not**
    re-checked and that Gmail's `q` did not match this message - which is the whole point of
    the string and the half that a paraphrase would lose.
    """
    checked = ", ".join(verdict.names) if verdict.checked else "none"
    return (
        f"history.list messageAdded since {history_id}; "
        f"constraints re-checked locally: [{checked}]; "
        "free-text terms NOT re-checked - Gmail q did not match this message"
    )


__all__ = [
    "RECHECKED",
    "RecheckOperator",
    "RecheckVerdict",
    "RecheckedOperator",
    "recency_reason",
    "recheck",
]
