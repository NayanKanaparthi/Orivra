"""The corpus, assembled from the family builders.

`generate` no longer decides what any message says. It allocates situations, runs one builder
per registered family, and then does the four things that are the same for every family:
threads the messages, dates them, gives each one a reference, and writes the manifest.

**Every message carries a reference of the same shape.** The previous generator appended
`Reference token: <sentinel>` to the ninety-six messages that carried an answer and to nothing
else, so `grep "Reference token"` selected the answer-bearing message in ninety-six of
ninety-six cases with no false positives and solved eight families without possessing any
mechanism under test (R-M2-046). Indexing verification still needs a token per message that the
settle gate can poll and a recall metric can join on, and that need is met by giving *all* of
them one. A marker every message carries distinguishes nothing. The reference is also opaque -
a digest rather than the thread and position - so it does not leak the structure it sits in.

Ground truth lives in the manifest and nowhere else: which message is evidence, what the answer
is, why each distractor is wrong. None of it is in a body.
"""

from __future__ import annotations

import base64
import datetime as dt
import email.utils
import random
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Final, Mapping

from . import families as fam
from .drafts import Chronology, ThreadDraft
from .manifest import AnswerKey, Manifest, SeededMessage, ThreadTruth
from .world import BY_KEY, DOMAIN, EPOCH

#: Bumped because no corpus from version 2 is comparable with one from this version: the
#: families are built rather than templated, the references are uniform, and the dates run
#: forwards. A shared version number across that change would make the regeneration contract
#: a claim about two different functions.
GENERATOR_VERSION: Final[str] = "3"

#: EP §3.8. A conversation at or past this splits server-side, which moves evidence into a
#: conversation the manifest does not describe.
CONVERSATION_CEILING: Final[int] = 100


@dataclass(frozen=True)
class SizeProfile:
    """One corpus shape, stated as family counts rather than as a thread total.

    The field that matters is `family_counts`, keyed by EP family id. A profile now says how
    many *cases* of each registered family it intends, and `generate` fails if a builder cannot
    produce them. The previous profile named nine families against a register of seventeen and
    nothing noticed (R-M2-054).
    """

    name: str
    family_counts: Mapping[str, int]
    long_length: int
    filler_threads: int
    short_threads: int
    situations: int

    def __post_init__(self) -> None:
        unknown = sorted(set(self.family_counts) - set(fam.REGISTERED_N))
        if unknown:
            raise ValueError(
                f"{self.name}: {unknown} are not registered families. EP §4.3 and §4.7 "
                f"register {sorted(fam.REGISTERED_N)}"
            )
        absent = sorted(set(fam.REGISTERED_N) - set(self.family_counts))
        if absent:
            raise ValueError(
                f"{self.name}: no count for {absent}. A profile that silently omits a family "
                "produces a corpus whose coverage report has nothing to measure, which is how "
                "four families came to have zero threads"
            )
        over = {
            key: count for key, count in self.family_counts.items()
            if count > fam.REGISTERED_N[key]
        }
        if over:
            raise ValueError(
                f"{self.name}: {over} exceed their registered counts "
                f"{ {key: fam.REGISTERED_N[key] for key in over} }"
            )
        if self.long_length >= CONVERSATION_CEILING:
            raise ValueError(
                f"{self.name}: long threads of {self.long_length} reach the "
                f"{CONVERSATION_CEILING}-message ceiling of EP §3.8 and would be split "
                "server-side into conversations the manifest does not describe"
            )
        if self.long_length < 40:
            raise ValueError(
                f"{self.name}: at {self.long_length} messages the seven sweep fractions do not "
                "land on seven distinct positions, so the position adversary measures one "
                "position several times"
            )
        landed = {fam.sweep_position(self.long_length, one) for one in fam.SWEEP_FRACTIONS}
        if len(landed) != len(fam.SWEEP_FRACTIONS):
            raise ValueError(f"{self.name}: sweep fractions collide at length {self.long_length}")

    @property
    def registered_cases(self) -> int:
        return sum(self.family_counts.values())


def _counts(**overrides: int) -> dict[str, int]:
    return {key: overrides.get(key, value) for key, value in fam.REGISTERED_N.items()}


#: `sample` is the small offline corpus the repair brief asks for before anything scales: every
#: family present, all seven sweep fractions present, small enough to be read by a person.
#: `smoke` is EP §4.2's dev profile. `gate` is the registered corpus, at §4.4's length-90
#: fallback - the sweep fractions land on {2, 6, 18, 33, 46, 75, 89} there, which is exactly the
#: rescaled list §4.4 names, and 90 is the longest conversation the live mailbox has been shown
#: to thread correctly.
PROFILES: Final[dict[str, SizeProfile]] = {
    "sample": SizeProfile(
        name="sample",
        family_counts=_counts(
            F1=2, F2=2, F3=7, F4=2, F5=2, F6=2, F7=2, F8=2, F10=2, F11=2, F12=2,
            F13=2, F14=2, F15=4, F16=2, F17=2,
        ),
        long_length=90, filler_threads=10, short_threads=6, situations=150,
    ),
    "smoke": SizeProfile(
        name="smoke",
        family_counts=_counts(
            F1=3, F2=3, F3=21, F4=3, F5=2, F6=2, F7=2, F8=2, F10=3, F11=3, F12=3,
            F13=2, F14=2, F15=4, F16=2, F17=2,
        ),
        long_length=90, filler_threads=14, short_threads=8, situations=215,
    ),
    "gate": SizeProfile(
        name="gate",
        family_counts=_counts(),
        long_length=90, filler_threads=40, short_threads=12, situations=460,
    ),
}


def _shape_rng(generator_version: str, size_profile: str) -> random.Random:
    """The generator that decides shape. **It is not given the master seed.**

    EP §5.3 requires thread lengths and evidence positions to hold across seeds so that a
    system cannot be tuned to one corpus's geometry, while bodies and references re-randomise
    so it cannot be tuned to one corpus's words. Passing the master seed in here would make
    the geometry move with the surface and quietly remove the lever.
    """
    return random.Random(f"{generator_version}:{size_profile}")


def _reference(master_seed: int, generator_version: str, index: int) -> str:
    """One opaque, unique, uniform per-message token.

    Opaque so it does not leak the position it sits at; uniform so it does not say what the
    message is; seeded so two corpora from different seeds never collide in one mailbox, which
    was R-M2-044.
    """
    digest = sha256(f"{generator_version}:{master_seed}:{index}".encode("utf-8")).hexdigest()
    return "mw" + digest[:14]


def _message_id(master_seed: int, thread_index: int, position: int) -> str:
    """Opaque, and that is the repair.

    The first version spelled the thread and the position into the Message-ID
    (`<mw3.4311.0027.0089@...>`). Unlike `role` or `is_distractor`, which stay in the manifest,
    the Message-ID is inserted into the mailbox - so anything that reads headers could sort a
    conversation, find its last message or spot a sweep position without retrieving anything.
    An independent reader found it. The digest is still deterministic, so the regeneration
    contract holds, and still unique, so threading is unaffected.
    """
    digest = sha256(f"id:{master_seed}:{thread_index}:{position}".encode("utf-8")).hexdigest()
    return f"<mw3.{digest[:24]}@{DOMAIN}>"


def _body(text: str, sender_key: str, reference: str) -> str:
    return f"{text}\n-- \n{BY_KEY[sender_key].display}\nRef {reference}"


def _drafts(
    profile: SizeProfile, master_seed: int
) -> tuple[list[ThreadDraft], dict[str, object]]:
    context = fam.make_context(
        master_seed,
        situations_needed=profile.situations,
        long_length=profile.long_length,
        shape_key=f"{GENERATOR_VERSION}:{profile.name}",
    )
    out: list[ThreadDraft] = []
    for key in sorted(profile.family_counts, key=lambda one: int(one[1:])):
        count = profile.family_counts[key]
        if count:
            out.extend(fam.with_tail(context, fam.BUILDERS[key](context, count)))
    out.extend(fam.build_filler(context, profile.filler_threads))
    out.extend(fam.build_short(context, profile.short_threads))
    # Every entity a paraphrase-consuming family relies on gets its colloquial name introduced
    # somewhere in the corpus.
    # **Every colloquial name that appears in a scored conversation**, not only the ones a
    # query is written from. An audit found ten aliases used by decoys and never introduced -
    # a decoy naming something the reader cannot resolve is not a decoy.
    from .world import ENTITIES as _ENTITIES

    scored = "\n".join(
        one.text for draft in out if draft.family for one in draft.lines
    )
    needs_alias = {
        entity.key for entity in _ENTITIES if entity.plain in scored
    }
    # Six introductions per conversation, one conversation per six scored threads: enough
    # slots for every colloquial name a scored conversation uses, computed from a count the
    # profile fixes rather than from which entities this seed happened to draw.
    conversations = -(-sum(1 for one in out if one.family) // 6)
    out.extend(fam.build_bridges(context, needs_alias, conversations))
    fam.with_routine_attachments(context, out)
    return out, {one.key: one for one in context.pool}


def generate(
    *,
    generator_version: str = GENERATOR_VERSION,
    master_seed: int,
    size_profile: str = "sample",
) -> Manifest:
    """The corpus, the manifest and the answer key, from three inputs and nothing else."""
    if size_profile not in PROFILES:
        raise ValueError(
            f"unknown size profile {size_profile!r}; this build ships {sorted(PROFILES)}"
        )
    profile = PROFILES[size_profile]
    drafts, situations = _drafts(profile, master_seed)
    shape = _shape_rng(generator_version, size_profile)
    clock = Chronology()
    messages: list[SeededMessage] = []
    truths: list[ThreadTruth] = []
    owner: dict[str, str] = {}
    counter = 0
    probe: list[str] = []
    #: Where each conversation ended, so a continuation starts after it. `Chronology` enforces
    #: order *within* a thread; an audit found three of four F15 continuations starting before
    #: their parent finished, one of them by 117 days, which inverts the shape the family is
    #: built on - the superseded position ended up being the newest message in the scenario.
    ended: dict[str, dt.datetime] = {}
    for thread_index, draft in enumerate(drafts):
        key = f"t{thread_index:04d}"
        stamps = clock.stamp(draft)
        after = ended.get(draft.continues) if draft.follows_parent else None
        if after is not None and stamps[0] <= after:
            shift = (after - stamps[0]) + dt.timedelta(days=2)
            stamps = tuple(one + shift for one in stamps)
        ended[draft.situation_key] = stamps[-1]
        cast = draft.participants or tuple({one.sender for one in draft.lines})
        ids: list[str] = []
        chains: list[tuple[str, ...]] = []
        roles: dict[str, list[int]] = {}
        evidence: list[int] = []
        for position, (line, when) in enumerate(zip(draft.lines, stamps)):
            reference = _reference(master_seed, generator_version, counter)
            counter += 1
            message_id = _message_id(master_seed, thread_index, position)
            recipients = tuple(
                BY_KEY[one].address for one in cast if one != line.sender
            ) or (BY_KEY[line.sender].address,)
            # **Replies branch.** Every conversation used to be a straight chain, so
            # `len(references)` equalled the position in 1,473 messages of 1,473 and the reply
            # graph was the position vector written a second time - which an audit reported as
            # a header-level position oracle, and which left F13 with no reply relationship to
            # reason about at all. A reply now answers a recent message rather than always the
            # last one, drawn from the shape generator so the graph holds across seeds.
            # A builder that knows what answers what says so, and that wins over the draw.
            # F13 is registered for "ordering **plus reply-relationship** reasoning, not date
            # filtering alone", and without this its conversations are strict chains: the reply
            # graph is the position vector written a second time, which an independent reader
            # reported twice before this landed.
            if position and line.replies_to is not None:
                parent_index = min(max(0, line.replies_to), position - 1)
                parent = ids[parent_index]
                references = chains[parent_index] + (parent,)
            elif position:
                # Mostly the previous message, sometimes one further back. Real threads look
                # like this, and a uniform draw over the last four changed the shape of the
                # conversation enough that the fixed-window baseline stopped filling windows
                # at all - a behaviour change in the thing being measured, caused by the
                # corpus rather than by the code.
                far = min(position, 4)
                back = 1 if (shape.random() < 0.75 or far < 2) else shape.randrange(2, far + 1)
                back = min(back, position)
                parent_index = position - back
                parent = ids[parent_index]
                references = chains[parent_index] + (parent,)
            else:
                parent = None
                references = ()
            messages.append(
                SeededMessage(
                    rfc822_message_id=message_id,
                    thread_key=key,
                    position=position,
                    sender=BY_KEY[line.sender].address,
                    recipients=recipients,
                    subject=line.subject_override or draft.subject,
                    date_rfc2822=email.utils.format_datetime(
                        when.replace(tzinfo=dt.timezone.utc)
                    ),
                    body=_body(line.text, line.sender, reference),
                    sentinels=(reference,),
                    is_distractor=line.is_distractor,
                    in_reply_to=parent,
                    references=references,
                    role=line.role,
                    scenario_key=draft.situation_key,
                    attachments=line.attachments,
                )
            )
            owner[reference] = message_id
            ids.append(message_id)
            chains.append(references)
            roles.setdefault(line.role, []).append(position)
            if line.role in {"evidence", "authored_claim", "confirmation", "reversal",
                             "attachment_cover"}:
                evidence.append(position)
        base = "::".join(draft.situation_key.split("::")[:2])
        situation = situations.get(base)
        # Two per conversation, by position. See `AnswerKey.settle_probe` for why it is not
        # by role.
        first_reference = messages[-len(draft.lines)].sentinels[0]
        probe.append(first_reference)
        if len(draft.lines) > 1:
            probe.append(messages[-1].sentinels[0])
        if draft.evidence_at:
            evidence = list(draft.evidence_at)
        truths.append(
            ThreadTruth(
                answer=(
                    draft.answer_override
                    if draft.answer_override is not None
                    else getattr(situation, "answer", "")
                ),
                wrong_value=(
                    draft.wrong_override
                    if draft.wrong_override is not None
                    else getattr(situation, "wrong", "")
                ),
                older_value=(
                    draft.older_override
                    if draft.older_override is not None
                    else getattr(situation, "older", "")
                ),
                facts=dict(draft.facts),
                thread_key=key,
                length=len(draft.lines),
                subject=draft.subject,
                evidence_positions=tuple(evidence),
                family=draft.family,
                scenario_key=draft.situation_key,
                roles_at={name: tuple(at) for name, at in roles.items()},
                participants=cast,
                answer_note=draft.answer_note,
                continues=draft.continues,
                orphan=draft.orphan,
                cross_thread_decoy_for=draft.cross_thread_decoy_for,
                has_alias_bridge=any(
                    "are the same thing" in one.text for one in draft.lines
                ),
                follows_parent=draft.follows_parent,
                first_date=stamps[0].date().isoformat(),
                last_date=stamps[-1].date().isoformat(),
                paraphrase_of_fact=draft.paraphrase_of_fact,
            )
        )
    # A declared value that occurs in no message names nothing: an audit found twenty-seven of
    # them, including two decoy threads whose `answer` was absent from the entire corpus. What
    # a thread declares is now what its messages say.
    from .world import states as _states

    # Attachment content counts: F8's answer is deliberately in the file and in no body, so a
    # bodies-only scan would blank the very values that family is built on.
    # **Scoped to the conversation and its sibling**, not to the corpus. A value that occurs
    # somewhere else entirely is not a distractor for this case: an audit found declared
    # competitors absent from the query's scope in 28 case threads of 51, including every F7
    # and F12 case.
    scope: dict[str, str] = {}
    for message in messages:
        scope[message.thread_key] = "\n".join(
            [scope.get(message.thread_key, ""), message.body]
            + [part.content for part in message.attachments]
        )
    by_situation: dict[str, list[str]] = {}
    for one in truths:
        by_situation.setdefault("::".join(one.scenario_key.split("::")[:2]), []).append(
            one.thread_key
        )

    def _visible(one: ThreadTruth, value: str) -> bool:
        base = "::".join(one.scenario_key.split("::")[:2])
        return any(
            _states(value, scope.get(key, "")) for key in by_situation.get(base, ())
        )

    truths = [
        one.model_copy(
            update={
                "wrong_value": one.wrong_value if _visible(one, one.wrong_value) else "",
                "older_value": one.older_value if _visible(one, one.older_value) else "",
            }
        )
        for one in truths
    ]

    return Manifest(
        generator_version=generator_version,
        master_seed=master_seed,
        size_profile=size_profile,
        messages=tuple(messages),
        answer_key=AnswerKey(
            sentinel_owner=owner, threads=tuple(truths), settle_probe=tuple(probe)
        ),
    )


def rfc2822(message: SeededMessage) -> str:
    """One message as the RFC 2822 text `messages.insert` takes.

    Hand-built rather than assembled with `email.message.EmailMessage`, because the byte
    identity the regeneration contract claims has to be a property of *this* function: a
    library that changed its header ordering or its line folding between versions would
    change the corpus without the generator version moving.
    """
    headers = [
        f"Message-ID: {message.rfc822_message_id}",
        f"Date: {message.date_rfc2822}",
        f"From: {message.sender}",
        f"To: {', '.join(message.recipients)}",
        f"Subject: {message.subject}",
        "MIME-Version: 1.0",
    ]
    if message.in_reply_to is not None:
        headers.append(f"In-Reply-To: {message.in_reply_to}")
    if message.references:
        headers.append(f"References: {' '.join(message.references)}")
    body = message.body.replace("\n", "\r\n")
    if not message.attachments:
        headers += [
            'Content-Type: text/plain; charset="utf-8"',
            "Content-Transfer-Encoding: 8bit",
        ]
        return "\r\n".join(headers) + "\r\n\r\n" + body + "\r\n"

    # **`multipart/mixed`, hand-built for the same reason the rest of this function is.** The
    # boundary is derived from the message id rather than drawn, so the byte identity the
    # regeneration contract claims survives attachments. F8 was unauthorable before this: the
    # generator emitted a single text/plain part and there was nothing in any mailbox for an
    # attachment case to retrieve (R-M2-041).
    boundary = "mw-" + sha256(message.rfc822_message_id.encode("utf-8")).hexdigest()[:24]
    headers += [f'Content-Type: multipart/mixed; boundary="{boundary}"']
    parts = [
        "\r\n".join(
            [
                'Content-Type: text/plain; charset="utf-8"',
                "Content-Transfer-Encoding: 8bit",
                "",
                body,
            ]
        )
    ]
    for attachment in message.attachments:
        encoded = base64.b64encode(attachment.content.encode("utf-8")).decode("ascii")
        wrapped = "\r\n".join(encoded[at : at + 76] for at in range(0, len(encoded), 76))
        parts.append(
            "\r\n".join(
                [
                    f'Content-Type: {attachment.media_type}; name="{attachment.filename}"',
                    "Content-Transfer-Encoding: base64",
                    f'Content-Disposition: attachment; filename="{attachment.filename}"',
                    "",
                    wrapped,
                ]
            )
        )
    rendered = f"\r\n--{boundary}\r\n".join(parts)
    return (
        "\r\n".join(headers)
        + "\r\n\r\n"
        + f"--{boundary}\r\n"
        + rendered
        + f"\r\n--{boundary}--\r\n"
    )


def corpus_bytes(manifest: Manifest) -> bytes:
    """The whole corpus as one byte string, for the regeneration contract's own assertion."""
    return "".join(rfc2822(message) for message in manifest.messages).encode("utf-8")


__all__ = [
    "CONVERSATION_CEILING",
    "GENERATOR_VERSION",
    "PROFILES",
    "SizeProfile",
    "corpus_bytes",
    "generate",
    "rfc2822",
]
