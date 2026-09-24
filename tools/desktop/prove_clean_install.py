"""Run a built bundle as a brand-new user who has nothing else, and record what happens.

    sudo python3 tools/desktop/prove_clean_install.py --bundle <linux .mcpb> --report <file>

**Linux only, and never a real OAuth client.** It creates a fresh Unix account with an empty
home, configures the bundle with a placeholder client id and secret (which Google will not
accept), unpacks it with the official `mcpb unpack` into that account's home, and speaks MCP
to the launcher exactly as the manifest's `mcp_config` says, from outside the account. It
cannot prove what only a real Google account and a real Mac can - see `docs/DESKTOP_BETA.md`
for which steps those are - and it says so in the report rather than simulating them.

What it establishes, each as an observation in the report:

  * the account can read nothing of this repository, its virtual environment, the Python
    driving this script or the builder's caches - and if it can, the run stops there, because
    nothing after that would be a proof;
  * the extension starts from its own files: the process's executable, its import path and
    every file it maps are inside the unpacked bundle or the system's own libraries;
  * the tool surface is the product's plus `orivra_setup`, and a product tool before setup
    says so;
  * `orivra_setup` starts the product's own consent command, whose link is Google's
    authorization endpoint with the bundle's client id, the single read-only scope, a
    loopback redirect and PKCE; a browser answer of `access_denied` delivered to that loopback
    is reported, and the next call issues a new link;
  * the model download is started and, where the network cannot reach the model host, fails
    as a reported step rather than as a crash.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pwd
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
USER = "orivra-cleanroom"
PLACEHOLDER_CLIENT = {
    "installed": {
        "client_id": "cleanroom-placeholder.apps.googleusercontent.com",
        "client_secret": "placeholder-not-a-real-secret",
        "redirect_uris": ["http://localhost"],
    }
}


def _sh(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, **kwargs)


def _fresh_account() -> Path:
    if _sh(["id", USER]).returncode == 0:
        _sh(["userdel", "-r", USER])
    created = _sh(["useradd", "--create-home", "--shell", "/bin/sh", USER])
    if created.returncode != 0:
        raise SystemExit(f"useradd failed: {created.stderr}")
    home = Path(pwd.getpwnam(USER).pw_dir)
    return home


def _as_user(command: str) -> subprocess.CompletedProcess[str]:
    return _sh(["su", "-s", "/bin/sh", USER, "-c", command])


def _text(result: Any) -> str:
    return "\n".join(getattr(block, "text", "") for block in result.content)


async def _drive(launcher: Path, home: Path, report: dict[str, Any]) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    environment = f"env -i HOME={home} PATH=/usr/bin:/bin LANG=C.UTF-8"
    parameters = StdioServerParameters(
        command="su",
        args=["-s", "/bin/sh", USER, "-c", f"{environment} /bin/sh {launcher}"],
    )
    async with stdio_client(parameters) as (read, write), ClientSession(read, write) as session:
        initialized = await session.initialize()
        report["server"] = {
            "name": initialized.server_info.name,
            "version": initialized.server_info.version,
            "protocol": initialized.protocol_version,
        }
        tools = await session.list_tools()
        report["tools"] = [tool.name for tool in tools.tools]

        before = await session.call_tool("orivra_ask", {"query": "what was decided"})
        report["product_tool_before_setup"] = {
            "is_error": before.is_error,
            "text": _text(before),
        }

        first = await session.call_tool("orivra_setup", {})
        text = _text(first)
        report["setup_first_call"] = text
        url = next(
            line for line in text.splitlines() if line.startswith("https://accounts.google.com/")
        )
        query = parse_qs(urlsplit(url).query)
        report["authorization_url"] = {
            "host": urlsplit(url).netloc,
            "path": urlsplit(url).path,
            "client_id": query.get("client_id"),
            "scope": query.get("scope"),
            "redirect_uri": query.get("redirect_uri"),
            "code_challenge_method": query.get("code_challenge_method"),
            "access_type": query.get("access_type"),
            "prompt": query.get("prompt"),
        }
        report["process"] = _process_facts(home)

        # The browser's answer when a person declines, delivered where Google would send it.
        redirect = query["redirect_uri"][0]
        state = query["state"][0]
        with urllib.request.urlopen(
            f"{redirect}/?error=access_denied&state={state}", timeout=10
        ) as answer:
            report["loopback_answer_status"] = answer.status
        time.sleep(2.0)
        # Give the download child long enough to meet the network and report it.
        time.sleep(20.0)
        second = await session.call_tool("orivra_setup", {})
        report["setup_second_call"] = _text(second)
        report["home_after"] = _tree(home)


def _process_facts(home: Path) -> dict[str, Any]:
    """The launcher's Python and its children: executable, arguments, and every mapped file."""
    facts: list[dict[str, Any]] = []
    for entry in Path("/proc").iterdir():
        pid = entry.name
        if not pid.isdigit():
            continue
        try:
            status = Path(f"/proc/{pid}/status").read_text()
            uid = int(
                next(line.split()[1] for line in status.splitlines() if line.startswith("Uid:"))
            )
            if uid != pwd.getpwnam(USER).pw_uid:
                continue
            exe = str(Path(f"/proc/{pid}/exe").readlink())
            cmdline = Path(f"/proc/{pid}/cmdline").read_text().split("\0")
            maps = {
                line.split()[-1]
                for line in Path(f"/proc/{pid}/maps").read_text().splitlines()
                if len(line.split()) >= 6 and line.split()[-1].startswith("/")
            }
            environ = [
                item.split("=", 1)[0]
                for item in Path(f"/proc/{pid}/environ").read_text().split("\0")
                if item
            ]
        except (OSError, StopIteration):
            continue
        if "python3.12" not in exe:
            continue
        outside = sorted(
            path
            for path in maps
            if not path.startswith(str(home))
            and not path.startswith(("/usr/lib", "/lib", "/usr/lib64", "/lib64", "/etc", "/dev"))
        )
        facts.append(
            {
                "pid": int(pid),
                "exe": exe,
                "argv": [part for part in cmdline if part][:8],
                "mapped_files": len(maps),
                "mapped_outside_home_and_system": outside,
                "environment_variables": sorted(environ),
            }
        )
    return {"python_processes": facts}


def _tree(root: Path) -> list[str]:
    lines = []
    for path in sorted(root.rglob("*")):
        if "extension" in path.relative_to(root).parts[:1]:
            continue
        mode = oct(path.stat().st_mode & 0o777)
        lines.append(f"{mode} {path.relative_to(root)}{'/' if path.is_dir() else ''}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--mcpb", default="npx --yes @anthropic-ai/mcpb")
    arguments = parser.parse_args(argv)
    if sys.platform != "linux" or os.geteuid() != 0:
        raise SystemExit("run as root on Linux: it creates and removes a Unix account")

    report: dict[str, Any] = {"bundle": str(arguments.bundle)}
    home = _fresh_account()
    report["account"] = {"user": USER, "home": str(home), "home_before": _tree(home)}

    with tempfile.TemporaryDirectory() as scratch:
        client = Path(scratch) / "placeholder-client.json"
        client.write_text(json.dumps(PLACEHOLDER_CLIENT))
        configured = Path(scratch) / "configured.mcpb"
        _sh(
            [sys.executable, str(HERE / "configure_bundle.py"), "--bundle", str(arguments.bundle),
             "--client", str(client), "--out", str(configured)],
            check=True,
        )  # fmt: skip
        extension = home / "extension"
        unpacked = _sh([*arguments.mcpb.split(), "unpack", str(configured), str(extension)])
        report["unpack"] = unpacked.stdout.strip().splitlines()[-1:] or unpacked.stderr
        shutil.chown(extension, USER, USER)
        for path in extension.rglob("*"):
            shutil.chown(path, USER, USER)

    builder = (
        REPO,
        REPO / ".venv",
        Path(sys.prefix),
        Path("/home/claude"),
        Path("/root"),
        Path.home() / ".cache",
    )
    report["account"]["can_read"] = {
        str(path): _as_user(f"ls {path} >/dev/null 2>&1 && echo yes || echo no").stdout.strip()
        for path in builder
    }
    readable = [path for path, answer in report["account"]["can_read"].items() if answer != "no"]
    if readable:
        # Not a proof of anything if the account could have used the builder's files: stop,
        # record why, and say what to make unreadable. The script does not change permissions
        # on the machine it runs on.
        arguments.report.write_text(json.dumps(report, indent=2) + "\n")
        raise SystemExit(
            f"not isolated: {USER} can read {readable}. Make them unreadable to other users "
            "(for example `chmod 700` on the directory that holds them) and run again."
        )
    report["account"]["python_on_path"] = _as_user("command -v python3 || echo none").stdout.strip()
    python = home / "extension" / "server" / "python" / "bin" / "python3.12"
    probe = _as_user(
        f"env -i HOME={home} PATH=/usr/bin:/bin {python} -I -c "
        '"import sys, mailweave, orivra; print(sys.executable); print(sys.path); '
        'print(mailweave.__file__); print(orivra.__file__)"'
    )
    report["import_probe"] = probe.stdout.strip().splitlines() or probe.stderr

    asyncio.run(_drive(home / "extension" / "server" / "orivra-beta", home, report))
    arguments.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
