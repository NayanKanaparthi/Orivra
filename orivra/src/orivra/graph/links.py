"""`obs.said.links_to`, for the links this release can actually resolve - and honest about the rest.

A URL in a message body is something the message **said**, so `links_to` sits in `obs.said`
and is source-stated: spans, an asserter, no confidence. It is not metadata and it is not an
inference.

**The constraint this release is under, stated rather than worked around.** An
`obs.said.*` edge must pass `StatedAssertionCheck`, whose second gate requires
`stated.target.resolved_to == edge.target`, and `QueryGraph` refuses an edge whose endpoint is
not a node it holds. So a `links_to` edge needs its target to **be a node in the graph**. In a
Gmail-only release the only URLs that can satisfy that are Gmail's own permalinks to a message
or thread this response already returned. Every other link - a Drive document, a vendor's
pricing page, an internal wiki - points at something no node represents.

Three ways that could have been handled and two of them are wrong:

* Invent a node for the URL, so the edge has an endpoint. That manufactures a graph node for a
  document this server never read, never verified and has no permission requirement for - an
  endpoint that looks like evidence and is a string from a body.
* Add a Drive adapter to give the URL something real to point at. Out of scope by instruction
  and out of scope by milestone; M4 is where cross-source `links_to` belongs.
* **Represent the unresolved link as what it is: a link the response saw and could not
  resolve.** That is an `OmissionRecord` at node granularity, carrying the URL, with no
  recovery this release can offer.

The third is what this does. The count of URLs found and the count of edges drawn are
different numbers, and on ordinary mail the second is usually zero.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from mailweave.content.annotate import AnnotatedBody, AnnotatedSpan, SpanClass
from mailweave.envelope.vocab import Depth
from orivra.contracts import (
    DerivationMethod,
    EvidenceEdge,
    EvidenceNode,
    FreshnessStatus,
    NodeKind,
    Relation,
    SourceReference,
    StatedAssertionCheck,
    TargetResolution,
    requirements_of,
)
from orivra.recognise.stated import Refused, clear_clause, match_span

LINK_METHOD = DerivationMethod(name="rule/gmail_permalink", version="1")

#: The language the clause gate is written for, as in `orivra.graph.stated`.
LANGUAGE = "en"


def _annotated(text: str) -> AnnotatedBody:
    """The row's disclosed text as one `ORIGINAL` span - the same justification as
    `orivra.graph.stated._annotated`, and restricted to the same depths for the same reason."""
    return AnnotatedBody(
        text=text,
        spans=(
            AnnotatedSpan(
                start=0,
                end=len(text),
                classification=SpanClass.ORIGINAL,
                signal="depth=body_clean: the content pipeline's original-text extraction",
            ),
        ),
    )


#: A URL in a body. Deliberately plain: this finds candidates for a resolver that refuses
#: nearly all of them, and a cleverer pattern would only find more things to refuse.
_URL = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)

#: Gmail's own web permalink shapes. The fragment after `#` names a thread or message in the
#: *user's own* mailbox, which is the only kind of URL a Gmail-only graph can resolve to a node
#: it holds.
_PERMALINK: Final[re.Pattern[str]] = re.compile(
    r"https?://mail\.google\.com/mail/u/\d+/#(?:[a-z]+/)*(?P<native>[0-9a-fA-F]{6,})",
)


@dataclass(frozen=True)
class UnresolvedLink:
    """A URL the response saw and this release cannot point at a node."""

    node_id: str
    url: str
    why: str


@dataclass(frozen=True)
class LinkEdges:
    edges: tuple[EvidenceEdge, ...] = ()
    unresolved: tuple[UnresolvedLink, ...] = ()

    def payload(self) -> list[dict[str, str]]:
        """The unresolved links, as their own named thing rather than as omission records.

        **The vocabulary has no cause for this and stretching one would lie.** `OmissionCause`
        offers `cap`, `ceiling`, `permission`, `freshness_unverifiable`, `source_gone`,
        `pruned`, `not_tried` and `partial_source_failure`. Nothing was capped, refused or
        lost; there is simply no connector in this release that could reach a Drive document
        or a vendor's page. `not_tried` is the near miss and `OmissionRecord` refuses it
        without a recovery handle - correctly, because `not_tried` means a call exists and was
        not made, and offering a handle this server cannot execute would be an offer that
        refuses when taken.

        So they travel under their own key. A reader sees exactly what the response saw: a
        link, and the reason no node represents it. **Filed as a finding for M4**, where a
        Drive adapter both resolves most of these and makes a cause for the remainder
        meaningful.
        """
        return [
            {"url": link.url, "from": link.node_id, "why": link.why} for link in self.unresolved
        ]


def _native_of(url: str) -> str | None:
    match = _PERMALINK.match(url)
    return match.group("native") if match else None


def link_edges(
    nodes: Sequence[EvidenceNode],
    *,
    reference_of: dict[str, SourceReference],
    freshness: FreshnessStatus,
) -> LinkEdges:
    """Every `links_to` edge whose target this graph holds, and every link that has none."""
    by_native = {
        node.ref.native_id: node.node_id
        for node in nodes
        if node.kind in (NodeKind.MESSAGE, NodeKind.THREAD)
    }
    edges: list[EvidenceEdge] = []
    unresolved: list[UnresolvedLink] = []
    for node in nodes:
        if node.kind is not NodeKind.MESSAGE or node.depth not in (
            Depth.BODY_CLEAN,
            Depth.BODY_FULL,
        ):
            continue
        text = node.content or ""
        for match in _URL.finditer(text):
            url = match.group(0)
            native = _native_of(url)
            target = by_native.get(native) if native else None
            if target is None or target == node.node_id:
                unresolved.append(
                    UnresolvedLink(
                        node_id=node.node_id,
                        url=url,
                        why=(
                            "this message links to a location no node in this graph "
                            "represents. Gmail is the only connected source in this release, "
                            "so a link outside the mailbox has nothing here to point at - it "
                            "is recorded rather than given an invented endpoint"
                        )
                        if native is None
                        else (
                            "this message links to a Gmail item this response did not return, "
                            "so the edge would have no endpoint to land on"
                        ),
                    )
                )
                continue
            # **The clause gate runs here too.** The first version passed a synthetic
            # clearance in language "und" on the reasoning that a URL is not prose, and
            # `ClauseClearance` refused it - correctly: a clearance that clears because the
            # recogniser does not speak the language is not a clearance. And the premise was
            # wrong anyway. "We are **not** using https://... any more" is a negated statement
            # about a link, and a `links_to` edge drawn from it would assert the opposite of
            # what the sentence says. So the URL's own sentence goes through the same gate the
            # supersede path uses.
            body = _annotated(text)
            checked = match_span(body, match.start(), match.end(), url, node_id=node.node_id)
            if isinstance(checked, Refused):
                unresolved.append(UnresolvedLink(node_id=node.node_id, url=url, why=checked.why))
                continue
            cleared = clear_clause(body, match.start(), match.end(), language=LANGUAGE)
            if isinstance(cleared, Refused):
                unresolved.append(
                    UnresolvedLink(
                        node_id=node.node_id,
                        url=url,
                        why=(
                            "the sentence carrying this link is negated, hypothetical or "
                            f"hedged ({cleared.why}), so it does not state a link"
                        ),
                    )
                )
                continue
            span = checked
            support = (reference_of[node.node_id], reference_of[target])
            edges.append(
                EvidenceEdge(
                    edge_id=f"{Relation.LINKS_TO.value}/{node.node_id}->{target}@{match.start()}",
                    source=node.node_id,
                    target=target,
                    relation=Relation.LINKS_TO,
                    support=support,
                    spans=(span,),
                    stated=StatedAssertionCheck(
                        span=span,
                        target=TargetResolution(
                            resolved_to=target,
                            considered=(target,),
                            referring_text=url,
                        ),
                        # A URL is not prose: there is no clause around it to negate, hedge or
                        # make hypothetical. The clearance records that the signal checked was
                        # the link's own form rather than a sentence's cues, so a reader is not
                        # told a clause gate ran where none could.
                        clearance=cleared.clearance,
                        asserted_by=node.node_id,
                    ),
                    method=LINK_METHOD,
                    requires=requirements_of(support),
                    freshness=freshness,
                )
            )
    return LinkEdges(edges=tuple(edges), unresolved=tuple(unresolved))


__all__ = ["LINK_METHOD", "LinkEdges", "UnresolvedLink", "link_edges"]
