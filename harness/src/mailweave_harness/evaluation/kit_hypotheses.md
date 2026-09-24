# What the measurement is trying to falsify

Three hypotheses, stated in `ORIVRA_V1_PLAN.md` §8.2 with the conditions that falsify each. They
are here so you know what a case is *for*: a case that cannot come out differently depending on
whether the mechanism works is a case that will pass on every arm and decide nothing.

You are not writing cases to make these hold. `EVALUATION_PLAN.md` §7.1 pre-registers the
ablation, and a no-gain result is a publishable negative that removes machinery from the product.
A case file designed to produce a particular verdict is worthless in either direction.

---

### H1 — semantic escalation

> Semantic escalation recovers at least one class of evidence lexical retrieval misses, at zero
> cost on exact-lookup families.

**Falsified if** F4/F11 recall does not rise over the lexical arm, **or** embedding calls appear
on F1/F2 traces.

The cases that decide it are **F4** (`semantic_paraphrase`) and **F11**
(`semantic_lexical_trap`). An F4 case only tests semantic retrieval if the query and the evidence
share no content words - a shared distinctive noun makes it a lexical case wearing an F4 label.
An F11 case needs a decoy a keyword match prefers over the true evidence.

The second clause is measured from traces, not from cases: it checks that the cheap path stayed
cheap. Your F1 and F2 cases are what it runs on, so those must be genuinely exact-lookup shaped -
a message id, an exact phrase, a named sender and a date.

---

### H2 — bounded reranking

> Bounded reranking improves top-of-list precision on ambiguous families without changing
> exact-match families.

**Falsified if** F16 `cut_loss` does not fall, **or** F1 ordering changes, **or** F12 (the
semantic negative control) regresses.

`cut_loss` is the evidence that was retrieved and then lost at the ranking cut, and it is the
**only** thing that justifies an expensive reranker. It is measurable only on cases where the
pool genuinely contains near-duplicates: an **F16** case wants four to six candidates that are
maximally similar, exactly one of which is the answer, differing in one decisive detail - invoice
v1 through v5, four successive reschedules of the same meeting.

**F12** is the control that stops the answer being "escalate always": cases where the lexical
path is correct and a semantic detour would make it worse.

---

### H3 — query-aware disclosure

> Query-aware disclosure selects the answering message more often than position-based selection,
> without dropping the reply-chain floor.

**Falsified if** F3 position-flatness does not improve, **or** F17 reversal recall drops in the
query-aware arm.

**F3** (`buried_evidence`) is the position sweep: the same template with its evidence at each of
the seven normative positions in a long thread. The measurement is the *spread* across positions
- a system that always shows the newest messages scores well at the end of a thread and badly in
the middle - so a sweep missing positions measures nothing. All seven, or the family reports
nothing.

**F17** (`decision_reversal`) is the only test of the reply-chain floor: a decision made and then
reversed later in the same thread, where returning the first message and not the second is a
confident wrong answer rather than a miss.

---

## The families that are not about a hypothesis

They are not optional. **`unanswerable_control`** is what stops every other family being passed
by dumping the mailbox: a system that never says "not found" scores perfectly on recall and is
useless. Its cases name no evidence and set `acceptable_not_found` to true.

**F1** and **F2** are the non-regression families. They exist to catch the cost of everything
else: if the expensive machinery fires on an exact lookup, these are where it shows.
