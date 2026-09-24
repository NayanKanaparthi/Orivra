"""P8: does the driver execute search affordances during expansion, and which trace record supplies pool_ids?"""
import tempfile, json
from pathlib import Path
from collections import Counter
from mailweave_harness.evaluation.arms import run_case, TraceCursor
from mailweave_harness.evaluation.cases import resolve_against
from tests.fixtures.eval_dummy import dummy_arms, dummy_case_file, dummy_manifest, mailbox_of
m = dummy_manifest(); box, ver = mailbox_of(m); cf = dummy_case_file(m)
resolved = [resolve_against(c, manifest=m, report=ver) for c in cf.cases]
arms = dummy_arms(m, box, traces=Path(tempfile.mkdtemp()))
for arm in arms:
    tools = Counter()
    for r in resolved:
        before = arm.trace_sink.path.stat().st_size if arm.trace_sink.path.exists() else 0
        run = run_case(arm, r)
        tools.update(run.reach.calls)
        lines = arm.trace_sink.path.read_text()[before:].splitlines()
        recs = [json.loads(l) for l in lines if l.strip()]
        withpool = [i for i, x in enumerate(recs) if (x.get("semantic") or {}).get("pool_ids")]
        if len(recs) > 1 and withpool and withpool[0] != 0:
            print(f"  {arm.name} {r.case.case_id}: pool came from record #{withpool[0]} of {len(recs)} (tool={recs[withpool[0]]['tool']})")
    print(arm.name, dict(tools))
