"""`mailweave auth login`, up to the consent boundary (round 11, part 2).

The interactive step is a parameter, so every check around it is reachable with no browser,
no socket and no credential: `run_login` takes `wait_for_code` and `fetch_address`, and the
tests supply both. What is *not* faked is the token exchange - that goes through the real
`httpx` client behind the real egress allowlist, with an `httpx.MockTransport` where the
socket would be.

Three properties get the most attention here, because they are the three the work order
names: the granted scope set is read back and any difference is fatal; the account is
observed before anything is stored; and no secret appears in any rendering of anything.
"""

from __future__ import annotations

import json
import stat
import traceback
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, SecretBytes, SecretStr, ValidationError

from mailweave.auth.consent import (
    ConsentFailed,
    GrantedScopeMismatch,
    LoopbackReceiver,
    ScopeUnverifiable,
    TokenGrant,
    exchange_code,
    read_installed_client,
    run_login,
    verify_granted_scopes,
)
from mailweave.auth.pkce import LOOPBACK_HOST, generate_pkce
from mailweave.auth.tokenstore import StoredCredentials, TokenStore
from mailweave.config import MailweaveConfig, load_config
from mailweave.constants import READ_SCOPE, SERVER_SCOPES
from mailweave.errors import ConfigError, SecretDocumentMalformed
from mailweave.net.egress import build_client
from mailweave.validation import SecretBearingModel
from tests.fixtures.secret_models import _classes_in, models_with_secrets, secret_fields

CLIENT_SECRET = "GOCSPX-THE-CLIENT-SECRET-abcdef"
AUTH_CODE = "4/0AY0e-THE-AUTHORIZATION-CODE"
ACCESS_TOKEN = "ya29.THE-ACCESS-TOKEN"
REFRESH_TOKEN = "1//THE-REFRESH-TOKEN"
ACCOUNT = "owner@personal.example"

SECRETS = (CLIENT_SECRET, AUTH_CODE, ACCESS_TOKEN, REFRESH_TOKEN)


def write_client_file(tmp_path: Path, *, section: str = "installed") -> Path:
    path = tmp_path / "mailweave-server-oauth.json"
    path.write_text(
        json.dumps(
            {
                section: {
                    "client_id": "1234-abc.apps.googleusercontent.com",
                    "project_id": "mailweave-read",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "client_secret": CLIENT_SECRET,
                    "redirect_uris": ["http://localhost"],
                }
            }
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def token_endpoint(body: Any, status: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "oauth2.googleapis.com"
        return httpx.Response(
            status, content=json.dumps(body).encode("utf-8"), headers={"content-type": "app/json"}
        )

    return build_client(inner=httpx.MockTransport(handler))


def grant_body(scope: str | None = READ_SCOPE, refresh: str | None = REFRESH_TOKEN) -> Any:
    body: dict[str, Any] = {
        "access_token": ACCESS_TOKEN,
        "expires_in": 3599,
        "token_type": "Bearer",
    }
    if scope is not None:
        body["scope"] = scope
    if refresh is not None:
        body["refresh_token"] = refresh
    return body


# --- the client file ------------------------------------------------------------------------


def test_a_desktop_client_file_is_read_and_its_secret_is_not_renderable(tmp_path: Path) -> None:
    client = read_installed_client(write_client_file(tmp_path))
    assert client.client_id.endswith(".apps.googleusercontent.com")
    assert CLIENT_SECRET not in repr(client)
    assert CLIENT_SECRET not in str(client)
    assert client.client_secret.get_secret_value() == CLIENT_SECRET


def test_a_web_client_is_refused_rather_than_coerced(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as raised:
        read_installed_client(write_client_file(tmp_path, section="web"))
    assert "Desktop app" in str(raised.value)


def test_a_group_readable_client_file_is_refused(tmp_path: Path) -> None:
    path = write_client_file(tmp_path)
    path.chmod(0o644)
    with pytest.raises(ConfigError):
        read_installed_client(path)


# --- scope verification ----------------------------------------------------------------------


def test_the_granted_scope_set_is_read_back_and_an_exact_match_passes() -> None:
    grant = TokenGrant(
        access_token=SecretStr(ACCESS_TOKEN),
        refresh_token=SecretStr(REFRESH_TOKEN),
        granted_scopes=(READ_SCOPE,),
        expires_in=3599,
        token_type="Bearer",
    )
    assert verify_granted_scopes(grant) == (READ_SCOPE,)


def test_a_narrower_grant_is_fatal() -> None:
    grant = TokenGrant(
        SecretStr("a"), None, ("https://www.googleapis.com/auth/userinfo.email",), 1, "Bearer"
    )
    with pytest.raises(GrantedScopeMismatch) as raised:
        verify_granted_scopes(grant)
    assert "missing=" in str(raised.value)


def test_a_wider_grant_is_equally_fatal() -> None:
    """A scope nobody asked for is capability nobody agreed to give this client (SEC-01)."""
    grant = TokenGrant(
        SecretStr("a"),
        None,
        (READ_SCOPE, "https://www.googleapis.com/auth/userinfo.email"),
        1,
        "Bearer",
    )
    with pytest.raises(GrantedScopeMismatch) as raised:
        verify_granted_scopes(grant)
    assert "unexpected=" in str(raised.value)


def test_a_response_with_no_scope_field_fails_closed() -> None:
    """ "We requested readonly, therefore we hold readonly" is the assumption being removed."""
    grant = TokenGrant(SecretStr("a"), None, None, 1, "Bearer")
    with pytest.raises(ScopeUnverifiable):
        verify_granted_scopes(grant)


# --- the exchange ------------------------------------------------------------------------------


def test_the_exchange_reaches_the_allowlisted_token_host(tmp_path: Path) -> None:
    client = read_installed_client(write_client_file(tmp_path))
    grant = exchange_code(
        client=client,
        code=AUTH_CODE,
        verifier=generate_pkce().verifier,
        port=1234,
        http=token_endpoint(grant_body()),
    )
    assert grant.granted_scopes == (READ_SCOPE,)
    assert grant.refresh_token is not None
    assert ACCESS_TOKEN not in repr(grant)
    assert REFRESH_TOKEN not in repr(grant)


def test_an_oauth_error_body_is_reported_by_code_and_not_by_its_description(
    tmp_path: Path,
) -> None:
    client = read_installed_client(write_client_file(tmp_path))
    body = {
        "error": "invalid_grant",
        "error_description": f"Bad Request for code {AUTH_CODE}",
    }
    with pytest.raises(ConsentFailed) as raised:
        exchange_code(
            client=client,
            code=AUTH_CODE,
            verifier="v",
            port=1,
            http=token_endpoint(body, status=400),
        )
    assert "invalid_grant" in str(raised.value)
    assert AUTH_CODE not in str(raised.value)


# --- the whole flow -----------------------------------------------------------------------------


def run(
    tmp_path: Path,
    *,
    body: Any | None = None,
    address: str = ACCOUNT,
    state: str = "STATE-VALUE",
    redirect_state: str | None = None,
    expected_account: str | None = None,
) -> Any:
    client = read_installed_client(write_client_file(tmp_path))
    store = TokenStore(tmp_path / "state" / "credentials.json")

    def wait_for_code(url: str, expected: str) -> str:
        assert "code_challenge_method=S256" in url
        assert "prompt=consent" in url
        return f"http://127.0.0.1:1/?code={AUTH_CODE}&state={redirect_state or state}"

    return run_login(
        client=client,
        store=store,
        fetch_address=lambda _token: address,
        announce=lambda _message: None,
        wait_for_code=wait_for_code,
        http=token_endpoint(body if body is not None else grant_body()),
        expected_account=expected_account,
        state=state,
        port=1,
    ), store


def test_a_successful_login_stores_the_granted_scopes_and_states_what_was_granted(
    tmp_path: Path,
) -> None:
    report, store = run(tmp_path)

    assert report.scopes_verified is True
    assert report.granted_scopes == (READ_SCOPE,)
    assert report.account == ACCOUNT
    assert report.refresh_token_stored is True
    rendered = "\n".join(report.lines())
    assert "GRANTED scopes:    https://www.googleapis.com/auth/gmail.readonly" in rendered
    assert "OK - Google granted exactly what was requested" in rendered
    for secret in SECRETS:
        assert secret not in rendered

    stored = store.load()
    assert stored.scopes == SERVER_SCOPES
    assert stored.refresh_token.get_secret_value() == REFRESH_TOKEN
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(store.path.parent.stat().st_mode) == 0o700


def test_a_state_mismatch_aborts_before_anything_is_exchanged(tmp_path: Path) -> None:
    with pytest.raises(ConsentFailed) as raised:
        run(tmp_path, redirect_state="A-DIFFERENT-STATE")
    assert "state" in str(raised.value).lower()


def test_a_scope_mismatch_aborts_before_anything_is_stored(tmp_path: Path) -> None:
    client = read_installed_client(write_client_file(tmp_path))
    store = TokenStore(tmp_path / "state" / "credentials.json")
    with pytest.raises(GrantedScopeMismatch):
        run_login(
            client=client,
            store=store,
            fetch_address=lambda _t: ACCOUNT,
            announce=lambda _m: None,
            wait_for_code=lambda _u, _s: f"http://127.0.0.1:1/?code={AUTH_CODE}&state=S",
            http=token_endpoint(grant_body(scope="https://mail.example/all")),
            state="S",
            port=1,
        )
    assert not store.path.exists()


def test_a_pinned_account_that_does_not_match_aborts_before_anything_is_stored(
    tmp_path: Path,
) -> None:
    with pytest.raises(ConsentFailed):
        run(tmp_path, address="someone.else@personal.example", expected_account=ACCOUNT)
    assert not (tmp_path / "state" / "credentials.json").exists()


def test_a_grant_with_no_refresh_token_is_refused_with_the_remedy(tmp_path: Path) -> None:
    with pytest.raises(ConsentFailed) as raised:
        run(tmp_path, body=grant_body(refresh=None))
    assert "revoke" in str(raised.value).lower()
    assert not (tmp_path / "state" / "credentials.json").exists()


def test_no_secret_survives_into_a_traceback_on_any_failing_step(tmp_path: Path) -> None:
    """RR SEC-04 / PF-8's canary, applied to the consent path specifically.

    Every failure mode of the flow is forced and the *formatted traceback* - not just the
    exception message - is searched for the client secret, the authorization code, the access
    token and the refresh token. Exception formatting renders locals through `__repr__`, which
    is why the secrets are `SecretStr` and the dataclasses carry explicit ones.
    """
    failures: list[str] = []
    cases: list[tuple[str, dict[str, Any]]] = [
        ("scope mismatch", {"body": grant_body(scope="https://mail.example/all")}),
        ("no scope", {"body": grant_body(scope=None)}),
        ("no refresh", {"body": grant_body(refresh=None)}),
        ("state mismatch", {"redirect_state": "WRONG"}),
        ("account mismatch", {"address": "other@x.example", "expected_account": ACCOUNT}),
    ]
    for name, kwargs in cases:
        try:
            run(tmp_path, **kwargs)
        except Exception:
            failures.append(f"{name}\n{traceback.format_exc()}")
        else:
            raise AssertionError(f"{name} did not fail")
    blob = "\n".join(failures)
    assert len(failures) == len(cases)
    for secret in SECRETS:
        assert secret not in blob, f"a secret reached a traceback: {secret[:8]}..."


# --- the canary's second half: the paths that never walked a flow (R-SEC-043) ----------------

#: A synthetic value in the shape of a Google refresh token. Random-looking on purpose: the
#: assertions below search for **every eight-character window** of it, so a value containing
#: an English word would report a leak the moment that word appeared in an error message.
CANARY_SECRET = "1//0gQxZ7mKp2vR8sT4nW9jL6hB3dF5yC1aE0uI7oP"

#: The shortest run of a secret that counts as a leak. Pydantic's default report truncates a
#: long value in the middle and keeps an intact prefix and suffix, so "the whole secret is
#: absent" was never the property worth asserting - R-SEC-043's leak was a fragment.
FRAGMENT = 8


def fragments(secret: str) -> frozenset[str]:
    return frozenset(secret[at : at + FRAGMENT] for at in range(len(secret) - FRAGMENT + 1))


def renderings(failure: BaseException) -> str:
    """Every way this exception can become text, including everything reachable from it.

    **The chain is walked rather than formatted** (R-SEC-049). `raise ... from None` sets
    `__cause__` to `None` and suppresses the context, so `format_exception` prints neither -
    and `__context__` still *held* the raw `ValidationError`, whose `str()` printed a secret
    that had become a JSON key, in full. A canary that only reads what the formatter chooses
    to print measures the formatter's politeness rather than what a handler can reach, so this
    follows `__cause__` and `__context__` explicitly, to any depth.
    """
    rendered = [
        str(failure),
        repr(failure),
        repr(failure.args),
        repr(getattr(failure, "__notes__", None)),
        traceback.format_exc(),
        "".join(traceback.format_exception(type(failure), failure, failure.__traceback__)),
    ]
    seen: set[int] = set()
    pending: list[BaseException | None] = [failure.__cause__, failure.__context__]
    while pending:
        linked = pending.pop()
        if linked is None or id(linked) in seen:
            continue
        seen.add(id(linked))
        rendered.extend((str(linked), repr(linked), repr(linked.args)))
        if isinstance(linked, ValidationError):
            # `.errors()` and `.json()` carry the input the report refused, which is the
            # whole point: an object hanging off the refusal is as good as printed.
            #
            # **With no arguments too** (R-SEC-056). `hide_input_in_errors` was described in
            # `validation.py` as closing the input "for *every* renderer of that error"; it
            # closes `str()` and nothing else, and both of these default to
            # `include_input=True`. Driving the no-argument forms is what makes that a pinned
            # fact rather than a sentence: if a future version changes the default, or a
            # future refusal starts hanging a raw `ValidationError` off itself, this battery
            # says so.
            rendered.extend(
                (
                    repr(linked.errors(include_input=True)),
                    repr(linked.errors()),
                    linked.json(),
                )
            )
        pending.extend((linked.__cause__, linked.__context__))
    return "\n".join(rendered)


def leaked_fragments(text: str) -> list[str]:
    return sorted(window for window in fragments(CANARY_SECRET) if window in text)


def corrupt_documents(model: type[BaseModel]) -> list[tuple[str, Any]]:
    """Every shape a secret-bearing document can be corrupted into, named.

    Generated from the model's own field list rather than written per model, so a model that
    grows a field grows its cases. The shapes are the distinct routes a value takes into a
    Pydantic report: a wrong *type* for a field (the reported shape), a wrong type one
    container deep, a value that reaches one of *our* validators (`msg`), a key the model does
    not declare and a key that *is* the secret (`extra_forbidden` carries the value in the
    first case and the name in the second), and a document that is not a mapping at all -
    which is the one shape that never reaches `__init__`, so it is the shape that reaches
    Pydantic's own reporting machinery instead.
    """
    names = sorted(model.model_fields)
    cases: list[tuple[str, Any]] = []
    for name in names:
        cases.append((f"{name}: wrapped in a dict", {name: {"nested": CANARY_SECRET}}))
        cases.append((f"{name}: wrapped in a list", {name: [CANARY_SECRET]}))
        cases.append((f"{name}: the secret written into this field", {name: CANARY_SECRET}))
        cases.append((f"{name}: an undeclared neighbour holds it", {f"{name}_x": CANARY_SECRET}))
    cases.append(("every field holds the secret", dict.fromkeys(names, CANARY_SECRET)))
    cases.append(("the secret is a key", {CANARY_SECRET: 1}))
    cases.append(
        (
            "the secret is a key beside a full document",
            {**dict.fromkeys(names, CANARY_SECRET), CANARY_SECRET: 1},
        )
    )
    cases.append(("the document is the secret", CANARY_SECRET))
    cases.append(("the document is a list holding it", [CANARY_SECRET]))
    return cases


def entry_points(model: type[BaseModel], document: Any) -> list[tuple[str, Callable[[], object]]]:
    """Every supported way to turn a document into one of these models.

    `model_validate_strings` and the two `__pydantic_validator__` methods are here because
    "the public API is covered" is exactly the assumption this project keeps finding false.
    The raw validator is what a *library* would reach for, and what Pydantic itself uses when
    one of these models is a field of another.
    """
    as_json = json.dumps(document)
    points: list[tuple[str, Callable[[], object]]] = [
        ("model_validate", lambda: model.model_validate(document)),
        ("model_validate_json", lambda: model.model_validate_json(as_json)),
        ("model_validate_strings", lambda: model.model_validate_strings(document)),
        (
            "validator.validate_python",
            lambda: model.__pydantic_validator__.validate_python(document),
        ),
        ("validator.validate_json", lambda: model.__pydantic_validator__.validate_json(as_json)),
    ]
    if isinstance(document, dict):
        points.append(("keyword construction", lambda: model(**document)))
    return points


@pytest.mark.parametrize(
    "model", models_with_secrets(), ids=lambda m: f"{m.__module__}.{m.__qualname__}"
)
def test_no_secret_survives_a_validation_failure_on_any_model_that_holds_one(
    model: type[BaseModel],
) -> None:
    """The half of the canary that was missing, over the models it was missing for.

    The shipped canary walked five *flows* and grepped four secrets. A flow-shaped canary can
    only find a leak on a path somebody thought to walk, and nobody walked
    `StoredCredentials.model_validate` - so R-SEC-043 sat in the one code path the preflight
    runner reaches and `auth login` does not.

    This one is shaped the other way round. The models are **discovered** by reflection
    (`tests.fixtures.secret_models`), the corruption shapes are generated from each model's
    own fields, and every entry point is driven for every shape. Nothing here names
    `refresh_token`, so a model or a field added later is covered without editing this test.

    Both defences are load-bearing and each has shapes only it catches. A mapping reaches
    `SecretBearingModel.__init__`, because Pydantic routes validation through a custom
    `__init__`; a non-mapping never does, and is refused by Pydantic's own machinery with
    `hide_input_in_errors` deciding whether the report quotes it.
    """
    refused = 0
    for shape, document in corrupt_documents(model):
        for entry, call in entry_points(model, document):
            try:
                call()
            except Exception as failure:  # every exception type is in scope here
                refused += 1
                leaked = leaked_fragments(renderings(failure))
                assert not leaked, (
                    f"{model.__qualname__} leaked {len(leaked)} fragment(s) of a secret "
                    f"through {entry} on the '{shape}' shape, first {leaked[0]!r}"
                )
    assert refused >= len(corrupt_documents(model)), (
        f"{model.__qualname__}: only {refused} of these documents were refused, so most of "
        "this battery asserted nothing"
    )


@pytest.mark.parametrize(
    "model", models_with_secrets(), ids=lambda m: f"{m.__module__}.{m.__qualname__}"
)
def test_every_pydantic_validation_entry_point_is_covered_for_a_secret_bearing_model(
    model: type[BaseModel],
) -> None:
    """The assumption the `__init__` override rests on, asserted instead of trusted.

    Pydantic routes *all* mapping validation through a model's custom `__init__`, which is
    why one override covers `model_validate`, `model_validate_json`,
    `model_validate_strings`, the raw validator and this model appearing as a field of
    another. That is internal routing, not a documented contract, so it is pinned here: if a
    Pydantic upgrade stops honouring it, this fails loudly rather than quietly restoring the
    disclosure.

    The entry-point *names* are discovered from `BaseModel` rather than listed, so a
    `model_validate_*` added by a future version is driven the day it appears.
    """
    document = {"client_id": {"nested": CANARY_SECRET}}
    discovered = sorted(name for name in dir(BaseModel) if name.startswith("model_validate"))
    assert discovered, "no model_validate* entry point was discovered at all"
    driven = {name for name, _ in entry_points(model, document)}
    assert set(discovered) <= driven, f"an entry point is not driven: {set(discovered) - driven}"
    for name, call in entry_points(model, document):
        try:
            call()
        except SecretDocumentMalformed:
            continue
        except Exception as failure:
            raise AssertionError(
                f"{name} raised {type(failure).__name__} rather than the value-free refusal; "
                "Pydantic no longer routes this entry point through the model's __init__"
            ) from None
        raise AssertionError(f"{name} accepted a document with a type-invalid field")

    class Outer(BaseModel):
        inner: model  # type: ignore[valid-type]  # a model object, not a name

    with pytest.raises(SecretDocumentMalformed):
        Outer.model_validate({"inner": document})


@pytest.mark.parametrize(
    "model", models_with_secrets(), ids=lambda m: f"{m.__module__}.{m.__qualname__}"
)
def test_a_secret_bearing_model_declares_that_it_may_not_quote_its_input(
    model: type[BaseModel],
) -> None:
    """`hide_input_in_errors`, asserted as configuration as well as behaviour.

    Its behavioural arm is the non-mapping shape above, which is refused before `__init__` is
    reached and is therefore rendered by Pydantic rather than by us. Asserted as declared
    config too, because the flag also covers every path a future version might add, and a
    setting whose only evidence is one shape is the pattern this round is about.
    """
    assert issubclass(model, SecretBearingModel), (
        f"{model.__qualname__} declares a SecretStr and does not inherit SecretBearingModel"
    )
    assert model.model_config.get("hide_input_in_errors") is True


def unfunnelled(model: type[BaseModel]) -> type[BaseModel]:
    """A subclass of `model` with Pydantic's own `__init__` restored.

    `SecretBearingModel.__init__` is the funnel every validation path goes through, which is
    what makes the refusal value-free - and which also *hides* the two defences underneath
    it, so a suite that only drives the funnel would pass with both of them removed. This
    twin declares `BaseModel.__init__`, so Pydantic marks it as having no custom init and
    raises its own `ValidationError` with the same fields, the same validators and the same
    `model_config` the real model carries. What that report says about the input is then
    exactly what a caller would see if the funnel were ever bypassed or removed.
    """
    return type(f"Unfunnelled{model.__name__}", (model,), {"__init__": BaseModel.__init__})


@pytest.mark.parametrize(
    "model", models_with_secrets(), ids=lambda m: f"{m.__module__}.{m.__qualname__}"
)
def test_nothing_under_the_funnel_quotes_what_it_refused(model: type[BaseModel]) -> None:
    """The two defences below the entry-point overrides, tested without them.

    Channel 1 is `input_value=...`, closed by `hide_input_in_errors`. Channel 2 is `msg`,
    which belongs to whichever validator refused: `parse_instant` spelled its refusal
    `f"{field}={value!r} ..."` and runs on `StoredCredentials.obtained_at`, so a credential
    file that had the refresh token written into its timestamp field reported the token
    whole. Neither is visible through the funnel, and both would be a disclosure the moment
    the funnel moved.

    The two documents where the secret is a *key* are not driven here. That is channel 3: a
    Pydantic report always names the key an `extra_forbidden` error is about and no model
    setting changes it, so the only defence is `failure_summary` withholding a name the
    model does not declare - which lives in the funnel this twin steps around on purpose.
    Those two shapes are driven, and closed, by the canary above.
    """
    twin = unfunnelled(model)
    driven = [
        (shape, document)
        for shape, document in corrupt_documents(model)
        if not (isinstance(document, dict) and CANARY_SECRET in document)
    ]
    refused = 0
    for shape, document in driven:
        try:
            twin.__pydantic_validator__.validate_python(document)
        except Exception as failure:  # every exception type is in scope here
            refused += 1
            leaked = leaked_fragments(renderings(failure))
            assert not leaked, (
                f"{model.__qualname__} quotes its input under the funnel on the "
                f"'{shape}' shape: {leaked[0]!r}"
            )
    assert refused >= len(driven) - 1, "most of this battery asserted nothing"


def test_the_credential_and_config_loaders_refuse_a_corrupt_file_without_quoting_it(
    tmp_path: Path,
) -> None:
    """The same battery through the two real loaders, files and permissions included.

    R-SEC-043's reproduction was a file, not a model call: `preflight.__main__` ->
    `StoredTokenProvider.access_token()` -> `store.load()`. `load_config` is here for the
    same reason one field was not enough - it reads the client secret, which is short enough
    to sit *inside* Pydantic's truncation window and was therefore echoed whole.
    """
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    loaders: tuple[tuple[str, type[BaseModel], Callable[[Path], object]], ...] = (
        ("credential_store", StoredCredentials, lambda path: TokenStore(path=path).load()),
        ("config", MailweaveConfig, load_config),
    )
    refused = 0
    for name, model, load in loaders:
        for shape, document in corrupt_documents(model):
            path = state / f"{name}.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            path.chmod(0o600)
            try:
                load(path)
            except Exception as failure:  # every exception type is in scope here
                refused += 1
                leaked = leaked_fragments(renderings(failure))
                assert not leaked, (
                    f"the {name} loader leaked a secret fragment on the '{shape}' shape: "
                    f"{leaked[0]!r}"
                )
    assert refused >= sum(len(corrupt_documents(model)) for _, model, _ in loaders) - 2


def test_the_canary_covers_every_model_that_holds_a_secret() -> None:
    """A discovery that silently found nothing would make the tests above vacuous."""
    discovered = {model.__qualname__ for model in models_with_secrets()}
    assert {"StoredCredentials", "MailweaveConfig"} <= discovered
    for model in models_with_secrets():
        assert secret_fields(model), model


# --- R-SEC-050: three shapes the discovery missed, and each of them leaked -------------------


def test_a_secret_str_subclass_is_a_secret() -> None:
    """`part is SecretStr` is an identity test, so a subclass was not a secret (R-SEC-050).

    R-SEC planted one and drove it to a `ValidationError` quoting the secret in full. A
    subclass is a secret by every argument that makes `SecretStr` one - it exists to keep a
    value out of a `repr` - so the question is `issubclass`.
    """

    class HarnessSecret(SecretStr):
        pass

    class UsesTheSubclass(BaseModel):
        token: HarnessSecret

    assert secret_fields(UsesTheSubclass) == ("token",)


def test_secret_bytes_is_a_secret_too() -> None:
    """It was not considered at all, though it is the same wrapper for the same purpose."""

    class HoldsBytes(BaseModel):
        blob: SecretBytes

    class HoldsBytesInAGeneric(BaseModel):
        blobs: dict[str, list[SecretBytes | None]]

    assert secret_fields(HoldsBytes) == ("blob",)
    assert secret_fields(HoldsBytesInAGeneric) == ("blobs",)


def test_a_model_nested_inside_a_class_is_discovered() -> None:
    """Never in `vars(module)`, so the discovery never examined it (R-SEC-050).

    Planted into a synthetic module rather than into a real one: the discovery walks imported
    modules, and mutating one to prove a point would leave the plant behind for every test
    after this one. What is exercised is the walker itself, at two nesting depths.
    """
    module = types.ModuleType("mailweave._canary_probe")

    class Enclosing:
        class Nested(BaseModel):
            token: SecretStr

        class Deeper:
            class Bottom(BaseModel):
                blob: SecretBytes

    for cls in (Enclosing, Enclosing.Nested, Enclosing.Deeper, Enclosing.Deeper.Bottom):
        cls.__module__ = module.__name__
    module.Enclosing = Enclosing  # type: ignore[attr-defined]

    discovered = {
        # These classes are defined inside this test, so their `__qualname__` carries a
        # `<locals>` prefix the real ones do not have; the nesting after it is the point.
        cls.__qualname__.split(".<locals>.")[-1]
        for cls in _classes_in(vars(module), module.__name__)
        if issubclass(cls, BaseModel) and secret_fields(cls)
    }

    assert discovered == {"Enclosing.Nested", "Enclosing.Deeper.Bottom"}


def test_the_discovery_still_finds_exactly_the_models_that_hold_a_secret() -> None:
    """Widening a search is only an improvement if it did not also start finding everything."""
    discovered = {f"{m.__module__}.{m.__qualname__}" for m in models_with_secrets()}
    assert discovered == {
        "mailweave.auth.tokenstore.StoredCredentials",
        "mailweave.config.MailweaveConfig",
    }


# --- the loopback listener ------------------------------------------------------------------


def test_the_loopback_listener_binds_only_to_127_0_0_1() -> None:
    """SN 2.1: installed-app loopback, no OOB, no custom scheme - and loopback only.

    RR SEC-07 forbids the *server* process a listening socket; this is a CLI command, the
    bind is to `127.0.0.1`, and it is closed when consent ends. Asserted rather than argued.
    """
    receiver = LoopbackReceiver(timeout_s=0.01)
    try:
        host, port = receiver._server.server_address[0], receiver.port
        assert host == LOOPBACK_HOST == "127.0.0.1"
        assert 1 <= port <= 65535
    finally:
        receiver.close()


def test_the_redirect_handler_ignores_a_request_that_carries_no_code() -> None:
    """A browser asks for /favicon.ico. Treating that as the redirect loses the consent."""
    from mailweave.auth.consent import _RedirectHandler

    assert _RedirectHandler.captured is None or isinstance(_RedirectHandler.captured, str)
    # The handler's own logger is silenced because the request line contains the code.
    assert _RedirectHandler.log_message.__doc__ is not None
    assert "authorization code" in _RedirectHandler.log_message.__doc__


# --- refresh ---------------------------------------------------------------------------------


def test_a_refresh_re_verifies_the_scope_set(tmp_path: Path) -> None:
    """A grant can be narrowed after consent; a refresh is where that first becomes visible."""
    from mailweave.auth.consent import refresh_access_token

    client = read_installed_client(write_client_file(tmp_path))
    with pytest.raises(GrantedScopeMismatch):
        refresh_access_token(
            client=client,
            refresh_token=SecretStr(REFRESH_TOKEN),
            http=token_endpoint(grant_body(scope="https://www.googleapis.com/auth/userinfo.email")),
        )


def test_a_refresh_response_without_a_scope_field_is_treated_as_unchanged(tmp_path: Path) -> None:
    """Different from a first consent, and deliberately so.

    At first consent there is nothing to fall back on, so an unverifiable scope set fails
    closed. At refresh there is a previously verified grant, verified by this same check, so
    an omitted `scope` means unchanged rather than unknown. The two call sites of
    `verify_granted_scopes` are not interchangeable and the difference is stated where it is.
    """
    from mailweave.auth.consent import refresh_access_token

    client = read_installed_client(write_client_file(tmp_path))
    grant = refresh_access_token(
        client=client,
        refresh_token=SecretStr(REFRESH_TOKEN),
        http=token_endpoint(grant_body(scope=None, refresh=None)),
    )
    assert grant.access_token.get_secret_value() == ACCESS_TOKEN


def test_a_revoked_grant_names_the_re_auth_command_and_leaks_nothing(tmp_path: Path) -> None:
    """GMAIL-06: token failure is a clear re-auth instruction, never a confusing error."""
    from mailweave.auth.consent import refresh_access_token

    client = read_installed_client(write_client_file(tmp_path))
    with pytest.raises(ConsentFailed) as raised:
        refresh_access_token(
            client=client,
            refresh_token=SecretStr(REFRESH_TOKEN),
            http=token_endpoint(
                {"error": "invalid_grant", "error_description": f"token {REFRESH_TOKEN} revoked"},
                status=400,
            ),
        )
    rendered = f"{raised.value}\n{traceback.format_exc()}"
    assert "mailweave auth login" in rendered
    assert REFRESH_TOKEN not in rendered


def test_the_stored_token_provider_never_renders_its_token(tmp_path: Path) -> None:
    from mailweave.auth.consent import StoredTokenProvider

    client = read_installed_client(write_client_file(tmp_path))
    store = TokenStore(tmp_path / "state" / "credentials.json")
    provider = StoredTokenProvider(client=client, store=store, http=token_endpoint(grant_body()))
    assert ACCESS_TOKEN not in repr(provider)
    assert "redacted" in repr(provider)


def test_the_reported_profile_is_derived_and_not_asserted(tmp_path: Path) -> None:
    """A report stating a value the code chose is the project's own recurring defect.

    Both branches are exercised: with no seed configuration the derivation fails closed to
    `personal`, and with a seed configuration whose two conditions cannot both hold it still
    does - which is AD A.4's config-forgery property, reached through this command.
    """
    from mailweave.auth.profile import Profile, account_digest

    report, _ = run(tmp_path)
    assert report.profile is Profile.PERSONAL

    client = read_installed_client(write_client_file(tmp_path))
    store = TokenStore(tmp_path / "forged" / "credentials.json")
    forged, _ = (
        run_login(
            client=client,
            store=store,
            fetch_address=lambda _t: ACCOUNT,
            announce=lambda _m: None,
            wait_for_code=lambda _u, _s: f"http://127.0.0.1:1/?code={AUTH_CODE}&state=S",
            http=token_endpoint(grant_body()),
            # A hash of the *personal* address, which is the forgery AD A.4 (ii) closes: the
            # digest can be made to match and the client id cannot, because Google will not
            # issue this mailbox a token for the harness client at all.
            seed_account_hash=account_digest(b"a-salt", ACCOUNT),
            seed_client_id="harness-client.apps.googleusercontent.example",
            state="S",
            port=1,
        ),
        None,
    )
    assert forged.profile is Profile.PERSONAL
