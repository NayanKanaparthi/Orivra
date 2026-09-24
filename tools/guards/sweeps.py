"""Source-tree guards (WS-00).

Each guard walks Python source with `ast`, not with a text grep, for one reason: a grep
cannot tell prose from code. The rules below must be able to say "the word *harness* in a
docstring is fine, an import of it is not" - otherwise the gate is either useless or
un-passable, and an un-passable gate gets disabled.

Docstrings are excluded from string-literal checks for the same reason. Comments are not
scanned at all: a comment cannot read a file, name a scope, or call an endpoint.

## What these guards claim, after R-SEC-001

R-SEC-001 defeated all six with ordinary code - string concatenation, `importlib.
import_module`, `Path(...).open("w")` - while their docstrings claimed to catch exactly
those things. An overstated guard is worse than no guard, because the rubric leans on it.
Both halves of that finding are addressed here: the guards were hardened, **and** every
guard's docstring now carries an explicit "Does not catch" list. Where the two disagree,
the "Does not catch" list is the claim.

Hardening common to every guard:

  * **Constant folding.** `"a" + "b"`, adjacent-literal concatenation and f-strings are
    folded before matching, so splitting a literal no longer hides it. An f-string's
    interpolations fold to `{}`, and path shapes are compared with their placeholders
    normalised, so `f"gmail/v1/users/{uid}/messages/send"` is compared as
    `gmail/v1/users/{}/messages/send`. **What the fold reads, and what it does not, is
    listed below** - it is the single most load-bearing claim these guards make, because
    every content-matching guard is exactly as good as it.
  * **Dynamic imports.** `importlib.import_module(...)` and `__import__(...)` are read as
    imports. When the module name is a constant it is matched like any other import; when
    it is computed at runtime the call is itself a violation, because a name no static
    pass can read is a name no static pass can clear.

## What the constant fold reads (R-SEC-013)

R-SEC-008 fixed `b"...".decode()` and R-SEC-013 then walked through seven more ordinary
string-construction idioms with zero violations. The forbidden thing is the *text*, not the
spelling, so the fold now evaluates each of these when every operand is itself foldable:

  * concatenation (`+`), adjacent literals, f-strings (interpolations become `{}`);
  * `.decode()` / `.encode()` and `codecs.decode(...)` / `codecs.encode(...)`, and
    `bytes(...)` / `bytearray(...)` re-wrapping;
  * `"".join([...])` over a literal list or tuple;
  * `%`-formatting restricted to `%s`, and `.format()` restricted to plain `{}` / `{0}`
    replacement fields;
  * `bytes.fromhex("...")` and `(1234).to_bytes(n, "big")`;
  * `str.translate(str.maketrans("a", "b"))`;
  * constant slicing and indexing, including the reversing `[::-1]`.

**What the fold does not read, named rather than left to be rediscovered.** Any of these
hides a literal from every content-matching guard, and each is a real gap, not a claim:

  * a value reached through any **indirection**, which is the biggest of these gaps by far
    and has four distinct shapes rather than the one round 3 named (R-SEC-018). The fold
    evaluates literal expressions; it does not evaluate lookups. So none of these is read:

      - a **variable**: `part = "ground"; part + "_truth/x"` - nothing propagates
        assignments into expressions;
      - a **class or instance attribute**: `Config.SUFFIX + "/cases.json"` - an
        `ast.Attribute` receiver is not evaluated;
      - a **container element**: `_PARTS["suffix"]`, `_PARTS[0]` - a subscript of anything
        but a literal string is not evaluated. (Slicing and indexing a literal string *is*
        folded, which is a different thing and is listed above);
      - a **function return value**: `suffix()` - a call to anything outside the small set
        of foldable builtins above is not evaluated.

    The four share one root cause and each was confirmed to produce zero violations against
    a `"benchmarks/ground_truth/cases" + <indirection>` probe. Round 3's wording named only
    the first, which under-stated the gap by three shapes; the fold is unchanged and it is
    the claim that has been corrected;
  * `"".join(...)` over a comprehension or a name rather than a literal sequence;
  * `%d`/`%r`/width/precision conversions, and `.format()` fields carrying a conversion
    (`!r`), a format spec (`:>8`), a keyword or an attribute lookup;
  * text-changing transforms: `str.replace`, `.upper()`/`.lower()`, `base64.b64decode`,
    `zlib.decompress`, `codecs.decode(x, "rot13")` and any other non-text-preserving codec
    (the codec argument is checked, and an unrecognised one refuses the fold rather than
    reporting the input as though it were the output);
  * `str.maketrans` given a dict, or a `translate` table built any other way;
  * anything assembled at runtime from data - a file, the environment, a network response.

A **half-completed fold absorbs nothing** (R-SEC-013): under the round-3 shape,
`"benchmarks/ground_truth/x" + suffix` marked the literal as absorbed and then failed on
`suffix`, so neither the folded string nor the raw literal was ever reported. An expression
the fold cannot finish now leaves its literals to the plain-`Constant` scan.

What no guard here can catch, stated once so no individual guard has to claim it does:
`eval`/`exec`, a name or path read from a file or an environment variable at runtime,
`getattr`-driven attribute chains that never name their target, C-extension calls, and
anything under a `# noqa`-style deletion of the file from the sweep. These are guards
against drift and accident, not against a determined author of the code they scan.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from string import Formatter
from typing import Final

from mailweave.constants import GMAIL_ENDPOINTS, READ_SCOPE

# --- violation record -------------------------------------------------------------------


@dataclass(frozen=True)
class Violation:
    guard: str
    path: Path
    line: int
    detail: str

    def render(self, root: Path | None = None) -> str:
        relative = root is not None and self.path.is_relative_to(root)
        shown = self.path.relative_to(root) if relative and root else self.path
        return f"{self.guard}: {shown}:{self.line}: {self.detail}"


# --- helpers ----------------------------------------------------------------------------


def iter_python_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*.py")):
        parts = set(path.parts)
        if parts & {".venv", "__pycache__", "build", "dist", ".git"}:
            continue
        yield path


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return None


def _docstring_nodes(tree: ast.Module) -> set[int]:
    """`id()` of every string constant that is a module/class/function docstring."""
    marked: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                marked.add(id(body[0].value))
    return marked


#: Rendered in place of an f-string interpolation, so a path's *shape* still matches.
INTERPOLATION = "{}"


def _as_text(value: object) -> str | None:
    """The text a `Constant` carries, whether it was spelled as `str` or as `bytes`.

    R-SEC-008: every content-matching guard tested `isinstance(node.value, str)`, so
    `b"benchmarks/ground_truth/cases.json".decode()` was invisible to all four of them at
    once. A codec-declaring literal is ordinary Python, not an evasion technique, and the
    forbidden thing is the *text*, not the spelling. `latin-1` is the fallback because it
    cannot raise, and a guard that crashes on odd bytes is a guard that gets removed.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.decode("latin-1")
    return None


#: Methods that only re-spell the text of their receiver, so folding sees through them.
_TRANSCODING_METHODS = {"decode", "encode"}

#: Codecs that change a string's *type* without changing its text. Anything else -
#: `rot13`, `base64`, `zlib` - produces different text, so the fold refuses it rather than
#: reporting the input as if it were the output.
_TEXT_PRESERVING_CODECS = {
    "utf-8",
    "utf8",
    "utf_8",
    "u8",
    "ascii",
    "us-ascii",
    "latin-1",
    "latin1",
    "latin_1",
    "iso-8859-1",
    "iso8859-1",
    "cp1252",
}

#: Builtins that wrap a string or bytes value without altering the characters in it.
_REWRAPPING_BUILTINS = {"bytes", "bytearray", "memoryview"}

#: The longest string the fold will materialise. A pass that a literal in the tree it
#: scans can make allocate a gigabyte is a pass that gets removed, and no path, scope or
#: endpoint any guard matches on is anywhere near this long.
_FOLD_MAX_CHARS = 16_384


def _constant_int(node: ast.expr) -> int | None:
    """The integer an expression names, including a negated literal (`-1` in a slice)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.operand, ast.Constant):
        value = node.operand.value
        if isinstance(value, int):
            if isinstance(node.op, ast.USub):
                return -value
            if isinstance(node.op, ast.UAdd):
                return value
    return None


def _codec_is_text_preserving(node: ast.Call, position: int) -> bool:
    """Whether a transcoding call's codec argument leaves the characters alone."""
    codec: ast.expr | None = None
    for keyword in node.keywords:
        if keyword.arg == "encoding":
            codec = keyword.value
    if codec is None and len(node.args) > position:
        codec = node.args[position]
    if codec is None:
        return True  # the default is utf-8
    if isinstance(codec, ast.Constant) and isinstance(codec.value, str):
        return codec.value.lower() in _TEXT_PRESERVING_CODECS
    return False


def _fold_percent(template: str, values: list[str]) -> str | None:
    """`"%s/x" % "a"`, and only that: `%d`, widths and precisions are not folded.

    Written as a scan rather than by calling `%`, so a width in the template cannot make
    this allocate.
    """
    out: list[str] = []
    used = 0
    index = 0
    while index < len(template):
        character = template[index]
        if character != "%":
            out.append(character)
            index += 1
            continue
        following = template[index + 1 : index + 2]
        if following == "%":
            out.append("%")
            index += 2
            continue
        if following != "s":
            return None
        if used >= len(values):
            return None
        out.append(values[used])
        used += 1
        index += 2
    return "".join(out) if used == len(values) else None


def _fold_format(template: str, values: list[str]) -> str | None:
    """`"{}/x".format("a")` with plain replacement fields.

    A field carrying a conversion (`!r`), a format spec (`:>8`), a keyword or an attribute
    lookup is not folded: substituting the argument for it would report text the call does
    not produce, and a guard that reports the wrong string is one nobody trusts.
    """
    try:
        parsed = list(Formatter().parse(template))
    except ValueError:
        return None
    out: list[str] = []
    automatic = 0
    for literal, replacement, spec, conversion in parsed:
        out.append(literal)
        if replacement is None:
            continue
        if spec or conversion:
            return None
        if replacement == "":
            position = automatic
            automatic += 1
        elif replacement.isdigit():
            position = int(replacement)
        else:
            return None
        if position >= len(values):
            return None
        out.append(values[position])
    return "".join(out)


def _translation_table(node: ast.expr) -> dict[int, str] | None:
    """The mapping a `str.maketrans("ab", "cd")` call builds, when both sides are literal."""
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "maketrans"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "str"
        and len(node.args) == 2
    ):
        return None
    source, target = node.args
    if not (isinstance(source, ast.Constant) and isinstance(source.value, str)):
        return None
    if not (isinstance(target, ast.Constant) and isinstance(target.value, str)):
        return None
    if len(source.value) != len(target.value):
        return None
    return {ord(a): b for a, b in zip(source.value, target.value, strict=True)}


def _fold(node: ast.expr, consumed: set[int]) -> str | None:
    """Fold `node` to the string it evaluates to, as far as that is statically knowable.

    Returns `None` for anything that is not a string expression. Every `Constant` the fold
    absorbed is added to `consumed`, so `_string_literals` does not report the same text
    twice - once whole and once in pieces.

    Constants are absorbed **only on success** (R-SEC-013). Under the round-3 shape the
    fold wrote into `consumed` as it descended, so `"benchmarks/ground_truth/x" + suffix`
    marked the literal absorbed, then failed on `suffix` and returned `None` - and the
    literal was never reported by anything. A half-completed fold now leaves no trace.
    """
    scratch: set[int] = set()
    text = _fold_step(node, scratch)
    if text is None or len(text) > _FOLD_MAX_CHARS:
        return None
    consumed |= scratch
    return text


def _fold_call(node: ast.Call, consumed: set[int]) -> str | None:
    """The call shapes that produce a statically-knowable string (R-SEC-013).

    Every one of these is ordinary Python that some real module somewhere writes on
    purpose, which is why they are folded rather than named as evasions. What is *not*
    folded is listed in the module docstring's fold section, and that list is the claim.
    """
    func = node.func
    if isinstance(func, ast.Name):
        if func.id in _REWRAPPING_BUILTINS and len(node.args) == 1:
            # `bytearray(b"...")` / `bytes(b"...")`: a different container, same characters.
            return _fold_step(node.args[0], consumed)
        return None
    if not isinstance(func, ast.Attribute):
        return None
    attribute = func.attr
    receiver = func.value

    if attribute in _TRANSCODING_METHODS:
        if isinstance(receiver, ast.Name) and receiver.id == "codecs":
            # `codecs.decode(b"...", "utf-8")`: the text is the *argument*, not the
            # receiver. Round 3 matched on the attribute name alone, failed to fold
            # `codecs`, and the inner literal was then caught by the plain-Constant
            # fallback - by accident, not because the call was understood.
            if not node.args or not _codec_is_text_preserving(node, 1):
                return None
            return _fold_step(node.args[0], consumed)
        if not _codec_is_text_preserving(node, 0):
            return None
        # `b"...".decode()`, `"...".encode()`, and chains of the two: the codec changes
        # the type, never the text, so the fold looks straight through it.
        return _fold_step(receiver, consumed)

    if (
        attribute == "fromhex"
        and isinstance(receiver, ast.Name)
        and receiver.id in {"bytes", "bytearray"}
    ):
        digits = _fold_step(node.args[0], consumed) if len(node.args) == 1 else None
        if digits is None or len(digits) > 2 * _FOLD_MAX_CHARS:
            return None
        try:
            return _as_text(bytes.fromhex(digits))
        except ValueError:
            return None

    if attribute == "to_bytes" and isinstance(receiver, ast.Constant):
        number = receiver.value
        if not isinstance(number, int) or isinstance(number, bool):
            return None
        length = _constant_int(node.args[0]) if node.args else 1
        order = "big"
        if len(node.args) > 1:
            if not (isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str)):
                return None
            order = node.args[1].value
        if length is None or not 0 <= length <= _FOLD_MAX_CHARS or order not in {"big", "little"}:
            return None
        try:
            return _as_text(number.to_bytes(length, order))  # type: ignore[arg-type]
        except (OverflowError, ValueError):
            return None

    if attribute == "join":
        separator = _fold_step(receiver, consumed)
        if separator is None or len(node.args) != 1:
            return None
        elements = node.args[0]
        if not isinstance(elements, ast.List | ast.Tuple):
            return None  # a comprehension or a name: nothing static to join
        pieces: list[str] = []
        for element in elements.elts:
            piece = _fold_step(element, consumed)
            if piece is None:
                return None
            pieces.append(piece)
        return separator.join(pieces)

    if attribute == "format":
        template = _fold_step(receiver, consumed)
        if template is None or node.keywords:
            return None
        values: list[str] = []
        for argument in node.args:
            value = _fold_step(argument, consumed)
            if value is None:
                return None
            values.append(value)
        return _fold_format(template, values)

    if attribute == "translate" and len(node.args) == 1:
        table = _translation_table(node.args[0])
        text = _fold_step(receiver, consumed)
        if table is None or text is None:
            return None
        return text.translate(table)

    return None


def _fold_step(node: ast.expr, consumed: set[int]) -> str | None:
    """One level of the fold. Absorbs into `consumed`; `_fold` decides whether to keep it."""
    if isinstance(node, ast.Constant):
        text = _as_text(node.value)
        if text is not None:
            consumed.add(id(node))
        return text
    if isinstance(node, ast.Call):
        return _fold_call(node, consumed)
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Add):
            left = _fold_step(node.left, consumed)
            right = _fold_step(node.right, consumed)
            if left is None or right is None:
                return None
            return left + right
        if isinstance(node.op, ast.Mod):
            template = _fold_step(node.left, consumed)
            if template is None:
                return None
            operands = node.right
            parts = operands.elts if isinstance(operands, ast.Tuple) else [operands]
            values: list[str] = []
            for part in parts:
                value = _fold_step(part, consumed)
                if value is None:
                    return None
                values.append(value)
            return _fold_percent(template, values)
        return None
    if isinstance(node, ast.Subscript):
        text = _fold_step(node.value, consumed)
        if text is None:
            return None
        if isinstance(node.slice, ast.Slice):
            bounds: list[int | None] = []
            for bound in (node.slice.lower, node.slice.upper, node.slice.step):
                if bound is None:
                    bounds.append(None)
                    continue
                number = _constant_int(bound)
                if number is None:
                    return None
                bounds.append(number)
            if bounds[2] == 0:
                return None
            return text[bounds[0] : bounds[1] : bounds[2]]
        position = _constant_int(node.slice)
        if position is None:
            return None
        return text[position] if -len(text) <= position < len(text) else None
    if isinstance(node, ast.JoinedStr):
        fragments: list[str] = []
        for fragment in node.values:
            if isinstance(fragment, ast.Constant) and isinstance(fragment.value, str):
                consumed.add(id(fragment))
                fragments.append(fragment.value)
            elif isinstance(fragment, ast.FormattedValue):
                fragments.append(INTERPOLATION)
            else:  # pragma: no cover - JoinedStr holds only these two node kinds
                return None
        return "".join(fragments)
    return None


def _string_literals(tree: ast.Module) -> Iterator[tuple[int, str]]:
    """Every string a module builds out of literals, except docstrings.

    Round 1 yielded whole `Constant` nodes only, so `"https://mail.google.com" + "/"` was
    invisible to every guard that matched on literals (R-SEC-001). Concatenations and
    f-strings are folded first; a fragment that is *only* part of a folded expression is
    not yielded again on its own.
    """
    docstrings = _docstring_nodes(tree)
    consumed: set[int] = set()
    folded: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp | ast.JoinedStr | ast.Call | ast.Subscript):
            value = _fold(node, consumed)
            if value is not None:
                folded.append((node.lineno, value))
    yield from folded
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant):
            text = _as_text(node.value)
            if text is None or id(node) in docstrings or id(node) in consumed:
                continue
            yield node.lineno, text


def _identifiers(tree: ast.Module) -> Iterator[tuple[int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            yield node.lineno, node.id
        elif isinstance(node, ast.Attribute):
            yield node.lineno, node.attr
        elif isinstance(node, ast.arg):
            yield node.lineno, node.arg
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            yield node.lineno, node.name


#: Yielded by `_imported_modules` for an import whose module name is computed at runtime.
UNREADABLE_IMPORT = "<computed at runtime>"

_DYNAMIC_IMPORT_CALLS = {"import_module", "__import__"}


def _dynamic_import_name(node: ast.Call) -> str | None:
    """The module a dynamic-import call names, or `UNREADABLE_IMPORT`, or `None`.

    Recognises `importlib.import_module(x)`, a bare `import_module(x)` and `__import__(x)`
    - the shapes that made `forbidden_imports` and `generative_client_sweep` blind in
    R-SEC-001.
    """
    func = node.func
    if isinstance(func, ast.Attribute):
        name = func.attr
    elif isinstance(func, ast.Name):
        name = func.id
    else:  # pragma: no cover - a call on a subscript/lambda is not an import shape
        return None
    if name not in _DYNAMIC_IMPORT_CALLS:
        return None
    if not node.args:
        return UNREADABLE_IMPORT
    return _fold(node.args[0], set()) or UNREADABLE_IMPORT


def _imported_modules(tree: ast.Module) -> Iterator[tuple[int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.lineno, node.module
        elif isinstance(node, ast.Call):
            dynamic = _dynamic_import_name(node)
            if dynamic is not None:
                yield node.lineno, dynamic


# --- guard 1: ground-truth isolation (PROC-03) -------------------------------------------

_GROUND_TRUTH_IDENTIFIER_TOKENS = ("seed_map", "ground_truth", "manifest", "harness")
_GROUND_TRUTH_STRING_TOKENS = ("seed_map", "ground_truth", "mailweave_harness", "manifest.json")

#: Splits an identifier into the words it is made of: `snake_case`, `camelCase`,
#: `PascalCase` and digit runs all break a segment (R-SEC-028).
_IDENTIFIER_SEGMENT_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z]*|[a-z]+|\d+")


def _identifier_segments(name: str) -> tuple[str, ...]:
    """The lower-cased words `name` is composed of."""
    return tuple(match.group(0).lower() for match in _IDENTIFIER_SEGMENT_RE.finditer(name))


def _names_ground_truth(name: str) -> str | None:
    """Which ground-truth token `name` names, comparing **words** and not substrings.

    R-SEC-028: the check was `token in name.lower()`, so `is_manifestly_invalid` and
    `harnessed_load` were both reported as naming ground-truth material - "manifestly"
    contains "manifest" and "harnessed" contains "harness". Neither identifier refers to a
    case manifest or to the harness, and a guard that says they do is one an engineer
    learns to ignore.

    A token matches when its own words appear as a contiguous run of the identifier's
    words, so `seed_map`, `seedMap`, `load_ground_truth` and `case_manifest` all match and
    the two collisions above do not.

    **Still flagged, by design:** an identifier whose words genuinely include `harness` or
    `manifest` - `harness_the_energy` is R-SEC's other example and does contain the whole
    word `harness`. A word-boundary rule cannot tell that apart from a real reference, and
    the tighter rule that could would be a list of allowed phrasings, which is a
    maintenance burden with no security value. Nothing in `server/src` collides today.
    """
    segments = _identifier_segments(name)
    for token in _GROUND_TRUTH_IDENTIFIER_TOKENS:
        wanted = _identifier_segments(token)
        if not wanted:  # pragma: no cover - every token has at least one word
            continue
        span = len(wanted)
        if any(segments[start : start + span] == wanted for start in range(len(segments))):
            return token
    return None


def ground_truth_sweep(root: Path) -> list[Violation]:
    """The server must not name, import or read case manifests, seed maps or the harness.

    Catches: any identifier (name, attribute, argument, def) one of whose **words** is
    `seed_map`, `ground_truth`, `manifest` or `harness` - compared word by word since
    R-SEC-028, so `is_manifestly_invalid` and `harnessed_load` no longer collide; and any
    non-docstring string -
    including one built by concatenation or an f-string - containing `seed_map`,
    `ground_truth`, `mailweave_harness` or `manifest.json`. `globals()["se"+"ed"+"_map"]`
    is caught by the string half after folding.

    Does not catch: a name assembled at runtime from data (`"".join(parts)`, a value read
    from a file or the environment), or ground-truth material reached without ever naming
    it - for instance by iterating a directory. This guard is evidence that the server
    does not *reference* ground truth, not proof that it cannot reach it.
    """
    violations: list[Violation] = []
    for path in iter_python_files(root):
        tree = _parse(path)
        if tree is None:
            continue
        for line, name in _identifiers(tree):
            token = _names_ground_truth(name)
            if token is not None:
                violations.append(
                    Violation(
                        "ground-truth-isolation",
                        path,
                        line,
                        f"identifier {name!r} names ground-truth material ({token})",
                    )
                )
        for line, value in _string_literals(tree):
            lowered = value.lower()
            for token in _GROUND_TRUTH_STRING_TOKENS:
                if token in lowered:
                    violations.append(
                        Violation(
                            "ground-truth-isolation",
                            path,
                            line,
                            f"string literal references ground-truth material ({token})",
                        )
                    )
    return violations


# --- guard 2: forbidden imports (import contract) ----------------------------------------

_FORBIDDEN_IMPORT_ROOTS = ("mailweave_harness", "harness", "tools", "tests", "conftest")


def forbidden_imports(root: Path) -> list[Violation]:
    """`server` must not import the harness, the repo tooling, or the test tree.

    Catches: `import x` / `from x import y`, and dynamic imports -
    `importlib.import_module("mailweave" + "_harness")`, `__import__(...)` - whose module
    name folds to a constant. A dynamic import whose name cannot be read statically is
    itself reported, because an unreadable name is one this guard cannot clear.

    Does not catch: a module loaded through `importlib.util.spec_from_file_location`, an
    `exec` of source text, or an object obtained from an already-imported module by
    attribute lookup.
    """
    violations: list[Violation] = []
    for path in iter_python_files(root):
        tree = _parse(path)
        if tree is None:
            continue
        for line, module in _imported_modules(tree):
            if module == UNREADABLE_IMPORT:
                violations.append(
                    Violation(
                        "forbidden-import",
                        path,
                        line,
                        "dynamic import with a module name computed at runtime; the import "
                        "contract cannot be checked against a name no static pass can read",
                    )
                )
                continue
            head = module.split(".")[0]
            if head in _FORBIDDEN_IMPORT_ROOTS:
                violations.append(
                    Violation(
                        "forbidden-import",
                        path,
                        line,
                        f"server code imports {module!r}; the dependency direction is "
                        "harness -> server, never the reverse",
                    )
                )
    return violations


# --- guard 3: scope literals (SEC-01, SEC-03) --------------------------------------------

_DESTRUCTIVE_SCOPE_MARKER = "mail.google.com/"


def scope_literal_sweep(root: Path) -> list[Violation]:
    """Exactly one Gmail scope literal may appear in server code, and it is read-only.

    Catches: any non-docstring string containing `googleapis.com/auth/` that is not the
    single read-only scope, and any string containing the destructive harness scope -
    including `"https://mail.google.com" + "/"` and the f-string equivalent, which is
    what R-SEC-001 walked through.

    Does not catch: a scope assembled from data at runtime, or a scope that never appears
    as a string in server code at all (read from configuration, say). The runtime
    enforcement in `config.py` / `auth/clients.py` is the other half of SEC-01/SEC-03 and
    does not depend on this sweep.
    """
    violations: list[Violation] = []
    for path in iter_python_files(root):
        tree = _parse(path)
        if tree is None:
            continue
        for line, value in _string_literals(tree):
            if "googleapis.com/auth/" in value and value != READ_SCOPE:
                violations.append(
                    Violation(
                        "scope-literal",
                        path,
                        line,
                        f"scope literal {value!r} is not the single permitted scope {READ_SCOPE!r}",
                    )
                )
            if _DESTRUCTIVE_SCOPE_MARKER in value:
                violations.append(
                    Violation(
                        "scope-literal",
                        path,
                        line,
                        f"destructive harness scope {value!r} appears in server code (SEC-03)",
                    )
                )
    return violations


# --- guard 4: Gmail endpoint literals (AD A.5) -------------------------------------------


def _normalise_path_shape(value: str) -> str:
    """Compare endpoint paths by shape: every `{...}` placeholder folds to `{}`.

    `f"gmail/v1/users/{user_id}/messages"` and the declared
    `gmail/v1/users/{userId}/messages` are the same endpoint; the send endpoint remains a
    different one however its literal was assembled.
    """
    out: list[str] = []
    depth = 0
    for character in value:
        if character == "{":
            if depth == 0:
                out.append("{}")
            depth += 1
        elif character == "}":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(character)
    return "".join(out)


def gmail_path_sweep(root: Path) -> list[Violation]:
    """No `gmail/v1` path may appear that is not one of the six declared endpoints.

    Catches: any non-docstring string containing `gmail/v1` whose placeholder-normalised
    shape is not one of `GMAIL_ENDPOINTS`. Concatenated literals (`"gmail/v" + "1/..."`)
    and f-strings are folded first, so the R-SEC-001 send-endpoint literal is reported.

    Does not catch: a path built from a variable that does not itself contain `gmail/v1`
    (`base + suffix` where `base` is read from configuration), or a request made against
    a full URL constructed elsewhere. The egress allowlist bounds the *host*; this sweep
    bounds the paths that appear in source.
    """
    allowed = {_normalise_path_shape(endpoint) for endpoint in GMAIL_ENDPOINTS}
    violations: list[Violation] = []
    for path in iter_python_files(root):
        tree = _parse(path)
        if tree is None:
            continue
        for line, value in _string_literals(tree):
            if "gmail/v1" not in value:
                continue
            trimmed = _normalise_path_shape(value.strip("/ "))
            if trimmed not in allowed:
                violations.append(
                    Violation(
                        "gmail-endpoint",
                        path,
                        line,
                        f"path literal {value!r} is not one of the six declared endpoints",
                    )
                )
    return violations


# --- guard 5: generative clients (D.8, SEC-08) -------------------------------------------

_GENERATIVE_MODULES = {
    "openai",
    "anthropic",
    "cohere",
    "litellm",
    "google.generativeai",
    "vertexai",
    "llama_cpp",
    "ollama",
}
_GENERATIVE_PATH_MARKERS = ("chat/completions", "/v1/messages", "generateContent")


def generative_client_sweep(root: Path) -> list[Violation]:
    """`generative_llm_calls = 0` is hard: no chat/completions client may be importable.

    Catches: an import of a known generative SDK, static or dynamic
    (`importlib.import_module("open" + "ai")` folds to `openai`); a dynamic import whose
    name cannot be read statically; and any non-docstring string - folded, so
    `"chat/completio" + "ns"` counts - naming a generative API path.

    Does not catch: an SDK that is not on `_GENERATIVE_MODULES`, a raw HTTP call to a
    generative endpoint whose URL never appears as a literal, or a model invoked through
    a local library that is not on the list. The list is a denylist and says so.
    """
    violations: list[Violation] = []
    for path in iter_python_files(root):
        tree = _parse(path)
        if tree is None:
            continue
        for line, module in _imported_modules(tree):
            if module == UNREADABLE_IMPORT:
                violations.append(
                    Violation(
                        "generative-client",
                        path,
                        line,
                        "dynamic import with a module name computed at runtime; a generative "
                        "client cannot be ruled out for a name no static pass can read",
                    )
                )
                continue
            if module in _GENERATIVE_MODULES or module.split(".")[0] in _GENERATIVE_MODULES:
                violations.append(
                    Violation(
                        "generative-client",
                        path,
                        line,
                        f"server code imports generative client {module!r}; this release "
                        "makes zero generative model calls (AD D.8)",
                    )
                )
        for line, value in _string_literals(tree):
            for marker in _GENERATIVE_PATH_MARKERS:
                if marker in value:
                    violations.append(
                        Violation(
                            "generative-client",
                            path,
                            line,
                            f"string literal {value!r} names a generative API path",
                        )
                    )
    return violations


# --- guard 6: unaudited disk writes (seed of the trace-content audit, SEC-05) -------------

#: The modules permitted to write to disk. Two, deliberately, and each is a file whose whole
#: job is "persist exactly this shape at exactly these permissions":
#:
#:   * `auth/tokenstore.py` - the refresh token and salt (SEC-04, SEC-05);
#:   * `freshness/watermark.py` - the four-field historyId stamp (AD D.9, ADV-101), which
#:     refuses any payload that is not exactly those four fields and imports its mode
#:     constants from `constants.py` rather than restating them, so the two writers cannot
#:     drift apart on what 0600 means here.
#:
#: An entry here is a deliberate line in a diff a reviewer sees, which is the point.
_WRITE_ALLOWLISTED_MODULES = {
    "mailweave/auth/tokenstore.py",
    "mailweave/freshness/watermark.py",
    # The only writer of model weights (AD D.8). It is also the only module allowed to
    # contact the model host, which `no-model-host-at-runtime` enforces separately: the two
    # guards bound different things about the same file and neither implies the other.
    "mailweave/models/provision.py",
    # The only writer of traces (AD A.11, D.10). What it writes is bounded by a *type*
    # rather than by this guard - `PersonalTrace` has no field mail text can reach - and
    # this guard bounds the other half: that no other module writes one, so "what does this
    # process put on disk?" has a three-line answer.
    "mailweave/trace/sink.py",
    # The call lifecycle diagnostic (2026-09-21): one line per tool-call start and one per
    # end, opt-in by `MAILWEAVE_DIAGNOSTICS`. What it writes is bounded by `shape_of`, which
    # replaces every caller-supplied string with its shape, and `test_repairs_2026_09_21`
    # holds that no query, body, identifier or credential reaches the file.
    "mailweave/diagnostics.py",
}

#: Attribute calls that write a file whatever the receiver is.
_WRITE_ATTRS = {"write_text", "write_bytes", "writelines"}
#: `<module>.<name>` calls that create, write or move a file on disk.
_WRITE_QUALIFIED = {
    ("json", "dump"),
    ("pickle", "dump"),
    ("marshal", "dump"),
    ("os", "write"),
    ("os", "open"),
    ("os", "replace"),
    ("os", "rename"),
    ("os", "link"),
    ("os", "symlink"),
    ("shutil", "copy"),
    ("shutil", "copy2"),
    ("shutil", "copyfile"),
    ("shutil", "copytree"),
    ("shutil", "move"),
    ("tempfile", "NamedTemporaryFile"),
    ("tempfile", "TemporaryFile"),
    ("tempfile", "mkstemp"),
}
#: Characters that make an `open()` mode a writing mode.
_WRITE_MODE_CHARS = frozenset("wax+")
#: Every character a real `open` mode is made of, and the longest one there is ("xb+" and
#: friends are three; "rb+t" is four). R-SEC-027: this is what separates a mode from an
#: English word that happens to contain one of `w`, `a`, `x` or `+`.
_FILE_MODE_CHARS = frozenset("rwaxbt+U")
_MAX_FILE_MODE_CHARS = 4

#: Stdlib file objects whose *constructor* takes the path first and the mode second, like
#: the builtin `open`. There is nothing structural to recognise in a name like `ZipFile`,
#: so unlike `.open()` below this is a list, and it is one - `zipfile.ZipFile("x", "w")`
#: was missed entirely before R-SEC-016 and a constructor that is not named here still is.
_MODE_AT_ONE_CONSTRUCTORS = {
    ("zipfile", "ZipFile"),
    ("zipfile", "PyZipFile"),
    ("tarfile", "TarFile"),
    ("gzip", "GzipFile"),
    ("bz2", "BZ2File"),
    ("lzma", "LZMAFile"),
    ("io", "FileIO"),
}

#: Openers that spell their mode as a dbm *flag* (`r`/`w`/`c`/`n`) rather than as an
#: `open` mode, so the mode characters to look for are different ones.
_FLAG_STYLE_OPENERS = {
    ("shelve", "open"),
    ("dbm", "open"),
    ("dbm.gnu", "open"),
    ("dbm.ndbm", "open"),
    ("dbm.dumb", "open"),
    ("dbm.sqlite3", "open"),
}
#: And of those, the ones whose *default* flag creates the file, so an absent flag is a
#: write rather than a read. `shelve.open(path)` defaults to `flag="c"`; `dbm.open` to `r`.
_OPENERS_WRITING_BY_DEFAULT = {("shelve", "open")}
_FLAG_WRITE_CHARS = frozenset("cnw")

_PARTIAL_NAMES = {"partial", "partialmethod"}
#: `dataclasses.field(default=...)`, the other ordinary way a class attribute is declared.
_FIELD_FACTORY_NAMES = {"field"}
#: Keywords of `field(...)` that hold the callable the attribute will refer to.
_FIELD_DEFAULT_KEYWORDS = ("default", "default_factory")


@dataclass(frozen=True)
class _Binding:
    """One assignment of a local name, and what this pass could read it as.

    `target` is `None` when the value is something the pass cannot resolve. Those are kept
    rather than dropped: an unreadable assignment still *shadows*, and treating it as "not
    bound here" is precisely how R-SEC-015's false positive arose one scope up.
    """

    line: int
    target: tuple[str, str] | None


@dataclass
class _Scope:
    """One Python scope's binding table: which local names refer to what.

    R-SEC-009: `_writes_to_disk` only ever recognised a write whose *call node* named the
    write - `os.write(...)`, `open(...)`. Bind the callable to any other name first and the
    later call is an ordinary `ast.Name` the guard never looked at:

        from os import write as w   ->  w(fd, body)
        _writer = os.write          ->  _writer(fd, body)
        functools.partial(os.write) ->  leak(fd, body)
        class W: handler = os.write ->  W.handler(fd, body)

    All four are ordinary refactors, not adversarial code, which is what made the gap worth
    closing rather than documenting.

    R-SEC-015: the round-3 index was one flat table for the whole module, so a name bound
    in *any* function was resolved at *every* call of that name anywhere in the file. Two
    unrelated functions that each happened to use `_disk_writer` - one for `os.write`, one
    for `"{}={}".format` - produced two violations for one real write. A guard that fires
    on innocent code is a guard the next engineer switches off, and then it protects
    nothing; that is a worse outcome than the bypass it was trading against. So bindings
    now live in the scope that makes them and are looked up through enclosing scopes,
    stopping at the first scope that binds the name at all - which is what makes a local
    re-binding shadow an outer one instead of inheriting it.

    `bound` is deliberately wider than `modules | functions | classes`: it holds every name
    the scope assigns, including the ones this pass cannot resolve. A name it cannot read
    still shadows, and treating an unreadable local as "not bound here" is exactly how the
    false positive happened.
    """

    parent: _Scope | None = None
    #: Line of the `def`/`class` that created this scope; `None` for the module scope.
    #: R-SEC-017 needs it: for a name owned by an enclosing *function*, the binding in
    #: force is the one above the point where this scope was created, not the last one in
    #: the file.
    defined_at: int | None = None
    modules: dict[str, str] = field(default_factory=dict)
    functions: dict[str, list[_Binding]] = field(default_factory=dict)
    classes: dict[str, dict[str, list[_Binding]]] = field(default_factory=dict)
    #: Base classes per class, by the name written in the `class` header (R-SEC-024).
    #: Only plain names and dotted paths; a computed base is not recorded, and a base
    #: imported from another module resolves to no table here.
    bases: dict[str, tuple[str, ...]] = field(default_factory=dict)
    bound: set[str] = field(default_factory=set)

    def _owner_and_entry(self, name: str) -> tuple[_Scope | None, int | None]:
        """The nearest scope binding `name`, and the line at which the lookup entered it.

        The second value is the `defined_at` of the scope directly below the owner on the
        path from here - i.e. the line in the owner's body where this closure was created.
        """
        scope: _Scope | None = self
        entry: int | None = None
        while scope is not None:
            if name in scope.bound:
                return scope, entry
            entry = scope.defined_at
            scope = scope.parent
        return None, None

    def _owner(self, name: str) -> _Scope | None:
        """The nearest scope that binds `name`, or `None` if nothing does."""
        return self._owner_and_entry(name)[0]

    def is_bound(self, name: str) -> bool:
        """Whether any enclosing scope binds this name, i.e. it is not the builtin."""
        return self._owner(name) is not None

    def module_named(self, name: str) -> str | None:
        owner = self._owner(name)
        return owner.modules.get(name) if owner else None

    def function_named(self, name: str, line: int | None = None) -> tuple[str, str] | None:
        """What `name` refers to at `line`, or `None` if this pass cannot read it.

        Within the scope that owns the name, the binding in force is the most recent one
        *above* the call - so `w = os.write; w(fd, b); w = str.upper; w(x)` reports the
        first call and not the second, and the conditional masking R-SEC found (`handler`
        assigned in both arms of an `if`, called after) resolves to the arm nearest the
        call rather than to whichever the pass happened to read first.

        For a binding in the **module** scope the last one wins regardless of line: a
        module-level name is fully bound by the time any function in that module runs, so
        comparing line numbers across the boundary would miss the ordinary case of a helper
        defined above the constant it uses.

        R-SEC-017: that argument is about module scope, and round 4 applied it to every
        scope crossing. It does not hold for a closure over an *enclosing function's*
        local, which can be called before a later - and possibly conditional - rebind in
        the same call:

            def process(fd, body, reconfigure):
                def dispatch():
                    action(fd, body)     # `action` is str.strip when this runs
                action = str.strip
                dispatch()
                if reconfigure:
                    action = os.write    # textually later, may never execute

        Reported as an unconditional disk write, which is a false positive on an ordinary
        closure-then-reconfigure shape - and a guard that fires on innocent code is a guard
        someone switches off, which is how it comes to protect nothing. So for an enclosing
        *function* scope the binding in force is the last one above the line where this
        closure was **created**, which is the best static approximation of what the free
        variable held when the closure was made.
        """
        owner, entry = self._owner_and_entry(name)
        if owner is None:
            return None
        bindings = sorted(owner.functions.get(name, []), key=lambda binding: binding.line)
        if not bindings:
            return None
        if owner is self:
            effective = line
        elif owner.parent is None:
            return bindings[-1].target
        else:
            effective = entry
        if effective is None:
            return bindings[-1].target
        preceding = [binding for binding in bindings if binding.line <= effective]
        return preceding[-1].target if preceding else None

    def class_attribute(self, class_name: str, attribute: str) -> tuple[str, str] | None:
        """`class_name` may be dotted (`Outer.Inner`); ownership follows its first segment.

        A nested class's attribute table is registered on the scope that binds the
        *outermost* class, under the dotted path, because that is the only name a call
        outside the class can reach it by (R-SEC-019).

        R-SEC-024: an attribute a class *inherits* is reached by exactly the same
        expression as one it declares - `class Base: handler = os.write` / `class
        Sub(Base): pass` / `Sub.handler(fd, body)` - and only the class's own body was
        read, so the write disappeared. Bases are followed depth-first in declaration
        order, which is Python's own resolution order for this case, with the class's own
        body winning over any base. Visited classes are tracked, so a cycle (which Python
        would reject anyway) terminates here rather than recursing.
        """
        return self._class_attribute(class_name, attribute, set())

    def _class_attribute(
        self, class_name: str, attribute: str, seen: set[str]
    ) -> tuple[str, str] | None:
        if class_name in seen:
            return None
        seen.add(class_name)
        owner = self._owner(class_name.split(".")[0])
        if owner is None:
            return None
        bindings = owner.classes.get(class_name, {}).get(attribute, [])
        if bindings:
            return bindings[-1].target
        for base in owner.bases.get(class_name, ()):
            inherited = self._class_attribute(base, attribute, seen)
            if inherited is not None:
                return inherited
        return None


def _resolve_module(node: ast.expr, scope: _Scope) -> str | None:
    """The module a receiver expression refers to, following `import ... as` bindings."""
    if isinstance(node, ast.Name):
        return scope.module_named(node.id)
    if isinstance(node, ast.Attribute):
        parent = _resolve_module(node.value, scope)
        return f"{parent}.{node.attr}" if parent else None
    return None


def _dotted_name(node: ast.expr) -> str | None:
    """`Outer.Inner` for a chain of plain attribute accesses, or `None` for anything else."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_name(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


def _class_receiver(node: ast.expr) -> str | None:
    """The class an attribute access is reaching into, by the name a caller writes.

    Three shapes, all ordinary: `Writer.handler` (R-SEC-014), `Outer.Inner.handler` - a
    chained `ast.Attribute`, which the bare-`Name` branch skipped entirely (R-SEC-019) -
    and `Writer().handler`, the way a dataclass's field default is normally reached
    (R-SEC-020). A name that is not a class resolves to no attribute table, so widening
    the receiver costs nothing in false positives.
    """
    if isinstance(node, ast.Call):
        return _dotted_name(node.func)
    return _dotted_name(node)


def _qualified_target(node: ast.expr, scope: _Scope) -> tuple[str, str] | None:
    """`(module, attribute)` for an expression that *names* a function without calling it."""
    if isinstance(node, ast.Attribute):
        module = _resolve_module(node.value, scope)
        if module:
            return (module, node.attr)
        receiver = _class_receiver(node.value)
        # `Writer.handler` / `Outer.Inner.handler` where the class was indexed.
        return scope.class_attribute(receiver, node.attr) if receiver else None
    if isinstance(node, ast.Name):
        return scope.function_named(node.id)
    return None


def _bind(scope: _Scope, target: ast.expr, line: int) -> None:
    """Record every name a target expression binds, resolvable or not."""
    if isinstance(target, ast.Name):
        scope.bound.add(target.id)
        scope.functions.setdefault(target.id, []).append(_Binding(line, None))
    elif isinstance(target, ast.Tuple | ast.List):
        for element in target.elts:
            _bind(scope, element, line)
    elif isinstance(target, ast.Starred):
        _bind(scope, target.value, line)


def _statement_bindings(scope: _Scope, node: ast.stmt) -> None:
    """The names one statement binds in `scope`, before anything is resolved."""
    if isinstance(node, ast.Assign):
        for target in node.targets:
            _bind(scope, target, node.lineno)
    elif isinstance(node, ast.AnnAssign | ast.AugAssign | ast.For | ast.AsyncFor):
        _bind(scope, node.target, node.lineno)
    elif isinstance(node, ast.With | ast.AsyncWith):
        for item in node.items:
            if item.optional_vars is not None:
                _bind(scope, item.optional_vars, node.lineno)
    elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        scope.bound.add(node.name)
    elif isinstance(node, ast.Import):
        for alias in node.names:
            scope.bound.add(alias.asname or alias.name.split(".")[0])
    elif isinstance(node, ast.ImportFrom):
        for alias in node.names:
            scope.bound.add(alias.asname or alias.name)
    elif isinstance(node, ast.Try):
        for handler in node.handlers:
            if handler.name:
                scope.bound.add(handler.name)


def _own_statements(body: Sequence[ast.stmt]) -> Iterator[ast.stmt]:
    """Every statement of a body, descending through blocks but not into nested scopes."""
    for statement in body:
        yield statement
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        for child in ast.iter_child_nodes(statement):
            if isinstance(child, ast.stmt):
                yield from _own_statements([child])
            else:
                for grandchild in ast.walk(child):
                    if isinstance(grandchild, ast.stmt):  # pragma: no cover - lambdas hold exprs
                        yield grandchild


def _root(scope: _Scope) -> _Scope:
    while scope.parent is not None:
        scope = scope.parent
    return scope


def _walrus_bindings(statement: ast.stmt) -> Iterator[ast.NamedExpr]:
    """`(writer := os.write)` inside a statement's expressions, not inside a nested def."""
    if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return
    for child in ast.iter_child_nodes(statement):
        if isinstance(child, ast.stmt):
            continue
        for inner in ast.walk(child):
            if isinstance(inner, ast.NamedExpr):
                yield inner


def _populate(scope: _Scope, body: Sequence[ast.stmt]) -> None:
    """Fill one scope's tables from the statements that belong to it.

    Three passes, in this order: names bound (so shadowing is known before anything is
    resolved), imports (so `os` is bound before `_writer = os.write` is read), then
    assignments. A name a `global` statement declares is bound in the module scope
    instead, which is where the assignment really lands.
    """
    statements = list(_own_statements(body))
    declared_global = {
        name
        for statement in statements
        if isinstance(statement, ast.Global)
        for name in statement.names
    }
    for statement in statements:
        for walrus in _walrus_bindings(statement):
            _bind(scope, walrus.target, statement.lineno)
        target_scope = scope
        if declared_global and _binds_a_global(statement, declared_global):
            target_scope = _root(scope)
        _statement_bindings(target_scope, statement)
    for statement in statements:
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                bound = alias.asname or alias.name.split(".")[0]
                scope.modules[bound] = alias.name if alias.asname else bound
        elif isinstance(statement, ast.ImportFrom) and statement.module:
            for alias in statement.names:
                bound = alias.asname or alias.name
                scope.functions.setdefault(bound, []).append(
                    _Binding(statement.lineno, (statement.module, alias.name))
                )
                # `from os import path` also binds a module name.
                scope.modules.setdefault(bound, f"{statement.module}.{alias.name}")
    for statement in statements:
        for walrus in _walrus_bindings(statement):
            if isinstance(walrus.target, ast.Name):
                _record_assignment(scope, walrus.target, walrus.value, statement.lineno)
        # R-SEC-020: an annotated assignment is an assignment. A dataclass field
        # (`handler: Callable = os.write`, or `= field(default=os.write)`) is an
        # `ast.AnnAssign`, and this pass read only `ast.Assign`, so the name was recorded
        # as bound-but-unresolvable - indistinguishable from a value the pass genuinely
        # cannot read, which is what made it worse than a documented gap.
        if isinstance(statement, ast.AnnAssign):
            annotated = statement.target
            if statement.value is not None and isinstance(annotated, ast.Name):
                _record_assignment(
                    _root(scope) if annotated.id in declared_global else scope,
                    annotated,
                    statement.value,
                    statement.lineno,
                )
            continue
        if not isinstance(statement, ast.Assign):
            continue
        # R-SEC-023: this required exactly one target, so `a = b = os.write` resolved
        # neither name - both were recorded bound-but-unresolvable, indistinguishable from
        # a value the pass genuinely cannot read, and `b(fd, body)` was reported by no
        # guard. Chained assignment is an ordinary idiom, not an evasion, and the first
        # pass (`_statement_bindings`) already iterates every target; only this one did
        # not. Same defect as R-SEC-006's shape bound in `content/payload.py`: a pass that
        # handles one concrete spelling of a structure is absent for the others.
        for target, value in _assigned_pairs(statement):
            _record_assignment(
                _root(scope) if target.id in declared_global else scope,
                target,
                value,
                statement.lineno,
            )


def _assigned_pairs(statement: ast.Assign) -> Iterator[tuple[ast.Name, ast.expr]]:
    """Every `(name, value)` an assignment statement binds that this pass can read.

    Three shapes, all ordinary Python and none of them an evasion:

      * `w = os.write` - one target, one value;
      * `a = b = os.write` - several targets, one value. Every name gets the same value
        (R-SEC-023);
      * `a, b = os.write, str.upper` - one tuple target against a tuple value, matched
        element-wise. Nested and starred unpacking are not read: a `*rest` makes the
        pairing depend on the length of a value this pass may not be able to evaluate, and
        guessing it would resolve names to the wrong callables, which is worse than not
        resolving them. `_bind` still records those names as bound, so they still shadow.
    """
    for target in statement.targets:
        if isinstance(target, ast.Name):
            yield target, statement.value
        elif isinstance(target, ast.Tuple | ast.List) and isinstance(
            statement.value, ast.Tuple | ast.List
        ):
            elements = target.elts
            values = statement.value.elts
            if len(elements) != len(values) or any(
                isinstance(element, ast.Starred) for element in elements
            ):
                continue
            for element, value in zip(elements, values, strict=True):
                if isinstance(element, ast.Name):
                    yield element, value


def _binds_a_global(statement: ast.stmt, declared: set[str]) -> bool:
    """Whether a statement assigns one of the names a `global` declaration named."""
    targets: list[ast.expr] = []
    if isinstance(statement, ast.Assign):
        targets = list(statement.targets)
    elif isinstance(statement, ast.AnnAssign | ast.AugAssign):
        targets = [statement.target]
    return any(isinstance(t, ast.Name) and t.id in declared for t in targets)


def _record_assignment(scope: _Scope, target: ast.Name, value: ast.expr, line: int) -> None:
    """Read one `name = <expr>` into the scope's module and function tables."""
    # `mod = io; mod.open(p, "w")`: a module held in a local variable resolves like an
    # `import ... as` alias, which is what round 3 named as a gap it could not follow.
    held_module = _resolve_module(value, scope)
    if held_module is not None:
        scope.modules.setdefault(target.id, held_module)
    resolved = _qualified_target(value, scope)
    if resolved is None and isinstance(value, ast.Call):
        resolved = _partial_target(value, scope) or _field_default_target(value, scope)
    if resolved is not None:
        scope.functions.setdefault(target.id, []).append(_Binding(line, resolved))


def _scoped_calls(
    body: Sequence[ast.stmt], scope: _Scope, *, functions_see: _Scope
) -> Iterator[tuple[ast.Call, _Scope]]:
    """Every call in `body`, paired with the scope whose bindings apply to it.

    `functions_see` is the scope a nested `def` inherits, which is *not* always `scope`: a
    class body's own names are invisible inside its methods, so a method defined in
    `class W` sees the module, not `W`. Resolving `W.handler` is `class_attribute`'s job,
    and conflating the two would put class attributes into method scope where Python does
    not.
    """
    _populate(scope, body)
    yield from _walk_statements(body, scope, functions_see=functions_see)


def _walk_statements(
    body: Sequence[ast.stmt], scope: _Scope, *, functions_see: _Scope
) -> Iterator[tuple[ast.Call, _Scope]]:
    """The calls in an already-populated scope, descending through blocks within it.

    Kept apart from `_scoped_calls` so a nested block does not re-run `_populate` over
    statements the scope has already read: same answer, but each nested `if`/`try` would
    otherwise re-record every binding under it once per level of nesting.
    """
    for statement in body:
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef):
            for decorator in statement.decorator_list:
                yield from _calls_in(decorator, scope)
            for default in [*statement.args.defaults, *statement.args.kw_defaults]:
                if default is not None:
                    yield from _calls_in(default, scope)
            inner = _Scope(parent=functions_see, defined_at=statement.lineno)
            inner.bound.update(
                argument.arg
                for argument in [
                    *statement.args.posonlyargs,
                    *statement.args.args,
                    *statement.args.kwonlyargs,
                ]
            )
            for special in (statement.args.vararg, statement.args.kwarg):
                if special is not None:
                    inner.bound.add(special.arg)
            yield from _scoped_calls(statement.body, inner, functions_see=inner)
        elif isinstance(statement, ast.ClassDef):
            for decorator in statement.decorator_list:
                yield from _calls_in(decorator, scope)
            body_scope = _Scope(parent=scope, defined_at=statement.lineno)
            _populate(body_scope, statement.body)
            # Registered *before* the body is walked: a method that calls `W.handler(...)`
            # is inside the class it names, and a generator that registered afterwards
            # resolved the same call from outside the class and not from within it.
            scope.classes[statement.name] = {
                name: list(bindings) for name, bindings in body_scope.functions.items()
            }
            scope.bases[statement.name] = tuple(
                base for base in (_dotted_name(node) for node in statement.bases) if base
            )
            yield from _walk_statements(statement.body, body_scope, functions_see=scope)
            # R-SEC-019: a nested class's table was registered on the enclosing class's own
            # body scope, reachable only from a call written inside that body. Lifted here
            # under the dotted path a caller outside actually writes. Recursive by
            # construction: each level lifts what the level below it already lifted.
            for nested, table in body_scope.classes.items():
                scope.classes[f"{statement.name}.{nested}"] = table
                scope.bases[f"{statement.name}.{nested}"] = body_scope.bases.get(nested, ())
        else:
            for child in ast.iter_child_nodes(statement):
                if isinstance(child, ast.stmt):
                    yield from _walk_statements([child], scope, functions_see=functions_see)
                else:
                    yield from _calls_in(child, scope)


def _lambda_scope(node: ast.Lambda, scope: _Scope) -> _Scope:
    """A lambda's own scope, with its parameters bound (R-SEC-026)."""
    inner = _Scope(parent=scope, defined_at=node.lineno)
    inner.bound.update(
        argument.arg
        for argument in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
    )
    for special in (node.args.vararg, node.args.kwarg):
        if special is not None:
            inner.bound.add(special.arg)
    return inner


def _calls_in(node: ast.AST, scope: _Scope) -> Iterator[tuple[ast.Call, _Scope]]:
    """Calls inside an expression, paired with the scope whose bindings apply to them.

    R-SEC-026: this walked every descendant against one scope, because the comment above
    it said an expression opens no scope. In Python it does - a comprehension and a lambda
    each introduce one - so a comprehension variable named `os` never shadowed the module
    import, and

        import os
        ...
        [os.replace("Windows", "windows") for os in entries]

    resolved `os.replace` through the *import* and reported a disk write in code that
    touches no file. R-SEC reproduced it three ways (list comp, dict comp, lambda
    parameter). A guard that fires on ordinary code is one the next engineer switches off,
    and then it protects nothing - which is the same reasoning R-SEC-015 was fixed under.

    Python's own scoping rule is followed rather than approximated: the **outermost**
    iterable of a comprehension is evaluated in the enclosing scope, and everything else -
    later iterables, the conditions, the element expressions - inside the comprehension's
    own scope. A lambda's defaults are likewise evaluated where the lambda is written, and
    its body inside its own scope.
    """
    if isinstance(node, ast.Lambda):
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            if default is not None:
                yield from _calls_in(default, scope)
        yield from _calls_in(node.body, _lambda_scope(node, scope))
        return
    if isinstance(node, ast.ListComp | ast.SetComp | ast.GeneratorExp | ast.DictComp):
        inner = _Scope(parent=scope, defined_at=node.lineno)
        for index, generator in enumerate(node.generators):
            yield from _calls_in(generator.iter, scope if index == 0 else inner)
            _bind(inner, generator.target, node.lineno)
        for generator in node.generators:
            for condition in generator.ifs:
                yield from _calls_in(condition, inner)
        if isinstance(node, ast.DictComp):
            yield from _calls_in(node.key, inner)
            yield from _calls_in(node.value, inner)
        else:
            yield from _calls_in(node.elt, inner)
        return
    if isinstance(node, ast.Call):
        yield node, scope
    for child in ast.iter_child_nodes(node):
        yield from _calls_in(child, scope)


def _partial_target(node: ast.Call, scope: _Scope) -> tuple[str, str] | None:
    """The function a `functools.partial(...)` call wraps, if it names one."""
    func = node.func
    name = (
        func.attr
        if isinstance(func, ast.Attribute)
        else func.id
        if isinstance(func, ast.Name)
        else None
    )
    if name not in _PARTIAL_NAMES or not node.args:
        return None
    return _qualified_target(node.args[0], scope)


def _field_default_target(node: ast.Call, scope: _Scope) -> tuple[str, str] | None:
    """The callable a `field(default=os.write)` declaration installs (R-SEC-020)."""
    func = node.func
    name = (
        func.attr
        if isinstance(func, ast.Attribute)
        else func.id
        if isinstance(func, ast.Name)
        else None
    )
    if name not in _FIELD_FACTORY_NAMES:
        return None
    for keyword in node.keywords:
        if keyword.arg in _FIELD_DEFAULT_KEYWORDS:
            return _qualified_target(keyword.value, scope)
    return None


def _mode_argument(node: ast.Call, position: int) -> ast.expr | None:
    for keyword in node.keywords:
        if keyword.arg == "mode":
            return keyword.value
    if len(node.args) > position:
        return node.args[position]
    return None


def _is_a_file_mode_token(value: str) -> bool:
    """Whether a string is plausibly a real `open` mode rather than an English word.

    R-SEC-027. The check used to be `_WRITE_MODE_CHARS & set(value)`: *any* of `w`, `a`,
    `x` or `+` appearing *anywhere* in the string. That is true of most English words, so
    a domain class with its own `.open(mode)` - a session, a connection, a parser - had
    `Parser().open("readonly")` reported as a disk write because "readonly" contains an
    "a". "manual", "active", "auto", "exclusive" and "append-only" all do it too.

    A real mode is short and drawn from a closed alphabet, so that is what is required
    here. This is only ever consulted for the *unresolved-receiver* fallback; a receiver
    that resolved to a real module or class is classified by shape, where the argument in
    the mode position is known to be a mode.
    """
    token = value.strip()
    if not token or len(token) > _MAX_FILE_MODE_CHARS:
        return False
    return set(token) <= _FILE_MODE_CHARS


def _opens_for_writing(node: ast.Call, position: int, label: str) -> str | None:
    """Classify an `open`-shaped call by its mode argument.

    An absent mode is a read. A constant mode is checked for `w`/`a`/`x`/`+`, but only
    once it looks like a mode at all (R-SEC-027). A mode this pass cannot read is
    reported: an unverifiable write is not a cleared one.

    **Does not catch** (stated here rather than left to be rediscovered): a genuine write
    whose mode is spelled in a way `_is_a_file_mode_token` rejects - there is no such
    spelling for the standard library, whose modes are all one to four characters from
    `rwaxbt+`, but a third-party `open`-alike with a long word for a write mode
    (`.open("truncate")`) is now read as a non-mode and passes. That is the direction this
    guard has to err: a guard that reports ordinary code gets switched off, and then it
    catches nothing at all (R-SEC-015).
    """
    mode = _mode_argument(node, position)
    if mode is None:
        return None
    if isinstance(mode, ast.Constant):
        if not isinstance(mode.value, str):
            # The argument in the mode's position is not a mode - `webbrowser.open(url, 2)`
            # takes an int there. Reading it as an unreadable mode would report a browser
            # launch as a disk write, which is the false-positive failure mode R-SEC-015
            # filed: this pass has to stay passable by ordinary code.
            return None
        if not _is_a_file_mode_token(mode.value):
            return None
        if _WRITE_MODE_CHARS & set(mode.value):
            return f"{label}(mode={mode.value!r})"
        return None
    folded = _fold(mode, set())
    if folded is not None:
        if not _is_a_file_mode_token(folded):
            return None
        return f"{label}(mode={folded!r})" if _WRITE_MODE_CHARS & set(folded) else None
    return f"{label}(mode=<computed at runtime>)"


def _is_write_shape(module: str, attribute: str) -> bool:
    """Whether `(module, attribute)` is a shape this guard knows how to classify.

    Kept separate from the classification so a *resolved* receiver is never re-read under
    `pathlib`'s signature as a fallback: `io.open(path)` is a resolved, cleared read, not
    an unknown `.open()` whose mode has to be guessed at position 0.

    R-SEC-016: `open` on a resolved module is classified **whatever the module is**. Round
    3 listed five modules, and `tarfile.open("dump.tgz", "w")` - which resolves perfectly
    well - fell through to the position-0 fallback that reads the *path* for `w`/`a`/`x`,
    reproducing the original R-SEC-010 defect for every stdlib opener outside the list. The
    structural fact is the argument order: everything that reaches this point through a
    resolved module name is a module-level function, and the only mode-first `.open` in
    reach is `pathlib.Path.open`, which is a *bound method on an instance* and so never
    resolves to a module.
    """
    return (
        (module, attribute) in _WRITE_QUALIFIED
        or (module, attribute) in _MODE_AT_ONE_CONSTRUCTORS
        or (module == "os" and attribute == "fdopen")
        or attribute == "open"
    )


def _classify_qualified(node: ast.Call, module: str, attribute: str, label: str) -> str | None:
    """Report a `(module, attribute)` write, reading the mode where the call has one."""
    if (module, attribute) in _WRITE_QUALIFIED:
        return label
    if attribute == "fdopen" and module == "os":
        return _opens_for_writing(node, 1, label)
    if (module, attribute) in _FLAG_STYLE_OPENERS:
        flag = _mode_argument(node, 1)
        if flag is None:
            if (module, attribute) not in _OPENERS_WRITING_BY_DEFAULT:
                return None
            return f"{label}(flag=<default, creates>)"
        folded = _fold(flag, set())
        if folded is None:
            return f"{label}(flag=<computed at runtime>)"
        return f"{label}(flag={folded!r})" if _FLAG_WRITE_CHARS & set(folded) else None
    if attribute == "open" or (module, attribute) in _MODE_AT_ONE_CONSTRUCTORS:
        # R-SEC-010: `io.open`'s signature is `(file, mode)`, the builtin's order - not
        # `pathlib.Path.open`'s `(mode, ...)`. Reading position 0 inspected the *path* for
        # `w`/`a`/`x`/`+`, so `io.open("output.log", "w")` passed while
        # `io.open("leaked.log", "w")` was caught by the accident of an `a` in the name.
        return _opens_for_writing(node, 1, label)
    return None


def _writes_to_disk(node: ast.Call, scope: _Scope) -> str | None:
    func = node.func
    partial = _partial_target(node, scope)
    if partial is not None and partial in _WRITE_QUALIFIED:
        return f"functools.partial({partial[0]}.{partial[1]})"
    if isinstance(func, ast.Attribute):
        if func.attr in _WRITE_ATTRS:
            return func.attr
        module = _resolve_module(func.value, scope)
        if module is not None and _is_write_shape(module, func.attr):
            return _classify_qualified(node, module, func.attr, f"{module}.{func.attr}")
        receiver = _class_receiver(func.value) if module is None else None
        if receiver is not None:
            # R-SEC-014: `class W: handler = os.write` then `W.handler(fd, body)`. The
            # class-body assignment was always indexed; nothing ever looked for it from a
            # call whose receiver is a plain name rather than a module. R-SEC-019/020
            # widened the receiver to a chained one (`Outer.Inner.handler`) and to an
            # immediate instantiation (`Writer().handler`).
            attribute_of_class = scope.class_attribute(receiver, func.attr)
            if attribute_of_class is not None and _is_write_shape(*attribute_of_class):
                bound_module, bound_attribute = attribute_of_class
                label = (
                    f"{receiver}.{func.attr} "
                    f"(class attribute bound to {bound_module}.{bound_attribute})"
                )
                return _classify_qualified(node, bound_module, bound_attribute, label)
        if func.attr == "open":
            # `Path(...).open("w")`, `self._path.open("w")` - the receiver is not knowable,
            # the mode is (R-SEC-001 (d)), and `Path.open` takes the mode first. A receiver
            # that *did* resolve to a module was handled above, at the right position.
            return _opens_for_writing(node, 0, ".open")
    if isinstance(func, ast.Name):
        if func.id == "open" and not scope.is_bound("open"):
            return _opens_for_writing(node, 1, "open")
        bound = scope.function_named(func.id, node.lineno)
        if bound is not None and _is_write_shape(*bound):
            module, attribute = bound
            label = f"{func.id} (bound to {module}.{attribute})"
            return _classify_qualified(node, module, attribute, label)
    return None


def unaudited_disk_write_sweep(root: Path) -> list[Violation]:
    """No server module outside the credential store may write to disk.

    This is the seed of the trace-content audit: WS-13 owns the redacted trace sink and
    the sentinel canary, and until it exists the honest guarantee is the stronger, cruder
    one - server code writes nothing at all except the token store. A new writer must be
    added to the allowlist deliberately, in a diff a reviewer sees.

    Catches: `.write_text` / `.write_bytes` / `.writelines` on any receiver; `open(...)`
    and `<anything>.open(...)` with a writing mode, including `Path(out).open("w")`;
    `os.write`, `os.open`, `os.fdopen` with a writing mode; `os.replace` / `os.rename` /
    `os.link` / `os.symlink`; `shutil.copy*` / `shutil.move`; `tempfile` file factories;
    `json` / `pickle` / `marshal` `.dump`. A mode expression this pass cannot evaluate is
    reported rather than assumed to be a read.

    Since R-SEC-009/010 it also resolves the name a write is reached through, because
    every one of these is an ordinary refactor rather than an evasion: a module alias
    (`import os as o; o.write(...)`), a `from`-import alias
    (`from os import write as w; w(fd, body)`), a plain re-binding
    (`_writer = os.write; _writer(...)`), `functools.partial(os.write)`, a class attribute
    (`class W: handler = os.write; W.handler(fd, body)`, R-SEC-014) and a module held in a
    local variable (`mod = io; mod.open(p, "w")`).

    Since R-SEC-019/020 the class-attribute path is receiver-shape-agnostic in the two ways
    a class attribute is normally reached: a **nested** class
    (`class Outer: class Inner: handler = os.write`, called as `Outer.Inner.handler(...)`,
    a chained `ast.Attribute` the bare-`Name` branch skipped entirely) and an **annotated**
    attribute, which is how a dataclass declares one (`handler: Callable = os.write`, or
    `= field(default=os.write)`; both are `ast.AnnAssign`, which the resolution pass did
    not read at all, so the name was recorded as bound-but-unresolvable and looked exactly
    like a value the pass genuinely cannot read). An immediate instantiation
    (`Writer().handler(...)`) resolves too, since that is how a dataclass field default is
    normally called.

    The mode argument is read at the position the *receiver's* signature puts it: position
    1 for the builtin and for **any** `.open` reached through a resolved module, position 0
    for `pathlib`'s mode-first `Path.open`, which is a bound method on an instance and so
    never resolves to a module. Round 3 made that a five-module list, and R-SEC-016 showed
    `tarfile.open("dump.tgz", "w")` therefore fell back to reading the *path* for
    `w`/`a`/`x` - R-SEC-010's original defect, reproduced for every stdlib opener outside
    the list. `shelve` and the `dbm` family spell their mode as a dbm flag
    (`r`/`w`/`c`/`n`) and are read that way; `shelve.open(path)`, whose default flag creates
    the file, is reported with no flag argument at all.

    A binding made by a walrus (`(w := os.write)`) or routed to module scope by a `global`
    declaration is read the same way, because both are assignments that a reader would call
    ordinary. Since R-SEC-023 that also covers a **chained** assignment
    (`a = b = os.write`, which resolved *neither* name before) and an element-wise
    **tuple** assignment (`a, b = os.write, str.upper`); starred unpacking is not read,
    because the pairing then depends on a length this pass may not know and a wrong pairing
    resolves a name to the wrong callable.

    Since R-SEC-024 a class attribute is also found through **inheritance**
    (`class Base: handler = os.write` / `class Sub(Base): pass` / `Sub.handler(fd, body)`),
    following bases depth-first in declaration order with the class's own body winning. A
    base class imported from another module is not followed - this pass reads one file.

    Names are resolved **per scope** (R-SEC-015). A binding made inside one function is not
    applied to a call in another, because a guard that reports innocent code gets switched
    off and then protects nothing; within the scope that owns a name, the binding in force
    at a call is the most recent one above it.

    Does not catch:

      * a bare `handle.write(...)` where the handle was obtained somewhere this pass did
        not see - the `open` that produced it is normally the violation;
      * an alias reached through a data structure (`{"w": os.write}["w"](...)`), returned
        from a function (`pick()(fd, body)`), or installed by a decorator;
      * an **instance** attribute: `self.handler = os.write` then `self.handler(...)`. Only
        class-body attributes are indexed, because `self` is not a name this pass can tie
        to a class;
      * `getattr(os, "write")(...)`, a write through a C extension or a third-party
        library's own file API, or a file written by a subprocess;
      * a third-party `open`-alike whose write mode is spelled as a word rather than as a
        mode token - `session.open("truncate")`. Since R-SEC-027 the unresolved-receiver
        fallback fires only on strings that look like real modes (at most four characters
        from `rwaxbt+U`), because the previous rule read *any* `w`, `a`, `x` or `+`
        anywhere in the string and so reported `Parser().open("readonly")` as a write. No
        stdlib mode is spelled any other way;
      * a stdlib *constructor* that writes and is not named in `_MODE_AT_ONE_CONSTRUCTORS`.
        `zipfile.ZipFile` and `tarfile.TarFile` are there since R-SEC-016; the structural
        rule covers `.open()` only, and a constructor has no shape to recognise;
      * an `.open()` whose receiver still resolves to nothing - a module returned from a
        call, say - which is read with `pathlib`'s mode-first signature and will miss
        `mod.open(path, "w")` reached that way;
      * an **instance held in a variable**: `w = Writer(); w.handler(fd, body)`. The
        immediate `Writer().handler(...)` form resolves and `self.handler` never will, but
        a name holding an instance is not tracked back to its class;
      * a base class defined in **another module** (`from base import Writer` /
        `class Sub(Writer): pass`), or a base named by an expression rather than a dotted
        path. Inheritance is followed only within the file being read;
      * `field(default_factory=lambda: os.write)`, the only `default_factory` form that
        actually works for a callable-typed field: `_qualified_target` does not evaluate an
        `ast.Lambda`. The bare `field(default_factory=os.write)` *is* resolved, but that
        form raises `TypeError` at construction and never runs, so what round 5's handoff
        called "learns `field(default_factory=...)`" holds for the syntax and not for the
        working idiom (R-SEC-025, left open this round);
      * a name rebound by anything other than a plain assignment before the call - a `for`
        target or a `with ... as` binding shadows correctly, but a rebinding inside a
        branch this pass cannot order (a `while` body, a `try`/`except` pair) is resolved
        by line number, which is an approximation of control flow and not control flow;
      * a closure whose **free variable is bound after the closure is created**:

            def process(fd, body):
                def dispatch():
                    writer(fd, body)
                writer = os.write     # below the `def`, so not seen
                dispatch()

        This is the false negative R-SEC-017's fix trades for. An enclosing function's
        local is resolved as of the line the closure was created, because resolving it as
        of the last binding in the file reported the far more common
        closure-then-reconfigure shape as an unconditional write, and a guard that fires on
        innocent code is one that gets switched off. Module-level names keep the
        last-binding rule, which is where its justification actually holds.

    It is a guard against a writer landing unnoticed, not a sandbox.
    """
    violations: list[Violation] = []
    for path in iter_python_files(root):
        if any(str(path).endswith(allowed) for allowed in _WRITE_ALLOWLISTED_MODULES):
            continue
        tree = _parse(path)
        if tree is None:
            continue
        module_scope = _Scope()
        for node, scope in _scoped_calls(tree.body, module_scope, functions_see=module_scope):
            kind = _writes_to_disk(node, scope)
            if kind is not None:
                violations.append(
                    Violation(
                        "unaudited-disk-write",
                        path,
                        node.lineno,
                        f"{kind} in server code outside the credential store; mail content "
                        "at rest is forbidden by default (SEC-05)",
                    )
                )
    return violations


# --- guard 7: unwrapped HTTP clients (SEC-07, R-ARCH-006) --------------------------------

#: The one module allowed to construct a raw `httpx` client: it is where the allowlist
#: transport is attached, so a client built here is a wrapped one by construction.
_CLIENT_ALLOWLISTED_MODULES = {"mailweave/net/egress.py"}

#: The package whose client constructors are guarded, and their names. Matched against the
#: whole `httpx.*` package rather than the exact module string `"httpx"`: `httpx.Client` is
#: *defined* in `httpx._client`, so `import httpx._client as hc; hc.Client()` builds the
#: identical class object with a real, unwrapped transport (R-SEC-022). The submodule path
#: is an ordinary one-line import, not obfuscation, and there is no `httpx` submodule whose
#: `Client`/`AsyncClient` is a different thing.
_HTTP_CLIENT_PACKAGE = "httpx"
_HTTP_CLIENT_NAMES = {"Client", "AsyncClient"}


def _is_http_client_constructor(target: tuple[str, str]) -> bool:
    """Whether a resolved `(module, attribute)` names an `httpx` client constructor."""
    module, attribute = target
    if attribute not in _HTTP_CLIENT_NAMES:
        return False
    return module == _HTTP_CLIENT_PACKAGE or module.startswith(f"{_HTTP_CLIENT_PACKAGE}.")


def unwrapped_http_client_sweep(root: Path) -> list[Violation]:
    """Only `net/egress.py` may construct an `httpx` client; everyone else calls its builder.

    `egress.py` has always described `build_client`/`build_async_client` as "the only
    supported way to get an HTTP client in server code", and nothing enforced it
    (R-ARCH-006). The allowlist is a *transport wrapper*: a client constructed without it
    is an ordinary client that will speak to any host it is given, so the adoption of the
    wrapper is the whole of the property, and adoption enforced by a docstring is
    adoption enforced by nothing. SEC-07's network capture proves the property for the
    code that ran; this makes it hold for the code that has not run yet.

    Catches: `httpx.Client(...)` / `httpx.AsyncClient(...)`, the same call through a module
    alias (`import httpx as h; h.Client()`), through a `from`-import
    (`from httpx import AsyncClient as AC; AC()`), and through a plain rebinding
    (`_ctor = httpx.Client; _ctor()`) - the same per-scope name resolution the disk-write
    guard uses, and the same ordinary refactors it was built for. Since R-SEC-023 that
    includes a chained assignment (`a = b = httpx.Client; b()`) and an element-wise tuple
    assignment. Since R-SEC-022 it also includes any **private submodule path** to the same
    class - `import httpx._client as hc; hc.Client()` is `httpx.Client` exactly
    (`hc.Client is httpx.Client`), with a real `httpx.HTTPTransport` and no allowlist, and
    the round-5 guard matched the module string `"httpx"` and could not see it.

    It also resolves a class attribute, a nested class attribute and a dataclass field
    default (`class W: ctor = httpx.Client; W.ctor()`), because it shares the disk-write
    guard's resolution engine - that was true in round 5 and unmentioned here, which is
    how a guard comes to be trusted for more than it was tested for. Since R-SEC-024 an
    attribute inherited from a base class in the same file resolves too.

    Does not catch, and each of these is exercised against this guard by
    `test_each_documented_http_client_gap_is_really_a_gap`:

      * a client obtained from a data structure (`{"c": httpx.Client}["c"]()`), from a
        factory function's return value, or through `getattr(httpx, "Client")()`;
      * a subclass of `httpx.Client` defined elsewhere and instantiated by its own name;
      * an **instance** attribute - `self.ctor = httpx.Client` then `self.ctor()` - and an
        **instance held in a variable** - `w = Holder(); w.ctor()`. Both are named in the
        disk-write guard's own gap list; this guard inherited the mechanism in round 5 and
        not the disclosure (R-SEC-024);
      * a base class imported from another module, whose body this pass never reads;
      * a third-party library that opens its own sockets, or a subprocess.

    It bounds the ordinary way a client gets built without the allowlist, not every way a
    socket can be opened - `AllowlistTransport` itself, and the capture, are the
    enforcement.
    """
    violations: list[Violation] = []
    for path in iter_python_files(root):
        if any(str(path).endswith(allowed) for allowed in _CLIENT_ALLOWLISTED_MODULES):
            continue
        tree = _parse(path)
        if tree is None:
            continue
        module_scope = _Scope()
        for node, scope in _scoped_calls(tree.body, module_scope, functions_see=module_scope):
            target = _qualified_target(node.func, scope)
            if target is not None and _is_http_client_constructor(target):
                violations.append(
                    Violation(
                        "unwrapped-http-client",
                        path,
                        node.lineno,
                        f"{target[0]}.{target[1]} constructed outside net/egress.py; a client "
                        "built without the allowlist transport reaches any host it is given "
                        "(AD D.8, SEC-07). Use net.build_client / net.build_async_client",
                    )
                )
    return violations


# --- registry ----------------------------------------------------------------------------

GuardFn = Callable[[Path], list[Violation]]

# --- guard 8: the model host is setup-time only (AD D.8, ADV-210, PF-5) ------------------

#: The one module permitted to name the model host or the setup allowlist. Everything else
#: in server code must be unable to reach it, which is the property PF-5 verifies by running
#: the whole suite cold with that host blocked.
_MODEL_HOST_ALLOWLISTED_MODULES = {"mailweave/models/provision.py", "mailweave/constants.py"}

#: Names whose use outside those modules would put the model host on a runtime path.
_MODEL_HOST_NAMES = {"MODEL_HOST", "MODEL_CDN_HOST", "MODEL_CDN_HOST_ALT", "SETUP_EGRESS_ALLOWLIST"}

#: The provisioner is the module that can reach the host, so **importing** it is the other
#: half of D.8's "never invoked from the server process". `cli.py` imports it inside the
#: `setup-models` function, which is the one legitimate caller; the loader deliberately goes
#: through `models/paths.py` and `models/verify.py` instead, so the server's import graph
#: does not contain the provisioner at all.
_PROVISIONER_MODULE = "mailweave.models.provision"
_PROVISIONER_IMPORTERS = {"mailweave/cli.py", "mailweave/models/__init__.py"}


def model_host_sweep(root: Path) -> list[Violation]:
    """No server module but the provisioner may name the model host or its allowlist.

    D.8's rule is that `mailweave setup-models` is the only code path that contacts the
    model host, and that it is never invoked from the server process or a query path. That
    is a claim about reachability, and the cheap half of it is checkable statically: a
    module that cannot name the host cannot widen the allowlist to include it.

    Catches: any use of the host names or the setup allowlist outside the provisioner and
    `constants.py`; any import of `mailweave.models.provision` outside the CLI and the
    package's own `__init__`; and any folded string literal naming the host, so the
    R-SEC-008 byte-string spelling counts.

    Does not catch: a host assembled at runtime from values no static pass can read, a
    request to an IP address, or a redirect from an allowlisted host to the model host - the
    transport's `check_url` bounds that last one and this sweep does not. It also says
    nothing about whether the provisioner is *called*; the expensive half of D.8's claim is
    PF-5, which runs the whole suite cold with the host blocked. This sweep catches the
    regression PF-5 would catch months later, on the day someone adds a convenient import.
    """
    violations: list[Violation] = []
    for path in iter_python_files(root):
        if any(str(path).endswith(allowed) for allowed in _MODEL_HOST_ALLOWLISTED_MODULES):
            continue
        tree = _parse(path)
        if tree is None:
            continue
        if not any(str(path).endswith(allowed) for allowed in _PROVISIONER_IMPORTERS):
            for node in ast.walk(tree):
                imported = node.module if isinstance(node, ast.ImportFrom) else None
                names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else []
                if imported == _PROVISIONER_MODULE or _PROVISIONER_MODULE in names:
                    violations.append(
                        Violation(
                            "no-model-host-at-runtime",
                            path,
                            node.lineno,
                            "importing the provisioner puts the model host in this module's "
                            "import graph; D.8 keeps it out of the server process",
                        )
                    )
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in _MODEL_HOST_NAMES:
                violations.append(
                    Violation(
                        "no-model-host-at-runtime",
                        path,
                        node.lineno,
                        f"{node.id} names the model host outside the provisioner; D.8 makes "
                        "it reachable from `mailweave setup-models` and nowhere else",
                    )
                )
            elif isinstance(node, ast.Attribute) and node.attr in _MODEL_HOST_NAMES:
                violations.append(
                    Violation(
                        "no-model-host-at-runtime",
                        path,
                        node.lineno,
                        f"{node.attr} names the model host outside the provisioner",
                    )
                )
        for line, value in _string_literals(tree):
            if value in {"huggingface.co", "hf.co"} or value.endswith(
                (".huggingface.co", ".hf.co")
            ):
                violations.append(
                    Violation(
                        "no-model-host-at-runtime",
                        path,
                        line,
                        f"string literal {value!r} names the model host directly",
                    )
                )
    return violations


#: Every way this codebase could come to accept an inbound connection, by name. Names rather
#: than a call-graph, because the property SEC-07 states is about the *process*: a module that
#: cannot name `bind` cannot open a listening socket, and one that can is where to look.
#:
#: `socket.socket` itself is not here and that is deliberate. An outbound client opens one, and
#: `net/egress.py`'s allowlist is what governs those - a guard that flagged every socket would
#: be flagged into uselessness within a round. What makes a socket a *listening* socket is
#: `bind`/`listen`/`accept`, and those are the names below.
_LISTEN_CALLS: Final[frozenset[str]] = frozenset(
    {
        "bind",
        "listen",
        "accept",
        "create_server",
        "start_server",
        "start_unix_server",
        "serve_forever",
        "run_app",
    }
)

#: Server frameworks and inbound-transport libraries. Importing one of these into server code
#: is the commonest way a "let me add a health endpoint" change becomes a listening socket.
_LISTENING_MODULES: Final[frozenset[str]] = frozenset(
    {
        "http.server",
        "socketserver",
        "wsgiref",
        "wsgiref.simple_server",
        "uvicorn",
        "hypercorn",
        "gunicorn",
        "flask",
        "fastapi",
        "starlette",
        "aiohttp.web",
        "tornado",
        "tornado.web",
        "werkzeug.serving",
        "waitress",
        "xmlrpc.server",
    }
)


#: The one module permitted to open an inbound socket, and why. `mailweave auth login` runs
#: Google's installed-app loopback flow: it binds `127.0.0.1` on an ephemeral port for the
#: duration of one consent and closes it. That is a **setup-time command the owner runs**, not
#: the served process - the same distinction D.8 draws for the model host, and the same
#: allowlist shape.
_LOOPBACK_RECEIVER: Final[str] = "mailweave/auth/consent.py"

#: The receiver's own names. Nothing outside `_LOOPBACK_RECEIVER` may name one: the module is
#: in the serve path's import graph (it also holds the token reader), so the allowlist alone
#: would let a second listener be written anywhere and merely blame the wrong file.
_RECEIVER_NAMES: Final[frozenset[str]] = frozenset(
    {"HTTPServer", "ThreadingHTTPServer", "BaseHTTPRequestHandler", "free_loopback_port"}
)


def listening_socket_sweep(root: Path) -> list[Violation]:
    """SEC-07's third clause: this server has no listening socket, and stdio is why.

    AD D.1 puts MailWeave on **stdio**: one long-lived process reading a pipe, with no port,
    no bind and nothing for a scanner to find. That is a property of the transport rather than
    a configuration, and it is the reason SEC-07 can ask for a port scan and expect nothing -
    so the regression it guards against is not a misconfiguration, it is a **line of code**:
    the health endpoint, the metrics exporter, the "just for local debugging" HTTP server that
    somebody adds and does not remove.

    Catches: a call to `bind`, `listen`, `accept`, `create_server`, `start_server`,
    `start_unix_server`, `serve_forever` or `run_app` at any attribute depth; and an import of
    a server framework or inbound-transport module (`http.server`, `socketserver`, `uvicorn`,
    `fastapi`, `aiohttp.web`, `tornado`, and the rest of `_LISTENING_MODULES`).

    **Does not catch**, and each of these is exercised against this guard by
    `test_each_documented_listening_socket_gap_is_really_a_gap`:

      * a listener opened through a name this pass cannot read - `getattr(sock, "bi" + "nd")()`,
        a method held in a dict, a C extension that binds internally;
      * a subprocess that listens (`subprocess.Popen(["python", "-m", "http.server"])`), which
        is a different process and not this one's socket - though it is still a socket on the
        machine, which is why SEC-07 asks for a scan and not only for this;
      * an inbound connection over a transport with no `bind` at all, such as a library that
        registers a handler with an already-listening parent.

    What it does is make the *cheap* half of SEC-07 continuous. The scan stays the evidence for
    the property; this catches the commit that would have broken it, on the day it is written
    rather than on the day somebody next runs a scanner.

    **One allowlisted module, and one residue that is recorded rather than closed.**
    `mailweave/auth/consent.py` runs Google's installed-app loopback flow and is exempt: it is
    a setup-time command, exactly as `mailweave setup-models` is for the model host. The
    residue is that the serve path imports that module - for the token reader and an error
    class that live in it - so `http.server` is in the server process's import graph even
    though nothing there calls it. Importing a class is not opening a socket and this guard
    does not pretend otherwise; what it does instead is refuse the receiver's *names*
    (`HTTPServer`, `BaseHTTPRequestHandler`, `free_loopback_port`) anywhere else, so a second
    listener cannot be written somewhere the allowlist would not have blamed. Splitting the
    token reader out of that module would close the residue properly, and that is R-M2-020.
    """
    violations: list[Violation] = []
    for path in iter_python_files(root):
        tree = _parse(path)
        if tree is None:
            continue
        receiver = str(path).replace("\\", "/").endswith(_LOOPBACK_RECEIVER)
        for node in ast.walk(tree):
            if not receiver and isinstance(node, ast.Name | ast.Attribute):
                named = node.id if isinstance(node, ast.Name) else node.attr
                if named in _RECEIVER_NAMES:
                    violations.append(
                        Violation(
                            "no-listening-socket",
                            path,
                            node.lineno,
                            f"{named} is the loopback consent receiver; only "
                            f"{_LOOPBACK_RECEIVER} may name it, and only `mailweave auth "
                            "login` runs it",
                        )
                    )
            if receiver:
                continue
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in _LISTENING_MODULES or any(
                        alias.name.startswith(f"{module}.") for module in _LISTENING_MODULES
                    ):
                        violations.append(
                            Violation(
                                "no-listening-socket",
                                path,
                                node.lineno,
                                f"{alias.name} is an inbound-transport module; MailWeave is a "
                                "stdio server and SEC-07 asserts it opens no listening socket",
                            )
                        )
            elif isinstance(node, ast.ImportFrom) and node.module in _LISTENING_MODULES:
                violations.append(
                    Violation(
                        "no-listening-socket",
                        path,
                        node.lineno,
                        f"{node.module} is an inbound-transport module; MailWeave is a stdio "
                        "server and SEC-07 asserts it opens no listening socket",
                    )
                )
            elif isinstance(node, ast.Call):
                called = node.func
                name = (
                    called.attr
                    if isinstance(called, ast.Attribute)
                    else (called.id if isinstance(called, ast.Name) else None)
                )
                if name in _LISTEN_CALLS:
                    violations.append(
                        Violation(
                            "no-listening-socket",
                            path,
                            node.lineno,
                            f"{name}() opens or serves an inbound connection; AD D.1 puts this "
                            "server on stdio and SEC-07 asserts no listening socket",
                        )
                    )
    return violations


GUARDS: dict[str, GuardFn] = {
    "ground-truth-isolation": ground_truth_sweep,
    "forbidden-import": forbidden_imports,
    "scope-literal": scope_literal_sweep,
    "gmail-endpoint": gmail_path_sweep,
    "generative-client": generative_client_sweep,
    "unaudited-disk-write": unaudited_disk_write_sweep,
    "unwrapped-http-client": unwrapped_http_client_sweep,
    "no-model-host-at-runtime": model_host_sweep,
    "no-listening-socket": listening_socket_sweep,
}


def run_all(root: Path, guards: Iterable[str] | None = None) -> list[Violation]:
    selected: Sequence[str] = list(guards) if guards else list(GUARDS)
    found: list[Violation] = []
    for name in selected:
        found.extend(GUARDS[name](root))
    return found
