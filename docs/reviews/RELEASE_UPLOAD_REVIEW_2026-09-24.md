# Release upload review — 2026-09-24

## Decision for this preparation

**Documents prepared locally; no upload or public-release approval.** The owner authorized
README, installation, release-note, and upload-review work. No product code, build input,
installer, OAuth setting, credential, Git ref, remote, repository visibility, or website was
changed. Nothing was staged, committed, tagged, pushed, or submitted to Google.

Target: [NayanKanaparthi/Orivra](https://github.com/NayanKanaparthi/Orivra). The authenticated
repository read showed a private, empty repository, default branch `main`, no licence. The
preceding branch and release reads returned empty lists. The local checkout has no remote.
The repository description already expresses the broader Orivra product vision; it was not
changed to a Gmail-only description.

## Prepared files

- `README.md`: product overview, MailWeave as the first connector, explicit beta availability,
  the two installation paths, and privacy/claim limits.
- `docs/INSTALL_DESKTOP_BETA.md`: user-facing install, consent, first query, troubleshooting,
  disconnect, and optional checksum instructions.
- `docs/releases/0.2.0-beta.1.md`: draft release notes, exact artifact identity, build inputs,
  and publication caveats.
- `docs/releases/SHA256SUMS`: checksum of the existing configured installer.
- `docs/DESKTOP_BETA.md`: a new current-status preface; original engineering observations,
  historic hashes, and results preserved below it.
- `docs/SETUP.md`: only the opening link to the new desktop guide changed; the self-managed
  procedure remains in place.
- This review.

The release-note draft is a local Markdown file, **not a GitHub draft release**. The binary
has not been rebuilt or copied into tracked source. These documents do not create a public
download link, change the licence, or approve an earlier release deferral.

## Candidate binary: checked, unchanged

File: `dist/desktop/Orivra-Beta-0.2.0-beta.1.mcpb`.

- Size: **346,486,371 bytes**; SHA-256:
  `2edd449db7da45caae3aa7ab66c237b3737f2721c368d68821b06317c87a97cc`.
- 38,219 archive entries; 1,158,051,980 bytes unpacked. The packaged model lock names
  1,265,572,626 bytes of model files for the separate setup download.
- `tools.desktop.inspect_bundle.inspect`: no problems; every native Mach-O contains an
  arm64 slice, each arm64 slice has an attached signature, highest declared macOS minimum
  14.0, no ELF files. An attached signature is not proof of notarization or directory review.
- All **169 product `.py` files** in the archive match the current `mailweave` and `orivra`
  source files byte-for-byte. The manifest tool list matches the working-tree `tools.json`.
  This comparison does not independently revalidate every dependency or compiled `.pyc`.
- `server/config/oauth-client.json` matches the intended server client's file byte-for-byte.
  Known current development and extension refresh-token values, and the harness client ID
  and secret, were absent from every archive entry scanned. No raw values are recorded here.
- Generic pattern hits in dependencies were inspected: the OpenSSH marker is a serialization
  delimiter constant in `cryptography` (and its compiled bytecode); the GitHub-token-like
  substrings are parts of `highs_...` C++ symbols in SciPy's native module. That module's bytes
  match its installed `RECORD` digest. These are not identified live tokens.

The installed-app client ID and `client_secret` field are intentionally extractable. Google
[documents embedding installed-app client values](https://developers.google.com/identity/protocols/oauth2#installed).
They are not a user's mailbox authorization. This does **not** imply that refresh tokens,
web-app secrets, or the separate harness configuration belong in a public release.

The owner's successful Mac installation/setup is **owner-reported**. It is not recast as a
fresh-account/clean-machine acceptance run, and no additional mailbox test was run here.

## Source provenance and history: do not push blindly

Base HEAD remains `98e44ba2c6627aab78f6dad131abec0e6b9c641b`. The binary also includes two
pre-existing, uncommitted build inputs:

| File | SHA-256 |
|---|---|
| `server/src/mailweave/surface/tools.py` | `4380b2d3c6cb65beb713988e0e6581c814450aea3ecc24709a201691a0034780` |
| `tools/desktop/bundle/tools.json` | `f0e458ffee0a308a2be5064eed998f6909aaece348987f1d9725c43163be34e9` |

An upload/tag must identify those inputs accurately. Do not tag the base commit alone as the
complete source of this binary. The modified `tests/test_mcp_surface_round24.py` and all
existing marketing work belong to the owner and were not altered or implicitly included.

The targeted scan covered **703 tracked working-tree files** and **2,169 reachable blobs**
from `git rev-list --objects --all`. It compared actual current client/token markers and common
credential shapes without printing values. No known current client or token value matched the
tracked working-tree files. Generic matches there were confined to tests and a documented
synthetic-canary report; this is not a general privacy clearance for every document.

Two historical blobs still contain the known current OAuth client values:

| Historical path | Blob |
|---|---|
| `mailweave-harness-oauth.json` | `34798b456543ed6aefca1c3ca12ce36574b5ff18` |
| `mailweave-server-oauth.json` | `a455f6c36dc335c56ef161bfa15cfe99188f7d33` |

Neither known current refresh token was found in those reachable blobs. This is a targeted
scan, not proof that every possible old credential or personal record is absent. Reachable
blobs are not every local Git object, and commit/tag message contents were not scanned.

**Proposed source-publication route, not executed:** prepare a separate, reviewed clean
snapshot for the new repository while preserving this development checkout and its history.
The alternative is an explicitly approved history sanitization. Either needs the owner's
choice; no orphan branch, history rewrite, credential rotation, or retirement was performed.
Historical live-run evidence remains unchanged and is not automatically cleared for public
upload by this scan.

## Proposed upload boundaries

| Destination | Proposed contents | Current state |
|---|---|---|
| GitHub release assets | Exact approved `.mcpb` plus `SHA256SUMS` | Local only; candidate has private-beta terms |
| Release description | Reviewed draft release notes | Local only |
| Repository source | Owner-approved source snapshot/clean history, accurate build inputs, setup docs, applicable notices | Selection and history decision not executed |
| Excluded by default | Credential/token stores, harness OAuth JSON, `.env`, local models/caches, `.venv`, `_to_delete/`, `Claude outputs/`, private transcripts/logs, unrelated marketing drafts | Not uploaded |

Do not run a bulk add/push of the working folder or its existing refs. `.gitignore` does not
remove files already present in history. GitHub supports installer binaries as
[release assets](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases);
the installer should not be committed as ordinary source.

## Outstanding publication decisions, not new product repairs

1. **Distribution terms and package label.** The current manifest's display name is
   `Orivra (invite-only beta)`; its licence field is
   `Proprietary - invite-only beta; not for redistribution`. There is no repository-wide
   `LICENSE`/`COPYING` file. Do not label the source open-source or silently replace these
   terms. The owner must choose the intended public source/binary terms. Any corresponding
   manifest change is a separately approved packaging change with a new artifact checksum.
   Third-party licence compliance was not comprehensively audited in this preparation.
2. **Source-publication route and exact release inputs.** Resolve the history choice above
   and include the two intended source changes in the approved release source state. No tag
   name or commit has been created.
3. **Google data-access status and public distribution.** The last supplied evidence says
   External / In production, branding published, Gmail data access unverified. Working
   OAuth consent does not close that review; the unverified user cap is not blanket approval
   for public distribution. Selected evidence goes to Claude, so no local-only assessment
   exemption is asserted. Follow
   [Google's restricted-scope requirements](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification).
4. **Owner release approval.** Older release gates/deferral decisions have not been silently
   waived. This document is an upload-preparation review, not a replacement acceptance verdict
   or authorization to publish. The website download link and public visibility stay unchanged.

## Verification of this documentation change

- The two desktop regression files ran locally: **34 tests passed**, exit 0.
- No full-suite run, benchmark, live mailbox call, dependency upgrade, or rebuild was needed
  or performed for the documentation work. Historical test totals were not relabelled as a
  fresh full-suite result.
- The installer checksum was checked against `docs/releases/SHA256SUMS` and still matches.
- All 17 relative Markdown links in the seven prepared/updated files resolve locally;
  code fences, final newlines, and trailing-whitespace checks passed. External documentation
  for Claude's install path, GitHub release assets, and installed-app OAuth was read; this
  is not a blanket availability check of every external link.
- `git diff --check` passed. All **319 pre-existing modified/untracked files** remained
  byte-identical by a sorted path/SHA-256 inventory comparison, including marketing and the
  three modified source/test/tool-list files. HEAD and the empty staging area are unchanged.

The temporary value-redacting audit helper is in gitignored `_to_delete/`; it is not a proposed
release file. It reads current credentials in memory only for exact-match exclusion checks and
prints labels, paths, and hashes, never credential values.
