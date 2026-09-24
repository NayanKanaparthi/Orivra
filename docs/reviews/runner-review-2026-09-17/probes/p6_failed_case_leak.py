"""P6: a first search that raises leaves its network fetches in the arm's FetchLog; run_case's failure path never drains it,
so the NEXT case's lexical pool (EP 6.4 second clause) includes the failed case's fetches."""
import tempfile
from pathlib import Path
from mailweave_harness.evaluation.arms import run_case, SEM_OFF
from mailweave_harness.evaluation.cases import resolve_against
from tests.fixtures.eval_dummy import dummy_arms, dummy_case_file, dummy_manifest, mailbox_of

m = dummy_manifest(); box, ver = mailbox_of(m); cf = dummy_case_file(m)
resolved = [resolve_against(c, manifest=m, report=ver) for c in cf.cases]
a, b = resolved[0], resolved[3]
def arm():
    return next(x for x in dummy_arms(m, box, traces=Path(tempfile.mkdtemp())) if x.name == SEM_OFF.name)
clean = arm(); run_case(clean, a); want = run_case(clean, b)
faulty = arm(); real = faulty.service.search
calls = {"n": 0}
def search(req):
    calls["n"] += 1
    env = real(req)                                   # fetches happen, as they would before a late raise
    if calls["n"] == 1: raise RuntimeError("raised after fetching (simulated late failure)")
    return env
object.__setattr__(faulty.service, "search", search) if False else setattr(faulty.service, "search", search)
first = run_case(faulty, a); got = run_case(faulty, b)
print("case A state on faulty arm:", first.state.value, "|", first.declined)
print("case B pool, clean arm :", len(want.pool_ids or ()), want.pool_source)
print("case B pool, after fail:", len(got.pool_ids or ()), got.pool_source)
print("ids in B's pool that only A fetched:", len((got.pool_ids or frozenset()) - (want.pool_ids or frozenset())))
