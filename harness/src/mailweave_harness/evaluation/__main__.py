"""`python -m mailweave_harness.evaluation` - validate a case file, or run M2's two arms.

    --schema              print the case-file interface: families, distractor types, the
                          sweep grid, and every field with its refusal. Needs nothing.
    --validate CASES      load and check a case file. Every refusal fires here, before any
                          mailbox is touched. Add --manifest to check the ref joins too.
    --run                 run every case on both arms and print the three hypothesis
                          verdicts. Needs a credential, a seeded mailbox, its manifest and
                          its verification report.

**This prints verdicts, not a gate.** A hypothesis that falsifies removes its machinery from
the default path rather than being argued with (M2's brief); a hypothesis that holds is a
measurement a gating reviewer re-runs. Nothing here moves a rubric row.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from mailweave_harness.evaluation.arms import (
    FULL,
    HYPOTHESIS_PAIRS,
    SPECS,
    Arm,
    CaseRun,
    CountingBackend,
    as_json,
    build_arm,
    run_all,
)
from mailweave_harness.evaluation.cases import (
    DISTRACTOR_TYPES,
    FAMILIES,
    FAMILY_LABELS,
    SWEEP_POSITIONS,
    CaseFile,
    ResolvedCase,
    check_against,
    load_cases,
    resolve_against,
)
from mailweave_harness.evaluation.hypotheses import (
    Scoring,
    Verdict,
    evaluate,
    recoverability,
)

LEXICAL_ARM = "lexical-v0.1"
SEMANTIC_ARM = "semantic"


def _path(raw: str) -> Path:
    """Every path argument, expanded. A `~` a shell did not expand is still a home directory,
    and the failure it produces reads like a missing file rather than an unexpanded path."""
    return Path(raw).expanduser()


def _schema() -> str:
    lines = [
        "M2 case-file interface (EVALUATION_PLAN.md §4.1), as this harness enforces it",
        "",
        "A case file is one JSON object:",
        '  {"schema_version": 1, "generator_version": "<from the manifest>",',
        '   "master_seed": <from the manifest>, "cases": [ <case>, ... ]}',
        "",
        "and each case is EP §4.1's object:",
        json.dumps(
            {
                "case_id": "BE-t07-p37-s1042",
                "template_id": "BE-t07",
                "family": "buried_evidence",
                "seed": 1042,
                "query": "<the question>",
                "query_variants": ["<an alternative phrasing>"],
                "evidence": [
                    {
                        "ref": "thread:<thread_key>/pos:<n>",
                        "rfc_message_id": "<optional; checked against the manifest>",
                        "role": "primary",
                        "quote": "<the span that counts as disclosing it>",
                        "answer_field": {"value": "<optional>"},
                    }
                ],
                "evidence_cardinality": "single | all_of | any_of",
                "distractors": [{"ref": "thread:<k>/pos:<n>", "type": "lexical_decoy"}],
                "position": {"thread_len": 100, "target_pos": 37, "fraction": 0.37},
                "paraphrase": {"tier": 2, "content_word_jaccard": 0.0},
                "expected_behavior": {
                    "must_retrieve": ["primary"],
                    "acceptable_not_found": False,
                    "partiality_expected": True,
                    "notes": "<required: what would make a pass hollow>",
                },
                "scoring": {"recall_rule": "<how recall is judged>", "answer_rule": ""},
            },
            indent=2,
        ),
        "",
        "families (the `family` string, and the plan's label):",
    ]
    for family in sorted(FAMILIES):
        lines.append(f"    {FAMILY_LABELS[family]:>4}  {family}")
    lines += [
        "",
        f"distractor types (EP §4.6): {', '.join(sorted(DISTRACTOR_TYPES))}",
        f"position sweep (EP §4.4, fractions normative): {list(SWEEP_POSITIONS)}",
        "",
        "Refused at load, each because scoring it would produce a number nobody could read:",
        "  * an answerable case with no evidence (recall of 1.0 over nothing)",
        "  * an unanswerable control that names evidence, or that does not accept not-found",
        "  * must_retrieve naming a role no evidence item carries",
        "  * a family or distractor type nobody registered",
        "  * a position whose fraction does not describe it (§4.4 makes the fraction normative)",
        "  * a paraphrase tier contradicting its own measured jaccard (§4.5)",
        "  * an empty expected_behavior.notes (§4.1 requires it; the gate reviewer reads it)",
        "  * a ref naming no message in the corpus, or declaring an rfc_message_id the",
        "    manifest does not hold at that position",
        "",
        "This harness holds no queries and no answers. It is written so a campaign can hand",
        "them over as data, and so that a case that cannot be scored is refused before a",
        "mailbox is touched rather than after a number is published.",
    ]
    return "\n".join(lines)


def _validate(cases_path: Path, manifest_path: Path | None) -> int:
    try:
        case_file = load_cases(cases_path)
    except Exception as failure:
        print(f"REFUSED  {cases_path}\n  {type(failure).__name__}: {failure}")
        return 2
    print(f"ok  {cases_path}: {len(case_file.cases)} case(s), schema {case_file.schema_version}")
    print(f"    corpus: generator {case_file.generator_version}, seed {case_file.master_seed}")
    for family, cases in case_file.by_family.items():
        positions = sorted({c.position.target_pos for c in cases if c.position is not None})
        shown = f", positions {positions}" if positions else ""
        print(f"    {FAMILY_LABELS[family]:>4}  {family:<28} {len(cases):>4} case(s){shown}")
    if manifest_path is None:
        print("\n    refs not checked against a corpus: pass --manifest to join them")
        return 0
    from mailweave_harness.seed.manifest import Manifest

    manifest = Manifest.model_validate(json.loads(manifest_path.read_text(encoding="utf-8")))
    if manifest.generator_version != case_file.generator_version or (
        manifest.master_seed != case_file.master_seed
    ):
        print(
            f"REFUSED  the case file was written against generator "
            f"{case_file.generator_version}/seed {case_file.master_seed} and this manifest is "
            f"{manifest.generator_version}/seed {manifest.master_seed}"
        )
        return 2
    # `check_against`, not `resolve_against` with an empty report: the mailbox half cannot hold
    # before seeding, and the previous version told the two apart by **matching the prose of an
    # exception**. A check that depends on an error message's wording is a check that stops
    # working the day somebody improves the wording.
    problems = 0
    for case in case_file.cases:
        try:
            check_against(case, manifest=manifest)
        except Exception as failure:
            problems += 1
            print(f"    REFUSED  {failure}")
    print(f"\n    ref joins against the manifest: {problems} refusal(s)")
    return 0 if problems == 0 else 2


def _export_kit(destination: Path) -> int:
    """Write the kit an independent case author works from. Nothing here reads a mailbox."""
    from mailweave_harness.evaluation import kit

    source_root = Path(__file__).resolve().parents[2]
    destination.mkdir(parents=True, exist_ok=True)
    written = kit.export(destination, source_root=source_root, schema=_schema())
    print(f"case-authoring kit written to {destination}")
    for path in written:
        print(f"  {path.relative_to(destination)}")
    print(
        "\nHand this folder plus the corpus manifest to the case author. It carries no "
        "queries,\nno answers and no retrieval code: the schema modules are this "
        "repository's own files,\nso the refusals the author sees are the refusals the "
        "scoring run applies."
    )
    return 0


#: **The canonical acceptance entry point, and its version.** RR-10. The runner review found
#: the rubric grading structures that live only in `benchmarks/*.py` - a gitignored directory -
#: while the command itself computes neither of the two baselines the review package put in
#: scope. Naming the entry point and stamping its version into every record is what stops a
#: number being read back later against a program nobody can identify.
ENTRY_POINT: dict[str, str] = {
    "command": "python -m mailweave_harness.evaluation",
    "version": "acceptance-runner-2",
    "changed": (
        "2026-09-17 bounded repair against RUNNER_REVIEW_RESULT_2026-09-17.md: verdict "
        "semantics, missing-measurement handling, factor-execution evidence, arm/case/run "
        "isolation, scoring cardinality, control reporting"
    ),
}

#: **What this command does and does not compute**, stated in the record rather than inferred
#: from its absence. Reconciled against `docs/ORIVRA_V1_PLAN.md` (which registers H1-H3) and
#: `docs/EVALUATION_PLAN.md` (which registers the baselines and the metric set). Every entry
#: here is a fact about this program; none of them is a waiver of anything.
SCOPE: dict[str, object] = {
    "hypotheses_registered_in": "docs/ORIVRA_V1_PLAN.md:877-879",
    "arms_run": [spec.name for spec in SPECS],
    "plan_baselines_not_implemented_here": [
        "Baseline A/A' (hosted-MCP provenance)",
        "Baseline B (full-thread dump)",
        "Baseline C (fixed newest/oldest-K)",
        "Baseline D (message-level search)",
        "Baseline E (primitive-tools agent) - `primitive.py` is a fixed policy and says in "
        "its own docstring that it is not Baseline E",
        "Baseline F at N != 2 (no budget-recall curve)",
        "SEM-LOCAL-ALT / SEM-HOSTED (no backend-parity arm)",
    ],
    "plan_metrics_not_computed_here": [
        "rank_of_evidence",
        "token totals as a reported metric (captured per case, not aggregated)",
        "latency p50/p95 and the cold/warm split",
        "Gmail API call counts at the network layer",
        "the escalation confusion table and escalation_cost",
        "budget-matched budget-recall curves",
        "P6/P7 pass rates and every freshness measure",
        "McNemar / paired bootstrap (deltas and Wilson intervals only)",
    ],
    "in_this_package_but_not_run_by_this_command": {
        "boundary.py": "a second recovery driver through the MCP boundary",
        "queryfree.py": "the query-free baseline",
        "note": (
            "both are imported only by gitignored scripts under benchmarks/. They are not "
            "capabilities of this command and the review brief should not have described "
            "them as in scope for it"
        ),
    },
}


def _present(runs: Sequence[CaseRun], resolved: Sequence[ResolvedCase], *, out: Path | None) -> int:
    """Every comparison, the recoverability report and the three verdicts.

    **Shared between `--run` and `--dry-run` on purpose.** What the dry run establishes
    is that this code path executes end to end with the instruments attached; that claim
    is only worth making if it is the same code path. The live run differs from the dry
    run in exactly two places - `runtime.start` with a real credential, and the case
    files read from disk - and everything downstream of the runs is this function.
    """
    from mailweave_harness.evaluation import primitive, report

    # N-7: one scoring object, built once from the case file's own declared cardinality, and
    # handed to every metric and to the report. The verdict path and the printed table cannot
    # disagree about what a case was worth because there is only one scorer.
    scoring = Scoring.of(resolved)
    required = dict(scoring.required)
    # **RR-05. The comparison table is derived from `HYPOTHESIS_PAIRS`, not written out again
    # beside it.** The hand-written tuple carried no `full vs no-rerank` block, so H2's verdict
    # was printed with no comparison table for its own baseline - in stdout and in the `--out`
    # record. A declaration and the thing it declares were two artefacts once before in this
    # file; deriving one from the other is the only thing that stops it happening a third time.
    by_name = {spec.name: spec for spec in SPECS}
    comparisons = tuple(
        (candidate, baseline, by_name[baseline].isolates)
        for candidate, baseline in HYPOTHESIS_PAIRS.values()
    ) + (
        (FULL.name, primitive.TIGHT.name, "MailWeave against a fixed primitive-tools policy"),
        (FULL.name, primitive.GENEROUS.name, "the same floor at the wider budget"),
    )
    for candidate, baseline, isolates in comparisons:
        print(
            report.render(
                runs,
                scoring=scoring,
                candidate_arm=candidate,
                baseline_arm=baseline,
                isolates=isolates,
            )
        )
        print()
    print("RECOVERABILITY - what expansion added over the first response")
    for arm in (*(spec.name for spec in SPECS), primitive.TIGHT.name, primitive.GENEROUS.name):
        print("  " + json.dumps(recoverability(runs, arm=arm)))
    print()
    # **One hypothesis, one factor, one baseline** (`HYPOTHESIS_PAIRS`). H2's baseline is
    # `no-rerank`, not `sem-off`: the latter removes stage-A embedding as well, so a verdict
    # computed against it answers H1's question under H2's name.
    # **N-8: the mapping itself, not four hand-keyed slots.** The previous version read
    # `HYPOTHESIS_PAIRS["H1"][0]` as *the* candidate for all three hypotheses and each
    # baseline by literal key, so changing H2's pair reached the comparison table and not the
    # verdict. `evaluate` takes the mapping and derives both arms of every pair from it.
    results = evaluate(runs, scoring=scoring, pairs=HYPOTHESIS_PAIRS)
    # The table above is derived from the same mapping, so a pair the registered hypotheses do
    # not read still gets a comparison block printed and no verdict beneath it. That is the
    # divergence this file keeps producing, in its smallest form: say it out loud rather than
    # letting a reader take an unlabelled block for evidence about a hypothesis.
    decided = {result.id for result in results}
    orphans = [name for name in HYPOTHESIS_PAIRS if name not in decided]
    if orphans:
        print(
            f"  NOTE: {', '.join(sorted(orphans))} appear(s) in HYPOTHESIS_PAIRS and has no "
            "registered clause in contracts.py. Its comparison block above is printed and "
            "nothing below decides it"
        )
    for result in results:
        print(f"[{result.id}] {result.verdict.value.upper()}")
        print(f"      {result.statement}")
        for clause in result.clauses:
            print(f"  {clause.verdict.value:>14}  {clause.name}")
            print(f"                  falsified if: {clause.quoted}")
            print(f"                  {clause.detail}")
    if out is not None:
        out.write_text(
            json.dumps(
                {
                    "entry_point": ENTRY_POINT,
                    "scope": SCOPE,
                    "cases": len(resolved),
                    "runs": len(runs),
                    "arms": [
                        {
                            "name": s.name,
                            "isolates": s.isolates,
                            "does_not_isolate": s.does_not_isolate,
                        }
                        for s in SPECS
                    ]
                    + [{"name": b.name, "isolates": b.why} for b in primitive.BUDGETS],
                    "per_case": [as_json(one) for one in runs],
                    "report": {
                        f"{candidate} vs {baseline}": report.render(
                            runs,
                            scoring=scoring,
                            candidate_arm=candidate,
                            baseline_arm=baseline,
                            isolates=isolates,
                        )
                        for candidate, baseline, isolates in comparisons
                    },
                    "recoverability": [
                        recoverability(runs, arm=name)
                        for name in (
                            *(spec.name for spec in SPECS),
                            primitive.TIGHT.name,
                            primitive.GENEROUS.name,
                        )
                    ],
                    "hypotheses": [
                        {
                            "id": r.id,
                            "verdict": r.verdict.value,
                            "clauses": [
                                {
                                    "name": c.name,
                                    "verdict": c.verdict.value,
                                    "falsified_if": c.quoted,
                                    "detail": c.detail,
                                }
                                for c in r.clauses
                            ],
                        }
                        for r in results
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nrecord written to {out}")
    print(
        "\nThese are measurements, not a gate. A falsified hypothesis removes its machinery "
        "from the default path rather than being argued with; one that holds is a citation a "
        "gating reviewer re-runs."
    )
    return 0 if all(r.verdict is not Verdict.FALSIFIED for r in results) else 2


def _run(args: argparse.Namespace) -> int:
    """Every arm, with every instrument attached, and the three questions answered.

    **All four MailWeave arms plus both primitive-floor budgets run**, and a trace sink is
    attached to each MailWeave arm - without one `cut_loss` is UNMEASURED and H2's first
    clause cannot be decided, which would be a missing instrument reported as a result.
    """
    import httpx

    from mailweave.disclosure import FixedWindow
    from mailweave.net.egress import build_client
    from mailweave.semantic import REGISTRY
    from mailweave.semantic.interface import BackendRegistry
    from mailweave.surface import runtime
    from mailweave_harness.evaluation import primitive
    from mailweave_harness.evaluation.observe import FetchLog, FetchObserver
    from mailweave_harness.seed.manifest import Manifest
    from mailweave_harness.seed.substrate import VerificationReport

    manifest = Manifest.model_validate(json.loads(args.manifest.read_text(encoding="utf-8")))
    if args.live_check:
        # **The corpus writing its own case file.** Every query is a sentinel token, so no arm
        # can be distinguished from another and nothing here is evidence about retrieval. What
        # it establishes is the thing `--dry-run` cannot: that `runtime.start` with a real
        # credential, the trace sinks, the floor client and the report all work against the
        # live mailbox, found out now rather than on the first run that matters.
        from mailweave_harness.evaluation.selftest import sentinel_case_file

        case_file: CaseFile = sentinel_case_file(manifest)
    else:
        case_file = load_cases(args.cases)
    verification = VerificationReport(**json.loads(args.verification.read_text(encoding="utf-8")))
    resolved = [
        resolve_against(case, manifest=manifest, report=verification) for case in case_file.cases
    ]
    args.traces.mkdir(parents=True, exist_ok=True)

    started: list[runtime.Runtime] = []
    arms: list[Arm] = []
    counters: dict[str, CountingBackend] = {}
    try:
        for spec in SPECS:
            registry = BackendRegistry()
            if spec.semantic:

                def factory(name: str = spec.name) -> CountingBackend:
                    made = CountingBackend(REGISTRY.acquire())
                    counters[name] = made
                    return made

                registry.register("counting", factory, default=True)
            # The observer sits *underneath* the egress allowlist - `build_client(inner=)`
            # wraps it - so it records what was actually sent and cannot widen what the
            # server may reach. It is EP §6.4's "observable at the network layer", and the
            # lexical arm has no pool without it.
            log = FetchLog()
            live = runtime.start(
                client_path=args.client_path,
                http=build_client(inner=FetchObserver(httpx.HTTPTransport(), log)),
                registry=registry,
                selector=FixedWindow() if spec.fixed_window else None,
                # D.7's second tier. `False` is the H2 bypass arm (`no-rerank`): the shipped
                # startup path builds it, so the arm under measurement is the arm this server
                # would run with that one setting changed.
                cross_encoder=spec.cross_encoder,
            )
            started.append(live)
            # RR-06: one arm constructor, shared with the dry run. It also gives the arm its
            # own trace root and its own watermark (RR-07), so no two arms share either and
            # neither touches the production state directory.
            # N-4: `warm_semantic_backend` returning `False` is discarded by `runtime.start`,
            # so the runner asks the registry directly and records the answer as layer (1).
            # A semantic arm whose backend did not load is not a lexical arm; every clause
            # that reads a semantic count has to be able to tell them apart.
            available: bool | None = None
            if spec.semantic:
                available = counters.get(spec.name) is not None
            arms.append(
                build_arm(
                    spec,
                    live.service,
                    counter=counters.get(spec.name),
                    traces_root=args.traces,
                    fetch_log=log,
                    backend_available=available,
                )
            )
        runs = list(run_all(arms, resolved))
        # **The floor uses the same credential and the same client construction**, so its
        # API-call and quota counts are comparable with MailWeave's rather than being a
        # different instrument's numbers.
        # The floor shares the first arm's transport, so its traffic would land in that
        # arm's log. Drained first, and nothing reads it afterwards: the floor's pool is not
        # attributed to any arm, and an undrained log would become the next reader's pool.
        for built in arms:
            if built.fetch_log is not None:
                built.fetch_log.take()
        floor_client = started[0].service.open_client()
        runs.extend(primitive.run_all(primitive.PrimitiveTools(client=floor_client), resolved))
    finally:
        for live in started:
            live.close()

    if args.live_check:
        print(
            "LIVE CHECK - sentinel-token queries against the real corpus. Every query has one\n"
            "lexical match by construction, so no arm can differ from another and no number\n"
            "below is evidence about retrieval. What it establishes is that this command runs\n"
            "end to end against a live credential.\n"
        )
    return _present(runs, resolved, out=None if args.live_check else args.out)


def _dry_run(traces: Path, out: Path | None = None) -> int:
    """The whole pipeline on the dummy corpus, offline. No credential, no mailbox, no network.

    This exists so the command path is exercised before it is handed over: the arms build, the
    floor runs, the report renders and the verdicts compute. **Every number it prints is about
    dummy cases whose queries are sentinel tokens** and says nothing about retrieval.
    """
    from mailweave.gmail import BackoffPolicy, CallMeter, GmailClient, StaticToken
    from mailweave.net.egress import build_client
    from mailweave_harness.evaluation import primitive
    from tests.fixtures.eval_dummy import (
        TOKEN,
        dummy_arms,
        dummy_case_file,
        dummy_manifest,
        mailbox_of,
    )

    manifest = dummy_manifest()
    box, verification = mailbox_of(manifest)
    case_file = dummy_case_file(manifest)
    resolved = [
        resolve_against(case, manifest=manifest, report=verification) for case in case_file.cases
    ]
    arms = dummy_arms(manifest, box, traces=traces)
    runs = list(run_all(arms, resolved))
    tools = primitive.PrimitiveTools(
        client=GmailClient(
            token=StaticToken(TOKEN),
            http=build_client(inner=box.transport()),
            meter=CallMeter(),
            policy=BackoffPolicy(),
            sleeper=lambda _seconds: None,
            jitterer=lambda: 0.5,
        )
    )
    runs.extend(primitive.run_all(tools, resolved))
    print("DRY RUN - dummy cases, sentinel-token queries, no mailbox. No number here is")
    print("evidence about retrieval; what it establishes is that the command path executes.\n")
    for spec in SPECS:
        print(f"  arm {spec.name:<22} isolates: {spec.isolates[:88]}")
    for budget in primitive.BUDGETS:
        print(f"  arm {budget.name:<22} {budget.why}")
    print()
    # **The same presentation the live run uses, and the same record writer.** `out` used to
    # be hard-coded to `None` here, so the one path a reviewer can run offline was the one
    # path that never exercised the campaign record - the same shape as RR-06, one step on.
    code = _present(runs, resolved, out=out)
    answerable = sum(1 for one in resolved if one.case.family != "unanswerable_control")
    controls = len(resolved) - answerable
    print(
        f"\nNothing above is evidence about retrieval. {answerable} dummy case(s) and "
        f"{controls} control(s) cannot reach any registered n, which is why every hypothesis "
        "reports NOT_EVALUABLE rather than a verdict, and that is the correct output for this "
        "corpus."
    )
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mailweave-evaluation", description=__doc__)
    parser.add_argument("--schema", action="store_true", help="the case-file interface")
    parser.add_argument(
        "--export-kit",
        type=_path,
        default=None,
        metavar="DIR",
        help=(
            "write the independent case-authoring kit: the brief, the field list, the "
            "registered families, the hypotheses, and a standalone checker built from this "
            "repository's own schema modules. Carries no queries, no answers and no retrieval "
            "code. Offline"
        ),
    )
    parser.add_argument("--validate", type=_path, default=None, metavar="CASES")
    parser.add_argument("--manifest", type=_path, default=None, metavar="PATH")
    parser.add_argument("--run", action="store_true")
    parser.add_argument(
        "--live-check",
        action="store_true",
        help=(
            "run the whole campaign command against the real seeded mailbox using a "
            "sentinel-token case file the corpus writes about itself. Needs --manifest and "
            "--verification but NOT --cases. Establishes that the live path works; "
            "establishes nothing about retrieval"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "run the whole pipeline on the dummy corpus, offline: arms, floor, report and "
            "verdicts. Needs no credential and no mailbox, and every number it prints is "
            "about sentinel-token queries rather than about retrieval"
        ),
    )
    parser.add_argument("--cases", type=_path, default=None, metavar="PATH")
    parser.add_argument("--verification", type=_path, default=None, metavar="PATH")
    parser.add_argument("--client-path", type=_path, default=Path("mailweave-server-oauth.json"))
    parser.add_argument("--out", type=_path, default=None, metavar="PATH")
    parser.add_argument(
        "--traces",
        type=_path,
        default=Path("benchmarks/traces"),
        help=(
            "where each arm's trace goes, one root per arm. The exposed candidate set lives "
            "in the trace and nowhere else (D.10); without it the pool falls back to EP "
            "6.4's network-layer clause, which is measured but is a different instrument - "
            "`pool_source` on each case says which one produced its figure"
        ),
    )
    args = parser.parse_args(argv)

    if args.export_kit is not None:
        return _export_kit(args.export_kit)
    if args.dry_run:
        args.traces.mkdir(parents=True, exist_ok=True)
        return _dry_run(args.traces, args.out)
    if args.validate is not None:
        return _validate(args.validate, args.manifest)
    if args.run or args.live_check:
        needed = (
            (("--manifest", args.manifest), ("--verification", args.verification))
            if args.live_check
            else (
                ("--cases", args.cases),
                ("--manifest", args.manifest),
                ("--verification", args.verification),
            )
        )
        missing = [name for name, value in needed if value is None]
        if missing:
            flag = "--live-check" if args.live_check else "--run"
            raise SystemExit(f"{flag} needs {', '.join(missing)}")
        return _run(args)
    print(_schema())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
