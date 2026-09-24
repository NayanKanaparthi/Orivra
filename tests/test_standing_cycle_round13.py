"""The standing check, round 13: the sweep re-scoped to what it is actually about.

Round 12 added a sweep for one chokepoint - "the seed session's proof must be verified
somewhere other than its constructor" - scoped to `pinning.py` on the argument that a general
rule ("an invariant established at construction must be re-established at use") would flag the
codebase's several honestly constructor-only `__post_init__` validators and get switched off.

R-SEC judged that an argument against a rule nobody proposed, and was right. The category is
not `__post_init__` validators; it is **capability tokens** - objects whose existence
authorises something - and a sweep scoped to those flags exactly three sites in this
repository, of which one was not innocent: `DispositionCertificate` had the identical defect,
in the server tree, in the seal invariant I-1 rests on (R-SEC-046).

So the sweep below is scoped to capability tokens, which is a decidable category here because
this repository mints them in exactly two idioms and both are visible in the source:

  * a **module-private sentinel** compared with `is` (`_MINT_TOKEN`, `_RECORD_TOKEN`);
  * a **keyed proof** compared with `hmac.compare_digest` (`_MINT_KEY`).

Every class that does either must re-establish the capability somewhere a *use site* reaches -
by comparing the token again outside construction, or by reading its facts out of a
`mailweave.sealing.IdentityRegistry`, which is the same property with nothing left on the
object to check. What the sweep cannot decide is named in
`test_the_capability_sweep_states_what_it_cannot_decide` rather than left for a reviewer.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.fixtures.source_trees import parsed, source_files

#: The names a mint compares. Both idioms this repository uses, and nothing else: a sweep that
#: guessed at "anything that looks like a token" would report innocent code, which is round
#: 11's stated reason for keeping these narrow.
_TOKEN_COMPARISONS = ("compare_digest",)

#: How a capability is re-established without comparing anything: the facts live in the
#: registry and the object holds none of them, so reading them *is* the check.
_SEAL_LOOKUPS = ("recall",)

#: Where construction happens. A check here is an early failure, never the guarantee.
_CONSTRUCTORS = frozenset({"__init__", "__post_init__", "__new__"})


def _private_sentinels(tree: ast.Module) -> set[str]:
    """Module-private names bound to a bare `object()`: this repository's mint tokens."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        if not (isinstance(node.value.func, ast.Name) and node.value.func.id == "object"):
            continue
        found.update(
            target.id
            for target in node.targets
            if isinstance(target, ast.Name) and target.id.startswith("_")
        )
    return found


def _checks_a_capability(body: ast.AST, sentinels: set[str]) -> bool:
    """Whether this code compares a mint token, or reads facts out of a seal registry."""
    for node in ast.walk(body):
        if isinstance(node, ast.Compare) and any(
            isinstance(operator, ast.Is | ast.IsNot) for operator in node.ops
        ):
            names = {
                item.id
                for item in ast.walk(node)
                if isinstance(item, ast.Name) and item.id in sentinels
            }
            if names:
                return True
        if isinstance(node, ast.Call):
            spelled = ast.unparse(node.func)
            if any(name in spelled for name in (*_TOKEN_COMPARISONS, *_SEAL_LOOKUPS)):
                return True
    return False


def capability_classes(tree: ast.Module) -> dict[str, tuple[set[str], set[str]]]:
    """Classes that check a capability, and where: `{name: (constructors, use sites)}`.

    A class appears here only if something in it checks a capability at all, so an ordinary
    class - and an honestly constructor-only validator like `ProbeSpec`, which checks its own
    fields and no token - is not in the result and cannot be flagged by the test below.
    """
    sentinels = _private_sentinels(tree)
    found: dict[str, tuple[set[str], set[str]]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        constructors: set[str] = set()
        use_sites: set[str] = set()
        for member in node.body:
            if not isinstance(member, ast.FunctionDef):
                continue
            if not _checks_a_capability(member, sentinels):
                continue
            (constructors if member.name in _CONSTRUCTORS else use_sites).add(member.name)
        if constructors or use_sites:
            found[node.name] = (constructors, use_sites)
    return found


def test_every_capability_token_is_re_established_at_a_use_site() -> None:
    """The round-12 sweep, re-scoped from one module to the category it was about.

    R-SEC-039, round 12's part 3b and R-SEC-046 are one defect: a capability checked where the
    object is *built*, in a language with several ways to build one. `copy.copy`, `pickle`,
    `__reduce_ex__` and `object.__new__` all produce an instance whose `__init__` never ran,
    so a constructor-only check is a check every rebuild skips.

    A class that mints a capability must therefore also check it somewhere a caller reaches.
    Both ways of doing that count, because they establish the same thing: comparing the token
    again outside construction, and reading the object's facts out of the seal registry - the
    second is stronger, since it leaves nothing on the object for a copy to carry.
    """
    offenders: list[str] = []
    swept: list[str] = []
    for path in source_files():
        for name, (constructors, use_sites) in capability_classes(parsed(path)).items():
            swept.append(f"{path}:{name}")
            if constructors and not use_sites:
                offenders.append(f"{path}:{name} (only {sorted(constructors)})")

    assert offenders == [], (
        f"a capability is checked only at construction: {offenders}. __init__ is one of "
        "several ways an object appears; copy, deepcopy, pickle and __reduce_ex__ each "
        "produce one without running it (R-SEC-039, R-SEC-046)."
    )
    assert len(swept) >= 3, (
        f"the capability sweep found only {swept}; it is supposed to reach the seed session, "
        "the fetched-page seal and the disposition certificate, and a sweep that has stopped "
        "matching its own subjects asserts nothing"
    )


def test_the_capability_sweep_reaches_the_three_sites_it_is_about() -> None:
    """Named, so that a rename or a move fails here rather than silently emptying the sweep."""
    found = {name for path in source_files() for name in capability_classes(parsed(path))}
    assert {"SeedSession", "FetchedIds", "DispositionCertificate"} <= found, found


def _refuses_subclassing(tree: ast.Module, class_name: str) -> bool:
    """Whether the named class has an `__init_subclass__` whose **first act** is to raise.

    "Contains a `raise` somewhere" is not the property, and this test knows that by having
    been fooled: the round-13 reintroduction battery disabled the refusal by inserting
    `return None` *above* the `raise`, and an any-`Raise`-node check called that a refusal.
    The first statement after any docstring must be the `raise`, which is decidable and is
    the shape all three of these are written in.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for member in node.body:
            if not (isinstance(member, ast.FunctionDef) and member.name == "__init_subclass__"):
                continue
            body = [
                statement
                for statement in member.body
                if not (
                    isinstance(statement, ast.Expr)
                    and isinstance(statement.value, ast.Constant)
                    and isinstance(statement.value.value, str)
                )
            ]
            return bool(body) and isinstance(body[0], ast.Raise)
    return False


def test_every_capability_token_also_refuses_subclassing() -> None:
    """The half of the property that moving the facts into the registry does **not** buy.

    Round 13 moved `DispositionCertificate`'s facts into a `mailweave.sealing`
    `IdentityRegistry`, which closes every route that *rebuilds* the object - and closes none
    that **replaces the reader**. A subclass overriding `withheld` and `withheld_ids` never
    consults the registry, so nothing raises, and `Envelope`'s field is an `isinstance` check
    a subclass passes: the implementer built exactly that forgery against its own fix and the
    envelope serialised `withheld: []` for a response missing a message.

    This is R-RETR's round-3 attack 8 - defeat a mint token by subclassing rather than by
    reaching for it - which `SeedSession` has refused since round 12 while its two peers in
    the same category did not. So the rule is swept rather than remembered: a class that
    checks a capability token may not be subclassed, with no exceptions to keep a list of.

    What it is worth differs by site, and the sweep does not pretend otherwise: for the
    certificate and the session it closes the last ordinary forgery; for `FetchedIds` it stops
    the one-shot latch being overridden and leaves amendment A1's over-recording residue
    exactly where A1 puts it, because that constructor is public by design.
    """
    offenders: list[str] = []
    for path in source_files():
        tree = parsed(path)
        offenders.extend(
            f"{path}:{name}"
            for name in capability_classes(tree)
            if not _refuses_subclassing(tree, name)
        )

    assert offenders == [], (
        f"a capability class can be subclassed: {offenders}. A subclass overrides the members "
        "that do the checking, so neither the token nor the seal registry is ever consulted "
        "(R-RETR round 3 attack 8; found live against DispositionCertificate in round 13)."
    )


def test_the_subclassing_sweep_catches_a_planted_instance(tmp_path: Path) -> None:
    """Shown firing, on the exact shape the certificate had before this round."""
    path = tmp_path / "unsealed.py"
    path.write_text(
        "_MINT = object()\n"
        "class Certificate:\n"
        "    def __init__(self, token: object) -> None:\n"
        "        if token is not _MINT:\n"
        "            raise RuntimeError\n"
        "    @property\n"
        "    def withheld(self) -> tuple[str, ...]:\n"
        "        return _CERTIFIED.recall(self).withheld\n",
        encoding="utf-8",
    )
    tree = parsed(path)

    assert "Certificate" in capability_classes(tree)
    assert not _refuses_subclassing(tree, "Certificate")


def test_the_subclassing_sweep_accepts_a_class_that_refuses() -> None:
    """The other half: a class that does refuse must not be reported."""
    tree = ast.parse(
        "class Certificate:\n"
        "    def __init_subclass__(cls, **kwargs: object) -> None:\n"
        '        """A docstring is allowed before the raise."""\n'
        "        raise TypeError('no')\n"
        "    @property\n"
        "    def withheld(self) -> tuple[str, ...]:\n"
        "        return _CERTIFIED.recall(self).withheld\n"
    )

    assert "Certificate" in capability_classes(tree)
    assert _refuses_subclassing(tree, "Certificate")


def test_a_refusal_that_returns_before_it_raises_is_not_a_refusal() -> None:
    """The exact shape that fooled this sweep once, kept as the case that must stay caught.

    The reintroduction battery disabled `DispositionCertificate.__init_subclass__` by putting
    `return None` above the `raise` and the sweep reported the class as still refusing, so the
    battery's own result said "not caught" for a defect that was genuinely reintroduced. That
    is the sweep failing in the direction that matters, and it is why the check is on the first
    statement rather than on whether a `raise` appears anywhere in the method.
    """
    tree = ast.parse(
        "class Certificate:\n"
        "    def __init_subclass__(cls, **kwargs: object) -> None:\n"
        "        return None\n"
        "        raise TypeError('unreachable')\n"
    )

    assert not _refuses_subclassing(tree, "Certificate")


PLANTED = {
    "constructor_only_token": (
        "_MINT = object()\n"
        "class Certificate:\n"
        "    def __init__(self, token: object) -> None:\n"
        "        if token is not _MINT:\n"
        "            raise RuntimeError\n"
        "    @property\n"
        "    def hit_count(self) -> int:\n"
        "        return self._hit_count\n"
    ),
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
}

INNOCENT = {
    "a constructor-only field validator": (
        "class ProbeSpec:\n"
        "    def __post_init__(self) -> None:\n"
        "        if not self.title:\n"
        "            raise ValueError\n"
    ),
    "a use-site token check": (
        "_RECORD = object()\n"
        "class Page:\n"
        "    def _release(self, token: object) -> tuple[str, ...]:\n"
        "        if token is not _RECORD:\n"
        "            raise RuntimeError\n"
        "        return self._ids\n"
    ),
    "facts read out of a registry": (
        "class Certificate:\n"
        "    def __init__(self, token: object) -> None:\n"
        "        if token is not _MINT:\n"
        "            raise RuntimeError\n"
        "    @property\n"
        "    def _certified(self) -> object:\n"
        "        return _CERTIFIED.recall(self)\n"
    ),
}


@pytest.mark.parametrize("planted", sorted(PLANTED))
def test_the_capability_sweep_catches_a_planted_instance(tmp_path: Path, planted: str) -> None:
    """A guard that has never been shown to fire is a guard nobody has tested."""
    path = tmp_path / f"{planted}.py"
    path.write_text(PLANTED[planted], encoding="utf-8")

    classes = capability_classes(parsed(path))

    assert classes, f"the sweep did not even see the planted {planted}"
    for constructors, use_sites in classes.values():
        assert constructors and not use_sites


@pytest.mark.parametrize("innocent", sorted(INNOCENT))
def test_the_capability_sweep_does_not_report_innocent_code(tmp_path: Path, innocent: str) -> None:
    """The other half of round 11's rule: a sweep that reports innocent code gets switched off.

    `ProbeSpec` is the case round 12 named when it declined to widen the sweep, and it is
    genuinely innocent: it validates its own fields at construction and checks no capability at
    all, so it is not in the sweep's population rather than being excused from it.
    """
    path = tmp_path / "innocent.py"
    path.write_text(INNOCENT[innocent], encoding="utf-8")

    for constructors, use_sites in capability_classes(parsed(path)).values():
        assert not constructors or use_sites, innocent


def test_the_capability_sweep_states_what_it_cannot_decide() -> None:
    """The sweep's own limits, asserted so they are read rather than assumed.

    It reads two idioms: a module-private sentinel compared with `is`, and a
    `compare_digest`/`recall` call. A capability minted some third way is outside it, and this
    test says so by planting one and showing the sweep does *not* see it. That is a real gap
    and it is stated here rather than left for a reviewer to find - the alternative, a sweep
    that guesses at what looks like a token, is the one that reports innocent code.
    """
    tree = ast.parse(
        "class Ticket:\n"
        "    def __init__(self, granted: bool) -> None:\n"
        "        if not granted:\n"
        "            raise RuntimeError('not granted')\n"
    )

    assert capability_classes(tree) == {}, (
        "the sweep now sees a capability expressed as a plain boolean; if that is deliberate "
        "the docstring above needs to say so, and if it is not, this test has stopped "
        "describing the sweep"
    )


# --- R-SEC-050's third shape: a model reflection cannot reach ---------------------------------


def test_no_model_is_defined_where_reflection_cannot_find_it() -> None:
    """The secret canary discovers models by walking namespaces; a local class is in none.

    `tests/fixtures/secret_models.py` imports both trees and asks every class whether it
    declares a secret. Round 13 widened that to nested classes, which are reachable through
    their enclosing class's namespace. A class defined **inside a function** is reachable
    through nothing until the function runs, so no reflection can cover it - and R-SEC drove
    exactly that shape to a `ValidationError` quoting a planted secret in full.

    It cannot be fixed by discovery, so it is fixed by refusal: neither source tree may define
    a class inside a function. Nothing in either tree does today, which makes this a rule that
    costs nothing to keep and closes the one shape the canary cannot see. If a future round
    needs a factory-built model, the honest move is to hoist the class to module level, not to
    delete this test.
    """
    offenders: list[str] = []
    for path in source_files():
        for node in ast.walk(parsed(path)):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            offenders.extend(
                f"{path}:{inner.lineno}: class {inner.name} inside {node.name}"
                for inner in ast.walk(node)
                if isinstance(inner, ast.ClassDef)
            )
    assert offenders == [], (
        f"a class is defined inside a function: {offenders}. It is in no namespace until the "
        "function runs, so the secret-model canary cannot discover it and 'covered the moment "
        "it exists' stops being true (R-SEC-050)."
    )


def test_the_local_class_sweep_catches_a_planted_instance(tmp_path: Path) -> None:
    path = tmp_path / "factory.py"
    path.write_text(
        "from pydantic import BaseModel, SecretStr\n"
        "def make() -> type[BaseModel]:\n"
        "    class Hidden(BaseModel):\n"
        "        token: SecretStr\n"
        "    return Hidden\n",
        encoding="utf-8",
    )

    found = [
        inner.name
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        for inner in ast.walk(node)
        if isinstance(inner, ast.ClassDef)
    ]

    assert found == ["Hidden"]
