"""Record exactly which corpus the round-two results were taken on. Records, not a gate.

A reviewer reading `CORPUS_REPAIR_ROUND2_RESULT_2026-09-16.md` has to be able to regenerate the
bytes those numbers came from and check that they are the same bytes. The generator is
deterministic in its seed, its profile and its own source, so the identity of a corpus is
`(generator source digest, seed, profile)` - and the digest of what it produced is the proof
that the three of them still mean what they meant.

This file computes both sides: the digests of every module the corpus is built from, and the
digest of the manifest those modules produce. Nothing here can change a corpus or a verdict.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from mailweave_harness.seed import corpus
from mailweave_harness.seed.manifest import Manifest

#: Every module a generated corpus depends on. A change to any of them changes the corpus, so
#: all of them are hashed rather than the one that happened to be edited last.
SOURCES: tuple[str, ...] = (
    "harness/src/mailweave_harness/seed/corpus.py",
    "harness/src/mailweave_harness/seed/families.py",
    "harness/src/mailweave_harness/seed/chatter.py",
    "harness/src/mailweave_harness/seed/voice.py",
    "harness/src/mailweave_harness/seed/drafts.py",
    "harness/src/mailweave_harness/seed/situations.py",
    "harness/src/mailweave_harness/seed/world.py",
    "harness/src/mailweave_harness/seed/lexical.py",
    "harness/src/mailweave_harness/seed/manifest.py",
    "harness/src/mailweave_harness/seed/coverage.py",
)

#: The two profiles the round-two results were taken on, with their seeds.
FROZEN: tuple[tuple[int, str], ...] = ((4311, "sample"), (5309, "gate"))


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def source_digests() -> dict[str, str]:
    root = _root()
    return {
        one: hashlib.sha256((root / one).read_bytes()).hexdigest()
        for one in SOURCES
    }


def manifest_digest(built: Manifest) -> dict[str, str]:
    """Two digests: the bodies alone, and the whole manifest including ground truth.

    Separated because they answer different questions. A reviewer asking "is this the same mail"
    reads the first; one asking "is this the same case set" reads the second, which moves when a
    note or a declared position changes even though no message did.
    """
    bodies = "\n".join(
        f"{one.thread_key}|{one.position}|{one.role}|{one.date_rfc2822}|{one.body}"
        for one in sorted(built.messages, key=lambda x: (x.thread_key, x.position))
    )
    whole = built.model_dump_json()
    return {
        "messages_sha256": hashlib.sha256(bodies.encode()).hexdigest(),
        "manifest_sha256": hashlib.sha256(whole.encode()).hexdigest(),
    }


def freeze() -> dict[str, Any]:
    out: dict[str, Any] = {
        "what_this_is": (
            "the identity of the corpus the round-two results were taken on. It is a record, "
            "not a gate: nothing here passes or fails, and nothing here can change a corpus"
        ),
        "regenerate_with": (
            "PYTHONPATH=server/src:harness/src:orivra/src:tests/fixtures:. python -c "
            "'from mailweave_harness.seed.corpus import generate; "
            "generate(master_seed=SEED, size_profile=PROFILE)'"
        ),
        "generator_sources": source_digests(),
        "profiles": {},
    }
    for seed, profile in FROZEN:
        built = corpus.generate(master_seed=seed, size_profile=profile)
        out["profiles"][f"{profile}-{seed}"] = {
            "master_seed": seed,
            "size_profile": profile,
            "generator_version": built.generator_version,
            "messages": len(built.messages),
            "threads": len(built.answer_key.threads),
            **manifest_digest(built),
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--check", type=Path,
        help="compare against an earlier freeze record and exit non-zero if it moved",
    )
    args = parser.parse_args()
    now = freeze()
    text = json.dumps(now, indent=1, sort_keys=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
    if args.check:
        was = json.loads(args.check.read_text())
        moved = {
            key: (was.get(key), now.get(key))
            for key in ("generator_sources", "profiles")
            if was.get(key) != now.get(key)
        }
        if moved:
            print(json.dumps({"frozen": False, "moved": sorted(moved)}, indent=1))
            raise SystemExit(1)
        print(json.dumps({"frozen": True}, indent=1))
        return
    print(text)


if __name__ == "__main__":
    main()
