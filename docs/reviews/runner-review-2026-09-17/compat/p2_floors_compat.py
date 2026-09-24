"""`p2_floors.py`, adapted to survive a repaired `mean_cut_loss`. **Not the reviewer's probe.**

The original is `../probes/p2_floors.py` and is unchanged, at its recorded sha256
`2b393daf6774dc9d0a842277aea30280465d161dc06e729b89720f296e3fe17d`. Run that one to reproduce
the finding; run this one to read the repaired behaviour.

**Why a second file rather than an edit.** The probe's last line does `round(cl.value, 3)`, and
RR-08's repair makes `cl.value` `None` when a per-case `cut_loss` is negative - so on a repaired
tree the original probe raises `TypeError` at that line, *after* printing the result the finding
is about. That raise is itself evidence the repair landed. An earlier pass edited the line in
place, which broke the probe's recorded hash and is exactly the kind of quiet change to
another party's evidence that makes a review unauditable (the recheck caught it as N-10). The
edit is here instead, under its own name, and the discrepancy is recorded in
`../../PROBE_INTEGRITY_2026-09-18.md`.

The only difference from the original is the final `print`.
"""

from __future__ import annotations

import runpy
import sys
import tempfile
from pathlib import Path

ORIGINAL = Path(__file__).resolve().parents[1] / "probes" / "p2_floors.py"
EXPECTED_SHA256 = "2b393daf6774dc9d0a842277aea30280465d161dc06e729b89720f296e3fe17d"


def main() -> int:
    import hashlib

    body = ORIGINAL.read_text(encoding="utf-8")
    seen = hashlib.sha256(body.encode()).hexdigest()
    if seen != EXPECTED_SHA256:
        print(f"REFUSING: {ORIGINAL} is {seen}, not the recorded {EXPECTED_SHA256}")
        return 2
    # The one adaptation, applied to a copy in memory. The file on disk is never touched.
    patched = body.replace(
        'round(cl.value,3), "cases", cl.cases)',
        'cl.value if cl.value is None else round(cl.value,3), "cases", cl.cases, "|", cl.note)',
    )
    if patched == body:  # pragma: no cover - the line moved; say so rather than run silently
        print("REFUSING: the line this adaptation patches is no longer in the probe")
        return 2
    # Written outside the repo, so nothing in the review directory is created or removed.
    with tempfile.TemporaryDirectory() as room:
        scratch = Path(room) / "p2_floors_adapted.py"
        scratch.write_text(patched, encoding="utf-8")
        runpy.run_path(str(scratch), run_name="__main__")
    return 0


if __name__ == "__main__":
    sys.exit(main())
