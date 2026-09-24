# R-ARCH — Round 1 review (architecture and code quality)

**Reviewer:** R-ARCH · **Date:** 2026-08-31 · Fresh instance, no prior-round context.
**Scope:** WS-00, WS-19, WS-01, WS-07 (my assigned criteria); read WS-03 (envelope/disposition)
for architectural fidelity per the work order's binding constraints and this review's brief, since
extensibility of the ledger seam cannot be judged without it.

## Execution record (AGENT_LOOP §7.1)

All commands run by me, not taken from HANDOFF.md:

1. **In place** (`/root/mailweave`, uv 0.8.17, system Python 3.11 but `.python-version`
   pins 3.12 and `uv` resolved CPython 3.12.3 automatically): read every file in `tests/`
   (12 files, ~2,650 lines) and the source under `server/src/mailweave/{envelope,content,net,auth}`,
   `config.py`, `tools/guards/sweeps.py`, `tools/rubric_status.py`.
2. **Clean-copy reproduction** (`/tmp/mw-review/fresh/mailweave`, full copy, caches wiped):
   - `uv sync --all-packages --extra dev --frozen` → clean install, 29 packages, no network needed
     beyond the local wheel cache (already warm; not independently verified network-free from a
     truly empty cache).
   - `uv run ruff check .` → `All checks passed!`
   - `uv run mypy` → `Success: no issues found in 55 source files`
   - `uv run pytest -q -m "not network"` → `199 passed in 3.64s` (matches HANDOFF exactly)
   - `uv run python -m tools.guards` → clean over all six guards
   - `uv run python tools/rubric_status.py --check` → 113 criteria, 0 PASS, 0 FAIL, 0 BLOCKER,
     113 NOT TESTED, 0 transitions — consistent with an honest "nothing certified yet" state
   - `uv run ruff format --check .` (run separately; CI runs it as its own step, `make check`
     does not) → **one file would be reformatted**: `docs/reviews/ROUND_01/R-SEC.md` (a fenced
     code block in a prior reviewer's own report, not implementer source — see R-ARCH-007).
3. **Adversarial probes**, written to `/tmp/mw-review/` only (never touched project source/tests):
   `test_quote_stripper.py`, `test_html_quote.py` (9 realistic reply-chain shapes: Gmail top-post,
   Outlook header block, mobile sig, 4-level nesting, forwarded message, French "wrote:", sig with
   no `--` delimiter, bare quote with no attribution, false-positive `>`, and an HTML-only
   Gmail-web blockquote); `test_conservation_gap.py` (monkeypatched quote stripper that
   under-reports its removal); `test_ledger_bypass.py` (a caller that records 10 of 100 fetched
   IDs). All outputs quoted in the findings below.

No finding here is asserted without a command or script that produced it.

## Findings

**R-ARCH-001 · HIGH**
Rubric: DISC-03. Location: `server/src/mailweave/content/quotes.py:65-76`.
Reproduction: `/tmp/mw-review/test_quote_stripper.py`, cases `outlook_header_block` and
`forwarded_message`.
Expected: D.4a §6 declares two reduction kinds — `quoted` (reply chain) and `signature`. An
Outlook-style `From:/Sent:/To:/Subject:` quote block or a `-------- Original Message --------`
forward is quoted prior conversation, not a signature.
Actual: `email_reply_parser` marks these fragments `hidden` (not `quoted`), and `quotes.py`'s
comment at line 71-74 folds every `hidden` fragment into `signature_chars`. Both fixtures produced
`quoted_chars=0`, with the entire prior message (347 and 181 chars respectively) declared as
`kind="signature"`. The content is correctly *removed*; the declaration is *mislabeled*.
Required fix: split `hidden` fragments that match a quote-header shape (From/Sent/To/Subject or a
date-prefixed separator) into `QUOTED`, reserving `SIGNATURE` for trailing sign-offs — or, at
minimum, rename/document the fallback's semantics so a downstream reader of `reductions[].kind`
is not misled about what was removed.

**R-ARCH-002 · HIGH**
Rubric: DISC-03 (declared-reduction contract); corroborates HANDOFF §5's own flagged risk.
Location: `server/src/mailweave/content/quotes.py` (fallback stripper, whole module).
Reproduction: `/tmp/mw-review/test_quote_stripper.py`, case `sig_no_delimiter` vs the `-- `-delimited
comparison case appended to the same file.
Expected: a common corporate signature block (`Best regards,\nName\nTitle\nCompany\nPhone`) is
declared and removed, per D.4a §6's purpose (token economics).
Actual: with a `--` delimiter, 86 chars are stripped and declared. Without one (the majority
convention among Outlook/Gmail web users), **zero characters are stripped or declared** — the
signature is silently retained inside `body_clean`, consuming disclosure/token budget with no
`reductions[]` entry at all. This is a genuinely silent reduction-that-should-have-happened, not
merely a mislabeled one.
Required fix: not a code fix this round (`talon`'s absence is an owner-known, already-disclosed
substitution) — but this specific failure mode should become a tracked WS-17 regression fixture
before DISC-03/GMAIL-02 are claimed against real mail, since HANDOFF currently states the risk as
a hypothesis ("I expect... I have no measurement") and this review turns it into a measured fact.

**R-ARCH-003 · MEDIUM**
Rubric: DISC-03 / GMAIL-02 fixture coverage. Location: `content/quotes.py` (English-only
attribution-line patterns inherited from `email_reply_parser`).
Reproduction: `/tmp/mw-review/test_quote_stripper.py`, case `french_wrote`.
Expected: the reply is separated cleanly from the quoted chain.
Actual: `reply == "D'accord, allons-y.\n\nLe mar. 25 août 2026 à 15:14, Priya Shah <...> a écrit :"`
— the French attribution line is left dangling in the "new content" half, un-declared as either
quote or noise, while the quoted body beneath it is correctly stripped.
Required fix: add non-English fixtures to the WS-07/WS-17 fixture set; no code fix is owed by this
round's mandate.

**R-ARCH-004 · MEDIUM (test quality, AGENT_LOOP §7.2)**
Rubric: DISC-03 ("Silent reductions: 0"). Location: `server/src/mailweave/content/pipeline.py`
(no cross-check between actual shrinkage and declared total);
`tests/test_content_pipeline.py:184-226` (`test_no_fixture_loses_characters_without_declaring_a_reduction`,
the hypothesis property `test_arbitrary_bodies_never_crash_the_pipeline_and_never_shrink_silently`).
Reproduction: `/tmp/mw-review/test_conservation_gap.py` — monkeypatches `strip_quotes_and_signature`
to strip the real 220 characters of quoted content from the `nested_multipart` fixture but declare
only `quoted_chars=1`. Output:
```
declared reduction total (chars): 1
body_clean length: 25          source_length: 245
TEST test_no_fixture_loses_characters_without_declaring_a_reduction WOULD PASS
  (declared=1, actual_shrink=220)
```
Expected: the property both tests intend to check is "the declared total accounts for what was
removed" (that is what DISC-03's "declared in place with a size count" means).
Actual: both tests assert only `declared > 0` (fixture test) or `any(removed_chars>0 or count>0
for ...)` (property test) — presence, not magnitude. A reduction that under-reports its size by two
orders of magnitude passes both. This is the same "silent-loss-that-a-later-stage-doesn't-notice"
failure mode the disposition ledger (A.7a) was built specifically to structurally rule out for IDs
— the pattern was not carried over to characters, the other quantity D.4a cares about.
Required fix: either add a stage-boundary assertion in `pipeline.py` comparing declared totals to
actual length deltas (mirroring `DispositionLedger.certify`'s set-difference-and-raise shape), or at
minimum strengthen the two tests to bound `declared_total` against the real shrinkage rather than
checking non-zero presence.

**R-ARCH-005 · MEDIUM (extensibility — priority #4 of this review)**
Rubric: EV-01/EV-03 (WS-03), directly relevant to WS-02's design, which starts next round.
Location: `server/src/mailweave/envelope/disposition.py:134-164` (`record_list_page` accepts any
caller-supplied `Iterable[str]`); no WS-02 Gmail client exists yet to constrain it.
Reproduction: `/tmp/mw-review/test_ledger_bypass.py` — a stand-in `fake_gmail_messages_list`
returns 100 real hit IDs; the "caller" records only the first 10 into the ledger. Output:
```
Envelope built successfully: answered
H (ledger.hit_ids) size: 10   disclosed size: 10   withheld size: 0
'real-hit-50' not in envelope.disclosed_ids and not in ledger.hit_ids: True
```
The invariant `H == disclosed ∪ withheld` held — vacuously, because the 90 unrecorded IDs were
never in `H`. This is exactly the gap the implementer self-flagged in HANDOFF §6 ("If a reviewer
looks at one thing, look at this seam") and the orchestrator's probe already confirmed; I
independently reproduced it rather than taking either claim on faith.
Assessment of the proposed fix's fit: **natural, not awkward.** `record_list_page` already returns
exactly the object (`ScanScopeEntry`) a transport method should hand back. The fix is to make the
raw ID list simply inexpressible outside the ledger call:
```python
def list_messages(
    self, ledger: DispositionLedger, *, rung: RungId, query: str, page_token: str | None = None
) -> ScanScopeEntry:
    response = self._get(GMAIL_MESSAGES_LIST, params={...})
    ids = [m["id"] for m in response.get("messages", [])]
    return ledger.record_list_page(
        rung=rung, query=query, ids=ids, page_size=..., more_pages="nextPageToken" in response,
    )
```
No method on the future `GmailClient` should ever return `list[str]`/a bare page object; the HTTP
call and the ledger write must be the same call, so a caller cannot observe fetched IDs without
having already recorded them. The identical shape applies to `history.list` →
`record_history_additions` and the L5 participant probes → the same `record_list_page` path. This
is a design note for WS-02's work order, not a defect in this round's code — WS-03 already built
the right-shaped receiving end.

**R-ARCH-006 · LOW**
Rubric: SEC-07-adjacent (WS-02 territory, flagged now while the seam is open).
Location: `server/src/mailweave/net/egress.py:78-84` — `build_client`/`build_async_client` are
"the only supported way to get an HTTP client" per docstring, but nothing enforces it. The six
guards in `tools/guards/sweeps.py` do not cover direct `httpx.Client()`/`httpx.AsyncClient()`
construction.
Required fix: add a seventh AST guard forbidding those constructor calls outside `net/egress.py`,
mirroring `unaudited_disk_write_sweep`'s shape (already a `_WRITE_ALLOWLISTED_MODULES`-style
pattern this project uses elsewhere).

**R-ARCH-007 · LOW**
Location: `docs/reviews/ROUND_01/R-SEC.md:130` (a fenced code block, not implementer source).
`ruff format --check .` — which CI runs as its own step and which HANDOFF lists as one of five
individually-runnable commands — currently fails on this file; `make check` does not run
format-check at all, so this drift is invisible from the one command reviewers were told to run.
Not a code defect; recommend excluding `docs/reviews/` from ruff's markdown formatting, or folding
`ruff format --check .` into `make check`/`gate` since CI already runs it separately.

**R-ARCH-008 · LOW (tracked ambiguity, not a defect)**
HANDOFF §3.3's self-flagged D.2-vs-R-05 arithmetic conflict on `included`/`included_as_stub`
(`wire.py:397-423`) is real and correctly disclosed; the implementer's chosen reading (R-05,
subset semantics) is internally consistent and PART-02-compliant. This needs an orchestrator
ruling to close, not a code change from this round.

## The "hollow implementation would pass" list (priority #2)

| Mechanism | Verdict | Basis |
|---|---|---|
| Disposition ledger's **internal** set-difference (`certify`) | **Not hollow-able.** `test_disposition_property.py`/`test_disposition_invariant.py` are genuinely adversarial (unforgeable mint token, certificate-to-payload binding, all three residue directions, `python -O` subprocess test for the assert-vs-raise distinction). | Read + ran the suite; tried to construct a bypass and could not without importing the private `_MINT_TOKEN`, which the tests already document as the accepted, narrow exception. |
| Disposition ledger's **boundary** (what gets recorded in the first place) | **Hollow today, by omission of the caller, not the ledger.** Nothing yet exists to record incompletely — but the type signature places no obligation on a future `messages.list` wrapper to record everything it fetches. | R-ARCH-005, demonstrated. |
| Envelope validators (`response.py`) | **Not hollow-able.** Every "computed, never asserted" field (`partial`, `included`, `withheld`) is re-derived from the payload and compared; a hollow builder that hardcodes `partial=False` fails immediately. | Read all nine `model_validator`s; each recomputes rather than trusts. |
| Content pipeline's **declared-removal accounting** | **Hollow.** A stage can remove hundreds of characters and declare a `removed_chars` of 1, and the offline suite (fixture test + hypothesis property) still passes. | R-ARCH-004, demonstrated. |
| Content pipeline's **presence** of a reduction (all-or-nothing) | **Not hollow-able** for a no-op stripper: `test_a_quoted_chain_is_stripped_and_the_removal_is_counted` checks that specific quoted substrings are *absent* from `reply`, so a stripper that does nothing fails outright. Only the *magnitude* of what it does report is unchecked. | Read the test; ran it. |
| Egress allowlist (`AllowlistTransport`) itself | **Not hollow-able.** Tests use a recording inner transport and assert zero requests reach it for blocked hosts, including a suffix-attack case (`gmail.googleapis.com.evil.example`) and an http-vs-https case. | Read + ran `test_egress.py`. |
| Egress allowlist's **adoption** (`build_client` as "the only way") | **Hollow, structurally open.** No guard stops a future module from calling `httpx.Client()` directly. | R-ARCH-006. |
| Config / token store / profile derivation | **Not hollow-able.** Refusal-first design throughout (over-permissive file/dir refused not repaired, seed profile needs two independently-satisfied conditions, `getProfile` failure is fatal not defaulted); tests assert refusal in every case I checked, including a forged `seed_account_hash` that cannot also satisfy the client-id condition. | Read `config.py`, `auth/*.py`, `tests/test_auth_and_config.py` in full. |
| AST guards (WS-00) | **Not hollow-able for what they cover.** Each of the six has a planted-violation test *and* a "does not fire on the legitimate shape" test — the harder property to get right. Missing coverage (R-ARCH-006) is a gap in the *set* of guards, not a hollow guard. | Read `tools/guards/sweeps.py` + `tests/test_guards.py` in full. |
| Rubric gate integrity (WS-19, `rubric_status.py`) | **Not hollow-able.** Tests cover a PASS with no transition, a transition signed by a non-reviewer domain, a transition missing reproduction evidence, and a summary/detail-block disagreement. | Read + ran `test_rubric_status.py`; ran `tools/rubric_status.py --check` myself. |

## Quote-stripper verdict (priority #3 — talon substitution)

The `email-reply-parser` fallback is an honest, licence-compatible substitution for `talon`, and the
substitution itself was correctly disclosed rather than hidden. On the fixture the implementer wrote
(a clean, single-level, English, `>`-quoted Gmail-style chain with a `--`-delimited signature) it
works correctly. Against the broader realistic set I tested — Gmail top-post, 4-level nesting,
mobile top-post, HTML-only Gmail-web blockquote, and a bare `>` quote with no attribution — it also
works correctly, sometimes via a fragment-classification path (`hidden`) that mislabels quoted
content as signature (R-ARCH-001) but never leaks it. Against Outlook/O365-style header-block quotes
and forwards it works (strips, mislabeled) but against a **corporate signature with no `--`
delimiter it fails completely** (R-ARCH-002, zero chars removed) and against **non-English
attribution lines it leaves a dangling fragment** (R-ARCH-003). HANDOFF §5 correctly predicted this
class of defect in the abstract ("I expect materially worse recall... and I have no measurement");
this review supplies the measurement. **Verdict: adequate as a stopgap given the `cchardet`/Python
3.12 constraint is real and unavoidable within this round's scope, but it is a quality regression
the project must track, not merely disclose** — it should not be allowed to sit as an
"unmeasured risk" through another round once GMAIL-02's real-mailbox fixtures exist.

## Per-criterion recommendations — WS-00, WS-19, WS-01, WS-07

None of these move to `PASS` on my report alone: several are explicitly multi-domain
(`SEC-*` name R-SEC as verifier; `PROC-01/02/04/06` name the **adversarial reviewer**, not R-ARCH,
per the rubric's own `Verify` field, even though `IMPLEMENTATION_PLAN.md` lists R-ARCH against
WS-19). Where I list "R-ARCH: supports PASS", the orchestrator still needs the paired domain's
report before the rubric table is edited.

| Criterion | WS | R-ARCH recommendation | Why |
|---|---|---|---|
| NFR-01 | 00 | **Not yet PASS** | Requires the semantic rung "exercised... in key-free configuration" (Appendix A.1); it does not exist this round. |
| NFR-04 | 00/01 | **R-ARCH: supports PASS** | I independently reproduced the clean-machine bootstrap (lockfile → green offline suite) myself, per this criterion's own `Verify` line. |
| PROC-03 | 00/19 | **R-ARCH: supports PASS** (needs adversarial reviewer too) | Ground-truth sweep is structurally sound (AST-based, tested against both violation and legitimate-prose cases); I found no server-side path to `mailweave_harness` or manifest files. |
| REG-03 | 00 | **R-ARCH: supports PASS** | No benchmark-specific literals, case IDs, or special-cased query strings found in `server/**` or `tests/**` in my read. |
| SEC-01 | 00/01 | **Not yet PASS (R-ARCH half only)** | Guard + config both correctly enforce exactly one scope literal; final PASS is R-SEC's call per the rubric's `Verify` field. |
| SEC-02 | 00/01 | **Not yet PASS** | No tool/MCP surface exists yet to evaluate "no write path reachable from any tool" against; the read-only client constraint (`ClientDescriptor` refuses `SEEDER`) is necessary but not sufficient evidence. |
| SEC-08 | 00 | **R-ARCH: supports PASS** | No learned scorer exists; `generative_client_sweep` covers the adjacent generative-call constant, and no routing logic exists yet to smuggle a learned threshold into. |
| SEC-03 | 01 | **Not yet PASS (R-ARCH half only)** | `ClientDescriptor.__post_init__` refuses the seeder role structurally, and the harness's own scope isolation is real; R-SEC owns the final call. |
| SEC-04 | 01 | **Not yet PASS (R-ARCH half only)** | Token-store code is genuinely solid (open-time mode, umask-proof, refuse-don't-repair); R-SEC's sign-off is still required per `Verify`. |
| GMAIL-06 | 01 | **Not yet PASS** | HANDOFF is explicit and correct: no refresh/expiry/re-auth code path exists this round. |
| GMAIL-02 | 07 | **Not yet PASS** | Requires "real-mailbox messages" (this criterion's own `Verify` names R-GMAIL on a live sample); this round is synthetic fixtures only, and R-ARCH-002/003 show the synthetic fixtures already understate real-world failure modes. |
| INJ-04 | 07 | **Not yet PASS** | Hidden-construct removal and the zero-network proof are solid and I re-ran them; but "declared" is weaker than claimed per R-ARCH-004, and this criterion's own `Verify` names R-SEC, not R-ARCH, as the deciding domain. |
| DISC-03 | 07 | **Not yet PASS** | "Silent reductions: 0" is asserted by tests that check presence, not magnitude (R-ARCH-004), and two concretely silent/mislabeled cases exist in realistic (not adversarially-constructed) input (R-ARCH-001/002). |
| PROC-01 | 19 | **Not R-ARCH's call** | `Verify` names the adversarial reviewer. Machinery works: `--check` correctly reports 113/113 `NOT TESTED`, 0 `PASS`. |
| PROC-02 | 19 | **Not R-ARCH's call** | Same; no PASS exists yet to certify improperly, so vacuously satisfied today, but the adversarial reviewer sets status. |
| PROC-04 | 19 | **Not yet PASS** | No baselines exist this round (WS-16 territory); criterion cannot be evaluated. |
| PROC-05 | 19 | **R-ARCH: satisfied for my own findings** | This report itself names the dumbest passing implementation for every mechanism in scope (see table above); other domains' metrics are theirs to cover. |
| PROC-06 | 19 | **Not yet PASS** | This review is not the designated adversarial pass; no such pass has run yet. |

## Summary

Zero BLOCKER findings. Two HIGH findings (R-ARCH-001, R-ARCH-002), both in the quote-stripper
fallback and both real, demonstrated, previously-hypothesized-but-unmeasured defects rather than
speculative ones. Three MEDIUM findings, one of which (R-ARCH-004) is a genuine test-quality gap in
the project's own anti-silent-reduction machinery, and one (R-ARCH-005) confirms and gives concrete
shape to the extensibility gap the implementer and orchestrator had already flagged. The envelope,
disposition ledger, config, auth and guard machinery are unusually strong: adversarial by
construction, not merely by test count, and I was unable to find a hollow variant of any of them
that the existing suite would miss. The clean-machine build reproduced exactly (199/199 tests,
clean lint/types/guards/gate) on an independent copy.
