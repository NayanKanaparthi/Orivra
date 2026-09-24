"""A synthetic mailbox that answers Gmail's four id-yielding endpoints, behind the real client.

This is the fixture the lexical-ladder tests stand on, and two properties of it are what
make those tests mean anything:

  * **it evaluates `q` message-scoped.** RO F2 is the fact the whole project turns on: in
    the API, all terms of a `q` must match within a *single* message, and there is no thread
    operator (RO F3). `matches` below implements that, so a query whose constraints are
    satisfied jointly by different messages of one thread returns **nothing** here, exactly
    as it would from Gmail - which is what makes L1b's recovery a real recovery rather than
    a fixture that was generous;
  * **it is written from the documentation, not from the parser.** Nothing in this module
    imports `mailweave.query`. A double that reused the parser would agree with it about
    every mis-parse, and the operator-parse fidelity table would be checking the parser
    against itself.

It also **refuses an operator it does not implement** rather than ignoring it. An ignored
operator silently widens the query, which would make a rung look successful because the
double was permissive - the exact shape of a test that passes for the wrong reason (AL §7.2).

No fixture here contains real or realistic personal mail. Addresses use the reserved
`.example` / `.invalid` TLDs (RFC 2606/6761), and every subject and body is invented for the
structural property the test is about.
"""

from __future__ import annotations

import base64
import json
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

import httpx

from tests.fixtures.gmail_shapes import FakeGmail, json_response

#: Operators this double evaluates. An operator outside this set raises, so a test cannot
#: pass because the mailbox quietly ignored a constraint the ladder sent.
IMPLEMENTED_OPERATORS: frozenset[str] = frozenset(
    {
        "from",
        "to",
        "cc",
        "subject",
        "after",
        "before",
        "newer_than",
        "older_than",
        "label",
        "in",
        "has",
        "rfc822msgid",
        "is",
        # `category:` is one of Gmail's documented operators and the ladder can send it, so a
        # double that raised on it was refusing a query the product accepts (round 19). Gmail
        # files a tab as a `CATEGORY_<TAB>` label id, which is what this matches on - written
        # from the documentation, like every other branch here, and not from the parser.
        "category",
    }
)


class UnimplementedOperator(AssertionError):
    """The ladder sent an operator this double does not evaluate. Never ignore one."""


#: `historyTypes` values mapped to the response key each one selects. Written from the API
#: reference, like every other branch here. A `historyTypes` value outside this mapping is
#: refused rather than ignored, for the same reason an unimplemented `q` operator is: an
#: ignored filter silently widens what comes back, and a liveness probe that asked for four
#: types and was answered with all records regardless would pass with one type on the wire.
_HISTORY_TYPE_KEYS: dict[str, str] = {
    "messageAdded": "messagesAdded",
    "messageDeleted": "messagesDeleted",
    "labelAdded": "labelsAdded",
    "labelRemoved": "labelsRemoved",
}


@dataclass(frozen=True)
class Msg:
    """One synthetic message. Every field is something Gmail would really return.

    The four threading fields are WS-05's, and each of them is a header **value** rather
    than a parsed form, so a test can write the broken shapes that arrive in the field -
    a comma-separated `References`, a client's commentary in an `In-Reply-To`, a header
    present and empty - without the double being the thing that decides what they mean.
    `omit_message_id` is the fifth state and is not a value at all: it removes the header,
    which is what AD D.4a's "a missing `Message-ID`" case needs and what no value can
    express.
    """

    id: str
    thread_id: str
    sender: str
    subject: str
    body: str
    internal_date_ms: int
    to: tuple[str, ...] = ()
    cc: tuple[str, ...] = ()
    labels: tuple[str, ...] = ("INBOX",)
    rfc822_message_id: str | None = None
    has_attachment: bool = False
    #: Raw `In-Reply-To` / `References` header values. `None` means the header is absent,
    #: which is a different fact from a header whose value names nothing.
    in_reply_to: str | None = None
    references: str | None = None
    #: `Reply-To`, as a raw header value. A routing directive the sender asserts.
    reply_to: str | None = None
    #: `Authentication-Results`, as a raw header value (WS-14 INJ-05). Written by the
    #: *receiving* MTA, not by the sender, and carried here verbatim so a test can drive a
    #: pass record, a fail record and a record past `MAX_AUTH_RECORD_CHARS` through the same
    #: path a real one takes. `None` means the header is absent, which is a different fact
    #: from a record that says nothing passed.
    authentication_results: str | None = None
    #: Emit no `Message-ID` header at all (AD D.4a).
    omit_message_id: bool = False
    #: The HTML half of a `multipart/alternative` message. When set, this message arrives in
    #: the shape most real mail arrives in - a `text/plain` part and a `text/html` part under
    #: `multipart/alternative` - rather than as a bare `text/plain` payload.
    #:
    #: **Round 27, R-MCP-023.** This double had no way to emit that shape, and twenty-six
    #: review rounds therefore never served one: the content layer emits an
    #: `alternative_part_unused` reduction for the unused half, and the wire layer refused it,
    #: so `mailweave_search` answered `-32603` on the commonest message format there is.
    html_alternative: str | None = None
    #: The `charset=` this message *declares* on its text part. Left `None` the part carries
    #: no `Content-Type` header, which is the shape every other fixture message has. Set to a
    #: name Python cannot resolve (`unicode`, `UNKNOWN-8BIT`) or to one it can but that is not
    #: the encoding used (`ISO-8859-8-I`) to reach AD D.4a's charset ladder from a served
    #: response rather than only from `content`'s own unit tests.
    declared_charset: str | None = None
    #: Encode the body with this codec rather than UTF-8, so a declared charset can be right,
    #: wrong, or unresolvable independently of what the bytes actually are.
    body_encoding: str = "utf-8"

    @property
    def message_id_header(self) -> str | None:
        if self.omit_message_id:
            return None
        return self.rfc822_message_id or f"<{self.id}@mail.invalid>"

    @property
    def haystack(self) -> str:
        """What a bare term is matched against: headers a human would search plus the body."""
        return " ".join((self.subject, self.body, self.sender, *self.to, *self.cc))


#: The attachment a `Msg(has_attachment=True)` carries. The zero-width joiner and the
#: right-to-left override are deliberate: an attachment filename is the canonical
#: Trojan-Source target (R-SEC-011), and a fixture whose filename is plain ASCII cannot show
#: that the stripping happens on the path a real response takes.
ATTACHMENT_FILENAME = "quarterly\u200d\u202ereport.pdf"
ATTACHMENT_SIZE = 20_480


def epoch_ms(year: int, month: int, day: int, hour: int = 12) -> int:
    return int(datetime(year, month, day, hour, tzinfo=UTC).timestamp() * 1000)


def _split(query: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    quoted = False
    for char in query:
        if char == '"':
            quoted = not quoted
            current.append(char)
        elif char.isspace() and not quoted:
            if current:
                tokens.append("".join(current))
                current = []
        else:
            current.append(char)
    if current:
        tokens.append("".join(current))
    return tokens


def _collapse(text: str) -> str:
    return " ".join(text.casefold().split())


def _term_matches(term: str, message: Msg) -> bool:
    return (
        re.search(rf"(?<![\w]){re.escape(term.casefold())}(?![\w])", _collapse(message.haystack))
        is not None
    )


def _phrase_matches(phrase: str, message: Msg) -> bool:
    return _collapse(phrase) in _collapse(message.haystack)


def _date_value(value: str) -> int | None:
    """The instant this `after:`/`before:` value names, or `None` for one the double cannot judge.

    **`None` already means "Gmail judges this, we do not", and a calendar-invalid date is
    that case** (R-RETR-033). The regex matched the *shape* and `datetime` then raised for an
    out-of-range month or day, so `after:2026/13/45 zephyr` - an ordinary typo, and a
    documented A.6a case, since MailWeave deliberately carries a date it cannot resolve and
    lets Gmail judge it - crashed every end-to-end harness that uses this double with an
    uncaught `ValueError` out of `LadderRunner.run`. MailWeave itself is correct there:
    `parsed.window is None`, the fragment is carried unchanged, and the ladder plans. The
    double refusing to *evaluate* the value is the same answer it already gives for a value
    whose shape it does not recognise, and it is what makes an end-to-end statement about
    such a query establishable by anybody.
    """
    # **Epoch seconds, because that is the form MailWeave itself writes** (2026-09-15).
    # Gmail accepts `after:` as `YYYY/MM/DD` *or* as epoch seconds, and A.6a rule 4 has the
    # server emit the second everywhere - including D.5 step (c)'s recency probe
    # (`semantic.pool._recency_query`). A double that returned `None` here judged that clause
    # unjudgeable and therefore **matched every message with it**, so no test in this
    # repository could observe the pool's own window excluding anything: every integration
    # statement about the recency probe was made against a probe that selected the whole
    # mailbox. Found when an independent review had to monkeypatch the product's clause
    # renderer to reproduce a defect (A16, finding 1). Ten digits is `2001-09-09` to
    # `2286-11-20`, which is every instant this project's fixtures use.
    if re.match(r"\A\d{9,11}\Z", value):
        return int(value) * 1000
    match = re.match(r"\A(\d{4})/(\d{1,2})/(\d{1,2})\Z", value)
    if match is None:
        return None
    year, month, day = (int(part) for part in match.groups())
    try:
        return epoch_ms(year, month, day, hour=0)
    except ValueError:
        return None


def _age_ms(value: str, now_ms: int) -> int | None:
    match = re.match(r"\A(\d+)([dmy])\Z", value.casefold())
    if match is None:
        return None
    days = int(match.group(1)) * {"d": 1, "m": 30, "y": 365}[match.group(2)]
    return now_ms - days * 86_400_000


def _participant_matches(field_value: tuple[str, ...] | str, wanted: str) -> bool:
    """`from:`/`to:`/`cc:` matching: the whole address, its local part, or a display word.

    **Deliberately stricter than Gmail, in the one direction that is safe.** A double that
    matched a *substring* would say `from:ops@team.example` matches `bulkops@team.example`,
    which Gmail does not - and a permissive double makes a rung look successful for a reason
    the real API would not supply, which is a test passing for the wrong reason (AL Sec 7.2).
    Strictness can only make a rung look *less* successful than it is, so the residue is a
    test that fails rather than one that lies.
    """
    values = (field_value,) if isinstance(field_value, str) else field_value
    needle = wanted.casefold().strip('"')
    for raw in values:
        value = raw.casefold().strip()
        address = value.rsplit("<", 1)[-1].strip(">").strip()
        display = value.rsplit("<", 1)[0].strip().strip('"') if "<" in value else ""
        local = address.split("@", 1)[0]
        if needle in {address, local} or (display and needle == display):
            return True
        if display and needle in re.findall(r"[\w'-]+", display):
            return True
    return False


def _operator_matches(name: str, value: str, message: Msg, *, now_ms: int) -> bool:
    if name not in IMPLEMENTED_OPERATORS:
        raise UnimplementedOperator(
            f"the ladder sent operator {name!r}, which this mailbox does not evaluate. "
            "Ignoring it would widen the query and make the rung look successful"
        )
    if name == "from":
        return _participant_matches(message.sender, value)
    if name == "to":
        return _participant_matches(message.to, value)
    if name == "cc":
        return _participant_matches(message.cc, value)
    if name == "subject":
        return _collapse(value.strip('"')) in _collapse(message.subject)
    if name == "rfc822msgid":
        header = message.message_id_header
        return header is not None and header.casefold() == value.casefold()
    if name == "after":
        boundary = _date_value(value)
        return boundary is None or message.internal_date_ms >= boundary
    if name == "before":
        boundary = _date_value(value)
        return boundary is None or message.internal_date_ms < boundary
    if name == "newer_than":
        boundary = _age_ms(value, now_ms)
        return boundary is None or message.internal_date_ms >= boundary
    if name == "older_than":
        boundary = _age_ms(value, now_ms)
        return boundary is None or message.internal_date_ms < boundary
    if name in {"label", "in", "is"}:
        wanted = value.casefold()
        if wanted == "anywhere":
            return True
        return wanted.upper() in {label.upper() for label in message.labels}
    if name == "category":
        return f"CATEGORY_{value}".upper() in {label.upper() for label in message.labels}
    return message.has_attachment if value.casefold() == "attachment" else False


def _token_matches(token: str, message: Msg, *, now_ms: int) -> bool:
    negated = token.startswith("-") and len(token) > 1
    body = token[1:] if negated else token
    if body.startswith("{") or body.endswith("}"):
        # Gmail's `{a b}` is OR. The group may arrive as several whitespace-split tokens;
        # the caller rejoins them before calling here.
        inner = body.strip("{}")
        result = any(_token_matches(part, message, now_ms=now_ms) for part in _split(inner) if part)
        return (not result) if negated else result
    head, separator, tail = body.partition(":")
    # `name:value` is an operator only when `name` is unquoted, which is what Gmail's own
    # documentation means by a quoted phrase: the quotes make everything inside them
    # content, colons included. This double had the same defect the parser did, from its own
    # independent code (R-RETR-018) - `"Re: quarterly plan"` reached `_operator_matches` as
    # an operator called `"re` and raised `UnimplementedOperator`. Written from the
    # documentation, not from the parser: nothing here imports `mailweave.query`.
    if separator and head and not head.startswith('"'):
        result = _operator_matches(head.casefold(), tail, message, now_ms=now_ms)
    elif body.startswith('"') and body.endswith('"') and len(body) > 1:
        result = _phrase_matches(body.strip('"'), message)
    else:
        result = _term_matches(body, message)
    return (not result) if negated else result


def _regroup(tokens: list[str]) -> list[str]:
    """Rejoin `{...}` groups that whitespace-splitting broke apart."""
    grouped: list[str] = []
    buffer: list[str] = []
    for token in tokens:
        if buffer:
            buffer.append(token)
            if token.endswith("}"):
                grouped.append(" ".join(buffer))
                buffer = []
            continue
        if token.startswith("{") and not token.endswith("}"):
            buffer = [token]
            continue
        grouped.append(token)
    if buffer:
        grouped.append(" ".join(buffer))
    return grouped


def matches(query: str, message: Msg, *, now_ms: int) -> bool:
    """Gmail's message-scoped conjunction (RO F2): every token must match this one message.

    `OR` between two tokens is honoured, because the ladder never emits it but a fidelity
    case may. Everything else is an AND, which is what the filtering guide documents.
    """
    tokens = _regroup(_split(query))
    if not tokens:
        return True
    index = 0
    result = True
    while index < len(tokens):
        token = tokens[index]
        if token.upper() in {"OR", "AND", "|"}:
            index += 1
            continue
        current = _token_matches(token, message, now_ms=now_ms)
        joins_previous = index > 0 and tokens[index - 1].upper() in {"OR", "|"}
        result = (result or current) if joins_previous else (result and current)
        index += 1
    return result


@dataclass
class SyntheticMailbox:
    """Answers `messages.list`, `messages.get`, `threads.get` and `history.list`."""

    messages: tuple[Msg, ...]
    now_ms: int = field(default_factory=lambda: epoch_ms(2026, 9, 3))
    #: PF-2's open question, as a switch: does `format=metadata` return `internalDate`?
    metadata_returns_internal_date: bool = True
    #: PF-2's **other** open question, and it is a different one: the Format enum's own text
    #: says METADATA returns "only email message ID, labels, and email headers" and does not
    #: mention `snippet`. With no snippet and no fetched body, a row is one this response
    #: holds no text for at all - which is the branch the participant index must declare as
    #: unscanned rather than report as mentioning nobody.
    metadata_returns_snippet: bool = True
    #: PF-2's third branch, and the one `Linkage.HEADERS_UNOBSERVED` exists for: a thread row
    #: that carries `internalDate` and **no `payload`**, so this response has seen none of
    #: that message's headers. Distinct from `metadata_returns_internal_date=False`, which
    #: removes the chronological order as well and makes the whole thread unmappable; here
    #: the thread maps and one row's reply headers were simply never observed.
    metadata_returns_headers: bool = True
    #: **Gmail does not promise `threads.get` returns its `messages[]` in any order**, and
    #: this is where a test says so. `None` leaves the array in `internalDate` order, which
    #: is the shape every earlier round's fixtures had and is exactly why array-order
    #: dependence went unnoticed: with the two orders always equal, code that reads the
    #: array position and code that reads `internalDate` are indistinguishable. A callable
    #: here permutes the array the double returns and nothing else, which the responder
    #: asserts, so a reordering cannot smuggle in a changed thread.
    thread_array_order: Callable[[tuple[Msg, ...]], tuple[Msg, ...]] | None = None
    #: The mailbox's `historyId` watermark. Every mutation below bumps it, and every
    #: `threads.get` reports the watermark of the last change that touched that thread - which
    #: is what makes a handle's liveness probe (WS-06) testable at all: with one constant id
    #: for the whole mailbox, "has this thread changed since its own historyId" has no
    #: answer the double can give, and the probe would be asserted against a fixture that
    #: could not disagree with it.
    history_id: int = 99120034
    #: The watermark before any mutation. A thread nothing has touched reports **this**, not
    #: the mailbox's current watermark: a thread's `historyId` is the id of the last change
    #: that touched *it*, and a double that moved every thread's id whenever any thread
    #: changed would make a handle over an untouched thread look stale for someone else's
    #: mutation - which is the false-positive a per-thread floor exists to prevent.
    starting_history_id: int = 99120034
    #: `{thread id: the watermark of the last change that touched it}`. A thread absent from
    #: here has never been mutated and reports the mailbox's starting watermark.
    thread_history: dict[str, int] = field(default_factory=dict)
    #: `history[]` records, oldest first, exactly as `history.list` returns them.
    history_records: list[dict[str, Any]] = field(default_factory=list)
    #: Gmail 404s `history.list` when `startHistoryId` is older than its retention (RO F6).
    #: A switch rather than a simulated retention window: which ids Gmail has forgotten is
    #: not something a double can know, and the branch under test is "the probe could not
    #: tell", which this reaches directly.
    history_is_expired: bool = False
    #: Records per `history.list` page. `None` is one page for everything, which is what
    #: Gmail does for a small window; a number forces the continuation-token branch, which is
    #: the *other* way a liveness probe fails to be conclusive.
    history_page_size: int | None = None
    queries: list[tuple[str, bool]] = field(default_factory=list)
    calls: Counter[str] = field(default_factory=Counter)
    #: Every endpoint touched, **in order**. LEX-01 is a statement about which call comes
    #: first, which a Counter cannot answer.
    call_log: list[str] = field(default_factory=list)
    #: Ids `messages.list` returned, per executed `q` - the content witness this test
    #: harness can be, standing outside the process the way amendment A1 requires.
    returned_ids: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)

    # -- mutation, so a handle can be redeemed against a mailbox that moved ------------
    #
    # Every mutation does two things and they are separate on purpose: it changes the
    # mailbox, and it writes the `history[]` record Gmail would write. A double that changed
    # the mailbox without the record would make a liveness probe pass over a changed mailbox
    # - the exact failure PF-15 exists to detect - and a double that wrote the record without
    # changing the mailbox would make the digest recompute agree with a probe that fired.

    def _next_history_id(self, thread_id: str) -> int:
        self.history_id += 1
        self.thread_history[thread_id] = self.history_id
        return self.history_id

    def history_id_of(self, thread_id: str) -> str:
        """The watermark `threads.get` reports for one thread."""
        return str(self.thread_history.get(thread_id, self.starting_history_id))

    def _record(self, thread_id: str, kind: str, message: Msg) -> None:
        self.history_records.append(
            {
                "id": str(self._next_history_id(thread_id)),
                kind: [{"message": {"id": message.id, "threadId": message.thread_id}}],
            }
        )

    def add_message(self, message: Msg) -> None:
        """A message arrives in a thread: `messagesAdded`."""
        self.messages = (*self.messages, message)
        self._record(message.thread_id, "messagesAdded", message)

    def delete_message(self, message_id: str) -> None:
        """A message leaves: `messagesDeleted`."""
        message = self.by_id(message_id)
        self.messages = tuple(m for m in self.messages if m.id != message_id)
        self._record(message.thread_id, "messagesDeleted", message)

    def relabel_message(
        self, message_id: str, *, add: tuple[str, ...] = (), remove: tuple[str, ...] = ()
    ) -> None:
        """Labels move on a message: `labelsAdded` / `labelsRemoved`.

        A label change touches a thread without changing which messages are in it, which is
        why a handle's liveness probe asks about all four `historyTypes`: a map that reports
        provenance (OD-5) is a map a relabel invalidates.
        """
        message = self.by_id(message_id)
        labels = tuple(label for label in message.labels if label not in remove) + add
        moved = replace(message, labels=labels)
        self.messages = tuple(moved if m.id == message_id else m for m in self.messages)
        if add:
            self._record(message.thread_id, "labelsAdded", moved)
        if remove:
            self._record(message.thread_id, "labelsRemoved", moved)

    def by_id(self, message_id: str) -> Msg:
        for message in self.messages:
            if message.id == message_id:
                return message
        raise KeyError(message_id)

    def thread(self, thread_id: str) -> tuple[Msg, ...]:
        return tuple(
            sorted(
                (m for m in self.messages if m.thread_id == thread_id),
                key=lambda m: (m.internal_date_ms, m.id),
            )
        )

    def search(self, query: str, *, include_spam_trash: bool) -> tuple[Msg, ...]:
        hidden = {"SPAM", "TRASH"}
        return tuple(
            message
            for message in self.messages
            if (include_spam_trash or not (hidden & {label.upper() for label in message.labels}))
            and matches(query, message, now_ms=self.now_ms)
        )

    # -- the wire ---------------------------------------------------------------------

    def _list(self, params: httpx.QueryParams) -> dict[str, Any]:
        query = params.get("q") or ""
        include = params.get("includeSpamTrash") == "true"
        self.queries.append((query, include))
        found = self.search(query, include_spam_trash=include)
        page_size = int(params.get("maxResults") or 100)
        page = found[:page_size]
        self.returned_ids.append((query, tuple(m.id for m in page)))
        body: dict[str, Any] = {
            "messages": [{"id": m.id, "threadId": m.thread_id} for m in page],
            "resultSizeEstimate": len(found),
        }
        if len(found) > page_size:
            body["nextPageToken"] = "synthetic-page-2"
        return body

    def _message_row(self, message: Msg, *, metadata: bool) -> dict[str, Any]:
        headers = [
            {"name": "From", "value": message.sender},
            {"name": "Subject", "value": message.subject},
            {"name": "Date", "value": "Thu, 03 Sep 2026 12:00:00 +0000"},
        ]
        # Every header below is emitted only when the message carries it. A double that
        # always emitted `In-Reply-To` - empty for a root - would make "the header is
        # absent" unreachable, and that is the state AD D.6's orphan rule is about.
        if message.message_id_header is not None:
            headers.append({"name": "Message-ID", "value": message.message_id_header})
        if message.in_reply_to is not None:
            headers.append({"name": "In-Reply-To", "value": message.in_reply_to})
        if message.references is not None:
            headers.append({"name": "References", "value": message.references})
        if message.reply_to is not None:
            headers.append({"name": "Reply-To", "value": message.reply_to})
        if message.authentication_results is not None:
            headers.append(
                {"name": "Authentication-Results", "value": message.authentication_results}
            )
        if message.cc:
            headers.append({"name": "Cc", "value": ", ".join(message.cc)})
        if message.to:
            headers.append({"name": "To", "value": ", ".join(message.to)})
        row: dict[str, Any] = {
            "id": message.id,
            "threadId": message.thread_id,
            "labelIds": list(message.labels),
            "historyId": self.history_id_of(message.thread_id),
        }
        if metadata and not self.metadata_returns_internal_date:
            return row
        row["internalDate"] = str(message.internal_date_ms)
        if not metadata or self.metadata_returns_snippet:
            row["snippet"] = message.body[:60]
        if metadata and not self.metadata_returns_headers:
            return row
        raw_body = message.body.encode(message.body_encoding, errors="replace")
        text_body: dict[str, Any] = (
            {"size": len(raw_body)}
            if metadata
            else {
                "size": len(raw_body),
                "data": base64.urlsafe_b64encode(raw_body).decode("ascii").rstrip("="),
            }
        )
        part_headers = (
            [
                {
                    "name": "Content-Type",
                    "value": f'text/plain; charset="{message.declared_charset}"',
                }
            ]
            if message.declared_charset is not None
            else []
        )
        if message.html_alternative is not None and not message.has_attachment:
            # The shape most real mail arrives in (round 27, R-MCP-023).
            html_raw = message.html_alternative.encode(message.body_encoding, errors="replace")
            html_body: dict[str, Any] = (
                {"size": len(html_raw)}
                if metadata
                else {
                    "size": len(html_raw),
                    "data": base64.urlsafe_b64encode(html_raw).decode("ascii").rstrip("="),
                }
            )
            row["payload"] = {
                "partId": "",
                "mimeType": "multipart/alternative",
                "headers": headers,
                "body": {"size": 0},
                "parts": [
                    {
                        "partId": "0",
                        "mimeType": "text/plain",
                        "filename": "",
                        "headers": part_headers,
                        "body": text_body,
                    },
                    {
                        "partId": "1",
                        "mimeType": "text/html",
                        "filename": "",
                        "headers": [
                            {
                                "name": "Content-Type",
                                "value": (
                                    f'text/html; charset="{message.declared_charset}"'
                                    if message.declared_charset is not None
                                    else "text/html"
                                ),
                            }
                        ],
                        "body": html_body,
                    },
                ],
            }
            return row
        if not message.has_attachment:
            row["payload"] = {
                "partId": "",
                "mimeType": "text/plain",
                "headers": [*headers, *part_headers],
                "body": text_body,
            }
            return row
        # **A message with an attachment is a multipart tree, because that is the only shape
        # one can arrive in.** `Msg.has_attachment` used to change only what `has:attachment`
        # matched, so the `payload.parts` path AD A.5/ADV-207 serves attachment metadata from
        # was unreachable from this double at all - a fixture flag that named a fact the wire
        # never carried. The filename carries a zero-width joiner and a right-to-left
        # override so the stripping `content.mime` performs is visible on a real response
        # rather than only in that module's own unit tests.
        row["payload"] = {
            "partId": "",
            "mimeType": "multipart/mixed",
            "headers": headers,
            "body": {"size": 0},
            "parts": [
                {
                    "partId": "0",
                    "mimeType": "text/plain",
                    "filename": "",
                    "headers": [{"name": "Content-Type", "value": "text/plain"}],
                    "body": text_body,
                },
                {
                    "partId": "1",
                    "mimeType": "application/pdf",
                    "filename": ATTACHMENT_FILENAME,
                    "headers": [
                        {
                            "name": "Content-Disposition",
                            "value": f'attachment; filename="{ATTACHMENT_FILENAME}"',
                        }
                    ],
                    "body": {"size": ATTACHMENT_SIZE, "attachmentId": f"att-{message.id}"},
                },
            ],
        }
        return row

    def _history(self, params: httpx.QueryParams) -> httpx.Response:
        """`history.list`, evaluated the way the reference documents it.

        Three behaviours the probe under test depends on, and each is written from the API
        docs rather than from the client:

          * records **after** `startHistoryId` are returned, and a `startHistoryId` Gmail no
            longer holds is a **404** ([VERIFIED] RO F6), not an empty page;
          * `historyTypes` is a repeated key and it **filters**. A double that ignored it
            would return deletions to a client that asked only for additions, and the
            liveness probe's four-type request would be untested - it would pass with one
            type on the wire;
          * a page carries `nextPageToken` when more records remain, which is the branch a
            probe that stops early has to declare rather than read as "nothing changed".
        """
        if self.history_is_expired:
            return json_response(404, {"error": {"code": 404, "message": "not found"}})
        start = int(params.get("startHistoryId") or 0)
        wanted = set(params.get_list("historyTypes")) or set(_HISTORY_TYPE_KEYS)
        keys = {_HISTORY_TYPE_KEYS[name] for name in wanted if name in _HISTORY_TYPE_KEYS}
        unknown = wanted - set(_HISTORY_TYPE_KEYS)
        if unknown:
            raise UnimplementedOperator(f"history.list was asked for {sorted(unknown)}")
        selected = [
            {"id": record["id"], **{k: v for k, v in record.items() if k in keys}}
            for record in self.history_records
            if int(record["id"]) > start and keys & set(record)
        ]
        token = params.get("pageToken")
        offset = int(token.removeprefix("history-page-")) if token else 0
        size = self.history_page_size or max(len(selected), 1)
        page = selected[offset : offset + size]
        body: dict[str, Any] = {"historyId": str(self.history_id)}
        if page:
            body["history"] = page
        if offset + size < len(selected):
            body["nextPageToken"] = f"history-page-{offset + size}"
        return json_response(200, body)

    def respond(self, key: str, request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if key == "messages.list":
            return json_response(200, self._list(params))
        if key == "messages.get":
            message = self.by_id(request.url.path.rsplit("/", 1)[-1])
            metadata = params.get("format") == "metadata"
            return json_response(200, self._message_row(message, metadata=metadata))
        if key == "threads.get":
            thread_id = request.url.path.rsplit("/", 1)[-1]
            rows = self.thread(thread_id)
            if self.thread_array_order is not None:
                reordered = self.thread_array_order(rows)
                assert sorted(m.id for m in reordered) == sorted(m.id for m in rows), (
                    "a thread array reordering may permute the rows and nothing else"
                )
                rows = reordered
            metadata = params.get("format") != "full"
            return json_response(
                200,
                {
                    "id": thread_id,
                    "historyId": self.history_id_of(thread_id),
                    "messages": [self._message_row(m, metadata=metadata) for m in rows],
                },
            )
        if key == "history.list":
            return self._history(params)
        if key == "profile":
            return json_response(
                200,
                {
                    "emailAddress": "owner@mailbox.example",
                    "messagesTotal": len(self.messages),
                    "threadsTotal": len({m.thread_id for m in self.messages}),
                    "historyId": str(self.history_id),
                },
            )
        raise AssertionError(f"the ladder reached an endpoint this double does not serve: {key}")

    def handler(self, request: httpx.Request) -> httpx.Response:
        key = FakeGmail.key_for(request.url.path)
        self.calls[key] += 1
        self.call_log.append(key)
        return self.respond(key, request)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def as_json(self) -> str:
        """Only used by tests that assert the fixture carries no real mail text."""
        return json.dumps([m.__dict__ for m in self.messages], default=str)
