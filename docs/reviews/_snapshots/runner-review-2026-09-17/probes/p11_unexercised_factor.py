"""P11: a pair whose factor never executed (cross-encoder never called on `full`; no FILL row so fixed-window is
wire-identical) is scored as a null effect and FALSIFIES, although the runner holds the counter that says so."""
from mailweave_harness.evaluation.arms import CaseRun, Reach, FULL, SEM_OFF, NO_RERANK, FIXED_WINDOW
from mailweave_harness.evaluation.hypotheses import evaluate
from mailweave_harness.seed.metrics import Disclosure, Terminal
Q = "span"
def run(case, fam, arm, got, **kw):
    return CaseRun(case_id=case, family=fam, arm=arm, terminal=Terminal.ANSWERED,
                   disclosure=Disclosure(content_by_id={"m1": Q} if got else {}),
                   reach=Reach(first_response=frozenset({"m1"}) if got else frozenset()), **kw)
runs, req = [], {}
for i in range(8):   # F16: identical on both arms; the cross-encoder was called zero times on `full`
    for arm in (FULL.name, NO_RERANK.name):
        runs.append(run(f"R{i}", "ranking_stress", arm, i < 5, pool_ids=frozenset({"m1"}), rerank_calls=0, embed_calls=1))
    req[f"R{i}"] = {"m1": Q}
for i in range(8):   # F17: identical on both arms (no FILL row survived, so the selector never acted)
    for arm in (FULL.name, FIXED_WINDOW.name):
        runs.append(run(f"V{i}", "decision_reversal", arm, i < 6))
    req[f"V{i}"] = {"m1": Q}
print("rerank calls on full across F16:", sum(r.rerank_calls for r in runs if r.arm == FULL.name))
for h in evaluate(runs, required=req, candidate_arm=FULL.name, semantic_baseline_arm=SEM_OFF.name,
                  selection_baseline_arm=FIXED_WINDOW.name, rerank_baseline_arm=NO_RERANK.name):
    for c in h.clauses:
        if c.name in ("F16-cut-loss-falls", "F17-reversal-holds"): print(h.id, h.verdict.value, c.name, c.verdict.value, "|", c.detail[:90])
