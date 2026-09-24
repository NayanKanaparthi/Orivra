# Retrieval and graph feature freeze, and what the last live runs established (2026-09-23)

## The freeze

**Retrieval and graph feature work is frozen from 2026-09-23.** No new retrieval rungs, ranking
or disclosure behaviour, graph features, or evaluation campaigns start without a new, recorded
decision. What stays open during the freeze:

- defect fixes that a failing test or a preserved live run demonstrates, scoped to that defect;
- installation and onboarding work that changes no retrieval behaviour - the invite-only desktop
  beta (`docs/DESKTOP_BETA.md`) is the current deliverable;
- documentation.

The two open questions below stay open, and the freeze does not close them.

## Run 3 (2026-09-22/23): verified live results, as reported by the owner

Run under `docs/RETEST_2026-09-21.md`'s run 3 procedure, after `15fc262` put each row's
`attribution` and `internal_date` lines in the text the client reads. Answers, raw tool results
and diagnostics are preserved privately, outside the repository. The retest's two questions are
numbered as the retest numbers them; the campaign's numbers are in brackets.

- **Question 1 (campaign Question 2, the decision).** The decision and its reasoning are
  supported by the four messages the tools returned.
- **Question 2 (campaign Question 4, the two threads).** The ordering the answer stated was
  verified against the timestamps the text exposed, for the Sable threads and for the Maple
  threads: 23 seconds and 6 seconds apart respectively. `internal_date` is when Gmail received a
  message, so what these separations verify is the order of receipt; they say nothing further
  about when the messages were written. The run-3 review's other rows (the stated meaning of the
  stamps, attribution) are not marked here, because they were not reported.

## Recorded separately

- **A message read given a thread identifier was refused.** A `mailweave_get_messages` call made
  with a thread identifier where a message identifier belongs was refused. The 2026-09-21 repair
  makes a read of an identifier Gmail does not know final, and deliberately does not probe
  whether it was a thread; whether this refusal took exactly that path is for the preserved
  results to show, and is not asserted here. Recorded on its own, not as a finding about the
  answers above.
- **A separate `mailweave_thread_map` call failed, and it is not explained.** Its cause has not
  been established, and this record does not offer one. It stays an open question, beside
  run 1's 104-110 second calls (`docs/EXPLORATORY_RUNS_2026-09-21.md`), which are also still
  unexplained.

## What these runs do not establish

- **The graph's additional benefit.** Nothing here compares answers with and without the graph
  layer; the answers being supported says nothing about what the graph added.
- **M2 acceptance.** M2's acceptance is its registered criteria over its campaign
  (`docs/ORIVRA_V1_PLAN.md` §9). The exploratory runs and three retest runs over two questions
  in one mailbox are not that campaign, and no M2 criterion is marked by them.
- Anything about other mailboxes, other clients, other days, or speed.
