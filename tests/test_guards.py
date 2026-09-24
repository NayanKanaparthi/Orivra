"""Every CI guard is exercised against a deliberately planted violation (WS-00).

The implementation plan's acceptance condition for the gates is exactly this: "CI gates
fail on a deliberately planted violation of each sweep". A guard that has only ever been
run against clean code is a guard nobody knows works.

Each test also checks the guard does *not* fire on the legitimate shape it must tolerate,
because a gate that cannot be passed gets disabled, which is worse than no gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.guards import GUARDS, Violation, listening_socket_sweep, run_all
from tools.guards.sweeps import (
    forbidden_imports,
    generative_client_sweep,
    gmail_path_sweep,
    ground_truth_sweep,
    model_host_sweep,
    scope_literal_sweep,
    unaudited_disk_write_sweep,
    unwrapped_http_client_sweep,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_SRC = REPO_ROOT / "server" / "src"


def plant(tmp_path: Path, source: str, name: str = "planted.py") -> Path:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return tmp_path


def details(violations: list[Violation]) -> str:
    return " | ".join(v.detail for v in violations)


# --- the real tree stays clean ---------------------------------------------------------------


def test_the_shipped_server_tree_passes_every_guard() -> None:
    assert run_all(SERVER_SRC) == []


def test_every_registered_guard_is_covered_by_a_planted_violation_test() -> None:
    """If a guard is added without a planted-violation test, this fails."""
    covered = {
        "ground-truth-isolation",
        "forbidden-import",
        "scope-literal",
        "gmail-endpoint",
        "generative-client",
        "unaudited-disk-write",
        "unwrapped-http-client",
        "no-model-host-at-runtime",
        "no-listening-socket",
    }
    assert set(GUARDS) == covered


# --- ground truth --------------------------------------------------------------------------


def test_ground_truth_identifiers_are_caught(tmp_path: Path) -> None:
    root = plant(tmp_path, "def load():\n    seed_map = {}\n    return seed_map\n")
    assert ground_truth_sweep(root)


def test_ground_truth_paths_in_string_literals_are_caught(tmp_path: Path) -> None:
    root = plant(tmp_path, 'PATH = "benchmarks/ground_truth/cases.json"\n')
    assert "ground_truth" in details(ground_truth_sweep(root))


def test_prose_about_the_harness_is_not_a_violation(tmp_path: Path) -> None:
    """A docstring that mentions the harness cannot read a file; a gate that says otherwise
    is one nobody will keep."""
    root = plant(
        tmp_path,
        '"""The harness owns seeding and the ground_truth manifests; this module does not."""\n'
        "VALUE = 1\n",
    )
    assert ground_truth_sweep(root) == []


# --- import direction ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "import mailweave_harness\n",
        "from mailweave_harness.scopes import SEEDER_SCOPE\n",
        "from tools.guards import run_all\n",
        "import tests.fixtures\n",
    ],
)
def test_server_imports_of_the_harness_or_tooling_are_caught(tmp_path: Path, source: str) -> None:
    assert forbidden_imports(plant(tmp_path, source))


def test_ordinary_imports_are_untouched(tmp_path: Path) -> None:
    root = plant(tmp_path, "import httpx\nfrom mailweave.constants import READ_SCOPE\n")
    assert forbidden_imports(root) == []


# --- scopes ---------------------------------------------------------------------------------


def test_a_second_gmail_scope_literal_is_caught(tmp_path: Path) -> None:
    root = plant(tmp_path, 'SCOPE = "https://www.googleapis.com/auth/gmail.modify"\n')
    assert "not the single permitted scope" in details(scope_literal_sweep(root))


def test_the_destructive_harness_scope_in_server_code_is_caught(tmp_path: Path) -> None:
    root = plant(tmp_path, 'SCOPE = "https://mail.google.com/"\n')
    assert "destructive" in details(scope_literal_sweep(root))


def test_the_read_scope_itself_is_allowed(tmp_path: Path) -> None:
    root = plant(tmp_path, 'SCOPE = "https://www.googleapis.com/auth/gmail.readonly"\n')
    assert scope_literal_sweep(root) == []


# --- Gmail endpoints -------------------------------------------------------------------------


def test_an_endpoint_outside_the_declared_six_is_caught(tmp_path: Path) -> None:
    root = plant(tmp_path, 'URL = "gmail/v1/users/{userId}/messages/send"\n')
    assert gmail_path_sweep(root)


def test_the_six_declared_endpoints_pass(tmp_path: Path) -> None:
    from mailweave.constants import GMAIL_ENDPOINTS

    body = "\n".join(f'E{i} = "{path}"' for i, path in enumerate(GMAIL_ENDPOINTS))
    assert gmail_path_sweep(plant(tmp_path, body + "\n")) == []


# --- generative clients ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "import openai\n",
        "from anthropic import Anthropic\n",
        "import google.generativeai as genai\n",
        'URL = "https://example.invalid/v1/chat/completions"\n',
    ],
)
def test_a_generative_client_in_server_code_is_caught(tmp_path: Path, source: str) -> None:
    assert generative_client_sweep(plant(tmp_path, source))


def test_the_embedding_stack_is_not_a_generative_client(tmp_path: Path) -> None:
    """SEC-08 forbids a learned *router*, not the embedding model; the gate must agree."""
    root = plant(tmp_path, "import sentence_transformers\nimport onnxruntime\n")
    assert generative_client_sweep(root) == []


# --- disk writes ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        'from pathlib import Path\nPath("/tmp/x").write_text("body")\n',
        'import json\nwith open("/tmp/x", "w") as f:\n    json.dump({}, f)\n',
        'open("/tmp/trace.jsonl", mode="a").write("x")\n',
    ],
)
def test_an_unaudited_disk_write_is_caught(tmp_path: Path, source: str) -> None:
    assert unaudited_disk_write_sweep(plant(tmp_path, source))


def test_reading_a_file_is_not_a_write(tmp_path: Path) -> None:
    root = plant(tmp_path, 'from pathlib import Path\nDATA = Path("x").read_text()\n')
    assert unaudited_disk_write_sweep(root) == []


def test_the_credential_store_is_the_one_allowlisted_writer() -> None:
    """The allowlist is a named module, so a new writer shows up in a diff."""
    violations = unaudited_disk_write_sweep(SERVER_SRC)
    assert violations == []
    tokenstore = SERVER_SRC / "mailweave" / "auth" / "tokenstore.py"
    assert "json.dump" in tokenstore.read_text(encoding="utf-8")


# --- the CLI ------------------------------------------------------------------------------


def test_the_guard_cli_exits_non_zero_on_a_violation(tmp_path: Path) -> None:
    from tools.guards.__main__ import main

    root = plant(tmp_path, 'SCOPE = "https://www.googleapis.com/auth/gmail.modify"\n')
    assert main([str(root)]) == 1
    assert main([str(SERVER_SRC)]) == 0
    assert main([str(tmp_path / "missing")]) == 2


# --- H3 / R-SEC-001: the four demonstration files that used to pass all six guards -----------

#: R-SEC-001's reproduction, verbatim in shape: ordinary code - split literals, dynamic
#: imports, `Path(...).open("w")` - that does exactly what the guards exist to forbid.
#: Round 1 reported **zero violations** for all four. Each is asserted here against the
#: guard whose documented intent it violates.
BYPASS_FILES: dict[str, str] = {
    "a_harness.py": (
        "import importlib\n"
        '_mod = importlib.import_module("mailweave" + "_harness")\n'
        'globals()["se" + "ed" + "_map"] = getattr(_mod, "SEEDER_SCOPE", None)\n'
        'PATH = "benchmarks/" + "ground" + "_truth/cases.json"\n'
    ),
    "b_scope.py": (
        'DESTRUCTIVE_SCOPE = "https://mail.google.com" + "/"\n'
        'SEND_ENDPOINT = "gmail/v" + "1/users/{userId}/messages/send"\n'
    ),
    "c_generative.py": (
        "import importlib\n"
        '_client = importlib.import_module("open" + "ai")\n'
        'path = "chat/completio" + "ns"\n'
    ),
    "d_write.py": (
        "import os\n"
        "from pathlib import Path\n"
        "def dump(out_path: str, body_clean: str) -> None:\n"
        '    Path(out_path).open("w", encoding="utf-8").write(body_clean)\n'
        '    fd = os.open(out_path + ".2", os.O_WRONLY | os.O_CREAT)\n'
        "    os.write(fd, body_clean.encode())\n"
    ),
}


@pytest.fixture
def bypass_tree(tmp_path: Path) -> Path:
    for name, source in BYPASS_FILES.items():
        (tmp_path / name).write_text(source, encoding="utf-8")
    return tmp_path


#: The guards R-SEC-001's four files defeat, named rather than taken as "every guard".
#: `unwrapped-http-client` is deliberately absent: it was added in round 5 for R-ARCH-006
#: and these files construct no HTTP client, so asserting it fires here would be asserting
#: coverage this fixture does not exercise.
R_SEC_001_GUARDS = frozenset(
    {
        "ground-truth-isolation",
        "forbidden-import",
        "scope-literal",
        "gmail-endpoint",
        "generative-client",
        "unaudited-disk-write",
    }
)


def test_the_round_one_bypass_files_no_longer_pass_the_guards(bypass_tree: Path) -> None:
    """R-SEC-001's acceptance condition: the demonstration file must fail the guards."""
    violations = run_all(bypass_tree)
    assert violations, "the four R-SEC-001 files produced zero violations again"
    # Not "some guard fired": all six intents these files violate are reported.
    assert {v.guard for v in violations} == R_SEC_001_GUARDS
    assert set(GUARDS) > R_SEC_001_GUARDS


@pytest.mark.parametrize(
    ("filename", "guard", "expected"),
    [
        ("a_harness.py", "ground-truth-isolation", "seed_map"),
        ("a_harness.py", "forbidden-import", "mailweave_harness"),
        ("b_scope.py", "scope-literal", "mail.google.com"),
        ("b_scope.py", "gmail-endpoint", "messages/send"),
        ("c_generative.py", "generative-client", "openai"),
        ("c_generative.py", "generative-client", "chat/completions"),
        ("d_write.py", "unaudited-disk-write", ".open(mode='w')"),
        ("d_write.py", "unaudited-disk-write", "os.write"),
    ],
)
def test_each_bypass_shape_is_caught_by_the_guard_it_defeats(
    tmp_path: Path, filename: str, guard: str, expected: str
) -> None:
    root = plant(tmp_path, BYPASS_FILES[filename], name=filename)
    found = [v for v in run_all(root) if v.guard == guard]
    assert expected in details(found), f"{guard} did not catch {expected!r} in {filename}"


def test_a_split_literal_is_folded_before_matching(tmp_path: Path) -> None:
    """The mechanism, tested apart from the four files: concatenation is not concealment."""
    root = plant(tmp_path, 'SCOPE = "https://www.googleapis.com/auth/" + "gmail.modify"\n')
    assert "gmail.modify" in details(scope_literal_sweep(root))


def test_an_f_string_endpoint_is_compared_by_shape_not_by_text(tmp_path: Path) -> None:
    """A declared endpoint stays legal when its id is interpolated; the send path does not."""
    (tmp_path / "legal").mkdir()
    (tmp_path / "illegal").mkdir()
    legal = plant(
        tmp_path / "legal",
        'def url(user_id: str) -> str:\n    return f"gmail/v1/users/{user_id}/messages"\n',
    )
    assert gmail_path_sweep(legal) == []
    illegal = plant(
        tmp_path / "illegal",
        'def url(user_id: str) -> str:\n    return f"gmail/v1/users/{user_id}/messages/send"\n',
    )
    assert "send" in details(gmail_path_sweep(illegal))


def test_an_unreadable_dynamic_import_is_itself_a_violation(tmp_path: Path) -> None:
    """A module name no static pass can read is a name no static pass can clear."""
    root = plant(
        tmp_path,
        "import importlib\nimport os\n_m = importlib.import_module(os.environ['PKG'])\n",
    )
    assert "computed at runtime" in details(forbidden_imports(root))


def test_an_ordinary_dynamic_import_of_a_permitted_module_is_not_a_violation(
    tmp_path: Path,
) -> None:
    """The gate has to be passable: importing a legitimate module dynamically is fine."""
    root = plant(tmp_path, 'import importlib\n_m = importlib.import_module("json")\n')
    assert forbidden_imports(root) == []
    assert generative_client_sweep(root) == []


def test_an_open_whose_mode_cannot_be_read_is_reported_not_assumed_to_be_a_read(
    tmp_path: Path,
) -> None:
    root = plant(tmp_path, "import os\ndef w(p: str, m: str) -> None:\n    open(p, m).write('x')\n")
    assert "computed at runtime" in details(unaudited_disk_write_sweep(root))


def test_an_open_for_reading_through_an_attribute_is_still_not_a_write(tmp_path: Path) -> None:
    root = plant(
        tmp_path,
        "from pathlib import Path\ndef r(p: str) -> str:\n    return Path(p).open().read()\n",
    )
    assert unaudited_disk_write_sweep(root) == []


def test_every_guard_states_what_it_does_not_catch() -> None:
    """An overstated guard is worse than none (R-SEC-001), so the claim is part of the code."""
    from tools.guards import sweeps

    for name, guard in GUARDS.items():
        doc = guard.__doc__ or ""
        assert "Does not catch" in doc, f"guard {name} does not bound its own claim"
    assert "What no guard here can catch" in (sweeps.__doc__ or "")


# --- H3 round 2 / R-SEC-008: a literal's spelling is not its meaning -------------------------

#: R-SEC-008's reproduction, verbatim. One byte-string literal per content-matching guard;
#: `b"...".decode()` is ordinary Python, and round 2's `isinstance(node.value, str)` made
#: all four guards blind to it at once. Reported: **0 violations**.
BYTES_BYPASS = (
    '_p1 = b"benchmarks/ground_truth/cases.json".decode()\n'
    '_p2 = b"https://mail.google.com/".decode()\n'
    '_p3 = b"gmail/v1/users/{userId}/messages/send".decode()\n'
    '_p4 = b"chat/completions".decode()\n'
    '_p5 = b"huggingface.co".decode()\n'
)


def test_the_byte_string_bypass_registers_on_every_content_matching_guard(
    tmp_path: Path,
) -> None:
    """R-SEC-008's acceptance condition, stated as a set rather than as "something fired".

    The set grows when a content-matching guard is added, which is the point: round 2's
    `isinstance(node.value, str)` made four guards blind at once, and the way a fifth
    inherits the fix is by being written against the shared folding walker and then proving
    it here. `no-model-host-at-runtime` joined on 2026-09-11.
    """
    root = plant(tmp_path, BYTES_BYPASS, name="bytes_bypass.py")
    fired = {v.guard for v in run_all(root)}
    assert fired == {
        "ground-truth-isolation",
        "scope-literal",
        "gmail-endpoint",
        "generative-client",
        "no-model-host-at-runtime",
    }


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('X = b"seed" + b"_map"\n', "seed_map"),
        ('X = (b"chat/comple" + b"tions").decode("utf-8")\n', "chat/completions"),
        ('X = "https://mail.google.com/".encode().decode()\n', "mail.google.com"),
    ],
)
def test_bytes_are_folded_the_same_way_strings_are(
    tmp_path: Path, source: str, expected: str
) -> None:
    """Concatenation and transcoding compose; the fold has to see through both."""
    assert expected in details(run_all(plant(tmp_path, source)))


def test_an_ordinary_byte_literal_is_not_a_violation(tmp_path: Path) -> None:
    """The gate stays passable: bytes are how MIME payloads arrive."""
    root = plant(tmp_path, 'PREFIX = b"--boundary"\nEMPTY = b""\n')
    assert run_all(root) == []


# --- R-SEC-009 / R-SEC-010: the name a write is reached through ------------------------------

#: Each is a shape R-SEC reproduced against round 2's guard for **0 violations**. None is
#: adversarial: re-binding an imported function is an ordinary refactor, which is why these
#: are caught rather than documented as out of reach.
WRITE_BYPASSES: dict[str, tuple[str, str]] = {
    "from_import_alias": (
        "from os import write as w\ndef leak(fd: int, body: bytes) -> None:\n    w(fd, body)\n",
        "os.write",
    ),
    "from_import_plain": (
        "from shutil import copy\ndef leak(src: str, dst: str) -> None:\n    copy(src, dst)\n",
        "shutil.copy",
    ),
    "assign_then_call": (
        "import os\n_writer = os.write\ndef leak(fd: int, body: bytes) -> None:\n"
        "    _writer(fd, body)\n",
        "os.write",
    ),
    "functools_partial": (
        "import functools\nimport os\nleak = functools.partial(os.write)\n"
        "def go(fd: int, body: bytes) -> None:\n    leak(fd, body)\n",
        "os.write",
    ),
    "module_alias": (
        "import os as o\ndef leak(fd: int, body: bytes) -> None:\n    o.write(fd, body)\n",
        "os.write",
    ),
    "io_open_ordinary_filename": (
        'import io\ndef leak(body: str) -> None:\n    io.open("output.log", "w").write(body)\n',
        "io.open(mode='w')",
    ),
}


@pytest.mark.parametrize(("name", "case"), sorted(WRITE_BYPASSES.items()))
def test_a_write_reached_through_a_rebound_name_is_still_a_write(
    tmp_path: Path, name: str, case: tuple[str, str]
) -> None:
    source, expected = case
    root = plant(tmp_path, source, name=f"{name}.py")
    assert expected in details(unaudited_disk_write_sweep(root))


def test_the_io_open_filename_is_no_longer_mistaken_for_the_mode(tmp_path: Path) -> None:
    """R-SEC-010 exactly: the old guard read position 0, so it inspected the *path*.

    `io.open("leaked.log", "w")` was caught by the accident of an `a` in `leaked`, and
    `io.open("output.log", "w")` - the same write, a duller filename - passed. Both must be
    caught now, and for the same stated reason: the mode says `w`.
    """
    for filename in ("output.log", "leaked.log"):
        root = plant(
            tmp_path,
            f'import io\nio.open("{filename}", "w").write("body")\n',
            name="w.py",
        )
        assert "io.open(mode='w')" in details(unaudited_disk_write_sweep(root))


@pytest.mark.parametrize(
    "source",
    [
        "import io\ndef r(p: str) -> str:\n    return io.open(p).read()\n",
        'import io\ndef r(p: str) -> str:\n    return io.open(p, "r").read()\n',
        "import os\ndef r(p: str) -> int:\n    return os.stat(p).st_size\n",
        "from shutil import which\ndef r(p: str) -> str | None:\n    return which(p)\n",
    ],
)
def test_resolving_the_receiver_does_not_turn_reads_into_writes(
    tmp_path: Path, source: str
) -> None:
    """The cost of reading position 1 is that position 0 must stop being a fallback.

    A resolved `io.open` is a *cleared* read, not an unknown `.open()` whose mode has to
    be guessed - otherwise every `io.open(path)` in the tree reports "mode computed at
    runtime" and the gate becomes one nobody can pass.
    """
    assert unaudited_disk_write_sweep(plant(tmp_path, source)) == []


def normalised(doc: str | None) -> str:
    """Docstring text with line wrapping removed, so a phrase can be asserted whole."""
    return " ".join((doc or "").split())


def test_the_disk_write_guard_names_the_aliasing_it_still_cannot_follow() -> None:
    """The standing rule: a guard may catch a bypass or document it, never imply coverage.

    Round 2 documented `import os as o` and left three sibling shapes unmentioned; round 3
    caught those four and left a class attribute and a five-module opener list. Each round
    the documented gap has to move to what is actually left, and the shapes named here are
    each exercised against the guard by `test_each_documented_gap_is_really_a_gap`.
    """
    doc = normalised(unaudited_disk_write_sweep.__doc__)
    for phrase in (
        "functools.partial",
        "import os as o",
        "from os import write as w",
        "class W: handler = os.write",
        'mod = io; mod.open(p, "w")',
    ):
        assert phrase in doc, f"the guard no longer mentions {phrase!r}"
    gap = doc.split("Does not catch:", 1)[1]
    assert "returned from a function" in gap
    assert "instance** attribute" in gap
    assert "getattr" in gap
    assert "resolves to nothing" in gap
    assert "constructor" in gap


def test_an_alias_the_index_cannot_follow_is_documented_rather_than_silently_missed(
    tmp_path: Path,
) -> None:
    """The honest half of R-SEC-009: this shape is *not* caught, and the docstring says so.

    A test that only showed the caught cases would let the "Does not catch" list drift out
    of date silently, which is the failure mode R-SEC-001 filed in the first place.
    """
    root = plant(
        tmp_path,
        "import os\n"
        "def pick() -> object:\n    return os.write\n"
        "def leak(fd: int, body: bytes) -> None:\n    pick()(fd, body)\n",
    )
    assert unaudited_disk_write_sweep(root) == []


# --- R-SEC-013: a literal's spelling is not its meaning, round three -------------------------

#: The nine idioms R-SEC-013 reproduced against round 3's fold. Seven produced **0
#: violations**; two "passed" only because `_fold` bailed without marking the inner literal
#: absorbed, so the unrelated plain-`Constant` scan picked it up by accident. Each builds the
#: literal text `ground_truth/cases.json` at runtime, and none of the nine is adversarial -
#: every one is ordinary Python somebody writes on purpose, which is why they are folded
#: rather than named as evasions.
FOLDED_IDIOMS: dict[str, str] = {
    "fromhex": 'X = bytes.fromhex("67726f756e645f74727574682f63617365732e6a736f6e").decode()\n',
    "join": 'X = "".join(["ground_tr", "uth/cases.json"])\n',
    "percent": 'X = "%s_truth/cases.json" % "ground"\n',
    "format": 'X = "{}_truth/cases.json".format("ground")\n',
    "translate": 'X = "groundZtruth/cases.json".translate(str.maketrans("Z", "_"))\n',
    "reversed_slice": 'X = "nosj.sesac/hturt_dnuorg"[::-1]\n',
    "to_bytes": (
        "X = (9908255405203514195101013946677413356969247666922024814)"
        ".to_bytes(23, 'big').decode()\n"
    ),
    "bytearray": 'X = bytearray(b"ground_truth/cases.json").decode()\n',
    "codecs_decode": 'import codecs\nX = codecs.decode(b"ground_truth/cases.json", "utf-8")\n',
}


@pytest.mark.parametrize(("name", "source"), sorted(FOLDED_IDIOMS.items()))
def test_each_constant_obfuscation_idiom_is_folded_before_matching(
    tmp_path: Path, name: str, source: str
) -> None:
    root = plant(tmp_path, source, name=f"{name}.py")
    assert "ground_truth" in details(ground_truth_sweep(root)), (
        f"{name} builds the forbidden text and the fold did not see it"
    )


def test_the_two_accidental_catches_are_now_understood_rather_than_lucky(
    tmp_path: Path,
) -> None:
    """`bytearray(...)` and `codecs.decode(...)` used to "pass" for the wrong reason.

    Round 3's `_fold` returned `None` for both without visiting the inner literal, which
    left it unabsorbed for the plain-`Constant` scan to report as a loose string. Nesting a
    fold *inside* them removes the accident: the raw literal is now hexadecimal, which
    contains no forbidden token at all, so only a fold that understands both calls can
    report anything.
    """
    hexed = b"ground_truth/cases.json".hex()
    root = plant(
        tmp_path,
        f'import codecs\nX = codecs.decode(bytes.fromhex("{hexed}"), "utf-8")\n',
        name="nested.py",
    )
    assert "ground_truth" in details(ground_truth_sweep(root))


def test_a_fold_that_cannot_finish_leaves_its_literals_to_the_plain_scan(
    tmp_path: Path,
) -> None:
    """The half-completed fold, which hid a literal outright.

    `_fold` used to write into `consumed` as it descended. Folding
    `"benchmarks/ground_truth/cases" + suffix` therefore marked the literal absorbed, then
    failed on `suffix` and returned `None` - and `_string_literals` skipped the absorbed
    literal, so neither the whole string nor the piece was ever reported. Found while
    fixing R-SEC-013; the same shape would have swallowed every new fold below it.
    """
    root = plant(
        tmp_path,
        'def path(suffix: str) -> str:\n    return "benchmarks/ground_truth/cases" + suffix\n',
        name="half.py",
    )
    assert "ground_truth" in details(ground_truth_sweep(root))


#: Shapes the fold does **not** read. Each is named in the module docstring's fold section,
#: and each is asserted here to really produce nothing - so the documented gap cannot drift
#: into being either an overstatement or an understatement of what the code does.
UNFOLDED_IDIOMS: dict[str, str] = {
    "through_a_variable": 'PART = "ground"\nX = PART + "_truth/cases.json"\n',
    "join_over_a_comprehension": (
        'PARTS = ["ground_tr", "uth/cases.json"]\nX = "".join(p for p in PARTS)\n'
    ),
    "percent_d": 'X = "%s_truth/cases.js%dn" % ("ground", 0)\n',
    "format_spec": 'X = "{:s}_truth/cases.json".format("ground")\n',
    "base64": 'import base64\nX = base64.b64decode("Z3JvdW5kX3RydXRoLw==").decode()\n',
    "replace": 'X = "groundZtruth/cases.json".replace("Z", "_")\n',
}


@pytest.mark.parametrize(("name", "source"), sorted(UNFOLDED_IDIOMS.items()))
def test_each_unfolded_idiom_is_named_in_the_docstring_rather_than_silently_missed(
    tmp_path: Path, name: str, source: str
) -> None:
    from tools.guards import sweeps

    assert ground_truth_sweep(plant(tmp_path, source, name=f"{name}.py")) == [], (
        f"{name} is now caught; move it out of the docstring's 'does not read' list"
    )
    doc = normalised(sweeps.__doc__)
    assert "What the constant fold reads" in doc
    for phrase in (
        'a **variable**: `part = "ground"; part + "_truth/x"`',
        "over a comprehension or a name",
        "`%d`/`%r`/width/precision conversions",
        "a format spec (`:>8`)",
        "`base64.b64decode`",
        "`str.replace`",
    ):
        assert phrase in doc, f"the fold no longer names {phrase!r} as unread"


def test_a_non_text_preserving_codec_is_refused_rather_than_reported_as_its_input(
    tmp_path: Path,
) -> None:
    """`codecs.decode(x, "rot13")` produces different text; folding it would report a lie.

    The literal is still reported - it is a plain constant and the fallback scan sees it -
    but the *fold* declines, which is what stops the guard from claiming a call produces a
    string it does not.
    """
    import ast as ast_module

    from tools.guards.sweeps import _fold

    call = ast_module.parse('codecs.decode("tebhaq_gehgu", "rot13")', mode="eval").body
    assert _fold(call, set()) is None


# --- R-SEC-014/015/016: the name and the signature a write is reached through ----------------


def test_a_write_through_a_class_attribute_is_caught(tmp_path: Path) -> None:
    """R-SEC-014: the class-body assignment was always indexed; nothing looked it up.

    `_writes_to_disk` resolved an `Attribute` receiver only through the module aliases, so
    `Writer.handler(...)` fell through every branch and was never classified - even though
    `handler = os.write` sits in the index the whole time.
    """
    root = plant(
        tmp_path,
        "import os\n"
        "class Writer:\n"
        "    handler = os.write\n"
        "def leak(fd: int, body: bytes) -> None:\n"
        "    Writer.handler(fd, body)\n",
        name="class_attr.py",
    )
    assert "os.write" in details(unaudited_disk_write_sweep(root))


def test_a_class_attribute_is_not_visible_as_a_bare_name_outside_the_class(
    tmp_path: Path,
) -> None:
    """The other half of R-SEC-014: resolving it must not leak the name into module scope.

    `class W: handler = os.write` binds `handler` inside `W`, not beside it. A pass that
    indexed it flat would report an unrelated local `handler` in some other function, which
    is exactly the false positive R-SEC-015 is about.
    """
    root = plant(
        tmp_path,
        "import os\n"
        "class Writer:\n"
        "    handler = os.write\n"
        "def format_metric(name: str, value: str) -> str:\n"
        '    handler = "{}={}".format\n'
        "    return handler(name, value)\n",
        name="class_attr_scope.py",
    )
    assert unaudited_disk_write_sweep(root) == []


#: R-SEC-015's two reproductions, verbatim in shape: two ordinary, unrelated functions that
#: merely reuse a local name. Round 3 reported **2 violations for 1 real write** in each.
FALSE_POSITIVE_FILES: dict[str, tuple[str, int]] = {
    "reused_local_name": (
        "import os\n"
        "def emit(fd: int, body: bytes) -> None:\n"
        "    _disk_writer = os.write\n"
        "    _disk_writer(fd, body)\n"
        "def emit_metric(name: str, value: str) -> str:\n"
        '    _disk_writer = "{}={}".format\n'
        "    return _disk_writer(name, value)\n",
        4,
    ),
    "reused_local_name_copy": (
        "import shutil\n"
        "def archive(src: str, dst: str) -> None:\n"
        "    do_copy = shutil.copy\n"
        "    do_copy(src, dst)\n"
        "def duplicate(rows: list[str]) -> list[str]:\n"
        "    do_copy = list.copy\n"
        "    return do_copy(rows)\n",
        4,
    ),
}


@pytest.mark.parametrize(("name", "case"), sorted(FALSE_POSITIVE_FILES.items()))
def test_a_local_name_reused_in_another_function_is_not_reported(
    tmp_path: Path, name: str, case: tuple[str, int]
) -> None:
    """R-SEC-015. A guard that fires on innocent code is one the next engineer switches off.

    The real write must still be reported, at its own line and only there: "reports nothing"
    would pass this test by breaking the guard, so the line number is asserted too.
    """
    source, write_line = case
    violations = unaudited_disk_write_sweep(plant(tmp_path, source, name=f"{name}.py"))
    assert [v.line for v in violations] == [write_line]


def test_a_name_rebound_later_in_the_same_function_stops_being_a_write(
    tmp_path: Path,
) -> None:
    """Scope alone is not enough: the same name can mean two things in one function."""
    root = plant(
        tmp_path,
        "import os\n"
        "def mixed(fd: int, body: bytes) -> str:\n"
        "    w = os.write\n"
        "    w(fd, body)\n"
        "    w = str.upper\n"
        "    return w(body.decode())\n",
        name="rebound.py",
    )
    assert [v.line for v in unaudited_disk_write_sweep(root)] == [4]


def test_a_write_hidden_in_the_second_arm_of_a_branch_is_reported(tmp_path: Path) -> None:
    """The other direction of the same mechanism, which round 3 missed entirely.

    `handler` assigned `json.dumps` in one arm and `os.write` in the other, called after the
    `if`: round 3 kept whichever binding it read first and reported nothing.
    """
    root = plant(
        tmp_path,
        "import json\n"
        "import os\n"
        "def leak(fd: int, body: bytes, flag: bool) -> None:\n"
        "    if flag:\n"
        "        handler = json.dumps\n"
        "    else:\n"
        "        handler = os.write\n"
        "    handler(fd, body)\n",
        name="branch.py",
    )
    assert "os.write" in details(unaudited_disk_write_sweep(root))


#: R-SEC-016: stdlib openers outside round 3's five-module list. `tarfile` and `shelve`
#: *resolve* perfectly well and were re-read at position 0 anyway - the path, not the mode -
#: which is R-SEC-010's original defect for every opener the list did not name.
OPENER_BYPASSES: dict[str, tuple[str, str]] = {
    "tarfile_clean_filename": (
        'import tarfile\ndef dump(p: str) -> None:\n    tarfile.open("dump.tgz", "w").close()\n',
        "tarfile.open(mode='w')",
    ),
    "shelve_default_flag": (
        'import shelve\ndef dump() -> None:\n    shelve.open("records.db").close()\n',
        "shelve.open(flag=<default, creates>)",
    ),
    "zipfile_constructor": (
        'import zipfile\ndef dump() -> None:\n    zipfile.ZipFile("dump.zip", "w").close()\n',
        "zipfile.ZipFile(mode='w')",
    ),
    "an_opener_on_no_list_at_all": (
        'import wave\ndef dump(p: str) -> None:\n    wave.open(p, "wb").close()\n',
        "wave.open(mode='wb')",
    ),
    "a_dbm_flag_rather_than_a_mode": (
        'import dbm\ndef dump(p: str) -> None:\n    dbm.gnu.open(p, "c").close()\n',
        "dbm.gnu.open(flag='c')",
    ),
}


@pytest.mark.parametrize(("name", "case"), sorted(OPENER_BYPASSES.items()))
def test_a_resolved_opener_is_read_at_the_mode_position_whatever_the_module_is(
    tmp_path: Path, name: str, case: tuple[str, str]
) -> None:
    """`wave` is the one that matters: it is on no list anywhere in this file.

    If the fix were still an allowlist, that case would pass silently. It is caught because
    the rule is structural - a receiver that resolves to a module is a module-level `open`,
    and those take the path first and the mode second, like the builtin.
    """
    source, expected = case
    root = plant(tmp_path, source, name=f"{name}.py")
    assert expected in details(unaudited_disk_write_sweep(root))


@pytest.mark.parametrize(
    "source",
    [
        "import wave\ndef r(p: str) -> None:\n    wave.open(p).close()\n",
        'import tarfile\ndef r(p: str) -> None:\n    tarfile.open(p, "r").close()\n',
        "import dbm\ndef r(p: str) -> None:\n    dbm.open(p).close()\n",
        "import webbrowser\ndef go(url: str) -> None:\n    webbrowser.open(url, 2)\n",
        "import webbrowser\ndef go(url: str) -> None:\n    webbrowser.open(url)\n",
    ],
)
def test_making_open_structural_does_not_turn_reads_and_browsers_into_writes(
    tmp_path: Path, source: str
) -> None:
    """The cost of classifying every resolved `.open` is that it must stay passable.

    `webbrowser.open(url, 2)` puts an integer where a mode would be; reading it as a mode
    this pass "cannot evaluate" would report a browser launch as a disk write.
    """
    assert unaudited_disk_write_sweep(plant(tmp_path, source)) == []


def test_a_module_held_in_a_local_variable_now_resolves(tmp_path: Path) -> None:
    """Round 3 named this as a gap; it is cheap to close once bindings are scoped."""
    root = plant(
        tmp_path,
        "import io\ndef leak(p: str, body: str) -> None:\n"
        "    mod = io\n"
        '    mod.open(p, "w").write(body)\n',
        name="held.py",
    )
    assert "io.open(mode='w')" in details(unaudited_disk_write_sweep(root))


#: Shapes the disk-write guard still does not catch. Each is named in its "Does not catch"
#: list, and each is asserted here to really be missed - the list is the claim, so it has to
#: be wrong in neither direction.
DOCUMENTED_WRITE_GAPS: dict[str, str] = {
    "returned_from_a_function": (
        "import os\n"
        "def pick() -> object:\n    return os.write\n"
        "def leak(fd: int, body: bytes) -> None:\n    pick()(fd, body)\n"
    ),
    "inside_a_data_structure": (
        'import os\ndef leak(fd: int, body: bytes) -> None:\n    {"w": os.write}["w"](fd, body)\n'
    ),
    "instance_attribute": (
        "import os\n"
        "class W:\n"
        "    def __init__(self) -> None:\n        self.handler = os.write\n"
        "    def leak(self, fd: int, body: bytes) -> None:\n        self.handler(fd, body)\n"
    ),
    "getattr_chain": (
        'import os\ndef leak(fd: int, body: bytes) -> None:\n    getattr(os, "write")(fd, body)\n'
    ),
    "unnamed_constructor": (
        'import sqlite3\ndef dump(p: str) -> None:\n    sqlite3.connect("cache.db").close()\n'
    ),
}


@pytest.mark.parametrize(("name", "source"), sorted(DOCUMENTED_WRITE_GAPS.items()))
def test_each_documented_gap_is_really_a_gap(tmp_path: Path, name: str, source: str) -> None:
    assert unaudited_disk_write_sweep(plant(tmp_path, source, name=f"{name}.py")) == [], (
        f"{name} is now caught; move it out of the guard's 'Does not catch' list"
    )


#: Bindings that are ordinary Python and are *not* a plain `name = module.attr` at the top
#: of a scope. Each was found by probing the scope rewrite rather than by a reviewer, and
#: each is caught: they are the shapes where getting scoping wrong shows up first.
SCOPE_SHAPES: dict[str, tuple[str, int]] = {
    "walrus": (
        "import os\n"
        "def leak(fd: int, body: bytes) -> None:\n"
        "    if (writer := os.write) is not None:\n"
        "        writer(fd, body)\n",
        4,
    ),
    "global_declaration": (
        "import os\n"
        "_writer = None\n"
        "def install() -> None:\n"
        "    global _writer\n"
        "    _writer = os.write\n"
        "def leak(fd: int, body: bytes) -> None:\n"
        "    _writer(fd, body)\n",
        7,
    ),
    "class_attribute_from_inside_its_own_class": (
        "import os\n"
        "class W:\n"
        "    writer = os.write\n"
        "    def leak(self, fd: int, body: bytes) -> None:\n"
        "        W.writer(fd, body)\n",
        5,
    ),
}


@pytest.mark.parametrize(("name", "case"), sorted(SCOPE_SHAPES.items()))
def test_a_binding_made_any_ordinary_way_still_resolves(
    tmp_path: Path, name: str, case: tuple[str, int]
) -> None:
    """Scoping must not become a way to lose writes it used to catch.

    The class case is the one that bites: a method calling `W.writer(...)` is *inside* the
    class it names, so registering the class only after walking its body resolved the call
    from outside the class and reported nothing.
    """
    source, line = case
    violations = unaudited_disk_write_sweep(plant(tmp_path, source, name=f"{name}.py"))
    assert [v.line for v in violations] == [line]


# --- R-ARCH-006: `build_client` is the only supported way to get an HTTP client -------------

UNGUARDED_CLIENT = (
    "import httpx\n\n\ndef fetch(url: str) -> None:\n    httpx.Client().get(url)\n",
    "import httpx\n\n\nasync def fetch(u: str) -> None:\n    await httpx.AsyncClient().get(u)\n",
    "from httpx import Client\n\n\ndef fetch(url: str) -> None:\n    Client().get(url)\n",
    "from httpx import AsyncClient as AC\n\n\ndef fetch(url: str) -> None:\n    AC()\n",
    "import httpx as h\n\n\ndef fetch(url: str) -> None:\n    h.Client()\n",
    "import httpx\n\n\n_ctor = httpx.Client\n\n\ndef fetch(url: str) -> None:\n    _ctor()\n",
)


@pytest.mark.parametrize("source", UNGUARDED_CLIENT, ids=range(len(UNGUARDED_CLIENT)))
def test_an_http_client_built_outside_the_egress_module_is_caught(
    tmp_path: Path, source: str
) -> None:
    """R-ARCH-006: `egress.py`'s docstring called `build_client` "the only supported way to
    get an HTTP client" and nothing enforced it. The allowlist transport is a wrapper, so
    a client constructed without it speaks to whatever host it is handed."""
    violations = run_all(plant(tmp_path, source), ["unwrapped-http-client"])
    assert len(violations) == 1, details(violations)
    assert "allowlist" in violations[0].detail


def test_the_egress_module_itself_may_construct_clients() -> None:
    """The allowlisted writer pattern: exactly one module, named in the guard."""
    module = SERVER_SRC / "mailweave" / "net" / "egress.py"
    assert "httpx.Client(" in module.read_text()
    assert run_all(SERVER_SRC, ["unwrapped-http-client"]) == []


def test_the_builders_own_call_sites_are_not_violations(tmp_path: Path) -> None:
    """`build_client()` is the shape the guard exists to push callers towards."""
    source = (
        "from mailweave.net import build_client\n\n\n"
        "def fetch(url: str) -> None:\n"
        "    build_client().get(url)\n"
    )
    assert run_all(plant(tmp_path, source), ["unwrapped-http-client"]) == []


def test_an_unrelated_class_named_client_is_not_a_violation(tmp_path: Path) -> None:
    """The guard resolves `httpx`; a `Client` from anywhere else is somebody else's object."""
    source = (
        "from mailweave.auth.clients import ClientDescriptor as Client\n\n\n"
        "def make() -> object:\n"
        "    return Client()\n"
    )
    assert run_all(plant(tmp_path, source), ["unwrapped-http-client"]) == []


def test_a_transport_of_our_own_is_not_a_client(tmp_path: Path) -> None:
    """Subclassing `httpx.BaseTransport` is how the allowlist is implemented, not a bypass."""
    source = (
        "import httpx\n\n\n"
        "class Recorder(httpx.BaseTransport):\n"
        "    def handle_request(self, request: httpx.Request) -> httpx.Response:\n"
        "        return httpx.Response(200)\n"
    )
    assert run_all(plant(tmp_path, source), ["unwrapped-http-client"]) == []


# --- R-SEC-017: "last binding wins" is a module-scope argument, applied module-wide -------

CLOSURE_CALLED_BEFORE_REBIND = (
    "import os\n"
    "\n"
    "\n"
    "def process(fd: int, body: bytes, reconfigure: bool) -> None:\n"
    "    def dispatch() -> None:\n"
    "        action(fd, body)\n"
    "\n"
    "    action = str.strip\n"
    "    dispatch()\n"
    "    if reconfigure:\n"
    "        action = os.write\n"
)

REBIND_BEFORE_THE_CLOSURE_IS_MADE = (
    "import os\n"
    "\n"
    "\n"
    "def process(fd: int, body: bytes) -> None:\n"
    "    writer = os.write\n"
    "\n"
    "    def dispatch() -> None:\n"
    "        writer(fd, body)\n"
    "\n"
    "    dispatch()\n"
)

MODULE_LEVEL_HELPER_ABOVE_ITS_CONSTANT = (
    "import os\n"
    "\n"
    "\n"
    "def leak(fd: int, body: bytes) -> None:\n"
    "    _writer(fd, body)\n"
    "\n"
    "\n"
    "_writer = os.write\n"
)


def test_a_closure_called_before_a_later_rebind_is_not_an_unconditional_write(
    tmp_path: Path,
) -> None:
    """R-SEC-017: at the moment `dispatch()` runs, `action` is `str.strip`.

    The rebind is textually later and conditional, and may never execute at all. The
    "last binding wins regardless of line" rule was justified by an argument about
    *module* scope - "fully bound by the time any function in that module runs" - which
    is simply not true of an enclosing function's local. A guard that reports this
    ordinary closure-then-reconfigure shape is a guard someone switches off.
    """
    violations = run_all(plant(tmp_path, CLOSURE_CALLED_BEFORE_REBIND), ["unaudited-disk-write"])
    assert violations == [], details(violations)


def test_a_free_variable_bound_before_the_closure_is_made_is_still_a_write(
    tmp_path: Path,
) -> None:
    """The other side of the same edit: fixing the false positive must not gut the guard."""
    violations = run_all(
        plant(tmp_path, REBIND_BEFORE_THE_CLOSURE_IS_MADE), ["unaudited-disk-write"]
    )
    assert len(violations) == 1, details(violations)
    assert "os.write" in violations[0].detail


def test_the_module_level_case_the_rule_was_written_for_still_resolves(tmp_path: Path) -> None:
    """A helper defined above the constant it uses: the shape "last wins" exists for."""
    violations = run_all(
        plant(tmp_path, MODULE_LEVEL_HELPER_ABOVE_ITS_CONSTANT), ["unaudited-disk-write"]
    )
    assert len(violations) == 1, details(violations)
    assert "os.write" in violations[0].detail


# --- R-SEC-019: a nested class's attribute is indexed like any other ----------------------

NESTED_CLASS_DISPATCH = (
    "import os\n"
    "\n"
    "\n"
    "class Outer:\n"
    "    class Inner:\n"
    "        handler = os.write\n"
    "\n"
    "\n"
    "def leak(fd: int, body: bytes) -> None:\n"
    "    Outer.Inner.handler(fd, body)\n"
)

THREE_LEVEL_NESTED_CLASS_DISPATCH = (
    "import os\n"
    "\n"
    "\n"
    "class A:\n"
    "    class B:\n"
    "        class C:\n"
    "            handler = os.write\n"
    "\n"
    "\n"
    "def leak(fd: int, body: bytes) -> None:\n"
    "    A.B.C.handler(fd, body)\n"
)


@pytest.mark.parametrize(
    "source", (NESTED_CLASS_DISPATCH, THREE_LEVEL_NESTED_CLASS_DISPATCH), ids=("two", "three")
)
def test_nested_class_attribute_dispatch_is_caught(tmp_path: Path, source: str) -> None:
    """R-SEC-019: `Outer.Inner` is a chained `ast.Attribute`, and the class-attribute path
    required a bare `ast.Name` receiver - which is not how a nested class is referenced."""
    violations = run_all(plant(tmp_path, source), ["unaudited-disk-write"])
    assert len(violations) == 1, details(violations)
    assert "os.write" in violations[0].detail


def test_a_nested_class_attribute_that_is_not_a_write_is_not_a_violation(
    tmp_path: Path,
) -> None:
    """Resolving more receivers must not turn ordinary code into violations."""
    source = (
        "class Outer:\n"
        "    class Inner:\n"
        "        handler = str.strip\n"
        "\n"
        "\n"
        "def clean(text: str) -> str:\n"
        "    return Outer.Inner.handler(text)\n"
    )
    assert run_all(plant(tmp_path, source), ["unaudited-disk-write"]) == []


def test_a_chained_module_attribute_is_still_resolved_as_a_module(tmp_path: Path) -> None:
    """`dbm.gnu.open` is a chained attribute too, and must keep resolving to the module."""
    source = 'import dbm.gnu\n\n\ndef cache(path: str) -> None:\n    dbm.gnu.open(path, "c")\n'
    violations = run_all(plant(tmp_path, source), ["unaudited-disk-write"])
    assert len(violations) == 1, details(violations)


# --- R-SEC-020: a dataclass field is an AnnAssign, which nothing resolved -----------------

DATACLASS_FIELD_DEFAULT = (
    "import os\n"
    "from collections.abc import Callable\n"
    "from dataclasses import dataclass, field\n"
    "\n"
    "\n"
    "@dataclass\n"
    "class Writer:\n"
    "    handler: Callable[..., int] = field(default=os.write)\n"
    "\n"
    "\n"
    "def leak(fd: int, body: bytes) -> None:\n"
    "    Writer().handler(fd, body)\n"
)

DATACLASS_BARE_DEFAULT = (
    "import os\n"
    "from collections.abc import Callable\n"
    "from dataclasses import dataclass\n"
    "\n"
    "\n"
    "@dataclass\n"
    "class Writer:\n"
    "    handler: Callable[..., int] = os.write\n"
    "\n"
    "\n"
    "def leak(fd: int, body: bytes) -> None:\n"
    "    Writer.handler(fd, body)\n"
)

ANNOTATED_MODULE_LEVEL_BINDING = (
    "import os\n"
    "from collections.abc import Callable\n"
    "\n"
    "\n"
    "_writer: Callable[..., int] = os.write\n"
    "\n"
    "\n"
    "def leak(fd: int, body: bytes) -> None:\n"
    "    _writer(fd, body)\n"
)


@pytest.mark.parametrize(
    "source",
    (DATACLASS_FIELD_DEFAULT, DATACLASS_BARE_DEFAULT, ANNOTATED_MODULE_LEVEL_BINDING),
    ids=("field_default", "bare_default", "annotated_module_binding"),
)
def test_an_annotated_binding_to_a_write_is_caught(tmp_path: Path, source: str) -> None:
    """R-SEC-020: the resolution pass filtered to `ast.Assign`, so an `ast.AnnAssign`
    target was recorded as bound-but-unreadable - indistinguishable from a value the pass
    genuinely cannot read, which is what makes it worse than a documented gap."""
    violations = run_all(plant(tmp_path, source), ["unaudited-disk-write"])
    assert len(violations) == 1, details(violations)
    assert "os.write" in violations[0].detail


def test_an_annotated_binding_to_something_harmless_is_not_a_violation(
    tmp_path: Path,
) -> None:
    source = (
        "from collections.abc import Callable\n"
        "from dataclasses import dataclass, field\n"
        "\n"
        "\n"
        "@dataclass\n"
        "class Cleaner:\n"
        "    handler: Callable[..., str] = field(default=str.strip)\n"
        "    name: str = 'cleaner'\n"
        "\n"
        "\n"
        "def clean(text: str) -> str:\n"
        "    return Cleaner().handler(text)\n"
    )
    assert run_all(plant(tmp_path, source), ["unaudited-disk-write"]) == []


def test_an_annotation_with_no_value_binds_without_resolving_to_anything(
    tmp_path: Path,
) -> None:
    """`handler: Callable` declares a name and assigns nothing; it must still shadow."""
    source = (
        "import os\n"
        "from collections.abc import Callable\n"
        "\n"
        "\n"
        "_writer = os.write\n"
        "\n"
        "\n"
        "def scrub(fd: int, body: bytes) -> None:\n"
        "    _writer: Callable[..., str]\n"
        "    _writer = str.strip\n"
        "    _writer(body.decode())\n"
    )
    assert run_all(plant(tmp_path, source), ["unaudited-disk-write"]) == []


# --- the widened resolution must stay passable by ordinary code ---------------------------

ORDINARY_CODE_WITH_TWO_REAL_WRITES = '''
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class Formatter:
    """A dataclass field default that is not a write, reached both ways."""

    render: Callable[..., str] = field(default=str.strip)
    fallback: Callable[..., str] = str.lower
    label: str = "formatter"


class Registry:
    """A nested class whose attributes are ordinary callables."""

    class Text:
        clean = str.strip
        upper = str.upper

    class Numbers:
        parse = int


def tidy(values: list[str]) -> list[str]:
    return [Registry.Text.clean(value) for value in values]


def shout(values: list[str]) -> list[str]:
    return [Registry.Text.upper(value) for value in values]


def render_all(rows: list[str]) -> list[str]:
    formatter = Formatter()
    return [formatter.render(row) for row in rows]


def make_reporter(prefix: str) -> Callable[[str], str]:
    write = "{}: {}".format

    def report(message: str) -> str:
        return write(prefix, message)

    return report


def reconfigurable(payload: str, switch: bool) -> str:
    def apply() -> str:
        return transform(payload)

    transform = str.strip
    first = apply()
    if switch:
        transform = str.upper
    return first


def duplicate(rows: list[str]) -> list[str]:
    copy = list.copy
    return copy(rows)


def summarise(rows: list[str]) -> str:
    join = ", ".join
    return join(rows)


class Session:
    def __init__(self, path: str) -> None:
        self.path = path

    def open(self) -> str:
        return self.path


def read_config(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def persist_token(path: str, blob: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT)
    os.write(fd, blob)


def archive(src: str, dst: str) -> None:
    shutil.copy(src, dst)


class BaseRenderer:
    """A base class whose attributes are ordinary callables (R-SEC-024's widening)."""

    clean = str.strip
    write = "{}: {}".format


class Renderer(BaseRenderer):
    """Inherits both, overrides neither, and calls the inherited names."""

    def describe(self, key: str, value: str) -> str:
        return Renderer.write(key, self.clean(value))


class Loud(BaseRenderer):
    clean = str.upper


def shout_all(rows: list[str]) -> list[str]:
    return [Loud.clean(row) for row in rows]


def label(rows: list[str]) -> list[str]:
    header = trailer = "-".join
    first, second = str.strip, str.upper
    return [header([first(row), second(row), trailer([row])]) for row in rows]
'''


def test_the_widened_resolution_finds_no_false_positives_in_ordinary_code(
    tmp_path: Path,
) -> None:
    """R-SEC's own sweep shape, extended to the three paths round 5 widened.

    Nested classes, dataclass fields and closures are now resolved, which is exactly the
    machinery that can start reporting innocent code. So the sweep reuses the names the
    guard cares about (`write`, `copy`, `open`, `render`, `clean`) across a dataclass, a
    two-level nested class, a closure that is reconfigured after it is called, a method
    named `open`, and a `with open(...)` read - and contains exactly three real writes,
    which must be the only things reported.

    Round 6 adds the two shapes it widened: a class hierarchy whose inherited attribute is
    called `write` and whose subclass overrides `clean` (R-SEC-024), and chained and tuple
    assignments binding names the guard resolves (R-SEC-023). Both are the machinery most
    likely to start firing on ordinary code, which is why they are in the sweep and not
    only in their own tests.
    """
    violations = unaudited_disk_write_sweep(
        plant(tmp_path, ORDINARY_CODE_WITH_TWO_REAL_WRITES, name="ordinary.py")
    )
    reported = sorted(v.detail.split(" in server code")[0] for v in violations)
    assert reported == ["os.open", "os.write", "shutil.copy"], details(violations)


# --- the residues round 5 leaves, pinned so the claim cannot drift ------------------------

#: Shapes the widened resolution still misses. Each is named in the guard's "Does not
#: catch" list; each is asserted here to really be missed, so the list stays wrong in
#: neither direction (the discipline `test_each_documented_gap_is_really_a_gap` applies to
#: the round 1-4 gaps, extended to round 5's and now round 6's `default_factory=lambda`,
#: which is R-SEC-025 - left open this round and stated rather than implied fixed).
ROUND_FIVE_WRITE_GAPS: dict[str, str] = {
    "instance_held_in_a_variable": (
        "import os\n"
        "from collections.abc import Callable\n"
        "from dataclasses import dataclass\n"
        "@dataclass\n"
        "class Writer:\n"
        "    handler: Callable[..., int] = os.write\n"
        "def leak(fd: int, body: bytes) -> None:\n"
        "    w = Writer()\n"
        "    w.handler(fd, body)\n"
    ),
    "lambda_default_factory": (
        "import os\n"
        "from collections.abc import Callable\n"
        "from dataclasses import dataclass, field\n"
        "@dataclass\n"
        "class Writer:\n"
        "    handler: Callable[..., int] = field(default_factory=lambda: os.write)\n"
        "def leak(fd: int, body: bytes) -> None:\n"
        "    Writer().handler(fd, body)\n"
    ),
    "closure_over_a_later_binding": (
        "import os\n"
        "def process(fd: int, body: bytes) -> None:\n"
        "    def dispatch() -> None:\n"
        "        writer(fd, body)\n"
        "    writer = os.write\n"
        "    dispatch()\n"
    ),
}


@pytest.mark.parametrize(("name", "source"), sorted(ROUND_FIVE_WRITE_GAPS.items()))
def test_each_round_five_gap_is_really_a_gap(tmp_path: Path, name: str, source: str) -> None:
    assert unaudited_disk_write_sweep(plant(tmp_path, source, name=f"{name}.py")) == [], (
        f"{name} is now caught; move it out of the guard's 'Does not catch' list"
    )


def test_the_disk_write_guard_names_the_residues_round_five_leaves() -> None:
    """R-SEC-017's fix trades a false positive for a false negative; both are stated."""
    doc = normalised(unaudited_disk_write_sweep.__doc__)
    assert "Outer.Inner.handler" in doc
    assert "field(default=os.write)" in doc
    gap = doc.split("Does not catch:", 1)[1]
    assert "instance held in a variable" in gap
    assert "free variable is bound after the closure is created" in gap


def test_the_disk_write_guard_names_what_round_six_widened_and_what_it_left() -> None:
    """R-SEC-023/024 caught two shapes; R-SEC-025 is left open and now says so.

    The `default_factory=lambda` bullet is the one that matters here: round 5's handoff
    claimed the guard "learns `field(default_factory=...)`", which holds for a form that
    raises `TypeError` at construction and not for the only form that works. The claim is
    corrected in the guard's own gap list rather than restated, and
    `test_each_round_five_gap_is_really_a_gap` runs the lambda form against the guard.
    """
    doc = normalised(unaudited_disk_write_sweep.__doc__)
    caught, gap = doc.split("Does not catch:", 1)
    assert "chained** assignment" in caught or "chained assignment" in caught
    assert "inheritance" in caught
    assert "another module" in gap
    assert "field(default_factory=lambda: os.write)" in gap
    assert "starred unpacking is not read" in caught


def test_the_fold_documentation_names_all_four_indirection_shapes() -> None:
    """R-SEC-018: the bullet named "a variable" and three more shapes defeat the fold."""
    from tools.guards import sweeps

    doc = normalised(sweeps.__doc__)
    gap = doc.split("What the fold does not read", 1)[1]
    for shape in ("class or instance attribute", "container element", "function return value"):
        assert shape in gap, f"the fold's gap list does not name {shape!r}"


#: R-SEC-018's four probes: each builds `ground_truth/cases.json` through one indirection.
FOLD_INDIRECTION_SHAPES: dict[str, str] = {
    "variable": '_p = "ground"\n_q = _p + "_truth/cases.json"\n',
    "class_attribute": (
        'class Config:\n    SUFFIX = "_truth/cases.json"\n_q = "ground" + Config.SUFFIX\n'
    ),
    "dict_element": ('_PARTS = {"s": "_truth/cases.json"}\n_q = "ground" + _PARTS["s"]\n'),
    "list_element": ('_PARTS = ["_truth/cases.json"]\n_q = "ground" + _PARTS[0]\n'),
    "function_return": (
        'def suffix() -> str:\n    return "_truth/cases.json"\n_q = "ground" + suffix()\n'
    ),
}


@pytest.mark.parametrize(("name", "source"), sorted(FOLD_INDIRECTION_SHAPES.items()))
def test_each_indirection_shape_really_defeats_the_fold(
    tmp_path: Path, name: str, source: str
) -> None:
    """The documentation is only honest if the shapes it names are the shapes that get past.

    If a future fold starts following one of these, this fails and the bullet is corrected
    with it - which is the direction the round-1 finding was about.
    """
    root = plant(tmp_path, source, name=f"fold_{name}.py")
    assert run_all(root, ["ground-truth-isolation"]) == []


# --- R-SEC-022: the class is `httpx.Client` whatever module path reaches it ----------------

#: Each of these builds the *same class object* as `httpx.Client` - verified at runtime by
#: `test_the_private_submodule_path_is_the_same_class_object` below, so the guard's claim
#: rests on a fact about `httpx` rather than on a fact about this test.
PRIVATE_SUBMODULE_CLIENTS: dict[str, str] = {
    "module_alias": "import httpx._client as hc\n\n\ndef fetch() -> None:\n    hc.Client()\n",
    "dotted_attribute": (
        "import httpx._client\n\n\ndef fetch() -> None:\n    httpx._client.Client()\n"
    ),
    "from_import": (
        "from httpx._client import AsyncClient\n\n\ndef fetch() -> None:\n    AsyncClient()\n"
    ),
    "rebound_from_submodule": (
        "import httpx._client as hc\n\n\n_ctor = hc.Client\n\n\ndef fetch() -> None:\n    _ctor()\n"
    ),
}


@pytest.mark.parametrize(("name", "source"), sorted(PRIVATE_SUBMODULE_CLIENTS.items()))
def test_a_client_built_through_a_private_httpx_submodule_is_caught(
    tmp_path: Path, name: str, source: str
) -> None:
    """R-SEC-022: `import httpx._client as hc; hc.Client()`, one ordinary line.

    The round-5 guard matched the module string `"httpx"` exactly, and `Client` is
    *defined* in `httpx._client`, so this built the identical class with a real
    `httpx.HTTPTransport` and produced no violation at all.
    """
    violations = run_all(plant(tmp_path, source, name=f"{name}.py"), ["unwrapped-http-client"])
    assert len(violations) == 1, details(violations)
    assert "allowlist" in violations[0].detail


def test_the_private_submodule_path_is_the_same_class_object() -> None:
    """Why the guard may treat `httpx._client.Client` as `httpx.Client`: it is that class.

    Without this the widening would rest on an assumption about another library's layout.
    """
    import httpx
    import httpx._client

    assert httpx._client.Client is httpx.Client
    assert httpx._client.AsyncClient is httpx.AsyncClient


def test_a_client_class_from_a_package_merely_named_like_httpx_is_not_caught(
    tmp_path: Path,
) -> None:
    """The widening is to `httpx.*`, not to anything whose name contains `httpx`."""
    source = "import vendor.httpx_compat as compat\n\n\ndef fetch() -> None:\n    compat.Client()\n"
    assert run_all(plant(tmp_path, source), ["unwrapped-http-client"]) == []


# --- R-SEC-023: chained and tuple assignment are ordinary bindings -------------------------

#: Round 5's third resolution pass required `len(statement.targets) == 1`, so both guards
#: lost every name bound this way - recorded as bound-but-unresolvable, which is what an
#: unreadable value looks like, so nothing distinguished them.
MULTI_TARGET_BINDINGS: dict[str, tuple[str, str]] = {
    "chained_write": (
        "import os\n\n\ndef leak(fd: int, body: bytes) -> None:\n"
        "    a = b = os.write\n    b(fd, body)\n",
        "unaudited-disk-write",
    ),
    "chained_write_three_targets": (
        "import os\n\n\ndef leak(fd: int, body: bytes) -> None:\n"
        "    a = b = c = os.write\n    c(fd, body)\n",
        "unaudited-disk-write",
    ),
    "chained_client": (
        "import httpx\n\n\ndef fetch() -> None:\n    a = b = httpx.Client\n    b()\n",
        "unwrapped-http-client",
    ),
    "tuple_write": (
        "import os\n\n\ndef leak(fd: int, body: bytes) -> None:\n"
        "    a, b = os.write, str.upper\n    a(fd, body)\n",
        "unaudited-disk-write",
    ),
    "tuple_client": (
        "import httpx\n\n\ndef fetch() -> None:\n"
        "    ctor, other = httpx.Client, str.upper\n    ctor()\n",
        "unwrapped-http-client",
    ),
}


@pytest.mark.parametrize(("name", "case"), sorted(MULTI_TARGET_BINDINGS.items()))
def test_a_multi_target_assignment_resolves_like_any_other(
    tmp_path: Path, name: str, case: tuple[str, str]
) -> None:
    """R-SEC-023, across both guards, because the gap was in the engine they share."""
    source, guard = case
    violations = run_all(plant(tmp_path, source, name=f"{name}.py"), [guard])
    assert len(violations) == 1, details(violations)


def test_the_other_name_in_a_tuple_assignment_is_not_confused_with_the_write(
    tmp_path: Path,
) -> None:
    """Element-wise means element-wise: calling the *other* name is not a write.

    A pairing that resolved every name to every value would report this, which is worse
    than the gap it replaced.
    """
    source = (
        "import os\n\n\ndef tidy(value: str) -> str:\n"
        "    a, b = os.write, str.upper\n    return b(value)\n"
    )
    assert run_all(plant(tmp_path, source), ["unaudited-disk-write"]) == []


def test_starred_unpacking_is_not_resolved_and_is_documented_that_way(
    tmp_path: Path,
) -> None:
    """The gap the tuple fix deliberately leaves, named in the guard's own docstring."""
    source = (
        "import os\n\n\ndef leak(fd: int, body: bytes) -> None:\n"
        "    a, *rest = os.write, str.upper\n    a(fd, body)\n"
    )
    assert run_all(plant(tmp_path, source), ["unaudited-disk-write"]) == []
    assert "starred unpacking is not read" in normalised(unaudited_disk_write_sweep.__doc__)


# --- R-SEC-024: an inherited attribute is reached by the same expression -------------------

INHERITED_ATTRIBUTE_CALLS: dict[str, tuple[str, str]] = {
    "class_call": (
        "import os\n\n\nclass Base:\n    handler = os.write\n\n\nclass Sub(Base):\n    pass\n\n\n"
        "def leak(fd: int, body: bytes) -> None:\n    Sub.handler(fd, body)\n",
        "unaudited-disk-write",
    ),
    "instance_call": (
        "import os\n\n\nclass Base:\n    handler = os.write\n\n\nclass Sub(Base):\n    pass\n\n\n"
        "def leak(fd: int, body: bytes) -> None:\n    Sub().handler(fd, body)\n",
        "unaudited-disk-write",
    ),
    "two_levels": (
        "import os\n\n\nclass Root:\n    handler = os.write\n\n\nclass Middle(Root):\n"
        "    pass\n\n\nclass Leaf(Middle):\n    pass\n\n\n"
        "def leak(fd: int, body: bytes) -> None:\n    Leaf.handler(fd, body)\n",
        "unaudited-disk-write",
    ),
    "inherited_client": (
        "import httpx\n\n\nclass Base:\n    ctor = httpx.Client\n\n\nclass Sub(Base):\n"
        "    pass\n\n\ndef fetch() -> None:\n    Sub.ctor()\n",
        "unwrapped-http-client",
    ),
}


@pytest.mark.parametrize(("name", "case"), sorted(INHERITED_ATTRIBUTE_CALLS.items()))
def test_an_inherited_class_attribute_resolves_to_the_base_that_declares_it(
    tmp_path: Path, name: str, case: tuple[str, str]
) -> None:
    """R-SEC-024: only the class's own body was read, so `Sub.handler` resolved to nothing."""
    source, guard = case
    violations = run_all(plant(tmp_path, source, name=f"{name}.py"), [guard])
    assert len(violations) == 1, details(violations)


def test_a_subclass_that_overrides_the_attribute_uses_its_own_value(tmp_path: Path) -> None:
    """Own body wins over a base, which is Python's own answer and not a special case."""
    source = (
        "import os\n\n\nclass Base:\n    handler = os.write\n\n\nclass Sub(Base):\n"
        "    handler = str.upper\n\n\ndef tidy(value: str) -> str:\n"
        "    return Sub.handler(value)\n"
    )
    assert run_all(plant(tmp_path, source), ["unaudited-disk-write"]) == []


def test_a_base_class_from_another_module_is_a_documented_gap(tmp_path: Path) -> None:
    """Inheritance is followed within one file; the guard says so rather than implying more."""
    source = (
        "from vendor.base import Writer\n\n\nclass Sub(Writer):\n    pass\n\n\n"
        "def leak(fd: int, body: bytes) -> None:\n    Sub.handler(fd, body)\n"
    )
    assert run_all(plant(tmp_path, source), ["unaudited-disk-write"]) == []
    assert "another module" in normalised(unaudited_disk_write_sweep.__doc__)


# --- the http-client guard's own gap list, held to the same standard as its sibling --------

#: The shapes the seventh guard still misses. R-SEC-024's documentation half: round 5's
#: gap list was a strict subset of what its shared mechanism actually misses, and the two
#: instance shapes below are named in the disk-write guard's list and were not in this one.
HTTP_CLIENT_GAPS: dict[str, str] = {
    "instance_attribute": (
        "import httpx\n\n\nclass Holder:\n    def __init__(self) -> None:\n"
        "        self.ctor = httpx.Client\n\n    def go(self) -> object:\n"
        "        return self.ctor()\n"
    ),
    "instance_held_in_a_variable": (
        "import httpx\n\n\nclass Holder:\n    ctor = httpx.Client\n\n\n"
        "def fetch() -> object:\n    holder = Holder()\n    return holder.ctor()\n"
    ),
    "dict_element": (
        'import httpx\n\n\n_CTORS = {"c": httpx.Client}\n\n\ndef fetch() -> object:\n'
        '    return _CTORS["c"]()\n'
    ),
    "factory_return": (
        "import httpx\n\n\ndef pick() -> object:\n    return httpx.Client\n\n\n"
        "def fetch() -> object:\n    return pick()()\n"
    ),
    "getattr": (
        'import httpx\n\n\ndef fetch() -> object:\n    return getattr(httpx, "Client")()\n'
    ),
    "same_named_subclass": (
        "import httpx\n\n\nclass Client(httpx.Client):\n    pass\n\n\n"
        "def fetch() -> object:\n    return Client()\n"
    ),
}


@pytest.mark.parametrize(("name", "source"), sorted(HTTP_CLIENT_GAPS.items()))
def test_each_documented_http_client_gap_is_really_a_gap(
    tmp_path: Path, name: str, source: str
) -> None:
    """A gap list is only honest if the shapes it names are the shapes that get past.

    If a later round catches one of these, this fails and the list is corrected with it.
    """
    assert run_all(plant(tmp_path, source, name=f"{name}.py"), ["unwrapped-http-client"]) == [], (
        f"{name} is now caught; move it out of the guard's 'Does not catch' list"
    )


def test_the_http_client_guard_names_what_it_resolves_and_what_it_does_not() -> None:
    """R-SEC-024's documentation half, and R-SEC-022's residue after the fix."""
    doc = normalised(unwrapped_http_client_sweep.__doc__)
    assert "httpx._client" in doc
    assert "class attribute" in doc
    caught, gap = doc.split("Does not catch", 1)
    assert "chained assignment" in caught
    for shape in (
        "instance** attribute",
        "instance held in a variable",
        "getattr",
        "factory function",
        "subclass of `httpx.Client`",
        "another module",
    ):
        assert shape in gap, f"the guard's gap list does not name {shape!r}"


# --- R-SEC-026: a comprehension and a lambda each open a scope -------------------------------

#: R-SEC's three reproductions, verbatim in shape. Each binds `os` to something that is not
#: the module - a comprehension variable, a dict-comprehension variable, a lambda parameter -
#: and then calls `.replace` on it. `os.replace` is a real entry in `_WRITE_QUALIFIED`, so
#: before round 7 all three resolved through the module import and reported a disk write in
#: code that touches no file.
COMPREHENSION_SHADOWING: dict[str, str] = {
    "list_comprehension": (
        "import os\n\n\n"
        "def normalise(entries: list[str]) -> list[str]:\n"
        '    return [os.replace("Windows", "windows") for os in entries]\n'
    ),
    "dict_comprehension": (
        "import os\n\n\n"
        "def normalise(entries: list[str]) -> dict[str, str]:\n"
        '    return {os: os.replace("Windows", "windows") for os in entries}\n'
    ),
    "set_comprehension": (
        "import os\n\n\n"
        "def normalise(entries: list[str]) -> set[str]:\n"
        '    return {os.replace("Windows", "windows") for os in entries}\n'
    ),
    "generator_expression": (
        "import os\n\n\n"
        "def normalise(entries: list[str]) -> object:\n"
        '    return (os.replace("Windows", "windows") for os in entries)\n'
    ),
    "lambda_parameter": (
        'import os\n\n\nnormalise = lambda os: os.replace("Windows", "windows")\n'
    ),
}


@pytest.mark.parametrize(("name", "source"), sorted(COMPREHENSION_SHADOWING.items()))
def test_a_comprehension_or_lambda_local_shadows_the_module_it_reuses_the_name_of(
    tmp_path: Path, name: str, source: str
) -> None:
    """R-SEC-026: ordinary Python scoping, respected rather than approximated.

    A comprehension variable and a lambda parameter each introduce a scope. Round 6's pass
    visited only `ast.stmt` nodes when collecting bindings, so neither could shadow an
    outer name and a string called `os` inherited the module import. A guard that reports
    innocent code is one the next engineer switches off, which is why R-SEC filed two false
    positives at bypass weight.
    """
    assert run_all(plant(tmp_path, source, name=f"{name}.py"), ["unaudited-disk-write"]) == [], (
        f"{name}: a shadowed local was resolved through the outer import"
    )


def test_the_same_shadowing_no_longer_misleads_the_http_client_guard(tmp_path: Path) -> None:
    """The two guards share the resolution engine, so the false positive was shared too."""
    source = (
        "import httpx\n\n\n"
        "def names(clients: list[str]) -> list[str]:\n"
        "    return [httpx.Client() for httpx in clients]\n"
    )
    assert run_all(plant(tmp_path, source), ["unwrapped-http-client"]) == []


def test_an_unshadowed_write_inside_a_comprehension_is_still_caught(tmp_path: Path) -> None:
    """The control R-SEC ran beside the reproduction: this is not a blanket suppression.

    Without it the fix would be indistinguishable from switching the guard off inside every
    comprehension in the codebase, which is the far more likely way to make the three cases
    above pass.
    """
    source = (
        "import os\n\n\n"
        "def move(pairs: list[tuple[str, str]]) -> list[None]:\n"
        "    return [os.replace(src, dst) for src, dst in pairs]\n"
    )
    violations = run_all(plant(tmp_path, source), ["unaudited-disk-write"])
    assert violations, "a genuine os.replace inside a comprehension must still be caught"
    assert "os.replace" in details(violations)


def test_a_lambda_that_does_not_shadow_still_resolves_through_the_import(tmp_path: Path) -> None:
    """The lambda half of the same control."""
    source = "import os\n\n\nmove = lambda src, dst: os.replace(src, dst)\n"
    assert "os.replace" in details(run_all(plant(tmp_path, source), ["unaudited-disk-write"]))


def test_the_outermost_iterable_is_read_in_the_scope_the_comprehension_sits_in(
    tmp_path: Path,
) -> None:
    """Python evaluates the first iterable outside the comprehension, and so does this pass.

    Binding the target before reading the iterable would have been the simpler fix and
    would have hidden a real write in the one expression the comprehension's own scope does
    not cover.
    """
    source = (
        "import os\n\n\n"
        "def wipe(paths: list[str]) -> list[str]:\n"
        '    return [entry for entry in os.replace("a", "b")]\n'
    )
    assert "os.replace" in details(run_all(plant(tmp_path, source), ["unaudited-disk-write"]))


# --- R-SEC-027: an English word is not an open mode ------------------------------------------

#: R-SEC's reproduction: a domain class with its own `.open(mode)` that has nothing to do
#: with files. The receiver does not resolve, so the guard falls back to reading position 0
#: as a mode - and round 6 read it as `_WRITE_MODE_CHARS & set(mode)`, i.e. any of `w`, `a`,
#: `x` or `+` anywhere in the string. Most English words contain one.
NON_FILE_OPEN_WORDS = ("readonly", "manual", "active", "auto", "exclusive", "append-only")


@pytest.mark.parametrize("word", NON_FILE_OPEN_WORDS)
def test_an_english_word_in_the_mode_position_is_not_a_write(tmp_path: Path, word: str) -> None:
    """R-SEC-027: "readonly" contains an `a`, and was reported as a disk write."""
    source = (
        "class Parser:\n"
        "    def open(self, mode: str) -> None:\n"
        "        return None\n\n\n"
        "def go() -> None:\n"
        f'    Parser().open("{word}")\n'
    )
    assert run_all(plant(tmp_path, source), ["unaudited-disk-write"]) == [], (
        f"{word!r} is an ordinary word, not an open mode"
    )


@pytest.mark.parametrize("mode", ["w", "a", "x", "wb", "r+", "xb+", "rb+t"])
def test_a_real_write_mode_on_an_unresolved_receiver_is_still_caught(
    tmp_path: Path, mode: str
) -> None:
    """The control: narrowing the fallback must not switch it off.

    Every mode here is a real one, and `Path(...).open("w")` reached through a receiver the
    pass cannot resolve is the shape R-SEC-001 (d) filed in the first place.
    """
    source = f'from pathlib import Path\n\n\ndef go(p: Path) -> None:\n    p.open("{mode}")\n'
    assert details(run_all(plant(tmp_path, source), ["unaudited-disk-write"])), (
        f"mode {mode!r} is a write and must still be reported"
    )


@pytest.mark.parametrize("mode", ["r", "rb", "rt"])
def test_a_real_read_mode_is_still_not_a_write(tmp_path: Path, mode: str) -> None:
    source = f'from pathlib import Path\n\n\ndef go(p: Path) -> None:\n    p.open("{mode}")\n'
    assert run_all(plant(tmp_path, source), ["unaudited-disk-write"]) == []


def test_an_unreadable_mode_is_still_reported_rather_than_assumed_to_be_a_read(
    tmp_path: Path,
) -> None:
    """The narrowing applies to constants, not to expressions this pass cannot evaluate."""
    source = "from pathlib import Path\n\n\ndef go(p: Path, mode: str) -> None:\n    p.open(mode)\n"
    assert "computed at runtime" in details(
        run_all(plant(tmp_path, source), ["unaudited-disk-write"])
    )


# --- R-SEC-028: the ground-truth guard compares words, not substrings ------------------------

#: Ordinary English identifiers that merely contain a token as a substring. R-SEC reported
#: two; the rest are the same collision in other words.
GROUND_TRUTH_COLLISIONS = (
    "is_manifestly_invalid",
    "harnessed_load",
    "manifestation_count",
    "unharnessed",
)


@pytest.mark.parametrize("identifier", GROUND_TRUTH_COLLISIONS)
def test_an_english_word_containing_a_token_is_not_a_ground_truth_reference(
    tmp_path: Path, identifier: str
) -> None:
    """R-SEC-028: "manifestly" contains "manifest" and "harnessed" contains "harness"."""
    root = plant(
        tmp_path, f"def check() -> bool:\n    {identifier} = True\n    return {identifier}\n"
    )
    assert ground_truth_sweep(root) == [], f"{identifier!r} does not name ground-truth material"


@pytest.mark.parametrize(
    "identifier",
    ["seed_map", "seedMap", "load_ground_truth", "case_manifest", "GroundTruth", "harness_client"],
)
def test_an_identifier_whose_words_name_ground_truth_is_still_caught(
    tmp_path: Path, identifier: str
) -> None:
    """The control: the narrowing must not make the guard blind to the real thing."""
    root = plant(
        tmp_path, f"def load() -> object:\n    {identifier} = 1\n    return {identifier}\n"
    )
    assert ground_truth_sweep(root), (
        f"{identifier!r} names ground-truth material and must be caught"
    )


def test_the_residual_word_boundary_collision_is_declared_rather_than_hidden() -> None:
    """`harness_the_energy` contains the whole word `harness` and is still reported.

    A word-boundary rule cannot tell a real reference from a sentence that happens to use
    the word, and the rule that could would be a list of allowed phrasings. The guard says
    so in its own docstring rather than implying a precision it does not have.
    """
    from tools.guards.sweeps import _names_ground_truth

    assert _names_ground_truth("harness_the_energy") == "harness"
    assert "Still flagged, by design" in (_names_ground_truth.__doc__ or "")


# -- what the guards actually sweep (M1) --------------------------------------------------
#
# `orivra/src` arrived as a second server-side source tree and the runner's default target
# was `server/src` alone, so three sweeps that name "the source" covered a subset of it. The
# fix derives the trees from the workspace; these tests hold the derivation to the two things
# that make it safe - that it grows with the workspace, and that its one exclusion stays one.


def test_the_guards_sweep_every_workspace_member_that_runs_server_side() -> None:
    from tools.guards.__main__ import guarded_trees, workspace_members

    swept = {tree.parent.name for tree in guarded_trees()}
    expected = {
        member
        for member in workspace_members()
        if member != "harness" and (REPO_ROOT / member / "src").is_dir()
    }
    assert swept == expected
    assert "orivra" in swept, "the Orivra source tree runs with the server credential"


def test_the_harness_is_the_only_tree_the_guards_do_not_sweep() -> None:
    """It owns the destructive scope literal by design; the sweep exists to keep that
    literal out of the trees that must never hold it. A second exclusion would have to
    change this test with it."""
    from tools.guards.__main__ import DESTRUCTIVE_CAPABLE

    assert frozenset({"harness"}) == DESTRUCTIVE_CAPABLE


def test_every_swept_tree_is_clean_today() -> None:
    from tools.guards.__main__ import guarded_trees

    for tree in guarded_trees():
        assert run_all(tree) == [], tree


def test_the_standing_sweeps_read_every_workspace_source_tree() -> None:
    """`tests/fixtures/source_trees.TREES` is the other sweeper, and it listed two of three.

    The guard runner's trees were derived from the workspace at M1; this one was not, so
    every standing-cycle sweep silently stopped covering a third of the repository - including
    `test_no_module_renders_a_validation_error_any_other_way`, which exists so R-SEC-043
    cannot recur. It recurred, in `orivra/surface/server.py`, and this is why nothing caught
    it (review finding R-M1-015).
    """
    from tests.fixtures.source_trees import TREES
    from tools.guards.__main__ import workspace_members

    swept = {tree.parent.name for tree in TREES}
    assert swept == {
        member for member in workspace_members() if (REPO_ROOT / member / "src").is_dir()
    }
    assert "orivra" in swept


# --- the model host is setup-time only (AD D.8, ADV-210) ------------------------------------


def test_a_module_naming_the_model_host_is_caught(tmp_path: Path) -> None:
    root = plant(tmp_path, 'HOST = "huggingface.co"\n')
    assert model_host_sweep(root)


def test_the_byte_string_spelling_of_the_model_host_is_caught(tmp_path: Path) -> None:
    # R-SEC-008, one guard later: the forbidden thing is the text, not the spelling.
    root = plant(tmp_path, '_h = b"huggingface.co".decode()\n')
    assert model_host_sweep(root)


def test_importing_the_provisioner_is_caught(tmp_path: Path) -> None:
    root = plant(tmp_path, "from mailweave.models.provision import pin\n")
    assert "import graph" in details(model_host_sweep(root))


def test_the_provisioner_and_constants_may_name_the_host(tmp_path: Path) -> None:
    root = tmp_path / "src"
    package = root / "mailweave" / "models"
    package.mkdir(parents=True)
    (package / "provision.py").write_text('HOST = "huggingface.co"\n', encoding="utf-8")
    (root / "mailweave" / "constants.py").write_text(
        'MODEL_HOST = "huggingface.co"\n', encoding="utf-8"
    )
    assert model_host_sweep(root) == []


# --- no listening socket (SEC-07's third clause) ---------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "import http.server\n",
        "import socketserver\n",
        "from http.server import HTTPServer\n",
        "import uvicorn\n",
        "from fastapi import FastAPI\n",
        "import aiohttp.web\n",
        'sock.bind(("127.0.0.1", 8080))\n',
        "sock.listen(5)\n",
        "conn, addr = sock.accept()\n",
        "await asyncio.start_server(handle, '0.0.0.0', 9000)\n",
        "server.serve_forever()\n",
        "web.run_app(app)\n",
    ],
)
def test_a_listening_socket_in_server_code_is_caught(tmp_path: Path, source: str) -> None:
    """AD D.1 puts this server on stdio: no port, no bind, nothing for a scanner to find.

    The regression SEC-07 guards against is not a misconfiguration, it is a line of code - the
    health endpoint, the metrics exporter, the local debugging server somebody adds and does
    not remove.
    """
    root = plant(tmp_path, source)
    assert listening_socket_sweep(root), source


def test_the_loopback_consent_receiver_is_allowlisted(tmp_path: Path) -> None:
    """`mailweave auth login` binds 127.0.0.1 for one consent, and is a setup-time command.

    The same distinction D.8 draws for the model host, and the same allowlist shape. A guard
    that flagged it would be turned off within a round, which is worse than one that exempts
    it and says why.
    """
    module = tmp_path / "mailweave" / "auth"
    module.mkdir(parents=True)
    (module / "consent.py").write_text(
        "from http.server import HTTPServer\n"
        'def receive() -> None:\n    HTTPServer(("127.0.0.1", 0), None).serve_forever()\n',
        encoding="utf-8",
    )
    assert listening_socket_sweep(tmp_path) == []


def test_the_receivers_names_are_refused_outside_that_one_module(tmp_path: Path) -> None:
    """The allowlist alone would let a second listener be written anywhere and blame the wrong
    file: `auth/consent.py` is in the serve path's import graph, because the token reader lives
    in it too."""
    root = plant(tmp_path, "def serve() -> None:\n    HTTPServer(('127.0.0.1', 0), None)\n")
    assert "HTTPServer" in details(listening_socket_sweep(root))
    root = plant(tmp_path, "port = free_loopback_port()\n", name="other.py")
    assert "free_loopback_port" in details(listening_socket_sweep(root))


def test_an_outbound_socket_is_not_a_listening_socket(tmp_path: Path) -> None:
    """`socket.socket` is deliberately not in the caught set.

    An outbound client opens one and `net/egress.py`'s allowlist is what governs those. A
    guard that flagged every socket would be flagged into uselessness within a round; what
    makes a socket a *listening* socket is bind/listen/accept.
    """
    root = plant(
        tmp_path,
        "import socket\n"
        "def fetch() -> None:\n"
        "    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        '    s.connect(("gmail.googleapis.com", 443))\n',
    )
    assert listening_socket_sweep(root) == []


@pytest.mark.parametrize(
    "source",
    [
        # A name this pass cannot read.
        'getattr(sock, "bi" + "nd")(("0.0.0.0", 80))\n',
        # A method held in a data structure.
        'handlers = {"go": sock.bind}\nhandlers["go"](("0.0.0.0", 80))\n',
        # A different process's socket. Still a socket on the machine, which is why SEC-07
        # asks for a scan and not only for this.
        'subprocess.Popen(["python", "-m", "http.server"])\n',
    ],
)
def test_each_documented_listening_socket_gap_is_really_a_gap(tmp_path: Path, source: str) -> None:
    """The docstring's gap list, exercised. A gap that has quietly closed is a docstring that
    has quietly become wrong in the other direction, and this is the only thing that notices."""
    root = plant(tmp_path, source)
    assert listening_socket_sweep(root) == [], source
