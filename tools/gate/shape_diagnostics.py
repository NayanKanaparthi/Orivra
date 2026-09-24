"""How much a conversation's content-free shape says about which family it is. Non-gating.

`content_gate.py`'s **C1 is frozen and stays as written**: every
`(length, participants, senders, distinct hours)` value must map to at least two families.
This file does not replace it, does not feed it, and nothing here can move the gate's verdict.

It exists because C1 measures two things at once and only one of them is the defect. R-M2-070
is a claim about *leakage*: a content-free record of a conversation identifies the family it
belongs to. C1 tests that by asking whether the exact tuple is ever unique to a family - and
`length` is an exact message count, so at forty-odd conversations of registered shapes almost
every thread has a tuple of its own whatever the generator does. A criterion that is satisfied
only when threads collide exactly is measuring thread granularity, not leakage. That is a
property of the criterion and it is recorded, not worked around.

So this file reports the quantity C1 is reaching for, on a coarsened shape a reader could
actually observe: how many bits the shape carries about the family, against the bits a shuffle
of the same labels carries. Mutual information is biased upwards when the table is sparse, so
the shuffle baseline is not decoration - it is the only thing that makes the number readable.

Nothing here is a threshold. There is no pass or fail in this file.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import random
from collections import Counter, defaultdict
from collections.abc import Callable
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from mailweave_harness.seed import corpus
from mailweave_harness.seed.manifest import Manifest

#: Bucket edges chosen from EP §4.4's own thread-length bands, not from this corpus's numbers.
LENGTH_BANDS: tuple[tuple[str, int], ...] = (
    ("short", 15), ("medium", 30), ("long", 60), ("very_long", 10 ** 9),
)

SHUFFLES = 999


def _band(length: int) -> str:
    for name, ceiling in LENGTH_BANDS:
        if length <= ceiling:
            return name
    return LENGTH_BANDS[-1][0]


def _rows(manifest: Manifest) -> list[tuple[dict[str, Any], str]]:
    by_thread: dict[str, list[Any]] = defaultdict(list)
    for message in manifest.messages:
        by_thread[message.thread_key].append(message)
    out: list[tuple[dict[str, Any], str]] = []
    for truth in manifest.answer_key.threads:
        if not truth.family:
            continue
        group = by_thread.get(truth.thread_key, [])
        if not group:
            continue
        hours = set()
        for one in group:
            with contextlib.suppress(TypeError, ValueError):  # pragma: no cover
                hours.add(parsedate_to_datetime(one.date_rfc2822).hour)
        out.append((
            {
                "length": truth.length,
                "length_band": _band(truth.length),
                "participants": len(truth.participants),
                "senders": len({one.sender for one in group}),
                "distinct_hours": len(hours),
                "hours_band": "few" if len(hours) <= 3 else ("some" if len(hours) <= 6 else "many"),
            },
            truth.family,
        ))
    return out


def _mutual_information(pairs: list[tuple[Any, str]]) -> float:
    """Bits the shape carries about the family."""
    total = len(pairs)
    if not total:
        return 0.0
    joint = Counter(pairs)
    left = Counter(one for one, _ in pairs)
    right = Counter(one for _, one in pairs)
    out = 0.0
    for (shape, family), count in joint.items():
        p = count / total
        out += p * math.log2(p / ((left[shape] / total) * (right[family] / total)))
    return out


def _entropy(values: list[str]) -> float:
    total = len(values)
    counts = Counter(values)
    return -sum((one / total) * math.log2(one / total) for one in counts.values())


def _measure(pairs: list[tuple[Any, str]], seed: int) -> dict[str, Any]:
    observed = _mutual_information(pairs)
    shapes = [one for one, _ in pairs]
    families = [one for _, one in pairs]
    rng = random.Random(seed)
    null: list[float] = []
    for _ in range(SHUFFLES):
        shuffled = list(families)
        rng.shuffle(shuffled)
        null.append(_mutual_information(list(zip(shapes, shuffled, strict=True))))
    null.sort()
    beaten = sum(1 for one in null if one >= observed)
    singles = {
        one for one, group in
        ((shape, {fam for shp, fam in pairs if shp == shape}) for shape in set(shapes))
        if len(group) == 1
    }
    return {
        "distinct_values": len(set(shapes)),
        "values_mapping_to_one_family": len(singles),
        "mutual_information_bits": round(observed, 4),
        "family_entropy_bits": round(_entropy(families), 4),
        "fraction_of_family_entropy": round(observed / _entropy(families), 4)
        if _entropy(families) else 0.0,
        "shuffled_mean_bits": round(sum(null) / len(null), 4),
        "shuffled_95th_bits": round(null[int(0.95 * len(null))], 4),
        "p_value": round((beaten + 1) / (SHUFFLES + 1), 4),
        "reading": (
            "mutual information is biased upwards when the table is sparse, so the number to "
            "read is the observed value against the shuffled 95th percentile, and the p-value "
            "beside it. A value at or below the shuffle baseline carries no more about the "
            "family than a random relabelling would"
        ),
    }


def report(manifest: Manifest, seed: int = 20260916) -> dict[str, Any]:
    rows = _rows(manifest)
    views: dict[str, Callable[[dict[str, Any]], tuple[Any, ...]]] = {
        "exact_C1_tuple": lambda one: (
            one["length"], one["participants"], one["senders"], one["distinct_hours"],
        ),
        "coarsened": lambda one: (
            one["length_band"], one["participants"], one["senders"], one["hours_band"],
        ),
        "length_band_only": lambda one: (one["length_band"],),
        "participants_only": lambda one: (one["participants"],),
        "senders_only": lambda one: (one["senders"],),
        "hours_band_only": lambda one: (one["hours_band"],),
    }
    return {
        "what_this_is": "a non-gating diagnostic. content_gate.py's C1 is unchanged by it",
        "corpus": {
            "generator_version": manifest.generator_version,
            "master_seed": manifest.master_seed,
            "size_profile": manifest.size_profile,
            "threads_with_a_family": len(rows),
        },
        "length_bands": dict(LENGTH_BANDS),
        "shuffles": SHUFFLES,
        "views": {
            name: _measure([(project(one), family) for one, family in rows], seed)
            for name, project in views.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=4311)
    parser.add_argument("--profile", default="sample")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    built = corpus.generate(master_seed=args.seed, size_profile=args.profile)
    out = report(built)
    text = json.dumps(out, indent=1, sort_keys=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
