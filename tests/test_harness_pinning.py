"""Harness account pinning: the destructive credential cannot reach the real mailbox.

The strongest control here is not code - it is the harness OAuth client's Testing status with
a seed-only test-user allowlist, which makes consenting the personal mailbox to the write
client impossible at Google's side (AD A.4 condition (ii), ADV-205). These tests cover the
half that *is* code, and the module under test says plainly which half that is.

**Round 12.** Round 11's version of this file asserted that a session could not be issued
"beside the check" by calling the private `_issue` with the wrong token - and R-SEC then built
one with the *public constructor*, no token involved, for the owner's real mailbox address.
A test that only drives the guarded door cannot see the open one next to it, so the tests
below attack the constructor, `dataclasses.replace`, subclassing and credential swapping
directly, and each of those was a way in that needed no private name.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import gc
import hashlib
import hmac
import inspect
import pickle
import weakref
from collections.abc import Callable
from functools import partial
from unittest import mock

import pytest

from mailweave.gmail import Profile
from mailweave_harness import pinning
from mailweave_harness.pinning import SeedSession, verify_seed_account
from mailweave_harness.scopes import SEEDER_SCOPES, SeedAccountMismatch

SEED = "mailweave.seed@harness.example"
PERSONAL = "owner@personal.example"


class FakeCredential:
    """A stand-in for the client the harness runs on. `GmailClient` satisfies the same shape.

    It is a whole object rather than a callable because the binding is to *the credential*,
    and a bound method is a fresh object on every attribute access - `client.get_profile is
    client.get_profile` is `False` - so binding to one would fail on identity for reasons
    that have nothing to do with pinning.
    """

    def __init__(self, address: str = SEED, failure: Exception | None = None) -> None:
        self.address = address
        self.failure = failure
        self.calls = 0

    def get_profile(self) -> Profile:
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return Profile.model_validate({"emailAddress": self.address})


def test_the_seed_account_opens_a_session() -> None:
    credential = FakeCredential()

    session = verify_seed_account(credential, seed_address=SEED)

    assert session.address == SEED
    assert session.scopes == SEEDER_SCOPES
    assert credential.calls == 1, "a session was issued without observing the profile"
    session.assert_bound_to(credential)


def test_the_real_mailbox_is_refused() -> None:
    with pytest.raises(SeedAccountMismatch):
        verify_seed_account(FakeCredential(PERSONAL), seed_address=SEED)


def test_case_and_whitespace_do_not_defeat_the_comparison() -> None:
    session = verify_seed_account(FakeCredential(f"  {SEED.upper()} "), seed_address=SEED)
    assert session.address == SEED


def test_a_getprofile_failure_is_not_a_pass() -> None:
    """An address that cannot be observed is an address that cannot be compared."""
    with pytest.raises(SeedAccountMismatch) as raised:
        verify_seed_account(
            FakeCredential(failure=ConnectionError("network down")), seed_address=SEED
        )
    assert "unobservable" in str(raised.value)


def test_an_empty_address_is_not_a_pass() -> None:
    """Both arms, because the two refusals are different code and only one is reachable
    from a *parsed* response.

    `Profile.email_address` is `min_length=1`, so a real `getProfile` body with an empty
    address never becomes a `Profile` at all and the refusal comes from the unobservable
    arm. `model_construct` skips validation - Pydantic's own documented way to build a model
    without it - so it is what reaches `verify_seed_account`'s explicit empty-address check.
    Without this second arm that check is a branch nothing exercises, which is the defect
    this round is about rather than a place to introduce a fresh one.
    """
    with pytest.raises(SeedAccountMismatch) as parsed:
        verify_seed_account(FakeCredential(""), seed_address=SEED)
    assert "unobservable" in str(parsed.value)

    class UnvalidatedCredential(FakeCredential):
        def get_profile(self) -> Profile:
            self.calls += 1
            return Profile.model_construct(email_address="")

    with pytest.raises(SeedAccountMismatch) as unvalidated:
        verify_seed_account(UnvalidatedCredential(), seed_address=SEED)
    assert "no emailAddress" in str(unvalidated.value)


# --- R-SEC-039: minting, and the ways in that needed no private name -------------------------


def test_the_public_constructor_cannot_mint_a_session() -> None:
    """R-SEC's reproduction, verbatim: the attack that worked in round 11.

    `SeedSession(address=<the owner's real mailbox>, scopes=(<the delete scope>,))` built a
    valid session with zero `getProfile` calls and no private name at all. The check lived in
    `_issue`, beside the constructor rather than in it.
    """
    with pytest.raises(SeedAccountMismatch) as raised:
        SeedSession(
            address=PERSONAL,
            scopes=SEEDER_SCOPES,
            credential=FakeCredential(PERSONAL),
            proof="not a proof",
        )
    assert "nobody checked" in str(raised.value)


def test_a_session_cannot_be_re_pointed_at_another_mailbox_after_it_is_minted() -> None:
    """`dataclasses.replace` is public, ordinary, and re-runs `__post_init__`.

    This is why the binding is a proof over the fields rather than a capability token in a
    field: a token would travel through `replace` untouched, and a legitimate seed session
    would become a session for the personal mailbox with one line of stdlib.
    """
    credential = FakeCredential()
    session = verify_seed_account(credential, seed_address=SEED)

    with pytest.raises(SeedAccountMismatch):
        dataclasses.replace(session, address=PERSONAL)
    with pytest.raises(SeedAccountMismatch):
        dataclasses.replace(session, scopes=(*SEEDER_SCOPES, "https://www.googleapis.com/x"))
    with pytest.raises(SeedAccountMismatch):
        dataclasses.replace(session, credential=FakeCredential())


def test_a_session_cannot_be_minted_by_subclassing_the_check_away() -> None:
    """R-RETR's round-3 attack on the disposition seal, applied here.

    It defeated a mint token by subclassing rather than by reaching for the token, and the
    same move defeats any `__post_init__` check. The class refuses to be subclassed at all,
    so the attack fails at class-creation time rather than at mint time.
    """
    with pytest.raises(TypeError) as raised:

        class Forged(SeedSession):
            def __post_init__(self) -> None:
                return None

    assert "may not be subclassed" in str(raised.value)


def test_the_proof_of_one_session_does_not_validate_another() -> None:
    """A real proof, lifted off a real session, for a different address."""
    credential = FakeCredential()
    session = verify_seed_account(credential, seed_address=SEED)

    with pytest.raises(SeedAccountMismatch):
        SeedSession(
            address=PERSONAL,
            scopes=session.scopes,
            credential=credential,
            proof=session.proof,
        )


def test_every_public_field_of_a_real_session_is_still_not_enough() -> None:
    """The forgery that worked needed only public fields.

    Address, scopes and the credential object itself are all reproduced here, so what fails
    is the binding rather than the field list being hard to guess.
    """
    credential = FakeCredential()
    session = verify_seed_account(credential, seed_address=SEED)

    with pytest.raises(SeedAccountMismatch):
        SeedSession(
            address=session.address,
            scopes=session.scopes,
            credential=session.credential,
            proof="",
        )


# --- R-SEC-040: the session is bound to the credential that produced it ----------------------


def test_a_session_minted_from_one_credential_is_refused_by_another() -> None:
    """Profile client A, then run the destructive call on client B.

    Both credentials authenticate the seed account here, so nothing about the *address* is
    wrong: the point is that the check was performed on one object and says nothing about the
    other. `is`, not `==`, because two clients holding one token are two credentials and only
    one of them was asked who it was.
    """
    minted_on = FakeCredential()
    other = FakeCredential()
    session = verify_seed_account(minted_on, seed_address=SEED)

    session.assert_bound_to(minted_on)
    with pytest.raises(SeedAccountMismatch) as raised:
        session.assert_bound_to(other)
    assert "different credential" in str(raised.value)


def test_the_session_never_renders_the_credential_it_holds() -> None:
    """A `repr` that prints the client prints whatever the client's own `repr` prints."""

    class TalkativeCredential(FakeCredential):
        def __repr__(self) -> str:
            return "TalkativeCredential(token='ya29.THE-SEED-ACCESS-TOKEN')"

    session = verify_seed_account(TalkativeCredential(), seed_address=SEED)

    rendered = f"{session!r} {session!s}"
    assert "ya29." not in rendered
    assert session.proof not in rendered
    assert SEED in rendered


# --- the claim itself, which is what R-SEC-039 was about -------------------------------------


def test_the_module_no_longer_claims_a_private_name_is_needed() -> None:
    """The false claim is the finding, so its correction is asserted rather than assumed.

    R-SEC-039 is a claim defect: the module said bypass required "reaching for the private
    name" while the public constructor sufficed. The correction has to say so plainly - a
    quiet edit leaves the next reader unable to tell a corrected claim from one that was
    always right - so the docstring is required to name the finding, to say the old claim was
    wrong, and to state what is still possible.
    """
    import mailweave_harness.pinning as pinning

    text = pinning.__doc__ or ""
    assert "R-SEC-039" in text and "R-SEC-040" in text
    assert "That was wrong" in text
    assert "object.__setattr__" in text, "the surviving residue must still be stated"


def test_the_private_path_is_the_residue_the_docstring_describes() -> None:
    """The honest half: reaching for `_mint_proof` does still work, and is claimed to.

    Asserted because an overstated control is worse than a documented one. If a later change
    made this fail, the docstring's "what remains possible" section would be wrong in the
    *safe* direction - and it would still be wrong, which is a finding either way.
    """
    from mailweave_harness.pinning import _mint_proof

    credential = FakeCredential(PERSONAL)
    forged = SeedSession(
        address=PERSONAL,
        scopes=SEEDER_SCOPES,
        credential=credential,
        proof=_mint_proof(PERSONAL, SEEDER_SCOPES, credential),
    )

    assert forged.address == PERSONAL
    assert credential.calls == 0, "no getProfile was needed - which is the documented residue"


# --- part 3b: the proof is verified where it is used, so no construction path matters --------


def _rebuild(session: SeedSession, protocol: int) -> SeedSession:
    """Apply `__reduce_ex__` by hand, which is what `copy` and `pickle` each do internally."""
    reduced = session.__reduce_ex__(protocol)
    assert isinstance(reduced, tuple), "a SeedSession reduces to a callable, not to a name"
    rebuilt = reduced[0](*reduced[1])
    state = reduced[2] if len(reduced) > 2 else None
    if state is not None:
        setter = getattr(rebuilt, "__setstate__", None)
        if setter is not None:
            setter(state)
        else:
            rebuilt.__dict__.update(state if isinstance(state, dict) else state[0] or {})
    assert isinstance(rebuilt, SeedSession)
    return rebuilt


def _blank_slate(session: SeedSession) -> SeedSession:
    """The floor of the whole class of bypass: an instance whose `__init__` never ran."""
    rebuilt = object.__new__(SeedSession)
    rebuilt.__dict__.update(session.__dict__)
    return rebuilt


def a_tampered_session(credential: FakeCredential) -> SeedSession:
    """A real session for the seed account, with the personal mailbox written into it.

    `object.__setattr__` is the surgery the module's docstring names as an unclosable
    residue. The point of the tests below is not that this is preventable - it is not - but
    that nothing the tampered object is put through can make it authorise anything.
    """
    session = verify_seed_account(credential, seed_address=SEED)
    tampered = copy.copy(session)
    object.__setattr__(tampered, "address", PERSONAL)
    return tampered


#: Every way this interpreter will rebuild an object without calling `__init__`, plus the
#: object itself. `SeedSession` defines none of `__reduce__`, `__reduce_ex__`, `__getstate__`,
#: `__setstate__`, `__copy__` or `__deepcopy__`, so each of these restores `__dict__`
#: directly and `__post_init__` never runs.
REBUILDS: dict[str, Callable[[SeedSession], SeedSession]] = {
    "the tampered object itself": lambda session: session,
    "copy.copy": copy.copy,
    "copy.deepcopy": copy.deepcopy,
    "pickle, default protocol": lambda session: pickle.loads(pickle.dumps(session)),
    "pickle, protocol 2": lambda session: pickle.loads(pickle.dumps(session, 2)),
    "pickle, highest protocol": lambda session: pickle.loads(
        pickle.dumps(session, pickle.HIGHEST_PROTOCOL)
    ),
    "__reduce_ex__(2), applied by hand": lambda session: _rebuild(session, 2),
    "__reduce_ex__(4), applied by hand": lambda session: _rebuild(session, 4),
    "object.__new__ and a copied __dict__": _blank_slate,
}


@pytest.mark.parametrize("rebuild", sorted(REBUILDS))
def test_no_way_of_rebuilding_a_session_authorises_a_tampered_one(rebuild: str) -> None:
    """The orchestrator's finding: `__post_init__` is a check at *construction*, and there
    are several constructions.

    Before this, `copy.copy` of a tampered session authorised the destructive credential
    outright - the address said the owner's real mailbox and the proof was the seed
    account's, because `__dict__` was restored wholesale and nothing re-checked it. Two of
    the three paths happened to be refused, and for the wrong reason: `deepcopy` and
    `pickle` copy the credential too, so the old identity comparison failed on an artefact
    of deep copying rather than on anything about the proof.

    This is the eighth appearance of "one shape validated, peers trusted", inside the fix
    for the seventh: `dataclasses.replace` was defended and `__reduce_ex__`, `__copy__` and
    `__deepcopy__` were trusted. It is not fixed by naming those three - it is fixed by the
    check moving to the point of use, which is why this test asserts about
    `assert_bound_to` and not about any of the paths below.
    """
    credential = FakeCredential()
    rebuilt = REBUILDS[rebuild](a_tampered_session(credential))

    assert rebuilt.address == PERSONAL, "the tampering did not survive; the test asserts nothing"
    with pytest.raises(SeedAccountMismatch):
        rebuilt.assert_bound_to(credential)


@pytest.mark.parametrize("rebuild", sorted(REBUILDS))
def test_rebuilding_an_untampered_session_still_authorises_its_own_credential(
    rebuild: str,
) -> None:
    """The check must not close the door on the legitimate case.

    A session that was copied and not altered is still a session for the account whose
    profile was observed, and the credential it names is still the one that answered. An
    identity comparison would have refused a `deepcopy` here - for the artefact reason
    above - so the recomputation is what makes the refusals mean something.
    """
    credential = FakeCredential()
    rebuilt = REBUILDS[rebuild](verify_seed_account(credential, seed_address=SEED))

    rebuilt.assert_bound_to(credential)


def test_a_session_that_reaches_another_process_authorises_nothing_there() -> None:
    """`_MINT_KEY` is per-process, so a session cannot be carried out of the one that minted
    it.

    Simulated by replacing the module's key rather than by spawning an interpreter: what a
    second process has is a different key, and this is that, without adding a subprocess to
    a suite that has none. The scenario is the one worth failing closed on - a cache, xdist,
    or multiprocessing handing a session to a worker that never observed a profile.
    """
    credential = FakeCredential()
    session = verify_seed_account(credential, seed_address=SEED)
    session.assert_bound_to(credential)

    with (
        mock.patch.object(pinning, "_MINT_KEY", b"the key another process generated"),
        pytest.raises(SeedAccountMismatch),
    ):
        session.assert_bound_to(credential)


def test_the_mint_key_is_generated_per_process_and_not_baked_into_the_module() -> None:
    """The half of the claim above that patching a module attribute cannot establish.

    Simulating a second process by replacing `_MINT_KEY` shows what happens *given* a
    different key; it says nothing about whether the key would actually differ. A literal
    baked into the source would make every process share one, and the test above would still
    pass. Asserted from the source rather than by spawning an interpreter, because this
    suite runs no subprocesses and adding one to check a constant would be a poor trade.
    """
    assignment = next(
        node
        for node in ast.walk(ast.parse(inspect.getsource(pinning)))
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "_MINT_KEY"
    )
    assert assignment.value is not None
    generated = ast.unparse(assignment.value)
    assert "secrets.token_bytes" in generated, (
        f"_MINT_KEY is {generated}; a key that is not generated at import is a key every "
        "process shares, and a session would then authorise a credential in a process that "
        "never observed a profile"
    )


# --- the other two controls ------------------------------------------------------------------


def test_the_server_package_still_cannot_import_the_harness() -> None:
    """The import direction is the third control, and it is enforced by a CI guard."""
    from pathlib import Path

    from tools.guards import forbidden_imports

    assert forbidden_imports(Path("server/src")) == []


def test_the_destructive_scope_literal_is_absent_from_server_code() -> None:
    from pathlib import Path

    from tools.guards import scope_literal_sweep

    assert scope_literal_sweep(Path("server/src")) == []


# --- R-SEC-045: the binding was a memory address, and addresses are reused -------------------


def test_a_credential_this_process_never_observed_can_produce_no_proof_at_all() -> None:
    """The material, asserted directly: R-SEC-045 was about what the HMAC binds.

    The proof used to bind `str(id(credential))`, which any object can present simply by
    existing at the right address. It now binds a nonce minted where a `Profile` came back, so
    for a credential this process never observed there is no proof to compute - not a
    different one, none. This is the deterministic half of the finding: it fails the moment
    the binding goes back to anything a fresh object can take on, without depending on the
    allocator to recycle anything.
    """
    unobserved = FakeCredential()

    assert pinning._expected_proof(SEED, SEEDER_SCOPES, unobserved) is None

    observed = FakeCredential()
    verify_seed_account(observed, seed_address=SEED)
    assert pinning._expected_proof(SEED, SEEDER_SCOPES, observed) is not None


def _forged_session(address: str, scopes: tuple[str, ...], proof: str) -> SeedSession:
    """A session carrying stolen public fields, built without running `__post_init__`.

    `object.__new__` plus a copied `__dict__` is the floor of the whole bypass class, and it
    is used here so the test reaches `assert_bound_to` even where the constructor already
    refuses - the guarantee is the use-site check, and a test that only ever saw the early
    failure would not be testing it.
    """
    shell = _blank_slate(verify_seed_account(FakeCredential(), seed_address=SEED))
    object.__setattr__(shell, "address", address)
    object.__setattr__(shell, "scopes", scopes)
    object.__setattr__(shell, "proof", proof)
    return shell


def test_a_stolen_proof_does_not_authorise_a_credential_at_the_freed_address() -> None:
    """R-SEC's reproduction: four public reads, no private name, no copy, no pickle.

    Read `address`, `scopes` and `proof` off a real session; let the session and its credential
    go out of scope; allocate attacker-controlled credentials until one lands on the freed
    address; build with the **ordinary public constructor**. Before this round that session was
    accepted by `__post_init__` and authorised by `assert_bound_to`, and the credential it
    authorised reported a different mailbox from the one the session named - measured at 59/60
    and 60/60 by R-SEC and 39/40 by the orchestrator.

    **Two halves, because one of them cannot be made deterministic.** Whether an allocation
    lands on a freed address is CPython's business, and in a process that has already run
    thousands of tests it is genuinely unpredictable: measured here at 12/12, 1/12 and 0/12 on
    three consecutive runs of the same suite. So the loop below asserts about every recycle it
    *does* get, and the planted half then reaches the identical state unconditionally - an
    entry whose weak reference no longer resolves to the object at its key is exactly what a
    recycled address produces. The test therefore never asserts nothing, and never fails
    because an allocator did something it was entitled to do.
    """

    def steal() -> tuple[str, tuple[str, ...], str, int]:
        credential = FakeCredential()
        session = verify_seed_account(credential, seed_address=SEED)
        return session.address, session.scopes, session.proof, id(credential)

    for _ in range(12):
        address, scopes, proof, target = steal()
        # No `gc.collect()` here: the credential dies by refcount when `steal` returns, and a
        # collection first shuffles the arenas and makes reuse much less likely.
        pool = []
        impostor: FakeCredential | None = None
        for _ in range(64):
            candidate = FakeCredential(PERSONAL)
            if id(candidate) == target:
                impostor = candidate
                break
            pool.append(candidate)
        if impostor is None:
            continue
        with pytest.raises(SeedAccountMismatch):
            SeedSession(address=address, scopes=scopes, credential=impostor, proof=proof)
        with pytest.raises(SeedAccountMismatch):
            _forged_session(address, scopes, proof).assert_bound_to(impostor)

    address, scopes, proof, target = steal()
    planted = FakeCredential(PERSONAL)
    collected = FakeCredential()
    stale = weakref.ref(collected)
    del collected
    gc.collect()
    pinning._OBSERVED._entries[id(planted)] = (stale, "the observed credential's nonce")

    with pytest.raises(SeedAccountMismatch):
        SeedSession(address=address, scopes=scopes, credential=planted, proof=proof)
    with pytest.raises(SeedAccountMismatch) as raised:
        _forged_session(address, scopes, proof).assert_bound_to(planted)
    assert "different credential" in str(raised.value)


def test_the_proof_does_not_bind_the_credentials_address() -> None:
    """The finding at the level it was actually about: what goes into the HMAC.

    R-SEC-045 is not "a session can be forged"; it is "the material is an address". Asserted
    directly, because the end-to-end version above needs the allocator to recycle and this one
    does not: if the binding ever goes back to `id(credential)`, the two digests below become
    the same one.
    """
    credential = FakeCredential()
    session = verify_seed_account(credential, seed_address=SEED)

    bound_to_the_address = hmac.new(
        pinning._MINT_KEY,
        pinning._material(SEED, SEEDER_SCOPES, str(id(credential))),
        hashlib.sha256,
    ).hexdigest()

    assert session.proof != bound_to_the_address
    assert session.proof == pinning._expected_proof(SEED, SEEDER_SCOPES, credential)


def test_the_nonce_belongs_to_the_object_and_not_to_its_address() -> None:
    """The mechanism, without depending on the allocator to recycle anything.

    An entry whose weak reference no longer resolves to the caller's object is the exact state
    a recycled address produces, and it is reachable deterministically by planting one. The
    registry answers `None`, which every caller here treats as "never observed".
    """
    live = FakeCredential()
    verify_seed_account(live, seed_address=SEED)
    assert pinning._OBSERVED.recall(live) is not None

    impostor = FakeCredential(PERSONAL)
    collected = FakeCredential()
    stale = weakref.ref(collected)
    del collected
    gc.collect()
    pinning._OBSERVED._entries[id(impostor)] = (stale, "the observed credential's nonce")

    assert pinning._OBSERVED.recall(impostor) is None
    assert pinning._expected_proof(SEED, SEEDER_SCOPES, impostor) is None


def test_the_binding_does_not_outlive_the_credential_it_was_minted_from() -> None:
    """A nonce is a fact about an object, so it ends when the object does."""
    credential = FakeCredential()
    verify_seed_account(credential, seed_address=SEED)
    key = id(credential)
    assert key in pinning._OBSERVED._entries

    del credential
    gc.collect()

    assert key not in pinning._OBSERVED._entries, (
        "the mint's record outlived the credential it describes; an entry that outlives its "
        "subject is one a later object at the same address can inherit (R-SEC-045)"
    )


def test_a_credential_that_cannot_be_told_apart_from_its_address_is_refused() -> None:
    """`object()` and `__slots__` classes without `__weakref__` cannot be sealed.

    Binding to one would be binding to an address again, so it is refused at the mint rather
    than admitted with a weaker guarantee. `SeedSession(credential=object())` was one of the
    shapes R-SEC's reproduction accepted.
    """

    class Unreferenceable:
        __slots__ = ("address",)

        def __init__(self) -> None:
            self.address = SEED

        def get_profile(self) -> Profile:
            return Profile.model_validate({"emailAddress": SEED})

    with pytest.raises(SeedAccountMismatch) as raised:
        verify_seed_account(Unreferenceable(), seed_address=SEED)
    assert "weak references" in str(raised.value)

    with pytest.raises(SeedAccountMismatch):
        SeedSession(address=SEED, scopes=SEEDER_SCOPES, credential=object(), proof="")


def test_two_credentials_never_share_a_binding() -> None:
    """Distinct objects get distinct nonces, so one session never speaks for another client."""
    credentials = [FakeCredential() for _ in range(8)]
    for credential in credentials:
        verify_seed_account(credential, seed_address=SEED)

    nonces = [pinning._OBSERVED.recall(credential) for credential in credentials]
    assert all(nonce is not None for nonce in nonces)
    assert len(set(nonces)) == len(nonces)


# --- R-SEC-052: one proof binds one triple ---------------------------------------------------


def test_two_different_triples_cannot_share_the_hmac_material() -> None:
    """The material is length-prefixed, so a separator inside a component cannot move a bound.

    Not exploitable today - the address comes from `getProfile` and the scopes from a module
    constant - and asserted anyway, because "this proof binds one triple" is either true or it
    is a sentence. Both collisions below held before this round.
    """
    credential = FakeCredential()
    verify_seed_account(credential, seed_address=SEED)
    proof = partial(pinning._expected_proof, credential=credential)

    assert proof("a\x00b", ("c",)) != proof("a", ("b\x00c",))
    assert proof("x", ("p\x1fq",)) != proof("x", ("p", "q"))
    assert proof("ab", ("c",)) != proof("a", ("bc",))
