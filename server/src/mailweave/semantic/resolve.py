"""Turning preflight records into the profile the rung runs under (AD D.5, F PF-2, PF-4).

This is the only place a measured number becomes an operating parameter, and the only place
the `assumed` branch is chosen. Keeping it in one function is what makes "no guessed
constant is on the semantic path" a property somebody can check by reading one file.

## The branch table, executed rather than described

PF-2 asks two separable questions about `threads.get(format=metadata, metadataHeaders=[…])`:

  1. **Does a per-message `snippet` survive?** This is what D.5's pool text depends on. If
     it does not, the primary fallback is `threads.get(format=full)` at the **same 40 u**
     (quota is per method, not per format), pool text becomes subject + participants +
     body-head-400, and `max_pool_threads` drops 25 → 15.
  2. **Do `In-Reply-To` / `References` survive?** This is what the reply-chain floor
     depends on, and it is a *different* consumer with a *different* consequence: the floor
     needs `format=full`, a bytes-and-latency change at the same quota.

The probe reports a single `FAIL` if **either** fails, plus `messages_losing_snippet_under_
metadata` and `reply_linking_headers_dropped` in its findings. So a FAIL verdict alone
cannot select a branch: reading it as "no snippet" would move the pool onto the fallback
whenever a header was dropped, and reading it as "snippet fine" would do the reverse. The
resolver reads the **findings**, and the verdict only decides whether the findings are
trustworthy enough to act on.

That distinction is the whole reason this file exists rather than a boolean somewhere.

## An inconclusive record is an absent record

`Verdict.INCONCLUSIVE` means the probe ran and could not decide - too few threads, no
shared message between the arms. `preflight/spec.py` states it is "never a pass". A design
commitment guarded by an inconclusive probe is unvalidated, so it lands on the declared
fallback exactly as if nobody had run anything.
"""

from __future__ import annotations

from typing import Any, Final

from mailweave import constants
from mailweave.semantic.profile import (
    FALLBACK_MAX_POOL_THREADS,
    Basis,
    PoolTextMode,
    Provenance,
    SemanticProfile,
    unmeasured_profile,
)
from mailweave.semantic.records import PreflightRecord, load_records

#: The probe ids this resolver consumes. `PF-2` exists and runs today; `PF-4` is the
#: model-latency probe M2 adds. A record that is not present resolves to `assumed`, so
#: naming an id here commits nothing and asserts nothing about whether it has run.
PF2_METADATA_HEADERS: Final[str] = "PF-2-metadata-headers"
PF4_MODEL_LATENCY: Final[str] = "PF-4-model-latency"

_SNIPPET_LOSS_KEY: Final[str] = "messages_losing_snippet_under_metadata"
_DATE_LOSS_KEY: Final[str] = "messages_losing_internal_date_under_metadata"
_REPLY_DROPPED_KEY: Final[str] = "reply_linking_headers_dropped"
_COMPARED_KEY: Final[str] = "messages_compared"
#: PF-2 answers two questions with different consumers, and one thread can exercise them to
#: different degrees. Since 2026-09-11 the probe writes a verdict per question; a record
#: without them predates that and cannot be read as having answered either.
_SNIPPET_VERDICT_KEY: Final[str] = "snippet_verdict"
_REPLY_VERDICT_KEY: Final[str] = "reply_header_verdict"


def _count(findings: dict[str, Any], key: str) -> int | None:
    value = findings.get(key)
    # `bool` is an `int`; a `True` here would read as 1 and quietly mean "one message lost
    # its snippet", which is a different claim from the one the producer made.
    if type(value) is not int:
        return None
    return value


def _positive_int(findings: dict[str, Any], key: str) -> int | None:
    value = _count(findings, key)
    if value is None or value <= 0:
        return None
    return value


def _question_answered(record: PreflightRecord | None, verdict_key: str) -> bool:
    """Whether PF-2 actually answered one of its two questions.

    The overall verdict cannot decide this and never could. Run 1 (2026-09-11) returned
    PASS from a one-message thread carrying neither `In-Reply-To` nor `References`: no
    header was dropped, so the header rule held vacuously, so the probe passed - having
    asked nothing about reply-header survival. Reading that verdict as an answer would have
    put a design commitment on a measurement that does not exist.

    So each question carries its own verdict, and only `pass` or `fail` is an answer.
    A record written before 2026-09-11 has neither key, and is therefore not an answer to
    either question: it is preserved as raw evidence and it decides nothing. That is the
    non-destructive way to invalidate a claim - the file is untouched, and the reader
    stops being able to draw the conclusion.
    """
    if record is None:
        return False
    compared = _count(record.findings, _COMPARED_KEY)
    if compared is None or compared <= 0:
        return False
    verdict = record.findings.get(verdict_key)
    if type(verdict) is not str:
        return False
    return verdict in {"pass", "fail"}


def resolve_profile(
    records: dict[str, PreflightRecord] | None = None,
    *,
    directory: str | None = None,
) -> SemanticProfile:
    """The profile this process runs the semantic rung under.

    With no usable PF-2 record this returns `unmeasured_profile()`: D.5's primary fallback,
    taken deliberately, declared as unmeasured. With one, the branch is selected from the
    findings and the provenance names the record and its run date.
    """
    if records is None:
        records = load_records(directory or "preflight-records")

    pf2 = records.get(PF2_METADATA_HEADERS)
    pf4 = records.get(PF4_MODEL_LATENCY)

    if not _question_answered(pf2, _SNIPPET_VERDICT_KEY):
        base = unmeasured_profile()
        return _with_pf4(base, pf4)

    assert pf2 is not None  # narrowed by _question_answered
    snippet_lost = _positive_int(pf2.findings, _SNIPPET_LOSS_KEY)
    date_lost = _positive_int(pf2.findings, _DATE_LOSS_KEY)

    if snippet_lost is None and date_lost is None:
        mode = PoolTextMode.SNIPPET
        threads = constants.MAX_POOL_THREADS
        detail = (
            f"PF-2 compared {_count(pf2.findings, _COMPARED_KEY)} messages and observed no "
            "message losing its snippet or internalDate under format=metadata"
        )
    else:
        mode = PoolTextMode.BODY_HEAD
        threads = FALLBACK_MAX_POOL_THREADS
        lost = []
        if snippet_lost is not None:
            lost.append(f"{snippet_lost} lost their snippet")
        if date_lost is not None:
            lost.append(f"{date_lost} lost internalDate")
        detail = (
            "PF-2 measured the metadata arm dropping what the pool needs ("
            + "; ".join(lost)
            + "), so D.5's primary fallback threads.get(format=full) applies at the same 40 u "
            "and max_pool_threads drops 25->15"
        )

    profile = SemanticProfile(
        pool_text_mode=mode,
        pool_text_provenance=Provenance(
            basis=Basis.MEASURED,
            source=f"{PF2_METADATA_HEADERS} ({pf2.recorded_at})",
            detail=detail,
        ),
        max_pool_threads=threads,
        max_pool_messages=constants.MAX_POOL_MESSAGES,
        max_rerank_pairs=constants.MAX_RERANK_PAIRS,
        max_semantic_ms=constants.MAX_SEMANTIC_MS,
        bounds_provenance=unmeasured_profile().bounds_provenance,
    )
    return _with_pf4(profile, pf4)


def _with_pf4(profile: SemanticProfile, pf4: PreflightRecord | None) -> SemanticProfile:
    """Overlay PF-4's measured bounds, if a passing record exists.

    PF-4 measures the owner's laptop, so unlike PF-2 only a `pass` is actionable: a failing
    model-latency run means the candidate model did not clear its bar, and its numbers are
    evidence for changing the default model, not parameters to run under.
    """
    if pf4 is None or not pf4.is_measured:
        return profile
    findings = pf4.findings
    # Run 1 (2026-09-11) passed without recording which device loaded the weights and
    # without warming the reranker, and its rerank curve fell as the work grew. A record
    # that cannot say what it measured on, or that timed each size once, is not a
    # measurement this can adopt - invalidated by what it does not contain, so the file
    # stays on disk untouched and simply stops deciding anything.
    if type(findings.get("device")) is not str or not findings.get("device"):
        return profile
    if _positive_int(findings, "repeats_per_size") is None:
        return profile
    if findings.get("rerank_curve_is_non_decreasing") is not True:
        return profile
    semantic_ms = _positive_int(findings, "max_semantic_ms")
    pool_messages = _positive_int(findings, "max_pool_messages")
    rerank_pairs = _positive_int(findings, "max_rerank_pairs")
    if semantic_ms is None or pool_messages is None or rerank_pairs is None:
        # A passing record that does not carry the three constants it exists to set is not
        # a usable record. Taking the two it does have and leaving the third assumed would
        # produce a profile that calls itself measured on mixed warrant.
        return profile
    return SemanticProfile(
        pool_text_mode=profile.pool_text_mode,
        pool_text_provenance=profile.pool_text_provenance,
        max_pool_threads=profile.max_pool_threads,
        max_pool_messages=pool_messages,
        max_rerank_pairs=rerank_pairs,
        max_semantic_ms=semantic_ms,
        bounds_provenance=Provenance(
            basis=Basis.MEASURED,
            source=f"{PF4_MODEL_LATENCY} ({pf4.recorded_at})",
            detail=(
                "measured on the owner's laptop, CPU only: embed wall clock, rerank latency "
                "at the shortlist size, cold load and RSS"
            ),
        ),
    )


def reply_chain_needs_full(
    records: dict[str, PreflightRecord] | None = None,
    *,
    directory: str | None = None,
) -> tuple[bool, Provenance]:
    """PF-2's *other* consequence: does the reply-chain floor need `format=full`?

    Separate from the pool because it is a separate consumer with a separate cost. A
    dropped `In-Reply-To` changes bytes and latency at the same quota; it says nothing about
    the snippet, and the snippet says nothing about it.
    """
    if records is None:
        records = load_records(directory or "preflight-records")
    pf2 = records.get(PF2_METADATA_HEADERS)
    if not _question_answered(pf2, _REPLY_VERDICT_KEY):
        return (
            True,
            Provenance(
                basis=Basis.ASSUMED,
                source="AD F PF-2 (unanswered)",
                detail=(
                    "the survival of In-Reply-To/References under metadataHeaders is "
                    "unanswered: either PF-2 has not run, or it ran on a sample whose "
                    "full arm carried neither header and so could not exhibit a drop. "
                    "format=full needs no such fact and costs the same 40 u"
                ),
            ),
        )
    assert pf2 is not None
    dropped = pf2.findings.get(_REPLY_DROPPED_KEY)
    lost = bool(dropped) if type(dropped) is list else True
    return (
        lost,
        Provenance(
            basis=Basis.MEASURED,
            source=f"{PF2_METADATA_HEADERS} ({pf2.recorded_at})",
            detail=(
                f"reply-linking headers dropped by the metadata arm: {sorted(dropped)}"
                if type(dropped) is list and dropped
                else "the metadata arm returned every reply-linking header the full arm shows"
            ),
        ),
    )
