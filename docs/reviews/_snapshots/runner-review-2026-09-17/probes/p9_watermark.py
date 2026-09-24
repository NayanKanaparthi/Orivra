"""P9: runtime.start gives every arm the same settings.watermark_path. Interleaved arms share one watermark file,
so the LR rung's state on a case depends on which arm ran before it. eval_dummy's arms have no watermark at all."""
import tempfile
from pathlib import Path
from mailweave_harness.evaluation.arms import SPECS
from mailweave_harness.evaluation.cases import resolve_against
from mailweave.surface.arguments import parse_search
from tests.fixtures.eval_dummy import dummy_arms, dummy_case_file, dummy_manifest, mailbox_of
m = dummy_manifest(); box, ver = mailbox_of(m); cf = dummy_case_file(m)
resolved = [resolve_against(c, manifest=m, report=ver) for c in cf.cases]
def lr(env):
    rep = env.retrieval_report
    nt = [n for n in rep.not_tried if n.rung == "LR"]
    return ("not_tried:" + nt[0].why.value) if nt else ("ran" if "LR" in [str(getattr(r, "value", r)) for r in rep.rungs] else "absent")
for label, shared in (("dry-run arms (as shipped)", None), ("arms sharing one watermark file (as runtime.start builds them)", Path(tempfile.mkdtemp()) / "watermark.json")):
    arms = dummy_arms(m, box)
    if shared is not None:
        for a in arms: a.service.watermark_path = shared
    print("==", label)
    for r in resolved[:3]:
        row = []
        for a in arms:
            env = a.service.search(parse_search({"query": r.case.query}))
            row.append(f"{a.name}={lr(env)}/{env.retrieval_report.outcome.value}")
        print("  ", r.case.case_id, " | ".join(row))
