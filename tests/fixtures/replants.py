"""The replant manifest for rounds 18-20, and the harness that runs it in a scratch tree.

**A fix no test defends is a fix the next round silently undoes.** R-RETR established that
round 17's repairs for R-RETR-026 and R-RETR-028 were *unasserted*: planting the defects back
left all 2,248 tests green, so both could have been reverted by an unrelated refactor without
anything going red. That is a finding about the suite rather than about either fix, and the
answer to it is not two more tests - it is a manifest, executed, of every behaviour this round
changed together with the test that catches its removal.

Three properties make the run mean something, and each of them is a way a reintroduction
harness has silently tested the wrong tree in this project before:

  * **every anchor is asserted to match exactly once** before anything is written. An anchor
    that matches zero times plants nothing and reports MISSED for a defect that was never
    introduced; an anchor that matches twice plants more than the manifest describes;
  * **every file is asserted to have changed** after the write, by content hash;
  * **the scratch tree is asserted to be the tree under test**. `mailweave.__file__` and
    `tests.__file__` must both resolve inside the scratch copy and must both *not* resolve
    into the working tree - the venv installs `mailweave` as an editable `.pth`, so a
    subprocess with a merely-prepended `PYTHONPATH` can import the real package and report
    every plant as CAUGHT while changing nothing. Three separate agents have hit that.

The manifest is data rather than a script so that `tests/test_replants.py` can pin the
anchors against the working tree on every run - a manifest whose anchors have rotted is a
manifest that reports MISSED for free - while the full plant-and-run pass is driven from
`run_replants`, which needs a scratch tree and a subprocess.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

#: The working tree this manifest describes.
TREE = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Replant:
    """One behaviour this round changed, written back out, and the test that catches it."""

    name: str
    #: What the finding was, in one line, so a MISSED row says what is undefended.
    behaviour: str
    path: str
    anchor: str
    replacement: str
    #: The test that must fail when the behaviour is removed. Named, so a plant caught by
    #: something unrelated is not counted as defended.
    caught_by: tuple[str, ...]


#: Every behaviour rounds 18, 19 and 20 changed, plus the two *guard-strength* plants R-RETR-031
#: asks for by name. R1-R16 are round 18's, re-anchored where round 19 moved the code they
#: describe - `declares_the_search_region` now lives beside the registry it reads, so R1 plants
#: round 17's polarity defect into its new home rather than into a function that no longer
#: exists. R17-R28 are round 19's, and R29-R41 are round 20's - WS-05's reply tree, its
#: chronological ordering, its participant index and its structural expansion. R42-R57 are
#: round 21's: the seven claims R-RETR found wider than the code, and WS-06's handles.
#: R58-R66 are round 22's - amendment A10's two rules, and WS-10's budgets, stopping
#: rules, mid-rung timeout contract and three-way outcome.
#:
#: R42-R48 exist because round 20's manifest had no entry for any of them, which is how
#: R-RETR could mutate `Link.evidence` two different ways and the mention scanner's input
#: one way and get a green suite each time. A manifest that defends the reconstruction and
#: not the claims made about it defends half of what the round changed.
#:
#: One entry per behaviour, not one per edit: the question the manifest answers is
#: "can this be removed without anything going red?", and an edit no caller reaches is not a
#: behaviour.
#:
#: R15 and R16 are different in kind from the rest and are here for that reason. They do not
#: remove a round-18 behaviour; they plant the two shapes the round-17 invariant test was
#: *green* on - a probe that narrows into a region nobody named, and a probe that declares a
#: widening and then restricts - so the claim "the invariant is enforced once, by one
#: membership test" is executed rather than asserted. The round-17 version of that claim was
#: false and the finding was found by a reviewer planting exactly these.
REPLANTS: tuple[Replant, ...] = (
    Replant(
        name="R1-negated-region-is-not-a-region",
        behaviour=(
            "R-RETR-026: a negated location is classified as an ordinary negation, so a "
            "probe may drop it and the search leaves the region the caller declared"
        ),
        path="server/src/mailweave/query/operators.py",
        anchor=(
            "    name = operator_of(fragment)\n"
            "    return (\n"
            "        name is not None\n"
            "        and KIND_BY_OPERATOR[name] is OperatorKind.REGION\n"
            "        and bool(matchable_content_of(fragment))\n"
            "    )\n"
        ),
        replacement=(
            "    name = operator_of(fragment)\n"
            "    return (\n"
            "        name is not None\n"
            "        and KIND_BY_OPERATOR[name] is OperatorKind.REGION\n"
            "        and bool(matchable_content_of(fragment))\n"
            "        and not operator_token(fragment).startswith(NEGATION_PREFIX)\n"
            "    )\n"
        ),
        caught_by=(
            "tests/test_lexical_ladder.py::"
            "test_a_query_that_named_a_region_is_never_widened_out_of_it",
        ),
    ),
    Replant(
        name="R2-l3-widens-out-of-a-declared-region",
        behaviour=(
            "OD-5 point 2: the whole-mailbox step runs over a query that named a region, "
            "so an inbox-scoped or spam-excluding query is answered from everywhere"
        ),
        path="server/src/mailweave/retrieval/ladder.py",
        anchor="        if region_declarations_of(parsed):\n",
        replacement="        if False:\n",
        caught_by=(
            "tests/test_lexical_ladder.py::"
            "test_a_query_that_named_a_region_is_never_widened_out_of_it",
        ),
    ),
    Replant(
        name="R3-region-derivation-drops-negations",
        behaviour=(
            "R-RETR-026 at the derivation: the region carried onto every probe is the "
            "positive fragments only, which is round 17's rule verbatim"
        ),
        path="server/src/mailweave/query/analysis.py",
        anchor="        if declares_the_search_region(fragment)\n",
        replacement=(
            "        if declares_the_search_region(fragment)\n"
            "        and not fragment.startswith(NEGATION_PREFIX)\n"
        ),
        caught_by=(
            "tests/test_lexical_ladder.py::"
            "test_every_probe_the_ladder_composes_searches_the_region_the_query_named",
        ),
    ),
    Replant(
        name="R4-relaxation-drops-the-region",
        behaviour=(
            "OD-5 point 3: L2 relaxes the region away, so a probe searches a region the "
            "caller did not name and calls it a declared relaxation"
        ),
        path="server/src/mailweave/retrieval/ladder.py",
        anchor="        if search_region_of(kept) != search_region_of(parsed.constraints):\n",
        replacement="        if False:\n",
        caught_by=(
            "tests/test_lexical_ladder.py::"
            "test_every_probe_the_ladder_composes_searches_the_region_the_query_named",
        ),
    ),
    Replant(
        name="R5-l0-claims-the-whole-constraint",
        behaviour=(
            "R-RETR-028: L0 reports the whole constraint from one fragment of it, and D.3 "
            "rule 1b then halts the ladder on the over-claim"
        ),
        path="server/src/mailweave/retrieval/ladder.py",
        anchor="            enforced=constraints_carried_whole(query, parsed.constraints),\n",
        replacement="            enforced=parsed.constraint_names,\n",
        caught_by=(
            "tests/test_lexical_ladder.py::"
            "test_a_probe_enforces_only_the_constraints_its_own_q_carries_whole",
            "tests/test_region_and_provenance_round18.py::"
            "test_a_route_that_executed_one_fragment_does_not_report_the_constraint_enforced",
        ),
    ),
    Replant(
        name="R6-enforcement-credits-a-fragment",
        behaviour=(
            "R-RETR-028 at the derivation: a constraint counts as carried when *any* of "
            "its fragments is in the q, which is the over-claim for every rung at once"
        ),
        path="server/src/mailweave/query/analysis.py",
        anchor=(
            "        and all(\n"
            "            all(carriage_token(piece) in carried "
            "for piece in query_tokens(fragment))\n"
            "            for fragment in constraint.fragments\n"
            "        )\n"
        ),
        replacement=(
            "        and any(\n"
            "            all(carriage_token(piece) in carried "
            "for piece in query_tokens(fragment))\n"
            "            for fragment in constraint.fragments\n"
            "        )\n"
        ),
        caught_by=(
            "tests/test_lexical_ladder.py::"
            "test_a_probe_enforces_only_the_constraints_its_own_q_carries_whole",
        ),
    ),
    Replant(
        name="R7-negated-phrase-is-searched-for",
        behaviour=(
            "R-RETR-027: the phrase constraint renders without its polarity, so a phrase "
            "the caller excluded is executed as a phrase search and reported enforced"
        ),
        path="server/src/mailweave/query/analysis.py",
        anchor=(
            '                    f\'{NEGATION_PREFIX if negated else ""}"{phrase}"\' '
            "for phrase, negated in phrases\n"
        ),
        replacement="                    f'\"{phrase}\"' for phrase, negated in phrases\n",
        caught_by=(
            "tests/test_region_and_provenance_round18.py::"
            "test_a_negated_phrase_is_excluded_rather_than_searched_for",
            "tests/test_query_analysis.py::"
            "test_a_quoted_phrase_containing_a_colon_is_a_phrase_not_an_unknown_operator",
        ),
    ),
    Replant(
        name="R8-predicates-split-a-quoted-value",
        behaviour=(
            "round 18's own finding: the predicate family whitespace-splits a quoted "
            "operator value, so a negated participant with a two-word value becomes a "
            "whole-mailbox decomposition probe"
        ),
        path="server/src/mailweave/constants.py",
        anchor=("    tokens: list[str] = []\n    current: list[str] = []\n    in_quotes = False\n"),
        replacement="    return query.split()\n    tokens: list[str] = []\n",
        caught_by=(
            "tests/test_region_and_provenance_round18.py::"
            "test_a_negated_operator_with_a_quoted_value_is_not_a_probe_of_its_own",
        ),
    ),
    Replant(
        name="R9-provenance-is-not-the-observed-labels",
        behaviour=(
            "OD-5 point 1: the row's mailbox provenance stops being a projection of the "
            "message's own labels, so a spam result is indistinguishable from an inbox one"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        # Re-anchored in round 20: WS-05 moved the row-building loop out of `assemble` into
        # `_rows_of`, one indent level shallower. The behaviour is the same and the plant is
        # the same; an anchor that no longer matches would report this defended for free,
        # which is what `test_every_replant_anchor_matches_exactly_once_in_the_tree` exists
        # to catch and did.
        anchor=(
            "        provenance = (\n"
            "            MailboxProvenance.unobserved()\n"
            "            if message.label_ids is None\n"
            "            else MailboxProvenance.of(message.label_ids)\n"
            "        )\n"
        ),
        replacement="        provenance = MailboxProvenance.of(())\n",
        caught_by=(
            "tests/test_region_and_provenance_round18.py::"
            "test_every_disclosed_row_states_the_region_its_own_labels_place_it_in",
        ),
    ),
    Replant(
        name="R10-region-derivation-from-labels-is-empty",
        behaviour=(
            "OD-5 point 1 at the derivation: no label set names a region, so every row "
            "reports itself as ordinary mail"
        ),
        path="server/src/mailweave/constants.py",
        anchor="    stated = frozenset(label_ids)\n",
        replacement="    stated = frozenset()\n",
        caught_by=(
            "tests/test_region_and_provenance_round18.py::"
            "test_every_disclosed_row_states_the_region_its_own_labels_place_it_in",
        ),
    ),
    Replant(
        name="R11-zero-evidence-report-offers-nothing",
        behaviour=(
            "R-RETR-032: the report class mints no affordance, so ROUTE-01's fifth "
            "acceptance item is absent from every zero-evidence response"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor="        offers = report_affordances(run.parsed)\n",
        replacement="        offers: tuple[Affordance, ...] = ()\n",
        caught_by=(
            "tests/test_region_and_provenance_round18.py::"
            "test_a_zero_evidence_report_offers_the_call_that_would_reach_a_rung",
        ),
    ),
    Replant(
        name="R12-content-filter-is-one-category-again",
        behaviour=(
            "R-RETR-029's derivable half: the content predicate removes format characters "
            "only, so a lone combining mark or a control character is a searchable term"
        ),
        path="server/src/mailweave/constants.py",
        anchor=(
            "NON_MATCHING_CHARACTER_CATEGORIES: Final[frozenset[str]] = frozenset(\n"
            '    {FORMAT_CHARACTER_CATEGORY, "Cc", "Cs", "Co", "Cn", '
            '"Zs", "Zl", "Zp", "Mn", "Me"}\n'
            ")\n"
        ),
        replacement=(
            "NON_MATCHING_CHARACTER_CATEGORIES: Final[frozenset[str]] = frozenset(\n"
            "    {FORMAT_CHARACTER_CATEGORY}\n"
            ")\n"
        ),
        caught_by=(
            "tests/test_region_and_provenance_round18.py::"
            "test_a_token_of_marks_controls_or_separators_names_nothing_to_match",
        ),
    ),
    Replant(
        name="R13-double-crashes-on-a-calendar-invalid-date",
        behaviour=(
            "R-RETR-033: the test double raises an uncaught ValueError for a date whose "
            "shape it matched, so no end-to-end statement about that class is establishable"
        ),
        path="tests/fixtures/mailbox.py",
        anchor=(
            "    try:\n"
            "        return epoch_ms(year, month, day, hour=0)\n"
            "    except ValueError:\n"
            "        return None\n"
        ),
        replacement="    return epoch_ms(year, month, day, hour=0)\n",
        caught_by=(
            "tests/test_region_and_provenance_round18.py::"
            "test_a_calendar_invalid_date_is_carried_to_gmail_and_the_double_does_not_crash",
        ),
    ),
    Replant(
        name="R15-a-unit-narrows-into-a-region-nobody-named",
        behaviour=(
            "R-RETR-031's narrowing half: a decomposition probe adds a location the query "
            "never wrote, which the round-17 invariant test could not see at all"
        ),
        path="server/src/mailweave/query/analysis.py",
        anchor='            fragment=f"{carried} {unit.fragment}",\n',
        replacement='            fragment=f"in:inbox {carried} {unit.fragment}",\n',
        caught_by=(
            "tests/test_lexical_ladder.py::"
            "test_every_probe_the_ladder_composes_searches_the_region_the_query_named",
        ),
    ),
    Replant(
        name="R16-a-widening-probe-restricts-after-declaring",
        behaviour=(
            "R-RETR-031's L3 exemption: a probe declares a widening and conjoins a "
            "narrowing location, which the round-17 `continue` waved through"
        ),
        path="server/src/mailweave/retrieval/ladder.py",
        anchor='        broadened = " ".join([ANYWHERE_OPERATOR, *fragments])\n',
        replacement='        broadened = " ".join([ANYWHERE_OPERATOR, "in:inbox", *fragments])\n',
        caught_by=(
            "tests/test_lexical_ladder.py::"
            "test_every_probe_the_ladder_composes_searches_the_region_the_query_named",
        ),
    ),
    Replant(
        name="R14-carriage-strips-grouping-punctuation",
        behaviour=(
            "R-RETR-020 through the new derivation: a member of L3's `{from:x to:x}` "
            "disjunction reads as the constraint, so a widened participant is enforced"
        ),
        path="server/src/mailweave/constants.py",
        anchor='    normalised = unicodedata.normalize("NFKC", token).casefold()\n    negated =',
        replacement=(
            "    normalised = (\n"
            '        unicodedata.normalize("NFKC", token)\n'
            "        .strip(QUERY_GROUPING_PUNCTUATION)\n"
            "        .casefold()\n"
            "    )\n"
            "    negated ="
        ),
        caught_by=(
            "tests/test_lexical_ladder.py::"
            "test_a_probe_enforces_only_the_constraints_its_own_q_carries_whole",
        ),
    ),
    Replant(
        name="R17-region-predicate-is-a-prefix-again",
        behaviour=(
            "R-RETR-036: the region asymmetry is decided from one lexical prefix instead of "
            "the operator's registered kind, so a region operator not spelled `in:` is a "
            "filter and a newly registered one is dropped from every probe"
        ),
        path="server/src/mailweave/query/operators.py",
        anchor="        and KIND_BY_OPERATOR[name] is OperatorKind.REGION\n",
        replacement=(
            '        and operator_token(fragment).lstrip(NEGATION_PREFIX).startswith("in:")\n'
        ),
        caught_by=(
            "tests/test_region_kind_round19.py::"
            "test_the_region_predicate_reads_what_an_operator_does_not_how_it_is_spelled",
            "tests/test_region_kind_round19.py::"
            "test_a_label_that_names_a_system_mailbox_is_a_region_declaration",
        ),
    ),
    Replant(
        name="R18-the-broadening-gate-cannot-see-an-unparsed-region",
        behaviour=(
            "R-RETR-035/037: the region a query declared is read from its parsed constraints "
            "only, so a grouped or fullwidth region declaration is invisible to the gate and "
            "the published whole-mailbox step runs over a query that excluded a region"
        ),
        path="server/src/mailweave/query/analysis.py",
        anchor=(
            "    return (\n"
            "        *search_region_of(parsed.constraints),\n"
            "        *(token for token in query_tokens(parsed.raw) "
            "if declares_the_search_region(token)),\n"
            "    )\n"
        ),
        replacement="    return search_region_of(parsed.constraints)\n",
        caught_by=(
            "tests/test_region_kind_round19.py::"
            "test_a_region_the_parse_could_not_carry_still_stops_the_broadening",
        ),
    ),
    Replant(
        name="R19-a-group-holding-one-operator-is-not-read",
        behaviour=(
            "R-RETR-035: a token carrying Gmail's grouping punctuation is passthrough "
            "whatever it says, so a grouped region declaration never becomes a constraint"
        ),
        path="server/src/mailweave/query/operators.py",
        anchor="            sole = _sole_operator_of_a_group(raw)\n",
        replacement="            sole = None\n",
        caught_by=(
            "tests/test_region_kind_round19.py::"
            "test_a_grouped_region_declaration_is_the_operator_it_groups",
        ),
    ),
    Replant(
        name="R20-a-label-is-registered-as-a-filter",
        behaviour=(
            "R-RETR-036's reachable half: `label:` naming a system mailbox is read as a "
            "filter, so a query excluding it is relaxed and widened into the region"
        ),
        path="server/src/mailweave/query/operators.py",
        anchor="        OperatorName.LABEL: OperatorKind.REGION,\n",
        replacement="        OperatorName.LABEL: OperatorKind.ATTRIBUTE,\n",
        caught_by=(
            "tests/test_region_kind_round19.py::"
            "test_a_label_that_names_a_system_mailbox_is_a_region_declaration",
            "tests/test_region_kind_round19.py::"
            "test_what_the_conservative_reading_costs_is_declared_and_one_call_from_recovered",
        ),
    ),
    Replant(
        name="R21-stub-rows-lose-their-provenance",
        behaviour=(
            "R-RETR-038 (plant X2): only hit rows carry provenance, so a spam reply carried "
            "into an ordinary thread by the thread map reports itself as unobserved"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        # Re-anchored in round 20 with R9, for the same reason: the loop moved into
        # `_rows_of` and the row is built from `message_id` rather than `message.id`.
        anchor=(
            "                constraint_coverage=coverage(run, message_id) if is_hit else (),\n"
            "                mailbox=provenance,\n"
        ),
        replacement=(
            "                constraint_coverage=coverage(run, message_id) if is_hit else (),\n"
            "                mailbox=provenance if is_hit else MailboxProvenance.unobserved(),\n"
        ),
        caught_by=(
            "tests/test_region_kind_round19.py::"
            "test_a_stub_row_states_the_region_its_own_labels_place_it_in",
        ),
    ),
    Replant(
        name="R22-provenance-is-optional-on-a-row",
        behaviour=(
            "R-RETR-038 (plant X1): `MessageRow.mailbox` is defaulted rather than required, "
            "so OD-5's 'every row' is a comment beside a declaration"
        ),
        path="server/src/mailweave/envelope/wire.py",
        anchor="    mailbox: MailboxProvenance\n",
        replacement="    mailbox: MailboxProvenance = MailboxProvenance(observed=False)\n",
        caught_by=(
            "tests/test_region_kind_round19.py::"
            "test_a_row_without_a_mailbox_provenance_is_not_representable",
        ),
    ),
    Replant(
        name="R23-an-absent-label-set-is-a-stated-empty-one",
        behaviour=(
            "R-RETR-039: `labelIds` defaults to the empty tuple, so a response that stated "
            "no labels is indistinguishable from one that stated none and every row reports "
            "`observed: true`"
        ),
        path="server/src/mailweave/gmail/models.py",
        anchor='    label_ids: tuple[str, ...] | None = Field(default=None, alias="labelIds")\n',
        replacement='    label_ids: tuple[str, ...] = Field(default=(), alias="labelIds")\n',
        caught_by=(
            "tests/test_region_kind_round19.py::"
            "test_a_response_that_observed_no_labels_says_so_and_states_no_negative",
        ),
    ),
    Replant(
        name="R24-an-unobserved-provenance-reads-as-a-negative",
        behaviour=(
            "R-RETR-039 at the field a caller branches on: `outside_the_default_mailbox` is "
            "false rather than absent for a row whose labels nothing observed"
        ),
        path="server/src/mailweave/envelope/wire.py",
        anchor=(
            "        regions = self.regions\n"
            "        return None if regions is None else bool(regions)\n"
        ),
        replacement="        return bool(self.regions)\n",
        caught_by=(
            "tests/test_region_kind_round19.py::"
            "test_the_unobserved_state_is_on_the_wire_as_an_absence",
        ),
    ),
    Replant(
        name="R25-a-scoped-zero-evidence-response-offers-nothing",
        behaviour=(
            "R-RETR-040/041: the recall the unrelaxable region costs is reported and never "
            "offered, so a scoped query that found nothing names untried drops with no way on"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor=(
            "    recovered = without_the_region_it_named(run.parsed)\n"
            "    if recovered is None:\n"
            "        return ()\n"
        ),
        replacement="    return ()\n    recovered = without_the_region_it_named(run.parsed)\n",
        caught_by=(
            "tests/test_region_kind_round19.py::"
            "test_a_scoped_query_that_found_nothing_carries_the_call_that_drops_the_scope",
        ),
    ),
    Replant(
        name="R26-an-offer-undoes-an-exclusion-the-caller-wrote",
        behaviour=(
            "I-4 the wrong way round: the response offers the caller a call into the region "
            "they excluded, which A.7 L3 then widens to the whole mailbox"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor=(
            "    if any("
            "operator_token(fragment).startswith(NEGATION_PREFIX) for fragment in fragments):\n"
            "        return None\n"
        ),
        replacement="    if False:\n        return None\n",
        caught_by=(
            "tests/test_region_kind_round19.py::"
            "test_nothing_offered_would_undo_an_exclusion_the_caller_wrote",
        ),
    ),
    Replant(
        name="R27-a-degrouping-offer-inverts-a-negated-region",
        behaviour=(
            "R-RETR-035 through the affordance: stripping the grouping off a negated group "
            "asserts its second member, so the offer names the region the caller excluded"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor="    if parsed.passthrough and not region_declarations_of(parsed):\n",
        replacement="    if parsed.passthrough:\n",
        caught_by=(
            "tests/test_region_kind_round19.py::"
            "test_nothing_offered_would_undo_an_exclusion_the_caller_wrote",
        ),
    ),
    Replant(
        name="R28-the-offer-that-reaches-no-rung-comes-back",
        behaviour=(
            "R-RETR-040: a query naming only where to look is offered the same refused query "
            "with an empty `terms` slot, which sends no request when it is executed"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor="    return tuple(offers)\n",
        replacement=(
            "    region = region_declarations_of(parsed)\n"
            "    if region and not any(\n"
            "        selects_something(f) for c in parsed.constraints for f in c.fragments\n"
            "    ):\n"
            "        offers.append(\n"
            '            Affordance(tool=ToolName.SEARCH, args={"query": " ".join(region), '
            '"terms": []})\n'
            "        )\n"
            "    return tuple(offers)\n"
        ),
        caught_by=(
            "tests/test_region_and_provenance_round18.py::"
            "test_a_report_with_nothing_to_offer_offers_nothing",
        ),
    ),
    # --- round 20 (WS-05: the thread map) -------------------------------------------------
    #
    # Same rule as above: one entry per *behaviour*, each named against the test that must
    # go red when it is removed. The reply-tree entries are deliberately the shapes a naive
    # JWZ implementation gets wrong rather than the ones a fixture happened to cover -
    # re-parenting, a cycle, a duplicate `Message-ID` - because that is where this round's
    # claims live.
    Replant(
        name="R29-an-orphan-is-re-parented-to-the-first-message-of-the-thread",
        behaviour=(
            "C-02a / STR-01's own named dumbest max: a message whose reply headers name a "
            "parent this thread does not hold is attached to a message it never named, and "
            "the guess is reported as a link"
        ),
        path="server/src/mailweave/structure/reply_tree.py",
        anchor=(
            "        drafts[view.message_id] = Link(\n"
            "            message_id=view.message_id,\n"
            "            parent_id=None,\n"
            "            linkage=Linkage.AMBIGUOUS_PARENT if ambiguous else "
            "Linkage.UNRESOLVED_PARENT,\n"
            "            evidence=nearest,\n"
            "            can_be_a_parent=parentable,\n"
            "        )\n"
        ),
        replacement=(
            "        adjacent = next(\n"
            "            (o.message_id for o in ordered if o.message_id != view.message_id),\n"
            "            None,\n"
            "        )\n"
            "        drafts[view.message_id] = Link(\n"
            "            message_id=view.message_id,\n"
            "            parent_id=adjacent,\n"
            "            linkage=Linkage.IN_REPLY_TO if adjacent else "
            "Linkage.UNRESOLVED_PARENT,\n"
            "            evidence=nearest,\n"
            "            can_be_a_parent=parentable,\n"
            "        )\n"
        ),
        caught_by=(
            "tests/test_thread_map_round20.py::"
            "test_no_row_is_attached_to_a_parent_its_own_headers_do_not_name",
            "tests/test_thread_map_round20.py::"
            "test_every_reply_tree_shape_keeps_the_four_properties_that_make_it_not_a_guess",
        ),
    ),
    Replant(
        name="R30-a-reply-cycle-is-kept-instead-of-refused",
        behaviour=(
            "the reply forest stops being a forest: a cycle in the headers is followed, so "
            "walking parents upward from a member never terminates"
        ),
        path="server/src/mailweave/structure/reply_tree.py",
        anchor="    for member in _members_of_a_cycle(parents):\n",
        replacement="    for member in frozenset():\n",
        caught_by=(
            "tests/test_thread_map_round20.py::"
            "test_every_reply_tree_shape_keeps_the_four_properties_that_make_it_not_a_guess",
            "tests/test_thread_map_round20.py::"
            "test_each_declared_gap_is_the_one_the_headers_actually_produce",
        ),
    ),
    Replant(
        name="R31-an-ambiguous-message-id-resolves-to-whichever-came-first",
        behaviour=(
            "two messages carry the named Message-ID and one of them is picked, so a guess "
            "is reported as a link and the weaker AMBIGUOUS_PARENT declaration disappears"
        ),
        path="server/src/mailweave/structure/reply_tree.py",
        anchor="        if len(held) > 1:\n            ambiguous = True\n",
        replacement="        if len(held) > 1:\n            return held[0], candidate, False\n",
        caught_by=(
            "tests/test_thread_map_round20.py::"
            "test_each_declared_gap_is_the_one_the_headers_actually_produce",
        ),
    ),
    Replant(
        name="R32-chronological-ties-break-on-the-array-index-again",
        behaviour=(
            "STR-03: two messages stamped in the same millisecond are ordered by the order "
            "Gmail happened to send the array in, so the representation depends on an "
            "ordering the API does not promise"
        ),
        path="server/src/mailweave/gmail/client.py",
        anchor=(
            "        key=lambda index: (\n"
            "            moment[thread.messages[index].id],\n"
            "            thread.messages[index].id,\n"
            "        ),\n"
        ),
        replacement=(
            "        key=lambda index: (\n"
            "            moment[thread.messages[index].id],\n"
            "            index,\n"
            "        ),\n"
        ),
        caught_by=(
            "tests/test_thread_map_round20.py::"
            "test_two_messages_stamped_in_the_same_millisecond_order_the_same_way_either_way",
        ),
    ),
    Replant(
        name="R33-the-thread-map-reads-the-array-order-instead-of-the-sealed-positions",
        behaviour=(
            "C-02c: rows are ordered by the array Gmail sent rather than by internalDate, "
            "so a thread whose array is unsorted is presented out of chronological order"
        ),
        path="server/src/mailweave/structure/threadmap.py",
        anchor="    ordered = sorted(messages, key=lambda message: positions[message.id])\n",
        replacement="    ordered = list(messages)\n",
        caught_by=(
            "tests/test_thread_map_round20.py::"
            "test_the_array_order_gmail_returns_does_not_change_the_representation",
        ),
    ),
    Replant(
        name="R34-a-mention-is-counted-as-authorship",
        behaviour=(
            "C-02b / STR-02: an address named in a body is recorded as having written the "
            "message, so 'what did X say' answers with what somebody said about X"
        ),
        path="server/src/mailweave/structure/participants.py",
        anchor="    authors = tuple(address for _display, address in parsed[FROM])\n",
        replacement=(
            "    authors = tuple(address for _display, address in parsed[FROM]) + tuple(\n"
            "        a for a in addresses_in_text(observed_text)\n"
            "        if a not in {b for _d, b in parsed[FROM]}\n"
            "    )\n"
        ),
        caught_by=(
            "tests/test_thread_map_round20.py::"
            "test_an_address_a_message_only_names_is_not_an_address_that_wrote_it",
        ),
    ),
    Replant(
        name="R35-a-senders-own-address-in-their-own-body-becomes-hearsay-about-them",
        behaviour=(
            "the mention set stops being disjoint from the address headers, so an author "
            "who quotes their own address is recorded as talked about in their own message"
        ),
        path="server/src/mailweave/structure/participants.py",
        anchor="    in_headers = set(authors) | set(recipients) | set(reply_to)\n",
        replacement="    in_headers: set[str] = set()\n",
        caught_by=(
            "tests/test_thread_map_round20.py::"
            "test_one_address_cannot_be_both_the_author_and_the_hearsay_of_one_message",
        ),
    ),
    Replant(
        name="R36-a-multi-address-from-is-promoted-to-sole-authorship",
        behaviour=(
            "RFC 5322 permits a multi-mailbox From and the headers do not say who wrote; "
            "promoting either address attributes one person's words to another"
        ),
        path="server/src/mailweave/structure/participants.py",
        anchor=("        if len(self.authors) == 1:\n            return ParticipantRole.AUTHOR\n"),
        replacement=(
            "        if len(self.authors) >= 1:\n            return ParticipantRole.AUTHOR\n"
        ),
        caught_by=(
            "tests/test_thread_map_round20.py::"
            "test_a_from_naming_two_people_is_coauthorship_and_is_not_promoted_to_authorship",
        ),
    ),
    Replant(
        name="R37-structural-expansion-drops-the-region-the-query-named",
        behaviour=(
            "OD-5 point 3 / A9-A2 at the newest rung: L4's rfc822msgid probes leave the "
            "region the caller declared, so -in:spam searches spam"
        ),
        path="server/src/mailweave/retrieval/structural.py",
        anchor="    region = search_region_of(parsed.constraints)\n",
        replacement="    region: tuple[str, ...] = ()\n",
        caught_by=(
            "tests/test_thread_map_round20.py::"
            "test_structural_expansion_carries_the_region_the_query_named",
            "tests/test_thread_map_round20.py::"
            "test_the_expansion_never_leaves_the_region_the_query_named_at_the_wire",
        ),
    ),
    Replant(
        name="R38-a-capped-sibling-thread-is-dropped-instead-of-withheld",
        behaviour=(
            "I-1: ids L4 put into H sit in a thread the response does not disclose and no "
            "cap note is filed, so a hit is dropped rather than converted to a withheld "
            "record with an affordance"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor="    for message_id, origin in sorted(ledger.origins.items()):\n",
        replacement="    for message_id, origin in sorted({}.items()):\n",
        caught_by=(
            "tests/test_thread_map_round20.py::"
            "test_sibling_threads_beyond_the_cap_are_withheld_rather_than_dropped",
        ),
    ),
    Replant(
        name="R39-linkage-is-optional-on-a-row",
        behaviour=(
            "STR-01's 'every unlinked message is marked unlinked' becomes a comment beside "
            "a declaration: a row can omit its linkage and a reader infers it from order"
        ),
        path="server/src/mailweave/envelope/wire.py",
        anchor="    linkage: Linkage\n",
        replacement="    linkage: Linkage = Linkage.HEADERS_UNOBSERVED\n",
        caught_by=(
            "tests/test_thread_map_round20.py::"
            "test_a_message_row_carries_exactly_one_linkage_and_it_is_never_absent",
        ),
    ),
    Replant(
        name="R40-a-parent-may-be-named-beside-a-declared-gap",
        behaviour=(
            "C-02a's silent re-parenting arrives through the schema: a row declares a gap "
            "and names a parent anyway, and nothing refuses it"
        ),
        path="server/src/mailweave/envelope/wire.py",
        anchor="        linked = self.linkage in RESOLVED_LINKAGES\n",
        replacement="        linked = self.reply_parent_id is not None\n",
        caught_by=(
            "tests/test_thread_map_round20.py::"
            "test_a_parent_beside_a_declared_gap_is_not_representable",
        ),
    ),
    Replant(
        name="R41-a-message-whose-text-was-never-observed-reports-no-mentions",
        behaviour=(
            "the negative-from-an-absence defect at the participant index: a row with no "
            "body and no snippet reports 'nobody named' instead of 'nothing looked'"
        ),
        path="server/src/mailweave/structure/participants.py",
        # Anchored on the derived predicate rather than on either of the two places
        # `text_observed` is set: the behaviour is "a mention was only looked for where it
        # could be", and that lives in one property with two inputs.
        anchor="        return self.headers_observed and self.text_observed\n",
        replacement="        return True\n",
        caught_by=(
            "tests/test_thread_map_round20.py::"
            "test_when_no_text_was_observed_mentions_are_declared_unscanned_rather_than_absent",
        ),
    ),
    # --- round 21: the four over-claims R-RETR-049..055 named, and WS-06's handles ---------
    #
    # Every round-20 entry above defends the *reconstruction*. These defend the **claims made
    # about it** and the handles built on top of them, which is where all five of round 20's
    # MEDIUMs were and which the round-20 manifest had no entry for: R-RETR mutated
    # `Link.evidence` and the mention scanner's input and got a green suite both times.
    Replant(
        name="R42-the-gap-records-the-thread-root-instead-of-the-nearest-ancestor",
        behaviour=(
            "R-RETR-049: an unlinked child records the leftmost id its headers name - the "
            "thread root - so L4 probes for an ancestor three hops up and the recovered row "
            "is disclosed as the child's reply parent"
        ),
        path="server/src/mailweave/structure/reply_tree.py",
        anchor=(
            "        nearest = view.in_reply_to[0] if view.in_reply_to else view.references[-1]\n"
        ),
        replacement="        nearest = (view.in_reply_to + view.references)[0]\n",
        caught_by=(
            "tests/test_structural_claims_round21.py::"
            "test_the_id_an_unlinked_child_records_is_the_nearest_ancestor_its_headers_name",
            "tests/test_structural_claims_round21.py::"
            "test_l4_probes_for_the_parent_and_not_for_the_thread_root",
        ),
    ),
    Replant(
        name="R43-a-message-id-in-two-threads-yields-two-parents-for-one-child",
        behaviour=(
            "R-RETR-050: the ambiguity the reply tree refuses inside a thread is asserted "
            "twice across threads - both recovered rows are disclosed as *the* parent"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor="                if found.names_one_message\n",
        replacement="                if True\n",
        caught_by=(
            "tests/test_structural_claims_round21.py::"
            "test_one_child_is_never_told_it_has_two_reply_parents",
        ),
    ),
    Replant(
        name="R44-the-mention-scanner-is-handed-the-quote-stripped-view-again",
        behaviour=(
            "R-RETR-051: quoted and forwarded blocks are invisible to the mention scan while "
            "the row reports itself scanned, so the participant index is a function of which "
            "row the query matched rather than of the thread"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor=(
            "        return ObservedText(text=processed.body_clean.text, truncated_at_end=False)\n"
        ),
        replacement=(
            "        return ObservedText(text=processed.default_view, truncated_at_end=False)\n"
        ),
        caught_by=(
            "tests/test_structural_claims_round21.py::"
            "test_an_address_inside_a_quoted_block_is_a_mention_the_response_can_see",
        ),
    ),
    Replant(
        name="R45-a-truncation-boundary-is-treated-as-an-address-boundary",
        behaviour=(
            "R-RETR-052: an address straddling the point a snippet was cut at is minted as a "
            "participant identity that appears in no message of the mailbox"
        ),
        path="server/src/mailweave/structure/participants.py",
        anchor="        if text.truncated_at_end and match.end() == end_of_text:\n",
        replacement="        if False:\n",
        caught_by=(
            "tests/test_structural_claims_round21.py::"
            "test_a_truncated_snippet_never_mints_an_address_that_is_in_no_message",
        ),
    ),
    Replant(
        name="R46-a-message-no-reply-can-name-looks-like-an-ordinary-reply-again",
        behaviour=(
            "R-RETR-054: AD D.4a's compensating fact stops reaching the row, so a message "
            "with no Message-ID is byte-identical on the wire to an ordinary linked reply "
            "while its own well-formed child reports a parent it cannot find"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        # The **stub** branch of `_rows_of`. R57 is the body branch: the fact is written in
        # two places and each is removable on its own, so one anchor would leave the other
        # undefended - which is one entry per *behaviour* read strictly, and this is the
        # exception the manifest's own rule allows for when the sites are independent.
        # Re-anchored in round 23 with R57, for the same reason: WS-11 put the ladder's
        # `disclosed_reductions` on this branch too, so the line after the anchored one
        # changed text. Same behaviour, same plant, and the two branches are still two
        # anchors at two indents because each is removable on its own.
        anchor=(
            "                can_be_a_parent=link.can_be_a_parent,\n"
            "                reductions=disclosed_reductions,\n"
        ),
        replacement=(
            "                can_be_a_parent=True,\n"
            "                reductions=disclosed_reductions,\n"
        ),
        caught_by=(
            "tests/test_structural_claims_round21.py::"
            "test_a_message_no_reply_can_ever_name_is_distinguishable_on_the_wire",
        ),
    ),
    Replant(
        name="R57-the-body-bearing-row-loses-the-same-fact",
        behaviour=(
            "R-RETR-054 at the other of the two sites: a *matched* row that carries a body "
            "reports that a reply could name it when its own Message-ID was never sent"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        # Re-anchored in round 23: WS-11 made the disclosed reductions the *ladder's*
        # (`disclosed_reductions`) rather than the content pipeline's alone, so the line
        # below this one changed text. The behaviour and the plant are unchanged; an anchor
        # that no longer matched would report this defended for free.
        anchor=(
            "                    can_be_a_parent=link.can_be_a_parent,\n"
            "                    reductions=disclosed_reductions,\n"
        ),
        replacement=(
            "                    can_be_a_parent=True,\n"
            "                    reductions=disclosed_reductions,\n"
        ),
        caught_by=(
            "tests/test_structural_claims_round21.py::"
            "test_a_message_no_reply_can_ever_name_is_distinguishable_on_the_wire",
        ),
    ),
    Replant(
        name="R47-the-tie-census-reads-the-string-and-the-sort-reads-the-integer",
        behaviour=(
            "R-RETR-055: two rows whose internalDate is equal as an integer and unequal as a "
            "string tie in the ordering and are named in no tied_on_internal_date entry, so "
            "a pair ordered by message id is presented with no declaration"
        ),
        path="server/src/mailweave/gmail/client.py",
        anchor="    stamps = Counter(moment[message.id] for message in thread.messages)\n",
        replacement="    stamps = Counter(message.internal_date for message in thread.messages)\n",
        caught_by=(
            "tests/test_structural_claims_round21.py::"
            "test_a_tie_settled_by_message_id_is_declared_however_the_stamp_is_spelled",
        ),
    ),
    Replant(
        name="R48-a-declined-l4-lookup-goes-unreported-when-other-probes-ran",
        behaviour=(
            "R-RETR-053: a Message-ID L4 cannot put into a query is skipped silently whenever "
            "any other probe went out, so the rung's account of a lookup it chose not to make "
            "is missing from a response that accounts for everything else"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor="    if plan.skipped and executed:\n",
        replacement="    if False:\n",
        caught_by=(
            "tests/test_structural_claims_round21.py::"
            "test_a_probe_declined_while_others_ran_is_reported_rather_than_invisible",
        ),
    ),
    Replant(
        name="R49-the-liveness-probe-asks-only-about-additions",
        behaviour=(
            "WS-06 / AD A.10 step 2: a handle claims its threads have not changed while its "
            "probe asks about one of the four ways a mailbox can move, so a deletion or a "
            "relabel redeems as unchanged"
        ),
        path="server/src/mailweave/gmail/client.py",
        anchor=(
            "LIVENESS_HISTORY_TYPES: Final[tuple[str, ...]] = (\n"
            '    "messageAdded",\n'
            '    "messageDeleted",\n'
            '    "labelAdded",\n'
            '    "labelRemoved",\n'
            ")\n"
        ),
        replacement='LIVENESS_HISTORY_TYPES: Final[tuple[str, ...]] = ("messageAdded",)\n',
        caught_by=(
            "tests/test_handles_round21.py::"
            "test_a_handle_notices_every_way_the_mailbox_can_move_under_it",
        ),
    ),
    Replant(
        name="R50-a-warm-digest-recompute-claims-the-cold-paths-guarantee",
        behaviour=(
            "AD A.10 step 4: a redemption served from the LRU labels its tautological digest "
            "comparison `recomputed_from_fetch`, which is the warm path claiming a check that "
            "compared a value with itself"
        ),
        path="server/src/mailweave/handles/redeem.py",
        anchor=(
            "    check = DigestCheck.CACHE_TAUTOLOGY if from_cache "
            "else DigestCheck.RECOMPUTED_FROM_FETCH\n"
        ),
        replacement="    check = DigestCheck.RECOMPUTED_FROM_FETCH\n",
        caught_by=(
            "tests/test_handles_round21.py::"
            "test_a_warm_redemption_labels_its_digest_check_a_cache_tautology",
            "tests/test_handles_round21.py::"
            "test_every_handle_outcome_only_claims_what_the_step_that_ran_produced",
        ),
    ),
    Replant(
        name="R51-fetched-at-is-restamped-when-the-cache-serves-a-map",
        behaviour=(
            "AD A.10 / FRESH-03: a cache-served response asserts it was fetched now, which is "
            "a freshness it does not have - and makes a handle that cannot expire, since "
            "expiry is measured from fetched_at"
        ),
        path="server/src/mailweave/handles/redeem.py",
        anchor="                    fetched_at=hit.fetched_at,\n",
        replacement="                    fetched_at=verified_at,\n",
        caught_by=(
            "tests/test_handles_round21.py::"
            "test_a_cached_map_keeps_the_stamp_of_the_read_that_produced_it",
            "tests/test_handles_round21.py::"
            "test_every_handle_outcome_only_claims_what_the_step_that_ran_produced",
        ),
    ),
    Replant(
        name="R52-a-probe-that-could-not-tell-is-read-as-a-probe-that-found-nothing",
        behaviour=(
            "AD A.10 / D.11: Gmail's 404 on the watermark stops meaning 'this could not be "
            "verified', so the LRU serves a map nothing checked, no declaration reaches the "
            "response, and handle_stale_unverifiable becomes unproducible"
        ),
        path="server/src/mailweave/handles/redeem.py",
        # Anchored on the predicate rather than on either of the two things it gates. The
        # bypass is defended twice - the entries are evicted *and* the lookup is skipped - so
        # planting either one alone leaves the behaviour intact, which is defence in depth
        # working and is why the plant is the condition they both read.
        anchor="    unverifiable = not probe.conclusive\n",
        replacement="    unverifiable = False\n",
        caught_by=(
            "tests/test_handles_round21.py::"
            "test_an_unverifiable_probe_bypasses_the_cache_and_evicts_what_it_could_not_check",
            "tests/test_handles_round21.py::"
            "test_every_handle_outcome_only_claims_what_the_step_that_ran_produced",
        ),
    ),
    Replant(
        name="R53-a-deliberate-key-rotation-is-reported-as-age",
        behaviour=(
            "AD A.10 / D.11: handle_key_rotated collapses into handle_expired, so an operator "
            "who rotated a key is told that time passed - two causes, two remedies, one class"
        ),
        path="server/src/mailweave/handles/mint.py",
        anchor="            ErrorCode.HANDLE_KEY_ROTATED,\n",
        replacement="            ErrorCode.HANDLE_EXPIRED,\n",
        caught_by=(
            "tests/test_handles_round21.py::"
            "test_a_deliberate_key_rotation_is_reported_as_a_rotation_and_not_as_age",
            "tests/test_handles_round21.py::"
            "test_every_handle_error_class_is_one_this_product_can_actually_produce",
        ),
    ),
    Replant(
        name="R54-the-mapping-digest-covers-the-participant-block",
        behaviour=(
            "R-RETR-051's consequence for WS-06: the digest becomes a function of disclosure "
            "depth, so two redemptions of one handle at two depths report handle_stale for a "
            "thread nothing changed in"
        ),
        path="server/src/mailweave/handles/digest.py",
        anchor='        "tied": sorted(thread_map.tied_on_internal_date),\n',
        replacement=(
            '        "tied": sorted(thread_map.tied_on_internal_date),\n'
            '        "participants": sorted(thread_map.participants.by_address),\n'
        ),
        caught_by=(
            "tests/test_handles_round21.py::test_the_digest_does_not_cover_the_participant_block",
        ),
    ),
    Replant(
        name="R55-the-handle-watermark-is-the-threads-own-instead-of-the-mailboxs",
        behaviour=(
            "amendment A10 / R-RETR-060: the liveness walk starts at the named thread's own "
            "historyId, so its window is the thread's quietness rather than the handle's "
            "ttl - unbounded, one page per redemption, handle_stale_unverifiable as the "
            "routine answer with the LRU bypassed at two API calls for ever"
        ),
        path="server/src/mailweave/handles/mint.py",
        anchor="        history_id=mailbox_history_id,\n",
        replacement=("        history_id=str(min(int(value) for value in per_thread)),\n"),
        caught_by=(
            "tests/test_handles_round21.py::"
            "test_a_handles_watermark_is_the_mailbox_watermark_and_not_the_named_threads_own",
            "tests/test_handles_round21.py::"
            "test_a_quiet_thread_redeems_clean_at_the_shipped_page_budget",
        ),
    ),
    Replant(
        name="R58-the-watermark-is-observed-after-the-threads-are-fetched",
        behaviour=(
            "amendment A10: the mailbox watermark is read after the maps rather than before "
            "them, so a change to a named thread between its read and the observation sits "
            "below the walk's start - invisible to the probe and absent from the map"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor="    mailbox_history_id = _mailbox_watermark(client, minter, accountant)\n",
        replacement="    mailbox_history_id = None\n",
        caught_by=(
            "tests/test_handles_round21.py::"
            "test_the_mailbox_watermark_is_observed_before_the_first_thread_is_fetched",
        ),
    ),
    Replant(
        name="R59-a-walk-that-saw-a-change-reports-that-it-could-not-look",
        behaviour=(
            "amendment A10's second rule / R-RETR-059: a probe that read a page, found a "
            "named thread had moved and stopped with pages outstanding falls into "
            "handle_stale_unverifiable - the observation is discarded, the map is served, "
            "and the response says the change could not be verified from history"
        ),
        path="server/src/mailweave/handles/redeem.py",
        anchor="    if probe.saw_a_change:\n",
        replacement="    if probe.saw_a_change and probe.conclusive:\n",
        caught_by=(
            "tests/test_handles_round21.py::"
            "test_a_walk_that_saw_a_change_and_ran_out_of_pages_reports_what_it_saw",
            "tests/test_handles_round21.py::"
            "test_an_unverifiable_probe_is_reserved_for_a_walk_that_observed_nothing",
        ),
    ),
    Replant(
        name="R56-a-history-walk-that-stopped-early-is-read-as-clean",
        behaviour=(
            "AD A.10 step 2: a probe that stopped with pages outstanding reports the threads "
            "unchanged, which is a claim about a window it never read"
        ),
        path="server/src/mailweave/gmail/client.py",
        anchor="            pages_exhausted=token is not None,\n",
        replacement="            pages_exhausted=False,\n",
        caught_by=(
            "tests/test_handles_round21.py::"
            "test_a_history_walk_that_stopped_early_is_unverifiable_rather_than_clean",
        ),
    ),
    Replant(
        name="R60-a-budget-below-the-recoverability-floor-is-accepted",
        behaviour=(
            "AD A.7 / AD-03: a client budget under floor_quota_units = 845 is honoured "
            "instead of clamped up, so a response is issued that cannot pay for L0, L1, the "
            "hit maps, L1b, L2, L3 and the report - one nothing can be recovered from"
        ),
        path="server/src/mailweave/policy/budget.py",
        anchor="        applied_quota = FLOOR_QUOTA_UNITS\n",
        replacement="        applied_quota = requested\n",
        caught_by=(
            "tests/test_ws10_escalation.py::"
            "test_a_budget_below_the_floor_is_clamped_up_and_the_clamp_is_declared",
        ),
    ),
    Replant(
        name="R61-a-rung-declined-on-evidence-is-reported-as-inapplicable",
        behaviour=(
            "round 22's ruling on AD D.2's `not_tried[].why`: a rung the policy declined "
            "because a D.3 stop rule had already settled the query is reported "
            "`not_applicable` - the one value OD-2 makes compatible with `not_found`, and a "
            "claim that the rung could not have helped when it could"
        ),
        path="server/src/mailweave/retrieval/ladder.py",
        anchor="                        skipped=NotTriedWhy.STOPPED_ON_EVIDENCE,\n",
        replacement="                        skipped=NotTriedWhy.NOT_APPLICABLE,\n",
        caught_by=(
            "tests/test_ws10_escalation.py::"
            "test_the_shape_matrix_reaches_every_state_and_every_outcome_it_asserts_about",
        ),
    ),
    Replant(
        name="R62-not-found-is-claimed-over-a-ladder-that-is-missing-rungs",
        behaviour=(
            "OD-2: `not_found` is emitted although L5, L6 and LR are unbuilt, so the "
            "response claims every applicable path was executed and exhausted when three of "
            "them do not exist - the mailbox-nonexistence claim OD-2 forbids absolutely"
        ),
        path="server/src/mailweave/policy/account.py",
        anchor="    if not account.covers(applicable):\n",
        replacement="    if False:\n",
        caught_by=(
            "tests/test_ws10_escalation.py::"
            "test_a_ladder_missing_a_rung_entirely_cannot_say_not_found",
            "tests/test_ws10_escalation.py::test_no_response_this_build_can_produce_says_not_found",
        ),
    ),
    Replant(
        name="R63-rule-two-carries-rule-one-bs-answer-type-escape",
        behaviour=(
            "R-RETR-007 / round 16: D.3 rule 2's fourth conjunct becomes rule 1b's escape, "
            "so the L1 stop fires on every ordinary non-interrogative query and L1b is "
            "switched off for exactly the threads it exists for"
        ),
        path="server/src/mailweave/policy/stopping.py",
        anchor="        and inputs.answer_type.present is True\n",
        replacement="        and not inputs.answer_type.blocks_stop\n",
        caught_by=(
            "tests/test_ws10_escalation.py::test_rule_two_does_not_carry_rule_one_bs_escape",
        ),
    ),
    Replant(
        name="R64-a-rung-stopped-part-way-throws-away-the-probes-that-ran",
        behaviour=(
            "WS-10's mid-rung timeout contract: a rung the accountant stopped part-way "
            "reports itself as having executed nothing, so the ids its probes admitted are "
            "in H with no route listed for them and the response cannot be assembled at all "
            "- a timeout treated as permission to forget"
        ),
        path="server/src/mailweave/retrieval/ladder.py",
        anchor=(
            "                executions.append("
            "_blocked(rung.rung, planned, breach, executed=executed))\n"
        ),
        replacement="                executions.append(_blocked(rung.rung, planned, breach))\n",
        caught_by=(
            "tests/test_ws10_escalation.py::test_a_rung_stopped_part_way_keeps_the_probes_that_ran",
        ),
    ),
    Replant(
        name="R65-the-budget-is-checked-after-the-spend-instead-of-before-it",
        behaviour=(
            "AD A.7: a budget is never accepted-and-then-overrun. Body fetches stop being "
            "charged against the per-query caps, so a run spends its whole max_api_calls on "
            "messages.get and the response reports a spend above the budget it declared"
        ),
        path="server/src/mailweave/retrieval/ladder.py",
        anchor=(
            "            if self._accountant is not None:\n"
            "                breach = self._accountant.check("
            "(GmailEndpoint.MESSAGES_GET,))\n"
        ),
        replacement=(
            "            if False:\n"
            "                breach = self._accountant.check("
            "(GmailEndpoint.MESSAGES_GET,))\n"
        ),
        caught_by=(
            "tests/test_ws10_escalation.py::test_every_rung_is_accounted_for_in_exactly_one_state",
        ),
    ),
    Replant(
        name="R66-a-blocked-rung-is-reported-without-the-call-that-reaches-it",
        behaviour=(
            "AD-03: a rung a cap stopped is reported with no affordance, so the caller is "
            "told a dead end as a fact - and `not_applicable` and `cap` become "
            "indistinguishable on the wire, which is the OD-2 distinction itself"
        ),
        path="server/src/mailweave/retrieval/ladder.py",
        anchor=(
            "        skipped=breach.why,\n"
            "        cap=breach.cap,\n"
            "        affordance=breach.affordance,\n"
        ),
        replacement=(
            "        skipped=breach.why,\n"
            "        cap=breach.cap,\n"
            "        affordance=force_rungs(rung),\n"
        ),
        caught_by=(
            "tests/test_ws10_escalation.py::test_every_rung_is_accounted_for_in_exactly_one_state",
        ),
    ),
    # --- round 23, WS-11: representation and query-aware disclosure -----------------------
    Replant(
        name="R67-the-fill-admits-on-position-alone",
        behaviour=(
            "DISC-01's degenerate strategy: the E4 fill admits a row that is merely near a "
            "hit, so a one-term query emits Baseline F(+/-2) under the query-aware name"
        ),
        path="server/src/mailweave/disclosure/weights.py",
        anchor="        return self.value > E4_MINIMUM_FILL_SCORE and bool(self.anchored)\n",
        replacement="        return self.value > E4_MINIMUM_FILL_SCORE\n",
        caught_by=(
            "tests/test_disclosure_round23.py::"
            "test_a_row_no_anchored_component_reached_is_not_filled",
            "tests/test_region_kind_round19.py::"
            "test_a_stub_row_states_the_region_its_own_labels_place_it_in",
        ),
    ),
    Replant(
        name="R68-the-driver-stops-defending-floor-membership",
        behaviour=(
            "OD-3: the A.9a driver stops checking that every floor member survives each "
            "step, so a step that drops a reply parent ships a chain with a hole in it"
        ),
        path="server/src/mailweave/disclosure/ladder.py",
        anchor=(
            "        assert_floor_intact(before, after, precedence=step.precedence, "
            "name=step.name)\n"
        ),
        replacement="",
        caught_by=(
            "tests/test_disclosure_round23.py::"
            "test_every_ladder_step_is_refused_when_it_drops_a_floor_member",
        ),
    ),
    Replant(
        name="R69-every-floor-member-is-promoted",
        behaviour=(
            "OD-3's second half: the promotion rule stops saying no, so the E2 floor becomes "
            "a window of unbounded radius wearing the query-aware policy's name"
        ),
        path="server/src/mailweave/disclosure/floor.py",
        anchor=(
            "    if member.constraint_coverage - evidence.constraint_coverage:\n"
            "        return FloorDependence.CONSTRAINT_CARRIER\n"
            "    return None\n"
        ),
        replacement=(
            "    if member.constraint_coverage - evidence.constraint_coverage:\n"
            "        return FloorDependence.CONSTRAINT_CARRIER\n"
            "    return FloorDependence.CONSTRAINT_CARRIER\n"
        ),
        # One citation, not two. The shipped-path test does not catch this and is not
        # cited: its fixture's only floor members are the two the rule promotes, so a rule
        # that promotes everything changes nothing it asserts. A citation that does not
        # catch is the shape R-RETR-061 filed.
        caught_by=(
            "tests/test_disclosure_round23.py::"
            "test_the_promotion_rule_refuses_an_ordinary_adjacent_reply",
        ),
    ),
    Replant(
        name="R70-the-overflow-ceiling-is-a-budget",
        behaviour=(
            "A.9a step 6: the 9,000 -> 12,000 overflow is applied to a response with no floor "
            "to protect, which turns the declared promise into 3,000 extra tokens"
        ),
        path="server/src/mailweave/disclosure/ladder.py",
        anchor=(
            "    if not (layout.floor_ids & layout.present_ids):\n"
            "        return layout\n"
            "    if _reduction_still_available(layout, ceilings):\n"
        ),
        replacement="    if _reduction_still_available(layout, ceilings):\n",
        caught_by=(
            "tests/test_disclosure_round23.py::"
            "test_the_overflow_ceiling_is_reachable_only_for_floor_membership",
        ),
    ),
    Replant(
        name="R71-a-source-holding-a-floor-member-is-split-off",
        behaviour=(
            "A.9a step 7: a whole source is split into not_included_sources[] although it "
            "carries reply parents or children of this response's evidence - and although "
            "step 8, which comes after it, could have freed the tokens by withholding a "
            "handful of rows. The most expensive thing the ladder can do to a caller, done "
            "first (re-anchored round 25: the citation now names the property the clause "
            "protects, because the relative floor gate makes a whole-source split lawful "
            "*when nothing cheaper exists*, which is exactly what this clause decides)"
        ),
        path="server/src/mailweave/disclosure/ladder.py",
        # Re-anchored round 29: the candidate filter gained a second clause (a source may not
        # leave if it is the last one carrying evidence), so the anchor is the floor clause on
        # its own line and the replant removes only that clause, which is what R71 is about.
        anchor=(
            "            if not (source.present_ids & working.floor_ids)\n"
            "            and _may_leave_without_emptying_the_answer(source, working)\n"
        ),
        replacement=("            if _may_leave_without_emptying_the_answer(source, working)\n"),
        caught_by=(
            "tests/test_round25.py::"
            "test_step_7_does_not_split_a_source_that_step_8_could_have_saved",
        ),
    ),
    Replant(
        name="R72-a-floor-member-is-withheld-at-the-ceiling",
        behaviour=(
            "A.9a step 8: the ceiling converts a floor member into a withheld record, which "
            "is the one thing OD-3 says a cap may never cost"
        ),
        path="server/src/mailweave/disclosure/ladder.py",
        # Round 23 had to widen the candidate set rather than only drop the floor clause,
        # because `floor_of` excluded hits and removing the clause alone was a no-op - which
        # was itself the finding (R-DISC-021). Round 25 records hit-members, so dropping the
        # floor clause **is** the reintroduction: A.9a step 8 will then withhold a disclosed
        # hit's direct child and leave a hole in a reply chain.
        # Re-pointed after the navigation redesign (2026-09-14): the clause gained a third
        # term, `Band.REQUESTED`, on its own line; the replant drops the floor term alone.
        anchor="            if row.id not in layout.floor_ids\n",
        replacement="            if True\n",
        caught_by=(
            "tests/test_round25.py::"
            "test_the_ceiling_never_converts_a_floor_member_into_a_withheld_record",
        ),
    ),
    Replant(
        name="R73-the-ladder-and-the-envelope-measure-differently",
        behaviour=(
            "DISC-06: the ladder stops counting stub rows and collapsed runs, so it believes "
            "it has fitted a response the envelope then refuses - host truncation from inside"
        ),
        path="server/src/mailweave/disclosure/layout.py",
        # Re-pointed 2026-09-21: the call gained the row's `From` address and display name,
        # which the attribution block charges, and became a six-line call. The replant is
        # the same one - the whole call goes, and a bare word count takes its place.
        anchor=(
            "        return row_tokens(\n"
            "            text,\n"
            "            auth=self.auth_record,\n"
            "            from_address=self.from_address,\n"
            "            from_display=self.from_display,\n"
            "        )\n"
        ),
        replacement='        return 0 if text is None else len((text or "").split())\n',
        caught_by=(
            "tests/test_disclosure_round23.py::"
            "test_the_ladders_measure_and_the_envelopes_measure_are_the_same_number",
        ),
    ),
    Replant(
        name="R74-the-adjacency-radius-outgrows-the-baseline",
        behaviour=(
            "DISC-02: the E4 adjacency component is given a wider radius than Baseline F, so "
            "a measured win is a win over a straw baseline"
        ),
        path="server/src/mailweave/disclosure/weights.py",
        anchor="E4_ADJACENCY_POSITIONS: Final[int] = 2\n",
        replacement="E4_ADJACENCY_POSITIONS: Final[int] = 6\n",
        caught_by=(
            "tests/test_disclosure_round23.py::"
            "test_the_adjacency_radius_is_the_baselines_own_radius",
        ),
    ),
    Replant(
        name="R75-a-published-e4-weight-moves",
        behaviour=(
            "WS-17's sweep target: a weight is retuned, and the query-independent decision "
            "lexicon can then order a candidate ahead of one the query reached"
        ),
        path="server/src/mailweave/disclosure/weights.py",
        anchor="        FillComponent.DECISION_CUE: 1,\n",
        replacement="        FillComponent.DECISION_CUE: 6,\n",
        caught_by=(
            "tests/test_disclosure_round23.py::"
            "test_no_query_independent_component_can_outrank_a_query_derived_one",
            "tests/test_disclosure_round23.py::"
            "test_the_published_weights_are_the_ones_the_round_report_publishes",
        ),
    ),
    Replant(
        name="R76-the-disclosed-depth-goes-back-to-being-decided-in-assemble",
        behaviour=(
            "WS-11 unwired: every non-hit row is a stub again whatever the disclosure layer "
            "planned, so the E2 floor and the E4 fill reach nothing a caller can read"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor=("                mailbox=provenance,\n                depth=planned_row.depth,\n"),
        replacement=("                mailbox=provenance,\n                depth=Depth.STUB,\n"),
        caught_by=(
            "tests/test_disclosure_round23.py::"
            "test_the_shipped_path_promotes_the_floor_members_the_evidence_depends_on",
        ),
    ),
    Replant(
        name="R77-the-top-k-becomes-its-own-number",
        behaviour=(
            "A.9a step 3's protected hit count stops being A.7's published max_body_fetches, "
            "so a figure nobody registered decides how many hits keep their bodies"
        ),
        path="server/src/mailweave/disclosure/ladder.py",
        anchor="DISCLOSURE_TOP_K_HITS: Final[int] = MAX_BODY_FETCHES_L0\n",
        replacement="DISCLOSURE_TOP_K_HITS: Final[int] = 9\n",
        caught_by=(
            "tests/test_disclosure_round23.py::"
            "test_the_protected_hit_count_is_a_published_cap_and_not_a_new_number",
        ),
    ),
    Replant(
        name="R78-forcing-a-rung-does-nothing",
        behaviour=(
            "`force_rungs` stops adding rungs, so the affordance a `stopped_on_evidence` "
            "entry mints reaches nothing and the response promises a rerun it will not do"
        ),
        path="server/src/mailweave/retrieval/ladder.py",
        anchor="        self._forced = frozenset(forced)\n",
        replacement="        self._forced = frozenset()\n",
        caught_by=(
            "tests/test_mcp_surface_round24.py::"
            "test_forcing_a_rung_the_policy_declined_actually_runs_it",
        ),
    ),
    Replant(
        name="R79-forcing-a-rung-removes-the-others",
        behaviour=(
            "`force_rungs` becomes a filter rather than an addition, so a caller asking for "
            "more work gets a narrower search than the same query got without the argument"
        ),
        path="server/src/mailweave/retrieval/ladder.py",
        anchor="        if rung in self._forced:\n            return True\n",
        replacement="        if self._forced:\n            return rung in self._forced\n",
        caught_by=("tests/test_mcp_surface_round24.py::test_force_rungs_only_ever_adds_rungs",),
    ),
    Replant(
        name="R80-view-raw-becomes-an-unrecognised-word",
        behaviour=(
            '`view: "raw"` stops being a declared refusal and becomes a schema complaint, '
            "so a caller cannot tell a depth this release declines from a typo (AD D.1)"
        ),
        path="server/src/mailweave/surface/arguments.py",
        anchor="    if raw == UNREQUESTABLE_VIEW:\n",
        replacement="    if False:\n",
        caught_by=(
            "tests/test_mcp_surface_round24.py::"
            "test_view_raw_is_refused_as_unsupported_view_on_every_tool_that_takes_a_view",
        ),
    ),
    Replant(
        name="R81-an-in-band-condition-is-reported-as-a-refusal",
        behaviour=(
            "D.11's partition stops being read from ERROR_SURFACE, so a budget clamp can be "
            "delivered as a tool error and a client cannot tell declined from broken"
        ),
        path="server/src/mailweave/surface/partition.py",
        # Re-anchored in round 25: `declined` gained an `unanswerable` parameter for the one
        # case D.11's table does not cover - a condition that is in-band *when there is a
        # response for it to travel on* and aborted the whole call - so the clause that
        # decides the partition now reads both. The old anchor still matched, one line lower,
        # where it decides only the wording of the message: a plant into it changed nothing
        # and reported CAUGHT for a defect it had not introduced.
        anchor="    if surface is Surface.IN_BAND and not unanswerable:\n",
        replacement="    if False:\n",
        caught_by=(
            "tests/test_mcp_surface_round24.py::"
            "test_every_code_in_the_vocabulary_lands_on_the_surface_the_table_puts_it_on",
            "tests/test_mcp_surface_round24.py::"
            "test_an_in_band_code_travels_on_a_served_response_and_never_as_a_refusal",
        ),
    ),
    Replant(
        name="R82-an-unknown-tool-becomes-a-result",
        behaviour=(
            "a tool this server does not serve is answered with a result rather than a "
            "protocol error, so an unreviewed tool name looks like a MailWeave outcome"
        ),
        path="server/src/mailweave/surface/server.py",
        anchor="        raise MCPError(\n            code=types.METHOD_NOT_FOUND,\n",
        replacement=(
            "        from mailweave.errors import ErrorCode\n\n"
            "        return declined(\n"
            "            ErrorCode.UNSUPPORTED_VIEW,\n"
            '            message=f"unknown tool {name!r}",\n'
            "        )\n"
            "        raise MCPError(\n            code=types.METHOD_NOT_FOUND,\n"
        ),
        caught_by=(
            "tests/test_mcp_surface_round24.py::"
            "test_an_unknown_tool_is_a_protocol_error_and_never_a_result",
        ),
    ),
    Replant(
        name="R83-the-read-only-annotation-stops-being-true-of-itself",
        behaviour=(
            "the tools stop declaring `readOnlyHint`, so a client has no annotation to "
            "trust and MCP-04's claim has nothing behind it"
        ),
        path="server/src/mailweave/surface/server.py",
        anchor="    read_only_hint=True,\n",
        replacement="    read_only_hint=None,\n",
        caught_by=(
            "tests/test_mcp_surface_round24.py::"
            "test_every_tool_is_annotated_read_only_and_the_annotation_is_true",
        ),
    ),
    Replant(
        name="R84-the-tool-description-stops-being-a-constant",
        behaviour=(
            "a tool description acquires a value that varies between processes, so the "
            "metadata a client caches is not the metadata it gets next time (MCP-05)"
        ),
        path="server/src/mailweave/surface/tools.py",
        anchor='        return " ".join(claim.text for claim in self.claims)\n',
        replacement=(
            "        import os\n\n"
            '        return " ".join(claim.text for claim in self.claims) + str(os.getpid())\n'
        ),
        caught_by=(
            "tests/test_mcp_surface_round24.py::test_the_tool_metadata_is_constant_across_restarts",
        ),
    ),
    Replant(
        name="R85-the-text-mirror-stops-carrying-the-withheld-records",
        behaviour=(
            "the text rendering drops a fact the structured form carries, so a model reading "
            "the text believes the response is complete while the client sees it is not"
        ),
        path="server/src/mailweave/surface/rendering.py",
        anchor='    for record in structured.get("withheld") or ():\n',
        replacement="    for record in ():\n",
        caught_by=(
            "tests/test_mcp_surface_round24.py::"
            "test_the_structured_and_text_forms_agree_on_every_shape",
        ),
    ),
    Replant(
        name="R86-mail-text-can-forge-a-line-of-the-text-mirror",
        behaviour=(
            "the text mirror's reader stops skipping fenced regions, so a body shaped like "
            "one of this rendering's own lines is read as one"
        ),
        path="server/src/mailweave/surface/rendering.py",
        anchor="    residue, _ = split_fenced(text)\n    return [match for line in residue",
        replacement='    residue = text.split("\\n")\n    return [match for line in residue',
        caught_by=(
            "tests/test_mcp_surface_round24.py::"
            "test_a_body_that_imitates_this_rendering_cannot_forge_a_fact_in_the_text_mirror",
        ),
    ),
    Replant(
        name="R87-the-budget-floor-clamp-is-skipped-by-the-surface",
        behaviour=(
            "a client's budget reaches the accountant without A.7's floor clamp, so a "
            "response can be bought below the level it could be recovered from"
        ),
        path="server/src/mailweave/surface/service.py",
        anchor="        budget = apply_floor(request.budget)\n",
        replacement=(
            "        from mailweave.policy.budget import BudgetRequest\n\n"
            "        budget = apply_floor(BudgetRequest())\n"
        ),
        caught_by=(
            "tests/test_mcp_surface_round24.py::"
            "test_a_budget_below_the_floor_is_clamped_up_and_the_clamp_is_declared",
        ),
    ),
    Replant(
        name="R88-an-underivable-profile-stops-being-fatal",
        behaviour=(
            "startup defaults the redaction profile when `users.getProfile` does not answer, "
            "so the server serves under a policy nothing observed (AD A.4, D.11)"
        ),
        path="server/src/mailweave/surface/runtime.py",
        anchor="        observed = None\n",
        replacement='        observed = "unknown@example.invalid"\n',
        caught_by=(
            "tests/test_mcp_surface_round24.py::"
            "test_serve_refuses_to_start_without_a_valid_credential",
        ),
    ),
    Replant(
        name="R89-the-startup-banner-is-written-to-the-transport",
        behaviour=(
            "the startup banner goes to stdout, which is the MCP transport, so the server "
            "greets its client with a malformed JSON-RPC frame"
        ),
        path="server/src/mailweave/surface/runtime.py",
        anchor="    stream = out if out is not None else sys.stderr\n",
        replacement="    stream = out if out is not None else sys.stdout\n",
        caught_by=(
            "tests/test_mcp_surface_round24.py::"
            "test_a_startup_that_succeeds_prints_nothing_unsafe_and_prints_it_to_stderr",
        ),
    ),
    Replant(
        name="R90-body-full-stops-being-a-depth-the-ladder-measures",
        behaviour=(
            "`body_full` leaves the disclosure ladder's plannable set, so the one view that "
            "returns unabridged text has no path through the ceiling that binds every other"
        ),
        path="server/src/mailweave/disclosure/layout.py",
        anchor="    Depth.BODY_FULL: BODY_FULL_SOFT_CAP_TOKENS,\n",
        replacement="",
        caught_by=(
            "tests/test_mcp_surface_round24.py::"
            "test_get_messages_returns_the_named_messages_at_the_named_depth",
        ),
    ),
    Replant(
        name="R91-a-map-carrier-counts-only-its-rows",
        behaviour=(
            "an expansion response counts `included` off its rows alone, so a thread whose "
            "map was collapsed into declared runs reports itself as almost entirely missing"
        ),
        path="server/src/mailweave/surface/expansion.py",
        # Re-pointed after the navigation redesign (2026-09-14): the source is built once, in
        # `_source_of`, for the map, read and segment paths alike.
        anchor="        included=len(rows) + sum(run.count for run in runs),\n",
        replacement="        included=len(rows),\n",
        caught_by=(
            "tests/test_mcp_surface_round24.py::"
            "test_a_thread_too_large_for_the_ceiling_collapses_runs_that_name_members",
        ),
    ),
    Replant(
        name="R92-an-affordance-stops-being-a-call",
        behaviour=(
            "the `force_rungs` affordance drops the caller's query, so the call it names is "
            "one `mailweave_search` refuses - contract R-07's own failure mode"
        ),
        path="server/src/mailweave/policy/account.py",
        anchor=(
            "    return Affordance(tool=ToolName.SEARCH, "
            'args={"query": query, "force_rungs": [rung.value]})\n'
        ),
        replacement=(
            '    return Affordance(tool=ToolName.SEARCH, args={"force_rungs": [rung.value]})\n'
        ),
        caught_by=(
            "tests/test_mcp_surface_round24.py::"
            "test_every_affordance_this_server_mints_is_a_valid_argument",
        ),
    ),
    Replant(
        name="R93-attachment-mode-stops-being-metadata-only",
        behaviour=(
            "`mailweave_get_attachment` accepts a mode other than metadata, so the surface "
            "offers a path to attachment bytes that contract B-04 excludes"
        ),
        path="server/src/mailweave/surface/arguments.py",
        anchor='    if mode != "metadata":\n',
        replacement="    if False:\n",
        caught_by=(
            "tests/test_mcp_surface_round24.py::"
            "test_no_attachment_bytes_are_reachable_from_this_surface",
        ),
    ),
    # --- round 25 -----------------------------------------------------------------------
    #
    # Amendment A11's two rules, the fence's closing side, the estimate that is the wire, the
    # floor's real membership, D.11's partition and the two startup refusals. Each entry names
    # the finding it closes, so a MISSED row says which repair went undefended.
    #
    # R112 is the last of them and was added after the audit: A11's ordering rule reached the
    # *fill* and left the *evidence* scored zero, so A.9a step 3 still protected the oldest k
    # hits by position. It is the same defect as R95 one band over, which is why it is here
    # rather than folded into it - a manifest entry per behaviour, and these are two.
    Replant(
        name="R94-a-thread-constant-component-admits-again",
        behaviour=(
            "A11/DISC-01: every fact of a candidate counts as message-discriminating, so a "
            "term carried in the thread's one subject line admits every message again and six "
            "materially different queries produce one representation (R-DISC-017)"
        ),
        path="server/src/mailweave/disclosure/weights.py",
        anchor="    if len(candidates) < 2:\n        return frozenset()\n",
        replacement="    if True:\n        return CANDIDATE_FACTS\n",
        caught_by=(
            "tests/test_round25.py::test_five_queries_over_one_thread_produce_different_included_sets",
            "tests/test_round25.py::"
            "test_a_component_that_fires_on_every_candidate_of_a_thread_does_not_admit",
        ),
    ),
    Replant(
        name="R95-query-independent-components-order-the-fill-again",
        behaviour=(
            "A11's ordering half: the published sum re-enters the ranking key, so on a thread "
            "the query reached uniformly the E4 order is POSITION_ADJACENCY's - which is "
            "Baseline F's window, position for position (R-DISC-018)"
        ),
        path="server/src/mailweave/disclosure/weights.py",
        anchor="    keeping.sort(key=lambda pair: (-pair[1].anchored_value, pair[0].position))\n",
        replacement="    keeping.sort(key=lambda pair: (-pair[1].value, pair[0].position))\n",
        caught_by=(
            "tests/test_round25.py::"
            "test_the_e4_ranking_on_a_shared_subject_thread_is_not_the_plus_minus_two_window",
        ),
    ),
    Replant(
        name="R96-the-text-mirror-fence-closes-on-a-literal-again",
        behaviour=(
            "R-MCP-002: the fenced block ends at the first `>>>` rather than at this "
            "response's nonce, so a body line ending in three characters any sender can type "
            "puts forged withheld records, sources, rows and affordances into the text a model "
            "reads, in the connector's voice"
        ),
        path="server/src/mailweave/surface/rendering.py",
        anchor='        closer = f" {opened.group(1)}>>>"\n',
        replacement='        closer = ">>>"\n',
        caught_by=(
            "tests/test_round25.py::test_no_closing_sequence_a_sender_can_write_ends_the_fence",
        ),
    ),
    Replant(
        name="R97-a-withheld-record-costs-nothing-again",
        behaviour=(
            "R-DISC-022/R-MCP-003: A.9a steps 7 and 8 look free, so a response that could not "
            "carry four hundred rows 'fits' four hundred pointers to them and renders more "
            "wire than it started with, under a declared ceiling of 500 tokens"
        ),
        path="server/src/mailweave/disclosure/layout.py",
        # Re-anchored round 29: the per-record charge is over the *named* withheld ids now
        # (the grouped ones are charged as groups on the next line); the replant still zeroes
        # the record charge, which is the behaviour R97 is about.
        # Re-anchored 2026-09-15 (R-M2-095): the terms are built as `CostTerms` fields now.
        anchor="        records=WITHHELD_RECORD_TOKENS * len(layout.named_withheld_ids),\n",
        replacement="        records=0 * len(layout.named_withheld_ids),\n",
        caught_by=("tests/test_round25.py::test_a_withheld_record_is_charged_what_it_costs",),
    ),
    Replant(
        name="R98-the-driver-stops-checking-that-a-step-shrank-the-response",
        behaviour=(
            "A11/R-DISC-019: the third driver-level gate goes, so a rung that enlarges the "
            "layout it is degrading is applied instead of refused - the defect that took a "
            "9,300-token layout to 27,270 and then refused it"
        ),
        path="server/src/mailweave/disclosure/ladder.py",
        anchor=(
            "        assert_cost_did_not_rise(\n"
            "            before, after, precedence=step.precedence, name=step.name, bounds=bounds\n"
            "        )\n"
        ),
        replacement="        pass\n",
        caught_by=(
            "tests/test_round25.py::test_the_drivers_gate_refuses_a_step_that_inflates_the_response",
        ),
    ),
    Replant(
        name="R99-the-floor-skips-a-member-that-is-itself-a-hit",
        behaviour=(
            "R-DISC-021: `floor_of` drops a hit from the protection set, so A.9a step 8 "
            "withholds a disclosed hit's direct child and the surviving hit's reply chain has "
            "a hole in it filled by a bare pointer - the project's biggest claim, silently"
        ),
        path="server/src/mailweave/disclosure/floor.py",
        anchor="            if member_id in seen:\n                continue\n",
        replacement=(
            "            if member_id in hits or member_id in seen:\n                continue\n"
        ),
        caught_by=("tests/test_round25.py::test_the_floor_is_what_the_reply_tree_says_it_is",),
    ),
    Replant(
        name="R100-assemble-reads-the-plan-instead-of-the-ladders-output",
        behaviour=(
            "round 25: every A.9a step is computed, declared in `truncated_by` and then "
            "discarded before the wire, so a thread that reached step 5 emits its collapsed "
            "members as rows as well and the response is refused by its own model"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor=(
            "        planned = replace(planned_by_thread[planned_source.thread_id], "
            "source=planned_source)\n"
        ),
        replacement="        planned = planned_by_thread[planned_source.thread_id]\n",
        caught_by=(
            "tests/test_round25.py::test_the_estimate_is_an_upper_bound_on_the_rendered_wire",
        ),
    ),
    Replant(
        name="R101-every-gmail-fault-escapes-the-tool-surface-again",
        behaviour=(
            "R-MCP-001: `call` stops catching `GmailFault`, so a deleted message, a 5xx, a "
            "rate limit and an expired grant all reach the client as -32603 Internal server "
            "error and four D.11 codes can never reach the partition"
        ),
        path="server/src/mailweave/surface/server.py",
        anchor="    except GmailFault as fault:\n",
        replacement="    except _NeverRaised as fault:  # type: ignore[name-defined]\n",
        caught_by=(
            "tests/test_round25.py::"
            "test_every_gmail_fault_lands_on_the_side_its_own_code_puts_it_on",
        ),
    ),
    Replant(
        name="R102-the-access-token-is-never-refreshed-again",
        behaviour=(
            "R-MCP-009: the expiry check goes, so the process exchanges one token for its "
            "whole life and every call after `expires_in` fails permanently with no recovery "
            "and no instruction"
        ),
        path="server/src/mailweave/auth/consent.py",
        anchor="        return self._clock() < self._deadline - TOKEN_REFRESH_SKEW_S\n",
        replacement="        return True\n",
        caught_by=("tests/test_round25.py::test_the_access_token_is_refreshed_when_it_expires",),
    ),
    Replant(
        name="R103-four-startup-failures-collapse-into-one-code-again",
        behaviour=(
            "R-MCP-006: the broad catch returns, so a refused refresh, a narrowed grant and a "
            "revoked token are all reported as `auth_profile_underivable` with 'check network "
            "and credentials' - and GMAIL-06's re-auth instruction never appears at startup"
        ),
        path="server/src/mailweave/surface/runtime.py",
        anchor="    except (GmailAuthExpired, ConsentFailed, TokenStoreError):\n",
        replacement="    except _NeverRaised:  # type: ignore[name-defined]\n",
        caught_by=(
            "tests/test_round25.py::test_each_startup_credential_failure_reports_itself_as_itself",
        ),
    ),
    Replant(
        name="R104-verify-permissions-stats-before-it-checks-existence-again",
        behaviour=(
            "R-MCP-007: `mailweave serve` tracebacks with FileNotFoundError on a first run, "
            "which is the exact condition OD-6 criterion 1's companion sentence is about"
        ),
        path="server/src/mailweave/auth/tokenstore.py",
        anchor="        except FileNotFoundError as missing:\n",
        replacement="        except _NeverRaised as missing:  # type: ignore[name-defined]\n",
        caught_by=(
            "tests/test_round25.py::"
            "test_serve_refuses_rather_than_tracebacks_when_no_credential_is_stored",
        ),
    ),
    Replant(
        name="R105-doctor-stops-checking-the-oauth-client-file",
        behaviour=(
            "R-MCP-008: `doctor` exits 0 for the 0644 client JSON that `serve` and `auth "
            "login` both refuse, so the printed remedy points at a tool that passes"
        ),
        path="server/src/mailweave/cli.py",
        anchor="    if client_path.exists():\n",
        replacement="    if False:\n",
        caught_by=("tests/test_round25.py::test_doctor_diagnoses_the_oauth_client_files_mode",),
    ),
    Replant(
        name="R106-a-decision-verb-at-the-end-of-a-sentence-is-invisible-again",
        behaviour=(
            "R-DISC-027: the tokenizer keeps a trailing full stop, so `decided.` and "
            "`decided` are two tokens and the decision lexicon is blind to the commonest "
            "position of the word it is looking for"
        ),
        path="server/src/mailweave/query/analysis.py",
        anchor="    return word.rstrip(_TRAILING_PUNCTUATION)\n",
        replacement="    return word\n",
        caught_by=(
            "tests/test_round25.py::test_a_decision_verb_at_the_end_of_a_sentence_is_one_token",
        ),
    ),
    Replant(
        name="R107-a-lowered-disclosed-token-ceiling-is-unrepresentable-again",
        behaviour=(
            "R-MCP-004: the wire model refuses an applied ceiling below the published one, so "
            "every value of D.1's `budget.max_disclosed_tokens` that does anything is answered "
            "with -32602 INVALID_PARAMS - the server telling the caller their request was bad"
        ),
        path="server/src/mailweave/envelope/wire.py",
        anchor="        if self.applied != self.normal and not self.why:\n",
        replacement=(
            "        if self.applied < self.normal:\n"
            '            raise ValueError("applied ceiling below the normal ceiling")\n'
            "        if self.applied != self.normal and not self.why:\n"
        ),
        caught_by=(
            "tests/test_round25.py::test_a_lowered_disclosed_token_ceiling_is_accepted_and_applied",
        ),
    ),
    Replant(
        name="R108-view-null-defeats-the-required-view-check-again",
        behaviour=(
            'R-MCP-011: `{"view": null}` is served at `body_clean` - a depth the caller did '
            "not ask for and the one that costs a messages.get(format=full)"
        ),
        path="server/src/mailweave/surface/arguments.py",
        anchor='    if "view" in reader.raw and reader.raw["view"] is None:\n',
        replacement="    if False:\n",
        caught_by=("tests/test_round25.py::test_view_null_is_refused_rather_than_defaulted",),
    ),
    Replant(
        name="R109-an-unbounded-query-reaches-an-unwrapped-httpx-error-again",
        behaviour=(
            "R-MCP-013: `httpx.InvalidURL` is not an `httpx.HTTPError`, so it crosses the "
            "Gmail layer bare and falsifies that layer's own stated invariant"
        ),
        path="server/src/mailweave/gmail/client.py",
        anchor="            except httpx.InvalidURL as malformed:\n",
        replacement="            except _NeverRaised as malformed:  # type: ignore[name-defined]\n",
        caught_by=(
            "tests/test_round25.py::"
            "test_a_query_too_long_for_a_gmail_url_is_refused_before_it_is_sent",
        ),
    ),
    Replant(
        name="R110-the-ladder-exhausted-escapes-the-dispatcher-again",
        behaviour=(
            "R-DISC-020: `DisclosureLadderExhausted` is a MailweaveError in none of `call`'s "
            "except clauses, so a thread large enough to reach it kills the tool call with an "
            "internal error carrying no remediation and no affordance"
        ),
        path="server/src/mailweave/surface/server.py",
        anchor="    except DisclosureLadderExhausted as exhausted:\n",
        replacement="    except _NeverRaised as exhausted:  # type: ignore[name-defined]\n",
        caught_by=(
            "tests/test_round25.py::"
            "test_an_exhausted_ladder_becomes_a_declared_refusal_and_not_a_traceback",
        ),
    ),
    Replant(
        name="R111-step-5-collapses-by-band-instead-of-by-depth-again",
        behaviour=(
            "R-DISC-030: only rows the planner banded MAP are collapsible, so the ladder "
            "cannot recover the tokens its own earlier steps spent and an oversized response "
            "reaches step 8 with hundreds of uncollapsed stub rows still in it"
        ),
        path="server/src/mailweave/disclosure/ladder.py",
        # Re-pointed after the navigation redesign (2026-09-14): the rule gained the
        # `Band.REQUESTED` exemption; the replant restores the by-band reading for the rest.
        anchor=(
            "    return [\n"
            "        row for row in source.rows if row.depth is Depth.STUB and row.band is not "
            "Band.REQUESTED\n"
            "    ]\n"
        ),
        replacement=(
            "    return [\n"
            "        row\n"
            "        for row in source.rows\n"
            "        if row.band is Band.MAP and row.depth is Depth.STUB\n"
            "    ]\n"
        ),
        caught_by=(
            "tests/test_round25.py::test_a_stub_row_is_collapsible_whatever_band_planned_it",
        ),
    ),
    Replant(
        name="R112-a-hit-is-scored-zero-so-oldest-k-keeps-its-body-again",
        behaviour=(
            "R-DISC-026: every evidence row carries `fill_score = 0` because the fill never "
            "scores hits, so A.9a step 3's tie-break IS its selection and the protected hit "
            "bodies are the oldest k by thread position - EV-02's degenerate strategy, in "
            "both arms, for every query, under the published score's name"
        ),
        path="server/src/mailweave/disclosure/plan.py",
        anchor=(
            "            band, wanted, ranked = Band.EVIDENCE, evidence_view, "
            "hits.get(message_id, 0)\n"
        ),
        replacement="            band, wanted, ranked = Band.EVIDENCE, evidence_view, 0\n",
        caught_by=(
            "tests/test_round25.py::test_which_hit_keeps_its_body_is_not_the_oldest_k_by_position",
            "tests/test_round25.py::test_the_two_arms_sacrifice_evidence_depth_in_the_same_order",
        ),
    ),
    Replant(
        name="R113-the-row-mirror-stops-reading-back-the-facts-it-renders",
        behaviour=(
            "R-MCP-010: the row mirror carries id, position, role and depth only, so `reason`, "
            "`linkage`, `mailbox` and `reply_parent_id` are rendered and never round-tripped - "
            "a rendering that writes `reason semantic cosine 0.99` on every row, naming a "
            "mechanism this system does not have, passes the whole suite"
        ),
        path="server/src/mailweave/surface/rendering.py",
        anchor=(
            '            row.get("linkage"),\n'
            '            row.get("reply_parent_id"),\n'
            '            mailbox_token(row.get("mailbox")),\n'
            '            row.get("reason"),\n'
        ),
        replacement="",
        caught_by=(
            "tests/test_round25.py::"
            "test_a_fabricated_row_fact_fails_the_mirror_rather_than_passing_the_suite",
        ),
    ),
    Replant(
        name="R114-a-spam-row-says-nothing-about-its-mailbox-in-the-text",
        behaviour=(
            "R-MCP-010 / OD-6 criterion 4: the text a model reads omits the row's mailbox "
            "provenance entirely, so a spam or trash result is indistinguishable from an inbox "
            "one for a client reading the mirror"
        ),
        path="server/src/mailweave/surface/rendering.py",
        anchor='    regions = provenance.get("regions") or ()\n',
        replacement="    regions = ()\n",
        caught_by=("tests/test_round25.py::test_a_spam_row_says_so_in_the_text_a_model_reads",),
    ),
    # --- round 26: the eight that stood between here and a truthful demonstration --------
    Replant(
        name="R115-the-reply-prefix-is-content-again",
        behaviour=(
            "R-DISC-031: `fact_values` tokenises the raw subject, so `S` and `Re: S` are two "
            "subjects, `subject` is message-discriminating on every Gmail thread of more than "
            "one message, and amendment A11 stops applying to the fact it was written about"
        ),
        path="server/src/mailweave/disclosure/weights.py",
        anchor="        SUBJECT: _tokens(strip_reply_prefixes(candidate.subject)),\n",
        replacement="        SUBJECT: _tokens(candidate.subject),\n",
        caught_by=(
            "tests/test_round26.py::test_a_reply_prefix_is_not_a_message_discriminating_fact",
            "tests/test_round26.py::"
            "test_five_queries_over_a_gmail_shaped_thread_produce_different_fills",
        ),
    ),
    Replant(
        name="R116-hit-ranks-loses-the-all-or-none-sweep",
        behaviour=(
            "R-DISC-034: `hit_ranks` reads `anchored_value` without A11's second guard, so a "
            "component anchored on every hit gives every hit the same nonzero value and the "
            "position tie-break becomes the whole selection - oldest-K under the policy's name"
        ),
        path="server/src/mailweave/disclosure/plan.py",
        anchor=(
            "    return {result.message_id: result.anchored_value "
            "for _, result in a11_scores(pool, query)}\n"
        ),
        replacement=(
            "    from mailweave.disclosure.weights import message_discriminating_facts, score\n"
            "\n"
            "    discriminating = message_discriminating_facts(pool)\n"
            "    return {\n"
            "        c.message_id: score(c, query, discriminating=discriminating).anchored_value\n"
            "        for c in pool\n"
            "    }\n"
        ),
        caught_by=(
            "tests/test_round26.py::"
            "test_hit_ranks_on_gmail_shape_is_a_stated_zero_and_not_a_uniform_nonzero",
        ),
    ),
    Replant(
        name="R117-the-surface-stops-measuring-the-rendered-result",
        behaviour=(
            "R-DISC-033 / R-MCP-021: the last measurement before the wire goes, so a response "
            "the ladder's estimate got wrong is handed to a host that cuts it above the SDK, "
            "where nothing in this process can observe the cut or declare it"
        ),
        path="server/src/mailweave/surface/partition.py",
        anchor="    if size > HOST_RESULT_CHAR_CAP:\n",
        replacement="    if size > 10**9:\n",
        caught_by=(
            "tests/test_round26.py::"
            "test_the_surface_refuses_an_over_cap_result_even_when_the_ladder_passed_it",
        ),
    ),
    Replant(
        name="R118-the-ladder-stops-fitting-the-hosts-character-cap",
        behaviour=(
            "R-DISC-033: `over_budget` forgets the character half, so A.9a degrades only until "
            "the token ceiling is met and an ordinary twelve-message thread goes over the "
            "host's cap declaring `truncated_by: null` and `included: 12 of 12`"
        ),
        path="server/src/mailweave/disclosure/ladder.py",
        anchor=(
            "    if layout.cost() > layout.ceiling_applied:\n"
            "        return True\n"
            "    return bounds.host_chars is not None and layout.chars() > bounds.host_chars\n"
        ),
        replacement="    return layout.cost() > layout.ceiling_applied\n",
        caught_by=(
            "tests/test_round26.py::test_no_served_response_crosses_the_hosts_character_cap",
        ),
    ),
    Replant(
        name="R119-the-participant-index-is-free-again",
        behaviour=(
            "R-DISC-032: `measure_tokens` charges nothing for `Source.participants`, which is "
            "82 % of the rendered response on a mailing-list thread, so the estimate the "
            "ceiling is enforced against is not an upper bound on the thing it bounds"
        ),
        path="server/src/mailweave/envelope/measure.py",
        anchor=(
            "        total += participants_tokens(source.participants) + SOURCE_STRUCTURAL_TOKENS\n"
        ),
        replacement="        total += SOURCE_STRUCTURAL_TOKENS\n",
        caught_by=(
            "tests/test_round26.py::test_the_participant_index_is_charged_what_the_wire_carries",
        ),
    ),
    Replant(
        name="R120-a-sender-chosen-filename-is-unbounded-again",
        behaviour=(
            "R-MCP-016: `AttachmentMetadata`'s sender-chosen fields lose their bound, so one "
            "newline in a filename puts a forged withheld record, a forged source and a forged "
            "message row into the residue a model reads, in this connector's voice"
        ),
        path="server/src/mailweave/envelope/wire.py",
        anchor="    filename: SenderScalar = Field(max_length=MAX_ATTACHMENT_FILENAME_CHARS)\n",
        replacement='    filename: str = Field(default="")\n',
        caught_by=(
            "tests/test_round26.py::test_no_sender_chosen_attachment_field_can_carry_a_line_break",
            "tests/test_round26.py::test_the_sender_chosen_fields_are_the_ones_the_sweep_names",
        ),
    ),
    Replant(
        name="R121-the-mirror-stops-checking-that-a-line-is-a-line",
        behaviour=(
            "R-MCP-016, the structural half: the renderer's own invariant goes, so a field "
            "added later whose value a sender chooses writes a second record in this "
            "connector's voice and nothing notices"
        ),
        path="server/src/mailweave/surface/rendering.py",
        anchor="        if line and not is_one_line(line):\n",
        replacement="        if line and False:\n",
        caught_by=(
            "tests/test_round26.py::"
            "test_the_text_mirror_refuses_to_write_a_value_that_spans_two_lines",
        ),
    ),
    Replant(
        name="R122-a-credential-failure-escapes-the-partition-again",
        behaviour=(
            "R-MCP-017: `call` loses its credential clause, so a refresh refused mid-session "
            "and a vanished credential store reach the client as `-32603 Internal server "
            "error` with GMAIL-06's `mailweave auth login` instruction thrown away"
        ),
        path="server/src/mailweave/surface/server.py",
        anchor="    except (ConsentFailed, TokenStoreError) as credential:\n",
        replacement="    except ArgumentInvalid as credential:\n",
        caught_by=(
            "tests/test_round26.py::"
            "test_a_credential_failure_reaches_the_client_as_the_instruction_it_is",
        ),
    ),
    # --- round 29 -------------------------------------------------------------------------
    Replant(
        name="R123-the-emptiness-gate-is-removed",
        behaviour=(
            "R-MCP-039 and R-MCP-033 requirement 5: the ladder converges on a response that "
            "carries no evidence and serves it. For a `body_full` read at the cap's edge that "
            "is the zero-evidence envelope the response model refuses and the caller sees as "
            "`-32603`; for a search it is an empty answer served as success"
        ),
        path="server/src/mailweave/disclosure/ladder.py",
        anchor="    if _carries_nothing(working):\n",
        replacement="    if False:\n",
        # Since the navigation redesign (2026-09-14) the expansion producer declines a read
        # that fits nothing *before* the ladder runs (`expansion._fit` returns no arrangement),
        # so the `body_full` citation no longer exercises this gate; it still holds the
        # behaviour and is covered by `test_r_mcp_039_round29` on its own. The search path is
        # the one that reaches the gate, and its citation is the one that catches this.
        caught_by=(
            "tests/test_r_mcp_033_round29.py::"
            "test_no_compression_lets_an_empty_answer_be_served_as_success",
        ),
    ),
    Replant(
        name="R124-a-retry-repeats-the-failed-call",
        behaviour=(
            "R-MCP-033 requirement 4: a decline offers back the arguments that just failed - "
            "round 28's live diagnostic at `max_hit_threads: 1` - and a client following it "
            "loops without end"
        ),
        path="server/src/mailweave/surface/recovery.py",
        # The halving proposes the width that just failed. `is_the_same_call` then refuses to
        # emit it - which is the guard doing its job - and the chain ends one hop early with
        # no retry at all, which is what the schedule test sees. The first version of this
        # replant substituted a *narrower* width and was caught by nothing, because a narrower
        # retry is not the defect; a repeated one is.
        # Re-anchored 2026-09-15 (R-M2-095): the halving is the branch without a cause.
        anchor="            proposed = max(1, applied // 2) if fit is None else fit\n",
        replacement="            proposed = applied if fit is None else fit\n",
        caught_by=(
            "tests/test_recovery_chain_round29.py::"
            "test_following_the_pure_schedule_from_the_top_ends_within_the_bound",
            "tests/test_recovery_chain_round29.py::"
            "test_a_search_narrows_by_halving_and_declares_it",
        ),
    ),
    Replant(
        name="R125-grouped-withholdings-are-not-counted-against-H",
        behaviour=(
            "R-MCP-033 requirement 7: the certificate's hit accounting counts only the named "
            "records, so a response whose omissions are grouped under-reports what it withheld "
            "and `H == disclosed union withheld` is checked against a smaller withheld"
        ),
        path="server/src/mailweave/envelope/response.py",
        anchor=(
            "            + sum(group.message_count for group in self.disposition.withheld_groups)\n"
        ),
        replacement="            + 0\n",
        caught_by=(
            "tests/test_r_mcp_033_round29.py::"
            "test_h_equals_disclosed_union_withheld_over_the_original_identities",
        ),
    ),
    Replant(
        name="R126-budget-cap-records-are-not-charged-for-the-query-they-carry",
        behaviour=(
            "R-V01-013(a): a budget or clock cap's withheld records each carry the caller's "
            "search, query included; charging them at the flat constant lets twenty-four such "
            "records render thousands of characters past the estimate on a long query"
        ),
        path="server/src/mailweave/disclosure/layout.py",
        anchor=(
            "                layout.query_chars if message_id in layout.query_bearing_ids else 0,\n"
        ),
        replacement="                0,\n",
        caught_by=(
            "tests/test_r_mcp_033_round29.py::"
            "test_budget_cap_shapes_are_estimated_at_or_above_what_they_render_at_any_query_length",
        ),
    ),
    Replant(
        name="R127-a-read-by-map-id-and-positions-has-no-narrowing-schedule",
        behaviour=(
            "R-V01-010 (recheck): a `get_messages` read naming its messages by `map_id` plus "
            "`positions` fell through every branch of the schedule and was declared final at "
            "`body_full` with the `view` hop never offered"
        ),
        path="server/src/mailweave/surface/recovery.py",
        anchor=(
            '        isinstance(arguments.get("message_ids"), list)\n'
            '        or isinstance(arguments.get("positions"), list)\n'
        ),
        replacement=('        isinstance(arguments.get("message_ids"), list)\n        or False\n'),
        caught_by=(
            "tests/test_recovery_chain_round29.py::"
            "test_a_read_by_map_id_and_positions_runs_the_same_schedule",
            "tests/test_r_mcp_039_round29.py::"
            "test_a_read_by_map_id_and_positions_gets_the_same_view_hop",
        ),
    ),
    Replant(
        name="R128-a-width-cap-withholds-without-naming-itself-in-budget-caps-hit",
        behaviour=(
            "AD A.7 lists max_hit_threads among the global per-query caps and AD D.11 routes a "
            "reached per-query cap to in-band budget_caps_hit; without the sweep a cap that "
            "withheld forty-four of forty-five messages is absent from the cap list, and "
            "D.3 rule 5 then lets the response call itself answered"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor="        if named not in caps_hit:\n            caps_hit = (*caps_hit, named)\n",
        replacement="        if False:\n            caps_hit = (*caps_hit, named)\n",
        caught_by=(
            "tests/test_v0_1_acceptance_round30.py::"
            "test_every_cap_that_withheld_content_names_itself_in_budget_caps_hit",
            "tests/test_v0_1_acceptance_round30.py::"
            "test_a_response_that_hit_a_cap_never_calls_itself_answered",
        ),
    ),
    Replant(
        name="R129-omission-bound-names-a-ceiling-that-never-bound",
        behaviour=(
            "OmissionSummary.bound documents itself as None when the ladder reduced nothing; "
            "stated unconditionally it asserts the token ceiling on a response well inside "
            "both ceilings whose omissions were all cap-driven, which is the wrong cap and "
            "sends a reader to the wrong argument"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor="    if a_ceiling_bound(disclosure.layout, reduced=bool(disclosure.steps)):\n",
        replacement="    if True:\n",
        caught_by=(
            "tests/test_v0_1_acceptance_round30.py::"
            "test_the_acceptance_shape_states_no_ceiling_it_did_not_reach",
            "tests/test_v0_1_acceptance_round30.py::"
            "test_the_declarations_agree_on_every_shape_and_the_response_still_fits",
        ),
    ),
    Replant(
        name="R130-the-expansion-producer-states-a-ceiling-that-never-bound",
        behaviour=(
            "the same defect as R129 in the other producer: thread_map and get_messages state "
            "omission.bound unconditionally. R129 anchors on assemble.py alone, and reverting "
            "this gate left a hundred tests green across ten files (R-V30-006)"
        ),
        path="server/src/mailweave/surface/expansion.py",
        anchor="    if a_ceiling_bound(layout, reduced=reduced):\n",
        replacement="    if True:\n",
        caught_by=(
            "tests/test_v0_1_acceptance_round30.py::"
            "test_the_expansion_producer_states_its_bound_on_the_same_rule",
        ),
    ),
    Replant(
        name="R131-a-depth-only-reduction-names-no-ceiling",
        behaviour=(
            "the A.9a ladder can degrade a response by depth alone, splitting nothing off and "
            "withholding nothing; without the `reduced` term omission.bound is silent while "
            "truncated_by reads mailweave and budget_caps_hit names the ceiling (R-V30-005)"
        ),
        path="server/src/mailweave/disclosure/layout.py",
        anchor=(
            "    return bool(reduced or layout.host_capped or layout.split_off "
            "or layout.withheld_ids)\n"
        ),
        replacement=(
            "    return bool(layout.host_capped or layout.split_off or layout.withheld_ids)\n"
        ),
        caught_by=(
            "tests/test_v0_1_acceptance_round30.py::"
            "test_a_depth_only_reduction_still_names_the_ceiling_that_bound",
        ),
    ),
    # -- M1: Orivra's contracts, the adapter boundary, the surface and the seeder ---------
    #
    # One entry per behaviour M1 introduced that the design states in prose, in the order
    # the milestone built them: the four gates of a source-stated assertion (owner
    # correction 8), the edge-visibility rule, the graph's span check, the translation that
    # must not lose round 29's granularity or confuse a ceiling with a cap, the
    # compatibility claim on the published surface, the settle gate, the outcome-rate rule,
    # the presence-free record, the guard trees, and the freshness rule on a node.
    Replant(
        name="R132-negation-cues-are-scanned",
        behaviour=(
            "a source-stated edge is refused when its clause carries a negation cue; without "
            'the scan "we are not withdrawing the approval" produces '
            "obs.said.supersedes_stated and Orivra reports a withdrawal the source denied "
            "(owner correction 8, plan \u00a74.5 rule 3)"
        ),
        path="orivra/src/orivra/recognise/stated.py",
        anchor=('    cues += _phrase_hits(folded, NEGATION_CUES, "negation")\n'),
        replacement=("    cues += []\n"),
        caught_by=(
            "tests/test_orivra_stated_assertions.py::test_a_negated_withdrawal_produces_no_edge",
        ),
    ),
    Replant(
        name="R133-a-quoted-span-is-not-this-senders-assertion",
        behaviour=(
            "a span overlapping QUOTED, FORWARDED, SIGNATURE or UNCERTAIN content cannot "
            "support a source-stated edge; without the class gate a correspondent's "
            "withdrawal is attributed to this message's sender (plan \u00a74.5 rule 3, quotation "
            "case)"
        ),
        path="orivra/src/orivra/recognise/stated.py",
        anchor=(
            "ASSERTABLE_CLASSES: Final[frozenset[SpanClass]] = frozenset({SpanClass.ORIGINAL})\n"
        ),
        replacement=("ASSERTABLE_CLASSES: Final[frozenset[SpanClass]] = frozenset(SpanClass)\n"),
        caught_by=(
            "tests/test_orivra_stated_assertions.py::test_a_quoted_withdrawal_is_not_this_senders_assertion",
        ),
    ),
    Replant(
        name="R134-a-deictic-phrase-identifies-nothing",
        behaviour=(
            'a referring phrase that only points ("the earlier version") never resolves, '
            "whatever the candidate count; without the rule a resolver with one candidate in "
            "scope resolves uniquely every time and the uniqueness comes from the scope "
            "rather than the sentence (plan \u00a74.5 rule 2)"
        ),
        path="orivra/src/orivra/recognise/stated.py",
        anchor=(
            "    if stripped in {_fold(phrase) for phrase in DEICTIC_PHRASES} or not "
            "_distinguishing(folded):\n"
        ),
        replacement=("    if False:\n"),
        caught_by=(
            "tests/test_orivra_stated_assertions.py::test_a_deictic_phrase_does_not_resolve_even_with_one_candidate_in_scope",
        ),
    ),
    Replant(
        name="R135-a-clause-the-recogniser-cannot-read-is-refused",
        behaviour=(
            "the cue sets are English and a clause in another language is refused rather than "
            "cleared; without the check a German body clears because no cue was recognised "
            "rather than because none is there, which is the failure mode that looks most "
            "like success"
        ),
        path="orivra/src/orivra/recognise/stated.py",
        anchor=("    if language != SUPPORTED_LANGUAGE:\n"),
        replacement=("    if False:\n"),
        caught_by=(
            "tests/test_orivra_stated_assertions.py::test_a_clause_the_recogniser_cannot_read_is_refused_rather_than_cleared",
        ),
    ),
    Replant(
        name="R136-an-edge-is-visible-under-its-own-permission",
        behaviour=(
            "every supporting reference of an edge must be covered by the context the edge is "
            "published under; without it an edge built from a third document the caller "
            "cannot read discloses what that document says even though both endpoints are "
            "readable (plan \u00a74.2)"
        ),
        path="orivra/src/orivra/contracts/edges.py",
        anchor=("        if tuple(sorted(one.hash for one in derived)) != tuple(\n"),
        replacement=("        if False and tuple(\n"),
        caught_by=(
            "tests/test_orivra_contracts.py::"
            "test_an_edge_whose_conjunction_understates_its_own_support_is_refused",
        ),
    ),
    Replant(
        name="R137-a-source-stated-edge-arrives-with-its-gates",
        behaviour=(
            "obs.said.* requires a StatedAssertionCheck; without it a claim a human typed is "
            "published with no matched span, no identified target, no cleared clause and "
            "nobody named as having said it - which is a span that proves text exists "
            "standing in for a relationship that is correct (owner correction 8)"
        ),
        path="orivra/src/orivra/contracts/edges.py",
        anchor=(
            "        if self.assertion is Assertion.SOURCE_STATED:\n"
            "            if self.stated is None:\n"
        ),
        replacement=(
            "        if self.assertion is Assertion.SOURCE_STATED:\n            if False:\n"
        ),
        caught_by=(
            "tests/test_orivra_contracts.py::test_a_source_stated_edge_without_its_check_is_refused",
        ),
    ),
    Replant(
        name="R138-every-span-string-matches-what-it-quotes",
        behaviour=(
            "a span must reproduce the source content at its offsets, checked where the "
            "quoted node is in scope; without it a quotation that no longer matches its "
            "source is published as evidence and GraphRAG's covariate rule becomes advisory "
            "(plan \u00a74.4)"
        ),
        path="orivra/src/orivra/contracts/graph.py",
        anchor=("            if content[span.start : span.end] != span.text:\n"),
        replacement=("            if False:\n"),
        caught_by=(
            "tests/test_orivra_contracts.py::test_every_span_string_matches_the_content_it_quotes",
        ),
    ),
    Replant(
        name="R139-a-withheld-group-stays-a-group",
        behaviour=(
            "round 29's granularity rule survives the translation into Orivra's contracts: a "
            "group is a container record, not one node record per message. Splitting it mints "
            "one handle per message for a call that returns them all, which is the "
            "23,220-character failure R-MCP-033 recorded"
        ),
        path="orivra/src/orivra/gmail_adapter.py",
        anchor=("        granularity=Granularity.CONTAINER,\n"),
        replacement=("        granularity=Granularity.NODE,\n"),
        caught_by=(
            "tests/test_orivra_adapter.py::test_a_group_stays_a_group_because_granularity_is_the_call_that_recovers_it",
        ),
    ),
    Replant(
        name="R140-a-ceiling-is-not-a-cap",
        behaviour=(
            "a disclosed-token ceiling is reported as OmissionCause.CEILING, not as a cap; "
            "without the split a caller is sent to raise a cap that was not the reason, and "
            "widening a ceiling and raising a cap are different actions"
        ),
        path="orivra/src/orivra/gmail_adapter.py",
        anchor=("    if cap in _CEILING_CAPS:\n        return OmissionCause.CEILING\n"),
        replacement=("    if False:\n        return OmissionCause.CEILING\n"),
        caught_by=(
            "tests/test_orivra_adapter.py::test_a_ceiling_is_not_reported_as_a_cap_a_caller_could_raise",
        ),
    ),
    Replant(
        name="R141-mailweaves-four-tools-are-published-unchanged",
        behaviour=(
            "the four mailweave_* tools are published by MailWeave's own as_tool over "
            "MailWeave's own specs; giving them an Orivra outputSchema adds a field to the "
            "frozen v0.1 surface, which is exactly the silent divergence M1's compatibility "
            "claim is about"
        ),
        path="orivra/src/orivra/surface/server.py",
        anchor=("            *(as_tool(spec) for spec in MAILWEAVE_TOOL_SPECS),\n"),
        replacement=("            *(as_orivra_tool(ASK) for spec in MAILWEAVE_TOOL_SPECS),\n"),
        caught_by=(
            "tests/test_orivra_surface.py::test_mailweave_tools_gain_no_output_schema_on_this_surface",
        ),
    ),
    Replant(
        name="R142-the-settle-gate-needs-two-agreeing-polls",
        behaviour=(
            "EP \u00a73.6's gate requires two agreeing polls an interval apart; with one, Gmail's "
            "eventual consistency lets a single agreeing poll be followed by a disagreeing "
            "one and every recall number afterwards measures indexing delay rather than "
            "retrieval"
        ),
        path="harness/src/mailweave_harness/seed/substrate.py",
        anchor=("        if agreements == 2:\n"),
        replacement=("        if agreements == 1:\n"),
        caught_by=(
            "tests/test_seeder.py::test_the_gate_requires_two_agreeing_polls_an_interval_apart",
        ),
    ),
    Replant(
        name="R143-inconclusive-is-not-a-false-not-found",
        behaviour=(
            "inconclusive asserts no nonexistence and is excluded from FNF (OD-2); folding it "
            "in punishes the honest answer the whole outcome vocabulary exists to allow, and "
            "hides it inside a rate named for something else"
        ),
        path="harness/src/mailweave_harness/seed/metrics.py",
        anchor=(
            "    false_not_found = sum(1 for one in answerable if one is Terminal.NOT_FOUND) / "
            "len(answerable)\n"
        ),
        replacement=(
            "    false_not_found = sum(\n"
            "        1 for one in answerable if one is not Terminal.ANSWERED\n"
            "    ) / len(answerable)\n"
        ),
        caught_by=("tests/test_seeder.py::test_inconclusive_is_not_counted_as_a_false_not_found",),
    ),
    Replant(
        name="R144-a-presence-free-record-is-free-of-presence",
        behaviour=(
            "where even the existence of an omitted thing is unauthorised, only the connector "
            "and the cause survive; a presence-free record that still carried an id, a count "
            "or a handle would disclose all three, which is what plan \u00a74.2's degradation "
            "exists to prevent"
        ),
        path="orivra/src/orivra/contracts/omission.py",
        anchor=("        if self.what or self.count is not None or self.recover is not None:\n"),
        replacement=("        if False:\n"),
        caught_by=(
            "tests/test_orivra_contracts.py::test_the_presence_free_form_is_free_of_presence",
        ),
    ),
    Replant(
        name="R145-the-guards-sweep-every-server-side-tree",
        behaviour=(
            "the CI guards sweep every workspace member that runs with the server credential, "
            "derived from the workspace rather than listed; with server/src alone, orivra/src "
            "is covered by no sweep and the scope-literal, generative-client and disk-write "
            "guards all name more than they check"
        ),
        path="tools/guards/__main__.py",
        anchor=(
            '        if member not in DESTRUCTIVE_CAPABLE and (root / member / "src").is_dir()\n'
        ),
        replacement=('        if member == "server" and (root / member / "src").is_dir()\n'),
        caught_by=(
            "tests/test_guards.py::test_the_guards_sweep_every_workspace_member_that_runs_server_side",
        ),
    ),
    Replant(
        name="R146-a-node-that-failed-verification-serves-no-content",
        behaviour=(
            "a node whose freshness verification failed may exist, to account for an "
            "omission, but may not carry the content that failed verification; without the "
            "rule a stale or access-lost item is served with a caveat, which plan \u00a74.3 "
            "forbids in those words"
        ),
        path="orivra/src/orivra/contracts/nodes.py",
        anchor=("        if not self.freshness.servable and self.content:\n"),
        replacement=("        if False:\n"),
        caught_by=(
            "tests/test_orivra_contracts.py::test_a_node_that_failed_verification_carries_no_content",
        ),
    ),
    # -- The M1 correction pass: what an independent review found, and what defends it now --
    #
    # Each of these removes the *fix* rather than the original behaviour, so a change that
    # reverted a correction fails the test that correction shipped with. The numbering
    # follows the reviewer's finding ids, R-M1-001 to R-M1-020.
    Replant(
        name="R147-a-candidate-key-does-not-match-a-more-specific-phrase",
        behaviour=(
            "target identification requires the candidate's keys to account for every word "
            "the referring phrase used; the bidirectional subset rule let a candidate keyed "
            "on one common word match any phrase containing it, and being the only match made "
            "the resolution unique - an observed supersedes_stated edge against a document "
            "the sentence never named (R-M1-003)"
        ),
        path="orivra/src/orivra/recognise/stated.py",
        anchor=("            if key_words and reference_words <= key_words:\n"),
        replacement=(
            "            if key_words and (reference_words <= key_words or key_words <= referen"
            "ce_words):\n"
        ),
        caught_by=(
            "tests/test_orivra_stated_assertions.py::test_a_candidate_whose_key_is_a_common_word_does_not_match_a_specific_phrase",
        ),
    ),
    Replant(
        name="R148-orivra-uses-mailweaves-error-partition",
        behaviour=(
            "the Orivra surface applies D.11's partition to its own tool handlers; with three "
            "clauses of ten, a GmailFault reached the client as an internal error and a "
            "ValidationError - whose report quotes the input it refused, which here is a "
            "response built out of mail - escaped unhandled (R-M1-001, R-SEC-043)"
        ),
        path="orivra/src/orivra/surface/server.py",
        # Re-pointed 2026-09-21 (second repair): the call passes the tool's published schema
        # to the partition's diagnostic and became a six-line call. The replant is the same
        # one - the partition goes, and the handler's own result is returned bare.
        anchor=(
            "    return in_band(\n"
            "        name,\n"
            "        arguments,\n"
            "        produce,\n"
            "        schema=ORIVRA_SPEC_BY_NAME[OrivraToolName(name)].input_schema,\n"
            "    )\n"
        ),
        replacement=("    return produce()\n"),
        caught_by=(
            "tests/test_orivra_surface.py::test_a_gmail_fault_on_the_orivra_path_is_declared_not_an_internal_error",
        ),
    ),
    Replant(
        name="R149-a-missing-adapter-is-not-every-lookup-error",
        behaviour=(
            "ConnectorUnavailable is its own type; as a LookupError subclass every KeyError "
            "and IndexError inside a handler was reported to the client as "
            "auth_reauth_required with the exception string as the remediation (R-M1-002)"
        ),
        path="orivra/src/orivra/registry.py",
        anchor=("class ConnectorUnavailable(RuntimeError):\n"),
        replacement=("class ConnectorUnavailable(LookupError):\n"),
        caught_by=(
            "tests/test_orivra_adapter.py::test_a_registry_with_no_gmail_adapter_refuses_with_the_remedy",
        ),
    ),
    Replant(
        name="R150-a-collapsed-run-is-accounted-for",
        behaviour=(
            "MailWeave's fourth accounting shape is translated: without it a 300-message "
            "thread the ladder collapsed produced a container node claiming included=300 "
            "beside a handful of children and no omission record at all (R-M1-004)"
        ),
        path="orivra/src/orivra/gmail_adapter.py",
        anchor=(
            "            for run in source.collapsed_runs:\n"
            "                records.append(omission_from_collapsed_run(run, thread_id=source.t"
            "hread_id))\n"
        ),
        replacement=(
            "            for run in []:\n"
            "                records.append(omission_from_collapsed_run(run, thread_id=source.t"
            "hread_id))\n"
        ),
        caught_by=(
            "tests/test_orivra_adapter.py::test_a_collapsed_run_becomes_an_omission_record",
        ),
    ),
    Replant(
        name="R151-a-container-carries-its-collapsed-members",
        behaviour=(
            "container() reads collapsed_runs as well as messages; without it a thread the "
            "ladder compacted came back as a container of eighty with no members and no way "
            "to ask for more (R-M1-005)"
        ),
        path="orivra/src/orivra/gmail_adapter.py",
        anchor=(
            "        for run in source.collapsed_runs:\n            start, _end = run.positions\n"
        ),
        replacement=("        for run in []:\n            start, _end = run.positions\n"),
        caught_by=(
            "tests/test_orivra_adapter.py::test_container_carries_the_members_a_collapsed_run_holds",
        ),
    ),
    Replant(
        name="R152-node-content-is-unfenced",
        behaviour=(
            "a node carries unfenced text, as nodes.py states: fenced content stamps one "
            "response's nonce onto text a later response emits under another, and shifts "
            "every span offset by the length of the opening marker so the graph's "
            "string-match compares the wrong frame (R-M1-006)"
        ),
        path="orivra/src/orivra/gmail_adapter.py",
        anchor=("    return unfence(nonce, row.content.text) or None\n"),
        replacement=("    return row.content.text or None\n"),
        caught_by=(
            "tests/test_orivra_adapter.py::test_node_content_is_unfenced_so_a_span_can_be_checked_against_it",
        ),
    ),
    Replant(
        name="R153-a-version-is-the-messages-own-history-id",
        behaviour=(
            "version_of reads the message's historyId, not users.getProfile()'s mailbox "
            "watermark: with the watermark every message in the account shares one revision, "
            "so no version distinguishes this message changing from anything else changing "
            "(R-M1-008)"
        ),
        path="orivra/src/orivra/gmail_adapter.py",
        anchor=("            revision=message.history_id,\n"),
        replacement=("            revision=client.get_profile().history_id,\n"),
        caught_by=(
            "tests/test_orivra_adapter.py::test_version_of_reads_the_messages_own_history_id",
        ),
    ),
    Replant(
        name="R154-corpus-shapes-do-not-move-with-the-seed",
        behaviour=(
            "thread lengths, evidence positions and distractor placement are drawn from a "
            "generator seeded without master_seed, so EP \u00a75.3's lever holds: a different seed "
            "re-randomises the surface and keeps the shape (R-M1-014)"
        ),
        path="harness/src/mailweave_harness/seed/corpus.py",
        anchor=(
            "        long_length=profile.long_length,\n"
            '        shape_key=f"{GENERATOR_VERSION}:{profile.name}",\n'
        ),
        replacement=(
            "        long_length=profile.long_length,\n        shape_key=str(master_seed),\n"
        ),
        caught_by=(
            "tests/test_seeder.py::test_a_different_seed_keeps_the_sizes_and_the_position_grid",
        ),
    ),
    Replant(
        name="R155-cleanup-asserts-the-seed-account",
        behaviour=(
            "every write in the seeder asserts the authenticated account, deletion included: "
            "a report from a run against one account replayed against another deleted the "
            "second account's messages by the first's ids, and deletion is the one operation "
            "where being wrong is not recoverable (R-M1-013, RR SEC-03)"
        ),
        path="harness/src/mailweave_harness/seed/substrate.py",
        anchor=(
            "    assert_seed_account(\n"
            "        authenticated_address=transport.authenticated_address(), seed_address=seed"
            "_address\n"
            "    )\n"
            "    deleted: list[InsertedMessage] = []\n"
        ),
        replacement=("    deleted: list[InsertedMessage] = []\n"),
        caught_by=(
            "tests/test_seeder.py::test_cleanup_refuses_to_delete_from_a_mailbox_that_is_not_the_seed_account",
        ),
    ),
    Replant(
        name="R156-the-standing-sweeps-read-every-source-tree",
        behaviour=(
            "the standing-cycle sweeps read every workspace member's src, derived rather than "
            "listed: with two of three, the sweep that exists so R-SEC-043 cannot recur never "
            "read orivra/src, and R-SEC-043 recurred there (R-M1-015)"
        ),
        path="tests/fixtures/source_trees.py",
        anchor=('TREES = tuple(Path(member) / "src" for member in _members())\n'),
        replacement=('TREES = (Path("server/src"), Path("harness/src"))\n'),
        caught_by=(
            "tests/test_guards.py::test_the_standing_sweeps_read_every_workspace_source_tree",
        ),
    ),
    Replant(
        name="R157-a-missing-container-is-a-divergence",
        behaviour=(
            "the level-2 runner records a missing Gmail container as a divergence; an empty "
            "Comparison reads as equivalent, so M1's own evidence reported success for a "
            "query where one path answered and the other declined (R-M1-007)"
        ),
        path="orivra/src/orivra/__main__.py",
        anchor=("        comparison = Comparison(query=query, differences=(difference,))\n"),
        replacement=("        comparison = Comparison(query=query, differences=())\n"),
        caught_by=(
            "tests/test_orivra_surface.py::test_the_live_runner_calls_a_missing_container_a_divergence",
        ),
    ),
    Replant(
        name="R158-a-signature-no-argument-uses-is-refused",
        behaviour=(
            "ExpansionHandle refuses a credential nothing consumes and a map_id nothing "
            "signs; the original condition fired only on a present-and-empty map_id, so it "
            "implemented neither rule its docstring stated (R-M1-011)"
        ),
        path="orivra/src/orivra/contracts/omission.py",
        anchor=("        if self.handle is not None and named is None:\n"),
        replacement=("        if False:\n"),
        caught_by=("tests/test_orivra_contracts.py::test_a_signature_no_argument_uses_is_refused",),
    ),
    Replant(
        name="R159-the-published-schema-is-the-parsers",
        behaviour=(
            "orivra_ask publishes mailweave_search's own input schema plus sources, because "
            "ask() forwards to parse_search: a hand-written schema published four view values "
            "where the parser accepts two and additionalProperties false while seven blocks "
            "were honoured, so a strict client and this server disagreed in both directions "
            "(R-M1-010)"
        ),
        path="orivra/src/orivra/surface/tools.py",
        anchor=("    input_schema=_ask_input_schema(),\n"),
        replacement=(
            '    input_schema={"type": "object", "properties": {"query": {"type": "string"}}},\n'
        ),
        caught_by=(
            "tests/test_orivra_surface.py::test_the_published_input_schema_and_the_parser_agree",
        ),
    ),
    Replant(
        name="R160-an-unrepresentable-instant-is-an-absent-one",
        behaviour=(
            "_timestamps treats an internalDate Python cannot represent as absent; "
            "GmailNumericId accepts twenty digits and fromtimestamp raised out of the tool "
            "call, so one odd field took down the whole response as an internal error "
            "(R-M1-020)"
        ),
        path="orivra/src/orivra/gmail_adapter.py",
        anchor=("    except (ValueError, OverflowError, OSError):\n"),
        replacement=("    except ValueError:\n"),
        caught_by=(
            "tests/test_orivra_adapter.py::test_an_internal_date_python_cannot_represent_is_an_absent_one",
        ),
    ),
    Replant(
        name="R161-a-source-that-was-not-asked-says-so",
        behaviour=(
            "per_source states asked as a field: a connected source the call did not ask for "
            "was reported ready with hits 0, distinguished from searched-and-found-nothing "
            "only by prose (R-M1-018)"
        ),
        path="orivra/src/orivra/surface/service.py",
        anchor=('                    "asked": False,\n'),
        replacement=('                    "asked": True,\n'),
        caught_by=(
            "tests/test_orivra_surface.py::test_a_source_that_was_not_asked_says_so_in_a_field_not_in_prose",
        ),
    ),
    Replant(
        name="R162-partial-source-failure-has-its-own-cause",
        behaviour=(
            "a source that answered incompletely is not reported as freshness_unverifiable, "
            "which sends the caller to re-verify something that was never fetched (R-M1-009)"
        ),
        path="orivra/src/orivra/gmail_adapter.py",
        anchor=("        return OmissionCause.PARTIAL_SOURCE_FAILURE\n"),
        replacement=("        return OmissionCause.FRESHNESS_UNVERIFIABLE\n"),
        caught_by=(
            "tests/test_orivra_adapter.py::test_a_source_that_answered_incompletely_is_not_reported_as_unverifiable",
        ),
    ),
    Replant(
        name="R163-stub-depth-discloses-no-text",
        behaviour=(
            "items() at stub depth returns no content: returning a snippet and raising the "
            "declared depth discloses text no ceiling measured (R-M1-017)"
        ),
        path="orivra/src/orivra/gmail_adapter.py",
        anchor=("            if wanted is Depth.STUB:\n"),
        replacement=("            if False:\n"),
        caught_by=("tests/test_orivra_adapter.py::test_items_at_stub_depth_discloses_no_text",),
    ),
    Replant(
        name="R164-a-recipient-constraint-is-emitted-as-one",
        behaviour=(
            "translate emits to: for recipients; the operator was published as emitted and "
            "never produced, and every participant became a sender filter, so a planner was "
            "told a recipient constraint was expressible and the query asked something else "
            "(R-M1-019)"
        ),
        path="orivra/src/orivra/gmail_adapter.py",
        anchor=(
            '        parts.extend(f"{OperatorName.TO.value}:{who}" for who in facts.recipients)\n'
        ),
        replacement=("        parts.extend([])\n"),
        caught_by=(
            "tests/test_orivra_adapter.py::test_translate_emits_a_recipient_constraint_as_a_recipient_constraint",
        ),
    ),
    # -- The M1 closure pass: the owner's R-M1-016 decision, and two plan corrections -------
    Replant(
        name="R165-a-refused-reference-refuses-the-whole-edge",
        behaviour=(
            "release asks two questions, not one: every requirement authorised AND every "
            "reference currently reachable. A grant can be unchanged while a file is unshared "
            "or a channel is left, and an edge released on authorisation alone survives every "
            "one of those (owner decision on R-M1-016)"
        ),
        path="orivra/src/orivra/contracts/permission.py",
        anchor=("    for reference in references:\n        if not probe.can_access(reference):\n"),
        replacement=("    for reference in []:\n        if not probe.can_access(reference):\n"),
        caught_by=(
            "tests/test_orivra_contracts.py::test_losing_access_to_one_endpoint_refuses_the_whole_edge",
        ),
    ),
    Replant(
        name="R166-an-empty-conjunction-is-not-vacuously-true",
        behaviour=(
            "a conjunction over no requirements would release an edge to everyone; that is "
            "the one arithmetic this gate must not inherit (owner decision on R-M1-016)"
        ),
        path="orivra/src/orivra/contracts/permission.py",
        anchor=("    if not requirements:\n"),
        replacement=("    if False:\n"),
        caught_by=(
            "tests/test_orivra_contracts.py::test_a_conjunction_over_an_empty_set_is_refused_rather_than_vacuously_true",
        ),
    ),
    Replant(
        name="R167-a-permission-refusal-reveals-nothing",
        behaviour=(
            "the record standing in for a withheld edge is presence-free: connector and cause "
            "only. Naming the requirement names the source, naming the reference names the "
            "document, and naming the relation is the disclosure the edge itself would have "
            "made (owner decision on R-M1-016)"
        ),
        path="orivra/src/orivra/contracts/omission.py",
        anchor=("        presence_free=True,\n    )\n\n\n__all__ = [\n"),
        replacement=(
            "        presence_free=False,\n"
            '        what="gmail/withheld-edge",\n'
            "        count=1,\n"
            "    )\n"
            "\n"
            "\n"
            "__all__ = [\n"
        ),
        caught_by=(
            "tests/test_orivra_contracts.py::test_a_refused_edge_produces_a_record_that_reveals_nothing_about_it",
        ),
    ),
    Replant(
        name="R168-paired-affordances-are-executed",
        behaviour=(
            "the live level-2 runner executes each paired recovery affordance and compares "
            "the evidence they recover; recording the tool names each side offered is the "
            "weaker check the plan does not ask for, in the one dimension level 2 cannot "
            "compare as bytes"
        ),
        path="orivra/src/orivra/__main__.py",
        anchor=("    paired = compare_affordances(container, direct, execute=run)\n"),
        replacement=("    paired = ()\n"),
        caught_by=(
            "tests/test_orivra_equivalence.py::test_an_unresolved_pair_makes_the_whole_query_diverge",
        ),
    ),
    Replant(
        name="R169-an-offer-this-run-may-not-execute-is-not-executed",
        behaviour=(
            "only the four read-only mailweave_* tools are run by a live equivalence pass; an "
            "offer naming anything else is reported invalid rather than executed against the "
            "real mailbox"
        ),
        path="orivra/src/orivra/equivalence.py",
        anchor=("        if not ours.executable or not theirs.executable:\n"),
        replacement=("        if False:\n"),
        caught_by=(
            "tests/test_orivra_equivalence.py::test_an_offer_naming_a_tool_this_run_may_not_execute_is_invalid_not_run",
        ),
    ),
    Replant(
        name="R170-an-unpaired-offer-is-a-divergence",
        behaviour=(
            "an affordance only one side offers is a divergence: two responses that recovered "
            "the same evidence by routes only one of them offers have not answered the same "
            "question in the same way, and the retry contract is part of the answer"
        ),
        path="orivra/src/orivra/equivalence.py",
        anchor=("        if ours is None or theirs is None:\n"),
        replacement=("        if ours is None and theirs is None:\n"),
        caught_by=(
            "tests/test_orivra_equivalence.py::test_an_offer_only_one_side_makes_is_a_divergence",
        ),
    ),
    Replant(
        name="R171-the-affordance-comparison-is-bounded",
        behaviour=(
            "a live equivalence pass runs at most MAX_PAIRED_AFFORDANCES pairs per query and "
            "follows nothing an executed call itself offers; an unbounded walk is a quota "
            "bill that grows with how partial the answer was, which is exactly backwards"
        ),
        path="orivra/src/orivra/equivalence.py",
        anchor=("    reachable, beyond = pairs[:limit], pairs[limit:]\n"),
        replacement=("    reachable, beyond = pairs, []\n"),
        caught_by=("tests/test_orivra_equivalence.py::test_the_comparison_is_bounded",),
    ),
    # -- The M1 acceptance correction: the affordance bound fails closed --------------------
    Replant(
        name="R172-the-affordance-bound-fails-closed",
        behaviour=(
            "a response offering more affordance pairs than the bound is not declared "
            "equivalent on the ones that fit: what could not be executed is counted, named "
            "and returned as an unresolved divergence. Truncating silently let thirteen "
            "observed pairs pass as twelve, with the thirteenth never checked"
        ),
        path="orivra/src/orivra/equivalence.py",
        anchor=("    if beyond:\n"),
        replacement=("    if False:\n"),
        caught_by=(
            "tests/test_orivra_equivalence.py::test_thirteen_pairs_are_not_declared_equivalent_on_twelve",
        ),
    ),
    Replant(
        name="R173-completeness-is-a-term-of-agreement",
        behaviour=(
            "AffordanceReport.agreed is a conjunction - every executed pair agreed AND "
            "nothing was left unexecuted. Dropping the completeness term is the silence that "
            "let a bound breach read as agreement"
        ),
        path="orivra/src/orivra/equivalence.py",
        anchor=("        return self.complete and not self.unresolved\n"),
        replacement=("        return not self.unresolved\n"),
        caught_by=(
            "tests/test_orivra_equivalence.py::"
            "test_a_report_with_unexecuted_pairs_never_reads_as_agreement",
        ),
    ),
    Replant(
        name="R174-a-bound-breach-diverges-the-query",
        behaviour=(
            "the live runner's verdict moves with the bound: a query whose affordance pairs "
            "were not all executed is reported as diverged rather than equivalent, or "
            "counting the skipped pairs is bookkeeping nobody reads"
        ),
        path="orivra/src/orivra/__main__.py",
        anchor=('        "equivalent": comparison.equivalent and paired.agreed,\n'),
        replacement=('        "equivalent": comparison.equivalent,\n'),
        caught_by=(
            "tests/test_orivra_equivalence.py::test_a_bound_breach_makes_the_whole_query_diverge",
        ),
    ),
    # --- PF-2's under-exercise correction (2026-09-11) ---------------------------------
    Replant(
        name="R175-a-question-the-sample-could-not-answer-is-inconclusive",
        behaviour=(
            "PF-2 reports reply-header survival as INCONCLUSIVE when no message in the "
            "sample carried In-Reply-To or References in the full arm, or a vacuous rule "
            "reads as a passing one - which is what the first live run did"
        ),
        path="harness/src/mailweave_harness/preflight/probes/headers.py",
        anchor=(
            "    if reply_dropped:\n"
            "        reply_verdict = Verdict.FAIL\n"
            "    elif not reply_bearing:\n"
            "        reply_verdict = Verdict.INCONCLUSIVE\n"
            "    else:\n"
            "        reply_verdict = Verdict.PASS\n"
        ),
        replacement=(
            "    if reply_dropped:\n"
            "        reply_verdict = Verdict.FAIL\n"
            "    else:\n"
            "        reply_verdict = Verdict.PASS\n"
        ),
        caught_by=(
            "tests/test_preflight_probes.py::"
            "test_a_one_message_thread_with_no_reply_headers_cannot_produce_a_reply_header_pass",
        ),
    ),
    Replant(
        name="R176-the-snippet-question-has-the-same-floor",
        behaviour=(
            "the exercise floor covers both of PF-2's questions, or the identical defect "
            "survives one branch over under a different name"
        ),
        path="harness/src/mailweave_harness/preflight/probes/headers.py",
        anchor=(
            "    if snippet_lost or date_lost:\n"
            "        snippet_verdict = Verdict.FAIL\n"
            "    elif not snippet_bearing:\n"
            "        snippet_verdict = Verdict.INCONCLUSIVE\n"
            "    else:\n"
            "        snippet_verdict = Verdict.PASS\n"
        ),
        replacement=(
            "    if snippet_lost or date_lost:\n"
            "        snippet_verdict = Verdict.FAIL\n"
            "    else:\n"
            "        snippet_verdict = Verdict.PASS\n"
        ),
        caught_by=(
            "tests/test_preflight_probes.py::"
            "test_the_snippet_question_has_the_same_floor_one_branch_over",
        ),
    ),
    Replant(
        name="R177-the-selector-prefers-a-thread-that-can-answer",
        behaviour=(
            "PF-2's thread selection orders candidates by message count before thread id, "
            "or it takes the lexicographically smallest id and draws a one-message thread "
            "exactly as the first live run did"
        ),
        path="harness/src/mailweave_harness/preflight/measure.py",
        anchor=(
            "    candidates = sorted(sizes, key=lambda thread_id: (-sizes[thread_id], thread_id))\n"
        ),
        replacement=("    candidates = sorted(sizes)\n"),
        caught_by=(
            "tests/test_preflight_runner_end_to_end.py::"
            "test_the_selector_takes_the_largest_thread_not_the_smallest_id",
        ),
    ),
    Replant(
        name="R178-the-two-arms-are-read-at-one-instant",
        behaviour=(
            "the selector's full arm is reused as the probe's full arm, or the thread is "
            "fetched twice and a message delivered between the two calls reads as a header "
            "the metadata arm dropped"
        ),
        path="harness/src/mailweave_harness/preflight/measure.py",
        anchor=(
            "    if full_arm is None:\n"
            "        full_arm = client.get_thread(\n"
            "            DispositionLedger(), thread_id=thread_id, rung=RungId.L4, "
            'message_format="full"\n'
            "        ).thread\n"
        ),
        replacement=(
            "    full_arm = client.get_thread(\n"
            "        DispositionLedger(), thread_id=thread_id, rung=RungId.L4, "
            'message_format="full"\n'
            "    ).thread\n"
        ),
        caught_by=(
            "tests/test_preflight_runner_end_to_end.py::"
            "test_the_selectors_full_arm_is_reused_rather_than_refetched",
        ),
    ),
    Replant(
        name="R179-a-record-without-a-per-question-verdict-answers-nothing",
        behaviour=(
            "the server-side reader treats a PF-2 record carrying no per-question verdict "
            "as having answered neither question, or the preserved run-1 record silently "
            "reacquires the conclusion it was never entitled to"
        ),
        path="server/src/mailweave/semantic/resolve.py",
        anchor=(
            "    verdict = record.findings.get(verdict_key)\n"
            "    if type(verdict) is not str:\n"
            "        return False\n"
        ),
        replacement=(
            "    verdict = record.findings.get(verdict_key)\n"
            "    if type(verdict) is not str:\n"
            "        return True\n"
        ),
        caught_by=(
            "tests/test_semantic_profile.py::"
            "test_the_preserved_run_one_record_decides_neither_question",
        ),
    ),
    # --- the historyId watermark (AD D.9, ADV-101) ------------------------------------
    Replant(
        name="R180-the-watermark-holds-exactly-four-fields",
        behaviour=(
            "the watermark writer refuses a payload whose key set is not exactly the four "
            "declared fields, or a future field carries mail text into a persisted file "
            "and only a docstring ever asked it not to"
        ),
        path="server/src/mailweave/freshness/watermark.py",
        anchor=("    keys = set(payload)\n    if keys != set(Watermark.FIELDS):\n"),
        replacement=("    keys = set(payload)\n    if not set(Watermark.FIELDS) <= keys:\n"),
        caught_by=(
            "tests/test_freshness_watermark.py::test_an_extra_key_is_refused_rather_than_written",
        ),
    ),
    Replant(
        name="R181-an-over-permissive-watermark-is-refused-not-repaired",
        behaviour=(
            "reading the watermark refuses a file that is not 0600, or a file that was "
            "readable by others is silently repaired and nobody ever learns it may already "
            "have been read"
        ),
        path="server/src/mailweave/freshness/watermark.py",
        anchor=("        self._check_mode(self.path, TOKEN_FILE_MODE)\n"),
        replacement=("        pass\n"),
        caught_by=(
            "tests/test_freshness_watermark.py::"
            "test_an_over_permissive_file_is_refused_rather_than_repaired",
        ),
    ),
    Replant(
        name="R182-a-watermark-belongs-to-one-mailbox",
        behaviour=(
            "a stored watermark is only a floor for the account it was observed on, or a "
            "history walk runs from an unrelated sequence and reports someone else's "
            "arrivals as this mailbox's"
        ),
        path="server/src/mailweave/freshness/watermark.py",
        anchor=(
            "        return stored if stored.account_hash == account_hash(address) else None\n"
        ),
        replacement=("        return stored\n"),
        caught_by=(
            "tests/test_freshness_watermark.py::"
            "test_another_mailboxs_watermark_is_not_a_floor_for_this_one",
        ),
    ),
    Replant(
        name="R183-purge-means-the-watermark-too",
        behaviour=(
            "`mailweave purge` deletes the watermark as well as the credential, or the user "
            "is left a persisted file they were told is removable"
        ),
        path="server/src/mailweave/cli.py",
        anchor=("    removed_watermark = watermark.purge()\n"),
        replacement=("    removed_watermark = False\n"),
        caught_by=("tests/test_cli.py::test_purge_removes_the_watermark_too",),
    ),
    # --- model provisioning (AD D.8), corrected 2026-09-11 ----------------------------
    Replant(
        name="R184-a-set-takes-one-weight-format",
        behaviour=(
            "an artifact set selects by explicit include rather than taking the repo, or "
            "bge-reranker-base pulls safetensors, a pytorch .bin and an ONNX graph - about "
            "3.36 GB for roughly 1.1 GB any runtime loads. Aimed at the include list "
            "because the excludes are a second line that never fires with the sets as "
            "shipped, which this replant is what established. Both halves are planted "
            "together because either alone keeps the duplicates out: the include list does "
            "not name them and the exclude list removes them, so a single-line plant proves "
            "nothing about a set that has both"
        ),
        path="server/src/mailweave/models/catalog.py",
        anchor=(
            "                if any(fnmatch(name, pattern) "
            "for pattern in self.required + self.optional)\n"
            "                and not any(fnmatch(name, pattern) for pattern in self.exclude)\n"
        ),
        replacement=("                if True\n"),
        caught_by=(
            "tests/test_model_provisioning.py::"
            "test_a_set_takes_one_weight_format_and_leaves_the_duplicates",
        ),
    ),
    Replant(
        name="R185-a-requirement-that-matches-nothing-is-not-satisfied",
        behaviour=(
            "a required pattern matching no file fails the pin, or a missing tokenizer "
            "surfaces weeks later as a loader failure and gets read as a model result"
        ),
        path="server/src/mailweave/models/catalog.py",
        anchor=("        if unmatched:\n"),
        replacement=("        if False:\n"),
        caught_by=(
            "tests/test_model_provisioning.py::"
            "test_a_required_pattern_that_matches_nothing_fails_the_pin",
        ),
    ),
    Replant(
        name="R186-the-size-bound-stops-a-transfer-mid-file",
        behaviour=(
            "the download bound is enforced inside the chunk loop, or a 2 GB file blows a "
            "1.5 GB bound only once all 2 GB are on disk, which is a report not a limit"
        ),
        path="server/src/mailweave/models/provision.py",
        anchor=("                    if size > budget:\n"),
        replacement=("                    if False:\n"),
        caught_by=("tests/test_model_provisioning.py::test_the_bound_stops_a_transfer_mid_file",),
    ),
    Replant(
        name="R187-the-runtime-allowlist-takes-no-suffixes",
        behaviour=(
            "check_url's suffix arm is opt-in and empty by default, or the regional content "
            "host the setup path needs becomes reachable from the server process too"
        ),
        path="server/src/mailweave/net/egress.py",
        anchor=("    suffixes: Iterable[str] = (),\n    **kwargs: object,\n) -> httpx.Client:\n"),
        replacement=(
            "    suffixes: Iterable[str] = MODEL_CDN_SUFFIXES,\n"
            "    **kwargs: object,\n) -> httpx.Client:\n"
        ),
        caught_by=(
            "tests/test_model_provisioning.py::test_the_runtime_client_takes_no_suffixes_at_all",
        ),
    ),
    Replant(
        name="R188-two-sets-of-one-repo-do-not-share-a-directory",
        behaviour=(
            "the weights directory is keyed by lock key and revision, or the Python and "
            "ONNX sets of one repo land together and neither lock describes what is on disk"
        ),
        path="server/src/mailweave/models/paths.py",
        anchor=('    return Path(root).expanduser() / lock_key.replace("/", "__") / revision\n'),
        replacement=("    return Path(root).expanduser() / revision\n"),
        caught_by=(
            "tests/test_model_provisioning.py::"
            "test_the_two_sets_of_one_repo_do_not_share_a_directory",
        ),
    ),
    # --- PF-4 and the model lifecycle (2026-09-11) ------------------------------------
    Replant(
        name="R189-the-backend-is-built-once-per-process",
        behaviour=(
            "the registry memoises the built backend, or every query pays the cold load - "
            "36,543 ms on the owner's machine against a 6,000 ms MAX_SEMANTIC_MS, which "
            "would have surfaced as a timeout on every query rather than as an "
            "architecture mistake"
        ),
        path="server/src/mailweave/semantic/interface.py",
        anchor=(
            "            cached = self._built.get(chosen)\n"
            "            if cached is not None:\n"
            "                return cached\n"
        ),
        replacement=("            cached = None\n"),
        caught_by=("tests/test_modelbench_pf4.py::test_two_acquires_build_one_backend",),
    ),
    Replant(
        name="R190-a-decline-is-remembered",
        behaviour=(
            "a failing load is remembered for the process, or a machine with no weights "
            "retries an expensive failure on every single query"
        ),
        path="server/src/mailweave/semantic/interface.py",
        anchor=(
            "            remembered = self._declined.get(chosen)\n"
            "            if remembered is not None:\n"
            "                raise remembered\n"
        ),
        replacement=("            remembered = None\n"),
        caught_by=(
            "tests/test_modelbench_pf4.py::"
            "test_a_decline_is_remembered_rather_than_retried_every_query",
        ),
    ),
    Replant(
        name="R191-pf4-checks-the-reuse-it-relies-on",
        behaviour=(
            "PF-4 fails when the second acquire is not materially cheaper than the first, "
            "or it separates cold from warm on an assumption it never checked and reports "
            "a per-query figure the product cannot achieve"
        ),
        path="harness/src/mailweave_harness/modelbench/measure.py",
        anchor=("    if not reuse_holds:\n"),
        replacement=("    if False:\n"),
        caught_by=(
            "tests/test_modelbench_pf4.py::"
            "test_reuse_failing_is_reported_as_an_architecture_defect_not_a_tuning_result",
        ),
    ),
    Replant(
        name="R192-an-overrun-lowers-the-pool-not-the-bar",
        behaviour=(
            "a per-query overrun re-derives max_pool_messages downward, or MAX_SEMANTIC_MS "
            "gets raised to whatever was measured and the bound becomes a description"
        ),
        path="harness/src/mailweave_harness/modelbench/measure.py",
        anchor=(
            "        size for size, ms in sorted(arm.embed_ms_by_pool_size.items()) "
            "if ms <= remaining\n"
        ),
        replacement=("        size for size, ms in sorted(arm.embed_ms_by_pool_size.items())\n"),
        caught_by=(
            "tests/test_modelbench_pf4.py::"
            "test_an_overrun_re_derives_the_pool_downward_rather_than_raising_the_budget",
        ),
    ),
    # --- PF-4's benchmark qualification (2026-09-11) ----------------------------------
    Replant(
        name="R193-the-device-is-named-not-defaulted",
        behaviour=(
            "the loader passes an explicit device, or SentenceTransformer picks the best "
            "accelerator and a CPU-only plan is measured on MPS with nothing saying so"
        ),
        path="server/src/mailweave/semantic/local.py",
        anchor=("        return SentenceTransformer(path, device=device, local_files_only=True)\n"),
        replacement=("        return SentenceTransformer(path, local_files_only=True)\n"),
        caught_by=(
            "tests/test_modelbench_pf4.py::"
            "test_the_loader_names_a_device_rather_than_letting_the_library_choose",
        ),
    ),
    Replant(
        name="R194-a-falling-curve-is-not-a-capacity-curve",
        behaviour=(
            "PF-4 returns INCONCLUSIVE when a median curve falls as the work grows, or it "
            "derives constants from run 1's 288/229/137 ms shape, which is a missing "
            "warm-up rather than a model that speeds up under load"
        ),
        path="harness/src/mailweave_harness/modelbench/measure.py",
        anchor=("    elif not curves_readable:\n"),
        replacement=("    elif False:\n"),
        caught_by=(
            "tests/test_modelbench_pf4.py::test_a_falling_curve_is_inconclusive_rather_than_a_pass",
        ),
    ),
    Replant(
        name="R195-a-record-without-a-device-sets-no-constant",
        behaviour=(
            "the server reads a PF-4 record only when it says what it measured on, or run "
            "1's unqualified numbers silently become the operating bounds. All three "
            "guards are planted together because each rejects run 1 on its own"
        ),
        path="server/src/mailweave/semantic/resolve.py",
        anchor=(
            '    if type(findings.get("device")) is not str or not findings.get("device"):\n'
            "        return profile\n"
            '    if _positive_int(findings, "repeats_per_size") is None:\n'
            "        return profile\n"
            '    if findings.get("rerank_curve_is_non_decreasing") is not True:\n'
            "        return profile\n"
        ),
        replacement=("    if False:\n        return profile\n"),
        caught_by=(
            "tests/test_modelbench_pf4.py::test_a_pf4_record_without_a_device_sets_no_constant",
        ),
    ),
    Replant(
        name="R196-the-pool-may-create-sources",
        behaviour=(
            "a candidate the semantic pool listed and the shortlist did not select is not "
            "disclosed as a source. Without the split, a query with no lexical answer "
            "returns every thread in its own ninety-day recency window as a full source - "
            "the pool creating sources, which AD D.5 forbids in those words"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor=(
            "        if plan.rung is RungId.L5 and plan.thread_id not in selected:\n"
            "            drop.append(plan)\n"
            "        else:\n"
            "            keep.append(plan)\n"
        ),
        replacement="        keep.append(plan)\n",
        caught_by=(
            "tests/test_semantic_rung.py::test_the_pool_declares_its_scope_and_size_and_creates_no_rows",
        ),
    ),
    Replant(
        name="R197-the-backend-is-rebuilt-per-query",
        behaviour=(
            "the server process loads its models once. The registry memoises for the "
            "process lifetime and the service holds one registry across calls; a service "
            "that built its own would pay PF-4's 5,410 ms cold load on every query, which "
            "is a semantic rung that can never finish inside its own 6,000 ms cap"
        ),
        path="server/src/mailweave/surface/service.py",
        anchor=("            registry=self.registry,\n            accountant=accountant,\n"),
        replacement=(
            "            registry=BackendRegistry(),\n            accountant=accountant,\n"
        ),
        caught_by=(
            "tests/test_semantic_rung.py::test_the_server_process_reuses_one_backend_across_queries",
        ),
    ),
    Replant(
        name="R198-a-prohibited-rung-can-be-forced",
        behaviour=(
            "SEM-04 and RANK-01 forbid a semantic rung after an identity resolution, and a "
            "prohibition a caller can lift with force_rungs is not one. The gate is "
            "evaluated prohibition-first for exactly this reason"
        ),
        path="server/src/mailweave/retrieval/semantic.py",
        anchor=("        if gate.prohibited:\n"),
        replacement="        if gate.prohibited and False:\n",
        caught_by=(
            "tests/test_semantic_rung.py::test_an_identity_resolution_forbids_the_semantic_rung_and_force_rungs_cannot_lift_it",
        ),
    ),
    Replant(
        name="R199-the-shortlist-is-a-threshold",
        behaviour=(
            "the shortlist is top-k by cosine with k a pre-registered constant. A score "
            "threshold would hand the implementer the dial that sets |H| (SS H-5, ADV-109)"
        ),
        path="server/src/mailweave/semantic/shortlist.py",
        anchor=(
            "    return ShortlistResult(\n"
            "        rule=SHORTLIST_RULE, k=k, selected=tuple(ranked[:k]), "
            "scored=tuple(ranked)\n"
            "    )\n"
        ),
        replacement=(
            "    return ShortlistResult(\n"
            "        rule=SHORTLIST_RULE,\n"
            "        k=k,\n"
            "        selected=tuple(row for row in ranked if row.cosine >= 0.4),\n"
            "        scored=tuple(ranked),\n"
            "    )\n"
        ),
        caught_by=(
            "tests/test_semantic_rung.py::test_the_shortlist_is_k_by_rule_and_k_is_max_rerank_pairs",
        ),
    ),
    Replant(
        name="R200-the-pool-thread-is-fetched-twice",
        behaviour=(
            "a thread the pool read and the response discloses is fetched once. Two "
            "threads.get calls on one thread cost 40 u twice (I-3) and stamp two different "
            "fetched_at values, the second of which the source would state while the ledger "
            "sealed the first - a response that can restate a freshness stamp (R-08)"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor=(
            "    recorded = (\n"
            "        client.get_thread(ledger, thread_id=plan.thread_id, rung=plan.rung)\n"
            "        if observed is None\n"
            "        else observed\n"
            "    )\n"
        ),
        replacement=(
            "    recorded = client.get_thread(ledger, thread_id=plan.thread_id, rung=plan.rung)\n"
        ),
        caught_by=(
            "tests/test_semantic_rung.py::test_the_pool_declares_its_scope_and_size_and_creates_no_rows",
        ),
    ),
    Replant(
        name="R201-a-prohibited-rerank-can-fire-on-ambiguity",
        behaviour=(
            "RANK-01's three prohibitions are evaluated before D.7's ambiguity signals, so "
            "an identity lookup that happens to be ambiguous stays prohibited. Evaluated "
            "the other way round, a cross-encoder would re-order an exact answer"
        ),
        path="server/src/mailweave/ranking/gate.py",
        anchor=(
            "    if _is_an_identifier_route(parsed):\n"
            "        route = RerankProhibition.IDENTIFIER_ROUTE\n"
            "        return RerankGate(fires=False, prohibited_by=route)\n"
        ),
        replacement="    if False:\n        pass\n",
        caught_by=(
            "tests/test_ranking_l6.py::test_the_prohibitions_are_evaluated_before_the_signals",
        ),
    ),
    Replant(
        name="R202-a-rerank-orders-a-comparison-it-did-not-score",
        behaviour=(
            "a rerank score may order a comparison only where it exists for every candidate "
            "in it (ADV-110). Mixing a rerank score with a mechanical one inside one sort is "
            "the fabricated comparability RANK-03 exists to prevent"
        ),
        path="server/src/mailweave/ranking/rerank.py",
        anchor=(
            "        scored = self.by_id\n"
            "        return all(candidate in scored for candidate in candidates)\n"
        ),
        replacement=(
            "        scored = self.by_id\n"
            "        return any(candidate in scored for candidate in candidates)\n"
        ),
        caught_by=(
            "tests/test_ranking_l6.py::test_a_rerank_orders_only_a_comparison_it_scored_every_member_of",
        ),
    ),
    Replant(
        name="R203-a-q-selected-row-carries-a-score",
        behaviour=(
            "a row Gmail's q selected carries no numeric score (D.7). A similarity number "
            "beside an exact match invites a reader to compare the two on one scale"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor="    if reason.kind in _Q_SELECTED_REASONS:\n        return None\n",
        replacement="    if False:\n        return None\n",
        caught_by=(
            "tests/test_semantic_rung.py::test_a_row_gmail_q_selected_carries_no_numeric_score",
        ),
    ),
    Replant(
        name="R204-the-mechanical-ranking-is-not-total",
        behaviour=(
            "two candidates on which the same components fire are indistinguishable to this "
            "ranking, and an order that depended on input order would make the response's "
            "ordering a fact about dictionary iteration (C-04b)"
        ),
        path="server/src/mailweave/ranking/mechanical.py",
        anchor="    return tuple(sorted(ranked, key=lambda row: (-row.value, row.key)))\n",
        replacement="    return tuple(sorted(ranked, key=lambda row: -row.value))\n",
        caught_by=(
            "tests/test_ranking_l6.py::test_the_mechanical_ranking_is_total_and_reproducible",
        ),
    ),
    Replant(
        name="R205-a-messages-addresses-are-its-display-names",
        behaviour=(
            "addresses_in_header returns (display name, address) and every caller reads it "
            "in that order. Unpacked backwards, the E4 fill's participant_match compared "
            "the query's addresses against display names - and against the empty string for "
            "every bare address - so the most query-driven component of the query-aware fill "
            "could fire only by coincidence. This is the defect as it shipped"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor="        for _display, address in addresses_in_header(payload.header(name)):\n",
        replacement="        for address, _display in addresses_in_header(payload.header(name)):\n",
        caught_by=(
            "tests/test_semantic_rung.py::test_a_messages_own_addresses_are_addresses_and_not_display_names",
        ),
    ),
    Replant(
        name="R206-an-lr-row-claims-a-gmail-q-match",
        behaviour=(
            "a message LR surfaced is role: context with D.9's verbatim reason, never a q "
            "match. Attributing it to the user's query would be this server asserting a "
            "Gmail match it never observed (R-03, T-RC3)"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor="        elif message_id in surfaced:\n",
        replacement="        elif False:\n",
        caught_by=(
            "tests/test_freshness_lr.py::test_a_message_that_arrived_after_the_walk_is_surfaced_as_context",
        ),
    ),
    Replant(
        name="R207-a-contradicted-arrival-is-dropped",
        behaviour=(
            "history.list admits every messagesAdded id into H under clause H-hist, so a "
            "candidate the closed local re-check contradicted is retrieved, not disclosed, "
            "and owed an account. Dropping it would make the certificate refuse the response"
        ),
        path="server/src/mailweave/freshness/recency.py",
        anchor=(
            "            if not verdict.passed:\n"
            "                contradicted.append(message_id)\n"
            "                continue\n"
        ),
        replacement="            if False:\n                continue\n",
        caught_by=(
            "tests/test_freshness_lr.py::test_a_late_arrival_that_contradicts_a_stated_constraint_is_withheld",
        ),
    ),
    Replant(
        name="R208-the-watermark-moves-before-the-walk",
        behaviour=(
            "the watermark advances after the response is built, never before the walk. "
            "Advanced first it would sit above changes this query never looked at, and the "
            "next query would start from a place nobody reconciled - a gap that is invisible "
            "because each individual response looks whole"
        ),
        path="server/src/mailweave/surface/service.py",
        anchor="        self._advance_watermark(client, recency)\n",
        replacement="        pass\n",
        caught_by=(
            "tests/test_freshness_lr.py::test_the_first_query_has_no_watermark_and_writes_one_for_the_next",
        ),
    ),
    Replant(
        name="R209-a-redacted-value-renders-itself",
        behaviour=(
            "redaction is a type: every formatting path renders a placeholder, which is what "
            "makes SEC-06's error-path requirement achievable rather than aspirational. A "
            "filter runs where somebody remembered to call it, and an exception's repr is "
            "never that place"
        ),
        path="server/src/mailweave/trace/redaction.py",
        anchor="    def __repr__(self) -> str:\n        return self.placeholder\n",
        replacement="    def __repr__(self) -> str:\n        return self._value\n",
        caught_by=("tests/test_trace_d10.py::test_every_formatting_path_renders_the_placeholder",),
    ),
    Replant(
        name="R210-a-trace-carries-the-query-text",
        behaviour=(
            "SN 4.3: no raw query strings. Query text is stored as features plus a salted "
            "hash, and a trace that carried the string would hold the one piece of "
            "mail-adjacent text the user typed themselves"
        ),
        path="server/src/mailweave/trace/redaction.py",
        anchor='        "hash": Redacted(query).digest,\n',
        replacement='        "hash": query,\n',
        caught_by=(
            "tests/test_trace_d10.py::test_query_features_describe_the_shape_and_never_the_text",
        ),
    ),
    Replant(
        name="R211-pool-ids-reach-the-wire",
        behaviour=(
            "pool_ids[] lives in the trace and nowhere else (AD D.5, SS H-5(b)). It is what "
            "lets EV-01 join against a real set instead of the server's account of one, and "
            "300 stub rows on the wire is what putting it in the response would cost"
        ),
        path="server/src/mailweave/trace/emit.py",
        anchor=(
            "        pool_ids=() if build is None "
            "else tuple(row.message_id for row in build.rows),\n"
        ),
        replacement="        pool_ids=(),\n",
        caught_by=(
            "tests/test_trace_d10.py::test_pool_ids_live_in_the_trace_and_never_in_the_response",
        ),
    ),
    Replant(
        name="R212-a-trace-failure-fails-the-call",
        behaviour=(
            "a trace is a forensic record of a response that is already correct. Failing the "
            "call over one would make the instrumentation less safe than no instrumentation"
        ),
        path="server/src/mailweave/surface/service.py",
        anchor="        except (OSError, ValueError):\n            return\n",
        replacement="        except (OSError, ValueError):\n            raise\n",
        caught_by=(
            "tests/test_trace_d10.py::test_a_trace_that_cannot_be_written_does_not_fail_the_call",
        ),
    ),
    Replant(
        name="R213-the-offline-flags-are-set-per-call-site",
        behaviour=(
            "HF_HUB_OFFLINE is read at import time, so setting it inside the three functions "
            "that load a model makes the guarantee a property of those call sites rather than "
            "of the process. Anything that imported a hub-aware library first would have bound "
            "the flag as unset"
        ),
        path="server/src/mailweave/semantic/local.py",
        anchor="force_offline()\n\n\n#: The device the server loads on.",
        replacement="\n#: The device the server loads on.",
        caught_by=(
            "tests/test_offline_enforcement.py::test_the_offline_flags_are_set_before_any_hub_aware_library_is_imported",
        ),
    ),
    Replant(
        name="R214-a-declining-backend-is-retried-every-query",
        behaviour=(
            "a machine with no weights is a supported configuration, and retrying a failing "
            "load on every query spends the failure over and over. The registry remembers a "
            "decline for the process lifetime, and states the consequence: installing models "
            "into a running server takes effect at the next session"
        ),
        path="server/src/mailweave/semantic/interface.py",
        anchor=(
            "            remembered = self._declined.get(chosen)\n"
            "            if remembered is not None:\n"
            "                raise remembered\n"
        ),
        replacement="            pass\n",
        caught_by=(
            "tests/test_offline_enforcement.py::test_the_registry_remembers_a_decline_rather_than_retrying_every_query",
        ),
    ),
    Replant(
        name="R215-the-participant-component-reads-display-names",
        behaviour=(
            "A.9(3) ranks participant_match first because it is the most query-driven signal "
            "available. With the header pair unpacked backwards, two hits that differ only in "
            "who they are from tie at zero and thread position decides which body survives - "
            "the oldest-K policy EV-02's degenerate-strategy guard names, wearing the "
            "published policy's name"
        ),
        path="server/src/mailweave/semantic/pool.py",
        anchor=(
            "            # `(display name, address)` - see `_addresses_of`, "
            "which had this backwards.\n"
            "            for _display, address in addresses_in_header(payload.header(name)):\n"
        ),
        replacement=(
            "            for address, _display in addresses_in_header(payload.header(name)):\n"
        ),
        caught_by=(
            "tests/test_semantic_rung.py::test_a_messages_own_addresses_are_addresses_and_not_display_names",
        ),
    ),
    Replant(
        name="R216-the-freshness-p90-pools-across-depths",
        behaviour=(
            "OD-1 prohibits pooling across thread depths, because a pooled p90 passes "
            "whenever the two fast strata outnumber the slow one - which is the depth-25 "
            "case the design believes is slower. Pooling is unrepresentable here rather "
            "than merely forbidden"
        ),
        path="harness/src/mailweave_harness/freshness/analysis.py",
        anchor="    foreign = len(observations) - len(mine)\n    if foreign:\n",
        replacement="    foreign = 0\n    if foreign:\n",
        caught_by=(
            "tests/test_pf10_and_pf4b.py::"
            "test_pooling_across_strata_is_unrepresentable_rather_than_forbidden",
        ),
    ),
    Replant(
        name="R217-a-censored-probe-is-averaged-away",
        behaviour=(
            "a probe that never surfaced is MF1 itself, and dropping it from the sample "
            "improves the percentile by removing the worst case"
        ),
        path="harness/src/mailweave_harness/freshness/analysis.py",
        anchor="    if any(row.censored for row in mine):\n",
        replacement="    if False:\n",
        caught_by=(
            "tests/test_pf10_and_pf4b.py::test_a_probe_that_never_surfaced_cannot_be_averaged_away",
        ),
    ),
    Replant(
        name="R218-a-false-negative-is-excused-by-a-passing-p90",
        behaviour=(
            "OD-1 states a confirmed real-mail false negative as a defect regardless of "
            "percentile, a second and independent trigger: passing p90 does not excuse it"
        ),
        path="harness/src/mailweave_harness/freshness/analysis.py",
        anchor="        return not (self.mf2_fires or self.mf4_fires or self.inconclusive)\n",
        replacement="        return not (self.mf2_fires or self.inconclusive)\n",
        caught_by=(
            "tests/test_pf10_and_pf4b.py::"
            "test_a_confirmed_false_negative_is_a_defect_regardless_of_percentile",
        ),
    ),
    Replant(
        name="R219-the-two-arms-agree-about-a-seed-rather-than-a-corpus",
        behaviour=(
            "PF-4b's first registered rule is that both arms embed the same rows. A Node arm "
            "that re-implemented the Python generator would produce similar rows and the "
            "rule would read as satisfied while being false, so the rows cross as data and "
            "the agreement is checked by digest"
        ),
        path="harness/src/mailweave_harness/modelbench/nodearm.py",
        anchor="    if digest != expected:\n",
        replacement="    if False:\n",
        caught_by=(
            "tests/test_pf10_and_pf4b.py::test_a_node_result_for_a_different_corpus_is_refused",
        ),
    ),
    Replant(
        name="R220-ordering-effect-is-read-off-the-wrong-comparison",
        behaviour=(
            "`ordering_effect` is a fact about the candidate set the rerank ordered, not "
            "about one source's rows. Read off the source, a lone scored row reported an "
            "ordering effect on a response the rerank had declined to reorder - ADV-110's "
            "claim inverted, in the field built to make it"
        ),
        path="server/src/mailweave/retrieval/ranking.py",
        anchor="            ordering_effect=self.ordering_applied,\n",
        replacement="            ordering_effect=True,\n",
        caught_by=(
            "tests/test_ranking_l6.py::"
            "test_ordering_effect_is_about_the_set_the_rerank_ordered_not_one_source",
        ),
    ),
    Replant(
        name="R221-the-tier-that-ordered-the-response-is-not-stated",
        behaviour=(
            "D.7 gives a q-selected row no numeric score, so on an all-lexical response "
            "nothing else says a cross-encoder was involved. D.5's cost block is what makes "
            "two responses with identical rows and opposite order distinguishable"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor=(
            "        ordering_method=("
            "MECHANICAL_METHOD if ranking is None else ranking.ordering_method),\n"
        ),
        replacement="        ordering_method=MECHANICAL_METHOD,\n",
        caught_by=(
            "tests/test_semantic_rung.py::"
            "test_two_responses_that_differ_only_in_which_tier_ordered_them_are_distinguishable",
        ),
    ),
    # --- WS-14, INJ-05: sender identity is split from the things it is mistaken for -------
    Replant(
        name="R222-a-reply-to-difference-is-reported-as-no-difference",
        behaviour=(
            "INJ-05: the row states whether a Reply-To names an address the From does not, so "
            "a redirect is visible without the reader re-parsing two header strings"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor="    return bool(replies - authors)\n",
        replacement="    return False\n",
        caught_by=(
            "tests/test_injection_ws14.py::"
            "test_a_reply_to_that_names_another_address_is_flagged_beside_the_from",
        ),
    ),
    Replant(
        name="R223-an-unobserved-header-may-state-a-negative-identity-claim",
        behaviour=(
            "INJ-05/OD-5: with no headers observed, reply_to_differs and authentication are "
            "withheld rather than denied - a false there is a claim about a message nobody read"
        ),
        path="server/src/mailweave/envelope/wire.py",
        anchor="        if self.reply_to_differs is not None and not self.headers_observed:\n",
        replacement="        if False:\n",
        caught_by=(
            "tests/test_injection_ws14.py::"
            "test_with_no_headers_observed_both_identity_claims_are_withheld_rather_than_denied",
        ),
    ),
    Replant(
        name="R224-an-oversize-authentication-record-is-truncated-rather-than-declared",
        behaviour=(
            "INJ-05: a record past MAX_AUTH_RECORD_CHARS is declared oversize and not "
            "disclosed; truncating rewrites a record this server did not write"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        # Re-anchored 2026-09-23: the comparison moved into `constants.auth_record_fits`, the
        # one the producer, the model and the charge now share. The plant is the same one.
        anchor="    if not auth_record_fits(raw):\n",
        replacement="    if False:\n",
        caught_by=(
            "tests/test_injection_ws14.py::"
            "test_a_record_past_the_bound_is_declared_rather_than_truncated",
        ),
    ),
    Replant(
        name="R225-the-identity-block-is-carried-but-not-charged",
        behaviour=(
            "A11: a row is charged its structure at every depth, and INJ-05's three identity "
            "fields are structure - uncharged, the ladder fits a response the host then cuts"
        ),
        path="server/src/mailweave/envelope/measure.py",
        anchor="ROW_IDENTITY_CHARS = 110\n",
        replacement="ROW_IDENTITY_CHARS = 0\n",
        caught_by=(
            "tests/test_injection_ws14.py::test_the_estimate_bounds_the_identity_block_it_added",
        ),
    ),
    Replant(
        name="R226-a-map-does-not-account-for-what-step-8-withheld-from-it",
        behaviour=(
            "R-06/PART-05 on the expansion path: a map claiming map_id accounts for every "
            "position as a row, a collapsed-run member or a withheld record"
        ),
        path="server/src/mailweave/surface/expansion.py",
        # Re-pointed after R-M2-077 and again after the navigation redesign (2026-09-14): the
        # source is built once, in `_source_of`. A paged map withholds nothing, so the test
        # that catches this is now a *scoped* read, whose reply parents are exactly the
        # records `withheld_here` names - drop them and the row's parent reference points at
        # a message the source neither carries nor withholds, which `Source` refuses.
        anchor="        withheld_here=here,\n",
        replacement="        withheld_here=(),\n",
        caught_by=(
            "tests/test_navigation_and_disclosure.py::"
            "test_a_scoped_read_names_reply_parents_it_withholds_as_records_with_their_own_call",
        ),
    ),
    Replant(
        name="R227-a-display-name-is-suppressed-instead-of-split-from-the-identity",
        behaviour=(
            "INJ-05: the display name a message presented is disclosed fenced beside the "
            "address that used it, so an impersonation is legible rather than merely harmless"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor="    return {address: tuple(names) for address, names in found.items()}\n",
        replacement="    return {}\n",
        caught_by=(
            "tests/test_thread_map_round20.py::"
            "test_a_display_name_cannot_make_someone_the_author_of_a_message",
        ),
    ),
    # --- WS-14, INJ-02/INJ-03: mail text stays inside the fence ---------------------------
    Replant(
        name="R228-a-score-quotes-the-candidate-instead-of-naming-what-was-encoded",
        behaviour=(
            "INJ-02/ADV-110: score.basis names the text that was encoded - the pool's "
            "declared text mode - rather than carrying the message's own words unfenced into "
            "a field this server writes"
        ),
        path="server/src/mailweave/ranking/rerank.py",
        anchor="            basis=row.basis,\n",
        replacement="            basis=texts[row.message_id],\n",
        caught_by=(
            "tests/test_injection_ws14.py::"
            "test_no_connector_voiced_field_carries_a_string_a_message_chose",
            "tests/test_injection_ws14.py::"
            "test_the_bait_row_names_the_rung_that_selected_it_and_the_model_that_scored_it",
        ),
    ),
    Replant(
        name="R229-a-thread-the-shortlist-passed-over-is-dropped-rather-than-withheld",
        behaviour=(
            "I-1 under INJ-03: a thread a higher-scoring message displaced from the shortlist "
            "is a withheld record naming max_rerank_pairs, with a call that returns it"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor="            WithheldCap.MAX_RERANK_PAIRS,\n",
        replacement="            WithheldCap.DISCLOSED_TOKEN_CEILING,\n",
        caught_by=(
            "tests/test_injection_ws14.py::"
            "test_a_bait_that_takes_a_shortlist_slot_leaves_a_declared_way_back",
        ),
    ),
    Replant(
        name="R230-an-excluded-arrival-is-reported-as-a-fetch-bound",
        behaviour=(
            "D.9: a recent arrival the local re-check contradicted is not a cap - nothing "
            "was bounded - so reporting it under max_recency_fetch would say the fetch bound "
            "stopped a message the fetch bound did not stop"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor="            WithheldCap.RECENCY_RECHECK_EXCLUDED,\n",
        replacement="            WithheldCap.MAX_RECENCY_FETCH,\n",
        caught_by=(
            "tests/test_freshness_lr.py::"
            "test_an_excluded_arrival_leaves_the_outcome_answered_and_names_no_cap",
            "tests/test_freshness_lr.py::"
            "test_the_mirror_says_no_cap_fired_and_still_names_the_omission",
        ),
    ),
    Replant(
        name="R231-the-listening-socket-guard-exempts-every-module",
        behaviour=(
            "SEC-07: AD D.1 puts this server on stdio, so the loopback consent receiver is "
            "the one allowlisted inbound socket and its names are refused everywhere else"
        ),
        path="tools/guards/sweeps.py",
        anchor='_LOOPBACK_RECEIVER: Final[str] = "mailweave/auth/consent.py"\n',
        replacement='_LOOPBACK_RECEIVER: Final[str] = ".py"\n',
        caught_by=(
            "tests/test_guards.py::test_a_listening_socket_in_server_code_is_caught",
            "tests/test_guards.py::test_the_receivers_names_are_refused_outside_that_one_module",
        ),
    ),
    Replant(
        name="R232-baseline-f-cannot-execute",
        behaviour=(
            "DISC-02/EP §8.8: Baseline F's fixed +/-2 fill runs at the same ceiling through "
            "the same ladder, and its rows carry the mechanism that put them there - a "
            "window offset around a hit, which is a real reason and deliberately not a "
            "query-derived one"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor="    if isinstance(result, int):\n",
        replacement="    if False:\n",
        # `test_every_arm_runs_every_case_without_failing` was a second catcher until
        # 2026-09-15: with the fill path disabled an arm's response used to decline, and since
        # A15 (the last resort collapses rather than empties; the retry is the width that fits)
        # it is served instead, so that test no longer discriminates. The behaviour is still
        # caught by the test that is about it.
        caught_by=(
            "tests/test_evaluation_harness.py::"
            "test_baseline_f_executes_and_its_rows_say_why_they_are_there",
        ),
    ),
    Replant(
        name="R254-the-recency-probes-window-is-evidence-again",
        behaviour=(
            "A16: an id the internal D.5 step-(c) recency probe listed and nothing else "
            "reached takes the A.9(1) evidence tier, A.9a step 3's top-k protection and "
            "A.9(2)'s floor anchoring - so a ninety-day window becomes evidence and the "
            "rank-0 source's floor grows with it (R-M2-101)"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        # The same three lines R258 anchors, replaced the other way: R254 keeps the
        # shortlist's union and drops the demotion, R258 keeps the demotion and drops the
        # union. Each is planted on its own, so both match exactly once.
        anchor=(
            "                hit_ids=(frozenset(grouped[thread]) - demoted) "
            "| frozenset(chosen.get(thread, ())),\n"
        ),
        replacement=(
            "                hit_ids=frozenset(grouped[thread]) "
            "| frozenset(chosen.get(thread, ())),\n"
        ),
        # Cited on the layout and on `hit_threads` itself, not on the row roles: the role
        # rule declines to call a pool row `matched` whether or not it is in the evidence
        # tier, so a role assertion passes with this planted (found by planting it).
        caught_by=(
            "tests/test_a16_recency_pool_evidence.py::"
            "test_the_evidence_tier_excludes_the_probes_window",
            "tests/test_a16_recency_pool_evidence.py::"
            "test_hit_threads_subtracts_the_demoted_and_adds_only_the_shortlist",
        ),
    ),
    Replant(
        name="R255-the-routes-collapse-back-to-the-first-admission",
        behaviour=(
            "A16 asks every route an id was reached by; reading the first-admission origin "
            "instead strips a lexical match of its evidence protection whenever a pool probe "
            "listed it first, which the rungs that run after the pool make reachable"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor=(
            "        listings = [route for route in routes "
            "if route.endpoint is ObservedEndpoint.MESSAGES_LIST]\n"
        ),
        # The first-admission regression, without inventing an import: keep only the routes
        # that agree with the origin's rung, which is what reading `origins` amounts to.
        replacement=(
            "        origin = ledger.origins[message_id]\n"
            "        listings = [route for route in routes "
            "if route.endpoint is ObservedEndpoint.MESSAGES_LIST and route.rung is origin.rung]\n"
        ),
        caught_by=(
            "tests/test_a16_recency_pool_evidence.py::"
            "test_a_lexical_match_the_recency_probe_listed_first_keeps_its_evidence_route",
        ),
    ),
    Replant(
        name="R256-a-repeat-sighting-records-no-route",
        behaviour=(
            "The ledger records an admission route for every observation, not only the one "
            "that admitted the id (A16). Recording it inside the first-admission branch "
            "instead makes `routes` a second spelling of `origins`, which is the exact "
            "distinction the recency-pool separation rests on"
        ),
        path="server/src/mailweave/envelope/disposition.py",
        anchor=(
            "            self._routes.setdefault(message_id, set()).add(\n"
            "                AdmissionRoute(endpoint=page.endpoint, rung=rung, query=query)\n"
            "            )\n"
            "            existing = self._origins.get(message_id)\n"
            "            if existing is None:\n"
        ),
        replacement=(
            "            existing = self._origins.get(message_id)\n"
            "            if existing is None:\n"
            "                self._routes.setdefault(message_id, set()).add(\n"
            "                    AdmissionRoute(endpoint=page.endpoint, rung=rung, query=query)\n"
            "                )\n"
        ),
        caught_by=(
            "tests/test_a16_recency_pool_evidence.py::"
            "test_a_route_is_recorded_for_every_observation_and_the_origin_still_is_not",
            "tests/test_a16_recency_pool_evidence.py::"
            "test_a_lexical_match_the_recency_probe_listed_first_keeps_its_evidence_route",
        ),
    ),
    Replant(
        name="R257-every-pool-listing-is-a-recency-listing",
        behaviour=(
            "A16 is confined to D.5 step (c). Dropping the probe-query restriction demotes "
            "step (b)'s participant probes as well - the boundary the owner named explicitly "
            "as out of scope - and would demote a caller's own query if one ever listed at L5"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor=(
            "            route.rung is RungId.L5 and (wanted is None or route.query in wanted)\n"
        ),
        replacement="            route.rung is RungId.L5\n",
        caught_by=(
            "tests/test_a16_recency_pool_evidence.py::"
            "test_a_participant_probe_is_not_a_recency_probe_and_keeps_its_behaviour",
            "tests/test_a16_recency_pool_evidence.py::"
            "test_a_callers_own_date_query_is_not_an_internal_recency_probe",
        ),
    ),
    Replant(
        name="R258-the-shortlists-own-choice-is-not-put-back",
        behaviour=(
            "The evidence tier is what the query selected: the listings minus the demoted "
            "**plus the shortlist**. Subtracting alone empties the tier of a thread whose "
            "decisive message the pool read rather than listed, while the thread stays a "
            "source - so `_carries_nothing` takes its 'there was never any evidence' branch "
            "and step 7 may drop the source carrying the answer"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor=(
            "                hit_ids=(frozenset(grouped[thread]) - demoted) "
            "| frozenset(chosen.get(thread, ())),\n"
        ),
        replacement="                hit_ids=frozenset(grouped[thread]) - demoted,\n",
        caught_by=(
            "tests/test_a16_recency_pool_evidence.py::"
            "test_hit_threads_gives_the_shortlist_the_tier_even_when_no_listing_reached_it",
            "tests/test_a16_recency_pool_evidence.py::"
            "test_a_shortlisted_message_the_probe_could_not_list_is_still_evidence",
        ),
    ),
    Replant(
        name="R259-a-redraw-callback-runs-against-another-thread",
        behaviour=(
            "The corpus generator's four redraw callbacks close over the enclosing builder's "
            "per-thread locals (38 B023 diagnostics) and are safe only because "
            "`redraw_until_ranked` calls them synchronously and retains nothing. A callback "
            "that runs for a different iteration rewrites another conversation's evidence and "
            "leaves this one's family relationship unenforced - a corpus defect that both "
            "measurement entry points would then measure against"
        ),
        path="harness/src/mailweave_harness/seed/families.py",
        # The anchor carries the guard above the call. `redraw_until_top` was added for
        # R-M2-067 and calls `redraw()` at the same indentation, so the bare call is no longer
        # unique in the file; the `_ranks_ok` line names `redraw_until_ranked`'s loop and no
        # other.
        anchor=(
            "        if _ranks_ok(lines, query, above=above, below=below):\n"
            "            return\n"
            "        redraw()\n"
        ),
        replacement=(
            "        if _ranks_ok(lines, query, above=above, below=below):\n"
            "            return\n"
            '        globals().setdefault("_FIRST_REDRAW", []).append(redraw)\n'
            '        globals()["_FIRST_REDRAW"][0]()\n'
        ),
        # **One citation, and the other was dropped after planting it.** The natural corpus
        # fires only two redraws at seed 4311 (both F4), so the finished-corpus rank check does
        # not catch this on its own - it caught it in a combined run only because the forced
        # test had already run in the same process. The forced test is the one that holds.
        caught_by=(
            "tests/test_corpus_redraw_closure_binding.py::"
            "test_a_forced_redraw_lands_in_the_thread_it_was_handed",
        ),
    ),
    Replant(
        name="R260-a-rung-that-admitted-ids-is-reported-untried",
        behaviour=(
            "R-M2-113: D.5's declared fallback after an embedding failure. The pool's probes "
            "admit their ids to H at L5, so a report that names L5 only when the rung "
            "*completed* leaves a rung that produced hits absent from `rungs` - and the "
            "envelope's own validator then refuses the whole response, so the caller gets no "
            "answer at all where the contract promises a fallback"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor=(
            "    ran_semantic = semantic is not None and (\n"
            "        semantic.state is SemanticState.RAN or semantic_admitted\n"
            "    )\n"
        ),
        replacement=(
            "    ran_semantic = semantic is not None and semantic.state is SemanticState.RAN\n"
        ),
        caught_by=(
            "tests/test_r_m2_113_semantic_unavailable_fallback.py::"
            "test_the_declared_fallback_is_delivered",
            "tests/test_r_m2_113_semantic_unavailable_fallback.py::"
            "test_the_lexical_evidence_still_reaches_the_caller",
        ),
    ),
    Replant(
        name="R261-the-failed-rung-is-also-claimed-untried",
        behaviour=(
            "A rung named in `rungs` and again in `not_tried` is a response claiming one route "
            "both ran and was never reached. R-M2-113's repair stands the `not_tried` entry "
            "down for a rung whose probes are in H and reports the failure in band instead"
        ),
        path="server/src/mailweave/retrieval/assemble.py",
        anchor="    if admitted:\n",
        replacement="    if False:\n",
        caught_by=(
            "tests/test_r_m2_113_semantic_unavailable_fallback.py::"
            "test_the_declared_fallback_is_delivered",
        ),
    ),
    Replant(
        name="R262-the-h2-bypass-is-a-no-op",
        behaviour=(
            "H2's matched arm: `cross_encoder=False` must genuinely skip D.7's second tier - "
            "no backend acquired for it, no pair scored. A bypass that falls through runs the "
            "cross-encoder on both arms, and `full` against `no-rerank` then measures nothing "
            "while reporting a comparison"
        ),
        path="server/src/mailweave/retrieval/ranking.py",
        anchor="    if not cross_encoder:\n",
        replacement="    if False:\n",
        caught_by=(
            "tests/test_h2_rerank_arm.py::test_both_arms_embed_and_only_one_reranks",
            "tests/test_h2_rerank_arm.py::test_the_ranking_states_are_the_two_the_comparison_needs",
        ),
    ),
    Replant(
        name="R263-a-bypassed-tier-still-reports-a-cross-encoder-ordering",
        behaviour=(
            "The bypass arm's response must say the mechanical tier ordered it. A response "
            "that named `+cross-encoder` with no pair scored is the one field a reader has "
            "for telling a reranked response from a mechanically ordered one, saying the "
            "wrong thing"
        ),
        path="server/src/mailweave/retrieval/ranking.py",
        anchor=("        if self.state is RankingState.RERANKED and self.ordering_applied:\n"),
        replacement="        if True:\n",
        caught_by=(
            "tests/test_h2_rerank_arm.py::"
            "test_the_bypass_keeps_the_registered_ordering_and_invents_no_score",
        ),
    ),
    Replant(
        name="R264-h2s-verdict-comes-from-the-semantic-arm",
        behaviour=(
            "H2's clauses must be computed against the arm that differs in D.7's second tier. "
            "Reading the semantic baseline answers H1's question under H2's name: on a corpus "
            "where the embedding helps and the reranker hurts it reports HOLDS for a reranker "
            "that lost answers its own absence would have kept"
        ),
        path="harness/src/mailweave_harness/evaluation/hypotheses.py",
        # **Re-anchored 2026-09-18, same behaviour, new spelling.** The clause used to read a
        # hand-keyed `rerank_baseline_arm`; N-8 replaced the four baseline arguments with the
        # authoritative `pairs` mapping, so H2's baseline now arrives as `baseline`. The
        # mutation is the same mistake expressed against today's code: compute the baseline
        # side of `cut_loss` against the candidate's own arm, which makes any comparison
        # unfalsifiable.
        anchor=(
            '            mean_cut_loss(runs, family="ranking_stress", arm=baseline, '
            "scoring=score),\n"
        ),
        replacement=(
            '            mean_cut_loss(runs, family="ranking_stress", arm=candidate, '
            "scoring=score),\n"
        ),
        caught_by=(
            "tests/test_h2_verdict_follows_the_rerank_arm.py::"
            "test_h2s_verdict_follows_the_rerank_arm_and_not_the_semantic_one",
        ),
    ),
    Replant(
        name="R265-the-command-hands-h2-the-semantic-arm",
        behaviour=(
            "The caller half of the same defect: `evaluate` reading the right parameter is "
            "worth nothing if the command passes the wrong arm into it, which is the state "
            "that shipped once - the arm existed, the pairing was declared, and `__main__` "
            "still handed `evaluate` the semantic baseline"
        ),
        path="harness/src/mailweave_harness/evaluation/__main__.py",
        # **Re-anchored 2026-09-18.** The command used to pass four hand-keyed arms; it now
        # passes the mapping itself, which is what closed N-8 - changing a pair used to reach
        # the printed table and not the verdict. The mutation is today's version of the same
        # defect: hand `evaluate` a mapping whose H2 entry names the semantic arm, so the
        # table and the verdict disagree again.
        anchor="    results = evaluate(runs, scoring=scoring, pairs=HYPOTHESIS_PAIRS)\n",
        replacement=(
            "    results = evaluate(\n"
            "        runs,\n"
            "        scoring=scoring,\n"
            '        pairs={**HYPOTHESIS_PAIRS, "H2": (FULL.name, SEM_OFF.name)},\n'
            "    )\n"
        ),
        caught_by=(
            "tests/test_h2_verdict_follows_the_rerank_arm.py::test_the_command_itself_passes_h2s_arm",
        ),
    ),
    Replant(
        name="R233-a-gap-inside-the-intervals-is-called-a-win",
        behaviour=(
            "The report never calls a difference inside overlapping Wilson intervals an "
            "improvement. One corpus at one seed cannot separate a three-point lead from "
            "noise, and reporting it as a win is how a null result becomes a headline"
        ),
        path="harness/src/mailweave_harness/evaluation/report.py",
        anchor='        if not self.separated:\n            return "no change"\n',
        replacement='        if False:\n            return "no change"\n',
        caught_by=(
            "tests/test_evaluation_report.py::"
            "test_a_gap_inside_overlapping_intervals_is_reported_as_no_change",
            "tests/test_evaluation_report.py::"
            "test_the_rendered_report_names_both_arms_and_the_factor_isolated",
        ),
    ),
    Replant(
        name="R234-still-failing-merges-the-three-states",
        behaviour=(
            "'Still failing' keeps never_named, surfaced_never_carried and failed apart. "
            "They license different conclusions - retrieval, recoverability, and the "
            "product failing - and one merged count would say more than the run knows"
        ),
        path="harness/src/mailweave_harness/evaluation/report.py",
        anchor="        if missing & run.reach.surfaced_only:\n",
        replacement="        if False:\n",
        caught_by=(
            "tests/test_evaluation_report.py::test_the_three_still_failing_states_are_kept_apart",
        ),
    ),
    Replant(
        name="R235-an-empty-semantic-block-read-as-a-pool",
        behaviour=(
            "EP §6.4: an empty `pool_ids` is not an exposed candidate set. Every search "
            "emits a semantic block whether or not the semantic rungs ran, and scoring the "
            "empty one as a pool gives a negative cut_loss - which the metric forbids, "
            "since the shortlist is a subset of the pool"
        ),
        path="harness/src/mailweave_harness/evaluation/arms.py",
        anchor="            if record.semantic is not None and record.semantic.pool_ids:\n",
        replacement="            if record.semantic is not None:\n",
        caught_by=(
            "tests/test_evaluation_harness.py::test_an_empty_semantic_block_is_not_read_as_a_pool",
        ),
    ),
    Replant(
        name="R236-no-network-layer-pool-on-the-lexical-arm",
        behaviour=(
            "EP §6.4's second clause: where the system exposes no candidate set the pool is "
            "the union of messages it fetched, observed at the network layer. Without it the "
            "lexical arm has no pool at all, and cut_loss - the only thing EP lets a reranker "
            "be justified by - is unmeasurable on the arm the reranker has to beat"
        ),
        path="harness/src/mailweave_harness/evaluation/arms.py",
        anchor="    if pool_ids is None and observed:\n",
        replacement="    if False:\n",
        caught_by=(
            "tests/test_evaluation_harness.py::test_an_empty_semantic_block_is_not_read_as_a_pool",
        ),
    ),
    Replant(
        name="R237-the-harness-may-use-the-server-client",
        behaviour=(
            "A seeding run may not use the server's OAuth client. That client is for the "
            "owner's real mailbox at gmail.readonly; a seeding run against it would request "
            "https://mail.google.com/ on the personal account. The client ids are compared "
            "before any network call"
        ),
        path="harness/src/mailweave_harness/seed/driver.py",
        anchor="    if server.client_id == client.client_id:\n",
        replacement="    if False:\n",
        caught_by=(
            "tests/test_seed_driver.py::"
            "test_a_harness_client_that_is_the_server_client_is_refused_before_any_call",
        ),
    ),
    Replant(
        name="R238-approval-need-not-name-the-account",
        behaviour=(
            "`--approve-writes-to` names the mailbox and is compared with the configured "
            "seed address. An approval that does not name what it approves is a keystroke, "
            "and this one gates an irreversible first run"
        ),
        path="harness/src/mailweave_harness/seed/__main__.py",
        anchor="    if given != wanted:\n",
        replacement="    if False:\n",
        caught_by=(
            "tests/test_seed_driver.py::"
            "test_an_approval_that_names_a_different_account_stops_the_command",
        ),
    ),
    Replant(
        name="R239-a-rate-limited-insert-is-not-retried",
        behaviour=(
            "A bulk write of a few thousand messages meets Gmail's per-user rate limit. A "
            "429 that fails the run leaves a half-seeded mailbox, which is the one failure "
            "the seeding path must not have, so 429 and 5xx are retried with growing backoff "
            "and `Retry-After` is obeyed where Gmail sent one"
        ),
        path="harness/src/mailweave_harness/seed/gmail_transport.py",
        anchor="            if not retryable or attempt == self.max_attempts:\n",
        replacement="            if True:\n",
        caught_by=(
            "tests/test_seed_gmail_transport.py::"
            "test_a_rate_limited_insert_is_retried_rather_than_failing_the_run",
            "tests/test_seed_gmail_transport.py::test_retry_after_wins_over_the_computed_delay",
        ),
    ),
    Replant(
        name="R240-a-failed-seeding-leaves-no-cleanup-record",
        behaviour=(
            "Cleanup is driven from insert results and never from a query, so a run that "
            "fails partway still writes what it inserted. Without that record a half-seeded "
            "mailbox has no list of what to delete, and the only remaining option is the "
            "query-driven cleanup that removes somebody else's mail"
        ),
        path="harness/src/mailweave_harness/seed/driver.py",
        anchor="        _write(out, recorded, (), partial=True)\n",
        replacement="        pass\n",
        caught_by=(
            "tests/test_seed_driver.py::"
            "test_a_run_that_fails_partway_still_records_what_it_inserted",
            "tests/test_seed_driver.py::"
            "test_the_partial_report_cleans_up_exactly_what_was_inserted",
        ),
    ),
    Replant(
        name="R241-the-kit-schema-becomes-a-second-copy",
        behaviour=(
            "The authoring kit's schema modules are the repository's own files, copied at "
            "export time. A maintained second copy of the case schema is this project's "
            "recurring defect - one shape checked in two places, the second copy the one "
            "nobody updates - in the artifact whose whole claim is that the author's "
            "refusals are the scoring run's refusals"
        ),
        path="harness/src/mailweave_harness/evaluation/kit.py",
        anchor='        body = (source_root / relative).read_text(encoding="utf-8")\n',
        replacement='        body = "# a copy\\n"\n',
        caught_by=(
            "tests/test_authoring_kit.py::"
            "test_the_kit_schema_is_this_repositorys_own_file_and_not_a_copy",
            "tests/test_authoring_kit.py::test_the_checker_runs_standalone_and_passes_a_good_file",
        ),
    ),
    Replant(
        name="R242-the-manifest-join-is-not-checkable-before-seeding",
        behaviour=(
            "`check_against` is the manifest half of the ref join on its own, so a case "
            "author with a manifest and no mailbox gets the scoring run's own refusals. "
            "Without it the only check available was `resolve_against` with an empty "
            "verification report, telling the two halves apart by matching the prose of an "
            "exception"
        ),
        path="harness/src/mailweave_harness/evaluation/cases.py",
        anchor="    for one in case.distractors:\n",
        replacement="    for one in ():\n",
        caught_by=(
            "tests/test_authoring_kit.py::"
            "test_the_checker_refuses_a_distractor_ref_the_corpus_does_not_hold",
        ),
    ),
    Replant(
        name="R243-the-index-is-asked-before-the-gate",
        behaviour=(
            "The sentinel-uniqueness check asks Gmail's search index, which is eventually "
            "consistent. It runs AFTER the settle gate: asked straight after a bulk insert "
            "it answers 0 for almost every token, and a run that asked it there would report "
            "a discrepancy per sentinel on every successful seeding"
        ),
        path="harness/src/mailweave_harness/seed/driver.py",
        anchor="            check_mailbox=False,\n",
        replacement="            check_mailbox=True,\n",
        caught_by=(
            "tests/test_seed_driver.py::"
            "test_the_index_question_is_asked_after_the_settle_gate_and_not_before",
        ),
    ),
    Replant(
        name="R244-a-resume-inserts-everything-again",
        behaviour=(
            "A resumed run does not insert what the partial report already recorded, and "
            "those messages still count as present. Without that, recovering from a failure "
            "at message 2,000 means two thousand duplicates or a mass deletion"
        ),
        path="harness/src/mailweave_harness/seed/substrate.py",
        anchor="        if message.rfc822_message_id in already:\n",
        replacement="        if False:\n",
        caught_by=(
            "tests/test_seed_driver.py::"
            "test_a_resumed_run_inserts_only_what_is_missing_and_counts_the_rest_present",
        ),
    ),
    Replant(
        name="R245-a-literal-tilde-reaches-the-filesystem",
        behaviour=(
            "Every path argument is expanded where it enters the program. A `~` a shell did "
            "not expand reaches `TokenStore`, which stats it and reports "
            "'~/.mailweave-harness does not exist' - a message that reads like a missing "
            "login rather than an unexpanded path"
        ),
        path="harness/src/mailweave_harness/seed/__main__.py",
        anchor="    return Path(raw).expanduser()\n",
        replacement="    return Path(raw)\n",
        caught_by=(
            "tests/test_seed_driver.py::"
            "test_the_default_token_path_is_expanded_before_anything_stats_it",
        ),
    ),
    Replant(
        name="R246-insert-does-not-ask-for-a-thread",
        behaviour=(
            "Gmail's threading guide names three conditions for adding a message to an "
            "existing thread, and the first is that the target threadId is part of the "
            "resource supplied with the request. Without it Gmail opens a new conversation "
            "per message and says nothing: R-M2-033, 2,248 messages, 2,248 threads"
        ),
        path="harness/src/mailweave_harness/seed/substrate.py",
        anchor="thread_id=conversation.get(message.thread_key))\n",
        replacement="thread_id=None)\n",
        caught_by=(
            "tests/test_seed_threading.py::"
            "test_the_corpus_lands_in_one_conversation_per_manifest_thread",
            "tests/test_seed_threading.py::"
            "test_every_thread_after_the_first_message_asks_for_a_thread_id",
        ),
    ),
    Replant(
        name="R247-a-declined-association-is-not-noticed",
        behaviour=(
            "Gmail declines an association silently: it creates the message in a new thread "
            "and returns that id rather than failing the call. The transport compares the id "
            "it asked for against the id it got, because a seeder that trusted the request "
            "cannot tell success from failure and finds out 2,248 messages later"
        ),
        path="harness/src/mailweave_harness/seed/gmail_transport.py",
        anchor="        if thread_id is not None and assigned != thread_id:\n",
        replacement="        if False:\n",
        caught_by=(
            "tests/test_seed_gmail_transport.py::"
            "test_a_thread_gmail_declined_raises_rather_than_returning_the_new_thread",
        ),
    ),
    Replant(
        name="R248-a-resume-forgets-the-conversations-it-opened",
        behaviour=(
            "A resumed run rebuilds the thread_key to conversation map from the partial "
            "report. Without it, every thread it continues is opened as a second "
            "conversation and the split is invisible until `verify` runs at the end"
        ),
        path="harness/src/mailweave_harness/seed/substrate.py",
        anchor="    conversation: dict[str, str] = thread_map(manifest, prior)\n",
        replacement="    conversation: dict[str, str] = {}\n",
        caught_by=(
            "tests/test_seed_threading.py::"
            "test_a_resumed_run_continues_the_conversations_it_already_opened",
        ),
    ),
    Replant(
        name="R249-the-double-hands-itself-the-answer",
        behaviour=(
            "The mailbox double threads by the documented API rules, not by the manifest's "
            "own thread_key. A double that derives the conversation from the thing that "
            "defines the intent answers a question nobody asked, which is why every "
            "threading test passed while the real run produced one thread per message"
        ),
        path="tests/fixtures/gmail_threading.py",
        anchor="        if thread_id is None:\n            return False\n",
        replacement="        if thread_id is None:\n            return True\n",
        caught_by=(
            "tests/test_seed_threading.py::"
            "test_the_double_opens_a_new_thread_when_no_thread_id_is_asked_for",
            "tests/test_seed_threading.py::"
            "test_a_resume_with_no_thread_map_would_split_the_threads_it_continues",
        ),
    ),
    Replant(
        name="R250-an-already-deleted-id-reads-as-a-failure",
        behaviour=(
            "A delete that finds nothing to delete is the goal, not a failure. A cleanup of "
            "thousands of ids can stop partway and the record naming all of them is the only "
            "safe input to a second attempt; reporting every id the first pass removed as an "
            "error makes that attempt's output useless"
        ),
        path="harness/src/mailweave_harness/seed/gmail_transport.py",
        anchor=(
            '            if " returned 404" in str(failure) or " returned 410" in str(failure):\n'
        ),
        replacement="            if False:\n",
        caught_by=(
            "tests/test_seed_gmail_transport.py::"
            "test_a_delete_of_a_message_that_is_gone_is_not_a_failure",
        ),
    ),
    Replant(
        name="R251-an-irreversible-step-leaves-no-record",
        behaviour=(
            "`messages.delete` is permanent - not the trash, no bin, no undo - so the cleanup "
            "writes down what it actually deleted. The input record says what was targeted; "
            "without this there is nothing saying what was done"
        ),
        path="harness/src/mailweave_harness/seed/driver.py",
        anchor="    if out is not None:\n        out.parent.mkdir(parents=True, exist_ok=True)\n",
        replacement="    if False:\n        out.parent.mkdir(parents=True, exist_ok=True)\n",
        caught_by=("tests/test_seed_driver.py::test_a_cleanup_records_what_it_actually_deleted",),
    ),
    # --- continuation correctness across thread changes (2026-09-15) ----------------------
    Replant(
        name="R252-a-thread-continuation-is-a-pointer-again",
        behaviour=(
            "A `thread` continuation names its page's own map_id, so following it after the "
            "thread changed is refused as handle_stale with the restart rather than served as "
            "page k of a different state - a pointer form would skip or repeat silently"
        ),
        path="server/src/mailweave/disclosure/pages.py",
        anchor=(
            '        affordance=Affordance(tool=ToolName.THREAD_MAP, args={"map_id": map_id, '
            '"page": page + 1}),\n'
        ),
        replacement=(
            '        affordance=Affordance(tool=ToolName.THREAD_MAP, args={"thread_id": thread_id, '
            '"page": page + 1}),\n'
        ),
        caught_by=(
            "tests/test_navigation_and_disclosure.py::"
            "test_a_continuation_after_a_message_leaves_restarts_rather_than_skipping",
            "tests/test_navigation_and_disclosure.py::"
            "test_a_continuation_after_a_message_arrives_restarts_rather_than_repeating",
            "tests/test_navigation_and_disclosure.py::"
            "test_a_continuation_across_a_width_change_restarts_at_the_new_width",
        ),
    ),
    Replant(
        name="R253-a-continuation-is-offered-where-nothing-can-verify-it",
        behaviour=(
            "A response that mints no handle offers no `thread` continuation: a page nothing "
            "can verify is not the remainder of anything, and its runs still point at every page"
        ),
        path="server/src/mailweave/disclosure/pages.py",
        anchor="    if start >= total or map_id is None:\n",
        replacement="    if start >= total:\n",
        caught_by=(
            "tests/test_navigation_and_disclosure.py::"
            "test_the_no_key_path_offers_no_thread_continuation_and_pages_by_pointer",
        ),
    ),
    # --- the authentication-record bound is on the record, not its fence (2026-09-23) -----
    Replant(
        name="R254-the-authentication-bound-measures-the-fence",
        behaviour=(
            "INJ-05: SenderAuthentication measures the record inside its fence, as the "
            "producer and the charge do. Measuring the fenced text refuses every record "
            "within the fence's 46 characters of the bound, and a served thread becomes an "
            "internal error (the Harbor run's thread map and expansion)"
        ),
        path="server/src/mailweave/envelope/wire.py",
        anchor="        record = fenced_text(self.recorded.text)\n",
        replacement=(
            "        record = self.recorded.text if fenced_text(self.recorded.text) else None\n"
        ),
        caught_by=(
            "tests/test_auth_record_fence_boundary.py::"
            "test_mapping_the_thread_directly_serves_the_record",
            "tests/test_auth_record_fence_boundary.py::"
            "test_expanding_the_answers_thread_node_maps_the_thread_and_serves",
            "tests/test_auth_record_fence_boundary.py::"
            "test_the_model_measures_the_record_inside_its_fence",
        ),
    ),
    Replant(
        name="R255-an-unfenced-authentication-record-is-measured-and-carried",
        behaviour=(
            "INJ-05/R-09: the model reads the record out of its fence to measure it, and a "
            "record with no fence is refused, not measured as it stands"
        ),
        path="server/src/mailweave/envelope/wire.py",
        anchor="        if record is None:\n            raise ValueError(\n",
        replacement=(
            "        if record is None:\n            record = self.recorded.text\n"
            "        if False:\n            raise ValueError(\n"
        ),
        caught_by=(
            "tests/test_auth_record_fence_boundary.py::"
            "test_an_unfenced_record_is_refused_rather_than_measured",
        ),
    ),
)


def anchor_counts(tree: Path = TREE) -> dict[str, int]:
    """How many times each replant's anchor matches in `tree`. Every value must be 1."""
    return {
        replant.name: (tree / replant.path).read_text().count(replant.anchor)
        for replant in REPLANTS
    }


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class PlantResult:
    """One plant, run. `caught` is **every** named test failing on its own.

    **`caught` used to be one pytest invocation over the whole citation list and one return
    code** (R-RETR-061), so it meant "at least one of them failed" and a citation that never
    caught anything was invisible. Two of round 21's citations were exactly that, and it is
    how R-RETR-058 stayed unnoticed: the manifest said the commonality property defended the
    cache tautology and the `fetched_at` stamp, and it defended neither. A `caught_by` entry
    is a claim about *that test*, so it is now run alone and `caught_per_citation` records
    what each one did.
    """

    replant: Replant
    anchor_matches: int
    digest_before: str
    digest_after: str
    #: `{citation: did this test, run alone, fail?}`. One entry per `caught_by` entry.
    caught_per_citation: dict[str, bool]
    whole_suite_caught: bool | None
    detail: str

    @property
    def caught(self) -> bool:
        """Every citation catches. Not "some citation catches"; see the class docstring."""
        return bool(self.caught_per_citation) and all(self.caught_per_citation.values())

    @property
    def citations_that_do_not_catch(self) -> tuple[str, ...]:
        return tuple(name for name, did in self.caught_per_citation.items() if not did)

    @property
    def file_changed(self) -> bool:
        return self.digest_before != self.digest_after


def make_scratch_tree(destination: Path, tree: Path = TREE) -> Path:
    """A full copy of `tree` - source, tests and fixtures - to plant into."""
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(
        tree,
        destination,
        ignore=shutil.ignore_patterns(".venv", ".git", "__pycache__", ".*_cache", ".hypothesis"),
    )
    return destination


def assert_the_scratch_tree_is_green(scratch: Path) -> None:
    """The copy passes before anything is planted into it.

    Without this a broken *copy* makes every plant report CAUGHT for free, which is the
    reintroduction harness's own version of the vacuity trap - and it caught me: my first
    copy excluded `docs/`, `tools/rubric_status.py` reads `docs/RELEASE_RUBRIC.md`, and the
    whole-suite pass therefore failed on a tree nothing had been planted into.
    """
    result = _run(scratch, ["-m", "not network and not replant"], timeout=1200)
    if result.returncode != 0:
        tail = "\n".join(result.stdout.strip().splitlines()[-8:])
        raise AssertionError(f"the scratch tree is not green before planting:\n{tail}")


def assert_the_named_tests_pass_before_planting(scratch: Path) -> None:
    """Every test the manifest cites passes on the copy **before** any plant is written.

    The control every CAUGHT row rests on. A plant is "caught" when the test named against it
    fails after the plant; that is evidence only if the same test passed before it, and a copy
    that is broken - a missing directory, a stale `__pycache__`, a file the copy skipped -
    fails everything and reports the whole manifest defended. `assert_the_scratch_tree_is_green`
    is the exhaustive version and costs a whole suite run; this is the same guard over exactly
    the tests whose outcome the manifest reads, and it costs one.
    """
    named = sorted({citation for replant in REPLANTS for citation in replant.caught_by})
    result = _run(scratch, ["-m", "not network", *named], timeout=1200)
    if result.returncode != 0:
        tail = "\n".join(result.stdout.strip().splitlines()[-12:])
        raise AssertionError(
            "the tests this manifest reads do not pass on the unplanted copy, so a CAUGHT "
            f"row would be evidence of nothing:\n{tail}"
        )


def workspace_members(tree: Path = TREE) -> tuple[str, ...]:
    """The workspace members, read from `pyproject.toml` rather than listed here.

    R-RETR-042 was a hand-maintained list that stopped covering what it named, and adding
    the next package to the same hand-maintained list would only postpone the next
    occurrence. `[tool.uv.workspace] members` is where the answer already lives.
    """
    with (tree / "pyproject.toml").open("rb") as handle:
        configuration = tomllib.load(handle)
    members = configuration["tool"]["uv"]["workspace"]["members"]
    return tuple(str(member) for member in members)


def source_roots(scratch: Path) -> tuple[Path, ...]:
    """Every directory a planted subprocess must import from, inside `scratch`.

    Each workspace member's `src/`, plus the tree root for `tests`. Derived, so a fifth
    member is covered the day it exists rather than the day someone remembers.
    """
    roots = [scratch / member / "src" for member in workspace_members()]
    return (*[root for root in roots if root.is_dir()], scratch)


def source_packages_on_disk(tree: Path) -> tuple[str, ...]:
    """Every importable package that actually exists under a `<member>/src/`, found by
    walking the tree rather than by reading a declaration.

    The other half of the derivation, and the half that matters. Deriving the path *and* the
    probe from `[tool.uv.workspace] members` makes them agree with each other, which is not
    the same as making them agree with reality: a package added to the tree and never
    registered as a member is absent from both, so a planted subprocess imports it from the
    working tree and the probe never notices. This function looks at the disk, and
    `assert_imports_resolve_into_the_scratch_tree` refuses when the two disagree.
    """
    found: list[str] = []
    for source in sorted(tree.glob("*/src")):
        if not source.is_dir():
            continue
        found.extend(
            sorted(
                child.name
                for child in source.iterdir()
                if child.is_dir() and (child / "__init__.py").exists()
            )
        )
    return tuple(found)


def importable_packages(scratch: Path) -> tuple[str, ...]:
    """The package names those roots provide, plus `tests`.

    A package is a directory under a member's `src/` holding an `__init__.py`. Read off the
    tree for the same reason the members are: a list of names is a list that goes stale.
    """
    found: list[str] = []
    for member in workspace_members():
        source = scratch / member / "src"
        if not source.is_dir():
            continue
        found.extend(
            sorted(
                child.name
                for child in source.iterdir()
                if child.is_dir() and (child / "__init__.py").exists()
            )
        )
    return (*found, "tests")


def _environment(scratch: Path) -> dict[str, str]:
    """The `PYTHONPATH` a planted subprocess runs under: **every** importable package, copied.

    `harness/src` is here since round 19 (R-RETR-042). It was missing, and the assertion below
    covered `mailweave` and `tests` only - so in the planted subprocess `mailweave_harness`
    resolved into the *working* tree and the five test modules that import it ran against code
    no plant had touched. No manifest entry plants into `harness/`, so no row was wrong; the
    claim "both packages resolve inside the scratch copy" simply covered two of the three
    packages the suite imports, which is the shape of a guard that has stopped guarding.

    **`orivra/src` joins them at M1, and for exactly the same reason.** A fourth importable
    package arrived and this list did not grow with it, so a planted subprocess would have
    imported `orivra` from the editable install in the working tree - the same defect, one
    package later, and the reason it is caught here is that R-RETR-042 wrote down what the
    trap looks like. The rule the list now states: **every package the suite imports is on
    this path, and `assert_imports_resolve_into_the_scratch_tree` names every one of them.**

    **A planted subprocess does not inherit what this codebase sets into its own environment.**
    `dict(os.environ)` carried `HF_HUB_OFFLINE` and its three companions into the child,
    because importing `mailweave.semantic.local` in the *parent* calls `force_offline()`,
    which mutates the parent's process environment. So the plant that deletes that import-time
    call - R213 - could not be caught: the child inherited the flags the deleted line was
    supposed to set, and the test that reads `os.environ` after the import passed anyway.

    **That is what made it a full-suite-only failure.** Run `tests/test_replants.py` on its
    own and nothing has imported the backend, so the parent's environment is clean, the child
    inherits nothing and the plant is caught. Run the whole suite and
    `tests/test_offline_enforcement.py` has already imported it, so the flags are set and the
    plant is missed. A mutation harness whose verdict depends on what else ran first is not
    measuring the mutation.

    The excluded set is **derived from the product code**, never listed here: it is exactly
    the variables `force_offline` writes, and
    `test_the_products_only_environment_writer_is_the_one_this_excludes` fails if this
    codebase grows another writer.
    """
    env = {name: value for name, value in os.environ.items() if name not in not_inherited()}
    env["PYTHONPATH"] = os.pathsep.join(str(root) for root in source_roots(scratch))
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def not_inherited() -> frozenset[str]:
    """Environment variables the product itself sets, which a planted subprocess must not get.

    Imported rather than copied. A literal list here would be a second statement of the same
    fact, free to fall out of step with the first - and the way it would fail is silently, as
    a plant reported CAUGHT against a guarantee the child inherited instead of establishing.
    """
    from mailweave.semantic.local import OFFLINE_ENVIRONMENT

    return frozenset(OFFLINE_ENVIRONMENT)


def assert_imports_resolve_into_the_scratch_tree(scratch: Path) -> tuple[str, ...]:
    """**Every** package the suite imports resolves from `scratch`, and none from the working tree.

    The trap this exists for: the venv installs `mailweave` as an editable `.pth`, which is
    already on `sys.path` before `PYTHONPATH` is consulted for some layouts. A harness that
    does not check reports every plant CAUGHT while testing code it never modified. Asserting
    the positive (`startswith(scratch)`) is not enough on its own either, because a scratch
    path that happens to be under the working tree satisfies it; the negative is asserted too.

    **Four packages, not three** (M1; three since round 19, R-RETR-042). `mailweave_harness`
    used to be absent from both the path and the assertion, so five test modules in every
    planted run imported the working tree. `orivra` was in exactly that position the day it
    was added. A guard that covers some of what it names is the shape this file exists to
    remove, so the list is the packages themselves and the assertions are made over it.
    """
    declared = importable_packages(scratch)
    on_disk = (*source_packages_on_disk(scratch), "tests")
    if set(declared) != set(on_disk):
        missing = sorted(set(on_disk) - set(declared))
        stray = sorted(set(declared) - set(on_disk))
        raise AssertionError(
            "the workspace declaration and the tree disagree about which packages exist: "
            f"present on disk and undeclared {missing}, declared and absent {stray}. An "
            "undeclared package is not on the planted subprocess's path, so it imports from "
            "the working tree and every plant reports CAUGHT while testing code no plant "
            "touched - which is R-RETR-042 exactly, and is why this is checked against the "
            "disk rather than against the declaration that produced the path"
        )
    names = declared
    probe = (
        "import json, " + ", ".join(names) + ";"
        "print(json.dumps([" + ", ".join(f"{name}.__file__" for name in names) + "]))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=scratch,
        env=_environment(scratch),
        capture_output=True,
        text=True,
        check=True,
    )
    import json

    resolved: list[str] = json.loads(result.stdout.strip().splitlines()[-1])
    root = str(scratch.resolve())
    working = str(TREE.resolve())
    for path in resolved:
        assert path.startswith(root), path
        assert not path.startswith(working + os.sep), path
    return tuple(resolved)


def _run(
    scratch: Path, arguments: list[str], timeout: int = 900
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", *arguments],
        cwd=scratch,
        env=_environment(scratch),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def plant(scratch: Path, replant: Replant) -> tuple[int, str, str]:
    """Write one replant into `scratch`, asserting the anchor and the change."""
    target = scratch / replant.path
    original = target.read_text()
    matches = original.count(replant.anchor)
    if matches != 1:
        raise AssertionError(f"{replant.name}: anchor matched {matches} times, expected 1")
    before = _digest(target)
    target.write_text(original.replace(replant.anchor, replant.replacement))
    after = _digest(target)
    if before == after:
        raise AssertionError(f"{replant.name}: the file did not change")
    return matches, before, after


def run_replants(
    scratch: Path, *, whole_suite: bool = False, only: tuple[str, ...] = ()
) -> Iterator[PlantResult]:
    """Plant each replant in turn, run the tests that must catch it, restore the file.

    Each citation is run **alone** and each must fail (R-RETR-061): a `caught_by` entry is a
        claim about that test, and one pytest invocation over the whole list answers a
        different, weaker question.

    With `whole_suite`, the whole suite is run as well with the named tests **deselected**
        and `tests/test_replants.py` ignored (R-RETR-062) - which is the question R-RETR
        asked of round 17 and got "2,248 green" for: is this behaviour defended by anything
        other than the test written for it?

        **The copy is proved sound before anything is planted into it, on every pass** (round 19,
        R-RETR-042). The greenness precondition used to run only under `whole_suite`, which is the
        branch CI does not take - so the copy of this evidence that ships had no positive evidence
        that the tree it planted into was sound, and a broken copy reports every plant CAUGHT for
        free. The cheap form of that guard is the sound one here: every test the manifest names is
        run on the pristine copy and must pass, which is exactly the claim each CAUGHT row depends
        on. `assert_the_scratch_tree_is_green` remains the stronger form and still runs under
        `whole_suite`.
    """
    assert_imports_resolve_into_the_scratch_tree(scratch)
    assert_the_named_tests_pass_before_planting(scratch)
    if whole_suite:
        assert_the_scratch_tree_is_green(scratch)
    pristine = {replant.path: (scratch / replant.path).read_text() for replant in REPLANTS}
    for replant in REPLANTS:
        if only and replant.name not in only:
            continue
        matches, before, after = plant(scratch, replant)
        try:
            per_citation: dict[str, bool] = {}
            detail = ""
            for citation in replant.caught_by:
                alone = _run(scratch, [citation])
                per_citation[citation] = alone.returncode != 0
                if alone.stdout.strip():
                    detail = alone.stdout.strip().splitlines()[-1]
            elsewhere: bool | None = None
            if whole_suite:
                # **`tests/test_replants.py` is excluded from this run** (R-RETR-062).
                # `test_every_replant_anchor_matches_exactly_once_in_the_tree` is not marked
                # `replant` and runs in the default gate, so it fails for any plant that
                # rewrites its own anchored line - which made `elsewhere` True before any
                # behavioural test was consulted, for fifteen of round 21's sixteen entries.
                # The honest answer to "is this behaviour defended by anything other than the
                # test written for it?" is often False, and False is a perfectly acceptable
                # state for a replant: the point of a manifest is that the one test exists.
                deselect = [arg for test in replant.caught_by for arg in ("--deselect", test)]
                broad = _run(
                    scratch,
                    ["-m", "not network", "--ignore=tests/test_replants.py", *deselect],
                )
                elsewhere = broad.returncode != 0
            yield PlantResult(
                replant=replant,
                anchor_matches=matches,
                digest_before=before,
                digest_after=after,
                caught_per_citation=per_citation,
                whole_suite_caught=elsewhere,
                detail=detail,
            )
        finally:
            (scratch / replant.path).write_text(pristine[replant.path])
