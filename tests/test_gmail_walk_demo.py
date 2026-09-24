"""The release demonstration, rehearsed offline against the synthetic mailbox.

`tools/dev/gmail_walk.py` is what the Gmail demonstration actually runs: ask, inspect the
relations, follow one of the graph's own handles, inspect again. It talks to a mailbox, so it
cannot be run in CI - but every line of it except `start()` and `announce()` is driven here,
against the same fixture the surface tests use, through the same `call()` boundary a client
goes through.

The point is not coverage. It is that the steps written in the release notes are steps that
work: a demonstration whose script has drifted from the tools is a demonstration that fails in
front of the person it was written for.
"""

from __future__ import annotations

import pytest

from orivra.cache import BoundedCache
from orivra.contracts import ConnectorId
from orivra.gmail_adapter import GmailAdapter
from orivra.registry import ConnectorRegistry
from orivra.surface.service import OrivraService
from tests.test_mcp_surface_round24 import mailbox, make_service
from tools.dev.gmail_walk import walk

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
QUESTION = "Larch pricing draft"


def _service(max_nodes: int) -> OrivraService:
    """One Orivra process over the synthetic mailbox, with the cache the runtime would build.

    `ConnectorRegistry.from_runtime` is what supplies the process-lifetime cache in the
    shipped server; this is the same wiring without a runtime to start, so the rounds below
    exercise the seat the live demonstration exercises rather than a different one.
    """
    service = make_service(mailbox())
    adapter = GmailAdapter(
        service=service, granted_scopes=(SCOPE,), cache=BoundedCache(now=service.now)
    )
    return OrivraService(
        registry=ConnectorRegistry(adapters={ConnectorId.GMAIL: adapter}),
        max_graph_nodes=max_nodes,
    )


@pytest.fixture
def walked() -> dict:
    """A budget that prunes the decision branch, so there is a handle to follow."""
    record, status = walk(_service(4), QUESTION, view="body_clean")
    assert status == 0, record.get("stopped")
    return record


def test_the_walk_completes_all_four_steps(walked: dict) -> None:
    for step in ("step_1_ask", "step_2_inspect", "step_3_expand", "step_4_inspect_again"):
        assert step in walked, f"{step} is missing; the demonstration did not complete"
    assert walked["step_1_ask"]["graph_built"]
    assert walked["step_2_inspect"]["edges"]["relations"], "step 2 showed counts and no relations"
    assert walked["step_3_expand"]["added"]["nodes"], "the expansion recovered nothing"
    assert walked["step_4_inspect_again"]["gained"], "the graph did not visibly change"


def test_the_inspection_shows_relations_rather_than_counts(walked: dict) -> None:
    """The tools-first guarantee, at the level a reader can check it."""
    for relation in walked["step_2_inspect"]["edges"]["relations"]:
        assert relation["source"] and relation["target"] and relation["relation"]
        assert relation["support"], "a relation arrived without the sources it rests on"
        assert relation["origin"] and relation["assertion"]


def test_the_record_carries_no_message_text(walked: dict) -> None:
    """A demonstration record that quotes mail is a record nobody can paste into a review."""
    rendered = repr(walked)
    for leaked in (
        "pricing draft is attached",
        "we are not withdrawing",
        "Background is at",
    ):
        assert leaked not in rendered, f"the walk printed message text: {leaked!r}"


def test_what_expansion_could_not_read_names_only_rows_this_graph_has_not_read(
    walked: dict,
) -> None:
    """A thread map re-returns the whole thread, including rows the answer already disclosed.

    Reporting those as unread would be this server describing a gap it does not have - the
    graph holds that message at `body_clean` and drew its stated edge from it.
    """
    unread = walked["step_3_expand"]["text_not_read"]
    assert set(unread["nodes"]) == {"gmail/message/d-2", "gmail/message/d-3"}
    assert "gmail/message/18ab3f9c2d1e" not in unread["nodes"], (
        "a message the graph already read at body depth was reported as unread"
    )


def test_a_complete_answer_stops_the_walk_honestly() -> None:
    """No handle to follow is a fact about the mailbox, not a failure of the demonstration."""
    record, status = walk(_service(40), QUESTION, view="body_clean")
    assert status == 1
    assert "nothing to follow" in record["stopped"] or "get back" in record["stopped"]
    assert record["step_1_ask"]["graph_built"], "it stopped for the wrong reason"
    assert record["step_2_inspect"]["edges"]["by_relation"], "it stopped before showing anything"


# -- the rounds that make the cache visible -----------------------------------------------------


def test_the_counting_wrapper_changes_no_call_it_counts() -> None:
    """A counted run must make exactly the calls an uncounted one makes, or the numbers lie."""
    from tools.dev.gmail_walk import _counting

    plain = _service(4)
    counted = _service(4)
    tally = _counting(counted.registry.gmail().service)

    first, first_status = walk(plain, QUESTION, view="body_clean")
    second, second_status = walk(counted, QUESTION, view="body_clean")
    assert first_status == second_status == 0
    assert first["step_2_inspect"]["edges"]["by_relation"] == (
        second["step_2_inspect"]["edges"]["by_relation"]
    )
    assert first["step_4_inspect_again"]["gained"] == second["step_4_inspect_again"]["gained"]
    assert tally["threads.get"] >= 1, "the wrapper counted nothing, so it proves nothing"


def test_a_second_round_in_one_process_reads_the_change_feed_instead_of_the_thread() -> None:
    """What `--rounds 2` shows live, asserted here so the flag cannot start lying.

    The structure cache is process-lifetime, so a single scripted round always reads the
    thread: there is nothing cached yet. The second round is where the seat shows, and a
    demonstration that could not show it would be a demonstration of the wrong thing.
    """
    from tools.dev.gmail_walk import _counting

    service = _service(4)
    tally = _counting(service.registry.gmail().service)

    first, status = walk(service, QUESTION, view="body_clean", calls=tally)
    assert status == 0
    cold = first["step_3_expand"]["gmail_calls"]
    assert cold.get("threads.get") == 1, f"the first expansion did not read the thread: {cold}"
    assert "history.list" not in cold, "a cold read has nothing to revalidate"

    second, status = walk(service, QUESTION, view="body_clean", calls=tally)
    assert status == 0
    warm = second["step_3_expand"]["gmail_calls"]
    assert warm.get("history.list") == 1, f"the second expansion revalidated nothing: {warm}"
    assert "threads.get" not in warm, (
        f"the second expansion read the thread again ({warm}), so it is not served from the "
        "structure cache the registry builds"
    )
    # The answer's own thread read is step 1's and is not what the cache is about. Counting it
    # into the round would credit the cache with a call it never avoided.
    assert second["step_1_ask"]["gmail_calls"].get("threads.get", 0) >= 1
