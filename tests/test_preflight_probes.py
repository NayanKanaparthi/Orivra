"""Every probe can fail (round 11, part 3).

"A probe that cannot fail is not a probe" is the work order's phrase, and the only way to
show it is to make each one fail. Each probe's analysis is a pure function over an
observation, so this file constructs the observation that falsifies it and the observation
that does not, and asserts both verdicts. That is the whole argument: the falsification
condition each probe declares in prose is exercised as code.

The rest of the file guards what the records may contain (OD-4) and that the freshness probe
cannot be read as a claim (OD-1).
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from mailweave.constants import is_one_line
from mailweave.gmail import PUBLISHED_PER_MINUTE_UNITS, PUBLISHED_QUOTA_UNITS, GmailEndpoint
from mailweave.gmail.faults import GmailRateLimited, GmailUnavailable
from mailweave_harness.preflight import (
    PLAN,
    REGISTRY,
    RecordWouldCarryContent,
    Verdict,
    assert_record_is_content_free,
    plan_text,
    spec,
    write_records,
)
from mailweave_harness.preflight import record as record_module
from mailweave_harness.preflight.probes import (
    freshness,
    headers,
    invisible,
    latency,
    quota,
    threads,
)
from mailweave_harness.preflight.record import digest, run_salt
from mailweave_harness.preflight.scope import MailboxScope
from mailweave_harness.preflight.spec import PROSE_FIELDS, ProbeSpec

# --- the declaration itself -------------------------------------------------------------


#: `PF-<n>` as it appears in a docstring or comment, and as the architecture's §F table
#: spells a registered row. Two spellings of one identifier, which is the point of comparing
#: them: a question named in the code and in no list is a question no run works from.
_NAMED_IN_SOURCE = re.compile(r"PF-\d+[a-z]?")
_REGISTERED = re.compile(r"\| \*\*(PF-\d+[a-z]?)\*\*")

_SOURCE_TREES = (Path("server/src"), Path("harness/src"))


def test_every_preflight_question_named_in_the_source_is_registered_in_the_architecture() -> None:
    """Round 12 part 4: four open shapes belonged in the preflight list rather than in prose.

    `PF-17` had been named in `auth/consent.py` since round 11 and `PF-20` was introduced by
    round 12's own part 1, and neither existed in AD §F's table - so a reader working from
    the list would not have run either, and a reader working from the code had no consequence
    written down for a failure. The page-token bound (G3) and the duplicate-history-id
    question (G7) were in the round-11 handoff's guessed-shape table and in no list at all.

    Asserted rather than described, because "make sure it is recorded" is exactly the kind of
    task that is done once and then drifts.
    """
    named: set[str] = set()
    for tree in _SOURCE_TREES:
        for path in sorted(tree.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            named.update(_NAMED_IN_SOURCE.findall(path.read_text(encoding="utf-8")))
    registered = set(
        _REGISTERED.findall(Path("docs/ARCHITECTURE_DECISION.md").read_text(encoding="utf-8"))
    )

    assert named, "no preflight question is named anywhere in the source at all"
    assert named <= registered, (
        f"a preflight question is named in the source and registered nowhere: "
        f"{sorted(named - registered)}. AD §F is the list a live run works from."
    )
    for question in ("PF-17", "PF-18", "PF-19", "PF-20"):
        assert question in registered, f"{question} is not in AD §F"


def test_the_four_still_open_shapes_each_have_a_registered_consequence() -> None:
    """A row with no "then what" is a note, not a preflight question (AD §F's own rule).

    The four are G1 (metadata `snippet`/`internalDate`, which PF-2 already carries and a
    shipped probe already drives), G3 (page-token length), G7 (duplicate history ids) and G8
    (the `scope` field).
    """
    table = Path("docs/ARCHITECTURE_DECISION.md").read_text(encoding="utf-8")
    rows = {
        row.split("**")[1]: row
        for row in table.splitlines()
        if row.startswith("| **PF-") and row.count("|") >= 3
    }
    for question, must_mention in (
        ("PF-2", "snippet"),
        ("PF-17", "scope"),
        ("PF-18", "nextPageToken"),
        ("PF-19", "threadId"),
    ):
        row = rows[question]
        assert must_mention in row, f"{question} does not state what it measures"
        consequence = row.rsplit("|", 2)[1].strip()
        assert len(consequence) > 80, f"{question} has no stated consequence of failure"


def test_a_probe_cannot_be_declared_without_a_falsification_condition() -> None:
    with pytest.raises(ValueError, match="falsified_when"):
        ProbeSpec(
            id="PF-x",
            title="t",
            measures="m",
            validates="v",
            falsified_when="",
            changes_if_it_fails="c",
        )


def test_a_probe_cannot_be_declared_without_a_consequence() -> None:
    with pytest.raises(ValueError, match="changes_if_it_fails"):
        ProbeSpec(
            id="PF-x",
            title="t",
            measures="m",
            validates="v",
            falsified_when="f",
            changes_if_it_fails="",
        )


def test_every_registered_probe_states_all_four_things_and_the_plan_prints_them() -> None:
    rendered = plan_text()
    for probe in REGISTRY:
        assert probe.falsified_when in rendered
        assert probe.changes_if_it_fails in rendered
        assert probe.validates in rendered
    assert PLAN.total_budget_units > 0


# --- PF-3, quota ---------------------------------------------------------------------------


def observation_for(**per_endpoint: int) -> quota.QuotaObservation:
    """Build a quota observation from `endpoint -> calls that fitted before the refusal`."""
    observed = quota.QuotaObservation()
    for name, calls in per_endpoint.items():
        observed.per_endpoint.append(
            quota.EndpointObservation(
                endpoint=GmailEndpoint(name),
                calls_completed=calls,
                elapsed_s=45.0,
                refused=True,
                refusal_status=429,
                refusal_reason="rateLimitExceeded",
            )
        )
    return observed


def calls_for(endpoint: GmailEndpoint, multiplier: float = 1.0) -> int:
    """How many calls fit in one minute if the published rate is right (times a factor)."""
    return int(PUBLISHED_PER_MINUTE_UNITS / (PUBLISHED_QUOTA_UNITS[endpoint] * multiplier))


def test_quota_passes_when_the_published_table_is_right() -> None:
    result = quota.analyse(
        observation_for(
            **{
                GmailEndpoint.HISTORY_LIST.value: calls_for(GmailEndpoint.HISTORY_LIST),
                GmailEndpoint.MESSAGES_LIST.value: calls_for(GmailEndpoint.MESSAGES_LIST),
                GmailEndpoint.MESSAGES_GET.value: calls_for(GmailEndpoint.MESSAGES_GET),
                GmailEndpoint.THREADS_GET.value: calls_for(GmailEndpoint.THREADS_GET),
            }
        )
    )
    assert result.verdict is Verdict.PASS
    assert result.findings["rank_order_holds"] is True


def test_quota_fails_on_the_four_times_tighter_reality_the_architecture_names() -> None:
    """AD A.5c's own consequence table is written against a '~4x tighter reality'."""
    result = quota.analyse(
        observation_for(
            **{
                GmailEndpoint.HISTORY_LIST.value: calls_for(GmailEndpoint.HISTORY_LIST, 4),
                GmailEndpoint.MESSAGES_LIST.value: calls_for(GmailEndpoint.MESSAGES_LIST, 4),
                GmailEndpoint.MESSAGES_GET.value: calls_for(GmailEndpoint.MESSAGES_GET, 4),
                GmailEndpoint.THREADS_GET.value: calls_for(GmailEndpoint.THREADS_GET, 4),
            }
        )
    )
    assert result.verdict is Verdict.FAIL
    assert set(result.findings["outside_agreement_factor"]) == {
        endpoint.value for endpoint in quota.PUBLISHED_RANK
    }


def test_quota_fails_when_the_rank_order_is_wrong_even_inside_the_agreement_band() -> None:
    """The rank-order clause is the falsifier that survives the inference's assumptions."""
    result = quota.analyse(
        observation_for(
            **{
                # history.list made to look *more* expensive than messages.list
                GmailEndpoint.HISTORY_LIST.value: calls_for(GmailEndpoint.HISTORY_LIST, 1.9),
                GmailEndpoint.MESSAGES_LIST.value: calls_for(GmailEndpoint.MESSAGES_LIST, 0.6),
            }
        )
    )
    assert result.verdict is Verdict.FAIL
    assert result.findings["rank_order_holds"] is False
    assert result.findings["outside_agreement_factor"] == []


def test_quota_is_inconclusive_rather_than_passing_when_nothing_was_refused() -> None:
    observed = quota.QuotaObservation()
    observed.per_endpoint.append(
        quota.EndpointObservation(
            endpoint=GmailEndpoint.MESSAGES_LIST, calls_completed=50, elapsed_s=5.0, refused=False
        )
    )
    result = quota.analyse(observed)
    assert result.verdict is Verdict.INCONCLUSIVE
    assert "not a pass" in " ".join(result.notes)


def test_the_measurement_loop_stops_at_the_refusal_and_records_its_reason() -> None:
    """The loop itself is tested with no network, which is why `make_call` is a parameter."""
    calls = {"n": 0}

    def make_call() -> None:
        calls["n"] += 1
        if calls["n"] > 7:
            raise GmailRateLimited(
                "limited",
                endpoint=GmailEndpoint.MESSAGES_LIST,
                status=403,
                reason="userRateLimitExceeded",
            )

    observed = quota.measure_endpoint(GmailEndpoint.MESSAGES_LIST, make_call, max_calls=1_000)
    assert observed.calls_completed == 7
    assert observed.refused is True
    assert observed.refusal_status == 403
    assert observed.refusal_reason == "userRateLimitExceeded"


def test_a_non_rate_limit_failure_is_not_reported_as_a_budget_observation() -> None:
    """An endpoint that died for another reason has measured nothing, and says so."""

    def make_call() -> None:
        raise GmailUnavailable("down", endpoint=GmailEndpoint.MESSAGES_LIST, status=503)

    observed = quota.measure_endpoint(GmailEndpoint.MESSAGES_LIST, make_call, max_calls=10)
    assert observed.refused is False
    assert quota.inferred_units(observed) is None


# --- PF-2, metadata headers -----------------------------------------------------------------


def header_observation(
    *, metadata: set[str], full: set[str], metadata_date: bool = True
) -> headers.HeaderObservation:
    observed = headers.HeaderObservation(requested_headers=("In-Reply-To", "References"))
    observed.metadata_headers_by_id["m1"] = {name.lower() for name in metadata}
    observed.full_headers_by_id["m1"] = {name.lower() for name in full}
    observed.metadata_has_snippet["m1"] = True
    observed.full_has_snippet["m1"] = True
    observed.metadata_has_internal_date["m1"] = metadata_date
    observed.full_has_internal_date["m1"] = True
    return observed


def test_metadata_headers_pass_when_the_requested_headers_come_back() -> None:
    result = headers.analyse(
        header_observation(
            metadata={"In-Reply-To", "References"}, full={"In-Reply-To", "References"}
        )
    )
    assert result.verdict is Verdict.PASS


def test_metadata_headers_fail_when_a_reply_link_is_dropped() -> None:
    result = headers.analyse(
        header_observation(metadata={"In-Reply-To"}, full={"In-Reply-To", "References"})
    )
    assert result.verdict is Verdict.FAIL
    assert result.findings["reply_linking_headers_dropped"] == ["references"]


def test_metadata_headers_fail_when_internal_date_is_missing_under_metadata() -> None:
    """The branch the client already refuses to paper over: no internalDate, no chronology."""
    result = headers.analyse(
        header_observation(
            metadata={"In-Reply-To", "References"},
            full={"In-Reply-To", "References"},
            metadata_date=False,
        )
    )
    assert result.verdict is Verdict.FAIL
    assert result.findings["messages_losing_internal_date_under_metadata"] == 1


def test_a_header_absent_from_both_arms_is_the_message_s_doing_not_the_api_s() -> None:
    """Without the format=full arm this case is indistinguishable from a real failure.

    That claim is unchanged and still holds: nothing is counted as dropped. What changed is
    the verdict this shape is allowed to reach. This test previously asserted PASS, and in
    doing so it encoded the defect live run 1 then exhibited - a sample that could not have
    exhibited the property under test reporting that the property held.
    """
    result = headers.analyse(header_observation(metadata=set(), full=set()))
    assert result.findings["headers_dropped_by_metadata"] == {}
    assert result.findings["reply_linking_headers_dropped"] == []
    assert result.findings["headers_absent_from_both_arms"] == {
        "in-reply-to": 1,
        "references": 1,
    }
    assert result.verdict is Verdict.INCONCLUSIVE


def test_a_one_message_thread_with_no_reply_headers_cannot_produce_a_reply_header_pass() -> None:
    """The focused regression for the run-1 defect, in the exact shape that produced it.

    Live PF-2 run 1 (2026-09-11) compared one message whose full arm carried neither
    `In-Reply-To` nor `References`, found nothing dropped, and reported PASS. The
    reply-linking question AD D.5's thread-map pricing rests on was never asked.
    """
    result = headers.analyse(header_observation(metadata=set(), full=set()))

    assert result.findings["reply_header_verdict"] == "inconclusive"
    assert result.findings["reply_header_bearing_messages_compared"] == 0
    assert result.verdict is not Verdict.PASS
    assert any("UNDER-EXERCISED" in note for note in result.notes)


def test_the_snippet_question_has_the_same_floor_one_branch_over() -> None:
    """Found while fixing the reply-header case. Leaving it would be the same bug renamed."""
    observed = header_observation(
        metadata={"In-Reply-To", "References"}, full={"In-Reply-To", "References"}
    )
    observed.full_has_snippet["m1"] = False
    observed.metadata_has_snippet["m1"] = False

    result = headers.analyse(observed)

    assert result.findings["reply_header_verdict"] == "pass"
    assert result.findings["snippet_verdict"] == "inconclusive"
    assert result.findings["snippet_bearing_messages_compared"] == 0
    assert result.verdict is Verdict.INCONCLUSIVE


def test_a_pass_needs_both_questions_exercised_and_both_holding() -> None:
    result = headers.analyse(
        header_observation(
            metadata={"In-Reply-To", "References"}, full={"In-Reply-To", "References"}
        )
    )
    assert result.findings["reply_header_verdict"] == "pass"
    assert result.findings["snippet_verdict"] == "pass"
    assert result.findings["reply_header_bearing_messages_compared"] == 1
    assert result.verdict is Verdict.PASS


def test_coverage_per_requested_header_is_recorded_so_a_gap_is_visible_without_a_rerun() -> None:
    """The number that would have made run 1's gap legible at a glance."""
    result = headers.analyse(header_observation(metadata=set(), full=set()))
    assert result.findings["messages_carrying_each_requested_header_in_the_full_arm"] == {
        "in-reply-to": 0,
        "references": 0,
    }


# --- PF-1 and the ceiling ---------------------------------------------------------------------


def thread_observation(
    pairs: dict[str, tuple[int, int]], *, incomplete: bool = False
) -> threads.ThreadObservation:
    observed = threads.ThreadObservation(
        scope=MailboxScope.WITHOUT_SPAM_AND_TRASH,
        listing_incomplete=incomplete,
        pages_fetched=3,
    )
    for name, (from_threads_get, from_listing) in pairs.items():
        observed.threads_get_rows[name] = from_threads_get
        observed.listing_rows[name] = from_listing
    return observed


def test_thread_completeness_passes_when_both_endpoints_agree() -> None:
    result = threads.analyse_completeness(thread_observation({"a": (40, 40), "b": (7, 7)}))
    assert result.verdict is Verdict.PASS


def test_thread_completeness_fails_on_issue_239_s_shape() -> None:
    """threads.get returning fewer rows than the listing arm attributed to that thread."""
    result = threads.analyse_completeness(thread_observation({"a": (100, 137)}))
    assert result.verdict is Verdict.FAIL
    assert result.findings["threads_where_threads_get_returned_fewer"]["a"] == {
        "threads_get": 100,
        "messages_list": 137,
    }


def test_the_listing_arm_stopping_early_cannot_produce_a_false_failure() -> None:
    result = threads.analyse_completeness(thread_observation({"a": (12, 9)}, incomplete=True))
    assert result.verdict is Verdict.PASS
    assert result.findings["threads_where_threads_get_returned_more"] == 1
    assert "cannot produce a false FAIL" in " ".join(result.notes)


def test_the_ceiling_probe_fails_when_threads_pile_up_at_one_size() -> None:
    result = threads.analyse_ceiling(
        thread_observation({"a": (100, 100), "b": (100, 100), "c": (100, 100), "d": (12, 12)})
    )
    assert result.verdict is Verdict.FAIL
    assert result.findings["largest_thread_observed"] == 100
    assert result.findings["threads_at_that_size"] == 3


def test_the_ceiling_probe_passes_on_an_ordinary_tail_and_says_what_that_is_worth() -> None:
    result = threads.analyse_ceiling(
        thread_observation({"a": (63, 63), "b": (40, 40), "c": (12, 12)})
    )
    assert result.verdict is Verdict.PASS
    assert "not a proof that none exists" in " ".join(result.notes)


# --- freshness ------------------------------------------------------------------------------


def test_freshness_reports_raw_numbers_and_no_claim() -> None:
    observed = freshness.FreshnessObservation(window_s=600.0, arrivals_observed=3)
    observed.lag_seconds_by_message = {"a": 12.0, "b": 41.5, "c": 300.0}
    result = freshness.analyse(observed)

    assert result.verdict is Verdict.OBSERVATION_ONLY
    assert result.findings["observed_lag_seconds_raw"] == [12.0, 41.5, 300.0]
    # OD-1: no percentile, no aggregate that could be quoted as a service level.
    forbidden = {"p50", "p90", "p95", "median", "mean", "service_level", "meets_od1", "sla"}
    assert set(result.findings) & forbidden == set()
    assert "pooling prohibited" in " ".join(result.notes)


def test_freshness_fails_when_a_history_observed_message_never_becomes_findable() -> None:
    """The convergence failure, which is the one thing this probe is allowed to conclude."""
    observed = freshness.FreshnessObservation(window_s=600.0, arrivals_observed=2)
    observed.lag_seconds_by_message = {"a": 9.0}
    observed.never_found = ["b"]
    result = freshness.analyse(observed)
    assert result.verdict is Verdict.FAIL
    assert result.findings["never_found_within_window"] == 1


def test_freshness_is_inconclusive_when_no_mail_arrived() -> None:
    result = freshness.analyse(freshness.FreshnessObservation(window_s=60.0))
    assert result.verdict is Verdict.INCONCLUSIVE


# --- the Cf strip -----------------------------------------------------------------------------


def test_the_cf_probe_fails_when_a_join_control_is_stripped_from_arabic_text() -> None:
    """The exact question round 10 left open, made to fail on the shape that would answer it."""
    salt = run_salt()
    # Spelled with escapes, never as literal characters: an invisible character in a
    # source file is invisible in a diff, which is the whole reason it is being measured.
    arabic_with_zwnj = "\u0645\u0631\u062d\u0628\u0627\u200c\u0645\u0631\u062d\u0628\u0627"
    stripped = arabic_with_zwnj.replace("\u200c", "")
    observed = invisible.InvisibleObservation(bodies_examined=1)
    observed.messages.append(
        invisible.observe_message(digest("m1", salt), arabic_with_zwnj, stripped)
    )

    result = invisible.analyse(observed)

    assert result.verdict is Verdict.FAIL
    assert result.findings["damaged_messages"][0]["scripts"] == ["ARABIC"]
    assert result.findings["damaged_messages"][0]["removed"] == ["U+200C"]


def test_the_cf_probe_passes_when_only_a_bidi_override_is_stripped_from_arabic_text() -> None:
    """An RLO in Arabic text is still an attack shape, not shaping. The probe separates them."""
    salt = run_salt()
    text = "\u0645\u0631\u062d\u0628\u0627\u202emalicious"
    observed = invisible.InvisibleObservation(bodies_examined=1)
    observed.messages.append(
        invisible.observe_message(digest("m1", salt), text, text.replace("\u202e", ""))
    )
    result = invisible.analyse(observed)
    assert result.verdict is Verdict.PASS
    assert result.findings["removals_by_code_point"] == {"U+202E": 1}


def test_the_cf_probe_is_inconclusive_when_the_sample_had_no_at_risk_script() -> None:
    """A mailbox with no Arabic mail cannot answer whether stripping damages Arabic mail."""
    salt = run_salt()
    text = "hello\u200bworld"
    observed = invisible.InvisibleObservation(bodies_examined=1)
    observed.messages.append(
        invisible.observe_message(digest("m1", salt), text, text.replace("\u200b", ""))
    )
    result = invisible.analyse(observed)
    assert result.verdict is Verdict.INCONCLUSIVE
    assert "never saw" in " ".join(result.notes)


def test_the_observation_retains_no_text_from_the_body_it_measured() -> None:
    salt = run_salt()
    text = "confidential: the acquisition closes on Friday\u200c"
    observed = invisible.observe_message(digest("m1", salt), text, text.replace("\u200c", ""))
    rendered = repr(observed)
    for word in ("confidential", "acquisition", "Friday"):
        assert word not in rendered


def test_every_load_bearing_code_point_really_is_a_format_character() -> None:
    """The list is a claim about Unicode; the runtime is asked rather than trusted."""
    import unicodedata

    for character in invisible.LOAD_BEARING:
        assert unicodedata.category(character) == "Cf", f"U+{ord(character):04X}"


# --- the record ---------------------------------------------------------------------------------


def test_a_record_carrying_a_body_is_refused_before_it_is_written(tmp_path: Path) -> None:
    with pytest.raises(RecordWouldCarryContent):
        assert_record_is_content_free({"findings": {"sample": "line one\nline two"}})
    with pytest.raises(RecordWouldCarryContent):
        assert_record_is_content_free({"findings": {"sample": "x" * 400}})


def test_the_probes_own_prose_is_allowed_through(tmp_path: Path) -> None:
    """The exemption is by key name and is deliberately narrow: our sentences, not theirs."""
    assert_record_is_content_free({"measures": "x" * 400, "validates": "y" * 400})


# --- R-SEC-042: the exemption is a *path*, not a name that leaks downwards --------------------

#: Deliberately not mail. It is multi-line and over `MAX_RECORD_STRING`, which is all the
#: check looks at, and this project puts no realistic personal mail text in any fixture.
SHAPED_LIKE_A_BODY = "a synthetic first line\na synthetic second line\n" + "filler " * 40


def nestings(text: str) -> list[tuple[str, dict[str, object]]]:
    """One string, buried under an exempt top-level key in every way a record can bury it."""
    return [
        ("a dict directly under it", {"raw_snippet": text}),
        ("a dict two levels down", {"a": {"b": text}}),
        ("a dict inside a list", [{"raw_snippet": text}]),  # type: ignore[list-item]
        ("a list of dicts of lists", [{"a": [text]}]),  # type: ignore[list-item]
        ("a key rather than a value", {text: 1}),
    ]


@pytest.mark.parametrize("exempt", sorted(PROSE_FIELDS))
def test_no_exempt_key_carries_its_exemption_down_into_a_nested_shape(exempt: str) -> None:
    """R-SEC-042, over every exempt key rather than the one the reviewer happened to use.

    The finding was reproduced with `{"notes": {"raw_snippet": <a mail body>}}`. Round 11's
    walk set `key` at the first dict level and passed it down unchanged, so the exemption
    reached every string underneath, at any depth - and the identical text one key to the
    left was correctly refused. Six of these seven keys were never tested at all; `notes` was
    tested flat, which is the shape all six shipped probes emit and therefore the only shape
    anyone had looked at.
    """
    for shape, nested in nestings(SHAPED_LIKE_A_BODY):
        with pytest.raises(RecordWouldCarryContent) as refusal:
            assert_record_is_content_free({exempt: nested})
        assert SHAPED_LIKE_A_BODY[:20] not in str(refusal.value), (
            f"the refusal for '{shape}' quoted the text it was refusing"
        )


@pytest.mark.parametrize("exempt", sorted(PROSE_FIELDS))
def test_an_exempt_name_used_as_a_nested_key_is_not_exempt(exempt: str) -> None:
    """`findings.notes` is not `notes`. The exemption is one top-level key, not a name."""
    with pytest.raises(RecordWouldCarryContent):
        assert_record_is_content_free({"findings": {exempt: SHAPED_LIKE_A_BODY}})


# --- R-SEC-048: the exemption is the producer's shape, and the walk reads every container ---


@pytest.mark.parametrize("exempt", sorted(PROSE_FIELDS))
@pytest.mark.parametrize("burial", ["one extra list level", "five list levels", "a tuple"])
def test_a_prose_key_does_not_exempt_a_shape_the_producer_never_writes(
    exempt: str, burial: str
) -> None:
    """R-SEC-048, over every exempt key and every list burial the finding named.

    Round 12's exemption was "one prose key, then nothing but list indices", with no bound on
    how many - so `{"notes": [[<a body>]]}` passed, as did depth five, as did a tuple inside a
    list, for all seven keys. Driven to disk, `json.dumps` wrote the body out intact. The
    depth a key is exempt at is now the producer's own, so one level *more* than `as_record`
    writes is one level too many, at every key.
    """
    declared = PROSE_FIELDS[exempt]
    buried: object = SHAPED_LIKE_A_BODY
    if burial == "a tuple":
        buried = (SHAPED_LIKE_A_BODY,)
    else:
        for _ in range(1 if burial == "one extra list level" else 5):
            buried = [buried]
    for _ in range(declared):
        buried = [buried]

    with pytest.raises(RecordWouldCarryContent) as refusal:
        assert_record_is_content_free({exempt: buried})
    assert SHAPED_LIKE_A_BODY[:20] not in str(refusal.value)


@pytest.mark.parametrize(
    "exempt", sorted(name for name, depth in PROSE_FIELDS.items() if not depth)
)
def test_a_plain_string_prose_key_is_not_exempt_inside_a_list(exempt: str) -> None:
    """Five of the seven keys are written as a single sentence, so `title[0]` is not `title`.

    R-SEC noted this as the smaller half of the same finding: for those keys, *any* list
    nesting was already wider than the producer, and round 12's rule permitted it.
    """
    with pytest.raises(RecordWouldCarryContent):
        assert_record_is_content_free({exempt: [SHAPED_LIKE_A_BODY]})


def test_a_container_the_walk_cannot_read_is_refused_rather_than_stepped_over() -> None:
    """Sets, frozensets and non-dict mappings were never walked at all.

    Their contents were therefore unchecked, and the only thing between a body and the file
    was `json.dumps` raising - a crash, not a refusal, and one that says nothing about mail
    text. The walk now refuses what it cannot read, which is the same move as bounding by
    shape: it does not need a list of the containers a future record might use.
    """
    from collections import UserDict

    holder: UserDict[str, str] = UserDict()
    holder["k"] = SHAPED_LIKE_A_BODY

    for unreadable in (
        {"findings": {SHAPED_LIKE_A_BODY}},
        {"findings": frozenset({SHAPED_LIKE_A_BODY})},
        {"findings": holder},
        {"findings": SHAPED_LIKE_A_BODY.encode("utf-8")},
        {"findings": object()},
        {"notes": [{SHAPED_LIKE_A_BODY}]},
    ):
        with pytest.raises(RecordWouldCarryContent) as refusal:
            assert_record_is_content_free(unreadable)
        assert "cannot read" in str(refusal.value)
        assert SHAPED_LIKE_A_BODY[:20] not in str(refusal.value)

    with pytest.raises(RecordWouldCarryContent) as key_refusal:
        assert_record_is_content_free({("a", "tuple"): 1})
    assert "cannot read" in str(key_refusal.value)


def test_the_bound_is_taken_on_the_characters_and_not_on_the_values_own_word() -> None:
    """A `str` subclass may override `__len__` and `splitlines`; the file gets the characters.

    **This test used to pass for the wrong reason, and the round-13 reintroduction battery is
    what showed it.** Removing `record._plain` - the reduction that measures a value's actual
    characters - broke nothing, because the liar it planted returned `["short"]` from
    `splitlines`, and `is_one_line` compares `value.splitlines() == [value]`, so a *different*
    string came back and the value was refused as multi-line whatever `_plain` did. The
    defence being tested was never exercised.

    A liar that returns `[self]` reports itself as one line, understates its length, and is
    caught only by the reduction. That is now the case, and `str.__add__(value, "")` - the
    base implementation, which returns an exact `str` - is what the bound is taken on.
    """

    class Understating(str):
        def __len__(self) -> int:
            return 3

        def splitlines(self, keepends: bool = False) -> list[str]:
            return [self]

        def __str__(self) -> str:
            return "short"

    lying = Understating(SHAPED_LIKE_A_BODY)
    assert len(lying) == 3
    assert is_one_line(lying), "the liar must defeat the line check, or it tests nothing"

    with pytest.raises(RecordWouldCarryContent) as refusal:
        assert_record_is_content_free({"findings": lying})
    assert SHAPED_LIKE_A_BODY[:20] not in str(refusal.value)

    with pytest.raises(RecordWouldCarryContent) as key_refusal:
        assert_record_is_content_free({lying: 1})
    assert SHAPED_LIKE_A_BODY[:20] not in str(key_refusal.value)


def test_the_json_types_a_record_really_uses_still_pass() -> None:
    """The refusal must not close the door on an ordinary record."""
    assert_record_is_content_free(
        {
            "probe": "PF-1",
            "verdict": "pass",
            "quota_budget_units": 12,
            "ratio": 0.5,
            "exceeded": False,
            "absent": None,
            "findings": {"per_endpoint": {"messages.list": 3}, "codes": [1, 2, 3]},
            "notes": ["one of our sentences"],
        }
    )


def test_the_prose_that_is_actually_written_still_goes_through() -> None:
    """The exemption must survive the shapes a real record uses, or the check is unusable.

    `notes` and `pre_registered_rules` are lists of our own sentences, so the path is one
    prose key followed by list indices - which is exactly, and only, what stays exempt.
    """
    assert_record_is_content_free(
        {
            "title": "x" * 400,
            "measures": "y" * 400,
            "notes": ["a long sentence of ours " * 20, "another one " * 40],
            "pre_registered_rules": ["a rule stated before the run " * 20],
            "findings": {"count": 3, "slug": "rateLimitExceeded", "per_endpoint": {"a": 1}},
        }
    )


def test_a_key_is_checked_and_is_never_exempt() -> None:
    """Nothing checked keys before round 12, so a record could carry mail text as a name.

    A key is not our prose under any circumstances - `_OUR_PROSE` described *values* - so it
    is checked wherever it appears, including directly under a prose key.
    """
    for record in (
        {SHAPED_LIKE_A_BODY: 1},
        {"findings": {SHAPED_LIKE_A_BODY: 1}},
        {"notes": {SHAPED_LIKE_A_BODY: 1}},
        {"findings": [{"x" * 400: 1}]},
    ):
        with pytest.raises(RecordWouldCarryContent):
            assert_record_is_content_free(record)


def test_the_refusal_never_quotes_what_it_refused() -> None:
    """The check runs on a record about to be persisted; its error must not become the leak."""
    with pytest.raises(RecordWouldCarryContent) as key_refusal:
        assert_record_is_content_free({SHAPED_LIKE_A_BODY: 1})
    assert "withheld" in str(key_refusal.value)
    assert SHAPED_LIKE_A_BODY[:20] not in str(key_refusal.value)


def _list_depth(value: object) -> int | None:
    """How many list levels sit between `value` and a string, or `None` if it is neither."""
    depth = 0
    while isinstance(value, list | tuple):
        if not value:
            return None
        value = value[0]
        depth += 1
    return depth if isinstance(value, str) else None


def test_the_exempt_set_is_the_producers_own_list_and_still_matches_it() -> None:
    """One declaration, in the module that writes the record - not a copy in the checker.

    A copy would be R-ARCH-031's shape: the checker's set stops matching `as_record`'s keys
    the day a prose field is added, and the new field's text is then refused (or, worse, a
    removed one stays exempt).

    **Round 13 checks the shape as well as the name** (R-SEC-048). The exemption is now "this
    key, under exactly this many list levels", and a declared depth that does not match what
    `as_record` actually emits is the same drift one axis over: it would exempt a shape the
    producer does not write, which is precisely how a body in a nested list came to be exempt.
    The depth below is measured from the record rather than restated.
    """
    result = freshness.analyse(freshness.FreshnessObservation(window_s=60.0))
    record = result.as_record()
    assert set(record) >= set(PROSE_FIELDS), (
        f"a declared prose field is not in the record: {set(PROSE_FIELDS) - set(record)}"
    )
    for name, declared in PROSE_FIELDS.items():
        produced = _list_depth(record[name])
        assert produced == declared, (
            f"{name} is declared as prose under {declared} list level(s) and `as_record` "
            f"writes it under {produced}; the exemption and the producer have drifted"
        )


def test_the_checker_uses_the_producers_declaration_rather_than_its_own_copy() -> None:
    """R-SEC-053: the test above compares two things and neither of them was the checker.

    A divergent copy of `PROSE_FIELDS` *inside* `record.py`, widened by one key, was invisible
    to it - the de-duplication the test's docstring describes was never actually asserted. Two
    checks, because they fail on different mistakes: the object identity catches a copy built
    at import time, and the AST sweep catches a module-level rebinding that identity would miss
    if it happened to produce an equal mapping.
    """
    # `vars(...)` rather than an attribute read: the question is what object that module's
    # namespace binds, which is exactly what a divergent copy would change.
    assert vars(record_module)["PROSE_FIELDS"] is spec.PROSE_FIELDS, (
        "record.py holds its own PROSE_FIELDS rather than the producer's; a second copy is "
        "the copy that stops matching (R-ARCH-031, R-SEC-053)"
    )

    tree = ast.parse(Path(record_module.__file__ or "").read_text(encoding="utf-8"))
    rebindings = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign | ast.AnnAssign)
        for target in ([node.target] if isinstance(node, ast.AnnAssign) else node.targets)
        if isinstance(target, ast.Name) and target.id == "PROSE_FIELDS"
    ]
    assert rebindings == [], (
        f"record.py binds PROSE_FIELDS itself at line(s) {rebindings}; it imports the "
        "producer's declaration and does not restate it"
    )


def test_writing_a_run_produces_a_json_record_per_probe_and_a_summary(tmp_path: Path) -> None:
    results = [
        freshness.analyse(freshness.FreshnessObservation(window_s=60.0)),
        threads.analyse_ceiling(thread_observation({"a": (12, 12)})),
    ]
    summary = write_records(results, tmp_path)

    assert summary.exists()
    assert (tmp_path / "PF-freshness-raw.json").exists()
    record = json.loads((tmp_path / "PF-thread-size-ceiling.json").read_text(encoding="utf-8"))
    assert record["falsified_when"]
    assert record["changes_if_it_fails"]
    assert "recorded_at" in record
    text = summary.read_text(encoding="utf-8")
    assert "Falsified when" in text
    assert "Changes if it fails" in text


# --- the runner ------------------------------------------------------------------------------


def test_pf3_cannot_be_run_without_the_operator_declaring_an_exclusive_window() -> None:
    """PF-16, enforced rather than documented.

    PF-3 drives the per-minute budget to refusal by design. Contention makes its calibration
    tighter than reality - which looks like the safe direction for a cost bound and is the
    wrong one for a governor budget - so the run refuses until someone declares the window.
    Nothing here can verify the declaration, and the refusal says so.
    """
    from mailweave_harness.preflight.runner import ExclusiveWindowRequired, run_probes

    with pytest.raises(ExclusiveWindowRequired) as raised:
        run_probes(None, selected=["PF-3-quota-units"])  # type: ignore[arg-type]
    assert "nothing here can verify it" in str(raised.value).lower()


def test_the_other_probes_do_not_need_the_exclusive_window() -> None:
    """The refusal is scoped to the probe that earns it, not applied to the whole suite."""
    from mailweave_harness.preflight.runner import NEEDS_EXCLUSIVE_WINDOW

    assert {"PF-3-quota-units"} == NEEDS_EXCLUSIVE_WINDOW


def test_the_plan_needs_no_credential_and_no_network() -> None:
    """The reviewable artefact is reviewable before anything touches a mailbox.

    The offline fixture denies every outbound connection, so a plan that reached the network
    would fail here.
    """
    from mailweave_harness.preflight.__main__ import main

    assert main(["--plan"]) == 0
    assert main(["--list"]) == 0


# --- PF-21: endpoint latency (round 28) -------------------------------------------------------


def _latency(**series_ms: tuple[float, ...]) -> latency.LatencyObservation:

    observation = latency.LatencyObservation()
    for endpoint in latency.MEASURED:
        samples = series_ms.get(endpoint.value, tuple(float(i) for i in range(1, 11)))
        observation.per_endpoint.append(
            latency.EndpointLatency(endpoint=endpoint, samples_ms=samples)
        )
    return observation


def test_latency_passes_only_when_the_published_pair_is_consistent() -> None:
    """The published deadline can spend the published request cap only at 83 ms a request."""
    from mailweave.constants import MAX_HTTP_REQUESTS, MAX_SERVER_MS

    fast = tuple(float(40 + i) for i in range(10))  # p90 = 49 ms, x 24 = 1,176 ms
    result = latency.analyse(_latency(**{e.value: fast for e in latency.MEASURED}))
    assert result.verdict is Verdict.PASS
    assert result.findings["ms_per_request_the_published_pair_assumes"] == (
        MAX_SERVER_MS // MAX_HTTP_REQUESTS
    )

    slow = tuple(float(300 + 10 * i) for i in range(10))  # p90 = 380 ms (9th of 10), x 24 = 9,120
    result = latency.analyse(_latency(**{GmailEndpoint.THREADS_GET.value: slow}))
    assert result.verdict is Verdict.FAIL
    assert result.findings["slowest_p90_ms"] == 380
    # The candidate is registered as a bound, computed from the measurement, and not adopted.
    assert result.findings["candidate_deadline_ms"] == 9_200
    assert result.findings["candidate_is_a_bound_not_a_default"] is True


def test_latency_p90_is_an_observed_sample_and_the_cold_first_call_is_reported_alone() -> None:
    series = latency.EndpointLatency(
        endpoint=GmailEndpoint.MESSAGES_GET,
        samples_ms=(900.0, 210.0, 205.0, 230.0, 199.0, 240.0, 215.0, 208.0, 260.0, 220.0),
    )
    assert series.percentile(0.9) == 260.0  # the 9th of 10 sorted, not an interpolation
    assert series.percentile(0.5) == 215.0
    result = latency.analyse(_latency(**{GmailEndpoint.MESSAGES_GET.value: series.samples_ms}))
    entry = result.findings["endpoints"][GmailEndpoint.MESSAGES_GET.value]
    assert entry["cold_first_ms"] == 900
    assert entry["max_ms"] == 900
    assert entry["p90_ms"] == 260


def test_latency_is_inconclusive_when_a_series_ends_early_and_never_records_a_zero() -> None:
    from mailweave.gmail import GmailFault

    calls = {"n": 0}

    def flaky() -> None:
        calls["n"] += 1
        if calls["n"] == 3:
            raise GmailFault("simulated", endpoint=GmailEndpoint.GET_PROFILE)

    series = latency.time_endpoint(GmailEndpoint.GET_PROFILE, flaky, samples=10)
    assert series.count == 2 and series.stopped_early
    assert all(sample > 0 for sample in series.samples_ms)
    result = latency.analyse(_latency(**{GmailEndpoint.GET_PROFILE.value: series.samples_ms}))
    assert result.verdict is Verdict.INCONCLUSIVE
