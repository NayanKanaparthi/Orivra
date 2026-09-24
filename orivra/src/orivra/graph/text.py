"""The three relation families a message's *text* supports, assembled once.

`observed.py` draws edges from the response's own metadata - headers, thread membership,
participants. Everything here reads the message body instead, and the three families it
produces are deliberately separate things:

* **source-stated** (`obs.said.supersedes_stated`): a human wrote the sentence, and the four
  recognition gates - span, clause, target, asserted-by - agreed it is a performed assertion
  about a message this graph holds. Spans and a `StatedAssertionCheck`, never a confidence:
  the source stated it, so there is no estimate to report.
* **source-stated** (`obs.said.links_to`): a URL in the body that resolves to a Gmail message
  or thread this graph holds. Unresolved URLs are carried out of here as themselves, not
  fabricated as endpoints.
* **inferred** (`inf.graph.supersedes_potential`): built only from the one refusal that is an
  ambiguity rather than a denial, with a confidence and the basis for it.

**One assembly, used by both paths.** `build_query_graph` calls this for the ask response, and
`orivra_expand` calls it again over the merged node set. Two copies of this wiring would drift,
and the drift a caller would see is an expansion whose new messages carry metadata edges and
no others - a graph whose relationship vocabulary depends on which call produced a node.

Running it over the *union* of held and recovered nodes is the point, not an accident: an
assertion this server refused at build time because its target was outside the response can
become resolvable once the expansion brings that target in. The merge deduplicates, so an
edge already held costs nothing and an edge newly earned appears.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from orivra.contracts import EvidenceEdge, EvidenceNode, FreshnessStatus, SourceReference
from orivra.graph.inferred import InferredEdges, inferred_edges
from orivra.graph.links import LinkEdges, link_edges
from orivra.graph.stated import StatedEdges, stated_edges


@dataclass(frozen=True)
class TextEdges:
    """What the bodies supported, kept in its families rather than flattened.

    Flattened is what a graph holds; families are what a reader needs, because "the source
    said this" and "this server concluded this" are different claims and a single tuple cannot
    say which is which without re-reading every relation's namespace.
    """

    stated: StatedEdges = field(default_factory=StatedEdges)
    inferred: InferredEdges = field(default_factory=InferredEdges)
    links: LinkEdges = field(default_factory=LinkEdges)

    @property
    def edges(self) -> tuple[EvidenceEdge, ...]:
        """All three, in the order a reader should meet them: stated, then links, then inferred.

        Order matters only for pruning, which takes from the tail - so the inferred family,
        the one this server concluded rather than read, is the first to go.
        """
        return (*self.stated.edges, *self.links.edges, *self.inferred.edges)

    def unresolved_links(self) -> tuple[dict[str, str], ...]:
        return tuple(self.links.payload())


def text_edges(
    nodes: Sequence[EvidenceNode],
    *,
    reference_of: dict[str, SourceReference],
    freshness: FreshnessStatus,
) -> TextEdges:
    """Run the gates over `nodes`, and hand back the three families they earned.

    `reference_of` must cover every node an edge could land on, which is why both callers pass
    the whole node set rather than the new part of it: a target missing from the map is a
    target this server cannot cite, and an uncitable edge is one this package does not draw.
    """
    stated = stated_edges(nodes, reference_of=reference_of, freshness=freshness)
    inferred = inferred_edges(stated.refusals, reference_of=reference_of, freshness=freshness)
    links = link_edges(nodes, reference_of=reference_of, freshness=freshness)
    return TextEdges(stated=stated, inferred=inferred, links=links)


__all__ = ["TextEdges", "text_edges"]
