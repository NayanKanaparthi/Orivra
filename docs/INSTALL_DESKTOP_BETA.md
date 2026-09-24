# Install MailWeave through the Orivra desktop beta

This is the no-Terminal path for Claude Desktop. You do not create a Google Cloud project,
download an OAuth JSON file, or install Python yourself.

**Availability:** [MailWeave 0.2.0-beta.1 is a public experimental prerelease](https://github.com/NayanKanaparthi/Orivra/releases/tag/v0.2.0-beta.1),
licensed under MIT. Google data-access verification remains incomplete. The owner reported
successful installation and setup of the earlier build; the MIT build's executable product
contents are unchanged and its packaged startup was checked separately, not reinstalled in
Claude Desktop. See the verification record below for the limits of these checks.

Read the [known limitations](KNOWN_LIMITATIONS.md) before connecting. The
[launch packet](releases/LAUNCH_PACKET_0.2.0-beta.1.md) identifies the exact MIT candidate and
its verification results; do not use the older invite-only installer's checksum.

## Before you start

- An **Apple Silicon Mac (M-series), running macOS 14 or later**. This installer does not
  support Intel Macs, Windows, or Linux.
- Claude Desktop with custom extensions allowed. A managed account may require administrator
  approval.
- The Gmail account you want to connect, and an internet connection.
- Space for a 346 MB installer, about 1.16 GB unpacked, and about 1.27 GB of downloaded models
  (decimal units). Allow additional temporary space during installation and downloads.

Download **`Orivra-Beta-0.2.0-beta.1.mcpb`** and its `SHA256SUMS` companion from the
[beta release](https://github.com/NayanKanaparthi/Orivra/releases/tag/v0.2.0-beta.1).
Do not download a similarly named file from an unrelated repository. The source ZIP is not
the installer.

Read the [privacy policy](https://www.nayankanaparthi.dev/orivra/privacy) and
[terms](https://www.nayankanaparthi.dev/orivra/terms). The connector runs locally, but the email
evidence it returns goes into Claude's conversation and is processed by Anthropic.

## 1. Install the file

In Claude Desktop, open **Settings → Extensions → Advanced settings**. Under **Extension
Developer**, choose **Install Extension…**, select the `.mcpb` file, and follow the prompts.
This is Anthropic's [custom-extension installation path](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop).

The MIT candidate displays **“Orivra (beta)”**. It is a custom extension, not
a claim of Anthropic-directory review or Apple notarization. If installation is blocked by a
security policy, contact the maintainer or your administrator; do not disable OS protections.

If you already use a development or self-managed Orivra server, turn that connector off for
this chat so Claude does not see duplicate tool names. You do not need to delete its files.

## 2. Connect your Gmail

Open a new Claude chat with the extension enabled and send:

> Set up Orivra.

Allow the setup tool if Claude asks. Its response provides a Google authorization link and
starts the retrieval-model download.

Open the link **in a browser on the same Mac**, sign in to the Gmail account you want to use,
and review the requested permission: **read your email messages and settings**
(`gmail.readonly`). MailWeave cannot send, delete, or change mail. Never enter a Google
password or paste an authorization token into the chat.

The app's Gmail data-access verification is incomplete. Google may show an unverified-app
warning. Continue only if you understand and accept the beta's access and data handling; if
Google or your administrator blocks access, stop and contact support. The unverified user cap
does not mean Google has approved public distribution.

The link lasts five minutes. After the consent page confirms receipt, return to the chat.

## 3. Finish setup

Send:

> Continue the Orivra setup.

The tool reports download progress and what remains. Let the download finish and repeat that
message if necessary. It is safe to call setup again; do not reinstall just because a download
is still running.

Wait for **“Orivra is ready”** and check that it names the correct Gmail account and the
read-only permission. The setup also checks that the local retrieval models load.

There is no scheduled seven-day reconnection for this app's current production publishing
status. Google can still invalidate or revoke access. If reconnection is needed, ask Claude to
set up Orivra again. Access tokens are short-lived and are refreshed by the connector.

## 4. Ask a real question

For example, replace the bracketed words with a project in your own mail:

> Using Orivra / MailWeave, what was the latest decision about [project name], and why?
> Cite the supporting messages. Separate explicit statements from inference and say what
> evidence is missing.

For a first check, disable other mail connectors in that chat and confirm Claude actually
calls an Orivra or MailWeave tool. A reply from chat history alone is not a mailbox test.
Check the returned citations; setup success does not guarantee that every answer is complete.

## If something goes wrong

| What you see | Next action |
|---|---|
| Installed, but no Orivra tools | Check that the extension is enabled, then fully quit and reopen Claude Desktop. |
| Setup link expired, consent declined, or reconnect requested | Ask “Set up Orivra” for a fresh link. |
| Models still downloading | Keep the Mac connected; ask “Continue the Orivra setup” for progress. |
| Download failed | Retry setup on a trusted connection; share a redacted error if it repeats. Do not turn off TLS verification. |
| Google or an administrator blocks authorization | Stop and contact the maintainer/administrator; recreating the app is not part of this install path. |
| A mail query is partial or declined | Read the stated limit and recovery advice. It does not establish that the mail does not exist. |

Support: [kanaparthinayan@gmail.com](mailto:kanaparthinayan@gmail.com). Include the extension
version and a redacted error. Do not share token files, OAuth JSON, email bodies, or complete
logs containing private material.

## Where data lives, and how to disconnect

The extension keeps its authorization and downloaded models in:

```text
~/Library/Application Support/Orivra Beta
```

The refresh token is in `state/credentials.json`, restricted to the current OS user. The
application does not encrypt that file. The installer includes the app's Desktop OAuth
client, not anyone's Gmail refresh token. Do not share this data folder.

To stop future Gmail access, remove the app under your
[Google Account connections](https://myaccount.google.com/connections). Remove the extension
in Claude Desktop. To remove its local token and models, use Finder's **Go → Go to Folder…**
to open the exact folder above and move that folder to the Bin. This is separate from your
self-managed install. Removing these files does not delete mail or erase Claude chats.

## Optional: verify the download

Terminal is not required for installation. For those who want an integrity check, run this
in the folder containing both the installer and the release's `SHA256SUMS` file:

```sh
shasum -a 256 -c SHA256SUMS
```

Use the checksum for the exact release, not a later rebuilt package. A matching checksum
checks file integrity; it is not Google approval, Apple notarization, or a security guarantee.

Prefer to manage your own OAuth project and command-line install? Use
[Advanced / Self-managed setup](SETUP.md).
