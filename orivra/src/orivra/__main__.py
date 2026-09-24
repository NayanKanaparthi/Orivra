"""`python -m orivra` - the level-2 equivalence run, against the real mailbox.

**Read-only, and it says so before it starts.** It uses the server credential, whose only
Gmail scope is `gmail.readonly`; it inserts nothing, deletes nothing and sends nothing. Each
query is asked twice - once through `orivra_ask {sources: [gmail]}` and once through
`mailweave_search` - and the two are compared by `orivra.equivalence`, which is the same
function the offline rehearsal in `tests/test_orivra_equivalence.py` exercises.

The record is the evidence for M1's level-2 claim, in the shape the deadline validation runs
already use: the inputs, the raw comparison and the verdict, emitted whether the verdict
passed or failed. A run that only reports its successes is not a record.

**It is printed to stdout and not written to disk.** `tools/guards`' unaudited-disk-write
sweep refuses a write from server code outside the credential store (SEC-05), and it is right
to: this module runs with the mailbox credential, and a file-writing path here is a path that
a later change could point at mail. Redirect it instead - `python -m orivra ... > record.json`
- which puts the decision about where evidence lands with the person running it.

**No message text is in the record**, and no handle, no signature and no fence nonce. The
comparison is over identities, counts, scopes and declarations, which is what is printed.

**The paired affordances are executed.** Each side's recovery calls are matched by
`(tool, subject)`, run, and compared by the evidence identities they recover - which is the
plan's level-2 requirement rather than the weaker "record the tool names" this runner did at
first. Every executed call is one of the four read-only `mailweave_*` tools; at most twelve
pairs per query; nothing an executed call itself offers is followed.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mailweave.envelope.vocab import ToolName
from mailweave.surface.runtime import announce, start
from orivra.contracts import OrivraToolName
from orivra.equivalence import (
    Comparison,
    Difference,
    compare,
    compare_affordances,
)
from orivra.registry import ConnectorRegistry
from orivra.surface.server import call
from orivra.surface.service import OrivraService

#: The four v0.1 demonstrations, as queries this runner can ask directly.
#:
#: They are the questions the demonstrations put to the mailbox, not the prompts a person
#: types into a client: this runner compares two server responses, and a prompt would be
#: compared through a model, which is a different experiment.
DEMONSTRATION_QUERIES: tuple[str, ...] = (
    "harbor export mismatch",
    "larch willow",
    "sable demo kits",
    "after:2026/09/01",
)


def _structured(result: Any) -> dict[str, Any]:
    payload = result.structured_content
    if not isinstance(payload, dict):
        raise SystemExit("a tool returned no structured content; nothing to compare")
    return payload


def run_one(service: OrivraService, query: str, *, view: str) -> tuple[Comparison, dict[str, Any]]:
    """One query, both paths, compared - plus the facts the record needs."""
    arguments = {"query": query, "view": view}
    through = _structured(call(service, OrivraToolName.ASK.value, dict(arguments)))
    direct = _structured(call(service, ToolName.SEARCH.value, dict(arguments)))
    container = through.get("gmail")
    if container is None:
        # **A divergence, not an equivalence** (review finding R-M1-007). This returned an
        # empty `Comparison`, which reads as `equivalent=True`, so the record that is M1's
        # own evidence reported success for a query where one path answered and the other
        # declined - the maximal divergence, scored as agreement.
        difference = Difference(
            field="answered",
            orivra="declined: no Gmail container in the response",
            mailweave=f"answered with {len(direct.get('sources', []))} source(s)",
        )
        comparison = Comparison(query=query, differences=(difference,))
        return comparison, {
            "query": query,
            "view": view,
            "equivalent": False,
            "differences": [difference.render()],
            "note": "orivra_ask returned no Gmail container",
        }
    comparison = compare(query, container, direct)

    # **The affordances are executed, not listed** (owner decision on the closure pass). The
    # plan's level-2 requirement is that following the Orivra affordance and the MailWeave
    # affordance reaches the same evidence; recording the tool names each side offered was a
    # weaker check than the plan asks for. Read-only, bounded, deterministic - see
    # `orivra.equivalence.compare_affordances`.
    def run(tool: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        return _structured(call(service, tool, dict(arguments)))

    paired = compare_affordances(container, direct, execute=run)
    unresolved = list(paired.unresolved)

    facts = {
        "query": query,
        "view": view,
        # **`paired.agreed` is a conjunction: every executed pair agreed AND nothing was
        # left unexecuted.** Reading only the first term is the silence this closure pass
        # removed.
        "equivalent": comparison.equivalent and paired.agreed,
        "differences": [one.render() for one in comparison.differences],
        "affordances": {
            # **Three counts, not one.** `executed` alone reads as completeness, which is
            # exactly the reading that let a thirteenth pair go unchecked while the query
            # reported equivalent.
            "total_pairs": paired.total_pairs,
            "executed_pairs": paired.executed_pairs,
            "unexecuted_pairs": paired.unexecuted_pairs,
            "agreed": paired.executed_pairs
            - len([one for one in unresolved if one.status != "unchecked"]),
            "complete": paired.complete,
            "unresolved": [one.render().strip() for one in unresolved],
        },
        "per_source": through.get("per_source"),
        "budget_binds": [
            stage["stage"]
            for stage in through.get("budget", {}).get("stages", [])
            if stage.get("limit_ms") is not None
        ],
    }
    if not paired.agreed:
        # An affordance that is missing, invalid, unexecutable or lands on different evidence
        # is a divergence in its own right: the retry contract is part of the answer, and two
        # responses that recovered the same evidence by routes only one of them offers have
        # not answered the same question in the same way.
        comparison = Comparison(
            query=query,
            differences=(
                *comparison.differences,
                Difference(
                    field="affordances",
                    orivra=(
                        f"{len(unresolved)} of {paired.total_pairs} pairs unresolved "
                        f"({paired.executed_pairs} executed, "
                        f"{paired.unexecuted_pairs} not executed)"
                    ),
                    mailweave="every pair executed and agreed",
                ),
            ),
        )
    return comparison, facts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m orivra",
        description=(
            "Level-2 equivalence: ask each query through orivra_ask and through "
            "mailweave_search and compare them semantically. Read-only."
        ),
    )
    parser.add_argument("--client", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--view", default="snippet", choices=["stub", "snippet", "body_clean"])
    parser.add_argument("--query", action="append", default=None)
    arguments = parser.parse_args(argv)

    queries = tuple(arguments.query) if arguments.query else DEMONSTRATION_QUERIES
    runtime = start(config_path=arguments.config, client_path=arguments.client)
    try:
        announce(runtime.report)
        service = OrivraService(registry=ConnectorRegistry.from_runtime(runtime))
        comparisons: list[Comparison] = []
        records: list[dict[str, Any]] = []
        for query in queries:
            comparison, facts = run_one(service, query, view=arguments.view)
            comparisons.append(comparison)
            records.append(facts)
            print(comparison.render(), file=sys.stderr)
            affordances = facts.get("affordances")
            if isinstance(affordances, dict):
                print(
                    f"      affordances: {affordances['agreed']}/"
                    f"{affordances['total_pairs']} pairs reached the same evidence "
                    f"({affordances['executed_pairs']} executed, "
                    f"{affordances['unexecuted_pairs']} not executed)",
                    file=sys.stderr,
                )
                for line in affordances["unresolved"]:
                    print(f"      {line}", file=sys.stderr)
    finally:
        runtime.close()

    diverged = [one for one in comparisons if not one.equivalent]
    record = {
        "kind": "orivra-level-2-equivalence",
        "recorded_at": datetime.now(UTC).isoformat(),
        "view": arguments.view,
        "queries": list(queries),
        "results": records,
        "verdict": "equivalent" if not diverged else "diverged",
        "diverged": [one.query for one in diverged],
    }
    # **stdout, never a file.** See the module docstring: a file-writing path in code that
    # holds the mailbox credential is a path a later change could point at mail, and the
    # guard that refuses it is one this repository added on purpose.
    print(json.dumps(record, indent=2, sort_keys=True))
    return 1 if diverged else 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
