"""Does the blanket `Cf` strip damage legitimate content in real mail? (round 10, standing)

Round 10 replaced two hand-written character lists with `unicodedata.category(c) == "Cf"`,
which is right for the defect it fixed - the old list missed 154 of Unicode's 170 format
characters, including a whole invisible-ASCII tag block. It also strips characters that are
**genuine content** in some scripts: U+200C/U+200D drive Arabic and Indic shaping, U+061C is
an ordinary Arabic mark, U+0600..U+0605 are Arabic number signs, U+070F is the Syriac
abbreviation mark, and U+110BD/U+110CD are Kaithi number signs. Both R-SEC and the round-10
implementer flagged this independently and both said the same thing: it cannot be settled
without real mail.

**What is recorded, and what is not.** Counts, code points and script names. No body text, no
subject, no address, no snippet - not even the characters *around* a removal. That is not
politeness, it is OD-4: a probe run has no per-incident approval to persist mail text, so the
record must be shaped so that it cannot.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any, Final

from mailweave_harness.preflight.spec import ProbeResult, ProbeSpec, Verdict

SPEC = ProbeSpec(
    id="PF-cf-strip-damage",
    title="Whether stripping every Cf character damages legitimate mail",
    measures=(
        "over sampled real message bodies: which Unicode format characters the content "
        "pipeline removes, and which scripts the surrounding message uses - as code points "
        "and script names, never as text"
    ),
    validates=(
        "AD D.4a's invisible-character removal and its empty keep-list, and amendment A7's "
        "claim that the pipeline annotates rather than deletes - which today holds for spans "
        "and not for format characters"
    ),
    falsified_when=(
        "any message whose text uses Arabic, Syriac, Devanagari, Bengali, Gurmukhi, Gujarati, "
        "Kannada, Malayalam, Kaithi, Tamil, Telugu, Oriya, Sinhala, Thaana or Egyptian "
        "Hieroglyph characters has a shaping-or-semantic format character removed from it "
        "(U+200C, U+200D, U+061C, U+0600..U+0605, U+06DD, U+070F, U+08E2, U+110BD, U+110CD, "
        "U+13430..U+1343F)"
    ),
    changes_if_it_fails=(
        "A7's rule extends from spans to characters: the pipeline stops *removing* format "
        "characters and starts annotating them, so the default view hides them and any wider "
        "view returns the text exactly. `_KEPT_FORMAT_CHARACTERS` stops being empty, or - "
        "better, and this is the direction A7 already chose once - stops existing, because "
        "the decision moves from the pipeline to the disclosure layer. The invisible-character "
        "defence then rests on fencing and provenance, which is where INJ-04 already puts it"
    ),
    credential="read",
    quota_budget_units=2000,
    pre_registered_rules=(
        "one removal in one message is a failure. There is no rate here: the question is "
        "whether the operation can destroy legitimate content, and one instance answers it",
    ),
)

#: Format characters whose removal can change what a message *says* rather than only how it
#: is encoded. Derived from what each is for, not from a survey - the two joiners drive
#: shaping, the marks and number signs are ordinary characters in their scripts.
LOAD_BEARING_POINTS: Final[tuple[int, ...]] = (
    0x200C,  # ZERO WIDTH NON-JOINER - Persian/Indic word forms depend on it
    0x200D,  # ZERO WIDTH JOINER - Indic conjuncts, and emoji sequences
    0x061C,  # ARABIC LETTER MARK
    0x0600,  # ARABIC NUMBER SIGN
    0x0601,  # ARABIC SIGN SANAH
    0x0602,  # ARABIC FOOTNOTE MARKER
    0x0603,  # ARABIC SIGN SAFHA
    0x0604,  # ARABIC SIGN SAMVAT
    0x0605,  # ARABIC NUMBER MARK ABOVE
    0x06DD,  # ARABIC END OF AYAH
    0x070F,  # SYRIAC ABBREVIATION MARK
    0x08E2,  # ARABIC DISPUTED END OF AYAH
    0x110BD,  # KAITHI NUMBER SIGN
    0x110CD,  # KAITHI NUMBER SIGN ABOVE
    *range(0x13430, 0x13440),  # EGYPTIAN HIEROGLYPH format controls
)
"""Written as code points and never as characters.

A literal `\u200c` in a source file is invisible in a diff, which is the property that makes
these characters worth measuring in the first place. Spelling them numerically means a
reviewer can see what is on the list.
"""

LOAD_BEARING: Final[frozenset[str]] = frozenset(chr(point) for point in LOAD_BEARING_POINTS)

#: Scripts in which those characters are ordinary content. Matched against the **first word**
#: of `unicodedata.name`, which is how the standard names characters by script.
AT_RISK_SCRIPTS: Final[frozenset[str]] = frozenset(
    {
        "ARABIC",
        "SYRIAC",
        "DEVANAGARI",
        "BENGALI",
        "GURMUKHI",
        "GUJARATI",
        "KANNADA",
        "MALAYALAM",
        "KAITHI",
        "TAMIL",
        "TELUGU",
        "ORIYA",
        "SINHALA",
        "THAANA",
        "EGYPTIAN",
        "NKO",
        "THAI",
        "MYANMAR",
        "KHMER",
    }
)


def scripts_used(text: str) -> frozenset[str]:
    """The script names present in `text`, from the runtime's own character names.

    A heuristic, and named as one: Unicode names characters by script for exactly these
    blocks, so the first word of `ARABIC LETTER ALEF` is the script. Latin, digits and
    punctuation fall outside the at-risk set and are ignored rather than misclassified.
    """
    found: set[str] = set()
    for character in text:
        if character.isascii():
            continue
        try:
            name = unicodedata.name(character)
        except ValueError:
            continue
        head = name.split(" ", 1)[0]
        if head in AT_RISK_SCRIPTS:
            found.add(head)
    return frozenset(found)


@dataclass(frozen=True)
class MessageObservation:
    """One message, reduced to counts and code points before it leaves memory."""

    message_digest: str
    scripts: frozenset[str]
    removed_code_points: tuple[str, ...]
    removed_total: int


@dataclass
class InvisibleObservation:
    messages: list[MessageObservation] = field(default_factory=list)
    bodies_examined: int = 0


def observe_message(message_digest: str, text: str, stripped_text: str) -> MessageObservation:
    """Compare a body with its stripped form, keeping only counts and code points.

    The two texts are compared here, in memory, and neither is retained. What survives is a
    tuple of `U+XXXX` strings and an integer.
    """
    removed: list[str] = []
    stripped_counts: dict[str, int] = {}
    for character in stripped_text:
        stripped_counts[character] = stripped_counts.get(character, 0) + 1
    original_counts: dict[str, int] = {}
    for character in text:
        original_counts[character] = original_counts.get(character, 0) + 1
    total = 0
    for character, count in original_counts.items():
        lost = count - stripped_counts.get(character, 0)
        if lost > 0 and unicodedata.category(character) == "Cf":
            removed.append(f"U+{ord(character):04X}")
            total += lost
    return MessageObservation(
        message_digest=message_digest,
        scripts=scripts_used(text),
        removed_code_points=tuple(sorted(set(removed))),
        removed_total=total,
    )


def analyse(observation: InvisibleObservation) -> ProbeResult:
    load_bearing_points = {f"U+{ord(character):04X}" for character in LOAD_BEARING}
    damaged: list[dict[str, Any]] = []
    removals_by_point: dict[str, int] = {}
    scripts_seen: set[str] = set()
    for message in observation.messages:
        scripts_seen |= set(message.scripts)
        for point in message.removed_code_points:
            removals_by_point[point] = removals_by_point.get(point, 0) + 1
        hits = sorted(set(message.removed_code_points) & load_bearing_points)
        if hits and message.scripts:
            damaged.append(
                {
                    "message": message.message_digest,
                    "scripts": sorted(message.scripts),
                    "removed": hits,
                }
            )
    findings: dict[str, Any] = {
        "bodies_examined": observation.bodies_examined,
        "messages_with_any_removal": sum(
            1 for message in observation.messages if message.removed_total
        ),
        "removals_by_code_point": dict(sorted(removals_by_point.items())),
        "at_risk_scripts_seen": sorted(scripts_seen),
        "damaged_messages": damaged,
    }
    if not observation.messages:
        return ProbeResult(
            spec=SPEC,
            verdict=Verdict.INCONCLUSIVE,
            findings=findings,
            notes=("no bodies were examined",),
        )
    if damaged:
        return ProbeResult(spec=SPEC, verdict=Verdict.FAIL, findings=findings)
    if not scripts_seen:
        return ProbeResult(
            spec=SPEC,
            verdict=Verdict.INCONCLUSIVE,
            findings=findings,
            notes=(
                "no message in the sample used any of the at-risk scripts, so the question "
                "this probe asks was not exercised. A mailbox with no Arabic or Indic mail "
                "cannot answer whether stripping damages Arabic or Indic mail - and reporting "
                "that as a pass would be the sample answering a question it never saw.",
            ),
        )
    return ProbeResult(spec=SPEC, verdict=Verdict.PASS, findings=findings)
