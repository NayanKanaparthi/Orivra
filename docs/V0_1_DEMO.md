# MailWeave Gmail v0.1 — the demonstration, reproducibly

This is the procedure a second person follows to see what v0.1 does, on a Gmail account they
control, through a real MCP client. Everything it claims is checked by execution: the four
demonstrations below are the ones the owner ran live for acceptance; section 7 is the script
that records a run, and the acceptance record it writes is committed under
`validation-records/` beside the earlier diagnostic that reproduced the failure.

It builds on `docs/SETUP.md`, which is the installation and authorisation procedure and is not
repeated here.

---

## 1. Install

```sh
git clone <this repository> mailweave
cd mailweave
uv sync --all-packages --extra dev
uv run mailweave --version
```

## 2. Authorise, read-only

Follow `docs/SETUP.md` §2-§4. The only scope MailWeave requests is
`https://www.googleapis.com/auth/gmail.readonly`; the code refuses any other. Check:

```sh
uv run mailweave doctor
```

Every line must read `ok`. Use a mailbox you are content to point a model at; the owner's
acceptance runs used a dedicated test account, not a personal one.

## 3. Start the server

```sh
uv run mailweave serve --client /absolute/path/to/mailweave/mailweave-server-oauth.json
```

It speaks MCP over stdio and prints a one-line banner to stderr. It stays running; that is
what an MCP client expects. Stop it with Ctrl-C.

## 4. Connect it to Claude

Claude Desktop → Settings → Developer → Edit Config, and add the block from `docs/SETUP.md`
§5, with **every path absolute**. Restart Claude Desktop. The `mailweave` server shows as
connected with four read-only tools: `mailweave_search`, `mailweave_thread_map`,
`mailweave_get_messages`, `mailweave_get_attachment`.

A neutral connectivity check, before anything else: ask Claude to run **one**
`mailweave_search` for a single word you know appears in the mailbox, and to report the
status, the number of sources and messages, and the declared scope. That is the smoke test
the owner ran on 2026-09-07 (`docs/reviews/ROUND_28/`).

## 5. The four demonstrations

Each is run **through Claude**, against the live mailbox, and is accepted only if all of the
following hold: the essential answer is correct; the supporting message and thread ids are
identified; scope, provenance and incompleteness are reported truthfully; and the run
completes with no `-32603`, no manual timeout change, no unrecoverable decline and no retry
loop. `MAX_SERVER_MS` is the shipped 7,700 ms throughout (adopted 2026-09-09; the
first two attempts at 5.1 failed on the previous 2,000 ms).

### 5.1 The broad query that used to return bookkeeping and no mail (R-MCP-033)

Exactly the call that produced forty-five withheld records, zero rows and zero sources on
2026-09-08:

```
mailweave_search  {"query": "after:2026/09/01", "budget": {"max_hit_threads": 1}}
```

Expected: a served response (`is_error: false`) carrying at least one source with at least
one matched row, inside the 25,000-character host cap; `omission.withheld_messages` states
how many messages were not carried and `withheld_groups[]` names each thread they belong to
with an exact count and a `mailweave_thread_map` call; `omission.bound` names the ceiling that
bound **when a ceiling bound at all**, and is absent otherwise - the caps that withheld are
named exactly in `omission.withheld_by_cap` and in `retrieval_report.budget_caps_hit`, which
carry every per-query cap that was reached (round 30). If it declines instead, the decline carries `narrowing` and either a `retry_with` that
differs from the call or `terminal: true`; following `retry_with` reaches a served response
within four hops. Record the outcome with the one-call script in section 7.

### 5.2 A long thread

Ask Claude a question whose answer lives inside one long thread of the mailbox. Expected:
the thread arrives as one source, its total stated (`stated_total`), its members present as
rows or inside declared collapsed runs each carrying an expansion call, and the answering
message at `body_clean` or offered by the recommended `mailweave_get_messages` expansion.

### 5.3 A decision that was later reversed

Ask a question whose correct answer is the *later* of two messages that contradict each
other. Expected: both messages identified; the answer states the later one; if the earlier
one is not in the response it is named in `withheld[]` or reachable through a listed call.
The point is that the reversal is not silently flattened.

### 5.4 An answer spread across separate threads

Ask a question whose answer needs messages from two or more threads. Expected: each
contributing thread is a source (or, if capped, a `withheld_groups[]` entry with a map call),
the answer cites message ids from more than one thread, and `partial` is truthful.

For 5.2-5.4 the operator supplies the question. This document does not name one, and the
implementation was frozen before any evaluation answer was inspected; see section 8.

## 6. What you will see, and what it means

| field | what it tells you |
|---|---|
| `partial` | derived from the payload; `true` whenever anything was withheld, split off, or truncated |
| `withheld[]` | messages not carried, one record each, with the cap and a call that reaches the message |
| `withheld_groups[]` | messages not carried from a thread no map exists for: thread, cap, exact count, map call |
| `withheld_tail[]` | the threads beyond the 24 named groups under a cap, folded: cap, exact thread and message counts, the same search at the published width |
| `omission` | the counts as fields: `withheld_messages`, `withheld_by_cap`, `withheld_threads`, `not_included_sources`, and `bound` - the ceiling that forced the reduction, stated once, and absent when no ceiling did |
| `not_included_sources[]` | whole threads left out, grouped under one stated reason, each with its map call |
| `retrieval_report` | which rungs ran, which caps were hit - **every per-query cap that withheld content, width caps included** (AD A.7, D.11) - the scan scope, the Gmail request counts |
| a decline (`is_error: true`) | `code`, `remediation`, `retry_with`, `narrowing` (which dimension the retry reduces, from what to what), `terminal` |

## 7. Recording a run

For 5.1, and for any call worth keeping, this one-call script writes what the server returned
next to the earlier records. It passes no secrets, prints no tokens, and changes nothing:

```sh
uv run python - <<'PY'
import json, time
from pathlib import Path
from mailweave.envelope.measure import rendered_chars
from mailweave.surface.partition import rendered_of
from mailweave.surface.runtime import start
from mailweave.surface.server import call

ARGS = {"query": "after:2026/09/01", "budget": {"max_hit_threads": 1}}
runtime = start(client_path=Path("mailweave-server-oauth.json"))
try:
    began = time.monotonic()
    result = call(runtime.service, "mailweave_search", ARGS)
    wall_ms = int((time.monotonic() - began) * 1000)
finally:
    runtime.close()
p = result.structured_content or {}
sources = p.get("sources", ())
record = {
    "provenance": "R-MCP-033 acceptance, v0.1, after the round-29 fix. Same call as the failing diagnostic.",
    "arguments": ARGS, "declined": result.is_error, "search_wall_ms": wall_ms,
    "code": p.get("code"), "remediation": p.get("remediation"), "retry_with": p.get("retry_with"),
    "narrowing": p.get("narrowing"), "terminal": p.get("terminal"),
    "sources": len(sources),
    "matched_rows": sum(1 for s in sources for r in s.get("messages", ()) if r.get("role") == "matched"),
    "matched_ids": [(r["id"], s["thread_id"]) for s in sources for r in s.get("messages", ()) if r.get("role") == "matched"],
    "withheld_records": len(p.get("withheld", ())), "withheld_groups": len(p.get("withheld_groups", ())),
    "withheld_tail": p.get("withheld_tail"),
    "omission": p.get("omission"), "partial": p.get("partial"),
    "budget_caps_hit": (p.get("retrieval_report") or {}).get("budget_caps_hit"),
    "counters": (p.get("retrieval_report") or {}).get("counters"),
    "rendered_chars": None,
}
if not result.is_error:
    m = rendered_of(result); record["rendered_chars"] = rendered_chars(m.structured, m.text)
out = Path("validation-records"); out.mkdir(exist_ok=True)
(out / "rmcp033-acceptance-hit-threads-1.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
print(json.dumps(record, indent=2, sort_keys=True))
PY
```

Message and thread ids are opaque Gmail identifiers; no mail text is recorded.

## 8. Known limitations of v0.1

* **Depth is not query-aware.** Which messages get bodies is decided by rank and reply
  structure (A.9), not by which message best answers the question. N-1 is the tracked item.
* **Search is lexical.** Gmail's own operators and terms, with MailWeave's rung ladder over
  them. No semantic retrieval, no reranking.
* **A `body_full` body renders in both halves of the result**, so the largest message
  servable unabridged is roughly half the 25,000-character host cap. Larger bodies are offered
  as `body_clean` by the decline's `retry_with` (R-MCP-039).
* **A thread map of a very large thread at `segment: 0` may be all collapsed runs**: a true
  map skeleton with expansion calls, but no individual rows. Recorded for review; not a v0.1
  claim.
* **Very long threads (roughly 300 messages and up) bound what can be read from them.** A
  map of a ~450-message thread, and a single `body_clean` read of one message inside a
  ~300-message thread, decline as `budget_exhausted` with `terminal: true`: the accounting
  the response owes for the rest of the thread does not fit the host cap beside the message.
  The decline is declared and truthful - never `-32603`, never a silent cut - but there is no
  narrower call on offer. Notification and list threads of that size are where this is met.
* **Withholdings are summarised past 24 threads.** Under `max_hit_threads`, up to 24 capped
  threads are named with their own map call; beyond that they fold into one `withheld_tail`
  entry with exact thread and message counts and the same search at the published width. The
  counts in `omission` are exact whatever folds.
* **A decline's retry chain is bounded at 12 hops** (`MAX_RECOVERY_STEPS`; 7 until
  2026-09-15), each hop reducing one declared dimension (`max_hit_threads`, `view`,
  `message_ids`/`positions`, or a change of tool), never repeating a call; `terminal: true`
  means no smaller legal request exists. Since 2026-09-15 (A15) a search decline carries a
  `cause` and its retry is the widest `max_hit_threads` at which the ladder's own arithmetic
  fits the same search - in practice one hop - and the bound is what holds if that answer
  were ever wrong, one width per hop. The estimate that decides a decline errs high by
  design, so a long query under a budget cap can decline one hop before the wire strictly
  required it.
* **The shipped deadline is 7,700 ms, selected by the owner rather than by a passed
  validation.** Deadline run 3 measured 2,000 / 7,700 / 12,300 ms over three queries and three
  counterbalanced repeats; 2,000 returned zero evidence on every repeat of the acceptance
  query and 7,700 returned the same evidence on every one. The registered verdict is
  nonetheless `adoptable: false`, because the 12,300 ms reference arm took two
  `upstream_rate_limited` declines from Gmail during the run. Describe the figure as an
  operational default on repeat observations, never as validated
  (`validation-records/DEADLINE_DECISION.md`).
* **The text mirror names an affordance's tool and not its arguments.** Every `next call` line
  reads `next call mailweave_thread_map` or `next call mailweave_search` with no arguments. A
  map call can be reconstructed because the `withheld` line above it names the thread; a
  `mailweave_search` affordance cannot be reconstructed from the text half at all. The
  structured half always carries the full executable call, so a client reading
  `structured_content` is unaffected (R-MCP-042).
* **A broad query needs most of the 7,700 ms deadline.** Live acceptance 5.1 failed twice on
  the previous 2,000 ms, spending it on body fetches before it could afford the one
  `threads.get` a source requires
  (`validation-records/RMCP033-ACCEPTANCE-VERDICT-FAILED.md`,
  `docs/reviews/ROUND_30/ZERO_EVIDENCE_DIAGNOSIS.md`). At 7,700 ms the same call returns mail
  in about 6 seconds. A caller who lowers `budget.max_server_ms` on a broad query should expect
  the zero-evidence shape back.
* **Freshness, redacted traces, the remaining security work and the cross-source context
  graph are later workstreams**, not part of v0.1.

The implementation was frozen before any evaluation answer key was inspected. The eight
pilot questions were run by the owner in separate sessions with the key withheld.

**All four demonstrations were run and passed on 2026-09-10 at commit `ab72930`.** Results,
with the four observations they surfaced, are in `validation-records/V0_1_DEMO_RESULTS.md`.
The completion report is `docs/V0_1_COMPLETION.md`.
