> **DRAFT — not the published README.** Proposed replacement for the repository's `README.md`,
> which still describes round 1 and states that the Gmail client and the MCP tool surface are
> "deliberately absent". Nothing below is in force until the owner approves the swap. No
> licence is chosen here; see the licence section.

# Orivra for Gmail — preview

Two MCP servers in one repository. **MailWeave** reads a Gmail mailbox read-only and refuses to
hide what it dropped. **Orivra** sits on top of it and answers a question by building a graph
over the evidence, so a follow-up can navigate rather than re-search.

**Status: `0.2.0b1`, a preview.** It runs against a real mailbox and it has been used against
one. It has not been compared against any alternative, its retrieval quality has not been
measured, and several of its own safety claims are verified in code and not at runtime. Those
are itemised below rather than left for you to discover.

## What exists

| Server | Tools | Package |
|---|---|---|
| MailWeave | `mailweave_search`, `mailweave_thread_map`, `mailweave_get_messages`, `mailweave_get_attachment` | `mailweave 0.2.0b1` |
| Orivra | `orivra_ask`, `orivra_graph`, `orivra_expand`, `orivra_sources` | `orivra 0.2.0b1` |

Both tool lists are compile-time constants. Nothing an email author writes can add, remove or
rename a tool. Every tool is annotated read-only, and it is true: no tool here can send, draft,
delete, label or modify anything. `orivra_trace` is declared in the source and deliberately
**not** published, because it needs work that has not been done; a test asserts it never
reaches the tool list.

Three things are worth knowing before you read any result.

**Evidence that was dropped is named.** `mailweave.envelope.disposition` accumulates `H`, every
message id any executed retrieval stage returned, and at assembly time computes
`withheld := H − disclosed` as a set difference over the payload actually shipping. The
response cannot be certified if any id in that difference lacks a record naming the cap that
withheld it and an executable call that retrieves it. A cap that forgets to record a dropped
hit produces a loud failure during assembly rather than a quietly shorter answer.

**A response never silently exceeds a ceiling.** There are two, in two units: the disclosed
token ceiling MailWeave publishes, and the 25,000-character cap a host applies to a tool
result. Output is shortened to fit both, every reduction is declared in place with the call
that returns the unabridged form, and a response that cannot be brought inside is refused with
a code, a reason and a narrower call to make.

**Message text is untrusted data.** It arrives inside a per-response fence, labelled
`trust: untrusted_third_party`. It is evidence, never instructions, however it is phrased.

## Setup

Python 3.12+ and [uv](https://docs.astral.sh/uv/). You bring your own Google Cloud OAuth
client; there is no hosted service and no account to create with anyone but Google.

```bash
uv sync --all-packages --extra dev
uv run mailweave doctor          # checks config, token store and client-file permissions
```

`docs/SETUP.md` is the real instruction set: creating the OAuth client, writing the config,
authorising once, running the server, and connecting a client. Follow it rather than this
section.

Building and testing needs no credentials, no API keys and no network.

```bash
make check     # lint + types + offline tests + source guards + gate integrity
make test      # pytest, sockets denied
```

Every one of those is what CI runs. There is no CI-only step.

## What it does with your mail

- **One Gmail scope, `gmail.readonly`, fixed in code.** A configuration file that names a
  different scope is rejected; widening it takes a code change and a review.
- **A runtime egress allowlist of exactly two hosts**, `gmail.googleapis.com` and
  `oauth2.googleapis.com`, implemented as an httpx transport that refuses before a connection
  is attempted. A config file cannot add a third host.
- **No mail content is written to disk by any code path**, enforced by a CI source guard.
- **The token store is `0600` inside a `0700` directory**, with the mode set at open time; a
  read refuses an over-permissive file rather than repairing it.
- **Attachment bytes are never fetched or returned.** `mailweave_get_attachment` returns
  metadata only.
- **Ranking runs locally.** Two small models, pinned by revision and per-file SHA-256 with
  their licences recorded in `models.lock`. `mailweave setup-models` provisions them and is
  the only command in the repository that contacts a host outside the pair above.

## Limitations

- **One mailbox, one operator.** Everything known about how this behaves in practice comes
  from a single person using it on a single Gmail account.
- **No comparative evidence.** Nothing here has been run against another retrieval system on
  the same questions. Whether it is better than searching Gmail yourself is an open question,
  not a settled one.
- **No retrieval-quality measurement.** The registered acceptance work (H1/H2/H3) is unmet.
  It is unmet, not waived.
- **No persistent cache.** The structure cache lives for the life of a server process. A
  restart pays full cost again.
- **Latency figures are from synthetic rows.** `preflight-records/PF-4-model-latency.json`
  measures the local models on synthetic text of realistic length on one machine. It says
  nothing about retrieval quality and nothing about your machine.
- **Graph pagination is only partly exercised**, and cache reuse has never been demonstrated
  end to end.
- **`0.2.0b1` is a beta version number and means it.** Interfaces may change.

## What remains unverified

Stated separately from the limitations because these are claims the project makes about itself
that have not been checked the way the project's own plan says to check them.

- **Offline enforcement is verified in code, not at runtime.** The egress allowlist, the
  offline flags and the loader's refusal to reach for missing weights are covered by the
  offline suite, which denies `connect`, `connect_ex`, `create_connection` and `getaddrinfo`
  for every unmarked test. What has **not** been done is the plan's PF-5(b): the full suite
  cold-started behind an enforced network block. Two smaller runs exist and are recorded as
  *proxy-constrained smoke evidence* that closes no clause, because proxy environment
  variables constrain only clients that read them and are not an enforced boundary. Six items
  remain open and are listed in `docs/RELEASE_OWNER_ACTIONS.md` §7a. **Do not read anything
  here as "proven offline".**
- **The legacy-equivalence claim needs re-running.** Orivra's level-2 equivalence claim was
  amended when `orivra_ask` began allocating its container below the host cap. The live run
  that originally closed it tested the unamended claim.
- **The live demonstration is operator-reported and privately held.** One end-to-end Gmail
  workflow was completed in Claude Desktop and reported by the operator. No machine transcript
  was preserved, no independent verification was performed, and **the record is kept privately
  outside this repository** rather than published with it. `docs/GMAIL_PREVIEW_RELEASE_REPORT.md`
  describes its exact scope. Treat it as one person's report of one run, which is what it is.
- **The published OAuth client configurations in this repository's history are Desktop-app
  ("installed") client configs**: client id, client secret, project id and a loopback redirect.
  They contain no token, no grant and no mailbox data. An installed-app client is a public
  client by design and its secret is not confidential. They are reachable in history and have
  not been rotated. If you run this, create your own client; do not use those.

## Licence

**Not yet chosen.** Until a licence is added, default copyright applies and no permission to
use, copy, modify or distribute is granted. This is an open decision, not an oversight.

## Layout

```
server/            the MailWeave MCP server package (`mailweave`)
orivra/            the Orivra MCP server package (`orivra`)
harness/           the evaluation harness (`mailweave_harness`) — separate OAuth client,
                   separate scopes; the server never imports it and CI enforces that
tools/             repo tooling: CI source guards, rubric status, dev walkers
tests/             offline test suite; every fixture is synthetic
docs/              the governing documents; `docs/reviews/` holds the loop records
preflight-records/ measured preflight evidence, including runs whose verdicts were later
                   found not to mean what they appeared to mean
```

## Reading order for a reviewer

1. `docs/SETUP.md` — how to actually run it.
2. `server/src/mailweave/envelope/disposition.py` — the invariant everything else defends.
3. `tests/test_disposition_invariant.py` and `tests/test_disposition_property.py` — the
   failure paths, including the ones that demonstrate the assertion firing.
4. `orivra/src/orivra/surface/allocation.py` — why a response is sized before it is built.
5. `docs/GMAIL_PREVIEW_RELEASE_REPORT.md` §5 — every open row, with the claim each deferral
   forbids.
6. `preflight-records/raw/README.md` — the records that decided nothing, and why they are kept.
