"""The credential store: 0600 file inside a 0700 directory (AD A.4, RR SEC-04).

The store holds the refresh token and the profile salt. Both are secrets, so:

  * the directory is created 0700 and the file 0600, with the mode set **at open time**
    via `os.open`, not afterwards - a chmod after the write leaves a window in which the
    file exists with the process umask;
  * reads refuse an over-permissive file rather than repairing it silently. A file that
    was group-readable may already have been read.
"""

from __future__ import annotations

import json
import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path

from pydantic import ConfigDict, Field, SecretStr, field_validator

from mailweave.constants import SALT_BYTES, SERVER_SCOPES, TOKEN_DIR_MODE, TOKEN_FILE_MODE
from mailweave.envelope.wire import parse_instant
from mailweave.errors import SecretDocumentMalformed, TokenStoreError
from mailweave.validation import SecretBearingModel

#: Bytes of randomness in a temp file's suffix. Enough that two saves in the same process
#: in the same instant do not collide on `O_EXCL`; the name is not a secret.
TEMP_SUFFIX_BYTES = 4


def _is_ascii_decimal(value: str) -> bool:
    """Whether `value` is the ASCII decimal `_temporary_name` writes (R-SEC-035).

    `str.isdigit()` alone was the guard and `int()` was the use, and the two disagree:
    `"²".isdigit()` is `True` and `int("²")` raises `ValueError`, so a file named
    `.credentials.json.².abcd` in the credential directory made `sweep_orphaned_temporaries`
    raise out of `save()` - out of a method whose own docstring promises "every error is
    swallowed". Reproduced against a real store, not at the interpreter.

    ASCII rather than merely non-crashing, because `int()` *accepts* Arabic-Indic and
    fullwidth digits: `int("١٣")` is 13. A guard that only stopped the crash would leave
    `.credentials.json.١٣.abcd` being read as "PID 13" and its file deleted on the strength
    of a name this store never wrote. The name is written by `_temporary_name` from
    `os.getpid()`, which is ASCII decimal; anything else is not this store's file and is
    left for a human, which is what the sweep already promises for a name it cannot parse.
    """
    return value.isascii() and value.isdigit()


def _process_is_alive(pid: int) -> bool:
    """Whether `pid` names a running process. A permission error means alive, not absent."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:  # pragma: no cover - platform without signal semantics
        return True
    return True


class StoredCredentials(SecretBearingModel):
    """What lives in the token store. No mail content ever appears here.

    `SecretBearingModel`, not `BaseModel`: this file holds the refresh token, so no
    rendering of a failure to validate it may quote what it refused (R-SEC-043,
    `mailweave.validation`). Every value in this file is a candidate secret, not only the
    one field named for one - a corrupt save that writes the token into `obtained_at`
    reaches a different validator and the same disclosure.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    client_id: str = Field(min_length=1)
    refresh_token: SecretStr
    scopes: tuple[str, ...] = SERVER_SCOPES
    salt_hex: str = Field(min_length=2)
    obtained_at: str = Field(min_length=1)
    key_epoch: int = Field(default=0, ge=0)
    #: The HMAC key `map_id` handles are signed with (AD A.10, ADV-212), hex-encoded.
    #: **In this file rather than in process memory** because a key held only in memory makes
    #: every restart invalidate every outstanding handle - which is the misattributed
    #: `handle_expired`-on-a-fresh-handle the previous design produced. `None` means this
    #: server has never minted a handle; `mailweave.handles.keys.ensure_handle_key` generates
    #: one on first use and saves it back through the one atomic 0600-creating path here.
    #: A `SecretStr` like `refresh_token`, so this model's existing refusal to quote its own
    #: input covers it: the reflection canary in `tests/fixtures/secret_models.py` discovers
    #: the field from `model_fields` and generates its corruption shapes without being told.
    map_key_hex: SecretStr | None = None

    @field_validator("obtained_at")
    @classmethod
    def _obtained_at_is_an_instant(cls, value: str) -> str:
        """The same `parse_instant` check `fetched_at` and `verified_at` carry (R-SEC-034).

        The fifth appearance in this project of "one shape validated, its peers trusted":
        two timestamps on the wire were instant-checked and the one in the credential file
        took any non-empty string, so a whole sentence stored cleanly under a field named
        for a moment in time.

        Lower stakes than the disclosed cases, deliberately said rather than implied: this
        file is local, 0600, never disclosed, and **nothing reads this field back in
        production code today**. That is not a reason to leave it - a field with no reader
        is exactly the one that stays unchecked until it acquires one - but it is why this
        is LOW and R-SEC-032 is HIGH.

        `parse_instant` is imported rather than restated. It is the round-10 rule applied to
        itself: this round exists because one Gmail shape had two separately written checks
        and the second layer got the missing one.
        """
        parse_instant("obtained_at", value)
        return value

    @property
    def salt(self) -> bytes:
        return bytes.fromhex(self.salt_hex)


@dataclass(frozen=True)
class TokenStore:
    """File-backed credential store."""

    path: Path

    @property
    def directory(self) -> Path:
        return self.path.parent

    # -- permissions -------------------------------------------------------------------

    def _check_mode(self, path: Path, expected: int) -> None:
        try:
            mode = stat.S_IMODE(path.stat().st_mode)
        except FileNotFoundError as missing:
            # **Existence before permissions** (round 25, R-MCP-007). `verify_permissions`
            # stat'ed before it checked, so `mailweave serve` on the exact condition OD-6
            # criterion 1 is about - a first run, before `auth login`, or after `purge` -
            # printed a `FileNotFoundError` traceback naming the operator's absolute paths
            # instead of refusing with a cause and a next step. `TokenStoreError` is caught
            # by every command that reads the store, so the refusal reaches the operator.
            raise TokenStoreError(
                f"{path} does not exist. This server refuses to start without a stored "
                "credential; run `mailweave auth login` to authorise the read-only client."
            ) from missing
        except OSError as unreadable:
            raise TokenStoreError(
                f"{path} could not be read ({type(unreadable).__name__}); a credential path "
                "this process cannot stat is a credential path it may not use."
            ) from unreadable
        if mode & 0o077:
            raise TokenStoreError(
                f"{path} has mode {mode:04o}; expected {expected:04o}. Refusing to use a "
                "credential path that other local users can read."
            )

    def ensure_directory(self) -> Path:
        directory = self.directory
        directory.mkdir(parents=True, exist_ok=True, mode=TOKEN_DIR_MODE)
        # mkdir's mode is masked by umask, so set it explicitly and then verify.
        directory.chmod(TOKEN_DIR_MODE)
        self._check_mode(directory, TOKEN_DIR_MODE)
        return directory

    def verify_permissions(self) -> None:
        self._check_mode(self.directory, TOKEN_DIR_MODE)
        self._check_mode(self.path, TOKEN_FILE_MODE)

    # -- io -----------------------------------------------------------------------------

    def _temporary_name(self) -> str:
        return f".{self.path.name}.{os.getpid()}.{secrets.token_hex(TEMP_SUFFIX_BYTES)}"

    def sweep_orphaned_temporaries(self) -> int:
        """Delete temp files a killed `save()` left behind. Returns how many went.

        R-SEC-012, LOW: a `SIGKILL` between `fsync` and `replace` leaves
        `.credentials.json.<pid>.<hex>` on disk holding the refresh token. That is not a
        disclosure - the file is 0600 inside a 0700 directory, which is exactly the
        store's guarantee, and `save()`'s own `except` clause already removes it for every
        failure the process survives. It is housekeeping: nothing ever removed the file a
        process did not survive, so they accumulate for as long as the store exists.

        A leftover is only swept when the PID in its name belongs to no live process. A
        temp file whose writer is still running is another `save()` in flight, and
        deleting it would turn a housekeeping sweep into the crash it exists to clean up
        after. PID reuse can make a dead orphan look alive, in which case it survives this
        sweep and is collected by a later one - a file left behind is the failure mode
        this method tolerates, and a file taken from a live writer is not.

        Every error is swallowed: the sweep is not what the caller asked for, and a
        credential save must not fail because a stale file could not be removed.
        """
        swept = 0
        prefix = f".{self.path.name}."
        try:
            candidates = list(self.directory.iterdir())
        except OSError:  # pragma: no cover - unreadable directory is the caller's problem
            return 0
        for candidate in candidates:
            name = candidate.name
            if not name.startswith(prefix) or candidate == self.path:
                continue
            fields = name[len(prefix) :].split(".")
            if len(fields) != 2 or not _is_ascii_decimal(fields[0]):
                continue  # not a name this store writes; leave it for a human
            if _process_is_alive(int(fields[0])):
                continue
            try:
                candidate.unlink()
            except OSError:  # pragma: no cover - a race with another sweep
                continue
            swept += 1
        return swept

    def save(self, credentials: StoredCredentials) -> None:
        """Write the credential file atomically (RR SEC-04, R-SEC-003).

        `os.open`'s `mode` argument is applied by the kernel **only when the file is
        created**. Round 1 wrote straight to the final path, so a path that already
        existed at 0644 - a stale file from a prior run, a misconfigured deploy, anything
        that touched it first - kept its permissions for the whole of the write, and the
        forcing `chmod` came afterwards. R-SEC-003 killed the process in that window and
        recovered the refresh token from a world-readable file.

        So: create a fresh temp file inside the 0700 directory with `O_EXCL` (its mode is
        therefore honoured, there being no existing file to inherit from), write, force
        the mode, flush to disk, and rename it onto the final path. `Path.replace` is
        atomic within a filesystem, so the final path only ever holds a complete file at
        0600 - there is no instant at which it exists in an intermediate state, which is
        what makes the crash window closed rather than merely narrow.

        The one thing that shape leaves behind is a temp file from a save the process did
        not survive, which `sweep_orphaned_temporaries` collects here (R-SEC-012).
        """
        self.ensure_directory()
        self.sweep_orphaned_temporaries()
        payload = credentials.model_dump(mode="json")
        payload["refresh_token"] = credentials.refresh_token.get_secret_value()
        # Every `SecretStr` has to be unwrapped for the write, not only the one this method
        # was originally written for: `model_dump` renders a secret as `**********`, so a
        # field added later and not unwrapped here is silently persisted as asterisks and
        # read back as a key that verifies nothing. Written as a sweep over the model's own
        # secret fields rather than as a second named line, because a second named line is
        # what makes the third field the one nobody adds (R-SEC-043's shape, one round on).
        for name, value in credentials:
            if isinstance(value, SecretStr):
                payload[name] = value.get_secret_value()
        temporary = self.path.with_name(self._temporary_name())
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, TOKEN_FILE_MODE)
        try:
            try:
                handle = os.fdopen(descriptor, "w", encoding="utf-8")
            except BaseException:  # pragma: no cover - fdopen failing is a system fault
                os.close(descriptor)
                raise
            with handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.flush()
                # The umask can only clear bits, never set them, so O_EXCL|0600 cannot
                # leave the file more permissive than requested - but a filesystem that
                # ignores the mode would, and that is worth failing on rather than
                # assuming away.
                os.fchmod(handle.fileno(), TOKEN_FILE_MODE)
                os.fsync(handle.fileno())
            self._check_mode(temporary, TOKEN_FILE_MODE)
            temporary.replace(self.path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        self.verify_permissions()

    def load(self) -> StoredCredentials:
        if not self.path.exists():
            raise TokenStoreError(
                f"no credentials at {self.path}; run `mailweave auth` to authorise the "
                "read-only client"
            )
        self.verify_permissions()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TokenStoreError(f"credential store at {self.path} is unreadable: {exc}") from exc
        try:
            return StoredCredentials.model_validate(raw)
        except SecretDocumentMalformed as exc:
            # `exc` is the value-free refusal `SecretBearingModel` raises, so quoting it
            # here is safe; quoting Pydantic's own report is what R-SEC-043 was.
            raise TokenStoreError(f"credential store at {self.path} is malformed: {exc}") from exc

    def purge(self) -> bool:
        """Delete the store. Returns True if something was removed."""
        if self.path.exists():
            self.path.unlink()
            return True
        return False


def new_salt() -> bytes:
    """Generated once, on first run; stored beside the refresh token; never logged."""
    return secrets.token_bytes(SALT_BYTES)
