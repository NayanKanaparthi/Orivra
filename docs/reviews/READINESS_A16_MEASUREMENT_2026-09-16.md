# Readiness for the A16 real-model paired measurement

**2026-09-16, against `9a03eb4` + the A16 working tree.** Bounded, as asked: no campaign was
started, no model, budget, case or acceptance threshold was changed, nothing was reseeded, M3
is not begun. This says what was done to make the measurement path trustworthy, what is still
untrustworthy about it, and gives the one command.

---

## 1. The earlier records are preserved and qualified

Every figure counting what D.5 step (c)'s probe admitted was produced through
`SyntheticMailbox`, whose `_date_value` matched `YYYY/MM/DD` only. The server writes that probe
as `after:<epoch>` (A.6a rule 4); the double returned "cannot judge", and that is implemented as
**matching every message**. The probe therefore had no window in any run in this repository.

**Real models did not make the synthetic date filtering correct.** The models decide which pool
rows the shortlist selects and in what order; they do not decide whether the double filters by
date. So the real-model records at `07b9f9c` and `ba99c7a` carry the same defect as the
stand-in ones.

What survives is the **mechanism**: a pool probe's `messages.list` admits its whole result set
to `H` at L5, and A.9 then spends the evidence tier and the E2 floor on it. That is a reading of
the code and the contract. What does not survive is the **magnitude**: "334 to 462 ids" is a
windowless probe's result set. Re-measured under the corrected double the same mechanism leaves
three demoted ids inside mapped threads on DIAG-SEM-03, not hundreds.

A qualification block saying exactly this was added, without altering a word of the original
text, to: `DIAG_SEMANTIC_REGRESSION_2026-09-15.md`, `R_M2_101_102_INVESTIGATION_2026-09-15.md`,
`INTEGRATION_REPAIR_2026-09-15.md`, `M2_CHECKPOINT_2026-09-15.md`, ledger **R-M2-101**, and the
A16 amendment's "forced by" line. **No further work should be justified by the old number.**

## 2. A16's three claims, separated

Stated at the head of `docs/ARCHITECTURE_AMENDMENTS.md` §A16 and used consistently since:

1. **Contract rationale** — A.9's evidence tier is owed to what the query selected. An argument
   from A.7a, A.9(1), A.9(2), A.9(5) and D.5. **Nothing measured bears on it**, either way.
2. **Protection-narrowing** — the change the owner authorised. On a correct instrument its
   measured effect on a served response is **zero**: the ids it demotes are almost entirely in
   threads A.9(5) already withholds (R-M2-112).
3. **Shortlist-union correction** — a defect repair (R-M2-111) found by the second review, not
   part of the authorisation. **Every measured difference on a correct instrument is this.**

Claim 1 is not evidence for claim 2's value; claim 3's effect is not claim 2's.

## 3. B023 triage — bounded to the measurement path, and it is not a defect

**Reachability, counted rather than assumed.** All 38 `B023` are in
`harness/src/mailweave_harness/seed/families.py`, which both entry points reach through
`corpus.generate`. `evaluation/`, `acceptance/`, `preflight/`, `modelbench/`, `server/src`,
`orivra/src`, `tools/` and `tests/` have **zero**. So **no deferred callback binds an arm or a
case** — there are none in that code. The one diagnostic outside `harness/` is in a one-off
`benchmarks/diagnosis-4311/` script that is not an entry point.

**What the 38 are.** 38 variable references across **four** closures — `_redraw_f4`,
`_redraw_f11`, `_redraw_f12`, `_redraw_f17` — each defined inside a per-thread loop and each
used exactly once, as the `redraw=` argument of `redraw_until_ranked`, which calls it inside a
bounded loop and retains nothing. The hazard is real in principle: the cells they close over
belong to the *builder*, not the iteration, so a callback that ran later would rewrite a
different conversation's evidence and leave this one's family relationship unenforced.

**Demonstrated, not argued** (`tests/test_corpus_redraw_closure_binding.py`):

  * at the moment `redraw_until_ranked` receives a callback, the callback's own `__closure__`
    cell for `lines` **is** the `lines` that call is about, and every integer it closes over
    indexes inside that list;
  * the callback is guarded and never runs after that call returns;
  * the path is **forced** — `_ranks_ok` is made to fail once per thread — so all eight
    handovers run a real redraw, and each is checked to have rewritten its own thread by `Line`
    identity. This matters: at seed 4311 / profile `sample` the natural corpus fires only two
    redraws, both F4, so a test that waits for the corpus to exercise the path tests almost
    nothing and is seed-dependent besides.

**Verdict: no measurement-affecting defect, so nothing was fixed.** `harness/` is unchanged.
Replant **R259** reintroduces the mis-binding with one anchor and is caught by the forced test.
One citation was dropped after planting it: the finished-corpus rank check does not catch this
on its own at seed 4311, and a citation that does not catch is worse than no citation. Recorded
as ledger **R-M2-114**. The tidy end state — a `per-file-ignores` entry for `B023` in
`families.py` citing that test — is a config change and is left to you.

## 4. R-M2-113 — the embedding failure that refuses instead of falling back

**This is a product correctness issue, it predates A16, and it is deliberately not repaired
here.**

**Reproduction** (`tests/test_r_m2_113_semantic_unavailable_fallback.py`, 30 corpus-independent
lines; reproduced identically against `git archive HEAD`): a backend that loads and then raises
at `embed`, a forced L5, three recent threads matching no term. Result:

```
DispositionInvariantError: rungs ['L5'] admitted ids into H and are absent from the
retrieval report's `rungs`: a route that produced evidence and is not listed is a route
the reader cannot see (EV-01, PART-01)
```

**Mechanism — two correct rules meeting.** `SemanticRunner._build_pool` sends the pool's
`messages.list` probes at `RungId.L5`, so their ids enter `H` under L5 (A.7a; no repair may
undo that). `assemble._rungs_run` names L5 in `retrieval_report.rungs` only when
`semantic.state is SemanticState.RAN`, and an embed failure is `UNAVAILABLE`. The envelope
validator then finds a rung that admitted ids and is not listed, and refuses the response. D.5
promises a deterministic fallback here — `not_tried` with an `error` reason and the ladder's own
answer — and the caller gets no response at all instead.

**Smallest repair scope, stated and not taken.** A rung that sent probes and admitted ids *ran*;
the embed failure is an error **on a rung that ran**, not a reason it was never tried. So:
(a) `_rungs_run` names L5 whenever the ledger counted L5 hits, not only on `RAN`; and (b) the
failure is reported as an in-band `errors[]` entry rather than `not_tried[].why = error`. That
is a change to D.2's reporting vocabulary for one state. It touches no budget, no cap, nothing
in `H`, and nothing in A16 — which is exactly why it must not be absorbed into an amendment
about the evidence tier. The declared behaviour is an `xfail(strict=True)`: when the repair
lands, the marker says so.

`SemanticState.BLOCKED` reaches the same two rules by the `if not build.rows` branch. No
reproduction is claimed for it.

**This also bounds R-M2-109.** A16 stands down when the pool ran and produced no shortlist —
and that is the same path, which cannot emit a response at all today. Ungating A16 alone would
make it worse, not better. The two need one repair together, after this one.

## 5. A16's boundaries claim, reconciled

`A16_RECENCY_POOL_2026-09-15.md` §2a now states it exactly: **every boundary the owner drew is
held on the path A16 changes, and three pre-existing limits bound that path** — R-M2-106 (the
role rule still reads origins, so a row's role and its tier can disagree), R-M2-108
(`hit_threads` still decides *membership* on the first-admission origin, so "a lexical match
keeps its protection even if the probe returned it first" holds for probe-*listed*-first and not
probe-*read*-first), and R-M2-109/R-M2-113 above. None is introduced by A16; each has a ledger
row; one now has a reproduction.

## 6. The paired runner

`benchmarks/paired-a16-runner.py`. One script, two sides, one difference.

    pre  = <base ref>'s product  + the shared-instrumentation overlay
    post = this working tree     + the *same* overlay, byte for byte

**Shared instrumentation is an explicit, hashed list**, applied to both sides and refused if the
two copies disagree: `tests/fixtures/mailbox.py` (the corrected simulator — the first entry, and
the reason the list exists), the diagnostic runner, the case file, the trace script and the
stand-in wrapper. The manifest records that on `pre` the simulator was replaced
(`222e2fad…` → `edbb0d93…`) and on `post` it was already `same`. That line is the proof the
instrument fix applied equally.

**It never writes the checkout it reads.** `pre` comes from `git archive` and `post` from a copy;
no branch is switched, nothing is stashed, no virtualenv is created or synchronised, and every
subprocess runs under the interpreter the script was started with. `git` is called through a
read-only whitelist that refuses `checkout`, `add`, `commit` and anything else not in
`{rev-parse, describe, status, archive, log}` — verified by calling `_git("checkout", "main")`
and getting a refusal. `--work` is refused if it resolves inside the repository — verified.

**The manifest** (`manifest.json`) carries: run id and timestamp; interpreter, Python version,
platform; base ref and both commits, plus the working tree's dirty flag; a **product digest per
side** over `server/src`, `harness/src`, `orivra/src` (path-sensitive, sorted), with a refusal if
the two are equal — there would be nothing to pair; every overlay file's sha256 and what it
replaced on each side; corpus generator version, seed and profile; the case file's path, sha256,
schema version and its **13 answerable / 2 controls** split; `models.lock`'s sha256; the
**backend facts read out of the records** (model id, revision, device, runtime versions), with a
refusal if the two sides ran different backends; and the output file names. Each side is an
export rather than a checkout, so the per-side records carry `revision: unknown` by design and
the manifest is their provenance.

**The report keeps the quantities apart.** The 13 answerable cases are tabulated alone;
`required evidence complete` is the case's own required set, all of it. The 2 controls are a
separate table where the question is whether a control was answered anyway — a leak, not a
delivery. The first-response table reports `tier`, `tier present`, **`content rows`** (every row
the response carries, evidence or not) and `run members` (present, but not rows) as four
different columns.

### 6.1 Stand-in validation — it ran end to end

`benchmarks/paired-a16/standin-9a03eb4/`. Both sides, both driver modes, both traces.

| arm | required evidence complete (13) | calls | declines |
|---|---|---|---|
| `full`, listed | 9/13 → 9/13 | 338 → **333** | 9 → 9 |
| `full`, named | 11/13 → 11/13 | 318 → **317** | 9 → 9 |
| `sem-off`, both | 9/13 and 11/13, unchanged | 299 / 279, **unchanged** | 4 → 4 |

Controls: 0 answered on either side in every retrieval arm.

**`sem-off` being byte-identical across the pair is the pairing's own control** — a change that
moved it would be a change that is not A16's. Two first-response cases move and the rest do not:
DIAG-RANK-02 `full` (tier 15 → 39, run members 89 → 8, chars 24,159 → 21,806) and DIAG-SEM-03
`full` (tier 23 → 45, tier present 8 → 27, run members 181 → 94, chars 23,096 → 17,395).

**And the distinction the split makes visible:** `content rows` is **0** on thirteen of the
fourteen traced case/arms, on both sides. Every present message is a collapsed-run member. So
"tier present" and "rows delivered" are not the same quantity anywhere on this set, and a
delivery claim made from either alone would be wrong.

None of this is a result about the models. It establishes that the path runs, that the manifest
is complete, and that the pairing's control holds.

## 7. What is still untrustworthy, stated plainly

  * **The size of the problem A16 addresses is unestablished** (§1). It should be re-measured
    before more work is justified by it — the run below does that as a by-product.
  * **The stand-in is a weaker proxy here than it was for A15.** §5.2 of the A16 report shows the
    result turns on precisely which rows the shortlist selects, which is the one thing the
    stand-in does not decide as the models do.
  * **The pre-A16 real-model records cannot be the comparison.** They were produced under the
    uncorrected double. The run below re-runs *both* sides under the corrected one; do not read
    it against `…-ba99c7a` alone.
  * **R-M2-113 is unrepaired**, so any real-model run that hits an embed failure will refuse
    rather than fall back. It will not arise on a healthy load, and it is a hole in the path.
  * `make lint` / `make types` / `make format-check` remain red at HEAD (R-M2-107); untouched.

## 8. The command

On the laptop, in the MailWeave checkout, with the working tree as it is now:

```
python benchmarks/paired-a16-runner.py \
    --models-root ~/.local/share/mailweave/models --device cpu
```

It exports both sides to `~/a16-paired-work`, runs four campaign legs and two traces, and
writes `benchmarks/paired-a16/models-<commit>/` — `manifest.json`, the six records, and
`paired-report.md`. Roughly 20–40 minutes, dominated by model load and the walks.

Notes: `--base-ref <sha>` if the pre side should be something other than `HEAD`; `--only
post-named` to run one leg at a time; `--report` to rebuild the comparison from whatever has
finished. It needs `.venv/bin/python` only in the sense that whatever interpreter you start it
with is the one both sides use — **it will not create or synchronise one**, so start it with the
interpreter you already have. Nothing it does writes to the checkout except the output directory
under `benchmarks/`.

## 9. Housekeeping

Two zero-byte `git` index locks are sitting in `_to_delete/` at the repo root
(`git-index.lock`, `git-index.lock.2`). This sandbox cannot unlink files in the mounted folder,
so a `git status` that took the index lock could not release it, and a stale
`.git/index.lock` blocks the next `git add` or `git commit`. The lock is cleared now and the
runner passes `--no-optional-locks` so it cannot recur from here; the `_to_delete/` folder is
yours to remove.

## 10. Gates

Full offline suite **4,153 passed, 1 xfailed (R-M2-113's declared behaviour), 0 failed** across
105 files. Replants **R254–R259 CAUGHT**, every citation. `ruff` clean on every file touched;
`mypy` **73 errors in 21 files, identical to HEAD**, none from this work. The Mac `.venv` was not
touched and no `uv` or `make` target was invoked.
