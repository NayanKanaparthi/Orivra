"""The round-14 LOWs and MEDIUM: every claim narrowed to what the code does, and executed.

Five findings, one shape. R-SEC put it as *"five of my six findings are the same shape - a
claim wider than the code"*, and each of the corrections below is only worth having if the
corrected sentence is now something a test drives:

  * **R-SEC-055** - `record.py` said the walk "refuses what it cannot read" and used
    `isinstance(record, dict)`, so a `dict` subclass hiding its `items()` was read as *empty*
    and passed, and `render_summary` then wrote its contents into `SUMMARY.md` by
    `__getitem__`. The stated defence - "the checker and the writer agree" - was true of one of
    the two writers;
  * **R-SEC-056** - `validation.py` said `hide_input_in_errors` "closes it for *every*
    renderer". It closes `str()`;
  * **R-SEC-057** - `pinning.py` said the refusal "is one comparison and it has one answer".
    For a `proof` that is not an ASCII `str` it was a `TypeError` out of `compare_digest`;
  * **R-SEC-058** - `constants.py` described its residue as "a different spelling of the same
    *intent*". Grouping punctuation and Unicode equivalence around the *same* operator evaded
    it, which is a different class and the same one the case fold closed;
  * **R-SEC-059** - the module says control 2 compares against "the configured seed address".
    There is no configuration binding and no caller. Not fixed here, and the residue is now
    named; this file pins that the gap is real, so the note cannot rot into a description of
    something that was quietly fixed.
"""

from __future__ import annotations

import inspect
import json
import tempfile
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from mailweave.config import MailweaveConfig
from mailweave.constants import widens_beyond_the_default_mailbox as widens
from mailweave_harness.pinning import SeedSession, verify_seed_account
from mailweave_harness.preflight.record import (
    RecordWouldCarryContent,
    _over_the_bound,
    assert_record_is_content_free,
    render_summary,
    write_records,
)
from mailweave_harness.scopes import SEEDER_SCOPES, SeedAccountMismatch

#: Synthetic filler, not mail. Multi-line and over the bound, which is all the check looks at.
SHAPED_LIKE_A_BODY = "line one of a message-shaped block\nline two of a message-shaped block\n" * 4

HONEST_RECORD: dict[str, Any] = {
    "probe": "PF-01",
    "title": "a probe",
    "verdict": "pass",
    "measures": "a measure",
    "validates": "a claim",
    "falsified_when": "a condition",
    "changes_if_it_fails": "a consequence",
    "pre_registered_rules": ["one of our sentences"],
    "credential": "read-only",
    "quota_budget_units": 1,
    "findings": {"per_endpoint": {"messages.list": 3}},
    "notes": ["one of our sentences"],
}


# --- R-SEC-055, and the peer of its own fix ----------------------------------------------------


class Hiding(dict[str, Any]):
    """R-SEC's container: a `dict` the walk cannot read, which passed as empty."""

    def items(self) -> Any:
        return []

    def keys(self) -> Any:
        return []

    def __iter__(self) -> Any:
        return iter(())

    def __len__(self) -> int:
        return 0


class Understating(int):
    """The peer nobody filed: a scalar whose `__str__` is what the second writer prints."""

    def __str__(self) -> str:
        return SHAPED_LIKE_A_BODY


class Silent(list[Any]):
    def __iter__(self) -> Any:
        return iter(())

    def __len__(self) -> int:
        return 0


SUBCLASS_SHAPES: dict[str, Any] = {
    "a dict that hides its items": Hiding({**HONEST_RECORD, "credential": SHAPED_LIKE_A_BODY}),
    "a dict subclass one level down": {
        **HONEST_RECORD,
        "findings": Hiding({"x": SHAPED_LIKE_A_BODY}),
    },
    "an int whose __str__ is a body": {
        **HONEST_RECORD,
        "quota_budget_units": Understating(1),
    },
    "a list that hides its contents": {**HONEST_RECORD, "notes": Silent([SHAPED_LIKE_A_BODY])},
}


@pytest.mark.parametrize("shape", sorted(SUBCLASS_SHAPES))
def test_a_json_type_lookalike_is_refused_rather_than_read_as_empty(shape: str) -> None:
    """The rule is the JSON types themselves, not what passes `isinstance` for them.

    A subclass is exactly a thing that answers one interface differently from another, and this
    record has two writers that use different interfaces: `json.dumps` iterates a mapping with
    `items()` and formats a scalar with its base type, while `render_summary` looks keys up
    with `__getitem__` and interpolates values with `__str__`. "The checker and the writer
    agree" is a claim about a pair, and there is no single pair.
    """
    with pytest.raises(RecordWouldCarryContent) as raised:
        assert_record_is_content_free(SUBCLASS_SHAPES[shape])
    assert "cannot read" in str(raised.value)
    assert SHAPED_LIKE_A_BODY[:20] not in str(raised.value)


@pytest.mark.parametrize("shape", sorted(SUBCLASS_SHAPES))
def test_nothing_is_written_for_a_record_the_walk_refuses(shape: str) -> None:
    """The end-to-end half: R-SEC-055's harm was `SUMMARY.md`, not the walk's return value.

    `write_records` checks each record before it writes anything, so a refusal means no JSON
    file and no summary - which is what makes the refusal a defence rather than a report.
    """

    class Result:
        class spec:
            id = "PF-01"

        def as_record(self) -> Any:
            return SUBCLASS_SHAPES[shape]

    out = Path(tempfile.mkdtemp())
    with pytest.raises(RecordWouldCarryContent):
        write_records([Result()], out)  # type: ignore[list-item]

    written = sorted(path.name for path in out.iterdir())
    assert written == [], f"a refused record still wrote {written}"


def test_the_second_writer_reads_the_same_object_the_walk_read() -> None:
    """Why `type(record) is dict` is the fix rather than "also check `render_summary`".

    Both writers are driven over one record that has passed the walk, and what they emit is
    compared. With an exact `dict` there is no interface for the two to disagree through:
    `json.dumps` sees the same items the walk saw, and `render_summary`'s `__getitem__` returns
    the same values. That is the property "the checker and the writer agree" was reaching for,
    and it is asserted here rather than argued.
    """
    record = dict(HONEST_RECORD)
    assert_record_is_content_free(record)

    as_json = json.loads(json.dumps(record, sort_keys=True))
    assert as_json == record

    summary = render_summary([record], "2026-09-02T00:00:00Z")
    for value in ("PF-01", "a probe", "read-only", "one of our sentences"):
        assert value in summary


def test_the_bound_is_still_taken_on_the_characters_where_it_is_measured() -> None:
    """`_plain` is now a second net, and a second net is only worth having if it is live.

    A `str` subclass no longer reaches the bound at all - the walk refuses it as a type it
    cannot read - so the reduction is exercised directly here. Deleting `_plain` would
    otherwise stop failing anything, which is how a defence becomes decoration.
    """

    class Understated(str):
        def __len__(self) -> int:
            return 3

        def splitlines(self, keepends: bool = False) -> list[str]:
            return [self]

    lying = Understated(SHAPED_LIKE_A_BODY)
    assert len(lying) == 3, "the liar must understate itself, or it tests nothing"

    problem = _over_the_bound(lying, "somewhere")
    assert problem is not None and SHAPED_LIKE_A_BODY[:20] not in problem

    with pytest.raises(RecordWouldCarryContent):
        assert_record_is_content_free({**HONEST_RECORD, "credential": lying})


def test_the_records_the_six_shipped_probes_actually_emit_still_pass() -> None:
    """The rule must not refuse the thing it exists to permit."""
    assert_record_is_content_free(dict(HONEST_RECORD))
    assert_record_is_content_free({"absent": None, "ratio": 0.5, "exceeded": False, "n": 3})
    assert_record_is_content_free({"notes": [], "pre_registered_rules": []})


# --- R-SEC-056 ---------------------------------------------------------------------------------


def test_hide_input_in_errors_closes_the_string_rendering_and_not_the_other_two() -> None:
    """The A/B behind the corrected sentence, so the correction is a measurement.

    `hide_input_in_errors` is real and it closes the surface every traceback, log line and
    f-string uses. It does not close `.errors()` or `.json()`, which default to
    `include_input=True` - and `.json()` returns a string, so "not a rendering" was not
    available as a defence either.
    """

    class Hidden(BaseModel):
        model_config = ConfigDict(hide_input_in_errors=True)
        a: int

    class Shown(BaseModel):
        a: int

    secret = "SECRET-VALUE-THAT-SHOULD-NOT-APPEAR-0123456789"

    with pytest.raises(ValidationError) as hidden:
        Hidden(a=secret)  # type: ignore[arg-type]
    with pytest.raises(ValidationError) as shown:
        Shown(a=secret)  # type: ignore[arg-type]

    assert secret not in str(hidden.value), "the flag closes the default string rendering"
    assert secret in str(shown.value), "and without it the string rendering carries the value"

    assert secret in json.dumps(hidden.value.errors()), ".errors() carries it with no argument"
    assert secret in hidden.value.json(), ".json() carries it with no argument"
    assert secret not in json.dumps(hidden.value.errors(include_input=False))


def test_nothing_in_either_tree_renders_a_validation_error_the_two_open_ways() -> None:
    """What actually keeps those two surfaces out of this tree, asserted.

    The corrected docstring says the AST sweep is the defence rather than the flag. That sweep
    is round 12's and lives in its own standing-cycle file; this asserts the narrower fact the
    sentence rests on - the only `.errors()` call in the server tree passes
    `include_input=False` - so the claim is not left resting on a test somewhere else being
    about what this one needs.
    """
    import ast

    from mailweave import validation

    tree = ast.parse(inspect.getsource(validation))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"errors", "json"}
    ]
    assert calls, "the sweep found no call at all, so it asserts nothing"
    for call in calls:
        attribute = call.func
        assert isinstance(attribute, ast.Attribute)
        assert attribute.attr == "errors", f"validation.py calls .{attribute.attr}()"
        assert any(
            keyword.arg == "include_input"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is False
            for keyword in call.keywords
        ), "a .errors() call in validation.py does not pass include_input=False"


# --- R-SEC-057 ---------------------------------------------------------------------------------


class _Credential:
    """A `ProfileSource` that answers for the seed account."""

    def get_profile(self) -> Any:
        from mailweave.gmail import Profile

        return Profile.model_validate(
            {
                "emailAddress": "mailweave.seed@harness.example",
                "messagesTotal": 0,
                "threadsTotal": 0,
                "historyId": "1",
            }
        )


UNCOMPARABLE_PROOFS: dict[str, Any] = {
    "None": None,
    "an int": 5,
    "bytes": b"0" * 64,
    "a non-ASCII str": "é" * 64,
    "a list": [],
    "a bare object": object(),
}


@pytest.mark.parametrize("shape", sorted(UNCOMPARABLE_PROOFS))
def test_an_uncomparable_proof_is_a_refusal_and_not_a_type_error(shape: str) -> None:
    """Six shapes, six `TypeError`s before this round, and zero `SeedAccountMismatch`.

    Fail-closed either way - the operation aborts - but a WS-16 call site written as
    `except SeedAccountMismatch:` would have got an exception it did not plan for, and the
    docstring's "one comparison and it has one answer" was not true of the code.
    """
    credential = _Credential()
    session = verify_seed_account(credential, seed_address="mailweave.seed@harness.example")
    session.assert_bound_to(credential)  # the control: this one authorises

    shell = object.__new__(SeedSession)
    object.__setattr__(shell, "address", session.address)
    object.__setattr__(shell, "scopes", session.scopes)
    object.__setattr__(shell, "credential", credential)
    object.__setattr__(shell, "proof", UNCOMPARABLE_PROOFS[shape])

    with pytest.raises(SeedAccountMismatch):
        shell.assert_bound_to(credential)


# --- R-SEC-058 ---------------------------------------------------------------------------------


WIDENING_SPELLINGS = (
    "in:anywhere",
    "IN:ANYWHERE",
    "(in:anywhere)",
    "{in:anywhere in:spam}",
    "in:anywhere,",
    "in:anywhere)",
    "[in:trash]",
    "in:spam;",
    "ＩＮ：ＡＮＹＷＨＥＲＥ",
    "from:amy (in:anywhere)",
)

NOT_WIDENING = (
    "-in:spam",
    "in:spammers",
    '"in:anywhere"',
    "in:inbox",
    "from:amy launch",
    "label:mailweave",
)


@pytest.mark.parametrize("query", WIDENING_SPELLINGS)
def test_the_same_operator_with_punctuation_or_normalisation_around_it_is_flagged(
    query: str,
) -> None:
    """R-SEC-058's shapes. These are not a different intent; they are the same operator."""
    assert widens(query) is True


@pytest.mark.parametrize("query", NOT_WIDENING)
def test_a_narrowing_or_unrelated_query_is_still_not_flagged(query: str) -> None:
    """The strip and the normalisation can only refuse a disagreeing pair, never allow one.

    Asserted, because a strip is exactly the kind of change that quietly turns `-in:spam` into
    `in:spam`. The leading `-` and the phrase-search quotes are deliberately not stripped.
    """
    assert widens(query) is False


def test_the_residue_the_docstring_now_names_is_the_residue_that_exists() -> None:
    """A zero-width space *inside* the operator survives NFKC and is not seen.

    Named in the docstring as a residue rather than closed, and pinned here so the sentence
    cannot become an overstatement. Stripping format characters from a query is a different
    decision from stripping them from mail content, and it is not this round's to make.
    """
    assert widens("in​:anywhere") is False
    assert widens("label:spam") is False


# --- R-SEC-059 ---------------------------------------------------------------------------------


def test_the_seed_address_is_a_callers_parameter_with_no_configuration_binding() -> None:
    """The residue, asserted so the note in `pinning.py` describes something real.

    Not a fix: binding this to a config field for a caller that does not exist would be
    guessing at WS-16's shape. What is pinned is the two facts the note rests on - the
    parameter has no default and no config source, and the one related config field is a hash
    that cannot be fed to a plaintext comparison - so a later round can act on it and this test
    fails the day somebody closes it, which is the prompt to delete the note.
    """
    signature = inspect.signature(verify_seed_account)
    seed_address = signature.parameters["seed_address"]
    assert seed_address.default is inspect.Parameter.empty
    assert signature.parameters["scopes"].default == SEEDER_SCOPES

    assert "seed_address" not in MailweaveConfig.model_fields
    assert "seed_account_hash" in MailweaveConfig.model_fields

    source = inspect.getsource(verify_seed_account)
    assert "MailweaveConfig" not in source, (
        "verify_seed_account now reads configuration; R-SEC-059's residue note in pinning.py "
        "describes a gap that no longer exists and should be replaced by what closed it"
    )
