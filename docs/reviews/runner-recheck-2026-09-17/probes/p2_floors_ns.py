"""P2: verdicts produced below REGISTERED_N through clauses that carry no floor; P3 masked negative cut_loss; P9 control aggregation."""
import io, contextlib
from types import SimpleNamespace as NS
from mailweave_harness.evaluation.arms import CaseRun, Reach, FULL, SEM_OFF, NO_RERANK, FIXED_WINDOW, Measured
from mailweave_harness.evaluation.hypotheses import evaluate, mean_cut_loss, recoverability
from mailweave_harness.evaluation import __main__ as cli
from mailweave_harness.seed.metrics import Disclosure, Terminal

Q = "the agreed figure is 41"
def run(case, fam, arm, *, got=True, order=("a","b"), embed=0, pool=None, position=None, content=None):
    c = {"m1": Q} if got else {}
    if content is not None: c = content
    return CaseRun(case_id=case, family=fam, arm=arm, terminal=Terminal.ANSWERED,
                   disclosure=Disclosure(content_by_id=c),
                   reach=Reach(first_response=frozenset({"m1"}) if got else frozenset(),
                               after_expansion=frozenset({"m1"}) if got else frozenset()),
                   order=order, embed_calls=embed, pool_ids=pool, position=position)
REQ = lambda ids: {i: {"m1": Q} for i in ids}

def show(title, runs, req):
    print("==", title, "| total cases:", len({r.case_id for r in runs}))
    for h in evaluate(runs, required=req, candidate_arm=FULL.name, semantic_baseline_arm=SEM_OFF.name,
                      selection_baseline_arm=FIXED_WINDOW.name, rerank_baseline_arm=NO_RERANK.name):
        print(f"  {h.id} -> {h.verdict.value}   " + "; ".join(f"{c.name}={c.verdict.value}" for c in h.clauses))

# (a) ONE F1 case whose ordering differs between full and no-rerank
runs = [run("F1-1","exact_lookup",FULL.name,order=("a","b")), run("F1-1","exact_lookup",NO_RERANK.name,order=("b","a"))]
show("(a) one F1 case, ordering differs", runs, REQ(["F1-1"]))
# through the CLI's own presentation path, to show the printed verdict and exit code
res = [NS(case=NS(case_id="F1-1", evidence_cardinality="single", family="exact_lookup"), required={"m1": Q}, any_of={})]
buf = io.StringIO()
with contextlib.redirect_stdout(buf): code = cli._present(runs, res, out=None)
print("  _present exit code:", code, "| printed:", [l for l in buf.getvalue().splitlines() if l.startswith("[H")])

# (b) ONE F1 case with one embedding call on full
show("(b) one F1 case, one embed call", [run("F1-1","exact_lookup",FULL.name,embed=1)], REQ(["F1-1"]))

# (c) TWO F3 cases at two positions (registered: 84)
runs = [run("F3-a","buried_evidence",FULL.name,got=True,position=2), run("F3-b","buried_evidence",FULL.name,got=False,position=99),
        run("F3-a","buried_evidence",FIXED_WINDOW.name,got=True,position=2), run("F3-b","buried_evidence",FIXED_WINDOW.name,got=True,position=99)]
show("(c) two F3 cases, two positions", runs, REQ(["F3-a","F3-b"]))

# (d) H2 HOLDS with F1 ordering on 1 case and F12 on 1 case (floors registered 10 and 10)
POOL = frozenset({"m1","d"})
runs = []
for i in range(8):
    runs += [run(f"R{i}","ranking_stress",FULL.name,pool=POOL,got=True), run(f"R{i}","ranking_stress",NO_RERANK.name,pool=POOL,got=(i<4))]
runs += [run("F1-1","exact_lookup",FULL.name), run("F1-1","exact_lookup",NO_RERANK.name)]
runs += [run("F12-1","semantic_negative_control",FULL.name), run("F12-1","semantic_negative_control",NO_RERANK.name)]
show("(d) H2 with 8 F16, 1 F1, 1 F12", runs, REQ([f"R{i}" for i in range(8)]+["F1-1","F12-1"]))

# P3: per-case negative cut_loss hidden by the mean
runs = [run(f"R{i}","ranking_stress",FULL.name,pool=frozenset({"m1"}),got=False) for i in range(7)]
runs.append(run("R7","ranking_stress",FULL.name,pool=frozenset({"other"}),got=True))  # disclosed evidence the pool lacks: loss -1
cl = mean_cut_loss(runs, family="ranking_stress", arm=FULL.name, required=REQ([f"R{i}" for i in range(8)]))
print("== P3 per-case losses: seven +1.0, one -1.0 (forbidden by the metric) ->", cl.state.value, cl.value if cl.value is None else round(cl.value,3), "cases", cl.cases, "|", cl.note)

# P9: recoverability over an arm that includes an unanswerable control
runs = [run("A1","exact_lookup",FULL.name), CaseRun(case_id="C1", family="unanswerable_control", arm=FULL.name,
        terminal=Terminal.ANSWERED, disclosure=Disclosure(content_by_id={}), reach=Reach(levels=5))]
print("== P9 recoverability with one control (answered, 5 levels):", recoverability(runs, arm=FULL.name))
