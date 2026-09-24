"""The watermark: four fields, 0600, and a re-baseline nobody can miss (AD D.9, ADV-101).

The property under test is not "it round-trips". It is that the file **cannot** come to hold
anything but a non-content synchronisation stamp, and that losing one's place is a value in
the response rather than a silence.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from mailweave.constants import TOKEN_DIR_MODE, TOKEN_FILE_MODE
from mailweave.freshness import (
    WATERMARK_SCHEMA,
    Watermark,
    WatermarkFile,
    WatermarkRefused,
    account_hash,
    assert_payload_is_content_free,
)

ADDRESS = "someone@example.com"


def _file(tmp_path: Path) -> WatermarkFile:
    return WatermarkFile(tmp_path / "state" / "watermark.json")


# --- the file holds four fields and nothing else ---------------------------------------
def test_a_saved_watermark_is_exactly_the_declared_keys(tmp_path: Path) -> None:
    store = _file(tmp_path)
    store.observe(address=ADDRESS, history_id="99120034")
    written = json.loads(store.path.read_text(encoding="utf-8"))
    assert set(written) == set(Watermark.FIELDS)
    assert written["schema"] == WATERMARK_SCHEMA


def test_no_address_or_message_id_reaches_the_file(tmp_path: Path) -> None:
    store = _file(tmp_path)
    store.observe(address=ADDRESS, history_id="99120034")
    raw = store.path.read_text(encoding="utf-8")
    assert ADDRESS not in raw
    assert "example.com" not in raw
    assert "someone" not in raw


def test_an_extra_key_is_refused_rather_than_written() -> None:
    # The failure mode is a future field carrying mail text into a persisted file. A
    # docstring asking for four fields cannot catch that; a key-set check can.
    with pytest.raises(WatermarkRefused, match="extra="):
        assert_payload_is_content_free(
            {
                "schema": 1,
                "account_hash": "0" * 64,
                "history_id": "1",
                "observed_at": "2026-09-11T00:00:00+00:00",
                "subject": "quarterly numbers",
            }
        )


def test_a_missing_key_is_refused() -> None:
    with pytest.raises(WatermarkRefused, match="missing="):
        assert_payload_is_content_free({"schema": 1, "account_hash": "0" * 64})


def test_a_history_id_that_is_not_a_history_id_is_refused() -> None:
    # The one way mail text could arrive in this field is a caller passing the wrong
    # value, so the field is bounded by shape rather than trusted.
    with pytest.raises(WatermarkRefused, match="history_id"):
        Watermark(
            account_hash=account_hash(ADDRESS),
            history_id="Re: the Harbor export mismatch",
            observed_at="2026-09-11T00:00:00+00:00",
        )


def test_an_account_hash_that_is_not_a_digest_is_refused() -> None:
    with pytest.raises(WatermarkRefused, match="account_hash"):
        Watermark(
            account_hash=ADDRESS,
            history_id="1",
            observed_at="2026-09-11T00:00:00+00:00",
        )


def test_a_str_subclass_does_not_pass_for_a_str() -> None:
    class Sneaky(str):
        def __str__(self) -> str:  # pragma: no cover - never reached if refused
            return "a mail body"

    with pytest.raises(WatermarkRefused, match="history_id is not a str"):
        assert_payload_is_content_free(
            {
                "schema": 1,
                "account_hash": "0" * 64,
                "history_id": Sneaky("1"),
                "observed_at": "2026-09-11T00:00:00+00:00",
            }
        )


# --- permissions ------------------------------------------------------------------------
def test_the_directory_is_0700_and_the_file_0600(tmp_path: Path) -> None:
    store = _file(tmp_path)
    store.observe(address=ADDRESS, history_id="1")
    assert stat.S_IMODE(store.directory.stat().st_mode) == TOKEN_DIR_MODE
    assert stat.S_IMODE(store.path.stat().st_mode) == TOKEN_FILE_MODE


def test_an_over_permissive_file_is_refused_rather_than_repaired(tmp_path: Path) -> None:
    # A file that was group-readable may already have been read. Repairing it silently
    # would leave nobody with any way to know that.
    store = _file(tmp_path)
    store.observe(address=ADDRESS, history_id="1")
    store.path.chmod(0o644)
    with pytest.raises(WatermarkRefused, match="already have been read"):
        store.load()


def test_no_temporary_file_survives_a_write(tmp_path: Path) -> None:
    store = _file(tmp_path)
    store.observe(address=ADDRESS, history_id="1")
    assert [p.name for p in store.directory.iterdir()] == ["watermark.json"]


def test_a_failed_write_leaves_no_partial_file(tmp_path: Path) -> None:
    store = _file(tmp_path)
    store.observe(address=ADDRESS, history_id="1")
    before = store.path.read_text(encoding="utf-8")

    class Exploding(Watermark):
        def as_payload(self) -> dict[str, object]:
            raise OSError("disk went away")

    with pytest.raises(OSError):
        store.save(
            Exploding(
                account_hash=account_hash(ADDRESS),
                history_id="2",
                observed_at="2026-09-11T00:00:00+00:00",
            )
        )
    assert store.path.read_text(encoding="utf-8") == before
    assert [p.name for p in store.directory.iterdir()] == ["watermark.json"]


# --- losing the place is a value, not a silence -----------------------------------------
def test_an_absent_file_reads_as_none(tmp_path: Path) -> None:
    assert _file(tmp_path).load() is None


def test_a_corrupt_file_reads_as_absent_rather_than_stopping_the_server(tmp_path: Path) -> None:
    store = _file(tmp_path)
    store.ensure_directory()
    descriptor = os.open(store.path, os.O_WRONLY | os.O_CREAT, TOKEN_FILE_MODE)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write("{not json")
    assert store.load() is None


def test_an_unknown_schema_reads_as_absent(tmp_path: Path) -> None:
    # A watermark we cannot interpret is worse than none: it would be used as a floor.
    store = _file(tmp_path)
    store.observe(address=ADDRESS, history_id="1")
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    payload["schema"] = WATERMARK_SCHEMA + 1
    descriptor = os.open(store.path, os.O_WRONLY | os.O_TRUNC, TOKEN_FILE_MODE)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload))
    assert store.load() is None


def test_another_mailboxs_watermark_is_not_a_floor_for_this_one(tmp_path: Path) -> None:
    # Walking history from it would either 404 or, worse, succeed against an unrelated
    # sequence and report someone else's arrivals as this mailbox's.
    store = _file(tmp_path)
    store.observe(address="other@example.com", history_id="500")
    assert store.load() is not None
    assert store.load_for(ADDRESS) is None


def test_a_rebaseline_names_the_place_that_was_lost(tmp_path: Path) -> None:
    store = _file(tmp_path)
    stored = store.observe(address=ADDRESS, history_id="42")
    declared = store.rebaseline(stored)
    assert declared.previous_history_id == "42"
    assert declared.previous_observed_at == stored.observed_at
    assert "no longer holds history" in declared.reason


# --- purge ------------------------------------------------------------------------------
def test_purge_deletes_it_and_says_whether_there_was_anything(tmp_path: Path) -> None:
    store = _file(tmp_path)
    assert store.purge() is False
    store.observe(address=ADDRESS, history_id="1")
    assert store.purge() is True
    assert not store.path.exists()
