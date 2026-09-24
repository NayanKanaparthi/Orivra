"""The two-client credential model (AD A.4, A.2; RR SEC-01, SEC-03).

Two OAuth clients exist in this project:

  * the **read client**, used by the server, holding exactly `gmail.readonly`;
  * the **seeder client**, used by the evaluation harness, holding the destructive scope.

The seeder's scope literal deliberately does not appear anywhere in this package - it
lives in `mailweave_harness.scopes`, and a CI sweep fails the build if it ever appears
here. That is what makes SEC-03's isolation structural rather than a matter of care.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from mailweave.constants import SERVER_SCOPES
from mailweave.errors import ConfigError


class ClientRole(StrEnum):
    READ = "read"
    SEEDER = "seeder"


@dataclass(frozen=True)
class ClientDescriptor:
    """An OAuth client this process may use."""

    role: ClientRole
    client_id: str
    scopes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.role is ClientRole.SEEDER:
            raise ConfigError(
                "the server may not describe or use the seeder client; destructive "
                "capability lives in the harness package under its own OAuth client (SEC-03)"
            )
        if tuple(self.scopes) != SERVER_SCOPES:
            raise ConfigError(
                f"read client scopes must be exactly {SERVER_SCOPES}, got {self.scopes}"
            )


def read_client(client_id: str) -> ClientDescriptor:
    """The only client the server process is allowed to construct."""
    return ClientDescriptor(role=ClientRole.READ, client_id=client_id, scopes=SERVER_SCOPES)
