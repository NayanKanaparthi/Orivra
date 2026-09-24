# User-task pilot — does this help a real person with real questions?

**Not an evaluation framework.** No corpus is generated, no case files are written, no metric
is added to the rubric, and nothing in `harness/` is touched. This is a procedure for running
five to ten of one person's own questions through two systems and recording what happened.

**Not a gate.** Source-publication readiness, safety verification and user-value evidence are
three separate decisions. This produces evidence for the third and says nothing about the
other two.

## What this can and cannot conclude

One mailbox, one owner, five to ten questions, one run each. It **can** show that a system
failed on a question a real person actually had, show where it failed, and show whether the
information was there to be found. A single clear failure is informative.

It **cannot** establish that either system is better in general, produce a win rate worth
quoting, or support any comparative claim in any material. With n < 10 and one judge, an
aggregate score is noise wearing a number. The output is a set of cases, not a percentage.

**Graph usage is not an outcome.** Whether Orivra built a graph, paged it, or reused a cache is
recorded as a mechanism note and never scored. A wrong answer reached through the graph is a
wrong answer. A right answer reached without it is a right answer.

## Roles

| Role | Who | Does |
|---|---|---|
| **Owner** | the person whose mailbox it is | writes the questions, seals them, judges the answers, establishes ground truth |
| **Operator** | whoever drives the sessions | runs both arms, preserves artifacts, times the runs. Never edits a question, never hints |
| **Judge** | ideally a second person | scores the answer packet without knowing which arm produced which answer |

If Owner, Operator and Judge are one person, blinding is not achievable and the result is a
structured self-report. That is still worth having. It is recorded as a self-report and not
described as blind.

## Arms

| | A | B |
|---|---|---|
| System | Orivra MCP server (`orivra serve`) over the real mailbox | the regular Gmail connector, whatever the owner would otherwise use |
| Model | **the same model in both**, named and recorded | same |
| Conversation | **fresh, empty, no prior context** | same |
| Question text | **verbatim, identical** | same |
| Effort cap | whichever comes first: 10 minutes wall clock, or 3 owner messages total (the question plus at most two follow-ups) | same |

Caps are a ceiling, not a target. A run that finishes in one turn finishes in one turn.

Only one MCP server is connected at a time. Arm A has Orivra connected and the Gmail connector
disconnected; arm B is the reverse. If both are visible to the model at once the comparison is
meaningless.

## Procedure

**1. Seal the questions.** The owner writes 5 to 10 questions in their own words, before seeing
any result from either system, and before this document's author sees them. For each question
the owner also records, at writing time:

- why they are asking, in one line;
- what a good answer would let them do;
- whether they already know the answer: `yes` / `partly` / `no`.

The sealed set is saved with a timestamp and is not edited afterwards. **The questions are not
written, suggested, reworded or "cleaned up" by Claude.** A question that is vague is data, not
a defect: vague questions are what people actually type.

**2. Randomise.** For each question, flip a coin for which arm runs first. Record the order.

**3. Run.** For each question, in each arm: fresh conversation, paste the question verbatim,
start the clock. The operator does not hint, does not rephrase, and does not name tools. If the
owner intervenes, that is allowed and is counted; the operator records the intervention text
verbatim.

Stop at the cap, or when the system produces an answer it presents as final, or when it
declines.

**4. Preserve.** Per question, per arm, into the private artifact folder:

- the full conversation transcript;
- the raw tool call inputs and outputs, unedited;
- wall-clock elapsed, number of assistant turns, number of owner interventions;
- any refusal, decline code or error, verbatim.

Nothing here is committed to the repository. See **Preservation** below.

**5. Build the judging packet.** The operator strips system names, tool names, accounting
blocks, handles and any other arm-identifying markup from the **final answer only**, and
presents the two answers per question in random order as "Answer 1" and "Answer 2".

Say plainly where this leaks: Orivra's answers carry a distinctive citation and accounting
style, and a judge familiar with both systems will often guess correctly. Blinding is partial.
The judge records, per question, whether they think they can tell which is which, before
scoring. That guess is itself a datum.

**6. Judge, before ground truth.** The judge scores each answer on:

| Dimension | Scale | Note |
|---|---|---|
| Task completion | did it do what was asked: `yes` / `partly` / `no` | not "was it a good answer" |
| Correctness | `correct` / `partly correct` / `wrong` / `cannot tell yet` | `cannot tell yet` is expected at this stage |
| Missing context | what a person would need that the answer did not give | free text |
| Citation support | `every claim traceable to a named message` / `some` / `none` / `citations present but wrong` | a citation that does not support the claim is worse than none |
| Usable as-is | `yes` / `no`, plus one line on what they would do next | |

Time and intervention count come from the operator's record, not the judge.

**7. Establish ground truth, after judging.** The owner then searches their own mailbox by hand
for each question and records what is actually there: message dates, senders, subjects or ids,
or the finding that nothing relevant exists. This happens **after** scoring so that the manual
search cannot tip which arm is which.

**8. Classify every miss.** For each question where an arm did not produce the right answer:

| Code | Meaning |
|---|---|
| **R1 retrieval failure** | the information exists in the mailbox and the arm did not surface it |
| **R2 genuinely absent** | the information is not in the mailbox. Neither arm can be faulted, and an arm that *said so* did better than one that answered anyway |
| **R3 surfaced but misread** | the right message was retrieved and the answer drawn from it was wrong |
| **R4 undetermined** | the owner could not establish what is there |

R1 and R3 are different defects with different fixes and must not be pooled. **R2 with a
confident answer is a fabrication and is the most serious single result this pilot can
produce**, in either arm.

## Prohibitions

- Claude does not write, suggest or edit the questions, and does not write expected answers.
- No change is made to retrieval, ranking, prompts, caps or defaults in response to what the
  pilot shows, until the pilot is closed and written up. Tuning against five questions is how
  a system learns five questions.
- No aggregate score, win rate or percentage is produced or quoted.
- Graph construction, pagination and cache reuse are mechanism notes, never outcomes.
- The pilot does not run twice with a fix in between and report the second run.

## Preservation

Everything the pilot produces is real mail content and stays private.

- Artifacts go to a folder **outside the repository**, for example `~/mailweave-pilot/`, so no
  `git add -A` can reach them. `benchmarks/` is gitignored but it is inside the working tree,
  which is a weaker guarantee than being nowhere near it.
- The only thing that may enter the repository is a written summary with **no message content,
  no subjects, no sender addresses and no question text** — the classification counts and the
  narrative of what failed.
- Whether even that summary is published is a separate decision, taken after reading it.

## What I need from you

Nothing below is something I can produce, and each one blocks the step it names.

1. **The sealed question set.** 5 to 10 questions in the owner's words, with the three
   metadata lines each. Send them when the runs are ready to start, not before.
2. **Who plays each role.** If you are Owner, Operator and Judge, say so and I will label the
   result a self-report throughout.
3. **Arm B, named exactly.** Which Gmail connector, in which client, at which version. "The
   regular Gmail connector" needs to become a specific thing for the record to mean anything.
4. **The model**, and confirmation that both arms use it.
5. **Confirmation of the effort caps**, or your own numbers in place of 10 minutes / 3 messages.
6. **The private artifact folder path**, and confirmation it is outside the repository.
7. **Permission to run read-only against the real mailbox.** Mailbox work is currently frozen;
   this pilot needs that frozen state lifted for arm A only, read-only, for the duration.
8. **Confirmation the owner will do the manual ground-truth pass** in step 7. Without it,
   every miss collapses into R4 and the pilot answers nothing.

Optional, and it materially improves the result: **a second person to judge**, so step 6 is
blind rather than self-reported.
