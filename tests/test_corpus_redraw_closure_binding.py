"""B023 in the corpus generator: whether a redraw callback binds the thread it is about.

**Why this file exists.** `ruff` reports 38 `B023` ("function definition does not bind loop
variable") in `mailweave_harness.seed.families`, and that module is on the path of *both*
measurement entry points - the diagnostic runner and the evaluation runner both call
`corpus.generate`. A late-binding closure there would not be a lint nit: a redraw that wrote
into the previous thread's `lines` would put a family's evidence in another family's
conversation, and every retrieval number measured on that corpus would be measured on a corpus
that is not the one the manifest describes.

**The triage, in one sentence: all 38 are one shape, and the shape is safe** - but that is
asserted here rather than argued, because "the callback happens to be called immediately" is a
property of the call site, and a call site can move.

The four closures (`_redraw_f4`, `_redraw_f11`, `_redraw_f12`, `_redraw_f17`) are each defined
inside a per-thread loop and each used exactly once, as the `redraw=` argument of
`redraw_until_ranked` **or of `redraw_until_top`** - F11 moved to the second when R-M2-067
changed its registered relationship from "the trap beats its evidence" to "the trap is the best
hit in the conversation" - each of which calls it inside a bounded loop and retains nothing. So the free
variables are read while the loop still holds this thread's values. Two tests below hold that:
one on the mechanism (what the callback is bound to at the moment it is handed over, and that
it is never called afterwards), one on the corpus the generator actually produces.

Nothing here is a fix. `families.py` is unchanged; the B023 diagnostics remain, and the
recommendation about them is in the readiness report, not in this file.
"""

from __future__ import annotations

from typing import Any

import pytest

from mailweave_harness.seed import corpus
from mailweave_harness.seed import families as fam
from mailweave_harness.seed import lexical as lex
from mailweave_harness.seed.drafts import Line

#: The generator inputs the diagnostic runner uses (`benchmarks/run-diagnostic-4311.py`).
SEED = 4311
PROFILE = "sample"

#: `(family, facts key, the role the line at that position must carry)`. Read off each
#: builder's own `facts` dictionary, which is what the manifest publishes as ground truth.
DECLARED = (
    ("F4", "evidence_at", "evidence"),
    ("F4", "decoy_at", "trap_decoy"),
    ("F11", "evidence_at", "evidence"),
    ("F12", "evidence_at", "evidence"),
    ("F17", "reversal_at", "reversal"),
)


def _cells(callback: Any) -> dict[str, Any]:
    """What this closure is actually bound to, read off the function object.

    `co_freevars` names the variables the compiler closed over and `__closure__` holds their
    cells in the same order, so this is the binding itself rather than a reconstruction of it.
    """
    free = callback.__code__.co_freevars
    cells = callback.__closure__ or ()
    return {name: cell.cell_contents for name, cell in zip(free, cells, strict=True)}


def test_every_redraw_callback_is_bound_to_the_thread_it_is_handed_with(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The mechanism, on every call the whole corpus makes.

    Three things are checked at the moment `redraw_until_ranked` receives a callback, which is
    the moment a late binding would be wrong at:

      * the `lines` the callback writes into **is** the `lines` the call is about - identity,
        not equality, because two threads can hold equal lists;
      * every integer the callback uses as an index is inside that list;
      * the callback is not invoked after the call returns, so no later iteration can reach it.
    """
    real_ranked = fam.redraw_until_ranked
    real_top = fam.redraw_until_top
    seen: list[str] = []
    escaped: list[str] = []

    def _spy(real: Any, ctx: Any, lines: list[Line], query: str, **kwargs: Any) -> None:
        callback = kwargs.pop("redraw")
        bound = _cells(callback)
        name = callback.__name__
        seen.append(name)
        assert bound["lines"] is lines, (
            f"{name} writes into a different list from the one "
            f"`redraw_until_ranked` was given: the late binding B023 warns about"
        )
        for variable, value in bound.items():
            positions = value if isinstance(value, (list, tuple)) else [value]
            for position in positions:
                if isinstance(position, int) and not isinstance(position, bool):
                    assert 0 <= position < len(lines), (
                        f"{name} closes over {variable}={position}, outside its own thread of "
                        f"{len(lines)} lines"
                    )
        live = True

        def guarded() -> None:
            if not live:  # pragma: no cover - the assertion below is what reports it
                escaped.append(name)
            callback()

        real(ctx, lines, query, redraw=guarded, **kwargs)
        live = False

    monkeypatch.setattr(
        fam, "redraw_until_ranked",
        lambda ctx, lines, query, **kw: _spy(real_ranked, ctx, lines, query, **kw),
    )
    monkeypatch.setattr(
        fam, "redraw_until_top",
        lambda ctx, lines, query, **kw: _spy(real_top, ctx, lines, query, **kw),
    )
    corpus.generate(master_seed=SEED, size_profile=PROFILE)

    assert not escaped, f"a redraw callback ran after its own call returned: {escaped}"
    # The generator must actually have gone through the guarded path, or the test above is a
    # statement about nothing.
    assert set(seen) == {"_redraw_f4", "_redraw_f11", "_redraw_f12", "_redraw_f17"}, sorted(
        set(seen)
    )


def test_the_rank_relationship_each_redraw_exists_for_holds_in_the_finished_corpus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The consequence, checked on the corpus a measurement is actually made against.

    `redraw_until_ranked` exists to leave one guarantee behind: for this thread and this
    family's query, the line at `above` out-scores the line at `below`. That guarantee is what
    F4, F11, F12 and F17 *are* - F11's trap must beat its own evidence, F17's reinforcements
    must beat the reversal - and a callback that ran against another thread would leave it
    unenforced here and over-enforced there.

    So the call's own arguments are captured and the relationship is re-evaluated **after**
    `generate` has returned, against the same list objects, with the generator's own predicate.
    The mechanism test above catches a mis-binding where it happens; this catches it where it
    would be measured.
    """
    real_ranked = fam.redraw_until_ranked
    real_top = fam.redraw_until_top
    captured: list[tuple[str, list[Line], str, int, int]] = []
    topped: list[tuple[str, list[Line], str, int]] = []

    def spy(ctx: Any, lines: list[Line], query: str, **kwargs: Any) -> None:
        captured.append((kwargs["redraw"].__name__, lines, query, kwargs["above"], kwargs["below"]))
        real_ranked(ctx, lines, query, **kwargs)

    def spy_top(ctx: Any, lines: list[Line], query: str, **kwargs: Any) -> None:
        topped.append((kwargs["redraw"].__name__, lines, query, kwargs["winner"]))
        real_top(ctx, lines, query, **kwargs)

    monkeypatch.setattr(fam, "redraw_until_ranked", spy)
    monkeypatch.setattr(fam, "redraw_until_top", spy_top)
    drafts, _ = corpus._drafts(corpus.PROFILES[PROFILE], SEED)

    assert {name for name, *_ in captured} == {
        "_redraw_f4",
        "_redraw_f12",
        "_redraw_f17",
    }, sorted({name for name, *_ in captured})
    assert {name for name, *_ in topped} == {"_redraw_f11"}, sorted(
        {name for name, *_ in topped}
    )
    # R-M2-067. F11's guarantee is not a pair relationship, so it is re-evaluated with the
    # predicate that actually defines it: the trap is rank 1 in its own finished conversation.
    not_top = [
        (name, lex.rank_of([one.text for one in lines], query, winner))
        for name, lines, query, winner in topped
        if lex.rank_of([one.text for one in lines], query, winner) != 1
    ]
    assert not not_top, (
        f"{len(not_top)} of {len(topped)} threads reach the corpus without their trap at the "
        f"top of the conversation: {not_top[:4]}"
    )
    unenforced = [
        (name, query[:40])
        for name, lines, query, above, below in captured
        if not fam._ranks_ok(lines, query, above=above, below=below)
    ]
    assert not unenforced, (
        f"{len(unenforced)} of {len(captured)} threads reach the corpus without the rank "
        f"relationship their family is defined by: {unenforced[:4]}"
    )

    # And the cheap structural half: a builder's published `facts` still name a line of the
    # role they claim, in that builder's own thread.
    by_family: dict[str, int] = {}
    for draft in drafts:
        for family, key, role in DECLARED:
            if draft.family != family or key not in draft.facts:
                continue
            at = int(draft.facts[key])
            assert 0 <= at < len(draft.lines), (draft.family, draft.situation_key, key, at)
            assert draft.lines[at].role == role, (
                f"{draft.family}/{draft.situation_key} declares {key}={at} but the line there "
                f"is {draft.lines[at].role!r}, not {role!r}"
            )
            by_family[family] = by_family.get(family, 0) + 1
    assert set(by_family) == {"F4", "F11", "F12", "F17"}, sorted(by_family)


def test_a_forced_redraw_lands_in_the_thread_it_was_handed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The decisive one, and the reason the two above are not enough on their own.

    At seed 4311 / profile `sample` the generator hands over eight redraw callbacks and the
    relationship already holds on the first draw for six of them: only F4 fires, twice. A test
    that waits for the corpus to exercise the redraw path is therefore mostly testing nothing,
    and it is seed-dependent in a way a regression must not be.

    So the path is forced instead. `_ranks_ok` is made to fail once per thread, which makes
    every handover run exactly one real redraw with the real callback over the real lines. Each
    redraw constructs new `Line` objects, so "did this thread's own lines get rewritten" is an
    identity question with a deterministic answer - no text comparison, nothing to flake on.

    A callback bound to another iteration would rewrite that thread instead, and this fails
    with the untouched threads named.
    """
    real_ranks = fam._ranks_ok
    real_redraw = fam.redraw_until_ranked
    failed_once: set[int] = set()
    watched: list[tuple[str, list[Line], int, int, Line, Line]] = []

    def ranks(lines: list[Line], query: str, *, above: int, below: int) -> bool:
        if id(lines) not in failed_once:
            failed_once.add(id(lines))
            return False
        return real_ranks(lines, query, above=above, below=below)

    def spy(ctx: Any, lines: list[Line], query: str, **kwargs: Any) -> None:
        above, below = kwargs["above"], kwargs["below"]
        watched.append((kwargs["redraw"].__name__, lines, above, below, lines[above], lines[below]))
        real_redraw(ctx, lines, query, **kwargs)

    monkeypatch.setattr(fam, "_ranks_ok", ranks)
    monkeypatch.setattr(fam, "redraw_until_ranked", spy)
    corpus._drafts(corpus.PROFILES[PROFILE], SEED)

    assert watched, "no redraw callback was handed over at all"
    untouched = [
        name
        for name, lines, above, below, was_above, was_below in watched
        if lines[above] is was_above and lines[below] is was_below
    ]
    assert not untouched, (
        f"{len(untouched)} of {len(watched)} forced redraws did not rewrite the thread they "
        f"were handed: {untouched}"
    )
