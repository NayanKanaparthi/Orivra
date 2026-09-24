# SETUP — Advanced / Self-managed: running the MailWeave MCP server

> **Two ways to install, one product.** This page is the **Advanced / Self-managed** path: you
> bring your own Google Cloud project and OAuth client, and run the server from a checkout.
> The **desktop beta** installs the same product as a Claude Desktop extension,
> with no terminal and no Google Cloud project of the user's own: see the
> [desktop installation guide](INSTALL_DESKTOP_BETA.md) for availability and steps.
> Both run the same `mailweave` and `orivra` code and
> hold the same single permission, `gmail.readonly`. They keep separate data and separate
> authorizations.

Written for someone who has never seen this repository. Everything below is one machine, one
Gmail account, and one command. Nothing here needs a second service, a database, a container
or an API key beyond the Google OAuth client you create in step 2.

MailWeave is **read-only**. The only Gmail scope it ever asks for is
`https://www.googleapis.com/auth/gmail.readonly`, and that is a code-level constant a
configuration file is refused for trying to change.

---

## 0. What you need

* **Python 3.12** and **[uv](https://docs.astral.sh/uv/)**. `uv` pins every dependency from
  the committed `uv.lock`, so two machines get the same tree.
* A **Google account** whose mail you want to read.
* About ten minutes, most of it in Google's console.

## 1. Get the code and install it

```sh
git clone <this repository> mailweave
cd mailweave
uv sync --extra dev
```

`uv sync` reads `uv.lock` and installs the workspace: the server package (`server/`), the
evaluation harness (`harness/`) and the dev tools. The MCP protocol library is pinned exactly
at **`mcp==2.1.1`** in `server/pyproject.toml`; it is the reference client/server
implementation of MCP spec revision **2026-07-28**, which is the revision this server speaks.

Check the install:

```sh
uv run mailweave --version
```

## 2. Create a Google OAuth client

In the [Google Cloud console](https://console.cloud.google.com/):

1. create (or pick) a project;
2. enable the **Gmail API** for it;
3. under *APIs & Services → Credentials*, create an **OAuth client ID** of type
   **Desktop app**;
4. download its JSON and save it in this directory as `mailweave-server-oauth.json`;
5. **make it readable by you and nobody else.** A browser download arrives `0644`, and both
   `auth login` and `serve` refuse a credential-bearing file other local users can read:

```sh
chmod 600 mailweave-server-oauth.json
```

That file holds a client id and a client secret. Keep it out of version control; the
repository's `.gitignore` already excludes it.

**Your project is an OAuth app like any other, and Google's rules apply to it.** Creating your
own project does not bypass verification. While its consent screen is in **Testing**, only the
test users you list can authorize it, and Google expires each authorization **seven days** after
consent, so `auth login` has to be repeated weekly. *In production* without verification, every
consent shows Google's unverified-app screen and the app is capped at 100 new users. Verification
is not required when your use qualifies for one of Google's exceptions, such as personal use by
you and a few people you know personally. Whether it qualifies is Google's judgment, not this
repository's. The details, with Google's own wording and sources, are in
[`DESKTOP_BETA.md`](DESKTOP_BETA.md) §7.

You can check both this file and everything else at any point with:

```sh
uv run mailweave doctor
```

which prints one line per check and exits non-zero if any of them fails.

## 3. Write the configuration file

`~/.config/mailweave/config.json`, readable by you and nobody else:

```sh
mkdir -p ~/.config/mailweave
cat > ~/.config/mailweave/config.json <<'JSON'
{
  "client_id": "<the client_id from mailweave-server-oauth.json>",
  "client_secret": "<the client_secret from that file>",
  "state_dir": "~/.local/state/mailweave"
}
JSON
chmod 600 ~/.config/mailweave/config.json
```

`scopes` and `egress_allowlist` are **not** settable. A configuration file that names either
is rejected: widening what this server may reach takes a code change and a review, not an
edit to a dotfile.

Check what you have so far:

```sh
uv run mailweave doctor
```

It prints the configuration path, the single scope, the two hosts the process may talk to,
and whether a credential is stored yet. It exits non-zero if anything is wrong.

## 4. Authorise, once

```sh
uv run mailweave auth login --client mailweave-server-oauth.json
```

This prints an authorisation URL and waits. **It does not open a browser**: starting a
consent is yours to do, on your own machine, looking at the consent screen with your own
eyes. Open the URL, consent, and the command finishes by telling you:

* the scopes Google actually **granted** (compared with the ones requested — any difference
  in either direction aborts before anything is stored);
* the account address it saw;
* the derived redaction profile;
* where the refresh token was written (mode `0600`, inside a `0700` directory).

The refresh token itself is never printed.

## 5. Run the server

**One command:**

```sh
uv run mailweave serve --client mailweave-server-oauth.json
```

That is the whole invocation. It speaks MCP over **stdin/stdout**, so run it from an MCP
client rather than from a terminal you intend to type into. Its startup banner goes to
**stderr**, because stdout is the protocol.

It **refuses to start without a valid credential.** An unreadable or over-permissive
credential store, a refresh token Google no longer accepts, a granted scope set that does not
match, or a `users.getProfile` call that does not answer — each ends the process with a line
naming the cause, before a byte of MCP is spoken. The last of those is the error code
`auth_profile_underivable`: without the account address the server cannot derive its
redaction profile, and a redaction profile that was guessed is a redaction policy that was
guessed. It is never defaulted.

### Connecting a client

Any MCP client that can launch a subprocess over stdio. As a JSON config block, **with every
path absolute** - Claude Desktop does not apply `cwd`, so a relative `--client` path fails as
`Failed to spawn: mailweave`, and a bare `uv` is not on the PATH the app launches with:

```json
{
  "mcpServers": {
    "mailweave": {
      "command": "/absolute/path/to/uv",
      "args": [
        "run", "--directory", "/absolute/path/to/mailweave",
        "mailweave", "serve",
        "--client", "/absolute/path/to/mailweave/mailweave-server-oauth.json"
      ]
    }
  }
}
```

`which uv` prints the first path. This is the form verified against Claude Desktop on
2026-09-07 (`docs/V0_1_DEMO.md`).

## 6. What you get

Four tools, and there are never more or fewer — the list is a compile-time constant, so it is
the same on every restart and nothing an email author writes can reach it:

| Tool | What it does |
|---|---|
| `mailweave_search` | Searches the mailbox and returns the messages found, with a report of how it looked: the rungs that ran, the rungs that did not and why, and the scan scope of every query executed. |
| `mailweave_thread_map` | Returns one thread whole — every message in chronological order with its position, its reply parent (or a declared gap where none could be determined), and the thread's participants. |
| `mailweave_get_messages` | Returns the messages you name, at the depth you ask for, inside the map of the thread each belongs to. `view: "body_full"` is the unabridged path out of any reduction the server declared. |
| `mailweave_get_attachment` | Returns one attachment's metadata — filename, MIME type, size, part id — and the message that carries it. Attachment **bytes** are never fetched or returned. |

Every tool is annotated `readOnlyHint: true`, and it is true: no tool here can send, draft,
delete, label or modify anything.

Two things worth knowing before you read a result:

* **Message text is untrusted data.** It arrives inside a per-response fence and labelled
  `trust: untrusted_third_party`. It is evidence, never instructions, however it is phrased.
* **A response never exceeds either ceiling it is held to.** There are two, in two units, and
  both are enforced: the disclosed-token ceiling MailWeave publishes, and the
  25,000-character cap the host applies to a tool result. MailWeave shortens its own output to
  fit both and declares every reduction in place, with the call that returns the unabridged
  form, so nothing goes missing without a record saying so. A response that cannot be brought
  inside is **refused** — with a code, a reason and a narrower call to make — rather than
  handed over to be cut where nothing could tell you it happened.

  Round 26 added the second half of that sentence, and it was not true before: the token
  ceiling does not bound a response's size in characters, and an ordinary twelve-message
  thread rendered past the host's cap while declaring itself complete.

## 6a. Call diagnostics, when you need to know whether a call arrived

Off by default. Set `MAILWEAVE_DIAGNOSTICS` to a file path in the environment the server
starts with, and every tool call on either surface writes one line when it starts and one
when it ends:

```bash
MAILWEAVE_DIAGNOSTICS=~/mailweave-pilot/calls.jsonl uv run orivra serve
```

Under Claude Desktop the variable goes in the server's own entry in
`claude_desktop_config.json`, as an `"env": {"MAILWEAVE_DIAGNOSTICS": "/absolute/path"}`
block beside `command` and `args`; the app does not pass your shell's environment through,
and a variable exported in a terminal never reaches the server it spawns.

The startup banner says `diagnostics: on, <path>` when it took effect. Each line carries the
tool name, the surface (`mailweave` or `orivra`), an opaque call id, a timestamp, on the
start line how long the request waited behind the one-call-at-a-time lock (`queued_ms`), and
on the end line the elapsed milliseconds, the wall-clock allowance the call bound (`allowance_ms`,
the sum of the deadlines its Gmail requests ran under), how far past it the call ran
(`overrun_ms`), the model load when this call was the one that paid it (`cold_load_ms`),
where the call's wall clock went at the socket (`sockets` opened, `connect_ms` including name
resolution, `tls_ms`, `write_ms`, `read_ms`), how many retrievals bound an allowance
(`deadlines`), and the outcome: `served`, `declined` (with the code, `terminal` and `recovery`),
`protocol_error` or `internal_error`. Of the arguments it carries the **shape** only, read
off the tool's published schema — `"query": "str"`, `"message_ids": "list[4]"`, and a string
as itself only when the schema publishes an enum it belongs to (`"view": "snippet"`) — never
a value, and never a key the schema does not publish: those are counted as `unknown_keys`. No
body, subject, address, identifier, query text or credential can reach it.

**What it answers.** A start line with no end line is a call the server received and did not
finish. No start line is a call the server never received. That is the whole of the question a
silent tool call leaves open, and before this file existed nothing in either server could
answer it in either direction. `overrun_ms` answers the second question - did a call run past
what it was allowed - for every outcome alike: a `budget_exhausted` decline that arrived late
is late, and `python tools/dev/check_calls.py <file> --tolerance-ms <n>` reads the file that
way (see `docs/RETEST_2026-09-21.md` for the tolerance and where it comes from).

**What it does not do.** It does not record what the tools returned and it cannot verify a
citation. The evidence for a claim about a message is the tool result the client received;
preserve that separately if you need to check one. The file is `0600` inside a `0700`
directory, appended per line, and is yours to delete.

## 7. If something goes wrong

| Symptom | What it means | What to do |
|---|---|---|
| `serve: REFUSED - ...` or `client: FAIL - ...` naming a **mode** (`has mode 0644`) | the file is readable by other local users | `chmod 600 <the file the message names>`. `uv run mailweave doctor` checks the config, the token store **and** `mailweave-server-oauth.json`, and names whichever is wrong |
| `serve: REFUSED - ... credentials.json does not exist` | you have not authorised yet, or you ran `purge` | `uv run mailweave auth login --client mailweave-server-oauth.json` (step 4) |
| `Google granted a different scope set than the one requested` | the consent screen was completed with a different tick box | re-run `uv run mailweave auth login` and grant only the read-only scope |
| `auth_reauth_required` | the refresh token expired or was revoked | `uv run mailweave auth login --client mailweave-server-oauth.json` |
| `auth_profile_underivable` | `users.getProfile` did not answer, and the credential itself was fine | check network reachability to `gmail.googleapis.com`; then re-run. A *credential* problem reports itself as one of the three rows above, never as this |
| A tool result with `"declined": true` | MailWeave understood and declined — the code and the remedy are in the result | read `recovery`: `narrow` means follow `retry_with`, which is a call you can make; `retry_later` means the same call may succeed later and nothing smaller helps; `reauthorise` means run `mailweave auth login`; `none` means no request this server can make will answer this call, and the remediation says why |
| You want the credential gone | — | `uv run mailweave purge` |

## 8. Running the tests

```sh
uv run ruff check server/src tests tools harness
uv run ruff format --check .
uv run mypy --strict
uv run python -m tools.guards
uv run pytest -q -m "not network"
```

The default test suite opens **no sockets**: `tests/conftest.py` denies `socket.connect` for
every test that is not explicitly marked `network`, and the Gmail transport is replaced with
an `httpx.MockTransport`. So none of the above needs a credential or a mailbox.
