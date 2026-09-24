"""The case-file interface, from `EVALUATION_PLAN.md` §4.1 rather than invented here.

**Why this exists and what it deliberately does not contain.** `mailweave_harness.seed` builds
the corpus and states, in its own docstring, that the F1-F29 case content is *not* there and
that each milestone adds the families it needs - M2 the Gmail families. This is that interface:
the shape of a case file, the join that turns a case's evidence references into the Gmail ids a
response can be scored against, and the refusals that stop a mis-specified case from producing
a number. It holds **no queries and no answers**. Those are the campaign's, and an implementer
writing them would be writing the exam it is sitting; this file is written so that they can be
handed over as data.

**The schema is EP §4.1's, field for field.** Where a field was optional in the plan's example
it is optional here; where the plan states a field is required - `expected_behavior.notes`, which
"states what would make a pass hollow" - it is required here and non-empty. The one addition is
`ref` parsing: the plan writes evidence references as `thread:A07/pos:37` and joins `gmail_id`
"from the seed manifest at seeding time", so `EvidenceRef.parse` and `resolve_against` are that
sentence made executable instead of left to each caller.

**Two joins, in order, each refusing rather than guessing.** A `ref` resolves against a
`Manifest` to one `SeededMessage` and therefore to one `rfc822_message_id`; that id resolves
against a `VerificationReport` to the `gmail_id` the mailbox assigned. A case whose ref names no
seeded message, or whose declared `rfc_message_id` disagrees with the one the manifest holds at
that position, is refused at load - because a recall metric scored through a bad join scores a
retrieval that never happened, and nothing downstream can see it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Final, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mailweave_harness.seed.manifest import Manifest, SeededMessage

if TYPE_CHECKING:  # the mailbox half of the join only. A case author validating against a
    # manifest needs this module and `manifest.py` and nothing else, which is what makes the
    # authoring kit the real files rather than a copy of them.
    from mailweave_harness.seed.substrate import VerificationReport

#: EP §4.3 and §4.7's families, by the `family` string a case file carries. Closed, because a
#: family this harness does not know is a family whose bars nobody registered - and a case set
#: that silently contributed to an aggregate under an unknown name is the way a hypothesis gets
#: answered by cases it was never about.
FAMILIES: Final[frozenset[str]] = frozenset(
    {
        "exact_lookup",  # F1
        "sender_date",  # F2
        "buried_evidence",  # F3
        "semantic_paraphrase",  # F4
        "decision_evolution",  # F5
        "participant_reasoning",  # F6
        "multi_thread",  # F7
        "attachment",  # F8
        "unanswerable_control",  # F10
        "semantic_lexical_trap",  # F11
        "semantic_negative_control",  # F12
        "temporal_structural",  # F13
        "participant_graph",  # F14
        "thread_structure_reality",  # F15
        "ranking_stress",  # F16
        "decision_reversal",  # F17
    }
)

#: The family each `F<n>` label names, so a report can print the plan's own label beside the
#: string a case file carries and a reader does not have to hold the mapping in their head.
FAMILY_LABELS: Final[Mapping[str, str]] = {
    "exact_lookup": "F1",
    "sender_date": "F2",
    "buried_evidence": "F3",
    "semantic_paraphrase": "F4",
    "decision_evolution": "F5",
    "participant_reasoning": "F6",
    "multi_thread": "F7",
    "attachment": "F8",
    "unanswerable_control": "F10",
    "semantic_lexical_trap": "F11",
    "semantic_negative_control": "F12",
    "temporal_structural": "F13",
    "participant_graph": "F14",
    "thread_structure_reality": "F15",
    "ranking_stress": "F16",
    "decision_reversal": "F17",
}

#: EP §4.6's distractor taxonomy. Closed for the reason `FAMILIES` is: "returned distractor
#: tokens" is exactly computable only because the manifest names them, and a type nobody
#: registered cannot be reported against.
DISTRACTOR_TYPES: Final[frozenset[str]] = frozenset(
    {
        "lexical_decoy",
        "same_thread_near_miss",
        "cross_thread_decoy",
        "participant_decoy",
        "temporal_decoy",
    }
)

#: EP §4.4's position sweep. The **fractions** are normative, not the indices - §4.4 says so
#: explicitly, against the S6 fallback where the conversation ceiling is below 100.
SWEEP_POSITIONS: Final[tuple[int, ...]] = (2, 7, 20, 37, 51, 83, 99)

#: The per-family case counts `EVALUATION_PLAN.md` §4.3 and §4.7 register, per seed. They are
#: here because a clause answered by fewer cases than the plan asked for is a clause answered
#: by a corpus nobody registered - and because taking them from the plan rather than choosing
#: them means the floor cannot be lowered after seeing a result. F3's figure is the sweep's:
#: 12 templates at 7 positions.
REGISTERED_N: Final[Mapping[str, int]] = {
    "exact_lookup": 10,
    "sender_date": 10,
    "buried_evidence": 84,
    "semantic_paraphrase": 12,
    "decision_evolution": 8,
    "participant_reasoning": 8,
    "multi_thread": 6,
    "attachment": 6,
    "unanswerable_control": 10,
    "semantic_lexical_trap": 10,
    "semantic_negative_control": 10,
    "temporal_structural": 8,
    "participant_graph": 8,
    "thread_structure_reality": 8,
    "ranking_stress": 8,
    "decision_reversal": 8,
}

_REF = re.compile(r"^thread:(?P<thread>[^/]+)/pos:(?P<position>\d+)$")


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RefUnresolvable(ValueError):
    """A case names a message the corpus does not hold, or holds differently."""


class EvidenceRef(Frozen):
    """`thread:A07/pos:37` - the portable name EP §4.1 writes evidence references in.

    Portable because it survives regeneration: a `master_seed` change re-randomises names,
    dates and message ids while the *shape* - thread count, lengths, position grid - is drawn
    from a generator seeded without it. A case pinned to an rfc822 id would have to be rewritten
    for every seed; a case pinned to a position does not, which is EP §5.3's anti-gaming lever
    working as designed rather than as a slogan.
    """

    thread_key: str = Field(min_length=1, max_length=64)
    position: int = Field(ge=0)

    @classmethod
    def parse(cls, raw: str) -> EvidenceRef:
        match = _REF.match(raw.strip())
        if match is None:
            raise RefUnresolvable(
                f"{raw!r} is not an evidence reference. EP §4.1 writes them "
                "`thread:<thread_key>/pos:<n>`"
            )
        return cls(thread_key=match["thread"], position=int(match["position"]))

    def render(self) -> str:
        return f"thread:{self.thread_key}/pos:{self.position}"


class Evidence(Frozen):
    """One required or acceptable piece of evidence, and the quote that counts as disclosing it.

    `quote` is what `seed.metrics.disclosed` joins on, whitespace-normalised: a response that
    re-wrapped a line still disclosed it, one that dropped a word did not. It is required here
    even though EP §4.1's example could be read as allowing it to be absent, because a case with
    no quote can only be scored by "the id appeared", and an id appearing is what
    `surfaced_not_disclosed` exists to report *separately* from recall.
    """

    ref: str = Field(min_length=1)
    rfc_message_id: str | None = Field(default=None, max_length=400)
    role: str = Field(default="primary", min_length=1, max_length=32)
    quote: str = Field(min_length=1)
    answer_field: Mapping[str, str] = Field(default_factory=dict)

    @property
    def reference(self) -> EvidenceRef:
        return EvidenceRef.parse(self.ref)


class Distractor(Frozen):
    ref: str = Field(min_length=1)
    type: str
    note: str = ""

    @model_validator(mode="after")
    def _the_type_is_one_the_taxonomy_names(self) -> Self:
        if self.type not in DISTRACTOR_TYPES:
            raise ValueError(
                f"distractor type {self.type!r} is not in EP §4.6's taxonomy "
                f"({sorted(DISTRACTOR_TYPES)}); an unregistered type cannot be reported against"
            )
        EvidenceRef.parse(self.ref)
        return self


class Position(Frozen):
    thread_len: int = Field(gt=0)
    target_pos: int = Field(ge=0)
    fraction: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _the_fraction_describes_the_position(self) -> Self:
        if not 0 <= self.target_pos < self.thread_len:
            raise ValueError(
                f"target_pos {self.target_pos} is outside a thread of {self.thread_len}"
            )
        stated = self.target_pos / self.thread_len
        if abs(stated - self.fraction) > 0.02:
            raise ValueError(
                f"fraction {self.fraction} does not describe position {self.target_pos} of "
                f"{self.thread_len} ({stated:.2f}). §4.4 makes the fraction normative, so the "
                "two disagreeing means the sweep would be reported at a depth nobody ran"
            )
        return self


class Paraphrase(Frozen):
    tier: int = Field(ge=0, le=3)
    content_word_jaccard: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _the_tier_and_the_overlap_agree(self) -> Self:
        """EP §4.5 defines the tiers by measured overlap, so a tier that contradicts its own
        jaccard is a case that would be reported at a paraphrase distance it does not have."""
        if self.tier == 0 and self.content_word_jaccard < 1.0:
            raise ValueError("T0 is an exact phrase; its content-word jaccard is 1.0")
        if self.tier == 2 and self.content_word_jaccard > 0.0:
            raise ValueError(
                f"T2 is zero content-word overlap (§4.5) and this case measures "
                f"{self.content_word_jaccard}"
            )
        return self


class ExpectedBehavior(Frozen):
    must_retrieve: tuple[str, ...] = ()
    acceptable_not_found: bool = False
    partiality_expected: bool = True
    notes: str = Field(min_length=1)
    """**Required, per EP §4.1.** It states what would make a pass hollow, and the gate
    reviewer reads it. A case that cannot say what a hollow pass looks like has not been
    thought about hard enough to contribute to a hypothesis."""


class Scoring(Frozen):
    recall_rule: str = Field(min_length=1)
    answer_rule: str = ""


class Case(Frozen):
    """One case instance. EP §4.1's object, with its refusals attached."""

    case_id: str = Field(min_length=1, max_length=128)
    template_id: str = Field(min_length=1, max_length=64)
    family: str
    seed: int = Field(ge=0)
    query: str = Field(min_length=1)
    query_variants: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    evidence_cardinality: str = "single"
    distractors: tuple[Distractor, ...] = ()
    position: Position | None = None
    paraphrase: Paraphrase | None = None
    expected_behavior: ExpectedBehavior
    scoring: Scoring

    @model_validator(mode="after")
    def _the_case_can_be_scored(self) -> Self:
        if self.family not in FAMILIES:
            raise ValueError(
                f"family {self.family!r} is not one this harness knows ({sorted(FAMILIES)}); "
                "a case contributing to an aggregate under an unknown family is a hypothesis "
                "answered by cases it was never about"
            )
        if self.evidence_cardinality not in {"single", "all_of", "any_of"}:
            raise ValueError(
                f"evidence_cardinality {self.evidence_cardinality!r} is not one of "
                "single | all_of | any_of (EP §4.1)"
            )
        answerable = self.family != "unanswerable_control"
        if answerable and not self.evidence:
            raise ValueError(
                f"{self.case_id}: an answerable case with no evidence cannot be scored - "
                "`evidence_recall` refuses an empty requirement set, because a recall of 1.0 "
                "over nothing looks like success for a system that returned nothing"
            )
        if not answerable and self.evidence:
            raise ValueError(
                f"{self.case_id}: an unanswerable control that names evidence is not a "
                "control. Its whole job is that the correct answer is a grounded not-found"
            )
        if not answerable and not self.expected_behavior.acceptable_not_found:
            raise ValueError(
                f"{self.case_id}: an unanswerable control must accept not-found, or the only "
                "correct behaviour scores as a failure"
            )
        roles = {one.role for one in self.evidence}
        missing = set(self.expected_behavior.must_retrieve) - roles
        if missing:
            raise ValueError(
                f"{self.case_id}: must_retrieve names roles {sorted(missing)} that no evidence "
                f"item carries (present: {sorted(roles)})"
            )
        for one in self.evidence:
            EvidenceRef.parse(one.ref)
        return self

    @property
    def answerable(self) -> bool:
        return self.family != "unanswerable_control"

    @property
    def required(self) -> tuple[Evidence, ...]:
        """The evidence `must_retrieve` names, or all of it when the field is left empty."""
        if not self.expected_behavior.must_retrieve:
            return self.evidence
        wanted = set(self.expected_behavior.must_retrieve)
        return tuple(one for one in self.evidence if one.role in wanted)


class CaseFile(Frozen):
    """A whole case file, with the corpus inputs it was written against.

    `master_seed` and `generator_version` are carried for the reason `Manifest` carries them:
    a case file resolves refs against a corpus, and one resolved against a corpus generated by
    different inputs is scoring a mailbox nobody described.
    """

    schema_version: int = 1
    generator_version: str = Field(min_length=1, max_length=40)
    master_seed: int = Field(ge=0)
    cases: tuple[Case, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _case_ids_are_unique(self) -> Self:
        seen = [case.case_id for case in self.cases]
        if len(set(seen)) != len(seen):
            duplicated = sorted({one for one in seen if seen.count(one) > 1})
            raise ValueError(f"case ids repeat: {duplicated}")
        return self

    @property
    def by_family(self) -> dict[str, tuple[Case, ...]]:
        out: dict[str, list[Case]] = {}
        for case in self.cases:
            out.setdefault(case.family, []).append(case)
        return {family: tuple(cases) for family, cases in sorted(out.items())}


def load_cases(path: Path) -> CaseFile:
    """Read and validate a case file. Every refusal above fires here, before anything runs."""
    return CaseFile.model_validate(json.loads(path.read_text(encoding="utf-8")))


class ResolvedCase(Frozen):
    """One case with its refs joined through to Gmail ids: what an arm is actually scored on."""

    case: Case
    #: `{gmail_id: quote}` for the evidence `must_retrieve` names.
    required: Mapping[str, str]
    #: `{gmail_id: quote}` for every evidence item, which is what `any_of` is scored over.
    any_of: Mapping[str, str]
    distractor_ids: frozenset[str]
    #: The true length of the thread each required evidence item sits in, for P1a.
    thread_lengths: Mapping[str, int]

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)


def _seeded_by_ref(manifest: Manifest) -> dict[tuple[str, int], SeededMessage]:
    return {(message.thread_key, message.position): message for message in manifest.messages}


def _manifest_message(
    case: Case,
    manifest: Manifest,
    seeded: Mapping[tuple[str, int], SeededMessage],
    raw_ref: str,
    declared: str | None,
) -> SeededMessage:
    """The manifest half of the join: one ref, two refusals, no mailbox involved."""
    reference = EvidenceRef.parse(raw_ref)
    message = seeded.get((reference.thread_key, reference.position))
    if message is None:
        raise RefUnresolvable(
            f"{case.case_id}: {raw_ref} names no message in this corpus "
            f"(generator {manifest.generator_version}, seed {manifest.master_seed})"
        )
    if declared is not None and declared != message.rfc822_message_id:
        raise RefUnresolvable(
            f"{case.case_id}: {raw_ref} declares rfc_message_id {declared!r} and the "
            f"manifest holds {message.rfc822_message_id!r} at that position. The case was "
            "written against a different corpus"
        )
    return message


def check_against(case: Case, *, manifest: Manifest) -> None:
    """Every ref resolves in this corpus, and every declared id agrees with it. No mailbox.

    Separate from `resolve_against` because **the case author has a manifest and no mailbox**,
    and the alternative on offer was matching the prose of an exception about a verification
    report they do not have. `resolve_against` calls the same `_manifest_message`, so the
    refusals a case author sees are the refusals the scoring run applies and not a second copy
    of them.
    """
    seeded = _seeded_by_ref(manifest)
    for item in case.evidence:
        _manifest_message(case, manifest, seeded, item.ref, item.rfc_message_id)
    for one in case.distractors:
        _manifest_message(case, manifest, seeded, one.ref, None)


def resolve_against(case: Case, *, manifest: Manifest, report: VerificationReport) -> ResolvedCase:
    """Join one case's refs through the manifest to the ids the mailbox assigned.

    Three lookups, each refusing rather than guessing. The ref must name a message the manifest
    holds, a case that also *states* an `rfc_message_id` must state the one the manifest holds
    at that position - a disagreement there is a case written against a different corpus, and
    scoring it would credit or blame a retrieval that never happened - and the message must be
    one the verification report says was actually inserted.
    """
    seeded = _seeded_by_ref(manifest)
    gmail_by_rfc = {one.rfc822_message_id: one.gmail_id for one in report.inserted}
    lengths = manifest.answer_key.thread_lengths

    def gmail_id_of(raw_ref: str, declared: str | None) -> tuple[str, str]:
        message = _manifest_message(case, manifest, seeded, raw_ref, declared)
        gmail_id = gmail_by_rfc.get(message.rfc822_message_id)
        if gmail_id is None:
            raise RefUnresolvable(
                f"{case.case_id}: {message.rfc822_message_id} is in the manifest and not in "
                "the verification report, so it was never inserted. Re-seed before scoring"
            )
        return gmail_id, message.thread_key

    required: dict[str, str] = {}
    any_of: dict[str, str] = {}
    thread_lengths: dict[str, int] = {}
    for item in case.evidence:
        gmail_id, thread_key = gmail_id_of(item.ref, item.rfc_message_id)
        any_of[gmail_id] = item.quote
        thread_lengths[gmail_id] = lengths[thread_key]
    for item in case.required:
        gmail_id, _thread_key = gmail_id_of(item.ref, item.rfc_message_id)
        required[gmail_id] = item.quote
    distractors = frozenset(gmail_id_of(one.ref, None)[0] for one in case.distractors)
    return ResolvedCase(
        case=case,
        required=required,
        any_of=any_of,
        distractor_ids=distractors,
        thread_lengths=thread_lengths,
    )


__all__ = [
    "DISTRACTOR_TYPES",
    "FAMILIES",
    "FAMILY_LABELS",
    "REGISTERED_N",
    "SWEEP_POSITIONS",
    "Case",
    "CaseFile",
    "Distractor",
    "Evidence",
    "EvidenceRef",
    "ExpectedBehavior",
    "Paraphrase",
    "Position",
    "RefUnresolvable",
    "ResolvedCase",
    "Scoring",
    "check_against",
    "load_cases",
    "resolve_against",
]
