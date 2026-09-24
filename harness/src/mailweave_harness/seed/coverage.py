"""Whether the registered families can actually be authored from a corpus.

**This file is a repair of itself.** The previous version reported every one of the seventeen
families met, and an independent reader who was told not to run it found ten of them
unauthorable. It passed because seven of its rules had no failing case: F1, F2 and F12 each
counted the same ninety-six sentinel-carrying messages under three descriptions; F13 and F14
counted "threads carrying dated events" and "threads with three or more participants", which is
every thread; F15 counted threads long enough for structure to be *a question*; F10 granted
itself; and F3 multiplied the number of threads in which seven fractions *could* land by seven
and reported 567 against a registered 84 while the corpus planted 24. It took its denominator
from the allocation it was auditing (R-M2-045), which is R-M2-034 one level up.

So the rules here are written to a single standard: **a rule must name a property of the text,
and a corpus that lacks that property must fail it.** `tests/test_coverage_rules.py` holds one
negative fixture per rule - a manifest mutated to remove exactly the property - and asserts the
rule rejects it. A rule with no negative fixture is not shipped; `RULES_WITHOUT_NEGATIVES` is
checked by that test and must be empty.

The count a family reports is the number of threads that trigger **no finding**, not the number
of threads that declare the family. A declaration is what the generator intended; a finding is
what the text does or does not do.

Two standing limits, stated rather than implied. A passing report is not a substitute for an
independent read: it checks the properties someone thought to check, and the last version's
failure was entirely in properties nobody had. And `_no_discriminating_token` is a detector with
thresholds, so it demonstrates the presence of an oracle and never the absence of one.
"""

from __future__ import annotations

import datetime as dt
import email.utils
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Callable, Final, Sequence

from . import lexical, voice
from .drafts import EVIDENCE_ROLES
from .families import FAMILY_NAMES, REGISTERED_N, SWEEP_FRACTIONS
from .manifest import Manifest, SeededMessage, ThreadTruth
from .world import BY_ENTITY, BY_KEY, content_words, jaccard, states

#: The roles a builder plants to compete with an answer. Used by the per-case distractor rule;
#: kept beside `EVIDENCE_ROLES` so "answer-bearing" and "planted to compete" stay one decision.
_DISTRACTOR_ROLES: Final[frozenset[str]] = frozenset(
    {"trap_decoy", "paraphrase_decoy", "near_duplicate", "hearsay", "reinforcement",
     "proposal", "objection", "reminder", "attachment_wrong_version"}
)


@dataclass(frozen=True)
class Finding:
    rule: str
    family: str
    where: str
    detail: str


@dataclass
class View:
    """A manifest indexed the way the rules need to read it."""

    manifest: Manifest

    def __post_init__(self) -> None:
        self.by_thread: dict[str, list[SeededMessage]] = defaultdict(list)
        for message in self.manifest.messages:
            self.by_thread[message.thread_key].append(message)
        for group in self.by_thread.values():
            group.sort(key=lambda one: one.position)
        self.truth: dict[str, ThreadTruth] = {
            one.thread_key: one for one in self.manifest.answer_key.threads
        }

    def family(self, key: str) -> list[ThreadTruth]:
        return [one for one in self.manifest.answer_key.threads if one.family == key]

    def primary(self, key: str) -> list[ThreadTruth]:
        """Threads that *are* a case, as opposed to a case's second half or its decoy."""
        return [
            one for one in self.family(key)
            if not one.continues and not one.cross_thread_decoy_for
        ]

    def bodies(self, key: str) -> list[str]:
        return [one.body for one in self.by_thread[key]]

    def at(self, key: str, position: int) -> SeededMessage | None:
        group = self.by_thread[key]
        return group[position] if 0 <= position < len(group) else None

    def roles(self, key: str, role: str) -> list[SeededMessage]:
        return [one for one in self.by_thread[key] if one.role == role]

    def when(self, message: SeededMessage) -> float:
        return email.utils.parsedate_to_datetime(message.date_rfc2822).timestamp()


def _values(truth: ThreadTruth) -> set[str]:
    """Every candidate value declared for a thread, so a skeleton comparison masks them all."""
    declared = {truth.answer, truth.wrong_value, truth.older_value}
    declared |= set(truth.facts.get("revision_values", "").split("|"))
    return {one for one in declared if one}


def _fact(truth: ThreadTruth, name: str) -> str:
    return truth.facts.get(name, "")


def _int(truth: ThreadTruth, name: str, default: int = -1) -> int:
    raw = _fact(truth, name)
    return int(raw) if raw.lstrip("-").isdigit() else default


def _strip_reference(body: str) -> str:
    return re.sub(r"\n-- \n.*$", "", body, flags=re.S).strip()


def _unframed(body: str) -> str:
    """A body with the shared lead-in and closer removed.

    Every message is framed the same way, so the frame carries no information and a rule that
    compares two messages has to compare what is left. Without this, F16's near-duplicates read
    as different sentences because they opened differently, which is the frame doing its job.
    """
    text = _strip_reference(body)
    for phrase in voice.LEAD_INS:
        if text.startswith(phrase):
            text = text[len(phrase):].strip()
            break
    for phrase in voice.CLOSERS:
        if text.endswith(phrase):
            text = text[: -len(phrase)].strip()
            break
    return text


# ------------------------------------------------------------------------------ corpus rules

def _uniform_reference(view: View) -> list[Finding]:
    """Every message carries exactly one reference, so carrying one says nothing.

    Rejects: a corpus where the marker is on the answers. The old corpus put it on 96 messages,
    all of which were evidence and none of which were distractors.
    """
    found: list[Finding] = []
    missing = [one for one in view.manifest.messages if len(one.sentinels) != 1]
    if missing:
        found.append(Finding(
            "uniform_reference", "corpus", "corpus",
            f"{len(missing)} message(s) do not carry exactly one reference, starting at "
            f"{missing[0].rfc822_message_id}. A marker only some messages carry is evidence "
            "about which ones they are",
        ))
    evidence = [one for one in view.manifest.messages if one.role in EVIDENCE_ROLES]
    other = [one for one in view.manifest.messages if one.role not in EVIDENCE_ROLES]
    if evidence and other:
        on_evidence = sum(1 for one in evidence if one.sentinels) / len(evidence)
        on_other = sum(1 for one in other if one.sentinels) / len(other)
        if abs(on_evidence - on_other) > 1e-9:
            found.append(Finding(
                "uniform_reference", "corpus", "corpus",
                f"{on_evidence:.1%} of evidence messages carry a reference and "
                f"{on_other:.1%} of the rest do. The difference is the answer key",
            ))
    return found


def _no_discriminating_token(view: View) -> list[Finding]:
    """No word in any body predicts that its message is evidence.

    For every word occurring in at least six messages, the rule measures how often a message
    containing it is evidence and how much of the evidence it reaches. A word that is almost
    always on evidence and reaches much of it is an oracle: `grep <word>` answers the corpus.

    Rejects: the old corpus, where `token` reached 100% of evidence at 100% precision.
    **A detector, not a proof.** Passing means no oracle of this shape was found at these
    thresholds; it cannot mean none exists.
    """
    precision_bar, recall_bar, floor = 0.90, 0.20, 6
    evidence_ids = {
        one.rfc822_message_id for one in view.manifest.messages if one.role in EVIDENCE_ROLES
    }
    if not evidence_ids:
        return []
    holders: dict[str, set[str]] = defaultdict(set)
    for message in view.manifest.messages:
        for word in set(re.findall(r"[a-z]{4,}", _strip_reference(message.body).lower())):
            holders[word].add(message.rfc822_message_id)
    found: list[Finding] = []
    for word, ids in holders.items():
        if len(ids) < floor:
            continue
        hits = ids & evidence_ids
        precision = len(hits) / len(ids)
        recall = len(hits) / len(evidence_ids)
        if precision >= precision_bar and recall >= recall_bar:
            found.append(Finding(
                "no_discriminating_token", "corpus", "corpus",
                f"the word {word!r} occurs in {len(ids)} messages, {precision:.0%} of which "
                f"are evidence, and reaches {recall:.0%} of all evidence. A search for it "
                "answers the corpus without retrieving anything",
            ))
    return sorted(found, key=lambda one: one.detail)[:5]


def _shape_carries_no_signal(view: View) -> list[Finding]:
    """No structural feature of a body predicts that the message was planted to be something.

    **This is the rule that would have caught the defect that collapsed every family.** An
    independent evaluator, using no labels at all, separated the decisive messages from the
    distractor population by counting sentences: filler was always an opener, a topic sentence
    and a closer, and everything planted was a bare one- or two-sentence assertion. Precision
    0.76, recall 0.98, and a ninety-message conversation reduced to four candidates before any
    retrieval ran.

    So each cheap feature a reader could compute - how many sentences, whether it opens with a
    known lead-in, whether it closes with a known closer, whether it contains a digit, how long
    it is - is scored as a classifier for "this message was planted to be something". Any
    feature value that is mostly role-bearing and reaches much of the role-bearing population
    is reported.

    Like `_no_discriminating_token` this is a detector at thresholds, so it demonstrates a
    shortcut and never the absence of one.
    """
    planted = {
        one.rfc822_message_id for one in view.manifest.messages if one.role != "filler"
    }
    if not planted or len(planted) == len(view.manifest.messages):
        return []
    buckets: dict[str, set[str]] = defaultdict(set)
    for message in view.manifest.messages:
        text = _strip_reference(message.body)
        sentences = [one for one in re.split(r"(?<=[.?!])\s+", text) if one.strip()]
        opens = any(text.startswith(one) for one in voice.LEAD_INS)
        closes = any(text.endswith(one) for one in voice.CLOSERS)
        for name in (
            f"sentences={min(len(sentences), 5)}",
            f"opens_with_lead_in={opens}",
            f"ends_with_closer={closes}",
            f"frame={opens}/{closes}",
            f"has_digit={any(one.isdigit() for one in text)}",
            f"length_bucket={min(len(text) // 60, 5)}",
        ):
            buckets[name].add(message.rfc822_message_id)
    # **Lift, not raw precision.** The first version of this rule required precision 0.80 and
    # would therefore have *passed* the defect it is named for, which ran at 0.761. What makes
    # a feature useful to a reader is how far it beats the base rate: planted messages are
    # under a tenth of the corpus, so a bucket that is two fifths planted has already shrunk
    # the search four-fold.
    base = len(planted) / len(view.manifest.messages)
    found: list[Finding] = []
    for name, ids in buckets.items():
        hits = ids & planted
        if not hits:
            continue
        precision = len(hits) / len(ids)
        recall = len(hits) / len(planted)
        lift = precision / base
        if recall >= 0.25 and (lift >= 2.5 or precision >= 0.75):
            found.append(Finding(
                "shape_carries_no_signal", "corpus", "corpus",
                f"the feature {name} covers {len(ids)} messages, {precision:.0%} of which were "
                f"planted to be something against a base rate of {base:.0%} ({lift:.1f}x), and "
                f"reaches {recall:.0%} of everything planted. A reader can shrink every thread "
                "before retrieving anything",
            ))
    return sorted(found, key=lambda one: one.detail)[:4]


def _dates_advance(view: View) -> list[Finding]:
    """Within a conversation, every reply is dated after the message it replies to.

    Rejects: the old corpus, where this failed in 84 threads of 84, taking F2, F5, F13 and F17
    with it. Structural anomalies are untouched: F15's renamed subjects, forwards, orphans and
    splits all still run forwards.
    """
    found: list[Finding] = []
    for key, group in view.by_thread.items():
        stamps = [view.when(one) for one in group]
        backwards = [
            index for index in range(len(stamps) - 1) if stamps[index + 1] <= stamps[index]
        ]
        if backwards:
            found.append(Finding(
                "dates_advance", view.truth[key].family or "(filler)", key,
                f"{len(backwards)} message(s) are dated at or before their parent, first at "
                f"position {backwards[0] + 1}",
            ))
    return found


def _body_diversity(view: View) -> list[Finding]:
    """The corpus is a population, not one message repeated.

    Rejects: the old corpus, whose 2,452 messages held 345 distinct bodies once the boilerplate
    was stripped, 37% of them under forty characters. A thread of ninety-nine identical
    distractors is not a hard retrieval problem.
    """
    texts = [_strip_reference(one.body) for one in view.manifest.messages]
    distinct = len(set(texts)) / len(texts)
    short = sum(1 for one in texts if len(one) < 60) / len(texts)
    found: list[Finding] = []
    if distinct < 0.55:
        found.append(Finding(
            "body_diversity", "corpus", "corpus",
            f"{distinct:.0%} of message bodies are distinct; below 55% the distractor "
            "population is the same message repeated",
        ))
    if short > 0.20:
        found.append(Finding(
            "body_diversity", "corpus", "corpus",
            f"{short:.0%} of bodies are under 60 characters, above the 20% bar",
        ))
    return found


def _distractors_are_wrong(view: View) -> list[Finding]:
    """No distractor states the answer of the thread it sits in.

    A distractor that happens to be right is not a distractor: selecting it is not an error, so
    the case cannot be scored. This caught a trap decoy that named its two "witnesses" by
    display name in a thread whose answer *was* a person's name, which no family-specific rule
    would have looked for.

    **F6's hearsay is the deliberate exception** and is excluded by role: that family plants a
    second-hand report which is correct and still not the answer, because the thing being
    scored is authorship rather than correctness.
    """
    found: list[Finding] = []
    for truth in view.manifest.answer_key.threads:
        if not truth.family or not truth.answer or truth.continues:
            continue
        for message in view.by_thread[truth.thread_key]:
            if not message.is_distractor or message.role == "hearsay":
                continue
            if states(truth.answer, _strip_reference(message.body)):
                found.append(Finding(
                    "distractors_are_wrong", truth.family, truth.thread_key,
                    f"the {message.role} at {message.position} states the answer "
                    f"{truth.answer!r}, so selecting it is not an error",
                ))
    return found


def _siblings_agree(view: View) -> list[Finding]:
    """Two conversations about one matter do not state different answers.

    Rejects: the old corpus, where three threads shared a subject line and carried three
    contradictory complete facts, so the same question had three answers in three places
    (R-M2-050, R-M2-051).
    """
    by_situation: dict[str, set[str]] = defaultdict(set)
    for truth in view.manifest.answer_key.threads:
        # Continuations are excluded: F7's two halves answer with two different things by
        # construction, and F15's sibling carries the answer its original deliberately lacks.
        if truth.family and truth.answer and not truth.continues:
            by_situation["::".join(truth.scenario_key.split("::")[:2])].add(truth.answer)
    found = [
        Finding("siblings_agree", "corpus", base,
                f"threads on one matter declare different answers {sorted(answers)}")
        for base, answers in by_situation.items() if len(answers) > 1
    ]
    by_subject: dict[str, set[str]] = defaultdict(set)
    for truth in view.manifest.answer_key.threads:
        if truth.family and truth.answer and not truth.continues:
            by_subject[truth.subject].add(truth.answer)
    found.extend(
        Finding("siblings_agree", "corpus", subject,
                f"unrelated conversations share a subject line and declare different answers "
                f"{sorted(answers)}, so the subject is actively misleading")
        for subject, answers in by_subject.items() if len(answers) > 1
    )
    return found


# ------------------------------------------------------------------------------ family rules

def _f1(view: View) -> list[Finding]:
    """One identifier in exactly one message, with a real near collision elsewhere."""
    found: list[Finding] = []
    for truth in view.primary("F1"):
        token, near = _fact(truth, "identifier"), _fact(truth, "near_collision")
        holders = [
            one.rfc822_message_id for one in view.manifest.messages if token and token in one.body
        ]
        if len(holders) != 1:
            found.append(Finding("f1_unique_identifier", "F1", truth.thread_key,
                                 f"identifier {token!r} occurs in {len(holders)} messages"))
        if not near or near == token:
            found.append(Finding("f1_near_collision", "F1", truth.thread_key,
                                 "no near-collision identifier, so the family measures the "
                                 "presence of a rare string rather than precise matching"))
        elif not any(near in one.body for one in view.manifest.messages):
            found.append(Finding("f1_near_collision", "F1", truth.thread_key,
                                 f"the near collision {near!r} is in no message"))
    return found


def _f2(view: View) -> list[Finding]:
    """Three qualifying messages inside the window, decoys outside it, with §1.2.2 margins.

    **Read from the declared dates, not reconstructed from an offset.** The first version
    rebuilt each message's day as `window_open - 6 + (its age in days)`, which silently assumed
    the conversation's first message sat six days before the window opened. It did until
    R-M2-072 drew ordinary traffic in ahead of it, and then every margin this rule measured was
    wrong by however many days had been inserted. The window edges are in the manifest as
    dates; so are the messages.
    """
    found: list[Finding] = []
    for truth in view.primary("F2"):
        who = BY_KEY.get(_fact(truth, "subject_person"))
        opened_on, closed_on = _fact(truth, "window_open"), _fact(truth, "window_close")
        if who is None or not opened_on or not closed_on:
            found.append(Finding("f2_window", "F2", truth.thread_key, "no window declared"))
            continue
        opened = dt.datetime.fromisoformat(opened_on).replace(
            tzinfo=dt.timezone.utc).timestamp()
        closed = dt.datetime.fromisoformat(closed_on).replace(
            tzinfo=dt.timezone.utc).timestamp()
        group = view.by_thread[truth.thread_key]
        theirs = [one for one in group if one.sender == who.address]
        theirs_in = [one for one in theirs if opened <= view.when(one) <= closed]
        theirs_out = [one for one in theirs if not opened <= view.when(one) <= closed]
        others_in = [
            one for one in group
            if one.sender != who.address and opened <= view.when(one) <= closed
        ]
        if len(theirs_in) < 2:
            found.append(Finding("f2_qualifying_messages", "F2", truth.thread_key,
                                 f"{len(theirs_in)} messages from {who.display} inside the "
                                 "window; EP §4.3 asks for 2 to 5"))
        if not theirs_out:
            found.append(Finding("f2_same_sender_outside", "F2", truth.thread_key,
                                 "the same sender never writes outside the window, so date "
                                 "filtering is not being tested"))
        if not others_in:
            found.append(Finding("f2_other_sender_inside", "F2", truth.thread_key,
                                 "no other sender writes inside the window, so sender "
                                 "filtering is not being tested"))
        margins = [
            min(abs(view.when(one) - opened), abs(view.when(one) - closed)) / 86400
            for one in theirs
        ]
        if margins and min(margins) < 2:
            found.append(Finding("f2_margins", "F2", truth.thread_key,
                                 f"a qualifying message sits {min(margins):.1f} days from a "
                                 "window edge; EP §1.2.2 requires at least 48 hours"))
    return found


def _f3(view: View) -> list[Finding]:
    """A distinct fact at a declared sweep position, with the three distractor kinds present."""
    found: list[Finding] = []
    threads = view.primary("F3")
    sentences: list[str] = []
    fractions: Counter[int] = Counter()
    for truth in threads:
        at = _int(truth, "evidence_at")
        message = view.at(truth.thread_key, at)
        if message is None or message.role != "evidence":
            found.append(Finding("f3_evidence_at_position", "F3", truth.thread_key,
                                 f"no evidence message at the declared position {at}"))
            continue
        if truth.answer and not states(truth.answer, _strip_reference(message.body)):
            found.append(Finding("f3_evidence_carries_answer", "F3", truth.thread_key,
                                 f"the message at {at} does not state {truth.answer!r}"))
        sentences.append(_strip_reference(message.body))
        fractions[_int(truth, "fraction")] += 1
        kinds = {"paraphrase_decoy", "hearsay", "trap_decoy"}
        present = {one.role for one in view.by_thread[truth.thread_key]} & kinds
        if present != kinds:
            found.append(Finding("f3_distractors", "F3", truth.thread_key,
                                 f"missing distractor kinds {sorted(kinds - present)}; EP §4.3 "
                                 "requires at least three including a same-thread lexical decoy"))
        for decoy in view.by_thread[truth.thread_key]:
            if decoy.role in kinds and states(truth.answer, _strip_reference(decoy.body)):
                found.append(Finding("f3_distractors_are_wrong", "F3", truth.thread_key,
                                     f"the {decoy.role} at {decoy.position} states the answer"))
    duplicates = [text for text, count in Counter(sentences).items() if count > 1]
    if duplicates:
        found.append(Finding(
            "f3_sweep_sentences_distinct", "F3", "corpus",
            f"{len(duplicates)} evidence sentence(s) appear in more than one sweep thread. The "
            "position adversary varies where a fact sits; repeating one sentence across "
            "positions varies nothing (R-M2-049)",
        ))
    if threads:
        expected = set(SWEEP_FRACTIONS)
        missing = sorted(expected - set(fractions))
        if missing and len(threads) >= len(SWEEP_FRACTIONS):
            found.append(Finding("f3_all_fractions", "F3", "corpus",
                                 f"no case at fraction(s) {missing}; §4.4's pass bars bind on "
                                 "every position, not the mean"))
    return found


def _paraphrase_pair(view: View, key: str, rule: str) -> list[Finding]:
    found: list[Finding] = []
    for truth in view.primary(key):
        question = truth.paraphrase_of_fact or _fact(truth, "construction_query")
        evidence = view.at(truth.thread_key, _int(truth, "evidence_at"))
        decoy = view.at(truth.thread_key, _int(truth, "decoy_at"))
        if evidence is None or decoy is None or not question:
            found.append(Finding(rule, key, truth.thread_key,
                                 "no evidence, decoy or question declared"))
            continue
        overlap = jaccard(question, _strip_reference(evidence.body))
        if overlap > 0.0:
            shared = sorted(content_words(question) & content_words(evidence.body))
            found.append(Finding(
                f"{rule}_disjoint", key, truth.thread_key,
                f"question and evidence share {shared} (jaccard {overlap:.2f}); EP §4.5 tier 2 "
                "requires none, and without it the case is reachable lexically",
            ))
        if not content_words(question) & content_words(decoy.body):
            found.append(Finding(
                f"{rule}_decoy_matches", key, truth.thread_key,
                "the decoy shares no content word with the question, so a lexical query never "
                "reaches it and there is no trap",
            ))
        if states(truth.answer, _strip_reference(decoy.body)):
            found.append(Finding(f"{rule}_decoy_is_wrong", key, truth.thread_key,
                                 "the decoy states the true answer"))
    return found


def _f4(view: View) -> list[Finding]:
    """Zero content-word overlap between question and evidence; the decoy takes the lexical hit."""
    return _paraphrase_pair(view, "F4", "f4_paraphrase")


def _f5(view: View) -> list[Finding]:
    """Four stages present, the reminder later than the confirmation and carrying the old value."""
    found: list[Finding] = []
    for truth in view.primary("F5"):
        stages = {"proposal", "objection", "confirmation", "reminder"}
        present = {one.role for one in view.by_thread[truth.thread_key]} & stages
        if present != stages:
            found.append(Finding("f5_four_stages", "F5", truth.thread_key,
                                 f"missing {sorted(stages - present)}"))
            continue
        confirmation = view.roles(truth.thread_key, "confirmation")[0]
        reminder = view.roles(truth.thread_key, "reminder")[-1]
        if view.when(reminder) <= view.when(confirmation):
            found.append(Finding("f5_reminder_is_later", "F5", truth.thread_key,
                                 "the reminder is not dated after the confirmation, so it is "
                                 "not the temporal decoy EP §4.6 asks for"))
        if truth.answer and not states(truth.answer, _strip_reference(confirmation.body)):
            found.append(Finding("f5_confirmation_carries_answer", "F5", truth.thread_key,
                                 "the confirmation does not state the answer"))
        if truth.older_value and not states(truth.older_value, _strip_reference(reminder.body)):
            found.append(Finding("f5_reminder_is_stale", "F5", truth.thread_key,
                                 "the reminder does not restate the superseded value, so "
                                 "answering from the newest message is not an error"))
    return found


def _f6(view: View) -> list[Finding]:
    """X's own message is evidence; second-hand reports name X and are written by someone else."""
    found: list[Finding] = []
    for truth in view.primary("F6"):
        author = BY_KEY.get(_fact(truth, "author"))
        claims = view.roles(truth.thread_key, "authored_claim")
        hearsay = view.roles(truth.thread_key, "hearsay")
        if author is None or not claims:
            found.append(Finding("f6_authored_claim", "F6", truth.thread_key,
                                 "no authored claim, so there is nothing to cite"))
            continue
        if claims[0].sender != author.address:
            found.append(Finding("f6_authorship", "F6", truth.thread_key,
                                 "the authored claim is not from the declared author"))
        if len(hearsay) < 2:
            found.append(Finding("f6_hearsay_present", "F6", truth.thread_key,
                                 f"{len(hearsay)} second-hand report(s); the family needs one "
                                 "that is wrong and one that is right but still not the answer"))
        for one in hearsay:
            if author.display not in _strip_reference(one.body):
                found.append(Finding(
                    "f6_hearsay_names_the_person", "F6", truth.thread_key,
                    f"the report at {one.position} names nobody. The old generator left the "
                    "literal string 'participant 0' here and the family could not be scored "
                    "(R-M2-052)",
                ))
            if one.sender == author.address:
                found.append(Finding("f6_hearsay_is_second_hand", "F6", truth.thread_key,
                                     f"the report at {one.position} is from the author"))
        if truth.answer and not any(
            states(truth.answer, _strip_reference(one.body)) for one in hearsay
        ):
            found.append(Finding("f6_correct_hearsay", "F6", truth.thread_key,
                                 "no second-hand report states the right answer, so the family "
                                 "does not distinguish authorship from correctness"))
    return found


def _f7(view: View) -> list[Finding]:
    """Two halves in two conversations, neither sufficient, plus a vocabulary-sharing decoy."""
    found: list[Finding] = []
    for truth in view.primary("F7"):
        siblings = [
            one for one in view.family("F7") if one.continues == truth.scenario_key
        ]
        halves = [one for one in siblings if _fact(one, "half") == "figure"]
        if not halves:
            found.append(Finding("f7_two_halves", "F7", truth.thread_key,
                                 "no sibling conversation, so nothing is split"))
            continue
        other = halves[0]
        charge = _fact(other, "charge")
        decision = view.at(truth.thread_key, _int(truth, "evidence_at"))
        figure = view.at(other.thread_key, _int(other, "evidence_at"))
        if decision is None or figure is None:
            found.append(Finding("f7_two_halves", "F7", truth.thread_key, "a half has no evidence"))
            continue
        if charge and states(charge, _strip_reference(decision.body)):
            found.append(Finding("f7_halves_are_disjoint", "F7", truth.thread_key,
                                 "the decision conversation also states the figure, so one "
                                 "conversation answers the case and it is not cross-thread"))
        if truth.answer and states(truth.answer, _strip_reference(figure.body)):
            found.append(Finding("f7_halves_are_disjoint", "F7", other.thread_key,
                                 "the figure conversation also states the decision"))
        if not any(one.cross_thread_decoy_for == truth.scenario_key for one in view.family("F7")):
            found.append(Finding("f7_cross_thread_decoy", "F7", truth.thread_key,
                                 "no vocabulary-sharing decoy thread; EP §4.3 asks for two"))
    return found


def _f8(view: View) -> list[Finding]:
    """The fact is in the attachment and not in the covering body, with a same-named wrong copy."""
    found: list[Finding] = []
    for truth in view.primary("F8"):
        cover = view.at(truth.thread_key, _int(truth, "cover_at"))
        if cover is None or not cover.attachments:
            found.append(Finding("f8_attachment_present", "F8", truth.thread_key,
                                 "the covering message carries no attachment"))
            continue
        carrier = [one for one in cover.attachments if one.carries_the_fact]
        # **The answer is the file, not the figure.** EP §4.3 scores F8 as retrieving the
        # carrying message and signalling the attachment, and scores extraction only if
        # MailWeave claims it - which it does not. So what the rule checks is that the declared
        # answer names the attachment on the covering message, and that the figure the case
        # turns on really is inside the file and outside every body.
        inside = _fact(truth, "value_in_attachment")
        if not carrier:
            found.append(Finding("f8_attachment_carries_the_fact", "F8", truth.thread_key,
                                 "the covering message carries no attachment that is declared "
                                 "to hold the fact"))
            continue
        if truth.answer and truth.answer != carrier[0].filename:
            found.append(Finding(
                "f8_answer_names_the_attachment", "F8", truth.thread_key,
                f"the declared answer {truth.answer!r} is not the attachment's filename "
                f"{carrier[0].filename!r}; a pass here is retrieval plus signalling, so the "
                "answer has to be something the product can return",
            ))
        if inside and inside not in carrier[0].content:
            found.append(Finding("f8_attachment_carries_the_fact", "F8", truth.thread_key,
                                 f"the figure {inside!r} the case turns on is not in the file"))
            continue
        if inside and states(inside, _strip_reference(cover.body)):
            found.append(Finding("f8_body_withholds_the_fact", "F8", truth.thread_key,
                                 "the covering body states the figure, so the attachment is "
                                 "decoration and the family reduces to an ordinary lookup"))
        same_name = [
            (one, part)
            for one in view.manifest.messages for part in one.attachments
            if part.filename == carrier[0].filename and one.rfc822_message_id != cover.rfc822_message_id
        ]
        if not same_name:
            found.append(Finding("f8_wrong_version_exists", "F8", truth.thread_key,
                                 f"no other message attaches {carrier[0].filename!r}; EP §4.3 "
                                 "asks for the same filename elsewhere with a wrong version"))
        elif any(part.content == carrier[0].content for _, part in same_name):
            found.append(Finding("f8_wrong_version_differs", "F8", truth.thread_key,
                                 "the same-named attachment elsewhere is byte-identical"))
        if len(carrier[0].content) < 100:
            found.append(Finding("f8_fixture_is_real", "F8", truth.thread_key,
                                 f"the attachment is {len(carrier[0].content)} bytes; a "
                                 "one-line file makes finding the file the same as reading it"))
    # The decoy conversation must not declare an answer. It inherited the situation's default
    # once, so the manifest said the authentic figure was the truth of the thread holding the
    # corrupt copy, and a case author joining on `answer` would have scored the right figure
    # as retrieved from the wrong file.
    for truth in view.family("F8"):
        if truth in view.primary("F8"):
            continue
        if truth.answer:
            found.append(Finding(
                "f8_decoy_declares_no_answer", "F8", truth.thread_key,
                f"the decoy conversation declares the answer {truth.answer!r}; it holds the "
                "wrong version of the file, so a case built on this thread would score a "
                "figure that is not in it",
            ))
    return found


def _f10(view: View) -> list[Finding]:
    """A proposal with no confirmation anywhere, and no message that states an answer."""
    found: list[Finding] = []
    for truth in view.primary("F10"):
        roles = {one.role for one in view.by_thread[truth.thread_key]}
        if not {"proposal", "objection"} <= roles:
            found.append(Finding("f10_near_miss_present", "F10", truth.thread_key,
                                 "no proposal and objection, so there is no near miss to "
                                 "tempt a confident wrong answer"))
        settled = roles & {"confirmation", "reversal", "evidence", "authored_claim"}
        if settled:
            found.append(Finding("f10_nothing_was_settled", "F10", truth.thread_key,
                                 f"the thread contains {sorted(settled)}, so the control has "
                                 "an answer and is not a control"))
        absent = _fact(truth, "absent_claim")
        if truth.answer:
            found.append(Finding(
                "f10_declares_no_answer", "F10", truth.thread_key,
                f"the control declares an answer {truth.answer!r}; the correct output is a "
                "grounded not-found, and a declared answer invites scoring against a string "
                "the corpus deliberately does not contain",
            ))
        if not absent:
            found.append(Finding("f10_no_answer_exists", "F10", truth.thread_key,
                                 "no value is recorded as the one that must be absent, so the "
                                 "control's defining property cannot be checked"))
        elif any(states(absent, _strip_reference(one.body)) for one in view.manifest.messages):
            found.append(Finding("f10_no_answer_exists", "F10", truth.thread_key,
                                 f"the claim {absent!r} that must be absent from the whole "
                                 "corpus appears in a message"))
        else:
            # The bare value may occur elsewhere about other matters - that is ordinary mail,
            # not an answer. What must not happen is a message in *this* conversation carrying
            # it, which would settle the thing the control says was never settled.
            value = _fact(truth, "absent_value")
            if value and any(
                states(value, _strip_reference(one.body)) for one in view.by_thread[truth.thread_key]
            ):
                found.append(Finding(
                    "f10_no_answer_exists", "F10", truth.thread_key,
                    f"a message in this conversation states {value!r}",
                ))
    return found


def _ranked(view: View, key: str, rule: str, *, winner: str, loser: str) -> list[Finding]:
    found: list[Finding] = []
    for truth in view.primary(key):
        query = _fact(truth, "construction_query")
        bodies = [_strip_reference(one) for one in view.bodies(truth.thread_key)]
        high, low = _int(truth, winner), _int(truth, loser)
        if not query or not 0 <= high < len(bodies) or not 0 <= low < len(bodies):
            found.append(Finding(rule, key, truth.thread_key, "no construction query declared"))
            continue
        high_rank = lexical.rank_of(bodies, query, high)
        low_rank = lexical.rank_of(bodies, query, low)
        if high_rank >= low_rank:
            found.append(Finding(
                rule, key, truth.thread_key,
                f"position {high} ranks {high_rank} and position {low} ranks {low_rank} on the "
                f"construction query. The family is registered on the opposite relationship",
            ))
    return found


def _f11(view: View) -> list[Finding]:
    """The trap outranks its evidence, so a system escalating only on weak hits never escalates."""
    return _paraphrase_pair(view, "F11", "f11_paraphrase") + _ranked(
        view, "F11", "f11_trap_outranks_evidence", winner="decoy_at", loser="evidence_at")


def _f11_trap_is_the_top_hit(view: View) -> list[Finding]:
    """R-M2-067. The trap is the best lexical hit in its conversation, not just above evidence.

    `f11` asserts the pair relationship - trap above evidence - and `t0031` satisfied it with
    the trap at rank 5 of 21, behind four ordinary filler messages. F11 is registered to show
    that a policy of "escalate when the lexical hits are weak" fails to escalate, and what such
    a policy reads is the *best* hit in the conversation. A thread whose best hit is filler
    exercises the opposite case.

    Scoped to F11's registered requirement. It is not a general claim that every family's
    distractor must top its thread; the other families are registered on other relationships
    and this rule says nothing about them.
    """
    found: list[Finding] = []
    for truth in view.primary("F11"):
        query = _fact(truth, "construction_query")
        bodies = [_strip_reference(one) for one in view.bodies(truth.thread_key)]
        decoy_at = _int(truth, "decoy_at")
        if not query or not 0 <= decoy_at < len(bodies):
            found.append(Finding("f11_trap_is_the_top_hit", "F11", truth.thread_key,
                                 "no construction query or no declared trap position"))
            continue
        rank = lexical.rank_of(bodies, query, decoy_at)
        if rank != 1:
            better = sorted(
                (lexical.rank_of(bodies, query, one), view.by_thread[truth.thread_key][one].role)
                for one in range(len(bodies))
                if lexical.rank_of(bodies, query, one) < rank
            )
            found.append(Finding(
                "f11_trap_is_the_top_hit", "F11", truth.thread_key,
                f"the trap at {decoy_at} ranks {rank} of {len(bodies)} on the construction "
                f"query, behind {[one[1] for one in better]}. A weak-hit escalation policy "
                "reads the best hit in the conversation, and here that is not the trap",
            ))
    return found


def _f12(view: View) -> list[Finding]:
    """The exact match wins, so always escalating is punished."""
    return _ranked(view, "F12", "f12_exact_match_wins",
                   winner="evidence_at", loser="decoy_at")


def _f13(view: View) -> list[Finding]:
    """The answer is on the far side of a named event, and the pre-event messages match it."""
    found: list[Finding] = []
    for truth in view.primary("F13"):
        stamp = _fact(truth, "event_on")
        evidence = view.at(truth.thread_key, _int(truth, "evidence_at"))
        if not stamp or evidence is None:
            found.append(Finding("f13_event_anchor", "F13", truth.thread_key,
                                 "no anchoring event declared"))
            continue
        event = dt.datetime.fromisoformat(stamp).replace(tzinfo=dt.timezone.utc).timestamp()
        if view.when(evidence) <= event:
            found.append(Finding("f13_answer_is_after", "F13", truth.thread_key,
                                 "the answer is not dated after the event it is supposed to "
                                 "follow"))
        before = [
            one for one in view.by_thread[truth.thread_key]
            if view.when(one) < event and truth.wrong_value and states(truth.wrong_value, _strip_reference(one.body))
        ]
        if not before:
            found.append(Finding("f13_pre_event_decoys", "F13", truth.thread_key,
                                 "nothing before the event states the superseded position, so "
                                 "a date filter alone separates the cases"))
        elif not content_words(before[0].body) & content_words(evidence.body):
            found.append(Finding("f13_pre_event_decoys_match", "F13", truth.thread_key,
                                 "the pre-event messages share no vocabulary with the answer, "
                                 "so they are not competitive"))
    return found


def _f14(view: View) -> list[Finding]:
    """A silent participant, a same-name decoy at a different address, and one changed address."""
    found: list[Finding] = []
    for truth in view.primary("F14"):
        group = view.by_thread[truth.thread_key]
        senders = {one.sender for one in group}
        silent = [
            one for one in truth.participants
            if one in BY_KEY and BY_KEY[one].address not in senders
        ]
        if not silent:
            found.append(Finding("f14_silent_participant", "F14", truth.thread_key,
                                 "everyone on the conversation sends, so 'who else was on it' "
                                 "is answerable from the senders alone"))
        objector = BY_KEY.get(_fact(truth, "objector"))
        decoy = BY_KEY.get(_fact(truth, "same_name_decoy"))
        if objector is None or decoy is None:
            found.append(Finding("f14_identity_traps", "F14", truth.thread_key,
                                 "no same-name pair declared"))
            continue
        if objector.display != decoy.display or objector.address == decoy.address:
            found.append(Finding("f14_identity_traps", "F14", truth.thread_key,
                                 "the declared pair does not share a display name at two "
                                 "addresses, so display name and identity are not separable"))
        if decoy.address not in senders:
            found.append(Finding("f14_identity_traps", "F14", truth.thread_key,
                                 "the same-name decoy never writes in the conversation"))
        evidence = view.at(truth.thread_key, _int(truth, "evidence_at"))
        objection = view.roles(truth.thread_key, "objection")
        if evidence is None or not objection:
            found.append(Finding("f14_objector_speaks_later", "F14", truth.thread_key,
                                 "no objection or no later message from its author"))
        elif evidence.sender != objection[0].sender:
            found.append(Finding("f14_objector_speaks_later", "F14", truth.thread_key,
                                 "the later message is not from whoever raised the objection"))
        pair = _fact(truth, "changed_address").split("/")
        if len(pair) != 2 or not all(
            one in BY_KEY and BY_KEY[one].address in senders for one in pair
        ):
            found.append(Finding("f14_changed_address", "F14", truth.thread_key,
                                 "the one-person-two-addresses pair does not both write here"))
    return found


def _f15(view: View) -> list[Finding]:
    """All four structural shapes, each with the answer outside the conversation you would read."""
    found: list[Finding] = []
    shapes = Counter(_fact(one, "shape") for one in view.primary("F15"))
    wanted = {"subject_change", "forward", "orphan", "ceiling_split"}
    if view.primary("F15"):
        missing = sorted(wanted - set(shapes))
        if missing and len(view.primary("F15")) >= len(wanted):
            found.append(Finding("f15_all_shapes", "F15", "corpus",
                                 f"no instance of {missing}. The generator could emit none of "
                                 "these shapes and no profile setting added them (R-M2-054)"))
    for truth in view.primary("F15"):
        shape = _fact(truth, "shape")
        group = view.by_thread[truth.thread_key]
        sibling = [
            one for one in view.family("F15") if one.continues == truth.scenario_key
        ]
        if not sibling:
            found.append(Finding("f15_sibling_exists", "F15", truth.thread_key,
                                 f"the {shape} shape has no second conversation"))
            continue
        other = sibling[0]
        if not any(one.role == "evidence" for one in view.by_thread[other.thread_key]):
            found.append(Finding("f15_answer_is_in_the_sibling", "F15", truth.thread_key,
                                 "the continuation carries no answer"))
        if any(one.role == "evidence" for one in group):
            found.append(Finding("f15_answer_is_in_the_sibling", "F15", truth.thread_key,
                                 "the conversation a reader would follow already answers the "
                                 "question, so the structural anomaly costs nothing"))
        # Findings about a continuation are attributed to the case's primary thread. A defect
        # recorded only against the sibling leaves the case counted as authorable, which is the
        # accounting error that let the old report publish a number nothing could move.
        if shape == "subject_change":
            stripped = re.sub(r"^(re|fwd):\s*", "", other.subject, flags=re.I)
            if stripped == truth.subject or other.subject == truth.subject:
                found.append(Finding(
                    "f15_subject_changes", "F15", truth.thread_key,
                    "the continuation carries the same subject, or the original one behind a "
                    "Re:/Fwd: prefix, so the rename is decoration and the two conversations "
                    "are joinable by subject alone",
                ))
        if shape == "orphan" and not other.orphan:
            found.append(Finding("f15_orphan_is_detached", "F15", truth.thread_key,
                                 f"the orphan {other.thread_key} is not marked detached"))
        if shape == "orphan":
            first = view.at(other.thread_key, 0)
            if first is not None and (first.in_reply_to or first.references):
                found.append(Finding("f15_orphan_is_detached", "F15", truth.thread_key,
                                     f"the orphan {other.thread_key} carries reference headers, "
                                     "so Gmail files it with the thread it is supposed to be "
                                     "detached from"))
    return found


def _f16(view: View) -> list[Finding]:
    """Near-duplicates that differ in one value, adopted by a message rather than by recency."""
    found: list[Finding] = []
    for truth in view.primary("F16"):
        candidates = view.roles(truth.thread_key, "near_duplicate")
        if len(candidates) < 4:
            found.append(Finding("f16_enough_candidates", "F16", truth.thread_key,
                                 f"{len(candidates)} near-duplicates; EP §4.3 asks for 4 to 6"))
            continue
        skeletons = set()
        for one in candidates:
            text = _unframed(one.body)
            for value in sorted(_values(truth), key=len, reverse=True):
                text = text.replace(value, "<value>")
            # R-M2-068. The ordinal used to be normalised away here, which is how the rule
            # passed a corpus whose candidates differed in *two* details. There is no ordinal
            # in the text now, so the skeleton is the sentence with its figures masked and
            # nothing else - and five candidates that are not then identical fail.
            skeletons.add(text)
        if len(skeletons) > 1:
            found.append(Finding(
                "f16_candidates_are_alike", "F16", truth.thread_key,
                "the candidates differ in more than their value, so a string match separates "
                "them. The old corpus prefixed its wrong candidates with 'Superseded draft: ' "
                "(R-M2-053)",
            ))
        adopted_at = _int(truth, "adopted_at")
        if adopted_at not in truth.evidence_positions:
            found.append(Finding(
                "f16_key_names_the_answer", "F16", truth.thread_key,
                f"the key names {truth.evidence_positions} and the adopted revision is at "
                f"{adopted_at}. An independent reader found the declared evidence did not "
                "contain the answer string at all",
            ))
        adopted = view.at(truth.thread_key, adopted_at)
        latest = max(candidates, key=view.when)
        if adopted is None or adopted.role != "near_duplicate":
            found.append(Finding("f16_adopted_is_a_candidate", "F16", truth.thread_key,
                                 "the adopted revision is not one of the candidates"))
            continue
        if adopted.rfc822_message_id == latest.rfc822_message_id:
            found.append(Finding("f16_recency_does_not_win", "F16", truth.thread_key,
                                 "the adopted revision is the newest, so taking the latest "
                                 "message passes without reading the confirmation"))
        confirmation = view.roles(truth.thread_key, "confirmation")
        adopted_value = _fact(truth, "adopted_value")
        # R-M2-068. It used to look for the revision *ordinal*. The candidates no longer carry
        # one, so what the confirmation has to name is the figure it signed.
        names_it = bool(adopted_value) and any(
            states(adopted_value, _strip_reference(one.body)) for one in confirmation
        )
        if not names_it:
            found.append(Finding("f16_confirmation_names_it", "F16", truth.thread_key,
                                 "no message names which figure was adopted, so the decisive "
                                 "detail is not in the corpus"))
    return found


def _f17(view: View) -> list[Finding]:
    """The reversal is the answer, and it is not the message a query-score selector would pick."""
    found: list[Finding] = []
    for truth in view.primary("F17"):
        reversal_at = _int(truth, "reversal_at")
        reversal = view.at(truth.thread_key, reversal_at)
        if reversal is None or reversal.role != "reversal":
            found.append(Finding("f17_reversal_present", "F17", truth.thread_key,
                                 "no reversal at the declared position"))
            continue
        if truth.evidence_positions != (reversal_at,):
            found.append(Finding(
                "f17_ground_truth_points_at_the_reversal", "F17", truth.thread_key,
                f"the answer key marks {truth.evidence_positions} as evidence and the reversal "
                f"is at {reversal_at}. The old corpus marked the first reinforcement in eight "
                "threads of eight, so the key pointed at the message the family exists to "
                "catch systems returning (R-M2-047)",
            ))
        if truth.answer and not states(truth.answer, _strip_reference(reversal.body)):
            found.append(Finding("f17_reversal_carries_the_answer", "F17", truth.thread_key,
                                 "the reversal does not state the new position"))
        reinforcements = view.roles(truth.thread_key, "reinforcement")
        if len(reinforcements) < 3:
            found.append(Finding("f17_reinforcements", "F17", truth.thread_key,
                                 f"{len(reinforcements)} reinforcing distractors; the trap is "
                                 "that the wrong answer looks better evidenced"))
        if reinforcements and view.when(reversal) <= max(view.when(one) for one in reinforcements):
            found.append(Finding("f17_reversal_is_late", "F17", truth.thread_key,
                                 "the reversal is not the latest of the decision messages"))
    positions = [
        (truth, _int(truth, "reinforcements_at", -1)) for truth in view.primary("F17")
    ]
    del positions
    found.extend(_ranked_f17(view))
    return found


def _ranked_f17(view: View) -> list[Finding]:
    found: list[Finding] = []
    for truth in view.primary("F17"):
        query = _fact(truth, "construction_query")
        raw = _fact(truth, "reinforcements_at")
        bodies = [_strip_reference(one) for one in view.bodies(truth.thread_key)]
        reversal_at = _int(truth, "reversal_at")
        spots = [int(one) for one in raw.split(",") if one.strip().isdigit()]
        if not query or not spots or not 0 <= reversal_at < len(bodies):
            continue
        reversal_rank = lexical.rank_of(bodies, query, reversal_at)
        best = min(lexical.rank_of(bodies, query, one) for one in spots)
        if best >= reversal_rank:
            found.append(Finding(
                "f17_reinforcements_outrank_the_reversal", "F17", truth.thread_key,
                f"the reversal ranks {reversal_rank} and the best reinforcement ranks {best} "
                "on the construction query. The old corpus had the reversal at rank 1 in eight "
                "threads of eight, so selecting on query score alone passed the family",
            ))
    return found


def _older_value_is_not_the_last_word(view: View) -> list[Finding]:
    """R-M2-073. The message planted to carry a superseded position is not the newest one.

    F2 put its `formal_older` rendering four days after the window closed, which made it the
    newest message in the conversation. The key called that value `older_value` while the text
    made it the last word on the matter: ground truth and chronology disagreed about which
    position had been superseded.

    **What this reads is a declaration, not the prose.** A superseded value is normally also
    *mentioned* by the messages that supersede it - the F2 template renders as "restated at 27,
    against 85 at the prior approval", so the current message names the old figure as its own
    reference point - and no text rule separates "states X as the position" from "names X as
    what the position replaced". So a builder that plants such a message says where it is, in
    `older_at`, and this rule checks that placement. Its limit is stated rather than implied: a
    family that plants one and declares nothing is not checked here.
    """
    found: list[Finding] = []
    for truth in view.manifest.answer_key.threads:
        raw = truth.facts.get("older_at", "")
        if not raw or not raw.isdigit():
            continue
        group = view.by_thread[truth.thread_key]
        planted = view.at(truth.thread_key, int(raw))
        if not group or planted is None:
            found.append(Finding("older_value_is_not_the_last_word", truth.family or "corpus",
                                 truth.thread_key,
                                 f"older_at names position {raw}, which the thread has no "
                                 "message at"))
            continue
        newest = max(group, key=view.when)
        if planted.rfc822_message_id == newest.rfc822_message_id:
            found.append(Finding(
                "older_value_is_not_the_last_word", truth.family or "corpus", truth.thread_key,
                f"the message planted to carry the superseded value {truth.older_value!r} is "
                f"the newest in the conversation (position {planted.position} of "
                f"{len(group) - 1}). Nothing in the text supersedes it",
            ))
    return found


def _f7_each_half_carries_a_distractor(view: View) -> list[Finding]:
    """R-M2-073. EP §4.3 asks every case for a distractor; F7's figure half had none.

    The decision half has carried a competing proposal since the earlier repair. The figure
    half did not, so the half that holds the number was answerable by finding the one message
    in it with a number in it. Stated per half, because a case whose second conversation is
    uncontested is uncontested in the place the reader has to go.
    """
    found: list[Finding] = []
    for truth in view.primary("F7"):
        halves = [truth] + [
            one for one in view.family("F7") if one.continues == truth.scenario_key
        ]
        for half in halves:
            group = view.by_thread[half.thread_key]
            distractors = [one for one in group if one.role in _DISTRACTOR_ROLES]
            if not distractors:
                found.append(Finding(
                    "f7_each_half_carries_a_distractor", "F7", truth.thread_key,
                    f"the {_fact(half, 'half') or 'decision'} half {half.thread_key} carries no "
                    "distractor, so the only message in it stating a value is the answer",
                ))
    return found


def _f12_query_is_not_the_evidence(view: View) -> list[Finding]:
    """R-M2-073. F12's construction query was its evidence sentence, verbatim and complete.

    Two consequences, and the rule names both. `f12_exact_match_wins` becomes a question about
    whether a sentence outranks its neighbours *on itself*, which nothing can fail. And the
    query carries the answer value, so the query alone answers the case.

    The query must still be present in the evidence word for word - that is F12's registered
    mechanism and this rule does not weaken it - but it is a fragment someone would quote, not
    the whole sentence.
    """
    found: list[Finding] = []
    for truth in view.primary("F12"):
        query = _fact(truth, "construction_query")
        evidence = view.at(truth.thread_key, _int(truth, "evidence_at"))
        if not query or evidence is None:
            found.append(Finding("f12_query_is_not_the_evidence", "F12", truth.thread_key,
                                 "no construction query or no evidence at the declared spot"))
            continue
        body = _unframed(evidence.body)
        if query not in _strip_reference(evidence.body):
            found.append(Finding(
                "f12_query_is_not_the_evidence", "F12", truth.thread_key,
                "the construction query is not present in the evidence word for word, so the "
                "family's exact-match mechanism is not exercised",
            ))
        if query.strip(" .") == body.strip(" ."):
            found.append(Finding(
                "f12_query_is_not_the_evidence", "F12", truth.thread_key,
                "the construction query is the evidence sentence entire. A sentence cannot "
                "fail to outrank its neighbours on itself",
            ))
        for name, value in (("answer", truth.answer), ("wrong", truth.wrong_value),
                            ("older", truth.older_value)):
            if value and states(value, query):
                found.append(Finding(
                    "f12_query_is_not_the_evidence", "F12", truth.thread_key,
                    f"the construction query states the {name} value {value!r}, so it answers "
                    "the case without retrieving anything",
                ))
    return found


def _f15_split_is_not_claimed_as_a_ceiling(view: View) -> list[Finding]:
    """R-M2-073. The split note claimed a ceiling the corpus itself contradicts.

    It read "a conversation that reached the 90-message ceiling of EP §3.8". EP §3.8's ceiling
    is 100; 90 is §4.4's thread length; and the corpus carries unsplit conversations of 91 to
    96 messages, so no ceiling of 90 was reached by anything. The rule reads whatever numeric
    ceiling the note claims and checks the corpus against it.
    """
    found: list[Finding] = []
    unsplit = [
        one for one in view.manifest.answer_key.threads
        if not one.continues
        and not any(other.continues == one.scenario_key
                    for other in view.manifest.answer_key.threads)
    ]
    longest = max((one.length for one in unsplit), default=0)
    for truth in view.family("F15"):
        claimed = re.search(r"(\d+)-message ceiling", truth.answer_note or "")
        if not claimed:
            continue
        ceiling = int(claimed.group(1))
        if longest >= ceiling:
            found.append(Finding(
                "f15_split_is_not_claimed_as_a_ceiling", "F15", truth.thread_key,
                f"the note says the conversation reached a {ceiling}-message ceiling, and the "
                f"corpus holds an unsplit conversation of {longest}. Ground truth states a "
                "cause the text refutes",
            ))
    return found


def _f16_mechanism_is_necessary(view: View) -> list[Finding]:
    """R-M2-068. Reading the confirmation is the only way to know which figure was adopted.

    Scoped to F16's own registered requirement - near-duplicates that a ranker cannot separate,
    adopted by a message rather than by recency - and to nothing else. It does not say a
    question must have one solution method; it says the *second* method this family shipped
    with was a unique exact-match key, which is F1's mechanism, and while it was there a
    failure here could not be read as a ranking failure rather than a retrieval failure.

    Three properties, each of the text:

    1. mask the declared figures and the candidates are one sentence. Nothing else differs.
    2. no candidate numbers itself. An ordinal the answer key names verbatim is the key.
    3. exactly two messages state the adopted figure - the adopted candidate and the
       confirmation - so the confirmation is the only thing that points at one candidate.
    """
    found: list[Finding] = []
    for truth in view.primary("F16"):
        candidates = view.roles(truth.thread_key, "near_duplicate")
        if not candidates:
            found.append(Finding("f16_mechanism", "F16", truth.thread_key,
                                 "no near-duplicate candidates"))
            continue
        figures = [one for one in _fact(truth, "revision_values").split("|") if one]
        skeletons = set()
        for one in candidates:
            text = _unframed(one.body)
            for value in sorted(figures, key=len, reverse=True):
                text = text.replace(value, "<figure>")
            skeletons.add(text)
        if len(skeletons) > 1:
            found.append(Finding(
                "f16_mechanism", "F16", truth.thread_key,
                f"{len(skeletons)} distinct candidate skeletons once the figures are masked. "
                "A second differing detail is a second way to pick the adopted revision",
            ))
        numbered = [
            one for one in candidates
            if re.search(r"\b(?:revision|draft)\s+\d+", _strip_reference(one.body), re.I)
        ]
        if numbered:
            found.append(Finding(
                "f16_mechanism", "F16", truth.thread_key,
                f"{len(numbered)} candidate(s) number themselves, and the answer key names the "
                "ordinal. That is a unique exact-match key - F1's mechanism, not this one's",
            ))
        adopted_value = _fact(truth, "adopted_value")
        if adopted_value:
            holders = [
                one for one in view.by_thread[truth.thread_key]
                if states(adopted_value, _strip_reference(one.body))
            ]
            roles = sorted(one.role for one in holders)
            if roles != ["confirmation", "near_duplicate"]:
                found.append(Finding(
                    "f16_mechanism", "F16", truth.thread_key,
                    f"the adopted figure {adopted_value!r} is stated by {roles}. It should be "
                    "the adopted candidate and the confirmation and nothing else, or the "
                    "confirmation is not the only thing that points at one candidate",
                ))
    return found


def _f17_reversal_answers_a_reinforcement(view: View) -> list[Finding]:
    """R-M2-068. The reply relation is what connects the trap to the thing that overturns it.

    F17 is registered as the falsifier for the non-negotiable E2 reply-chain floor, and it
    shipped with the reversal replying to whichever message happened to precede it - in both
    instances, an ordinary filler. The chain a system is supposed to follow, from the
    reinforcement a query-score selector returns to the message that overturns it, was not in
    the headers at all.

    Scoped to F17's registered requirement. It says nothing about other families' reply
    structure and does not require this conversation to be unanswerable by any other route;
    it requires the route the family exists to test to be present.
    """
    found: list[Finding] = []
    for truth in view.primary("F17"):
        group = view.by_thread[truth.thread_key]
        reversal_at = _int(truth, "reversal_at")
        spots = [int(one) for one in _fact(truth, "reinforcements_at").split(",")
                 if one.strip().isdigit()]
        if not 0 <= reversal_at < len(group) or not spots:
            found.append(Finding("f17_chain", "F17", truth.thread_key,
                                 "no reversal position or no declared reinforcements"))
            continue
        reversal = group[reversal_at]
        by_id = {one.rfc822_message_id: one for one in group}
        parent = by_id.get(reversal.in_reply_to or "")
        if parent is None:
            found.append(Finding(
                "f17_chain", "F17", truth.thread_key,
                "the reversal replies to nothing inside its own conversation, so there is no "
                "chain from the reinforcement a query-score selector returns to the message "
                "that overturns it",
            ))
        elif parent.position not in spots:
            found.append(Finding(
                "f17_chain", "F17", truth.thread_key,
                f"the reversal replies to position {parent.position} ({parent.role}), not to "
                f"one of the reinforcements at {spots}. Following the chain from the trap "
                "leads nowhere",
            ))
        newest = max(group, key=view.when)
        if reversal.rfc822_message_id == newest.rfc822_message_id:
            found.append(Finding(
                "f17_chain", "F17", truth.thread_key,
                "the reversal is the newest message, so taking the latest substitutes for "
                "following the chain",
            ))
    return found


def _f13_reply_chain_is_load_bearing(view: View) -> list[Finding]:
    """R-M2-068. F13's registered requirement is ordering **and** reply-relationship reasoning.

    The question is what the objector settled on. The acceptance says it accepts, and does not
    say what: which message it accepts is in its References header and nowhere else. For that
    to be doing work, more than one message after the event has to state a declared value -
    otherwise "the post-event message with a figure in it" answers the case and the graph is
    decoration.

    Measured at the time this rule was written, F13 already satisfied all four clauses; the
    finding that named it predates the earlier F13 repair. The rule is here so that stays true.
    """
    found: list[Finding] = []
    for truth in view.primary("F13"):
        group = view.by_thread[truth.thread_key]
        by_id = {one.rfc822_message_id: one for one in group}
        stamp = _fact(truth, "event_on")
        evidence = view.at(truth.thread_key, _int(truth, "evidence_at"))
        objection = view.at(truth.thread_key, _int(truth, "objection_at"))
        acceptance = view.at(truth.thread_key, _int(truth, "acceptance_at"))
        if not stamp or evidence is None or objection is None or acceptance is None:
            found.append(Finding("f13_chain", "F13", truth.thread_key,
                                 "the thread does not declare the three messages the chain "
                                 "runs through"))
            continue
        parent = by_id.get(evidence.in_reply_to or "")
        if parent is None or parent.position != objection.position:
            found.append(Finding(
                "f13_chain", "F13", truth.thread_key,
                "the answer does not reply to the objection, so nothing in the headers says "
                "which concern it addresses",
            ))
        accepted = by_id.get(acceptance.in_reply_to or "")
        if accepted is None or accepted.position != evidence.position:
            found.append(Finding(
                "f13_chain", "F13", truth.thread_key,
                "the acceptance does not reply to the answer, so which post-event message the "
                "objector accepted is not recoverable",
            ))
        if truth.answer and states(truth.answer, _strip_reference(acceptance.body)):
            found.append(Finding(
                "f13_chain", "F13", truth.thread_key,
                "the acceptance states the answer outright, so the reply relation carries "
                "nothing the text does not already say",
            ))
        event = dt.datetime.fromisoformat(stamp).replace(tzinfo=dt.timezone.utc).timestamp()
        declared = [one for one in (truth.answer, truth.wrong_value, truth.older_value) if one]
        after = [
            one for one in group
            if view.when(one) > event
            and any(states(value, _strip_reference(one.body)) for value in declared)
        ]
        if len(after) < 2:
            found.append(Finding(
                "f13_chain", "F13", truth.thread_key,
                f"{len(after)} message(s) after the event state a declared value. With one, "
                "a date filter answers the case and the reply graph is decoration",
            ))
    return found


def _scaffolding_is_not_family_exclusive(view: View) -> list[Finding]:
    """R-M2-071. No scaffolding sentence occurs inside exactly one family.

    The earlier repair re-minted the *values* and shared the *frames*, and checked exclusivity
    at `(family, role)`. It did not reach one level up: twelve entity-free, digit-free
    sentences - F14's roster line and its address-change line, F15's "Original below.", F8's
    staleness caveats, F13's acceptance - were written inline by one builder each and so
    occurred in exactly one family in the whole corpus. `grep` on any of them returned that
    family and nothing else.

    **Exclusivity is measured against the family's own share of the corpus, not asserted.**
    One family holds most of the messages - F3 is seven ninety-message conversations - so a
    sentence emitted rarely lands inside it by arithmetic, and a rule that called that a marker
    would report the corpus's shape rather than a defect. A sentence occurring in `k` messages
    all inside a family holding share `p` is flagged when `p**k`, multiplied by the number of
    sentences tested, is below 0.05: the chance of this concentration arising from the
    corpus's own proportions, corrected for testing every sentence at once.

    Sentences carrying a digit or an entity name are out of scope, and so are the twelve topic
    rationales. Those are *about* the matter, and a matter belongs to one conversation by
    construction; what this rule is for is the scaffolding, which belongs to nobody. The
    rationales have to be named explicitly because they carry neither a digit nor an entity -
    they would otherwise be reported, and the concentration they show is a topic's, not a
    family's: F3 covers every topic in long conversations and the foil pool prefers a foil of
    the conversation's own topic, so a rationale lands where its topic is busiest.

    **The count is conversations; the probability is the family's share of messages.** Those
    are deliberately different units. A sentence emitted twice inside one conversation is one
    event and not two, so conversations are what is counted. But a conversation's chance of
    containing any given sentence rises with its length, and F3's are ninety messages against
    F13's fifteen - so the chance that an occurrence falls in a family is that family's share
    of the *corpus*, not of its conversations. Counting conversations against a
    conversation-share null reported F3's ordinary closing lines as F3 markers, which is the
    long-thread family's length restated.

    The floor is three conversations. Below that nothing is distinguishable from chance at this
    corpus size whatever correction is applied: that is a stated limit, and a marker in two
    conversations is invisible here.
    """
    from .situations import TOPICS

    names: set[str] = set()
    for entity in BY_ENTITY.values():
        names |= {entity.formal.lower(), entity.plain.lower()}
    rationales = {one.reason for one in TOPICS}
    family_of = {
        one.thread_key: (one.family or "") for one in view.manifest.answer_key.threads
    }
    total = len(view.manifest.messages)
    if not total:
        return []
    share = Counter(family_of.get(one.thread_key, "") for one in view.manifest.messages)
    holders: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for message in view.manifest.messages:
        for sentence in re.split(r"(?<=[.?!])\s+", _strip_reference(message.body)):
            sentence = sentence.strip()
            if len(sentence.split()) < 2 or any(one.isdigit() for one in sentence):
                continue
            low = sentence.lower()
            if any(one and one in low for one in names):
                continue
            if any(sentence in one or one in sentence for one in rationales):
                continue
            holders[sentence].add(
                (family_of.get(message.thread_key, ""), message.thread_key)
            )
    tested = {one: group for one, group in holders.items() if len(group) >= 3}
    if not tested:
        return []
    found: list[Finding] = []
    for sentence, group in tested.items():
        families = {one for one, _ in group}
        if len(families) != 1:
            continue
        family = next(iter(families))
        if not family:
            continue
        count = len(group)
        expected = (share[family] / total) ** count * len(tested)
        if expected < 0.05:
            found.append(Finding(
                "scaffolding_is_not_family_exclusive", family, "corpus",
                f"the sentence {sentence[:70]!r} occurs in {count} conversations and every one "
                f"of them is {family}. That family holds {share[family] / total:.0%} of the "
                f"corpus's messages, so the concentration arises by chance with "
                f"probability {expected:.4f} across all sentences tested. Searching for it "
                "returns the family",
            ))
    return sorted(found, key=lambda one: one.detail)[:6]


def _role_positions_vary(view: View) -> list[Finding]:
    """R-M2-072, first half. A family does not lay its roles out the same way twice.

    F14 put its proposal at 1, its objection at 2, its near-duplicate at 4 and its answer at 7
    in all eight instances; F2 did the same across ten. The whole role-position map was one
    tuple, so "index 7 of an F14-shaped thread" named the answer with no query, and §4.7's
    requirement that a family draw its positions from the §4.4 grid was not met.

    **The fingerprint, not the single role.** A family whose one attachment cover happens to
    land at the same index in four short conversations is a coincidence at these lengths, and
    a rule that reported it would report a different set every seed. A family whose *entire*
    map of planted roles to positions is identical across every instance is not.
    """
    found: list[Finding] = []
    prints: dict[str, set[tuple[tuple[str, tuple[int, ...]], ...]]] = defaultdict(set)
    counts: Counter[str] = Counter()
    for truth in view.manifest.answer_key.threads:
        if not truth.family:
            continue
        counts[truth.family] += 1
        prints[truth.family].add(tuple(sorted(
            (role, tuple(spots)) for role, spots in truth.roles_at.items()
            if role != "filler"
        )))
    for family, seen in sorted(prints.items()):
        if counts[family] < 2 or len(seen) > 1:
            continue
        only = next(iter(seen))
        if not only:
            continue
        found.append(Finding(
            "role_positions_vary", family, "corpus",
            f"all {counts[family]} {family} conversations put every planted role at the same "
            f"position: {dict(only)}. The layout names the answer without reading anything",
        ))
    return found


def _hour_is_independent_of_role(view: View) -> list[Finding]:
    """R-M2-072, second half. What time a message was sent does not say what it is.

    `trap_decoy` was 11 of 11 after 13:00, and later 78% of 106 against a corpus rate of 58%,
    after the hour itself had been made a hash of the conversation and the position. The
    residual came from collision handling: a role written with a short gap landed on its
    predecessor's timestamp more often, and each bump used to move it an hour later in the day.
    Rolling the date instead of adding an hour removed it.

    **The observation is a conversation, not a message, and each conversation is its own
    control.** The hour is drawn per `(conversation, position)`, so several messages of one
    role inside one thread are not independent draws - five revisions of one F16 schedule all
    landing in the afternoon is one coincidence, not five. A message-level test says otherwise
    and reports a different set of roles at every seed. So for each thread the rule takes the
    difference between the role's afternoon share and the afternoon share of everything else in
    *that* thread, and tests whether the mean difference across threads is zero. Pairing inside
    the conversation also removes whatever the conversation's own hours happen to be.

    **Mantel-Haenszel across conversations.** Each conversation is a stratum: its messages are
    late or not, and each is this role or not. Under the null the pairing describes - within a
    conversation, which message carries which role is exchangeable - a stratum's count of late
    messages of that role is hypergeometric, with a mean and a variance in closed form. The
    statistic sums the observed-minus-expected counts over strata and divides by the summed
    variances, which is the standard test for exactly this shape and needs nothing estimated
    from the data.

    It replaces a mean of per-conversation differences, which was a worse estimator of the same
    quantity and not a different threshold: a conversation carrying one message of a role gives
    a difference of about +0.5 or -0.5 whichever way its single message falls, and averaging
    those with a conversation carrying five gives the least informative strata the most weight.
    Weighting by information is what Mantel-Haenszel does.

    Bonferroni-corrected across the roles tested; roles carried by fewer than ten conversations
    are not tested. Both limits are of the corpus's size, and are stated rather than implied: a
    skew in a role that appears in nine conversations is invisible here.
    """
    threads: dict[str, list[tuple[str, bool]]] = defaultdict(list)
    for message in view.manifest.messages:
        stamp = email.utils.parsedate_to_datetime(message.date_rfc2822)
        threads[message.thread_key].append((message.role, stamp.hour >= 13))
    observed: Counter[str] = Counter()
    expected: dict[str, float] = defaultdict(float)
    variance: dict[str, float] = defaultdict(float)
    strata: Counter[str] = Counter()
    shares: dict[str, list[float]] = defaultdict(list)
    for group in threads.values():
        size = len(group)
        if size < 2:
            continue
        late_total = sum(1 for _, late in group if late)
        counts: Counter[str] = Counter(role for role, _ in group)
        late_of: Counter[str] = Counter(role for role, late in group if late)
        for role, mine in counts.items():
            rest = size - mine
            if not rest:
                continue
            observed[role] += late_of[role]
            expected[role] += mine * late_total / size
            variance[role] += (
                mine * rest * late_total * (size - late_total)
                / (size * size * (size - 1))
            )
            strata[role] += 1
            shares[role].append(
                late_of[role] / mine - (late_total - late_of[role]) / rest
            )
    tested = sorted(one for one in strata if strata[one] >= 10)
    if len(tested) < 2:
        return []
    found: list[Finding] = []
    for role in tested:
        if variance[role] <= 0:
            continue
        z = abs(observed[role] - expected[role]) / variance[role] ** 0.5
        corrected = math.erfc(z / (2 ** 0.5)) * len(tested)
        if corrected < 0.05:
            mean = sum(shares[role]) / len(shares[role])
            found.append(Finding(
                "hour_is_independent_of_role", "corpus", "corpus",
                f"{role!r} is sent after 13:00 {mean:+.0%} more often than the rest of its own "
                f"conversation, across {strata[role]} conversations: {observed[role]} late "
                f"against {expected[role]:.1f} expected, Mantel-Haenszel z={z:.2f}, corrected "
                f"p={corrected:.4f}. The clock says what the message is",
            ))
    return found


@dataclass(frozen=True)
class Rule:
    name: str
    family: str
    asserts: str
    check: Callable[[View], list[Finding]]


RULES: Final[tuple[Rule, ...]] = (
    Rule("uniform_reference", "corpus",
         "every message carries exactly one reference, so carrying one says nothing",
         _uniform_reference),
    Rule("no_discriminating_token", "corpus",
         "no word predicts that its message is the evidence", _no_discriminating_token),
    Rule("shape_carries_no_signal", "corpus",
         "no structural feature of a body predicts that the message was planted to be "
         "something", _shape_carries_no_signal),
    Rule("dates_advance", "corpus",
         "every reply is dated after the message it replies to", _dates_advance),
    Rule("body_diversity", "corpus",
         "the corpus is a population of messages rather than one message repeated",
         _body_diversity),
    Rule("distractors_are_wrong", "corpus",
         "no distractor states the answer of the thread it sits in", _distractors_are_wrong),
    Rule("siblings_agree", "corpus",
         "conversations about one matter do not state different answers", _siblings_agree),
    Rule("f1", "F1", "one identifier in one message, with a real near collision elsewhere", _f1),
    Rule("f2", "F2", "qualifying messages inside a window with 48-hour margins and decoys "
                     "outside it", _f2),
    Rule("f3", "F3", "a distinct fact at each declared sweep position with three distractor "
                     "kinds", _f3),
    Rule("f4", "F4", "zero content-word overlap between question and evidence; the decoy takes "
                     "the lexical hit", _f4),
    Rule("f5", "F5", "four stages, with the reminder later than the confirmation and stale", _f5),
    Rule("f6", "F6", "an authored claim plus second-hand reports that name its author", _f6),
    Rule("f7", "F7", "two conversations holding two halves, neither sufficient alone", _f7),
    Rule("f8", "F8", "the fact in the attachment, not in the body, with a same-named wrong copy",
         _f8),
    Rule("f10", "F10", "a proposal that nothing ever confirms", _f10),
    Rule("f11", "F11", "a trap that outranks its own evidence on a lexical query", _f11),
    Rule("f11_top", "F11", "F11's trap is the best lexical hit in its own conversation, so a "
                           "weak-hit escalation policy does not escalate (R-M2-067)",
         _f11_trap_is_the_top_hit),
    Rule("f12", "F12", "an exact match that beats the paraphrase-shaped neighbour", _f12),
    Rule("f13", "F13", "the answer after a named event, with competitive messages before it",
         _f13),
    Rule("f14", "F14", "a silent participant, a same-name decoy and a changed address", _f14),
    Rule("f15", "F15", "four structural shapes, each putting the answer outside the obvious "
                       "conversation", _f15),
    Rule("f16", "F16", "near-duplicates differing in one value, adopted by a message not by "
                       "recency", _f16),
    Rule("f17", "F17", "the reversal is the answer and is not what a query-score selector picks",
         _f17),
    Rule("older_value_is_older", "corpus",
         "a value the key calls superseded is not the newest thing its conversation says "
         "(R-M2-073)", _older_value_is_not_the_last_word),
    Rule("f7_halves_each_contested", "F7",
         "both halves of an F7 case carry a distractor (R-M2-073)",
         _f7_each_half_carries_a_distractor),
    Rule("f12_query", "F12",
         "F12's construction query is a quotable fragment of the evidence, not the sentence "
         "entire, and states none of the declared values (R-M2-073)",
         _f12_query_is_not_the_evidence),
    Rule("f15_split_cause", "F15",
         "the ceiling-split note claims no ceiling the corpus refutes (R-M2-073)",
         _f15_split_is_not_claimed_as_a_ceiling),
    Rule("f16_mechanism", "F16",
         "the figures are the only difference between F16's candidates and the confirmation is "
         "the only thing that names one (R-M2-068)", _f16_mechanism_is_necessary),
    Rule("f17_chain", "F17",
         "F17's reversal replies to one of the reinforcements, so the reply-chain floor has "
         "something to follow (R-M2-068)", _f17_reversal_answers_a_reinforcement),
    Rule("f13_chain", "F13",
         "F13's answer replies to the objection and the objector's acceptance replies to the "
         "answer, with more than one post-event value in play (R-M2-068)",
         _f13_reply_chain_is_load_bearing),
    Rule("scaffolding_not_family_exclusive", "corpus",
         "no entity-free, digit-free sentence is concentrated in one family beyond what that "
         "family's share of the corpus explains (R-M2-071)",
         _scaffolding_is_not_family_exclusive),
    Rule("role_positions_vary", "corpus",
         "no family lays every planted role at the same position in all of its instances "
         "(R-M2-072)", _role_positions_vary),
    Rule("hour_independent_of_role", "corpus",
         "no role's time of day differs from the rest of the corpus beyond chance (R-M2-072)",
         _hour_is_independent_of_role),
)

#: Checked by `tests/test_coverage_rules.py`. A rule with no negative fixture has not been
#: shown to be able to fail, and an unfailable rule is what R-M2-045 was.
RULES_WITHOUT_NEGATIVES: Final[tuple[str, ...]] = ()


def audit(manifest: Manifest) -> tuple[Finding, ...]:
    view = View(manifest)
    out: list[Finding] = []
    for rule in RULES:
        out.extend(rule.check(view))
    return tuple(out)


@dataclass(frozen=True)
class FamilyCoverage:
    family: str
    name: str
    registered: int
    declared: int
    authorable: int
    findings: tuple[Finding, ...]

    @property
    def shortfall(self) -> int:
        return max(0, self.registered - self.authorable)


def coverage(manifest: Manifest) -> tuple[FamilyCoverage, ...]:
    """Per family: how many threads carry no finding.

    `authorable` counts threads that pass, not threads that declare. That is the whole
    difference between this report and the one it replaces.
    """
    view = View(manifest)
    findings = audit(manifest)
    corpus_wide = tuple(one for one in findings if one.family == "corpus")
    out: list[FamilyCoverage] = []
    for key in sorted(REGISTERED_N, key=lambda one: int(one[1:])):
        mine = tuple(one for one in findings if one.family == key)
        broken = {one.where for one in mine}
        primary = view.primary(key)
        blocked = bool(corpus_wide) or any(one.where == "corpus" for one in mine)
        authorable = 0 if blocked else sum(
            1 for one in primary if one.thread_key not in broken
        )
        out.append(FamilyCoverage(
            family=key, name=FAMILY_NAMES[key], registered=REGISTERED_N[key],
            declared=len(primary), authorable=authorable, findings=mine + corpus_wide,
        ))
    return tuple(out)


def render(manifest: Manifest) -> str:
    rows = coverage(manifest)
    lines = [
        "corpus content coverage",
        f"  generator {manifest.generator_version}, seed {manifest.master_seed}, "
        f"profile {manifest.size_profile}",
        f"  {len(manifest.messages)} message(s) in {len(manifest.answer_key.threads)} thread(s)",
        "",
        f"  {'':>4} {'family':<30} {'need':>5} {'built':>6} {'clean':>6}  rule",
    ]
    for row in rows:
        mark = "ok  " if row.shortfall == 0 else "SHORT"
        rule = next((one.asserts for one in RULES if one.family == row.family), "")
        lines.append(
            f"  {mark:<4} {row.family + ' ' + row.name:<30} {row.registered:>5} "
            f"{row.declared:>6} {row.authorable:>6}  {rule}"
        )
    problems = audit(manifest)
    if problems:
        lines += ["", f"  {len(problems)} finding(s):"]
        for one in problems[:40]:
            lines.append(f"    [{one.rule}] {one.where}: {one.detail}")
        if len(problems) > 40:
            lines.append(f"    ... and {len(problems) - 40} more")
    else:
        lines += [
            "",
            "  No rule found a defect. That is a statement about the properties these rules "
            "check,",
            "  and the last version of this report passed a corpus an independent reader "
            "failed on",
            "  properties it did not have. An independent read is still the gate.",
        ]
    return "\n".join(lines)


__all__ = [
    "EVIDENCE_ROLES", "RULES", "RULES_WITHOUT_NEGATIVES", "FamilyCoverage", "Finding", "Rule",
    "View", "audit", "coverage", "render",
]
