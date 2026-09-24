"""Level-2 equivalence: what two correct responses to one question may differ in, and what
they may not.

M1 claims that `orivra_ask {sources: [gmail]}` and `mailweave_search` answer the same
question with the same evidence. Level 1 checks that byte-for-byte where it is meaningful
(`tests/test_orivra_surface.py`).

**Amended 2026-09-19, and the amendment is a real weakening - so here is exactly how far.**
The claim above was written when both paths were fitted to the same room. They are not any
more: an `orivra_ask` is MailWeave's container plus Orivra's navigation block under one host
cap, and the container is now fitted to the cap *minus* what that block needs. Without that,
two live Claude Desktop runs composed past the cap and the ask declined - the second one took
the decline's `mailweave_search` offer, answered the question out of message reads and never
saw a graph, which is the product failing while every test passed.

So near the cap the two paths disclose different evidence, by design and permanently. The
claim is now: **equal, or different in a way the Orivra response itself wholly accounts for.**
`compare_ask` is where that is enforced, and it is deliberately hard to satisfy - the
allocation must be declared in the response, what Orivra disclosed must be a subset of what
MailWeave did, the response must call itself partial, and every missing identity must be
covered by its own omission accounting. An undeclared or unaccounted difference is a
divergence exactly as it always was. M1 was closed on the unamended claim at `91a2607` and
needs re-closing on this one.

Level 2 is the live half, and it cannot be byte identity:
MailWeave mints a fresh fence nonce per response, stamps `fetched_at` and `verified_at` from
the real clock, and signs handles that embed both. **Two correct responses to the same
question differ byte-for-byte, and a test that demanded otherwise would fail for correct
reasons** - which is worse than no test, because it trains everyone to ignore it.

So this module states exactly three things:

* `normalise` - the three families that legitimately differ, substituted, and nothing else;
* `semantic_view` - what survives, which is exactly what the plan says level 2 compares: the
  evidence identities at each depth, the declared scope, the omission counts by cap, the cap
  declarations, `partial`, and the outcome;
* `compare` - the difference between two views, field by field, so a failure says which
  claim broke rather than that "the responses differ";
* `compare_ask` - the same comparison over a whole ask response, which is the only place the
  container's allocation is declared and therefore the only place a difference can be shown
  to be accounted for rather than merely observed.

**Affordances are compared by where they land, never as bytes.** Two correct responses sign
two different handles for the same thread, so comparing the calls would compare signatures.
What the plan requires is their *executable behaviour* - that following the Orivra affordance
and the MailWeave affordance reaches the same evidence - and `compare_affordances` below does
exactly that: it pairs the two sides' offers, **executes** each pair, and compares the
evidence identities they recover.

Three properties make executing them safe to do in a live run:

* **read-only** - every call it will run names one of the four `mailweave_*` tools, all of
  which are annotated `readOnlyHint: true` and hold no scope but `gmail.readonly`. A pair
  naming anything else is reported as invalid and not run;
* **bounded, and failing closed** - `MAX_PAIRED_AFFORDANCES` pairs per query, and no
  recursion: what an executed affordance itself offers is not followed. A recovery chain is
  bounded, monotonic and cycle-free by `surface/recovery.py`'s contract, and this runner does
  not need to walk it to answer the question it is asking. **A response with more pairs than
  the bound does not quietly pass**: the pairs it could not execute are counted, named and
  reported as an unresolved divergence, because "we checked twelve of thirteen" and "the two
  paths agree" are different statements;
* **deterministic** - pairs are matched by `(tool, subject)` and ordered,
  so two runs pair the same offers in the same order.

An earlier draft of this paragraph cited an `execute_and_compare` function that did not
exist, and the live runner recorded only the tool *names* each side offered. That was the
sentence claiming the strongest thing in the module with nothing behind it, and the weaker
behaviour it described was not what the plan asks for.

**Nothing recovered is printed.** The comparison is over evidence *identities* - thread and
message ids - and the divergence report names ids and counts. No body text, no handle, no
signature and no nonce reaches the record.

One implementation, used by the offline rehearsal and by the live run. A live check whose
comparison function is only exercised on the day of the live run is a comparison function
nobody has tested.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

#: The response fields that legitimately differ between two correct answers to one question.
#: Named here, so what is being normalised away is visible rather than implied by a regex.
TIMESTAMP_KEYS: frozenset[str] = frozenset({"fetched_at", "verified_at", "observed_at"})
HANDLE_KEYS: frozenset[str] = frozenset({"map_id"})

#: What the substituted values become. Distinct strings, so a view that lost a field can be
#: told apart from one whose field was normalised.
NONCE_MARK = "<nonce>"
INSTANT_MARK = "<instant>"
HANDLE_MARK = "<handle>"


def normalise(payload: Any, nonce: str | None = None) -> Any:
    """Substitute the fence nonce, the freshness stamps and the handle payloads.

    `nonce` is read off the payload when it is not given, and its absence is an error rather
    than a no-op: a payload with no fence nonce is not a MailWeave response, and normalising
    it as though it were would silently compare something else.
    """
    if nonce is None:
        if not isinstance(payload, Mapping):
            raise TypeError("a response to normalise is an object with a fence_nonce")
        found = payload.get("fence_nonce")
        if not isinstance(found, str) or not found:
            raise ValueError(
                "this payload carries no fence_nonce, so it is not a MailWeave response and "
                "normalising it would compare something other than what was claimed"
            )
        nonce = found
    return _substitute(payload, nonce)


def _substitute(node: Any, nonce: str) -> Any:
    if isinstance(node, Mapping):
        cleaned: dict[str, Any] = {}
        for key, value in node.items():
            if key == "fence_nonce":
                cleaned[key] = NONCE_MARK
            elif key in TIMESTAMP_KEYS and isinstance(value, str):
                cleaned[key] = INSTANT_MARK
            elif key in HANDLE_KEYS and isinstance(value, str):
                cleaned[key] = HANDLE_MARK
            else:
                cleaned[key] = _substitute(value, nonce)
        return cleaned
    if isinstance(node, str):
        return node.replace(nonce, NONCE_MARK)
    if isinstance(node, Sequence) and not isinstance(node, str | bytes):
        return [_substitute(item, nonce) for item in node]
    return node


def semantic_view(payload: Mapping[str, Any]) -> dict[str, Any]:
    """The comparable part of one response.

    Six fields, and they are the six the plan names. Nothing here is a summary or a hash: a
    difference has to be readable as *which message*, *which cap*, *which scope*, or the
    failure report says only that something changed.
    """
    cleaned = normalise(dict(payload))
    identities: dict[str, list[str]] = {}
    for source in cleaned.get("sources", []):
        for row in source.get("messages", []):
            identities.setdefault(row["depth"], []).append(f"{source['thread_id']}/{row['id']}")
    report = cleaned.get("retrieval_report") or {}
    omission = cleaned.get("omission") or {}
    return {
        "evidence_by_depth": {depth: sorted(ids) for depth, ids in sorted(identities.items())},
        "declared_scope": [entry.get("query") for entry in report.get("scan_scope", [])],
        "omission_by_cap": omission.get("by_cap", omission),
        "caps_declared": sorted(report.get("budget_caps_hit", [])),
        "partial": cleaned.get("partial"),
        "outcome": report.get("outcome"),
    }


@dataclass(frozen=True)
class Difference:
    """One field of the semantic view on which the two paths disagree."""

    field: str
    orivra: Any
    mailweave: Any

    def render(self) -> str:
        return f"{self.field}: orivra={self.orivra!r} mailweave={self.mailweave!r}"


@dataclass(frozen=True)
class Comparison:
    """The result of comparing two responses to one question."""

    query: str
    differences: tuple[Difference, ...]

    @property
    def equivalent(self) -> bool:
        return not self.differences

    def render(self) -> str:
        if self.equivalent:
            return f"EQUIVALENT  {self.query}"
        lines = "\n    ".join(one.render() for one in self.differences)
        return f"DIVERGED    {self.query}\n    {lines}"


def compare(query: str, orivra: Mapping[str, Any], mailweave: Mapping[str, Any]) -> Comparison:
    """Field by field, so a failure names the claim that broke."""
    left, right = semantic_view(orivra), semantic_view(mailweave)
    differences = tuple(
        Difference(field=field, orivra=left.get(field), mailweave=right.get(field))
        for field in sorted(set(left) | set(right))
        if left.get(field) != right.get(field)
    )
    return Comparison(query=query, differences=differences)


def _identities(view: Mapping[str, Any]) -> set[str]:
    return {identity for ids in (view.get("evidence_by_depth") or {}).values() for identity in ids}


def _accounted_omissions(payload: Mapping[str, Any]) -> int:
    """How many items this response says it left out, by its own accounting."""
    omission = payload.get("omission") or {}
    if not isinstance(omission, Mapping):
        return 0
    total = 0
    for key in ("withheld_messages", "withheld_threads", "not_included_sources"):
        value = omission.get(key)
        if isinstance(value, int):
            total += value
    by_cap = omission.get("withheld_by_cap")
    if isinstance(by_cap, Mapping):
        total += sum(value for value in by_cap.values() if isinstance(value, int))
    return total


def compare_ask(query: str, ask: Mapping[str, Any], mailweave: Mapping[str, Any]) -> Comparison:
    """Level 2, over a whole `orivra_ask` response rather than its Gmail container alone.

    **Why this exists, and what it deliberately does not do.** Until 2026-09-19 the two paths
    were fitted to the same room, so `compare` over the container was the whole check. They no
    longer are: `orivra_ask` fits MailWeave's container to the cap *minus* the room Orivra's
    own block needs, because the alternative - measured on two live Claude Desktop runs - is a
    composed response over the cap and no answer at all. Near the cap the two paths therefore
    disclose different evidence, and they will keep doing so.

    A check that simply accepted that would be worthless, so this does not. A difference is
    treated as accounted only when **all four** of these hold, and any one of them failing
    leaves it reported as a divergence exactly as before:

    * the Orivra side **declares** a container below the host cap, in the response, under
      `allocation`. An undeclared difference is a divergence, whatever caused it;
    * what Orivra disclosed is a **subset** of what MailWeave did. A message Orivra returned
      and MailWeave did not is not a narrower answer, it is a different one;
    * the Orivra side says it is `partial`. A response that dropped evidence and calls itself
      whole is wrong about itself;
    * the number of identities missing is covered by the Orivra side's **own omission
      accounting**. Evidence that vanished without a record is the failure this whole project
      is built to refuse, and a declared allocation is not a licence for it.

    What remains reported, always, is `outcome` and `declared_scope`: the allocation changes
    how much of an answer fits, never what was asked or how the retrieval ended.
    """
    container = ask.get("gmail")
    if not isinstance(container, Mapping):
        return Comparison(
            query=query,
            differences=(Difference(field="gmail", orivra=None, mailweave="present"),),
        )
    plain = compare(query, container, mailweave)
    if plain.equivalent:
        return plain

    allocation = ask.get("allocation")
    declared = (
        isinstance(allocation, Mapping)
        and isinstance(allocation.get("container_chars"), int)
        and isinstance(allocation.get("host_cap_chars"), int)
        and allocation["container_chars"] < allocation["host_cap_chars"]
    )
    if not declared:
        return plain

    left, right = semantic_view(container), semantic_view(mailweave)
    theirs, ours = _identities(right), _identities(left)
    missing = theirs - ours
    if ours - theirs or not missing:
        return plain
    if container.get("partial") is not True:
        return plain
    if len(missing) > _accounted_omissions(container):
        return plain

    # Everything that differs *because* less room was available, and nothing else.
    allocation_fields = {"evidence_by_depth", "omission_by_cap", "caps_declared", "partial"}
    return Comparison(
        query=query,
        differences=tuple(one for one in plain.differences if one.field not in allocation_fields),
    )


#: How many affordance pairs one query's comparison will execute.
#:
#: Bounded because this runs live against a real mailbox: an unbounded walk of a response's
#: offers is a quota bill that grows with how partial the answer was, which is exactly
#: backwards.
#:
#: **The first draft's docstring said twelve "covers every offer the four demonstrations
#: produce with room over". That was false - thirteen recovery affordances have been
#: observed** - and the bound then silently truncated: pairs past it were dropped and the
#: query could still be declared equivalent with an affordance never checked. The number is
#: deliberately *not* raised to make that observation fit, because tuning a constant until a
#: run passes is the shape of defect this project exists to refuse. Instead the bound now
#: **fails closed**: what it could not execute is counted and reported as an unresolved
#: divergence, so a breach is loud and the decision to raise the bound is made on the
#: evidence rather than in advance of it.
MAX_PAIRED_AFFORDANCES: int = 12

#: The tools an equivalence run may execute. **Read-only, and checked rather than assumed.**
#:
#: Every one is annotated `readOnlyHint: true` on the published surface and the server holds
#: no Gmail scope but `gmail.readonly`. An offer naming anything else is reported as invalid
#: and not run - which is a divergence, not a silence.
EXECUTABLE_TOOLS: frozenset[str] = frozenset(
    {
        "mailweave_search",
        "mailweave_thread_map",
        "mailweave_get_messages",
        "mailweave_get_attachment",
    }
)


@dataclass(frozen=True)
class Offer:
    """One executable call a response made, with the facts that pair it deterministically.

    `subject` is the thing the call is *about* - a thread id, the sorted message ids, a query
    - so two responses' offers about the same thread pair with each other rather than by
    position. Position pairing would compare an Orivra offer about thread A with a MailWeave
    offer about thread B and call the difference a divergence.
    """

    tool: str
    args: dict[str, Any]
    subject: str

    @property
    def executable(self) -> bool:
        return self.tool in EXECUTABLE_TOOLS

    @property
    def key(self) -> tuple[str, str]:
        return (self.tool, self.subject)


def _subject_of(args: Mapping[str, Any]) -> str:
    """What a call is about, from its own arguments. Never a handle.

    `map_id` is deliberately excluded: it is a signed value that differs between two correct
    responses, so pairing on it would pair nothing. A call that names only a `map_id` pairs on
    its tool and its narrowing instead.
    """
    for key in ("thread_id", "query"):
        value = args.get(key)
        if isinstance(value, str) and value:
            return f"{key}={value}"
    ids = args.get("message_ids")
    if isinstance(ids, list) and ids:
        return "message_ids=" + ",".join(sorted(str(one) for one in ids))
    positions = args.get("positions")
    if isinstance(positions, list) and positions:
        return "positions=" + ",".join(sorted(str(one) for one in positions))
    return "unaddressed"


def offers_of(payload: Mapping[str, Any]) -> tuple[Offer, ...]:
    """Every executable call a response offers, deterministically ordered.

    Gathered from the response's own blocks rather than from a shape guessed here. Sorted by
    `(tool, subject)` and de-duplicated, so two runs over one mailbox produce the same list in
    the same order - which is what makes pairing deterministic.
    """
    found: dict[tuple[str, str], Offer] = {}
    blocks: list[Any] = list(payload.get("affordances") or [])
    for block in ("withheld", "withheld_groups", "withheld_tail"):
        for record in payload.get(block) or []:
            if isinstance(record, Mapping) and isinstance(record.get("affordance"), Mapping):
                blocks.append(record["affordance"])
    for source in payload.get("sources") or []:
        if not isinstance(source, Mapping):
            continue
        for run in source.get("collapsed_runs") or []:
            if isinstance(run, Mapping) and isinstance(run.get("affordance"), Mapping):
                blocks.append(run["affordance"])
    for offer in blocks:
        if not isinstance(offer, Mapping) or "tool" not in offer:
            continue
        args = dict(offer.get("args") or {})
        one = Offer(tool=str(offer["tool"]), args=args, subject=_subject_of(args))
        found.setdefault(one.key, one)
    return tuple(found[key] for key in sorted(found))


def evidence_of(payload: Mapping[str, Any]) -> frozenset[str]:
    """The evidence identities a response carries: `thread/message` pairs, and nothing else.

    Identities rather than content, because that is what "reaches the same evidence" means
    and because a live record must not carry mail. A response that disclosed nothing produces
    an empty set, which compares equal only to another empty set.
    """
    found: set[str] = set()
    for source in payload.get("sources") or []:
        if not isinstance(source, Mapping):
            continue
        thread = source.get("thread_id")
        if not isinstance(thread, str):
            continue
        for row in source.get("messages") or []:
            if isinstance(row, Mapping) and isinstance(row.get("id"), str):
                found.add(f"{thread}/{row['id']}")
        for run in source.get("collapsed_runs") or []:
            if isinstance(run, Mapping):
                for member in run.get("member_ids") or []:
                    if isinstance(member, str):
                        found.add(f"{thread}/{member}")
    return frozenset(found)


def affordances_of(payload: Mapping[str, Any]) -> tuple[tuple[str, dict[str, Any]], ...]:
    """Every executable call a response offers, as `(tool, args)` pairs.

    Gathered from the response's own blocks rather than from a shape guessed here, and
    returned as calls rather than as bytes - because what level 2 compares about an
    affordance is where following it lands, not how it was signed.
    """
    found: list[tuple[str, dict[str, Any]]] = []
    for block in ("affordances",):
        for offer in payload.get(block, []) or []:
            if isinstance(offer, Mapping) and "tool" in offer:
                found.append((str(offer["tool"]), dict(offer.get("args", {}))))
    for block in ("withheld", "withheld_groups", "withheld_tail"):
        for record in payload.get(block, []) or []:
            offer = record.get("affordance") if isinstance(record, Mapping) else None
            if isinstance(offer, Mapping) and "tool" in offer:
                found.append((str(offer["tool"]), dict(offer.get("args", {}))))
    return tuple(found)


@dataclass(frozen=True)
class AffordanceComparison:
    """What executing one pair of offers established, or why it could not be executed."""

    subject: str
    tool: str
    status: str
    """`agreed` | `diverged` | `unpaired` | `invalid` | `unexecutable` | `unchecked`. Six,
    because they are six different failures and a caller told "diverged" for all of them
    would look for a retrieval difference where the actual problem was an offer only one side
    made, or a bound that stopped before the last pair."""

    orivra_evidence: int = 0
    mailweave_evidence: int = 0
    only_orivra: tuple[str, ...] = ()
    only_mailweave: tuple[str, ...] = ()
    detail: str = ""

    @property
    def agreed(self) -> bool:
        return self.status == "agreed"

    def render(self) -> str:
        head = f"      {self.status:12s} {self.tool} {self.subject}"
        if self.agreed:
            return f"{head} -> {self.orivra_evidence} evidence identities, identical"
        parts = [head]
        if self.only_orivra:
            parts.append(f"        only via orivra:    {list(self.only_orivra)[:8]}")
        if self.only_mailweave:
            parts.append(f"        only via mailweave: {list(self.only_mailweave)[:8]}")
        if self.detail:
            parts.append(f"        {self.detail}")
        return "\n".join(parts)


#: What one side's tool call does. `(tool, args) -> structured payload`, or a raise.
Execute = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True)
class AffordanceReport:
    """What a paired-affordance comparison did, **including what it did not do**.

    The counts are first-class rather than derived from `results`, because what went wrong
    before was a silence: the bound truncated the pair list and nothing in the output said so,
    so a query offering thirteen pairs could be declared equivalent with the thirteenth never
    executed. A caller reading this cannot miss `unexecuted_pairs`.
    """

    results: tuple[AffordanceComparison, ...]
    total_pairs: int
    executed_pairs: int
    unexecuted_pairs: int

    @property
    def unresolved(self) -> tuple[AffordanceComparison, ...]:
        return tuple(one for one in self.results if not one.agreed)

    @property
    def complete(self) -> bool:
        """Whether every pair the two responses offered was actually executed."""
        return self.unexecuted_pairs == 0

    @property
    def agreed(self) -> bool:
        """**A conjunction, and `complete` is one of its terms.** Every executed pair agreed
        *and* nothing was left unexecuted. Dropping the second term is the silence."""
        return self.complete and not self.unresolved


def compare_affordances(
    orivra_payload: Mapping[str, Any],
    mailweave_payload: Mapping[str, Any],
    *,
    execute: Execute,
    limit: int = MAX_PAIRED_AFFORDANCES,
) -> AffordanceReport:
    """Pair the two sides' offers, **execute** each pair, and compare what they recover.

    This is the plan's level-2 requirement in the form it states: not that the two responses
    offer affordances with matching bytes - they cannot, they are signed differently - but
    that following either one reaches the same evidence.

    Bounded, read-only and deterministic. Every executed call is one of the four `mailweave_*`
    tools; an offer naming anything else is `invalid` and is not run. At most `limit` pairs,
    and nothing an executed call itself offers is followed. Pairing is by `(tool, subject)`,
    so the same offers pair in the same order on every run.

    **An offer only one side made is a divergence** (`unpaired`), not something to skip: two
    responses that recovered the same evidence but offered different routes back to it have
    not answered the same question in the same way, and the retry contract is part of the
    answer.
    """
    if limit < 1:
        raise ValueError(
            "a comparison bound below one executes nothing and would report every query as "
            "unchecked; the bound exists to cap a live quota bill, not to disable the check"
        )
    left = {one.key: one for one in offers_of(orivra_payload)}
    right = {one.key: one for one in offers_of(mailweave_payload)}
    pairs = sorted(set(left) | set(right))
    reachable, beyond = pairs[:limit], pairs[limit:]
    results: list[AffordanceComparison] = []
    for key in reachable:
        tool, subject = key
        ours, theirs = left.get(key), right.get(key)
        if ours is None or theirs is None:
            results.append(
                AffordanceComparison(
                    subject=subject,
                    tool=tool,
                    status="unpaired",
                    detail=(
                        "offered only by " + ("mailweave_search" if ours is None else "orivra_ask")
                    ),
                )
            )
            continue
        if not ours.executable or not theirs.executable:
            results.append(
                AffordanceComparison(
                    subject=subject,
                    tool=tool,
                    status="invalid",
                    detail="names a tool this run may not execute; only the four read-only "
                    "mailweave_* tools are run",
                )
            )
            continue
        try:
            ours_payload = execute(ours.tool, ours.args)
            theirs_payload = execute(theirs.tool, theirs.args)
        except Exception as failure:
            results.append(
                AffordanceComparison(
                    subject=subject,
                    tool=tool,
                    status="unexecutable",
                    detail=f"the call did not execute: {type(failure).__name__}",
                )
            )
            continue
        ours_evidence, theirs_evidence = evidence_of(ours_payload), evidence_of(theirs_payload)
        results.append(
            AffordanceComparison(
                subject=subject,
                tool=tool,
                status="agreed" if ours_evidence == theirs_evidence else "diverged",
                orivra_evidence=len(ours_evidence),
                mailweave_evidence=len(theirs_evidence),
                only_orivra=tuple(sorted(ours_evidence - theirs_evidence))[:16],
                only_mailweave=tuple(sorted(theirs_evidence - ours_evidence))[:16],
            )
        )

    if beyond:
        # **One record for the breach, not one per skipped pair.** The skipped subjects are
        # named so a reader can see which routes went unchecked - they are evidence
        # identities, which this record already carries - and the list is bounded for the
        # same reason the execution is.
        results.append(
            AffordanceComparison(
                subject=f"{len(beyond)} pair(s) past the bound",
                tool="(bound)",
                status="unchecked",
                detail=(
                    f"{len(pairs)} affordance pairs were offered and this run executes at "
                    f"most {limit}; {len(beyond)} were not executed, so the two paths are not "
                    "known to agree on them. Skipped: "
                    + ", ".join(f"{tool} {subject}" for tool, subject in beyond[:8])
                    + ("" if len(beyond) <= 8 else f", and {len(beyond) - 8} more")
                ),
            )
        )

    return AffordanceReport(
        results=tuple(results),
        total_pairs=len(pairs),
        executed_pairs=len(reachable),
        unexecuted_pairs=len(beyond),
    )


__all__ = [
    "EXECUTABLE_TOOLS",
    "HANDLE_KEYS",
    "HANDLE_MARK",
    "INSTANT_MARK",
    "MAX_PAIRED_AFFORDANCES",
    "NONCE_MARK",
    "TIMESTAMP_KEYS",
    "AffordanceComparison",
    "AffordanceReport",
    "Comparison",
    "Difference",
    "Execute",
    "Offer",
    "affordances_of",
    "compare",
    "compare_affordances",
    "compare_ask",
    "evidence_of",
    "normalise",
    "offers_of",
    "semantic_view",
]
