"""The setup flow: connect Gmail, download the models, verify, then serve.

**Every step is a product command or a product function.** Connecting is `mailweave auth
login --events`; downloading is `mailweave setup-models --events`; verifying is
`mailweave.surface.runtime.start`, the function `orivra serve` calls, with the semantic
backend loaded from this installation's own model directory. Nothing here decides whether a
credential is valid, which scopes were granted or whether a weight file is the locked one: the
product already decides each of those, and this module reports what it decided.

`Setup.advance()` is the one entry point the setup tool calls. It is idempotent: it looks at
what is done, starts whichever step is missing and not already running, and says so. A person
can call it as often as they like; two consents or two downloads never run at once.
"""

from __future__ import annotations

import sys
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from mailweave.auth.consent import ConsentFailed, read_installed_client
from mailweave.auth.tokenstore import TokenStore
from mailweave.config import MailweaveConfig
from mailweave.errors import (
    AuthProfileUnderivable,
    ConfigError,
    MailweaveError,
    TokenStoreError,
)
from mailweave.gmail.faults import GmailAuthExpired, GmailFault
from mailweave.models.lock import Lock, LockError, load_lock
from mailweave.semantic import BackendUnavailable, SemanticError
from mailweave.semantic.interface import BackendRegistry
from mailweave.semantic.local import build_local_backend
from mailweave.surface.runtime import Runtime, announce, start
from orivra.desktop import texts
from orivra.desktop.children import Child, Spawner, spawn_mailweave
from orivra.desktop.paths import DesktopPaths
from orivra.registry import ConnectorRegistry
from orivra.surface.service import OrivraService

#: How long `advance` waits for a fresh `auth login` child to print its link. The child binds
#: its listener and builds the URL before anything slow happens; this bounds a cold start of
#: the interpreter, not a network call.
LINK_WAIT_S = 20.0


@dataclass(frozen=True)
class Ready:
    """What a successful bring-up established. Every field was observed, not assumed."""

    runtime: Runtime
    service: OrivraService
    account: str
    granted: tuple[str, ...]
    obtained_at: datetime | None
    models: tuple[str, ...]


class BringUpFailed(Exception):
    """Bring-up did not reach a served state. `kind` says which step has to be redone."""

    def __init__(self, kind: str, reason: str) -> None:
        super().__init__(reason)
        self.kind = kind  # "gmail", "models" or "retry"
        self.reason = reason


def start_desktop_runtime(paths: DesktopPaths) -> tuple[Runtime, OrivraService, tuple[str, ...]]:
    """`orivra serve`'s startup, over this installation's paths.

    The one difference from `orivra serve` is where the semantic backend loads from: a
    registry of its own, whose factory is `register_default`'s with the bundle's lock and this
    installation's model directory named instead of the working directory's `models.lock` and
    `~/.local/share/mailweave/models`. A fresh registry per bring-up, because a registry
    remembers a decline for the life of the process and a download that finished after one
    must be able to take effect.
    """
    registry = BackendRegistry()

    def factory() -> Any:
        try:
            lock = load_lock(paths.lock)
        except Exception as exc:
            raise BackendUnavailable(str(exc)) from exc
        return build_local_backend(lock, root=paths.models)

    registry.register("local", factory, default=True)
    client = read_installed_client(paths.client)
    config = MailweaveConfig(
        client_id=client.client_id, client_secret=client.client_secret, state_dir=paths.state
    )
    runtime = start(config=config, client_path=paths.client, installed=client, registry=registry)
    announce(runtime.report)
    if not runtime.service.warm_semantic_backend():
        try:
            registry.acquire()
            reason = "the local models did not load"
        except SemanticError as declined:
            reason = str(declined)
        runtime.close()
        raise BringUpFailed("models", reason)
    backend = registry.acquire()
    service = OrivraService(registry=ConnectorRegistry.from_runtime(runtime))
    return runtime, service, (f"{backend.model_id}@{backend.model_revision[:12]}",)


BringUp = Callable[[DesktopPaths], tuple[Runtime, OrivraService, tuple[str, ...]]]


def models_present(lock: Lock, root: Path) -> bool:
    """Every locked file is on disk at its locked size. Cheap; the digests are checked by the
    loader at bring-up and by the installer, which is where a mismatch is decided."""
    from mailweave.models.paths import model_dir

    for key, locked in lock.models.items():
        directory = model_dir(key, locked.revision, root)
        for entry in locked.files:
            target = directory / entry.name
            if not target.is_file() or target.stat().st_size != entry.bytes:
                return False
    return True


class Setup:
    """The state of one installation, and the one call that moves it forward."""

    def __init__(
        self,
        paths: DesktopPaths,
        *,
        spawn: Spawner = spawn_mailweave,
        bring_up: BringUp = start_desktop_runtime,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.paths = paths
        self._spawn = spawn
        self._bring_up = bring_up
        self._clock = clock
        self._lock = threading.RLock()
        self._consent: Child | None = None
        self._models: Child | None = None
        self._ready: Ready | None = None
        #: Why the stored credential cannot be used, when bring-up found out. Cleared by a
        #: fresh grant.
        self._auth_invalid: str | None = None
        #: Why the installed models cannot be used, when bring-up found out.
        self._models_invalid: str | None = None
        self._last_error: str | None = None
        self._granted_as: str | None = None
        self._plan_shown = False
        self._warming: threading.Thread | None = None

    # -- readiness ------------------------------------------------------------------------

    @property
    def ready(self) -> Ready | None:
        return self._ready

    def _lock_file(self) -> Lock | None:
        try:
            return load_lock(self.paths.lock)
        except LockError:
            return None

    def _prerequisites(self) -> bool:
        lock = self._lock_file()
        return (
            self.paths.credentials.exists()
            and self._auth_invalid is None
            and lock is not None
            and self._models_invalid is None
            and models_present(lock, self.paths.models)
        )

    def warm_in_background(self) -> None:
        """Bring the runtime up now, off the protocol's thread, if nothing is missing.

        Claude Desktop starts an extension when the app starts, so on every day but the first
        the model load is paid before the person asks anything.
        """
        with self._lock:
            if self._ready is not None or self._warming is not None or not self._prerequisites():
                return
            self._warming = threading.Thread(target=self._try_bring_up, daemon=True)
            self._warming.start()

    def _join_warming(self) -> None:
        warming = self._warming
        if warming is not None:
            warming.join()
            self._warming = None

    def _try_bring_up(self) -> None:
        with self._lock:
            if self._ready is not None:
                return
            try:
                runtime, service, models = self._bring_up(self.paths)
            except BringUpFailed as failed:
                self._record(failed)
                return
            except (GmailAuthExpired, ConsentFailed) as expired:
                self._record(BringUpFailed("gmail", str(expired)))
                return
            except TokenStoreError as store:
                self._record(BringUpFailed("gmail", str(store)))
                return
            except ConfigError as config:
                self._record(BringUpFailed("retry", f"the installation's files: {config}"))
                return
            except (AuthProfileUnderivable, GmailFault, MailweaveError) as unreachable:
                self._record(BringUpFailed("retry", str(unreachable)))
                return
            except Exception as unexpected:  # the log gets the traceback; the person a sentence
                traceback.print_exc(file=sys.stderr)
                self._record(BringUpFailed("retry", f"unexpected {type(unexpected).__name__}"))
                return
            stored = TokenStore(self.paths.credentials).load()
            try:
                obtained: datetime | None = datetime.fromisoformat(stored.obtained_at)
            except ValueError:
                obtained = None
            self._ready = Ready(
                runtime=runtime,
                service=service,
                account=runtime.report.account,
                granted=tuple(runtime.report.granted_scopes),
                obtained_at=obtained,
                models=models,
            )
            self._last_error = None

    def _record(self, failed: BringUpFailed) -> None:
        if failed.kind == "gmail":
            self._auth_invalid = failed.reason
        elif failed.kind == "models":
            self._models_invalid = failed.reason
        self._last_error = failed.reason

    def service_or_status(self) -> tuple[OrivraService | None, str]:
        """For an Orivra tool call: the service, or why there is none yet."""
        with self._lock:
            self._join_warming()
            if self._ready is None and self._prerequisites():
                self._try_bring_up()
            if self._ready is not None:
                return self._ready.service, ""
            return None, self._short_status()

    def reauthorisation_needed(self) -> None:
        """A tool call came back `recovery: reauthorise`: the credential died mid-session."""
        with self._lock:
            if self._ready is not None:
                self._ready.runtime.close()
                self._ready = None
            self._auth_invalid = (
                "Google no longer accepts the stored authorization (it was revoked, or Google "
                "stopped accepting it)"
            )

    def close(self) -> None:
        with self._lock:
            for child in (self._consent, self._models):
                if child is not None:
                    child.terminate()
            if self._ready is not None:
                self._ready.runtime.close()

    # -- the steps ------------------------------------------------------------------------

    def _models_view(self) -> dict[str, Any]:
        """Where the download stands, from the child's own events when there is one."""
        lock = self._lock_file()
        if lock is None:
            return {"phase": "broken", "reason": f"no readable model lock at {self.paths.lock}"}
        sizes = {
            (key, entry.name): entry.bytes
            for key, locked in lock.models.items()
            for entry in locked.files
        }
        total = sum(sizes.values())
        repos = [f"{locked.repo_id}" for _key, locked in sorted(lock.models.items())]
        child = self._models
        if child is None:
            if self._models_invalid is None and models_present(lock, self.paths.models):
                return {"phase": "installed", "total": total, "repos": repos}
            return {"phase": "needed", "total": total, "repos": repos}
        done: dict[tuple[str, str], int] = {}
        current: str | None = None
        outcome: str | None = None
        reason: str | None = None
        for event in child.events():
            kind = event.get("event")
            if kind == "progress":
                done[(str(event.get("model")), str(event.get("file")))] = int(event.get("done", 0))
                current = str(event.get("file"))
            elif kind == "file":
                identity = (str(event.get("model")), str(event.get("file")))
                done[identity] = sizes.get(identity, 0)
            elif kind == "done":
                outcome = "done"
            elif kind == "failed":
                outcome, reason = "failed", str(event.get("reason"))
        code = child.returncode()
        if outcome == "done" and code == 0:
            return {"phase": "installed", "total": total, "repos": repos}
        if outcome == "failed" or code is not None:
            return {
                "phase": "failed",
                "total": total,
                "repos": repos,
                "reason": reason or f"the download stopped (exit status {code})",
            }
        return {
            "phase": "downloading",
            "total": total,
            "repos": repos,
            "done": sum(done.values()),
            "current": current,
        }

    def _start_models(self) -> None:
        self._models_invalid = None
        self._models = self._spawn(
            [
                "setup-models",
                "--events",
                "--lock",
                str(self.paths.lock),
                "--models-dir",
                str(self.paths.models),
            ],
            "setup-models",
        )

    def _consent_view(self) -> dict[str, Any]:
        child = self._consent
        if child is None:
            return {"phase": "none"}
        view: dict[str, Any] = {"phase": "starting"}
        for event in child.events():
            kind = event.get("event")
            if kind == "authorization_url":
                view = {
                    "phase": "awaiting",
                    "url": str(event.get("url")),
                    "minutes": max(1, int(float(event.get("timeout_s", 300)) // 60)),
                }
            elif kind == "granted":
                view = {"phase": "granted", "account": str(event.get("account"))}
            elif kind == "failed":
                view = {"phase": "failed", "reason": str(event.get("reason"))}
        code = child.returncode()
        if code is not None and view["phase"] in ("starting", "awaiting"):
            view = {"phase": "failed", "reason": f"the Gmail helper stopped (exit status {code})"}
        return view

    def _start_consent(self) -> dict[str, Any]:
        self._consent = self._spawn(
            [
                "auth",
                "login",
                "--events",
                "--client",
                str(self.paths.client),
                "--state-dir",
                str(self.paths.state),
            ],
            "auth-login",
        )
        deadline = self._clock() + LINK_WAIT_S
        view = self._consent_view()
        while view["phase"] == "starting" and self._clock() < deadline:
            time.sleep(0.1)
            view = self._consent_view()
        return view

    # -- the one call -------------------------------------------------------------------

    def advance(self) -> str:
        """Report, start what is missing, verify when nothing is. Idempotent."""
        with self._lock:
            self._join_warming()
            if self._ready is None and self._prerequisites():
                self._try_bring_up()
            if self._ready is not None:
                return self._ready_text()

            sections: list[str] = []
            models = self._models_view()
            retried_after: str | None = None
            if models["phase"] in ("needed", "failed"):
                if models["phase"] == "failed":
                    retried_after = str(models["reason"])
                self._start_models()
                if not self._plan_shown:
                    sections.append(texts.models_plan(models["total"], models["repos"]))
                    self._plan_shown = True
                models = self._models_view()

            consent = self._consent_view()
            if consent["phase"] == "granted":
                # A fresh grant supersedes whatever made the last credential unusable. Taken
                # once: the child is done, and a grant read twice would clear a later
                # refusal of this same credential and retry it for ever.
                self._auth_invalid = None
                self._granted_as = consent["account"]
                self._consent = None
                consent = {"phase": "none"}
            have_credential = self.paths.credentials.exists() and self._auth_invalid is None
            if not have_credential and consent["phase"] not in ("awaiting", "starting"):
                if consent["phase"] == "failed":
                    sections.append(f"Gmail: the last attempt did not finish - {consent['reason']}")
                elif self._auth_invalid is not None:
                    sections.append(f"Gmail: {self._auth_invalid}.")
                consent = self._start_consent()

            if models["phase"] == "installed" and have_credential:
                self._try_bring_up()
                if self._ready is not None:
                    return self._ready_text()
                # Bring-up told us which step to redo; take it on the next pass through.
                if self._restartable():
                    return self.advance()
            return self._status_text(sections, retried_after=retried_after)

    def _restartable(self) -> bool:
        """After a failed bring-up, is there a step `advance` can start? (Stops recursion.)"""
        models_again = self._models_invalid is not None and self._models is None
        gmail_again = self._auth_invalid is not None and self._consent_view()["phase"] in (
            "none",
            "failed",
        )
        return models_again or gmail_again

    # -- words ----------------------------------------------------------------------------

    def _status_text(self, sections: list[str], *, retried_after: str | None = None) -> str:
        lines = ["Orivra setup - not finished yet.", ""]
        lines.extend(sections)
        models = self._models_view()
        if models["phase"] == "downloading":
            if retried_after is not None:
                lines.append(f"Models: the last download failed ({retried_after}); started again.")
            lines.append(texts.progress(models["done"], models["total"], models.get("current")))
        elif models["phase"] == "installed":
            lines.append("Models: installed.")
        elif models["phase"] == "failed":
            lines.append(
                f"Models: the download failed - {models['reason']}. {texts.SETUP_TOOL_NAME} tries "
                "again on its next call; if it keeps failing, check this Mac's internet connection."
            )
        elif models["phase"] == "broken":
            lines.append(f"Models: {models['reason']}.")
        consent = self._consent_view()
        if self.paths.credentials.exists() and self._auth_invalid is None:
            who = f" as {self._granted_as}" if self._granted_as else ""
            lines.append(f"Gmail: authorized on this Mac{who}.")
        elif consent["phase"] == "awaiting":
            lines.append("")
            lines.append(
                texts.consent(
                    consent["url"],
                    minutes=consent["minutes"],
                    credentials_path=str(self.paths.credentials),
                )
            )
        elif consent["phase"] == "failed":
            lines.append(f"Gmail: not connected - {consent['reason']}")
        if self._last_error and self._auth_invalid is None and self._models_invalid is None:
            lines.append(f"Last check: {self._last_error}. Call {texts.SETUP_TOOL_NAME} again.")
        lines.append("")
        lines.append(
            f"Call {texts.SETUP_TOOL_NAME} again to see progress; it finishes setup by itself once "
            "Gmail is connected and the models are in place."
        )
        return "\n".join(lines)

    def _short_status(self) -> str:
        models = self._models_view()
        gmail = self.paths.credentials.exists() and self._auth_invalid is None
        parts = []
        parts.append("Gmail is connected" if gmail else "Gmail is not connected")
        parts.append(
            "the models are installed"
            if models["phase"] == "installed"
            else "the models are not installed"
        )
        return f"{' and '.join(parts)}."

    def _ready_text(self) -> str:
        ready = self._ready
        assert ready is not None
        return texts.ready(
            account=ready.account,
            granted=ready.granted,
            obtained_at=ready.obtained_at,
            models=ready.models,
            installation=installation_facts(self.paths),
        )


def installation_facts(paths: DesktopPaths) -> list[str]:
    """Where this process runs from and keeps its data - the clean-install check, stated.

    Reported rather than asserted, so a person installing on a fresh account can read, in
    Claude, that the interpreter and every import path are the extension's own.
    """
    bundle = paths.bundle
    outside = [
        entry for entry in sys.path if entry and not Path(entry).resolve().is_relative_to(bundle)
    ]
    runs_from = Path(sys.prefix).resolve()
    where = "inside the extension" if runs_from.is_relative_to(bundle) else f"at {runs_from}"
    imports = (
        "every import path is inside the extension"
        if not outside
        else f"{len(outside)} import path(s) outside the extension: {', '.join(outside)}"
    )
    return [
        f"Installation: Python runs {where}; {imports}.",
        f"Data: {paths.home} (authorization in state/, models in models/).",
    ]
