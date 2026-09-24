"""Recheck probes for the two adjudicated judgements and RR-01/02/03/04."""
from mailweave_harness.evaluation.arms import CaseRun, Reach, FULL, SEM_OFF, NO_RERANK, FIXED_WINDOW
from mailweave_harness.evaluation.hypotheses import evaluate
from mailweave_harness.seed.metrics import Disclosure, Terminal
Q = "span"
def run(case, fam, arm, got=True, *, embed=1, rerank=1, select=1, cost=None, order=("a","b"), pool=None, position=None):
    return CaseRun(case_id=case, family=fam, arm=arm, terminal=Terminal.ANSWERED,
                   disclosure=Disclosure(content_by_id={"m1": Q} if got else {}),
                   reach=Reach(first_response=frozenset({"m1"}) if got else frozenset(),
                               after_expansion=frozenset({"m1"}) if got else frozenset()),
                   embed_calls=embed, embed_texts=embed, rerank_calls=rerank, rerank_pairs=rerank,
                   select_calls=select, semantic_cost=cost, order=order, pool_ids=pool, position=position)
def ev(runs, ids, **kw):
    req = {i: {"m1": Q} for i in ids}
    out = {}
    for h in evaluate(runs, required=req, candidate_arm=FULL.name, semantic_baseline_arm=SEM_OFF.name,
                      selection_baseline_arm=FIXED_WINDOW.name, rerank_baseline_arm=NO_RERANK.name, **kw):
        out[h.id] = (h.verdict.value, {c.name: c.verdict.value for c in h.clauses}, {c.name: c.detail for c in h.clauses})
    return out

print("== J1a: F1 on a correct product (gate prohibits rerank on exact lookups, rerank=0), ordering unchanged, 10 F1 cases")
runs = [run(f"F1-{i}", "exact_lookup", a, rerank=0) for i in range(10) for a in (FULL.name, NO_RERANK.name)]
r = ev(runs, [f"F1-{i}" for i in range(10)]); print("  ", r["H2"][1]["F1-ordering-unchanged"], "|", r["H2"][2]["F1-ordering-unchanged"][:120])
print("== J1b: same, but ordering changed on 1 case (rerank=0 on F1)")
runs[1] = run("F1-0", "exact_lookup", NO_RERANK.name, rerank=0, order=("b","a"))
r = ev(runs, [f"F1-{i}" for i in range(10)]); print("  ", r["H2"][1]["F1-ordering-unchanged"])

print("== J2: selection 'ran' (select_calls>0) but arms identical; F17 at n=8, equal/above/below")
for label, base_got in (("equal", lambda i: i < 6), ("candidate above", lambda i: i < 4), ("candidate below", lambda i: i < 8)):
    runs = []
    for i in range(8):
        runs += [run(f"V{i}", "decision_reversal", FULL.name, i < 6, select=3), run(f"V{i}", "decision_reversal", FIXED_WINDOW.name, base_got(i), select=3)]
    r = ev(runs, [f"V{i}" for i in range(8)]); print(f"   {label:<16}", r["H3"][1]["F17-reversal-holds"], "H3:", r["H3"][0])

print("== RR-03/04 H1: backend never loaded (counter None on both arms), 12 F4 cases, identical recall")
runs = [run(f"P{i}", "semantic_paraphrase", a, i < 6, embed=None, rerank=None) for i in range(12) for a in (FULL.name, SEM_OFF.name)]
r = ev(runs, [f"P{i}" for i in range(12)]); print("   F4:", r["H1"][1]["F4-recall-rises"], "|", r["H1"][2]["F4-recall-rises"][:100])
print("== RR-03/04 H1: instrumented, embed=0 on every F4 case (L5 never ran), identical recall")
runs = [run(f"P{i}", "semantic_paraphrase", a, i < 6, embed=0, rerank=0) for i in range(12) for a in (FULL.name, SEM_OFF.name)]
r = ev(runs, [f"P{i}" for i in range(12)]); print("   F4:", r["H1"][1]["F4-recall-rises"])

print("== RR-03 cross-check: seam 0 embed, wire says 50 embedded texts (F1)")
runs = [run("F1-0", "exact_lookup", FULL.name, embed=0, rerank=0, cost={"embed_texts": 50, "rerank_pairs": 0, "escalated": 1})]
r = ev(runs, ["F1-0"]); print("  ", r["H1"][1]["no-embedding-on-F1-F2"], "|", r["H1"][2]["no-embedding-on-F1-F2"])
print("== RR-03 cross-check: wire semantic_cost None (not escalated) on every F1 case")
runs = [run("F1-0", "exact_lookup", FULL.name, embed=0, rerank=0, cost=None)]
r = ev(runs, ["F1-0"]); print("  ", r["H1"][1]["no-embedding-on-F1-F2"], "|", r["H1"][2]["no-embedding-on-F1-F2"])

print("== RR-04 partial instrumentation: 8 F16 cases, only 1 instrumented and reranked, 7 uninstrumented")
runs = []
for i in range(8):
    inst = dict(embed=1, rerank=1) if i == 0 else dict(embed=None, rerank=None)
    runs += [run(f"R{i}", "ranking_stress", FULL.name, i < 4, pool=frozenset({"m1"}), **inst),
             run(f"R{i}", "ranking_stress", NO_RERANK.name, i < 4, pool=frozenset({"m1"}), embed=1, rerank=0)]
r = ev(runs, [f"R{i}" for i in range(8)]); print("  ", r["H2"][1]["F16-cut-loss-falls"], "|", r["H2"][2]["F16-cut-loss-falls"][:90])
