"""`mailweave auth login`: the desktop loopback consent flow (AD A.4, SN 2.1, RR GMAIL-06).

Round 1 built the non-interactive half - PKCE, the authorisation URL, redirect parsing. This
completes it, up to and including the two checks that make the result trustworthy:

  * **scope verification after consent.** Google's token response carries the scope set it
    actually granted. It is read back and compared to what was requested, and any difference
    in *either* direction is fatal. A missing scope means the client cannot do its job; an
    extra one means the process now holds capability nobody asked for, which is exactly what
    SEC-01's single-scope posture exists to prevent. If the response carries no `scope` field
    at all the flow **fails closed** rather than assuming the request was honoured - that is
    the whole instruction, and "we asked for readonly so we have readonly" is the assumption
    it forbids;
  * **account pinning.** `users.getProfile` is called before the credential is stored, and
    the address it returns is shown to the owner and compared against whatever the caller
    pinned. The harness's half of this lives in `mailweave_harness.pinning`, because the
    harness holds the destructive scope and the server may not name it.

**Nothing here logs, and no secret appears in any value that can be rendered.** The client
secret, the authorization code, the PKCE verifier, the access token and the refresh token are
all `SecretStr` or local variables that never enter a dataclass with a default `__repr__`.
`tests/test_auth_consent.py` forces an exception on each step and greps the formatted
traceback for every one of them.

**Consent is not run from an agent environment.** This module opens no browser by itself: it
prints the URL and waits. The owner runs the command on their own machine, sees Google's
consent screen with their own eyes, and reads back what was granted.
"""

from __future__ import annotations

import json
import secrets
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr

from mailweave.auth.pkce import (
    LOOPBACK_HOST,
    OAuthCallbackError,
    PkcePair,
    build_authorization_url,
    generate_pkce,
    new_state,
    parse_redirect,
    redirect_uri,
)
from mailweave.auth.profile import Profile, derive_profile, normalise_address
from mailweave.auth.tokenstore import StoredCredentials, TokenStore, new_salt
from mailweave.config import assert_not_group_or_world_accessible
from mailweave.constants import OAUTH_TOKEN_HOST, SERVER_SCOPES, clean_slug
from mailweave.errors import ConfigError, MailweaveError
from mailweave.net.egress import build_client, check_url

TOKEN_ENDPOINT: Final[str] = f"https://{OAUTH_TOKEN_HOST}/token"

#: How long the loopback listener waits for the browser to come back, in seconds. Long enough
#: for a person to read a consent screen; short enough that a forgotten terminal frees the
#: port. Not a product threshold and not measured against any criterion.
CONSENT_TIMEOUT_S: Final[float] = 300.0

_DONE_PAGE: Final[bytes] = (
    b"<!doctype html><meta charset=utf-8><title>MailWeave</title>"
    b"<p>Consent received. You can close this tab: the program that asked for it - Claude or "
    b"your terminal - reports what Google granted."
)


class ConsentFailed(MailweaveError):
    """The consent flow did not complete. Never carries a code, a token or a secret."""


class GrantedScopeMismatch(ConsentFailed):
    """Google granted a different scope set than the one requested.

    Fatal, in both directions. A narrower grant cannot serve; a wider one is capability the
    owner did not agree to give this client and the code did not ask for.
    """


class ScopeUnverifiable(ConsentFailed):
    """The token response carried no scope set, so what was granted cannot be read back.

    Fail closed. The instruction for this flow is "never assume the request was honoured",
    and a flow that stored the credential here would be assuming exactly that.

    **Whether Google's token endpoint always returns `scope` for an installed-app grant is a
    preflight question (PF-17, registered in AD §F), not a settled fact.** If it turns out
    to be routinely absent, the fix is a second read-back - `oauth2.googleapis.com/tokeninfo`,
    which is on the runtime egress allowlist already - and *not* relaxing this check.
    """


@dataclass(frozen=True)
class InstalledClient:
    """A Google Cloud "Desktop app" OAuth client, read from its downloaded JSON."""

    client_id: str
    client_secret: SecretStr
    path: Path

    def __repr__(self) -> str:
        return f"InstalledClient(client_id={self.client_id!r}, secret=<redacted>)"


def read_installed_client(path: Path) -> InstalledClient:
    """Read a client-secrets file, refusing an over-permissive one and a web client.

    The `installed` key is what the console emits for a Desktop-app client. A `web` client is
    refused rather than coerced: its redirect handling is different, and SN 2.1 puts this
    project on the installed-app loopback flow with no OOB and no custom scheme.
    """
    resolved = path.expanduser()
    assert_not_group_or_world_accessible(resolved)
    try:
        raw: Any = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as failure:
        raise ConfigError(f"cannot read the OAuth client at {resolved}: {failure}") from failure
    if not isinstance(raw, dict):
        raise ConfigError(f"the OAuth client at {resolved} is not a JSON object")
    if "web" in raw and "installed" not in raw:
        raise ConfigError(
            f"the OAuth client at {resolved} is a *web* client. MailWeave uses the "
            "installed-app loopback flow (no OOB, no custom scheme), which needs a client of "
            'type "Desktop app" (SN 2.1)'
        )
    section = raw.get("installed")
    if not isinstance(section, dict):
        raise ConfigError(
            f"the OAuth client at {resolved} has no `installed` section; download the JSON "
            'for a "Desktop app" client from the Google Cloud console'
        )
    client_id = section.get("client_id")
    client_secret = section.get("client_secret")
    if not isinstance(client_id, str) or not client_id:
        raise ConfigError(f"the OAuth client at {resolved} carries no client_id")
    if not isinstance(client_secret, str) or not client_secret:
        raise ConfigError(f"the OAuth client at {resolved} carries no client_secret")
    return InstalledClient(
        client_id=client_id, client_secret=SecretStr(client_secret), path=resolved
    )


@dataclass(frozen=True)
class TokenGrant:
    """What the token endpoint returned. Every secret is a `SecretStr`."""

    access_token: SecretStr
    refresh_token: SecretStr | None
    granted_scopes: tuple[str, ...] | None
    expires_in: int | None
    token_type: str

    def __repr__(self) -> str:
        return (
            f"TokenGrant(granted_scopes={self.granted_scopes!r}, "
            f"expires_in={self.expires_in!r}, token_type={self.token_type!r}, "
            "access_token=<redacted>, refresh_token=<redacted>)"
        )


def _grant_from(body: Any) -> TokenGrant:
    if not isinstance(body, dict):
        raise ConsentFailed("the token endpoint returned a body that is not a JSON object")
    if "error" in body:
        # `error` is a closed OAuth vocabulary token; `error_description` is free text from
        # the remote side and is not repeated.
        # `constants.clean_slug`, not `str.isidentifier()`: the two agree on `invalid_grant`
        # and disagree on everything Unicode calls an identifier, which is most of it. The
        # Gmail client checks the same shape in the same way (round 11's standing-cycle sweep).
        code = clean_slug(body.get("error")) or "unspecified"
        raise ConsentFailed(f"the token endpoint refused the exchange: {code}")
    access = body.get("access_token")
    if not isinstance(access, str) or not access:
        raise ConsentFailed("the token endpoint returned no access token")
    refresh = body.get("refresh_token")
    scope = body.get("scope")
    expires = body.get("expires_in")
    token_type = body.get("token_type")
    return TokenGrant(
        access_token=SecretStr(access),
        refresh_token=SecretStr(refresh) if isinstance(refresh, str) and refresh else None,
        granted_scopes=tuple(scope.split()) if isinstance(scope, str) and scope.strip() else None,
        expires_in=expires if isinstance(expires, int) else None,
        token_type=token_type if isinstance(token_type, str) else "",
    )


def exchange_code(
    *,
    client: InstalledClient,
    code: str,
    verifier: str,
    port: int,
    http: httpx.Client | None = None,
) -> TokenGrant:
    """Trade the authorization code for tokens at `oauth2.googleapis.com`.

    One of the two allowlisted runtime hosts, and `check_url` is called on the composed URL
    before the request, for the same reason the Gmail client does it: a caller-supplied
    client's transport is not this module's to trust.
    """
    check_url(TOKEN_ENDPOINT)
    owned = http is None
    session = http if http is not None else build_client(timeout=30.0)
    try:
        response = session.post(
            TOKEN_ENDPOINT,
            data={
                "client_id": client.client_id,
                "client_secret": client.client_secret.get_secret_value(),
                "code": code,
                "code_verifier": verifier,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri(port),
            },
        )
    except httpx.HTTPError as failure:
        raise ConsentFailed(
            f"the token exchange could not be completed: {type(failure).__name__}"
        ) from failure
    finally:
        if owned:
            session.close()
    try:
        body = response.json()
    except ValueError as failure:
        raise ConsentFailed(
            f"the token endpoint returned {response.status_code} with a non-JSON body"
        ) from failure
    return _grant_from(body)


def verify_granted_scopes(
    grant: TokenGrant, *, requested: tuple[str, ...] = SERVER_SCOPES
) -> tuple[str, ...]:
    """Read back what Google granted and refuse anything that is not exactly what was asked.

    Order is not significant - a scope set is a set - but membership is, in both directions.
    """
    if grant.granted_scopes is None:
        raise ScopeUnverifiable(
            "the token response carried no `scope` field, so the granted scope set cannot be "
            "read back. Refusing to store a credential whose capability is unverified: "
            '"we requested readonly, therefore we hold readonly" is the assumption this '
            "check exists to remove (AD A.4, RR SEC-01)"
        )
    granted = set(grant.granted_scopes)
    wanted = set(requested)
    if granted != wanted:
        missing = sorted(wanted - granted)
        extra = sorted(granted - wanted)
        raise GrantedScopeMismatch(
            "Google granted a different scope set than the one requested. "
            f"requested={sorted(wanted)} granted={sorted(granted)} "
            f"missing={missing} unexpected={extra}. Refusing to store the credential: a "
            "narrower grant cannot serve, and a wider one is capability nobody asked for."
        )
    return tuple(sorted(granted))


def refresh_access_token(
    *,
    client: InstalledClient,
    refresh_token: SecretStr,
    http: httpx.Client | None = None,
    requested_scopes: tuple[str, ...] = SERVER_SCOPES,
) -> TokenGrant:
    """Exchange a stored refresh token for an access token, re-verifying the scope set.

    The scope check runs again here and is not a formality: a grant can be *narrowed* after
    consent - the owner revokes part of it at myaccount.google.com, or the client's
    configuration changes - and a refresh is where that first becomes visible. Google returns
    `scope` on a refresh response, so the same read-back applies.

    A refused refresh is `auth_reauth_required` in D.11's vocabulary: the remedy is
    `mailweave auth login`, in those words, never a retrieval error (GMAIL-06).
    """
    check_url(TOKEN_ENDPOINT)
    owned = http is None
    session = http if http is not None else build_client(timeout=30.0)
    try:
        response = session.post(
            TOKEN_ENDPOINT,
            data={
                "client_id": client.client_id,
                "client_secret": client.client_secret.get_secret_value(),
                "refresh_token": refresh_token.get_secret_value(),
                "grant_type": "refresh_token",
            },
        )
    except httpx.HTTPError as failure:
        raise ConsentFailed(
            f"the token refresh could not be completed: {type(failure).__name__}"
        ) from failure
    finally:
        if owned:
            session.close()
    try:
        body = response.json()
    except ValueError as failure:
        raise ConsentFailed(
            f"the token endpoint returned {response.status_code} with a non-JSON body"
        ) from failure
    try:
        grant = _grant_from(body)
    except ConsentFailed as failure:
        raise ConsentFailed(
            f"{failure}. The stored grant is expired or revoked: run `mailweave auth login` "
            "to re-authorise the read-only client (auth_reauth_required)."
        ) from failure
    # A refresh response omitting `scope` is treated as "unchanged", not as "unverifiable":
    # unlike a first consent, there is a previously verified grant to fall back on, and it
    # was verified by this same check. Stated because it is a real difference between the two
    # call sites of `verify_granted_scopes`, and reading them as identical would be wrong.
    if grant.granted_scopes is not None:
        verify_granted_scopes(grant, requested=requested_scopes)
    return grant


#: How long before a grant's stated expiry a refresh is taken (seconds). **Derived, not
#: chosen:** it is one `GmailClient` retry ladder's worth of wall clock plus the round trip
#: to the token endpoint, so a token that passes this check cannot expire *during* the call
#: it was fetched for. A larger margin would refresh tokens that are still good; a smaller
#: one would hand a request a credential that dies mid-ladder, which is the failure this
#: margin exists to prevent rather than a cost it trades against.
TOKEN_REFRESH_SKEW_S: Final[float] = 120.0


class StoredTokenProvider:
    """A `TokenProvider` backed by the credential store: refreshes on expiry, single-flight.

    **The expiry check and the single-flight guard this docstring used to promise to WS-15
    now exist here** (round 25, R-MCP-009). WS-15 shipped a long-lived server process and
    this class exchanged the refresh token exactly **once for the life of that process**:
    `self._grant` was set on the first call and nothing ever cleared it, so from the moment
    Google's `expires_in` (3,599 s on a real grant) elapsed, every tool call failed with a
    401 for as long as the server ran, and never recovered. A demonstration inside the first
    hour succeeded and the same server tried the next morning failed on every call.

    Three things close it, and each is small:

      * **expiry.** A grant states `expires_in`; the deadline is recorded against
        `time.monotonic` - which no clock change can move - and a grant inside
        `TOKEN_REFRESH_SKEW_S` of it is refreshed before it is handed out. A grant that
        states no `expires_in` is treated as valid until it fails, because guessing a
        lifetime for it would be inventing a fact the token endpoint declined to state;
      * **single flight.** One lock around the exchange, and the deadline is re-checked
        inside it, so N concurrent callers arriving at expiry produce one exchange and not N.
        A.5c gives the server a single event loop, so this is belt and braces - and the
        `anyio.Lock` in `surface/server.py` is a different lock in a different layer, which
        is exactly the kind of thing that changes without this one noticing;
      * **invalidation.** `invalidate()` drops the cached grant so a caller that saw a 401
        can force a re-exchange rather than the process having to be restarted.

    A refresh the token endpoint refuses raises `ConsentFailed` naming `mailweave auth login`
    (GMAIL-06), which is `refresh_access_token`'s own behaviour and is not repeated here.
    """

    __slots__ = ("_client", "_clock", "_deadline", "_grant", "_http", "_lock", "_store")

    def __init__(
        self,
        *,
        client: InstalledClient,
        store: TokenStore,
        http: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._store = store
        self._http = http
        self._grant: TokenGrant | None = None
        self._deadline: float | None = None
        self._lock = threading.Lock()
        # Injected so a test can reach the expiry branch without sleeping an hour. It is a
        # *monotonic* clock by contract - never a wall clock - because a wall clock moving
        # backwards would make a live token look expired and one moving forwards would make
        # an expired token look live.
        self._clock = clock

    def _usable(self) -> bool:
        if self._grant is None:
            return False
        if self._deadline is None:
            return True
        return self._clock() < self._deadline - TOKEN_REFRESH_SKEW_S

    def access_token(self) -> str:
        if not self._usable():
            with self._lock:
                if not self._usable():
                    stored = self._store.load()
                    grant = refresh_access_token(
                        client=self._client,
                        refresh_token=stored.refresh_token,
                        http=self._http,
                        requested_scopes=stored.scopes,
                    )
                    self._grant = grant
                    self._deadline = (
                        None if grant.expires_in is None else self._clock() + grant.expires_in
                    )
        assert self._grant is not None  # `_usable()` is exactly "the grant is set and fresh"
        return self._grant.access_token.get_secret_value()

    def invalidate(self) -> None:
        """Forget the cached grant, so the next `access_token()` exchanges a new one."""
        with self._lock:
            self._grant = None
            self._deadline = None

    def __repr__(self) -> str:
        return f"StoredTokenProvider(store={self._store.path!s}, token=<redacted>)"


class _RedirectHandler(BaseHTTPRequestHandler):
    """Captures one loopback redirect and says nothing to the log."""

    captured: str | None = None

    def do_GET(self) -> None:
        query = urlsplit(self.path).query
        if "code=" not in query and "error=" not in query:
            # A browser asks for /favicon.ico before, after, or instead of anything useful.
            self.send_response(204)
            self.end_headers()
            return
        type(self).captured = self.path
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(_DONE_PAGE)))
        self.end_headers()
        self.wfile.write(_DONE_PAGE)

    def log_message(self, format: str, *args: Any) -> None:
        """Silence. The request line contains the authorization code."""


class LoopbackReceiver:
    """A one-shot listener on `127.0.0.1`, for the duration of one consent and no longer.

    RR SEC-07 forbids the *server* process a listening socket. This is not the server
    process: it is a CLI command the owner runs, the socket is bound to loopback only, it
    accepts exactly one redirect, and it is closed before the credential is stored. Stated
    here rather than left for a reviewer to reconcile.
    """

    def __init__(self, timeout_s: float = CONSENT_TIMEOUT_S) -> None:
        _RedirectHandler.captured = None
        self._server = HTTPServer((LOOPBACK_HOST, 0), _RedirectHandler)
        self._server.timeout = timeout_s
        self._deadline_s = timeout_s

    @property
    def port(self) -> int:
        port: int = self._server.server_address[1]
        return port

    def wait_for_redirect(self) -> str:
        """Serve requests until one carries a code or an error, or the timeout expires."""
        remaining = self._deadline_s
        while remaining > 0:
            started = datetime.now(UTC)
            self._server.handle_request()
            captured = _RedirectHandler.captured
            if captured is not None:
                return f"http://{LOOPBACK_HOST}:{self.port}{captured}"
            remaining -= (datetime.now(UTC) - started).total_seconds()
        raise ConsentFailed(
            f"no redirect arrived on the loopback listener within {self._deadline_s:.0f}s"
        )

    def close(self) -> None:
        self._server.server_close()


@dataclass(frozen=True)
class LoginReport:
    """What `mailweave auth login` states, as data rather than as printed lines.

    The command's output is a rendering of this, so what it claims is testable without a
    terminal - and so a reviewer can see that every sentence it prints is a field that was
    actually observed rather than a hopeful string.
    """

    client_id: str
    client_path: Path
    requested_scopes: tuple[str, ...]
    granted_scopes: tuple[str, ...]
    scopes_verified: bool
    account: str
    profile: Profile
    token_path: Path
    refresh_token_stored: bool
    obtained_at: str

    def lines(self) -> list[str]:
        return [
            f"client:            {self.client_id} ({self.client_path})",
            f"requested scopes:  {' '.join(self.requested_scopes)}",
            f"GRANTED scopes:    {' '.join(self.granted_scopes)}",
            "scope check:       "
            + (
                "OK - Google granted exactly what was requested"
                if self.scopes_verified
                else "FAILED"
            ),
            f"account:           {self.account}",
            f"redaction profile: {self.profile.value}",
            f"token store:       {self.token_path} (0600, in a 0700 directory)",
            "refresh token:     "
            + ("stored" if self.refresh_token_stored else "NOT RETURNED - see below"),
            f"obtained at:       {self.obtained_at}",
        ]


ProfileFetcher = Callable[[str], str]
"""Given an access token, return the authenticated `emailAddress`.

A parameter rather than an import for two reasons: the consent flow is then testable end to
end with no socket, and the evaluation harness package - which the server may not name, let
alone import - can pass a fetcher that pins to the seed account.
"""


def run_login(
    *,
    client: InstalledClient,
    store: TokenStore,
    fetch_address: ProfileFetcher,
    announce: Callable[[str], None],
    wait_for_code: Callable[[str, str], str],
    requested_scopes: tuple[str, ...] = SERVER_SCOPES,
    http: httpx.Client | None = None,
    expected_account: str | None = None,
    seed_account_hash: str | None = None,
    seed_client_id: str | None = None,
    pkce: PkcePair | None = None,
    state: str | None = None,
    port: int = 0,
) -> LoginReport:
    """The consent flow, with the browser and the listener supplied by the caller.

    `wait_for_code(authorization_url, state) -> redirect_url` is where the interactive step
    lives. The CLI passes an implementation that prints the URL and runs the loopback
    receiver; a test passes one that returns a canned redirect. Splitting it this way is what
    makes every check in here reachable without a browser - and it is why nothing in this
    module can start a consent by itself.
    """
    pair = pkce if pkce is not None else generate_pkce()
    expected_state = state if state is not None else new_state()
    authorization_url = build_authorization_url(
        client_id=client.client_id,
        port=port,
        pkce=pair,
        state=expected_state,
        scopes=requested_scopes,
    )
    redirect = wait_for_code(authorization_url, expected_state)
    try:
        code = parse_redirect(redirect, expected_state=expected_state)
    except OAuthCallbackError as failure:
        raise ConsentFailed(f"the loopback redirect was refused: {failure}") from failure

    grant = exchange_code(client=client, code=code, verifier=pair.verifier, port=port, http=http)
    granted = verify_granted_scopes(grant, requested=requested_scopes)
    announce("scope check: OK - Google granted exactly what was requested")

    address = normalise_address(fetch_address(grant.access_token.get_secret_value()))
    if expected_account is not None and address != normalise_address(expected_account):
        raise ConsentFailed(
            "the consented account is not the one this command was pinned to. Refusing to "
            "store the credential; nothing has been written."
        )
    if grant.refresh_token is None:
        raise ConsentFailed(
            "Google returned no refresh token, so this credential would die with the "
            "process. Revoke the app's access at myaccount.google.com and consent again - a "
            "re-consent for an already-granted client omits the refresh token unless the "
            "grant is fresh (`prompt=consent` is already sent)."
        )

    obtained_at = datetime.now(UTC).isoformat()
    salt = new_salt()
    # The profile is **derived**, not asserted. Writing `Profile.PERSONAL` here would have
    # been correct in every case this command can currently produce - a fresh salt makes the
    # digest comparison vacuous, and an unset seed configuration fails closed to personal
    # anyway - and it would still have been the project's own recurring defect: a report
    # stating a value the code decided rather than one the code computed. It is computed, and
    # what it is computed from is visible in the call.
    profile = derive_profile(
        observed_address=address,
        salt=salt,
        configured_seed_hash=seed_account_hash,
        credential_client_id=client.client_id,
        seed_client_id=seed_client_id,
    )
    store.save(
        StoredCredentials(
            client_id=client.client_id,
            refresh_token=grant.refresh_token,
            scopes=granted,
            salt_hex=salt.hex(),
            obtained_at=obtained_at,
        )
    )
    return LoginReport(
        client_id=client.client_id,
        client_path=client.path,
        requested_scopes=requested_scopes,
        granted_scopes=granted,
        scopes_verified=True,
        account=address,
        profile=profile,
        token_path=store.path,
        refresh_token_stored=True,
        obtained_at=obtained_at,
    )


def free_loopback_port() -> int:
    """A port nothing is listening on. Used only when a caller wants the URL before the server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((LOOPBACK_HOST, 0))
        port: int = probe.getsockname()[1]
    return port


def random_nonce() -> str:
    """Kept beside `new_state` so nothing here reaches for `random` when it means `secrets`."""
    return secrets.token_urlsafe(24)
