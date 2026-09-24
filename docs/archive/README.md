# Archive

Superseded documents, kept for the research trail.

## ARCHITECTURE_DECISION_v0_superseded.md

Written 2026-08-30 under a misreading of "loop engineering." It scoped MailWeave to
the *smallest coherent architecture that can test the thesis* and deferred semantic
retrieval, structural retrieval, reranking and freshness mitigation behind
benchmark-gated future loops.

Superseded by `docs/SCOPE_CORRECTION.md`, which establishes that the build target is
the complete product. Its factual reasoning (Gmail primitives, MCP constraints,
map-carrier response shape, invariant enforcement mechanics) remains sound and is
carried forward into the replacement `docs/ARCHITECTURE_DECISION.md`. Its *scope
verdicts* — the Chosen/Deferred/Experimental/Rejected allocation — do not apply.
