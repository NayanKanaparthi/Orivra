"""PF-4b's two halves that need no Node: the corpus export, and the record reader.

**Why this is a file and not a note saying "run the Node arm".** PF-4b's first pre-registered
rule is that *both arms embed the same rows, from the same seed, so the comparison is not
between two samples of one distribution*. A rule like that is exactly the kind this project
keeps finding was asserted rather than held: the Python arm generates its rows from a seeded
RNG in Python, and a Node arm that re-implemented the same generator in JavaScript would
produce *similar* rows and the rule would read as satisfied while being false.

So the rows cross the language boundary as **data**. `export_corpus` writes the exact strings
the Python arm measured, with the seed and the sizes beside them; the Node arm reads that
file and embeds what it is given. `record_from` then reads the Node arm's timings back and
refuses them if they do not describe the corpus that was exported - by digest, not by
agreement about a seed.

**What this file cannot do, and says so.** It cannot measure Node. That needs a Node runtime,
`@huggingface/transformers`, and the `node-onnx` artifact set on a machine - all of which are
the owner's laptop. What it does is make the run a two-command operation whose result is
checkable, instead of a number typed into a document.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from mailweave_harness.modelbench.corpus import pool_rows, rerank_pairs
from mailweave_harness.modelbench.spec import POOL_SIZES, REPEATS, RERANK_SIZES

#: The seed both arms take their rows from. One constant, exported beside the rows, so a
#: disagreement about it is visible in the file rather than inferred from two behaviours.
CORPUS_SEED: int = 20260911

#: The exported file's own schema. A Node arm reading a shape it does not know should say so
#: rather than index into it hopefully.
CORPUS_SCHEMA: int = 1


def corpus_payload(*, body_head: bool = False, seed: int = CORPUS_SEED) -> dict[str, Any]:
    """Exactly the rows and pairs the Python arm measures, as data.

    The largest pool size is generated once and the smaller sizes are its prefixes, which is
    what `measure_python_arm` does - so "the same rows" is true across sizes as well as
    across arms.
    """
    rows = pool_rows(max(POOL_SIZES), seed=seed, body_head=body_head)
    query, candidates = rerank_pairs(max(RERANK_SIZES), seed=seed)
    payload: dict[str, Any] = {
        "schema": CORPUS_SCHEMA,
        "seed": seed,
        "body_head": body_head,
        "pool_sizes": list(POOL_SIZES),
        "rerank_sizes": list(RERANK_SIZES),
        "repeats": REPEATS,
        "rows": rows,
        "rerank_query": query,
        "rerank_candidates": candidates,
    }
    payload["digest"] = corpus_digest(payload)
    return payload


def corpus_digest(payload: Mapping[str, Any]) -> str:
    """A digest of the *rows*, which is what the two arms have to share.

    Deliberately not a digest of the whole file: the seed and the size list are metadata a
    reader checks by eye, and including them would make a formatting change look like a
    different corpus. What must be identical is the text that was embedded.
    """
    hasher = hashlib.sha256()
    for row in payload["rows"]:
        hasher.update(row.encode("utf-8"))
        hasher.update(b"\x00")
    hasher.update(str(payload["rerank_query"]).encode("utf-8"))
    for candidate in payload["rerank_candidates"]:
        hasher.update(candidate.encode("utf-8"))
        hasher.update(b"\x00")
    return hasher.hexdigest()


def export_corpus(path: Path, *, body_head: bool = False, seed: int = CORPUS_SEED) -> Path:
    """Write the corpus the Node arm must embed. Returns the path written."""
    payload = corpus_payload(body_head=body_head, seed=seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


class NodeArmRefused(ValueError):
    """The Node arm's results do not describe the corpus that was exported."""


#: The two stages PF-4b compares. A Node arm may measure one of them and say so; it may not
#: measure one of them and stay quiet, which is the distinction `read_node_results` enforces.
STAGES: Final[tuple[str, ...]] = ("embed", "rerank")


@dataclass(frozen=True)
class NodeArm:
    """What the Node arm reported, after it has been checked against the exported corpus."""

    corpus_digest: str
    runtime_versions: Mapping[str, str]
    device: str
    cold_acquire_ms: int
    warm_acquire_ms: int
    embed_ms_by_pool_size: Mapping[int, int]
    rerank_ms_by_pairs: Mapping[int, int]
    repeats_per_size: int
    embedding_dimension: int
    #: Which of `STAGES` this arm actually measured. **A partial arm is a legitimate result
    #: and a silent one is not.** Today `models-catalog.json` pins a `node-onnx` artifact set
    #: for `stage_b_default` and for nothing else: `stage_a_default`
    #: (`minishlab/potion-retrieval-32M`) has no Node set, so a Node arm on this repository's
    #: lock has nothing to embed with and can only measure the reranker. Recording that as
    #: `stages_measured: ["rerank"]` keeps the gap in the record, where R2's condition can see
    #: it, instead of leaving a reader to infer it from an absent key.
    stages_measured: tuple[str, ...] = STAGES


def read_node_results(results: Mapping[str, Any], corpus: Mapping[str, Any]) -> NodeArm:
    """Validate one Node-arm result file against the corpus it claims to have measured.

    **Every check here is a refusal, not a warning.** PF-4b exists to decide whether the
    stack decision reopens (AD B.8 R2), and a comparison between two arms that measured
    different rows, different sizes or different repeat counts is not evidence about the
    stack - it is evidence about the two harnesses. A result that cannot be checked is worth
    less than no result, because it looks like one.
    """
    digest = str(results.get("corpus_digest", ""))
    expected = str(corpus.get("digest") or corpus_digest(corpus))
    if digest != expected:
        raise NodeArmRefused(
            "the Node arm reports a different corpus digest from the exported corpus, so "
            "the two arms did not embed the same rows (PF-4b registered rule 1)"
        )
    stages = _stages(results)
    embed = (
        _int_keyed(results.get("embed_ms_by_pool_size"), "embed_ms_by_pool_size")
        if "embed" in stages
        else {}
    )
    rerank = (
        _int_keyed(results.get("rerank_ms_by_pairs"), "rerank_ms_by_pairs")
        if "rerank" in stages
        else {}
    )
    if "embed" in stages and sorted(embed) != sorted(corpus["pool_sizes"]):
        raise NodeArmRefused(
            f"the Node arm timed pool sizes {sorted(embed)}, the corpus declares "
            f"{sorted(corpus['pool_sizes'])}"
        )
    if "rerank" in stages and sorted(rerank) != sorted(corpus["rerank_sizes"]):
        raise NodeArmRefused(
            f"the Node arm timed {sorted(rerank)} pairs, the corpus declares "
            f"{sorted(corpus['rerank_sizes'])}"
        )
    for stage, timings in (("embed", "embed_ms_by_pool_size"), ("rerank", "rerank_ms_by_pairs")):
        if stage not in stages and results.get(timings):
            raise NodeArmRefused(
                f"the Node arm reports {timings} while declaring it did not measure "
                f"{stage!r}; the declaration and the numbers have to agree or one of them is "
                "decoration"
            )
    repeats = results.get("repeats_per_size")
    if not isinstance(repeats, int) or repeats < corpus["repeats"]:
        raise NodeArmRefused(
            f"the Node arm reports repeats_per_size={repeats!r}; PF-4's registered rule is "
            f"{corpus['repeats']} repeats with the median recorded, and a single pass is "
            "what produced run 1's falling rerank curve"
        )
    device = results.get("device")
    if not isinstance(device, str) or not device:
        raise NodeArmRefused(
            "the Node arm did not record the device it loaded on; a device chosen by a "
            "library default is an unverified assumption under every number above it"
        )
    return NodeArm(
        corpus_digest=digest,
        runtime_versions=dict(results.get("runtime_versions") or {}),
        device=device,
        cold_acquire_ms=int(results.get("cold_acquire_ms", 0)),
        warm_acquire_ms=int(results.get("warm_acquire_ms", 0)),
        embed_ms_by_pool_size=embed,
        rerank_ms_by_pairs=rerank,
        repeats_per_size=repeats,
        embedding_dimension=int(results.get("embedding_dimension", 0)),
        stages_measured=stages,
    )


def _stages(results: Mapping[str, Any]) -> tuple[str, ...]:
    """Which stages this arm declares it measured, defaulting to both for an older file.

    Defaulting to both is safe because the size checks below then apply in full: a file that
    predates this field and measured only one stage is refused for the stage it left empty,
    which is the behaviour it had before the field existed.
    """
    raw = results.get("stages_measured")
    if raw is None:
        return STAGES
    if not isinstance(raw, list | tuple) or not raw:
        raise NodeArmRefused("stages_measured is present and is not a non-empty list")
    stages = tuple(str(stage) for stage in raw)
    unknown = [stage for stage in stages if stage not in STAGES]
    if unknown:
        raise NodeArmRefused(f"stages_measured names {unknown}; PF-4b compares {list(STAGES)}")
    return stages


def _int_keyed(raw: Any, field: str) -> dict[int, int]:
    if not isinstance(raw, dict) or not raw:
        raise NodeArmRefused(f"the Node arm reported no {field}")
    out: dict[int, int] = {}
    for key, value in raw.items():
        try:
            out[int(key)] = int(value)
        except (TypeError, ValueError) as exc:
            raise NodeArmRefused(f"{field} carries a non-numeric entry {key!r}") from exc
    return out


def comparison(python_arm: Mapping[str, Any], node: NodeArm) -> dict[str, Any]:
    """The two arms side by side, with R2's firing condition evaluated rather than eyeballed.

    R2 fires when the Node arm is *materially* faster at equal quality on the same pool and
    the same hardware. "Materially" is pre-registered here as a ratio rather than left to a
    reader: a 5% difference between two runtimes on one laptop is noise, and reopening a
    stack decision on noise is how a project loses a week.
    """
    if "embed" not in node.stages_measured:
        # **R2 is not evaluable, and that is a result rather than a gap to fill in later.**
        # Its condition is "materially faster at equal quality", and the quantity the
        # semantic rung actually spends at `MAX_POOL_MESSAGES` is stage A. A comparison over
        # the reranker alone would answer a smaller question under R2's name.
        return {
            "shared_pool_sizes": [],
            "python_over_node_embed_ratio": {},
            "node_is_materially_faster_at": [],
            "r2_fires": False,
            "r2_evaluable": False,
            "why_not_evaluable": (
                "the Node arm measured "
                f"{list(node.stages_measured)} and not the embed stage, because "
                "models-catalog.json pins a node-onnx artifact set for stage_b_default and "
                "for no other model. R2 asks whether the Node stack is materially faster at "
                "equal quality; the cost the semantic rung is bounded by at "
                "MAX_POOL_MESSAGES is stage A, so an answer over the reranker alone would be "
                "a different question wearing R2's name"
            ),
            "materially_means": "the Python arm takes at least twice as long at a shared size",
            "quality_is_not_compared_here": (
                "R2's condition is 'materially faster at equal quality'. This compares "
                "latency only; equal quality is H1/H2/H3's question on F1-F17 and is not "
                "established by any number here"
            ),
        }
    python_embed = {int(k): int(v) for k, v in python_arm["embed_ms_by_pool_size"].items()}
    shared = sorted(set(python_embed) & set(node.embed_ms_by_pool_size))
    ratios = {
        size: (python_embed[size] / node.embed_ms_by_pool_size[size])
        if node.embed_ms_by_pool_size[size]
        else None
        for size in shared
    }
    material = [size for size, ratio in ratios.items() if ratio is not None and ratio >= 2.0]
    return {
        "shared_pool_sizes": shared,
        "python_over_node_embed_ratio": ratios,
        "node_is_materially_faster_at": material,
        "r2_fires": bool(material),
        "r2_evaluable": True,
        "materially_means": "the Python arm takes at least twice as long at a shared size",
        "quality_is_not_compared_here": (
            "R2's condition is 'materially faster at equal quality'. This compares latency "
            "only; equal quality is H1/H2/H3's question on F1-F17 and is not established by "
            "either arm of PF-4"
        ),
    }


__all__ = [
    "CORPUS_SCHEMA",
    "CORPUS_SEED",
    "NodeArm",
    "NodeArmRefused",
    "comparison",
    "corpus_digest",
    "corpus_payload",
    "export_corpus",
    "read_node_results",
]
