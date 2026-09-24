"""Repository tooling: CI guards and rubric status.

This package is never importable from `server/**`; the forbidden-import guard enforces
that, so nothing the server runs can reach repo tooling or, through it, ground truth.
"""
