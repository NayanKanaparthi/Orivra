# Orivra desktop beta: engineering notes and historical build evidence

**Current reader guide, 2026-09-24.** For installation, use
[`INSTALL_DESKTOP_BETA.md`](INSTALL_DESKTOP_BETA.md). The configured candidate is now built,
and the owner has reported successful installation and setup on their Mac. Its exact identity
and source inputs are in the [draft release notes](releases/0.2.0-beta.1.md). This does not
establish a clean-machine test, general answer quality, or public-release approval.

The original 2026-09-23 build observations below are retained as history. In particular,
§8.B–C describe the older unconfigured artifact, not the current installer, and §8.E describes
what had not been observed **at the time**. Their older hashes, sizes, and “not yet run”
statements must not be used as the current package status. No public asset has been uploaded.
The current candidate still carries its invite-only display name and distribution restriction;
the [upload review](reviews/RELEASE_UPLOAD_REVIEW_2026-09-24.md) records these without changing
the tested package. The remaining sections are the original engineering/reference material.

**Status, 2026-09-23.** Built and checked, not yet run on a Mac. The macOS bundle has been
built twice on two machines with byte-identical results, and read file by file. The same build
for Linux has been installed and driven as a brand-new user who had nothing else (§8). No
bundle has been configured with a real OAuth client, installed in Claude Desktop, or
authorized by a Google account. Nothing has been published, tagged or shared.

**Corrected 2026-09-24.** The beta's Google application is **External and In production**, and
its data-access verification is not yet complete. It is not a Testing application. §1, §3, §6,
§7 and §9 below, and the setup text Claude shows (`orivra/src/orivra/desktop/texts.py`), now
describe that application. The earlier text described a Testing application, with a test-user
list and a seven-day reconnection, and neither applies. No Google setting was changed to make
this correction.

This is **an additional way to install Orivra**, not a replacement. The bring-your-own-OAuth
command-line install in [`SETUP.md`](SETUP.md) stays as the **Advanced / Self-managed** path.
Both run the same product code, `mailweave` and `orivra` built from this tree, and both hold one
Google permission, `https://www.googleapis.com/auth/gmail.readonly`. That scope is a
code-level constant (`SERVER_SCOPES`), and neither path can widen it.

| | Desktop beta (this page) | Advanced / Self-managed ([`SETUP.md`](SETUP.md)) |
|---|---|---|
| Who it is for | people the organiser invites | anyone comfortable with a terminal |
| Terminal, JSON editing | none for the tester | yes |
| Google Cloud project | the organiser's (External, In production, verification incomplete) | your own |
| Python | shipped inside the extension | yours, via `uv` |
| Supported machines | Apple Silicon Macs, macOS 14 or later | anything that runs Python 3.12 |
| Permission | `gmail.readonly` only | `gmail.readonly` only |
| Authorization lasts | until revoked, or until Google stops accepting it (§3) | depends on your project's publishing status (§7) |
| Data | `~/Library/Application Support/Orivra Beta` | `~/.local/state/mailweave`, `~/.local/share/mailweave/models` |

The two installs keep separate data. Someone who uses both authorizes each one separately and
downloads the models twice.

---

## 1. What a tester needs

- An **Apple Silicon Mac on macOS 14 or later.** Every native binary in the bundle is arm64
  and needs at most macOS 14.0 (§8.B). Intel Macs, Windows and Linux are not supported by this
  bundle.
- **Claude Desktop** with desktop extensions allowed. An organisation's Claude Desktop policy
  can switch local extension installs off. The tester then cannot install it, and only that
  organisation's administrator can change this.
- The file **`Orivra-Beta-0.2.0-beta.1.mcpb`**, from the organiser. It is about 345 MB and
  unpacks to about 1.15 GB.
- The **Google account whose mail Orivra should read**. There is no test-user list: while the
  application is unverified, any account can pass Google's warning until 100 new users in
  total have connected (§3).
- About 1.2 GB of free disk space and a direct internet connection for the one-time model
  download (§10 explains why a proxy that inspects TLS will not work).

## 2. Install and set up

1. **Install the extension.** In Claude Desktop open **Settings → Extensions → Advanced
   settings**. Under **Extension Developer**, click **Install Extension…**, choose the `.mcpb`
   file, and follow the prompts. This menu path is Anthropic's own documentation for
   installing a local extension ([Claude Help Center][claude-local]). The extension is not
   from Anthropic's directory and carries no developer signature. Claude Desktop may say so
   before it installs it; that screen has not been observed yet (§8.E).
2. **Ask Claude to set it up.** In a new chat, write *"Set up Orivra."* Claude calls the
   extension's `orivra_setup` tool. Claude Desktop may first ask whether to allow it.
3. **Read the reply.** In one message it:
   - starts the model download (two models, 1.18 GB together, checked byte for byte against
     the digests this release was built with);
   - gives a Google link, with what the next screens will show and why (§3).
4. **Open the link in a browser on the same Mac** and sign in with the Google account.
   The link works for 5 minutes. Google sends its answer to a one-time listener on this Mac
   (`127.0.0.1`), so a phone or another computer cannot finish it.
5. **Go back to Claude and write *"Continue the Orivra setup."*** Each call reports what is
   done, the download's progress and what is left, and it starts any step that failed again.
   When Gmail is connected and the models are in place, it verifies the connection by
   starting the product, loading the models and asking Google who the account is. It then
   answers:
   - **Orivra is ready**;
   - the account;
   - the permission Google actually granted;
   - when Google granted the authorization, which has no expiry date;
   - the hosts Orivra contacts while answering;
   - where the interpreter runs from;
   - where the data lives.
6. **Ask a question** about your email, for example what was decided about a project and which
   messages say so. Every product tool is the same one the self-managed install serves. Before
   setup finishes, each of them says setup is not finished and names `orivra_setup`.

If a step fails, calling `orivra_setup` again is always the next move. A declined or expired
consent gets a new link. A failed download is started again, and a model file that fails its
digest check is downloaded again. If Google refuses a stored authorization, setup asks for
consent again rather than looping. An unreachable Gmail is reported as a retry, and it does not
ask for new consent.

## 3. What Google shows, and why

**The unverified-app warning.** Google shows its *unverified app* screen whenever an OAuth
client asks for sensitive or restricted scopes before its project has completed verification
for them ([Google][pub-status]). `gmail.readonly` is a restricted scope. The beta's application
is published (External, In production) and has not yet completed that verification, so every
tester sees the screen (§7). Google's own wording and layout can change, and they have
not been observed here. The setup text therefore does not quote them. It says only that the
screen offers either *Continue*, or *Advanced* followed by a link to the app.

**Who can get past it.** An app in production has no test-user list. Until verification is
complete, Google's user cap applies instead: *"100 new users in total, after the app presents
the unverified app screen"* ([Google][pub-status]). The cap counts accounts, not invitations.
Anyone who has the bundle and a Google account can connect until it is reached, which is one
more reason to share the bundle only privately (§6.1).

**The permission screen** asks for one permission: to read email messages and settings.
Orivra cannot send, delete, label or change anything.

**How long the authorization lasts.** No reconnection is scheduled. The seven-day expiry is a
Testing-status rule, and this application is not in Testing. A refresh token lasts until one
of the reasons Google lists applies ([Google][oauth2]):
- the user revokes the app's access;
- the token has not been used for six months;
- the user changes their password, because the token carries a Gmail scope;
- the account has too many live tokens;
- an administrator restricts the service.

When Google stops accepting it, the next question returns the product's own `reauthorise`
refusal, and the beta adds a note under it. The note says what happened, tells the tester to
call `orivra_setup` for a new link, and tells them to ignore the terminal instruction meant for
self-managed installs. The *ready* message states when access was granted, and that it has no
expiry date.

## 4. What stays on the Mac

- **The authorization** Google returns, a refresh token, is written to
  `~/Library/Application Support/Orivra Beta/state/credentials.json`, mode `0600`. It is never
  sent to the organiser or anyone else. A tester's token does not exist until that tester
  consents, on their own Mac, and the bundle carries none: the inspection fails any bundle
  that contains a credential or token file (§8.B).
- **The models** go to `~/Library/Application Support/Orivra Beta/models`.
- **Mail content** is read from Gmail when a question needs it and is not written to disk
  (`SECURITY_NOTES.md` §4.1). Nothing about the mail goes to the model host. The download is
  the only time Orivra contacts it.
- **While answering**, Orivra contacts only the Gmail and Google OAuth hosts in
  `RUNTIME_EGRESS_ALLOWLIST`.

## 5. Uninstall, and revoking access

1. Claude Desktop: **Settings → Extensions**, then remove Orivra.
2. Finder: **Go → Go to Folder…**, enter `~/Library/Application Support/Orivra Beta`, and move
   that folder to the Bin. It holds the authorization and the models, and removing the extension
   does not delete it.
3. Google Account: remove the beta's access under the account's third-party apps and services
   ([myaccount.google.com](https://myaccount.google.com)). This revokes the authorization at
   Google, whether or not the Mac still holds it.

---

## 6. For the organiser

The organiser runs these steps once per release, on their own machine. They need a terminal.
The tester's steps above do not.

### 6.1 Build, inspect, configure

The build needs:

- `uv`;
- CPython **3.12.14**, the release the bundle ships (`uv python install 3.12.14`);
- network access to PyPI;
- the pinned runtime archive from python-build-standalone release `20260901`,
  `cpython-3.12.14+20260901-aarch64-apple-darwin-install_only_stripped.tar.gz`, whose sha256 is
  in `tools/desktop/python-runtime.json`.

```sh
python3 tools/desktop/build_bundle.py --platform darwin-arm64 \
    --python-archive <path to that archive> --out dist/desktop \
    --build-python "$(uv python find 3.12.14)"

python3 tools/desktop/inspect_bundle.py \
    dist/desktop/orivra-beta-0.2.0-beta.1-darwin-arm64-unconfigured.mcpb --expect darwin-arm64

python3 tools/desktop/configure_bundle.py \
    --bundle dist/desktop/orivra-beta-0.2.0-beta.1-darwin-arm64-unconfigured.mcpb \
    --client mailweave-server-oauth.json \
    --refuse mailweave-harness-oauth.json \
    --out dist/desktop/Orivra-Beta-0.2.0-beta.1.mcpb
```

What each step does:

- **`build_bundle.py`** writes an *unconfigured* bundle: no OAuth client, no credential, no
  token.
  - It checks the runtime archive's digest.
  - It installs every dependency for macOS arm64 from the committed `uv.lock`, with its hashes.
  - It builds `mailweave` and `orivra` from this tree.
  - It byte-compiles with the bundled Python release and refuses any other.
  - It keeps each `RECORD` true to the files the bundle carries.
  - It writes a zip with regular files only: the MCPB unpacker cannot open directory entries,
    and the zip carries no symlinks.

  `dist/` is gitignored. For this tree the unconfigured bundle's sha256 is
  `f6e0bd882463e0b7ec35e22f02ad37e6bec8a943db4d50fa1360ec05f1baade3` (§8.C).
- **`inspect_bundle.py`** reads the bundle without running it. It fails on:
  - a Mach-O without an arm64 slice, an arm64 slice with no code signature attached, or one
    that needs a macOS later than 14.0;
  - a Linux binary;
  - a credential file, a symlink or a directory entry;
  - a path of the machine that built it.
- **`configure_bundle.py`** adds one file, `server/config/oauth-client.json`, at mode `0600`.
  It refuses:
  - a client that is not a Desktop-app client;
  - a bundle that already has a client;
  - a client with the same id as any `--refuse` file.

  The harness client is passed as `--refuse` because it may only ever authenticate the test
  mailbox. The script prints the client id, the output path and the sha256, and never the
  secret.

The client file contains the Desktop-app client id and its client secret. For installed
applications Google's position is that *"it is assumed that these apps cannot keep secrets"*
([Google][native-app]) and that the client secret *"is obviously not treated as a secret"*
([Google][oauth2]). Anyone with the bundle can read them. **Share the configured bundle only
with invited testers, directly, and not at a public link.** The client alone authorizes nobody:
Google still requires the tester's own consent. The project is in production, though, so no
test-user list stands between the bundle and any Google account. The only limit is the
100-new-user cap (§3).

### 6.2 Google Cloud console: the organiser's own actions

These are settings on the organiser's Google project. Nothing in this repository changes them,
and none was changed while building this beta.

- The client is a **Desktop app** OAuth client in a project with the **Gmail API** enabled.
- The OAuth consent screen is **External**, publishing status **In production**, and
  data-access verification is **not yet complete** (as of 2026-09-24). The tester-facing text
  in `orivra/src/orivra/desktop/texts.py` states this in two places:
  - Google shows the unverified-app screen and caps new users at 100;
  - the authorization has no scheduled expiry.

  Completing verification removes the screen and the cap, which would make the first
  statement out of date. Moving the project back to Testing would make both statements false.
- **No test users to add.** In production, the test-user list does not decide who can connect.
  The bundle's distribution and the user cap are the limits.

### 6.3 Which client the bundle carries

Decided 2026-09-24: `mailweave-server-oauth.json`, the read-only server client. Its project is
External and In production, with verification incomplete. `configure_bundle.py` refuses the
harness client, which may only ever authenticate the test mailbox. The publishing status is a
console setting and cannot be read from the client file; it is recorded here as the organiser
stated it.

---

## 7. Google's rules: Testing, production, personal use

The quotations are from Google's pages as read on 2026-09-23. Google changes these pages.

| | Who can authorize | Warning screen | Authorization lifetime | Verification |
|---|---|---|---|---|
| **Testing** | only the listed test users, up to 100 | unverified app screen | **7 days** from consent | not required while in testing |
| **In production, unverified** (this beta, 2026-09-24) | anyone who reaches consent, until 100 new users in total | unverified app screen | until revoked or otherwise invalidated | required before a public launch, unless an exception applies |
| **In production, verified** | anyone | none | until revoked or otherwise invalidated | done, and reassessed at least every 12 months |

- **Testing.** *"Projects configured with a publishing status of Testing are limited to up to
  100 test users listed in the OAuth consent screen."* *"Authorizations by a test user will
  expire seven days from the time of consent."* ([Google][pub-status]) *"Apps in
  development/testing/staging mode are not subject to verification."* *"Your app will be
  subject to the unverified app screen and the 100-user cap will be in effect when an app is in
  development/testing/staging."* ([Google][not-needed]) *"if your app is experimental or a test
  build, you don't need to go through verification unless you decide to launch it to the
  public"* ([Google][unverified]).
- **The user cap.** *"The user cap limits the number of users that can grant permission to your
  app when requesting unapproved sensitive or restricted scopes"*: *"100 new users in total,
  after the app presents the unverified app screen"* ([Google][pub-status]).
- **Verification and the security assessment.** *"If your app requests sensitive or
  restricted scopes, you need to complete the verification process unless your app's use
  qualifies for an exception."* *"Every app that requests access to Google users' restricted
  data and has the ability to access data from or through a third-party server must go through
  a security assessment."* Reassessment happens *"at least every 12 months"*
  ([Google][restricted]).
- **Exceptions.** Google lists these:
  - personal use: *"If you are the only user of your app or if your app is used by only a few
    users, all of whom are known personally to you"* ([Google][restricted]). The help page
    words it as *"If the app is for your personal use (fewer than 100 users), you and your
    limited number of users can continue using the app without going through verification"*
    ([Google][not-needed]);
  - development, testing or staging;
  - internal use within a Google Workspace or Cloud Identity organisation;
  - apps that access only their own data through a service account.

**What this means for each path.**

- **The desktop beta** is in the *In production, unverified* row.
  - Testers see the unverified-app screen.
  - At most 100 new users can connect in total.
  - No seven-day expiry applies.
  - Offering the beta to the public needs restricted-scope verification.

  Until that is done, keeping it to a few people known personally is what Google's personal-use
  exception describes. Whether a use qualifies is Google's judgment.
- **Creating your own Google Cloud project does not bypass verification.** In the
  self-managed path each person is the developer of their own OAuth app, and every rule above
  applies to that app:
  - in Testing, their own authorization also expires every 7 days;
  - in production and unverified, they see the same warning and have the same cap;
  - they are exempt from verification only if their use qualifies for one of Google's
    exceptions, such as personal use. Whether a use qualifies is Google's judgment.

  What the self-managed path changes is who operates the app, not which rules apply. The
  Limited Use requirements of Google's user-data policy apply either way (`SECURITY_NOTES.md`
  §2.4).

---

## 8. What has been proven, and where

### 8.A A brand-new Linux user with nothing else (cloud sandbox, 2026-09-23)

`tools/desktop/prove_clean_install.py` ran the Linux build of the same bundle. That build is
identical except that it has the Linux interpreter and binaries and is built without the
semantic dependencies (`torch` and its stack). The
report is `docs/reviews/desktop-beta-2026-09-23/cleanroom-report.json`. The script:

1. created a fresh Unix account with an empty home;
2. configured the bundle with a **placeholder** client that Google will not accept;
3. unpacked it with the official `mcpb unpack` (`@anthropic-ai/mcpb` 2.1.2);
4. spoke MCP to the launcher exactly as the manifest's `mcp_config` says, with an environment
   of `HOME`, `PATH=/usr/bin:/bin` and `LANG` only.

Observed:

- **Nothing of the builder was available.** The account could not read:
  - the repository or its virtual environment;
  - the Python driving the proof;
  - `/home/claude`, `/root` or `/root/.cache`.

  It had no uv cache and no models. The script checks this first and stops if any of them is
  readable. The builder's home was made owner-only for the run and restored afterwards.
- **The extension ran from its own files.**
  - Every Python process the account was running when processes were listed ran the bundled
    `python3.12 -I`: the server and the product's consent command. The download command had
    already failed and exited by then.
  - `sys.path`, `mailweave.__file__` and `orivra.__file__` were all inside the unpacked
    extension.
  - No process mapped a file outside the account's home, which holds the extension, and the
    system's own libraries.
- **The surface** was the product's 8 tools plus `orivra_setup`. `orivra_ask` called before
  setup returned an error naming `orivra_setup`.
- **The consent link** pointed at `accounts.google.com/o/oauth2/v2/auth`. It carried:
  - the bundle's client id;
  - exactly `gmail.readonly`;
  - a `127.0.0.1` redirect;
  - PKCE `S256`;
  - `access_type=offline` and `prompt=consent`.

  It came with the explanation in §3.
- **A declined consent** was delivered to that loopback as the browser would deliver it
  (`error=access_denied`). The next `orivra_setup` reported the refusal and issued a new link.
- **The model download** started as the product's own `mailweave setup-models --events`. It
  failed as a reported step: the sandbox intercepts TLS and the product refuses the chain with
  `CERTIFICATE_VERIFY_FAILED`. The next call started it again. It did not crash.

### 8.B The macOS bundle, read without running it

`inspect_bundle.py --expect darwin-arm64` read the bundle with no problems found:

| Check | Result |
|---|---|
| Mach-O files | every one has an arm64 slice, and every arm64 slice has a code signature attached |
| Slices | 239 arm64, 7 x86_64 |
| Universal files | 7 universal2 files from `lxml`, each with an arm64 slice; one fat file in `scipy` with only an arm64 slice |
| Minimum macOS | 14.0, the highest any arm64 slice states (in `numpy`, `scipy` and `torch`) |
| Linux binaries | none |
| Credential, token or `.env` files | none |
| Symlinks, directory entries | none |
| OAuth client | none |
| Build machine's paths | none |
| Tools | the same 9 in the manifest |

Size: 344,380,808 bytes zipped, 37,649 files, 1,152,607,197 bytes unpacked. `torch` is 574 MB of
that.

### 8.C Two builds, two machines, the same bytes

The unconfigured macOS bundle was built on two machines:

- the cloud sandbox: x86_64 Linux, uv 0.8.17;
- the Linux VM on the owner's Mac: aarch64, uv 0.12.13, working from `git archive HEAD` plus
  this change.

Both used CPython 3.12.14. The two `.mcpb` files are byte-identical, sha256 `f6e0bd88…aade3`.
Getting there found three defects in the build, now fixed and tested
(`docs/reviews/desktop-beta-2026-09-23/reproducible-builds.json`):

1. Before any comparison, the inspector found `direct_url.json` in the two workspace packages
   naming the build directory.
2. The first comparison differed in 21 entries other than bytecode:
   - 18 `RECORD` files listed console scripts the bundle drops. Their hashes cover the build
     interpreter's path;
   - uv's `.lock` and two `uv_cache.json` files shipped.
3. The second comparison matched in all 25,254 other entries, but all 12,395 `.pyc` files
   differed. They had been compiled by 3.12.3 on one machine and 3.12.14 on the other. The
   builder now refuses any `--build-python` other than the bundled release.

### 8.D Offline tests

- `tests/test_desktop_beta.py` covers the flow, the surface, the reauthorise note and both
  `--events` commands.
- `tests/test_desktop_bundle_tools.py` covers:
  - the tool list's sync with the product;
  - `configure_bundle`'s refusals and its `0600` entry;
  - the zip's file-only rule;
  - `RECORD` pruning;
  - each inspector check.

  Six of its rules were broken one at a time, and a test failed each time.

### 8.E Not proven yet: the acceptance run on a Mac

No macOS binary has run, and no Google consent or model download has completed, because none
of the environments available here can do either:

- macOS executables cannot run in them;
- the sandbox cannot reach Google's or Hugging Face's hosts without TLS interception.

Checklist for the first Mac run, best done in a **fresh macOS user account** with a Google
account of the organiser's choosing, so the Mac itself is as clean as §8.A's account was:

1. Install through Settings → Extensions → Install Extension…, and record every prompt
   Claude Desktop shows, including anything about the missing signature.
2. Record whether macOS shows any Gatekeeper or quarantine prompt when the interpreter first
   starts (§10).
3. *"Set up Orivra"*. The link opens in the browser. Record Google's unverified-app screen and
   permission screen as they actually appear.
4. The download runs to completion with progress. Record the time.
5. *"Orivra is ready"*. Check that it shows:
   - the right account;
   - only `gmail.readonly`;
   - the grant time, with no expiry date;
   - the installation facts: the interpreter inside the extension, and every import path
     inside it.
6. Ask one question and check that its evidence comes from that mailbox.
7. Optional: revoke the app's access from the Google account. The next question shows the
   reauthorise note, and `orivra_setup` issues a new link.
8. Uninstall as in §5 and check that nothing is left outside the data folder.

## 9. Manual steps that cannot be removed

- **The organiser**:
  - builds and configures each release (§6.1), which needs a terminal on the organiser's
    machine, once;
  - shares the file privately. In production, with no test-user list, private
    distribution and the 100-new-user cap are the only limits on who can connect (§6.2).
- **Which client:** the server client, decided 2026-09-24 (§6.3).
- **The tester**:
  - installs from Claude Desktop's settings and accepts its prompts;
  - consents in a browser on the same Mac, which means passing Google's unverified-app
    screen;
  - reconnects only if Google stops accepting the authorization (§3). Nothing is
    scheduled.
- **Possibly**, a macOS prompt the first time the unsigned, un-notarized interpreter runs.
  Whether one appears is not known until §8.E.

## 10. Known limitations

- **Not signed with an Apple Developer ID and not notarized.** The binaries carry only the
  signatures their builders' linkers attached. Notarization needs a paid Apple Developer
  Program membership, which is a purchase and has not been approved.
- **Size.** A 345 MB download, 1.15 GB installed, plus 1.18 GB of models. Most of it is the
  semantic stack the product already locks (`torch`, `transformers`, `scipy`).
- **Proxies.** The product sets its own HTTP transport, so it ignores system proxy settings.
  On a network that intercepts TLS, the product refuses the intercepted certificate chain. §8.A
  observed this for the model download. The same check applies to its calls to Google, which
  were not reached there.
- **Apple Silicon only**, macOS 14 or later.
- **Separate from a self-managed install** on the same Mac: separate authorization, separate
  models.

[claude-local]: https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop
[pub-status]: https://support.google.com/cloud/answer/15549945
[not-needed]: https://support.google.com/cloud/answer/13464323
[unverified]: https://support.google.com/cloud/answer/7454865
[restricted]: https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification
[oauth2]: https://developers.google.com/identity/protocols/oauth2
[native-app]: https://developers.google.com/identity/protocols/oauth2/native-app
