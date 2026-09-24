"""Where the desktop beta reads what it shipped with, and keeps what it owns.

Two roots and no third:

  * **the bundle** - the extension's own `server/` directory, read-only in spirit: the beta's
    OAuth client file (`config/oauth-client.json`) and the reviewed model lock
    (`models.lock`). The launcher script names it in `ORIVRA_DESKTOP_BUNDLE`;
  * **the home** - everything this installation creates: `state/` (the credential store, the
    handle key and the watermark, exactly as `MailweaveConfig.state_dir` lays them out) and
    `models/` (the verified weights). On macOS it is `~/Library/Application Support/Orivra
    Beta`; elsewhere `$XDG_DATA_HOME/orivra-beta`.

Nothing here is shared with a self-managed install (`~/.config/mailweave`,
`~/.local/state/mailweave`, `~/.local/share/mailweave/models`). Two installs on one machine then
hold two credentials and two model copies, which is the cost of a second install that can be
removed without touching the first.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

#: Set by the extension's launcher script to its own `server/` directory.
BUNDLE_ENV: Final[str] = "ORIVRA_DESKTOP_BUNDLE"
#: Overrides the home. For tests and for the clean-install proof, which runs the bundle as a
#: fresh user and needs to say where it looked; not something an installation sets.
HOME_ENV: Final[str] = "ORIVRA_DESKTOP_HOME"

#: The folder name under `~/Library/Application Support` on macOS.
MACOS_HOME_NAME: Final[str] = "Orivra Beta"


def default_home() -> Path:
    """The platform's conventional place for an application's own data."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / MACOS_HOME_NAME
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "orivra-beta"


@dataclass(frozen=True)
class DesktopPaths:
    """The two roots, and every file this beta reads or causes to be written under them."""

    bundle: Path
    home: Path

    @property
    def client(self) -> Path:
        """The beta's Desktop-app OAuth client. Its id and installed-app secret, no token."""
        return self.bundle / "config" / "oauth-client.json"

    @property
    def lock(self) -> Path:
        return self.bundle / "models.lock"

    @property
    def state(self) -> Path:
        return self.home / "state"

    @property
    def credentials(self) -> Path:
        """Where `mailweave auth login --state-dir` stores the refresh token (0600)."""
        return self.state / "credentials.json"

    @property
    def models(self) -> Path:
        return self.home / "models"


def resolve(bundle: Path | None = None, home: Path | None = None) -> DesktopPaths:
    """The paths for this process: arguments first, then the environment, then the default.

    A bundle is required. Without one there is no OAuth client and no lock, and guessing a
    directory would be how a development checkout's files get read by an installed beta.
    """
    chosen_bundle = bundle or (Path(os.environ[BUNDLE_ENV]) if os.environ.get(BUNDLE_ENV) else None)
    if chosen_bundle is None:
        raise SystemExit(
            f"orivra.desktop: no bundle directory; the extension's launcher sets {BUNDLE_ENV}"
        )
    chosen_home = home or (Path(os.environ[HOME_ENV]) if os.environ.get(HOME_ENV) else None)
    return DesktopPaths(
        bundle=chosen_bundle.expanduser().resolve(),
        home=(chosen_home or default_home()).expanduser(),
    )
