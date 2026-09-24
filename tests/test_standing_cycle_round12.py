"""The standing check, round 12: three more shapes, one per fix this round made structural.

`tests/test_standing_cycle_round11.py` guards three idioms that had each been written twice.
This file guards four *couplings* - places where two things must agree and nothing made them
agree - which is the same defect one level up, and the shape the work order's standing check
asks about:

  * a model that holds a secret must be one whose validation failures cannot quote it
    (R-SEC-043). The check is by reflection over both trees, so a model added later is
    covered without editing anything here;
  * a `ValidationError` must be rendered through `validation.failure_summary` and nowhere
    else. Pydantic's own rendering quotes the input, which is a secret in one layer and mail
    text in another, and the fix is only as good as its last call site;
  * `messages.list`'s two ways of naming a mailbox scope - the `includeSpamTrash` parameter
    and the `in:` operator in `q` - may not be supplied independently (part 6). Neither may
    be written as a literal at a call site; both come off one `MailboxScope`;
  * a mint proof must be verified somewhere a *use site* reaches, not only in the constructor
    (part 3b). `__init__` is one of several ways an object appears, and the other ways were
    trusted - which is the eighth instance of this pattern, found inside the fix for the
    seventh.

They are deliberately narrow, for the reason round 11 gave: a guard that reports innocent
code is a guard that gets switched off. Each is shown firing against a planted instance at
the bottom of the file, because a sweep that has never fired is a sweep nobody has tested.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import BaseModel, SecretStr

from mailweave.constants import WIDENING_MAILBOX_OPERATORS
from mailweave.validation import SecretBearingModel
from mailweave_harness.preflight.scope import MailboxScope
from tests.fixtures.secret_models import models_with_secrets, secret_fields
from tests.fixtures.source_trees import parsed, source_files

#: The one module allowed to render a `ValidationError`, and the one allowed to spell a scope.
#:
#: **The scope home moved in round 13** (R-SEC-051). The operators are Gmail vocabulary and
#: the *server* needs them too now - `GmailClient._fetch_list_page` refuses a query and a flag
#: that disagree at the point the request is built, which is the only place they meet and the
#: only check an f-string or a concatenation cannot walk past. So they are written once, in
#: the module both trees already import for Gmail's other shapes, and `MailboxScope` composes
#: its two spellings out of them rather than restating them.
RENDERER_HOME = "mailweave/validation.py"
SCOPE_HOME = "mailweave/constants.py"


# --- shape 1: a model that holds a secret is a model that cannot quote it --------------------


def test_every_model_that_declares_a_secret_cannot_render_its_input() -> None:
    """R-SEC-043 was one field of one model, and the fix is only as wide as its last subclass.

    Discovered rather than listed: `tests.fixtures.secret_models` imports both trees and asks
    every Pydantic model whether any field annotation mentions `SecretStr`. A model added in
    a later round is in this sweep the moment it exists.
    """
    offenders = [
        f"{model.__module__}.{model.__qualname__} (fields {', '.join(secret_fields(model))})"
        for model in models_with_secrets()
        if not issubclass(model, SecretBearingModel)
    ]
    assert offenders == [], (
        f"a model declares a SecretStr without inheriting SecretBearingModel: {offenders}. "
        "Pydantic's default report quotes the input it refused, which for these models is a "
        "credential (R-SEC-043)."
    )


def test_the_secret_model_sweep_would_catch_a_planted_model() -> None:
    """The sweep asserts an empty result; this shows the search is not itself empty."""

    class PlainSecretModel(BaseModel):
        token: SecretStr

    assert secret_fields(PlainSecretModel) == ("token",)
    assert not issubclass(PlainSecretModel, SecretBearingModel)


# --- shape 2: one renderer for a validation failure ------------------------------------------


def _validation_error_handlers(tree: ast.Module) -> list[ast.ExceptHandler]:
    handlers: list[ast.ExceptHandler] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler) or node.type is None:
            continue
        names = {
            item.id if isinstance(item, ast.Name) else getattr(item, "attr", "")
            for item in ast.walk(node.type)
            if isinstance(item, ast.Name | ast.Attribute)
        }
        if "ValidationError" in names:
            handlers.append(node)
    return handlers


def _renders_the_failure(handler: ast.ExceptHandler) -> list[int]:
    """Lines where the caught failure is used for anything but the permitted three.

    Permitted: `raise X(...) from failure` (chaining the object, not its text),
    `failure.error_count()` (a number), and `failure_summary(model, failure)` (the one
    renderer). Everything else - an f-string, `str(...)`, `.errors()`, `.json()` - can put
    Pydantic's own report, and therefore the input it refused, into a message.
    """
    caught = handler.name
    if caught is None:
        return []
    parents = _parents(handler)
    offending: list[int] = []
    for node in ast.walk(handler):
        if not (isinstance(node, ast.Name) and node.id == caught):
            continue
        owner = parents.get(id(node))
        if isinstance(owner, ast.Raise):
            continue
        if (
            isinstance(owner, ast.Call)
            and isinstance(owner.func, ast.Name)
            and owner.func.id == "failure_summary"
        ):
            continue
        if isinstance(owner, ast.Attribute) and owner.attr == "error_count":
            continue
        offending.append(node.lineno)
    return offending


def _parents(root: ast.AST) -> dict[int, ast.AST]:
    found: dict[int, ast.AST] = {}
    for node in ast.walk(root):
        for child in ast.iter_child_nodes(node):
            found[id(child)] = node
    return found


def test_no_module_renders_a_validation_error_any_other_way() -> None:
    """The R-SEC-043 shape as a coupling: one renderer, or as many leaks as call sites.

    `TokenStore.load()` interpolated the caught `ValidationError` straight into its message,
    and that is the whole finding. The renderer that does not quote values exists
    (`validation.failure_summary`); what makes it worth anything is that it is the only one.
    """
    offenders: list[str] = []
    for path in source_files(excluding=RENDERER_HOME):
        for handler in _validation_error_handlers(parsed(path)):
            offenders.extend(f"{path}:{line}" for line in _renders_the_failure(handler))
    assert offenders == [], (
        f"a caught ValidationError is used for something other than chaining, counting or "
        f"`failure_summary`: {offenders}. Pydantic's report quotes the input it refused."
    )


# --- shape 3: the two spellings of a mailbox scope --------------------------------------------

#: The `in:` operators that name where `messages.list` looks, **imported from the module that
#: defines them** rather than restated. A sweep that carried its own copy of the vocabulary
#: would stop matching the day an operator is added, in the file whose subject is second
#: copies - which is R-SEC-053's finding one shape over.
_SCOPE_OPERATORS = WIDENING_MAILBOX_OPERATORS


def test_no_module_spells_a_mailbox_scope_operator_outside_the_scope_enum() -> None:
    """Part 6: the `q` half of the pair, written where it cannot be paired with the other."""
    offenders: list[str] = []
    for path in source_files(excluding=SCOPE_HOME):
        for node in ast.walk(parsed(path)):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and any(operator in node.value for operator in _SCOPE_OPERATORS)
            ):
                offenders.append(f"{path}:{node.lineno}")
    assert offenders == [], (
        f"a module writes its own spam/trash scope operator: {offenders}. There is one place "
        "the two spellings are written, `preflight/scope.py`, and it writes them together."
    )


def _scope_argument_pairs(tree: ast.Module) -> list[tuple[int, str]]:
    """Every call passing `include_spam_trash`, with what is wrong about it, if anything."""
    problems: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        keywords = {item.arg: item.value for item in node.keywords if item.arg}
        flag = keywords.get("include_spam_trash")
        if flag is None:
            continue
        if isinstance(flag, ast.Name) and flag.id == "include_spam_trash":
            # Pure forwarding: `include_spam_trash=include_spam_trash`, which is what the
            # Gmail client does down its own call chain. It decides nothing - the value came
            # from its own parameter, and whoever supplied *that* is checked here too.
            continue
        if not (isinstance(flag, ast.Attribute) and flag.attr == "include_spam_trash"):
            problems.append((node.lineno, "include_spam_trash is neither a scope's nor forwarded"))
            continue
        receiver = ast.unparse(flag.value)
        query = keywords.get("query")
        if query is None:
            problems.append((node.lineno, "a scope's flag travels without its query"))
        elif ast.unparse(query) != f"{receiver}.query":
            problems.append((node.lineno, "the query comes from somewhere else than the flag"))
    return problems


def test_the_two_scope_settings_cannot_be_supplied_independently() -> None:
    """The coupling itself: `includeSpamTrash` may only be read off the scope its `q` came from.

    `include_spam_trash=True` written at a call site is refused outright, whatever query sits
    beside it - which is what makes the pairing structural rather than a docstring's promise.
    """
    offenders: list[str] = []
    for path in source_files():
        offenders.extend(
            f"{path}:{line}: {why}" for line, why in _scope_argument_pairs(parsed(path))
        )
    assert offenders == [], (
        f"a call supplies the two mailbox-scope settings separately: {offenders}. They come "
        "off one `MailboxScope`, together, or a probe samples a mailbox neither describes."
    )


def test_both_scopes_declare_both_spellings_and_they_do_not_collide() -> None:
    """One value per scope, and the two scopes really are two different mailboxes."""
    assert {scope.query for scope in MailboxScope} == {"in:anywhere", "-in:spam -in:trash"}
    assert {scope.include_spam_trash for scope in MailboxScope} == {True, False}
    assert len({(scope.query, scope.include_spam_trash) for scope in MailboxScope}) == len(
        list(MailboxScope)
    )


# --- shape 4: a proof checked only at construction is a proof with no chokepoint -------------

#: The module that mints and verifies seed sessions, and the comparison that does the
#: verifying. Scoped to one module and one call on purpose: this is a guard on a specific
#: chokepoint, not a general rule about `__post_init__`, of which this codebase has several
#: that are honestly constructor-only.
PINNING_HOME = Path("harness/src/mailweave_harness/pinning.py")
_PROOF_COMPARISON = "compare_digest"


def methods_verifying_the_proof(tree: ast.Module) -> set[str]:
    """Names of the methods whose body compares a mint proof."""
    verifying: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute | ast.Name)
                and _PROOF_COMPARISON in ast.unparse(inner.func)
            ):
                verifying.add(node.name)
    return verifying


def test_the_seed_session_proof_is_verified_somewhere_other_than_its_constructor() -> None:
    """Part 3b, as the standing shape: `__init__` is not the only way an object appears.

    `SeedSession` verified its proof in `__post_init__` and nowhere else, and `copy.copy`,
    `copy.deepcopy` and `pickle` all restore `__dict__` without running it - so a session
    tampered with `object.__setattr__` and then copied authorised the credential that can
    permanently delete mail. That is the eighth instance of this project's recurring defect
    and it appeared *inside* the fix for the seventh: `dataclasses.replace` was defended and
    its peers `__reduce_ex__`, `__copy__` and `__deepcopy__` were trusted.

    The fix was not to name those three - Python is free to ship a fourth - but to verify at
    the point of use, so no construction path matters. This sweep is what keeps the check
    there: it fails if the only verification is back inside construction, which is the state
    every behavioural test on the `__init__` path would still be green in.
    """
    verifying = methods_verifying_the_proof(parsed(PINNING_HOME))

    assert verifying, "nothing in pinning.py compares a mint proof at all"
    assert verifying - {"__post_init__", "__init__"}, (
        f"the seed session's proof is verified only at construction ({sorted(verifying)}). "
        "copy, deepcopy and pickle rebuild an instance without running __post_init__, so a "
        "check that only runs there is a check a rebuilt session skips."
    )


# --- each sweep, fired against a planted instance ---------------------------------------------


PLANTED = {
    "renderer": (
        "from pydantic import ValidationError\n"
        "def load(raw: object) -> None:\n"
        "    try:\n"
        "        Model.model_validate(raw)\n"
        "    except ValidationError as failure:\n"
        '        raise RuntimeError(f"malformed: {failure}") from failure\n'
    ),
    "operator": 'QUERY = "in:anywhere"\n',
    "pair": "def walk() -> None:\n    client.list_messages(q, include_spam_trash=True)\n",
    "constructor_only_proof": (
        "import hmac\n"
        "class Session:\n"
        "    def __post_init__(self) -> None:\n"
        "        if not hmac.compare_digest(self.proof, mint(self.address)):\n"
        "            raise Mismatch\n"
        "    def assert_bound_to(self, credential: object) -> None:\n"
        "        if credential is not self.credential:\n"
        "            raise Mismatch\n"
    ),
    "split_pair": (
        "def walk(scope: object, other: object) -> None:\n"
        "    client.list_messages(query=other.query, include_spam_trash=scope.include_spam_trash)\n"
    ),
}


@pytest.mark.parametrize("planted", sorted(PLANTED))
def test_the_sweeps_would_actually_catch_a_planted_instance(tmp_path: Path, planted: str) -> None:
    """A guard that has never been shown to fire is a guard nobody has tested."""
    path = tmp_path / f"{planted}.py"
    path.write_text(PLANTED[planted], encoding="utf-8")
    tree = parsed(path)

    if planted == "constructor_only_proof":
        verifying = methods_verifying_the_proof(tree)
        assert verifying == {"__post_init__"}, verifying
        return
    if planted == "renderer":
        found = [
            line
            for handler in _validation_error_handlers(tree)
            for line in _renders_the_failure(handler)
        ]
    elif planted == "operator":
        found = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and any(operator in node.value for operator in _SCOPE_OPERATORS)
        ]
    else:
        found = [line for line, _ in _scope_argument_pairs(tree)]

    assert len(found) == 1, f"the {planted} sweep found {found} in its own planted instance"
