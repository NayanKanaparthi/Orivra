"""Judgement 1: an existence falsifier needs no floor to FALSIFY. Does it need one to HOLD?"""
from mailweave_harness.evaluation.arms import CaseRun, Reach, FULL, SEM_OFF, NO_RERANK, FIXED_WINDOW
from mailweave_harness.evaluation.hypotheses import evaluate
from mailweave_harness.seed.metrics import Disclosure, Terminal
Q="span"
def run(case, fam, arm, got, embed):
    return CaseRun(case_id=case, family=fam, arm=arm, terminal=Terminal.ANSWERED,
        disclosure=Disclosure(content_by_id={"m1":Q} if got else {}),
        reach=Reach(first_response=frozenset({"m1"}) if got else frozenset()),
        embed_calls=embed, embed_texts=embed, rerank_calls=0, rerank_pairs=0, select_calls=1)
runs, ids = [], []
for fam, n in (("semantic_paraphrase", 12), ("semantic_lexical_trap", 10)):
    for i in range(n):
        cid=f"{fam}-{i}"; ids.append(cid)
        runs += [run(cid, fam, FULL.name, True, 1), run(cid, fam, SEM_OFF.name, i < n//2, None)]
runs.append(run("F1-only", "exact_lookup", FULL.name, True, 0)); ids.append("F1-only")   # ONE exact-lookup case, zero F2
h1 = evaluate(runs, required={i:{"m1":Q} for i in ids}, candidate_arm=FULL.name, semantic_baseline_arm=SEM_OFF.name,
              selection_baseline_arm=FIXED_WINDOW.name, rerank_baseline_arm=NO_RERANK.name)[0]
print("H1:", h1.verdict.value, {c.name: c.verdict.value for c in h1.clauses})
print("  ", [c.detail for c in h1.clauses if c.name == "no-embedding-on-F1-F2"][0])
