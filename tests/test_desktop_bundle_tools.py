"""The desktop beta's build tools: what a bundle may contain, and what configuring it adds.

These hold the rules the clean-install proof relies on, offline and without building anything:

  * the manifest's tool list (`tools/desktop/bundle/tools.json`, read by the stdlib-only
    builder, which cannot import the product) is the extension's own list, name for name and
    description for description (§1);
  * `configure_bundle` adds exactly one file, the Desktop-app client at mode 0600, refuses the
    harness client, a non-Desktop client and a bundle that already has one, and prints no
    secret (§2);
  * the builder writes regular files only - no directory entry, which the MCPB unpacker
    cannot open, and no symlink - keeps executable modes, removes the install location a local
    wheel records, and leaves each `RECORD` listing only files the bundle carries (§3);
  * `inspect_bundle` finds each thing a bundle must not carry, tells a dependency's own bytes
    (verified against its `RECORD`) from this build's, and reads each Mach-O slice's CPU,
    minimum macOS and attached code signature from its load commands, universal files
    included (§4).
"""

from __future__ import annotations

import base64
import hashlib
import json
import stat
import struct
import zipfile
from pathlib import Path

import pytest

from orivra.desktop.server import desktop_tools
from tools.desktop import build_bundle, configure_bundle, inspect_bundle

TOOLS_JSON = Path(build_bundle.HERE) / "bundle" / "tools.json"
SECRET = "GOCSPX-must-never-be-printed"


def _client(path: Path, client_id: str, *, section: str = "installed") -> Path:
    path.write_text(json.dumps({section: {"client_id": client_id, "client_secret": SECRET}}))
    return path


def _bundle(path: Path, entries: dict[str, tuple[bytes, int]]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, (body, mode) in entries.items():
            archive.writestr(build_bundle.zip_entry(name, mode), body)
    return path


def _minimal_bundle(path: Path) -> Path:
    manifest = {"manifest_version": "0.3", "name": "orivra-beta", "tools": []}
    return _bundle(
        path,
        {
            "manifest.json": (json.dumps(manifest).encode(), 0o644),
            "server/orivra-beta": (b"#!/bin/sh\n", 0o755),
        },
    )


# --- §1 the manifest's tools ---------------------------------------------------------------


def test_the_manifests_tool_list_is_the_extensions_own() -> None:
    committed = json.loads(TOOLS_JSON.read_text())
    served = [{"name": tool.name, "description": tool.description} for tool in desktop_tools()]
    assert committed == served


# --- §2 configuring a bundle ---------------------------------------------------------------


def test_configuring_adds_only_the_desktop_client_at_0600_and_prints_no_secret(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle = _minimal_bundle(tmp_path / "unconfigured.mcpb")
    client = _client(tmp_path / "server-client.json", "beta.apps.googleusercontent.com")
    out = configure_bundle.configure(bundle, client, [], tmp_path / "configured.mcpb")

    printed = capsys.readouterr().out
    assert SECRET not in printed and "beta.apps.googleusercontent.com" in printed
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    with zipfile.ZipFile(bundle) as before, zipfile.ZipFile(out) as after:
        added = set(after.namelist()) - set(before.namelist())
        assert added == {configure_bundle.CLIENT_ENTRY}
        entry = after.getinfo(configure_bundle.CLIENT_ENTRY)
        assert stat.S_IMODE(entry.external_attr >> 16) == 0o600
        assert after.read(entry) == client.read_bytes()
        for name in before.namelist():
            assert after.read(name) == before.read(name)


def test_the_harness_client_is_refused(tmp_path: Path) -> None:
    bundle = _minimal_bundle(tmp_path / "unconfigured.mcpb")
    harness = _client(tmp_path / "harness.json", "harness.apps.googleusercontent.com")
    same = _client(tmp_path / "copy-of-harness.json", "harness.apps.googleusercontent.com")
    with pytest.raises(SystemExit, match="same OAuth client"):
        configure_bundle.configure(bundle, same, [harness], tmp_path / "out.mcpb")
    assert not (tmp_path / "out.mcpb").exists()


def test_a_client_that_is_not_a_desktop_client_is_refused(tmp_path: Path) -> None:
    bundle = _minimal_bundle(tmp_path / "unconfigured.mcpb")
    web = _client(tmp_path / "web.json", "web.apps.googleusercontent.com", section="web")
    with pytest.raises(SystemExit, match="not a Desktop-app OAuth client"):
        configure_bundle.configure(bundle, web, [], tmp_path / "out.mcpb")


def test_a_bundle_is_configured_once_and_an_output_is_never_overwritten(tmp_path: Path) -> None:
    bundle = _minimal_bundle(tmp_path / "unconfigured.mcpb")
    client = _client(tmp_path / "server-client.json", "beta.apps.googleusercontent.com")
    configured = configure_bundle.configure(bundle, client, [], tmp_path / "configured.mcpb")
    with pytest.raises(SystemExit, match="already carries"):
        configure_bundle.configure(configured, client, [], tmp_path / "twice.mcpb")
    with pytest.raises(SystemExit, match="not overwriting"):
        configure_bundle.configure(bundle, client, [], configured)


# --- §3 building ---------------------------------------------------------------------------


def test_the_zip_holds_regular_files_only_with_their_modes(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    (stage / "server" / "python" / "bin").mkdir(parents=True)
    (stage / "manifest.json").write_text("{}")
    launcher = stage / "server" / "orivra-beta"
    launcher.write_text("#!/bin/sh\n")
    launcher.chmod(0o755)
    (stage / "server" / "python" / "bin" / "python3.12").write_bytes(b"\x7fELF")
    (stage / "server" / "python" / "bin" / "python3.12").chmod(0o700)
    output = tmp_path / "out.mcpb"
    build_bundle._zip(stage, output)

    with zipfile.ZipFile(output) as archive:
        infos = {info.filename: info for info in archive.infolist()}
    assert set(infos) == {"manifest.json", "server/orivra-beta", "server/python/bin/python3.12"}
    modes = {name: info.external_attr >> 16 for name, info in infos.items()}
    assert all(stat.S_ISREG(mode) for mode in modes.values())
    assert stat.S_IMODE(modes["manifest.json"]) == 0o644
    assert stat.S_IMODE(modes["server/orivra-beta"]) == 0o755
    assert stat.S_IMODE(modes["server/python/bin/python3.12"]) == 0o755
    assert all(info.create_system == 3 for info in infos.values())


def test_nothing_the_lock_carries_is_dropped_from_the_bundle() -> None:
    """The bundle is the locked set for its platform, so no locked distribution is removed.

    `setuptools` was dropped as build tooling, but torch declares it as a runtime requirement
    and the lock carries it (2026-09-24). A drop list that matches a locked name is a bundle
    that differs from the lock it claims to install.
    """
    import tomllib

    lock = tomllib.loads((build_bundle.REPO / "uv.lock").read_text())
    names = {package["name"] for package in lock["package"]}
    assert "setuptools" in names, "precondition: the lock carries setuptools"
    dropped = {name for name in names if name.startswith(build_bundle._SITE_DROP_PREFIXES)}
    assert dropped == set(), dropped


def test_a_symlink_in_the_stage_stops_the_build(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "real").write_text("x")
    (stage / "link").symlink_to(stage / "real")
    with pytest.raises(SystemExit, match="symlink"):
        build_bundle._zip(stage, tmp_path / "out.mcpb")


def test_the_install_location_a_local_wheel_records_is_removed_with_its_record_line(
    tmp_path: Path,
) -> None:
    info = tmp_path / "mailweave-0.2.0b1.dist-info"
    (tmp_path / "mailweave").mkdir()
    (tmp_path / "mailweave" / "__init__.py").write_text("")
    info.mkdir()
    (info / "direct_url.json").write_text('{"url": "file:///Users/someone/build/x.whl"}')
    (info / "uv_cache.json").write_text('{"timestamp": {"secs_since_epoch": 1790168989}}')
    (info / "METADATA").write_text("Name: mailweave\n")
    (info / "RECORD").write_text(
        "mailweave/__init__.py,sha256=abc,0\n"
        f"{info.name}/direct_url.json,sha256=def,40\n"
        f"{info.name}/METADATA,sha256=ghi,16\n"
        f"{info.name}/RECORD,,\n"
    )
    build_bundle.forget_install_location(tmp_path, "mailweave")
    build_bundle.prune_records(tmp_path)
    assert not (info / "direct_url.json").exists()
    assert not (info / "uv_cache.json").exists()
    assert (info / "METADATA").exists()
    assert (info / "RECORD").read_text().splitlines() == [
        "mailweave/__init__.py,sha256=abc,0",
        f"{info.name}/METADATA,sha256=ghi,16",
        f"{info.name}/RECORD,,",
    ]


def test_records_list_only_what_the_bundle_carries(tmp_path: Path) -> None:
    """Dropped console scripts leave `RECORD`; files that are there keep their lines verbatim."""
    site = tmp_path / "site-packages"
    info = site / "httpx-0.28.1.dist-info"
    info.mkdir(parents=True)
    (site / "httpx").mkdir()
    (site / "httpx" / "__init__.py").write_text("")
    (site / ".lock").write_text("")
    record = "\n".join(
        [
            "../../../../etc/hosts,sha256=x,1",  # never anything outside site-packages
            "bin/httpx,sha256=from-the-build-interpreter,250",
            "httpx/__init__.py,sha256=abc,0",
            f"{info.name}/RECORD,,",
        ]
    )
    (info / "RECORD").write_text(record + "\n")
    untouched = site / "idna-3.19.dist-info"
    untouched.mkdir()
    (untouched / "RECORD").write_text(f"{untouched.name}/RECORD,,\r\n")
    build_bundle.prune_records(site)
    assert (
        info / "RECORD"
    ).read_text() == f"httpx/__init__.py,sha256=abc,0\n{info.name}/RECORD,,\n"
    assert (untouched / "RECORD").read_bytes() == f"{untouched.name}/RECORD,,\r\n".encode()
    assert not (site / ".lock").exists()


# --- §4 inspecting -------------------------------------------------------------------------


def _macho(cpu: int, minos: tuple[int, int], *, signed: bool = True) -> bytes:
    commands = struct.pack("<IIIIII", 0x32, 24, 1, (minos[0] << 16) | (minos[1] << 8), 0, 0)
    if signed:
        commands += struct.pack("<IIII", 0x1D, 16, 0, 0)  # LC_CODE_SIGNATURE
    count = 2 if signed else 1
    header = struct.pack("<IiiIIIII", 0xFEEDFACF, cpu, 0, 2, count, len(commands), 0, 0)
    return header + commands


ARM64, X86_64 = 0x0100000C, 0x01000007


def _universal(*slices: bytes) -> bytes:
    """A fat file: big-endian header, one fat_arch per slice, slices at 4 KiB-aligned offsets."""
    header = struct.pack(">II", 0xCAFEBABE, len(slices))
    offset, arches, body = 4096, b"", b""
    for slice_ in slices:
        (cpu,) = struct.unpack("<i", slice_[4:8])
        arches += struct.pack(">iiIII", cpu, 0, offset + len(body), len(slice_), 12)
        body += slice_ + b"\0" * (4096 - len(slice_))
    return header + arches + b"\0" * (offset - len(header) - len(arches)) + body


def _mac_bundle(tmp_path: Path, binaries: dict[str, bytes]) -> Path:
    manifest = {"manifest_version": "0.3", "name": "orivra-beta", "tools": [{"name": "t"}]}
    entries = {"manifest.json": (json.dumps(manifest).encode(), 0o644)}
    entries.update({name: (body, 0o755) for name, body in binaries.items()})
    return _bundle(tmp_path / "mac.mcpb", entries)


def test_mach_o_cpu_and_minimum_macos_are_read_from_the_load_commands(tmp_path: Path) -> None:
    bundle = _mac_bundle(
        tmp_path,
        {
            "server/python/bin/python3.12": _macho(ARM64, (13, 0)),
            "server/python/lib/python3.12/site-packages/torch/lib/libtorch.dylib": _macho(
                ARM64, (14, 0)
            ),
            # lxml's macOS wheel is universal2; its x86_64 slice needs a later macOS than the
            # beta supports, and that does not matter on Apple Silicon.
            "server/python/lib/python3.12/site-packages/lxml/etree.so": _universal(
                _macho(X86_64, (15, 0)), _macho(ARM64, (11, 0))
            ),
        },
    )
    report = inspect_bundle.inspect(bundle, [str(tmp_path / "nowhere")])
    assert report["macho_slices_by_cpu"] == {"arm64": 3, "x86_64": 1}
    assert report["macho_universal_files"] == 1
    assert report["macho_without_arm64"] == []
    assert report["macho_arm64_without_signature"] == []
    assert report["macos_minimum"] == "14.0"
    assert inspect_bundle.main([str(bundle), "--expect", "darwin-arm64"]) == 0


@pytest.mark.parametrize(
    ("binary", "complaint"),
    [
        (_macho(X86_64, (14, 0)), "server/extra: a Mach-O file with no arm64 slice"),
        (_macho(ARM64, (15, 0)), "the beta supports 14.0"),
        (_universal(_macho(X86_64, (11, 0))), "server/extra: a Mach-O file with no arm64 slice"),
        (_universal(_macho(X86_64, (11, 0)), _macho(ARM64, (15, 0))), "the beta supports 14.0"),
        (b"\x7fELF" + b"\0" * 60, "Linux (ELF) files"),
        (_macho(ARM64, (14, 0), signed=False), "server/extra: arm64 code with no code signature"),
    ],
    ids=[
        "intel",
        "macos-15",
        "universal-intel-only",
        "universal-arm64-macos-15",
        "linux",
        "unsigned",
    ],
)
def test_a_macos_bundle_for_another_machine_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], binary: bytes, complaint: str
) -> None:
    bundle = _mac_bundle(
        tmp_path,
        {"server/python/bin/python3.12": _macho(ARM64, (14, 0)), "server/extra": binary},
    )
    assert inspect_bundle.main([str(bundle), "--expect", "darwin-arm64"]) == 1
    assert complaint in capsys.readouterr().out


def test_what_a_bundle_must_never_carry_is_each_reported(tmp_path: Path) -> None:
    build_home = "/Users/builder"
    site = "server/python/lib/python3.12/site-packages/"
    bundle = tmp_path / "bad.mcpb"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr(build_bundle.zip_entry("manifest.json", 0o644), b'{"tools": []}')
        archive.writestr(zipfile.ZipInfo("server/"), b"")
        link = zipfile.ZipInfo("server/python/bin/python3")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, b"python3.12")
        archive.writestr(build_bundle.zip_entry("server/credentials.json", 0o600), b"{}")
        archive.writestr(
            build_bundle.zip_entry(site + "orivra-0.2.0b1.dist-info/direct_url.json", 0o644),
            b'{"url": "file:///somewhere/else/orivra.whl"}',
        )
        archive.writestr(
            build_bundle.zip_entry(site + "orivra/desktop/texts.py", 0o644),
            f"PATH = '{build_home}/MailWeave'\n".encode(),
        )
        # The interpreter's own stdlib names python-build-standalone's build machine: upstream
        # bytes, pinned by digest, and not this build's.
        archive.writestr(
            build_bundle.zip_entry("server/python/lib/python3.12/sysconfig.py", 0o644),
            f"PREFIX = '{build_home}/install'\n".encode(),
        )
    problems = inspect_bundle.inspect(bundle, [build_home])["problems"]
    joined = "\n".join(problems)
    assert "directory entry server/" in joined
    assert "symlink server/python/bin/python3" in joined
    assert "server/credentials.json: a credential file" in joined
    assert "direct_url.json: records the local file it was installed from" in joined
    assert f"orivra/desktop/texts.py: {build_home}/" in joined
    assert "sysconfig.py" not in joined
    assert len(problems) == 5


def _record_line(path: str, body: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(body).digest()).rstrip(b"=").decode()
    return f"{path},sha256={digest},{len(body)}"


def test_a_dependencys_own_bytes_may_name_a_path_and_a_changed_or_workspace_file_may_not(
    tmp_path: Path,
) -> None:
    """An upstream docstring that says `/root/.cache` is not this build's `/root`."""
    site = "server/python/lib/python3.12/site-packages/"
    mention = b"# e.g. /root/.cache/huggingface\n"
    files = {
        "huggingface_hub/utils.py": mention,  # recorded, bytes as recorded: upstream
        "huggingface_hub/other.py": mention,  # recorded with another digest: changed here
        "orivra/desktop/texts.py": mention,  # a workspace package is built here
    }
    records = {
        "huggingface_hub-1.0.dist-info/RECORD": "\n".join(
            [
                _record_line("huggingface_hub/utils.py", mention),
                _record_line("huggingface_hub/other.py", b"what the wheel had"),
            ]
        ),
        "orivra-0.2.0b1.dist-info/RECORD": _record_line("orivra/desktop/texts.py", mention),
    }
    bundle = tmp_path / "b.mcpb"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr(build_bundle.zip_entry("manifest.json", 0o644), b'{"tools": []}')
        for name, body in files.items():
            archive.writestr(build_bundle.zip_entry(site + name, 0o644), body)
        for name, text in records.items():
            archive.writestr(build_bundle.zip_entry(site + name, 0o644), text.encode())
    report = inspect_bundle.inspect(bundle, ["/root"])
    assert report["upstream_files_mentioning_those_paths"] == [
        f"{site}huggingface_hub/utils.py: /root/"
    ]
    assert sorted(report["problems"]) == [
        f"build machine path in {site}huggingface_hub/other.py: /root/",
        f"build machine path in {site}orivra/desktop/texts.py: /root/",
    ]
