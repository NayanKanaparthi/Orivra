"""The source, workspace packages, and desktop builder carry the owner's MIT licence."""

from __future__ import annotations

import json
import tomllib
import zipfile
from pathlib import Path

import pytest

from tools.desktop import build_bundle

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("package", [".", "server", "orivra", "harness"])
def test_workspace_metadata_and_licence_text_agree(package: str) -> None:
    root_licence = (REPO / "LICENSE").read_bytes()
    assert root_licence.startswith(b"MIT License\n")
    assert b"Copyright (c) 2026 Nayan Kanaparthi" in root_licence
    assert b"Permission is hereby granted, free of charge" in root_licence
    assert b'THE SOFTWARE IS PROVIDED "AS IS"' in root_licence
    directory = REPO / package
    metadata = tomllib.loads((directory / "pyproject.toml").read_text())["project"]
    assert metadata["license"] == "MIT"
    assert metadata["license-files"] == ["LICENSE"]
    assert (directory / "LICENSE").read_bytes() == root_licence


@pytest.mark.parametrize("platform", sorted(build_bundle.PLATFORMS))
def test_desktop_manifest_uses_mit_without_invite_only_restrictions(platform: str) -> None:
    manifest = build_bundle._manifest(platform)
    assert manifest["license"] == "MIT"
    assert manifest["display_name"] == "Orivra (beta)"
    text = json.dumps(manifest).lower()
    assert "invite-only" not in text
    assert "not for redistribution" not in text
    assert "unverified-app warning" in text


def test_desktop_zip_contains_unmodified_project_and_third_party_notices(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    build_bundle._copy_notices(stage)
    output = tmp_path / "notices.mcpb"
    build_bundle._zip(stage, output)
    with zipfile.ZipFile(output) as archive:
        assert set(archive.namelist()) == {"LICENSE", "THIRD_PARTY_NOTICES.md"}
        for name in archive.namelist():
            assert archive.read(name) == (REPO / name).read_bytes()
