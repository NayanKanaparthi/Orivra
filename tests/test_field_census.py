"""The field census, and the claim R-ARCH-024 found false (round 8, part 4).

Round 7's audit said its 187 fields were "enumerated programmatically ... cannot silently
omit a field somebody forgot to look at". Running its published script gives **173**. The
missing 14 belong to `FetchedIds` and `DispositionCertificate`, which are plain classes
holding their state in `__slots__`: the script tested `issubclass(obj, BaseModel)` and
`dataclasses.is_dataclass(obj)`, both false, and skipped each of them without a word.

Three things are asserted here, and they are different claims:

  * the corrected census reaches the audited total, and that total is **pinned**, so a
    field added or removed without updating the audit fails a test rather than drifting;
  * the round 7 blind spot is real and is exactly the two classes named - measured here by
    running the old reading against this tree rather than by repeating R-ARCH's number;
  * a class shape the census cannot read **raises**. That is the property the round 7
    script claimed and did not have, and it is what makes "cannot silently omit" true.
"""

from __future__ import annotations

import dataclasses

import pytest
from pydantic import BaseModel

from mailweave.envelope.disposition import DispositionCertificate, FetchedIds
from tools.field_census import (
    AUDITED_MODULES,
    FieldCensusError,
    census,
    per_module,
)

#: The audited field total for this tree.
#:
#: Round 7's audit reported **187** and its published script produced **173**. The
#: corrected census reproduces 187 exactly against the round 7 field set - the missing 14
#: are `FetchedIds`'s 7 and `DispositionCertificate`'s 7 - and this tree is 187 plus
#: amendment A6's changes: **+14** sealed and derived scalars (5 constructor parameters and
#: 2 per-message fields on `HitOrigin`, 4 on the new `ObservedThread`, 2 more certificate
#: parameters, 1 more ledger accumulator) and **-2** caller-supplied parameters removed
#: (`MessageRow.internal_date`, `Source.history_id`), for 199.
#:
#: Round 13 moves it to **207**: `_CertifiedFacts`'s 8 fields, which are R-SEC-046's fix.
#: They are not new facts and not new caller-supplied parameters - `DispositionCertificate`'s
#: constructor still takes the same nine - they are the certificate's own conclusions moved
#: *off* the object into `_CERTIFIED`, where a copy of the certificate cannot carry them and
#: an attribute write cannot rewrite them. The audit sees a new place fields live, which is
#: exactly what it is for; all 8 are derived, class D, and none is caller-supplied.
#:
#: Round 14 moves it to **208**: `_CertifiedFacts.withheld_seal`, which is R-ARCH-032's fix
#: for the one value in that record whose type this module does not own. Derived, class D,
#: not caller-supplied. `ObservedThread` and `_CertifiedFacts` became named tuples in the same
#: round and the census had to be extended to read one - which it demanded rather than
#: skipping, exactly as it was written to.
#:
#: Round 18 moves it to **213**: mailbox provenance on every disclosed row (OD-5, A9-A1).
#: `MessageRow.mailbox` is one field; `MailboxProvenance` is four - `observed` and `labels`,
#: which a caller supplies because they are what the observation stated, and `regions` and
#: `outside_the_default_mailbox`, which are computed from `labels` and are therefore class D.
#: The census reads a computed field as a field, which is what makes the split visible here:
#: the point of the schema change is that the two branchable values are **derived** from the
#: observation rather than accepted beside it, and a total that counted only constructor
#: parameters would have hidden exactly that.
#:
#: Round 20 moves it to **231**: WS-05's structural schema. `MessageRow` gains `linkage` and
#: `reply_parent_id` (2); `Source` gains `participants` and `structure` (2);
#: `ThreadParticipant` is 7 caller-supplied fields plus the computed `wrote_here` (8); and
#: `ThreadStructureReport` is 6. Every caller-supplied one of those is a fact of the
#: `threads.get` response the row came out of, and the two that a caller could otherwise
#: contradict - "did this address write here" and the linked/unlinked counts - are derived
#: instead: `wrote_here` is computed from the role lists beside it, and `Source` re-counts
#: `linked`/`unlinked` off the rows rather than accepting the summary.
#:
#: Round 21 moves it to **236**, five fields in two places and both of them a claim that was
#: being made without a field to carry it. `MessageRow` gains `can_be_a_parent` (1): AD D.4a's
#: compensating fact, which `reply_tree` computed correctly and nothing outside that module
#: could read, so a message no reply can ever name was byte-identical on the wire to an
#: ordinary reply (R-RETR-054). And `ReplyParentAmbiguous` is a new `ReasonKind` with three
#: parameters beside its discriminator (4): one `Message-ID` carried by messages in two
#: threads used to produce two rows each disclosed as *the* parent of one child, and the
#: count of how many messages the identifier really named is what makes the row's own
#: statement true (R-RETR-050).
#:
#: Round 23 moves it to **243**, seven fields in two new `ReasonKind` variants, and both are
#: a claim WS-11 makes that no field carried. `QueryScoredFill` is three (`kind`,
#: `components`, `score`): a row the E4 fill put in the payload has to name **which**
#: published components fired and what they summed to, or DISC-01's "each inclusion carries
#: a query-specific reason" is satisfied by a sentence rather than by a mechanism a reader
#: can recompute. `FloorPromoted` is four (`kind`, `relation`, `anchor_id`, `dependence`):
#: OD-3 splits the reply-chain floor into absolute membership and earned depth, and without
#: `dependence` on the wire a promoted floor member is byte-identical to one the promotion
#: rule refused - which is the whole of the distinction the round is about.
#:
#: Round 24 moves it to **249**, six fields in one new model and one new field on
#: `MessageRow`, and both exist because WS-15 puts a tool on the surface whose whole result
#: had nowhere to live. `AttachmentMetadata` is five (`filename`, `mime_type`, `size`,
#: `part_id`, `attachment_id`): B-04 contracts attachment **metadata** as a disclosed fact
#: and `mailweave_get_attachment` is the tool that asks for it, so without this model the
#: tool would have had to serialise itself beside the envelope - a second wire path, which
#: is the one thing rounds 13-14 closed. `MessageRow.attachments` is the sixth: the parts
#: tree is a fact of the carrying message, so it hangs off the message's row rather than
#: off a block of its own, and `mailweave_get_messages` at body depth carries it for free.
#: Every one of the six is caller-supplied and every one is a projection of
#: `content.mime.AttachmentRow`, which the content pipeline has produced since round 8 with
#: no reader on the wire.
#:
#: A change to any model in the audited layers moves this, which is the point: the number a
#: review document quotes is now a number a test holds.
#: Round 29, R-MCP-033: +18. `WithheldGroup` (5) and `OmissionSummary` (5, with `bound`) on
#: the wire; `NotIncludedBlock` (2) with `why` moved onto it from `NotIncludedSource` (-1);
#: `Envelope.withheld_groups`/`omission` (2); `_CertifiedFacts.withheld_groups`/`grouped_ids`
#: and the disposition side of the same change (5).
#: The repair pass after the v0.1 review: +9. `WithheldTail` (5) on the wire; `Envelope.
#: withheld_tail` (1); `_CertifiedFacts.withheld_tail` and the ledger's `_tail_recovery` and
#: the disposition side of the same change (3).
#: Round 31, WS-14's INJ-05: +6. `SenderAuthentication` (2: `recorded`, `oversize` - there is
#: deliberately no `observed`, because `MessageRow.headers_observed` already states it and a
#: second spelling of one fact is what this census exists to notice); `MessageRow.
#: headers_observed`/`reply_to_differs`/`authentication` (3); `ThreadParticipant.display_names`
#: (1, thread-level rather than per row, because a `To:` list is unbounded and a thread's
#: distinct display names are exactly measurable).
#: The navigation redesign (2026-09-14): +10. `Continuation` (6: `scope`, `thread_id`,
#: `positions`, `message_ids`, `remaining`, `affordance`); `Envelope.continuations` (1);
#: `Source.page`/`page_size`/`pages` (3). No disposition-side change: a continuation is not a
#: disposition, and the ledger's `withdraw_notes` is a method, not a field.
#: The integration repair of 2026-09-15 (R-M2-094/096): +3. `WithheldGroup.rank` and
#: `NotIncludedSource.rank` (2, optional, the retrieval rank the entry is written in); the
#: ledger's `_ranks` (1), the producer-filed ranks those read. The group arrangement itself
#: (`envelope.grouping`) is a function, not a field.
#: A16, the scoped separation of accounting from evidence (2026-09-15): +4. `AdmissionRoute`
#: (3: `endpoint`, `rung`, `query` - every observation that returned an id, as against
#: `HitOrigin`'s first admission) and the ledger's `_routes` (1) that accumulates them. The
#: predicate over them (`assemble.pool_listed_only`) is a function, not a field, and `H` is
#: unchanged: these record how ids were reached, never which ids there are.
#: Per-message attribution (2026-09-21): +5. `Attribution` (4: `provenance`, `address`,
#: `display_name`, `stated_addresses`) and `MessageRow.attribution` (1). The `From` header's
#: addr-spec and fenced display name, per row, with where they came from stated on every row
#: - the fact the exploratory runs of 2026-09-21 had to read out of body text because no row
#: carried it. `internal_date_provenance` is **not** a field: like `internal_date` it is
#: written onto the wire from the certificate by `Envelope`, and has no reader in the model.
AUDITED_FIELD_TOTAL = 315


def test_the_census_reaches_the_audited_total() -> None:
    """The claim, as a number. 187 is the round 7 audit's own figure."""
    records = census()
    assert len(records) == AUDITED_FIELD_TOTAL, (
        f"the census found {len(records)} fields against an audited total of "
        f"{AUDITED_FIELD_TOTAL}; per module {per_module(records)}"
    )


def test_the_census_reads_every_audited_module() -> None:
    counts = per_module(census())
    assert set(counts) == set(AUDITED_MODULES)
    assert all(count > 0 for count in counts.values())


def test_the_two_classes_round_sevens_script_could_not_see_are_now_counted() -> None:
    """R-ARCH-024 by name: the 14 hand-added fields, found by the enumerator itself."""
    owners = {record.owner for record in census()}
    assert {"FetchedIds", "DispositionCertificate"} <= owners
    seal = [record.field for record in census() if record.owner == "FetchedIds"]
    certificate = [record.field for record in census() if record.owner == "DispositionCertificate"]
    assert "ids" in seal and "endpoint" in seal
    assert "token" in certificate and "hit_count" in certificate


def test_the_round_seven_reading_misses_exactly_the_shapes_it_cannot_read() -> None:
    """The gap, measured rather than quoted: this is what the published script did.

    The old script's two type tests are reproduced verbatim here and run against *this*
    tree, and the classes they cannot read are computed the same way rather than listed - so
    the assertion stays a statement about the enumerator when the tree changes shape, which
    it did in round 14 when two records became named tuples (R-ARCH-032). Naming the two
    plain classes here, as this test used to, would have made it fail for the *right* reason
    with the *wrong* message: it would have said the blind spot moved when what moved was the
    code the blind spot covers.
    """
    import inspect
    from importlib import import_module

    old_reading = 0
    unreadable_owners: set[str] = set()
    for module_name in AUDITED_MODULES:
        module = import_module(module_name)
        for obj in vars(module).values():
            if not (inspect.isclass(obj) and obj.__module__ == module_name):
                continue
            if issubclass(obj, BaseModel):
                old_reading += len(obj.model_fields) + len(obj.model_computed_fields)
            elif dataclasses.is_dataclass(obj):
                old_reading += len(dataclasses.fields(obj))
            else:
                unreadable_owners.add(obj.__qualname__)

    records = census()
    invisible = [record for record in records if record.owner in unreadable_owners]
    assert len(records) - old_reading == len(invisible), (
        "the corrected census differs from the round 7 reading by something other than "
        "the classes that reading cannot see"
    )
    assert old_reading == len(records) - len(invisible)
    # R-ARCH-024's own two, plus the two records round 14 made immutable. Every one of them
    # holds fields; the enums in `unreadable_owners` hold none and contribute nothing.
    assert {record.owner for record in invisible} == {
        "DispositionCertificate",
        "FetchedIds",
        "ObservedThread",
        "_CertifiedFacts",
    }


def test_a_class_shape_the_census_cannot_read_raises_rather_than_being_skipped() -> None:
    """The planted violation: silence is the defect, so the census must not be silent."""
    import types

    unreadable = types.new_class("UnreadableShape", (object,), {})
    module = types.ModuleType("mailweave.envelope._census_probe")
    unreadable.__module__ = module.__name__
    module.UnreadableShape = unreadable  # type: ignore[attr-defined]

    import sys

    sys.modules[module.__name__] = module
    try:
        with pytest.raises(FieldCensusError) as caught:
            census((module.__name__,))
        assert "UnreadableShape" in str(caught.value)
    finally:
        del sys.modules[module.__name__]


def test_the_seal_and_the_certificate_are_read_from_their_constructors() -> None:
    """The reading used for a plain class is the caller-facing one the audit tabulates."""
    seal = {record.field for record in census() if record.owner == "FetchedIds"}
    assert "_consumed" not in seal, (
        "a private latch no caller can state is not a field the audit asks about"
    )
    assert FetchedIds.__slots__  # the state is in slots; the census reads the constructor
    certificate = {record.field for record in census() if record.owner == "DispositionCertificate"}
    assert "token" in certificate
    assert DispositionCertificate.__slots__
    shapes = {
        record.shape
        for record in census()
        if record.owner in {"FetchedIds", "DispositionCertificate"}
    }
    assert shapes == {"constructor-parameter"}
