# Writing the M2 evaluation cases

You are writing the **questions and the expected answers** for a retrieval measurement. Nothing
else about the campaign is yours to invent: the families, their sizes, the distractor taxonomy,
the position discipline, the paraphrase tiers and the scoring rules are already specified in
`EVALUATION_PLAN.md`, and the three hypotheses and their falsifiers are already stated in
`ORIVRA_V1_PLAN.md` §8.2. This kit is the interface and the checker; the plan is the brief.

**Why the split exists.** The people who built the retrieval engine must not write the questions
it is measured on. An implementer writing the cases writes the exam it is sitting, and no amount
of care afterwards recovers from that. So: they hold the corpus generator, the schema, the joins,
the arms and the scoring; you hold the queries and the answers; and the case file does not go
into their repository at any point.

---

## What you have

| | |
|---|---|
| `README.md` | this file |
| `CASE_FILE_INTERFACE.txt` | the authoritative field list, printed from the code that enforces it |
| `validate.py` | the checker. Same refusals as the scoring run |
| `kit_schema/` | the repository's own schema modules, copied at export time (see `VERSION.txt`). Do not edit them. One line in `cases.py` imports from `mailweave_harness` under `if TYPE_CHECKING`, which never runs - you do not need that package and cannot get it |
| `FAMILIES.md` | the registered families and how many cases each needs per seed |
| `HYPOTHESES.md` | what the measurement is trying to falsify, so you know what a case is *for* |
| `manifest-gate-1042.json` | **the corpus.** Every thread, every message, every body, every date, and the answer key |

You return **one file**: `cases-1042.json`.

---

## The corpus

`manifest-gate-1042.json` is 40 threads, 2,248 messages, deterministic at generator version 1 and
master seed 1042. Each message carries its `thread_key`, its `position` in the thread (0-based),
its sender, recipients, subject, date and full body. The answer key holds thread lengths and the
sentinel tokens.

Read it as data, write queries against what it says. A message at
`thread:t007/pos:37` is the 38th message of thread `t007`, and that is the identity your case
refers to.

**`ref` is the portable identity, not `rfc_message_id`.** A ref survives regeneration: a new
master seed re-randomises names, dates and message ids while the *shape* - thread count, lengths,
the position grid - is drawn from a generator seeded without the master seed. A case pinned to a
position carries across seeds; a case pinned to an id does not. `rfc_message_id` is optional and,
where you give it, it is **checked** against what the manifest holds at that position: a
disagreement is a refusal, because a case written against a different corpus would score a
retrieval that never happened.

---

## Writing one case

Every field is specified in `CASE_FILE_INTERFACE.txt`. Three things about it are worth knowing
before you write a hundred of them.

**`expected_behavior.notes` is required and must be non-empty.** It states *what would make a
pass hollow* - the way this case could be passed by something that is not the behaviour under
test. "A full-thread dump also passes recall here; the discriminator is tokens plus partiality"
is the shape. A case that cannot say what a hollow pass looks like is refused at load, because a
gate reviewer reads exactly that line.

**The query must be answerable from the evidence you named, and from nothing else.** If a second
message in the corpus also answers it, the case measures something other than what it says.

**Distractors are part of the case, not scenery.** Name them with their type from the taxonomy;
they are what separates retrieval from luck.

## What makes a case worth having

The hypotheses are in `HYPOTHESES.md`. A case earns its place by being able to **discriminate** -
to come out differently depending on whether the mechanism under test works:

- an **F4** case where the query and the evidence share no content words is a test of semantic
  retrieval; one where they share the distinctive noun is a test of lexical search wearing an F4
  label, and it will pass on every arm and tell you nothing;
- an **F11** case needs a lexical decoy that a keyword match prefers and a semantic match does
  not;
- an **F16** case needs four to six near-duplicates where exactly one is the answer and the
  others differ in one decisive detail - that is what separates a ranking failure from a
  retrieval failure;
- an **F3** case is the same template at seven positions in a long thread; the measurement is the
  spread across positions, so all seven must exist or the sweep reports nothing;
- the **unanswerable controls** are load-bearing. A system that never says "not found" passes
  every other family by dumping the mailbox, and the controls are the only thing that catches it.
  Their evidence list is empty and `acceptable_not_found` is true.

## What to avoid

- **Do not write the query from the message's own words.** A query built by lightly rewording the
  evidence measures string overlap.
- **Do not make the answer depend on outside knowledge.** The corpus is the whole world.
- **Do not use the sentinel tokens in queries.** They are unique strings the seeder uses to check
  the mailbox settled; a query containing one has exactly one lexical match and tests nothing.
- **Do not tune a case after seeing a system's output.** If you see any, the case is spent.

---

## Checking your file

```
python validate.py cases-1042.json manifest-gate-1042.json
```

Needs Python 3.12+ and pydantic; no other install, no network, no credentials. Exit 0 means every
case loaded and every ref resolved. Exit 2 prints each refusal with its case id.

**Run it before you hand anything back.** These are the same refusals the scoring run applies -
the schema modules here are the repository's own files - so a file that passes here will not be
turned away later for a reason you could have seen now. It also reports where you are short of a
registered family count, which is not a refusal but does mean the run will report
`NOT_EVALUABLE` for the clauses that depend on that family.

What it cannot check, and nobody can check for you: whether the query is answerable **only** from
the evidence you named, and whether the expected answer is right.

---

## Handing it back

One file, `cases-1042.json`, by whatever channel you agreed. **Do not put it in the MailWeave
repository, and do not commit it anywhere that repository can read.** Do not send the queries or
the answers in a message, a ticket or a chat with the implementation team - the file itself,
once, to the person running the campaign.

If you regenerate against a different master seed, say so: the case file names the generator
version and the seed it was written against, and the run refuses a manifest that disagrees.
