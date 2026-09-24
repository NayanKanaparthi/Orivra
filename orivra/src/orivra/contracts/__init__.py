"""Orivra's source-independent contracts (plan §4).

Import from here rather than from the modules: the split between `refs`, `nodes`, `edges`,
`entities`, `omission`, `graph` and `trace` is an import-order convenience, and a caller that
depends on which file a model lives in will be broken by the next reorganisation.
"""

from orivra.contracts.edges import (
    ClauseClearance,
    Confidence,
    EvidenceEdge,
    StatedAssertionCheck,
    TargetResolution,
)
from orivra.contracts.entities import DeterministicKey, Entity, EntityCandidate
from orivra.contracts.graph import DEFAULT_TTL, QueryGraph
from orivra.contracts.nodes import (
    CONTAINERS,
    DerivationMethod,
    EvidenceNode,
    Span,
    Timestamps,
)
from orivra.contracts.omission import (
    Dimension,
    ExpansionHandle,
    Granularity,
    OmissionRecord,
    OrivraToolName,
    permission_safe_omission,
)
from orivra.contracts.permission import (
    AccessProbe,
    PermissionRequirement,
    Release,
    release,
    requirement_digest,
    requirements_of,
)
from orivra.contracts.reasons import (
    ALL_GRAPH_REASON_KINDS,
    GraphReason,
    ParticipantIn,
)
from orivra.contracts.refs import (
    DIGEST_CHARS,
    ChangeMarker,
    ContentVersion,
    FreshnessStatus,
    Frozen,
    PermissionContext,
    SourceReference,
)
from orivra.contracts.trace import (
    REDACTION_POLICY,
    EntitySpend,
    GraphSpend,
    RetrievalTrace,
    SourceSpend,
)
from orivra.contracts.vocab import (
    Assertion,
    CandidateBasis,
    CandidateStatus,
    ConnectorId,
    EdgeOrigin,
    FreshnessState,
    GraphReasonKind,
    Namespace,
    NodeKind,
    OmissionCause,
    Origin,
    RefKind,
    Relation,
    SourceState,
)

__all__ = [
    "ALL_GRAPH_REASON_KINDS",
    "CONTAINERS",
    "DEFAULT_TTL",
    "DIGEST_CHARS",
    "REDACTION_POLICY",
    "AccessProbe",
    "Assertion",
    "CandidateBasis",
    "CandidateStatus",
    "ChangeMarker",
    "ClauseClearance",
    "Confidence",
    "ConnectorId",
    "ContentVersion",
    "DerivationMethod",
    "DeterministicKey",
    "Dimension",
    "EdgeOrigin",
    "Entity",
    "EntityCandidate",
    "EntitySpend",
    "EvidenceEdge",
    "EvidenceNode",
    "ExpansionHandle",
    "FreshnessState",
    "FreshnessStatus",
    "Frozen",
    "Granularity",
    "GraphReason",
    "GraphReasonKind",
    "GraphSpend",
    "Namespace",
    "NodeKind",
    "OmissionCause",
    "OmissionRecord",
    "Origin",
    "OrivraToolName",
    "ParticipantIn",
    "PermissionContext",
    "PermissionRequirement",
    "QueryGraph",
    "RefKind",
    "Relation",
    "Release",
    "RetrievalTrace",
    "SourceReference",
    "SourceSpend",
    "SourceState",
    "Span",
    "StatedAssertionCheck",
    "TargetResolution",
    "Timestamps",
    "permission_safe_omission",
    "release",
    "requirement_digest",
    "requirements_of",
]
