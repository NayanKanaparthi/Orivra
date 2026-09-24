# Independent corpus review: package and brief

**For a reader who did not build this corpus.** The corpus is frozen as of 2026-09-17.
Generator repairs have stopped. Its content gate **fails**, on C1, and C4 - the independent
read - has never been attempted. You are C4.

**You are not being asked to fix anything.** Do not repair the corpus, do not propose generator
patches, and do not author the held-out acceptance questions. That authoring is a separate
commission that happens after this review, deliberately by someone else, so the person who
grades the corpus is not the person who wrote the questions it will be graded on. If you find
yourself drafting a question that could be used for acceptance, stop and describe the defect
instead.

The runner that will execute the campaign is reviewed separately and in parallel
(`RUNNER_REVIEW_PACKAGE_2026-09-16.md`). Neither review waits for the other.

---

## 1. The corpus you are reviewing, and how to be sure it is that one

| | |
|---|---|
| generator | version 3 |
| scored population | seed **4311**, profile **sample** - 1,756 messages, 76 conversations, 41 of them scored |
| large profile | seed **5309**, profile **gate** - 12,102 messages, 339 conversations |
| identity record | `benchmarks/gate/corpus-freeze-round2.json` - digests of all ten generator modules and of each manifest |

```
export PYTHONPATH=server/src:harness/src:orivra/src:tests/fixtures:.

# regenerate and confirm nothing moved (exits non-zero if it did)
python tools/gate/freeze_corpus.py --check benchmarks/gate/corpus-freeze-round2.json

# write the corpus out in a readable form
python tools/gate/export_review.py --seed 4311 --profile sample \
       --out benchmarks/gate/review/sample-4311
```

**`benchmarks/` is gitignored, so none of these artefacts are in version control.** The freeze
record plus the two commands above are what make them reproducible; regenerate rather than
trusting a copy someone sent you.

**Which profile is the reviewed one, and why it is the small one.** The content gate's
population is the **sample** profile at seed 4311: 41 scored conversations. The **gate** profile
at seed 5309 is the one that builds the registered counts - 84 F3 conversations, 10 F1, and so
on, 339 in all - and the coverage rules are run against both. So the answer key below shows "F1:
registered 10, built here 2", which is the sample profile being a sample and not a shortfall;
`freeze_corpus.py` records both and `export_review.py --seed 5309 --profile gate` writes the
large one out if you want it (about 28 MB of thread files).

This split is itself worth your attention. **C1, C2 and C3 were measured on 41 conversations**,
eleven of the fourteen scored families contributing two each. Whether conclusions drawn there
carry to a corpus of 339 is not something the gate can tell you.

The export gives you three things:

* `answer-key.md` - every scored conversation: its declared answer, the positions the key points
  at, its competitors, and the note written for the case author. **This is the document to read
  first.**
* `threads/<id>.txt` - each conversation as plain mail in order, with each message's planted
  role shown. The roles are visible *because* checking them is your job; no reader of a mailbox
  would see them.
* `manifest.json` - the whole thing, if you would rather query it.

## 2. What the corpus is supposed to be

| | |
|---|---|
| registered families and counts | `harness/src/mailweave_harness/seed/families.py` - `REGISTERED_N`, `FAMILY_NAMES`, and each `build_fNN` docstring, which states what that family is registered to test |
| the requirements those come from | `docs/EVALUATION_PLAN.md` §4.3 (family definitions), §4.4 (thread shapes and the position grid), §4.5 (the paraphrase tiers), §4.6 (distractor kinds), §4.7 (what a new family must do) |
| the rules that check them | `harness/src/mailweave_harness/seed/coverage.py` - 34 rules, each with a negative fixture in `tests/test_coverage_rules.py` |
| what the rules currently say | `python -c "from mailweave_harness.seed.corpus import generate; from mailweave_harness.seed.coverage import render; print(render(generate(master_seed=4311, size_profile='sample')))"` - no rule finds a defect |

"No rule finds a defect" is worth exactly as much as the rules are worth. The previous version
of that file reported every family met and an independent reader found ten of them unauthorable.
That is the precedent this review exists because of.

## 3. The criteria, unchanged since before the repair

From `docs/reviews/CONTENT_GATE_FREEZE_2026-09-16.md`, hashed before any generator edit:

* **C1 - shape.** Every `(length, participants, senders, distinct hours)` value maps to at least
  two families.
* **C2 - no family solved outright.** The frozen query-free solver `qf-1` scores below 100% on
  every family with at least one scored thread.
* **C3 - bounded residual.** `qf-1` scores at most 40% over the whole population.
* **C4 - the independent read returns YES.** Not computed anywhere. It is your judgement.

C3's 40% is a provisional engineering threshold with no power analysis behind it. `qf-1` is
handed **the correct conversation** and answers inside it, so its score is an upper bound on
register leakage given perfect retrieval, not a lower bound on anyone's difficulty.

## 4. Every round's result

| | C1 | C2 | C3 | verdict | file |
|---|---|---|---|---|---|
| round 0 baseline | FAIL, 41 of 45 shapes unique to a family | FAIL, 3 families at 100% | FAIL, 18/41 = 0.439 | FAIL | `benchmarks/gate/content-gate-round0-baseline.json` |
| round 1 | FAIL, 41 of 44 | PASS | PASS, 10/41 = 0.244 | FAIL | `…/content-gate-round1.json` |
| round 1b | FAIL | PASS | PASS, 12/41 = 0.293 | FAIL | `…/content-gate-round1b.json` |
| round 2 (frozen) | FAIL, 36 of 41 | PASS | PASS, 10/41 = 0.244 | FAIL | `…/content-gate-round2.json` |

Six-seed means, because n=41 on one seed is not a measurement: `qf-1` 0.354 → 0.232, families at
100% 0.75 → 0.17.

Regenerate any of them: `python tools/gate/content_gate.py --seed <seed>`. The gate and solver
hashes are printed in every result file and are identical across all four.

## 5. Everything that is known to be wrong or unproven

Read `CORPUS_REPAIR_ROUND2_RESULT_2026-09-16.md` in full; §5 is the limitations list and §4 and
§6 carry corrections made on 2026-09-17. In short:

1. **C1 fails and the argument that it is unsatisfiable is the implementer's**, not an
   established impossibility. Question 4 below is exactly this.
2. **C2 is fragile at n=2.** Eleven of fourteen scored families have two threads. At a 0.23 base
   rate, about a 40% chance that some family scores 2/2 by luck.
3. **The 40% ceiling has no power analysis.**
4. **`qf-1` still scores 0.232** with the conversation handed to it. The residual is not zero
   and is not expected to reach zero.
5. **Two coverage rules were revised mid-repair by the implementer** - a methodology revision,
   §6 of the result report. Every superseded definition is preserved and runnable in
   `tools/gate/superseded_rules.py`; on the frozen corpus they agree with the shipped versions
   except one finding from the version that was replaced for producing that class of finding.
   The intermediate corpora those revisions were judged against no longer exist.
6. **Two rules cannot see small effects**: the time-of-day rule ignores a role carried by fewer
   than ten conversations; the scaffolding rule ignores a sentence in fewer than three.
7. **F17's `construction_query` is a message body verbatim** (R-M2-121, open), so the check that
   a reinforcement outranks the reversal asks whether a sentence outranks its neighbours on its
   own text.
8. **Exact-shape information exceeds its shuffle baseline** after the repair (3.522 vs 3.405,
   p=0.001) - slightly more than before it. See the corrected §4.

## 6. The four questions

Answer these. Everything else is optional.

**Q1 - are the questions naturally answerable?** Take the scored conversations as mail. Would a
competent person with access to this mailbox, asked the question the `answer_note` describes,
find the answer and be confident in it? Name the ones where the answer is ambiguous, where two
readings are equally defensible, where the text is contorted, or where the conversation does not
read like mail people wrote.

**Q2 - is the ground truth correct?** For each scored conversation, does the declared answer
match what the text says? Do the declared competitors compete? Does the declared evidence
position hold the evidence? Are the notes accurate about their own conversations? This is the
question the previous independent read failed the corpus on, in ten families.

**Q3 - do the remaining shortcuts invalidate particular comparisons?** Not "is there a
shortcut" - there is, `qf-1` scores 0.232 and the report says so. The question is **which
comparisons it makes uninterpretable.** If a family can be solved without the mechanism it is
registered to test, a result on that family measures something else. Name the families and the
hypotheses affected, and say whether the whole campaign, part of it, or none of it is
compromised.

**Q4 - does C1 measure a meaningful risk?** C1 requires every content-free shape record
`(length, participants, senders, distinct hours)` to be shared by at least two families. Two
things to separate. Is the underlying risk real - can a Tier-1 redacted observable identify what
kind of case it is, and does that matter for what this corpus is for? And is C1 a sound way to
measure it, given that it uses an exact message count and 41 conversations? §4 of the result
report argues it is not; that argument was written by the party that failed the criterion and
you are free to reject it. `tools/gate/shape_diagnostics.py` reports an alternative measurement
and is not a gate.

## 7. How to report

Numbered findings, a severity, the exact evidence - thread id, position, the quoted text, the
command and its output - and why it matters. A finding you can demonstrate beats one you can
argue. Findings go to `docs/reviews/FINDINGS_LEDGER.md`.

Then a verdict on **C4: YES or NO**, with the reasoning. A qualified YES ("yes for these
families, no for those") is more useful than either bare answer if that is what you find.

**A review that finds nothing is acceptable only if it shows what was tried.** Include that
section.

## 8. Out of scope

* the runner, its arms, its scoring and its verdicts - separate package, separate reviewer
* repairing the corpus, or proposing how to
* authoring the held-out acceptance questions
* changing C1, C2, C3 or the solver
* anything touching the mailbox
