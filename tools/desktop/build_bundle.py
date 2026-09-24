"""Build the Orivra desktop beta as a Claude Desktop extension (`.mcpb`), without its OAuth client.

    python3 tools/desktop/build_bundle.py --platform darwin-arm64 \\
        --python-archive <cpython-...-install_only_stripped.tar.gz> --out dist/desktop

The result is a zip whose layout is MCPB's (manifest 0.3, server type `binary`):

    manifest.json
    server/orivra-beta        the launcher (`tools/desktop/bundle/orivra-beta`), 0755
    server/python/            python-build-standalone CPython 3.12, pinned by digest
    server/python/lib/python3.12/site-packages/
                              the product (mailweave, orivra) and every dependency, installed
                              from the committed uv.lock with its hashes, for the target platform
    server/models.lock        the reviewed model lock; the weights are downloaded at setup

**It carries no OAuth client and no credential.** `configure_bundle.py` adds the beta's client
file on the owner's machine, where that file lives; nothing this script produces can
authenticate anything. No account token exists at build time at all - one is created on each
tester's own machine when they consent.

**Why a bundled interpreter.** Claude Desktop ships Node.js, not Python; an MCPB `python`
server uses whatever Python the machine has, and compiled dependencies (pydantic's core, and
for the semantic rung torch) only load on the platform they were built for. So the beta is a
`binary` server: a relocatable CPython for the target, and wheels resolved for the target by
`uv pip install --python-platform`, both pinned, neither taken from the machine it is built on.

Stdlib only, and runnable on Python 3.10, because it runs wherever `uv` does; it calls `uv`
for exporting the lock, building the two workspace wheels and installing for the target.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

#: What each supported target needs from uv and from the manifest. `darwin-arm64` is the beta
#: (Apple Silicon; torch's macOS wheels start at macOS 14). `linux-x86_64` exists for the
#: clean-install proof only and is built without the semantic extra: torch's Linux wheels
#: pull several gigabytes of CUDA libraries, and the proof environment cannot reach the model
#: host anyway. It is never distributed.
PLATFORMS: dict[str, dict[str, object]] = {
    "darwin-arm64": {
        "uv_platform": "aarch64-apple-darwin",
        "env": {"MACOSX_DEPLOYMENT_TARGET": "14.0"},
        "manifest_platforms": ["darwin"],
        "semantic": True,
    },
    "linux-x86_64": {
        "uv_platform": "x86_64-manylinux_2_28",
        "env": {},
        "manifest_platforms": ["linux"],
        "semantic": False,
    },
}

#: Parts of python-build-standalone that an MCP server never runs. Symlinks are dropped for a
#: different reason: a zip carries them badly, and the launcher names `python3.12` itself.
_RUNTIME_DROP = ("python/include", "python/share", "python/lib/pkgconfig")
#: What is removed from site-packages after installing: `pip`, which no locked distribution needs
#: and an MCP server never runs. **Nothing the lock carries is removed.** `setuptools` used to be:
#: torch declares it (`Requires-Dist: setuptools>=77.0.3`), the lock resolves it for this
#: platform, and dropping it made the bundle's distributions differ from the locked set
#: (2026-09-24, found by comparing the bundle with `uv export` for darwin-arm64).
#: `test_nothing_the_lock_carries_is_dropped_from_the_bundle` holds this.
_SITE_DROP_PREFIXES = ("pip",)


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    print("+", " ".join(command), file=sys.stderr)
    merged = dict(os.environ)
    merged.update(env or {})
    completed = subprocess.run(
        command, cwd=cwd, env=merged, check=True, text=True, stdout=subprocess.PIPE
    )
    return completed.stdout


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _version() -> str:
    """The product version, as MCPB's semver wants it: `0.2.0b1` -> `0.2.0-beta.1`."""
    for line in (REPO / "orivra" / "pyproject.toml").read_text().splitlines():
        if line.startswith("version = "):
            raw = line.split("=", 1)[1].strip().strip('"')
            if "b" in raw:
                base, _, number = raw.partition("b")
                return f"{base}-beta.{number}"
            return raw
    raise SystemExit("no version in orivra/pyproject.toml")


def _unpack_runtime(archive: Path, platform: str, into: Path) -> None:
    pins = json.loads((HERE / "python-runtime.json").read_text())
    pin = pins["platforms"][platform]
    if archive.name != pin["archive"]:
        raise SystemExit(f"{archive.name} is not the pinned archive {pin['archive']}")
    actual = _sha256(archive)
    if actual != pin["sha256"]:
        raise SystemExit(f"{archive.name}: sha256 {actual} does not match the pin {pin['sha256']}")
    with tarfile.open(archive) as bundle:
        members = [member for member in bundle.getmembers() if not member.issym()]
        bundle.extractall(into, members=members, filter="tar")
    for relative in _RUNTIME_DROP:
        shutil.rmtree(into / relative, ignore_errors=True)
    bin_dir = into / "python" / "bin"
    for entry in bin_dir.iterdir():
        if entry.name != "python3.12":
            entry.unlink()


def _site_packages(stage: Path) -> Path:
    return stage / "server" / "python" / "lib" / "python3.12" / "site-packages"


def _install_dependencies(stage: Path, platform: str, work: Path, build_python: Path) -> None:
    spec = PLATFORMS[platform]
    # Pointed at a scratch path so no `uv` call here can create, sync or even find the
    # checkout's own `.venv` - which on the owner's machine belongs to another platform.
    project_env = {"UV_PROJECT_ENVIRONMENT": str(work / "never-a-venv")}
    export = ["uv", "export", "--frozen", "--no-dev", "--no-emit-workspace"]
    export += ["--package", "mailweave", "--format", "requirements-txt"]
    if spec["semantic"]:
        export += ["--extra", "semantic"]
    requirements = work / "requirements.txt"
    requirements.write_text(_run(export, cwd=REPO, env=project_env))
    site = _site_packages(stage)
    env = {"UV_NO_CONFIG": "1", **spec["env"]}  # type: ignore[dict-item]
    # `--python` is the build machine's own 3.12, for uv to resolve with; the target is still
    # the platform named, and nothing is installed into that interpreter.
    target = [
        "uv", "pip", "install", "--no-config", "--python", str(build_python),
        "--target", str(site),
        "--python-platform", str(spec["uv_platform"]), "--python-version", "3.12",
        "--only-binary", ":all:",
    ]  # fmt: skip
    _run([*target, "--require-hashes", "-r", str(requirements)], cwd=work, env=env)
    wheels = work / "wheels"
    for package in ("mailweave", "orivra"):
        _run(
            ["uv", "build", "--package", package, "--wheel", "--out-dir", str(wheels)],
            cwd=REPO,
            env=project_env,
        )
    built = sorted(str(wheel) for wheel in wheels.glob("*.whl"))
    _run([*target, "--no-deps", *built], cwd=work, env=env)
    for package in ("mailweave", "orivra"):
        forget_install_location(site, package)
    for entry in list(site.iterdir()):
        if entry.name == "bin" or entry.name.startswith(_SITE_DROP_PREFIXES):
            shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
    prune_records(site)


#: What installing a local wheel records about where it came from: PEP 610's `direct_url.json`
#: names the wheel file's path in this build's scratch directory, under the builder's home, and
#: uv's `uv_cache.json` the time it was built. Nothing at run time reads either.
_INSTALL_LOCATION_FILES = ("direct_url.json", "uv_cache.json")


def forget_install_location(site: Path, package: str) -> None:
    """Drop what the installation recorded about the local wheel `package` came from.

    Found by `inspect_bundle.py` (`direct_url.json`) and by comparing two builds entry by entry
    (`uv_cache.json`). The `RECORD` lines go with the files, in `prune_records`.
    """
    for info in site.glob(f"{package}-*.dist-info"):
        for name in _INSTALL_LOCATION_FILES:
            (info / name).unlink(missing_ok=True)


def _carried(site: Path, recorded: str) -> bool:
    path = (site / recorded).resolve()
    return path.is_relative_to(site.resolve()) and path.exists()


def prune_records(site: Path) -> None:
    """Make every `RECORD` list only files the bundle carries.

    Installing writes console scripts to `bin/` - with the build interpreter's path in their
    first line - and lists them in `RECORD`; the bundle drops `bin/`, pip and setuptools, and
    the install-location files above. A `RECORD` naming files that are not there is untrue
    about the installation, and its hashes of those scripts differ with the machine that built
    it. Lines for files that exist are kept byte for byte, in order.
    """
    (site / ".lock").unlink(missing_ok=True)  # uv's lock on the target directory
    for record in site.glob("*.dist-info/RECORD"):
        lines = record.read_text(encoding="utf-8").splitlines()
        kept = [line for line in lines if line and _carried(site, line.rsplit(",", 2)[0])]
        if kept != lines:
            record.write_text("\n".join(kept) + "\n", encoding="utf-8")


def _manifest(platform: str) -> dict[str, object]:
    tools = json.loads((HERE / "bundle" / "tools.json").read_text())
    spec = PLATFORMS[platform]
    return {
        "manifest_version": "0.3",
        "name": "orivra-beta",
        "display_name": "Orivra (beta)",
        "version": _version(),
        "description": (
            "Ask Claude about your Gmail, read-only. Orivra retrieves the evidence on this "
            "computer and shows what it did not see."
        ),
        "long_description": (
            "An early beta. After installing, ask Claude to set up Orivra: you connect "
            "Gmail through the beta's Google application (read-only; until the application "
            "completes Google's verification for this permission, Google shows an "
            "unverified-app warning before consent), the two local models download with "
            "progress, and the connection is verified. Your authorization stays on this "
            "computer. The only permission requested is Gmail read-only."
        ),
        "author": {"name": "Orivra beta"},
        "license": "MIT",
        "server": {
            "type": "binary",
            "entry_point": "server/orivra-beta",
            "mcp_config": {"command": "/bin/sh", "args": ["${__dirname}/server/orivra-beta"]},
        },
        "tools": tools,
        "compatibility": {"platforms": spec["manifest_platforms"]},
        "keywords": ["gmail", "email", "read-only", "evidence"],
    }


def _copy_notices(stage: Path) -> None:
    """Carry the project's licence and distinguish it from dependency licences."""
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copyfile(REPO / name, stage / name)


def _compile(stage: Path, compiler: Path) -> None:
    """Byte-compile with `unchecked-hash` pycs, so the first start is not a compile.

    **With the same Python release the bundle ships.** An unchecked-hash pyc is never checked
    against its source again, so it should be exactly what the bundled interpreter would have
    written; bytecode is platform-independent, so a build machine's CPython of the same release
    can write it. A different 3.12.x writes different bytes (found by comparing two builds entry
    by entry), so any other version is refused rather than trusted. Source paths are rewritten
    to be relative to the bundle, so a traceback in the extension's log does not name the
    machine it was built on.
    """
    wanted = json.loads((HERE / "python-runtime.json").read_text())["python"]
    output = subprocess.run(
        [str(compiler), "-c", "import platform; print(platform.python_version())"],
        check=True, text=True, stdout=subprocess.PIPE,
    ).stdout.strip()  # fmt: skip
    if output != wanted:
        raise SystemExit(
            f"--build-python must be CPython {wanted}, the bundled release, not {output}"
        )
    lib = stage / "server" / "python" / "lib" / "python3.12"
    subprocess.run(
        [
            str(compiler), "-m", "compileall", "-q", "-j", "0",
            "--invalidation-mode", "unchecked-hash",
            "-s", str(stage), "-p", "orivra-beta", str(lib),
        ],
        check=False,
    )  # fmt: skip


def _mode(path: Path) -> int:
    current = stat.S_IMODE(path.stat().st_mode)
    return 0o755 if current & 0o111 else 0o644


def zip_entry(name: str, mode: int) -> zipfile.ZipInfo:
    """One regular-file entry as `mcpb pack` writes it: Unix host, mode in the high bits.

    **Files only - no directory entries.** The MCPB unpacker opens every entry as a file, so a
    `server/` entry fails an install with `EISDIR` (found on this bundle's first build, with
    `mcpb unpack`); directories are implied by the paths, as they are in `mcpb pack`'s output.
    """
    info = zipfile.ZipInfo(name)
    info.date_time = (2026, 9, 23, 0, 0, 0)
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | mode) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def _zip(stage: Path, output: Path) -> None:
    """Write the `.mcpb`: deterministic order, Unix modes, no symlinks, no directories."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(stage.rglob("*")):
            if path.is_symlink():
                raise SystemExit(f"{path} is a symlink; the bundle carries none")
            if path.is_dir():
                continue
            relative = path.relative_to(stage).as_posix()
            bundle.writestr(zip_entry(relative, _mode(path)), path.read_bytes())


def build(platform: str, archive: Path, out: Path, build_python: Path) -> Path:
    if platform not in PLATFORMS:
        raise SystemExit(f"unknown platform {platform}; one of {sorted(PLATFORMS)}")
    # Scratch beside the output: the build is several hundred megabytes, and a small `/tmp`
    # is the first thing it would fill.
    with tempfile.TemporaryDirectory(prefix=".orivra-beta-build-", dir=out) as scratch:
        work = Path(scratch)
        stage = work / "stage"
        (stage / "server").mkdir(parents=True)
        _unpack_runtime(archive, platform, stage / "server")
        _install_dependencies(stage, platform, work, build_python)
        launcher = stage / "server" / "orivra-beta"
        shutil.copyfile(HERE / "bundle" / "orivra-beta", launcher)
        launcher.chmod(0o755)
        shutil.copyfile(REPO / "models.lock", stage / "server" / "models.lock")
        _copy_notices(stage)
        (stage / "manifest.json").write_text(json.dumps(_manifest(platform), indent=2) + "\n")
        _compile(stage, build_python)
        name = f"orivra-beta-{_version()}-{platform}-unconfigured.mcpb"
        target = out / name
        _zip(stage, target)
    files = zipfile.ZipFile(target).infolist()
    unpacked = sum(info.file_size for info in files)
    print(
        json.dumps(
            {
                "bundle": str(target),
                "sha256": _sha256(target),
                "zipped_bytes": target.stat().st_size,
                "unpacked_bytes": unpacked,
                "entries": len(files),
            },
            indent=2,
        )
    )
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--platform", required=True, choices=sorted(PLATFORMS))
    parser.add_argument("--python-archive", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=REPO / "dist" / "desktop")
    parser.add_argument(
        "--build-python",
        type=Path,
        required=True,
        help=(
            "a CPython of the bundled release (python-runtime.json's `python`) that runs on "
            "this build machine: uv resolves with it and the bundle is byte-compiled with it. "
            "Nothing is installed into it"
        ),
    )
    arguments = parser.parse_args(argv)
    arguments.out.mkdir(parents=True, exist_ok=True)
    build(arguments.platform, arguments.python_archive, arguments.out, arguments.build_python)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
