# MailWeave beta launch packet

**Preparation only — not published, not Google-approved, and not a release-gate waiver.**
This is the single handoff for the owner's request to prepare the existing beta for launch.
The exact installer is frozen; no new product features, dependency upgrades, model changes,
benchmark campaign, or changes to Google settings are part of this preparation.

## Candidate

| Field | Value |
|---|---|
| Repository | [NayanKanaparthi/Orivra](https://github.com/NayanKanaparthi/Orivra), currently private |
| Intended tag | `v0.2.0-beta.1`; existing release is a draft prerelease |
| Installer | `Orivra-Beta-0.2.0-beta.1.mcpb` |
| Size | 346,489,677 bytes |
| SHA-256 | `82554d1e4c7103062fbeffbb281749e1558d0253f01549ea2ee9f975764ba6c7` |
| Build revision | `98758576d1dbfbe8cccf3ea18f26438ef3423b77` |
| Checked release-source revision | `afba7d9fcb7240155905c7a6ab7fdfdd5d018fcc` |
| Supported installer platform | Apple Silicon, macOS 14+, Claude Desktop custom extensions |
| Licence | MIT for original software; upstream components retain their own terms |

The later checked source revision adds documentation only. This preparation also changes
documentation/support material only; it does not rebuild or replace the installer.

## Launch materials

- [Prepared GitHub release copy](0.2.0-beta.1-public-notes.md).
- [Installation and removal guide](../INSTALL_DESKTOP_BETA.md).
- [User-facing limitations and support](../KNOWN_LIMITATIONS.md).
- [Checksum file](SHA256SUMS) for the MIT installer, not the older invite-only build.
- A redaction-first GitHub bug-report form, with suspected security incidents directed to
  the owner's private email rather than a public issue.

## Verification record

Checked on the owner's Mac on **2026-09-24 UTC / 2026-09-23 America/New_York**, against the
source revision and installer above. A separate temporary environment used `uv sync --frozen
--all-packages --extra dev --offline`, with CPython 3.12.13 and the locked dependencies. The
development environment was not modified. The actual bundle checks used its own CPython 3.12.14.

| Check | Observed result |
|---|---|
| Installer identity | Local SHA-256/size match the existing private GitHub asset and checksum companion. No rebuild or replacement. |
| Product source identity | All 169 packaged product Python sources and the manifest tool list match the checked release source. |
| Package inspection | 38,223 archive entries; no inspector problems; arm64/macOS 14 minimum retained. |
| Dependency compatibility | All 68 installed packages pass `uv pip check` on the extracted bundle. |
| Native imports | The bundled interpreter loads Torch, lxml, selectolax, pydantic-core, MailWeave, and Orivra. No models were loaded or downloaded. |
| Actual installer startup | The extracted launcher's MCP session negotiates `2026-07-28`, lists all nine expected tools, and refuses a pre-setup mail query with setup guidance. All four MailWeave tools retain read-only annotations. |
| Isolation of startup check | A separate empty app-data directory was used. No setup/OAuth flow, live Gmail call, or token creation occurred; the installed extension was untouched. |
| Credential exclusion | 698 tracked files, 793 reachable Git objects, and every bundle entry checked. No known current user token or harness-client values found. Server-client values occur only in the intended bundle configuration, not the release source/history. |
| Pattern matches | Source/history hits were synthetic test credentials and documented canaries. Dependency hits were serializer marker text and a compiled symbol; the corresponding upstream files match their wheel RECORD hashes. The intended Desktop client remains embedded. This is a targeted scan, not a blanket proof that no private information can exist. |
| Offline suite | **4,603 passed, 5 skipped, 1 failed, 1 deselected**, in 1,163.81 seconds. The sole failure was a sandbox-denied localhost bind, detailed below; it was not suppressed. |
| Regression harness | All 267 existing replant cases completed and were caught, including their prerequisite checks on the pristine copy. No new mutation campaign was introduced. |
| Permitted localhost checks | The exact failed bind test passed when permission to bind 127.0.0.1 was granted. The separately selected real-socket deadline test also passed. Neither uses real Gmail. |
| Product static checks | Lint and formatting pass for `server/src` and `orivra/src` (169 files). The whole-workspace type check reports no findings in those two directories. All nine source guards pass over both packages. |
| Public pages | Product, setup, privacy, and terms pages return HTTP 200. Privacy/terms have effective dates and the requested `kanaparthinayan@gmail.com` contact. Current availability text still correctly says no public download is linked. |

The exact offline invocation was `pytest -m 'not network'`; the test
`tests/test_auth_consent.py::test_the_loopback_listener_binds_only_to_127_0_0_1` still binds a
localhost listener despite lacking that marker. It failed with `PermissionError` at `bind`,
before its assertion. Both the original exit-1 result and its successful permitted rerun are
preserved. This record does **not** relabel the original invocation as an exit-0 full-suite run.

Four skips are impossible one-character-ID sizing combinations; the fifth is the check against
the deliberately unimported `v0.1` Git tag. The cached legacy-schema checks still run. The one
deselected network test is the real-clock silent-upstream test, subsequently run and passed
using only 127.0.0.1. No test was edited, skipped by a new exception, or marked PASS in the
release rubric to make these results look green.

### Existing CI findings, separated from the shipped packages

- **200 lint findings:** 140 in `harness/`, 57 in `tests/`, 3 in `tools/`; none in the shipped
  product source directories. These are not all cosmetic: 51 loop-variable warnings are in
  the synthetic corpus generator, so they must not be dismissed as harmless formatting.
- **44 files** would be reformatted, outside the two product source trees.
- **236 type errors in 45 files**, outside the two product source trees.
- Release-ledger integrity passes, but the advisory release gate still reports **106 criteria
  without PASS**. That number is not a count of product defects. No criterion is waived or
  promoted by this preparation.

The CI workflow is unchanged. Running the tests independently here prevents lint from hiding
their result; it does not turn the GitHub workflow green. The scoped checks identified no new
product failure, shipped-startup defect, or known-current-token leak. They do not establish
general mailbox reliability or a completed security review.

Content-free audit reports, original test logs/XML, and rerun results are retained locally in
gitignored `_to_delete/launch-prep-2026-09-24-F0Xn8y/`, with a checksum manifest. They are not
public release assets. No raw mail was retrieved for these checks.

The startup test above is not a fresh installation and consent flow inside Claude Desktop.
The earlier owner-reported installation remains separate evidence; the executable product
contents of the MIT candidate are unchanged from that earlier candidate.

## What this preparation does not decide

Google data-access verification remains incomplete on the supplied evidence. A working consent
flow, an unverified-app continuation choice, or the 100-user cap does not establish an exception
for public distribution. See
[Google's requirements](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification).
No review-submission date, completion date, or security-assessment exemption is asserted.

Historical release criteria retain their recorded states. Passing the checks above does not
rewrite reviewer transitions or substitute for the open PF-5(b) runtime network-boundary
verification. Deferring an internal criterion requires an explicit owner decision naming the
criterion and the unsupported claim; preparation itself is not that decision.

## Publication handoff — not executed

1. Resolve/record the outstanding Google requirement and any explicitly approved internal
   exceptions without claiming that deferred checks passed.
2. Use the existing clean release repository, not the original development history. Keep
   credentials, tokens, private logs, raw transcripts, and unrelated marketing drafts excluded.
3. Confirm the two uploaded assets match the identities above, then make the repository public
   and publish the draft as a **prerelease**, not a stable/general-availability release.
   In that publication change, replace the private-draft availability text in README, the
   installation guide, and the versioned release notes; remove the draft-only banner from the
   GitHub release body. Preserve historical evidence records and the remaining limitations.
4. Check the release page and asset download without authentication; verify the downloaded hash.
5. Only after that check, link the download on the portfolio's Orivra/setup page and share the
   announcement below. Do not point at a private draft or use `/releases/latest` for this prerelease.

The intended public release URL is
`https://github.com/NayanKanaparthi/Orivra/releases/tag/v0.2.0-beta.1`.
It is a planned URL until publication, not a currently available public download.

For the portfolio after publication, the download button should read **Download MailWeave
beta** and link to that release page, where the platform requirements and warnings are visible.
Replace the current unavailable-download notice and matching FAQ with:

> The experimental MailWeave beta is available for Claude Desktop on Apple Silicon Macs
> running macOS 14 or later. Read the release notes and known limitations before connecting
> Gmail. Google's data-access verification is incomplete; authorization may show a warning
> or be blocked. Selected email evidence is sent to Claude/Anthropic.

The website's privacy and terms links stay in place. This copy is prepared here, not deployed
to the separate Portfolio project.

## Announcement draft — use only after publication

> I'm opening an experimental beta of MailWeave, Orivra's first connector for Claude Desktop.
> Orivra is about helping AI agents navigate large information spaces and bring back evidence
> you can check. MailWeave starts with Gmail: find relevant messages, follow the conversation,
> and inspect what supports an answer.
>
> This build is for Apple Silicon Macs on macOS 14+. It requests read-only Gmail access;
> selected email evidence is sent to Claude. Google's data-access verification is incomplete,
> so authorization may show a warning or be blocked. This is an early preview with known
> limitations, not a promise of complete or always-correct answers.
>
> Download, setup, and limitations: [link to the published prerelease].

No announcement, website edit, repository visibility change, tag, or public release is made by
preparing this packet.
