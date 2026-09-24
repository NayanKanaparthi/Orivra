"""`python -m mailweave_harness.modelbench` - run PF-4 on this machine.

No credential, no mailbox, no network. It needs the weights `mailweave setup-models` put on
disk and nothing else.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from mailweave.models.lock import load_lock
from mailweave.models.paths import DEFAULT_MODELS_DIR
from mailweave_harness.modelbench.measure import analyse, measure_python_arm
from mailweave_harness.modelbench.nodearm import (
    NodeArmRefused,
    comparison,
    export_corpus,
    read_node_results,
)
from mailweave_harness.modelbench.spec import PF4, PF4B
from mailweave_harness.preflight.record import write_records


def _plan() -> str:
    lines = ["PF-4 / PF-4b - run plan", ""]
    for probe in (PF4, PF4B):
        lines.append(f"[{probe.id}] {probe.title}")
        lines.append(f"    measures:    {probe.measures}")
        lines.append(f"    validates:   {probe.validates}")
        lines.append(f"    FAILS WHEN:  {probe.falsified_when}")
        lines.append(f"    then:        {probe.changes_if_it_fails}")
        for rule in probe.pre_registered_rules:
            lines.append(f"    registered:  {rule}")
        lines.append("")
    lines.append("Nothing in this plan has been run. No mailbox is touched and no text is")
    lines.append("recorded: the rows are synthetic and the record carries only numbers.")
    return "\n".join(lines)


def _python_findings(record_path: Path | None, out_dir: Path) -> dict[str, Any]:
    """The Python arm's findings, from a named record or the newest one written.

    Read from the record rather than re-measured, because re-measuring here would compare a
    Node run from one machine-state against a Python run from another - which is the shape
    PF-4b's first registered rule exists to rule out, one level up from the rows.
    """
    if record_path is None:
        candidates = sorted(out_dir.glob("**/PF-4-model-latency*.json"))
        if not candidates:
            raise SystemExit(
                f"no PF-4 record under {out_dir}; run `--run` first, or pass --python-record"
            )
        record_path = candidates[-1]
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    findings = payload.get("findings")
    if not isinstance(findings, dict):
        raise SystemExit(f"{record_path} carries no findings block")
    return findings


def _compare_arms(args: argparse.Namespace) -> int:
    """PF-4b's third step: check the Node arm against the corpus, then compare."""
    if args.corpus is None:
        raise SystemExit("--node-results needs --corpus: the file the Node arm was given")
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    results = json.loads(args.node_results.read_text(encoding="utf-8"))
    try:
        node = read_node_results(results, corpus)
    except NodeArmRefused as refusal:
        print(f"PF-4b: the Node arm's result is REFUSED\n  {refusal}")
        return 2
    python_findings = _python_findings(args.python_record, args.out)
    verdict = comparison(python_findings, node)

    print(f"PF-4b - corpus {node.corpus_digest[:12]}, stages {list(node.stages_measured)}")
    print(f"  node device         {node.device:>12}")
    print(
        "  node runtime        "
        + ", ".join(f"{k} {v}" for k, v in sorted(node.runtime_versions.items()))
    )
    print(f"  node cold acquire   {node.cold_acquire_ms:>12,} ms")
    print(f"  node warm acquire   {node.warm_acquire_ms:>12,} ms")
    for pairs, ms in sorted(node.rerank_ms_by_pairs.items()):
        python_ms = python_findings["rerank_ms_by_pairs"].get(pairs) or python_findings[
            "rerank_ms_by_pairs"
        ].get(str(pairs))
        print(f"    rerank {pairs:>4} pairs  node {ms:>8,} ms   python {python_ms or '-':>8} ms")
    for size, ms in sorted(node.embed_ms_by_pool_size.items()):
        print(f"    embed  {size:>4} rows   node {ms:>8,} ms")
    if verdict.get("r2_evaluable") is False:
        print("\n  R2: NOT EVALUABLE")
        for line in str(verdict["why_not_evaluable"]).split(". "):
            print(f"      {line.strip()}")
    else:
        print(f"\n  R2 fires: {verdict['r2_fires']}")
        print(f"      materially means: {verdict['materially_means']}")
        print(f"      faster at: {verdict['node_is_materially_faster_at'] or 'no shared size'}")
    print(f"\n  {verdict['quality_is_not_compared_here']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mailweave-modelbench", description=__doc__)
    parser.add_argument("--plan", action="store_true", help="the run plan; needs nothing")
    parser.add_argument("--run", action="store_true", help="measure on this machine")
    parser.add_argument("--lock", type=Path, default=Path("models.lock"))
    parser.add_argument("--models-dir", type=Path, default=DEFAULT_MODELS_DIR)
    parser.add_argument("--out", type=Path, default=Path("preflight-records"))
    parser.add_argument(
        "--body-head",
        action="store_true",
        help="measure D.5's fallback branch (400-char body heads) instead of snippets",
    )
    parser.add_argument(
        "--export-node-corpus",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "write the exact rows PF-4 measured, for the PF-4b Node arm to embed. The rows "
            "cross the language boundary as data rather than as a seed, so 'both arms "
            "embedded the same rows' is checkable by digest instead of asserted"
        ),
    )
    parser.add_argument(
        "--node-results",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "read a PF-4b Node-arm result file, check it against the corpus that produced it "
            "and print the two arms side by side with R2's condition evaluated. Needs "
            "--corpus, and --python-record when the Python arm's numbers are not in --out"
        ),
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=None,
        metavar="PATH",
        help="the corpus file --export-node-corpus wrote, for --node-results to check against",
    )
    parser.add_argument(
        "--python-record",
        type=Path,
        default=None,
        metavar="PATH",
        help="a PF-4 record to compare against; defaults to the newest one under --out",
    )
    args = parser.parse_args(argv)

    if args.node_results is not None:
        return _compare_arms(args)

    if args.export_node_corpus is not None:
        written = export_corpus(args.export_node_corpus, body_head=args.body_head)
        print(f"wrote {written}")
        print(
            "the Node arm embeds these rows and reports back its own timings plus this "
            "file's `digest`; `nodearm.read_node_results` refuses a result that does not "
            "carry it"
        )
        return 0

    if not args.run:
        print(_plan())
        return 0

    lock = load_lock(args.lock)
    print("loading models (this is the cold cost being measured) ...", file=sys.stderr)
    arm = measure_python_arm(lock, models_dir=args.models_dir, body_head=args.body_head)
    result = analyse(arm)

    print(f"{result.spec.id}: {result.verdict.value}\n")
    findings = result.findings
    print(f"  device              {findings['device']:>8}")
    unused = findings["accelerators_available_but_unused"]
    print(f"  present but unused  {(', '.join(unused) or 'none'):>8}")
    versions = findings["runtime_versions"]
    print(f"  runtime             {', '.join(f'{k} {v}' for k, v in sorted(versions.items()))}")
    print(f"  repeats per size    {findings['repeats_per_size']:>8}")
    print(f"  cold acquire        {findings['cold_acquire_ms']:>8,} ms   (once per process)")
    print(f"  warm acquire        {findings['warm_acquire_ms']:>8,} ms   (second acquire)")
    print(f"  reuse holds         {findings['reuse_holds']!s:>8}")
    print("  embed wall clock (median of repeats)")
    for size, ms in findings["embed_ms_by_pool_size"].items():
        samples = findings["embed_samples_by_pool_size"][size]
        print(f"    {size:>4} rows        {ms:>8,} ms   samples {samples}")
    print(
        f"  one call, one row   {findings['single_call_embed_ms']:>8,} ms"
        "   (call overhead + a row; do not multiply by a pool size)"
    )
    print("  rerank wall clock (median of repeats, after a discarded warm-up)")
    for pairs, ms in findings["rerank_ms_by_pairs"].items():
        samples = findings["rerank_samples_by_pairs"][pairs]
        print(f"    {pairs:>4} pairs       {ms:>8,} ms   samples {samples}")
    print(
        f"  curves readable     "
        f"embed {findings['embed_curve_is_non_decreasing']}, "
        f"rerank {findings['rerank_curve_is_non_decreasing']}"
    )
    print(f"  dimension           {findings['embedding_dimension']:>8}")
    print(f"  peak RSS            {findings['peak_rss_mb']:>8,} MB")
    print(
        f"\n  warm per-query at pool {findings['published_max_pool_messages']}: "
        f"{findings['warm_per_query_ms_at_published_pool']:,} ms "
        f"against MAX_SEMANTIC_MS {findings['published_max_semantic_ms']:,} ms"
    )
    for note in result.notes:
        print(f"\n  note: {note}")

    summary = write_records([result], args.out)
    print(f"\nrecord written to {summary}", file=sys.stderr)
    return 0 if result.verdict.value == "pass" else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
