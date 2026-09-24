"""A *situation* is one matter with one true answer, rendered four ways.

The generator used to hold six scenarios and reuse them across dozens of threads, so twelve
threads carried nine facts between them and sibling threads disagreed about the same question
(R-M2-051). A situation here is minted per thread from a topic and an entity, and
`mint_situations` refuses to hand out the same pair twice.

The four renderings are the whole reason this module exists, and each one is required by a
registered family:

- `formal_true` is the evidence. It contains the answer.
- `plain_question` is what a case author turns into the query. It contains **no** answer value
  and, by assertion, **no content word** that `formal_true` also contains (EP §4.5 T2).
- `plain_decoy` is written in the query's own register and says something **false**. A query
  built from `plain_question` matches it lexically and matches the evidence not at all, which
  is F4's falsifier and, with the confident framing, F11's trap.
- `formal_near_miss` shares the evidence's vocabulary and is also false. It is the same-thread
  lexical decoy EP §4.3 requires of every F3 case.

`check_situation` measures those properties rather than asserting them in a comment, and
`mint_situations` runs it on every situation it returns. That measurement is a **construction
check**: it says what the generated text is, and it says nothing whatever about whether any
retrieval system finds it. The corpus is never adjusted against MailWeave's output.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from random import Random
from typing import Final

from .world import BY_ENTITY, ENTITIES, EPOCH, Entity, jaccard, states

VALUE_KINDS: Final[frozenset[str]] = frozenset(
    {"days", "index", "date", "measure", "rate", "site", "supplier", "person"}
)

#: Kinds that read as a figure. F16's revisions say "the figure stands at X", and a corpus that
#: filled that with a place name was reported as semantically incoherent by a reader who could
#: not tell whether it was a bug or the point.
NUMERIC_KINDS: Final[frozenset[str]] = frozenset({"days", "index", "measure", "rate"})


@dataclass(frozen=True)
class Situation:
    """One matter, its answer, and the four renderings the families draw on."""

    key: str
    topic: str
    entity: str
    answer: str
    wrong: str
    older: str
    formal_true: str
    plain_question: str
    plain_decoy: str
    formal_near_miss: str
    reason: str
    subject: str
    value_kind: str

    @property
    def formal_older(self) -> str:
        """The evidence sentence carrying the superseded value.

        Both slots move. A template that names a current value *and* a prior one - "revised
        upward to {answer}, from {older}" - produced "revised upward to 40, from 40" when only
        the first was substituted, which an audit reported as a null revision.
        """
        return self.formal_true.replace(self.answer, self.older).replace(
            f"from {self.older}", f"from {self.wrong}"
        )

    @property
    def formal_wrong(self) -> str:
        return self.formal_true.replace(self.answer, self.wrong)


@dataclass(frozen=True)
class Topic:
    """A shape a fact can take, in both registers. One of EP §4.3's twelve F3 templates."""

    key: str
    value_kind: str
    subject: str
    """A bank of phrasings separated by `|`. A subject is drawn from it per thread.

    Subjects used to carry a family's name in a suffix - " - the decision", " - costing",
    " - invoice", " - revisions" - and an audit reported twenty-two of fifty-one threads
    identified by subject line alone, with F7's cross-thread retrieval solved by reading two of
    them. A bank lets sibling conversations differ without either of them saying what it is."""
    formal: str
    question: str
    decoy: str
    near_miss: str
    reason: str


#: Twelve topics, which are EP §4.4's "12 templates". Each renders in both registers; the
#: import-time check below proves each pair is disjoint before any corpus is generated.
TOPICS: Final[tuple[Topic, ...]] = (
    Topic(
        "notice_period", "days",
        "{formal} agreement - termination terms|{formal}: notice and exit|Terms review: {formal}|{formal} contract wording",
        "Contractual termination notice under the {formal} agreement stands at {answer} "
        "calendar days. The amendment was executed at the last renewal.",
        "How much warning do we owe {plain} before we walk away from them?",
        "We only have to give {plain} {wrong} days of warning before we walk away.",
        "Contractual termination notice under the {formal} agreement stands at {wrong} "
        "calendar days. The amendment was executed at the last renewal.",
        "The renewal round pulled the clause forward because the previous term left us "
        "exposed over a quarter end.",
    ),
    Topic(
        "inspection_site", "site",
        "{formal} - where inspection happens|Inspection arrangements: {formal}|{formal} site question|Where we check {formal}",
        "{formal} inspection is relocated to the designated {answer} facility with immediate "
        "contractual effect.",
        "Where do we look over {plain} now that it moved somewhere else?",
        "They look over {plain} at {wrong}.",
        "{formal} inspection is relocated to the designated {wrong} facility with immediate "
        "contractual effect.",
        "The previous floor could not hold the quantities once the range grew.",
    ),
    Topic(
        "budget_line", "index",
        "{formal} expenditure allocation|Budget line: {formal}|{formal} spend|Allocation for {formal}",
        "The {formal} expenditure allocation is restated at {answer}, against {older} at "
        "the prior approval.",
        "How much more money are we spending on {plain} this time round?",
        "Spending on {plain} came out at {wrong} in the end.",
        "The {formal} expenditure allocation is restated at {wrong}, against {older} at "
        "the prior approval.",
        "Work at one location had to be redone, and the redo was not in the prior approval.",
    ),
    Topic(
        "certification", "date",
        "{formal} certification status|Certificates: {formal}|{formal} paperwork|Compliance record for {formal}",
        "{formal} certification carries the reissue date {answer}; compliance runs from "
        "that date.",
        "When did the paperwork for {plain} get sorted out again?",
        "The paperwork for {plain} got sorted back on {wrong}.",
        "{formal} certification carries the reissue date {wrong}; compliance runs from "
        "that date.",
        "The lapse was clerical: the renewal sat unactioned while the owner was away.",
    ),
    Topic(
        "tolerance", "measure",
        "{formal} - measured tolerance|Readings on {formal}|{formal} measurement query|Tolerance check: {formal}",
        "Measured tolerance on {formal} exceeded specification at {answer} against the "
        "stated threshold.",
        "How far off was {plain} when they checked, was it too big?",
        "{plain} came out at {wrong} when they checked.",
        "Measured tolerance on {formal} exceeded specification at {wrong} against the stated "
        "threshold.",
        "The tooling drifted after the line was moved and nobody re-zeroed it.",
    ),
    Topic(
        "delivery_window", "date",
        "{formal} consignment scheduling|Dispatch dates: {formal}|{formal} delivery|Scheduling {formal}",
        "The {formal} consignment is scheduled for dispatch on {answer} within the agreed "
        "delivery window.",
        "When do the boxes for {plain} actually turn up?",
        "Boxes for {plain} turn up on {wrong}.",
        "The {formal} consignment is scheduled for dispatch on {wrong} within the agreed "
        "delivery window.",
        "The window moved once the carrier lost a slot at the port.",
    ),
    Topic(
        "liability", "supplier",
        "{formal} - indemnity position|Who carries {formal}|Indemnity: {formal}|{formal} liability wording",
        "The indemnity clause was amended so that {answer} carries contractual liability "
        "under the {formal} agreement.",
        "If something goes wrong with {plain}, who actually pays for it?",
        "If {plain} goes wrong it is {wrong} who pays.",
        "The indemnity clause was amended so that {wrong} carries contractual liability "
        "under the {formal} agreement.",
        "Insurers refused to price the old split after the second claim.",
    ),
    Topic(
        "throughput", "rate",
        "{formal} - rated throughput|Capacity on {formal}|{formal} line rate|Throughput question: {formal}",
        "{formal} throughput is constrained at {answer} units against rated capacity.",
        "How many of {plain} can we squeeze through in a day?",
        "We can push {wrong} of {plain} through in a day.",
        "{formal} throughput is constrained at {wrong} units against rated capacity.",
        "One of the two lines is down for a rebuild until the quarter turns.",
    ),
    Topic(
        "defect_cause", "site",
        "{formal} - defect attribution|What went wrong on {formal}|{formal} failure review|Attribution: {formal}",
        "The defect on {formal} is attributable to the {answer} plant; root cause was "
        "determined at the review.",
        "Why did {plain} break, where did it trace back to?",
        "{plain} broke because of {wrong}.",
        "The defect on {formal} is attributable to the {wrong} plant; root cause was "
        "determined at the review.",
        "A batch of seals from a single shift failed the same way.",
    ),
    Topic(
        "approval", "person",
        "{formal} - escalation authority|Sign-off on {formal}|Who approves {formal}|Delegation: {formal}",
        "Escalation approval under the {formal} agreement is authorised by {answer} as "
        "countersigning signatory.",
        "Who is the one that says yes on {plain} these days?",
        "You ask {wrong} about {plain}.",
        "Escalation approval under the {formal} agreement is authorised by {wrong} as "
        "countersigning signatory.",
        "The previous signatory moved teams and the delegation was never updated.",
    ),
    Topic(
        "storage_move", "site",
        "{formal} - storage arrangements|Where {formal} is kept|Storage: {formal}|{formal} warehousing",
        "{formal} stock is relocated to the {answer} facility under the revised storage "
        "schedule.",
        "Where are they keeping {plain} now?",
        "They keep {plain} at {wrong}.",
        "{formal} stock is relocated to the {wrong} facility under the revised storage "
        "schedule.",
        "The lease on the old unit ended and was not renewed.",
    ),
    Topic(
        "handover", "date",
        "{formal} - handover completion|Handover of {formal}|{formal} transition|Completing {formal}",
        "Contractual handover of {formal} is recorded against {answer} on the executed "
        "schedule.",
        "When did they finish giving {plain} over to us?",
        "They finished giving {plain} over on {wrong}.",
        "Contractual handover of {formal} is recorded against {wrong} on the executed "
        "schedule.",
        "The second stage slipped when the inventory count did not reconcile.",
    ),
)

BY_TOPIC: Final[dict[str, Topic]] = {one.key: one for one in TOPICS}


def _mint_value(kind: str, rng: Random, taken: set[str]) -> str:
    """One value of the right kind, distinct from everything already handed out for this
    situation. Values collide across situations by design - two threads may both say 63 days
    about different agreements - but never inside one, or `formal_older` would be the answer."""
    for _ in range(400):
        if kind == "days":
            value = f"{rng.randrange(11, 121)}"
        elif kind == "index":
            value = f"{rng.randrange(11, 99)}"
        elif kind == "rate":
            value = f"{rng.randrange(120, 960)}"
        elif kind == "measure":
            value = f"{rng.randrange(2, 98)}.{rng.randrange(0, 9)}mm"
        elif kind == "date":
            value = (EPOCH + dt.timedelta(days=rng.randrange(10, 620))).strftime("%d %B %Y")
        elif kind in {"site", "supplier"}:
            pool = [e for e in ENTITIES if e.kind == kind]
            value = pool[rng.randrange(len(pool))].formal
        elif kind == "person":
            from .world import PEOPLE

            value = PEOPLE[rng.randrange(len(PEOPLE))].display
        else:  # pragma: no cover - guarded by VALUE_KINDS
            raise ValueError(f"unknown value kind {kind!r}")
        # Containment, not equality. The values are substituted into prose and the checks
        # ask whether the answer *appears* in a decoy, so "11" drawn against a taken "113"
        # would make every decoy read as stating the answer. `mint_situations` found this on
        # the first seed that drew one.
        # Word-boundary aware. Raw containment rejected every date once a thread's answer was
        # a two-digit number, because "20" occurs inside "2026".
        if not any(states(value, other) or states(other, value) for other in taken):
            taken.add(value)
            return value
    raise RuntimeError(  # pragma: no cover - 200 draws from these ranges cannot all collide
        f"could not mint a distinct {kind} value"
    )


def build(topic: Topic, entity: Entity, rng: Random) -> Situation:
    # The subject entity's own names are barred from the value pool. Without this a
    # liability situation about Alder could name Alder as the liable party, so the evidence
    # sentence and its near-miss would both contain the answer string and selecting the
    # decoy would not be an error - which `check_situation` caught on the first run.
    taken: set[str] = {entity.formal, entity.plain}
    answer = _mint_value(topic.value_kind, rng, taken)
    wrong = _mint_value(topic.value_kind, rng, taken)
    older = _mint_value(topic.value_kind, rng, taken)
    taken.discard(entity.formal)
    taken.discard(entity.plain)
    fields = {
        "formal": entity.formal,
        "plain": entity.plain,
        "answer": answer,
        "wrong": wrong,
        "older": older,
    }
    return Situation(
        key=f"{topic.key}::{entity.key}",
        topic=topic.key,
        entity=entity.key,
        answer=answer,
        wrong=wrong,
        older=older,
        formal_true=topic.formal.format(**fields),
        plain_question=topic.question.format(**fields),
        plain_decoy=topic.decoy.format(**fields),
        formal_near_miss=topic.near_miss.format(**fields),
        reason=topic.reason,
        subject=topic.subject.split("|")[rng.randrange(len(topic.subject.split("|")))].format(
            **fields
        ),
        value_kind=topic.value_kind,
    )


def mint_values(kind: str, rng: Random, count: int, avoid: tuple[str, ...] = ()) -> tuple[str, ...]:
    """`count` values of one kind, none of which contains or is contained by another.

    F16 needs five revisions of one figure that are pairwise distinguishable. Building that
    list by hand produced duplicates, and a duplicate revision means a *distractor* carrying
    the adopted value, which the coverage rule reported as a distractor that is not wrong.
    """
    taken = set(avoid)
    return tuple(_mint_value(kind, rng, taken) for _ in range(count))


@dataclass(frozen=True)
class SituationDefect:
    situation: str
    rule: str
    detail: str


def check_situation(one: Situation) -> tuple[SituationDefect, ...]:
    """Measured properties of the four renderings. A construction check, nothing more.

    Each rule exists because a family breaks without it, and each is stated so that it can
    fail: `tests/test_situations.py` feeds this a deliberately broken situation per rule.
    """
    found: list[SituationDefect] = []
    overlap = jaccard(one.formal_true, one.plain_question)
    if overlap > 0.0:
        from .world import content_words

        shared = sorted(content_words(one.formal_true) & content_words(one.plain_question))
        found.append(
            SituationDefect(
                one.key, "T2_disjoint",
                f"evidence and question share {shared} (jaccard {overlap:.2f}); EP §4.5 tier 2 "
                "requires zero content-word overlap, so a query written from this question "
                "would be a lexical hit on its own evidence",
            )
        )
    if jaccard(one.plain_decoy, one.plain_question) <= 0.0:
        found.append(
            SituationDefect(
                one.key, "decoy_is_a_trap",
                "the decoy shares no content word with the question, so a lexical query would "
                "not reach it and the family tests nothing",
            )
        )
    if states(one.answer, one.plain_question):
        found.append(
            SituationDefect(
                one.key, "question_withholds_the_answer",
                f"the question contains the answer {one.answer!r}",
            )
        )
    if states(one.answer, one.plain_decoy) or states(one.answer, one.formal_near_miss):
        found.append(
            SituationDefect(
                one.key, "decoys_are_wrong",
                f"a decoy states the true answer {one.answer!r}, so selecting it is not an error",
            )
        )
    if len({one.answer, one.wrong, one.older}) != 3:
        found.append(
            SituationDefect(one.key, "values_are_distinct", "answer, wrong and older collide")
        )
    if not states(one.answer, one.formal_true):
        found.append(
            SituationDefect(one.key, "evidence_carries_the_answer", "evidence omits the answer")
        )
    if one.formal_older == one.formal_true:
        found.append(
            SituationDefect(
                one.key, "older_differs_in_one_detail",
                "the superseded rendering is identical to the evidence, so F16's near-duplicates "
                "would be duplicates",
            )
        )
    return tuple(found)


def mint_situations(rng: Random, count: int) -> tuple[Situation, ...]:
    """`count` distinct situations, every one of which passes `check_situation`.

    Pairs are drawn topic-major so that a small sample still spans all twelve topics rather
    than exhausting one of them.
    """
    pairs = [(topic, entity) for entity in ENTITIES for topic in TOPICS]
    if count > len(pairs):
        raise ValueError(
            f"asked for {count} situations from {len(pairs)} topic/entity pairs. Reusing a "
            "pair would put the same fact in two threads, which is R-M2-051"
        )
    # Balanced by topic rather than drawn uniformly. F3 needs seven situations of *each* of the
    # twelve topics, and a uniform draw of 120 from 384 pairs leaves some topic short of seven
    # often enough that the small profile failed to build at all on the second seed tried.
    grouped: dict[str, list[tuple[Topic, Entity]]] = {}
    for pair in pairs:
        grouped.setdefault(pair[0].key, []).append(pair)
    for group in grouped.values():
        rng.shuffle(group)
    order: list[tuple[Topic, Entity]] = []
    for depth in range(max(len(group) for group in grouped.values())):
        for key in sorted(grouped):
            if depth < len(grouped[key]):
                order.append(grouped[key][depth])
    out: list[Situation] = []
    for topic, entity in order:
        one = build(topic, entity, rng)
        defects = check_situation(one)
        if defects:
            raise AssertionError(
                "a minted situation failed its own construction check, which means the topic "
                f"template is wrong rather than the draw: {defects[0].rule} - {defects[0].detail}"
            )
        out.append(one)
        if len(out) == count:
            break
    return tuple(out)


def check_topic(topic: Topic) -> tuple[SituationDefect, ...]:
    """Structural properties of a template, independent of any draw.

    The rule that matters: a template must name its subject. `defect_cause` did not, so two
    situations about different entities rendered the *same* evidence sentence whenever their
    answers collided, and two sweep threads carried one sentence between them. The coverage
    rule found it at the gate size; this makes it impossible to reintroduce.
    """
    found: list[SituationDefect] = []
    if "|" not in topic.subject:
        found.append(SituationDefect(
            topic.key, "subject_has_a_bank",
            "the topic offers one subject phrasing, so sibling conversations about one matter "
            "must differ by a suffix, and a suffix that distinguishes them names what they are",
        ))
    if "{formal}" not in topic.formal:
        found.append(SituationDefect(
            topic.key, "evidence_names_its_subject",
            "the evidence template never names the entity, so two situations on different "
            "entities render the same sentence whenever their values collide",
        ))
    if "{plain}" not in topic.question:
        found.append(SituationDefect(
            topic.key, "question_names_its_subject",
            "the question template never names the entity colloquially, so the query cannot "
            "identify what it is asking about",
        ))
    if "{answer}" not in topic.formal:
        found.append(SituationDefect(
            topic.key, "evidence_carries_a_value", "the evidence template carries no value"))
    return tuple(found)


def audit_topics() -> tuple[SituationDefect, ...]:
    """Every topic, rendered against every entity, checked. Run at import and by a test."""
    rng = Random(0)
    found: list[SituationDefect] = []
    for topic in TOPICS:
        found.extend(check_topic(topic))
        for entity in ENTITIES:
            found.extend(check_situation(build(topic, entity, rng)))
    return tuple(found)


_defects = audit_topics()
if _defects:  # pragma: no cover - import-time guard
    raise AssertionError(
        f"{len(_defects)} topic rendering(s) fail their construction check; first: "
        f"{_defects[0].situation} {_defects[0].rule} - {_defects[0].detail}"
    )

__all__ = [
    "BY_TOPIC", "TOPICS", "VALUE_KINDS", "Situation", "SituationDefect", "Topic",
    "NUMERIC_KINDS", "audit_topics", "build", "check_situation", "check_topic",
    "mint_situations",
    "mint_values",
]
