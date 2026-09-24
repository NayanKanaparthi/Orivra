"""M2's acceptance, declared as checks that either run here or name what they need.

**Why this is code and not a section of the handoff.** M2's brief states four things that
must be true before the milestone is accepted. Three of the four are part runnable now and
part blocked on something outside this repository, and prose cannot keep those two halves
apart for long: a paragraph that says "the injection fixtures pass" reads as acceptance
whether the fixtures ran a minute ago or were last run three commits back, and a paragraph
that says "H1-H3 need the corpus" does not tell the owner which command to type when the
corpus arrives. So each check states what it runs, what a green result establishes, and -
when it is blocked - the exact prerequisite, in the owner's terms.

**What a green run of this does NOT mean.** It does not mean M2 is accepted. The rubric's own
rule is that only a reviewer who did not write the code may move a criterion to PASS, by
reproducing the evidence themselves (`tools/rubric_status.py` holds the structural half of
that). This module reports *evidence status* and nothing else: which of M2's acceptance
claims currently have executable support in this tree, and what each of the rest is waiting
for. A check that passes here is a citation a reviewer can re-run, not a verdict.

**Held-out boundaries are preserved by construction.** No check here reads a case file, an
expected answer or an evaluator record. The runnable checks are *properties* - a rung's
prohibitions, a trace's redaction, an allowlist's refusals - which is exactly why they can
run without a corpus, and also why they cannot stand in for H1-H3, which are measurements
over cases nobody in this process may see.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class Check:
    """One executable claim, or one named prerequisite. Never both."""

    id: str
    #: What a green result establishes - stated narrowly, because the gap between what a
    #: test proves and what a milestone claims is where this project keeps finding defects.
    establishes: str
    #: `pytest` node ids, run in this repository. Every one is resolved by `--check` before
    #: any of them runs, because a citation that does not resolve is a claim (AGENT_LOOP §6).
    runs: tuple[str, ...] = ()
    #: Non-empty when this check cannot run here. Each entry is a prerequisite in the
    #: owner's terms - a corpus, a credential, a runtime - not a task for the implementer.
    needs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if bool(self.runs) == bool(self.needs):
            raise ValueError(
                f"{self.id}: a check either runs here or names what it needs. Both means the "
                "blocked half is hiding behind the runnable one, which is the reporting "
                "failure this module exists to prevent; neither means it says nothing"
            )


@dataclass(frozen=True)
class Item:
    """One line of M2's acceptance, with the checks that bear on it."""

    id: str
    title: str
    #: The brief's own words, so this file cannot quietly restate the criterion more weakly.
    criterion: str
    checks: tuple[Check, ...]


A1 = Item(
    id="A1",
    title="Semantic retrieval compared with the v0.1 lexical baseline",
    criterion="H1, H2, H3 measured on F1-F17 against the v0.1 lexical arm",
    checks=(
        Check(
            id="A1-plumbing",
            establishes=(
                "the semantic rung escalates where every lexical rung returned nothing, "
                "selects by a pre-registered top-k rather than a threshold, creates no "
                "sources of its own, and declares the pool and the shortlist it used. This "
                "is the machinery working; it is NOT evidence about retrieval quality"
            ),
            runs=("tests/test_semantic_rung.py",),
        ),
        Check(
            id="A1-lifecycle",
            establishes=(
                "the server process loads its models once across queries and the cold load "
                "is accounted separately from per-query work, so a latency comparison "
                "between the two arms is not measuring a model load"
            ),
            runs=(
                "tests/test_semantic_rung.py::test_the_server_process_reuses_one_backend_"
                "across_queries",
                "tests/test_semantic_rung.py::test_warming_the_backend_at_startup_is_what_"
                "keeps_a_query_off_the_cold_path",
            ),
        ),
        Check(
            id="A1-harness",
            establishes=(
                "the harness runs end to end: EP §4.1's case file loads and refuses every case "
                "it could not score, the refs join through a generated manifest to the ids a "
                "mailbox assigned, all four MailWeave arms and both primitive-floor budgets "
                "run through the shipped service, first-response and expansion-reached "
                "evidence are measured separately, the pool is read from the trace or from the "
                "network layer per EP §6.4, and the three hypothesis clauses compute their own "
                "falsification conditions from plan §8.2 under the registered-n floor. It "
                "establishes nothing about retrieval: the dummy queries are sentinel tokens"
            ),
            runs=(
                "tests/test_evaluation_harness.py",
                "tests/test_evaluation_report.py",
                "tests/test_evaluation_pool.py",
                "tests/test_primitive_floor.py",
            ),
        ),
        Check(
            id="A1-command-path",
            establishes=(
                "the campaign command executes offline with every instrument attached - four "
                "arms, both floor budgets, a trace sink per arm, the three comparisons and the "
                "three verdicts - through the same `_present` the live run uses, so what the "
                "dry run proves is the path that will run. The live run differs in exactly two "
                "places: `runtime.start` with a real credential, and the case files read from "
                "disk"
            ),
            runs=("tests/test_evaluation_cli.py",),
        ),
        Check(
            id="A1-live-path",
            establishes=(
                "the campaign command's own shape: --live-check runs it against the real "
                "seeded mailbox using a sentinel-token case file the corpus writes about "
                "itself, needing no --cases, so `runtime.start` with a real credential, the "
                "trace sinks, the floor client and the report are exercised live before the "
                "independently authored cases arrive. Every query has one lexical match by "
                "construction, so it establishes nothing whatever about retrieval"
            ),
            runs=("tests/test_evaluation_cli.py",),
        ),
        Check(
            id="A1-authoring-kit",
            establishes=(
                "the independent case-authoring kit exports and runs: the brief, the field "
                "list, the registered families generated from the same table the scoring run "
                "reads, the hypotheses, and a standalone checker that imports with no "
                "`mailweave_harness` on the path and applies the scoring run's own refusals - "
                "because its schema modules ARE this repository's files, copied at export "
                "time and asserted byte for byte. It carries no queries, no answers and no "
                "engine code"
            ),
            runs=("tests/test_authoring_kit.py",),
        ),
        Check(
            id="A1-seeding-path",
            establishes=(
                "the seeding driver refuses before it writes: the harness client may not be "
                "the server's, the harness token store may not be the server's, the scope set "
                "is exactly https://mail.google.com/, and the authenticated address is "
                "compared with the declared seed account through a real getProfile before the "
                "first insert and again before the first delete. Every request in these tests "
                "goes to a double; the ones that matter make no request at all"
            ),
            runs=("tests/test_seed_driver.py", "tests/test_seed_gmail_transport.py"),
        ),
        Check(
            id="A1-H1-H3",
            establishes="",
            needs=(
                "the case file: the queries and the expected answers. Everything around them "
                "is built - the generator, the answer key, the schema, the joins, the arms, "
                "the scoring - and what is separate is the questions, because an implementer "
                "writing them writes the exam it is sitting. The handoff is a command rather "
                "than a document: `mailweave_harness.evaluation --export-kit DIR` writes the "
                "brief, the field list, the registered families, the hypotheses and a "
                "standalone checker. EVALUATION_PLAN §4 specifies every family, size, "
                "construction and scoring rule, so nothing has to be invented; see "
                "M2_EVALUATION_HANDOFF.md §7",
                "the owner's approval for the first live write. The concrete "
                "`GmailSeedTransport`, its driver, its four refusals, the settle gate and the "
                "cleanup are built and tested against a double, and have never touched a "
                "mailbox. `mailweave_harness.seed --plan-seeding` prints the account, the "
                "client, the token store, the scope, the message count, the settle gate and "
                "the cleanup behaviour and sends nothing; the approval is "
                "`--approve-writes-to <the seed account>`, typed and compared. This is not an "
                "implementation gap (M2_EVALUATION_HANDOFF.md §6)",
                "a real mailbox, for the arms to run against (GMAIL-01's live smoke suite is "
                "the same prerequisite)",
            ),
        ),
    ),
)

A2 = Item(
    id="A2",
    title="Reranking and query-aware disclosure on their registered cases",
    criterion=(
        "reranking and query-aware selection/disclosure evaluated on the cases registered "
        "for them (F11, F12, F17 and the position sweep)"
    ),
    checks=(
        Check(
            id="A2-rank-prohibitions",
            establishes=(
                "D.7's three hard prohibitions hold and are evaluated before any ambiguity "
                "signal: no rerank on an exact-signal match, none at hit_count == 1, none on "
                "an rfc822msgid route. And ordering_effect is false unless the score exists "
                "for every candidate in the comparison that was ordered"
            ),
            runs=("tests/test_ranking_l6.py",),
        ),
        Check(
            id="A2-disclosure-fill",
            establishes=(
                "the query-aware fill's components are the published ones with the published "
                "weights, no query-independent component can outrank a query-derived one, and "
                "the E2 reply-chain floor is not budget-negotiable"
            ),
            runs=(
                "tests/test_disclosure_round23.py",
                "tests/test_round25.py",
                "tests/test_round28.py",
            ),
        ),
        Check(
            id="A2-registered-cases",
            establishes="",
            needs=(
                "F11 (semantic with a lexical trap), F12 (semantic negative control) and F17 "
                "(decision reversal) as cases with answers. Both arms exist - `full` and the "
                "`fixed-window` Baseline F(+/-2) arm run on every case - so what is missing "
                "here is the cases and nothing else",
                "the position sweep grid (EP §4.4), which is a property of the corpus rather "
                "than of a fixture this repository can write",
            ),
        ),
    ),
)

A3 = Item(
    id="A3",
    title="Exact-lookup non-regression and trace checks",
    criterion=(
        "the adaptive-cost invariant on exact lookups, and generative_llm_calls stays zero "
        "on F1/F2 traces"
    ),
    checks=(
        Check(
            id="A3-exact-stop",
            establishes=(
                "the exact-signal definition is closed at three branches, each branch fires "
                "only inside its published hit band, and no branch fires on a candidate that "
                "was never executed - so the cheap path is entered for a stated reason"
            ),
            runs=("tests/test_exact_signal_match.py",),
        ),
        Check(
            id="A3-no-generative-call",
            establishes=(
                "GENERATIVE_LLM_CALLS is a hard constant, no generative client can appear in "
                "server code (a CI guard, with planted violations), and the MCP surface holds "
                "no reference to the client's model - so `generative_llm_calls = 0` is a "
                "property of the build rather than a number a trace reports about itself"
            ),
            runs=(
                "tests/test_guards.py::test_the_shipped_server_tree_passes_every_guard",
                "tests/test_guards.py::test_a_generative_client_in_server_code_is_caught",
                "tests/test_guards.py::test_the_embedding_stack_is_not_a_generative_client",
            ),
        ),
        Check(
            id="A3-trace",
            establishes=(
                "D.10's trace schema v2: no trace field can hold mail-derived text (checked "
                "over the model tree, not over one record), every formatting path renders the "
                "redaction placeholder, pool_ids live in the trace and never on the wire, and "
                "a served call writes a trace holding no sentinel"
            ),
            runs=("tests/test_trace_d10.py",),
        ),
        Check(
            id="A3-compatibility",
            establishes=(
                "MailWeave v0.1's observable behaviour is unchanged: both compatibility "
                "levels stay green, every Orivra recovery call parses under MailWeave's own "
                "parser and runs on the legacy surface"
            ),
            runs=(
                "tests/test_orivra_equivalence.py",
                "tests/test_orivra_contracts.py",
                "tests/test_orivra_surface.py",
            ),
        ),
        Check(
            id="A3-cost-non-regression",
            establishes="",
            needs=(
                "F1/F2 latency and API-call counts with the semantic path installed and not "
                "triggered, against the same figures without it. That is a measurement over "
                "the case corpus on a real mailbox; the invariant it checks is asserted "
                "structurally by A3-exact-stop, which is a different claim",
            ),
        ),
    ),
)

A4 = Item(
    id="A4",
    title="Injection fixtures and offline verification",
    criterion="the injection fixtures pass; runtime egress is exactly the two Gmail hosts",
    checks=(
        Check(
            id="A4-injection",
            establishes=(
                "INJ-02: no connector-voiced field carries a string a message chose, "
                "classified off the schema's own annotations across all four tools and a "
                "semantic response. INJ-03: an injection message is disclosed fenced and "
                "never dropped, changes no call the response offers, and a bait message "
                "removes no true evidence - with the narrow-shortlist case stated separately "
                "as a declared withholding rather than as immunity. INJ-05: identity fields "
                "split, authentication results labelled and never reduced to a verdict. "
                "INJ-06: every argument of every minted call comes from a closed set"
            ),
            runs=("tests/test_injection_ws14.py",),
        ),
        Check(
            id="A4-fence",
            establishes=(
                "INJ-01: mail-derived text is fenced with this response's nonce and cannot "
                "close its own fence. INJ-04: the content pipeline runs with networking "
                "denied and declares what it hid"
            ),
            runs=(
                "tests/test_envelope_contract.py::test_content_must_be_fenced_with_this_"
                "responses_nonce",
                "tests/test_envelope_contract.py::test_mail_text_cannot_close_its_own_fence",
                "tests/test_content_pipeline.py::test_the_pipeline_runs_with_networking_denied",
            ),
        ),
        Check(
            id="A4-egress",
            establishes=(
                "the runtime allowlist is exactly gmail.googleapis.com and "
                "oauth2.googleapis.com, a blocked host never reaches the transport (no DNS, "
                "no socket), plain HTTP is refused even to an allowlisted host, and the "
                "offline flags are set before any hub-aware library is imported"
            ),
            runs=("tests/test_egress.py", "tests/test_offline_enforcement.py"),
        ),
        Check(
            id="A4-no-listening-socket",
            establishes=(
                "SEC-07's third clause as a CI guard: no module opens or serves an inbound "
                "connection, and no module but the setup-time loopback consent receiver may "
                "even name one. This is the cheap half made continuous - the port scan below "
                "stays the evidence for the property itself"
            ),
            runs=(
                "tests/test_guards.py::test_a_listening_socket_in_server_code_is_caught",
                "tests/test_guards.py::test_the_loopback_consent_receiver_is_allowlisted",
                "tests/test_guards.py::"
                "test_the_receivers_names_are_refused_outside_that_one_module",
                "tests/test_guards.py::test_an_outbound_socket_is_not_a_listening_socket",
            ),
        ),
        Check(
            id="A4-cold-start",
            establishes="",
            needs=(
                "PF-5(b): the full suite run cold on your machine with all egress except the "
                "two Gmail hosts blocked AT THE NETWORK, the model host explicitly blocked. "
                "A4-egress asserts the allowlist in-process; this is the capture that shows "
                "the process made no other connection, and only a real network can show it",
                "PF-5(c): D.4a's content pipeline run with sockets disabled at the OS level. "
                "A4-fence runs it with networking denied in-process, which is the same claim "
                "one layer up and not the same evidence",
                "the real-mail O8 sample (EP §2.4.5): zero byte-provenance violations on the "
                "round's live sample, beside the fixture set. Needs your mailbox",
                "SEC-07's port scan of the default configuration. A4-no-listening-socket "
                "refuses the code that would open one; the scan is what shows none is open, "
                "and a scanner is the only thing that can",
            ),
        ),
    ),
)

ITEMS: Final[tuple[Item, ...]] = (A1, A2, A3, A4)
