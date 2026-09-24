"""P7: follow()'s state rule. A raised recovery call with evidence still out of hand is FAILED - unless ANY other
required message arrived, in which case it is MEASURED. Same for INCONCLUSIVE under a spent budget."""
import sys; sys.path.insert(0, "tests")
from test_r_m2_078_recovery_driver import _env, _row, FakeService, QUOTE
from mailweave_harness.evaluation.arms import follow
Q2 = "the second required span"
def case(carry_m1, raise_it=True, calls=32):
    first = _env(rows=[_row("m1", text=QUOTE if carry_m1 else None), _row("m2", text=None, unabridged=True)])
    svc = FakeService(raises={"m2": RuntimeError("boom")} if raise_it else {}, gets={"m2": _env(rows=[_row("m2", text=Q2)])})
    content = {"m1": QUOTE} if carry_m1 else {}
    reach, _ = follow(svc, first, required=frozenset({"m1","m2"}) if carry_m1 else frozenset({"m2"}),
                      first_content=content, quotes={"m1": QUOTE, "m2": Q2}, calls=calls)
    return reach
for label, kw in (("raise, m1 NOT in hand (only m2 required)", dict(carry_m1=False)),
                  ("raise, m1 in hand, m2 out           ", dict(carry_m1=True)),
                  ("budget 0, m1 NOT in hand          ", dict(carry_m1=False, raise_it=False, calls=0)),
                  ("budget 0, m1 in hand, m2 surfaced ", dict(carry_m1=True, raise_it=False, calls=0))):
    r = case(**kw)
    print(f"{label}: state={r.state.value:<12} after={sorted(r.after_expansion)} exceptions={list(r.exceptions)} stopped={r.stopped} surfaced_only={sorted(r.surfaced_only)}")
