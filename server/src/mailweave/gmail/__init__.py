"""The Gmail client layer (WS-02).

Four id-yielding endpoints plus `getProfile`, over `httpx`, on top of the foundation's
`RecordingListTransport` seam. Nothing here decides *what* to retrieve: the ladder, the
rungs, ranking and escalation policy are later workstreams, and a transport that knew about
them would be a transport a reviewer of the ladder never reads.
"""

from mailweave.gmail.client import (
    API_ROOT,
    THREAD_MAP_HEADERS,
    GmailClient,
    HistoryRun,
    ListingRun,
    RecordedThread,
    StaticToken,
    TokenProvider,
)
from mailweave.gmail.faults import (
    RATE_LIMIT_REASONS,
    GmailAuthExpired,
    GmailFault,
    GmailRateLimited,
    GmailRequestRejected,
    GmailResponseUnexpected,
    GmailTransportFailure,
    GmailUnavailable,
)
from mailweave.gmail.meter import CallMeter, MeterReading
from mailweave.gmail.models import (
    GmailResponseMalformed,
    HistoryPage,
    HistoryRecord,
    Message,
    MessageListPage,
    MessageRef,
    Profile,
    Thread,
    parse_response,
)
from mailweave.gmail.rates import (
    ID_YIELDING_ENDPOINTS,
    PUBLISHED_PER_MINUTE_UNITS,
    PUBLISHED_QUOTA_UNITS,
    RATE_CALIBRATION,
    RATE_PROVENANCE,
    GmailEndpoint,
)
from mailweave.gmail.retry import BackoffPolicy, BackoffState

__all__ = [
    "API_ROOT",
    "ID_YIELDING_ENDPOINTS",
    "PUBLISHED_PER_MINUTE_UNITS",
    "PUBLISHED_QUOTA_UNITS",
    "RATE_CALIBRATION",
    "RATE_LIMIT_REASONS",
    "RATE_PROVENANCE",
    "THREAD_MAP_HEADERS",
    "BackoffPolicy",
    "BackoffState",
    "CallMeter",
    "GmailAuthExpired",
    "GmailClient",
    "GmailEndpoint",
    "GmailFault",
    "GmailRateLimited",
    "GmailRequestRejected",
    "GmailResponseMalformed",
    "GmailResponseUnexpected",
    "GmailTransportFailure",
    "GmailUnavailable",
    "HistoryPage",
    "HistoryRecord",
    "HistoryRun",
    "ListingRun",
    "Message",
    "MessageListPage",
    "MessageRef",
    "MeterReading",
    "Profile",
    "RecordedThread",
    "StaticToken",
    "Thread",
    "TokenProvider",
    "parse_response",
]
