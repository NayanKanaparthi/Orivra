"""The `v0.1` legacy input surface, checked against the tag rather than against memory.

**Why this file exists.** `ORIVRA_V1_PLAN.md` §9a.2 lists "the v0.1 legacy Gmail path unchanged
in names, schemas, defaults and observable behaviour" under *What binds, unchanged*, and the
release report is permitted to say so. Nothing checked it. On 2026-09-19, reconciling the
release checklist, a diff of the four legacy tools' published input schemas between the `v0.1`
tag and `HEAD` found that `mailweave_search` had lost `pool.scope` and `pool.window`: both were
published at `v0.1`, both were accepted there, and a call carrying either had begun coming back
`INVALID_PARAMS`. It went in with M2, which built the semantic rung and reshaped `pool{}` around
it, and nobody noticed because no test compared the two.

So the first test here does the comparison mechanically, from the tag, on every run. A
regression that only asserts today's accept-list would have passed on the day the keys left.

**What is and is not claimed.** These keys are accepted and act on nothing - that is `v0.1`'s
own description of the whole block, which changed no retrieval because the rung did not exist.
The tests below hold the *input* contract: the call is accepted, the value shapes `v0.1`
published are still the shapes enforced, and nothing the keys carry reaches retrieval. They do
not claim the response is byte-identical to `v0.1`'s, which it is not and is not meant to be.
"""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from mailweave.envelope.vocab import ToolName
from mailweave.surface.arguments import (
    POOL_COMPAT_KEYS,
    POOL_COMPAT_SCOPES,
    POOL_KEYS,
    ArgumentInvalid,
    parse_search,
)
from mailweave.surface.tools import SPEC_BY_NAME

#: The tag the compatibility claim is about.
BASELINE = "v0.1"

REPO = Path(__file__).resolve().parents[1]


def _published_keys(source: str) -> dict[str, set[str]]:
    """Every argument key each legacy tool publishes, as dotted paths.

    Read out of the module source rather than by importing it: the point is to read the file as
    it stood at another revision, and that revision's imports are not this one's.
    """
    import re

    out: dict[str, set[str]] = {}
    tool: str | None = None
    stack: list[tuple[int, str | None]] = []
    for line in source.splitlines():
        found = re.search(r"ToolName\.([A-Z_]+)", line)
        if found:
            tool, stack = found.group(1), []
        if tool is None:
            continue
        indent = len(line) - len(line.lstrip())
        while stack and indent <= stack[-1][0]:
            stack.pop()
        opens = re.match(r'^\s*"([a-z_]+)"\s*:\s*\{', line)
        if opens:
            name = opens.group(1)
            if name in {"properties", "items", "inputSchema", "outputSchema"}:
                stack.append((indent, None))
                continue
            out.setdefault(tool, set()).add(".".join([p for _, p in stack if p] + [name]))
            stack.append((indent, name))
    return out


FIXTURE = REPO / "tests/fixtures/v01_input_keys.json"


def _baseline_from_fixture() -> dict[str, set[str]]:
    held = json.loads(FIXTURE.read_text())["published_argument_keys"]
    return {tool: set(keys) for tool, keys in held.items()}


def test_no_legacy_argument_key_has_been_withdrawn_since_v0_1() -> None:
    """The guard that would have caught this the day it happened.

    **Against the checked-in fixture, so that it runs where the suite runs.** The full suite
    runs in an isolated runner over an exported working tree with no `.git` in it; a test that
    read the tag directly would skip there, which is exactly the run that was silent when these
    keys left. `test_the_fixture_still_matches_the_tag` below is what keeps the fixture honest,
    and it is the one that skips.

    Additions are fine and are not checked: a new optional key breaks no client. A *removal* is
    what breaks one, because the call it was published for stops parsing.
    """
    before = _baseline_from_fixture()
    now = _published_keys((REPO / "server/src/mailweave/surface/tools.py").read_text())
    withdrawn = {
        tool: sorted(keys - now.get(tool, set()))
        for tool, keys in before.items()
        if keys - now.get(tool, set())
    }
    assert not withdrawn, (
        f"published argument keys withdrawn since {BASELINE}: {withdrawn}. A v0.1 client that "
        "sends one gets INVALID_PARAMS, which §9a.2 binds against. Restore the key as an "
        "accepted no-op, or take the claim out of the release report - not neither"
    )


def test_the_fixture_still_matches_the_tag() -> None:
    """The tag is the source of truth; the fixture is a cache of it.

    Skips without `.git`, which is the isolated runner. That is the right way round: the check
    that cannot run everywhere is the one that would merely be *stale*, not the one that would
    be *wrong*.
    """
    found = subprocess.run(
        ["git", "show", f"{BASELINE}:server/src/mailweave/surface/tools.py"],
        cwd=REPO,
        capture_output=True,
    )
    if found.returncode != 0:
        pytest.skip(f"{BASELINE} is not reachable from this checkout")
    from_tag = _published_keys(found.stdout.decode("utf-8"))
    assert from_tag == _baseline_from_fixture(), (
        "tests/fixtures/v01_input_keys.json no longer matches the v0.1 tag. Regenerate it with "
        "`python tools/dev/v01_input_keys.py` and look hard at what moved before accepting it"
    )


def test_the_two_restored_keys_are_published_with_v0_1_s_own_shapes() -> None:
    """Accepted, and no more loosely than `v0.1` accepted them.

    A key this server waves through where `v0.1` refused is its own break, in the other
    direction: a client that relied on `scope` being validated would stop being told.
    """
    schema = SPEC_BY_NAME[ToolName.SEARCH].input_schema
    pool = schema["properties"]["pool"]["properties"]
    for key in POOL_COMPAT_KEYS:
        assert key in pool, f"{key} is not published"
        assert "compat" in pool[key]["description"].lower(), (
            f"{key} is published without saying it is inert, so a client reads it as live"
        )
    assert pool["scope"]["enum"] == list(POOL_COMPAT_SCOPES)
    assert pool["window"]["type"] == "string"


@pytest.mark.parametrize(
    "block",
    [
        {"scope": "auto"},
        {"scope": "thread"},
        {"scope": "recency"},
        {"scope": "participant"},
        {"window": "7d"},
        {"window": "2026-01-01..2026-02-01"},
        {"scope": "auto", "window": "7d"},
        {"scope": "thread", "max_threads": 4},
    ],
)
def test_a_v0_1_shaped_pool_call_is_accepted(block: dict[str, Any]) -> None:
    parse_search({"query": "vendor", "pool": dict(block)})


@pytest.mark.parametrize(
    "block",
    [{"scope": "nonsense"}, {"scope": 42}, {"window": 42}, {"window": None}, {"unknown": 1}],
)
def test_a_value_v0_1_would_have_refused_is_still_refused(block: dict[str, Any]) -> None:
    with pytest.raises(ArgumentInvalid):
        parse_search({"query": "vendor", "pool": dict(block)})


def test_the_restored_keys_reach_no_part_of_the_request() -> None:
    """Accepted is not the same as acted on, and this is the half that says so.

    `PoolRequest` has no field for either key, so the check is that the parsed request is
    *identical* to the one the same call without them produces - not merely that the two
    fields it does have are unset.
    """
    plain = parse_search({"query": "vendor"})
    carried = parse_search({"query": "vendor", "pool": {"scope": "thread", "window": "7d"}})
    assert carried == plain, "a compatibility key changed the parsed request, so it is not a no-op"

    narrowed = parse_search({"query": "vendor", "pool": {"max_threads": 3}})
    also = parse_search(
        {"query": "vendor", "pool": {"max_threads": 3, "scope": "recency", "window": "7d"}}
    )
    assert also == narrowed, "a compatibility key changed a request that also narrowed the pool"


def test_the_two_key_sets_stay_separate_in_the_code() -> None:
    """The live keys and the inert ones must not merge.

    Folding them into one tuple is the obvious tidy-up and it is the thing that would let an
    inert key quietly become live, or the reverse, with nothing failing.
    """
    assert not set(POOL_KEYS) & set(POOL_COMPAT_KEYS)
    source = (REPO / "server/src/mailweave/surface/arguments.py").read_text()
    tree = ast.parse(source)
    fields = {
        node.target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert not {"scope", "window"} & fields, (
        "a compatibility key has become a field somewhere in the argument reader"
    )


def test_the_legacy_tool_schemas_are_still_valid_json_schema() -> None:
    """Republishing a key is a schema edit, and a schema that no longer validates is worse
    than the break it was fixing."""
    import jsonschema

    for name in (
        ToolName.SEARCH,
        ToolName.THREAD_MAP,
        ToolName.GET_MESSAGES,
        ToolName.GET_ATTACHMENT,
    ):
        schema = SPEC_BY_NAME[name].input_schema
        jsonschema.Draft202012Validator.check_schema(schema)
        json.dumps(schema)  # and it is serialisable, which the wire needs


@pytest.mark.parametrize("block", [{"scope": "auto"}, {"window": "7d"}])
def test_a_v0_1_call_validates_against_the_published_schema(block: dict[str, Any]) -> None:
    """The layer above the parser. A strict client validates before it sends, so a key the
    parser accepts and the schema omits is still a call that never arrives."""
    import jsonschema

    jsonschema.validate(
        {"query": "vendor", "pool": dict(block)},
        SPEC_BY_NAME[ToolName.SEARCH].input_schema,
    )
