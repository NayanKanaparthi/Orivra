"""Write the frozen corpus out in a form a reviewer can read without running the generator.

Three files per profile, into a directory:

  * `manifest.json` - the whole manifest, messages and answer key, as the generator produced it.
  * `answer-key.md` - every scored conversation in reading order: what it declares, what the
    text says, and which messages the key points at. This is the artefact a reader who is
    checking "is this question naturally answerable and is the stated answer correct" actually
    works from.
  * `threads/<thread_key>.txt` - each conversation as plain mail, in order, with the role the
    generator planted each message as. The roles are shown *because* the reviewer's job is to
    check them, not because a reader of the mailbox would see them.

Read-only. Nothing here generates, repairs or scores anything.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mailweave_harness.seed import corpus
from mailweave_harness.seed.families import FAMILY_NAMES, REGISTERED_N
from mailweave_harness.seed.manifest import Manifest, ThreadTruth


def _thread_text(built: Manifest, truth: ThreadTruth) -> str:
    rows = sorted(
        (one for one in built.messages if one.thread_key == truth.thread_key),
        key=lambda one: one.position,
    )
    head = [
        f"thread      {truth.thread_key}",
        f"family      {truth.family or '(unscored traffic)'} "
        f"{FAMILY_NAMES.get(truth.family, '')}",
        f"subject     {truth.subject}",
        f"scenario    {truth.scenario_key}",
        f"dates       {truth.first_date} to {truth.last_date}",
        f"length      {truth.length} messages, {len(truth.participants)} participants",
        f"answer      {truth.answer!r}",
        f"competitors wrong={truth.wrong_value!r} older={truth.older_value!r}",
        f"evidence at {truth.evidence_positions}",
        f"facts       {json.dumps(truth.facts, sort_keys=True)}",
        "",
        "note to the case author:",
        *(f"  {one}" for one in (truth.answer_note or "").splitlines()),
        "",
        "-" * 96,
        "",
    ]
    body = []
    for one in rows:
        marker = " <<< EVIDENCE" if one.position in truth.evidence_positions else ""
        body += [
            f"[{one.position:>3}] {one.role:<24} {one.date_rfc2822}{marker}",
            f"      from    {one.sender}",
            f"      subject {one.subject}",
            *(
                [f"      replies {one.in_reply_to}"]
                if getattr(one, "in_reply_to", None)
                else []
            ),
            *[
                f"      attach  {part.filename}: {part.content[:160]}"
                for part in one.attachments
            ],
            "",
            *(f"      {line}" for line in one.body.splitlines()),
            "",
        ]
    return "\n".join(head + body)


def _answer_key(built: Manifest) -> str:
    scored = [one for one in built.answer_key.threads if one.family and one.answer]
    lines = [
        "# Frozen corpus: the answer key a reviewer reads",
        "",
        f"generator {built.generator_version}, seed {built.master_seed}, "
        f"profile {built.size_profile}",
        f"{len(built.messages)} messages in {len(built.answer_key.threads)} conversations; "
        f"{len(scored)} of them declare a family and an answer",
        "",
        "Registered counts per family (EP §4.3, §4.7):",
        "",
        "| family | name | registered | built here |",
        "|---|---|---|---|",
    ]
    built_per = {
        key: len([
            one for one in built.answer_key.threads
            if one.family == key and not one.continues and not one.cross_thread_decoy_for
        ])
        for key in sorted(REGISTERED_N, key=lambda one: int(one[1:]))
    }
    for key, need in sorted(REGISTERED_N.items(), key=lambda one: int(one[0][1:])):
        lines.append(f"| {key} | {FAMILY_NAMES[key]} | {need} | {built_per[key]} |")
    lines += ["", "---", ""]
    for truth in sorted(scored, key=lambda one: one.thread_key):
        lines += [
            f"## {truth.thread_key} - {truth.family} {FAMILY_NAMES.get(truth.family, '')}",
            "",
            f"* subject: {truth.subject}",
            f"* answer: **{truth.answer!r}**, at position(s) {truth.evidence_positions}",
            f"* competitors: wrong={truth.wrong_value!r}, superseded={truth.older_value!r}",
            f"* facts: `{json.dumps(truth.facts, sort_keys=True)}`",
            f"* full text: `threads/{truth.thread_key}.txt`",
            "",
            (truth.answer_note or "").strip(),
            "",
        ]
    return "\n".join(lines)


def export(seed: int, profile: str, out: Path) -> dict[str, int]:
    built = corpus.generate(master_seed=seed, size_profile=profile)
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(built.model_dump_json(indent=1))
    (out / "answer-key.md").write_text(_answer_key(built))
    threads = out / "threads"
    threads.mkdir(exist_ok=True)
    for truth in built.answer_key.threads:
        (threads / f"{truth.thread_key}.txt").write_text(_thread_text(built, truth))
    return {
        "messages": len(built.messages),
        "threads": len(built.answer_key.threads),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=4311)
    parser.add_argument("--profile", default="sample")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.seed, args.profile, args.out), indent=1))


if __name__ == "__main__":
    main()
