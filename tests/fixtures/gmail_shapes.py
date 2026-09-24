"""Recorded Gmail response shapes, and a fake transport that replays them.

**Provenance is part of the fixture.** Every shape below carries one of two markers, and the
distinction is the point:

  * `[DISCOVERY]` - the field, its type and its presence are taken from the Gmail API v1
    discovery document and the matching reference page. These are shapes, not guesses.
  * `[PREFLIGHT PF-n]` - the *presence* of the field in this particular response depends on
    something no document settles, and a probe is registered to find out. A fixture built on
    one of these is a fixture of the API we imagined, so it is labelled rather than trusted,
    and the tests that depend on it say which way they would break.

No fixture here contains real mail. Addresses use the reserved `.example` / `.invalid` TLDs
(RFC 2606/6761), subjects and snippets are invented, and message ids are the short synthetic
ids the rest of this suite uses.

The fake is an `httpx.MockTransport` **behind the allowlist transport**, not a stub of the
client's own methods. That matters: a test that fakes `GmailClient.get_thread` proves nothing
about URL construction, the `metadataHeaders` repeated key, the bearer header, the retry
ladder or the egress check, all of which are where the defects in a transport actually live.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

# --- messages.list -----------------------------------------------------------------------
#
# [DISCOVERY] `ListMessagesResponse`: `messages[]` of `Message`, `nextPageToken`,
# `resultSizeEstimate`. The reference page states that the rows carry **only** `id` and
# `threadId`, which is why no other field appears here.

MESSAGES_LIST_PAGE_1: dict[str, Any] = {
    "messages": [
        {"id": "18f0a1", "threadId": "t100"},
        {"id": "18f0a2", "threadId": "t100"},
        {"id": "18f0a3", "threadId": "t200"},
    ],
    "nextPageToken": "07840618541123456789",
    "resultSizeEstimate": 42,
}

MESSAGES_LIST_PAGE_2: dict[str, Any] = {
    "messages": [{"id": "18f0a4", "threadId": "t300"}],
    "resultSizeEstimate": 42,
}

MESSAGES_LIST_EMPTY: dict[str, Any] = {"resultSizeEstimate": 0}
"""[DISCOVERY] An empty result omits `messages` entirely rather than sending `[]`.

Modelled with a default of `()` for exactly this reason. If Gmail in fact sends `[]` the
model accepts that too, so this fixture asserts the harder of the two shapes.
"""

# --- threads.get -------------------------------------------------------------------------
#
# [DISCOVERY] `Thread`: `id`, `snippet`, `historyId`, `messages[]` of `Message`.
# [PREFLIGHT PF-2] Whether `format=metadata` returns a per-message `snippet` and
# `internalDate` at all. The Format enum's own text says METADATA returns "only email message
# ID, labels, and email headers" and does not mention either; AD D.5's pool design assumes
# both. `THREAD_METADATA` is the optimistic shape and `THREAD_METADATA_NO_INTERNAL_DATE` is
# the pessimistic one, and both are tested, because which of them is real is unknown.
# [PREFLIGHT PF-2] Whether `metadataHeaders` honours `References` and `In-Reply-To`.

THREAD_METADATA: dict[str, Any] = {
    "id": "t100",
    "historyId": "99120034",
    "snippet": "quarterly planning",
    "messages": [
        {
            "id": "18f0a1",
            "threadId": "t100",
            "labelIds": ["INBOX", "IMPORTANT"],
            "snippet": "opening note",
            "historyId": "99120030",
            "internalDate": "1735689600000",
            "payload": {
                "partId": "",
                "mimeType": "text/plain",
                "headers": [
                    {"name": "Message-ID", "value": "<a1@mail.example>"},
                    {"name": "Subject", "value": "Quarterly planning"},
                    {"name": "From", "value": "Ana <ana@one.example>"},
                    {"name": "Date", "value": "Wed, 1 Jan 2025 00:00:00 +0000"},
                ],
            },
        },
        {
            "id": "18f0a2",
            "threadId": "t100",
            "labelIds": ["INBOX"],
            "snippet": "reply",
            "historyId": "99120034",
            "internalDate": "1735693200000",
            "payload": {
                "partId": "",
                "mimeType": "text/plain",
                "headers": [
                    {"name": "Message-ID", "value": "<a2@mail.example>"},
                    {"name": "In-Reply-To", "value": "<a1@mail.example>"},
                    {"name": "References", "value": "<a1@mail.example>"},
                    {"name": "Subject", "value": "Re: Quarterly planning"},
                    {"name": "From", "value": "Bo <bo@two.example>"},
                ],
            },
        },
    ],
}

THREAD_METADATA_NO_INTERNAL_DATE: dict[str, Any] = {
    "id": "t100",
    "historyId": "99120034",
    "messages": [
        {"id": "18f0a1", "threadId": "t100", "labelIds": ["INBOX"]},
        {"id": "18f0a2", "threadId": "t100", "labelIds": ["INBOX"]},
    ],
}
"""[PREFLIGHT PF-2] The shape if METADATA means what the Format enum's text says.

If this is what a real mailbox returns, no chronological order can be derived from a thread
map, `positions` and `internalDate` cannot be sealed, and AD A.2 step 4's "temporal order"
comes from `format=full` at the same 40 u - a bytes and latency change, not a quota one.
"""

THREAD_OUT_OF_ARRAY_ORDER: dict[str, Any] = {
    "id": "t400",
    "historyId": "99120040",
    "messages": [
        {"id": "m-later", "threadId": "t400", "internalDate": "1735693200000"},
        {"id": "m-earlier", "threadId": "t400", "internalDate": "1735689600000"},
    ],
}
"""[DISCOVERY] Array order is not documented to be chronological order.

AD A.2 requires strict `internalDate` ordering, so this fixture exists to prove the client
derives positions from the timestamp rather than from the array index. If Gmail always
happens to return chronological order, this test still passes and costs nothing; if it ever
does not, the behaviour is already right.
"""

# --- history.list ------------------------------------------------------------------------
#
# [DISCOVERY] `ListHistoryResponse`: `history[]`, `nextPageToken`, `historyId`. Each
# `history[]` record carries `id` plus optional `messages`, `messagesAdded`,
# `messagesDeleted`, `labelsAdded`, `labelsRemoved`. AD D.9 states that
# `messagesAdded[].message` carries id / threadId / labelIds and not headers or bodies.

HISTORY_PAGE: dict[str, Any] = {
    "history": [
        {
            "id": "99120050",
            "messagesAdded": [
                {"message": {"id": "18f0b1", "threadId": "t500", "labelIds": ["INBOX", "UNREAD"]}}
            ],
        },
        {
            "id": "99120051",
            "messagesAdded": [
                {"message": {"id": "18f0b2", "threadId": "t500", "labelIds": ["INBOX"]}},
                {"message": {"id": "18f0b1", "threadId": "t500", "labelIds": ["INBOX"]}},
            ],
        },
    ],
    "historyId": "99120051",
}
"""The duplicate `18f0b1` is deliberate: one message can be added, laballed and re-reported
inside a single history window. [PREFLIGHT] Whether Gmail really repeats an id this way is
not documented either direction; the client deduplicates because the seal takes a per-id map
and a repeated key is not a second message."""

HISTORY_EXPIRED_404: dict[str, Any] = {
    "error": {
        "code": 404,
        "message": "Requested entity was not found.",
        "errors": [{"domain": "global", "reason": "notFound", "message": "Not Found"}],
        "status": "NOT_FOUND",
    }
}
"""[VERIFIED RO F6] An expired `startHistoryId` 404s. AD D.9 makes that a declared
re-baseline, not an error."""

# --- messages.get ------------------------------------------------------------------------

MESSAGE_FULL: dict[str, Any] = {
    "id": "18f0a1",
    "threadId": "t100",
    "labelIds": ["INBOX"],
    "snippet": "opening note",
    "historyId": "99120030",
    "internalDate": "1735689600000",
    "sizeEstimate": 2048,
    "payload": {
        "partId": "",
        "mimeType": "text/plain",
        "headers": [{"name": "Subject", "value": "Quarterly planning"}],
        "body": {"size": 11, "data": "b3BlbmluZyBub3Rl"},
    },
}

# --- getProfile --------------------------------------------------------------------------

PROFILE: dict[str, Any] = {
    "emailAddress": "owner@personal.example",
    "messagesTotal": 51234,
    "threadsTotal": 20981,
    "historyId": "99120051",
}

SEED_PROFILE: dict[str, Any] = {
    "emailAddress": "seed@harness.example",
    "messagesTotal": 412,
    "threadsTotal": 190,
    "historyId": "1200",
}

# --- error envelopes ---------------------------------------------------------------------
#
# [DISCOVERY] The Google JSON error envelope: `error{code, message, errors[{domain, reason,
# message}], status}`. [PREFLIGHT PF-3] Which status a Gmail per-user rate limit actually
# arrives as - 429, or 403 with `userRateLimitExceeded` - is what PF-3 records. Both are
# handled and both are fixtured, because guessing one would leave the other untested.


def error_body(code: int, reason: str, message: str = "quota") -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "errors": [{"domain": "usageLimits", "reason": reason, "message": message}],
            "status": "RESOURCE_EXHAUSTED",
        }
    }


#: An error whose `message` is a sentence of mail-shaped text. Used to prove that no part of
#: a remote body reaches a MailWeave error string (AD A.11).
LEAKY_ERROR_BODY: dict[str, Any] = {
    "error": {
        "code": 400,
        "message": 'Invalid query: from:ana@one.example "the NDA we discussed on Tuesday"',
        "errors": [
            {
                "domain": "global",
                "reason": "invalidArgument",
                "message": 'Invalid query: "the NDA we discussed on Tuesday"',
            }
        ],
        "status": "INVALID_ARGUMENT",
    }
}


# --- the fake transport ------------------------------------------------------------------

Responder = Callable[[httpx.Request], httpx.Response]


def json_response(status: int, body: Any, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        status,
        content=json.dumps(body).encode("utf-8"),
        headers={"content-type": "application/json", **(headers or {})},
    )


@dataclass
class FakeGmail:
    """Replays queued responses per endpoint key, recording every request it received.

    The key is the endpoint's last path segment family - `messages`, `messages/<id>`,
    `threads`, `history`, `profile` - matched from the request path, so a test says which
    call it is programming without restating a URL.
    """

    queues: dict[str, deque[httpx.Response]] = field(default_factory=lambda: defaultdict(deque))
    requests: list[httpx.Request] = field(default_factory=list)

    def queue(self, key: str, *responses: httpx.Response) -> FakeGmail:
        for response in responses:
            self.queues[key].append(response)
        return self

    @staticmethod
    def key_for(path: str) -> str:
        parts = [part for part in path.split("/") if part]
        # gmail / v1 / users / me / <resource> [/ <id>]
        if len(parts) < 5:
            return "unknown"
        resource = parts[4]
        if resource == "messages" and len(parts) > 5:
            return "messages.get"
        return {
            "messages": "messages.list",
            "threads": "threads.get",
            "history": "history.list",
            "profile": "profile",
        }.get(resource, "unknown")

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = self.key_for(request.url.path)
        queue = self.queues.get(key)
        if not queue:
            return json_response(
                500,
                {"error": {"code": 500, "status": "INTERNAL", "message": f"no fixture for {key}"}},
            )
        return queue.popleft()

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def paths(self) -> list[str]:
        return [request.url.path for request in self.requests]

    def query_of(self, index: int) -> httpx.QueryParams:
        return self.requests[index].url.params
