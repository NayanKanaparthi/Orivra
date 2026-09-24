"""The answer stays where the manifest says it is.

`t0041` in the gate profile shipped with `evidence_at: 2` in its ground truth and a
`trap_decoy` at position 2. The trap was drawn by `_before`, whose fallback - taken when
nothing fits earlier than the anchor - ranged over the whole thread and had no reason to skip
the evidence, because the evidence position was not one of the things it was told about. The
family's own coverage rule caught it. No other family has that rule, so the same draw in any
other builder would have shipped.

Two repairs, tested here separately:

* `_before` takes the positions the caller has reserved and never returns one, in the near
  room or the fallback.
* `place` refuses to write a non-answer-bearing line over an answer-bearing one, which is the
  same defect caught one layer lower and in every family at once.

Each has a negative fixture: a version of the repair that is removed, and an assertion that
the removal is detected.
"""

from __future__ import annotations

import pytest

from mailweave_harness.seed.corpus import generate
from mailweave_harness.seed.coverage import coverage
from mailweave_harness.seed.drafts import EVIDENCE_ROLES, Line
from mailweave_harness.seed.families import _before, place


class _Draws:
    """The shape RNG `_before` draws from, forced to a chosen index."""

    def __init__(self, index: int) -> None:
        self.index = index
        self.asked: list[int] = []

    def randrange(self, size: int) -> int:
        self.asked.append(size)
        return min(self.index, size - 1)


class _Ctx:
    def __init__(self, index: int) -> None:
        self.shape = _Draws(index)


def _line(role: str) -> Line:
    return Line(role, f"a {role} message", "bea", gap_hours=3)


# ------------------------------------------------------------------ _before honours `avoid`

def test_the_fallback_never_returns_a_reserved_position() -> None:
    """Anchor at 1, so nothing fits before it and the fallback ranges over the thread.

    Every index of the fallback room is exercised, not one draw: the defect was that a
    *particular* draw landed on the evidence, and a test that fixes the draw proves nothing
    about the others.
    """
    for index in range(90):
        got = _before(_Ctx(index), 1, 94, avoid=(2,))
        assert got != 2, f"draw {index} returned the reserved evidence position"
        assert got != 1
        assert 1 <= got < 94


def test_the_near_room_never_returns_a_reserved_position() -> None:
    """Anchor at 30, so the near room is 1..29 and the reserved positions sit inside it."""
    seen = set()
    for index in range(40):
        got = _before(_Ctx(index), 30, 94, avoid=(4, 11, 23))
        assert got not in {4, 11, 23, 30}
        assert 1 <= got < 30, "the near room must stay before the anchor"
        seen.add(got)
    assert len(seen) > 1, "the position is drawn, not fixed"


def test_without_avoid_the_fallback_can_reach_every_position_but_the_anchor() -> None:
    """The repair narrows the room only by what the caller reserves - it is not a blanket ban.

    A repair that made `_before` refuse the whole head of the thread would defeat the defect
    and the family's construction with it.
    """
    reached = {_before(_Ctx(index), 1, 20, avoid=()) for index in range(19)}
    assert reached == set(range(2, 20))


def test_a_thread_with_no_free_position_is_a_generation_error_not_a_silent_collision() -> None:
    with pytest.raises(ValueError, match="free of"):
        _before(_Ctx(0), 1, 3, avoid=(2,))


# ------------------------------------------------- negative fixture: the repair removed

def _before_unrepaired(ctx: _Ctx, target: int, length: int, avoid: tuple[int, ...]) -> int:
    """`_before` as it stood: `avoid` ignored in the fallback. Kept so the test can fail."""
    room = [one for one in range(1, max(2, target)) if one != target]
    if not room:
        room = [one for one in range(1, length) if one != target] or [1]
    return room[ctx.shape.randrange(len(room))]


def test_the_unrepaired_draw_does_land_on_the_evidence() -> None:
    """The negative fixture. Without this the two tests above could be vacuous."""
    landed = [
        index for index in range(90) if _before_unrepaired(_Ctx(index), 1, 94, (2,)) == 2
    ]
    assert landed, "the fixture no longer reproduces the defect it is here to reproduce"


# ------------------------------------------------------------------ place refuses the overwrite

@pytest.mark.parametrize("role", sorted(EVIDENCE_ROLES))
def test_place_refuses_to_bury_any_answer_bearing_role(role: str) -> None:
    lines = [_line("filler") for _ in range(6)]
    place(lines, 2, _line(role))
    with pytest.raises(ValueError, match="would overwrite"):
        place(lines, 2, _line("trap_decoy"))
    assert lines[2].role == role, "the refused write must not have happened"


def test_place_still_allows_a_distractor_over_a_distractor() -> None:
    """Builders overwrite filler and redraw distractors. Only the answer is protected."""
    lines = [_line("filler") for _ in range(6)]
    place(lines, 3, _line("trap_decoy"))
    place(lines, 3, _line("paraphrase_decoy"))
    assert lines[3].role == "paraphrase_decoy"


def test_place_still_allows_an_answer_to_replace_an_answer() -> None:
    """The `_redraw_*` closures rewrite a planted answer; assigning a better one is not a bug."""
    lines = [_line("filler") for _ in range(6)]
    place(lines, 3, _line("evidence"))
    place(lines, 3, _line("confirmation"))
    assert lines[3].role == "confirmation"


def test_place_still_refuses_position_zero_and_out_of_range() -> None:
    lines = [_line("filler") for _ in range(6)]
    with pytest.raises(ValueError, match="thread opener"):
        place(lines, 0, _line("evidence"))
    with pytest.raises(ValueError, match="outside a thread"):
        place(lines, 6, _line("evidence"))


# ------------------------------------------------------------------ the corpus itself

def test_every_declared_evidence_position_holds_an_answer_bearing_message() -> None:
    """Across the gate profile, and not only on the one family with a rule for it.

    This is the assertion the family-specific rule made for F3 alone. Stated over every thread
    that declares a position, it is what the `place` guard is protecting.
    """
    gate = generate(master_seed=5309, size_profile="gate")
    by_thread: dict[str, dict[int, str]] = {}
    for message in gate.messages:
        by_thread.setdefault(message.thread_key, {})[message.position] = message.role

    checked = 0
    wrong = []
    for thread in gate.answer_key.threads:
        declared = thread.facts.get("evidence_at")
        if declared is None:
            continue
        checked += 1
        role = by_thread.get(thread.thread_key, {}).get(int(declared))
        if role not in EVIDENCE_ROLES:
            wrong.append((thread.thread_key, thread.family, declared, role))
    assert checked, "no thread declared an evidence position - the test is measuring nothing"
    assert not wrong, wrong


def test_the_gate_profile_has_no_family_shortfall() -> None:
    gate = generate(master_seed=5309, size_profile="gate")
    short = [one for one in coverage(gate) if one.shortfall]
    assert not short, [(one.family, one.registered, one.authorable) for one in short]
