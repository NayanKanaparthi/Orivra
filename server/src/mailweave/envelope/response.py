"""The response envelope (AD D.2), and the invariants it refuses to be built without."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any, Final, Literal, Self

from pydantic import (
    ConfigDict,
    Field,
    JsonValue,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    field_serializer,
    model_serializer,
    model_validator,
)

from mailweave.envelope.disposition import (
    DispositionCertificate,
    assert_is_a_minted_certificate,
    disclosure_digest,
)
from mailweave.envelope.fence import is_fenced
from mailweave.envelope.measure import degradation_artifacts, measure_tokens
from mailweave.envelope.vocab import Depth, Outcome, Role
from mailweave.envelope.wire import (
    Affordance,
    AskedFor,
    BudgetBlock,
    Ceiling,
    Continuation,
    ErrorEntry,
    Frozen,
    NotIncludedBlock,
    NotIncludedSource,
    OmissionSummary,
    RetrievalReport,
    Source,
    WithheldGroup,
    WithheldRecord,
    WithheldTail,
)
from mailweave.errors import DispositionInvariantError, ResponseCeilingExceeded
from mailweave.sealed_model import re_establish_tree


def _group_shapes(groups: tuple[WithheldGroup, ...]) -> list[tuple[str, str, int]]:
    """A withheld group as the three things it claims, for a message a reader can compare."""
    return [(group.thread_id, group.cap.value, group.message_count) for group in groups]


def _with_fields_after(
    dumped: dict[str, JsonValue], *, after: str, fields: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    """`dumped` with `fields` inserted directly after key `after`, preserving order.

    D.2 documents a field order and a computed field serialises last, so a value written
    onto the wire by an enclosing model has to be placed rather than appended - the same
    reason `Source._rows_carry_this_sources_thread` rebuilds its dicts instead of updating
    them.
    """
    if not fields:
        return dumped
    rebuilt: dict[str, JsonValue] = {}
    for key, value in dumped.items():
        rebuilt[key] = value
        if key == after:
            rebuilt.update(fields)
    for key, value in fields.items():
        if key not in rebuilt:  # pragma: no cover - `after` is always a real field
            rebuilt[key] = value
    return rebuilt


#: Where a row's `internal_date` came from, on every row (2026-09-21). `gmail_internal_date`
#: is Gmail's own `internalDate`, the receipt time the mailbox recorded - not the sender's
#: `Date` header, which is sender-chosen and is not disclosed here. `not_observed` means no
#: observation this response made placed this row, so it holds no timestamp for it.
INTERNAL_DATE_OBSERVED: Final[str] = "gmail_internal_date"
INTERNAL_DATE_NOT_OBSERVED: Final[str] = "not_observed"


def _rows_with_internal_dates(
    dumped: dict[str, JsonValue], internal_dates: Mapping[str, str]
) -> dict[str, JsonValue]:
    """Write each row's observed `internalDate` onto its wire form (amendment A6), and say
    where it came from - or that it did not come at all.

    **The omission was read as "no timestamps"** (2026-09-21). The rule since A6 was that an
    id the ledger never observed got no `internal_date` field, so "does not know" and "says
    none" stayed distinct. Four of five exploratory runs read the absent field as "rows carry
    no timestamps" and ordered threads by identifier instead. The distinction is now carried
    by a token beside the value rather than by the value's absence: `internal_date` is on
    every row, `null` when unobserved, and `internal_date_provenance` says which of the two
    statements is being made. Nothing about what is *known* changed; what changed is that a
    reader no longer has to notice a missing key to learn it.
    """
    messages = dumped.get("messages")
    if not isinstance(messages, list):  # pragma: no cover - `messages` is always a list
        return dumped
    rows: list[JsonValue] = []
    for row in messages:
        if not isinstance(row, dict):  # pragma: no cover - rows are always dicts
            rows.append(row)
            continue
        observed = internal_dates.get(str(row.get("id")))
        rows.append(
            _with_fields_after(
                row,
                after="position",
                fields={
                    "internal_date": observed,
                    "internal_date_provenance": (
                        INTERNAL_DATE_NOT_OBSERVED if observed is None else INTERNAL_DATE_OBSERVED
                    ),
                },
            )
        )
    dumped = dict(dumped)
    dumped["messages"] = rows
    return dumped


def _the_emitted_disposition_is_the_certified_one(
    dumped: Any, certificate: DispositionCertificate, stated_partial: bool
) -> None:
    """Read I-1's and I-2's claims back out of the wire form and compare them (round 14).

    Every other check in this module is a check on the **object**. This one is a check on the
    mapping that is about to be handed to a caller, and the difference is the whole of the
    round-14 exit condition: a response may not *state* a disposition that differs from what
    the ledger computed, whatever happened to the objects in between. A value can differ
    between the two - a serializer, an alias, a `computed_field` - and the object-level checks
    would all pass.

    Two fields, and only two, because these are the two the invariants are about:
    `withheld` is I-1's record of what a cap dropped, and `partial` is I-2's disclosure that
    something was. That narrowness is the claim, not an omission: **this function does not
    check the rest of the payload against anything**, and what protects the rest is that a
    wire model cannot be substituted (`Frozen.__init_subclass__`) and that every model's
    after-validators are re-run (`re_establish_tree`).

    A key that is absent is not checked - `model_dump(include={"partial"})` legitimately emits
    one field - and a `withheld` entry the walk cannot read as a mapping is refused rather
    than skipped, which is `preflight/record.py`'s rule and for the same reason: silence about
    a value is how the value gets out.
    """
    if not isinstance(dumped, Mapping):
        raise DispositionInvariantError(
            "the wire form of an envelope is not a mapping, so this response's disposition "
            f"cannot be read back out of it: {type(dumped).__name__}. A serializer that "
            "returns something else has replaced the response's shape with one nothing here "
            "can check (contract I-1, I-2)"
        )
    if "withheld" in dumped:
        emitted: list[str] = []
        for record in dumped["withheld"]:
            if not isinstance(record, Mapping) or "id" not in record:
                raise DispositionInvariantError(
                    "a withheld record on the wire is not a mapping carrying an id: "
                    f"{type(record).__name__}. AD A.7a's record shape is what makes a "
                    "withheld message reachable, and a shape this check cannot read is a "
                    "shape a reader cannot use either (contract R-06)"
                )
            emitted.append(str(record["id"]))
        named = frozenset(record.id for record in certificate.withheld)
        if frozenset(emitted) != named:
            raise DispositionInvariantError(
                "the wire form's withheld list is not the certified set difference: "
                f"wire={sorted(emitted)} certified={sorted(named)}. The "
                "object passed every invariant and the emitted form disagrees with it, which "
                "means something rewrote the value between the check and the caller "
                "(contract I-1, AD A.7a)"
            )
        # **Round 29.** The grouped half cannot be compared id for id - a group carries a
        # count, which is the whole point - so it is compared by what it does claim, and the
        # two halves are then required to cover the difference exactly. A group silently
        # dropped from the wire, or a count edited down, fails here even though every named
        # record still agrees.
        counted = 0
        if "withheld_groups" in dumped:
            wire_groups: list[tuple[str, str, int]] = []
            for group in dumped["withheld_groups"]:
                if not isinstance(group, Mapping) or not {
                    "thread_id",
                    "cap",
                    "message_count",
                } <= set(group):
                    raise DispositionInvariantError(
                        "a withheld group on the wire is not a mapping carrying a thread, a "
                        f"cap and a count: {type(group).__name__}. A group is what makes the "
                        "messages it stands for reachable, and a shape this check cannot "
                        "read is one a reader cannot use either (contract R-06, R-MCP-033)"
                    )
                wire_groups.append(
                    (str(group["thread_id"]), str(group["cap"]), int(group["message_count"]))
                )
                counted += int(group["message_count"])
            certified_groups = [
                (g.thread_id, g.cap.value, g.message_count) for g in certificate.withheld_groups
            ]
            if sorted(wire_groups) != sorted(certified_groups):
                raise DispositionInvariantError(
                    f"the wire form's withheld groups are not the certified ones: "
                    f"wire={sorted(wire_groups)} certified={sorted(certified_groups)}"
                )
        if "withheld_tail" in dumped:
            for tail in dumped["withheld_tail"]:
                if not isinstance(tail, Mapping) or "message_count" not in tail:
                    raise DispositionInvariantError(
                        "a withheld tail on the wire is not a mapping carrying a count"
                    )
                counted += int(tail["message_count"])
            certified_tails = sorted(
                (t.cap.value, t.thread_count, t.message_count) for t in certificate.withheld_tail
            )
            wire_tails = sorted(
                (str(t["cap"]), int(t["thread_count"]), int(t["message_count"]))
                for t in dumped["withheld_tail"]
            )
            if wire_tails != certified_tails:
                raise DispositionInvariantError(
                    f"the wire form's withheld tail is not the certified one: "
                    f"wire={wire_tails} certified={certified_tails}"
                )
        if "withheld" in dumped and len(emitted) + counted != len(certificate.withheld_ids):
            raise DispositionInvariantError(
                f"the wire form accounts for {len(emitted) + counted} of "
                f"{len(certificate.withheld_ids)} withheld messages. Named records plus group "
                "counts must equal the set difference: a response may write an omission "
                "compactly and may not write it away (AD A.7a, R-MCP-033 requirement 7)"
            )
    if "partial" in dumped and dumped["partial"] is not stated_partial:
        raise DispositionInvariantError(
            f"the wire form states partial={dumped['partial']!r} for an envelope whose "
            f"partial is {stated_partial!r}. `partial` is derived from the payload by "
            "`_partial_flag_is_derived` and that check has just passed on this object, so a "
            "different value on the wire is a second, unchecked statement of the same fact - "
            "which is what a response that dropped a message and reports itself complete "
            "looks like (contract I-2, PART-03)"
        )


class Envelope(Frozen):
    """A MailWeave response.

    An `Envelope` cannot be constructed without a `DispositionCertificate`, and a
    certificate cannot be obtained without running `withheld := H - disclosed` through
    `DispositionLedger.certify`. That is the structural half of invariant I-1: the type
    system will not let a caller assemble a response that drops a hit, because the only
    way to get the object the constructor demands is to account for every retrieved ID.

    The validators below are the mechanical half: they re-derive from the payload itself
    everything the payload claims about itself.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    # Field order is wire order (R-DISC-003). Everything that says *how complete this
    # answer is* comes before `sources`, which is the unbounded content block: `partial`
    # is the boolean, `withheld` is what is missing, `retrieval_report` carries the
    # outcome and the routes not tried. Round 1 put `sources` third, so a model reading
    # top to bottom - or a client rendering the stream as it arrives - met the bulk of the
    # payload before anything told it the answer was incomplete. No field was added,
    # removed or renamed: the signals were already all present and correct, and a reader
    # simply had to reach past the content to assemble them.
    #
    # **Round 29 added the summary block this comment used to refuse, and kept the rule it
    # refused it under.** `omission` is a root-level "K withheld, by cap, from N threads"
    # block, added because a client was parsing a remediation sentence to learn those numbers
    # (R-MCP-033 requirement 2). It is not a second statement of the fact: it is derived by
    # the builder from the certificate and *checked against the certificate here*
    # (`_the_omission_summary_restates_the_certificate_exactly`), so a summary that
    # disagrees with the enumeration is refused, which is exactly the protection R-DISC-001
    # asked for and the reason an unchecked summary was not allowed for twenty-eight rounds.
    schema_version: Literal[2] = 2
    fence_nonce: str = Field(min_length=8)
    asked_for: AskedFor
    partial: bool
    withheld: tuple[WithheldRecord, ...] = ()
    #: **Round 29, R-MCP-033.** Withholdings written at thread granularity, one entry per
    #: (thread, cap), each with an exact count. Minted by the same `certify` that mints
    #: `withheld`, and checked against it below: an envelope may not restate either half.
    withheld_groups: tuple[WithheldGroup, ...] = ()
    #: Groups past `MAX_WITHHELD_GROUPS_NAMED`, folded per cap into exact counts with the call
    #: that widens the cap (round 29, R-V01-007). Checked against the certificate below.
    withheld_tail: tuple[WithheldTail, ...] = ()
    #: The omission counts as fields rather than as a sentence (requirement 2). Derived from
    #: the certificate, never asserted beside it.
    omission: OmissionSummary | None = None
    retrieval_report: RetrievalReport
    sources: tuple[Source, ...] = ()
    not_included_sources: tuple[NotIncludedBlock, ...] = ()
    affordances: tuple[Affordance, ...] = ()
    #: Access to the remainder of what this response started - the rest of a requested
    #: batch, the other pages of a map (navigation redesign, 2026-09-14). Distinct from a
    #: decline's `narrowing`: a continuation preserves scope, a narrowing changes it.
    continuations: tuple[Continuation, ...] = ()
    ceiling: Ceiling
    errors: tuple[ErrorEntry, ...] = ()
    budget: BudgetBlock = BudgetBlock()
    truncated_by: Literal["mailweave"] | None = None

    #: Excluded from the wire form: it is the proof, not the payload.
    disposition: DispositionCertificate = Field(exclude=True, repr=False)

    # -- amendment A6: the observed scalars are written on, not accepted in -------------

    @field_serializer("sources")
    def _sources_carry_the_scalars_the_observation_recorded(
        self, sources: tuple[Source, ...], info: SerializationInfo
    ) -> list[dict[str, JsonValue]]:
        """Write `internal_date` and `history_id` onto the wire from the certificate (A6).

        The route `MessageRow.thread_id` took in round 7, one level further up. Those two
        fields were the class-O cases with **no reader inside the model**: nothing in
        `MessageRow` or `Source` validates against them, so they were pure caller
        assertions about facts of a Gmail response, and round 7 had to file both as `open`
        because the seal recorded neither. A6 seals them, so the parameters are gone and
        the values are projections of the ledger.

        Why here rather than on `Source`, which is where `thread_id` is written: the fact
        lives on the certificate, and `Envelope` is the first object that holds both the
        certificate and the payload. The three class-O fields that stayed parameters -
        `stated_total`, `position`, `fetched_at` - stayed because `Source` and `MessageRow`
        validate *against* them (A3's range, the map accounting, the freshness ordering),
        and a field the model reads cannot be supplied two levels up without threading the
        observation through the whole tree. Those are checked exactly instead; the
        validators below are where.

        An id or a thread the ledger never observed gets no field written, rather than a
        `null`: "this response does not know" and "this response says none" are different
        statements, and only the first one is true.
        """
        mode = "json" if info.mode_is_json() else "python"
        internal_dates = self.disposition.observed_internal_dates
        thread_facts = self.disposition.observed_thread_facts
        rendered: list[dict[str, JsonValue]] = []
        for source in sources:
            dumped: dict[str, JsonValue] = source.model_dump(mode=mode)
            observed = thread_facts.get(source.thread_id)
            history_id = observed.history_id if observed is not None else None
            rendered.append(
                _with_fields_after(
                    _rows_with_internal_dates(dumped, internal_dates),
                    after="verified_at",
                    fields={"history_id": history_id} if history_id is not None else {},
                )
            )
        return rendered

    # -- derived views ----------------------------------------------------------------

    @property
    def disclosed_ids(self) -> frozenset[str]:
        """`R`'s disclosed half: every ID present at any depth, in any source."""
        ids: set[str] = set()
        for source in self.sources:
            ids |= source.disclosed_ids
        return frozenset(ids)

    @property
    def not_included_entries(self) -> tuple[NotIncludedSource, ...]:
        """Every not-included source, flattened out of its reason block (round 29).

        The wire groups by reason so one sentence is written once; every check below is about
        an individual thread, its stated total and its recovery call, and none of them cares
        which block it arrived in. Flattening here keeps those checks over the entries rather
        than teaching each of them the block shape.
        """
        return tuple(entry for block in self.not_included_sources for entry in block.sources)

    @property
    def withheld_ids(self) -> frozenset[str]:
        """Every withheld id: the ones this envelope names, and the ones its groups stand for.

        The grouped half is read from the certificate because a group carries a count, not an
        enumeration - that is the point of it. `represented_ids` and every check built on it
        therefore keep covering the whole set difference, exactly as they did when every
        withholding was written out one message at a time.
        """
        named = frozenset(record.id for record in self.withheld)
        return named | (self.disposition.withheld_ids - self._named_by_certificate())

    def _named_by_certificate(self) -> frozenset[str]:
        return frozenset(record.id for record in self.disposition.withheld)

    @property
    def represented_ids(self) -> frozenset[str]:
        """`R` = disclosed at any depth, plus every ID carried by a withheld record."""
        return self.disclosed_ids | self.withheld_ids

    @property
    def matched_ids(self) -> frozenset[str]:
        return frozenset(
            row.id for source in self.sources for row in source.messages if row.role is Role.MATCHED
        )

    # -- the wire form re-derives what construction derived (R-SEC-047, R-ARCH-034) -----

    @model_serializer(mode="wrap")
    def _the_wire_form_states_only_what_still_holds(
        self, handler: SerializerFunctionWrapHandler
    ) -> Any:
        """The chokepoint: nothing reaches the wire without the invariants holding of it.

        This is the point of use for an envelope. Whatever produced the object - the builder,
        `model_copy`, `model_construct`, a write into `__dict__` past `frozen=True` - what a
        caller sends is what this returns, and it returns nothing for an envelope whose own
        payload no longer supports what it says.

        Three things happen here and they are three different guarantees:

          * `re_establish_tree(self)` runs every `mode="after"` validator of this model **and
            of every model inside it**, discovered off each class's MRO. Round 13 ran
            `type(self).__pydantic_decorators__` and covered seventeen of the tree's
            forty-one, so `model_copy(update={"sources": ...})` put a row at position 900 of a
            two-message thread on the wire (R-ARCH-034). The count is asserted in
            `tests/test_wire_tree_round14.py`, so the guarantee cannot narrow again quietly;
          * `handler(self)` produces the wire form;
          * `_the_emitted_disposition_is_the_certified_one` reads I-1's and I-2's two claims
            back **out of the emitted mapping** and compares them with the certificate. Every
            other check here is a check on the *object*; this one is a check on what is
            actually being handed out, which is a different statement and the one the exit
            condition is about. It is what makes "the wire form states only what still holds"
            true of the wire form rather than of the model behind it.

        The refusal surfaces as Pydantic's `PydanticSerializationError` wrapping the
        `DispositionInvariantError`, because Pydantic wraps whatever a serializer raises. The
        wrapped message carries the invariant's own text; the type does not survive, and that
        is a real cost of doing the check here rather than in a hand-written `to_wire`. It is
        the trade this round chose deliberately: a method callers must remember to call is a
        check the next consumer skips, which is the defect being fixed rather than a fix.

        **What "the wire" means here, since the word is doing work.** Every route through
        Pydantic's serializer passes through this: `model_dump` in both modes and with
        `include`, `exclude`, `by_alias` or `warnings=False`; `model_dump_json`; this envelope
        as a field of another model; a `TypeAdapter` over a list of them. Each was driven and
        each refuses a tampered envelope, at the envelope's own fields and inside its sources.

        It is **not** a check on reading the object's attributes, and it cannot be. `dict(env)`
        - Pydantic's field-iteration convenience - is a bulk attribute read, so it hands back
        the tampered values exactly as `env.withheld` does, and a caller who then serialises
        that dict themselves has assembled a payload this class never produced. `repr(env)`
        renders them too, into any log or error message that formats an envelope. That residue
        is named rather than patched on purpose: closing `__iter__` would close one route out
        of every possible hand-assembly and leave the impression the class is sealed against
        all of them, which is the enumeration habit this round exists to correct. In-process,
        no object can force a caller to ask it a question - the same sentence `pinning.py` has
        to write about `assert_bound_to`. The residue is pinned by
        `test_the_attribute_read_residue_is_what_the_docstring_says`, so this paragraph
        cannot quietly become an overstatement either.
        """
        re_establish_tree(self)
        dumped = handler(self)
        _the_emitted_disposition_is_the_certified_one(dumped, self.disposition, self.partial)
        return dumped

    def model_copy(self, *, update: Mapping[str, Any] | None = None, deep: bool = False) -> Self:
        """Pydantic's copy, with this model's invariants re-established on the result.

        The early failure to the serializer's guarantee, in the same relationship as
        `SeedSession.__post_init__` to `assert_bound_to`: it makes the ordinary mistake loud
        where somebody wrote it, and it is emphatically **not** what makes the property hold -
        `model_construct` and a direct `__dict__` write both walk past it, and both are caught
        at the wire. It re-establishes the whole tree, because `update={"sources": ...}` is
        R-ARCH-034's own line.
        """
        copied = super().model_copy(update=update, deep=deep)
        re_establish_tree(copied)
        return copied

    # -- invariants -------------------------------------------------------------------

    @model_validator(mode="after")
    def _the_disposition_is_a_certificate_this_process_minted(self) -> Envelope:
        """The reader asks the mint, not the object's own account of what it is (R-SEC-054).

        `disposition: DispositionCertificate` is a Pydantic field, so Pydantic runs an
        `isinstance` check, and for one round `disposition.py` said in terms that this refused
        "a duck-typed impostor - a class that merely has the same properties". It does not.
        `isinstance` consults `obj.__class__` when `type(obj)` does not match, so an ordinary
        object with

            @property
            def __class__(self): return DispositionCertificate

        passed the field, was accepted here, and serialised `withheld: []` / `partial: false`
        for a ledger holding an unaccounted hit - with **no `DispositionLedger` in the process
        at all**, because `disclosure_digest` is a public function and the impostor supplies
        the rest. The covering test planted a duck that did not declare `__class__`, so it
        passed without ever exercising the property its name asserts.

        A sealed object read by an unsealed reader is not sealed, and a type annotation is not
        a check against forgery. `assert_is_a_minted_certificate` asks the two questions that
        are not the same question - is this the actual type, and did `certify` mint *this
        object* - and asks neither of them of the candidate. Being an after-validator, it is
        re-established at the wire like every other one, so `model_construct` and a write into
        `__dict__` do not get past it either.
        """
        assert_is_a_minted_certificate(self.disposition)
        return self

    @model_validator(mode="after")
    def _withheld_matches_the_certificate(self) -> Envelope:
        """The envelope may not restate the certificate's conclusion differently.

        Record-for-record, not id-for-id (R-DISC-009). Round 5 compared only the id set and
        the length, so an envelope could ship records carrying the certified ids under a
        *different* `thread_id` than the ledger derived - which re-opens the cross-thread
        borrowing this round closed one layer down, at the last point where the records are
        still editable. Every field of a withheld record is the ledger's finding, so the
        whole record is compared and not just its name.
        """
        if self.withheld_ids != self.disposition.withheld_ids:
            raise DispositionInvariantError(
                "the envelope's withheld list disagrees with the certified set difference: "
                f"envelope={sorted(self.withheld_ids)} "
                f"certified={sorted(self.disposition.withheld_ids)}"
            )
        if len(self.withheld) != len(self.disposition.withheld):
            raise DispositionInvariantError("duplicate withheld records in the envelope")
        if self.withheld_tail != self.disposition.withheld_tail:
            raise DispositionInvariantError(
                "the envelope's withheld tail disagrees with the certified one: a folded count "
                "stands for threads this response does not name, so a restated count is a "
                "restated omission (R-MCP-033)"
            )
        if self.withheld_groups != self.disposition.withheld_groups:
            raise DispositionInvariantError(
                "the envelope's withheld groups disagree with the certified ones: "
                f"envelope={_group_shapes(self.withheld_groups)} "
                f"certified={_group_shapes(self.disposition.withheld_groups)}. "
                "A group's count stands for messages this response does not name, so a "
                "restated count is a restated omission - the same second, unchecked account "
                "of one fact that R-DISC-009 closed for the named records (R-MCP-033)"
            )
        certified = {record.id: record for record in self.disposition.withheld}
        altered = sorted(record.id for record in self.withheld if certified[record.id] != record)
        if altered:
            raise DispositionInvariantError(
                f"withheld records were rewritten after certification: {altered}. A record "
                "carries the cap, the reason, the affordance and the thread the ledger "
                "derived from where the id was observed; an envelope restating any of them "
                "is a second, unchecked account of the same fact - which is how a map comes "
                "to claim completeness with another thread's message (R-DISC-009)"
            )
        # **Round 29: both halves count.** A withholding written as a counted group accounts
        # for its messages exactly as a named record does, so the total is named + grouped.
        # Counting only the named half here would have made compaction look like loss.
        certified_total = (
            self.disposition.disclosed_hits
            + len(self.disposition.withheld)
            + sum(group.message_count for group in self.disposition.withheld_groups)
            + sum(tail.message_count for tail in self.disposition.withheld_tail)
        )
        if certified_total != self.disposition.hit_count:
            raise DispositionInvariantError(  # pragma: no cover - certify prevents this
                f"certificate does not account for every hit: "
                f"{certified_total} of {self.disposition.hit_count}"
            )
        if disclosure_digest(self.disclosed_ids) != self.disposition.disclosure_digest:
            raise DispositionInvariantError(
                "the certificate was computed against a different disclosed set than this "
                "envelope carries; a certificate cannot be lifted from another response"
            )
        return self

    @model_validator(mode="after")
    def _the_omission_summary_restates_the_certificate_exactly(self) -> Envelope:
        """`omission` is a restatement of the certificate's numbers, so it is checked against
        them (R-V01-011). The builder derives it correctly; this is what refuses a summary
        that says 0 withheld over 48, or none at all on a response that withheld something -
        the wire claimed the counts were "asserted at mint time" for one round and they were
        not. A summary that does not add up is worse than none, because a client trusts it.
        """
        by_cap: Counter[str] = Counter()
        for record in self.disposition.withheld:
            by_cap[record.cap.value] += 1
        for group in self.disposition.withheld_groups:
            by_cap[group.cap.value] += group.message_count
        for tail in self.disposition.withheld_tail:
            by_cap[tail.cap.value] += tail.message_count
        expected_total = len(self.disposition.withheld_ids)
        expected_threads = len(self.disposition.withheld_groups) + sum(
            tail.thread_count for tail in self.disposition.withheld_tail
        )
        if self.omission is None:
            if expected_total or self.not_included_entries:
                raise DispositionInvariantError(
                    "a response that withheld or left out something carries no omission "
                    "summary; the counts a client reads as fields must be present whenever "
                    "there is anything to count (R-MCP-033 requirement 2)"
                )
            return self
        stated = self.omission
        if (
            stated.withheld_messages != expected_total
            or dict(stated.withheld_by_cap) != dict(by_cap)
            or stated.withheld_threads != expected_threads
            or stated.not_included_sources != len(self.not_included_entries)
        ):
            raise DispositionInvariantError(
                "the omission summary disagrees with the certificate it restates: "
                f"summary={stated.model_dump(mode='json')} certified: withheld={expected_total} "
                f"by_cap={dict(by_cap)} threads={expected_threads} "
                f"not_included={len(self.not_included_entries)}"
            )
        return self

    @model_validator(mode="after")
    def _withheld_is_disjoint_from_disclosed(self) -> Envelope:
        """A message cannot be both present and withheld (AD A.7a: exactly one disposition)."""
        both = self.withheld_ids & self.disclosed_ids
        if both:
            raise DispositionInvariantError(
                f"messages are both disclosed and listed as withheld: {sorted(both)}"
            )
        return self

    @model_validator(mode="after")
    def _map_accounting_is_backed_by_real_withheld_records(self) -> Envelope:
        """A source's `withheld_here` must name records this response actually carries.

        `Source` checks that a claimed map accounts for every message; this checks that
        the third disposition it may use - "withheld" - is not a fiction. Without this,
        a map could close its own arithmetic by listing ids nothing withholds, which
        would put the assertion back beside the enumeration instead of deriving it from
        it (R-DISC-001).
        """
        for source in self.sources:
            claimed = set(source.withheld_here)
            backing = {r.id for r in self.withheld if r.thread_id == source.thread_id}
            unbacked = claimed - backing
            if unbacked:
                raise DispositionInvariantError(
                    f"source {source.thread_id} accounts for {sorted(unbacked)} as withheld, "
                    "but this response carries no withheld record for them; a message is "
                    "accounted for by a record, not by a mention (AD A.7a, contract R-06)"
                )
            if source.map_id is not None and backing != claimed:
                raise ValueError(
                    f"source {source.thread_id} claims map_id={source.map_id!r} while "
                    f"{sorted(backing - claimed)} of its messages are withheld without "
                    "appearing in the map's accounting"
                )
        return self

    @model_validator(mode="after")
    def _partial_flag_is_derived(self) -> Envelope:
        """`partial` is a computed fact, not a mood (I-2, PART-03 both directions)."""
        incomplete_sources = [s.thread_id for s in self.sources if not s.complete_as_reported]
        unfetched_pages = any(e.more_pages for e in self.retrieval_report.scan_scope)
        expected = bool(
            self.withheld
            # **Round 29.** An omission written as a counted group is an omission. Deriving
            # `partial` from the named half alone would have let compaction change I-2's
            # answer, which is the one thing compaction must not touch.
            or self.withheld_groups
            or self.withheld_tail
            or incomplete_sources
            or self.not_included_sources
            or unfetched_pages
            or self.truncated_by is not None
            # A `requested` continuation is part of the request this response does not
            # carry (navigation redesign, 2026-09-14); a `thread` continuation is not an
            # omission - the map beside it is whole - and does not enter here.
            or any(one.scope == "requested" for one in self.continuations)
        )
        if self.partial != expected:
            raise ValueError(
                f"partial={self.partial} but the payload says {expected} "
                f"(withheld={len(self.withheld)}, "
                f"withheld_groups={len(self.withheld_groups)}, "
                f"incomplete_sources={incomplete_sources}, "
                f"not_included_sources={len(self.not_included_entries)}, "
                f"unfetched_pages={unfetched_pages}, truncated_by={self.truncated_by}, "
                f"continuations={[one.scope for one in self.continuations]})"
            )
        return self

    def _remainder_is_recoverable_by_id(self, source: Source) -> bool:
        """Whether every message this source is missing is named by a call of its own.

        True only when the arithmetic closes - the rows, the collapsed-run members and the
        `withheld_here` ids together are `stated_total` - and every one of those ids has a
        withheld record whose affordance names it. A partially enumerated remainder is
        false, which is what keeps a search view (three rows of a forty-two message thread,
        nothing said about the other thirty-nine) on the thread-call branch.
        """
        missing = set(source.withheld_here)
        if not missing or source.included + len(missing) != source.stated_total:
            return False
        named = {
            record.id
            for record in self.withheld
            if record.thread_id == source.thread_id and record.affordance.mentions(record.id)
        }
        return missing <= named

    @model_validator(mode="after")
    def _incomplete_sources_carry_a_path_to_the_rest(self) -> Envelope:
        """R-07/PART-03: a partiality statement must sit next to an executable call.

        **The call may name the thread or it may name the remainder** (round 31,
        R-M2-016). Naming the thread is the general answer, because a source that discloses
        three of forty-two messages has an unenumerated remainder and the thread's map is
        the only thing that reaches it. A map source is the other case: its remainder is
        *enumerated*, id by id, in `withheld_here`, and each of those ids is backed by a
        `WithheldRecord` carrying its own recovery call - which
        `_map_accounting_is_backed_by_real_withheld_records` has already checked exists,
        and which `Source._a_claimed_map_accounts_for_every_message` has already checked
        is the whole remainder. For that source the per-message calls *are* the executable
        path, and requiring a thread call besides them asks for a second way of saying the
        same thing that returns the caller to the response they are already reading -
        `mailweave_get_messages` over a 300-message thread, whose one step-8 withholding
        would be answered with `mailweave_thread_map` on the thread the caller just mapped.

        So the reachability test is computed over the remainder rather than over the thread
        key alone. It is not a weaker rule: the enumerated branch requires a call for
        *every* missing message, where the thread branch requires one call for all of them.
        """
        for source in self.sources:
            keys = {source.thread_id, source.map_id or ""}
            if not source.complete_as_reported:
                reachable = (
                    any(a.mentions(*keys) for a in self.affordances)
                    or any(run.affordance.mentions(*keys) for run in source.collapsed_runs)
                    or self._remainder_is_recoverable_by_id(source)
                )
                if not reachable:
                    raise ValueError(
                        f"source {source.thread_id} includes {source.included} of "
                        f"{source.stated_total} messages with no affordance that names it "
                        "(contract R-07)"
                    )
            else:
                phantom = [r.id for r in self.withheld if r.thread_id == source.thread_id]
                if phantom:
                    raise ValueError(
                        f"source {source.thread_id} reports every message included, yet "
                        f"withholds {phantom}: a phantom remainder (PART-03)"
                    )
                split_off = [
                    n.thread_id
                    for n in self.not_included_entries
                    if n.thread_id == source.thread_id
                ]
                if split_off:
                    raise ValueError(
                        f"thread {source.thread_id} is both a complete source and a "
                        "not-included source"
                    )
        return self

    @model_validator(mode="after")
    def _no_bare_empty_response(self) -> Envelope:
        """ROUTE-01: a no-evidence outcome is a structured report, never an empty set.

        **The ladder must be accounted for, and "none of it ran" is an account.** This rule
        used to be `report.rungs` alone - a zero-evidence response must state which rungs
        *executed* - and that made a structured report unbuildable for the one query where
        every rung is genuinely `not_applicable`: one the parser could draw no probe from at
        all. The consequence was worse than the shape the rule guards against. Round 16 had
        nothing to return for such a query but an exception, so seventeen of fifty plausible
        queries produced no response at all, which fails ROUTE-01's own sentence - "a
        no-evidence outcome is a structured report, never an empty set or a nonexistence
        claim" - more completely than the bare empty payload it was written against.

        The requirement was never that a rung ran; it is that the response says what
        happened. A report naming every rung as not tried, with the parse, the tokens
        dropped and why, an `empty_diagnosis` and the affordances, is the opposite of a bare
        empty result. What is still refused is a response that says **neither**: no rung
        executed and no rung accounted for. The three checks below are unchanged in what they
        forbid - silence about the ladder, silence about the scan, silence about the drops.
        """
        if self.disclosed_ids:
            return self
        report = self.retrieval_report
        if not (report.rungs or report.not_tried):
            raise ValueError(
                "a zero-evidence response must account for the ladder: which rungs "
                "executed, or which did not and why (ROUTE-01)"
            )
        if not (report.scan_scope or report.not_tried or self.errors):
            raise ValueError(
                "a zero-evidence response must state the queries executed, the rungs not "
                "tried, or the errors that stopped it (ROUTE-01)"
            )
        if report.empty_diagnosis is None:
            raise ValueError(
                "a zero-evidence response must carry an empty_diagnosis stating which "
                "constraint drops were tried (ROUTE-01, ADV-105)"
            )
        return self

    @model_validator(mode="after")
    def _outcome_matches_the_payload(self) -> Envelope:
        """OD-2 at envelope level, on top of the report-level rule.

        `not_found` claims every applicable route ran and was exhausted. A withheld
        record, an unfetched page, or a matched message each contradict that claim
        directly, so each is refused here rather than left to a reviewer to notice.
        """
        outcome = self.retrieval_report.outcome
        if outcome is Outcome.ANSWERED and not self.disclosed_ids:
            raise ValueError("outcome=answered with nothing disclosed")
        if outcome is not Outcome.NOT_FOUND:
            return self
        if self.withheld:
            raise ValueError(
                "outcome=not_found while messages are withheld: a withheld record is "
                f"evidence that was retrieved and not shown ({sorted(self.withheld_ids)}); "
                "the honest outcome is inconclusive (OD-2)"
            )
        if any(e.more_pages for e in self.retrieval_report.scan_scope):
            raise ValueError(
                "outcome=not_found with unfetched result pages: pages outside H were "
                "never examined, so no route was exhausted (OD-2)"
            )
        if self.matched_ids:
            raise ValueError(
                "outcome=not_found while matched messages are disclosed: "
                f"{sorted(self.matched_ids)}"
            )
        if self.retrieval_report.empty_diagnosis is None:
            raise ValueError(
                "outcome=not_found requires an empty_diagnosis: OD-2 obliges every negative "
                "result to report routes executed and relaxations performed"
            )
        return self

    @model_validator(mode="after")
    def _self_truncation_is_verified_against_the_ceiling(self) -> Envelope:
        """DISC-06/R-10: a truncation claim is checked against the size that resulted.

        Round 1 gated the ceiling on the `truncated_by` flag alone, so calling
        `mark_self_truncated()` and then shipping 27,000 tokens against a 9,000-token
        ceiling was accepted with nothing removed (R-DISC-002). Two things are checked
        here, both derived from the assembled payload rather than from the claim:

          * the response fits its own declared ceiling - **whether or not** it says it
            truncated itself, because a response that does not fit hands truncation to
            the host, which is the thing DISC-06 forbids;
          * a self-truncation claim has at least one artifact of the A.9a ladder behind
            it. A flag with nothing removed is a false statement about what was done.

        The measurement is the whitespace estimate of `measure.py`, named as an estimate
        wherever it appears; the pinned tokenizer is registered at G0.
        """
        measured = measure_tokens(self)
        if measured > self.ceiling.applied:
            raise ResponseCeilingExceeded(
                f"assembled response is ~{measured} whitespace tokens against an applied "
                f"ceiling of {self.ceiling.applied}"
                + (
                    "; declaring self-truncation does not make it fit - the A.9a "
                    "degradation ladder must actually shrink the payload (DISC-06)"
                    if self.truncated_by is not None
                    else "; the A.9a degradation ladder must run before the response is "
                    "emitted (DISC-06)"
                )
            )
        if self.truncated_by is not None and not degradation_artifacts(self):
            raise ResponseCeilingExceeded(
                "truncated_by=mailweave with no trace of the degradation ladder in the "
                "payload: no collapsed run, no reduced-depth row, no head truncation, no "
                "ceiling-withheld record and no split-off source. A truncation claim is "
                "derived from what was removed, not asserted beside it (DISC-06)"
            )
        return self

    @model_validator(mode="after")
    def _constraint_coverage_names_constraints_the_query_carried(self) -> Envelope:
        """R-DISC-006: a row may not claim to satisfy a constraint the request never had.

        `constraint_coverage` is per-message evidence that this message matched a
        particular part of the query. Round 1 left it a live field with no validator and
        no reference anywhere, so it could name anything at all - including a constraint
        that would make an unrelated message look responsive.

        The constraints a response is allowed to talk about are the ones its own
        `asked_for` block enumerates: those still enforced, plus those a relaxation
        dropped, because a dropped constraint is still one the user wrote and a message
        may legitimately satisfy it. The check is a relation between two parts of the same
        payload, so nothing is asserted that is not also enumerated.
        """
        available = set(self.asked_for.enforced) | {
            entry.constraint for entry in self.asked_for.dropped
        }
        for source in self.sources:
            for row in source.messages:
                unknown = sorted(set(row.constraint_coverage) - available)
                if unknown:
                    raise ValueError(
                        f"message {row.id} reports constraint_coverage for {unknown}, which "
                        f"asked_for does not carry (enforced={sorted(self.asked_for.enforced)}, "
                        "dropped="
                        f"{sorted(e.constraint for e in self.asked_for.dropped)}). A message "
                        "cannot satisfy a constraint the request never made"
                    )
        return self

    @model_validator(mode="after")
    def _mail_text_is_fenced(self) -> Envelope:
        """Contract R-09: all mail-derived text is fenced with this response's nonce."""
        for source in self.sources:
            for row in source.messages:
                if row.content is None:
                    continue
                if not is_fenced(self.fence_nonce, row.content.text):
                    raise ValueError(
                        f"content of message {row.id} is not fenced with this response's nonce"
                    )
        return self

    @model_validator(mode="after")
    def _depth_stubs_are_accounted(self) -> Envelope:
        """A stub row is disclosed, not withheld - the confusion A.7a warns about."""
        stub_ids = {
            row.id for source in self.sources for row in source.messages if row.depth is Depth.STUB
        }
        overlap = stub_ids & self.withheld_ids
        if overlap:  # pragma: no cover - already caught by the disjointness check
            raise DispositionInvariantError(
                f"messages present as stubs are also listed as withheld: {sorted(overlap)}"
            )
        return self

    # -- R-DISC-011: the disclosed half of the borrowing R-DISC-009 closed -------------

    @model_validator(mode="after")
    def _disclosed_rows_sit_in_the_thread_they_were_observed_in(self) -> Envelope:
        """A source may not disclose a message the ledger saw in a different thread.

        R-DISC-009 closed this on the withheld side by deriving a record's thread from
        `HitOrigin`. The disclosed side kept asserting it: a `map_id`-bearing source for
        thread `t1` could reach `accounted_for == stated_total` by carrying a row for a
        real message that a real `threads.get` had observed in `t5`, and every check in the
        payload agreed, because every check compared the row against the source's own
        claim. R-DISC's executed proof built exactly that with `partial=False`.

        The certificate carries `observed_threads`, so the comparison is against the
        enumeration the set difference was computed from rather than against a second
        statement of the same fact. Three cases, and they are not the same:

          * **the observation named a thread** - the source must be that thread. This is
            the borrowing, and it raises;
          * **the observation named no thread** - nothing contradicts the source, so an
            ordinary search view is left alone. A `map_id`-bearing source is not: its
            claim is "these are all of thread X's messages", and counting a message
            toward that total with nothing observed placing it in X is the same borrowing
            with the evidence missing rather than contrary. `_record_for` refuses the
            withheld twin of this for the same reason;
          * **the id is not in `H` at all** - the ledger has no opinion. A parent, a child
            or a context row fetched outside any recorded retrieval is legitimate, and
            bounding *that* is A1's content witness, not something this process can do.
        """
        observed = self.disposition.observed_threads
        borrowed: list[str] = []
        unplaced_in_a_map: list[str] = []
        for source in self.sources:
            for message_id in sorted(source.disclosed_ids):
                if message_id not in observed:
                    continue
                thread = observed[message_id]
                if thread is None:
                    if source.map_id is not None:
                        unplaced_in_a_map.append(message_id)
                    continue
                if thread != source.thread_id:
                    borrowed.append(
                        f"{message_id} was observed in thread {thread} and is disclosed "
                        f"under source {source.thread_id}"
                    )
        if borrowed:
            raise DispositionInvariantError(
                "disclosed messages are shown under a thread other than the one the "
                f"observation put them in: {'; '.join(borrowed)}. Which thread a message "
                "belongs to is a fact of the Gmail response that returned it, and a source "
                "that borrows another thread's message can report a map complete while a "
                "real message of its own thread is represented nowhere (R-DISC-011, "
                "R-DISC-009, PART-05, contract R-06)"
            )
        if unplaced_in_a_map:
            raise DispositionInvariantError(
                "a thread map counts messages no observation placed in its thread: "
                f"{sorted(unplaced_in_a_map)}. These ids entered H through an observation "
                "that recorded no threadId, so nothing in this response says they are "
                "messages of this thread, and a map is exactly the claim that they are. "
                "Record the observation with the threadId Gmail returned beside each id - "
                "the same rule a withheld record has followed since R-DISC-009 "
                "(R-DISC-011, PART-05, contract R-06)"
            )
        return self

    @model_validator(mode="after")
    def _stated_total_is_not_below_what_was_observed_in_the_thread(self) -> Envelope:
        """A thread cannot be shorter than the number of its messages the ledger saw.

        Round 7 could only bound this from below: if four distinct ids were observed in
        thread `t1`, `t1` has at least four messages. Understating it is worth refusing on
        its own terms, because `complete_as_reported` is `included == stated_total` and
        `partial` is derived from that - so a shrunken total turns an incomplete answer
        into a confident one.

        **Amendment A6 gives the upper bound too**, where the observation carries it: a
        `threads.get` response states how many messages the thread holds, and the seal now
        records it, so `_stated_total_is_the_one_the_observation_stated` below holds the
        source to it exactly. This validator remains the answer for a thread whose
        observation recorded no total, which is every thread until a Gmail client supplies
        one - it is the honest floor, not a second opinion.
        """
        observed = self.disposition.observed_threads
        per_thread = Counter(thread for thread in observed.values() if thread is not None)
        for source in self.sources:
            seen = per_thread[source.thread_id]
            if source.stated_total < seen:
                raise DispositionInvariantError(
                    f"source {source.thread_id} states the thread holds "
                    f"{source.stated_total} messages, but {seen} distinct messages were "
                    "observed in it. A stated total below the number of messages actually "
                    "seen in that thread makes an incomplete answer report itself complete "
                    "(PART-01, PART-03, R-DISC-011)"
                )
        for entry in self.not_included_entries:
            if entry.stated_total is None:
                continue
            seen = per_thread[entry.thread_id]
            if entry.stated_total < seen:
                raise DispositionInvariantError(
                    f"not-included source {entry.thread_id} states the thread holds "
                    f"{entry.stated_total} messages, but {seen} distinct messages were "
                    "observed in it (PART-01, R-DISC-011)"
                )
        return self

    # -- amendment A6: the named scalars, checked against the observation ---------------

    @model_validator(mode="after")
    def _stated_total_is_the_one_the_observation_stated(self) -> Envelope:
        """A thread's length is what the response that returned it said, exactly (A6).

        The round 7 audit filed `Source.stated_total` and `NotIncludedSource.stated_total`
        as class O - "the fact *is* a fact of the Gmail response, and the sealed observation
        does not record it, so there is nothing to derive it from" - and the best available
        check was a lower bound. A6 seals the value, so the check is now total wherever the
        observation carries it.

        The parameter is **not removed**, and that is worth stating rather than glossing:
        `Source` reads its own `stated_total` in four places (`complete_as_reported`, the
        map accounting, A3's position range, the stub arithmetic), so removing it would
        mean threading the observation through `Source` and `MessageRow` - a second
        structure carrying the ledger's facts alongside the ledger. What A6 buys here is
        that a wrong value is now refused against the response rather than merely bounded.
        """
        facts = self.disposition.observed_thread_facts
        wrong: list[str] = []
        for source in self.sources:
            observed = facts.get(source.thread_id)
            if observed is None or observed.stated_total is None:
                continue
            if source.stated_total != observed.stated_total:
                wrong.append(
                    f"source {source.thread_id} states {source.stated_total} and the "
                    f"observation said {observed.stated_total}"
                )
        for entry in self.not_included_entries:
            observed = facts.get(entry.thread_id)
            if observed is None or observed.stated_total is None or entry.stated_total is None:
                continue
            if entry.stated_total != observed.stated_total:
                wrong.append(
                    f"not-included source {entry.thread_id} states {entry.stated_total} "
                    f"and the observation said {observed.stated_total}"
                )
        if wrong:
            raise DispositionInvariantError(
                "a source states a thread length the response that returned the thread did "
                f"not state: {'; '.join(wrong)}. `stated_total` is what Gmail reported at "
                "fetch time - the only honest reading of it - so a different number is a "
                "claim about a thread this response did not observe (amendment A6, "
                "PART-01, PART-03)"
            )
        return self

    @model_validator(mode="after")
    def _rows_sit_at_the_position_the_observation_put_them_at(self) -> Envelope:
        """A row's index in its thread is read off the response, not stated beside it (A6).

        `MessageRow.position` was the round 7 audit's "clearest class-O case": the row
        states an index into the `threads.get` response's message order, `FetchedIds`
        preserved the order and recorded no index, and A3's `0 <= p < stated_total` was
        therefore the only bound available. A5 of that bound survives - it is what protects
        a thread whose observation carried no positions - and where A6's seal carries one,
        the row must be at it.

        Collapsed runs are held to the same fact through their members: a run declares a
        span of positions and names the ids inside it, so an observed member position
        outside the span is the same defect one disposition to the left (A3, R-ARCH-013).
        """
        observed = self.disposition.observed_positions
        moved: list[str] = []
        for source in self.sources:
            for row in source.messages:
                seen = observed.get(row.id)
                if seen is not None and seen != row.position:
                    moved.append(
                        f"{row.id} is disclosed at position {row.position} and was "
                        f"observed at {seen}"
                    )
            for run in source.collapsed_runs:
                start, end = run.positions
                for member in run.member_ids:
                    seen = observed.get(member)
                    if seen is not None and not start <= seen <= end:
                        moved.append(
                            f"{member} is collapsed into the run spanning {start}-{end} "
                            f"and was observed at position {seen}"
                        )
        if moved:
            raise DispositionInvariantError(
                "disclosed messages are placed at a position other than the one the "
                f"observation put them at: {'; '.join(moved)}. A position is a 0-based "
                "index into the thread's chronological order (amendment A3) and it is a "
                "fact of the response that returned the message, so moving one silently "
                "moves evidence - the failure class this project exists to prevent "
                "(amendment A6, PART-05, R-06)"
            )
        return self

    @model_validator(mode="after")
    def _freshness_stamps_are_the_ones_the_observation_recorded(self) -> Envelope:
        """`fetched_at` is when the call was made, and the call is what records it (A6).

        R-DISC-005 made this parse as an instant with an offset, which stopped
        `fetched_at="not-a-real-timestamp-at-all"`; it did not stop a well-formed instant
        that is not when anything was fetched. A6 seals the stamp at the moment of the
        call, so a source describing an observed thread must carry that stamp.

        `verified_at` is deliberately not checked here: it is a claim about a *later*
        confirmation, which no single observation records, and its ordering against
        `fetched_at` is already total on `Source`.
        """
        facts = self.disposition.observed_thread_facts
        wrong = [
            f"source {source.thread_id} says {source.fetched_at!r}, the observation "
            f"was made at {facts[source.thread_id].fetched_at!r}"
            for source in self.sources
            if source.thread_id in facts
            and facts[source.thread_id].fetched_at is not None
            and source.fetched_at != facts[source.thread_id].fetched_at
        ]
        if wrong:
            raise DispositionInvariantError(
                "a source states a fetch time other than the one the observation recorded: "
                f"{'; '.join(wrong)}. A freshness stamp is a fact of the call, and a "
                "response that can restate it can claim an old answer is new (contract "
                "R-08, amendment A6)"
            )
        return self

    @model_validator(mode="after")
    def _the_per_rung_hit_counts_are_the_ledgers_own(self) -> Envelope:
        """`hit_count_per_rung` is counted from `H`, not stated beside it (R-DISC-011 sweep).

        The report-level check compared this tuple's *length* against `rungs`; nothing
        compared its *values* against anything at all, so a response could say a rung found
        three hits while the ledger held nine, in the one block a reader consults to decide
        whether the numbers add up. Every id in `H` carries the rung whose observation
        admitted it, so the counts are a read of the enumeration.

        Two failures, and they are different statements: a count that disagrees with the
        ledger, and a rung that produced hits and does not appear in `rungs` at all - the
        second is how a retrieval hides a whole route rather than misreporting one.
        """
        counted = self.disposition.hits_per_rung
        report = self.retrieval_report
        listed = set(report.rungs)
        missing = sorted(rung.value for rung in counted if rung is not None and rung not in listed)
        if missing:
            raise DispositionInvariantError(
                f"rungs {missing} admitted ids into H and are absent from the retrieval "
                "report's `rungs`: a route that produced evidence and is not listed is a "
                "route the reader cannot see (EV-01, PART-01)"
            )
        wrong = [
            f"{rung.value}: reported {stated}, ledger counted {counted.get(rung, 0)}"
            for rung, stated in zip(report.rungs, report.hit_count_per_rung, strict=True)
            if counted.get(rung, 0) != stated
        ]
        if wrong:
            raise DispositionInvariantError(
                "hit_count_per_rung disagrees with the hit set it describes: "
                f"{'; '.join(wrong)}. The count is a read of H - every id carries the rung "
                "whose observation admitted it - and a number stated beside the enumeration "
                "instead of taken from it is the shape this codebase refuses (R-DISC-001, "
                "R-DISC-011, EV-01)"
            )
        return self
