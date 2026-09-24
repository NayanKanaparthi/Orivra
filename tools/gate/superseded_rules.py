"""The earlier definitions of two coverage rules, kept runnable. Records, not gates.

**Two coverage rules were revised while the round-two repair was in flight.** The evaluation
methodology as a whole was therefore *not* frozen: `content_gate.py` and `queryfree.py` were,
and their hashes are reproduced in every result file, but `coverage.RULES` was edited during the
work and two of its rules changed shape more than once.

That is a methodology revision and it is recorded here rather than described. Each earlier
definition is preserved verbatim in behaviour so a reviewer can run it against the frozen corpus
and see for themselves what each version says - including the versions that reported defects the
shipped version does not report.

**The revisions were not threshold moves.** In both cases the earlier statistic mis-specified
the unit of independence, and the corpus's own structure made that visible: hours are drawn per
`(conversation, position)`, and a long conversation is likelier to contain any given sentence
than a short one. Whether that account is right is a question for the reviewer, which is why the
earlier definitions are here and executable rather than summarised.

Nothing in this file is imported by the generator, by `coverage.audit`, or by the content gate.
"""

from __future__ import annotations

import argparse
import email.utils
import json
import math
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from mailweave_harness.seed import corpus
from mailweave_harness.seed.coverage import _strip_reference
from mailweave_harness.seed.manifest import Manifest
from mailweave_harness.seed.world import BY_ENTITY

# --------------------------------------------------------------------- hour_independent_of_role


def hour_v1_message_level(built: Manifest) -> list[str]:
    """**v1, superseded.** Two-proportion z per role against every other message in the corpus.

    Superseded because the observations are not independent: the hour is a hash of
    `(conversation, position)`, so five revisions of one F16 schedule landing in the afternoon
    is one coincidence and not five. It also compares each role against a pool that is 87%
    filler, and filler carried one guaranteed nine-o'clock message per thread until the opener's
    hour was drawn too - so every planted role read as "late" relative to a baseline that was
    itself depressed.
    """
    late: Counter[str] = Counter()
    total: Counter[str] = Counter()
    for message in built.messages:
        hour = email.utils.parsedate_to_datetime(message.date_rfc2822).hour
        total[message.role] += 1
        if hour >= 13:
            late[message.role] += 1
    tested = [one for one in total if total[one] >= 30]
    if len(tested) < 2:
        return []
    everything, every_late = sum(total.values()), sum(late.values())
    out: list[str] = []
    for role in sorted(tested):
        mine, rest = total[role], everything - total[role]
        if rest < 30:
            continue
        p_mine = late[role] / mine
        p_rest = (every_late - late[role]) / rest
        pooled = every_late / everything
        spread = (pooled * (1 - pooled) * (1 / mine + 1 / rest)) ** 0.5
        if spread == 0:
            continue
        z = abs(p_mine - p_rest) / spread
        corrected = math.erfc(z / (2 ** 0.5)) * len(tested)
        if corrected < 0.05:
            out.append(
                f"{role!r} after 13:00 {p_mine:.0%} against {p_rest:.0%} for everything else "
                f"({late[role]} of {mine}); z={z:.2f}, corrected p={corrected:.4f}"
            )
    return out


def _paired_deltas(built: Manifest) -> dict[str, list[float]]:
    threads: dict[str, list[tuple[str, bool]]] = defaultdict(list)
    for message in built.messages:
        stamp = email.utils.parsedate_to_datetime(message.date_rfc2822)
        threads[message.thread_key].append((message.role, stamp.hour >= 13))
    out: dict[str, list[float]] = defaultdict(list)
    for group in threads.values():
        size = len(group)
        if size < 2:
            continue
        late_total = sum(1 for _, late in group if late)
        counts: Counter[str] = Counter(role for role, _ in group)
        late_of: Counter[str] = Counter(role for role, late in group if late)
        for role, mine in counts.items():
            rest = size - mine
            if not rest:
                continue
            out[role].append(late_of[role] / mine - (late_total - late_of[role]) / rest)
    return out


def hour_v2_mean_of_thread_deltas(built: Manifest) -> list[str]:
    """**v2, superseded.** Mean of per-conversation differences, normal tail on an estimated SD.

    Fixed v1's unit problem by pairing inside the conversation. Superseded because most
    conversations carry a role once, so the difference is near-binary and a standard deviation
    estimated from eleven of them is not a standard deviation. It also gives a conversation with
    one message of a role the same weight as one with five.
    """
    paired = _paired_deltas(built)
    tested = sorted(one for one in paired if len(paired[one]) >= 10)
    if len(tested) < 2:
        return []
    out: list[str] = []
    for role in tested:
        deltas = paired[role]
        count = len(deltas)
        mean = sum(deltas) / count
        variance = sum((one - mean) ** 2 for one in deltas) / (count - 1)
        if variance <= 0:
            continue
        z = abs(mean) / (variance / count) ** 0.5
        corrected = math.erfc(z / (2 ** 0.5)) * len(tested)
        if corrected < 0.05:
            out.append(
                f"{role!r} {mean:+.0%} against the rest of its own conversation over {count} "
                f"conversations; z={z:.2f}, corrected p={corrected:.4f}"
            )
    return out


def hour_v3_permutation(built: Manifest, rounds: int = 999) -> list[str]:
    """**v3, superseded.** The same statistic as v2 against a within-conversation permutation null.

    Correct about the null and slow: it re-labelled every message 999 times per audit, which
    took roughly ten times as long as every other rule in the file put together. Superseded by
    the closed-form version of the same null.
    """
    threads: dict[str, list[tuple[str, bool]]] = defaultdict(list)
    for message in built.messages:
        stamp = email.utils.parsedate_to_datetime(message.date_rfc2822)
        threads[message.thread_key].append((message.role, stamp.hour >= 13))
    groups = [one for one in threads.values() if len({role for role, _ in one}) > 1]
    if not groups:
        return []

    def deltas(labelled: list[list[tuple[str, bool]]]) -> dict[str, list[float]]:
        out: dict[str, list[float]] = defaultdict(list)
        for group in labelled:
            counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
            whole = [0, 0]
            for role, late in group:
                counts[role][0] += late
                counts[role][1] += 1
                whole[0] += late
                whole[1] += 1
            for role, (hits, seen) in counts.items():
                rest = whole[1] - seen
                if not rest:
                    continue
                out[role].append(hits / seen - (whole[0] - hits) / rest)
        return out

    observed = deltas(groups)
    tested = sorted(one for one in observed if len(observed[one]) >= 10)
    if len(tested) < 2:
        return []
    means = {one: sum(observed[one]) / len(observed[one]) for one in tested}
    beaten = dict.fromkeys(tested, 0)
    shuffler = random.Random(20260916)
    for _ in range(rounds):
        shuffled = []
        for group in groups:
            roles = [role for role, _ in group]
            shuffler.shuffle(roles)
            shuffled.append([(role, late) for role, (_, late) in zip(roles, group, strict=True)])
        null = deltas(shuffled)
        for role in tested:
            drawn = null.get(role, [])
            if drawn and abs(sum(drawn) / len(drawn)) >= abs(means[role]):
                beaten[role] += 1
    out: list[str] = []
    for role in tested:
        corrected = ((beaten[role] + 1) / (rounds + 1)) * len(tested)
        if corrected < 0.05:
            out.append(
                f"{role!r} {means[role]:+.0%}; {beaten[role]} of {rounds} shuffles this "
                f"extreme, corrected p={corrected:.4f}"
            )
    return out


# ------------------------------------------------- scaffolding_not_family_exclusive


def _sentences(
    built: Manifest, by_thread: bool
) -> tuple[dict[str, set[tuple[str, str]]], dict[str, str]]:
    from mailweave_harness.seed.situations import TOPICS

    names: set[str] = set()
    for entity in BY_ENTITY.values():
        names |= {entity.formal.lower(), entity.plain.lower()}
    rationales = {one.reason for one in TOPICS}
    family_of = {one.thread_key: (one.family or "") for one in built.answer_key.threads}
    holders: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for message in built.messages:
        for sentence in re.split(r"(?<=[.?!])\s+", _strip_reference(message.body)):
            sentence = sentence.strip()
            if len(sentence.split()) < 2 or any(one.isdigit() for one in sentence):
                continue
            low = sentence.lower()
            if any(one and one in low for one in names):
                continue
            if any(sentence in one or one in sentence for one in rationales):
                continue
            key = message.thread_key if by_thread else message.rfc822_message_id
            holders[sentence].add((family_of.get(message.thread_key, ""), key))
    return holders, family_of


def _report_exclusive(
    holders: dict[str, set[tuple[str, str]]], share: Counter[str], total: int, floor: int
) -> list[str]:
    tested = {one: group for one, group in holders.items() if len(group) >= floor}
    if not tested:
        return []
    out: list[str] = []
    for sentence, group in tested.items():
        families = {one for one, _ in group}
        if len(families) != 1:
            continue
        family = next(iter(families))
        if not family:
            continue
        count = len(group)
        expected = (share[family] / total) ** count * len(tested)
        if expected < 0.05:
            out.append(
                f"{sentence[:60]!r} in {count}, all {family} "
                f"(share {share[family] / total:.0%}, p={expected:.5f})"
            )
    return sorted(out)[:8]


def scaffolding_v1_messages_message_share(built: Manifest, floor: int = 3) -> list[str]:
    """**v1, superseded.** Count messages; null is the family's share of messages.

    Superseded because a sentence emitted twice inside one long conversation counted as two
    independent events. The floor was 2 before it was 3; at 2 it reported a different set of
    sentences at every seed.
    """
    holders, family_of = _sentences(built, by_thread=False)
    share = Counter(family_of.get(one.thread_key, "") for one in built.messages)
    return _report_exclusive(holders, share, len(built.messages), floor)


def scaffolding_v2_threads_thread_share(built: Manifest, floor: int = 3) -> list[str]:
    """**v2, superseded.** Count conversations; null is the family's share of conversations.

    Fixed v1's double-counting and introduced a worse error: a ninety-message conversation is
    ten times likelier to contain any given sentence than a nine-message one, so a
    conversation-share null reported the long-thread family's ordinary closing lines as that
    family's markers.
    """
    holders, _ = _sentences(built, by_thread=True)
    share = Counter(one.family or "" for one in built.answer_key.threads)
    return _report_exclusive(holders, share, len(built.answer_key.threads), floor)


VERSIONS: dict[str, Any] = {
    "hour_independent_of_role": {
        "v1_message_level_two_proportion": hour_v1_message_level,
        "v2_mean_of_thread_deltas": hour_v2_mean_of_thread_deltas,
        "v3_within_thread_permutation": hour_v3_permutation,
    },
    "scaffolding_not_family_exclusive": {
        "v1_messages_against_message_share": scaffolding_v1_messages_message_share,
        "v2_threads_against_thread_share": scaffolding_v2_threads_thread_share,
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=4311)
    parser.add_argument("--profile", default="sample")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    built = corpus.generate(master_seed=args.seed, size_profile=args.profile)
    from mailweave_harness.seed import coverage as live

    shipped = {
        "hour_independent_of_role": [
            one.detail for one in live._hour_is_independent_of_role(live.View(built))
        ],
        "scaffolding_not_family_exclusive": [
            one.detail for one in live._scaffolding_is_not_family_exclusive(live.View(built))
        ],
    }
    out = {
        "what_this_is": (
            "the superseded definitions of two coverage rules, run against the frozen corpus "
            "beside the shipped ones. A record of a methodology revision, not a gate"
        ),
        "corpus": {
            "master_seed": args.seed,
            "size_profile": args.profile,
            "generator_version": built.generator_version,
            "messages": len(built.messages),
        },
        "rules": {
            rule: {
                "shipped": shipped[rule],
                **{name: fn(built) for name, fn in versions.items()},
            }
            for rule, versions in VERSIONS.items()
        },
    }
    text = json.dumps(out, indent=1, sort_keys=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
