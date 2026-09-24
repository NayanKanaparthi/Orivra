"""The query-time context graph (plan §4.4-§4.8, M3).

Built for one question and discarded. What survives a query is the bounded cache of things
that are expensive and stable; the graph itself is not cached, and there is no persistent
whole-mailbox graph anywhere in this package.

The contracts in `orivra.contracts` decide what a node and an edge may be. This package
decides which ones a Gmail response produces, and nothing here may loosen a contract: when
a rule refuses an edge, the edge is not emitted and - where its absence is a fact a reader
would otherwise assume away - an `OmissionRecord` says so.
"""

from orivra.graph.observed import (
    OBSERVED_METHODS,
    ObservedEdges,
    observed_edges,
)

__all__ = ["OBSERVED_METHODS", "ObservedEdges", "observed_edges"]
