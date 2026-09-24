"""Add the beta's OAuth client to a built bundle, on the machine where that client file lives.

    python3 tools/desktop/configure_bundle.py \\
        --bundle dist/desktop/orivra-beta-<version>-darwin-arm64-unconfigured.mcpb \\
        --client mailweave-server-oauth.json \\
        --refuse mailweave-harness-oauth.json \\
        --out dist/desktop/Orivra-Beta-<version>.mcpb

**What it adds, and what it cannot.** One file, `server/config/oauth-client.json`, mode 0600:
the Desktop-app client JSON exactly as Google's console produced it - a client id and the
installed-app client secret, which Google does not treat as confidential for desktop clients.
It adds no token: none exists until each tester consents on their own machine, and that token
never leaves it. Configuring a bundle does not establish Google's permission for public OAuth
access; distribution of the configured application must meet Google's applicable requirements.

**What it refuses.** A client that is not a Desktop-app (`installed`) client; a bundle that
already has one; and any client whose id matches a `--refuse` file's. Pass the harness client
there: that client may only ever authenticate the test mailbox, and this is the check that keeps
it out of a bundle that will authenticate real ones. Nothing secret is printed; the output
names the client id, which Google shows on every consent URL anyway.

Stdlib only, and runnable on Python 3.10.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import sys
import zipfile
from pathlib import Path

CLIENT_ENTRY = "server/config/oauth-client.json"


def _installed_client_id(path: Path) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as failure:
        raise SystemExit(f"{path}: not readable JSON ({type(failure).__name__})") from None
    section = payload.get("installed") if isinstance(payload, dict) else None
    if not isinstance(section, dict):
        raise SystemExit(f"{path}: not a Desktop-app OAuth client (no `installed` section)")
    client_id = section.get("client_id")
    secret = section.get("client_secret")
    if not isinstance(client_id, str) or not client_id or not isinstance(secret, str) or not secret:
        raise SystemExit(f"{path}: the `installed` section needs a client_id and a client_secret")
    return client_id


def configure(bundle: Path, client: Path, refuse: list[Path], out: Path) -> Path:
    client_id = _installed_client_id(client)
    for refused in refuse:
        if refused.exists() and _installed_client_id(refused) == client_id:
            raise SystemExit(
                f"refusing: {client} is the same OAuth client as {refused}. That client may "
                "not authenticate testers' mailboxes."
            )
    with zipfile.ZipFile(bundle) as source:
        names = set(source.namelist())
    if CLIENT_ENTRY in names:
        raise SystemExit(f"{bundle} already carries {CLIENT_ENTRY}")
    if "manifest.json" not in names:
        raise SystemExit(f"{bundle} is not an MCPB bundle (no manifest.json)")
    if out.exists():
        raise SystemExit(f"{out} exists; not overwriting it")
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(bundle, out)
    out.chmod(0o600)
    info = zipfile.ZipInfo(CLIENT_ENTRY)
    info.date_time = (2026, 9, 23, 0, 0, 0)
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(out, "a") as target:
        target.writestr(info, client.read_bytes())
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print(f"client id: {client_id}")
    print(f"wrote:     {out} (0600)")
    print(f"sha256:    {digest}")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--client", type=Path, required=True)
    parser.add_argument("--refuse", type=Path, action="append", default=[])
    parser.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args(argv)
    configure(arguments.bundle, arguments.client, arguments.refuse, arguments.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
