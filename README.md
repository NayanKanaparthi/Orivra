# Orivra

Helping AI agents navigate large information spaces, find the right evidence, and understand
what happened and why.

Finding a useful answer is not just about matching a search term. An agent needs to locate
relevant information, follow the relationships around it, and recognize when it has only part
of the picture. Orivra is being built to make that navigation possible, with evidence the agent
can cite and limits it can explain.

## Start with MailWeave

**MailWeave is Orivra's first connector: read-only Gmail retrieval for AI assistants.**
This beta packages it with Orivra as a Claude Desktop extension. Gmail is the only connected
source in this release; other sources are not included.

Use it to ask questions such as:

- What was decided about a project, and which messages explain the reasons?
- Did a later message replace the earlier plan?
- What information is still missing before I can act?

MailWeave searches mail, maps conversations, and lets the agent read specific messages in more
detail. Responses include message references, reply relationships, and available Gmail receipt
timestamps. When a response leaves evidence out because of a limit, it describes the omission
and available follow-up. Orivra also exposes query-time evidence graphs for inspection and
further navigation. These are product capabilities, not a guarantee that an assistant's answer
is correct or complete.

## Install

**Release status: preparation only. There is no public installer release yet.** The owner has
reported successful installation and setup of the configured beta on their Mac. Public
distribution has not been approved, and Google's Gmail data-access verification is incomplete.

- **Claude Desktop extension:** Apple Silicon Mac, macOS 14 or later. Python and the app's
  Google OAuth client are included; users do not need Terminal or their own Google Cloud
  project. Follow the [desktop installation guide](docs/INSTALL_DESKTOP_BETA.md) if you have
  received the beta installer.
- **Advanced / Self-managed:** run from source with your own Google Cloud project and Desktop
  OAuth client. The [command-line setup guide](docs/SETUP.md) remains available. Google's
  requirements still apply to your project.

The intended download destination is this repository's
[Releases page](https://github.com/NayanKanaparthi/Orivra/releases). No asset is available there
yet; do not treat a source-code archive as the desktop installer.

## Your mail and your permissions

- MailWeave requests only `gmail.readonly`. It cannot send, delete, relabel, or modify mail.
- You authorize your own Google account. The installer contains the app's Desktop OAuth
  client, not the developer's Gmail access token or an authorization to read their mailbox.
- The connector and retrieval models run on your Mac. Selected email evidence is returned
  to Claude and processed by Anthropic to answer your question. **This is not a fully offline
  or device-only AI assistant.**
- The extension stores its refresh token in a local owner-readable file, not an encrypted
  application vault. Keep its data folder private. Revoking access in Google stops future
  access; it does not remove evidence already included in a Claude conversation.

Read the [privacy policy](https://www.nayankanaparthi.dev/orivra/privacy) and
[terms](https://www.nayankanaparthi.dev/orivra/terms) before connecting a mailbox.

## Beta limitations

Search and reading have limits; a partial response is not proof that no other relevant mail
exists. Gmail receipt time is not necessarily the time a message was written. A From header is
not an authenticated identity. Review cited evidence before relying on an answer.

This release makes no measured speed or accuracy advantage claim over another connector, and
no claim that the graph improves answer quality. The existing live checks cover a small seeded
mailbox, not general acceptance across users' mailboxes. See the
[recorded live-run scope](docs/FEATURE_FREEZE_2026-09-23.md).

The packaged Google app is External / In production, with data-access verification incomplete.
Google may show an unverified-app warning, enforce its user cap, or restrict access through
account policy. The cap is not a public-launch exemption. See
[Google's verification requirements](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification).

## For developers

From a checkout with Python 3.12 and [uv](https://docs.astral.sh/uv/):

```sh
uv sync --all-packages --extra dev
make test
```

Dependency installation needs network access unless dependencies are already cached. The
default tests use synthetic fixtures and deny sockets; they need no Gmail credentials.
`make check` also runs lint, formatting, types, guards, and evaluation gates. These are commands
to run, not a claim that every gate currently passes.

The repository contains `orivra/` (evidence navigation and desktop setup), `server/` (MailWeave),
`harness/` (separate development/evaluation tooling, not installed in the extension), `tests/`,
`tools/`, and `docs/`.

The [desktop engineering notes](docs/DESKTOP_BETA.md) describe packaging and historical checks.
[Draft release notes](docs/releases/0.2.0-beta.1.md) identify the exact candidate artifact.
Public source/distribution terms are pending owner approval; no open-source licence is claimed.

## Contact

[Product website](https://www.nayankanaparthi.dev/orivra) ·
[kanaparthinayan@gmail.com](mailto:kanaparthinayan@gmail.com)

For support, share a redacted error and the version you installed. Never post tokens, OAuth
JSON files, private email, or your extension data folder in a public issue.
