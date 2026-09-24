"""A dummy corpus, a dummy case file, and both arms over them - the development loop.

**Dummy, and the word is load-bearing.** The queries below are nonsense chosen to match a
sentinel token; the "evidence" is whichever message the generator put that token in. Nothing
here is a case in the campaign's sense, nothing here is held out from anybody, and no number
produced from it is evidence about retrieval quality. What it is for is the other question:
does the case interface load, do the ref joins resolve, do both arms run, and do the hypothesis
clauses compute - which is exactly what could not be checked while the harness had no input.

The corpus comes from `seed.corpus.generate`, which is the real generator. The mailbox is the
suite's own `SyntheticMailbox`, driven from the manifest, so the arms run through the shipped
`MailweaveService` against messages whose ids the manifest knows.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from mailweave.disclosure import FixedWindow, Selector
from mailweave.gmail import BackoffPolicy, CallMeter, GmailClient, StaticToken
from mailweave.handles.cache import ThreadMapCache
from mailweave.handles.keys import HandleKey
from mailweave.net.egress import build_client
from mailweave.semantic.interface import BackendRegistry, SemanticBackend, Vector
from mailweave.surface.service import MailweaveService
from mailweave_harness.evaluation.arms import (
    SPECS,
    Arm,
    ArmSpec,
    CountingBackend,
    build_arm,
)
from mailweave_harness.evaluation.cases import CaseFile
from mailweave_harness.evaluation.observe import FetchLog, FetchObserver
from mailweave_harness.evaluation.selftest import sentinel_case_file
from mailweave_harness.seed.corpus import generate
from mailweave_harness.seed.manifest import Manifest, SeededMessage
from mailweave_harness.seed.substrate import InsertedMessage, VerificationReport
from tests.fixtures.mailbox import Msg, SyntheticMailbox

TOKEN = "ya29.SECRET-ACCESS-TOKEN-NEVER-IN-AN-EVAL-FIXTURE"
ACCOUNT = "sha256:0f1e2d3c4b5a69788796a5b4c3d2e1f0"


def dummy_manifest(seed: int = 4242) -> Manifest:
    return generate(master_seed=seed, size_profile="smoke")


def _gmail_id(message: SeededMessage) -> str:
    """A stable stand-in for the id Gmail would assign. Deterministic, so a test can join."""
    return f"g-{message.thread_key}-{message.position:03d}"


def _epoch_ms(message: SeededMessage) -> int:
    try:
        when = parsedate_to_datetime(message.date_rfc2822)
    except (TypeError, ValueError):  # pragma: no cover - the generator writes valid dates
        when = datetime(2026, 1, 5, 9, tzinfo=UTC)
    if when.tzinfo is None:  # pragma: no cover
        when = when.replace(tzinfo=UTC)
    return int(when.timestamp() * 1000)


def mailbox_of(manifest: Manifest) -> tuple[SyntheticMailbox, VerificationReport]:
    """The manifest's messages as a synthetic mailbox, plus the report that joins the ids."""
    rows: list[Msg] = []
    inserted: list[InsertedMessage] = []
    by_thread: dict[str, list[SeededMessage]] = {}
    for message in manifest.messages:
        by_thread.setdefault(message.thread_key, []).append(message)
    for thread_key, messages in by_thread.items():
        ordered = sorted(messages, key=lambda one: one.position)
        for message in ordered:
            parent = None if message.position == 0 else ordered[message.position - 1]
            rows.append(
                Msg(
                    id=_gmail_id(message),
                    thread_id=f"t-{thread_key}",
                    sender=message.sender,
                    subject=message.subject,
                    body=message.body,
                    internal_date_ms=_epoch_ms(message),
                    to=tuple(message.recipients),
                    rfc822_message_id=message.rfc822_message_id,
                    in_reply_to=None if parent is None else parent.rfc822_message_id,
                    references=None
                    if parent is None
                    else " ".join(one.rfc822_message_id for one in ordered[: message.position]),
                )
            )
            inserted.append(
                InsertedMessage(
                    rfc822_message_id=message.rfc822_message_id,
                    gmail_id=_gmail_id(message),
                    thread_id=f"t-{thread_key}",
                )
            )
    latest = max(row.internal_date_ms for row in rows)
    box = SyntheticMailbox(messages=tuple(rows), now_ms=latest + 86_400_000)
    report = VerificationReport(inserted=tuple(inserted), discrepancies=())
    return box, report


def _probe_anchors(manifest: Manifest) -> tuple[str | None, str | None]:
    """Find a message that is *surfaced and not disclosed* until expansion carries it.

    Four harness tests are about the stage between a first response naming a message and a
    caller actually receiving it. Whether a given message has that shape depends on the
    mailbox, the ladder and the disclosure ceiling - none of which the case-file builder can
    see - and it moved the moment the corpus stopped being uniform. So the fixture probes here,
    where the mailbox exists, and passes the answer in. The builder stays single-implementation;
    only the choice of anchor is injected.
    """
    import re
    from collections import Counter

    from mailweave_harness.evaluation.arms import run_all
    from mailweave_harness.evaluation.cases import resolve_against

    box, report = mailbox_of(manifest)
    arm = dummy_arms(manifest, box)[0]
    lengths = manifest.answer_key.thread_lengths

    def prose(message: SeededMessage) -> list[str]:
        return re.findall(r"[A-Za-z]{5,}", re.sub(r"\n-- \n.*$", "", message.body, flags=re.S))

    frequency: Counter[str] = Counter()
    for message in manifest.messages:
        frequency.update(set(prose(message)))

    def has_shape(message: SeededMessage, word: str) -> bool:
        opening = re.sub(r"\n-- \n.*$", "", message.body, flags=re.S).splitlines()[0][:60]
        case = CaseFile.model_validate(
            {
                "schema_version": "1",
                "generator_version": manifest.generator_version,
                "master_seed": manifest.master_seed,
                "cases": [
                    {
                        "case_id": "probe",
                        "template_id": "PROBE",
                        "family": "semantic_paraphrase",
                        "seed": manifest.master_seed,
                        "query": f"{word} zzqnolexicalmatch",
                        "evidence": [
                            {
                                "ref": f"thread:{message.thread_key}/pos:{message.position}",
                                "rfc_message_id": message.rfc822_message_id,
                                "role": "primary",
                                "quote": opening,
                            }
                        ],
                        "evidence_cardinality": "single",
                        "expected_behavior": {
                            "must_retrieve": ["primary"],
                            "acceptable_not_found": False,
                            "partiality_expected": True,
                            "notes": "probe",
                        },
                        "scoring": {"recall_rule": "probe"},
                    }
                ],
            }
        )
        try:
            run = run_all(
                [arm],
                [resolve_against(one, manifest=manifest, report=report) for one in case.cases],
            )[0]
        except Exception:
            return False
        # The shape is *named by the first response, not disclosed by it, carried after
        # expansion*. All three, stated: the middle clause used to be implied by the third,
        # because a one-hop driver could only reach what the first response named. The driver
        # now reads every response it obtains (R-M2-078), so expansion can carry a message the
        # first response never named - a different shape, and not the one these tests are
        # about.
        named = set(run.disclosure.surfaced_ids)
        required = {message_id for one in case.cases for message_id in
                    resolve_against(one, manifest=manifest, report=report).required}
        return (
            required <= named
            and not run.reach.first_response
            and bool(run.reach.after_expansion)
        )

    from mailweave.envelope.reasons import WindowOffset
    from mailweave.surface.arguments import parse_search

    fixed = next(one for one in dummy_arms(manifest, box) if one.name == "fixed-window")

    def fills_a_window(word: str) -> bool:
        try:
            envelope = fixed.service.search(parse_search({"query": word}))
        except Exception:
            return False
        return any(
            isinstance(row.reason, WindowOffset)
            for source in envelope.sources
            for row in source.messages
        )

    # Both searches are bounded. Each candidate costs a full search over the corpus, and an
    # unbounded scan for a shape that no longer exists took minutes before reporting nothing.
    budget = 25
    window: str | None = None
    for message in sorted(
        manifest.messages,
        key=lambda one: (lengths[one.thread_key], one.position, one.rfc822_message_id),
    ):
        length = lengths[message.thread_key]
        if not (10 <= length <= 18 and 3 <= message.position <= length - 3):
            continue
        rare = [one for one in set(prose(message)) if frequency[one] <= 10]
        if not rare:
            continue
        budget -= 1
        if budget < 0:
            break
        if fills_a_window(min(rare, key=lambda one: (frequency[one], -len(one), one))):
            window = message.rfc822_message_id
            break

    # The bar is "rare enough to reach one conversation", not "unique". As ordinary traffic got
    # richer the number of corpus-unique words fell and this probe ran out of candidates
    # entirely - the search is for a *shape*, so it should search over anything that might have
    # it rather than over a proxy for it.
    budget = 25
    escalation: str | None = None
    for message in sorted(
        manifest.messages, key=lambda one: (one.position, -lengths[one.thread_key])
    ):
        if message.position == 0 or lengths[message.thread_key] < 8:
            continue
        rare = sorted(
            {one for one in set(prose(message)) if frequency[one] <= 10},
            key=lambda one: (frequency[one], -len(one), one),
        )
        if not rare:
            continue
        budget -= 1
        if budget < 0:
            break
        if any(has_shape(message, one) for one in rare[:2]):
            escalation = message.rfc822_message_id
            break
    return escalation, window


def dummy_case_file(manifest: Manifest) -> CaseFile:
    """The sentinel-token case file, over the dummy corpus.

    One implementation, in `evaluation.selftest`, because the live self-check builds the same
    thing against the real corpus and a second copy here would be the shape this project keeps
    finding: two constructions of the same artifact, the second one the one nobody updates.
    """
    escalation, window = _probe_anchors(manifest)
    return sentinel_case_file(manifest, escalation=escalation, window=window)


class _WordBackend:
    """A deterministic stand-in: a bag-of-words vector over the corpus's own vocabulary.

    No weights, no network, no claim about retrieval. It exists so the semantic arm *runs* -
    the counting proxy has something to count and L5/L6 have something to score - which is
    what the development loop needs and all it needs.
    """

    model_id = "dummy/word"
    model_revision = "0" * 40

    def __init__(self, vocabulary: Sequence[str]) -> None:
        self._vocabulary = tuple(vocabulary)

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        return [
            tuple(float(text.lower().count(word)) for word in self._vocabulary) for text in texts
        ]

    def rerank(self, query: str, candidates: Sequence[str]) -> list[float]:
        wanted = set(query.lower().split())
        return [
            float(sum(1 for word in candidate.lower().split() if word in wanted))
            for candidate in candidates
        ]


def _service(
    box: SyntheticMailbox,
    registry: BackendRegistry,
    *,
    selector: Selector | None = None,
    log: FetchLog | None = None,
    cross_encoder: bool = True,
) -> MailweaveService:
    def open_client() -> GmailClient:
        inner = box.transport()
        return GmailClient(
            token=StaticToken(TOKEN),
            http=build_client(inner=inner if log is None else FetchObserver(inner, log)),
            meter=CallMeter(),
            policy=BackoffPolicy(),
            sleeper=lambda _seconds: None,
            jitterer=lambda: 0.5,
        )

    return MailweaveService(
        open_client=open_client,
        account_hash=ACCOUNT,
        handle_key=HandleKey(material=b"k" * 32, epoch=0),
        cache=ThreadMapCache(),
        now=lambda: datetime.now(UTC),
        registry=registry,
        selector=selector,
        cross_encoder=cross_encoder,
    )


def dummy_arms(
    manifest: Manifest,
    box: SyntheticMailbox,
    *,
    specs: Sequence[ArmSpec] = SPECS,
    traces: Path | None = None,
) -> tuple[Arm, ...]:
    """The factorial over the dummy corpus, one `Arm` per spec.

    Each arm is built through the same `MailweaveService` construction, differing only in the
    factors the specs name: whether a backend is registered, whether D.7's second tier is
    present, and which disclosure selector is installed. **No arm here is the released v0.1** -
    `arms.py`'s module docstring lists what a no-backend run still carries that v0.1 did not.

    `traces` attaches a real `TraceSink` per arm, under its own root, exactly as the campaign
    runner does. It is a parameter rather than always-on because a trace is a file written to
    disk and a fixture that wrote one unasked would be making that choice for every test that
    imports it - but the dry run passes it, so the instrumentation the campaign depends on is
    exercised offline rather than first meeting a real mailbox.
    """
    vocabulary = sorted({word for one in manifest.messages for word in one.body.lower().split()})[
        :24
    ]
    built: list[Arm] = []
    for spec in specs:
        registry = BackendRegistry()
        counter: CountingBackend | None = None
        if spec.semantic:
            counter = CountingBackend(_WordBackend(vocabulary))
            registry.register("dummy", lambda made=counter: made, default=True)
        log = FetchLog()
        service = _service(
            box,
            registry,
            selector=FixedWindow() if spec.fixed_window else None,
            log=log,
            # H2's bypass arm. The backend is still registered and still embeds - only D.7's
            # second tier is absent - so `no-rerank` and `full` share a pool and a shortlist.
            cross_encoder=spec.cross_encoder,
        )
        # RR-06. The same constructor the campaign uses, so whatever the dry run establishes
        # is established about the arms the campaign runs. It was two independent copies, and
        # the differences between them were exactly where the instrument gaps were.
        built.append(
            build_arm(spec, service, counter=counter, traces_root=traces, fetch_log=log)
        )
    return tuple(built)


def _unused(backend: SemanticBackend) -> SemanticBackend:  # pragma: no cover
    """Kept so the protocol import is load-bearing rather than decorative."""
    return backend


__all__ = [
    "dummy_arms",
    "dummy_case_file",
    "dummy_manifest",
    "mailbox_of",
]
