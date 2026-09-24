"""Backoff with jitter, bounded twice (AD A.5a).

Exponential backoff, base 250 ms, factor 2, jitter +/-25 %, `max_retries = 3`, and a hard
`max_backoff_total_ms = 1500` that is **additionally clamped to the remaining clock of the
rung in flight**. Both bounds are real and the tighter one wins, which is the part that is
easy to leave out: a rung with 300 ms left must not sleep 1,500 ms just because the retrier
is allowed to.

Determinism is a parameter. `sleep` and `random` are injected, so the tests assert the exact
delay sequence rather than a range - a jitter that is tested by "it was roughly right"
passes with the jitter switched off.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass

from mailweave.constants import (
    MAX_BACKOFF_TOTAL_MS,
    MAX_RETRIES,
    RETRY_BASE_MS,
    RETRY_FACTOR,
    RETRY_JITTER_FRACTION,
)

#: Injected so tests need no clock. Takes seconds, like `time.sleep`.
Sleeper = Callable[[float], None]
#: Injected so tests need no entropy. Returns a float in [0, 1), like `random.random`.
Jitterer = Callable[[], float]


@dataclass(frozen=True)
class BackoffPolicy:
    """The A.5a figures, as data.

    Defaults come from `constants.py`, which is where the architecture's numbers live; the
    fields exist so a test can state a different policy explicitly rather than monkeypatching
    a module constant and leaving the next test to discover it.
    """

    base_ms: int = RETRY_BASE_MS
    factor: int = RETRY_FACTOR
    jitter_fraction: float = RETRY_JITTER_FRACTION
    max_retries: int = MAX_RETRIES
    max_backoff_total_ms: int = MAX_BACKOFF_TOTAL_MS

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if self.base_ms <= 0 or self.factor < 1:
            raise ValueError("a backoff needs a positive base and a factor of at least 1")
        if not 0.0 <= self.jitter_fraction < 1.0:
            raise ValueError("jitter is a fraction of the delay, in [0, 1)")


#: The least a request is allowed to start with. Below this the deadline is treated as
#: spent: a request that must complete inside a few milliseconds is a request that will
#: time out and charge the meter for nothing, so it is refused before it is sent.
MIN_ATTEMPT_MS: float = 50.0


@dataclass
class Deadline:
    """One tool call's wall-clock allowance, read live rather than copied once.

    **What `remaining_ms` on `BackoffState` did not do** (2026-09-21). It bounded the sleeps
    between attempts and nothing else: not the request in flight, not the next attempt, not
    the next message of a sequential read. With the client built at `timeout=30.0` and
    `MAX_RETRIES = 3`, a four-message `body_full` read had a worst case of 4 × 4 × 30 s
    against a published `MAX_SERVER_MS` of 7,700 ms, and the cap constrained 1.5 s of it.
    The observed four-minute silence on the Desktop surface sits inside that envelope.

    A `Deadline` is constructed once at the top of a tool call from the service's own clock
    and bound to the `GmailClient` for that call. Every `_request` asks it how much is left
    *now*: the per-attempt HTTP timeout is the smaller of the client's ceiling and what is
    left, an attempt with less than `MIN_ATTEMPT_MS` left is not started, and the backoff's
    sleep bound is refreshed from it before every sleep. A sequential fetch that reaches the
    deadline raises `GmailDeadlineExceeded` on its next request, which is how "stop at the
    deadline" is enforced without every loop in the retrieval stack knowing about it.
    """

    budget_ms: float
    clock_ms: Callable[[], float]
    started_ms: float = 0.0

    def __post_init__(self) -> None:
        if self.budget_ms <= 0:
            raise ValueError("a deadline needs a positive budget")
        self.started_ms = self.clock_ms()

    def elapsed_ms(self) -> float:
        return max(0.0, self.clock_ms() - self.started_ms)

    def remaining_ms(self) -> float:
        return max(0.0, self.budget_ms - self.elapsed_ms())

    def expired(self) -> bool:
        return self.remaining_ms() < MIN_ATTEMPT_MS


@dataclass
class BackoffState:
    """One call's retry budget, consumed as attempts are made.

    Holds the two clocks the A.5a bound names: the retrier's own 1,500 ms total and the
    caller's `remaining_ms`, which is the rung's unspent `max_server_ms`. `remaining_ms` is
    `None` when a caller has no clock - the CLI's one-shot calls, and the preflight probes.
    """

    policy: BackoffPolicy
    remaining_ms: float | None = None
    attempts: int = 0
    slept_ms: float = 0.0

    def _budget_ms(self) -> float:
        total = float(self.policy.max_backoff_total_ms)
        if self.remaining_ms is not None:
            total = min(total, max(0.0, self.remaining_ms))
        return total

    def next_delay_ms(
        self, jitter: Jitterer, *, retry_after_ms: float | None = None
    ) -> float | None:
        """The next sleep in milliseconds, or `None` if this call must stop retrying.

        `None` means the bound was reached - by attempt count, by the retrier's own total, or
        by the caller's remaining clock - and the caller raises the typed fault. It never
        means "sleep zero and try again", because a retry with no wait is the shape that
        turns a rate limit into a tighter one.

        `retry_after_ms` is Gmail's `Retry-After` header when it sent one. It **raises** the
        delay and never lowers it, and a `Retry-After` that does not fit inside the remaining
        budget stops the retrying rather than being truncated to fit: waiting less than the
        server asked for is how a client turns a soft limit into a hard one. Whether Gmail
        actually sends this header on a Gmail-API 429 is a preflight question (PF-3), not
        something this module asserts.
        """
        if self.attempts < 1:
            raise ValueError(
                "next_delay_ms is asked after an attempt has been made and counted; "
                "asking before the first attempt would compute a negative exponent"
            )
        if self.attempts > self.policy.max_retries:
            return None
        exponential = float(self.policy.base_ms) * float(self.policy.factor ** (self.attempts - 1))
        spread = exponential * self.policy.jitter_fraction
        # jitter() in [0,1) maps onto [-spread, +spread).
        delay: float = exponential + spread * (2.0 * jitter() - 1.0)
        if retry_after_ms is not None:
            delay = max(delay, retry_after_ms)
        remaining_budget = self._budget_ms() - self.slept_ms
        if delay > remaining_budget:
            return None
        return delay

    def sleep(self, delay_ms: float, sleeper: Sleeper) -> None:
        self.slept_ms += delay_ms
        if self.remaining_ms is not None:
            self.remaining_ms -= delay_ms
        sleeper(delay_ms / 1000.0)


def default_sleeper() -> Sleeper:
    return time.sleep


def default_jitterer() -> Jitterer:
    """`random.random`, not `secrets`. Jitter is a thundering-herd defence, not a secret."""
    return random.random
