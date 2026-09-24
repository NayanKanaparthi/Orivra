"""`ConnectorRegistry`: which sources this installation has, and what state each is in.

**By reference, never by copy.** The Gmail entry holds the `MailweaveService` that
`mailweave.surface.runtime.start()` established - the same object the four `mailweave_*`
tools use - so there is one authorised mailbox in the process, one token store, one handle
key and one place that decides what may be spent. A registry that built its own service
would be a second credential path with its own refresh clock, and the first symptom of that
is two `historyId` watermarks disagreeing about the same mailbox.

**A source that is absent is reported, not omitted.** `orivra_sources` names every connector
Orivra knows about and the state each is in, because "Drive is not configured" and "Drive
returned nothing" are different answers to "what did you look at?", and a caller that cannot
tell them apart will read an empty result as an empty Drive.
"""

from __future__ import annotations

from dataclasses import dataclass

from mailweave.surface.runtime import Runtime
from orivra.adapter import AdapterCapabilities, SourceAdapter
from orivra.cache import BoundedCache
from orivra.contracts import ConnectorId, SourceState
from orivra.gmail_adapter import GmailAdapter

#: Why each connector Orivra knows about but has not built is absent. Stated per connector
#: rather than as one sentence, because the reasons differ and will differ more: Drive
#: arrives at M4 and Slack at M5, and Slack's availability additionally depends on a token
#: kind and a plan tier that only a preflight can establish.
NOT_BUILT: dict[ConnectorId, str] = {
    ConnectorId.DRIVE: "the Google Drive adapter arrives at milestone M4",
    ConnectorId.SLACK: (
        "the Slack adapter arrives at milestone M5, and its search surface additionally "
        "depends on a token kind and a workspace plan tier that a preflight establishes"
    ),
}


class ConnectorUnavailable(RuntimeError):
    """This installation has no adapter for a connector a call needs.

    **Not a `LookupError`**, which is what it was and which is the whole point of the
    change. `LookupError` is the base class of `KeyError` and `IndexError`, so `except
    LookupError` in the surface caught every dictionary miss and index error anywhere inside
    a tool handler - including inside code walking a mail-derived payload - and reported it
    to the client as `auth_reauth_required` with `str(exc)` in the remediation. Two failures
    in one: an internal defect told the user to re-authenticate, and an arbitrary exception
    string, which can carry a thread id or a subject line, was written verbatim into the
    response (R-SEC-043's rule, in a place nobody was looking).
    """


@dataclass(frozen=True)
class ConnectorStatus:
    """One connector as `orivra_sources` reports it.

    `capabilities` is `None` for a connector with no adapter: a capability set for a source
    that cannot be reached would describe what it *would* do, which a planner might act on.
    """

    connector: ConnectorId
    state: SourceState
    detail: str
    capabilities: AdapterCapabilities | None = None


@dataclass(frozen=True)
class ConnectorRegistry:
    """The adapters this process has, keyed by connector."""

    adapters: dict[ConnectorId, SourceAdapter]

    @classmethod
    def from_runtime(cls, runtime: Runtime) -> ConnectorRegistry:
        """A Gmail-only registry over an already-started MailWeave runtime.

        `runtime.report.granted_scopes` is the **granted** set read back after consent, not
        the requested one - which is the figure a `PermissionContext` has to carry, because a
        request for `gmail.readonly` granted something narrower must not produce a context
        claiming the wider scope.

        **The process-lifetime cache is built here**, which is the only place it can be built
        and still be one cache. An adapter that made its own would make a new one per call and
        never hit; a module-level one would be shared across principals, which is exactly what
        the `principal` key dimension exists to prevent and is not a thing to rely on a key to
        catch. In-memory only: plan §5.1's on-disk store is not in this release (see
        `docs/GMAIL_PREVIEW_CACHE.md`), so this cache dies with the process.
        """
        gmail = GmailAdapter(
            service=runtime.service,
            granted_scopes=tuple(runtime.report.granted_scopes),
            cache=BoundedCache(now=runtime.service.now),
        )
        return cls(adapters={ConnectorId.GMAIL: gmail})

    def gmail(self) -> GmailAdapter:
        """The Gmail adapter, or a refusal naming what to do about its absence.

        Typed as `GmailAdapter` rather than `SourceAdapter` because M1's `orivra_ask`
        delegates through `answer`, which is Gmail's whole-query route; a caller that only
        needs the protocol methods should take `adapters[ConnectorId.GMAIL]` instead.
        """
        adapter = self.adapters.get(ConnectorId.GMAIL)
        if not isinstance(adapter, GmailAdapter):
            raise ConnectorUnavailable(
                "this Orivra process has no Gmail adapter. It is built from a started "
                "MailWeave runtime, so a registry without one means startup did not "
                "complete - run `mailweave doctor` and, if the credential is the problem, "
                "`mailweave auth login`"
            )
        return adapter

    def statuses(self) -> tuple[ConnectorStatus, ...]:
        """Every connector Orivra knows about, in `ConnectorId` order.

        Every one, including the ones with no adapter. A list containing only what is
        configured cannot answer "did you look at Drive?", and the answer to that question
        is the whole point of the tool that publishes this.
        """
        rows: list[ConnectorStatus] = []
        for connector in ConnectorId:
            adapter = self.adapters.get(connector)
            if adapter is None:
                rows.append(
                    ConnectorStatus(
                        connector=connector,
                        state=SourceState.NOT_CONFIGURED,
                        detail=NOT_BUILT.get(connector, "no adapter is registered"),
                    )
                )
                continue
            rows.append(
                ConnectorStatus(
                    connector=connector,
                    state=SourceState.READY,
                    detail=(
                        "authorised and read-only; retrieval runs through the MailWeave "
                        "engine this process started"
                    ),
                    capabilities=adapter.capabilities(),
                )
            )
        return tuple(rows)


__all__ = [
    "NOT_BUILT",
    "ConnectorRegistry",
    "ConnectorStatus",
    "ConnectorUnavailable",
]
