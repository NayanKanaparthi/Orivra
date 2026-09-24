"""Which questions get a graph, decided before one is built.

Plan §8.2a: *the query-type selector ships in M3 so the graph is off for simple lookups from
the start*. The reason is not cost alone. A graph over an exact lookup answers a question
nobody asked - the caller named a message and got back a structure telling them who else was
on the thread - and it spends the response's character budget on that structure instead of on
the message they asked for. The host cap is fixed, so width here is depth somewhere else.

**The routing reads the parsed query, not the raw string.** A raw-substring check would fire
on a quoted phrase that merely mentions an operator and miss a spelling the parser normalises,
which is `ranking.gate._is_an_identifier_route`'s reasoning and it applies unchanged here.

**It is a floor, not a ceiling.** `GraphRoute.OFF` means *this question does not need one*, and
the caller can still ask for a graph explicitly; what the routing never does is silently build
one where it decided not to. The decision travels on the response so a reader can see which
branch ran and why, because a graph that is sometimes absent and never explains itself is
indistinguishable from one that failed to build.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from mailweave.query.analysis import ParsedQuery
from mailweave.query.operators import OperatorName

#: Operators that name **one specific thing**, so the answer is that thing and not its
#: neighbourhood. An `rfc822msgid:` lookup is the clearest case: the caller already holds the
#: identifier, and the reply tree around it is not what they asked about.
_IDENTITY_OPERATORS: frozenset[OperatorName] = frozenset({OperatorName.RFC822MSGID})

#: Below this many content terms a query is a lookup rather than a question. One term is
#: "invoice"; a decision question carries several, because it is describing a situation rather
#: than naming a thing.
_QUESTION_TERMS: int = 2


class GraphRoute(StrEnum):
    """What this query gets."""

    #: Build the graph, with person nodes: the question spans messages and the useful
    #: relations include who said what where.
    FULL = "full"
    #: Build the reply tree and thread membership, without person nodes. The question is about
    #: one conversation's shape, and joining threads through participants would be width the
    #: caller did not ask for.
    STRUCTURE_ONLY = "structure_only"
    #: Build nothing. The caller named a thing; the answer is that thing.
    OFF = "off"


@dataclass(frozen=True)
class RoutingDecision:
    """The route, and the sentence that explains it to a reader of the response."""

    route: GraphRoute
    why: str

    @property
    def build(self) -> bool:
        return self.route is not GraphRoute.OFF

    @property
    def people(self) -> bool:
        return self.route is GraphRoute.FULL


def route_for(parsed: ParsedQuery, *, requested: bool | None = None) -> RoutingDecision:
    """Decide from the parse. `requested` is the caller's explicit `graph` argument.

    An explicit request wins in both directions and says so: a caller who asked for a graph on
    an exact lookup gets one, and a caller who asked for none gets none however the query
    reads. The routing decides only where the caller expressed no preference, which is what
    makes it a default rather than a policy the caller has to work around.
    """
    if requested is False:
        return RoutingDecision(GraphRoute.OFF, "the call asked for no graph, so none was built")
    if requested is True:
        return RoutingDecision(
            GraphRoute.FULL, "the call asked for a graph, so one was built whatever the query"
        )
    named = [one for one in parsed.operators if one.name in _IDENTITY_OPERATORS]
    if named:
        return RoutingDecision(
            GraphRoute.OFF,
            f"this query names a specific message by {named[0].name.value}, so the answer is "
            "that message. A graph here would spend the response's budget describing a "
            "neighbourhood nobody asked about",
        )
    if len(parsed.search_terms) < _QUESTION_TERMS:
        return RoutingDecision(
            GraphRoute.STRUCTURE_ONLY,
            f"this query carries {len(parsed.search_terms)} content term(s), which reads as a "
            "lookup rather than a question. The reply tree is built because a thread's shape "
            "is part of reading it; participants are not, because nothing here asked to join "
            "threads through people",
        )
    return RoutingDecision(
        GraphRoute.FULL,
        f"this query carries {len(parsed.search_terms)} content terms across no single named "
        "message, which is the shape a graph is for",
    )


__all__ = ["GraphRoute", "RoutingDecision", "route_for"]
