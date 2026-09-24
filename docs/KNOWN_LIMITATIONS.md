# MailWeave beta: what to know before connecting

These notes apply to Orivra / MailWeave `0.2.0-beta.1`. A beta label does not guarantee
reliability, Google approval, or suitability for sensitive work.

## Compatibility and setup

- The desktop installer supports **Apple Silicon Macs running macOS 14 or later** and Claude
  Desktop with custom extensions allowed. It does not support Intel Macs, Windows, or Linux.
- The download is about 346 MB. The unpacked extension uses about 1.16 GB and the retrieval
  models about 1.27 GB, plus temporary installation space. First setup downloads those models.
- Gmail and Google authorization require an internet connection. This is not an offline
  email assistant. Only Gmail is connected; Slack and Google Drive are not included.
- The [self-managed command-line path](SETUP.md) remains available. It uses your own Google
  project and OAuth client, subject to Google's requirements.

## Google authorization

The shared Google app's Gmail data-access verification is incomplete on the evidence currently
available. The published, unverified configuration can display an unverified-app warning and
has a **100-total-user cap**, not 100 new places every month. We have not checked the remaining
places. A workplace administrator or account policy may block authorization entirely.

If Google offers a continuation choice, review the app, account, permission, and privacy policy
before deciding whether to proceed. A user's consent does not satisfy the developer's
verification obligations. Do not disable account or operating-system protections to connect.
See [Google's app-state documentation](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview).
There is no claim of Google approval or a verification exception.

## Email and privacy

The connector requests `gmail.readonly`; it cannot send, delete, archive, or relabel mail.
Read-only still permits access to sensitive content. **Selected email evidence goes to Claude
and is processed by Anthropic.** Review your account's retention and model-improvement settings
and any workplace restrictions before connecting.

Your authorization token is stored in an owner-readable local file, not an app-encrypted vault.
The installer contains the app's Desktop OAuth configuration, not a user's Gmail token.
Never upload the extension's data directory, tokens, raw mail results, or unredacted logs to
an issue. Revoking Google access does not delete existing Claude conversations.
See the [privacy policy](https://www.nayankanaparthi.dev/orivra/privacy).

## Answers and reliability

Queries can fail, take time, or return partial evidence. An omitted message does not mean it
does not exist. Claude can misinterpret correctly retrieved evidence; verify important claims
against their cited messages. Gmail receipt time is not necessarily the time a message was
written, and a From header is not authenticated identity.

Live checks have covered a small seeded mailbox, not a representative range of users and
mailboxes. No measured accuracy or speed advantage, complete mailbox coverage, or additional
benefit from the graph is claimed. Do not rely on this preview alone for consequential decisions.

## Engineering status

Repository-wide CI is not green. The launch preparation distinguishes findings in the shipped
product from findings in the separate harness, tests, and developer tooling; it does not
silently disable those checks or mark unverified release criteria PASS. Runtime network-boundary
verification PF-5(b) remains open. Existing offline tests are not a substitute for that check.
The [launch packet](releases/LAUNCH_PACKET_0.2.0-beta.1.md) records the exact candidate and results.

For help, email [kanaparthinayan@gmail.com](mailto:kanaparthinayan@gmail.com) with the version,
macOS version, the step that failed, and a redacted error. Report suspected privacy or security
problems privately by email, not in a public issue.
