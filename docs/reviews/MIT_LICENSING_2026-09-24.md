# MIT licensing and desktop candidate — 2026-09-24

The owner explicitly selected MIT. This change applies it to Orivra and MailWeave's original
software and accompanying software documentation, not to third-party dependencies, model
weights, or separately licensed assets. Copyright holder: Nayan Kanaparthi, 2026.

## What changed

- Root `LICENSE`, identical licence files in the three workspace packages, and explicit
  `license = "MIT"` / `license-files = ["LICENSE"]` package metadata.
- `THIRD_PARTY_NOTICES.md` distinguishes the project's licence from upstream terms.
- The desktop manifest now says `Orivra (beta)` and `MIT`. The builder includes the root
  licence and third-party notice; package wheels include their own MIT licence text.
- Source commit: `98758576d1dbfbe8cccf3ea18f26438ef3423b77` in the clean release checkout.
  The original development Git history was not rewritten or pushed.

## Rebuilt candidate

`dist/desktop/mit/Orivra-Beta-0.2.0-beta.1.mcpb`, 346,489,677 bytes.

SHA-256: `82554d1e4c7103062fbeffbb281749e1558d0253f01549ea2ee9f975764ba6c7`.

Built using the existing builder, unchanged `uv.lock`, and the pinned CPython 3.12.14 runtime.
Dependency versions were not upgraded. The existing configured installer is preserved at its
original path with SHA-256 `2edd449db7da45caae3aa7ab66c237b3737f2721c368d68821b06317c87a97cc`.

Compared entry-by-entry with that installer:

- Four additions: root licence/third-party notice, and the two product wheel licence files.
- Five metadata changes: manifest, two wheel `METADATA` files, and their two `RECORD` files.
- Three dependency `.pyc` files serialize differently. Their headers and decoded code objects
  are equal when read with the pinned CPython 3.12.14. No source or native-library change.
- All other entries are byte-identical, including the 169 product Python sources, product
  bytecode, native binaries, launcher, model lock, tool list, and server OAuth configuration.
- No entries removed. The known harness-client and current user-token values were absent;
  only the intended server-client values occur, in `server/config/oauth-client.json`.

## Verification and limits

- 41 licensing/desktop tests passed in both the development and clean release checkouts.
- Ruff lint and formatting passed on the changed Python files; mypy passed on those files.
- All three actual workspace wheels declare MIT and carry the exact root licence text.
- Bundle inspection passed; arm64 compatibility and macOS 14 minimum remain as before.
- The MIT candidate has not been reinstalled in Claude Desktop. No live mailbox call, model
  download, full-suite rerun, OAuth setting change, or new performance claim was made.
- Existing repository-wide CI failures and unpassed release criteria remain unresolved.
- MIT licensing does not establish Google's data-access approval or an assessment exemption.
  The repository and release remain private; the release is a draft, not a public launch.

The earlier upload review and live-run records are preserved as history, not rewritten to
claim they reviewed this newer artifact. Public distribution of the configured application
still requires resolution of the separately documented release and Google requirements.
