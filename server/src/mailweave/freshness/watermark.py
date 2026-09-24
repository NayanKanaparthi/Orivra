"""The `historyId` watermark: a non-content synchronisation stamp on disk (AD D.9, ADV-101).

MCP is stateless and there is no persistent mail-content store (B-06). LR nonetheless needs
a watermark from *before* the delivery it is meant to catch: with in-process state only, the
first query of a process has none and later ones have one minutes old, so LR would see
almost nothing. The watermark therefore persists, and everything about this module exists to
make that persistence defensible rather than to make it work.

**What it is.** Four fields and nothing else::

    {"schema": 1, "account_hash": "<sha256 hex>", "history_id": "...", "observed_at": "..."}

No message ids, no subjects, no addresses, no mail content of any kind. It is never served
as an answer, and Gmail remains the source of truth (N-03, B-06). `mailweave purge` deletes
it.

**Why the shape is enforced rather than promised.** "This file only ever holds four
non-content fields" is checkable by shape, and a promise that it will is not. `WatermarkFile`
refuses to write a payload whose key set is not exactly `Watermark.FIELDS`, and refuses
values that are not the shape each field has - a digits-only `history_id`, a hex
`account_hash`, an ISO-8601 `observed_at`. That is the same move `preflight/record.py` makes
for probe records, and for the same reason: the failure mode is a future field that carries
mail text into a persisted file, and a reviewer cannot catch what a docstring merely asks
for.

**On `account_hash`.** It exists so the file does not carry an email address in plaintext,
and so a watermark cannot be silently applied to a different mailbox. It is **not** a
secrecy measure against someone who already holds the file: an unsalted digest of an address
is reversible by anyone with a list of addresses to try. The file's protection is its mode,
and the hash's job is identity, not concealment. Saying which of those two it does is the
point of saying it at all.

**Permissions.** The directory is created `0700` and the file `0600`, with the mode set at
open time via `os.open` rather than by a later `chmod`, because a chmod after the write
leaves a window in which the file exists at the process umask. The write is atomic: a fresh
temp file inside the `0700` directory with `O_EXCL`, forced mode, `fsync`, then `replace`.
The final path therefore only ever holds a complete file at `0600`. This is deliberately the
same pattern as `auth/tokenstore.py` and imports the **same mode constants** from
`constants.py`, so the two writers cannot drift apart on what `0600` means here.

**The re-baseline is declared.** Gmail returns 404 for a `historyId` that has aged out (RO
F6). That is not an error to swallow and not a reason to silently start again: `Rebaseline`
is a value the response carries, so a caller can tell "nothing arrived" from "I lost my
place and started over". A silent re-baseline would make LR's coverage a claim nobody can
check, which is the same defect as an omission with no record.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, Final

from mailweave.constants import GMAIL_NUMERIC_ID_RE, TOKEN_DIR_MODE, TOKEN_FILE_MODE

#: Bumped when the field set changes. A reader that meets a schema it does not know treats
#: the file as absent and re-baselines, declared: a watermark it cannot interpret is worse
#: than none, because it would be used as a floor.
WATERMARK_SCHEMA: Final[int] = 1

_TEMP_SUFFIX_BYTES: Final[int] = 4
#: A historyId's own shape is `constants.GMAIL_NUMERIC_ID_RE`, imported rather than
#: rewritten: round 11 found three layers checking one shape with two hand-written
#: copies, and a fourth was exactly what writing one here would have been.
_HEX_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")


class WatermarkRefused(ValueError):
    """A payload that is not exactly the four-field shape, or a file that is not `0600`."""


def account_hash(address: str) -> str:
    """Identity for a mailbox, so a watermark cannot be applied to the wrong one.

    Case-folded because Gmail addresses are case-insensitive and the same mailbox must not
    produce two identities.
    """
    return hashlib.sha256(address.strip().casefold().encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class Watermark:
    """The four fields. Adding a fifth means bumping `WATERMARK_SCHEMA` deliberately."""

    account_hash: str
    history_id: str
    observed_at: str
    schema: int = WATERMARK_SCHEMA

    #: ClassVar, not Final: a dataclass turns any other annotated class attribute into
    #: a field, and `FIELDS` is the shape declaration, not a value each watermark
    #: carries a copy of.
    FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"schema", "account_hash", "history_id", "observed_at"}
    )

    def __post_init__(self) -> None:
        if self.schema != WATERMARK_SCHEMA:
            raise WatermarkRefused(f"unknown watermark schema {self.schema!r}")
        if not _HEX_DIGEST.fullmatch(self.account_hash):
            raise WatermarkRefused("account_hash is not a sha256 hex digest")
        if not GMAIL_NUMERIC_ID_RE.fullmatch(self.history_id):
            # A historyId is an unsigned integer Gmail hands back as a string. Anything
            # else reaching this field is something that is not a historyId, and the one
            # way mail text could arrive here is a caller passing the wrong value.
            raise WatermarkRefused("history_id is not a Gmail historyId")
        try:
            datetime.fromisoformat(self.observed_at)
        except ValueError as exc:
            raise WatermarkRefused("observed_at is not an ISO-8601 timestamp") from exc

    def as_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "account_hash": self.account_hash,
            "history_id": self.history_id,
            "observed_at": self.observed_at,
        }


def assert_payload_is_content_free(payload: Any) -> None:
    """Refuse anything that is not exactly the four-field shape.

    Exact types, not `isinstance`: a `str` subclass with its own `__str__` is written by
    `json.dumps` as its base value and read back by anything else as whatever it wants to
    be, which is `preflight/record.py`'s R-SEC-055 one file over.
    """
    if type(payload) is not dict:
        raise WatermarkRefused(f"a watermark is a JSON object, not {type(payload).__name__}")
    keys = set(payload)
    if keys != set(Watermark.FIELDS):
        extra = sorted(keys - set(Watermark.FIELDS))
        missing = sorted(set(Watermark.FIELDS) - keys)
        raise WatermarkRefused(
            f"a watermark holds exactly {sorted(Watermark.FIELDS)}; extra={extra} missing={missing}"
        )
    if type(payload["schema"]) is not int:
        raise WatermarkRefused("schema is not an int")
    for field in ("account_hash", "history_id", "observed_at"):
        if type(payload[field]) is not str:
            raise WatermarkRefused(f"{field} is not a str")


@dataclass(frozen=True, slots=True)
class Rebaseline:
    """Gmail no longer holds history from the stored watermark, and we said so.

    Carried in the response. `previous_history_id` is a synchronisation stamp, not mail
    content, so naming it costs nothing and lets a caller see how far back the lost place
    was.
    """

    previous_history_id: str
    previous_observed_at: str
    reason: str = "gmail no longer holds history from this watermark"


class WatermarkFile:
    """Read and write the watermark, or refuse."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()

    @property
    def directory(self) -> Path:
        return self.path.parent

    # -- permissions ---------------------------------------------------------------------

    @staticmethod
    def _check_mode(path: Path, expected: int) -> None:
        actual = stat.S_IMODE(path.stat().st_mode)
        if actual != expected:
            raise WatermarkRefused(
                f"{path} is {actual:o}, expected {expected:o}; a file that was readable by "
                "others may already have been read, so it is refused rather than repaired"
            )

    def ensure_directory(self) -> Path:
        directory = self.directory
        directory.mkdir(parents=True, exist_ok=True, mode=TOKEN_DIR_MODE)
        # mkdir's mode is masked by umask, so set it explicitly and then verify.
        directory.chmod(TOKEN_DIR_MODE)
        self._check_mode(directory, TOKEN_DIR_MODE)
        return directory

    # -- io ------------------------------------------------------------------------------

    def save(self, watermark: Watermark) -> None:
        """Write atomically at `0600`, refusing a payload that is not the four fields."""
        payload = watermark.as_payload()
        assert_payload_is_content_free(payload)
        directory = self.ensure_directory()
        temporary = (
            directory / f".{self.path.name}.{os.getpid()}.{secrets.token_hex(_TEMP_SUFFIX_BYTES)}"
        )
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, TOKEN_FILE_MODE)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True))
                handle.flush()
                # O_EXCL honours the mode because there is no existing file to inherit
                # from, but a filesystem that ignores it would leave the window open.
                os.fchmod(handle.fileno(), TOKEN_FILE_MODE)
                os.fsync(handle.fileno())
            self._check_mode(temporary, TOKEN_FILE_MODE)
            temporary.replace(self.path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    def load(self) -> Watermark | None:
        """The stored watermark, or `None` when there is nothing usable.

        `None` means "re-baseline", and the caller declares that. A corrupt or
        unknown-schema file reads as absent rather than raising, because a watermark is a
        convenience and losing it must not stop the server answering; an **over-permissive**
        file is different and is refused, because it may already have been read.
        """
        if not self.path.exists():
            return None
        self._check_mode(self.path, TOKEN_FILE_MODE)
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            assert_payload_is_content_free(payload)
            return Watermark(
                account_hash=payload["account_hash"],
                history_id=payload["history_id"],
                observed_at=payload["observed_at"],
                schema=payload["schema"],
            )
        except (OSError, ValueError):
            return None

    def load_for(self, address: str) -> Watermark | None:
        """The watermark, but only if it belongs to this mailbox.

        A watermark from another account is not a floor for this one: walking history from
        it would either 404 or, worse, succeed against an unrelated sequence.
        """
        stored = self.load()
        if stored is None:
            return None
        return stored if stored.account_hash == account_hash(address) else None

    @staticmethod
    def _digest_of(identity: str) -> str:
        """Any identity string, as the sha256 hex digest this file's schema requires.

        Hashed rather than stored verbatim, for the same reason the address is: the file's
        one job beyond holding a `historyId` is to be **content-free**, and a caller's own
        identity spelling is something this module cannot vouch for. Hashing it makes the
        stored value a digest whatever the caller hands in, and `Watermark.__post_init__`
        refuses anything that is not one - so the invariant is checked rather than trusted.
        """
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def load_for_identity(self, identity: str) -> Watermark | None:
        """The watermark, but only if it was stored under this identity.

        **The identity is whatever the caller uses to tell its mailboxes apart, not
        necessarily `account_hash(address)`.** The server already holds a salted account
        digest for handle verification and has no reason to spend a `users.getProfile` call
        to recompute a second one; what this file needs of an identity is only that it
        differs between mailboxes and is stable for one. A caller whose identity scheme
        changes - a rotated salt, say - reads no watermark and re-baselines, which is the
        safe direction: a watermark from the wrong mailbox would either 404 or, worse,
        succeed against an unrelated sequence.
        """
        stored = self.load()
        if stored is None:
            return None
        return stored if stored.account_hash == self._digest_of(identity) else None

    def observe_identity(self, *, identity: str, history_id: str) -> Watermark:
        """Record a `historyId` under a caller-supplied identity. See `load_for_identity`."""
        watermark = Watermark(
            account_hash=self._digest_of(identity), history_id=history_id, observed_at=_now()
        )
        self.save(watermark)
        return watermark

    def observe(self, *, address: str, history_id: str) -> Watermark:
        """Record a `historyId` this response actually saw, and return what was stored."""
        watermark = Watermark(
            account_hash=account_hash(address),
            history_id=history_id,
            observed_at=_now(),
        )
        self.save(watermark)
        return watermark

    def rebaseline(self, previous: Watermark) -> Rebaseline:
        """Declare that the stored place was lost. The caller puts this in the response."""
        return Rebaseline(
            previous_history_id=previous.history_id,
            previous_observed_at=previous.observed_at,
        )

    def purge(self) -> bool:
        """Delete it. Returns whether there was anything to delete (`mailweave purge`)."""
        existed = self.path.exists()
        self.path.unlink(missing_ok=True)
        return existed
