# M1 live acceptance — level-2 semantic equivalence

**Commit under test:** `91a2607`
**Date:** 2026-09-10
**Operator:** owner, on the development Mac
**Account:** `mailweave.test@gmail.com`, scope `gmail.readonly` only
**Command:** `uv sync && uv run python -m orivra --client mailweave-server-oauth.json --view snippet`

This record is the acceptance evidence for M1. It is an operator-run live check against real
Gmail, not a fixture. The runner is read-only, prints to stdout and writes no file; what follows
is the verdict it reported.

## Verdict

```
"verdict": "equivalent"
"diverged": []
```

All four demonstration queries returned `"equivalent": true` through both the legacy MailWeave
surface and the Orivra surface.

| Query | Equivalent | Affordance pairs | Executed | Unexecuted |
|---|---|---|---|---|
| `harbor export mismatch` | yes | 0 | 0 | 0 |
| `larch willow` | yes | 0 | 0 | 0 |
| `sable demo kits` | yes | 0 | 0 | 0 |
| `after:2026/09/01` | yes | 11 | 11 | 0 |

Zero unexecuted pairs and zero unresolved comparisons across the run.

## What the affordance result proves, and what it does not

**Proves.** The closure pass replaced name-matching with execution. On `after:2026/09/01` the
runner executed 11 paired recovery affordances and compared the evidence each pair recovered.
All 11 agreed. That establishes, for those pairs, that the offered call is valid, runnable, and
reaches the evidence it promised through both surfaces.

**Does not prove.** Three of the four queries offered zero affordance pairs, so paired execution
was exercised on one query only. This run surfaced 11 pairs, not the 13 observed previously, so
the fail-closed over-limit path (`MAX_PAIRED_AFFORDANCES = 12`) did **not** fire live. It is
covered by `test_a_report_with_unexecuted_pairs_never_reads_as_agreement` and by replant R173,
and by nothing else. Both limits are stated here rather than left for a reader to notice.

`MAX_PAIRED_AFFORDANCES` stays at 12. It was deliberately not raised: raising a bound so a live
run goes green is the patch-work this project forbids.

## Budget and caps

`budget_binds: []` on every query. No Orivra budget stage binds at M1, as designed; all eight
stages ship unmeasured with stated reasons, which is recorded as a deviation from plan §2.3.

`after:2026/09/01` hit `max_server_ms`, `disclosed_token_ceiling` and `max_hit_threads`, with 45
hits and 526 quota units consumed. `max_server_ms` is MailWeave's legacy 7,700 ms deadline on the
legacy Gmail path, which is where it belongs.

## Per-source honesty

`gmail`: `asked: true`.
`drive`: `asked: false`, reason `not_configured`.
`slack`: `asked: false`, reason `not_configured`.

An unconfigured connector reports that it was not asked. It does not report an empty result.

## Operational note

`uv sync` prunes the `dev` extra and uninstalled 14 packages including ruff, mypy, pytest and
hypothesis. `uv sync --extra dev` restores them before any local gate run. Nothing in the
repository changed as a result of the acceptance run.
