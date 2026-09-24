# R-SEC — Round 2 Security & Privacy Review

**Reviewer:** R-SEC (fresh instance, did not write this code or Round 1's review) · 2026-08-31
**Scope:** H3 (AST guards), H4 (HTML depth/size caps), M2 (atomic `TokenStore.save`), M3
(bidi overrides), per `ROUND_02/WORK_ORDER.md`. `HANDOFF.md` claims were not trusted; every
number below was reproduced by execution. Baseline: `make check` clean (ruff, format-check,
mypy strict/61 files, pytest 297 passed, guards clean, rubric-status 113 NOT TESTED / 0
transitions). Probes live under `/tmp/.../scratchpad/sec2/`; no project source or test file
was modified.

## Verdicts

| Finding | Verdict | Basis |
|---|---|---|
| **H3** | **PARTIALLY CLOSED** | Round 1's exact bypass (concatenation/f-string, dynamic import, `Path.open`/`os.write`) is genuinely fixed and honestly documented. But two new, equally trivial, **undocumented** bypass classes exist: byte-string literals (defeats 4 of 6 guards at once) and several disk-write evasions (R-SEC-008, R-SEC-009, R-SEC-010). The "narrowed and honest" half of H3's claim is not yet true. |
| **H4** | **CLOSED** | Timing reproduced almost exactly (200k tags: 0.48s here vs claimed 0.47s; lxml no longer drops content). Every new attack angle tried (attribute counts, long tokens, siblings, entities, huge comments/CDATA, mixed) stayed bounded and every truncation was a declared `Reduction`; no silent loss found. |
| **M2** | **CLOSED** | Reproduced the original crash window at three mocked crash points plus a real `SIGKILL` on a child process. In every case the temp file is 0600 from `os.open(..., O_EXCL, mode)` at creation, lives in the 0700 target directory, and the final path is never observed at a permissive mode. One LOW housekeeping note (R-SEC-012), not a disclosure. |
| **M3** | **CLOSED** (as scoped) | Both body paths (`text/plain`, `text/html`) strip the full 11-character bidi-control set (LRE/RLE/PDF/LRO/RLO/LRI/RLI/FSI/PDI/LRM/RLM), declare it as a `hidden_content` Reduction with `BIDI_OVERRIDE`, and leave genuine RTL text (Hebrew) untouched. The identical spoof is **not** closed on Subject headers or attachment filenames (R-SEC-011) — outside M3's literal "body" scope but the same attack the finding exists to stop. |

---

## New findings

**R-SEC-008**
Severity: HIGH · Rubric: SEC-01, SEC-03, SEC-05, SEC-08
Location: `tools/guards/sweeps.py::_string_literals` / `_fold`
Reproduction: `/tmp/.../sec2/bytestring_full/full_bytes_bypass.py` —
`_p1 = b"benchmarks/ground_truth/cases.json".decode(); _p2 = b"https://mail.google.com/".decode(); _p3 = b"gmail/v1/users/{userId}/messages/send".decode(); _p4 = b"chat/completions".decode()`.
`uv run python -m tools.guards <dir>` → **0 violations**.
Expected: exactly the four things R-SEC-001 demonstrated (ground-truth path, destructive
scope, undeclared endpoint, generative path) still forbidden regardless of how the literal
is spelled.
Actual: `_fold`/`_string_literals` only test `isinstance(node.value, str)`; an
`ast.Constant` holding `bytes` is invisible to every content-matching guard (ground-truth,
scope-literal, gmail-endpoint, generative-client's path check). `b"...".decode()` is not
sophisticated — a codec-declaring literal is ordinary Python. None of the five "Does not
catch" paragraphs, nor the module's shared list, mentions byte strings.
Required fix: fold `ast.Constant` with `bytes` value (decoded as UTF-8 with a fallback)
alongside `str`, or explicitly add "byte-string literals" to every guard's documented gap.

**R-SEC-009**
Severity: HIGH · Rubric: SEC-05
Location: `tools/guards/sweeps.py::_writes_to_disk`, `unaudited_disk_write_sweep`
Reproduction (each alone, directory-scanned — a bare single-file argument to the CLI
trivially reports clean since `iter_python_files` uses `root.rglob`, note for future
reviewers): `/tmp/.../sec2/new_bypass/`:
(a) `n2_bare_name_write.py` — `from os import write as w; from shutil import copy` then
`w(fd, body)` / `copy(src, dst)`; (b) `n3_alias_then_call.py` — `_writer = os.write;
_writer(fd, body)`; (c) `n4_functools_partial.py` —
`leak = functools.partial(os.write); leak(fd, body)`; (d) `n5b_aliased_write_only.py` —
`import os as o; o.write(fd, body)`. All four → **0 violations**.
Expected: `os.write`/`shutil.copy` are named explicitly in `_WRITE_QUALIFIED` — the
implementer clearly meant these calls caught.
Actual: `_writes_to_disk` only recognises a write shaped as `<Name|Attr>(...)` where the
call's own `.func` is the qualified attribute (`os.write(...)`) or the bare name `open`.
Once the callable is bound to any other name — `from os import write as w`, a plain
assignment, `functools.partial` — the later call is an ordinary `ast.Name`/`ast.Call` the
guard never inspects. (d), the aliased-module case, **is** documented ("os.rename reached
through an aliased module (`import os as o`)"); (a)–(c) are not — the doc's only adjacent
note is about a *file handle*'s `.write()`, a different shape from re-binding the function
itself.
Required fix: either document (a)–(c) explicitly under "Does not catch", or track simple
local aliasing (a `Name = Attribute` assignment immediately preceding use) the way the
import guards already resolve dynamic-import names.

**R-SEC-010**
Severity: MEDIUM · Rubric: SEC-05
Location: `tools/guards/sweeps.py::_writes_to_disk` (the `func.attr == "open"` branch)
Reproduction: `/tmp/.../sec2/isolated/n6b_io_open_clean_filename.py` —
`import io; io.open("output.log", "w").write(body)` → **0 violations** (the same call with
a path like `"leaked.log"`, which happens to contain `a`, is caught by accident, since the
guard checks the *path* string for `w`/`a`/`x`/`+` characters — not because it evaluated
the real mode).
Expected: the guard's own comment claims "`Path(...).open('w')`, `self._path.open('w')`,
anything.open('w') - the receiver is not knowable, the mode is."
Actual: that claim is false for `io.open`, whose signature is `(file, mode)` — the same
order as the builtin — not `(mode, ...)` like `pathlib.Path.open`. `_opens_for_writing` is
called with `position=0` for every `.attr == "open"` call, so for `io.open` it inspects the
**path** argument for write-mode characters instead of the mode argument. An ordinary,
non-adversarial `io.open(path, "w")` with a ordinary filename silently passes.
Required fix: special-case `io.open` (and any other attribute-form call whose receiver
resolves to the `io` module) to check position 1, the way `os.fdopen` already does; or
narrow guard 6's own claim to admit this is unreliable for `io.open`.

**R-SEC-011**
Severity: MEDIUM · Rubric: INJ-04
Location: `content/headers.py::collect_headers`, `content/mime.py` (`AttachmentRow.filename`)
Reproduction: `/tmp/.../sec2/m3_headers.py`, `m3_filename.py` — the exact R-SEC-005/M3
payload `"Invoice_" + RLO + "exe.cod" + PDF + "_final.pdf"`, placed in a `Subject` header
or an attachment's `filename`, reaches `ProcessedMessage.subject` /
`AttachmentRow.filename` **byte-for-byte, unstripped, unflagged** — `RLO in r.subject` and
`RLO in a.filename` are both `True`.
Expected: M3's own stated rationale (`html_text.py`'s docstring, `reductions.py`'s
`BIDI_OVERRIDE` doc) is the "Trojan Source" filename/display-order spoof; the canonical
form of that attack is exactly a filename or subject line making a `.exe` read as a
`.pdf`, which is what the test fixture's own string literal is shaped like.
Actual: `strip_invisible_characters` is wired into the body pipeline only
(`html_text.py`'s extractors and `pipeline.py`'s per-body call); `collect_headers` and the
attachment-filename path never call it. `body_clean` is safe; `subject` and
`attachments[].filename` — both handed to the same downstream disclosure/agent surface —
are not, and this gap is not named anywhere in `HANDOFF.md` §3's "what I did not fix" list.
Required fix: run `strip_invisible_characters` over the decoded `Subject` (and other
free-text headers) and attachment filenames, declaring a `hidden_content` reduction the
same way, or state the gap explicitly if headers are ruled out of scope.

**R-SEC-012**
Severity: LOW · Rubric: SEC-04
Location: `auth/tokenstore.py::TokenStore.save`
Reproduction: `/tmp/.../sec2/m2_sigkill_parent.py` — a real `SIGKILL` sent to a child mid
`save()` (after `fsync`, before `replace`) leaves `.credentials.json.<pid>.<hex>` on disk
at **mode 0600** holding the refresh token; nothing removes it on a later run.
Expected/Actual: not a disclosure — 0600 is exactly the store's own guarantee, and the
existing test (`test_a_crash_during_the_write_never_leaves_the_token_in_a_readable_file`)
explicitly tolerates this shape (`not (secret in body and mode & 0o077)`). Purely a
housekeeping gap: orphaned temp files accumulate under the token directory indefinitely.
Required fix (optional): sweep `.{name}.*` leftovers older than the current PID's lifetime
at the start of `save()`/`ensure_directory()`.

---

## Execution record

### H3 — AST guards
| Attempt | Result |
|---|---|
| Original 4 R-SEC-001 files, unmodified, re-run against `run_all()` | **10 violations**, all 6 guards firing (0 → 10; HANDOFF's "0 → 11" reproduces exactly against its own `test_guards.py` fixture text, which rewords one file slightly — same substance, minor wording delta, not a finding) |
| `tests/test_guards.py`'s own `BYPASS_FILES` fixture | **11 violations**, all 6 guards — matches HANDOFF verbatim |
| Byte-string literal (`b"...".decode()`) for ground-truth/scope/endpoint/generative markers | **0 violations — new bypass** (R-SEC-008), undocumented |
| `from os import write as w` / `from shutil import copy`, bare-name call | **0 violations — new bypass** (R-SEC-009), undocumented |
| `_writer = os.write; _writer(fd, body)` (assign, then call) | **0 violations — new bypass** (R-SEC-009), undocumented |
| `functools.partial(os.write)(...)` | **0 violations — new bypass** (R-SEC-009), undocumented |
| `import os as o; o.write(...)` (aliased module) | **0 violations** — but explicitly documented in guard 6's own text |
| `io.open(path, "w")`, ordinary filename | **0 violations — new bypass** (R-SEC-010), undocumented, contradicts the guard's own claim |
| `getattr(os, "wr"+"ite")(fd, body)` | **0 violations** — covered by "getattr-driven attribute chains" |
| `eval("__import__('os').write")(fd, body)` | **0 violations** — covered by "eval/exec" |
| `os.fdopen(fd, "w")` | **Caught** — position-1 mode check works |
| `Path` aliased to a local name (`from pathlib import Path as P; P(x).open("w")`) | **Caught** — receiver name is irrelevant to the `.attr=="open"` check |
| Third-party lib's own internal file API (`fakepillib.Image_save(path, data)`) | **0 violations** — explicitly documented ("third-party library's own file API") |
| `import mailweave_harness as mh`, `from mailweave_harness.x import y as z` | **Caught** — import-name guards read `node.module`/`alias.name`, alias-proof by construction |
| CLI invoked with a **file** path instead of a directory | Silently scans **zero files** (`Path.rglob` on a non-directory yields nothing) — noted for future reviewers, not filed (HANDOFF's own regression fix only covers the "out-of-repo directory" crash, not this) |

### H4 — HTML bounds
| Attempt | Result |
|---|---|
| 10k/40k/100k/200k nested `<div>`, selectolax and lxml | 0.04s / 0.10s / 0.26s / **0.48s** (claim: 0.47s) selectolax; lxml matches; both return `'hi'` at every depth (no more silent drop) |
| 200,000 attributes on one tag; 5MB single attribute value; 3MB tag name | All caught entirely by `HTML_SOURCE_CHAR_CAP` (whole body truncated since the cap lands inside the one giant opening tag) — declared as `html_size_cap`, 100% of removal accounted for, sub-40ms |
| 200k flat siblings (no nesting), under/over the char cap | 0.86–1.02s, bounded; size cap and `html_to_text` both declared; no depth-cap interaction needed |
| Many attrs spread across 15,000 sibling tags (~1.2MB, under the char cap) | 0.17–0.19s, no cap needed, no blowup in per-node attribute-dict construction |
| 15,000 `display:none` nodes (~930k chars of hidden text) | 0.17–0.82s; `hidden_removed=450000` exactly matches the 30-char payload × 15,000 |
| 5MB single HTML comment; 3MB CDATA-like block | Both fully absorbed by the size cap, <35ms, declared |
| DOCTYPE-declared internal entities, nested 5 levels (billion-laughs shape) | Not expanded, sub-millisecond (HTML parsers ignore internal DTD entities; matches Round 1) |
| Unterminated attribute value swallowing the rest of the document; unterminated `<?xml`; deeply nested unterminated attrs | Text correctly empty **and** `lost_text_chars` non-zero (12/13/249/644 chars) — declared as `html_parse_lost_text`, not silently dropped |
| Unterminated `<!--` comment swallowing real trailing text to EOF | `text=''`, `lost=0` — correct: an unterminated HTML comment legitimately extends to EOF per the HTML5 spec, and the crude witness scanner agrees; not a bug |
| Full pipeline (`process_message`) over the above via a synthetic `text/html` MIME part | Every case produced a coherent `reductions` tuple (`html_size_cap`/`html_depth_cap`/`html_to_text`), `_reconcile`'s magnitude check never tripped |

### M2 — atomic `TokenStore.save()`
| Attempt | Result |
|---|---|
| Pre-existing 0644 file; crash inside `os.fchmod` (original R-SEC-003 spot) | Final path unchanged at 0644 (old content); no leftover; `OSError` propagates |
| Pre-existing 0644 file; crash mid `json.dump` (spied fd mode before failure) | Temp file's mode **already 0600** before any write completed (from `O_EXCL`+mode at `os.open`); no leftover; final path unchanged |
| Pre-existing 0644 file; crash inside the post-write `_check_mode`/before `replace` | Same: no leftover, final path unchanged |
| Pre-existing 0644 file; crash inside `Path.replace` itself | Same: no leftover, final path unchanged at 0644 (never the new secret) |
| Real `SIGKILL` on a child process, timed to land after `fsync`, before `replace` | Leftover `.credentials.json.<pid>.<hex>` at **0600** holding the secret (R-SEC-012, LOW — safe mode, never swept); final path still holds the *old* content, never a permissive file with the secret |

### M3 — bidi overrides
| Attempt | Result |
|---|---|
| Full 11-char control set (LRE/RLE/PDF/LRO/RLO/LRI/RLI/FSI/PDI/LRM/RLM) in a `text/plain` body | All 11 stripped; declared `hidden_content` w/ `BIDI_OVERRIDE` |
| Same payload in a `text/html` body (`<p>...</p>`) | Stripped after `html_to_text`; both `html_to_text` and `hidden_content` reductions present |
| R-SEC-005's exact filename-spoof string as body text, both MIME types | `RLO`/`PDF` absent from `body_clean` in both |
| Hebrew RTL prose (`שלום עולם`, real letters, no controls) | Preserved byte-for-byte — the strip does not touch genuine RTL text |
| Same spoof string as the `Subject` header | **Reaches `ProcessedMessage.subject` unstripped** (R-SEC-011) |
| Same spoof string as an attachment `filename` | **Reaches `AttachmentRow.filename` unstripped** (R-SEC-011) |
| Homoglyph substitution (e.g. Cyrillic `а` for Latin `a`) | Not attempted as a fix target — M3's rubric text is bidi-specific; no guard anywhere claims homoglyph coverage, so no over-claim to check |

---

## Per-criterion recommendations

| Criterion | Recommendation | Basis |
|---|---|---|
| SEC-01, SEC-03, SEC-08 | **NOT YET PASS** | R-SEC-001's exact shape is closed and well-documented. R-SEC-008 (byte strings) defeats the same guards just as trivially and is undocumented — the CI-gate evidence these criteria lean on is still overstated. |
| SEC-05 | **NOT YET PASS** | R-SEC-008/009/010 all bypass `unaudited_disk_write_sweep` (three of them undocumented); the "server writes nothing but the token store" CI claim does not hold against ordinary refactors, let alone adversarial code. |
| SEC-04 | Ready to re-verify as **PASS** on the atomicity claim specifically | M2 closed under mocked and real-SIGKILL crashes at every stage; R-SEC-012 is a LOW housekeeping item, not a blocker. |
| INJ-04 | **NOT YET PASS** | H4 (depth/size/lost-text) is solid and can move toward PASS on its own. M3's body-path fix is solid but R-SEC-011 leaves the identical spoof open on Subject/filename, which are disclosed to the same downstream consumer as `body_clean`. |
| SEC-07 | Unchanged from Round 1 (R-SEC-004, MEDIUM, out of this round's work order) — still open, untouched. |
