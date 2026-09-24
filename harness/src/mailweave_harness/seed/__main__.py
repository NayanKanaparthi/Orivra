"""`python -m mailweave_harness.seed` - generate a corpus and write its manifest.

    --generate --out DIR      write `manifest.json` for one (seed, profile). Offline: no
                              credential, no mailbox, no network.
    --profiles                the shipped size profiles and what each holds.
    --regenerate-check        generate twice and compare, which is EP §3.7's regeneration
                              contract checked rather than asserted.
    --coverage MANIFEST       per-family authorable units against the registered counts.
                              Exit 2 if any family is short. **Run this before seeding**:
                              threading and sentinel checks establish mailbox structure, not
                              evaluation readiness, and R-M2-041 is what that gap cost.

    --plan-seeding            everything a seeding run would do, printed. Every refusal that
                              can fire without a network call fires here. Nothing is sent.
    --survey                  read-only: how much mail is already in the account, and whether
                              any manifest sentinel already matches something in it.
    --rehearse-threading      the smallest live write that proves threading works: insert the
                              first few messages of one thread, then ask `threads.get` whether
                              they are one conversation. Writes `--rehearsal-messages` (4)
                              messages and records their ids for cleanup.
    --login                   the harness credential's consent flow at
                              `https://mail.google.com/`, into its own token store.
    --seed-mailbox            insert the corpus, verify it, wait for the settle gate, and
                              write the verification report the metric run reads.
    --cleanup REPORT          delete exactly the ids that report records, and nothing else.

**The three write commands refuse unless `--approve-writes-to` names the seed account.** Not a
`--yes`: an approval that does not name what it approves is a keystroke. Four refusals stand in
front of the first write and `seed/driver.py` states each one and why it is there. The short
version: the harness client may not be the server's, the harness token store may not be the
server's, the requested scope set is exactly `https://mail.google.com/`, and the authenticated
address is compared with the declared seed address through a real `getProfile` before the first
insert and again before the first delete.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mailweave_harness.seed.corpus import GENERATOR_VERSION, PROFILES, generate
from mailweave_harness.seed.families import REGISTERED_N
from mailweave_harness.seed.manifest import Manifest


def _profiles() -> str:
    lines = ["corpus size profiles", ""]
    for name, profile in sorted(PROFILES.items()):
        registered = sum(REGISTERED_N.values())
        lines.append(
            f"  {name:<7} {profile.registered_cases:>3} of {registered} registered case(s), "
            f"long threads of {profile.long_length}, {profile.filler_threads} filler thread(s)"
        )
    lines += [
        "",
        f"generator version {GENERATOR_VERSION}. The same (version, seed, profile) produces a",
        "byte-identical corpus; a different seed produces the same shapes with re-randomised",
        "surfaces, which is EP §5.3's anti-gaming lever.",
    ]
    return "\n".join(lines)


DEFAULT_TOKEN_PATH = Path("~/.mailweave-harness/credentials.json")


def _path(raw: str) -> Path:
    """Every path argument, expanded. **A `~` a shell did not expand is still a home directory.**

    `--token-path ~/x` written unquoted is expanded by the shell and arrives absolute; the same
    string as a default, or quoted, or from a script, arrives with a literal tilde - and
    `TokenStore` stats it and reports "~/.mailweave-harness does not exist", which reads like a
    missing login rather than an unexpanded path. Expanding here, where a user-supplied path
    enters the program, is the one place that covers all of those.
    """
    return Path(raw).expanduser()


def _manifest_at(path: Path) -> Manifest:
    return Manifest.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _approved(args: argparse.Namespace) -> bool:
    """`--approve-writes-to` must *name* the seed account, and match it."""
    given = (args.approve_writes_to or "").strip().lower()
    wanted = args.seed_address.strip().lower()
    if not given:
        return False
    if given != wanted:
        raise SystemExit(
            f"--approve-writes-to {given!r} does not name the configured seed account "
            f"({wanted!r}). Nothing was sent."
        )
    return True


def _seeding(args: argparse.Namespace) -> int:
    import time

    from mailweave_harness.seed import driver

    manifest = _manifest_at(args.manifest)
    try:
        planned = driver.plan(
            manifest,
            seed_address=args.seed_address,
            client_path=args.client_path,
            token_path=args.token_path,
            approved=_approved(args),
            server_client_path=args.server_client_path,
            server_token_path=args.server_token_path,
            resume_from=args.resume,
        )
    except driver.SeedingRefused as refused:
        print(f"REFUSED: {refused}")
        return 2
    print("seeding plan")
    for line in planned.lines():
        print(line)
    if args.plan_seeding:
        print(
            "\n  --plan-seeding: nothing was sent. The OAuth client file was read "
            "(its client id is above); the token store was not opened."
        )
        return 0
    if not planned.approved:
        print(
            "\n  no --approve-writes-to, so nothing was sent. Re-run with "
            f"--approve-writes-to {planned.seed_address}"
        )
        return 1
    transport = driver.transport_for(
        client_path=args.client_path,
        token_path=args.token_path,
        seed_address=planned.seed_address,
        approved=True,
    )
    out = args.out / f"verification-{args.manifest.stem.removeprefix('manifest-')}.json"
    prior = () if args.resume is None else driver.report_from(args.resume).inserted
    if prior:
        print(f"\n  resuming: {len(prior)} message(s) already inserted by {args.resume}")
    report = driver.run_seeding(
        transport,
        manifest,
        seed_address=planned.seed_address,
        out=out,
        sleep=time.sleep,
        clock=time.monotonic,
        prior=prior,
    )
    print(f"\n  inserted {len(report.inserted)} message(s); report written to {out}")
    print(f"  discrepancies: {len(report.discrepancies)}")
    return 0 if not report.discrepancies else 2


def _survey(args: argparse.Namespace) -> int:
    """Read-only: what is already in the mailbox, and whether any sentinel collides."""
    from mailweave_harness.seed import driver

    manifest = _manifest_at(args.manifest)
    transport = driver.transport_for(
        client_path=args.client_path,
        token_path=args.token_path,
        seed_address=args.seed_address.strip().lower(),
        approved=False,  # reads only; a write on this transport would still be refused
    )
    found = driver.survey(transport, manifest)
    print("mailbox survey (read-only; nothing was written)")
    for line in found.lines():
        print(line)
    return 0 if found.safe else 2


def _rehearse(args: argparse.Namespace) -> int:
    """The smallest live write that answers the threading question. Writes a few messages."""
    from mailweave_harness.seed import driver

    manifest = _manifest_at(args.manifest)
    if not _approved(args):
        print(
            "the threading rehearsal inserts a few real messages. Re-run with "
            f"--approve-writes-to {args.seed_address.strip().lower()}"
        )
        return 1
    transport = driver.transport_for(
        client_path=args.client_path,
        token_path=args.token_path,
        seed_address=args.seed_address.strip().lower(),
        approved=True,
    )
    out = args.out / f"rehearsal-{args.manifest.stem.removeprefix('manifest-')}.json"
    found = driver.rehearse_threading(
        transport,
        manifest,
        seed_address=args.seed_address.strip().lower(),
        messages=args.rehearsal_messages,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "inserted": [
                    {
                        "rfc822_message_id": one.rfc822_message_id,
                        "gmail_id": one.gmail_id,
                        "thread_id": one.thread_id,
                    }
                    for one in found.inserted
                ],
                "discrepancies": [],
                "rehearsal": True,
                "conversation": found.conversation,
                "members_from_gmail": list(found.members_from_gmail),
                "passed": found.passed,
                "note": (
                    "A threading rehearsal, not a corpus. These ids are recorded so "
                    "`--cleanup` on this file removes exactly them."
                ),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("threading rehearsal")
    for line in found.lines():
        print(line)
    print(f"\n  ids recorded in {out}; nothing else in the mailbox was touched")
    return 0 if found.passed else 2


def _cleanup(args: argparse.Namespace) -> int:
    from mailweave_harness.seed import driver

    if not _approved(args):
        print(
            "cleanup deletes mail. Re-run with --approve-writes-to "
            f"{args.seed_address.strip().lower()}"
        )
        return 1
    report = driver.report_from(args.cleanup)
    transport = driver.transport_for(
        client_path=args.client_path,
        token_path=args.token_path,
        seed_address=args.seed_address,
        approved=True,
    )
    record = args.out / f"cleanup-{args.cleanup.stem}.json"
    print(
        f"deleting {len(report.inserted)} recorded id(s). This is permanent: "
        "`users.messages.delete` does not use the trash and cannot be undone."
    )
    result = driver.run_cleanup(transport, report, seed_address=args.seed_address, out=record)
    print(f"\n  targeted:      {len(report.inserted)} recorded id(s)")
    print(f"  deleted:       {len(result.deleted)}")
    print(f"  already gone:  {len(result.already_gone)}")
    print(f"  failed:        {len(result.failed)}")
    if result.failed:
        shown = ", ".join(one.gmail_id for one in result.failed[:5])
        print(f"    first few: {shown}")
        print("    re-run this same command: ids already removed report as `already gone`")
    print(f"\n  record written to {record}")
    return 0 if result.complete else 2


def _login(args: argparse.Namespace) -> int:
    from mailweave.auth.consent import LoopbackReceiver
    from mailweave_harness.seed import driver

    receiver = LoopbackReceiver()

    def wait_for_code(authorization_url: str, _state: str) -> str:
        print("\nOpen this URL and consent as the SEED account only:\n")
        print(f"  {authorization_url}\n")
        print(f"Waiting for the redirect on 127.0.0.1:{receiver.port} ...")
        return receiver.wait_for_redirect()

    try:
        report = driver.login(
            client_path=args.client_path,
            token_path=args.token_path,
            seed_address=args.seed_address,
            wait_for_code=wait_for_code,
            port=receiver.port,
            server_client_path=args.server_client_path,
            server_token_path=args.server_token_path,
        )
    except driver.SeedingRefused as refused:
        print(f"REFUSED: {refused}")
        return 2
    finally:
        receiver.close()
    print(f"\n  account:         {report.account}")
    print(f"  granted scopes:  {' '.join(report.granted_scopes)}")
    print(f"  token store:     {report.token_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mailweave-seed", description=__doc__)
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--profiles", action="store_true")
    parser.add_argument("--regenerate-check", action="store_true")
    parser.add_argument(
        "--coverage",
        type=_path,
        default=None,
        metavar="MANIFEST",
        help=(
            "per-family authorable units in a generated corpus, against the counts "
            "EVALUATION_PLAN registers. Offline. Exit 2 if any family is short - a corpus "
            "that cannot support the registered families must not be seeded"
        ),
    )
    parser.add_argument("--seed", type=int, default=None, metavar="N")
    parser.add_argument("--profile", default="smoke", choices=sorted(PROFILES))
    parser.add_argument("--out", type=_path, default=Path("benchmarks"))
    parser.add_argument("--plan-seeding", action="store_true")
    parser.add_argument("--survey", action="store_true")
    parser.add_argument("--rehearse-threading", action="store_true")
    parser.add_argument("--rehearsal-messages", type=int, default=4, metavar="N")
    parser.add_argument("--login", action="store_true")
    parser.add_argument("--seed-mailbox", action="store_true")
    parser.add_argument("--cleanup", type=_path, default=None, metavar="REPORT")
    parser.add_argument("--manifest", type=_path, default=None, metavar="PATH")
    parser.add_argument(
        "--resume",
        type=_path,
        default=None,
        metavar="REPORT",
        help=(
            "the partial verification report a failed run wrote. Its messages are not "
            "inserted again and count as present, so a run that died at message 2,000 "
            "finishes rather than duplicating two thousand messages"
        ),
    )
    parser.add_argument("--seed-address", default="", metavar="ADDRESS")
    parser.add_argument(
        "--approve-writes-to",
        default=None,
        metavar="ADDRESS",
        help=(
            "the seed account, typed out. Every write command refuses without it, and "
            "refuses if it names a different address than the run is configured for"
        ),
    )
    parser.add_argument(
        "--client-path",
        type=_path,
        default=Path("mailweave-harness-oauth.json"),
        metavar="PATH",
    )
    parser.add_argument(
        "--token-path", type=_path, default=DEFAULT_TOKEN_PATH.expanduser(), metavar="PATH"
    )
    parser.add_argument(
        "--server-client-path", type=_path, default=Path("mailweave-server-oauth.json")
    )
    parser.add_argument("--server-token-path", type=_path, default=None)
    args = parser.parse_args(argv)

    mailbox = (
        args.plan_seeding
        or args.login
        or args.survey
        or args.rehearse_threading
        or args.seed_mailbox
        or args.cleanup is not None
    )
    if mailbox:
        if not args.seed_address:
            raise SystemExit("--seed-address names the account this run may touch; it is required")
        if args.login:
            return _login(args)
        if args.cleanup is not None:
            return _cleanup(args)
        if args.manifest is None:
            raise SystemExit(
                "--plan-seeding, --survey, --rehearse-threading and --seed-mailbox all "
                "need --manifest"
            )
        if args.survey:
            return _survey(args)
        if args.rehearse_threading:
            return _rehearse(args)
        return _seeding(args)

    if args.coverage is not None:
        from mailweave_harness.seed.coverage import coverage, render

        loaded = _manifest_at(args.coverage)
        print(render(loaded))
        return 0 if all(one.shortfall == 0 for one in coverage(loaded)) else 2
    if args.profiles or not (args.generate or args.regenerate_check):
        print(_profiles())
        return 0
    if args.seed is None:
        raise SystemExit("--generate and --regenerate-check both need --seed")

    manifest = generate(master_seed=args.seed, size_profile=args.profile)
    if args.regenerate_check:
        again = generate(master_seed=args.seed, size_profile=args.profile)
        same = manifest.model_dump_json() == again.model_dump_json()
        print(f"regeneration contract (EP §3.7): {'holds' if same else 'BROKEN'}")
        return 0 if same else 2

    target = args.out / f"manifest-{args.profile}-{args.seed}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    print(f"wrote {target}")
    print(
        f"  {len(manifest.messages)} message(s), {len(manifest.answer_key.threads)} thread(s), "
        f"{len(manifest.sentinels)} sentinel(s)"
    )
    print(
        "  no mailbox was touched. `--plan-seeding --manifest <this file> --seed-address "
        "<account>` prints exactly what seeding it would do, and sends nothing."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
