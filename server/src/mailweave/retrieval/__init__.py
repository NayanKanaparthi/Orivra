"""Retrieval: the transport seam (WS-02's receiving end) and the lexical ladder (WS-04).

`transport` holds the *shape* a Gmail client must have, so that a rung cannot be written
which fetches message IDs without recording them (R-ORCH-001, R-ARCH-005). `GmailClient`
now supplies that shape - which is why this module exports the seam and **not** the ladder:
`mailweave.gmail.client` imports `transport`, so re-exporting `ladder` or `assemble` here
would close an import cycle through the client they call. The ladder is imported from its
own module, `mailweave.retrieval.ladder`, exactly as the client is from `mailweave.gmail.client`.

The WS-04 modules beside this one:

  * `ladder` - the five lexical rungs of AD A.7 (L0, L1, L1b, L2, L3) as plans plus a runner;
  * `signals` - the model-free sufficiency signals of A.8, including A.8a's closed
    three-branch `exact_signal_match`;
  * `assemble` - the narrowest assembly of a run into a response envelope.

Nothing in this package embeds, scores or calls a model: `generative_llm_calls = 0` is a
hard constant (AD D.8) and the CI import sweep enforces it.
"""

from __future__ import annotations

from mailweave.retrieval.transport import (
    FetchHistoryPage,
    FetchListPage,
    RecordedListing,
    RecordingListTransport,
)

__all__ = [
    "FetchHistoryPage",
    "FetchListPage",
    "RecordedListing",
    "RecordingListTransport",
]
