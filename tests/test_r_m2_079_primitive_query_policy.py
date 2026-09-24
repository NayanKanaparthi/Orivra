"""R-M2-079: the primitive floor's query policy, frozen, and its degenerate-strategy guards.

The floor passed the case's question verbatim as Gmail `q`. Under conjunctive matching a
fifteen-word question with its punctuation attached matched nothing - 0 ids on 15 of 15
diagnostic questions - so its 0/13 said nothing about MailWeave's margin over primitives and
EP §7.5's degenerate-strategy guard was not being run.

`pf-q-1` is defined in `primitive.py` before any rerun: the proper nouns of the question when
it has any, otherwise its content words; one query, one page, no reformulation. It is a
deterministic function of the question string. It is not Claude's native Gmail connector and
it is not EP §4.5's Baseline E, and the tests here hold it to what it is.
"""

from __future__ import annotations

import ast
import inspect

import pytest

from mailweave.constants import MAX_BODY_FETCHES_L0, MAX_RERANK_PAIRS
from mailweave.gmail import BackoffPolicy, CallMeter, GmailClient, StaticToken
from mailweave.net.egress import build_client
from mailweave_harness.evaluation import primitive
from mailweave_harness.evaluation.arms import Measured
from mailweave_harness.evaluation.cases import CaseFile, resolve_against
from mailweave_harness.evaluation.primitive import (
    QUERY_POLICY,
    STOPWORDS,
    TIGHT,
    PrimitiveTools,
    QueryPolicy,
    Unqueryable,
)
from mailweave_harness.seed.manifest import Manifest
from mailweave_harness.seed.substrate import InsertedMessage, VerificationReport
from tests.fixtures.eval_dummy import TOKEN
from tests.fixtures.mailbox import Msg, SyntheticMailbox, epoch_ms

# --- the rule, as stated ---------------------------------------------------------------------


def test_the_policy_is_versioned_and_frozen() -> None:
    assert QUERY_POLICY.version == "pf-q-1"
    with pytest.raises(Exception):
        QUERY_POLICY.version = "pf-q-2"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("What notice period does the Lantern agreement carry?", "lantern"),
        ("Who carries contractual liability under the Jarrow agreement?", "jarrow"),
        ("Which of Alder or Rowan holds the Jarrow indemnity?", "alder rowan jarrow"),
        # The first word is capitalised because it starts the sentence, not because it is a name.
        ("Which revision went to signature?", "revision went signature"),
        # A name that is also a stopword by spelling ("I") is not a name.
        ("When did I last see Padstow?", "padstow"),
        # No names: content words, at least three characters, stopwords out, AND-joined.
        ("How far off was the firm we dropped when they checked, was it too big?",
         "far firm dropped checked too big"),
    ],
)
def test_the_rule_on_stated_questions(question: str, expected: str) -> None:
    assert QUERY_POLICY.to_q(question) == expected


def test_punctuation_never_reaches_the_query() -> None:
    q = QUERY_POLICY.to_q("Was it Harlow, or Fenwick? (The latter, I think.)")
    assert q == "harlow fenwick"
    assert not any(char in q for char in ",?().")


def test_a_question_with_nothing_to_select_by_is_refused_rather_than_issued_empty() -> None:
    """The match-everything degenerate strategy: an empty `q` returns the whole mailbox."""
    for question in ("", "   ", "?", "Is it, or is it not?", "The and of a"):
        with pytest.raises(Unqueryable):
            QUERY_POLICY.to_q(question)


def test_the_policy_is_deterministic_and_a_function_of_the_question_alone() -> None:
    """Two calls agree, and the signature admits nothing but the string."""
    question = "What figure was agreed for the Calder budget line?"
    assert QUERY_POLICY.to_q(question) == QueryPolicy().to_q(question)
    assert list(inspect.signature(QueryPolicy.to_q).parameters) == ["self", "question"]


def test_the_policy_module_can_see_neither_the_corpus_nor_the_cases() -> None:
    """No peeking: the module imports nothing from the seed or the case file.

    A policy that could read the corpus could pick the term that finds the answer; a policy
    that could read the case file could read the answer. Held at the import graph, where it
    cannot drift quietly.
    """
    tree = ast.parse(inspect.getsource(primitive))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    corpus_bearing = ("mailweave_harness.seed.corpus", "mailweave_harness.seed.families",
                      "mailweave_harness.seed.manifest", "mailweave_harness.seed.world",
                      "mailweave_harness.seed.situations", "mailweave_harness.seed.voice",
                      "mailweave_harness.seed.chatter", "mailweave_harness.seed.drafts",
                      "mailweave_harness.seed.coverage", "mailweave_harness.seed.lexical",
                      "mailweave.query")
    forbidden = {name for name in imported if name.startswith(corpus_bearing)}
    # `seed.metrics` is the scoring vocabulary (`Disclosure`, `disclosed`) and sees no corpus;
    # `cases` is imported for the `ResolvedCase` type, which carries the query and the
    # evidence ids - the policy takes the query string and never sees the object.
    assert not forbidden, forbidden


def test_the_stopword_list_is_function_words_only() -> None:
    """A stopword list that carried a corpus's content words would be a per-case rewrite in
    disguise. Every entry is short and none is a noun a question would be about."""
    assert STOPWORDS
    assert all(len(word) <= 9 for word in STOPWORDS), sorted(w for w in STOPWORDS if len(w) > 9)
    for suspicious in ("figure", "notice", "period", "date", "agreement", "budget", "recorded",
                       "holding", "carrying", "certification", "throughput", "revision"):
        assert suspicious not in STOPWORDS


# --- the guards that already existed still hold -----------------------------------------


def test_one_page_and_the_two_published_budgets() -> None:
    assert primitive._PAGES == 1
    assert TIGHT.gets == MAX_BODY_FETCHES_L0
    assert primitive.GENEROUS.gets == MAX_RERANK_PAIRS


def test_the_floor_is_labelled_as_a_deterministic_baseline_and_not_as_an_agent() -> None:
    doc = " ".join((primitive.__doc__ or "").split())
    assert "deterministic function of the question" in doc
    assert "Nor is it Claude's native Gmail connector" in doc
    assert "Calling it Baseline E would overstate" in doc


# --- the floor runs the policy, and says what it issued ----------------------------------


def _two_thread_mailbox() -> SyntheticMailbox:
    """One thread about Lantern with the fact deep in it, one about Fenwick as a distractor."""
    rows = []
    for index in range(8):
        rows.append(Msg(
            id=f"l-m{index:03d}", thread_id="l-th", sender="a@team.example",
            subject="Lantern terms" if index == 0 else "Re: Lantern terms",
            body=("The Lantern agreement carries a ninety-day notice period."
                  if index == 5 else f"Lantern housekeeping note {index}, nothing decided."),
            internal_date_ms=epoch_ms(2026, 8, 1) + index * 3_600_000,
            to=("b@team.example",),
            in_reply_to=(f"<l-m{index - 1:03d}@mail.invalid>" if index else None),
        ))
    for index in range(4):
        rows.append(Msg(
            id=f"f-m{index:03d}", thread_id="f-th", sender="c@team.example",
            subject="Fenwick paperwork" if index == 0 else "Re: Fenwick paperwork",
            body=f"Fenwick certification note {index}; the notice period there is thirty days.",
            internal_date_ms=epoch_ms(2026, 8, 2) + index * 3_600_000,
            to=("b@team.example",),
            in_reply_to=(f"<f-m{index - 1:03d}@mail.invalid>" if index else None),
        ))
    return SyntheticMailbox(messages=tuple(rows), now_ms=epoch_ms(2026, 9, 3))


def _resolved(question: str, evidence_id: str, quote: str, manifest_like_ids: list[str]):
    """A one-case file resolved by hand, so the floor is driven the way the runner drives it."""
    from mailweave_harness.evaluation.cases import ResolvedCase

    case_file = CaseFile.model_validate({
        "schema_version": 1, "generator_version": "test", "master_seed": 1,
        "cases": [{
            "case_id": "floor-1", "template_id": "floor-1", "family": "buried_evidence",
            "seed": 1, "query": question,
            "evidence": [{"ref": "thread:l-th/pos:5", "role": "primary", "quote": quote}],
            "evidence_cardinality": "single",
            "expected_behavior": {"must_retrieve": ["primary"], "acceptable_not_found": False,
                                  "notes": "floor positive control"},
            "scoring": {"recall_rule": "single"},
        }],
    })
    return ResolvedCase(case=case_file.cases[0], required={evidence_id: quote},
                        any_of={evidence_id: quote}, distractor_ids=frozenset(),
                        thread_lengths={evidence_id: 8})


def _tools(box: SyntheticMailbox) -> PrimitiveTools:
    return PrimitiveTools(client=GmailClient(
        token=StaticToken(TOKEN), http=build_client(inner=box.transport()),
        meter=CallMeter(), policy=BackoffPolicy(), sleeper=lambda _s: None, jitterer=lambda: 0.5,
    ))


def test_the_floor_reaches_a_named_thing_by_its_name_and_records_the_query_it_issued() -> None:
    """The positive control for the floor: a question about Lantern, at the generous budget,
    puts the Lantern message in hand; and the run says `q` was `lantern`, not the question."""
    quote = "The Lantern agreement carries a ninety-day notice period."
    resolved = _resolved("What notice period does the Lantern agreement carry?", "l-m005", quote, [])
    run = primitive.run_case(_tools(_two_thread_mailbox()), resolved, budget=primitive.GENEROUS)
    assert run.query_issued == "lantern"
    assert run.reach.first_response == frozenset({"l-m005"})
    assert run.state is Measured.MEASURED
    assert "f-m000" not in run.disclosure.content_by_id, "the distractor thread was fetched"


def test_the_verbatim_question_would_have_found_nothing() -> None:
    """The defect this repair is for, kept as a statement of what `q` semantics do."""
    tools = _tools(_two_thread_mailbox())
    assert tools.search("What notice period does the Lantern agreement carry?", limit=25) == ()
    assert tools.search("lantern", limit=25) != ()


def test_an_unqueryable_question_is_the_floor_declining_and_is_labelled_so() -> None:
    resolved = _resolved("Is it, or is it not?", "l-m005", "anything", [])
    run = primitive.run_case(_tools(_two_thread_mailbox()), resolved, budget=TIGHT)
    assert run.state is Measured.FAILED
    assert run.declined is not None and run.declined.startswith("Unqueryable")
    assert run.reach.exceptions == ("primitive-floor: Unqueryable",)
    assert run.reach.stopped == "no_query"
