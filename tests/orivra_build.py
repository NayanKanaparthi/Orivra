"""Builders for Orivra contract tests: the smallest valid object of each kind.

Every test in `test_orivra_contracts.py` works by taking one of these and breaking exactly
one thing, so what a test asserts is visible in its own diff rather than in a fixture file.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from mailweave.content.annotate import AnnotatedBody, AnnotatedSpan, SpanClass
from mailweave.envelope.reasons import GmailQueryMatch, RungId
from mailweave.envelope.vocab import Depth, Role
from orivra.contracts import (
    ClauseClearance,
    Confidence,
    ConnectorId,
    ContentVersion,
    DerivationMethod,
    DeterministicKey,
    Entity,
    EvidenceEdge,
    EvidenceNode,
    FreshnessState,
    FreshnessStatus,
    NodeKind,
    PermissionContext,
    RefKind,
    Relation,
    SourceReference,
    Span,
    StatedAssertionCheck,
    TargetResolution,
    requirements_of,
)

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
WIDER = "https://mail.google.com/"

#: The worked example every test in this module reuses: message A states that it supersedes
#: a draft, message B is that draft.
TEXT_A = "This supersedes the July 3 pricing draft."
CUE = "supersedes the July 3 pricing draft"
CUE_START = TEXT_A.index(CUE)
CUE_END = CUE_START + len(CUE)
TEXT_B = "The July 3 pricing draft is attached."
NODE_A = "gmail/message/mA"
NODE_B = "gmail/message/mB"


def permission(*scopes: str) -> PermissionContext:
    return PermissionContext(
        connector=ConnectorId.GMAIL,
        principal="account-digest",
        scope_set=tuple(sorted(scopes or (SCOPE,))),
        observed_at=NOW,
    )


def reference(native_id: str, *, kind: RefKind = RefKind.MESSAGE, **kwargs: Any) -> SourceReference:
    fields: dict[str, Any] = {
        "connector": ConnectorId.GMAIL,
        "account": "account-digest",
        "kind": kind,
        "native_id": native_id,
        "version": ContentVersion(connector=ConnectorId.GMAIL, native_id=native_id, revision="7"),
        "permission": permission(),
    }
    fields.update(kwargs)
    return SourceReference(**fields)


def fresh() -> FreshnessStatus:
    return FreshnessStatus(verified_at=NOW, state=FreshnessState.FRESH)


def degraded(state: FreshnessState = FreshnessState.STALE) -> FreshnessStatus:
    return FreshnessStatus(verified_at=NOW, state=state, why="the change feed refused the marker")


def node(native_id: str = "mA", content: str | None = TEXT_A, **kwargs: Any) -> EvidenceNode:
    fields: dict[str, Any] = {
        "node_id": f"gmail/message/{native_id}",
        "ref": reference(native_id),
        "kind": NodeKind.MESSAGE,
        "role": Role.MATCHED,
        "reason": GmailQueryMatch(query="after:2026/09/01", rung=RungId.L1),
        "depth": Depth.BODY_CLEAN,
        "content": content,
        "freshness": fresh(),
    }
    fields.update(kwargs)
    return EvidenceNode(**fields)


def span(
    node_id: str = NODE_A, start: int = CUE_START, end: int = CUE_END, text: str = CUE
) -> Span:
    return Span(node_id=node_id, start=start, end=end, text=text)


def method(name: str = "rule/explicit_supersede", version: str = "1") -> DerivationMethod:
    return DerivationMethod(name=name, version=version)


def stated_check(**kwargs: Any) -> StatedAssertionCheck:
    fields: dict[str, Any] = {
        "span": span(),
        "target": TargetResolution(
            resolved_to=NODE_B,
            considered=(NODE_B,),
            referring_text="the July 3 pricing draft",
        ),
        "clearance": ClauseClearance(
            clause=TEXT_A, language="en", span_class_signals=("no_structural_signal",)
        ),
        "asserted_by": NODE_A,
    }
    fields.update(kwargs)
    return StatedAssertionCheck(**fields)


def edge(**kwargs: Any) -> EvidenceEdge:
    """One valid edge. `requires` is **derived from `support`** unless a test overrides it,
    which is how the model itself builds a conjunction - a builder that typed one by hand
    would be typing the thing the validator re-derives."""
    fields: dict[str, Any] = {
        "edge_id": "e1",
        "source": NODE_A,
        "target": NODE_B,
        "relation": Relation.REPLY_TO,
        "support": (reference("mA"), reference("mB")),
        "method": method("metadata/reply_to"),
        "freshness": fresh(),
    }
    fields.update(kwargs)
    fields.setdefault("requires", requirements_of(fields["support"]))
    return EvidenceEdge(**fields)


def drive_reference(native_id: str, *, principal: str = "drive-account") -> SourceReference:
    """One Drive file, under its own grant. The second half of a cross-source edge."""
    return SourceReference(
        connector=ConnectorId.DRIVE,
        account="drive-account-digest",
        kind=RefKind.FILE,
        native_id=native_id,
        version=ContentVersion(connector=ConnectorId.DRIVE, native_id=native_id, revision="3"),
        permission=PermissionContext(
            connector=ConnectorId.DRIVE,
            principal=principal,
            scope_set=("https://www.googleapis.com/auth/drive.readonly",),
            observed_at=NOW,
        ),
    )


def slack_reference(native_id: str, *, principal: str = "slack-member") -> SourceReference:
    """One Slack message, under a workspace grant with a capability fact."""
    return SourceReference(
        connector=ConnectorId.SLACK,
        account="slack-workspace-digest",
        kind=RefKind.SLACK_MESSAGE,
        native_id=native_id,
        version=ContentVersion(connector=ConnectorId.SLACK, native_id=native_id, revision=None),
        permission=PermissionContext(
            connector=ConnectorId.SLACK,
            principal=principal,
            scope_set=("search:read", "users:read.email"),
            capability=("tier=enterprise", "token=user"),
            observed_at=NOW,
        ),
    )


def confidence(value: float = 0.6) -> Confidence:
    return Confidence(method=method(), value=value, basis="a verbatim supersede cue")


def body(text: str = TEXT_A, quoted_from: int | None = None) -> AnnotatedBody:
    """One annotated body. `quoted_from` marks everything from that offset as quoted."""
    spans: tuple[AnnotatedSpan, ...]
    if quoted_from is None:
        spans = (AnnotatedSpan(0, len(text), SpanClass.ORIGINAL, "no_structural_signal"),)
    else:
        spans = (
            AnnotatedSpan(0, quoted_from, SpanClass.ORIGINAL, "no_structural_signal"),
            AnnotatedSpan(quoted_from, len(text), SpanClass.QUOTED, "client_attribution"),
        )
    return AnnotatedBody(text=text, spans=spans)


def entity(*keys: DeterministicKey) -> Entity:
    chosen = keys or (
        DeterministicKey(connector=ConnectorId.GMAIL, kind="address", value="alex@company.com"),
    )
    digest = hashlib.sha256("\x1e".join(sorted(key.digest for key in chosen)).encode()).hexdigest()[
        :16
    ]
    return Entity(entity_id=f"entity/{digest}", keys=chosen)
