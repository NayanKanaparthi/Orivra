"""P5: a --traces root that already holds a trace (the CLI default is benchmarks/traces) feeds the previous run's pool to this run's first case."""
import tempfile
from pathlib import Path
from mailweave_harness.evaluation.arms import run_all
from mailweave_harness.evaluation.cases import resolve_against
from tests.fixtures.eval_dummy import dummy_arms, dummy_case_file, dummy_manifest, mailbox_of

m = dummy_manifest(); box, ver = mailbox_of(m); cf = dummy_case_file(m)
resolved = [resolve_against(c, manifest=m, report=ver) for c in cf.cases]
def pools(root, order):
    return {(r.case_id, r.arm): (r.pool_ids, r.pool_source) for r in run_all(dummy_arms(m, box, traces=root), order)}
clean = pools(Path(tempfile.mkdtemp()), resolved)
shared = Path(tempfile.mkdtemp())
pools(shared, list(reversed(resolved)))        # an earlier campaign into the same root
reused = pools(shared, resolved)
bad = [(k, sorted(clean[k][0] or []), sorted(reused[k][0] or [])) for k in clean if clean[k] != reused[k]]
print("runs whose pool differs from a clean root:", len(bad))
for k, a, b in bad: print(" ", k, "\n    clean :", a, "\n    reused:", b)
