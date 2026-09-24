"""LR executed: the price, the closed re-check, and what a surfaced message may claim.

Four properties, and the fourth is the one the rung exists for.

  * **`2 + 20n`, with `n <= max_recency_fetch`.** A.7's former flat "2 u" was wrong by up to
    two orders of magnitude; candidates past the bound are `withheld` records naming the
    cap, never a silent truncation.
  * **The re-check is closed.** `from`/`to`/`cc`, `after`/`before`, `has:attachment` and
    `label:` are evaluated exactly; free text, `subject:` term semantics, stemming, phrase
    semantics and boolean grouping are not evaluated at all. Reimplementing Gmail's query
    semantics is the cost T-RO3 names and E.4 cites to reject persistent indexes.
  * **A re-baseline is declared.** Gmail 404s a `historyId` older than its retention; the
    response says so and the watermark is re-based, never silently.
  * **A surfaced message is `role: context` with D.9's verbatim reason, and never a `q`
    match.** Attributing an LR row to the user's query would be this server asserting a
    Gmail match it never observed (R-03, T-RC3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mailweave.envelope.reasons import ReasonKind, RecencyContext, RungId
from mailweave.envelope.vocab import (
    BudgetCapName,
    Depth,
    NotTriedWhy,
    Outcome,
    RecheckedOperator,
    Role,
    ToolName,
    WithheldCap,
)
from mailweave.freshness.recheck import recheck
from mailweave.freshness.watermark import WatermarkFile
from mailweave.gmail import BackoffPolicy, CallMeter, GmailClient, StaticToken
from mailweave.gmail.models import Message
from mailweave.handles.cache import ThreadMapCache
from mailweave.handles.keys import HandleKey
from mailweave.net.egress import build_client
from mailweave.query.analysis import analyse
from mailweave.surface.arguments import parse_search
from mailweave.surface.partition import rendered_of
from mailweave.surface.server import call
from mailweave.surface.service import MailweaveService
from mailweave.trace.emit import trace_of
from tests.fixtures.mailbox import Msg, SyntheticMailbox, epoch_ms

TOKEN = "ya29.SECRET-ACCESS-TOKEN-NEVER-IN-AN-LR-FIXTURE"
ACCOUNT = "sha256:0f1e2d3c4b5a69788796a5b4c3d2e1f0"
NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def base_mailbox() -> SyntheticMailbox:
    return SyntheticMailbox(
        messages=(
            Msg(
                id="b-1",
                thread_id="t-base",
                sender="ana@team.example",
                subject="Cutover",
                body="The cutover is on Tuesday.",
                internal_date_ms=epoch_ms(2026, 8, 1),
                to=("bo@team.example",),
            ),
        ),
        now_ms=epoch_ms(2026, 9, 3),
    )


def make_service(box: SyntheticMailbox, tmp_path: Path) -> MailweaveService:
    def open_client() -> GmailClient:
        return GmailClient(
            token=StaticToken(TOKEN),
            http=build_client(inner=box.transport()),
            meter=CallMeter(),
            policy=BackoffPolicy(),
            sleeper=lambda _s: None,
            jitterer=lambda: 0.5,
        )

    return MailweaveService(
        open_client=open_client,
        account_hash=ACCOUNT,
        handle_key=HandleKey(material=b"k" * 32, epoch=0),
        cache=ThreadMapCache(),
        now=lambda: datetime.now(UTC),
        watermark_path=tmp_path / "state" / "watermark.json",
    )


# --- the watermark lifecycle ------------------------------------------------------------


def test_the_first_query_has_no_watermark_and_writes_one_for_the_next(tmp_path: Path) -> None:
    """A fresh install converges instead of never running LR at all.

    With in-process-only state the first query of a process has no watermark and later ones
    have one only minutes old, so LR would see almost nothing. D.9 persists it; this is the
    property that makes the persistence do its job.
    """
    box = base_mailbox()
    service = make_service(box, tmp_path)
    first = service.search(parse_search({"query": "cutover"}))
    entries = {entry.rung: entry for entry in first.retrieval_report.not_tried}
    assert entries[RungId.LR.value].why is NotTriedWhy.NOT_APPLICABLE
    stored = WatermarkFile(tmp_path / "state" / "watermark.json").load()
    assert stored is not None
    assert stored.history_id == str(box.history_id)

    second = service.search(parse_search({"query": "cutover"}))
    assert RungId.LR in second.retrieval_report.rungs


def test_the_watermark_file_holds_four_fields_and_no_mail_content(tmp_path: Path) -> None:
    """D.9's exact payload: `{schema, account_hash, history_id, observed_at}` and nothing else."""
    import json

    service = make_service(base_mailbox(), tmp_path)
    service.search(parse_search({"query": "cutover"}))
    payload = json.loads((tmp_path / "state" / "watermark.json").read_text())
    assert set(payload) == {"schema", "account_hash", "history_id", "observed_at"}
    assert "@" not in json.dumps(payload), "an address reached a non-content synchronisation stamp"


# --- the rung ------------------------------------------------------------------------------


def test_a_message_that_arrived_after_the_walk_is_surfaced_as_context(tmp_path: Path) -> None:
    """The whole point of the rung, and the whole of what a surfaced row may claim."""
    box = base_mailbox()
    service = make_service(box, tmp_path)
    # **A free-text query, deliberately.** With `from:ana@team.example` in it, L1b's own
    # decomposition probe reaches the late arrival and the row is a real `q` match - which
    # is correct behaviour and proves nothing about LR. This query's only route is the word
    # "cutover", which the late message does not carry, so the only rung that can reach it
    # is the one under test. It is also D.9's commonest case: nothing in the closed subset
    # is checkable, so the row says `[none]` and the disclaimer carries the whole weight.
    service.search(parse_search({"query": "cutover"}))

    box.add_message(
        Msg(
            id="late-1",
            thread_id="t-late",
            sender="ana@team.example",
            # **Deliberately not a lexical match.** The rung exists for arrivals Gmail's `q`
            # index has not caught up with, and this double indexes instantly - so a message
            # the query's own words would match is a message L1 finds, and LR would be
            # proved by a row the lexical ladder produced. This one is from the address the
            # query named and carries none of its words, which is exactly the state D.9
            # describes: the closed re-check passes, the free text is not re-checked, and
            # the row says both.
            subject="Schedule",
            body="It slipped to Thursday.",
            internal_date_ms=epoch_ms(2026, 9, 3),
            to=("bo@team.example",),
        )
    )
    envelope = service.search(parse_search({"query": "cutover"}))

    surfaced = [row for source in envelope.sources for row in source.messages if row.id == "late-1"]
    assert surfaced, "the recency rung did not surface the late arrival"
    row = surfaced[0]
    assert row.role is Role.CONTEXT, "an LR row claimed to be a query match"
    assert isinstance(row.reason, RecencyContext)
    rendered = row.reason.render()
    assert "free-text terms NOT re-checked" in rendered
    assert "Gmail q did not match this message" in rendered
    assert "constraints re-checked locally: [none]" in rendered, (
        "a free-text query has nothing in the closed subset to re-check, and the row has to "
        "say so rather than imply a check it did not make"
    )


def test_a_late_arrival_that_contradicts_a_stated_constraint_is_withheld(tmp_path: Path) -> None:
    """It is not attributed to the query, and it is not dropped either (I-1)."""
    box = base_mailbox()
    service = make_service(box, tmp_path)
    service.search(parse_search({"query": "cutover from:ana@team.example"}))
    box.add_message(
        Msg(
            id="late-2",
            thread_id="t-wrong",
            sender="zoe@other.example",
            subject="Unrelated",
            body="Nothing to do with it.",
            internal_date_ms=epoch_ms(2026, 9, 3),
        )
    )
    envelope = service.search(parse_search({"query": "cutover from:ana@team.example"}))
    assert "late-2" not in {row.id for source in envelope.sources for row in source.messages}
    caps = {record.cap for record in envelope.withheld} | {
        group.cap for group in envelope.withheld_groups
    }
    assert WithheldCap.RECENCY_RECHECK_EXCLUDED in caps


def test_more_arrivals_than_the_fetch_bound_become_withheld_records(tmp_path: Path) -> None:
    """`n <= max_recency_fetch`, and the overflow is accounted rather than truncated."""
    box = base_mailbox()
    service = make_service(box, tmp_path)
    service.search(parse_search({"query": "cutover", "budget": {"max_recency_fetch": 1}}))
    for index in range(4):
        box.add_message(
            Msg(
                id=f"many-{index}",
                thread_id=f"t-many-{index}",
                sender="ana@team.example",
                subject="Schedule",
                body="more",
                internal_date_ms=epoch_ms(2026, 9, 3),
            )
        )
    envelope = service.search(
        parse_search({"query": "cutover", "budget": {"max_recency_fetch": 1}})
    )
    caps = {record.cap for record in envelope.withheld} | {
        group.cap for group in envelope.withheld_groups
    }
    assert WithheldCap.MAX_RECENCY_FETCH in caps


def test_an_expired_watermark_declares_a_rebaseline_rather_than_failing(tmp_path: Path) -> None:
    """[VERIFIED] RO F6: Gmail 404s a `historyId` older than its retention."""
    box = base_mailbox()
    service = make_service(box, tmp_path)
    service.search(parse_search({"query": "cutover"}))
    box.history_is_expired = True
    envelope = service.search(parse_search({"query": "cutover"}))
    assert RungId.LR in envelope.retrieval_report.rungs, (
        "a re-baseline is a run: the rung walked, and Gmail said the place was lost"
    )


# --- the closed subset ------------------------------------------------------------------


def _message(**overrides: object) -> Message:
    payload: dict[str, object] = {
        "id": "m-1",
        "threadId": "t-1",
        "internalDate": str(epoch_ms(2026, 8, 15)),
        "labelIds": ["INBOX"],
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "Ana <ana@team.example>"},
                {"name": "To", "value": "bo@team.example"},
                {"name": "Subject", "value": "Cutover"},
            ],
        },
    }
    payload.update(overrides)
    return Message.model_validate(payload)


def test_the_participant_recheck_is_address_equality_and_nothing_else() -> None:
    parsed = analyse("cutover from:ana@team.example", now=NOW)
    good = recheck(_message(), parsed)
    assert good.passed is True
    assert RecheckedOperator.PARTICIPANT in good.checked

    other = _message(
        payload={
            "mimeType": "text/plain",
            "headers": [{"name": "From", "value": "zoe@other.example"}],
        }
    )
    bad = recheck(other, parsed)
    assert bad.passed is False
    assert bad.failed_on is RecheckedOperator.PARTICIPANT


def test_the_date_recheck_compares_integers_not_strings() -> None:
    parsed = analyse("cutover after:2026/09/01", now=NOW)
    assert recheck(_message(), parsed).passed is False
    assert recheck(_message(internalDate=str(epoch_ms(2026, 9, 2))), parsed).passed is True


def test_free_text_is_never_re_checked_and_the_verdict_says_so() -> None:
    """The half of the sentence a paraphrase loses, asserted as a field rather than a string."""
    parsed = analyse("cutover rollout", now=NOW)
    verdict = recheck(_message(), parsed)
    assert verdict.passed is True
    assert verdict.checked == (), "a free-text query produced a re-checked operator"
    assert verdict.residual_free_text is True


def test_an_unobserved_label_set_cannot_contradict_anything() -> None:
    """Round 19's absence-versus-zero rule, one module out (R-RETR-039)."""
    parsed = analyse("cutover label:work", now=NOW)
    unobserved = _message(labelIds=None)
    verdict = recheck(unobserved, parsed, label_ids={"work": "Label_7"})
    assert verdict.passed is True
    assert RecheckedOperator.LABEL not in verdict.checked, (
        "the response would claim a label was re-checked against labels nobody observed"
    )


def test_a_label_the_process_could_not_resolve_is_not_checked() -> None:
    """A silently skipped operator would make a narrower check read as the full one."""
    parsed = analyse("cutover label:work", now=NOW)
    verdict = recheck(_message(), parsed, label_ids={})
    assert verdict.passed is True
    assert RecheckedOperator.LABEL not in verdict.checked


def test_the_reason_kind_is_its_own_and_not_a_gmail_query_match() -> None:
    reason = RecencyContext(history_id="99120034", rechecked=(RecheckedOperator.PARTICIPANT,))
    assert reason.kind is ReasonKind.RECENCY_CONTEXT
    assert reason.kind.value != ReasonKind.GMAIL_QUERY_MATCH.value


def test_a_watermark_from_another_identity_is_not_a_floor_for_this_one(tmp_path: Path) -> None:
    """Walking from another mailbox's place would 404 or, worse, succeed on an unrelated seq."""
    file = WatermarkFile(tmp_path / "watermark.json")
    file.observe_identity(identity="account-a", history_id="99120034")
    assert file.load_for_identity("account-a") is not None
    assert file.load_for_identity("account-b") is None


def test_the_stored_identity_is_a_digest_whatever_the_caller_hands_in(tmp_path: Path) -> None:
    """The file's one job beyond holding a historyId is to be content-free."""
    file = WatermarkFile(tmp_path / "watermark.json")
    stored = file.observe_identity(identity="nayan@example.test", history_id="99120034")
    assert "nayan" not in stored.account_hash
    assert len(stored.account_hash) == 64


def test_a_watermark_refuses_a_history_id_that_is_not_one(tmp_path: Path) -> None:
    from mailweave.freshness.watermark import WatermarkRefused

    file = WatermarkFile(tmp_path / "watermark.json")
    with pytest.raises(WatermarkRefused):
        file.observe_identity(identity="a", history_id="not-a-history-id")


# --- an exclusion is not a cap, and it stays that way through every surface ------------------


def _excluded_arrival(tmp_path: Path) -> tuple[MailweaveService, SyntheticMailbox]:
    """A served query with exactly one `recency_recheck_excluded` withholding and no cap fired.

    Two searches and a message added between them, because that is the only way this state is
    reachable: the watermark has to exist and the arrival has to postdate it. The second
    search is the response under test; a third would see the advanced watermark and no
    arrival, which is how an earlier probe of this measured the wrong response.
    """
    box = base_mailbox()
    service = make_service(box, tmp_path)
    call(service, "mailweave_search", {"query": "cutover from:ana@team.example"})
    box.add_message(
        Msg(
            id="late-2",
            thread_id="t-wrong",
            sender="zoe@other.example",
            subject="Unrelated",
            body="Nothing to do with it.",
            internal_date_ms=epoch_ms(2026, 9, 3),
        )
    )
    return service, box


def test_an_exclusion_cannot_be_spelled_as_a_budget_cap_at_all() -> None:
    """The structural half, and it is the half that keeps holding without a fixture.

    `budget_caps_hit` is typed `BudgetCapName` and `RECENCY_RECHECK_EXCLUDED` is a
    `WithheldCap` that has no `BudgetCapName` twin - so a producer cannot put it there even
    by mistake, and no mapping between the two vocabularies can quietly acquire one. D.9's
    own words are that **no cap fired**: nothing was bounded, the fetch bound did not stop
    this message, and reporting it under `max_recency_fetch` would say the fetch bound did.
    """
    assert WithheldCap.RECENCY_RECHECK_EXCLUDED.value not in {name.value for name in BudgetCapName}
    # And the one cap it would most plausibly be confused with does exist on both sides,
    # so the absence above is a distinction rather than an oversight in the enum.
    assert WithheldCap.MAX_RECENCY_FETCH.value in {name.value for name in BudgetCapName}


def test_an_excluded_arrival_leaves_the_outcome_answered_and_names_no_cap(
    tmp_path: Path,
) -> None:
    """The behavioural half, over every field a reader would check for "was I cut off?".

    The combination is the point: **answered, partial, and no cap** - which is a different
    state from every budget exhaustion this server can report, and is the honest one. The
    query was answered; a message that arrived afterwards was fetched and found to contradict
    a constraint the query stated, so it is not attributed to the query and not disclosed; and
    nothing was bounded.
    """
    service, _box = _excluded_arrival(tmp_path)
    envelope = service.search(parse_search({"query": "cutover from:ana@team.example"}))
    report = envelope.retrieval_report
    assert report.outcome is Outcome.ANSWERED
    assert envelope.partial is True
    assert report.budget_caps_hit == (), report.budget_caps_hit
    assert envelope.truncated_by is None
    omission = envelope.omission
    assert omission is not None
    assert omission.withheld_by_cap == {WithheldCap.RECENCY_RECHECK_EXCLUDED.value: 1}, (
        omission.withheld_by_cap
    )
    # `bound` is the sentence a *ceiling* writes when it binds. No ceiling bound here, and a
    # non-null bound beside an empty `budget_caps_hit` would be the response naming a limit
    # it did not reach.
    assert omission.bound is None, omission.bound


def test_the_mirror_says_no_cap_fired_and_still_names_the_omission(tmp_path: Path) -> None:
    """MCP-03: the two halves of the result say the same thing, including this distinction.

    A reader of the text mirror must reach the same conclusion as a reader of the structured
    payload - the answer is partial, the omission has a name and a way back, and no budget
    ran out.
    """
    service, _box = _excluded_arrival(tmp_path)
    result = call(service, "mailweave_search", {"query": "cutover from:ana@team.example"})
    text = rendered_of(result).text
    assert "partial: yes" in text
    assert "caps hit: none" in text
    assert f"cap {WithheldCap.RECENCY_RECHECK_EXCLUDED.value}" in text
    assert "late-2" in text
    for cap in BudgetCapName:
        assert f"caps hit: {cap.value}" not in text, cap


def test_the_way_back_is_a_direct_read_and_it_executes(tmp_path: Path) -> None:
    """R-07, and the scope rule the recovery must not step around.

    The remedy for an excluded arrival is a **direct read of that message**, and that is the
    honest shape twice over: the server is not refusing to show the message, it is declining
    to attribute it to a query whose constraints it fails - so the call names the id rather
    than re-running the search at a wider setting, which would re-admit it *as a match*. It
    also stays inside the permissions this build has: `mailweave_get_messages` is a read on
    the same read-only scope, and it widens no budget key.
    """
    service, _box = _excluded_arrival(tmp_path)
    envelope = service.search(parse_search({"query": "cutover from:ana@team.example"}))
    record = next(
        entry for entry in envelope.withheld if entry.cap is WithheldCap.RECENCY_RECHECK_EXCLUDED
    )
    assert record.affordance.tool is ToolName.GET_MESSAGES, record.affordance.tool
    assert record.affordance.args == {"message_ids": [record.id], "view": Depth.SNIPPET.value}
    assert "budget" not in record.affordance.args
    followed = call(service, record.affordance.tool.value, dict(record.affordance.args))
    assert not followed.is_error
    payload = followed.structured_content
    assert isinstance(payload, dict)
    rows = [row for source in payload["sources"] for row in source["messages"]]
    assert record.id in {row["id"] for row in rows}, rows


def test_the_trace_carries_the_exclusion_and_an_empty_cap_list(tmp_path: Path) -> None:
    """OBS-01: the record kept for post-hoc reading makes the same distinction the wire does.

    A trace that flattened this into "something was withheld" would leave the one question a
    reader of it asks - was this run cut short? - answerable only by re-running the query.
    """
    service, _box = _excluded_arrival(tmp_path)
    envelope = service.search(parse_search({"query": "cutover from:ana@team.example"}))
    trace = trace_of(
        envelope,
        trace_id="tr-lr-1",
        tool=ToolName.SEARCH.value,
        query="cutover from:ana@team.example",
    )
    assert trace.retrieval_outcome.budget_caps_hit == ()
    assert [(entry.id, entry.cap) for entry in trace.disposition.withheld] == [
        ("late-2", WithheldCap.RECENCY_RECHECK_EXCLUDED.value)
    ]
