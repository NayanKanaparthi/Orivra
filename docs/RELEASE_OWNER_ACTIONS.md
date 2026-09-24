# RELEASE_OWNER_ACTIONS.md — the Gmail preview, and what only the owner can do

**Status: awaiting owner action.** Nothing here has been done. Nothing has been tagged, pushed
or published. Feature work is frozen.

Working head: `2588740` on `orivra-gmail-preview`. 170 commits.

**Corrected 2026-09-19 (third pass), on owner review.** §2 and §7a were rewritten again: the
first rewrite had the right principles and commands that would not run — `/etc/hosts` edits,
moving installed weights, an environment rebuild, and a token path that does not exist. Both
sections now use only shipped CLI flags, and every command in §7a that could be run without
your weights was run in isolation first. Five things in the first draft were
wrong and are marked **[corrected]** where they appear: PF-5's scope, the status of the beta
deferrals, what a history rewrite may do to evidence records, how a replacement credential is
verified, and the backup. Anything citing a commit count or a head is now read from the
repository rather than carried forward.

**Authorities.** `ORIVRA_V1_PLAN.md` §9a, `RELEASE_RUBRIC.md`,
`docs/GMAIL_PREVIEW_RELEASE_REPORT.md`.

---

## 1. The four actions, deliberately separate

They were one line in an earlier note — "credential rotation and repository sanitisation" — and
that was wrong, because it invited doing them together. They have different risks, different
reversibility, and three of the four can be done without the others.

| | Action | Reversible? | Blocks what |
|---|---|---|---|
| **A** | Issue replacement OAuth clients | yes — verification writes to a scratch store, the live one is never touched, and the old clients keep working until B | B, and any distribution |
| **B** | Retire the old OAuth clients | **no** | nothing; it is what ends the exposure |
| **C** | Rewrite local git history | yes, from the backup in §5 | pushing this repository anywhere |
| **D** | Publish to a remote | **no, in practice** | — |

**The ordering that matters: A, then verify, then B.** A and B are separate precisely so that
the old credentials keep working until the replacements are proven. Retiring a client you have
not yet authenticated against leaves you with a server that cannot start and no way back.

**C is not a prerequisite for A or B**, and B is not a prerequisite for C. C is a prerequisite
for D and for nothing else. The built artifact (§6) contains no history and no credentials, so
distributing *it* does not require C — only A and B.

---

## 2. Action A — issue replacement OAuth clients

**Reversible. Do this first.** Nothing here retires anything; §3 does that.

### 2.1 The two credentials are not distinguished by account **[corrected]**

The previous draft's check was "the harness authorizes `mailweave.test@gmail.com` and not the
real mailbox". That is the wrong axis and would pass with the two clients swapped: **both
credentials currently authorize `mailweave.test@gmail.com`.** What separates them is the client
and the scope.

| | Server | Harness (seeder) |
|---|---|---|
| Client file | `mailweave-server-oauth.json` | `mailweave-harness-oauth.json` |
| Cloud project | `mailweave-server` | `mailweave-harness` |
| Scope | `https://www.googleapis.com/auth/gmail.readonly` — read-only | `https://mail.google.com/` — **full, destructive** |
| Account today | `mailweave.test@gmail.com` | `mailweave.test@gmail.com` |
| Token store | `<state_dir>/credentials.json` | its own store, passed explicitly |

Two things follow. **The account is not evidence of which credential you are holding**, so any
check that only reads the address proves nothing. And the destructive scope lives on the
harness client, so a mix-up is not a tidiness problem: it is a `https://mail.google.com/` grant
landing on the credential the server uses.

The code already refuses that, and the refusals are worth knowing because they mean the
verification below does not rest on you reading output carefully:

- `seed/driver.py::_refuse_shared_credential` — the harness refuses to start if its client id
  equals the server client's, before any network call;
- `seed/driver.py::_refuse_shared_store` — it refuses if its token store resolves to the
  server's, because "two grants with different scopes in one file is how a read-only server
  acquires a destructive token by accident". **It returns without checking when
  `--server-token-path` is not passed**, so §2.4 passes it explicitly;
- both logins read the granted scopes back and compare them against their own set, and the
  harness pins the account with `assert_seed_account`.

### 2.2 Resolve the paths from the configuration, not from this document **[corrected]**

The previous draft named `~/.mailweave/token.json`. That path does not exist. The real one is
`<state_dir>/credentials.json`, where `state_dir` comes from `~/.config/mailweave/config.json`
and defaults to `~/.local/state/mailweave` — so it is a configured value, not a constant, and
the only correct way to get it is to ask:

```bash
cd ~/Desktop/Nayan/MailWeave
.venv/bin/mailweave doctor
```

It prints the config path it read, the scope set, the egress allowlist, **the OAuth client file
path** and **the token store path**, and exits non-zero on a permissions problem. Use the two
paths it prints below; do not assume them.

### 2.3 Issue the replacements

1. In the Google Cloud console, create a new **OAuth client ID**, type *Desktop app*, in
   project `mailweave-server`, and another in project `mailweave-harness`. **Do not delete the
   existing clients** — that is §3.
2. Download both JSON files.
3. **Keep the current files, under names nothing else will claim.** Not `.previous`, which is
   generic enough to collide with an earlier attempt:

   ```bash
   STAMP=$(date +%Y%m%dT%H%M%S)
   cp -p mailweave-server-oauth.json  "mailweave-server-oauth.json.pre-rotation.$STAMP"
   cp -p mailweave-harness-oauth.json "mailweave-harness-oauth.json.pre-rotation.$STAMP"
   ```

   `.gitignore` covers `mailweave-server-oauth.json` and `mailweave-harness-oauth.json` by
   exact name, so **these copies are not ignored**. Add the pattern before you make them, or
   keep them outside the repository:

   ```bash
   grep -q 'oauth.json.pre-rotation' .gitignore || \
     printf '\n# pre-rotation credential copies, never committed\n*-oauth.json.pre-rotation.*\n' >> .gitignore
   ```

4. Put the new files at the two paths the commands actually read, then `chmod 600` both. Only
   one of the two is discoverable from `doctor`:

   - **server** — the path `doctor` printed on its `oauth client file:` line (the default is
     `mailweave-server-oauth.json` in the project root);
   - **harness** — `doctor` does not know about this one. It is the harness's `--client-path`,
     whose default is `mailweave-harness-oauth.json` in the project root.

   A console download arrives `0644`. `doctor`, `serve` and `auth login` all refuse a
   credential-bearing file other local users can read, so `chmod 600` is not tidiness.

### 2.4 Verify by authenticating afresh — into a scratch store, moving nothing **[corrected twice]**

The previous draft said to move the token cache aside. There is no need: `auth login` takes
`--state-dir`, so a fresh consent can write somewhere new and leave the real store untouched.
Nothing is moved, so there is nothing to put back.

**Three things in the previous draft were not executable, and each is corrected below.** They
were found by running the shipped argument parsers and the harness refusal paths in isolation
against the exact files in this tree (`cli.py`, `seed/__main__.py`, `seed/driver.py`,
`tools/dev/gmail_walk.py`, `config.py` — SHA-256 matched between the tree and the environment
the checks ran in):

| Was | Is |
|---|---|
| "A browser must open. If none opens, the check is void" | **`auth login` opens no browser, by design** — it prints the authorisation URL and waits, because "consent is the owner's to start". A missing browser is not a finding. The real discriminator is below |
| `python -m mailweave_harness.seed --login … --state-dir …` | **`--state-dir` does not exist on the harness.** It takes `--token-path` and `--server-token-path`, and `--login` additionally **requires `--seed-address`** |
| "the read-only call … must use `--state-dir "$VERIFY/server"`" | **No read path takes `--state-dir`.** The store comes from `state_dir` in the config file, so the scratch store is reached with a scratch config and the top-level `--config` |

```bash
cd ~/Desktop/Nayan/MailWeave
VERIFY=$(mktemp -d -t rotcheck); chmod 700 "$VERIFY"
```

**Step 1 — the server credential, fresh consent, into a scratch store, account pinned.**

```bash
.venv/bin/mailweave auth login \
    --client mailweave-server-oauth.json \
    --state-dir "$VERIFY/server" \
    --expect-account mailweave.test@gmail.com
```

It prints `client: <client id> (<path>)`, then an authorisation URL, then waits on a loopback
listener. **Two things make this a real test of the new client rather than a replayed grant:**

- `$VERIFY/server` is empty, so there is no refresh token to serve. A consent flow must happen.
- The printed line and the `client_id=` parameter inside the authorisation URL must both be
  the **new** client id. If either is the old one you are verifying the credential you are
  about to retire. (Verified: the URL the code builds carries the client id of the file passed
  to `--client`.)

`auth login` aborts unless the consented mailbox matches `--expect-account`, and it reads the
*granted* scope set back and compares it with `SERVER_SCOPES`, so a consent screen that offered
more than `gmail.readonly` does not pass quietly. No secret and no token is printed.

**Step 2 — the harness credential, whose own refusals do most of the work.**

```bash
.venv/bin/python -m mailweave_harness.seed --login \
    --seed-address mailweave.test@gmail.com \
    --client-path mailweave-harness-oauth.json \
    --token-path "$VERIFY/harness/credentials.json" \
    --server-client-path mailweave-server-oauth.json \
    --server-token-path "$VERIFY/server/credentials.json"
```

`--server-token-path` is **not optional here**: `_refuse_shared_store` returns without checking
anything when it is absent, so leaving it off silently disables half the guard.

Both refusals were exercised in isolation against this tree and both fire **before any network
call**:

- two client files carrying the same client id → `REFUSED: … the same client id as the server
  credential … Refusing before any network call`;
- distinct clients but one shared store path → `REFUSED: … the harness token store … is the
  server's … Refusing`;
- distinct clients and distinct stores → proceeds to build a consent URL carrying the harness
  client id, which is the pass condition.

A clean run prints the account, the granted scopes (`https://mail.google.com/`) and the store
path. Exit 2 is a refusal, not a crash.

**Step 3 — one live read-only call through the new server grant.**

Consent completing proves the client exists. It does not prove the credential can read the
mailbox. The read path takes its store from the config, so point a copy of your config at the
scratch store and change nothing else:

```bash
CFG=$(.venv/bin/mailweave doctor | sed -n 's/^config: ok (\(.*\))$/\1/p')
[ -n "$CFG" ] || { echo "doctor did not report a config path; fix that first"; }
.venv/bin/python - "$CFG" "$VERIFY" <<'PY'
import json, pathlib, sys
src = pathlib.Path(sys.argv[1]).expanduser()
verify = pathlib.Path(sys.argv[2])
cfg = json.loads(src.read_text(encoding="utf-8"))
cfg["state_dir"] = str(verify / "server")          # the ONLY field changed
out = verify / "config.json"
out.write_text(json.dumps(cfg), encoding="utf-8")
out.chmod(0o600)
print(out)
PY
```

Nothing is printed from inside the file, so the client secret it carries does not reach the
terminal. Copying it whole rather than writing a minimal one matters: `seed_account_hash` and
`seed_client_id` are what `derive_profile` uses to choose the redaction profile, so a
hand-written config would verify a *different* profile from the one you run. (`client_id` and
`client_secret` in the config are not used by the read path at all — the OAuth client comes
from `--client` — but they are required fields, which is the other reason to copy rather than
compose.)

```bash
.venv/bin/python tools/dev/gmail_walk.py \
    --client mailweave-server-oauth.json \
    --config "$VERIFY/config.json" \
    --query "<a phrase you know is in that mailbox>"
```

This is the read-only demonstration path: four tools, all annotated read-only, on the
`gmail.readonly` client. It prints identities, relation names, origins, freshness states and
counts — **no subjects, no bodies, no tokens** — and writes no file. **Exit 0 with rows is the
proof the new credential reads the mailbox.** Exit 1 means the walk could not complete, which
for a mailbox with nothing matching the query is an honest answer about the query, not about
the credential: try a phrase you are certain is there before concluding anything.

Optionally confirm what the scratch config resolved to, which touches nothing:

```bash
.venv/bin/mailweave --config "$VERIFY/config.json" doctor
```

It prints the config path it read, the fixed scope set, the egress allowlist, the OAuth client
file and **the token store path** — which must be `$VERIFY/server/credentials.json`, not your
real store. If it names the real store, the copy did not take and step 3 tested the old grant.

**Rollback, at any point before §3:** `rm -rf "$VERIFY"` and put the `.pre-rotation.$STAMP`
files back. The live token store was never touched, the old clients still work, and nothing has
been retired.

**Then, and only then**, delete the scratch directory and move to §3. Keep the
`.pre-rotation.$STAMP` copies until §3 is done and confirmed.

## 3. Action B — retire the old OAuth clients

**Not reversible. Only after A is verified.**

Deleting the old client IDs in the Google Cloud console is the act that ends the exposure.
Until it happens, the secrets in git history are live credentials; after it, they are strings.

Nothing else in this document substitutes for it. In particular **C does not**: a history
rewrite makes the blobs unreachable from the refs it rewrites and does nothing to any copy
already taken.

> **Approval to record in the findings ledger:**
>
> "Replacement OAuth clients are in place. Each was verified by a **fresh consent flow into a
> scratch `--state-dir`** — a browser opened, so no cached grant was involved — with the live
> token store untouched throughout. The server client granted **`gmail.readonly` and nothing
> else** and returned rows from one read-only search; the harness client granted
> **`https://mail.google.com/`**, was accepted by `_refuse_shared_credential` and
> `_refuse_shared_store` as a distinct client with a distinct store, and pinned to the seed
> account. Both accounts are `mailweave.test@gmail.com`; the account was **not** used as the
> discriminator, the client id and the granted scope were. The previous client IDs in projects
> `mailweave-server` and `mailweave-harness` have been deleted in the Google Cloud console.
> Dated, and the exposure is closed as of this date."

---

## 4. Action C — rewrite local git history

**Reversible from the backup in §5. Required before D and before nothing else.**

### What is in there

| | |
|---|---|
| Blobs | `a455f6c36dc3` (405 B, server), `34798b456543` (406 B, harness) |
| Reachable from `HEAD` | **both** — not orphaned |
| Refs carrying them | `main`, `orivra-gmail-preview`, **and the `v0.1` tag** |
| Introduced by | `0162e79` (server), `948bd2a` (harness), re-added at `dd0711c` |
| Earliest offending commit | `0162e79`, **163 of 170** commits renamed |
| Commits a rewrite renames | **163** of **170** (`0162e79` and every descendant, across both branches); 7 commits are older and keep their ids |
| Anything else exposed | **no.** 1,955 blobs swept for `client_secret`, `refresh_token`, `access_token`, private-key headers, bearer tokens and the real Google client-id shape. The client-id shape appears in those two blobs and nowhere else; every other match is a placeholder or a named synthetic canary |

### Preconditions

1. §5's backup exists and has been verified.
2. `git-filter-repo` is installed (`brew install git-filter-repo`). `filter-branch` is the
   fallback and is slower, subtly wrong in more ways, and not recommended.
3. The working tree is clean, or its changes are committed — a rewrite discards nothing but is
   far easier to reason about from a clean tree.

### The rewrite

```bash
# from a clean tree, with the §5 backup already taken
printf '%s\n' \
  'mailweave-server-oauth.json' \
  'mailweave-harness-oauth.json' > /tmp/paths-to-purge.txt

git filter-repo --invert-paths --paths-from-file /tmp/paths-to-purge.txt \
  --replace-refs delete-no-add
```

`--invert-paths` on the two paths removes the blobs wherever they appear, across every ref
including the `v0.1` tag, which `filter-repo` rewrites in place.

### Afterwards, in order

```bash
git for-each-ref --format='%(refname) %(objectname:short)'      # the new ref tips
git rev-list --all --objects | grep -E 'a455f6c36dc3|34798b456543'   # must print nothing
git reflog expire --expire=now --all
git gc --prune=now --aggressive
```

Then re-run the sweep that produced the table above and confirm it comes back empty.

### The commit-ID mapping — §7. **Do not skip it.**

> **Approval to record in the findings ledger:**
>
> "Approved: rewrite git history to remove `mailweave-server-oauth.json` and
> `mailweave-harness-oauth.json`, and with them blobs `a455f6c36dc3` and `34798b456543`, across
> `main`, `orivra-gmail-preview` and the `v0.1` tag; expire the reflog and garbage-collect. I
> accept that all 163 commit ids from `0162e79` onward change, that `v0.1` will point at a new
> commit, and that the private backup in §5 has been taken and verified first."

---

## 5. The private backup, before C **[corrected]**

The first draft said `git clone --mirror` into `~/Desktop/Nayan`. Both halves were wrong.

**A mirror clone is not the working state.** It copies committed objects and refs. It does not
copy the working tree, so anything uncommitted or untracked is not in it — and right now that
includes `marketing/README.md` (modified), the whole untracked `marketing/` tree, and
`benchmarks/`, which is gitignored and holds the three preserved Desktop records. A rewrite
does not touch those, but a rewrite is the moment you most want a way back to *everything*, and
a backup that silently omits half the directory is worse than none.

**`~/Desktop` may be synced.** macOS Desktop & Documents sync to iCloud Drive when that setting
is on, and a synced folder is a remote for this purpose: a backup containing the credential
blobs must not go into one. Nor should it go to Dropbox, Google Drive or any other synced path.

Take two things instead, both to a location you have confirmed is local-only:

```bash
# Confirm the destination is not synced. On macOS, an iCloud-managed folder answers here:
BACKUP_ROOT=~/mailweave-backups          # NOT ~/Desktop, ~/Documents, or any synced folder
mkdir -p "$BACKUP_ROOT"
brctl status "$BACKUP_ROOT" 2>/dev/null | head -3   # silence or an error means not iCloud-managed
```

**1. The complete working state, credentials excluded.** An archive of the directory as it
stands, so untracked and gitignored files survive:

```bash
cd ~/Desktop/Nayan
tar --exclude='mailweave-server-oauth.json' \
    --exclude='mailweave-harness-oauth.json' \
    --exclude='*-oauth.json.previous' \
    --exclude='.venv' \
    --exclude='**/__pycache__' \
    --exclude='_to_delete' \
    -czf "$BACKUP_ROOT/mailweave-worktree-$(date +%Y%m%d).tar.gz" MailWeave
```

The two credential files and any `.previous` copies are excluded deliberately: they are on disk
already and putting live secrets into a second archive widens the exposure rather than
protecting against it. `marketing/` **is** included — it is excluded from *commits*, not from
backups, and losing someone's untracked work to a rewrite you took a backup for would be absurd.

**2. The full object store, which does carry the blobs.** This is the one that can restore the
original commit ids:

```bash
git clone --mirror ~/Desktop/Nayan/MailWeave "$BACKUP_ROOT/mailweave-prerewrite-$(date +%Y%m%d).git"
```

A `--mirror` clone carries every ref and every object **including the two credential blobs**.
Keep it local-only, keep it until C is verified *and* B is done, and delete it after B — at
which point the blobs are inert strings.

**Verify both before starting C:**

```bash
git -C "$BACKUP_ROOT"/mailweave-prerewrite-*.git rev-list --all --count     # expect 170
git -C "$BACKUP_ROOT"/mailweave-prerewrite-*.git cat-file -e a455f6c36dc3 && echo "objects present"
tar -tzf "$BACKUP_ROOT"/mailweave-worktree-*.tar.gz | grep -c '^MailWeave/benchmarks/'   # non-zero
tar -tzf "$BACKUP_ROOT"/mailweave-worktree-*.tar.gz | grep -c 'oauth.json'               # expect 0
```

To restore the repository: `git clone "$BACKUP_ROOT"/mailweave-prerewrite-*.git MailWeave-restored`,
which gives back the original ids exactly. To restore the rest: extract the tarball beside it.

## 6. Action D — publish to a remote

**Not reversible in practice.** Blocked until A, B, C are done and the must-pass rows in
`GMAIL_PREVIEW_RELEASE_REPORT.md` §5 pass.

Two things can be published and they have different prerequisites:

| What | Contains history? | Needs |
|---|---|---|
| The **built artifact** — four files, §6.1 | no | A and B. Not C |
| The **repository** — a push to any remote | yes | A, B **and** C |

### 6.1 The artifact

Built offline on 2026-09-19 and inspected file by file:

| File | sha256 (this build) |
|---|---|
| `orivra-0.2.0b1-py3-none-any.whl` | `86123b67cd440e15c5206d3966e9c22b9473e10ce696263e0d50fbecc71b4e3c` |
| `orivra-0.2.0b1.tar.gz` | `8c9753dd5a5ff13272a18fd16c8cb04f22440e832e814ba4e69e32f668b736a0` |
| `mailweave-0.2.0b1-py3-none-any.whl` | `26c53b374623b565c14a9388f82d4497869f9c07209fed40380707af8c24304c` |
| `mailweave-0.2.0b1.tar.gz` | `3053c3802b24b58325b5c598e45e3b4c53ffc8082aa2ea75fd99e9f44fb9f004` |

Every member of all four was enumerated. No credential file, no `client_secret` /
`refresh_token` / private-key / bearer / Google-client-id shape, no `.git`, no tests, no
benchmarks, no `validation-records`, no `preflight-records`, no `marketing`, no `uv.lock`, no
caches. Top-level entries are the package and its `dist-info`, and nothing else.

The two wheels were installed together into a clean Python 3.12 environment from the local
directory: `orivra 0.2.0b1` resolved `mailweave 0.2.0b1` through the new exact pin, `orivra
--version` printed, the installed server published all eight tools, and a `v0.1`-shaped
`pool: {"scope": …, "window": …}` call parsed from the installed wheel.

**Rebuild before publishing.** These digests are for the build made during verification; the
release build should be made from the tagged commit and its digests recorded then.

The harness does not ship: separate package, separate OAuth client, separate scopes, and
nothing in the preview needs it.

> **Approval to record in the findings ledger:**
>
> "Approved: publish `orivra` and `mailweave` at `0.2.0b1` to `<named destination>`, built from
> tag `<tag>`, with the four digests recorded in this document. A and B are complete."

### 6.2 The repository

> **Approval to record in the findings ledger:**
>
> "Approved: add remote `<name> <url>` and push `main`, `orivra-gmail-preview` and all tags. C
> is complete, the object sweep is empty, and B is done."

---

## 7. Commit-ID mapping, and evidence that must not be touched **[corrected]**

The first draft proposed a script that substitutes new commit ids for old ones "across those
files", and listed `benchmarks/`, `validation-records/` and `preflight-records/` among them.
**That is wrong and must not be done.**

### What may not be rewritten

`validation-records/`, `preflight-records/` and `benchmarks/*.preserved` are *records of what
happened*. Their value is that they say what was observed at a moment, and a record edited
afterwards to stay tidy is no longer a record — it is a reconstruction with the same filename.
The three preserved Desktop records are the clearest case: two of them exist precisely to say
that a demonstration did **not** succeed, and each carries a provenance block about what was and
was not verified. Editing ids inside them to match a rewritten history would be changing
evidence to agree with the present, which is the failure mode this whole project is organised
against.

So: **every file under `validation-records/`, `preflight-records/` and `benchmarks/` is
preserved byte-for-byte through any rewrite.** Nothing substitutes into them. After C, verify:

```bash
# digests taken BEFORE the rewrite
find validation-records preflight-records benchmarks -type f -exec shasum -a 256 {} + \
  | sort > "$BACKUP_ROOT/evidence-digests-before.txt"

# ... run C ...

find validation-records preflight-records benchmarks -type f -exec shasum -a 256 {} + \
  | sort > /tmp/evidence-digests-after.txt
diff "$BACKUP_ROOT/evidence-digests-before.txt" /tmp/evidence-digests-after.txt \
  && echo "evidence unchanged"
```

`benchmarks/` is gitignored, so a rewrite of tracked history cannot reach it in any case; the
check is there because "cannot" and "did not" are different claims and this one is cheap.

### The map, and an index beside it

`git filter-repo` writes `.git/filter-repo/commit-map` — two columns, old and new, one line per
commit. Preserve it as its own artifact rather than as an instruction to edit anything:

```bash
mkdir -p docs/reviews/rewrite-2026-09
cp .git/filter-repo/commit-map docs/reviews/rewrite-2026-09/commit-map.txt
wc -l docs/reviews/rewrite-2026-09/commit-map.txt        # ~171 lines including the header
```

Then write `docs/reviews/rewrite-2026-09/README.md` — an **explanatory index**, which is the
thing that replaces the substitution pass. It says:

- the date, why the rewrite happened, and which two blobs it removed;
- that **163 of 170** commits changed id, the earliest being `0162e79`;
- that `v0.1` now points at a different commit, and what the old one was;
- **that every id cited in `validation-records/`, `preflight-records/` and `benchmarks/` is a
  pre-rewrite id and is resolved through `commit-map.txt`**, not by looking it up in the
  current history, where it will not be found;
- that ids in *prose* documents — the plan, the release report, the completion notes — were
  left as they are for the same reason, and are resolved the same way.

A reader who finds an id that `git show` cannot resolve needs one place that explains why. That
place is this index. It is one file to write once, against many files edited irreversibly, and
it keeps every record exactly as it was written.

### What genuinely may be updated

Nothing has to be. If you later want the *living* documents to carry current ids — `README.md`,
`SETUP.md`, a changelog — that is an ordinary edit made deliberately, with the old id kept
beside the new one, and it is not part of C.

## 7a. PF-5(b) — two runs; case 1 produced **proxy-constrained smoke evidence**, 2026-09-19 **[corrected three times]**

**What PF-5 is.** `ARCHITECTURE_DECISION.md` §F: (a) a token-free model download with licence
and SHA-256 recorded; (b) the full suite run cold-started with every egress blocked except
`gmail.googleapis.com` and `oauth2.googleapis.com`, the model host explicitly among the blocked,
to catch the `huggingface_hub` revalidation call that setup-time provisioning does not prevent
(ADV-210); (c) D.4a's content pipeline run with sockets disabled. No timing figure appears
anywhere in it. **(a) and (c) are closed** — release report §5.2a.

The previous draft of this section told you to edit `/etc/hosts`, move your installed weights
and `uv sync`. None of that is necessary: `mailweave setup-models` already takes `--models-dir`,
`--status` and `--smoke`, so the weights are read where they are and nothing is moved.

### What was verified in isolation, and what was not

Run in this session against the shipped CLI, in a throwaway Linux environment with
`sentence-transformers 5.7.0` and `mailweave 0.2.0b1` installed from the tree:

| Verified | How |
|---|---|
| `--status` reports without touching anything | ran against an empty `--models-dir`: reported both stages MISSING, wrote nothing |
| `--smoke` honours `--models-dir` and does not silently fall back to the default | it looked in the directory given and failed *there*, naming the three missing files |
| The isolated-cache variables are honoured | `HF_HOME` and `XDG_CACHE_HOME` pointed at empty directories; **0 files** written to either, or to the models directory |
| **Case 2 end to end** | weights absent, proxy constrained → load fails by name, **no download attempted**, 0 files written |
| The proxy constraint reaches the two clients that matter here | `Connection refused` for both `urllib` and `huggingface_hub`'s own client, the latter with `HF_HUB_OFFLINE=0` set deliberately, so the refusal does not depend on the code's own offline flag. **This is a statement about two proxy-honouring clients, not about egress being enforced** — see the caveat under case 1 |

**Not verifiable here, and this is why case 1 was the owner's to run:** this environment's
egress allowlist does not include the model host, so the weights could not be provisioned and
the positive path — real embedding and reranking actually executing — could not be exercised.
**The owner ran case 1 on the Mac on 2026-09-19 and it produced a clean result**; the run and
its exact limits are recorded below and in `preflight-records/raw/README.md`.

**One correction worth knowing about the proxy constraint itself.** The first attempt set only
the uppercase proxy variables and **constrained nothing**: this environment presets a lowercase
`https_proxy`, and lowercase wins. Both cases are set below for that reason. If you take one
thing from this section into another procedure, take that.

### Case 1 — provisioned weights, isolated empty caches, proxy constrained

Establishes that real embedding and reranking execute from provisioned local weights with no
auxiliary cache to fall back on and every proxy-honouring client pointed at a closed port.
**That is a packaging and load result. It is not a network-boundary result**, for the reason
set out immediately below.

> **Run on the owner's Mac, 2026-09-19. Result: clean.** Exit `0`; a real 512-dimensional
> embedding over two texts and a real rerank over two candidates, correctly ordered. The log
> was preserved out of its temporary directory to
> `preflight-records/raw/PF-5b-case1-smoke-2026-09-19.log`, byte-for-byte, SHA-256
> `45373dee9a04efe7399489cbc2f49ba50252f63d40aef5067dd6d87f47b9fbc8`. The empty post-run cache
> listing is **operator-reported**: step 2 is a separate command and its output is not in that
> log.
>
> **Label: proxy-constrained smoke evidence.** Three things it is not, each of which an earlier
> draft of this section got wrong:
>
> - **Not evidence of an enforced network boundary.** Proxy environment variables constrain
>   only clients that read them. A raw socket, a client that ignores proxy variables, a
>   resolver call or a subprocess that rebuilds its environment is untouched. What the run
>   shows is that no proxy-honouring client completed a fetch during it.
> - **Not evidence about ADV-210.** Empty `HF_HOME` and `XDG_CACHE_HOME` remove a *fallback
>   cache*; they do not force `huggingface_hub` to revalidate. An absent retry ladder is
>   equally consistent with "revalidation was attempted and could not proceed" and with
>   "revalidation was never on this code path". Nothing here separates the two.
> - **Not PF-5(b) acceptance.** PF-5(b) is the full suite cold-started. This is one command.
>
> **Its timings are diagnostic only**; PF-4 is the measurement, and no figure in that log —
> `load 4680 ms` least of all — is a bound or may be quoted as one.
>
> The commands below are kept verbatim as the procedure that was run, so the record and the
> instruction cannot drift apart. Read the comments in them as describing what the commands
> *do*, not as claims about what they prove.

```bash
cd ~/Desktop/Nayan/MailWeave

# Scratch that is empty and yours; nothing existing is moved or modified.
PF5=$(mktemp -d -t pf5)              # e.g. /var/folders/.../pf5.XXXX
mkdir -p "$PF5/hf" "$PF5/xdg"
BLACK=http://127.0.0.1:9             # nothing listens there; every proxied request is refused

# 0. Where are the weights? This reads the lock and reports; it touches nothing.
.venv/bin/mailweave setup-models --status

# 1. Real encode and real rerank, caches empty, proxy-honouring clients pointed nowhere.
env HTTPS_PROXY=$BLACK https_proxy=$BLACK \
    HTTP_PROXY=$BLACK  http_proxy=$BLACK \
    ALL_PROXY=$BLACK   all_proxy=$BLACK \
    NO_PROXY=          no_proxy= \
    HF_HOME="$PF5/hf"  XDG_CACHE_HOME="$PF5/xdg" \
  .venv/bin/mailweave setup-models --smoke

# 2. Nothing was fetched. Both must print 0.
find "$PF5/hf" "$PF5/xdg" -type f | wc -l
```

`--smoke` loads the installed models offline and runs one encode over two texts and one rerank
over two candidates. **A pass prints `smoke: OK` with `model_id`, the revision and three
timings.** The timings are diagnostic, not a measurement — PF-4 measures; this answers whether
the artifacts load at all.

**What a failure looks like, and which failure it is:**

- `smoke: LOAD FAILED — … is not installed or does not match the lock` → the weights are not
  where `--models-dir` points, or they do not match `models.lock`. Says nothing about network.
- **Any `Retrying in Ns [Retry n/5]` line → this is a finding.** It means something reached for
  the network through a proxy-honouring client, and the proxy constraint makes that visible
  rather than silent. It is one-directional evidence: seeing a ladder tells you something
  reached out; **not seeing one does not tell you that nothing would have.** ADV-210 asks
  whether `huggingface_hub` revalidates against the host, and this run does not put the code on
  that path, so it answers the question neither way.
- `smoke: OK` with files appearing under `$PF5/hf` → it loaded, but something populated a cache
  on the way, which is the same finding wearing a quieter hat.

Clean up with `rm -rf "$PF5"`. Nothing else changed: no weights moved, no system file edited,
no environment rebuilt, and the proxy variables existed only for that one command.

### Case 2 — no weights at all

Establishes the negative half: that an installation with no weights declines rather than
reaching for them.

```bash
EMPTY=$(mktemp -d -t pf5empty)
env HTTPS_PROXY=$BLACK https_proxy=$BLACK HTTP_PROXY=$BLACK http_proxy=$BLACK \
    ALL_PROXY=$BLACK all_proxy=$BLACK NO_PROXY= no_proxy= \
    HF_HOME="$PF5/hf" XDG_CACHE_HOME="$PF5/xdg" \
  .venv/bin/mailweave setup-models --smoke --models-dir "$EMPTY"

find "$PF5/hf" "$PF5/xdg" "$EMPTY" -type f | wc -l     # must be 0
rm -rf "$EMPTY"
```

**Expected: exit 1, `smoke: LOAD FAILED` naming the missing files, no retry ladder, 0 files
written.** This exact run was executed in isolation during this session and produced exactly
that. Running it on your machine confirms it against your installed `sentence-transformers`
rather than the one in a throwaway environment, which is the only part that differs.

### What these two establish, and what they do not

| PF-5 clause | After these runs |
|---|---|
| (a) token-free download, licence + SHA-256 recorded | **closed** — `models.lock` carries a pinned revision, per-file digest and licence for both stages; `test_pf5_network_boundary.py` holds that the provisioning path reads no credential and sends no `Authorization` header |
| (c) content pipeline, sockets disabled | **closed** — a document carrying an external DTD entity, a remote stylesheet, a remote image and a CSS `url()` goes through both parsers with no fetch, no host in the extracted text and no entity substitution |
| (b) *weights load and execute from provisioned local files, with no auxiliary cache* | **shown, for the smoke command**, by the 2026-09-19 Mac run — `preflight-records/raw/PF-5b-case1-smoke-2026-09-19.log`, **proxy-constrained smoke evidence**, timings diagnostic only |
| (b) *an installation with no weights does not reach for them* | **shown in isolation 2026-09-19**, proxy-constrained. The owner's re-run would confirm it against their installed `sentence-transformers` rather than a throwaway one |
| (b) *the suite cold-started with egress blocked except the two Gmail hosts* | **open.** Neither run is the suite, and neither used an enforced block |

**Still open, and not claimable from either run.** This list is the remaining PF-5 gap; it is
**not** reducible to the full-suite item alone:

1. **An actually enforced network boundary.** Both runs used proxy environment variables, which
   constrain only proxy-honouring clients. Nothing here demonstrates that egress was blocked,
   that the model host was unreachable, or that a client bypassing proxy variables would have
   been stopped. PF-5(b)'s clause is about a block; what was run is a constraint on some
   clients. **Whatever else is done, the word "enforced" is not earned by this method.**
2. **ADV-210's `huggingface_hub` revalidation path.** Not exercised, and not shown to be
   suppressed. Empty auxiliary caches remove a fallback; they do not put the loader on the
   revalidation path, and an absent retry ladder does not distinguish "blocked" from "never
   attempted". This is the specific hazard PF-5(b) names, and it is untested.
3. **The full suite, cold-started.** PF-5(b) says the *suite*, not the smoke command. What the
   suite already gives is a different instrument — it denies `connect`, `connect_ex`,
   `create_connection` and `getaddrinfo` for every unmarked test, a socket-level ban rather
   than a host or proxy constraint — but it runs against whatever cache the machine has, which
   is exactly the condition (b) asks to remove. Neither run substitutes for it.
4. **The graceful in-band decline.** Case 2 shows the *loader* refusing. It does not show the
   *server* answering a query with `semantic_unavailable` and continuing, which is a different
   path; `test_offline_enforcement.py::test_the_semantic_rung_declines_in_band_rather_than_reaching_for_a_host`
   covers it offline and no live run has.
5. **The runtime egress allowlist against the two permitted hosts.** Tested statically; never
   exercised against the real Gmail endpoints with anything blocking.
6. **The empty-cache listing itself.** Operator-reported for case 1; not in the preserved log.

Items 1 and 2 are why the smoke run closes no PF-5(b) clause on its own. It is real evidence
about packaging and load, filed as that and nothing more.

> **Approval to record in the findings ledger** — the factual part is fixed; the bracketed
> parts are yours:
>
> "On 2026-09-19 the owner ran the PF-5(b) case-1 smoke command on the Mac. It exited 0 and
> performed a real embedding and a real rerank from provisioned local weights, with isolated
> empty auxiliary caches and every proxy-honouring client pointed at a closed port. The log is
> preserved at `preflight-records/raw/PF-5b-case1-smoke-2026-09-19.log` (SHA-256
> `45373dee…`). It is recorded as **proxy-constrained smoke evidence**, its timings are
> diagnostic only, and the empty-cache listing in it is operator-reported. **It closes no
> PF-5(b) clause.** PF-5(b) remains open on all of: an enforced network boundary, ADV-210's
> revalidation path, the full suite cold-started, the in-band `semantic_unavailable` decline,
> and the runtime allowlist against the two permitted hosts. Those are [to be completed before
> distribution / deferred for this beta — delete one]. If deferred: no claim is made that the
> runtime has been proven not to reach the model host, the boundary is described as
> **tested in code and not verified at runtime**, and the words 'enforced', 'cold-verified'
> and 'proven offline' are not used in any material."

## 8. What is not blocking, and what it costs to defer

See `GMAIL_PREVIEW_RELEASE_REPORT.md` §5. **[corrected]** Its §5.2 is a set of *proposals*, not
decisions already taken, and it is split so that a safety boundary is not filed beside a missing
benchmark: §5.2a is safety (two closed, PF-5(b) open — §7a above), §5.2b is performance and
comparison, §5.2c is coverage. Each carries the claim its deferral would forbid, and each needs
your approval. That table is the authority; this document does not duplicate it.

## 9. Done since this document was first written

- **`uv lock`** — run by the owner; committed at `2588740`. Verified by comparing the full
  package inventory rather than reading the diff: 104 packages before and after, none added,
  none removed, and the only versions that moved are `mailweave` (0.1.0 → 0.2.0b1) and `orivra`
  (0.1.0.dev0 → 0.2.0b1), both `source = editable`. **No third-party dependency changed.**

  One thing worth knowing rather than discovering: the lock still records
  `{ name = "mailweave", editable = "server" }` for Orivra's dependency rather than the new
  `==0.2.0b1` specifier. That is uv resolving the workspace source ahead of the version
  constraint and is expected. The exact pin is what goes into the published wheel —
  `Requires-Dist: mailweave==0.2.0b1`, read out of the built artifact.
- **PF-5(b) case 1** — run by the owner on the Mac, 2026-09-19. It exited `0` and performed a
  real embedding and a real rerank from provisioned local weights, with isolated empty
  auxiliary caches and every proxy-honouring client pointed at a closed port. The log is
  preserved byte-for-byte at `preflight-records/raw/PF-5b-case1-smoke-2026-09-19.log`, SHA-256
  `45373dee9a04efe7399489cbc2f49ba50252f63d40aef5067dd6d87f47b9fbc8`.

  It is filed as **proxy-constrained smoke evidence** with **diagnostic-only timings**, and
  **it closes no PF-5(b) clause**. A first draft of this entry said "under a proxy-enforced
  block" and credited it with exercising ADV-210. Both were wrong: proxy variables constrain
  only proxy-honouring clients and are not an enforced boundary, and empty auxiliary caches
  remove a fallback rather than forcing a revalidation, so an absent retry ladder does not
  distinguish "blocked" from "never attempted". The empty-cache listing is operator-reported
  and not in the log. §7a lists the six things still open, and the remaining PF-5 gap is **not**
  the full-suite form alone.

- **§2 made executable, and three non-executable instructions removed.** The argument parsers
  and the harness refusal paths were run in isolation against the exact files in this tree
  (SHA-256 matched). What changed: `auth login` **opens no browser** — the previous "a browser
  must open, or the check is void" would have failed a correct run; the harness takes
  `--token-path`/`--server-token-path` and requires `--seed-address`, not `--state-dir`; and no
  read path takes `--state-dir` at all, so the live read-only check now goes through a scratch
  config and the top-level `--config`. Both harness refusals were observed firing before any
  network call, and observed *not* firing when the clients and stores are properly distinct.
