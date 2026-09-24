"""Configuration loading and validation (WS-01).

Two properties this module refuses to compromise on:

  * the server's scope set and its egress allowlist are **not configurable**. A config
    file that names a different scope or a third host is rejected, so widening either one
    requires a code change and a review, not an edit to a dotfile (RR SEC-01, SEC-07);
  * secrets never reach argv, env or logs. The client secret is read from a file whose
    permissions are checked first, and is held in a `SecretStr` so it cannot be printed
    by accident (RR SEC-04).
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

from pydantic import ConfigDict, Field, SecretStr, field_validator, model_validator

from mailweave.constants import (
    RUNTIME_EGRESS_ALLOWLIST,
    SERVER_SCOPES,
    TOKEN_DIR_MODE,
    TOKEN_FILE_MODE,
)
from mailweave.errors import ConfigError, SecretDocumentMalformed
from mailweave.validation import SecretBearingModel

DEFAULT_CONFIG_PATH = Path("~/.config/mailweave/config.json")
DEFAULT_STATE_DIR = Path("~/.local/state/mailweave")


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def assert_not_group_or_world_accessible(path: Path) -> None:
    """Refuse a credential-bearing path that anyone but the owner can read (SEC-04)."""
    if not path.exists():
        raise ConfigError(f"{path} does not exist")
    mode = _mode(path)
    if mode & 0o077:
        raise ConfigError(
            f"{path} has mode {mode:04o}; credential-bearing paths must be "
            f"{TOKEN_FILE_MODE:04o} (files) or {TOKEN_DIR_MODE:04o} (directories). "
            "Refusing to read it rather than leaking a secret to other local users."
        )


class MailweaveConfig(SecretBearingModel):
    """The server's configuration. Everything security-relevant is fixed, not settable.

    `SecretBearingModel` for the same reason `StoredCredentials` is one: this file holds
    the client secret, and Pydantic's default report quotes what it refused. The client
    secret is short enough to sit *inside* the truncation window, so the leak here was the
    whole value rather than a fragment (R-SEC-043's class, one file wider).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    client_id: str = Field(min_length=1)
    client_secret: SecretStr
    state_dir: Path = DEFAULT_STATE_DIR
    #: Condition (i) of AD A.4 profile derivation. Unset means "no seed account" -> personal.
    seed_account_hash: str | None = None
    #: Condition (ii): the harness OAuth client id. Unset means the seed test can never pass.
    seed_client_id: str | None = None
    scopes: tuple[str, ...] = SERVER_SCOPES
    egress_allowlist: frozenset[str] = RUNTIME_EGRESS_ALLOWLIST

    @field_validator("state_dir")
    @classmethod
    def _expand(cls, value: Path) -> Path:
        return value.expanduser()

    @model_validator(mode="after")
    def _security_constants_are_not_configurable(self) -> MailweaveConfig:
        """`ConfigError`, not `ValueError` - so the refusal keeps its own words.

        A `ValueError` raised here is folded into a `ValidationError`, and since R-SEC-043
        this model's failures are rendered as field paths and error *types* only: no `msg`
        is read, because `msg` is whatever validator text happens to be there and
        `parse_instant` proved our own validator text can quote the value it refused. Both
        refusals below name only code-level constants, so they lose nothing by travelling
        as themselves - and Pydantic propagates a non-`ValueError` rather than wrapping it,
        which is the same mechanism `content/payload.py` uses for `ContentProcessingError`.
        """
        if tuple(self.scopes) != SERVER_SCOPES:
            raise ConfigError(
                f"scopes are fixed at {SERVER_SCOPES}; a configuration file may not widen them"
            )
        if frozenset(self.egress_allowlist) != RUNTIME_EGRESS_ALLOWLIST:
            raise ConfigError(
                f"the runtime egress allowlist is fixed at {sorted(RUNTIME_EGRESS_ALLOWLIST)}; "
                "a configuration file may not add a host"
            )
        return self

    @property
    def token_path(self) -> Path:
        return self.state_dir / "credentials.json"

    @property
    def watermark_path(self) -> Path:
        return self.state_dir / "watermark.json"


def load_config(path: Path | None = None) -> MailweaveConfig:
    """Read and validate the config file, refusing over-permissive files."""
    resolved = (path or DEFAULT_CONFIG_PATH).expanduser()
    assert_not_group_or_world_accessible(resolved)
    try:
        raw: Any = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot read configuration at {resolved}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"configuration at {resolved} is not an object")
    for forbidden in ("scopes", "egress_allowlist"):
        if forbidden in raw:
            raise ConfigError(
                f"configuration at {resolved} sets '{forbidden}', which is a code-level "
                "constant and may not be set from configuration"
            )
    try:
        return MailweaveConfig.model_validate(raw)
    except SecretDocumentMalformed as exc:
        raise ConfigError(f"invalid configuration at {resolved}: {exc}") from exc


def secret_is_absent_from_environment(secret: SecretStr) -> bool:
    """True if the client secret does not appear in this process's environment (SEC-04).

    Used as a startup assertion: a secret exported into the environment is a secret in
    every child process and every crash dump.
    """
    value = secret.get_secret_value()
    return not any(value and value in item for item in os.environ.values())
