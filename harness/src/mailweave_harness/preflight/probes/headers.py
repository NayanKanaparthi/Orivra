"""PF-2 - do `References` and `In-Reply-To` survive `metadataHeaders`? (AD F PF-2, D.5)

The method is a **differential**: fetch the same thread twice, once at `format=metadata` with
the eight headers the thread map needs and once at `format=full`, and compare. `format=full`
returns the message's real headers, so it is the ground truth for "does this message have an
`In-Reply-To` at all" - which is the question that makes the difference meaningful. Without
that arm, a missing header is indistinguishable from a message that never had one, and the
probe would report the mailbox's threading habits rather than the API's behaviour.

## The first live run passed without exercising the question it exists to ask

Run 1 (2026-09-11) returned PASS on a thread of **one** message that carried neither
`In-Reply-To` nor `References` in the full arm. Every rule fired correctly: no header the
full arm showed was dropped by the metadata arm, so `headers_dropped_by_metadata` was empty,
so the verdict was PASS. The reply-linking question - the whole reason D.5 prices the thread
map at `threads.get(format=metadata)` - was never asked, because there was nothing to drop.

That is a test passing for a reason that does not establish what it claims, which is the
defect class this project keeps meeting (R-M1-003; replants R134, R153). A probe cannot
report PASS for a property no message in its sample could have exhibited.

So the probe now carries **per-question verdicts**, because the two questions have different
consumers and different consequences and can be exercised to different degrees by the same
thread:

  * `reply_header_verdict` - INCONCLUSIVE unless at least one shared message's **full arm**
    carries `In-Reply-To` or `References`. Only then can "the metadata arm kept it" mean
    anything.
  * `snippet_verdict` - the identical floor one branch over, found while fixing the first:
    INCONCLUSIVE unless at least one shared message's full arm carries both a snippet and an
    `internalDate`. Leaving it would have been the same bug with a different name.

The overall verdict is the conservative join: FAIL if either question failed, INCONCLUSIVE if
either was under-exercised, PASS only when both were exercised and both held.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mailweave.gmail import Message, Thread
from mailweave_harness.preflight.spec import ProbeResult, ProbeSpec, Verdict

SPEC = ProbeSpec(
    id="PF-2-metadata-headers",
    title="References / In-Reply-To survival under format=metadata",
    measures=(
        "for one thread fetched twice - format=metadata with metadataHeaders, and format=full "
        "- which requested headers the metadata arm returned, out of those the full arm shows "
        "the message actually carries; and whether the metadata arm returned a per-message "
        "snippet and internalDate"
    ),
    validates=(
        "AD D.5's thread-map and pool design, which is priced at threads.get(format=metadata) "
        "= 40 u and assumes the reply-linking headers, the snippet and internalDate are all "
        "present. AD A.2 step 4's temporal ordering rests on internalDate specifically"
    ),
    falsified_when=(
        "any header requested via metadataHeaders is absent from the metadata arm while the "
        "full arm shows the message carries it; or the metadata arm returns no snippet or no "
        "internalDate for a message the full arm gives both for. Each question is answered "
        "separately and neither can PASS on a sample that could not have exhibited it"
    ),
    changes_if_it_fails=(
        "AD F PF-2's branch table executes. Headers absent => the reply-chain floor needs "
        "format=full (a bytes and latency change at the same 40 u, not a quota one). "
        "snippet/internalDate absent => primary fallback is threads.get(format=full) at the "
        "same cost, pool text becomes subject + participants + body-head-400, and "
        "max_pool_threads drops 25 -> 15 with the reduced bound declared per T-RO1. The "
        "client already refuses to invent chronological positions when internalDate is "
        "missing, so this failure degrades a thread map rather than corrupting one"
    ),
    credential="read",
    #: 80 u when the operator names a thread (two threads.get at 40 u). Without one, the
    #: runner probes up to MAX_SELECTION_PROBES candidate threads at format=full to find one
    #: that actually carries a reply-linking header, and reuses the chosen candidate's full
    #: arm rather than fetching it twice: 40*K + 40. Registered before the rerun, per PF-16.
    quota_budget_units=200,
    pre_registered_rules=(
        "the full arm is ground truth for header presence; a header absent from both arms is "
        "reported as 'the message has none' and is not counted as a metadata failure",
        "a question whose sample could not have exhibited it is INCONCLUSIVE, never PASS: "
        "reply-header survival needs at least one shared message whose full arm carries "
        "In-Reply-To or References, and snippet survival needs at least one whose full arm "
        "carries both a snippet and an internalDate",
        "the overall verdict is the conservative join of the per-question verdicts - FAIL if "
        "either failed, INCONCLUSIVE if either was under-exercised, PASS only if both held",
        "thread selection is deterministic: candidates ordered by message count descending "
        "then thread id ascending, and the first carrying a reply-linking header is used; "
        "the operator may name a thread id instead, and the choice is recorded",
    ),
)

#: The headers the thread map asks for. Imported from the client rather than restated would
#: be better still, and it is: see `measure`.
REPLY_LINKING = ("In-Reply-To", "References")


def _header_names(message: Message) -> set[str]:
    if message.payload is None:
        return set()
    return {header.name.lower() for header in message.payload.headers}


@dataclass
class HeaderObservation:
    """One thread, fetched both ways, reduced to per-message header name sets."""

    requested_headers: tuple[str, ...]
    metadata_headers_by_id: dict[str, set[str]] = field(default_factory=dict)
    full_headers_by_id: dict[str, set[str]] = field(default_factory=dict)
    metadata_has_snippet: dict[str, bool] = field(default_factory=dict)
    metadata_has_internal_date: dict[str, bool] = field(default_factory=dict)
    full_has_snippet: dict[str, bool] = field(default_factory=dict)
    full_has_internal_date: dict[str, bool] = field(default_factory=dict)
    #: How this thread came to be the one measured. A closed vocabulary token plus counts,
    #: never a thread id: an id is a mailbox identifier and the record is persisted (OD-4).
    selection: str = "unrecorded"
    #: How many candidate threads were fetched before this one was chosen. Zero when the
    #: operator named a thread. Lets a reviewer price the run without re-reading the runner.
    candidates_probed: int = 0


def observe(
    *, metadata_arm: Thread, full_arm: Thread, requested_headers: tuple[str, ...]
) -> HeaderObservation:
    """Reduce two `Thread` responses to the comparison, keeping no header *values*.

    Header names are a closed vocabulary; header values are mail content (a Subject is a
    subject, a From is an address). Only the names cross into the observation, which is what
    lets the record be written at all under OD-4.
    """
    observation = HeaderObservation(requested_headers=requested_headers)
    for message in metadata_arm.messages:
        observation.metadata_headers_by_id[message.id] = _header_names(message)
        observation.metadata_has_snippet[message.id] = bool(message.snippet)
        observation.metadata_has_internal_date[message.id] = message.internal_date is not None
    for message in full_arm.messages:
        observation.full_headers_by_id[message.id] = _header_names(message)
        observation.full_has_snippet[message.id] = bool(message.snippet)
        observation.full_has_internal_date[message.id] = message.internal_date is not None
    return observation


def analyse(observation: HeaderObservation) -> ProbeResult:
    """Judge each question separately, then join conservatively.

    The join is the part that matters. Run 1 passed because one PASS-shaped question (no
    header was dropped) stood in for a question that was never asked (could one have been?).
    A single verdict cannot express "the metadata arm kept every header it was given, and it
    was given none of the ones we care about", so it reported the first half.
    """
    shared = sorted(set(observation.metadata_headers_by_id) & set(observation.full_headers_by_id))
    if not shared:
        return ProbeResult(
            spec=SPEC,
            verdict=Verdict.INCONCLUSIVE,
            findings={
                "messages_compared": 0,
                "reply_header_verdict": Verdict.INCONCLUSIVE.value,
                "snippet_verdict": Verdict.INCONCLUSIVE.value,
                "reply_header_bearing_messages_compared": 0,
                "snippet_bearing_messages_compared": 0,
                "thread_selection": observation.selection,
                "candidate_threads_probed": observation.candidates_probed,
            },
            notes=("the two arms shared no message, so nothing could be compared",),
        )
    requested = {name.lower() for name in observation.requested_headers}
    reply_linking = {name.lower() for name in REPLY_LINKING}
    dropped: dict[str, list[str]] = {}
    absent_from_both: dict[str, list[str]] = {}
    #: Per requested header, how many shared messages the full arm shows actually carry it.
    #: This is the coverage number that would have made run 1's gap visible without a rerun.
    exercised: dict[str, int] = dict.fromkeys(sorted(requested), 0)
    for message_id in shared:
        in_metadata = observation.metadata_headers_by_id[message_id]
        in_full = observation.full_headers_by_id[message_id]
        for name in sorted(requested):
            if name in in_full:
                exercised[name] += 1
                if name not in in_metadata:
                    dropped.setdefault(name, []).append(message_id)
            else:
                absent_from_both.setdefault(name, []).append(message_id)

    snippet_lost = [
        message_id
        for message_id in shared
        if observation.full_has_snippet.get(message_id)
        and not observation.metadata_has_snippet.get(message_id)
    ]
    date_lost = [
        message_id
        for message_id in shared
        if observation.full_has_internal_date.get(message_id)
        and not observation.metadata_has_internal_date.get(message_id)
    ]

    # A question is only answerable over the messages that could have exhibited it.
    reply_bearing = [
        message_id
        for message_id in shared
        if observation.full_headers_by_id[message_id] & reply_linking
    ]
    snippet_bearing = [
        message_id
        for message_id in shared
        if observation.full_has_snippet.get(message_id)
        and observation.full_has_internal_date.get(message_id)
    ]
    reply_dropped = sorted(name for name in dropped if name in reply_linking)

    if reply_dropped:
        reply_verdict = Verdict.FAIL
    elif not reply_bearing:
        reply_verdict = Verdict.INCONCLUSIVE
    else:
        reply_verdict = Verdict.PASS

    if snippet_lost or date_lost:
        snippet_verdict = Verdict.FAIL
    elif not snippet_bearing:
        snippet_verdict = Verdict.INCONCLUSIVE
    else:
        snippet_verdict = Verdict.PASS

    # Non-reply headers are reported but do not carry their own verdict: no design
    # commitment in D.5 rests on Subject or Cc surviving, and `exercised` already shows a
    # reviewer exactly how much of each was sampled.
    other_dropped = sorted(name for name in dropped if name not in reply_linking)

    if Verdict.FAIL in (reply_verdict, snippet_verdict) or other_dropped:
        verdict = Verdict.FAIL
    elif Verdict.INCONCLUSIVE in (reply_verdict, snippet_verdict):
        verdict = Verdict.INCONCLUSIVE
    else:
        verdict = Verdict.PASS

    findings: dict[str, Any] = {
        "messages_compared": len(shared),
        "requested_headers": list(observation.requested_headers),
        "headers_dropped_by_metadata": {name: len(ids) for name, ids in dropped.items()},
        "headers_absent_from_both_arms": {name: len(ids) for name, ids in absent_from_both.items()},
        "messages_carrying_each_requested_header_in_the_full_arm": exercised,
        "reply_linking_headers_dropped": reply_dropped,
        "messages_losing_snippet_under_metadata": len(snippet_lost),
        "messages_losing_internal_date_under_metadata": len(date_lost),
        "reply_header_verdict": reply_verdict.value,
        "snippet_verdict": snippet_verdict.value,
        "reply_header_bearing_messages_compared": len(reply_bearing),
        "snippet_bearing_messages_compared": len(snippet_bearing),
        "thread_selection": observation.selection,
        "candidate_threads_probed": observation.candidates_probed,
    }
    notes = [
        "header *names* are recorded and header values are not: a Subject is a subject "
        "and a From is an address, and neither belongs in a persisted record (OD-4).",
    ]
    if reply_verdict is Verdict.INCONCLUSIVE:
        notes.append(
            "reply-header survival is UNDER-EXERCISED: no message in this sample carried "
            "In-Reply-To or References in the full arm, so the metadata arm had nothing to "
            "drop and nothing to keep. Rerun against a multi-message thread."
        )
    if snippet_verdict is Verdict.INCONCLUSIVE:
        notes.append(
            "snippet survival is UNDER-EXERCISED: no message in this sample carried both a "
            "snippet and an internalDate in the full arm."
        )
    return ProbeResult(spec=SPEC, verdict=verdict, findings=findings, notes=tuple(notes))
