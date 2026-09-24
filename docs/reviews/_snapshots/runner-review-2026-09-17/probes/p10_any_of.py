"""P10: an any_of case whose one alternative is disclosed: the plan's metric says satisfied, the runner says half."""
from mailweave_harness.evaluation.arms import CaseRun, Reach, FULL
from mailweave_harness.evaluation.hypotheses import family_recall
from mailweave_harness.seed import metrics
from mailweave_harness.seed.metrics import Disclosure, Terminal
import inspect
fn = [n for n, f in vars(metrics).items() if callable(f) and "any_of" in (inspect.signature(f).parameters if inspect.isfunction(f) else {})]
print("metric functions accepting any_of:", fn)
req = {"m-a": "alpha span", "m-b": "beta span"}
d = Disclosure(content_by_id={"m-a": "alpha span"})
print("seed metric with any_of:", metrics.case_recall_strict(d, must_retrieve={}, any_of=req))
run = CaseRun(case_id="C", family="semantic_paraphrase", arm=FULL.name, terminal=Terminal.ANSWERED, disclosure=d,
              reach=Reach(first_response=frozenset({"m-a"}), after_expansion=frozenset({"m-a"})))
r = family_recall([run], family="semantic_paraphrase", arm=FULL.name, required={"C": req})
print("runner family_recall:", r.mean_recall, "strict", r.strict_rate)
