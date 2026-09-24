"""Account pinning for the harness credential (AD A.4, B.9, SN 2.5; RR SEC-03).

The harness holds `https://mail.google.com/` - insert, import, and `batchDelete`. The rule it
must never be able to break is that this capability cannot reach the owner's real mailbox.

**Three controls, and only one of them is code.** Saying so plainly matters, because the
strongest of the three is not ours:

  1. **Google-side (the real one).** The harness OAuth client sits in a separate Cloud project
     whose publishing status is *Testing* with a test-user allowlist containing only the seed
     account. Google itself refuses consent for any other mailbox on that client, so the
     personal mailbox **cannot hold a token for the harness client at all** (ADV-205). This is
     what makes the pinning structural rather than conventional: it is not a check that could
     be skipped, it is a grant that cannot be issued.
  2. **Process-side (this module).** `users.getProfile(me).emailAddress` is compared with the
     configured seed address before any harness operation, and a mismatch aborts. This catches
     the case control 1 cannot: a *correctly issued* seed token used against the wrong
     configuration, and the day someone moves the harness project to Production and control 1
     silently stops existing.
  3. **Import-side.** `server/**` may not import this package, enforced by a CI guard, so no
     MCP tool can reach a write path even indirectly.

## Three corrections, in the order they were forced

This module has had to withdraw a claim three times. Each correction is kept, in order,
because a reader deciding how much to trust the next claim should be able to see the record
rather than only its latest revision.

**First (R-SEC-039/040).** Round 11 said, here, that building a `SeedSession` beside the
check "has to reach for a private name, which is a line a reviewer sees". **That was wrong,
and it was wrong in the direction that matters: it overstated the control.** R-SEC built a
valid session for the owner's real mailbox address with the ordinary public constructor -
`SeedSession(address=..., scopes=...)` - having made no `getProfile` call and touched no
private name at all. The token check lived in `_issue`, a classmethod *beside* the public
constructor, so it guarded a door with an open door next to it. A second finding (R-SEC-040)
noted that the session carried two strings and no link to the credential that produced them,
so a session minted while authenticated as the seed account could be handed to an operation
running on a different client.

**Second (the orchestrator, round 12).** The first fix put the proof check in `__post_init__`
and said the check was "*in* the constructor, not beside it". That was true and it was not
enough. `__init__` is not the only way a Python object comes into being: `SeedSession` defines
none of `__reduce__`, `__reduce_ex__`, `__getstate__`, `__setstate__`, `__copy__` or
`__deepcopy__`, so `copy.copy`, `copy.deepcopy` and `pickle` all restore `__dict__` directly
and `__post_init__` never runs:

    legit = verify_seed_account(client, seed_address=SEED)
    tampered = copy.copy(legit)
    object.__setattr__(tampered, "address", "<the owner's real mailbox>")
    copy.copy(tampered).assert_bound_to(client)     # authorised, before round 12's 3b

That was the **eighth** appearance of this project's recurring defect, and it appeared inside
the fix for the seventh: `dataclasses.replace` was defended and its peers `__reduce_ex__`,
`__copy__` and `__deepcopy__` were trusted. The answer was not to defend those three by name -
that leaves a fourth for the next round, and Python is free to ship a fifth - but to move the
check to the point of use (amendment A7's move: change the operation rather than enumerate the
ways in). `assert_bound_to` recomputes the proof over the credential in hand and compares.

**Third (R-SEC-045, this round).** The shape was right and the *material* was wrong. The proof
bound `str(id(credential))`, and this module argued that an id cannot be recycled "because the
session holds a reference to the object". That argument was false for the attacker's session,
and the second correction is what broke it: `assert_bound_to` deliberately stopped reading
`self.credential`, so nothing kept the minting credential alive once the honest session was
dropped. The forgery needed no private name, no `object.__setattr__`, no copy and no pickle:

    address, scopes, proof = <four public attribute reads off a real session>
    # let the honest session and its credential go out of scope, then allocate
    # attacker-controlled credentials until one lands on the freed address
    SeedSession(address=address, scopes=scopes, credential=evil, proof=proof
                ).assert_bound_to(evil)            # authorised, before this round

Reproduced at 59/60 and 60/60 independent trials, and at 39/40 by the orchestrator. The
credential it authorised reported a **different mailbox** from the one the session named,
which is precisely the property this module exists to make impossible.

An `id` is where an object happens to live, and an address is inherited by whatever is
allocated there next. The proof now binds a **per-credential nonce**, minted at the moment a
`Profile` was observed and held in a `mailweave.sealing.IdentityRegistry` - a table keyed by
the object itself, whose entry dies with it. A credential this process never observed has no
nonce, so there is nothing for a stolen proof to agree with; a credential allocated onto a
freed address is a different object and inherits nothing. See `sealing.py` for why that
registry is keyed by identity twice over rather than by a `WeakKeyDictionary`.

## What the checks are each worth, so neither is over-read

  * **`assert_bound_to` is the guarantee.** Every destructive harness operation takes a
    session *and* the credential it is about to run on, and calls this. WS-16 has no other
    supported way to use one. It settles three questions with one comparison: that the address
    and scopes are the ones a profile was observed for, that the credential in hand is the one
    that answered `getProfile` (R-SEC-040), and that some code in this process observed a
    profile at all - because a nonce is minted only where a real `Profile` came back.
  * **`__post_init__` is an early failure, not the guarantee.** It refuses a session built
    beside the check and one altered by `dataclasses.replace`, at the moment the mistake is
    made rather than at the moment it matters. It is what makes the ordinary error loud; it is
    not what makes the property hold.
  * **Subclassing is refused outright.** R-RETR's round-3 attack on the disposition seal
    (`ROUND_03/R-RETR.md`, attack 8) bypassed a mint token by subclassing rather than by
    reaching for it, and that attack applies verbatim to any `__post_init__` check.

## What this establishes, and what it does not

Three enumerations of "what remains possible" have been written here and **all three were
falsified** - twice by a reviewer and once by the orchestrator. So this section does not
enumerate. It states the property positively, which is checkable, and then names residues
**without claiming the list is complete**, because the evidence is that this module's authors
have not been able to complete one.

*The property.* `assert_bound_to(credential)` succeeds only if a `Profile` naming
`self.address` was observed **from that object** in this process, and only if the session's
fields are the ones that observation produced. Every input to that sentence is either
re-derived at the call (the fields, through the HMAC) or held outside the session where the
session cannot restate it (the credential's nonce). No construction path is consulted, so none
has to be enumerated.

*What it does not establish, named without a completeness claim.*

  * **In-process code is not an attacker this can stop.** `object.__setattr__` writes fields,
    `object.__new__` builds an instance without `__init__`, and importing `_mint_proof` mints a
    nonce for any object and computes a matching proof. All three are unclosable in Python;
    what changed is that none of them is *ordinary* code, and each is a line a reviewer sees.
  * **A credential can lie about itself.** `ProfileSource` is an object and an object's method
    table is mutable: `client.get_profile = lambda: Profile(<any address>)` on the very client
    a destructive call will run on mints a session for a mailbox no honest `getProfile`
    returned. The binding is to the object that answered, not to an answer that was honest.
  * **Nothing type-checks a session at a use site.** A `class Fake` with a do-nothing
    `assert_bound_to` satisfies every caller, and an operation that never calls
    `assert_bound_to` at all is stopped by nothing here. In-process, no object can force a
    caller to ask it a question. What the design buys is that the session is a *parameter*
    such an operation must already hold, and that holding one proves nothing on its own.
  * **The registry is per-process.** A session that reaches another process - a cache, xdist,
    multiprocessing - authorises nothing there, twice over: `_MINT_KEY` differs and the nonce
    table is empty. That is the intended failure, and it is closed rather than silent.
  * **Control 1 is not verifiable from here at all.** Whether Google's Testing-status
    allowlist really refuses consent for the personal mailbox is a Console setting, not
    executable code, and no test in this repository can establish it.
  * **The address control 2 compares against is a caller's parameter, not configuration**
    (R-SEC-059). Control 2 is stated above as "`users.getProfile(me).emailAddress` is compared
    with **the configured** seed address". `seed_address` is an ordinary keyword argument of
    `verify_seed_account` with no default and no binding to `MailweaveConfig`, and `scopes` is
    a keyword argument with a default and no validation, so

        verify_seed_account(cred, seed_address="<the owner's real mailbox>")

    mints a session naming that mailbox, through the public API and with no private name -
    and a `scopes=(..., "EXTRA")` mints one declaring a scope nobody granted. The mechanism is
    sound; the *input* it compares against is not yet pinned to anything, and there is no
    caller in either tree to establish that it will be. The one related config field is
    `MailweaveConfig.seed_account_hash`, a hash, which cannot be handed to
    `assert_seed_account`, which compares plaintext addresses.

    This is a **precondition on WS-16**, recorded here because it decides whether control 2
    works at all: the seeder must read the seed address from configuration rather than accept
    it from its caller - by deriving it inside this module, or by resolving the
    hash-versus-plaintext mismatch so `seed_account_hash` can be the input - and should refuse
    scopes that are not a subset of `SEEDER_SCOPES`. It is not fixed here because binding a
    parameter to a config field this module does not read, for a caller that does not exist,
    would be guessing at WS-16's shape; naming it is what a later round can act on.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

from mailweave.gmail import Profile
from mailweave.sealing import CannotBeSealed, IdentityRegistry
from mailweave_harness.scopes import SEEDER_SCOPES, SeedAccountMismatch, assert_seed_account

#: Per-process, module-private, never exported and never rendered. It keys the proof a
#: session carries, so a session's fields cannot be altered - by `replace`, by rebuilding, by
#: anything short of the `object.__setattr__` surgery the docstring names - without the proof
#: ceasing to match. Regenerated every process: a proof is not meant to outlive the run that
#: observed the profile, and a stored one would be a credential in its own right.
_MINT_KEY: Final[bytes] = secrets.token_bytes(32)

#: What the mint established about a credential: a random nonce, minted where a real
#: `Profile` came back from it, and held against *that object*.
#:
#: This is the material R-SEC-045 was about. It replaces `id(credential)`, which named an
#: address rather than an object and was therefore inheritable by the next allocation at that
#: address. A nonce is not derivable from anything a fresh object can take on: an attacker who
#: builds their own credential gets no entry, and one that lands on a freed address gets no
#: entry either, because the entry belongs to the object that was observed and dies with it.
_OBSERVED: Final[IdentityRegistry[str]] = IdentityRegistry(
    "credentials this process observed a getProfile response from"
)


class ProfileSource(Protocol):
    """The credential in use, as the object that can ask Gmail who it is authenticated as.

    Typed as the call rather than as a token, because *the object that performs the calls* is
    the thing a session must be bound to: binding to a token string would let two clients
    share one binding, and binding to a bound method would fail on identity, since
    `client.get_profile is client.get_profile` is `False` in Python.

    `mailweave.gmail.GmailClient` satisfies this as it stands, which is the point - WS-16
    hands over the client it is about to run the destructive call on, and there is no adapter
    in between for the two to drift apart in.

    One requirement the protocol cannot state in its signature: the object must support weak
    references, because that is what lets this process tell it apart from a later object at
    the same address. Ordinary classes do; `object()` and `__slots__` classes without
    `__weakref__` do not, and minting refuses them rather than binding to an address
    (`sealing.CannotBeSealed`).
    """

    def get_profile(self) -> Profile: ...


def _material(address: str, scopes: tuple[str, ...], nonce: str) -> bytes:
    """The HMAC's input, length-prefixed so two different triples cannot share it.

    R-SEC-052: the previous spelling joined the parts with separator characters, so
    `("a\\x00b", ("c",))` and `("a", ("b\\x00c",))` produced identical material, as did
    `("p\\x1fq",)` and `("p", "q")` as scopes. Not exploitable today - the address comes from
    `getProfile` and the scopes from a module constant, so neither can be steered to carry a
    separator - but a proof that claims to bind one triple should bind one triple, and this
    is four lines.
    """
    parts = (address, *scopes, nonce)
    joined = b"".join(
        f"{len(encoded)}:".encode() + encoded
        for encoded in (part.encode("utf-8") for part in parts)
    )
    return f"{len(parts)}|".encode() + joined


def _mint_proof(address: str, scopes: tuple[str, ...], credential: object) -> str:
    """Bind the three things a session states, so none of them can be changed afterwards.

    Minting is what establishes the credential's identity: the first proof computed for an
    object gives it a nonce, held in `_OBSERVED` against that object. `verify_seed_account` is
    the only caller in this tree, and it calls this only after a real `Profile` came back -
    which is what makes "a nonce exists" mean "a profile was observed from this object".

    Reaching for this function directly mints a nonce for anything and computes a matching
    proof. That residue is named in the module docstring and asserted by a test, because a
    control whose limits are documented is worth more than one whose limits are discovered.
    """
    nonce = _OBSERVED.recall(credential)
    if nonce is None:
        try:
            nonce = _OBSERVED.remember(credential, secrets.token_hex(32))
        except CannotBeSealed as failure:
            raise SeedAccountMismatch(
                "this credential cannot be bound to a session: it does not support weak "
                "references, so nothing distinguishes it from a later object allocated at "
                "the same address - which is the defect R-SEC-045 was filed against"
            ) from failure
    return hmac.new(_MINT_KEY, _material(address, scopes, nonce), hashlib.sha256).hexdigest()


def _refuse_unless_comparable(proof: object) -> str:
    """`proof` as an ASCII `str`, or `SeedAccountMismatch` - never a `TypeError` (R-SEC-057).

    `hmac.compare_digest` is defined for two ASCII `str`s or two byte-likes and raises
    `TypeError` for anything else, so `assert_bound_to` on a session whose `proof` is `None`,
    an `int`, `bytes`, a `list` or a `str` with a non-ASCII character raised out of the
    comparison instead of answering it. Six shapes, six `TypeError`s, zero
    `SeedAccountMismatch` - which falsified the sentence next door, "it is one comparison and
    it has one answer".

    Fail-closed either way: the operation aborts. But a WS-16 call site written as
    `except SeedAccountMismatch:` would get an exception it did not plan for, and a refusal
    that arrives as the wrong type is a refusal a caller can mishandle. Reaching this needs a
    type violation `mypy --strict` rejects in this tree - `object.__new__(SeedSession)` plus a
    written field - so it is robustness rather than a forgery route, and it is **not** caught
    with a `TypeError` handler that continues: the answer is the refusal, not the comparison.
    """
    if type(proof) is not str or not proof.isascii():
        raise SeedAccountMismatch(
            "this SeedSession carries no comparable proof: a proof is an ASCII string "
            f"produced by _mint_proof, and this one is a {type(proof).__name__}. A session "
            "whose proof cannot be compared authorises nothing (SEC-03, R-SEC-057)"
        )
    return proof


def _expected_proof(address: str, scopes: tuple[str, ...], credential: object) -> str | None:
    """The proof this credential's own nonce produces, or `None` if it has no nonce.

    Lookup only - it never mints. `None` is the answer for a credential this process never
    observed a profile from, which includes an attacker-supplied one, a copy of a real one,
    and one allocated onto the address a collected credential used to occupy. All three are
    the same fact and all three must fail closed, which is R-SEC-045.
    """
    nonce = _OBSERVED.recall(credential)
    if nonce is None:
        return None
    return hmac.new(_MINT_KEY, _material(address, scopes, nonce), hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class SeedSession:
    """Proof that the credential in hand authenticates the configured seed account.

    Every destructive harness operation takes one of these *and* the credential it will run
    on, and calls `assert_bound_to`. The seeder does not exist yet (WS-16), so this is the
    contract it will be written against rather than a wrapper around code that is already
    here - which is the right order: the constraint lands before the capability it constrains.
    """

    address: str
    scopes: tuple[str, ...]
    #: The object that performed the `getProfile` this session rests on.
    #:
    #: It is **not** what the proof binds, and holding it authorises nothing: the binding is
    #: the nonce in `_OBSERVED`, which is looked up against the credential a use site actually
    #: passes. Round 12 kept this field to "keep the minting credential alive so its id cannot
    #: be recycled", and that is the argument R-SEC-045 falsified - nothing enforced that a
    #: session still held it, and `assert_bound_to` had stopped reading it. It is kept for
    #: what it honestly is: the record of which object the session was minted from.
    credential: object = field(repr=False)
    #: `_mint_proof` over the address, the scopes and the credential's nonce. Not a secret and
    #: not a credential - on its own it authorises nothing, and unlike round 12's version that
    #: is now true for an attacker who holds it, because the nonce it was computed over belongs
    #: to an object they do not have. It is still not rendered: a `repr` that prints it invites
    #: the assumption that carrying it around is how a session is obtained.
    proof: str = field(repr=False)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        raise TypeError(
            "SeedSession may not be subclassed: a subclass can replace __post_init__ and "
            "mint a session for any address, which is how R-RETR defeated the disposition "
            "seal's mint token in round 3 without reaching for the token at all"
        )

    def __post_init__(self) -> None:
        """An early failure for the ordinary mistakes. **Not** the guarantee - see below.

        This runs on `__init__` and on `dataclasses.replace`, and on nothing else: `copy`,
        `deepcopy` and `pickle` restore `__dict__` without it. That is why the check that
        the property rests on is `assert_bound_to`, and why this one exists only to make a
        session built beside the check fail at the point somebody wrote the mistake rather
        than at the point it would have mattered.
        """
        if not self.address:
            raise SeedAccountMismatch("a seed session cannot be opened for no address")
        proof = _refuse_unless_comparable(self.proof)
        expected = _expected_proof(self.address, self.scopes, self.credential)
        if expected is None or not hmac.compare_digest(proof, expected):
            raise SeedAccountMismatch(
                "a SeedSession is issued by verify_seed_account and by nothing else. This "
                "one carries no proof that a getProfile response was ever observed for this "
                "address on this credential - a session built beside the check, or altered "
                "after it, is a session for an account nobody checked (R-SEC-039)"
            )

    def assert_bound_to(self, credential: object) -> None:
        """Re-establish at the point of use everything minting established. The chokepoint.

        Every destructive harness operation takes a session **and** the credential it is
        about to run on, and calls this first. One `compare_digest` settles all three
        questions, because the proof binds all three inputs:

          * are the address and scopes the ones a `getProfile` was actually observed for -
            or were they altered after minting, by `replace`, by `object.__setattr__`, or by
            a reconstruction that skipped `__post_init__` (`copy`, `deepcopy`, `pickle`);
          * is the credential in hand the one that answered that `getProfile` (R-SEC-040) -
            asked by looking up **that object's own nonce**, so a session that was
            legitimately copied still works with its own client, a session paired with a
            different client does not, and neither does one paired with an object that merely
            occupies the address a collected credential used to have (R-SEC-045);
          * did any code in this process observe a profile at all - a nonce exists only where
            a `Profile` came back, and `_MINT_KEY` is generated per process.

        The refusal does not say *which* of the three failed. It is one comparison and it has
        one answer: this session does not authorise this credential - and it is a
        `SeedAccountMismatch` for every input, including a `proof` that is not an ASCII `str`
        and therefore is not something `compare_digest` can be asked about at all
        (`_refuse_unless_comparable`, R-SEC-057).
        """
        proof = _refuse_unless_comparable(self.proof)
        expected = _expected_proof(self.address, self.scopes, credential)
        if expected is None or not hmac.compare_digest(proof, expected):
            raise SeedAccountMismatch(
                "this SeedSession does not authorise this credential. Either it was minted "
                "from a different credential than the one about to be used - the account "
                "check was performed on the client that answered getProfile and says "
                "nothing about any other (SEC-03, R-SEC-040) - or this process never "
                "observed a getProfile response from this object at all, or its address or "
                "scopes are not the ones that check observed, which is what a session "
                "rebuilt by copy, deepcopy or pickle around an altered field looks like "
                "from here"
            )

    def __repr__(self) -> str:
        return f"SeedSession(address={self.address!r}, scopes={self.scopes!r}, bound=True)"


def verify_seed_account(
    credential: ProfileSource,
    *,
    seed_address: str,
    scopes: tuple[str, ...] = SEEDER_SCOPES,
) -> SeedSession:
    """Call `getProfile` on `credential`, compare, and issue a session bound to it - or abort.

    The comparison itself is `mailweave_harness.scopes.assert_seed_account`, imported rather
    than re-implemented. It is a five-line function and re-typing it here would be the
    project's own recurring defect - one shape checked in two places, the second copy the one
    nobody updates - committed in the module whose entire purpose is that the check happens.

    A `getProfile` that fails is **not** a pass. An address that cannot be observed is an
    address that cannot be compared, and the harness aborts rather than proceeding on the
    assumption that a network error means the right mailbox.

    This function is the only code that computes a mint proof, and it computes one only after
    a real `Profile` came back from the credential it is about to bind. That is what "minted
    by the code that observed the profile" means here, and it is checkable by reading this one
    function rather than by trusting every caller.
    """
    try:
        profile = credential.get_profile()
    except Exception as failure:
        raise SeedAccountMismatch(
            "the harness could not observe the authenticated address "
            f"({type(failure).__name__}), so it cannot be compared with the seed account. "
            "Refusing to run: an unobservable account is not a verified one."
        ) from failure
    observed = profile.email_address
    if not observed:
        raise SeedAccountMismatch(
            "users.getProfile returned no emailAddress; refusing to run destructive "
            "operations against a mailbox this process cannot name"
        )
    assert_seed_account(authenticated_address=observed, seed_address=seed_address)
    address = observed.strip().lower()
    bound_scopes = tuple(scopes)
    return SeedSession(
        address=address,
        scopes=bound_scopes,
        credential=credential,
        proof=_mint_proof(address, bound_scopes, credential),
    )
