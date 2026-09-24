# GMAIL_PREVIEW_DEMO.md — the read-only live-Gmail demonstration

**What this shows:** ask → inspect the actual relationships → expand one omitted branch →
inspect the updated graph, against a real mailbox, through the shipped tool surface.

**What it does not show:** that the graph makes retrieval better. `ORIVRA_V1_PLAN.md` §9a.4
prohibits that claim for this release and §8.2a is why — H4 is not decided in M3. What is
demonstrable here is that the graph is **correct, bounded and accounted for**.

**Read-only, and structurally so.** The server credential's only Gmail scope is
`gmail.readonly` (SEC-01, enforced at startup and swept by `tools/guards`). Every tool on the
surface is annotated read-only and the annotation is tested against the dispatch table. Nothing
in this document inserts, deletes, modifies, labels or sends. Nothing writes mail to disk.

---

## 0. Before you start

```bash
cd /absolute/path/to/mailweave
uv run mailweave doctor                                        # config, token store, credential mode
uv run mailweave auth login --client mailweave-server-oauth.json   # only if doctor says to
```

`doctor` must be clean before either path below. If it names a mode (`has mode 0644`),
`chmod 600` the file it names. `docs/SETUP.md` §7 is the full table of startup refusals.

---

## Path A — the scripted walk (four steps, one command)

This is the demonstration as a runnable artifact, so the steps cannot drift from the tools.

```bash
cd /absolute/path/to/mailweave
.venv/bin/python tools/dev/gmail_walk.py \
    --client mailweave-server-oauth.json \
    --query "<a question about a thread you know has more than one message>" \
    --view body_clean --rounds 2 \
  > walk.json
```

`.venv/bin/python` directly, **not** `uv run`: `uv run` syncs the environment before it runs,
and the point here is to exercise the environment as it stands. The three workspace packages
are editable installs pointing at this working tree, so this picks up the current code with
no install step and changes nothing.

`--view body_clean` matters: the four recognition gates read disclosed text, so at `snippet` or
`stub` no `obs.said.*` relation can be drawn and the record will say so rather than imply the
mailbox is silent.

**It writes no file itself** — redirect it. A file-writing path in code that holds the mailbox
credential is a path a later change could point at mail, which is what SEC-05's sweep refuses.

**What `walk.json` contains, step by step:**

| Key | What to look at |
|---|---|
| `step_1_ask` | `graph_built`, `counts.by_relation`, `counts.by_origin`, `routing` (why a graph was or was not built), `unresolved_links` |
| `step_2_inspect` | `edges.relations` — each one naming its two endpoints, its relation, its `origin`/`assertion` pair, its method and the source ids it rests on. **Not counts.** Plus `nodes` and `omissions` |
| `step_3_expand` | the handle followed, the tool and arguments it executed, the new `revision`, the nodes and edges added, `already_held`, `text_not_read`, `narrowed_by_live_check` |
| `step_4_inspect_again` | the same paged read after the merge, plus `gained` and `lost` as readable `a -relation-> b` lines |
| `gmail_calls` on each step | the `threads.get` and `history.list` calls **that step** made. Per step, not per round, because the answer's own thread read and the expansion's are different things and only the second has a cache seat |
| `rounds` (with `--rounds > 1`) | one row per round, carrying that round's expansion counts |

**What `--rounds 2` shows**

```
round 1: expansion made {'threads.get': 1}
round 2: expansion made {'history.list': 1}
```

Round 1's expansion read the thread. Round 2's read the **change feed** instead and served the
structure from the process cache, because the walk found nothing had touched that thread since
the revision the entry was written under. A round showing both calls means the walk saw a
change, or could not finish looking, and sent the call back to the source - which is the
correct outcome and not a cache failure. `docs/GMAIL_PREVIEW_CACHE.md` has the seat in full,
including what is deliberately **not** cached and why.

One round shows nothing about the cache: the cache lives for the life of the process and a
single round has nothing to reuse.

**Exit status is the thing to read first**

| | |
|---|---|
| `0` | it ran **and** the demonstration criteria were met |
| `2` | it ran, every call succeeded, and one or more criteria were **not** met. `criteria.unmet` names which |
| `1` | it could not complete: no graph routed, or the graph left nothing recoverable to follow |

A run that could not fail is not evidence. The first live Harbor run exited `0` on a graph that
disclosed no node, a delta that was silently shed, a cache that was never consulted and a
branch chosen by list order - so "every call succeeded" and "the thing was demonstrated" are
now two answers with two exit codes.

**The criteria, each answered yes or no in the record**

| Criterion | Asks |
|---|---|
| `graph_holds_evidence` | the answer's graph carries a message node, not only threads and people |
| `relations_visible_through_tools` | `orivra_graph` returned relations, not counts, with no resource read |
| `branch_chosen_by_relevance` | the branch followed was the answer's own best-ranked one, not list order |
| `expansion_delta_accounted` | the expansion carried its delta, or said it was shed and where to read it |
| `graph_grew` | the second inspection shows relations the first did not |
| `cache_consulted` | the structure cache was looked up at all, whatever it answered |
| `cache_behaved_correctly` | the cache was consulted, gave a defined outcome, and served an entry **only** on a conclusive unchanged walk |
| `reached_message_content` | the walk read the recovered messages' bodies, not only their structure |

**Path A grades four things and nothing else**: tool operation, graph expansion, content access
and cache behaviour. It does not grade answers. A scripted walk cannot read, this server makes
zero generative calls by construction, and a check that scored word overlap against the question
was briefly a criterion and was wrong - it failed a correct walk because a mail said "fixed"
where the question said "resolved". Whether the mailbox contains the answer is Path B's
question.

**Reuse is reported, never graded.** `observations.cache_reuse` says whether an entry was served
and on what reason. A fresh fetch after a change feed that saw a change, ran out of pages or
found a watermark Gmail no longer retains is the design working: the entry was not served
because nothing established that it could be. Only one cache outcome is a defect, and
`cache_behaved_correctly` is what catches it - an entry served on a walk that established
nothing. A safe fresh fetch is not a wrong answer.

**Informational, in `observations` and `step_5_content`:** `query_term_overlap` counts how many
of the question's longer words appear in the retrieved text, per term and per message. Every
term missing from a fourteen-message thread is a hint that the five rows read were the wrong
five. It is a hint to a reader and is graded by nothing.

**Branch selection, and why it is recorded**

`step_3_selection.rule` says which of three rules chose the branch:
`best_ranked_not_included` (the answer ranked this source and could not include it;
`not_included_sources` is written best-first), `partially_disclosed_thread` (the question
reached this thread and the handle recovers the rest), or `first_recoverable_fallback` - list
order, recorded as a fallback so a reader knows relevance did not choose it. No scoring is
introduced here: the rank is the retrieval's own, already disclosed.

**The four things worth checking by eye**

1. `step_2_inspect.edges.relations` is a list of relationships, not a number. That is the
   tools-first guarantee: a client with no MCP-resource support sees this much.
2. `by_origin_and_assertion` separates `observed/metadata`, `observed/source_stated` and
   `inferred/derived`. A `supersedes_stated` edge carries spans and **no** confidence; an
   `inf.*` edge carries a confidence and the basis for it. They never describe the same pair.
3. `step_3_expand.text_not_read` names the recovered rows whose bodies were not fetched. A
   thread map returns a branch's shape, not its text, so no `obs.said.*` edge is drawn for
   them — and the record says that rather than leaving a silence a reader would take for
   "nobody said anything".
4. `step_4_inspect_again.gained` is non-empty and `lost` is empty. A merge only adds; anything
   in `lost` is the **live access gate** narrowing disclosure between two reads, which is
   checked on every page rather than once per graph.

**Honest non-outcomes.** Exit status 1 with a `stopped` line means either the question routed
to no graph (the `routing` line says why) or the graph left nothing out that it can get back.
Neither is a failure of the demonstration; pick a question over a thread that is long enough
to be pruned, or lower `max_graph_nodes`.

---

## Path B — through a real MCP client

Path A drives `orivra.surface.server.call`, which is the same function the protocol drives, and
it answers a bounded question: do the tools operate, does the graph expand, is content
reachable, does the cache behave. **It cannot answer whether the mailbox contains the answer**,
because deciding that is reading and this server makes zero generative calls by construction.
Path B is where that question goes, and it is what MCP-07 asks for.

### 1. Point the client at the Orivra surface

Every path absolute — Claude Desktop does not apply `cwd`, and a bare `uv` is not on the PATH
the app launches with (`which uv` prints the first path below):

```json
{
  "mcpServers": {
    "orivra": {
      "command": "/absolute/path/to/uv",
      "args": [
        "run", "--directory", "/absolute/path/to/mailweave",
        "orivra", "serve",
        "--client", "/absolute/path/to/mailweave/mailweave-server-oauth.json"
      ]
    }
  }
}
```

**`uv run`, not the venv's console script.** Pointing `command` straight at
`.venv/bin/orivra` looks equivalent and is not: observed on 2026-09-18, the app-spawned
interpreter reached `site` initialisation and then failed to read the venv's own `pyvenv.cfg`
with `PermissionError: [Errno 1] Operation not permitted`, and the server never got past
`initialize`. The `uv run` form above was running the sibling `mailweave` entry on the same
machine, same repo, same venv, at the same moment, with no such error. Use the form that works.

**Prove the command before wiring it up.** In a terminal:

```bash
/Users/nayankanaparthi/.local/bin/uv run \
  --directory /Users/nayankanaparthi/Desktop/Nayan/MailWeave \
  orivra --version
```

It should print a version. If it does, the client is being handed a command that resolves, and
anything that then goes wrong is the client's launch context rather than the environment.

**Turn off a standalone `mailweave` entry while running Path B.** `orivra serve` already
publishes MailWeave's four tools, unchanged, from the same process. A second server publishing
`mailweave_search`, `mailweave_thread_map`, `mailweave_get_messages` and
`mailweave_get_attachment` collides with it on all four names, and a client that drops one side
of a collision will attribute calls to a server you are not demonstrating. One entry, eight
tools.

Restart the client. Eight tools appear and there are never more or fewer, because the list is a
compile-time constant: `mailweave_search`, `mailweave_thread_map`, `mailweave_get_messages`,
`mailweave_get_attachment`, `orivra_ask`, `orivra_sources`, `orivra_expand`, `orivra_graph`.
All eight are annotated read-only.

**If it still will not start**, the log is at
`~/Library/Logs/Claude/mcp-server-orivra.log`. `Using MCP server command:` names what was
actually launched, which is the first thing to check against the config above - the two
disagreeing is what produced the failure described here.

Confirm before prompting: the startup banner on stderr names the account, and it must be the
mailbox you intend. Nothing below writes, labels, trashes or sends — no such code path is
reachable from any tool (contract N-01) — so the run is safe to repeat.

### 2. The prompt

One prompt, pasted as-is. It names no thread, no message and no expected answer:

> Using only the Orivra and MailWeave tools available to you, answer this question about my
> mailbox: **what caused the Harbor export mismatch, and what exact fix resolved it?**
>
> Work it out from the tools rather than from what you already believe. Start with
> `orivra_ask`. Inspect what it built with `orivra_graph` — the tools only, never a resource,
> since a client with no resource support has to be able to do this. When a response says it
> left something out, the omission record carries the call that gets it back: follow the ones
> that matter with `orivra_expand`, and read bodies with `mailweave_get_messages` at
> `view: "body_clean"`.
>
> Two things to keep doing rather than stopping early. A thread map returns each message's
> place in the thread and not its text, so recovering a branch is not the same as reading it —
> if the rows you have are stubs, fetch their bodies. And do not stop at the first few messages
> of a thread: if the cause or the fix is not in what you have read, read more of it, in
> whatever order the evidence suggests rather than from the start. Respect the budgets and caps
> the responses declare; when one binds, say which and stop rather than working around it.
>
> Then give me exactly this:
>
> 1. **The cause**, in one or two sentences, with the Gmail message id of every message that
>    supports it.
> 2. **The exact fix**, the same way — what was actually changed, not "it was fixed", with the
>    message ids that state it.
> 3. **Where the evidence is thin.** If the messages do not state a cause, or say a fix landed
>    without saying what it was, say so plainly and name what you would need. An honest
>    "insufficient evidence, and here is what is missing" is the correct answer to a mailbox
>    that does not contain one, and is worth more to me than a confident guess.
> 4. **The call log**: every tool call you made, in order, with its arguments, and how many
>    messages you read in total.
>
> Quote a sentence only where you are citing it as evidence, and attribute every quote to its
> message id.

### 3. What to check in the reply

* **Citations resolve.** Every message id in the answer should appear in a
  `mailweave_get_messages` call in the log. An id in the answer that is in no call is an id
  the model did not read.
* **It went past the first few.** The call log should show more than one `get_messages`, or one
  with several ids, if the first read did not settle it.
* **It stopped for a declared reason.** If it stopped early, the reply should name the cap or
  budget that bound, and that name should match one in the responses.
* **Insufficient evidence is an acceptable outcome.** If the mailbox does not contain a stated
  cause and a stated fix, the correct reply says so. Treat a confident answer with thin
  citations as the worse result.
* **No writes.** The log should contain only the eight read-only tools.

### 4. What Path B does not settle

It is one question against one mailbox, run once. It is not a measurement of retrieval quality,
it is not comparable with anything, and it is not evidence for any claim about how well the
graph works — H1/H2/H3 remain deferred and §9a.4's prohibited list stands. What a good Path B
run shows is narrower and worth having: that a real client, over the protocol, can navigate
from a question to cited message text using only what the tools offer it.

## What a reviewer should be able to say afterwards

- Every node and edge named a source reference; none appeared without one.
- Observed, source-stated and inferred relations were distinguishable on their face.
- Every branch the budget dropped had a record and an executable handle, and following one
  extended the same graph rather than returning a detached thread map.
- Continuations were bound to a view, and a changed view was refused rather than honoured.
- Unresolvable links were reported as links, not fabricated as graph endpoints.
- No message text, token or secret appeared in the record.

## What is still not demonstrated by any of this

The cache seat above is **in-memory and per-process**. Plan §5.1's on-disk cached category is
not built, and `docs/GMAIL_PREVIEW_CACHE.md` §2.1 proposes deferring it to M4 rather than
marking the rubric row passed.

`ORIVRA_V1_PLAN.md` §9a.3 and §9a.5 hold the remaining release obligations. In particular this
demonstration is **not** GMAIL-01's live-mailbox smoke suite, not FRESH-01's freshness
protocol, and not MCP-07 unless Path B is the one that was run — and the comparative
acceptance (H1/H2/H3) remains deferred under
`docs/reviews/RELEASE_AMENDMENT_GMAIL_PREVIEW_2026-09-18.md`, unmet rather than passed.
