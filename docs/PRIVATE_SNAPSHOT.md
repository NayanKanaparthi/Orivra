# Private initial source snapshot

**Historical import record.** This describes the initial `ac84704` snapshot. The owner later
selected MIT; see [the licensing record](reviews/MIT_LICENSING_2026-09-24.md) for the subsequent
source and installer changes. Neither step made the repository public.

This repository starts with a new, parentless commit. It does not import the development
repository's Git history, branches, or tags. It is a private source backup and review
checkpoint, not a public release or an approval to redistribute the desktop installer.

## Source and scope

Copied from development revision `98e44ba2c6627aab78f6dad131abec0e6b9c641b`, including the
current working-tree changes to the MailWeave search description, desktop tool list, matching
surface test, README, setup guides, and prepared release documents. Product and test files
were copied byte-for-byte; no retrieval, authentication, or packaging behavior was changed
while making this snapshot.

The separate candidate installer is identified in `releases/0.2.0-beta.1.md` and
`releases/SHA256SUMS`. It has not been uploaded to this repository. Its source inputs are
documented separately there; this snapshot does not pretend the installer was rebuilt from
this new commit.

Excluded from this snapshot:

- Both real OAuth client JSON files, user tokens, local state, and configuration.
- Original Git history and tags, including the commits that held OAuth client files.
- Installers, downloaded models, environments, scratch files, and private transcripts/logs.
- Live validation JSON records and the preserved PF-5 smoke log.
- Marketing drafts/assets and the internal root handoff notes.

Existing content-free validation summaries and review documents remain historical records.
References in them to excluded artifacts or old development commits require the original
private development checkout; this snapshot does not supply or recreate those artifacts.
Content-free preflight measurements needed by the runtime and regression tests are retained,
including the two explicitly invalidated historical fixtures. They contain counts/timings,
not message bodies, header values, or user authorization tokens. Their existing caveats and
verdicts are unchanged.

## What this does not settle

The private upload does not make the product public, change distribution terms, satisfy
Google's data-access verification, or establish that every release gate passes. The installer
still has its existing distribution restrictions. No Google Cloud settings were changed.
