"""P4: `_run`'s lazy counter pattern when the real backend declines to load. Mirrors __main__.py:344-384
line for line except runtime.start (credential) -> eval_dummy._service + the same warm call runtime.start makes."""
import tempfile
from pathlib import Path
from mailweave.semantic.interface import BackendRegistry, BackendUnavailable
from mailweave.disclosure import FixedWindow
from mailweave.trace.sink import TraceSink
from mailweave_harness.evaluation.arms import SPECS, Arm, CountingBackend, run_all, FULL, SEM_OFF, NO_RERANK, FIXED_WINDOW
from mailweave_harness.evaluation.cases import resolve_against
from mailweave_harness.evaluation.hypotheses import evaluate
from mailweave_harness.evaluation.observe import FetchLog
from tests.fixtures.eval_dummy import _service, dummy_case_file, dummy_manifest, mailbox_of

class _Declining:  # stands in for `REGISTRY` on a machine with no model weights
    def acquire(self): raise BackendUnavailable("no weights installed")
REAL = _Declining()

m = dummy_manifest(); box, ver = mailbox_of(m); cf = dummy_case_file(m)
resolved = [resolve_against(c, manifest=m, report=ver) for c in cf.cases]
root = Path(tempfile.mkdtemp())
arms, counters = [], {}
for spec in SPECS:
    registry = BackendRegistry()
    if spec.semantic:
        def factory(name: str = spec.name) -> CountingBackend:
            made = CountingBackend(REAL.acquire())
            counters[name] = made
            return made
        registry.register("counting", factory, default=True)
    log = FetchLog()
    service = _service(box, registry, selector=FixedWindow() if spec.fixed_window else None, log=log, cross_encoder=spec.cross_encoder)
    warmed = service.warm_semantic_backend()          # what runtime.start does, result discarded as there
    sink = TraceSink(root / spec.name); service.trace_sink = sink
    arms.append(Arm(spec=spec, service=service, counter=counters.get(spec.name), trace_sink=sink, fetch_log=log))
    print(f"{spec.name:<22} warmed={warmed!s:<5} counter={'None' if counters.get(spec.name) is None else 'attached'}")
runs = run_all(arms, resolved)
req = {r.case.case_id: dict(r.required) for r in resolved}
for h in evaluate(runs, required=req, candidate_arm=FULL.name, semantic_baseline_arm=SEM_OFF.name,
                  selection_baseline_arm=FIXED_WINDOW.name, rerank_baseline_arm=NO_RERANK.name):
    for c in h.clauses:
        if c.name in ("no-embedding-on-F1-F2", "F1-ordering-unchanged"): print(h.id, c.name, c.verdict.value, "|", c.detail)
same = all(a.order == b.order and a.reach == b.reach for a in runs if a.arm == FULL.name for b in runs if b.arm == SEM_OFF.name and b.case_id == a.case_id)
print("full identical to sem-off on every case:", same)
