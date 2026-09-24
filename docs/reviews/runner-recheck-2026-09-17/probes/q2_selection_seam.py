"""Is select_calls counting the factor reaching the response, or the selector being consulted?"""
import tempfile
from pathlib import Path
from collections import Counter
from mailweave.envelope.reasons import QueryScoredFill, WindowOffset
from mailweave_harness.evaluation.arms import run_case, FULL, FIXED_WINDOW
from mailweave_harness.evaluation.cases import resolve_against
from mailweave.surface.arguments import parse_search
from tests.fixtures.eval_dummy import dummy_arms, dummy_case_file, dummy_manifest, mailbox_of
m = dummy_manifest(); box, ver = mailbox_of(m); cf = dummy_case_file(m)
resolved = [resolve_against(c, manifest=m, report=ver) for c in cf.cases]
arms = {a.name: a for a in dummy_arms(m, box, traces=Path(tempfile.mkdtemp()))}
tot = Counter(); identical = 0; n = 0
for r in resolved:
    envs = {}
    for name in (FULL.name, FIXED_WINDOW.name):
        a = arms[name]; a.selector.reset()
        env = a.service.search(parse_search({"query": r.case.query}))
        fills = sum(1 for s in env.sources for row in s.messages if isinstance(row.reason, (QueryScoredFill, WindowOffset)))
        tot[(name, "select_calls")] += a.selector.select_calls
        tot[(name, "rows_admitted_by_selector")] += a.selector.rows_admitted
        tot[(name, "fill_rows_on_wire")] += fills
        envs[name] = [(row.id, row.depth.value) for s in env.sources for row in s.messages]
    n += 1; identical += envs[FULL.name] == envs[FIXED_WINDOW.name]
for k in sorted(tot): print(k, tot[k])
print(f"cases with identical message rows on full vs fixed-window: {identical}/{n}")
# build_arm twice on one service
from mailweave_harness.evaluation.arms import build_arm
a = arms[FULL.name]; again = build_arm(a.spec, a.service)
a.service.search(parse_search({"query": resolved[0].case.query}))
print("build_arm twice: outer select_calls", again.selector.select_calls, "| first arm's counter", a.selector.select_calls, "| nested:", type(again.selector._inner).__name__)
