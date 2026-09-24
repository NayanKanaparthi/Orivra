"""P1: what the dry run actually exercises per arm: seam counts, response semantic_cost, ranking state."""
import json, tempfile
from pathlib import Path
from collections import Counter
from mailweave_harness.evaluation.arms import run_all, SPECS
from mailweave_harness.evaluation.cases import resolve_against
from tests.fixtures.eval_dummy import dummy_arms, dummy_case_file, dummy_manifest, mailbox_of
from mailweave.surface.arguments import parse_search

m = dummy_manifest(); box, ver = mailbox_of(m); cf = dummy_case_file(m)
resolved = [resolve_against(c, manifest=m, report=ver) for c in cf.cases]
print("cases:", len(resolved), Counter(r.case.family for r in resolved))
arms = dummy_arms(m, box, traces=Path(tempfile.mkdtemp()))
tot = Counter()
for r in resolved:
    for arm in arms:
        if arm.counter: arm.counter.reset()
        env = arm.service.search(parse_search({"query": r.case.query}))
        cost = env.retrieval_report.semantic_cost
        c = arm.counter
        tot[(arm.name, "seam_embed")] += 0 if c is None else c.embed_calls
        tot[(arm.name, "seam_rerank")] += 0 if c is None else c.rerank_calls
        tot[(arm.name, "wire_rerank_pairs")] += 0 if cost is None else (cost.rerank_pairs or 0)
        tot[(arm.name, "ordering="+str(None if cost is None else cost.ordering_method))] += 1
for k in sorted(tot): print(k, tot[k])
