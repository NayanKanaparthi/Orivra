"""MailWeave evaluation harness.

A separate package with a separate OAuth client, separate scopes and its own account
pinning (AD B.9, RR SEC-03). The server never imports this package; an import contract in
CI enforces that direction, because destructive capability that can be imported is
destructive capability that can be reached.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
