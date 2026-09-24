"""PF-5's remaining two clauses, as checks rather than as a plan.

**What PF-5 actually is.** `ARCHITECTURE_DECISION.md` §F and `IMPLEMENTATION_PLAN.md` name three
parts: **(a)** a token-free download of each candidate model, with licence and SHA-256 recorded;
**(b)** the full suite run cold-started with every egress blocked except
`gmail.googleapis.com` and `oauth2.googleapis.com`, the model host explicitly among the blocked,
to catch the `huggingface_hub` revalidation call that setup-time provisioning alone does not
prevent (ADV-210); **(c)** D.4a's content pipeline run with sockets disabled, which is INJ-04's
zero-network condition. Its failure conditions are a gated default model, any runtime egress to
the model host, and a parser that fetches a remote entity.

It is a network-boundary check. It was briefly mis-recorded in the release report as a
"cold-start capture, live and timed", which is a performance measurement PF-5 does not ask for
and which would have deferred a safety check as though it were a benchmark.

**What was already covered, and why these two tests are what is left.** The suite denies
`connect`, `connect_ex`, `create_connection` and `getaddrinfo` for every unmarked test, which is
stricter than blocking one host; `test_offline_enforcement.py` holds the allowlists disjoint,
the flags set before any hub-aware library is imported, the loader declining rather than
reaching out, and the planted-subprocess case; `test_model_provisioning.py` holds the digests,
the pinned revision, the licence, and loading by path rather than by repo id; `models.lock`
records licence and per-file SHA-256 for both stages. Two things were not checked anywhere:

* **(a)'s "token-free"** - every provisioning test asserts *what arrived*, none that the request
  went out anonymously. A download that quietly works because a developer's token is in the
  environment is a download that fails on a clean machine, which is the thing (a) is for.
* **(c)'s "fetches a remote entity"** - the pipeline is exercised under the socket ban against
  inputs hostile in other ways (hidden characters, nested multipart, mixed charsets). None of
  them carries an external DTD entity, a remote stylesheet, a remote image or a CSS `url()`, so
  nothing has ever tempted the parser to reach out.

**(b) is not here**, and cannot be: it needs provisioned weights and an enforced egress block
around a real load. `RELEASE_OWNER_ACTIONS.md` §7a splits the smoke half into two runs -
weights present, and weights absent - using `mailweave setup-models --smoke --models-dir` with
isolated empty caches. Both were run by 2026-09-19 and both came back clean.

**Neither closes (b), and this file is not evidence that they do.** They constrained
proxy-honouring clients with environment variables, which is not an enforced egress block, and
neither put the loader on the `huggingface_hub` revalidation path ADV-210 names - empty
auxiliary caches remove a fallback rather than forcing a revalidation, so an absent retry
ladder does not distinguish "blocked" from "never attempted". §7a lists the six things (b)
still needs.
"""

from __future__ import annotations

import inspect
import socket
from pathlib import Path

import pytest

from mailweave.content import HtmlParserName, process_message
from tests.conftest import NetworkAccessDenied
from tests.fixtures import mime_kit

# --- (c) a parser that fetches a remote entity ------------------------------------------------

#: Four ways an HTML or MIME parser can be induced to open a socket, in one document. The
#: external DTD entity is the classic one (XXE); the stylesheet, the image and the CSS `url()`
#: are what a renderer would fetch and what a text extractor must not.
BAITED_HTML = """<!DOCTYPE html [
  <!ENTITY pull SYSTEM "http://entity.invalid/secret.txt">
]>
<html>
  <head>
    <link rel="stylesheet" href="http://stylesheet.invalid/theme.css">
    <style>body { background-image: url("http://css.invalid/bg.png"); }</style>
  </head>
  <body>
    <p>The invoice total is 1,240.50 EUR.</p>
    <img src="http://image.invalid/tracker.gif" alt="pixel">
    <p>&pull;</p>
  </body>
</html>
"""


def _baited_message() -> object:
    return mime_kit.message(
        mime_kit.part(
            "text/html",
            part_id="",
            charset="utf-8",
            data=BAITED_HTML.encode("utf-8"),
            headers=[("Subject", "Invoice")],
        )
    )


def test_the_block_is_live_in_this_process_first() -> None:
    """Otherwise every assertion below passes vacuously on a machine with no network."""
    with pytest.raises(NetworkAccessDenied):
        socket.create_connection(("example.invalid", 80))


@pytest.mark.parametrize("parser", list(HtmlParserName))
def test_no_parser_fetches_an_external_entity_stylesheet_or_image(
    parser: HtmlParserName,
) -> None:
    """INJ-04's zero-network condition, against a document that asks to be fetched from.

    The socket ban is what makes this readable: a parser that tried would raise
    `NetworkAccessDenied` out of the call rather than merely failing to resolve a host, so a
    pass here means *no attempt was made*, not that an attempt failed.
    """
    processed = process_message(_baited_message(), html_parser=parser)
    assert "1,240.50 EUR" in processed.default_view, (
        "the visible text was lost while handling the bait"
    )


@pytest.mark.parametrize("parser", list(HtmlParserName))
def test_the_remote_targets_do_not_reach_the_extracted_text(parser: HtmlParserName) -> None:
    """Not fetching is half of it; the other half is not carrying the URL into the body.

    A `src` or `href` that survives into extracted text becomes a link some later consumer
    follows, which puts the fetch one layer downstream instead of preventing it.
    """
    view = process_message(_baited_message(), html_parser=parser).default_view
    for host in ("entity.invalid", "stylesheet.invalid", "css.invalid", "image.invalid"):
        assert host not in view, f"{host} reached the extracted text through {parser}"


def test_the_entity_body_is_not_substituted_into_the_text() -> None:
    """An expanded external entity is the payload of the attack, not a rendering detail."""
    for parser in HtmlParserName:
        view = process_message(_baited_message(), html_parser=parser).default_view
        assert "secret.txt" not in view


# --- (a) the download is token-free ----------------------------------------------------------

#: Environment names a hub library reads for credentials. A provisioning path that consults any
#: of them can succeed on a developer's machine and fail on a clean one, which is exactly the
#: failure (a) exists to catch.
TOKEN_ENV_NAMES = (
    "HF_TOKEN",
    "HUGGING_FACE_HUB_TOKEN",
    "HUGGINGFACEHUB_API_TOKEN",
    "HF_API_TOKEN",
)


def _provisioning_source() -> str:
    """Every module of the model-provisioning package, read as text.

    The whole package rather than one module: the download, the verification and the path
    resolution are separate files and a credential read in any of them has the same effect.
    """
    from mailweave.models import provision

    root = Path(inspect.getfile(provision)).parent
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(root.rglob("*.py")))


def test_the_provisioning_path_reads_no_credential_from_the_environment() -> None:
    source = _provisioning_source()
    found = [name for name in TOKEN_ENV_NAMES if name in source]
    assert not found, (
        f"the model provisioning path names {found}, so a download can succeed with a "
        "developer's token present and fail on a clean machine. PF-5(a) asks for an "
        "anonymous download"
    )


def test_the_provisioning_path_sends_no_authorization_header() -> None:
    source = _provisioning_source()
    for marker in ("Authorization", "Bearer ", "use_auth_token", "token="):
        assert marker not in source, (
            f"the model provisioning path mentions {marker!r}; an authenticated download is "
            "not the token-free one PF-5(a) records"
        )


def test_every_locked_model_records_the_licence_and_a_digest_per_file() -> None:
    """The other half of (a): what was recorded, rather than how it was fetched."""
    import json

    lock = json.loads((Path(__file__).resolve().parents[1] / "models.lock").read_text())
    models = lock.get("models") or {}
    assert models, "models.lock names no model"
    for name, entry in models.items():
        # `license`, US spelling, is what the lock writes; the prose around it says
        # "licence". Read the key the file actually has rather than the one the docs use.
        assert entry.get("license"), f"{name} records no licence"
        files = entry.get("files") or []
        assert files, f"{name} records no files"
        for one in files:
            assert one.get("sha256"), f"{name}/{one.get('name')} has no digest"
            assert one.get("bytes"), f"{name}/{one.get('name')} has no size"
