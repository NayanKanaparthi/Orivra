# C4: independent read of the frozen corpus

**Verdict: C4 = NO.** A qualified YES holds for F1, F2, F5, F6 and for F3 as a position sweep. Every other scored family fails on at least one of Q1 to Q3 (table in §2). Nothing here repairs, patches or authors questions. Every number below comes from a command I ran on a regenerated corpus, and §6 lists what I tried that found nothing.

Reviewer: C4, commissioned by `CORPUS_REVIEW_PACKAGE_2026-09-17.md`. Date 2026-09-17. I did not treat anything the implementer wrote as a conclusion. I used the notes and docstrings only to find out what was *claimed*, then checked each claim against the text.

---

## 1. What I reviewed, and how I know it is the frozen corpus

* **Repo state.** HEAD `9a03eb42c0f9`, with uncommitted generator edits in the working tree. The corpus is defined by the working tree, not by HEAD, so the freeze digests are the only identity that counts.
* **Isolation.** I copied `server/ harness/ orivra/ tests/ tools/ docs/ pyproject.toml uv.lock` into a scratch directory outside the repo and ran `uv sync --frozen --no-dev` there, on Python 3.12.13. I did not touch the repo's `.venv`, the generator, the criteria or any record. The only writes to the repo are this report and `docs/reviews/c4-corpus-read-2026-09-17/`, which holds the evidence scripts as `.py.txt` so no lint or test gate collects them.
* **Freeze check.** `python tools/gate/freeze_corpus.py --check benchmarks/gate/corpus-freeze-round2.json` printed `{"frozen": true}` and exited 0. The freeze record's sha256 is `6d121120…d666b`.
* **Export.** `python tools/gate/export_review.py --seed 4311 --profile sample --out review/sample-4311` produced 1,756 messages in 76 threads. `diff -rq` against the repo's existing `benchmarks/gate/review/sample-4311` found no differences.
* **Gate profile.** I serialised `generate(master_seed=5309, size_profile='gate').model_dump_json()` and its sha256 is `e2e3b885…d109d`, which equals the freeze record's `manifest_sha256`. So the gate-scale numbers below are on the frozen 12,102-message corpus.
* **Instruments.** `content_gate.py` sha256 is `3e08991c…8fcb` and `queryfree.py` is `afc77fcb…db68`, both matching the result files. Re-running the gate gives 10/41 = 0.2439, FAIL. The coverage render reports "No rule found a defect".
* **Reading.** I read in full the 41 scored conversations and the 8 unscored family threads (t0002, t0019, t0020, t0023, t0024, t0026, t0028, t0029, t0030) from the manifest, with the reply graph resolved to positions. For the seven F3 threads (91 to 95 messages) I read the evidence neighbourhood and every message carrying the answer, wrong or superseded value. Claims that could be counted, I counted on the gate profile.

---

## 2. Verdict per family

| family | Q1 answerable | Q2 ground truth | Q3 mechanism measurable | C4 |
|---|---|---|---|---|
| F1 exact_lookup | yes | yes (LOW: t0000 declares the evidence's own author as its "wrong" competitor) | yes | **YES** |
| F2 sender_date | yes (1 thread read closely) | yes | not scored by C2/C3 at all | **YES, provisional** |
| F3 buried_evidence | yes, though extra undeclared hearsay competitors appear | answer yes; notes misstate length and fraction (C4-12) | position flatness survives; the absolute score is register-leaked (C4-07) | **YES for H3 flatness only** |
| F4 semantic_paraphrase | **t0012 contestable** | older competitor absent | H1 F4 clause confounded (C4-08) | **NO** |
| F5 decision_evolution | yes (t0014's proposal is contorted) | yes | yes | **YES** |
| F6 participant_reasoning | yes | answer yes; t0015's note undercounts hearsay | yes | **YES** |
| F7 multi_thread | **no** | **the cross-thread dependence is not in the text** (C4-02) | no | **NO** |
| F8 attachment | **t0027 not decidable** | same-name copies are indistinguishable except by a hedge (C4-09) | filename marker (C4-09) | **NO** |
| F10 unanswerable_control | yes if matter-specific | note overclaims (C4-12) | not scored | **YES, provisional** |
| F11 semantic_lexical_trap | **t0032 contestable** (C4-04) | contestable | recall clause OK in principle | **NO on the frozen population** |
| F12 semantic_negative_control | yes | yes | recall only; answer-level is register-leaked | **YES for recall, NO for answer accuracy** |
| F13 temporal_structural | yes | note miscounts | **reply graph not needed in 6/8** (C4-06) | **NO** |
| F14 participant_graph | same-name half yes; changed-address half incoherent | **corpus contradicts the changed-address truth in 10 conversations** (C4-10) | partly | **NO for the changed-address shape** |
| F15 thread_structure_reality | yes | notes false about their own threads (C4-12) | qf-1 cannot win 4 of 8 by construction (C4-03) | **YES answerable, NO as scored** |
| F16 ranking_stress | yes | yes | **not a ranking case: the answer is stated outright** (C4-05) | **NO** |
| F17 decision_reversal | **low confidence without headers** (C4-11) | defensible only via invisible headers | **reversal wording alone finds it 8/8** (C4-06) | **NO** |

Across all families: **evidence positions and role layouts are identical at every seed** (C4-01). No per-family YES above holds across seeds, because the seed lever the plan relies on does not exist.

---

## 3. The four questions

### Q1: Are the questions naturally answerable by a competent reader?

For most families, only partly. A reader who has learned this corpus's register can usually pick the answer, because the answer is almost always the formal, entity-naming sentence (C4-07). That is not the same thing as natural answerability, and five conversations fail outright or rest on very low confidence:

* **t0032 (F11).** Evidence at 3 says "As agreed: Padstow stock is relocated to the Nettleby facility … **Parking it until we hear.**" Afterwards come "My note from a conversation with Morgan Reid says North Dock" (11), and "Priya Raman told me North Dock when I caught them" (25). Priya is the evidence author. "We are paying for two units while Padstow is split across both" appears four times after the evidence (8, 12, 26, 27). I cannot defend Nettleby with confidence.
* **t0012 (F4).** The decoy at 18 says "You ask Sanjay Iyer about the bonded warehouse." The evidence at 21 says "Escalation approval under the Linford agreement is authorised by Bea Lindqvist". Asking someone and countersigning are different roles, and nothing says the decoy is false. "Nobody knows who countersigns Linford when the signatory is away" follows the evidence at 26.
* **t0027/t0028 (F8).** The same sender (Yuki Hara) sends two files called `mowbray-schedule-v3.csv` on 13 Feb 2026, with the same line "Here is the Mowbray sheet as it stands". The *wrong* copy is the later one (13:00 against 11:00). The only thing separating them is "I have not pulled a fresh copy in a while", and that sentence also appears in unrelated filler (t0011:16, t0012:22).
* **t0049, t0050 (F17).** The reversals are "Reversing what I said about Pennant. It is Thorne." from Priya Raman, who said nothing about Pennant, and "We have moved on Ilminster. Larch is where it sits. Parking it until we hear." Neither names the matter being reversed. Gmail shows no In-Reply-To, and **0 of 12,102 messages quote anything**, so a human reading the mailbox cannot see what these reply to (C4-11).

**Does it read like mail people wrote?** No. The problems are systemic and measured (C4-13):

* 512 gate messages report a future date in the past tense ("That was on 30 September 2026", sent 15 Aug 2025).
* 233 give a past date as upcoming, including an evidence message: t0046:11 is sent 22 Nov 2026 and says "The Alder consignment **is scheduled for dispatch on 16 November 2026**".
* 22 are hearsay about the sender themself ("Pieter Vos told me 16", sent by Pieter Vos).
* 66 of 538 distractors open with a finality marker, e.g. t0014:12: "**Settled, and this is the version to quote.** Straw man for Verge: 18 September 2026".
* 124 announce "original below" and none carries an original.

### Q2: Is the ground truth correct?

The declared answers match the text in most conversations. The declared *structure* does not in several:

* **F7:** the key's dependency claim is unsupported (C4-02).
* **F14:** the corpus asserts the opposite of the changed-address truth in 10 other conversations (C4-10).
* **Notes** are wrong about their own threads in F3, F6, F10, F13 and F15 (C4-12).
* **Competitors** that do not compete: t0000's wrong value is the evidence's author, and t0012's superseded 'Priya Raman' occurs nowhere in its thread. At gate scale, 6 of 12 F7 halves declare a wrong value absent from their conversation (C4-14).

I found no thread where the declared evidence position fails to hold the declared answer.

### Q3: Which comparisons do the shortcuts make uninterpretable?

* **All multi-seed claims.** Layouts are seed-invariant (C4-01). The six-seed means (0.354 → 0.232) and any "second fresh seed reproduces" check re-measure surface text over one fixed geometry. A content-free lookup trained on seed 777 places the answer exactly in 97 of 200 gate threads at seed 5309.
* **C2 and C3 as evidence about leakage.** qf-1 structurally cannot win 17 of 41 threads (C4-03). Over the 24 it can, it scores **10/24 = 0.417, above the 40% line**. F8, F11 and F17 pass C2 vacuously.
* **H2, the whole hypothesis.** The F16 `cut_loss` clause is uninterpretable because the confirmation states the answer outright (8/8 at gate), so no near-duplicate ranking is required (C4-05). A hypothesis with an uninterpretable clause cannot HOLD. The F12 clause is interpretable for recall only.
* **H1, partly.** The F4 clause is confounded: in 6 of 12 gate F4 cases the evidence is a direct reply to the lexical trap, and in 7 of 12 it sits within two positions (C4-08). A reply-chain or neighbour window reaches it without semantics. The F11 clause is interpretable in principle, but its sample population includes t0032.
* **H3, partly.** F3 flatness survives: the register leak is the same at every position, so the contrast still measures position. The F17 clause does not measure the reply-chain floor alone, because reversal wording plus the entity name finds the reversal in 8/8 (C4-06).
* **F13 comparisons.** A date filter from the question plus qf-1's own negative cues finds the evidence in 6/8 with no reply graph (C4-06).
* **Answer-level scoring anywhere in F3/F4/F11/F12.** "Trust the sentence that names the entity formally" is right 116/116 at gate (C4-07).

**Scope of compromise: part of the campaign, and more than half of it.** H2 cannot be evaluated. H1 and H3 each keep one interpretable clause. Every cross-seed statement is compromised.

### Q4: Does C1 measure a meaningful risk?

**The underlying risk is real.** Using only content-free shape:

* The leave-one-out nearest-length neighbour has the same family in 111 of 200 gate threads.
* It places the evidence at the exact position in 28 of 200, against 7.9 expected at random.
* Across seeds the risk is much larger (C4-01): 97 of 200 exact placements.

For a retrieval benchmark this matters. Thread length, position and participant count are features a product may legitimately use. A system or tuning loop can pick up "mid-length thread, answer near 80%" (F17 reversals sit at 76-90% in 8 of 8) without the mechanism a family registers.

**C1 is not a sound way to measure it.** I reject part of the implementer's argument and accept part:

* **I reject "cannot be met as written".** At the sample profile the only non-F3 long thread is t0045 (95|4|4|9). C1 is satisfiable by forcing all seven F3 threads onto that one tuple. So C1 is not impossible. It is satisfiable only by collapsing within-family variation, which is exactly the constant-per-family defect R-M2-070 repaired. That makes C1 a criterion that can pass while "95 messages → F3" stays about 7/8 predictive.
* **I accept that it is the wrong instrument, for five reasons of my own:**
  1. It ignores evidence position, which is the quantity that is actually exploitable. EP §2.4.1's shape record persists position too.
  2. It requires sharing between *families*, so a shape shared with filler still fails, even though filler is what a Tier-1 observer has to separate families from.
  3. It is computed once on 41 threads whose layout does not change with the seed, so it is a fixed property of the profile, not a sample.
  4. An exact count makes it a granularity statistic.
  5. It can be gamed by making shapes degenerate.

`shape_diagnostics.py` is closer, but it also ignores position. The measurement that matches the risk is cross-seed evidence-position predictability from content-free shape. I am not proposing it as a gate. That choice belongs to whoever re-registers criteria.

---

## 4. Findings

Severity follows `AGENT_LOOP.md` §4. Under "Must hold" I state the property that is missing, never how to build it.

### C4-01 · HIGH (possibly BLOCKER under EP §9 G3) · evidence positions and role layouts do not change with the seed

* **Location:** `harness/src/mailweave_harness/seed/corpus.py:142-150` (`_shape_rng` gets no master seed) and `families.py:75-80`. Against `docs/EVALUATION_PLAN.md:564`, which says a different master seed gives "re-randomized … evidence positions, distractor placement". Also `:681` ("randomized per seed") and `:1092` (G3: "evidence positions redrawn from the grid … Memorizing 'the answer is at position 37' … is worthless across runs by construction").
* **Reproduction:** `cross_seed.py.txt`.
* **Actual:**
  * Seeds 101 vs 4311 (sample): identical (family, evidence positions, full role layout) in 41/41.
  * Seeds 202 vs 4311: 41/41.
  * Seeds 777 vs 5309 (gate): 208/208.
  * A lookup keyed on (length, senders, participants) and trained on the other seed puts the answer at the exact position in 20/37, 23/37 and 97/200.
* **Why it matters:** R-M2-044 was closed by citing "EP §5.3 names [positions] as shape and requires [them] to hold". §5.3 of the current plan is about Tier-3 structural reproduction and says nothing of the kind, and line 564 says the reverse. The anti-memorisation lever G3 depends on is absent. Every multi-seed number in the repair report is one geometry measured six times.
* **Must hold:** what the plan says a new seed re-randomises actually re-randomises. Otherwise the plan is re-registered by its owner. An implementer's closing note does not settle it.

### C4-02 · HIGH · F7's two-halves dependence is not supported by the text

* **Location:** t0017/t0018, t0021/t0022, and gate F7.
* **Actual:**
  * t0018:6, the declared figure, reads "That puts Larch at 773 per consignment." It is a reply to t0018:5, "Larch inspection is relocated to the designated Dunmore facility with immediate contractual effect. That is the position." The anaphor "That" points at a decision in its own conversation, not at the declared decision "Contractual handover of Larch is recorded against 09 January 2027" in t0017.
  * t0017 itself also contains "We signed Dunmore for Larch" (5) and the Dunmore relocation (13, 14).
  * The same Larch relocation sentence appears in t0023:4 and t0024:5,7.
  * At gate, 11 of 12 F7 halves contain another settled statement about the same entity (`markers.py.txt`).
  * The declared wrong value '20 September 2025' for t0018 and 'Tarnbrook' for t0022 is absent from those threads.
* **Why it matters:** no reader can recover "the figure depends on the sibling's decision". The case is two independent lookups labelled `all_of`.
* **Must hold:** each half's text links it to the other half and to nothing in its own conversation.

### C4-03 · HIGH · C2/C3 pass partly because qf-1 cannot score 17 of 41 threads

* **Location:** `queryfree.py:78,127` (a candidate must match `_VALUE`, which requires digits or a date) and the gate population (4 F15 threads with empty `evidence_positions`).
* **Reproduction:** `cand.py.txt`.
* **Actual:**
  * 13 evidence messages carry no digit-bearing value (answers such as 'Tarlton', 'Pieter Vos', 'linford-schedule-v3.csv', 'It is Thorne'), and t0039, t0041, t0043 and t0045 can never be won.
  * Families where qf-1 cannot win *either* thread: F8, F11, F17.
  * Over the 24 winnable threads: **10/24 = 0.417**.
* **Why it matters:** C2's "no family at 100%" is vacuous for three families, and C3's margin depends on unwinnable denominators. This does not change the frozen verdict. It changes what a pass means.
* **Must hold:** a residual reported as evidence of low leakage is reported over threads the solver could win, with the unwinnable count beside it.
* **What I tried:** relaxing the value filter to names (probes A and B in `alt.py.txt`, written before running) made scores *worse*, 6/41 and 3/41. So I found no evidence that name-answer families leak through generic cues. The finding is about interpretation, not hidden leakage.

### C4-04 · HIGH · t0032's declared answer is contestable

* **Evidence:** as in Q1. Declared answer 'Nettleby' at 3 ("… Parking it until we hear."). Undeclared post-evidence reports put Padstow at North Dock (11, 25), one attributed to the evidence's author. "Split across both" appears at 8, 12, 26 and 27.
* **Why it matters:** one of F11's two scored threads carries ground truth a competent reader could reject. At gate, 0 of 10 F11 threads show the same-type hearsay pattern (`comp.py.txt`), so this may be local to the sample. But the sample is the graded population.

### C4-05 · HIGH · F16 does not isolate ranking

* **Location:** F16 builder; `answer_key` `evidence_positions` is (adopted, confirmation).
* **Reproduction:** `bypass.py.txt`.
* **Actual:**
  * At gate, the confirmation states the adopted figure in 8/8 ("91 went to signature on Jarrow; disregard the rest", "The adopted figure for Ilminster is 28"). It is the only adoption-worded message naming the entity in 6/8.
  * qf-1 won t0048 on that confirmation.
* **Why it matters:** retrieving one lexically distinctive sentence answers the case. Choosing among "maximally similar" revisions is optional. H2's F16 `cut_loss` clause therefore does not justify or refute a reranker. How `cut_loss` weights the two required messages is runner scope; I point it to the runner review.
* **Must hold:** answering an F16 case requires separating the near-duplicates.

### C4-06 · MEDIUM · F13 and F17 mechanisms can be bypassed

* **Reproduction:** `bypass.py.txt` on gate and sample.
* **F13:** the earliest post-event message that names the entity, carries a value and has no qf-1 negative cue is the evidence in **6/8** (gate) and 2/2 (sample). The event date comes from the question itself. The note's claim "Neither the dates nor the positions carry that; the References headers do" is false: the hedges on the stale entries carry it.
* **F17:** the newest reversal-worded message naming the entity is the answer in **8/8** (gate), and the only such message in 7/8. No reply graph and no query score are involved.
* **Why it matters:** F17 is registered as "the only test of the E2 reply-chain floor". A selector with any reversal-lexicon or recency-on-reversal feature passes it without the floor. Retrieval recall is affected only if the arm has such features. Answer-level scoring is affected in any case.

### C4-07 · MEDIUM · a register rule decides F3/F4/F11/F12 at the answer level

* **Reproduction:** `reg2.py.txt work/gate-5309.json`.
* **Actual:** in the sentence carrying the value, the evidence names the formal entity in 116/116. Every trap or paraphrase decoy in those families names only the colloquial alias in 116/116 (F3 trap 84, F4 12, F11 10, F12 10). Within a thread, a colloquial statement about the thread's own matter is always false.
* **Why it matters:** recall-based clauses are unaffected. Any answer-accuracy or "returned distractor" comparison on these families measures whether a reader learned the rule. F12's guard against always-escalating works only through budgeted selection, never through the answer.

### C4-08 · MEDIUM · F4 evidence is structurally adjacent to its lexical trap

* **Reproduction:** `adj.py.txt`.
* **Actual (gate):**
  * F4: the evidence is a direct reply to the trap in 6/12, and within two positions in 7/12.
  * F12: within two positions in 5/10.
  * F11: within two positions in 5/10.
  * Sample t0011: the evidence at 4 replies to the trap at 3.
* **Why it matters:** a lexical hit on the trap plus neighbour or reply-chain expansion discloses the evidence. H1's "F4 recall rises over the lexical arm" then depends on whether both arms carry that expansion. Either way the clause does not isolate semantic retrieval, and EP §4.3's F4 falsifier ("lexical-only recall already high") can fire because of layout.

### C4-09 · MEDIUM · F8's same-name copies are separable only by a hedge, and F8 files carry a unique marker

* **Reproduction:** `markers.py.txt`.
* **Actual:**
  * All 12 attachments named `*-v3.csv` belong to F8, out of 572. All 12 with rows dated 2026-02-01..04 belong to F8. Routine files draw days 10-27 (`chatter.py:175`).
  * In all 6 gate pairs, both copies carry identical `recorded` dates. The wrong copy is sent later in 2 of 6 (gilbey/jarrow/ulverton listing).
  * t0026's wrong copy (sent 26 Jan 2026) records rows dated 1-4 Feb 2026.
* **Why it matters:** "which file is current" is undecidable from the files themselves. The carrying message is found by filename, not by attachment signalling.

### C4-10 · MEDIUM · the corpus denies F14's changed-address identity, and F14's own timeline contradicts it

* **Actual:**
  * 11 messages in 10 sample conversations say Dana Okafor's two addresses are two people. Example, t0028:5: "Do not merge these: <dana.okafor@team.example> and <d.okafor@team.example> are both Dana Okafor, in procurement and procurement." Others: t0012:12, t0017:10, t0045:85, and more.
  * Cause: `chatter._duplicate_name` (`chatter.py:239`) picks from both duplicated display names, but its comment at `:302` assumes there is one.
  * In t0037, `d.okafor` sends at 0, 1 and 4, then announces "New address for me from today" at 11.
  * In t0038, `dana.okafor` still sends at 13, after `d.okafor` wrote "I have moved mailbox" at 10.
* **Must hold:** nothing in the mailbox contradicts an identity the key scores.

### C4-11 · MEDIUM · F17 and F13 are answerable only through headers a human mail reader cannot see

* **Actual:**
  * 0 of 12,102 messages contain quoted or forwarded content.
  * t0049's reversal comes from someone with no prior statement on the matter. t0050's reversal names no matter and ends "Parking it until we hear".
* **Why it matters:** Q1's standard, a competent person reading this as mail, is not met. The case is valid only for a machine reader of References headers, and that should be stated wherever F17 or F13 results are read as human-meaningful.

### C4-12 · MEDIUM · notes are inaccurate about their own conversations

The notes feed the question author, so errors here propagate.

* **t0039:** "announces the rename". No message announces a rename.
* **t0041 and t0043:** "Its last substantive message carries" the superseded value. That value sits at 11/19 and 9/16 respectively, and later substantive messages follow.
* **t0015:** "Two second-hand reports". There is a third, attributed to the author: "Sanjay Iyer said North Dock, though I am going from memory" (7).
* **t0035/t0036:** "four messages survive `date > event` and three of them are wrong". Three value-carrying messages survive, and two are wrong.
* **t0029:** "no … other agreed position on Padstow". The thread's own 22 and 24 say "Measured tolerance on Padstow exceeded specification at 8.2mm … That is the position."
* **F3:** "Position N of 90". Actual lengths are 91-96. The '99' fraction realises as 0.937-0.989 at gate.

### C4-13 · MEDIUM · systemic realism defects

* **Reproduction:** `nat.py.txt` (gate, all messages).
* **Actual:**
  * Past tense with a future date: 512.
  * Future tense with a past date: 233 (including evidence t0046:11).
  * Self-hearsay: 22.
  * Distractors opening with a finality marker: 66/538.
  * Answer messages closing on a hedge ("Will confirm once I have seen it in writing"): 35/230.
  * Later same-entity lines saying the matter is undecided: 51/200 scored threads ("Nobody knows who countersigns Linford" after the countersigner is named, t0012:26).
  * Undeclared hearsay reports of a value of the answer's type: 41/84 F3 threads.
* **Why it matters:** these are the reason Q1 fails as "mail people wrote". They also make date reasoning (F2, F5, F13) run on text whose own tenses contradict the send dates.

### C4-14 · LOW · declared competitors that do not compete

* t0000's `wrong_value` is 'Dana Okafor', the evidence's author.
* t0012's `older_value` 'Priya Raman' is absent from the thread.
* At gate, declared values absent from their own conversation: F7 wrong 6/12, F15 older 7/16, F3 older 4/84, and one each in F1, F4, F5 and F11. F8's 6/6 is by design, since the value is in the sibling.
* F16 t0048's `older_value` sits on the newest revision.
* **Why it matters:** any "returned distractor tokens" metric computed from these fields is noise.

---

## 5. Prepared ledger rows (not applied)

The package says findings go to `FINDINGS_LEDGER.md`, but my commission forbids modifying existing records. The orchestrator can paste these rows, or reject them, as they stand.

| ID | Severity | Summary | Status |
|---|---|---|---|
| R-C4-01 | HIGH | Evidence positions and role layouts identical across seeds (41/41, 208/208), contrary to EP :564/:1092; cross-seed shape lookup places 97/200 answers | OPEN |
| R-C4-02 | HIGH | F7 dependence absent from text; the figure's anaphor resolves to a same-thread decision (t0018:6 → :5); 11/12 halves | OPEN |
| R-C4-03 | HIGH | qf-1 cannot win 17/41; 10/24 = 0.417 over winnable; C2 vacuous for F8, F11, F17 | OPEN |
| R-C4-04 | HIGH | t0032 ground truth contestable | OPEN |
| R-C4-05 | HIGH | F16 confirmation states the answer (8/8); H2 F16 clause uninterpretable | OPEN |
| R-C4-06 | MEDIUM | F13 solvable without reply graph 6/8; F17 by reversal wording 8/8 | OPEN |
| R-C4-07 | MEDIUM | Formal-vs-colloquial register decides F3/F4/F11/F12 answers 116/116 | OPEN |
| R-C4-08 | MEDIUM | F4 evidence replies to its lexical trap 6/12; H1 F4 clause confounded | OPEN |
| R-C4-09 | MEDIUM | F8 `-v3.csv` and 2026-02-01..04 rows mark F8 files 12/572; copies separable only by hedge | OPEN |
| R-C4-10 | MEDIUM | 11 messages deny F14's changed-address identity; F14 address timelines incoherent | OPEN |
| R-C4-11 | MEDIUM | F13/F17 rely on headers invisible to a human mail reader; 0 quoted messages | OPEN |
| R-C4-12 | MEDIUM | Answer notes false about their own threads (F3, F6, F10, F13, F15) | OPEN |
| R-C4-13 | MEDIUM | Temporal and speaker incoherence at corpus scale | OPEN |
| R-C4-14 | LOW | Declared competitors absent or mis-typed | OPEN |

---

## 6. What was tried, including what found nothing

* **Freeze check, export diff, gate re-run, coverage render:** all matched the records (§1).
* **Answer string at evidence positions, all 41:** held in every thread. `occ.py.txt`.
* **Alternative query-free probes A and B**, fixed before running: 6/41 and 3/41, both below qf-1. I found **no** extra generic-cue leakage in name-answer families.
* **Undeclared filler hearsay attributed to the F6 author, gate:** 0/8. The t0015 instance is sample-local.
* **Same-entity *and* same-matter filler competitors, gate:** none that were real. Every hit turned out to be an entity name used as a value, so I dropped that line of attack.
* **F3 flatness under the register leak:** the leak is the same at all seven positions (84/84), so H3's F3 clause stays interpretable. This is the main reason F3 keeps a YES.
* **F13 reply chain as the note claims (4→3, 7→4, 8→7; objector = acceptor):** it holds in both sample threads. The finding is that the chain is not *needed*.
* **Freeze coverage:** the source digests plus both manifest digests are checked, so a module outside `SOURCES` could not move the frozen corpus unnoticed. No finding.
* **Not done:** I did not read the other 83 gate-profile conversations' full text beyond counted properties. I did not re-run the six-seed means. I did not evaluate the runner. I did not run the pytest suite, since that is outside a corpus read.

## 7. Uncertainty I want flagged

* Whether C4-01 is BLOCKER depends on whether G3 is a mandatory criterion. The plan's text is unambiguous. The ledger's R-M2-044 closure read it the other way, and a human has to settle which governs.
* C4-06 and C4-07 affect H1 to H3 only through features an arm actually has. I know the corpus side, not the arms.
* C4-04 and the t0012 part of Q1 are judgements. I would expect a second reader to agree on t0032 and could see one disagreeing on t0012.
* Every sample-level count sits on n=2 per family. The gate-profile counts are the ones to lean on.
