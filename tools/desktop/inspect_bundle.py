"""Inspect a built `.mcpb` without running it: what it contains, for which machine, and what not.

    python3 tools/desktop/inspect_bundle.py <bundle.mcpb> [--expect darwin-arm64]

For a macOS bundle this is the part of the proof that can be done on any computer: every
Mach-O file - each slice of a universal one - is read for its CPU type and the minimum macOS
version its load commands state (`LC_BUILD_VERSION` / `LC_VERSION_MIN_MACOSX`), so "runs on
Apple Silicon from macOS 14" is a reading of the binaries rather than a hope. It cannot show
that they load; only a Mac can. It also checks the things a bundle must never carry
- a credential store, a token file, a symlink, a directory entry the MCPB unpacker cannot
open, a path from the machine it was built on - and reports the OAuth client entry by its
mode and client id only.

Stdlib only, Python 3.10.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import stat
import struct
import sys
import zipfile
from pathlib import Path
from typing import Any

_MACHO_64 = 0xFEEDFACF
_FAT = 0xCAFEBABE
_FAT_64 = 0xCAFEBABF
_CPU = {0x0100000C: "arm64", 0x01000007: "x86_64"}
_LC_BUILD_VERSION = 0x32
_LC_VERSION_MIN_MACOSX = 0x24
_LC_CODE_SIGNATURE = 0x1D
_FORBIDDEN_NAMES = ("credentials.json", "token.json", ".env")
#: The interpreter's standard library names the machine python-build-standalone was built on,
#: and some dependencies' files name their own authors' machines (pydantic-core's SBOM names
#: `/home/runner/...`, huggingface_hub's docstrings `/root/...`): both are upstream bytes,
#: pinned by digest. What must not appear is the machine *this* bundle was built on - its home
#: directory and the bundle's own directory by default, run right after the build on the machine
#: that built it. A mention inside a dependency's file whose bytes still match that
#: distribution's `RECORD` is upstream by construction, and is listed rather than flagged; the
#: two workspace packages are never given that benefit, because they are built here.
_STDLIB = "server/python/lib/python3.12/"
_SITE = _STDLIB + "site-packages/"
_WORKSPACE = ("mailweave", "orivra")
_SCANNED_SUFFIXES = (".py", ".pyc", ".json", ".txt", ".lock", ".cfg", ".toml")
_MACOS_FLOOR = "14.0"


def _thin(data: bytes) -> tuple[str, str | None, bool] | None:
    """(cpu, minimum macOS, signed) from a thin 64-bit Mach-O's header and load commands.

    `signed` is whether a code signature is attached at all: Apple Silicon refuses to run
    arm64 code with none, and the builder never rewrites a binary, so the linker's ad-hoc
    signature on each one should still be there. Whether that signature is valid only a Mac
    can say (`codesign --verify`).
    """
    if len(data) < 32 or struct.unpack("<I", data[:4])[0] != _MACHO_64:
        return None
    cputype, _sub, _filetype, ncmds, _size, _flags, _reserved = struct.unpack(
        "<iiIIIII", data[4:32]
    )
    offset, minos, signed = 32, None, False
    for _ in range(ncmds):
        if offset + 16 > len(data):
            break
        cmd, cmdsize = struct.unpack("<II", data[offset : offset + 8])
        if cmd == _LC_BUILD_VERSION:
            _platform, version = struct.unpack("<II", data[offset + 8 : offset + 16])
            minos = f"{version >> 16}.{(version >> 8) & 0xFF}"
        elif cmd == _LC_VERSION_MIN_MACOSX:
            (version,) = struct.unpack("<I", data[offset + 8 : offset + 12])
            minos = f"{version >> 16}.{(version >> 8) & 0xFF}"
        elif cmd == _LC_CODE_SIGNATURE:
            signed = True
        offset += max(cmdsize, 8)
    return _CPU.get(cputype & 0xFFFFFFFF, hex(cputype & 0xFFFFFFFF)), minos, signed


def _slices(archive: zipfile.ZipFile, info: zipfile.ZipInfo, head: bytes) -> list[Any] | None:
    """Every architecture a Mach-O file carries, as (cpu, minos, signed); None if not one.

    A universal (fat) file is read slice by slice at the offsets its header names: lxml's
    macOS wheels are universal2, and scipy ships a fat file with a single slice. What matters is
    that an arm64 slice is there and which macOS it needs, not that the file is thin.
    """
    thin = _thin(head)
    if thin is not None:
        return [thin]
    if len(head) < 8 or struct.unpack(">I", head[:4])[0] not in (_FAT, _FAT_64):
        return None
    wide = struct.unpack(">I", head[:4])[0] == _FAT_64
    (count,) = struct.unpack(">I", head[4:8])
    size = 32 if wide else 20
    slices: list[Any] = []
    with archive.open(info) as member:
        for index in range(count):
            at = 8 + index * size
            if wide:
                _cpu, _sub, offset, _length, _align, _reserved = struct.unpack(
                    ">iiQQII", head[at : at + size]
                )
            else:
                _cpu, _sub, offset, _length, _align = struct.unpack(">iiIII", head[at : at + size])
            member.seek(offset)
            slice_ = _thin(member.read(1 << 16))
            if slice_ is not None:
                slices.append(slice_)
    return slices


def _records(archive: zipfile.ZipFile) -> dict[str, tuple[str, str]]:
    """Installed path -> (distribution, RECORD's sha256) for every recorded dependency file."""
    recorded: dict[str, tuple[str, str]] = {}
    for name in archive.namelist():
        if not (name.startswith(_SITE) and name.endswith(".dist-info/RECORD")):
            continue
        distribution = name[len(_SITE) :].split("-", 1)[0].lower().replace("_", "-")
        for row in archive.read(name).decode("utf-8", "replace").splitlines():
            path, _, rest = row.partition(",")
            digest = rest.partition(",")[0]
            if digest.startswith("sha256="):
                recorded[_SITE + path] = (distribution, digest[len("sha256=") :])
    return recorded


def _upstream(name: str, body: bytes, records: dict[str, tuple[str, str]]) -> bool:
    entry = records.get(name)
    if entry is None or entry[0] in _WORKSPACE:
        return False
    digest = base64.urlsafe_b64encode(hashlib.sha256(body).digest()).rstrip(b"=").decode()
    return digest == entry[1]


def _version_key(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def inspect(bundle: Path, build_paths: list[str] | None = None) -> dict[str, Any]:
    markers = build_paths or [str(Path.home()), str(bundle.resolve().parent)]
    report: dict[str, Any] = {"bundle": str(bundle), "problems": []}
    problems: list[str] = report["problems"]
    with zipfile.ZipFile(bundle) as archive:
        infos = archive.infolist()
        manifest = json.loads(archive.read("manifest.json"))
        report["manifest"] = {
            key: manifest.get(key)
            for key in ("manifest_version", "name", "version", "compatibility", "server")
        }
        report["tools"] = [tool["name"] for tool in manifest.get("tools", [])]
        slices_by_cpu: dict[str, int] = {}
        without_arm64: list[str] = []
        unsigned_arm64: list[str] = []
        universal = 0
        minimum = "0.0"
        elf = 0
        for info in infos:
            mode = info.external_attr >> 16
            name = info.filename
            if name.endswith("/"):
                problems.append(f"directory entry {name}: the MCPB unpacker cannot open it")
                continue
            if stat.S_ISLNK(mode):
                problems.append(f"symlink {name}")
            if Path(name).name in _FORBIDDEN_NAMES:
                problems.append(f"{name}: a credential file has no place in a bundle")
            head = archive.open(info).read(1 << 16) if info.file_size else b""
            if head[:4] == b"\x7fELF":
                elf += 1
            slices = _slices(archive, info, head)
            if slices is None:
                continue
            universal += len(slices) > 1
            for cpu, _minos, _signed in slices:
                slices_by_cpu[cpu] = slices_by_cpu.get(cpu, 0) + 1
            arm64 = [minos for cpu, minos, _signed in slices if cpu == "arm64"]
            if not arm64:
                without_arm64.append(name)
            if any(cpu == "arm64" and not signed for cpu, _minos, signed in slices):
                unsigned_arm64.append(name)
            for minos in arm64:
                if minos and _version_key(minos) > _version_key(minimum):
                    minimum = minos
        report["entries"] = len(infos)
        report["unpacked_bytes"] = sum(info.file_size for info in infos)
        report["macho_slices_by_cpu"] = slices_by_cpu
        report["macho_universal_files"] = universal
        report["macho_without_arm64"] = without_arm64
        report["macho_arm64_without_signature"] = unsigned_arm64
        report["macos_minimum"] = minimum if "arm64" in slices_by_cpu else None
        report["elf_files"] = elf
        client = next((info for info in infos if info.filename.endswith("oauth-client.json")), None)
        if client is None:
            report["oauth_client"] = "absent (unconfigured bundle)"
        else:
            payload = json.loads(archive.read(client))
            report["oauth_client"] = {
                "mode": oct(stat.S_IMODE(client.external_attr >> 16)),
                "client_id": payload.get("installed", {}).get("client_id"),
            }
        report["build_machine_paths_searched"] = markers
        leaks, upstream = _build_machine_paths(archive, infos, markers)
        problems.extend(f"build machine path in {leak}" for leak in leaks)
        report["upstream_files_mentioning_those_paths"] = upstream
    return report


def _build_machine_paths(
    archive: zipfile.ZipFile, infos: list[zipfile.ZipInfo], markers: list[str]
) -> tuple[list[str], list[str]]:
    """Files outside the interpreter's stdlib that name a path of the build machine.

    Returns the leaks, and separately the dependency files whose mention is upstream bytes.
    """
    # As directories: `/root` alone is also the start of `/root_model.py`.
    encoded = [marker.rstrip("/").encode() + b"/" for marker in markers if marker.strip("/")]
    records = _records(archive)
    hits: list[str] = []
    upstream: list[str] = []
    for info in infos:
        name = info.filename
        if name.startswith(_STDLIB) and not name.startswith(_SITE):
            continue
        if not name.endswith(_SCANNED_SUFFIXES) or info.file_size > 4 << 20:
            continue
        body = archive.read(info)
        if name.endswith("direct_url.json") and b"file://" in body:
            hits.append(f"{name}: records the local file it was installed from")
        found = [f"{name}: {marker.decode()}" for marker in encoded if marker in body]
        if found and _upstream(name, body, records):
            upstream.extend(found)
        else:
            hits.extend(found)
    return hits, upstream


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--expect", choices=("darwin-arm64", "linux-x86_64"), default=None)
    parser.add_argument(
        "--build-path",
        action="append",
        default=None,
        help="a path of the build machine that must not appear (default: home and bundle dir)",
    )
    arguments = parser.parse_args(argv)
    report = inspect(arguments.bundle, arguments.build_path)
    if arguments.expect == "darwin-arm64":
        for name in report["macho_without_arm64"]:
            report["problems"].append(f"{name}: a Mach-O file with no arm64 slice")
        for name in report["macho_arm64_without_signature"]:
            report["problems"].append(f"{name}: arm64 code with no code signature attached")
        if report["elf_files"]:
            report["problems"].append(f"{report['elf_files']} Linux (ELF) files in a macOS bundle")
        minimum = report["macos_minimum"]
        if minimum is None or _version_key(minimum) > _version_key(_MACOS_FLOOR):
            report["problems"].append(
                f"binaries need macOS {minimum}; the beta supports {_MACOS_FLOOR}"
            )
    print(json.dumps(report, indent=2))
    return 1 if report["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
