"""The bounded seeder: the foundation later measurement cannot proceed without.

Five things, and deliberately not a sixth:

1. `corpus.generate` - deterministic synthetic Gmail corpus generation, seeded RNG,
   reproducible ids and dates;
2. `manifest` - a manifest and answer key per corpus, written at generation time;
3. `substrate.seed` / `substrate.verify` / `substrate.cleanup` - verification that what was
   inserted is what the API returns, and removal that is driven from the insert results;
4. `substrate.settle` - EP §3.6's corpus settle gate, and `corpus.generate`'s regeneration
   contract: the same seed reproduces the same corpus;
5. `metrics` - the scoring primitives of EP §6, callable and unit-tested.

**Not here: the F1-F29 case content.** Each later milestone adds the families it needs - M2
the Gmail families, M4 Drive's, M5 Slack's and the cross-source ones. The foundation is built
once; the corpora grow with the sources. Building the families now would be building the
thing the measurement is supposed to be free to change.
"""

from __future__ import annotations
