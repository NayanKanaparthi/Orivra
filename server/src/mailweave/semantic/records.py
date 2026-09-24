"""Reading a preflight record from the server side, without importing the harness.

The harness writes `preflight-records/*.json`; the server reads them. The two must not
share a module: the harness holds the destructive scope literal and the CI sweep exists to
keep it out of server code (RR SEC-03). So this is a reader for a **file format**, not an
import of its producer.

That is a real hazard, not a stylistic one, and it caught this module while it was being
written: the first draft read `id` and `observed_at`. The producer writes **`probe`** and
**`recorded_at`**. Both keys would have been absent from every record on disk, every record
would have been skipped as malformed, and the server would have run the declared-assumed
fallback forever while a perfectly good measurement sat next to it. Nothing would have
failed; the profile would just have quietly said "assumed" for the rest of the project.

`test_the_reader_uses_the_key_names_the_producer_actually_writes` therefore derives the key
names from `ProbeResult.as_record()` itself and fails if this reader drifts from the
producer, the same move `test_the_exempt_set_is_the_producers_own_list_and_still_matches_it`
already makes for the prose-field table. A reader that restates a format is a copy that
stops matching; a reader that is *tested against* the format is not.

Three rules for what gets read:

  * **A record must name itself and its verdict.** No `probe`, or no `verdict`, and it is
    not a record.
  * **Only `pass` counts as measured.** `inconclusive` is explicitly "never a pass: an
    inconclusive preflight leaves the design commitment it guards unvalidated"
    (`preflight/spec.py`), and `observation_only` is raw numbers that OD-1 reserves from
    being a claim. Both read as *absent*, which lands on the declared-assumed branch.
  * **A malformed record is absent, not fatal.** A corrupt diagnostic artifact must not
    stop the server answering mail questions. It lands on the same fallback as no file, and
    the profile says the branch was assumed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

#: The keys this reader needs from the producer's record. Asserted against
#: `ProbeResult.as_record()` in the tests rather than trusted.
PROBE_ID_KEY: Final[str] = "probe"
VERDICT_KEY: Final[str] = "verdict"
FINDINGS_KEY: Final[str] = "findings"
#: Added by the writer rather than by `as_record`, so it is optional here.
RECORDED_AT_KEY: Final[str] = "recorded_at"

#: Verdicts meaning "this design commitment was checked and held". Mirrors
#: `preflight/spec.Verdict`, and the tests assert the two vocabularies have not drifted.
MEASURED_VERDICTS: Final[frozenset[str]] = frozenset({"pass"})

DEFAULT_RECORDS_DIR: Final[str] = "preflight-records"


@dataclass(frozen=True, slots=True)
class PreflightRecord:
    probe: str
    verdict: str
    recorded_at: str
    findings: dict[str, Any] = field(default_factory=dict)

    @property
    def is_measured(self) -> bool:
        return self.verdict in MEASURED_VERDICTS


def _coerce(payload: object) -> PreflightRecord | None:
    # Exact types, not `isinstance`: a dict subclass whose `get` returns nothing reads as
    # an empty record and would be skipped silently, and a `str` subclass can carry a
    # different `__str__` into whatever formats the verdict later. Same reasoning as
    # `preflight/record.py`'s R-SEC-055 fix, one layer down the pipe.
    if type(payload) is not dict:
        return None
    probe = payload.get(PROBE_ID_KEY)
    verdict = payload.get(VERDICT_KEY)
    if type(probe) is not str or not probe:
        return None
    if type(verdict) is not str or not verdict:
        return None
    recorded_at = payload.get(RECORDED_AT_KEY)
    findings = payload.get(FINDINGS_KEY)
    return PreflightRecord(
        probe=probe,
        verdict=verdict,
        recorded_at=recorded_at if type(recorded_at) is str else "unrecorded",
        findings=findings if type(findings) is dict else {},
    )


def load_records(directory: Path | str = DEFAULT_RECORDS_DIR) -> dict[str, PreflightRecord]:
    """Every readable record under `directory`, keyed by probe id.

    A file that does not parse, or parses to something without a probe id and a verdict, is
    skipped. That is not an error: the consequence of an absent record is already designed
    for, and it is declared in the profile rather than guessed around.
    """
    root = Path(directory)
    found: dict[str, PreflightRecord] = {}
    if not root.is_dir():
        return found
    for path in sorted(root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        # One record per file, or a batch in a list: the runner writes both shapes.
        entries = payload if type(payload) is list else [payload]
        for entry in entries:
            record = _coerce(entry)
            if record is not None:
                found.setdefault(record.probe, record)
    return found
