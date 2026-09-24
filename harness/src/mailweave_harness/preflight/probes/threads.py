"""PF-1 and the thread-size ceiling (AD F PF-1, EVALUATION_PLAN's ground truth, issue #239).

Issue #239 reports `threads.get` truncating long threads. The evaluation plan uses that call
as ground truth for "what is in this thread", so if it truncates, Baseline B is lossy, every
comparison against it is re-interpreted, and PART-01's manifest-equality bar is unachievable
as written.

**The method, without a seeded corpus.** The obvious ground truth is the seeder's manifest,
and the seeder does not exist yet (WS-16). A second, independent source does exist today:
`messages.list` returns a `threadId` beside every message id, so walking the mailbox's
listing pages and grouping by thread gives a per-thread message count derived from a
*different endpoint*. Comparing the two is a real cross-check that needs no seeding, and it
is the same comparison the seeded version will make with a better ground truth later.

**The trap this probe has to avoid**, and it is a real one: `messages.list` and `threads.get`
disagree about SPAM and TRASH unless both are told the same thing. A probe that forgot
`includeSpamTrash` would report every thread containing one spam reply as truncated. Both
arms therefore carry the same scope, and the scope is part of the record.

Round 12: the setting is a `MailboxScope` rather than a bare boolean, because `messages.list`
takes the same instruction twice - once as `includeSpamTrash` and once as an `in:` operator
in `q` - and the arms can only be "at the same setting" if those two cannot disagree.
`preflight/scope.py` has the reasoning.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from mailweave_harness.preflight.scope import MailboxScope
from mailweave_harness.preflight.spec import ProbeResult, ProbeSpec, Verdict

COMPLETENESS_SPEC = ProbeSpec(
    id="PF-1-thread-completeness",
    title="threads.get completeness against an independently derived thread membership",
    measures=(
        "per thread: the number of message rows threads.get returned, against the number of "
        "messages messages.list attributed to that thread by its threadId, with both arms run "
        "at the same includeSpamTrash setting"
    ),
    validates=(
        "AD F PF-1, and the evaluation plan's use of threads.get as ground truth for thread "
        "membership; contract R-05 and amendment A4's `included == stated_total` guarantee "
        "rest on the same response"
    ),
    falsified_when=(
        "for any thread, threads.get returned strictly fewer message rows than messages.list "
        "attributed to that thread at the same includeSpamTrash setting"
    ),
    changes_if_it_fails=(
        "Baseline B is labelled **lossy** in every table and every comparison against it is "
        "re-interpreted; PART-01's manifest-equality bar becomes unachievable as written and "
        "escalates to the owner (AD H-2). `stated_total` stops meaning 'the thread's length' "
        "and means 'the rows this response returned', which is what the ledger already seals "
        "- so the code does not change, the *claims* do"
    ),
    credential="read",
    quota_budget_units=600,
    pre_registered_rules=(
        "strictly fewer, not merely different: threads.get returning MORE than the listing "
        "arm is expected whenever the listing arm's page budget stopped early, and is "
        "reported as a coverage note rather than as a failure",
    ),
)

CEILING_SPEC = ProbeSpec(
    id="PF-thread-size-ceiling",
    title="The real messages-per-thread ceiling",
    measures=(
        "the distribution of messages-per-thread over the sampled listing pages, and whether "
        "threads pile up at one exact maximum with nothing above it"
    ),
    validates=(
        "AD F PF-1's 5 / 12 / 40 / 100-message test threads, AD A.9a's 40-message worked "
        "example, and OD-3's arithmetic, all of which assume threads grow past 40"
    ),
    falsified_when=(
        "at least three sampled threads sit at exactly the maximum observed size and no "
        "thread exceeds it - the signature of a cap rather than of a distribution's tail"
    ),
    changes_if_it_fails=(
        "the disclosure budget arithmetic in AD A.9a and OD-3 is re-derived against the real "
        "ceiling instead of against 40, the evaluation corpus's 100-message thread shape is "
        "unbuildable and EVALUATION_PLAN's corpus spec changes, and any thread at the cap is "
        "known to continue in a *sibling* thread, which the reply-chain floor must then reach "
        "across - a structural change to WS-05, not a tuning one"
    ),
    credential="read",
    quota_budget_units=600,
    pre_registered_rules=(
        "three threads at the exact maximum is the pile-up rule, chosen before the run. It is "
        "arbitrary and is declared as such; the full histogram is recorded so a reviewer can "
        "apply a different rule to the same numbers without a re-run",
    ),
)

PILE_UP_AT_MAXIMUM = 3


@dataclass
class ThreadObservation:
    """Both arms, reduced to counts. No ids and no content are retained by default."""

    #: Both spellings of "where did the listing arm look", as one value. Recorded rather
    #: than assumed: PF-1's falsifier is stated at a given scope and means nothing without it.
    scope: MailboxScope
    #: thread digest -> rows returned by threads.get
    threads_get_rows: dict[str, int] = field(default_factory=dict)
    #: thread digest -> messages attributed by messages.list
    listing_rows: dict[str, int] = field(default_factory=dict)
    #: whether the listing walk stopped on the page budget rather than on Gmail running out
    listing_incomplete: bool = False
    pages_fetched: int = 0


def analyse_completeness(observation: ThreadObservation) -> ProbeResult:
    compared = sorted(set(observation.threads_get_rows) & set(observation.listing_rows))
    if not compared:
        return ProbeResult(
            spec=COMPLETENESS_SPEC,
            verdict=Verdict.INCONCLUSIVE,
            findings={"threads_compared": 0},
            notes=("no thread was observed through both endpoints",),
        )
    short = {
        thread: {
            "threads_get": observation.threads_get_rows[thread],
            "messages_list": observation.listing_rows[thread],
        }
        for thread in compared
        if observation.threads_get_rows[thread] < observation.listing_rows[thread]
    }
    over = [
        thread
        for thread in compared
        if observation.threads_get_rows[thread] > observation.listing_rows[thread]
    ]
    findings: dict[str, Any] = {
        "threads_compared": len(compared),
        "include_spam_trash": observation.scope.include_spam_trash,
        "listing_query": observation.scope.query,
        "listing_pages_fetched": observation.pages_fetched,
        "listing_walk_incomplete": observation.listing_incomplete,
        "threads_where_threads_get_returned_fewer": short,
        "threads_where_threads_get_returned_more": len(over),
    }
    if short:
        return ProbeResult(spec=COMPLETENESS_SPEC, verdict=Verdict.FAIL, findings=findings)
    notes: tuple[str, ...] = ()
    if observation.listing_incomplete:
        notes = (
            "the listing arm stopped on its page budget, so a thread whose remaining messages "
            "are on an unfetched page is under-counted on that side. That direction cannot "
            "produce a false FAIL - it can only hide a real one - so the verdict is a pass "
            "with reduced coverage rather than an inconclusive.",
        )
    return ProbeResult(spec=COMPLETENESS_SPEC, verdict=Verdict.PASS, findings=findings, notes=notes)


def analyse_ceiling(observation: ThreadObservation) -> ProbeResult:
    sizes = observation.threads_get_rows or observation.listing_rows
    if not sizes:
        return ProbeResult(
            spec=CEILING_SPEC,
            verdict=Verdict.INCONCLUSIVE,
            findings={"threads_sampled": 0},
            notes=("no thread sizes were observed",),
        )
    histogram = Counter(sizes.values())
    largest = max(histogram)
    at_maximum = histogram[largest]
    findings: dict[str, Any] = {
        "threads_sampled": len(sizes),
        "largest_thread_observed": largest,
        "threads_at_that_size": at_maximum,
        "histogram": {str(size): count for size, count in sorted(histogram.items())},
        "pile_up_rule": PILE_UP_AT_MAXIMUM,
    }
    if at_maximum >= PILE_UP_AT_MAXIMUM:
        return ProbeResult(
            spec=CEILING_SPEC,
            verdict=Verdict.FAIL,
            findings=findings,
            notes=(
                f"{at_maximum} threads sit at exactly {largest} messages and none is larger, "
                "which is the shape of a cap rather than of a tail.",
            ),
        )
    return ProbeResult(
        spec=CEILING_SPEC,
        verdict=Verdict.PASS,
        findings=findings,
        notes=(
            "no ceiling is visible in this sample. That is not a proof that none exists: a "
            "mailbox with no long threads cannot show one, and the histogram is recorded so "
            "the sample's reach is visible rather than assumed.",
        ),
    )
