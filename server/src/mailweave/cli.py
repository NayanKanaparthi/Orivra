"""The `mailweave` command line.

`doctor` and `purge` are the round-1 credential-hygiene commands. `auth login` is round 11's
addition: the desktop loopback consent flow, in **one** step, whose output states plainly what
Google actually granted. `serve` is round 24's: the MCP server itself, over stdio.

**`mailweave serve` is the one documented invocation** (OD-6 criterion 1). It refuses to
start without a valid credential - an unreadable store, a refused refresh, or a
`users.getProfile` that does not answer all end the process before a byte of MCP is spoken,
and the last of those is D.11's `auth_profile_underivable`, which is a startup failure
precisely so that no run can default it. Its banner goes to **stderr**, because stdout is
the transport.

Two deliberate absences:

  * **no browser is opened.** The command prints the authorisation URL and waits. Opening a
    browser is starting a consent, and consent is the owner's to start, on the owner's own
    machine, looking at the consent screen with their own eyes;
  * **no secret is printed.** The report shows the client id, the scopes requested, the scopes
    *granted*, the account, the derived redaction profile and the store path. The refresh
    token is written to the 0600 store and never rendered.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO

from mailweave import __version__
from mailweave.auth.consent import (
    CONSENT_TIMEOUT_S,
    ConsentFailed,
    LoginReport,
    LoopbackReceiver,
    read_installed_client,
    run_login,
)
from mailweave.auth.tokenstore import TokenStore
from mailweave.config import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_STATE_DIR,
    MailweaveConfig,
    assert_not_group_or_world_accessible,
    load_config,
)
from mailweave.constants import RUNTIME_EGRESS_ALLOWLIST, SERVER_SCOPES
from mailweave.errors import (
    AuthProfileUnderivable,
    ConfigError,
    MailweaveError,
    TokenStoreError,
)
from mailweave.freshness import WatermarkFile
from mailweave.gmail import GmailClient, GmailFault, StaticToken
from mailweave.models.paths import DEFAULT_MODELS_DIR

#: Where the owner's downloaded "Desktop app" client JSON is expected. Overridable with
#: `--client`; named here so the error message can say what it was looking for.
DEFAULT_CLIENT_PATH = Path("mailweave-server-oauth.json")


def emit(stream: TextIO, event: str, **fields: Any) -> None:
    """One machine-readable line: `{"event": ..., ...}`, flushed (2026-09-23).

    `--events` is for a program that runs these commands for someone - the desktop beta runs
    `auth login` and `setup-models` as child processes and reads their progress from a pipe -
    so each line is complete JSON and is flushed as it is written. The fields are the same
    facts the human output prints, never more: no secret reaches a value here, because none
    reaches the human output either.
    """
    print(json.dumps({"event": event, **fields}, sort_keys=True), file=stream, flush=True)


def _load(path: Path | None) -> MailweaveConfig:
    return load_config(path)


def doctor(
    path: Path | None, client_path: Path = DEFAULT_CLIENT_PATH, out: TextIO | None = None
) -> int:
    """Check the things that must be true before the server may hold a credential.

    **The OAuth client file is checked here because `serve` and `auth login` both refuse on
    it and both send the operator here** (round 25, R-MCP-008). A client JSON downloaded from
    the Google console arrives 0644, both commands refuse a credential-bearing path other
    local users can read, and their printed remedy is "run `mailweave doctor`" - which
    exited 0 and did not mention the file. A stranger following `docs/SETUP.md` was stopped
    at step 4 by a refusal whose remedy, whose troubleshooting row and whose diagnostic tool
    all pointed somewhere else. SETUP now says `chmod 600`; this is the half that catches the
    operator who did not read it.
    """
    stream = out if out is not None else sys.stdout
    problems: list[str] = []
    try:
        config = _load(path)
    except ConfigError as failure:
        print(f"config: FAIL - {failure}", file=stream)
        return 1

    print(f"config: ok ({path or DEFAULT_CONFIG_PATH})", file=stream)
    print(f"scopes: {', '.join(config.scopes)}", file=stream)
    print(
        f"egress allowlist: {', '.join(sorted(RUNTIME_EGRESS_ALLOWLIST))}",
        file=stream,
    )
    print(
        "seed profile configured: "
        f"{'yes' if config.seed_account_hash and config.seed_client_id else 'no (personal)'}",
        file=stream,
    )

    if client_path.exists():
        try:
            assert_not_group_or_world_accessible(client_path)
            print(f"oauth client file: ok ({client_path})", file=stream)
        except ConfigError as failure:
            problems.append(f"{failure} Fix it with: chmod 600 {client_path}")
    else:
        print(
            f"oauth client file: absent ({client_path}) - download the Desktop-app client "
            "JSON, or pass --client",
            file=stream,
        )

    store = TokenStore(config.token_path)
    if store.path.exists():
        try:
            store.verify_permissions()
            print(f"token store: ok ({store.path})", file=stream)
        except TokenStoreError as failure:
            problems.append(str(failure))
    else:
        print(
            f"token store: absent ({store.path}) - run `mailweave auth`",
            file=stream,
        )

    if tuple(config.scopes) != SERVER_SCOPES:  # pragma: no cover - the model forbids it
        problems.append("scope set differs from the single read-only scope")

    for problem in problems:
        print(f"PROBLEM: {problem}", file=stream)
    return 1 if problems else 0


def purge(path: Path | None, out: TextIO | None = None) -> int:
    """Delete everything this server persists (SEC-05's purge command).

    Two files, and the second is the reason this docstring is not "delete the stored
    credentials" any more. AD D.9 says `mailweave purge` deletes the `historyId` watermark,
    and a purge that left it behind would leave a file the user was told is removable. It is
    not a credential and not mail content, but it is persisted state about their mailbox,
    and "purge" is a promise about all of it.

    Both are reported by path, whether or not they existed, so the output says what the
    command did rather than only that it succeeded.
    """
    stream = out if out is not None else sys.stdout
    try:
        config = _load(path)
    except ConfigError as failure:
        print(f"config: FAIL - {failure}", file=stream)
        return 1
    store = TokenStore(config.token_path)
    removed = store.purge()
    print(
        f"purged {store.path}" if removed else f"nothing to purge at {store.path}",
        file=stream,
    )
    watermark = WatermarkFile(config.watermark_path)
    removed_watermark = watermark.purge()
    print(
        f"purged {watermark.path}"
        if removed_watermark
        else f"nothing to purge at {watermark.path}",
        file=stream,
    )
    return 0


def setup_models(
    *,
    catalog_path: Path,
    lock_path: Path,
    models_dir: Path,
    pin_targets: list[str] | None,
    status_only: bool,
    smoke: bool,
    events: bool = False,
    out: TextIO | None = None,
) -> int:
    """Provision model weights (AD D.8). The only command that may reach the model host.

    Four modes:

      * **`--status`** reads the lock and reports what is installed and verified. No network.
      * **`--smoke`** loads the installed models offline and runs one encode and one rerank.
        It exists so that a packaging or loader failure is **diagnosed as one** before PF-4
        measures anything: a model that will not load is not a slow model, and reporting it
        as a latency result would put a packaging problem into a performance record.
      * **default** installs from the reviewed lock, verifying every byte against it.
      * **`--pin`** performs the download that produces the lock, per `model.set` target.

    Byte counts printed here are **model artifacts only**. Python runtime dependencies come
    from `uv sync` and are not counted in these figures; the two are separate downloads and
    conflating them would make the model figure unreviewable.

    `events` (2026-09-23) applies to the default install mode only, and replaces its lines
    with `emit`'s: the plan, per-file outcomes, byte progress while a file downloads, and a
    final `done` or `failed`. The install itself - the lock, the digests, the refusal to
    overwrite a mismatched file - is the same code either way.
    """
    stream = out if out is not None else sys.stdout
    if events and pin_targets is None and not status_only and not smoke:
        return _install_with_events(lock_path=lock_path, models_dir=models_dir, stream=stream)
    from mailweave.models import (
        CatalogError,
        LockError,
        ProvisionError,
        assert_host_is_the_declared_one,
        install,
        installed_models,
        load_catalog,
        load_lock,
        pin,
        write_lock,
    )
    from mailweave.models.lock import Lock

    try:
        if pin_targets is not None:
            catalog = load_catalog(catalog_path)
            assert_host_is_the_declared_one(catalog)
            targets: list[tuple[str, str]]
            if pin_targets:
                targets = []
                for spec in pin_targets:
                    model_key, _, set_name = spec.partition(".")
                    if not set_name:
                        entry = catalog.entry(model_key)
                        targets.extend((model_key, name) for name in sorted(entry.artifact_sets))
                    else:
                        targets.append((model_key, set_name))
            else:
                targets = list(catalog.targets())
            locked = {}
            # A first pin has no lock yet; a later one adds to what is already reviewed
            # rather than replacing it, so pinning one set never quietly drops another.
            with contextlib.suppress(LockError):
                locked.update(load_lock(lock_path).models)
            model_bytes = 0
            for model_key, set_name in targets:
                entry = catalog.entry(model_key)
                artifacts = entry.set_named(set_name)
                print(
                    f"pinning {model_key}.{set_name} ({entry.repo_id}, "
                    f"runtime {artifacts.runtime}) ...",
                    file=stream,
                )
                pinned = pin(entry, set_name, root=models_dir)
                locked[pinned.key] = pinned
                model_bytes += pinned.total_bytes
                print(
                    f"  {pinned.revision[:12]}  {len(pinned.files)} files  "
                    f"{pinned.total_bytes:,} model bytes",
                    file=stream,
                )
                for artifact in pinned.files:
                    print(f"    {artifact.bytes:>13,}  {artifact.name}", file=stream)
            written = write_lock(Lock(models=locked), lock_path)
            print(
                f"\nmodel artifact bytes downloaded: {model_bytes:,} "
                "(Python runtime dependencies are a separate download and are not counted "
                "here)",
                file=stream,
            )
            print(
                f"wrote {written}. Commit it: the digests are the reviewable artifact, and "
                "every later install is verified against them.",
                file=stream,
            )
            return 0

        lock = load_lock(lock_path)
        if status_only:
            total = 0
            for key, ok in sorted(installed_models(lock, root=models_dir).items()):
                locked_entry = lock.entry(key)
                total += locked_entry.total_bytes if ok else 0
                print(
                    f"{'installed' if ok else 'MISSING  '} {key:<34} "
                    f"{locked_entry.runtime:<22} {locked_entry.total_bytes:>14,} bytes",
                    file=stream,
                )
            print(f"\nmodel artifact bytes on disk: {total:,}", file=stream)
            return 0
        if smoke:
            return _smoke_test(lock, models_dir, stream)
        for key, locked_model in sorted(lock.models.items()):
            print(f"{key} ({locked_model.repo_id}@{locked_model.revision[:12]})", file=stream)
            for line in install(locked_model, root=models_dir):
                print(f"  {line}", file=stream)
        return 0
    except (CatalogError, LockError, ProvisionError) as failure:
        print(f"setup-models: FAIL - {failure}", file=stream)
        return 1


#: The smallest byte step between two `progress` events for one file, and the fraction of the
#: file that also triggers one. A 1.1 GB file then reports about a hundred times, a small one
#: once or twice; the pipe it is read from never fills.
PROGRESS_MIN_STEP_BYTES = 8 << 20
PROGRESS_STEPS_PER_FILE = 100


def _progress_events(stream: TextIO, model: str) -> Callable[[str, int, int], None]:
    """A `provision.Progress` that emits at most one `progress` line per step, per file."""
    last: dict[str, int] = {}

    def progress(name: str, done: int, total: int) -> None:
        step = max(PROGRESS_MIN_STEP_BYTES, total // PROGRESS_STEPS_PER_FILE)
        if done - last.get(name, 0) >= step or done == total:
            last[name] = done
            emit(stream, "progress", model=model, file=name, done=done, file_total=total)

    return progress


def _install_with_events(*, lock_path: Path, models_dir: Path, stream: TextIO) -> int:
    """`setup-models` install mode, reported as `emit` lines. See `setup_models`."""
    from mailweave.models import LockError, ProvisionError, install, load_lock

    try:
        lock = load_lock(lock_path)
    except LockError as failure:
        emit(stream, "failed", reason=f"setup-models: {failure}")
        return 1
    emit(
        stream,
        "plan",
        models=sorted(lock.models),
        total_bytes=sum(locked.total_bytes for locked in lock.models.values()),
        files=sum(len(locked.files) for locked in lock.models.values()),
    )
    try:
        for key, locked in sorted(lock.models.items()):
            emit(stream, "model", model=key, repo_id=locked.repo_id, bytes=locked.total_bytes)
            for line in install(locked, root=models_dir, progress=_progress_events(stream, key)):
                state, _, rest = line.partition(" ")
                emit(stream, "file", model=key, state=state, file=rest.split(" (", 1)[0])
    except (LockError, ProvisionError) as failure:
        emit(stream, "failed", reason=f"setup-models: {failure}")
        return 1
    except Exception as failure:
        # A network or egress refusal arrives as its own type (an `httpx` error, or the
        # allowlist's `EgressBlocked`). Named by type and message, which carry a host and a
        # status at most: model downloads carry no credential.
        emit(stream, "failed", reason=f"setup-models: {type(failure).__name__}: {failure}")
        return 1
    emit(stream, "done")
    return 0


def _smoke_test(lock: object, models_dir: Path, stream: TextIO) -> int:
    """Load offline, encode two texts, rerank two pairs. Diagnose, do not measure.

    Deliberately not a benchmark. PF-4 measures; this answers the prior question of whether
    the artifacts load at all, so that a packaging failure is never read as evidence about a
    model's quality or speed.
    """
    import time

    from mailweave.semantic import BackendUnavailable, checked_embed, checked_rerank
    from mailweave.semantic.local import build_local_backend

    try:
        started = time.perf_counter()
        backend = build_local_backend(lock, root=models_dir)  # type: ignore[arg-type]
        load_ms = int((time.perf_counter() - started) * 1000)
    except BackendUnavailable as failure:
        print(f"smoke: LOAD FAILED - {failure}", file=stream)
        print(
            "\nThis is a packaging or loader result, not a model result. Before treating it "
            "as evidence about the model, check in this order: the artifact set actually "
            "installed (`--status`), whether modules.json is among the locked files, and "
            "whether the installed sentence-transformers version supports the module classes "
            "that modules.json names.",
            file=stream,
        )
        return 1

    texts = ["we should postpone the launch", "the harbor export numbers look wrong"]
    started = time.perf_counter()
    vectors = checked_embed(backend, texts)
    embed_ms = int((time.perf_counter() - started) * 1000)

    query = "when did we decide to push go-live"
    candidates = ["we'll push go-live into Q4", "lunch is at one"]
    started = time.perf_counter()
    scores = checked_rerank(backend, query, candidates)
    rerank_ms = int((time.perf_counter() - started) * 1000)

    print(f"smoke: OK  model_id={backend.model_id}", file=stream)
    print(f"  revision       {backend.model_revision}", file=stream)
    print(f"  load           {load_ms} ms", file=stream)
    print(
        f"  embed          {len(vectors)} vectors, dim {len(vectors[0])}, {embed_ms} ms",
        file=stream,
    )
    print(f"  rerank         {len(scores)} scores, {rerank_ms} ms", file=stream)
    print(f"  scores         {[round(score, 4) for score in scores]}", file=stream)
    ordered = scores[0] > scores[1]
    print(
        f"  sanity         the on-topic candidate scores {'higher' if ordered else 'LOWER'}"
        f" than the off-topic one{'' if ordered else '  <-- look at this before PF-4'}",
        file=stream,
    )
    print(
        "\nThese timings are a smoke check on this run, not a measurement. PF-4 measures.",
        file=stream,
    )
    return 0


def _fetch_address(access_token: str) -> str:
    """`users.getProfile(me).emailAddress`, through the real client and the real allowlist."""
    client = GmailClient(token=StaticToken(access_token))
    try:
        return client.get_profile().email_address
    finally:
        client.close()


def auth_login(
    *,
    client_path: Path,
    state_dir: Path,
    dry_run: bool,
    expected_account: str | None,
    events: bool = False,
    out: TextIO | None = None,
) -> int:
    """The one command the owner runs. Everything it claims, it observed.

    `events` (2026-09-23) reports the same flow as `emit` lines for a program that runs this
    command for someone: the authorization URL to show them, then `granted` or `failed`. The
    flow is unchanged - no browser is opened, and the URL still has to be opened by the person
    whose mailbox it is.
    """
    stream = out if out is not None else sys.stdout
    if events:
        return _auth_login_with_events(
            client_path=client_path,
            state_dir=state_dir,
            expected_account=expected_account,
            stream=stream,
        )
    try:
        client = read_installed_client(client_path)
    except ConfigError as failure:
        print(f"client: FAIL - {failure}", file=stream)
        print(
            f"        expected a Desktop-app OAuth client JSON at {client_path}; "
            "pass --client to point somewhere else",
            file=stream,
        )
        return 1

    store = TokenStore(state_dir.expanduser() / "credentials.json")
    print(f"client:            {client.client_id} ({client.path})", file=stream)
    print(f"requested scopes:  {' '.join(SERVER_SCOPES)}", file=stream)
    print(f"token store:       {store.path}", file=stream)
    if dry_run:
        print("", file=stream)
        print("dry run: nothing was sent and no listener was bound. On a real run:", file=stream)
        print("  1. a one-shot listener binds 127.0.0.1 on an ephemeral port", file=stream)
        print("  2. this command prints a URL; you open it and consent", file=stream)
        print("  3. the code is exchanged at oauth2.googleapis.com with PKCE S256", file=stream)
        print("  4. the GRANTED scope set is read back and compared to the request;", file=stream)
        print(
            "     any difference in either direction aborts before anything is stored", file=stream
        )
        print(
            "  5. users.getProfile names the account; it is printed for you to check", file=stream
        )
        print("  6. the refresh token is written 0600 inside a 0700 directory", file=stream)
        return 0

    receiver = LoopbackReceiver()

    def wait_for_code(authorization_url: str, _state: str) -> str:
        print("", file=stream)
        print("Open this URL in your browser and consent:", file=stream)
        print("", file=stream)
        print(f"  {authorization_url}", file=stream)
        print("", file=stream)
        print(f"Waiting for the redirect on 127.0.0.1:{receiver.port} ...", file=stream)
        return receiver.wait_for_redirect()

    try:
        report: LoginReport = run_login(
            client=client,
            store=store,
            fetch_address=_fetch_address,
            announce=lambda _: None,
            wait_for_code=wait_for_code,
            expected_account=expected_account,
            port=receiver.port,
        )
    except (ConsentFailed, GmailFault, TokenStoreError, MailweaveError) as failure:
        print("", file=stream)
        print(f"auth login: FAILED - {failure}", file=stream)
        print("nothing was stored.", file=stream)
        return 1
    finally:
        receiver.close()

    print("", file=stream)
    for line in report.lines():
        print(line, file=stream)
    return 0


def _auth_login_with_events(
    *,
    client_path: Path,
    state_dir: Path,
    expected_account: str | None,
    stream: TextIO,
) -> int:
    """`auth login`, reported as `emit` lines. The same `run_login`, the same receiver."""
    try:
        client = read_installed_client(client_path)
    except ConfigError as failure:
        emit(stream, "failed", reason=f"client: {failure}")
        return 1
    store = TokenStore(state_dir.expanduser() / "credentials.json")
    receiver = LoopbackReceiver()

    def wait_for_code(authorization_url: str, _state: str) -> str:
        emit(
            stream,
            "authorization_url",
            url=authorization_url,
            port=receiver.port,
            timeout_s=CONSENT_TIMEOUT_S,
        )
        return receiver.wait_for_redirect()

    try:
        report = run_login(
            client=client,
            store=store,
            fetch_address=_fetch_address,
            announce=lambda _: None,
            wait_for_code=wait_for_code,
            expected_account=expected_account,
            port=receiver.port,
        )
    except (ConsentFailed, GmailFault, TokenStoreError, MailweaveError) as failure:
        emit(stream, "failed", reason=f"auth login: {failure}")
        return 1
    finally:
        receiver.close()
    emit(
        stream,
        "granted",
        account=report.account,
        client_id=report.client_id,
        granted_scopes=list(report.granted_scopes),
        scopes_verified=report.scopes_verified,
        profile=report.profile.value,
        token_store=str(report.token_path),
        obtained_at=report.obtained_at,
    )
    return 0


def serve(
    *,
    config_path: Path | None,
    client_path: Path,
    out: TextIO | None = None,
) -> int:
    """Start the MCP server on stdio. The one documented invocation (OD-6 criterion 1).

    Everything that can refuse, refuses here, before `run_stdio` is reached: the config
    file's permissions, the credential store's permissions, the stored refresh token, the
    granted scope set, and `users.getProfile`. A failure prints one line naming the cause
    and its remedy **to stderr** and exits non-zero; it never starts a server that would
    then have to answer tool calls it has no derived redaction profile for.
    """
    stream = out if out is not None else sys.stderr
    from mailweave.surface.runtime import announce, start
    from mailweave.surface.server import run_stdio

    try:
        runtime = start(config_path=config_path, client_path=client_path)
    except AuthProfileUnderivable as failure:
        print(f"serve: REFUSED - {failure}", file=stream)
        return 1
    except (ConfigError, TokenStoreError, GmailFault, MailweaveError) as failure:
        print(f"serve: REFUSED - {failure}", file=stream)
        print(
            "        a server with no valid credential cannot answer a tool call; run "
            "`mailweave doctor` and then `mailweave auth login`.",
            file=stream,
        )
        return 1
    announce(runtime.report, out=stream)
    try:
        run_stdio(runtime.service)
    finally:
        runtime.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mailweave", description=__doc__)
    parser.add_argument("--version", action="version", version=f"mailweave {__version__}")
    parser.add_argument("--config", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    checkup = sub.add_parser("doctor", help="validate configuration and credential-store hygiene")
    checkup.add_argument("--client", type=Path, default=DEFAULT_CLIENT_PATH)
    server = sub.add_parser("serve", help="run the MCP server on stdio")
    server.add_argument("--client", type=Path, default=DEFAULT_CLIENT_PATH)
    sub.add_parser("purge", help="delete the stored refresh token and salt")
    models = sub.add_parser(
        "setup-models",
        help="provision local model weights; the only command that contacts the model host",
    )
    models.add_argument("--catalog", type=Path, default=Path("models-catalog.json"))
    models.add_argument("--lock", type=Path, default=Path("models.lock"))
    models.add_argument("--models-dir", type=Path, default=DEFAULT_MODELS_DIR)
    models.add_argument(
        "--pin",
        nargs="*",
        default=None,
        metavar="MODEL[.SET]",
        help=(
            "download and record digests into the lock. This is the one command in this "
            "repository that reaches a host outside the runtime pair. A bare MODEL pins "
            "every artifact set it declares; MODEL.SET pins one. With no argument, pins "
            "every set in the catalog"
        ),
    )
    models.add_argument(
        "--status", action="store_true", help="report what is installed, touching nothing"
    )
    models.add_argument(
        "--events",
        action="store_true",
        help="install mode: report as one JSON object per line, with byte progress",
    )
    models.add_argument(
        "--smoke",
        action="store_true",
        help=(
            "load the installed models offline and run one encode and one rerank, so a "
            "packaging failure is diagnosed before PF-4 measures anything"
        ),
    )
    auth = sub.add_parser("auth", help="authorise the read-only client")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)
    login = auth_sub.add_parser("login", help="run the desktop loopback consent flow")
    login.add_argument("--client", type=Path, default=DEFAULT_CLIENT_PATH)
    login.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    login.add_argument(
        "--expect-account",
        default=None,
        help="abort unless the consented mailbox is this address",
    )
    login.add_argument(
        "--dry-run",
        action="store_true",
        help="print what would happen; bind nothing and send nothing",
    )
    login.add_argument(
        "--events",
        action="store_true",
        help="report as one JSON object per line, for a program running this for you",
    )

    args = parser.parse_args(argv)
    if args.command == "doctor":
        return doctor(args.config, client_path=args.client)
    if args.command == "purge":
        return purge(args.config)
    if args.command == "setup-models":
        return setup_models(
            catalog_path=args.catalog,
            lock_path=args.lock,
            models_dir=args.models_dir,
            pin_targets=args.pin,
            status_only=args.status,
            smoke=args.smoke,
            events=args.events,
        )
    if args.command == "serve":
        return serve(config_path=args.config, client_path=args.client)
    return auth_login(
        client_path=args.client,
        state_dir=args.state_dir,
        dry_run=args.dry_run,
        expected_account=args.expect_account,
        events=args.events,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
