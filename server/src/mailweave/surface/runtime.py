"""Server startup: the credential, the profile, the key - and the refusals before serving.

OD-6 criterion 1 is "the MCP server starts through a documented command", and the sentence
that matters more is the one beside it: **it refuses to start without a valid credential**.
Three things are established before a single byte of MCP is spoken, in this order, and each
of them ends the process rather than degrading:

  1. **the configuration and the credential store.** Both are read through WS-01's own
     loaders, which check file modes first and hold every secret in a `SecretStr`;
  2. **the access token.** The stored refresh token is exchanged, and the *granted* scope
     set is read back and compared with the requested one. A refused refresh is D.11's
     `auth_reauth_required` and its remediation is `mailweave auth login`, in those words
     (GMAIL-06);
  3. **the redaction profile** (AD A.4). `users.getProfile` names the account; if it fails,
     `AuthProfileUnderivable` is raised and the server does not serve. D.11 makes that a
     **startup failure** rather than a tool error precisely so it cannot be defaulted: a
     profile guessed is a redaction policy guessed.

**Nothing printed here is a secret.** The startup banner goes to **stderr**, because stdout
is the MCP transport and a byte written there is a protocol frame. It names the client id,
the granted scopes, the account address, the derived profile, the store path and the tool
names. `tests/fixtures/secret_models.py`'s reflection canary covers every model that carries
a secret, and
`test_a_startup_that_succeeds_prints_nothing_unsafe_and_prints_it_to_stderr` drives this
function's own output against a credential built out of recognisable values.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

import httpx

from mailweave.auth.consent import (
    ConsentFailed,
    InstalledClient,
    StoredTokenProvider,
    read_installed_client,
)
from mailweave.auth.profile import Profile, derive_profile
from mailweave.auth.tokenstore import TokenStore
from mailweave.config import MailweaveConfig, load_config
from mailweave.constants import RUNTIME_EGRESS_ALLOWLIST, SERVER_SCOPES
from mailweave.diagnostics import ENV_VAR, lifecycle
from mailweave.disclosure import Selector
from mailweave.errors import AuthProfileUnderivable, MailweaveError, TokenStoreError
from mailweave.gmail.client import GmailClient
from mailweave.gmail.faults import GmailAuthExpired, GmailFault
from mailweave.handles.cache import ThreadMapCache
from mailweave.handles.keys import HandleKey, ensure_handle_key
from mailweave.net.egress import build_client
from mailweave.semantic import REGISTRY
from mailweave.semantic.interface import BackendRegistry
from mailweave.surface.service import MailweaveService
from mailweave.surface.tools import TOOL_SPECS


@dataclass(frozen=True)
class StartupReport:
    """What the server established before it agreed to serve. Every line safe to print."""

    client_id: str
    account: str
    profile: Profile
    granted_scopes: tuple[str, ...]
    token_path: Path
    handles_enabled: bool

    def lines(self) -> tuple[str, ...]:
        return (
            f"mailweave serve: ready on stdio ({len(TOOL_SPECS)} read-only tools)",
            f"  tools:           {', '.join(spec.name.value for spec in TOOL_SPECS)}",
            f"  client:          {self.client_id}",
            f"  account:         {self.account}",
            f"  profile:         {self.profile.value}",
            f"  granted scopes:  {' '.join(self.granted_scopes)}",
            f"  egress:          {', '.join(sorted(RUNTIME_EGRESS_ALLOWLIST))}",
            f"  token store:     {self.token_path}",
            f"  map_id handles:  {'enabled' if self.handles_enabled else 'disabled (no key)'}",
            f"  diagnostics:     {_diagnostics_line()}",
        )


def _diagnostics_line() -> str:
    """Where the call lifecycle diagnostic writes, or that it is off (2026-09-21).

    On the banner so the owner running a retest can see, before the first call, whether the
    file they asked for is the file the process will write. The path is the owner's own
    choice and holds no mail; printing it is printing a setting.
    """
    writer = lifecycle()
    return f"on, {writer.path}" if writer.enabled else f"off (set {ENV_VAR} to a file path)"


@dataclass(frozen=True)
class Runtime:
    """A started server: the service the tools run against, and what starting established."""

    service: MailweaveService
    report: StartupReport
    close: Callable[[], None]


def start(
    *,
    config_path: Path | None = None,
    client_path: Path,
    http: httpx.Client | None = None,
    config: MailweaveConfig | None = None,
    installed: InstalledClient | None = None,
    registry: BackendRegistry | None = None,
    selector: Selector | None = None,
    cross_encoder: bool = True,
) -> Runtime:
    """Establish everything the four tools need, or raise before serving anything.

    `http`, `config` and `installed` are injected so the whole of startup - including its
    refusals - is drivable behind `httpx.MockTransport` with no network and no credential
    file on disk. Nothing about the order or the checks changes between that and a real
    start: this is the function `mailweave serve` calls.
    """
    settings = config if config is not None else load_config(config_path)
    client = installed if installed is not None else read_installed_client(client_path)
    store = TokenStore(settings.token_path)
    store.verify_permissions()
    stored = store.load()

    session = http if http is not None else build_client(timeout=30.0)
    token = StoredTokenProvider(client=client, store=store, http=session)
    probe = GmailClient(token=token, http=session)
    # **Four distinct credential failures, four distinct messages** (round 25, R-MCP-006).
    # Round 24 caught `(GmailFault, MailweaveError)` here - the broadest catch there is - and
    # set `observed = None`, so a refused refresh, a narrowed grant, a `getProfile` 500 and a
    # revoked token (a 401) all arrived as `auth_profile_underivable` with "Check network and
    # credentials", and SETUP's troubleshooting row for that code sends the operator to check
    # network reachability. Three of those four are consent problems and one of them - the
    # [VERIFIED] 7-day Testing clock - is the commonest first-run failure there is. This
    # module's own docstring already promised the right behaviour: "A refused refresh is
    # D.11's `auth_reauth_required` and its remediation is `mailweave auth login`, in those
    # words (GMAIL-06)". These two clauses are that sentence, executed.
    #
    # What is translated is only what the code actually means: a `users.getProfile` this
    # server could not read an address out of. D.11 makes that a **startup failure** rather
    # than a tool error precisely so it cannot be defaulted - a profile guessed is a
    # redaction policy guessed - and `observed = None` is the input `derive_profile` already
    # refuses, so the refusal keeps that module's own words.
    try:
        observed: str | None = probe.get_profile().email_address
    except (GmailAuthExpired, ConsentFailed, TokenStoreError):
        # The grant itself is the problem: it was refused, revoked, or granted for a
        # different scope set. Each of these already carries its own cause and, for the
        # first, `mailweave auth login` in GMAIL-06's own words. Re-raised as itself so the
        # operator reads the failure that happened.
        raise
    except (GmailFault, MailweaveError):
        observed = None
    # `derive_profile` raises `AuthProfileUnderivable` for an address it never observed. It
    # is raised rather than defaulted, and it is raised *here* - before the server exists -
    # because D.11 classes it as a startup failure and a redaction profile that was guessed
    # is a redaction policy that was guessed (AD A.4).
    profile = derive_profile(
        observed_address=observed,
        salt=stored.salt,
        configured_seed_hash=settings.seed_account_hash,
        credential_client_id=stored.client_id,
        seed_client_id=settings.seed_client_id,
    )
    # Reached only when `derive_profile` did not raise, which is exactly when it saw an
    # address. mypy cannot know that, and asserting it is cheaper than widening every field
    # below to `str | None` for a state this line is unreachable in.
    assert observed is not None
    key: HandleKey | None = ensure_handle_key(store)
    account_hash = _account_hash(stored.salt, observed)

    def open_client() -> GmailClient:
        return GmailClient(token=token, http=session)

    service = MailweaveService(
        open_client=open_client,
        account_hash=account_hash,
        handle_key=key,
        cache=ThreadMapCache(),
        # AD D.9: the `historyId` watermark's published location. Handed to the service
        # rather than looked up inside it, so a test builds a service over a temp directory
        # without touching the developer's own state.
        watermark_path=settings.watermark_path,
        # **Injected so an evaluation arm is built by the shipped startup path.** H1-H3
        # compare MailWeave with and without a semantic backend, and an arm constructed
        # some other way is an arm nobody ships - the registry is the one thing that
        # differs between them, so it is the one thing this takes. The default is the
        # module-level `REGISTRY`, which is what `mailweave serve` gets.
        registry=REGISTRY if registry is None else registry,
        # Baseline F's hook, for the registry's reason: DISC-02 compares the two disclosure
        # policies at equal budget, and an arm built outside the shipped startup path is an
        # arm nobody ships. `None` is `QueryAwareFill`.
        selector=selector,
        # D.7's second tier, for `selector`'s reason: `no-rerank` is H2's matched arm and an
        # arm built outside the shipped startup path is an arm nobody ships. `True` ships.
        cross_encoder=cross_encoder,
    )
    # **The model load is paid at startup, not inside the first query** (PF-4: 5,410 ms cold
    # against a 6,000 ms `max_semantic_ms`). Best-effort: a machine with no weights is a
    # supported configuration and L5 declines in band on it.
    service.warm_semantic_backend()
    report = StartupReport(
        client_id=client.client_id,
        account=observed,
        profile=profile,
        granted_scopes=tuple(stored.scopes),
        token_path=store.path,
        handles_enabled=key is not None,
    )
    return Runtime(service=service, report=report, close=session.close)


def _account_hash(salt: bytes, address: str) -> str:
    """The account a handle is bound to, as a digest rather than as an address (A.10).

    `account_digest` is WS-01's, imported rather than restated: a handle minted under one
    account must not verify under another, and the two computations of "which account is
    this" have to be one computation.
    """
    from mailweave.auth.profile import account_digest

    return f"sha256:{account_digest(salt, address)}"


def announce(report: StartupReport, out: TextIO | None = None) -> None:
    """Print the startup banner to **stderr**, never to stdout.

    stdout is the MCP transport. A line written there is a malformed JSON-RPC frame, and a
    server that greets its client with one is a server that does not start.
    """
    stream = out if out is not None else sys.stderr
    for line in report.lines():
        print(line, file=stream)


__all__ = [
    "SERVER_SCOPES",
    "AuthProfileUnderivable",
    "Runtime",
    "StartupReport",
    "announce",
    "start",
]
