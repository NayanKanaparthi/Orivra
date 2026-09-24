"""Loopback + PKCE S256 parameters (AD A.4, SN §3; RR GMAIL-06).

Only the non-interactive half is built in this round: verifier/challenge generation, the
authorisation URL, and redirect parsing with state checking. The consent step needs a
browser and a live OAuth client, and is explicitly out of scope for round 1.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlsplit

from mailweave.constants import SERVER_SCOPES

AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
LOOPBACK_HOST = "127.0.0.1"


class OAuthCallbackError(ValueError):
    """The redirect did not carry a usable, state-matched authorization code."""


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


@dataclass(frozen=True)
class PkcePair:
    verifier: str
    challenge: str
    method: str = "S256"


def generate_pkce(entropy_bytes: int = 64) -> PkcePair:
    """RFC 7636 S256. `plain` is never produced: PKCE is unconditional (SN §3)."""
    verifier = _b64url(secrets.token_bytes(entropy_bytes))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return PkcePair(verifier=verifier, challenge=challenge)


def redirect_uri(port: int) -> str:
    """Installed-app loopback redirect. No OOB, no custom scheme."""
    if not 1 <= port <= 65535:
        raise ValueError(f"port {port} is not a valid loopback port")
    return f"http://{LOOPBACK_HOST}:{port}/"


def build_authorization_url(
    *,
    client_id: str,
    port: int,
    pkce: PkcePair,
    state: str,
    scopes: tuple[str, ...] = SERVER_SCOPES,
) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri(port),
        "response_type": "code",
        "scope": " ".join(scopes),
        "code_challenge": pkce.challenge,
        "code_challenge_method": pkce.method,
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{AUTHORIZATION_ENDPOINT}?{urlencode(params)}"


def new_state() -> str:
    return _b64url(secrets.token_bytes(32))


def parse_redirect(url: str, *, expected_state: str) -> str:
    """Return the authorization code, or raise. State mismatch is a hard failure."""
    query = parse_qs(urlsplit(url).query)
    if "error" in query:
        raise OAuthCallbackError(f"authorization failed: {query['error'][0]}")
    states = query.get("state", [])
    if not states or not secrets.compare_digest(states[0], expected_state):
        raise OAuthCallbackError("state parameter did not match; refusing the redirect")
    codes = query.get("code", [])
    if not codes or not codes[0]:
        raise OAuthCallbackError("redirect carried no authorization code")
    return codes[0]
