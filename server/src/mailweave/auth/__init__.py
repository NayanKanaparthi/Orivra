"""Config and credential handling (WS-01), minus the interactive consent step."""

from mailweave.auth.clients import ClientDescriptor, ClientRole, read_client
from mailweave.auth.pkce import (
    OAuthCallbackError,
    PkcePair,
    build_authorization_url,
    generate_pkce,
    new_state,
    parse_redirect,
    redirect_uri,
)
from mailweave.auth.profile import Profile, account_digest, derive_profile, normalise_address
from mailweave.auth.tokenstore import StoredCredentials, TokenStore, new_salt

__all__ = [
    "ClientDescriptor",
    "ClientRole",
    "OAuthCallbackError",
    "PkcePair",
    "Profile",
    "StoredCredentials",
    "TokenStore",
    "account_digest",
    "build_authorization_url",
    "derive_profile",
    "generate_pkce",
    "new_salt",
    "new_state",
    "normalise_address",
    "parse_redirect",
    "read_client",
    "redirect_uri",
]
