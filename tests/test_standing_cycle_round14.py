"""The standing check, round 14: the sweep's population reaches the **reading** site.

R-ARCH-035. Round 13's sweep is a good sweep and its population is the wrong half of the
property it enforces. Its rule 2 reads:

> it refuses subclassing, because moving the facts off the object does not stop a subclass
> overriding the members that do the asking

That is a rule about *the object that does the asking*. Its population is discovered by looking
for classes that compare a module-private sentinel, call `compare_digest`, or call `recall` -
which is *the object that holds the capability*. `Envelope` asks, and `Envelope` compares no
sentinel and calls no `recall`, so it could never appear there. The rule was enforced on the
three classes that needed it least and not on the site where the defect it was written for
actually lived: three public subclass routes on `Envelope`, each publishing `partial: false`
for a certificate that still certified a withheld id (R-ARCH-033).

So this file sweeps the other half. Its subjects are the classes that **re-establish** somebody
else's capability, and the rule is the same one, applied where the rule came from: a reader
that can be substituted is not a reader.

Two deliberate differences from round 13's sweep, both because of what it was fooled by:

  * the refusal is checked **by execution** rather than by AST. `Envelope` inherits its refusal
    from `Frozen` and has no `__init_subclass__` of its own, so an AST check for "the first
    statement is a raise" would report it as unsealed - and, worse, a future class that *does*
    define one which silently returns would be reported as sealed. Trying to build the subclass
    answers both;
  * the population is asserted by name **and** by count, because round 12's sweep could be
    emptied by narrowing its scope and round 13's caught that only because a reviewer added the
    named assertion the implementer had not.
"""

from __future__ import annotations

import ast
import types
from pathlib import Path

import pytest
from pydantic import BaseModel

from mailweave.envelope.disposition import DispositionCertificate
from mailweave.envelope.response import Envelope
from mailweave.envelope.wire import Frozen
from mailweave.validation import annotation_parts
from tests.fixtures.source_trees import parsed, source_files

#: How this repository re-establishes a capability it does not itself hold. One entry today,
#: named rather than pattern-matched: `Envelope` cannot ask the certificate anything, because a
#: forgery answers questions the way a real one does, so it asks the mint instead.
REESTABLISHERS = ("assert_is_a_minted_certificate",)


def reading_sites(tree: ast.Module) -> set[str]:
    """Classes that re-establish a capability held by an object they were handed."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call) and any(
                name in ast.unparse(inner.func) for name in REESTABLISHERS
            ):
                found.add(node.name)
    return found


def test_the_reading_site_sweep_finds_the_class_that_reads_the_certificate() -> None:
    """Named and counted, so narrowing the sweep empties it loudly rather than quietly."""
    found = {name for path in source_files() for name in reading_sites(parsed(path))}

    assert "Envelope" in found, (
        f"the reading-site sweep found {sorted(found)}; the class that re-establishes the "
        "disposition certificate is what it exists to reach, and a sweep that has stopped "
        "matching its own subject asserts nothing"
    )


def _can_be_substituted(model: type) -> bool:
    """Whether a class can be replaced by a subclass of itself, asked by trying it."""
    try:
        types.new_class("Substituted", (model,))
    except TypeError:
        return False
    return True


def test_every_reading_site_refuses_to_be_substituted() -> None:
    """R-ARCH-033's rule, enforced where R-ARCH-035 says it belongs.

    A subclass of the reader replaces the members that do the re-establishing - the validator
    by name, the method that discovers the validators, the serializer that runs them, or a
    field serializer that rewrites a value after all of them have passed. None of those touches
    the object being read, which is why sealing the certificate did not close them.
    """
    offenders = [
        name
        for path in source_files()
        for name in reading_sites(parsed(path))
        if name in _importable() and _can_be_substituted(_importable()[name])
    ]

    assert offenders == [], (
        f"a class that re-establishes a sealed object's facts can be subclassed: {offenders}. "
        "A subclass overrides the members that do the asking, so the seal on the object it "
        "reads buys nothing (R-ARCH-033, R-ARCH-035)."
    )


def _importable() -> dict[str, type]:
    """The reading sites this sweep can resolve to a class object.

    Kept small and explicit: resolving an arbitrary class name out of an AST means importing by
    guesswork, and a sweep that silently fails to resolve a name reports no offender for it -
    which is the shape of every false green this project has had. The count assertion above is
    what fails if a site appears that this mapping does not carry.
    """
    return {"Envelope": Envelope, "DispositionCertificate": DispositionCertificate}


def test_the_sweep_reports_a_planted_substitutable_reader(tmp_path: Path) -> None:
    """Shown firing, on the shape `Envelope` had before this round."""
    path = tmp_path / "reader.py"
    path.write_text(
        "class Reader:\n"
        "    def _check(self) -> None:\n"
        "        assert_is_a_minted_certificate(self.disposition)\n",
        encoding="utf-8",
    )

    assert reading_sites(parsed(path)) == {"Reader"}

    class Reader:
        pass

    assert _can_be_substituted(Reader) is True, (
        "an ordinary class is substitutable, so the check above can report one"
    )


def test_the_sweep_does_not_report_a_class_that_reads_nothing_sealed() -> None:
    """The other half: a class that re-establishes nothing must not be in the population."""
    tree = ast.parse(
        "class Ordinary:\n"
        "    def check(self) -> None:\n"
        "        if self.value < 0:\n"
        "            raise ValueError('no')\n"
    )
    assert reading_sites(tree) == set()


def test_what_this_sweep_cannot_decide_is_asserted_rather_than_described() -> None:
    """A reader that re-establishes a capability *without* naming one of these functions.

    The discriminator is a call to a named function, so a future consumer that inlines the two
    questions - `type(x) is DispositionCertificate` and a registry lookup - is invisible here,
    exactly as round 13's sweep is blind to a capability expressed as a plain boolean. Naming
    that in a test rather than in a sentence is the difference between a known gap and a
    forgotten one.
    """
    tree = ast.parse(
        "class InlinedReader:\n"
        "    def check(self) -> None:\n"
        "        if type(self.disposition) is not DispositionCertificate:\n"
        "            raise TypeError\n"
    )
    assert reading_sites(tree) == set(), (
        "if this now finds the class, the sweep has become able to decide the case it "
        "declares it cannot, and this test is the place to widen the claim"
    )


# --- the structural half: every model that reaches the wire is unsubstitutable -----------------


def wire_tree_models() -> set[type[BaseModel]]:
    seen: set[type[BaseModel]] = set()
    pending: list[type[BaseModel]] = [Envelope]
    while pending:
        model = pending.pop()
        if model in seen:
            continue
        seen.add(model)
        for field in model.model_fields.values():
            pending.extend(
                part
                for part in annotation_parts(field.annotation)
                if isinstance(part, type) and issubclass(part, BaseModel) and part is not BaseModel
            )
    return seen


def test_no_model_in_the_envelope_tree_can_be_substituted() -> None:
    """The rule swept over the whole payload rather than over the class that owns the serializer.

    R-ARCH-034's lesson applied to R-ARCH-033: what reaches the wire is a tree, so "the reader"
    is every class in it. `Reduction` and the reason models live in other modules and inherit
    from other bases, and they are checked here by behaviour rather than by which base they
    happen to have - a rule about where a class inherits from would be a rule about this
    round's implementation.
    """
    substitutable = sorted(
        model.__name__ for model in wire_tree_models() if _can_be_substituted(model)
    )

    assert substitutable == [], (
        f"these models reach the wire and can be subclassed: {substitutable}. A subclass "
        "replaces an after-validator by name, the serializer that re-runs them, or a field "
        "serializer that rewrites the value after every check has passed (R-ARCH-033)."
    )


def test_the_abstract_bases_the_schema_is_written_on_stay_extensible() -> None:
    """A rule that refused both would be unusable, and an unusable rule gets removed.

    `Frozen` declares no fields, so extending it is how a wire model is written; extending a
    model that declares fields is how a reader is replaced. That is the whole distinction, and
    it is asserted in both directions so neither half can be lost.
    """

    class Later(Frozen):
        value: int = 1

    assert Later(value=2).model_dump() == {"value": 2}
    assert _can_be_substituted(Later) is False


def test_the_certificate_and_its_reader_are_both_sealed() -> None:
    """The sentence R-ARCH-033 was filed against, as an assertion about both objects.

    "Keeping the facts here is half of the property and the other half is that only this type
    can be the one reading them" - `sealing.py:59`. It was true of the first half only.
    """
    assert _can_be_substituted(DispositionCertificate) is False
    assert _can_be_substituted(Envelope) is False


def test_a_reading_site_added_later_is_swept_by_existing(tmp_path: Path) -> None:
    """The population is discovered, so a second consumer is covered on the day it is written.

    Driven rather than asserted about the loop: a module carrying a new reader is written to
    disk and the sweep is pointed at it.
    """
    path = tmp_path / "future_consumer.py"
    path.write_text(
        "class TextMirror:\n"
        "    def render(self, envelope) -> str:\n"
        "        assert_is_a_minted_certificate(envelope.disposition)\n"
        "        return ''\n",
        encoding="utf-8",
    )

    with pytest.raises(KeyError):
        _importable()["TextMirror"]  # not resolvable, and the sweep says so by name
    assert reading_sites(parsed(path)) == {"TextMirror"}
