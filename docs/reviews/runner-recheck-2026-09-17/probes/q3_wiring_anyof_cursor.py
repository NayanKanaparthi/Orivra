import io, contextlib, tempfile, os
from pathlib import Path
from types import SimpleNamespace as NS
from mailweave_harness.evaluation import __main__ as cli, arms as arms_mod
from mailweave_harness.evaluation.arms import CaseRun, Reach, FULL, NO_RERANK, FIXED_WINDOW, SEM_OFF, run_all
from mailweave_harness.evaluation.hypotheses import mean_cut_loss, position_spread, family_recall
from mailweave_harness.evaluation import report
from mailweave_harness.seed.metrics import Disclosure, Terminal

# RR-05: change H2's pair candidate, and add H4; which of table / evaluate follow?
calls = {}
real_eval = cli.evaluate
def spy(runs, **kw): calls.update(kw); return real_eval(runs, **kw)
cli.evaluate = spy
orig = cli.HYPOTHESIS_PAIRS
cli.HYPOTHESIS_PAIRS = {"H1": ("full","sem-off"), "H2": ("fixed-window","no-rerank"), "H3": ("full","fixed-window"), "H4": ("no-rerank","sem-off")}
buf = io.StringIO()
res = [NS(case=NS(case_id="x", evidence_cardinality="single", family="exact_lookup"), required={"m1": "q"}, any_of={})]
with contextlib.redirect_stdout(buf): cli._present([], res, out=None)
print("RR-05 table blocks:", [l for l in buf.getvalue().splitlines() if " vs " in l and not l.startswith(" ")])
print("RR-05 evaluate got candidate_arm =", calls.get("candidate_arm"), "(H2 pair now says fixed-window); H4 verdict printed:", "[H4]" in buf.getvalue())
cli.HYPOTHESIS_PAIRS = orig; cli.evaluate = real_eval

# RR-12: any_of beyond family_recall
Q = {"m-a": "alpha", "m-b": "beta"}
d = Disclosure(content_by_id={"m-a": "alpha"})
runs = [CaseRun(case_id=f"R{i}", family="ranking_stress", arm=a, terminal=Terminal.ANSWERED, disclosure=d,
                reach=Reach(first_response=frozenset({"m-a"})), pool_ids=frozenset({"m-a","m-b"})) for i in range(8) for a in (FULL.name, NO_RERANK.name)]
req = {f"R{i}": Q for i in range(8)}; anyof = {f"R{i}": Q for i in range(8)}
print("RR-12 family_recall with any_of:", family_recall(runs, family="ranking_stress", arm=FULL.name, required=req, any_of=anyof).mean_recall)
import inspect
print("RR-12 mean_cut_loss accepts any_of:", "any_of" in inspect.signature(mean_cut_loss).parameters, "| value:", mean_cut_loss(runs, family="ranking_stress", arm=FULL.name, required=req).value, "(any-of semantics: 0.0)")
print("RR-12 position_spread accepts any_of:", "any_of" in inspect.signature(position_spread).parameters)
print("RR-12 report.render/differences accept any_of:", "any_of" in inspect.signature(report.render).parameters, "any_of" in inspect.signature(report.differences).parameters)
txt = report.render(runs, required=req, candidate_arm=FULL.name, baseline_arm=NO_RERANK.name, isolates="x")
print("RR-12 report line:", [l.strip() for l in txt.splitlines() if "ranking_stress" in l])

# RR-13/09: sink file deleted mid-run
from mailweave_harness.evaluation.cases import resolve_against
from tests.fixtures.eval_dummy import dummy_arms, dummy_case_file, dummy_manifest, mailbox_of
m = dummy_manifest(); box, ver = mailbox_of(m); cf = dummy_case_file(m)
resolved = [resolve_against(c, manifest=m, report=ver) for c in cf.cases]
root = Path(tempfile.mkdtemp())
arm = next(a for a in dummy_arms(m, box, traces=root) if a.name == FULL.name)
clean = {r.case_id: r.pool_source for r in run_all([next(a for a in dummy_arms(m, box, traces=Path(tempfile.mkdtemp())) if a.name == FULL.name)], resolved)}
out = []
for i, r in enumerate(resolved):
    if i == 4: os.remove(arm.trace_sink.path)
    try:
        out.append(arms_mod.run_case(arm, r))
    except Exception as e:
        print(f"RR-13 sink deleted before case {i}: run_case raised {type(e).__name__}: {str(e)[:80]}"); break
changed = [(o.case_id, clean[o.case_id], o.pool_source) for o in out if clean[o.case_id] != o.pool_source]
print("RR-13 sink deleted mid-run: cases after deletion whose pool_source changed:", len(changed), changed[:2])

# RR-07: what still writes under the production state dir? (static)
src = inspect.getsource(cli._run)
print("RR-07 _run passes watermark/state to runtime.start:", "state" in src and "watermark" in src)
