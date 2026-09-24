"""A case file the corpus writes about itself, for checking the machinery and nothing else.

**Every query here is a sentinel token**, a unique string the generator planted in exactly one
message and nowhere else. A query that *is* the token has one lexical match by construction, so
any system with a working search answers it and no arm can be distinguished from another. That
is the whole point: these cases exercise the pipeline and are incapable of saying anything about
retrieval quality.

Two things use it. `--dry-run` builds it over a dummy corpus offline. `--live-check` builds it
over the real seeded corpus and runs the actual campaign command against the real mailbox, which
is the only way to find out whether `runtime.start`, the trace sinks, the floor client and the
report all work against a live credential **before** the independently authored cases arrive and
the first real run is also the first run.

One implementation rather than two, because the alternative is two constructions of the same
artifact and the second one is always the one nobody updates.

Nothing here is a campaign case, and `EVALUATION_PLAN.md` §4's families are not what the
`family` fields below mean: they are spread across four labels so the report has more than one
row to render. A number produced from this file is a statement about plumbing.
"""

from __future__ import annotations

import re

from mailweave_harness.evaluation.cases import CaseFile
from mailweave_harness.seed.manifest import Manifest, SeededMessage


def _opening(message: SeededMessage, width: int = 60) -> str:
    """The first line of a body, trimmed.

    **Used as the recall quote instead of the reference token.** EP §6.1's `disclosed` asks
    whether the quote is present in what the caller actually received, and the reference is the
    last line of every body, so any abridged disclosure drops it and a message that *was*
    disclosed scores as not carried. The reference stays the query - it is what finds the
    message - and the quote is text that survives being snipped.
    """
    first = re.sub(r"\n-- \n.*$", "", message.body, flags=re.S).splitlines()[0]
    return first[:width]


def sentinel_case_file(
    manifest: Manifest,
    *,
    escalation: str | None = None,
    window: str | None = None,
) -> CaseFile:
    """One case per sentinel, across four families. **Queries are the sentinel tokens.**

    A sentinel occurs in exactly one message and nowhere else in the corpus, which the manifest
    enforces - so a query that is the token has one right answer and the join is unambiguous.
    That makes these cases useful for exercising the pipeline and useless as evidence about
    retrieval, which is the trade this construction exists to make.
    """
    by_id = {one.rfc822_message_id: one for one in manifest.messages}
    lengths = manifest.answer_key.thread_lengths
    families = ("exact_lookup", "semantic_paraphrase", "semantic_lexical_trap", "ranking_stress")
    cases: list[dict[str, object]] = []
    # **Deliberately capped, and the cap is load-bearing.** Every message carries a reference
    # now, so one case per reference would build ten thousand cases for a gate corpus. That is
    # not only slow: at those counts the case file clears the `REGISTERED_N` floor and the
    # hypotheses stop reporting NOT_EVALUABLE and start returning verdicts computed from
    # queries that are sentinel tokens. A self-test that can falsify H1 is a self-test
    # producing evidence about retrieval, which this construction explicitly cannot do. Two
    # cases per family keeps every hypothesis below its floor, which is the honest output.
    per_family = 2
    # The deeper of each conversation's two probe references, never the opener. Still chosen by
    # position rather than by role, so it carries no information about what a message is - but
    # a case whose evidence is always message zero is reached without expanding anything, and
    # the harness tests that exercise the expansion stage then measure nothing.
    candidates = sorted(
        (
            (-by_id[manifest.answer_key.sentinel_owner[token]].position,
             by_id[manifest.answer_key.sentinel_owner[token]].thread_key,
             token,
             manifest.answer_key.sentinel_owner[token])
            for token in manifest.sentinels
            if by_id[manifest.answer_key.sentinel_owner[token]].position > 0
        )
    )
    probe = [(token, owner) for _, _, token, owner in candidates][: per_family * len(families)]
    if not probe:  # pragma: no cover - every profile has multi-message conversations
        raise ValueError("no probe reference sits past a conversation's first message")
    for index, (token, owner) in enumerate(probe):
        message = by_id[owner]
        family = families[index % len(families)]
        thread_len = lengths[message.thread_key]
        cases.append(
            {
                "case_id": f"selftest-{index:02d}",
                "template_id": f"SELFTEST-{family}",
                "family": family,
                "seed": manifest.master_seed,
                "query": token,
                "evidence": [
                    {
                        "ref": f"thread:{message.thread_key}/pos:{message.position}",
                        "rfc_message_id": message.rfc822_message_id,
                        "role": "primary",
                        "quote": _opening(message),
                    }
                ],
                "evidence_cardinality": "single",
                "position": {
                    "thread_len": thread_len,
                    "target_pos": message.position,
                    "fraction": round(message.position / thread_len, 2),
                },
                "expected_behavior": {
                    "must_retrieve": ["primary"],
                    "acceptable_not_found": False,
                    "partiality_expected": True,
                    "notes": (
                        "SELF TEST. The query is the sentinel token, so a lexical exact match "
                        "answers it and a semantic arm has nothing to add. A pass here is "
                        "hollow as evidence about retrieval and is meaningful only as "
                        "evidence that the pipeline executes."
                    ),
                },
                "scoring": {"recall_rule": "the owner's opening line disclosed under its own id"},
            }
        )
    # **One case that drives the ladder past the lexical rungs**, because without it the
    # counting proxy never counts and L6 never runs. The query is a corpus word plus a token
    # that occurs nowhere: the bare-term rungs AND their terms, so L1 matches nothing and the
    # ladder climbs. L1b's relaxation then drops the nonsense conjunct and finds the word
    # lexically, so this is **not** a semantic-only answer and the note below says so - what
    # it is is a case where L5 and L6 both execute and are scored. The F4 shape, where the
    # query and the evidence share no content words, is the campaign's to write.
    # **The deepest message of the longest conversation**, not the first message of the first.
    # A *prose* word from a long conversation, and both halves of that matter.
    #
    # Prose, because a query that is the message's own reference is identifier-shaped: the
    # ladder resolves it at L0 and never reaches the semantic rungs this case exists to
    # execute. That was tried, and `report.rungs` came back as ('L0',).
    #
    # Long, because the case has to land on evidence that is *surfaced and not disclosed* in
    # the first response and carried only by following the response's own affordance. A short
    # conversation discloses the hit immediately and the expansion stage measures nothing.
    #
    # The word is the rarest in its body by document frequency over this corpus, so it reaches
    # the evidence; the nonsense conjunct is what makes L1 fail and the ladder climb.
    def _words(message: SeededMessage) -> list[str]:
        return re.findall(
            r"[A-Za-z]{5,}", re.sub(r"\n-- \n.*$", "", message.body, flags=re.S)
        )

    frequency: dict[str, int] = {}
    for message in manifest.messages:
        for word in set(_words(message)):
            frequency[word] = frequency.get(word, 0) + 1
    # Early in a substantial conversation, carrying a word that occurs nowhere else. Every
    # part of that is load-bearing and every part was arrived at by measuring the alternatives
    # against the harness rather than by reasoning about it:
    #
    #   - a word occurring elsewhere surfaces fifty rows and the recovery driver spends its
    #     budget on thread maps without ever fetching content, so nothing is carried;
    #   - a message deep in a ninety-message conversation is surfaced and never reached either;
    #   - a message at position 1 of a conversation of twenty is surfaced at snippet depth and
    #     *is* carried by following the response's own affordance, which is the stage this case
    #     exists to exercise.
    #
    # If this stops finding such a message the case file should fail loudly rather than quietly
    # produce a case that measures nothing, so it does.
    unique = {
        word for word, count in frequency.items() if count == 1
    }
    ordered = sorted(
        (
            one for one in manifest.messages
            if one.position > 0
            and lengths[one.thread_key] >= 15
            and {word for word in _words(one) if frequency[word] <= 10}
        ),
        key=lambda one: (one.position, -lengths[one.thread_key], one.rfc822_message_id),
    )
    if not ordered:  # pragma: no cover - every shipped profile has such a message
        raise ValueError(
            "no message early in a substantial conversation carries a corpus-unique word, so "
            "no escalation case can be built that is surfaced before it is carried"
        )
    # The caller may name the anchor. Whether a given message is *surfaced and not disclosed*
    # in the first response is a property of the mailbox and the disclosure ceiling, not of the
    # corpus, so the only place it can be established is somewhere that has a mailbox. The
    # default below is a deterministic choice that usually has the shape; the harness fixture
    # probes and passes the one it verified. One construction either way - the choice is
    # injected, the case file is not built twice.
    chosen_escalation = (
        next((one for one in manifest.messages if one.rfc822_message_id == escalation), None)
        if escalation
        else None
    )
    escalating = chosen_escalation or ordered[0]
    # The longest of them: a short unique word is more likely to be a prefix or a subject-line
    # word, and the harness showed one such choice surfacing rows without ever carrying any.
    available = unique.intersection(_words(escalating)) or {
        one for one in _words(escalating) if frequency[one] <= 10
    }
    if not available:  # pragma: no cover - guarded by the selection above
        raise ValueError(f"{escalating.rfc822_message_id} carries no sufficiently rare word")
    rare = min(available, key=lambda one: (frequency[one], -len(one), one))
    cases.append(
        {
            "case_id": "selftest-escalates",
            "template_id": "SELFTEST-escalation",
            "family": "semantic_paraphrase",
            "seed": manifest.master_seed,
            "query": f"{rare} zzqnolexicalmatch",
            "evidence": [
                {
                    "ref": f"thread:{escalating.thread_key}/pos:{escalating.position}",
                    "rfc_message_id": escalating.rfc822_message_id,
                    "role": "primary",
                    "quote": _opening(escalating),
                }
            ],
            "evidence_cardinality": "single",
            "expected_behavior": {
                "must_retrieve": ["primary"],
                "acceptable_not_found": False,
                "partiality_expected": True,
                "notes": (
                    "SELF TEST. The escalation is forced by a nonsense conjunct rather than by "
                    "paraphrase distance, and L1b's relaxation finds the evidence lexically "
                    "anyway - so a pass here says the semantic rungs executed and were "
                    "scored, and says nothing whatever about semantic retrieval."
                ),
            },
            "scoring": {"recall_rule": "the owner's opening line disclosed under its own id"},
        }
    )
    # **One case whose evidence sits mid-way through a short conversation.** The fixed-window
    # baseline only fills a window when the whole conversation fits the disclosure ceiling, so
    # without a case of this shape Baseline F produces no `WindowOffset` row in the whole set
    # and the arm that exists to be compared against is never exercised. Measured, like the
    # escalation case: hits in conversations of twelve to sixteen fill, hits in conversations
    # of twenty-eight do not.
    windowed = sorted(
        (
            one for one in manifest.messages
            if 10 <= lengths[one.thread_key] <= 16
            and 3 <= one.position <= lengths[one.thread_key] - 3
            and {word for word in _words(one) if frequency[word] <= 10}
        ),
        key=lambda one: (lengths[one.thread_key], one.position, one.rfc822_message_id),
    )
    if not windowed:  # pragma: no cover - every shipped profile has such a message
        raise ValueError(
            "no message sits mid-way through a short conversation carrying a corpus-unique "
            "word, so the fixed-window baseline has nothing to fill around"
        )
    chosen_window = (
        next((one for one in manifest.messages if one.rfc822_message_id == window), None)
        if window
        else None
    )
    middle = chosen_window or windowed[0]
    middle_available = unique.intersection(_words(middle)) or {
        one for one in _words(middle) if frequency[one] <= 10
    }
    middle_word = min(
        middle_available, key=lambda one: (frequency[one], -len(one), one)
    )
    cases.append(
        {
            "case_id": "selftest-window",
            "template_id": "SELFTEST-window",
            "family": "ranking_stress",
            "seed": manifest.master_seed,
            "query": middle_word,
            "evidence": [
                {
                    "ref": f"thread:{middle.thread_key}/pos:{middle.position}",
                    "rfc_message_id": middle.rfc822_message_id,
                    "role": "primary",
                    "quote": _opening(middle),
                }
            ],
            "evidence_cardinality": "single",
            "expected_behavior": {
                "must_retrieve": ["primary"],
                "acceptable_not_found": False,
                "partiality_expected": True,
                "notes": (
                    "SELF TEST. Exists so the fixed-window baseline fills a window around a "
                    "hit and its rows can be rendered and checked. The query is a "
                    "corpus-unique word, so a pass says the arm executed and says nothing "
                    "about retrieval."
                ),
            },
            "scoring": {"recall_rule": "the owner's opening line disclosed under its own id"},
        }
    )
    # One unanswerable control, because `outcome_rates` refuses a set without one.
    cases.append(
        {
            "case_id": "selftest-control",
            "template_id": "SELFTEST-control",
            "family": "unanswerable_control",
            "seed": manifest.master_seed,
            "query": "zzzq-no-such-token-anywhere-in-this-corpus",
            "evidence": [],
            "evidence_cardinality": "single",
            "expected_behavior": {
                "must_retrieve": [],
                "acceptable_not_found": True,
                "partiality_expected": False,
                "notes": "SELF TEST. Nothing matches; the only correct answer is a grounded "
                "not-found, and a system that never says not-found passes this by gaming.",
            },
            "scoring": {"recall_rule": "no evidence is required"},
        }
    )
    return CaseFile.model_validate(
        {
            "schema_version": 1,
            "generator_version": manifest.generator_version,
            "master_seed": manifest.master_seed,
            "cases": cases,
        }
    )


__all__ = ["sentinel_case_file"]
