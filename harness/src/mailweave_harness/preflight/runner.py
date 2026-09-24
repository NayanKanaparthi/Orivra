"""The probe registry, the run plan, and the runner (AD F, PF-16).

`--plan` prints what would run, what credential each probe needs, what it would cost at the
published (uncalibrated) rates, and - for each - what would falsify it and what changes if it
does. It needs no credential and no network, so the plan can be reviewed before anything is
executed against a real mailbox, which is the point.

`--run` needs the owner's credential and their machine. It is not reachable from an agent
environment: it reads a token from the store the consent flow wrote, and there is no consent
flow that an agent can start.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from mailweave.envelope import DispositionLedger, RungId
from mailweave.gmail import GmailClient
from mailweave_harness.preflight import measure
from mailweave_harness.preflight.probes import (
    freshness,
    headers,
    invisible,
    latency,
    quota,
    threads,
)
from mailweave_harness.preflight.record import run_salt, write_records
from mailweave_harness.preflight.spec import ProbeResult, ProbeSpec

REGISTRY: Final[tuple[ProbeSpec, ...]] = (
    quota.SPEC,
    headers.SPEC,
    threads.COMPLETENESS_SPEC,
    threads.CEILING_SPEC,
    freshness.SPEC,
    invisible.SPEC,
    latency.SPEC,
)

#: Probes that must run under an exclusive window on the project (PF-16): PF-3 drives the
#: per-minute budget to refusal by design, and anything else running concurrently makes its
#: calibration wrong in the direction that looks safe and is not.
NEEDS_EXCLUSIVE_WINDOW: Final[frozenset[str]] = frozenset({quota.SPEC.id})


@dataclass(frozen=True)
class Plan:
    probes: tuple[ProbeSpec, ...]

    @property
    def total_budget_units(self) -> int:
        return sum(probe.quota_budget_units for probe in self.probes)


PLAN: Final[Plan] = Plan(probes=REGISTRY)


def plan_text() -> str:
    """The run plan, in full, with every falsification condition spelled out."""
    lines = [
        "MailWeave Loop-0 preflight - run plan",
        "",
        f"{len(PLAN.probes)} probes. Declared suite budget: {PLAN.total_budget_units} quota "
        "units at the PUBLISHED rates,",
        "which are themselves uncalibrated until PF-3 has run (AD A.11: quota units are a",
        "diagnostic, never a headline).",
        "",
    ]
    for probe in PLAN.probes:
        lines.extend(
            [
                f"[{probe.id}] {probe.title}",
                f"    credential:  {probe.credential}",
                f"    budget:      {probe.quota_budget_units} u (published, uncalibrated)",
                f"    measures:    {probe.measures}",
                f"    validates:   {probe.validates}",
                f"    FAILS WHEN:  {probe.falsified_when}",
                f"    then:        {probe.changes_if_it_fails}",
            ]
        )
        for rule in probe.pre_registered_rules:
            lines.append(f"    registered:  {rule}")
        if probe.id in NEEDS_EXCLUSIVE_WINDOW:
            lines.append(
                "    NOTE:        needs an exclusive window on the project (PF-16); the "
                "runner refuses without --exclusive-window"
            )
        lines.append("")
    lines.extend(
        [
            "Nothing in this plan has been run. No probe writes mail text: records carry",
            "counts, code points, closed-vocabulary tokens and salted digests, and the writer",
            "refuses a record that carries anything else (OD-4).",
        ]
    )
    return "\n".join(lines)


def record_results(results: list[ProbeResult], out_dir: Path) -> Path:
    """Write the run's record. Separated so a caller can assemble results any way it likes."""
    return write_records(results, out_dir)


class ExclusiveWindowRequired(RuntimeError):
    """PF-3 was selected without the operator declaring an exclusive window (PF-16)."""


def run_probes(
    client: GmailClient,
    *,
    selected: Sequence[str] | None = None,
    exclusive_window: bool = False,
    freshness_window_s: float = 0.0,
    freshness_poll_s: float = 30.0,
    sample_size: int = 40,
    headers_thread_id: str | None = None,
) -> list[ProbeResult]:
    """Execute the selected probes against a live mailbox and return their results.

    Written to be read alongside the plan: each block is one probe's `measure` followed by its
    `analyse`, and the judgement is entirely in the second half, which is unit-tested with no
    network. A probe that raises is not silently skipped - the exception carries out, because
    a preflight that half-ran and reported a pass is worse than one that stopped.

    PF-16 is enforced here rather than documented: PF-3 drives the per-minute budget to
    refusal, so anything sharing the project makes its calibration wrong in the direction that
    looks safe. `exclusive_window` is the operator's declaration; this code cannot verify it,
    and says so rather than pretending to check.

    `freshness_poll_s` is the watch loop's sleep between `history.list` polls. It is a
    parameter rather than a constant because it was the one thing in the whole runner that
    no test could reach: the loop's only exit is the window closing, and a hard-wired 30 s
    sleep meant exercising it cost 30 s of wall clock, so round 11 never did.
    """
    wanted = set(selected) if selected else {probe.id for probe in REGISTRY}
    if wanted & NEEDS_EXCLUSIVE_WINDOW and not exclusive_window:
        raise ExclusiveWindowRequired(
            f"{sorted(wanted & NEEDS_EXCLUSIVE_WINDOW)} drives the per-minute quota budget to "
            "refusal by design (PF-16). Confirm no other run is in flight on this Google "
            "Cloud project and pass --exclusive-window. This is your declaration: nothing "
            "here can verify it."
        )
    salt = run_salt()
    results: list[ProbeResult] = []
    ledger = DispositionLedger()
    sampled = measure.sample_mailbox(client, ledger, max_pages=5)
    message_ids = sorted(sampled.thread_by_message)[:sample_size]
    thread_ids = sorted(set(sampled.thread_by_message.values()))

    if headers.SPEC.id in wanted and (thread_ids or headers_thread_id):
        # `sorted(thread_ids)[0]` is the lexicographically smallest id in the sample and has
        # nothing to do with whether the thread can exhibit what PF-2 tests. Run 1 drew a
        # one-message thread that way and reported PASS on a question it never asked.
        choice: measure.ThreadChoice | None
        if headers_thread_id:
            choice = measure.ThreadChoice(
                thread_id=headers_thread_id,
                full_arm=None,
                selection="operator-supplied-thread-id",
                candidates_probed=0,
            )
        else:
            choice = measure.choose_reply_bearing_thread(
                client, thread_by_message=sampled.thread_by_message
            )
        if choice is not None:
            results.append(
                headers.analyse(
                    measure.measure_metadata_headers(
                        client,
                        thread_id=choice.thread_id,
                        full_arm=choice.full_arm,
                        selection=choice.selection,
                        candidates_probed=choice.candidates_probed,
                    )
                )
            )
    if {threads.COMPLETENESS_SPEC.id, threads.CEILING_SPEC.id} & wanted:
        observation = measure.measure_threads(client, salt=salt)
        if threads.COMPLETENESS_SPEC.id in wanted:
            results.append(threads.analyse_completeness(observation))
        if threads.CEILING_SPEC.id in wanted:
            results.append(threads.analyse_ceiling(observation))
    if invisible.SPEC.id in wanted and message_ids:
        results.append(
            invisible.analyse(measure.measure_invisible(client, message_ids=message_ids, salt=salt))
        )
    if freshness.SPEC.id in wanted:
        results.append(
            freshness.analyse(
                freshness.FreshnessObservation(window_s=freshness_window_s)
                if freshness_window_s <= 0
                else _freshness_run(
                    client,
                    salt=salt,
                    window_s=freshness_window_s,
                    poll_s=freshness_poll_s,
                )
            )
        )
    # PF-21 before PF-3 for the same reason PF-3 is last: a latency measured while the
    # project is being driven to refusal would be a measurement of the refusal.
    if latency.SPEC.id in wanted and message_ids and thread_ids:
        results.append(
            latency.analyse(
                measure.measure_latency(client, message_id=message_ids[0], thread_id=thread_ids[0])
            )
        )
    # PF-3 last, deliberately: it ends with the project rate limited, so every other probe
    # has already taken its measurement by the time the budget is gone.
    if quota.SPEC.id in wanted and message_ids and thread_ids:
        results.append(
            quota.analyse(
                measure.measure_quota(
                    client,
                    message_id=message_ids[0],
                    thread_id=thread_ids[0],
                    start_history_id=_watermark(client),
                )
            )
        )
    return results


def _watermark(client: GmailClient) -> str:
    """A `historyId` to start from: the mailbox's current one, from `getProfile`."""
    profile = client.get_profile()
    if profile.history_id is None:
        raise RuntimeError(
            "users.getProfile returned no historyId, so history.list has no starting point"
        )
    return profile.history_id


def _freshness_run(
    client: GmailClient, *, salt: bytes, window_s: float, poll_s: float = 30.0
) -> freshness.FreshnessObservation:
    """The freshness watch, with its id-exact search supplied.

    `rfc822msgid:` needs the message's RFC822 `Message-ID`, which costs one `messages.get`
    per candidate. That cost is in the probe's declared budget.
    """

    def find_by_id(message_id: str) -> bool:
        message = client.get_message(message_id, message_format="metadata")
        header = None
        if message.payload is not None:
            header = message.payload.header("Message-ID")
        if not header:
            return False
        probe_ledger = DispositionLedger()
        run = client.list_messages(
            probe_ledger,
            rung=RungId.LR,
            query=f"rfc822msgid:{header.strip('<>')}",
            widening_affordance=measure.WIDEN,
            page_size=1,
        )
        return run.ids_recorded > 0

    return measure.measure_freshness(
        client,
        start_history_id=_watermark(client),
        salt=salt,
        window_s=window_s,
        poll_s=poll_s,
        find_by_id=find_by_id,
    )
