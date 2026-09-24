"""Config, credential storage and profile derivation (WS-01).

The tests that matter here are the refusals: an over-permissive token file, a forged seed
account hash, a failed `getProfile`, a config that tries to widen the scope set.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

import pytest

from mailweave.auth import (
    ClientRole,
    Profile,
    StoredCredentials,
    TokenStore,
    account_digest,
    build_authorization_url,
    derive_profile,
    generate_pkce,
    new_salt,
    new_state,
    parse_redirect,
    read_client,
    redirect_uri,
)
from mailweave.auth.clients import ClientDescriptor
from mailweave.auth.pkce import OAuthCallbackError
from mailweave.config import MailweaveConfig, load_config
from mailweave.constants import READ_SCOPE
from mailweave.errors import AuthProfileUnderivable, ConfigError, TokenStoreError

SEED_ADDRESS = "seed-account@mailweave.example"
PERSONAL_ADDRESS = "owner@personal.example"
READ_CLIENT = "read-client-id.apps.googleusercontent.example"
SEED_CLIENT = "seed-client-id.apps.googleusercontent.example"


def credentials(salt: bytes, client_id: str = READ_CLIENT) -> StoredCredentials:
    return StoredCredentials(
        client_id=client_id,
        refresh_token="1//refresh-token-value",  # type: ignore[arg-type]
        salt_hex=salt.hex(),
        obtained_at="2026-08-30T00:00:00Z",
    )


# --- token store ---------------------------------------------------------------------------


def test_the_store_creates_a_0700_directory_holding_a_0600_file(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "state" / "credentials.json")
    store.save(credentials(new_salt()))

    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(store.directory.stat().st_mode) == 0o700


def test_the_store_refuses_to_read_a_group_readable_file(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "state" / "credentials.json")
    store.save(credentials(new_salt()))
    store.path.chmod(0o640)

    with pytest.raises(TokenStoreError) as failure:
        store.load()
    assert "0640" in str(failure.value)


def test_the_store_refuses_a_world_traversable_directory(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "state" / "credentials.json")
    store.save(credentials(new_salt()))
    store.directory.chmod(0o755)

    with pytest.raises(TokenStoreError):
        store.load()


def test_the_file_is_never_briefly_world_readable(tmp_path: Path) -> None:
    """Mode is set at open time, so there is no window between creation and chmod."""
    previous = os.umask(0o000)  # a permissive umask must not widen the file
    try:
        store = TokenStore(tmp_path / "state" / "credentials.json")
        store.save(credentials(new_salt()))
        assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    finally:
        os.umask(previous)


def test_a_saved_token_round_trips_and_the_secret_is_not_in_its_repr(tmp_path: Path) -> None:
    salt = new_salt()
    store = TokenStore(tmp_path / "state" / "credentials.json")
    store.save(credentials(salt))
    loaded = store.load()

    assert loaded.salt == salt
    assert loaded.refresh_token.get_secret_value() == "1//refresh-token-value"
    assert "1//refresh-token-value" not in repr(loaded)
    assert "1//refresh-token-value" not in str(loaded)


def test_purge_removes_the_store(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "state" / "credentials.json")
    store.save(credentials(new_salt()))
    assert store.purge() is True
    assert store.purge() is False
    with pytest.raises(TokenStoreError):
        store.load()


# --- profile derivation --------------------------------------------------------------------


def test_the_seed_profile_needs_both_the_digest_and_the_harness_client() -> None:
    salt = new_salt()
    seed_hash = account_digest(salt, SEED_ADDRESS)

    assert (
        derive_profile(
            observed_address=SEED_ADDRESS,
            salt=salt,
            configured_seed_hash=seed_hash,
            credential_client_id=SEED_CLIENT,
            seed_client_id=SEED_CLIENT,
        )
        is Profile.SEED
    )


def test_config_forgery_cannot_promote_the_personal_mailbox_to_seed() -> None:
    """The attack A.4 describes: edit `seed_account_hash` to the personal digest.

    Condition (i) then passes and condition (ii) cannot, because the personal mailbox
    holds a token for the read client, not the harness client.
    """
    salt = new_salt()
    forged = account_digest(salt, PERSONAL_ADDRESS)

    assert (
        derive_profile(
            observed_address=PERSONAL_ADDRESS,
            salt=salt,
            configured_seed_hash=forged,
            credential_client_id=READ_CLIENT,
            seed_client_id=SEED_CLIENT,
        )
        is Profile.PERSONAL
    )


def test_a_rotated_salt_fails_closed_to_personal() -> None:
    old_salt, new = new_salt(), new_salt()
    assert (
        derive_profile(
            observed_address=SEED_ADDRESS,
            salt=new,
            configured_seed_hash=account_digest(old_salt, SEED_ADDRESS),
            credential_client_id=SEED_CLIENT,
            seed_client_id=SEED_CLIENT,
        )
        is Profile.PERSONAL
    )


@pytest.mark.parametrize(
    ("seed_hash", "seed_client"),
    [(None, SEED_CLIENT), ("deadbeef", None), (None, None)],
)
def test_unset_configuration_fails_closed_to_personal(
    seed_hash: str | None, seed_client: str | None
) -> None:
    assert (
        derive_profile(
            observed_address=SEED_ADDRESS,
            salt=new_salt(),
            configured_seed_hash=seed_hash,
            credential_client_id=SEED_CLIENT,
            seed_client_id=seed_client,
        )
        is Profile.PERSONAL
    )


def test_a_failed_get_profile_is_fatal_rather_than_defaulted() -> None:
    with pytest.raises(AuthProfileUnderivable) as failure:
        derive_profile(
            observed_address=None,
            salt=new_salt(),
            configured_seed_hash=None,
            credential_client_id=READ_CLIENT,
            seed_client_id=SEED_CLIENT,
        )
    assert "refuses to start" in str(failure.value)


def test_the_digest_is_salted_and_address_normalised() -> None:
    salt = new_salt()
    expected = hashlib.sha256(salt + SEED_ADDRESS.encode()).hexdigest()
    assert account_digest(salt, f"  {SEED_ADDRESS.upper()} ") == expected
    assert account_digest(new_salt(), SEED_ADDRESS) != expected


# --- the two-client model --------------------------------------------------------------------


def test_the_server_can_only_construct_the_read_client() -> None:
    descriptor = read_client(READ_CLIENT)
    assert descriptor.role is ClientRole.READ
    assert descriptor.scopes == (READ_SCOPE,)

    with pytest.raises(ConfigError):
        ClientDescriptor(role=ClientRole.SEEDER, client_id=SEED_CLIENT, scopes=(READ_SCOPE,))
    with pytest.raises(ConfigError):
        ClientDescriptor(
            role=ClientRole.READ,
            client_id=READ_CLIENT,
            scopes=(READ_SCOPE, "https://www.googleapis.com/auth/gmail.modify"),
        )


def test_the_harness_scope_lives_in_the_harness_package_and_pins_its_account() -> None:
    from mailweave_harness.scopes import SEEDER_SCOPES, SeedAccountMismatch, assert_seed_account

    assert SEEDER_SCOPES != (READ_SCOPE,)
    assert_seed_account(authenticated_address=SEED_ADDRESS, seed_address=SEED_ADDRESS.upper())
    with pytest.raises(SeedAccountMismatch):
        assert_seed_account(authenticated_address=PERSONAL_ADDRESS, seed_address=SEED_ADDRESS)


# --- PKCE ------------------------------------------------------------------------------------


def test_the_code_challenge_is_the_s256_of_the_verifier() -> None:
    import base64

    pair = generate_pkce()
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(pair.verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    assert pair.challenge == expected
    assert pair.method == "S256"
    assert generate_pkce().verifier != pair.verifier


def test_the_authorization_url_uses_a_loopback_redirect_and_one_scope() -> None:
    url = build_authorization_url(
        client_id=READ_CLIENT, port=8731, pkce=generate_pkce(), state=new_state()
    )
    assert "redirect_uri=http%3A%2F%2F127.0.0.1%3A8731%2F" in url
    assert "code_challenge_method=S256" in url
    assert url.count("scope=") == 1
    assert "gmail.readonly" in url
    assert "urn:ietf:wg:oauth:2.0:oob" not in url


def test_a_redirect_with_the_wrong_state_is_refused() -> None:
    state = new_state()
    good = f"{redirect_uri(8731)}?code=abc&state={state}"
    assert parse_redirect(good, expected_state=state) == "abc"
    with pytest.raises(OAuthCallbackError):
        parse_redirect(f"{redirect_uri(8731)}?code=abc&state=other", expected_state=state)
    with pytest.raises(OAuthCallbackError):
        denied = f"{redirect_uri(8731)}?error=access_denied&state={state}"
        parse_redirect(denied, expected_state=state)
    with pytest.raises(OAuthCallbackError):
        parse_redirect(f"{redirect_uri(8731)}?state={state}", expected_state=state)


# --- configuration -----------------------------------------------------------------------------


def write_config(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)
    return path


def test_a_valid_config_loads_and_derives_its_state_paths(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        {
            "client_id": READ_CLIENT,
            "client_secret": "not-a-real-secret",
            "state_dir": str(tmp_path / "state"),
            "seed_account_hash": "abc123",
            "seed_client_id": SEED_CLIENT,
        },
    )
    config = load_config(path)
    assert config.scopes == (READ_SCOPE,)
    assert config.token_path.name == "credentials.json"
    assert config.watermark_path.parent == config.token_path.parent
    assert "not-a-real-secret" not in repr(config)


def test_a_config_may_not_widen_the_scope_set_or_the_egress_allowlist(tmp_path: Path) -> None:
    for forbidden in ("scopes", "egress_allowlist"):
        path = write_config(
            tmp_path,
            {
                "client_id": READ_CLIENT,
                "client_secret": "s",
                forbidden: ["https://www.googleapis.com/auth/gmail.modify"],
            },
        )
        with pytest.raises(ConfigError) as failure:
            load_config(path)
        assert forbidden in str(failure.value)


def test_the_model_itself_refuses_a_widened_allowlist() -> None:
    """`ConfigError` rather than a bare `ValueError` since R-SEC-043.

    `MailweaveConfig` holds the client secret, so its failures are now rendered as field
    paths and error types with no `msg` (`mailweave.validation`). This refusal quotes only
    code-level constants, so it is raised as a `ConfigError` and propagates with its own
    words intact rather than being folded into a report that would then drop them. The
    refusal itself is unchanged: a widened allowlist is still refused by the model and not
    only by `load_config`'s pre-check.
    """
    with pytest.raises(ConfigError) as failure:
        MailweaveConfig(
            client_id=READ_CLIENT,
            client_secret="s",  # type: ignore[arg-type]
            egress_allowlist=frozenset({"gmail.googleapis.com", "huggingface.co"}),
        )
    assert "may not add a host" in str(failure.value)


def test_a_world_readable_config_is_refused(tmp_path: Path) -> None:
    path = write_config(tmp_path, {"client_id": READ_CLIENT, "client_secret": "s"})
    path.chmod(0o644)
    with pytest.raises(ConfigError) as failure:
        load_config(path)
    assert "0644" in str(failure.value)


# --- M2 / R-SEC-003: the save is atomic, so there is no readable intermediate state ----------


def stale_permissive_store(tmp_path: Path) -> TokenStore:
    """A credential path that already exists at 0644 - a stale file, a bad deploy, anything.

    `os.open`'s mode argument applies only when the file is *created*, so this is the case
    round 1's "mode is set at open time" test could not cover: the existing file keeps its
    permissions through the write, and the forcing chmod comes afterwards.
    """
    directory = tmp_path / "state"
    directory.mkdir(mode=0o700)
    path = directory / "credentials.json"
    path.write_text('{"stale": true}', encoding="utf-8")
    path.chmod(0o644)
    return TokenStore(path)


def test_a_crash_during_the_write_never_leaves_the_token_in_a_readable_file(
    tmp_path: Path,
) -> None:
    """R-SEC-003 reproduced: kill the process once the payload has hit the filesystem."""
    store = stale_permissive_store(tmp_path)
    secret = "1//refresh-token-value"
    real_dump = json.dump

    def dump_then_die(*args: object, **kwargs: object) -> None:
        real_dump(*args, **kwargs)  # type: ignore[arg-type]
        raise OSError("simulated SIGKILL between the write and the permission fix")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("mailweave.auth.tokenstore.json.dump", dump_then_die)
        with pytest.raises(OSError, match="simulated SIGKILL"):
            store.save(credentials(new_salt()))

    # Whatever survived the crash, the refresh token is not sitting in a readable file.
    for leftover in store.directory.iterdir():
        body = leftover.read_text(encoding="utf-8")
        mode = stat.S_IMODE(leftover.stat().st_mode)
        assert not (secret in body and mode & 0o077), (
            f"{leftover.name} holds the refresh token at mode {mode:04o}"
        )
    assert secret not in store.path.read_text(encoding="utf-8")


def test_a_completed_save_over_a_stale_permissive_file_lands_at_0600(tmp_path: Path) -> None:
    store = stale_permissive_store(tmp_path)
    store.save(credentials(new_salt()))
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    assert store.load().refresh_token.get_secret_value() == "1//refresh-token-value"


def test_a_failed_save_leaves_no_temporary_file_behind(tmp_path: Path) -> None:
    store = stale_permissive_store(tmp_path)
    before = {path.name for path in store.directory.iterdir()}
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("mailweave.auth.tokenstore.json.dump", _raise_disk_full)
        with pytest.raises(OSError):
            store.save(credentials(new_salt()))
    assert {path.name for path in store.directory.iterdir()} == before


def _raise_disk_full(*args: object, **kwargs: object) -> None:
    raise OSError("no space left on device")


def test_the_final_path_is_only_ever_replaced_whole(tmp_path: Path) -> None:
    """The mechanism, named: the payload is written elsewhere and renamed into place."""
    store = stale_permissive_store(tmp_path)
    seen: list[int] = []
    real_replace = Path.replace

    def observe(self: Path, target: object) -> Path:
        # At the moment of the rename the destination still holds the *old* file, so the
        # secret has never been visible at 0644.
        seen.append(stat.S_IMODE(self.stat().st_mode))
        assert "1//refresh-token-value" not in store.path.read_text(encoding="utf-8")
        return real_replace(self, target)  # type: ignore[arg-type]

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Path, "replace", observe)
        store.save(credentials(new_salt()))
    assert seen == [0o600]


# --- R-SEC-012: the temp file a killed save leaves behind -------------------------------------


def orphan(store: TokenStore, pid: int, secret: str = "1//refresh-token-value") -> Path:
    """A leftover of the exact shape `save()` writes: `.<name>.<pid>.<hex>`, 0600."""
    leftover = store.path.with_name(f".{store.path.name}.{pid}.deadbeef")
    leftover.write_text(f'{{"refresh_token": "{secret}"}}', encoding="utf-8")
    leftover.chmod(0o600)
    return leftover


def dead_pid() -> int:
    """A pid belonging to no live process: fork a child and reap it."""
    pid = os.fork()
    if pid == 0:  # pragma: no cover - the child never returns to pytest
        os._exit(0)
    os.waitpid(pid, 0)
    return pid


def kill_a_save_after_fsync(store: TokenStore) -> None:
    """Run a real `save()` in a forked child and hard-exit it between fsync and replace.

    Not a simulation of the leftover - the child runs the shipped `save()` and dies inside
    it, so the file it leaves is whatever the production path actually writes. That matters
    because a sweep is only correct against the names `save()` really produces, and a test
    that synthesises the name would keep passing if the two drifted apart.
    """
    pid = os.fork()
    if pid == 0:  # pragma: no cover - the child never returns to pytest
        try:
            with pytest.MonkeyPatch.context() as patch:
                patch.setattr("pathlib.Path.replace", lambda self, target: os._exit(9))
                store.save(credentials(new_salt()))
        except BaseException:
            os._exit(1)
        os._exit(2)
    _, status = os.waitpid(pid, 0)
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 9, "the child did not die in save()"


def test_a_temp_file_from_a_killed_save_is_swept_by_the_next_one(tmp_path: Path) -> None:
    """R-SEC-012 verbatim: a hard kill between fsync and replace leaves the token on disk.

    Not a disclosure - the file is 0600 in a 0700 directory, which is the store's own
    guarantee - but nothing ever removed it, so orphans accumulated for the life of the
    store. The next successful save collects them.
    """
    store = TokenStore(tmp_path / "state" / "credentials.json")
    store.ensure_directory()
    kill_a_save_after_fsync(store)

    leftovers = [p for p in store.directory.iterdir() if p != store.path]
    assert leftovers, "the crash left nothing behind; this test is no longer reproducing it"
    assert "1//refresh-token-value" in leftovers[0].read_text(encoding="utf-8")
    assert stat.S_IMODE(leftovers[0].stat().st_mode) == 0o600

    store.save(credentials(new_salt()))

    assert [p.name for p in store.directory.iterdir()] == [store.path.name]


def test_the_sweep_leaves_a_temp_file_whose_writer_is_still_running(tmp_path: Path) -> None:
    """A live pid means a save in flight; deleting that file *causes* the crash it cleans up."""
    store = TokenStore(tmp_path / "state" / "credentials.json")
    store.ensure_directory()
    in_flight = orphan(store, os.getpid())

    store.save(credentials(new_salt()))

    assert in_flight.exists()


@pytest.mark.parametrize(
    "name",
    [
        "credentials.json.backup",  # not the temp prefix
        ".credentials.json.notapid.deadbeef",  # pid field is not a number
        ".credentials.json.1234",  # too few fields to be a name this store writes
        ".other.json.1.deadbeef",  # a different store's temp file
    ],
)
def test_the_sweep_only_removes_names_this_store_writes(tmp_path: Path, name: str) -> None:
    """A sweep that guesses is a sweep that deletes someone else's file."""
    store = TokenStore(tmp_path / "state" / "credentials.json")
    store.ensure_directory()
    bystander = store.directory / name
    bystander.write_text("not mine", encoding="utf-8")

    store.save(credentials(new_salt()))

    assert bystander.exists(), f"the sweep removed {name}"


def test_the_sweep_reports_what_it_removed(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "state" / "credentials.json")
    store.ensure_directory()
    for _ in range(3):
        orphan(store, dead_pid()).rename(
            store.path.with_name(f".{store.path.name}.{dead_pid()}.{os.urandom(4).hex()}")
        )
    assert store.sweep_orphaned_temporaries() == 3
    assert store.sweep_orphaned_temporaries() == 0
