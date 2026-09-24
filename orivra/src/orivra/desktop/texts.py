"""What the setup tool says. Plain text, because Claude Desktop reads the text half.

Every sentence here is a claim about Google, about this code or about where something lives,
and each is written to be checkable. The one permission is `SERVER_SCOPES`, the hosts are
`RUNTIME_EGRESS_ALLOWLIST`, the paths are `DesktopPaths`.

The statements about Google are its published rules for the beta's OAuth application as it
stands: External, **In production**, and not yet through verification for this restricted
scope (corrected 2026-09-24 - the text first described a Testing application, whose test-user
gate and seven-day expiry do not apply). `docs/DESKTOP_BETA.md` §3 and §7 cite each rule:

- the unverified-app screen, shown before consent until verification is complete;
- the cap of 100 new users in total that applies meanwhile;
- a refresh token that lasts until it is revoked or Google stops accepting it, with no
  schedule.

What this module does not know - the exact wording of Google's warning screen, which Google
changes - it does not quote.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Final

from mailweave.constants import RUNTIME_EGRESS_ALLOWLIST, SERVER_SCOPES

#: Google's user cap for an app that requests a restricted scope before completing
#: verification: "100 new users in total, after the app presents the unverified app screen".
UNVERIFIED_USER_CAP: Final[int] = 100

#: Why Google may stop accepting a refresh token for this app, as Google lists the reasons that
#: apply to it. The Testing-status seven-day rule is not among them, because the app is
#: published.
_WHEN_GOOGLE_STOPS_ACCEPTING: Final[str] = (
    "for example after six months unused, or when the account's password changes, because "
    "this permission reads Gmail"
)

SETUP_TOOL_NAME: Final[str] = "orivra_setup"


def _hosts() -> str:
    return " and ".join(sorted(RUNTIME_EGRESS_ALLOWLIST))


def consent(url: str, *, minutes: int, credentials_path: str) -> str:
    """The link, and everything a person should know before opening it."""
    return "\n".join(
        [
            "To connect Gmail, open this link in a browser on this Mac and sign in with the "
            "Google account whose mail Orivra should read:",
            "",
            url,
            "",
            "What you will see:",
            "1. A warning that Google hasn't verified this app. The beta's Google application "
            "is published but has not yet completed Google's verification for this "
            "permission, and until it does Google shows this screen before consent and "
            f"limits the app to {UNVERIFIED_USER_CAP} new users in total. The screen's wording "
            "is Google's; it offers either Continue, or Advanced followed by a link to go to "
            "the app.",
            "2. Google's permission screen, asking for one permission: to read your email "
            "messages and settings. Orivra cannot send, delete, label or change anything "
            f"({', '.join(SERVER_SCOPES)}).",
            '3. A page saying "Consent received". Close it and come back here.',
            "",
            f"The link works for {minutes} minutes, and only in a browser on this Mac: Google "
            "hands its answer to a one-time listener on this computer (127.0.0.1).",
            "",
            "The authorization does not expire on a schedule. It lasts until you revoke it from "
            "your Google Account, or until Google stops accepting it - "
            f"{_WHEN_GOOGLE_STOPS_ACCEPTING}. If that happens, {SETUP_TOOL_NAME} gives you a "
            "new link.",
            "",
            "The authorization Google returns (a refresh token) is stored only on this Mac, in "
            f"{credentials_path}, readable only by your macOS account. It is never sent to the "
            "beta's organiser or to anyone else.",
            "",
            "When you have consented, ask me to continue the Orivra setup.",
        ]
    )


def models_plan(total_bytes: int, repos: Sequence[str]) -> str:
    return (
        f"Orivra answers with two local models that run on this Mac ({', '.join(repos)}), "
        f"{_size(total_bytes)} together. They are downloaded once from Hugging Face and checked "
        "byte for byte against the digests this release was built with. Nothing about your "
        "mail is sent to the model host; this download is the only time Orivra contacts it."
    )


def _size(count: int) -> str:
    if count >= 1 << 30:
        return f"{count / (1 << 30):.2f} GB"
    return f"{count / (1 << 20):.0f} MB"


def progress(done: int, total: int, current: str | None) -> str:
    percent = 0 if total <= 0 else min(100, int(done * 100 / total))
    tail = f", now {current}" if current else ""
    return f"Models: downloading, {percent}% ({_size(done)} of {_size(total)}{tail})."


def ready(
    *,
    account: str,
    granted: Sequence[str],
    obtained_at: datetime | None,
    models: Sequence[str],
    installation: Sequence[str],
) -> str:
    lines = [
        "Orivra is ready.",
        f"- Gmail: connected as {account}, read-only. Google granted exactly "
        f"{', '.join(granted)}, and nothing else.",
    ]
    if obtained_at is not None:
        lines.append(
            f"- Authorization: granted {obtained_at:%Y-%m-%d %H:%M} UTC. It has no expiry date: "
            "it lasts until it is revoked or Google stops accepting it, and if that happens "
            f"Orivra says so and {SETUP_TOOL_NAME} gives you a new link."
        )
    lines.append(f"- Local models: loaded ({', '.join(models)}).")
    lines.append(f"- While answering, Orivra contacts only {_hosts()}.")
    lines.extend(f"- {line}" for line in installation)
    lines.append("")
    lines.append(
        "Ask a question about your email - for example, what was decided about a project, "
        "and which messages say so."
    )
    return "\n".join(lines)


def not_ready(status: str) -> str:
    """What an Orivra or MailWeave tool says before setup has finished."""
    return (
        f"Orivra (beta) is not set up on this Mac yet: {status} "
        f"Call the {SETUP_TOOL_NAME} tool; it reports what is left and does the next step."
    )


REAUTHORISE_NOTE: Final[str] = (
    "Orivra beta: Google no longer accepts this Mac's Gmail authorization - it was revoked from "
    f"the Google account, or Google stopped accepting it ({_WHEN_GOOGLE_STOPS_ACCEPTING}). "
    f"Call {SETUP_TOOL_NAME} for a new link; ignore any instruction above to run a command in a "
    "terminal, which is for self-managed installs."
)

SETUP_DESCRIPTION: Final[str] = (
    "Set up the Orivra beta on this Mac, or check it: connects Gmail read-only (the person "
    "opens a Google link and consents), downloads the two local models with progress, and "
    "verifies the connection. Safe to call repeatedly: each call reports what is done, what "
    "is in progress and the next step, and starts the next step if it is not running. Call it "
    "when the person asks to set up or reconnect Orivra, or when another Orivra tool says "
    "setup is not finished."
)
