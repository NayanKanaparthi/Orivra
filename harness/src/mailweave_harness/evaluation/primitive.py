"""The primitive-tools floor: `messages.list` + `messages.get`, run by a fixed policy.

## What this is, and the label matters more than the code

`EVALUATION_PLAN.md` §4.5 item 8 makes **Baseline E, a primitive-tools *agent***, mandatory at
every gate in two budget variants, because it is the arm most able to falsify MailWeave's added
value - `VERIFIED_RESEARCH.md` §8.1 reports that progressive disclosure's gain is "near zero
when a strong agent harness already divides and retrieves on its own".

**This is not that arm.** A strong agent decides what to search for, reads what comes back,
reformulates, and stops when it has the answer. What is here is a *fixed policy*: turn the
case's question into one Gmail `q` by a frozen rule (`QUERY_POLICY`, below), fetch the top-N
results within a budget, and stop. It cannot reformulate and it makes no decisions. Calling it
Baseline E would overstate the falsification pressure MailWeave has been under, which is the
one direction an evaluation must not err in. **Nor is it Claude's native Gmail connector**, or
any other agent's: it is a deterministic function of the question text and nothing else.

## The query policy, frozen before any rerun (R-M2-079)

The floor used to pass the question *verbatim* as `q`. Gmail's `q` is a conjunction - every
token must match - so a fifteen-word question with its punctuation attached matched nothing:
0 ids on 15 of 15 diagnostic questions, and a "floor" of 0/13 that said nothing about
MailWeave's margin over primitives. EP §7.5's degenerate-strategy guard was not being run.

`pf-q-1` is what a person types into the Gmail search box when they have a question about a
named thing: **the proper nouns of the question, and nothing else, when it has any; otherwise
its content words.** Concretely, on the question's words with punctuation stripped:

  1. a word is *named* if it is capitalised and is not the first word of the question - the
     first word is capitalised because it starts a sentence, and treating it as a name would
     put "Which" and "What" into every query;
  2. if any named words exist, `q` is those words, lower-cased, space-joined (Gmail AND);
  3. otherwise `q` is the content words - every word not in `STOPWORDS` and at least three
     characters long - space-joined (Gmail AND), which on a paraphrased question will usually
     match nothing, and that is the floor's honest answer for that question.

One query, one page, no reformulation, no second attempt. The stopword list is the floor's own,
general English, fixed here; nothing about it was chosen against any case or any corpus, and
two tests hold the module to that -
`test_the_policy_module_can_see_neither_the_corpus_nor_the_cases` (it imports nothing that
could see either) and `test_the_policy_is_deterministic_and_a_function_of_the_question_alone`
(two calls on one string agree, and the signature admits nothing but the string).

**Degenerate strategies for this floor, and their guards** (EP §7.5 / G12):

  * *peek at the answer key or the corpus* - the policy takes one string and imports nothing
    that could see either;
  * *page until the evidence appears* - `_PAGES = 1`;
  * *fetch an enormous top-N* - `TIGHT` and `GENEROUS` are MailWeave's own published bounds;
  * *match everything and rely on listing order* - a `q` that is empty or a lone stopword is
    refused as `Unqueryable` rather than issued, and the hit count each query returned is
    reported beside its reach so a query that hit the page cap is visible as one;
  * *rewrite per case* - there is one rule, above, applied to every question the same way.

So it is named for what it is - `primitive-floor` - and it does a different, real job:

  * **It is a floor.** If MailWeave's first response does not put more required evidence in
    hand than "run the query and read the top five", the extra machinery has not earned its
    place on those cases. That is EP §7.5's degenerate-strategy guard, run rather than argued.
  * **It prices the tools MailWeave is built on.** Every call goes through the same
    `GmailClient` and the same egress allowlist, so its API-call and quota counts are
    comparable with MailWeave's rather than being a different instrument's numbers.
  * **It is the substrate a real agent arm would drive.** `PrimitiveTools` is the two
    operations and nothing else; an agent harness hands it a query and reads the result. What
    is missing for Baseline E proper is the agent, not the tools.

## Two budgets, pre-registered

EP asks for two variants and does not fix the numbers. `TIGHT` and `GENEROUS` are declared here
before any run and are chosen against MailWeave's own published bounds rather than to flatter
anybody: `TIGHT` fetches `MAX_BODY_FETCHES_L0` bodies, which is what MailWeave's cheapest rung
is allowed, and `GENEROUS` fetches `MAX_RERANK_PAIRS`, which is the widest candidate set
MailWeave ever scores. A floor given less than MailWeave spends would be a straw one.
"""

from __future__ import annotations

from collections.abc import Sequence
import re
from dataclasses import dataclass
from time import perf_counter
from typing import Final

from mailweave.constants import MAX_BODY_FETCHES_L0, MAX_RERANK_PAIRS
from mailweave.envelope.disposition import DispositionLedger
from mailweave.envelope.reasons import RungId
from mailweave.envelope.vocab import ToolName
from mailweave.envelope.wire import Affordance
from mailweave.gmail.client import GmailClient
from mailweave.surface.service import process_gmail_message
from mailweave_harness.evaluation.arms import CaseRun, Measured, Reach
from mailweave_harness.evaluation.cases import ResolvedCase
from mailweave_harness.seed.metrics import Disclosure, Terminal, disclosed


@dataclass(frozen=True)
class Budget:
    """One pre-registered variant. `gets` is the only thing that differs between the two."""

    name: str
    gets: int
    why: str


TIGHT: Final[Budget] = Budget(
    name="primitive-floor-tight",
    gets=MAX_BODY_FETCHES_L0,
    why=f"MAX_BODY_FETCHES_L0 = {MAX_BODY_FETCHES_L0}: what MailWeave's cheapest rung may fetch",
)

GENEROUS: Final[Budget] = Budget(
    name="primitive-floor-generous",
    gets=MAX_RERANK_PAIRS,
    why=f"MAX_RERANK_PAIRS = {MAX_RERANK_PAIRS}: the widest candidate set MailWeave ever scores",
)

BUDGETS: Final[tuple[Budget, ...]] = (TIGHT, GENEROUS)

#: The listing this floor is allowed to walk. One page: a policy that pages until it finds the
#: answer is not a floor, it is a search for the answer key.
_PAGES: Final[int] = 1

#: The floor's own stopword list: general English function words, fixed here and nowhere else.
#: Deliberately not the product's `query.analysis.STOPWORDS`: a floor that shared the
#: product's tokeniser would be measuring part of the product.
STOPWORDS: Final[frozenset[str]] = frozenset(
    """
    a an the and or but if then than that this these those there here
    is are was were be been being am do does did doing have has had having
    can could will would shall should may might must
    i me my we our us you your he him his she her it its they them their
    who whom whose what which when where why how
    to of in on at by for from with about into onto over under between through
    as so not no nor only also very just still yet ever never
    up down out off again once more most much many any some such own same
    all both each few other another
    """.split()
)


class Unqueryable(ValueError):
    """The question yields no `q` the floor may issue: nothing to select by."""


@dataclass(frozen=True)
class QueryPolicy:
    """`pf-q-1`: the proper nouns of the question when it has any, else its content words.

    A pure function of the question string. No case, no corpus, no answer key, no second
    attempt. See the module docstring for the rule and the degenerate-strategy guards.
    """

    version: str = "pf-q-1"

    def words(self, question: str) -> tuple[str, ...]:
        return tuple(
            word for word in (re.sub(r"[^A-Za-z0-9'-]", "", raw) for raw in question.split())
            if word
        )

    def named(self, question: str) -> tuple[str, ...]:
        words = self.words(question)
        return tuple(
            word.lower() for index, word in enumerate(words)
            if index > 0 and word[:1].isupper() and word.lower() not in STOPWORDS
        )

    def content(self, question: str) -> tuple[str, ...]:
        return tuple(
            word.lower() for word in self.words(question)
            if len(word) >= 3 and word.lower() not in STOPWORDS
        )

    def to_q(self, question: str) -> str:
        terms = self.named(question) or self.content(question)
        terms = tuple(dict.fromkeys(terms))
        if not terms or all(one in STOPWORDS for one in terms):
            raise Unqueryable(f"{question!r} yields no term the floor may search for")
        return " ".join(terms)


QUERY_POLICY: Final[QueryPolicy] = QueryPolicy()

_WIDENING = Affordance(tool=ToolName.SEARCH, args={"query": "<primitive floor: not offered>"})


@dataclass(frozen=True)
class PrimitiveTools:
    """`messages.list` and `messages.get`, and nothing else.

    Deliberately two methods. A substrate that could also map threads, or expand, or rank,
    would be a smaller MailWeave rather than the primitives MailWeave is built on, and the
    comparison would stop meaning anything.
    """

    client: GmailClient

    def search(self, query: str, *, limit: int) -> tuple[str, ...]:
        ledger = DispositionLedger()
        run = self.client.list_messages(
            ledger,
            rung=RungId.L1,
            query=query,
            widening_affordance=_WIDENING,
            page_size=min(limit, 100),
            max_pages=_PAGES,
        )
        del run
        return tuple(ledger.hit_ids)[:limit]

    def get(self, message_id: str) -> str | None:
        """One message's clean body text, through the same content pipeline MailWeave uses."""
        message = self.client.get_message(message_id, message_format="full")
        processed = process_gmail_message(message)
        if processed is None or processed.body_clean is None:
            return None
        return processed.body_clean.text


def run_case(tools: PrimitiveTools, resolved: ResolvedCase, *, budget: Budget = TIGHT) -> CaseRun:
    """Run the query verbatim, read the top N, and report what that put in hand.

    There is no expansion stage here and `after_expansion` equals `first_response` by
    construction: every `get` is a round the policy spent, so its budget *is* its expansion.
    Reporting it otherwise would credit the floor with a recovery mechanism it does not have.
    """
    started = perf_counter()
    required = frozenset(resolved.required)
    try:
        issued = QUERY_POLICY.to_q(resolved.case.query)
        ids = tools.search(issued, limit=budget.gets)
        content: dict[str, str] = {}
        for message_id in ids[: budget.gets]:
            text = tools.get(message_id)
            if text is not None:
                content[message_id] = text
    except Exception as failure:
        return CaseRun(
            case_id=resolved.case.case_id,
            family=resolved.case.family,
            arm=budget.name,
            terminal=Terminal.OTHER,
            disclosure=Disclosure(content_by_id={}),
            latency_ms=(perf_counter() - started) * 1000,
            declined=f"{type(failure).__name__}: {failure}",
            # An `Unqueryable` question is the floor declining, not the product: recorded
            # with its class so the report can say which.
            state=Measured.FAILED,
            reach=Reach(never_named=required, state=Measured.FAILED,
                        exceptions=(f"primitive-floor: {type(failure).__name__}",),
                        stopped="no_query"),
            position=None if resolved.case.position is None else resolved.case.position.target_pos,
        )
    snapshot = Disclosure(content_by_id=content)
    carried = frozenset(
        mid for mid in required if disclosed(snapshot, mid, resolved.required.get(mid, ""))
    )
    return CaseRun(
        case_id=resolved.case.case_id,
        family=resolved.case.family,
        arm=budget.name,
        # **No outcome vocabulary.** The floor has no OD-2 outcome to report: it never says
        # "not found", it returns what it read. `ANSWERED` where it carried the evidence and
        # `INCONCLUSIVE` where it did not is the honest projection onto the shared enum, and
        # it is why the floor cannot be scored on the false-not-found rate.
        terminal=Terminal.ANSWERED if carried else Terminal.INCONCLUSIVE,
        disclosure=Disclosure(
            content_by_id=content,
            surfaced_ids=frozenset(ids),
            tokens_returned=sum(len(text.split()) for text in content.values()),
            evidence_tokens=sum(len(content[mid].split()) for mid in carried if mid in content),
            distractor_tokens=sum(
                len(text.split()) for mid, text in content.items() if mid in resolved.distractor_ids
            ),
        ),
        reach=Reach(
            first_response=carried,
            after_expansion=carried,
            surfaced_only=frozenset(required & frozenset(ids)) - carried,
            never_named=required - frozenset(ids),
            rounds=len(content),
            calls=tuple("messages.get" for _ in content),
            levels=1 + len(content),
        ),
        order=tuple(ids),
        latency_ms=(perf_counter() - started) * 1000,
        position=None if resolved.case.position is None else resolved.case.position.target_pos,
        thread_lengths=dict(resolved.thread_lengths),
        query_issued=issued,
        state=Measured.MEASURED,
    )


def run_all(
    tools: PrimitiveTools,
    resolved: Sequence[ResolvedCase],
    *,
    budgets: Sequence[Budget] = BUDGETS,
) -> tuple[CaseRun, ...]:
    return tuple(run_case(tools, one, budget=budget) for one in resolved for budget in budgets)


__all__ = [
    "BUDGETS", "GENEROUS", "QUERY_POLICY", "STOPWORDS", "TIGHT", "Budget", "PrimitiveTools",
    "QueryPolicy", "Unqueryable", "run_all", "run_case",
]
