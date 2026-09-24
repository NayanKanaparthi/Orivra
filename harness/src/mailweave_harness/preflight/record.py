"""Writing a probe's record, and refusing to write mail content into one (OD-4).

The probes run against the owner's real mailbox. OD-4 permits metadata, id, timing and
structure-only diagnostics without approval, and requires explicit per-incident approval
before any actual mail *text* is persisted or surfaced. A probe record is persisted, so the
rule is enforced mechanically rather than by each probe remembering:

`assert_record_is_content_free` walks the whole record and refuses any string that is
multi-line, longer than `MAX_RECORD_STRING`, or not on the probe's declared allowlist of
free-text fields (which hold the probe's *own* prose - `measures`, `validates` and the
like - written by us, not by a correspondent).

This is deliberately the same shape as amendment A6's sealed-scalar bound, and for the same
reason: "no mail text lands here" is checkable by shape, and a promise that it will not is
not checkable at all.

## R-SEC-042: the shape it was checkable for was the one shape its author had in mind

Round 11's walk carried a single `key`, set at the first dict level and then passed down
unchanged, so **every string under an exempt top-level key inherited the exemption at any
depth**. `{"notes": {"raw_snippet": <a mail body>}}` was written without complaint while the
identical text under a non-exempt key was correctly refused. The docstring said the property
was "checkable by shape"; it was checkable for flat shapes, which is what the six shipped
probes emit and therefore all anyone had looked at. Same class as R-SEC-032: a guard
validated against one shape, its peers trusted.

Two things changed, and both are about shapes nobody has written yet:

  * the walk carries the **whole path**, and the exemption applies only where the prose
    actually lives. `notes.raw_snippet` is not `notes`, and neither is `findings.notes`;
  * **dict keys are checked too.** Nothing ever checked them, so a record could carry mail
    text as a key and be written out with it: `{"<a mail body>": 1}` passed. A key is never
    our prose, so it is checked and never exempt.

## R-SEC-048: "then nothing but list indices" had no floor and no ceiling

Round 12's exemption was one prose key followed by *any number* of list indices, and the
docstring said that was "exactly the shape `notes` and `pre_registered_rules` are written in".
It was not. `notes[0]` is that shape; `notes[0][0]` is not, and neither is `title[0]` - five of
the seven prose keys are written as plain strings, so even one level of list nesting under them
was already wider than the producer. A body buried in nested lists under any exempt key passed
at any depth and `json.dumps` wrote it out intact.

The exemption is now **the producer's own shape**, taken from `spec.PROSE_FIELDS`, which
carries a list depth per key rather than a bare name. `notes[0]` is prose; `notes[0][0]` is
structure somebody added, and its strings have never been read by anyone.

Two more shapes the walk did not enter: sets, frozensets and non-`dict` mappings were never
descended into at all, so their contents were unchecked - `json.dumps` would then have raised,
which is a crash rather than a refusal, and the docstring claimed a walk "at any depth". The
walk now **refuses what it cannot read**: a record contains the JSON types or it is refused,
which is the same move as bounding by shape rather than by intention. Enumerating the
containers a walk should enter has the failure mode this project keeps meeting; enumerating the
ones it *can* enter, and refusing the rest, does not.

## R-SEC-055: "refuses what it cannot read" was `isinstance`, and there are two writers

`isinstance(record, dict)` admits a subclass, and a `dict` subclass whose `items()`, `keys()`
and `__iter__` return nothing is a container the walk cannot read: it was read as **empty** and
passed. The defence offered for that was "the checker and the writer agree, because
`json.dumps` uses the same overridden iteration". One writer agreed. `write_records` calls
`json.dumps` **and** `render_summary`, and `render_summary` reads `row["credential"]` by
`__getitem__` and formats it into `SUMMARY.md` - so a body hidden from the walk was written out
in full, on a key that is not even declared prose.

The rule is now the JSON types **themselves**, not things that pass `isinstance` for them, and
the reason is that second writer rather than tidiness. A subclass may differ from its base at
every interface the two writers use, and they do not use the same ones:

  * `json.dumps` iterates a mapping with `items()` and renders a scalar with the base type's
    formatting;
  * `render_summary` looks a key up with `__getitem__` and interpolates a value with `__str__`.

Found while fixing R-SEC-055 and not filed by anyone: `class Sneaky(int)` with a `__str__` that
returns a body passes an `isinstance(record, bool | int | float)` check, is written to the JSON
as `1`, and puts the body into `SUMMARY.md` through `f"budget {row['quota_budget_units']} u"`.
That is R-SEC-055 exactly, one type over, and it is why the scalars are exact-typed here and not
only the containers. What the six shipped probes emit is already the exact types - `as_record`
writes literals, `list(...)`, `dict`s and `enum.value` - so nothing legitimate is refused, which
`tests/test_preflight_probes.py` asserts rather than assumes.

Message ids are permitted by AD A.11 ("IDs and metadata are persisted by default") but are
**not** written by default anyway: probes record counts and salted digests, and a probe that
wants raw ids has to be run with `--include-ids`, which is recorded in the file.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, NoReturn

from mailweave.constants import is_one_line
from mailweave_harness.preflight.spec import PROSE_FIELDS, ProbeResult

#: The longest string a findings value may be. Long enough for a code point list or an
#: endpoint name, far too short for a body.
MAX_RECORD_STRING: Final[int] = 200

#: One path segment of a record: a mapping key or a sequence index.
Segment = str | int


class RecordWouldCarryContent(RuntimeError):
    """A probe record contains something shaped like mail text. Nothing is written."""


def _is_our_prose(path: tuple[Segment, ...]) -> bool:
    """Whether `path` names one of this repository's own declared prose values.

    Exactly one leading key, which must be a declared prose field, followed by **exactly the
    list indices the producer writes that key under** - none for the five keys `as_record`
    emits as plain strings, one for the two it emits as lists of sentences. A dict below a
    prose key is not prose; neither is a second list (R-SEC-048). Both are structure somebody
    added under a name that used to mean prose, and their strings have never been read by
    anyone.

    The depth comes from `spec.PROSE_FIELDS`, beside the code that writes the record, so this
    cannot drift from the producer without a test noticing.
    """
    if not path or not isinstance(path[0], str):
        return False
    depth = PROSE_FIELDS.get(path[0])
    if depth is None:
        return False
    indices = path[1:]
    return len(indices) == depth and all(isinstance(segment, int) for segment in indices)


def _render(path: tuple[Segment, ...]) -> str:
    """A readable path, with any segment that is itself over the bound withheld.

    A key can be the offending value, and naming it in the refusal would put the mail text
    into an exception message to complain that it was about to be put into a file.
    """
    if not path:
        return "<root>"
    rendered = ""
    for segment in path:
        if isinstance(segment, int):
            rendered += f"[{segment}]"
            continue
        safe = is_one_line(segment) and len(segment) <= MAX_RECORD_STRING
        rendered += f".{segment}" if safe else ".<key withheld>"
    return rendered.lstrip(".")


def _plain(value: str) -> str:
    """`value`'s actual characters, as a `str` rather than as whatever subclass it is.

    A `str` subclass may override `__len__`, `splitlines` and `__str__`, so measuring one on
    its own word means taking a 400-character body's word for it being three characters long.
    `str.__add__` is the base implementation and returns an exact `str`, so what is measured
    below is what would be written to the file rather than what the value says about itself.
    Contrived as an attack; free as a defence, and the bound is only meaningful if it is taken
    on the characters.
    """
    return value if type(value) is str else str.__add__(value, "")


def _over_the_bound(value: str, where: str) -> str | None:
    """The bound itself: one line, and short. No exemption is consulted here."""
    # `constants.is_one_line`, imported. This is the *fourth* layer to need the predicate;
    # the previous three each wrote it out, and two of them were found doing so by a
    # reviewer rather than by a test (R-SEC-029, R-ARCH-031).
    text = _plain(value)
    if not is_one_line(text):
        return f"{where}: multi-line string"
    if len(text) > MAX_RECORD_STRING:
        return f"{where}: {len(text)} characters, over the {MAX_RECORD_STRING} bound"
    return None


def _refuse_unreadable(what: str, where: str) -> NoReturn:
    """A value the walk cannot read is refused, not skipped (R-SEC-048).

    Silence is the defect: a container the walk steps over is a container whose contents are
    unchecked, and the record is written anyway. Neither the type name nor the path can carry
    mail text - the path's own segments are already bounded by `_render`.
    """
    raise RecordWouldCarryContent(
        f"a preflight record holds a {what} at {where}, which this check cannot read. A "
        "record is JSON: strings, numbers, booleans, null, objects and arrays. A value of "
        "another type is either not writable at all or writable with its contents never "
        "checked, and an unchecked value is how mail text reaches a file (OD-4, R-SEC-048)."
    )


def _refuse(problem: str) -> None:
    raise RecordWouldCarryContent(
        f"a preflight record would carry {problem}. Probes persist counts, closed "
        "vocabulary tokens and digests; persisting mail text needs the owner's explicit "
        "per-incident approval (OD-4), which a probe run does not have."
    )


def assert_record_is_content_free(record: Any, *, path: tuple[Segment, ...] = ()) -> None:
    """Walk a record and refuse anything shaped like mail text, at any depth (OD-4).

    A record may be made of the JSON types and nothing else: `str`, `int`, `float`, `bool`,
    `None`, `dict`, `list` and `tuple` - the types themselves, tested with `type(...) is` and
    not with `isinstance`, because a subclass is exactly a thing that answers one interface
    differently from another and this record has two writers (R-SEC-055; see the module
    docstring). Anything else is **refused rather than stepped over**, which is what makes "at
    any depth" true instead of "at any depth among the containers whoever wrote this thought
    of" (R-SEC-048). Sets, frozensets and `collections.UserDict` were previously not walked at
    all, so their contents reached `json.dumps` unchecked - which then raised, leaving a crash
    as the only thing between a body and a file.
    """
    if type(record) is str:
        if not _is_our_prose(path):
            problem = _over_the_bound(record, _render(path))
            if problem is not None:
                _refuse(problem)
        return
    if record is None or type(record) in (bool, int, float):
        return
    if type(record) is dict:
        for name, value in record.items():
            key = _key_of(name, path)
            key_path = (*path, key)
            # The key is bounded exactly as a value is, and **never** through the prose
            # exemption: a key is a name this repository or a probe chose, so a key that is
            # multi-line or 400 characters long is mail text whatever it sits beside.
            # Nothing checked keys at all until round 12, so `{<a mail body>: 1}` was
            # written out intact.
            key_problem = _over_the_bound(key, f"{_render(key_path)} (as a key)")
            if key_problem is not None:
                _refuse(key_problem)
            assert_record_is_content_free(value, path=key_path)
        return
    if type(record) is list or type(record) is tuple:
        for index, item in enumerate(record):
            assert_record_is_content_free(item, path=(*path, index))
        return
    _refuse_unreadable(type(record).__name__, _render(path))


def _key_of(name: object, path: tuple[Segment, ...]) -> str:
    """A mapping key as the string it will be written as, or a refusal.

    `json.dumps` renders `str`, `int`, `float`, `bool` and `None` keys and refuses the rest, so
    those are the keys a record may have. Anything else is refused here rather than left to a
    `TypeError` from the writer, and a `str` subclass is reduced to its characters for the same
    reason values are.
    """
    if type(name) is str:
        return _plain(name)
    if name is None or type(name) in (bool, int, float):
        return str(name)
    _refuse_unreadable(f"{type(name).__name__} key", _render(path))


def digest(value: str, salt: bytes) -> str:
    """A salted, truncated digest of an id: joinable within one run, opaque across runs."""
    return hashlib.sha256(salt + value.encode("utf-8")).hexdigest()[:16]


def run_salt() -> bytes:
    return secrets.token_bytes(16)


def write_records(results: Iterable[ProbeResult], out_dir: Path) -> Path:
    """Write one JSON record per probe plus a Markdown summary. Returns the summary path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamped = datetime.now(UTC).isoformat()
    rows: list[dict[str, Any]] = []
    for result in results:
        record = result.as_record()
        record["recorded_at"] = stamped
        assert_record_is_content_free(record)
        (out_dir / f"{result.spec.id}.json").write_text(
            json.dumps(record, indent=2, sort_keys=True), encoding="utf-8"
        )
        rows.append(record)
    summary = out_dir / "SUMMARY.md"
    summary.write_text(render_summary(rows, stamped), encoding="utf-8")
    return summary


def render_summary(rows: list[dict[str, Any]], stamped: str) -> str:
    lines = [
        "# Loop-0 preflight record",
        "",
        f"Run at {stamped}. One section per probe. A verdict of `fail` is a **result**, not",
        "an error: the consequence it forces is written in the probe and was written before",
        "the run.",
        "",
        "| Probe | Verdict | Validates |",
        "|---|---|---|",
    ]
    for row in rows:
        lines.append(f"| `{row['probe']}` | **{row['verdict']}** | {row['validates']} |")
    for row in rows:
        lines.extend(
            [
                "",
                f"## {row['probe']} - {row['title']}",
                "",
                f"**Verdict:** `{row['verdict']}`",
                "",
                f"- **Measures:** {row['measures']}",
                f"- **Validates:** {row['validates']}",
                f"- **Falsified when:** {row['falsified_when']}",
                f"- **Changes if it fails:** {row['changes_if_it_fails']}",
                f"- **Credential:** `{row['credential']}`; "
                f"budget {row['quota_budget_units']} u (published, uncalibrated)",
            ]
        )
        if row["pre_registered_rules"]:
            lines.append("- **Pre-registered decision rules:**")
            lines.extend(f"  - {rule}" for rule in row["pre_registered_rules"])
        lines.extend(["", "```json", json.dumps(row["findings"], indent=2, sort_keys=True), "```"])
        if row["notes"]:
            lines.append("")
            lines.extend(f"> {note}" for note in row["notes"])
    return "\n".join(lines) + "\n"
