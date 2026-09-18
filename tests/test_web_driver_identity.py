"""The door: sign-in, enrolment, a credential per session, and a deployment that
has none of it and notices nothing.

Driven through `AppTest` because *when* things are drawn is a whole-script
question (`.claude/rules/streamlit-driver.md`): "offered sign-in and nothing
else" is a claim about what the page did not draw, and no unit below the script
can see that. The unconfigured test runs first and is the regression guard for
every other web test in this suite -- they all run with no `[auth]` in secrets.

What is stubbed, and why it is honest to: `web.signed_in_claims` stands in for
`st.user`, which `AppTest` fixes to a test address with no `is_logged_in`. The
fixture asserts a verified address unless a test says otherwise, which is what
keeps the admitted population admitted while the refused one grows;
`web.accounts.lookup` stands in for the database; `web.AskAgent` is wrapped to
record the credential each agent was built with. `web.admit` and `web.agent_for`
themselves run for real, which is the point.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from conftest import FIXTURE, agent_with, ask_question
from streamlit.testing.v1 import AppTest

from agent_doubles import says, scripted
from scinumbers_ask import allowance, messages, trace, web
from scinumbers_ask.accounts import Account, EnrolmentUnavailable
from scinumbers_ask.permissions import Identity, Role

APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
TIMEOUT = 30

TESTER = Account(email="tester@example.org", role=Role.SCIENTIST, openrouter_key="sk-tester")
KEYLESS = Account(email="keyless@example.org", role=Role.STUDENT, openrouter_key=None)
DEV = Account(email="dev@example.org", role=Role.DEV, openrouter_key="sk-dev")


class _Caught(logging.Handler):
    """Every trail record, after the stamp -- what the durable sink would see."""

    def __init__(self):
        super().__init__(logging.INFO)
        self.records: list[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)

    def events(self) -> list[str]:
        return [r.getMessage() for r in self.records]

    def identities(self) -> set[tuple]:
        return {
            (getattr(r, "user_email", None), getattr(r, "user_role", None)) for r in self.records
        }


@pytest.fixture
def caught():
    logger = logging.getLogger(trace.LOGGER_NAME)
    trace.configure()
    web.install_identity_stamp()  # what `resources` does, which the tests replace
    handler = _Caught()
    logger.addHandler(handler)
    yield handler
    logger.removeHandler(handler)
    for f in [f for f in logger.filters if isinstance(f, web.IdentityStamp)]:
        logger.removeFilter(f)
    web.IDENTITIES.clear()


@pytest.fixture
def page(monkeypatch, repo, config, tmp_path):
    """Build the real script with the door set as a test chooses."""
    built: list[str | None] = []
    monkeypatch.setattr(web, "resources", lambda corpus=None: repo)
    monkeypatch.setenv("SCINUMBERS_CORPUS", FIXTURE)
    monkeypatch.setenv("SCINUMBERS_CHECKPOINTS", str(tmp_path / "c.sqlite"))
    # Something, so `admit` reaches `lookup` rather than concluding "no database".
    monkeypatch.setattr(web, "trail_destination", lambda: object())

    def make(
        *,
        auth: bool,
        email: str | None = None,
        enrolled: dict[str, Account] | None = None,
        unavailable: bool = False,
        answers=("an answer",),
        claims: dict | None = None,
        auth_section: dict | None = None,
    ) -> AppTest:
        agent = agent_with(repo, config, tmp_path, scripted(*(says(a) for a in answers)))

        def building(repo_, config_, path, model=None, api_key=None, **rest):
            # `**rest` so a new per-reader fact on the constructor (the budget
            # scope was the first) shows up as a changed assertion rather than a
            # blank page from a TypeError raised inside the script.
            built.append(api_key)
            building.rest = rest
            return agent

        monkeypatch.setattr(web, "AskAgent", building)
        asserted = (
            None
            if email is None and claims is None
            else {"email": email, "email_verified": True, **(claims or {})}
        )
        monkeypatch.setattr(web, "signed_in_claims", lambda: asserted)

        def lookup(engine, who, **kwargs):
            if unavailable:
                raise EnrolmentUnavailable("relation does not exist")
            return (enrolled or {}).get(who)

        monkeypatch.setattr(web.accounts, "lookup", lookup)
        at = AppTest.from_file(APP, default_timeout=TIMEOUT)
        if auth:
            at.secrets["auth"] = auth_section or {"client_id": "test-client"}
        return at

    make.built = built  # type: ignore[attr-defined]
    return make


_ask = ask_question


def _sidebar_text(at: AppTest) -> str:
    return " ".join(c.value for c in at.sidebar.caption)


# --- 4.6: no `[auth]` -- everything as before -----------------------------------


def test_with_no_identity_configured_a_question_is_answered_without_signing_in(page, caught):
    """The regression guard for every existing web test, which all run this way."""
    at = page(auth=False).run()
    assert at.chat_input, "the input must be there with no sign-in"
    assert not at.button, "no sign-in button, no sign-out button"
    at = _ask(at, "how many?")
    assert not at.exception
    assert any("an answer" in m.value for m in at.markdown)
    assert "question.asked" in caught.events()
    # Records carry no account -- absent, not empty.
    assert caught.identities() == {(None, None)}
    assert page.built == [None], "the environment's key, exactly as before"


def test_with_no_identity_configured_the_page_says_so(page):
    at = page(auth=False).run()
    assert messages.NO_SIGN_IN_CONFIGURED in _sidebar_text(at)
    assert web.RECORDS_NOTE in _sidebar_text(at)


# --- 4.7: `[auth]` configured -------------------------------------------------------


def test_a_visitor_who_is_not_signed_in_is_offered_sign_in_and_nothing_else(page, caught):
    at = page(auth=True, email=None).run()
    assert not at.exception
    assert not at.chat_input, "a question could be asked"
    # The title and its style rule are the page saying what it is, and they are
    # drawn before the door decides anything. What must not be here is the
    # conversation: a visitor who has not signed in sees no question, no answer
    # and no record of either.
    assert not at.chat_message, "a conversation was drawn"
    drawn = [m.value for m in at.markdown]
    assert all("bn-title" in text or "<style>" in text for text in drawn), drawn
    assert [b.label for b in at.button] == ["Sign in with Google"]
    assert caught.events() == [], "a record was written for a visitor who asked nothing"


# --- more than one way in ---------------------------------------------------------


def test_providers_reads_the_default_and_every_sub_table(monkeypatch):
    """`[auth]` holds the shared settings, the default provider's credentials, and
    a sub-table per named provider. Only the sub-tables are mappings, which is
    what separates them without naming Streamlit's own keys here."""
    shared = {"redirect_uri": "http://localhost:8501/oauth2callback", "cookie_secret": "s"}
    cases = {
        "google only": ({**shared, "client_id": "g"}, ["default"]),
        "google and auth0": (
            {**shared, "client_id": "g", "auth0": {"client_id": "a"}},
            ["default", "auth0"],
        ),
        "auth0 only": ({**shared, "auth0": {"client_id": "a"}}, ["auth0"]),
        "shared settings alone": (shared, []),
        # Two sub-tables, because with one the docstring's "in the order secrets
        # lists them" has no negative case at all. **Both orderings, and that is
        # the point**: with only the first of these, reverse-sorting the names
        # still passed -- `zeta` before `auth0` is what sorting backwards
        # produces anyway, so the case varied the outcome without varying what
        # the rule reads. A pair no sort can satisfy is what pins the claim. The
        # order is what the buttons appear in.
        "three providers keep their order": (
            {**shared, "client_id": "g", "zeta": {"client_id": "z"}, "auth0": {"client_id": "a"}},
            ["default", "zeta", "auth0"],
        ),
        # `client_kwargs` is a documented mapping under `[auth]`, not a
        # provider: the installed Streamlit lifts it into the default provider's
        # own section (`auth_util.generate_default_provider_section`). A "is it
        # a mapping" rule offered it as a third way in, and clicking that button
        # calls `st.login("client_kwargs")`, which cannot resolve. The
        # discriminator is `client_id`, which is one of the three keys Streamlit
        # itself requires of a provider section.
        "client_kwargs is not a way in": (
            {
                **shared,
                "client_id": "g",
                "client_kwargs": {"prompt": "login"},
                "auth0": {"client_id": "a"},
            },
            ["default", "auth0"],
        ),
        "a mapping with no client_id is not a provider": (
            {**shared, "client_id": "g", "expose_tokens": {"id": True}},
            ["default"],
        ),
        # Offered twice, the two buttons share the key `sign-in-default` and
        # Streamlit raises `StreamlitDuplicateElementKey` -- which takes the
        # whole door down rather than the one button.
        "a sub-table called default is not a second default": (
            {**shared, "client_id": "g", "default": {"client_id": "d"}},
            ["default"],
        ),
        "and the other way round": (
            {**shared, "client_id": "g", "auth0": {"client_id": "a"}, "zeta": {"client_id": "z"}},
            ["default", "auth0", "zeta"],
        ),
    }
    for name, (section, expected) in cases.items():
        monkeypatch.setattr(web.st, "secrets", {"auth": section})
        assert web.providers() == expected, name


def test_providers_is_empty_with_no_auth_section(monkeypatch):
    """The type Streamlit actually raises for a missing secrets file, because
    `_is_not_configured` matches by type and a double raising something else
    would pass while proving nothing about the real path."""
    from streamlit.errors import StreamlitSecretNotFoundError

    class NoSecrets(dict):
        def __getitem__(self, key):
            raise StreamlitSecretNotFoundError("No secrets files found")

    monkeypatch.setattr(web.st, "secrets", NoSecrets())
    assert web.providers() == []

    class Broken(dict):
        def __getitem__(self, key):
            raise RuntimeError("a broken secrets file is not an absent one")

    monkeypatch.setattr(web.st, "secrets", Broken())
    with pytest.raises(RuntimeError):
        web.providers()

    # A secrets file that exists and simply has no `[auth]`. Streamlit raises a
    # plain `KeyError` here, which is not one of its own error types, so
    # `_is_not_configured` does not match it -- and must not, since widening that
    # predicate would make it answer "not configured" to any missing key.
    class NoAuthSection(dict):
        def __getitem__(self, key):
            raise KeyError(key)

    monkeypatch.setattr(web.st, "secrets", NoAuthSection())
    assert web.providers() == []

    # `[auth] = "something"` rather than a section. Streamlit would not usually
    # produce it, but the rule is "a mapping or nothing" and an unexecuted branch
    # is a branch nobody has read.
    monkeypatch.setattr(web.st, "secrets", {"auth": "not a section"})
    assert web.providers() == []


def test_each_configured_provider_gets_its_own_button(page):
    at = page(
        auth=True,
        email=None,
        auth_section={"client_id": "g", "auth0": {"client_id": "a"}},
    ).run()
    assert [b.label for b in at.button] == ["Sign in with Google", "Sign in with email"]


def test_the_default_provider_is_signed_in_to_with_no_argument(page, monkeypatch):
    """`st.login()` and `st.login("default")` are different calls: the
    no-argument form means the credentials in `[auth]` itself, and Streamlit
    resolves the name "default" against a section that need not exist. Forcing
    either form for both providers passed every test until this one, so the
    comment in `draw_closed_door` asserting the distinction had nothing behind
    it."""
    asked: list = []
    monkeypatch.setattr(web.st, "login", lambda *args: asked.append(args))
    at = page(
        auth=True,
        email=None,
        auth_section={"client_id": "g", "auth0": {"client_id": "a"}},
    ).run()
    at.button[0].click().run()
    assert asked == [()], "the default provider was named, and it must not be"
    at.button[1].click().run()
    assert asked == [(), ("auth0",)], "a named provider was not named"


def test_auth_with_no_credentials_still_offers_the_default_button(page):
    """A misconfigured `[auth]` has to be diagnosable. The button calls
    `st.login()`, which raises Streamlit's own "credentials are missing" error
    naming the keys; drawing nothing would leave the operator a sentence, no
    control and no clue. The visitor is stuck either way, so the tie goes to the
    person who can fix it."""
    at = page(auth=True, email=None, auth_section={"redirect_uri": "x", "cookie_secret": "y"}).run()
    assert [b.label for b in at.button] == ["Sign in with Google"]


def test_a_provider_with_no_label_still_gets_a_button(page):
    """An operator adding `[auth.okta]` meets a plain button, not a KeyError."""
    at = page(auth=True, email=None, auth_section={"okta": {"client_id": "o"}}).run()
    assert [b.label for b in at.button] == ["Sign in with okta"]


# --- a verified address, or none ---------------------------------------------------


def test_address_verified_reads_the_claim_and_refuses_its_absence():
    """The negatives vary what the rule actually reads -- the claim's value and
    whether it is there at all -- not merely the outcome. `1` is here because it
    equals `True` in Python: a truthy check would admit anything a provider sent.
    """
    assert web.address_verified({"email_verified": True})
    assert web.address_verified({"email_verified": "true"})
    for value in (False, "false", 1, 0, None, "", "True", "yes"):
        assert not web.address_verified({"email_verified": value}), value
    assert not web.address_verified({}), "a provider that says nothing is refused"


def test_an_unverified_address_is_refused_with_its_own_sentence(page, caught):
    at = page(
        auth=True,
        email="unverified@example.org",
        enrolled={"unverified@example.org": TESTER},
        claims={"email_verified": False},
    ).run()
    assert not at.chat_input, "a question could be asked"
    shown = [e.value for e in at.error]
    assert messages.UNVERIFIED in shown
    assert messages.NOT_ENROLLED not in shown, "the two sentences send readers to different places"
    (refused,) = [r for r in caught.records if r.getMessage() == "signin.unverified"]
    assert refused.fields["email"] == "unverified@example.org"
    assert web.IDENTITIES == {}, "a refused account must not enter the registry"
    # This door's sentence tells the reader to sign in again, which they cannot
    # do while signed in as an unverified account. The `NO_CREDENTIAL` door has
    # carried this assertion since it existed; this one did not until a verifier
    # deleted the button and nothing failed.
    assert "Sign out" in [b.label for b in at.button], "no way out of the closed door"


def test_an_unverified_address_is_never_looked_up(monkeypatch):
    """The check is before the lookup, so an unverified address never reaches the
    accounts table -- and an enrolled tester cannot be impersonated by registering
    their address at a provider with open sign-up."""
    looked_up: list[str] = []
    _configured(monkeypatch, TESTER.email, email_verified=False)
    monkeypatch.setattr(web.accounts, "lookup", lambda e, who, **k: looked_up.append(who) or TESTER)
    assert web.admit({}, object(), "s1").door is web.Door.UNVERIFIED
    assert looked_up == []


def test_the_unverified_refusal_is_recorded_once_and_not_once_per_rerun(monkeypatch, caught):
    """The decision is re-made on every rerun; the record is not. Every other
    refusal is written once per account per session because its admission is
    cached, and this one would otherwise charge the trail an insert per click --
    the only door that does."""
    state: dict = {}
    _configured(monkeypatch, TESTER.email, email_verified=False)
    monkeypatch.setattr(web.accounts, "lookup", lambda e, who, **k: TESTER)
    for _ in range(4):
        assert web.admit(state, object(), "s1").door is web.Door.UNVERIFIED
    assert [r.getMessage() for r in caught.records].count("signin.unverified") == 1
    # A different unverified account on the same tab is its own refusal.
    _configured(monkeypatch, DEV.email, email_verified=False)
    assert web.admit(state, object(), "s1").door is web.Door.UNVERIFIED
    assert [r.getMessage() for r in caught.records].count("signin.unverified") == 2


def test_the_unverified_door_is_not_held_across_reruns(monkeypatch):
    """`end_session` does not clear the held admission, so a cached refusal would
    outlive the reader signing out, verifying and signing back in on the same tab
    -- which is the sequence the sentence asks them to perform."""
    state: dict = {}
    _configured(monkeypatch, TESTER.email, email_verified=False)
    monkeypatch.setattr(web.accounts, "lookup", lambda e, who, **k: TESTER)
    assert web.admit(state, object(), "s1").door is web.Door.UNVERIFIED
    _configured(monkeypatch, TESTER.email)
    assert web.admit(state, object(), "s1").door is web.Door.OPEN


def test_the_same_address_through_a_second_provider_is_the_same_reader(monkeypatch):
    """The address is the identity. A tester who used Google yesterday and email
    today keeps their role and their conversation: the provider is not part of
    the key and is not stamped on anything."""
    monkeypatch.setattr(web.accounts, "lookup", lambda e, who, **k: TESTER)
    seen = []
    for provider in ("google-oauth2", "auth0"):
        _configured(monkeypatch, TESTER.email, provider=provider)
        admission = web.admit({}, object(), "s1")
        assert admission.door is web.Door.OPEN
        seen.append((admission.account, web.effective_session(admission, "s1")))
    assert seen[0] == seen[1], "a second provider must not be a second account"


def test_which_provider_was_used_is_not_recorded_anywhere(page, caught):
    """The claim task 1.6 made and did not check. It passes vacuously today --
    nothing in `web.py` reads the `provider` claim at all -- and that is the
    point of writing it down: the day someone stamps it to "help with debugging",
    this is what says the address is the identity and the route to it is not
    (ADR-0880). A guard, declared as a guard."""
    at = page(
        auth=True,
        email=TESTER.email,
        enrolled={TESTER.email: TESTER},
        claims={"provider": "auth0", "sub": "auth0|abc123"},
    ).run()
    at = _ask(at, "how many?")
    assert not at.exception
    assert caught.records, "nothing was recorded, so this asserts nothing"
    for record in caught.records:
        for field in ("provider", "sub"):
            assert not getattr(record, field, None), field
            assert field not in getattr(record, "fields", {}), field


def test_a_signed_in_account_that_is_not_enrolled_is_refused_and_recorded(page, caught):
    at = page(auth=True, email="stranger@example.org", enrolled={}).run()
    assert not at.chat_input
    assert messages.NOT_ENROLLED in [e.value for e in at.error]
    (refused,) = [r for r in caught.records if r.getMessage() == "signin.refused"]
    assert refused.fields["email"] == "stranger@example.org"
    assert not getattr(refused, "user_email", None), "refused, so no identity to stamp"
    assert web.IDENTITIES == {}, "a refused account must not enter the registry"


def test_a_refusal_is_recorded_once_per_session_not_once_per_rerun(page, caught):
    at = page(auth=True, email="stranger@example.org", enrolled={}).run()
    at.run()
    at.run()
    assert caught.events().count("signin.refused") == 1


def test_an_enrolled_account_is_admitted_and_its_records_carry_who_and_as_what(page, caught):
    at = page(auth=True, email=TESTER.email, enrolled={TESTER.email: TESTER}).run()
    assert at.chat_input
    at = _ask(at, "how many?")
    assert any("an answer" in m.value for m in at.markdown)
    assert caught.identities() == {(TESTER.email, "scientist")}
    assert page.built == ["sk-tester"], "funded by the account's own credential"


def test_the_sidebar_says_who_is_signed_in_and_offers_sign_out(page):
    at = page(auth=True, email=TESTER.email, enrolled={TESTER.email: TESTER}).run()
    assert messages.SIGNED_IN_AS.format(email=TESTER.email, role="scientist") in _sidebar_text(at)
    assert "Signed in as" not in _sidebar_text(at), "the sign-out button beside it says that"
    assert "Sign out" in [b.label for b in at.sidebar.button]
    assert web.RECORDS_NOTE in _sidebar_text(at)


def _elements(block):
    """A block's children, which AppTest keys by index rather than listing."""
    children = getattr(block, "children", None) or {}
    return list(children.values() if isinstance(children, dict) else children)


def _identity_row(at: AppTest):
    """The container holding the name and the button, or None if they are not in
    one -- which is the whole claim, so it is read from the tree and not from a
    string."""
    for block in _elements(at.sidebar):
        inside = _elements(block)
        named = any("@" in str(getattr(e, "value", "")) for e in inside)
        signs_out = any(getattr(e, "label", "") == "Sign out" for e in inside)
        if named and signs_out:
            return block
    return None


def test_the_sign_out_button_shares_a_row_with_the_name_it_belongs_to(page):
    """Not "both appear somewhere in the panel", which was already true when they
    were stacked. The claim is the layout, so it is read off the element tree."""
    at = page(auth=True, email=TESTER.email, enrolled={TESTER.email: TESTER}).run()
    row = _identity_row(at)
    assert row is not None, "the name and its button share one container"
    assert row.type == "flex_container", (
        "a horizontal container, not columns: columns divide the panel by "
        "proportion, which put the button far from the name on a wide panel and "
        "squeezed it on a narrow one"
    )


def test_the_panel_keeps_the_identity_row_from_being_squeezed(page):
    """The reader can drag the panel narrower than its contents can survive, and a
    flex item can be squeezed below its own content. Neither is visible to a test
    that only reads elements, so the rules themselves are asserted."""
    at = page(auth=True, email=TESTER.email, enrolled={TESTER.email: TESTER}).run()
    css = "".join(m.value for m in at.sidebar.markdown if "<style>" in str(m.value))
    assert f"min-width: {web.SIDEBAR_MIN_WIDTH_PX}px" in css
    assert f".st-key-{web.SIGN_OUT_KEY} {{ flex: 0 0 auto; }}" in css
    assert f".st-key-{web.SIGN_OUT_KEY} button {{ white-space: nowrap; }}" in css


def test_the_sign_out_button_looks_like_a_button(page):
    """Tertiary was tried for one release: no border, no fill, and a reader saw a
    stray line of text where the way out should be."""
    at = page(auth=True, email=TESTER.email, enrolled={TESTER.email: TESTER}).run()
    out = next(b for b in at.sidebar.button if b.label == "Sign out")
    assert out.proto.type != "tertiary"


def test_the_role_sits_under_the_email_rather_than_beside_it(page):
    at = page(auth=True, email=TESTER.email, enrolled={TESTER.email: TESTER}).run()
    named = next(c for c in at.sidebar.caption if TESTER.email in c.value)
    assert named.value.endswith("\n(scientist)"), "a line break, not a parenthesis on the end"


def test_the_data_credit_is_one_click_from_every_page_view(page):
    """Present on every view and not spending a standing line on itself. Asserted
    on the popover's own content, because a citation drawn where nobody can reach
    it is the failure this guards."""
    at = page(auth=True, email=TESTER.email, enrolled={TESTER.email: TESTER}).run()
    popovers = [b for b in _elements(at.sidebar) if getattr(b, "type", "") == "popover"]
    assert [p.proto.popover.label for p in popovers] == [web.DATA_CREDIT_LABEL]
    assert web.DATA_CREDIT.startswith(web.DATA_CREDIT_LABEL.rstrip(")")), (
        "the button says whose data this is, not a generic word for it"
    )
    inside = [str(getattr(e, "value", "")) for pop in popovers for e in _elements(pop)]
    assert any("BioNumbers (Milo et al." in text for text in inside)
    beside = [str(getattr(e, "value", "")) for e in _elements(at.sidebar)]
    assert not any("BioNumbers (Milo" in text for text in beside), "behind it, not beside it"


def test_the_page_says_whose_money_the_questions_cost(page):
    """On the page itself rather than the side panel, which Streamlit collapses on
    a phone -- and on every deployment, not only the hosted one. A sentence that
    appears depending on which branch built the page is drift, not configuration.
    """
    at = page(auth=True, email=TESTER.email, enrolled={TESTER.email: TESTER}).run()
    assert any(web.BUDGET_NOTE in c.value for c in at.main.caption)


def test_the_budget_note_is_there_without_sign_in_too(page):
    """The deny case varies what the old arrangement keyed on -- the deployment,
    which sign-in configuration stands for here -- rather than the wording."""
    at = page(auth=False).run()
    assert any(web.BUDGET_NOTE in c.value for c in at.main.caption)


def test_the_mark_is_drawn_inside_the_title_before_the_words(page):
    """Inside the heading, not above it: the mark is part of what the page calls
    itself. Inlined rather than linked, because an `<img>` is a document of its own
    and `currentColor` in it would resolve against the image instead of the page --
    which is how a near-black mark becomes invisible to a reader on a dark theme.
    """
    at = page(auth=True, email=TESTER.email, enrolled={TESTER.email: TESTER}).run()
    title = next(m.value for m in at.markdown if "<h1" in m.value)
    assert title.index("<svg") < title.index(web.TITLE), "the mark comes before the words"
    assert "currentColor" in title, "the strokes take the reader's own text colour"
    assert "#15181C" not in title, "and none of them is left pinned to one theme"
    assert "c2pa:manifest" not in title, "the provenance manifest is not re-sent per rerun"


def test_a_missing_mark_costs_the_mark_and_nothing_else(page, monkeypatch, tmp_path):
    """The page is the product and the logo is decoration. An asset that did not
    survive a deployment must not take the title with it."""
    monkeypatch.setattr(web, "LOGO", tmp_path / "absent.svg")
    web.logo_svg.cache_clear()
    try:
        at = page(auth=True, email=TESTER.email, enrolled={TESTER.email: TESTER}).run()
        assert not at.exception
        assert [t.value for t in at.title] == [web.TITLE]
    finally:
        web.logo_svg.cache_clear()


def test_no_heading_offers_a_link_to_itself(page):
    """Streamlit gives every heading an anchor and a chain icon on hover. This
    page is one screen with one reading order, so the icon is a control that does
    nothing a reader wants."""
    at = page(auth=True, email=TESTER.email, enrolled={TESTER.email: TESTER}).run()
    headings = list(at.title) + list(at.header) + list(at.subheader)
    assert headings, "the page has headings to check"
    assert all(h.proto.hide_anchor for h in headings)


def test_the_spend_line_carries_what_is_left_on_the_reader_s_own_key(page, monkeypatch):
    """One caption, not two: the run budget with the key's ceiling in the
    parenthesis behind it."""
    monkeypatch.setattr(
        web,
        "_allowance",
        lambda key: allowance.Allowance(remaining=4.89, limit=5.0, resets="weekly"),
    )
    at = page(auth=True, email=TESTER.email, enrolled={TESTER.email: TESTER}).run()
    panel = _sidebar_text(at)
    assert "4.89 on key of weekly" in panel and "5.00)" in panel
    assert panel.count("on key") == 1, "one line, not a second caption beside it"
    assert "left of" not in panel, "the old sentence form is gone, not merely joined"


def test_a_reader_with_no_key_of_their_own_is_told_nothing_about_one(page):
    """The deny case varies what the rule reads -- no account, so no key -- rather
    than only changing the figure. The operator's balance is not a tester's
    business, and a blank parenthesis would be worse than none."""
    at = page(auth=False).run()
    panel = _sidebar_text(at)
    assert "on key" not in panel and "()" not in panel
    assert "of \\$" in panel, "the run budget itself is still there"


def test_an_enrolled_account_with_no_credential_meets_a_door_of_its_own(page, caught):
    """The dangerous direction: an agent built with no key falls back to the
    environment's. So the assertion is on what was *built*, not on the page --
    and the account never reaches the page at all, because no credential is now
    a closed door rather than a page with its input removed."""
    at = page(auth=True, email=KEYLESS.email, enrolled={KEYLESS.email: KEYLESS}).run()
    assert not at.chat_input
    assert messages.NO_CREDENTIAL in [e.value for e in at.error]
    assert page.built == [], "an agent was built, and would spend the environment's key"
    assert "Sign out" in [b.label for b in at.button], "no way out of the closed door"


def test_a_credential_the_provider_refuses_is_caught_at_sign_in(monkeypatch):
    """Not left for the first question to discover. Without this the model call
    fails, the tools retrieve nothing, and the answer reports finding nothing in
    the corpus -- a broken key wearing the face of a thin corpus, which is the one
    failure this project most wants not to look ordinary."""
    _configured(monkeypatch, TESTER.email)
    monkeypatch.setattr(web.accounts, "lookup", lambda e, who, **k: TESTER)
    rejected = web.admit(
        {}, object(), "s1", check_key=lambda key: web.allowance.Probe(rejected=True)
    )
    assert rejected.door is web.Door.CREDENTIAL_REJECTED
    assert rejected.account == TESTER, "enrolled; it is the credential that is wrong"


def test_a_provider_that_cannot_be_reached_does_not_shut_the_door(monkeypatch):
    """The asymmetry: a rejected key is the reader's problem to be told about, an
    unreachable provider is nobody's, and treating them alike would lock every
    tester out whenever OpenRouter blinked."""
    _configured(monkeypatch, TESTER.email)
    monkeypatch.setattr(web.accounts, "lookup", lambda e, who, **k: TESTER)
    admitted = web.admit({}, object(), "s1", check_key=lambda key: web.allowance.Probe())
    assert admitted.door is web.Door.OPEN


def test_the_key_is_checked_once_per_session_not_once_per_rerun(monkeypatch):
    """It is a network call on the render path; a held admission is what keeps it
    off every click."""
    _configured(monkeypatch, TESTER.email)
    monkeypatch.setattr(web.accounts, "lookup", lambda e, who, **k: TESTER)
    asked: list[str] = []
    state: dict = {}
    for _ in range(3):
        web.admit(
            state,
            object(),
            "s1",
            check_key=lambda key: asked.append(key) or web.allowance.Probe(),
        )
    assert asked == [TESTER.openrouter_key]


def test_no_check_at_all_admits_as_before(monkeypatch):
    """The terminal, the tests and any caller that passes nothing keep today's
    behaviour: the credential is believed until a question proves otherwise."""
    _configured(monkeypatch, TESTER.email)
    monkeypatch.setattr(web.accounts, "lookup", lambda e, who, **k: TESTER)
    assert web.admit({}, object(), "s1").door is web.Door.OPEN


def test_the_no_credential_door_is_its_own_state_not_an_open_one(monkeypatch):
    _configured(monkeypatch, KEYLESS.email)
    monkeypatch.setattr(web.accounts, "lookup", lambda e, who, **k: KEYLESS)
    admission = web.admit({}, object(), "s1")
    assert admission.door is web.Door.NO_CREDENTIAL
    assert admission.account == KEYLESS, "enrolled, and the page can say so"


def test_agent_for_refuses_rather_than_falling_back_to_the_environment(repo):
    """Defence behind the door: if a configured account without a credential ever
    reached here, building with `api_key=None` would quietly spend the
    deployment's own key."""
    admission = web.Admission(web.Door.OPEN, configured=True, account=KEYLESS)
    with pytest.raises(ValueError):
        web.agent_for({}, repo, admission)


def test_an_unreadable_accounts_table_admits_nobody_and_says_a_different_sentence(page, caught):
    at = page(
        auth=True, email=TESTER.email, enrolled={TESTER.email: TESTER}, unavailable=True
    ).run()
    assert not at.chat_input
    errors = [e.value for e in at.error]
    assert messages.ENROLMENT_CHECK_UNAVAILABLE in errors
    assert messages.NOT_ENROLLED not in errors, "an outage must not read as 'not enrolled'"
    assert "signin.refused" not in caught.events()
    assert page.built == []


def test_the_operator_is_told_what_could_not_be_read(page, caught, capsys):
    """The other half of the refusal: the reader is told to try again shortly,
    which is all they can act on, and whoever runs the app is told which failure
    it was. A refusal that reaches the operator with the reason stripped leaves
    them a page that says "try again shortly" and nothing to look at."""
    at = page(
        auth=True, email=TESTER.email, enrolled={TESTER.email: TESTER}, unavailable=True
    ).run()

    err = capsys.readouterr().err
    assert "EnrolmentUnavailable" in err
    assert "relation does not exist" in err, "the reason the lookup failed, on the operator's log"
    assert "relation does not exist" not in " ".join(e.value for e in at.error)


def test_the_credential_is_never_on_the_page(page):
    at = page(auth=True, email=TESTER.email, enrolled={TESTER.email: TESTER}).run()
    at = _ask(at, "how many?")
    everything = " ".join(
        [c.value for c in at.caption]
        + [m.value for m in at.markdown]
        + [e.value for e in at.error]
        + [i.value for i in at.info]
    )
    assert "sk-tester" not in everything


# --- 4.3: one repository, one agent per session ----------------------------------------


def test_two_sessions_get_two_agents_and_one_repository(monkeypatch, tmp_path):
    """Through the real cached `resources` and the real `agent_for`. The index is
    the expensive thing and stays shared; the agent holds a credential and
    cannot be."""
    from scinumbers_ask.corpus import load
    from scinumbers_ask.repository import CorpusRepository

    web.resources.clear()
    counts = {"indexed": 0, "agents": 0}
    rows = load(FIXTURE)
    monkeypatch.setattr(web, "load", lambda path: rows)

    def counting_repository(entries):
        counts["indexed"] += 1
        return CorpusRepository(entries)

    real_agent = web.AskAgent

    def counting_agent(*args, **kwargs):
        counts["agents"] += 1
        return real_agent(*args, **kwargs)

    monkeypatch.setattr(web, "CorpusRepository", counting_repository)
    monkeypatch.setattr(web, "AskAgent", counting_agent)
    monkeypatch.setattr(web.trace, "to_file", lambda spec: None)
    monkeypatch.setenv("SCINUMBERS_CORPUS", FIXTURE)
    monkeypatch.setenv("SCINUMBERS_CHECKPOINTS", str(tmp_path / "c.sqlite"))
    try:
        one = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
        one.run()  # a rerun of the same session builds nothing new
        AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    finally:
        web.resources.clear()
    assert counts == {"indexed": 1, "agents": 2}


# --- `admit` and `agent_for` below the page ----------------------------------------------


def _configured(monkeypatch, email, **claims):
    monkeypatch.setattr(web, "identity_configured", lambda: True)
    asserted = None if email is None else {"email": email, "email_verified": True, **claims}
    monkeypatch.setattr(web, "signed_in_claims", lambda: asserted)


def test_enrolment_is_read_once_per_account_per_session(monkeypatch):
    calls: list[str] = []
    _configured(monkeypatch, TESTER.email)
    monkeypatch.setattr(web.accounts, "lookup", lambda e, who, **k: calls.append(who) or TESTER)
    state: dict = {}
    try:
        for _ in range(3):
            assert web.admit(state, object(), "s1").door is web.Door.OPEN
        assert calls == [TESTER.email]
        # A different account on the same tab is looked up afresh.
        monkeypatch.setattr(
            web, "signed_in_claims", lambda: {"email": DEV.email, "email_verified": True}
        )
        monkeypatch.setattr(web.accounts, "lookup", lambda e, who, **k: calls.append(who) or DEV)
        admission = web.admit(state, object(), "s1")
        assert admission.account == DEV
        assert calls == [TESTER.email, DEV.email]
        session = web.effective_session(admission, "s1")
        web.establish_identity(admission, session)
        assert web.IDENTITIES[session] == Identity(DEV.email, Role.DEV)
    finally:
        web.IDENTITIES.clear()


def test_an_unavailable_check_is_retried_on_the_next_rerun(monkeypatch):
    """ "Try again shortly" has to mean the next rerun tries again."""
    _configured(monkeypatch, TESTER.email)
    attempts = {"n": 0}

    def flaky(engine, who, **k):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise EnrolmentUnavailable("asleep")
        return TESTER

    monkeypatch.setattr(web.accounts, "lookup", flaky)
    state: dict = {}
    try:
        assert web.admit(state, object(), "s1").door is web.Door.UNAVAILABLE
        assert web.admit(state, object(), "s1").door is web.Door.OPEN
    finally:
        web.IDENTITIES.clear()


def test_no_database_at_all_says_so_rather_than_asking_the_reader_to_wait(monkeypatch):
    """`[auth]` set and `[connections.usage]` not is the likeliest first-deploy
    mistake, and it never comes right on its own -- so "try again shortly" would
    leave every visitor waiting on a retry that cannot succeed."""
    _configured(monkeypatch, TESTER.email)
    door = web.admit({}, None, "s1").door
    assert door is web.Door.NO_ACCOUNTS_DATABASE
    assert door is not web.Door.OPEN, "fails closed either way"
    assert messages.NO_ACCOUNTS_DATABASE != messages.ENROLMENT_CHECK_UNAVAILABLE


def test_signing_out_forgets_the_session_s_identity(monkeypatch):
    """The page establishes identity every rerun, so the rerun after sign-out --
    which has no account -- is what clears it."""
    _configured(monkeypatch, TESTER.email)
    monkeypatch.setattr(web.accounts, "lookup", lambda e, who, **k: TESTER)
    state: dict = {}
    try:
        admission = web.admit(state, object(), "s1")
        session = web.effective_session(admission, "s1")
        web.establish_identity(admission, session)
        assert session in web.IDENTITIES
        monkeypatch.setattr(web, "signed_in_claims", lambda: None)
        after = web.admit(state, object(), "s1")
        assert after.door is web.Door.SIGN_IN
        web.establish_identity(after, web.effective_session(after, "s1"))
        assert web.ADMISSION_KEY not in state
        web.end_session(session)
        assert session not in web.IDENTITIES
    finally:
        web.IDENTITIES.clear()


def test_a_refusal_after_another_account_was_admitted_carries_no_stamp(monkeypatch, caught):
    """A verifier produced this row: admit as one account, then a stranger on the
    same session id with no signed-out rerun between, and the refusal came out
    stamped with the *first* account's email. The registry entry has to go
    before the lookup, not only on sign-out."""
    _configured(monkeypatch, TESTER.email)
    monkeypatch.setattr(web.accounts, "lookup", lambda e, who, **k: TESTER)
    state: dict = {}
    admitted = web.admit(state, object(), "s1")
    web.establish_identity(admitted, web.effective_session(admitted, "s1"))
    monkeypatch.setattr(
        web,
        "signed_in_claims",
        lambda: {"email": "stranger@example.org", "email_verified": True},
    )
    monkeypatch.setattr(web.accounts, "lookup", lambda e, who, **k: None)
    assert web.admit(state, object(), "s1").door is web.Door.NOT_ENROLLED
    (refused,) = [r for r in caught.records if r.getMessage() == "signin.refused"]
    assert refused.fields["email"] == "stranger@example.org"
    assert getattr(refused, "user_email", None) is None, (
        "the refusal is recorded against the URL token, which no account owns"
    )
    assert getattr(refused, "user_role", None) is None
    assert "s1" not in web.IDENTITIES


def test_sign_out_forgets_the_identity_and_then_logs_out(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(web.st, "logout", lambda: calls.append("logout"))
    web.remember_identity("s1", Identity(TESTER.email, Role.SCIENTIST))
    try:
        web._sign_out("s1")
        assert "s1" not in web.IDENTITIES
        assert calls == ["logout"]
    finally:
        web.IDENTITIES.clear()


def test_identity_is_not_configured_when_there_is_no_secrets_file_at_all(monkeypatch):
    """This checkout has a real secrets file, so the branch for a machine with
    none never runs here unless made to. Streamlit raises its own error for
    the missing file; that is "not configured", and anything else is not."""
    from streamlit.errors import StreamlitSecretNotFoundError

    class _NoFile:
        def __contains__(self, key):
            raise StreamlitSecretNotFoundError("no secrets.toml")

    class _Broken:
        def __contains__(self, key):
            raise RuntimeError("malformed")

    monkeypatch.setattr(web.st, "secrets", _NoFile())
    assert web.identity_configured() is False
    monkeypatch.setattr(web.st, "secrets", _Broken())
    with pytest.raises(RuntimeError):
        web.identity_configured()


def test_agent_for_holds_one_agent_per_state_and_rebuilds_on_a_new_credential(
    monkeypatch, repo, tmp_path
):
    monkeypatch.setenv("SCINUMBERS_CHECKPOINTS", str(tmp_path / "c.sqlite"))
    built: list = []
    monkeypatch.setattr(
        web, "AskAgent", lambda *a, api_key=None, **k: built.append(api_key) or object()
    )
    state: dict = {}
    open_as = web.Admission(web.Door.OPEN, configured=True, account=TESTER)
    first = web.agent_for(state, repo, open_as)
    assert web.agent_for(state, repo, open_as) is first
    assert built == ["sk-tester"]
    web.agent_for(state, repo, web.Admission(web.Door.OPEN, configured=True, account=DEV))
    assert built == ["sk-tester", "sk-dev"]
    assert web.agent_for({}, repo, web.Admission(web.Door.OPEN, configured=False)) is not first
    assert built[-1] is None, "unconfigured: the environment's key"


def test_signed_in_claims_are_none_without_is_logged_in(monkeypatch):
    """`AppTest` fixes `st.user` to an address with no `is_logged_in`; a real
    unconfigured deployment has no such key either. Neither is signed in."""
    monkeypatch.setattr(web.st, "user", type("U", (), {"to_dict": lambda self: {"email": "x@y"}})())
    assert web.signed_in_claims() is None
    monkeypatch.setattr(
        web.st,
        "user",
        type("U", (), {"to_dict": lambda self: {"email": "x@y", "is_logged_in": True}})(),
    )
    assert web.signed_in_claims() == {"email": "x@y", "is_logged_in": True}


# --- 4.5: the note, both variants -----------------------------------------------------------


def test_the_note_is_one_short_sentence_whatever_is_configured():
    """Deliberately not an enumeration, and deliberately not two sentences: the
    fuller statement of what is kept about a person is deferred to a disclaimer
    shown once before use, when there are users to show it to."""
    assert messages.RECORDS_NOTE == "All app exchange is logged for product development."
    assert messages.RECORDS_NOTE.count(".") == 1
    assert "account" not in messages.RECORDS_NOTE and "role" not in messages.RECORDS_NOTE


def test_a_signed_in_tester_is_told_whom_to_ask_when_the_allowance_is_spent():
    """The funder-neutral sentence was written so a developer on their own key is
    not told to contact themselves. A signed-in tester is not the funder, so
    the page may -- must -- say whom to ask, and that the allowance renews."""
    from scinumbers_ask.events import EndReason

    plain = messages.run_over_advice(EndReason.PROVIDER_LIMIT)
    tester = messages.run_over_advice(EndReason.PROVIDER_LIMIT, signed_in=True)
    assert "ask" not in plain.lower()
    assert "ask whoever runs this deployment" in tester
    assert "renews" in tester and "monthly" in tester
    assert "new session will not help" in tester
    # Endings with no advice of their own stay that way for both readers.
    assert messages.run_over_advice(EndReason.RUN_BUDGET, signed_in=True) is None


def test_the_no_credential_sentence_says_whom_to_ask():
    assert "Ask whoever runs this deployment" in messages.NO_CREDENTIAL


def test_the_page_shows_a_tester_the_tester_s_wording_and_a_developer_the_neutral_one(
    page, caught, repo, config, tmp_path
):
    from conftest import agent_with

    from agent_doubles import OutOfCreditModel, says

    def _spent_agent():
        return agent_with(repo, config, tmp_path, OutOfCreditModel(responses=[says("x")]))

    at = page(auth=True, email=TESTER.email, enrolled={TESTER.email: TESTER})
    monkeypatch_agent = _spent_agent()
    import scinumbers_ask.web as w

    original = w.agent_for
    w.agent_for = lambda state, repo_, admission: monkeypatch_agent
    try:
        at = _ask(at.run(), "how many?")
        banner = " ".join(e.value for e in at.error)
        assert "ask whoever runs this deployment" in banner
        assert "whoever funds it" not in banner

        w.agent_for = lambda state, repo_, admission: _spent_agent()
        dev = _ask(page(auth=False).run(), "how many?")
        banner = " ".join(e.value for e in dev.error)
        assert "whoever funds it" in banner
        assert "ask whoever runs this deployment" not in banner
    finally:
        w.agent_for = original


# --- the session is keyed on the account, not on the shared link ------------------------


def _admitted(account: Account) -> web.Admission:
    return web.Admission(web.Door.OPEN, configured=True, account=account)


def test_two_accounts_on_one_shared_link_get_two_sessions():
    """The defect this model exists to remove: `?session=` is shared by anyone
    given the link, so keying identity on it let the second reader's sign-in
    overwrite the first's stamp, and every later record of the first reader was
    attributed to the second."""
    link = "abc123"
    one = web.effective_session(_admitted(TESTER), link)
    two = web.effective_session(_admitted(DEV), link)
    assert one != two
    try:
        web.establish_identity(_admitted(TESTER), one)
        web.establish_identity(_admitted(DEV), two)
        assert web.IDENTITIES[one] == Identity(TESTER.email, Role.SCIENTIST)
        assert web.IDENTITIES[two] == Identity(DEV.email, Role.DEV)
    finally:
        web.IDENTITIES.clear()


def test_a_fresh_link_gives_one_account_a_fresh_conversation():
    """The escape hatch, and the reason the token is half of the key.

    The conversation is the LangGraph thread, and a thread that fills up refuses
    every further question. Keyed on the account alone the key was a pure
    function of the email, so a reader who filled one could not leave it: a new
    link did nothing, signing out gave the same key back, and the page's own
    advice to reload with a fresh `?session=` could not be followed.
    """
    account = _admitted(TESTER)
    assert web.effective_session(account, "abc") != web.effective_session(account, "zzz")
    assert web.effective_session(account, "abc") == web.effective_session(account, "abc")


def test_the_same_link_still_separates_two_accounts():
    """The other half. A shared link must not carry one reader into another's
    conversation, whatever the token says."""
    assert web.effective_session(_admitted(TESTER), "abc") != web.effective_session(
        _admitted(DEV), "abc"
    )


def test_with_no_identity_configured_the_url_token_is_still_the_session():
    """A developer's machine keeps today's bookmarkable behaviour."""
    unconfigured = web.Admission(web.Door.OPEN, configured=False)
    assert web.effective_session(unconfigured, "abc123") == "abc123"


def test_the_session_key_does_not_carry_the_address_in_the_clear():
    """It is shown in the page's caption and lands in the trail; an email there
    would put the account in places the stamp already covers properly."""
    assert TESTER.email not in web.effective_session(_admitted(TESTER), "abc")


def test_a_session_pruned_for_idleness_is_stamped_again_when_its_reader_returns(monkeypatch):
    """The silent one: prune evicts the identity, the held admission short-cuts
    the lookup, and every later record of a still-signed-in tab was written with
    no account while the sidebar still named one."""
    _configured(monkeypatch, TESTER.email)
    monkeypatch.setattr(web.accounts, "lookup", lambda e, who, **k: TESTER)
    state: dict = {}
    try:
        first = web.admit(state, object(), "url")
        session = web.effective_session(first, "url")
        web.establish_identity(first, session)
        web.forget_identity(session)  # what prune does after the idle window
        held = web.admit(state, object(), "url")
        assert held.account == TESTER, "the held admission is still the fast path"
        web.establish_identity(held, session)
        assert web.IDENTITIES[session] == Identity(TESTER.email, Role.SCIENTIST)
    finally:
        web.IDENTITIES.clear()


def test_ending_a_session_clears_the_identity_the_panel_and_the_place():
    """Sign-out cleared the identity and left the panel rows, so the next account
    on that tab could be shown the last one's questions."""
    import logging

    handler = web.install_recent_trail()
    web.session_registry.clear()
    try:
        web.remember_identity("s1", Identity(TESTER.email, Role.SCIENTIST))
        record = logging.LogRecord("x", logging.INFO, "f", 1, "question.asked", None, None)
        record.session_id, record.question_id, record.fields = "s1", "q1", {"question": "secret?"}
        handler.emit(record)
        assert web.session_registry().admit("s1")
        assert handler.rows("s1") and "s1" in web.IDENTITIES
        web.end_session("s1", "s1")
        assert handler.rows("s1") == []
        assert "s1" not in web.IDENTITIES
        assert web.session_registry().live() == 0
    finally:
        logging.getLogger(web.trace.LOGGER_NAME).removeHandler(handler)
        web.RECENT = None
        web.IDENTITIES.clear()
        web.session_registry.clear()


def test_the_cap_counts_tabs_and_not_accounts(monkeypatch):
    """One account is one conversation across its tabs (ADR-0830), so a cap keyed
    on the conversation would count *accounts*: eight testers with five tabs each
    is forty Streamlit sessions and forty agents, reported as eight. What costs
    the host is a tab, so that is what the registry holds."""
    web.session_registry.clear()
    try:
        registry = web.session_registry()
        conversation = web.effective_session(_admitted(TESTER), "ignored")
        for tab in ("tab-1", "tab-2", "tab-3"):
            assert registry.admit(tab, conversation)
        assert registry.live() == 3, "three tabs of one account are three sessions"
    finally:
        web.session_registry.clear()


def test_the_stamp_survives_the_prune_that_admitting_performs(monkeypatch):
    """The ordering the page depends on. `admit` prunes, and pruning clears the
    stamp of a conversation whose last tab has gone; establishing identity before
    that call had the stamp wiped in the same run, so a reader returning after
    the idle window asked their question against no account at all."""
    now = {"t": 1000.0}
    registry = web.SessionRegistry(max_sessions=20, idle_s=600, clock=lambda: now["t"])
    admission = _admitted(TESTER)
    conversation = web.effective_session(admission, "url")
    try:
        registry.admit("url", conversation)
        web.establish_identity(admission, conversation)
        assert web.IDENTITIES[conversation] == Identity(TESTER.email, Role.SCIENTIST)

        now["t"] += 601  # the reader steps away, then comes back and asks
        registry.admit("url", conversation)
        web.establish_identity(admission, conversation)
        assert web.IDENTITIES[conversation] == Identity(TESTER.email, Role.SCIENTIST), (
            "the stamp was pruned away in the same run that set it"
        )
    finally:
        web.IDENTITIES.clear()


def test_pruning_one_tab_leaves_a_conversation_another_tab_is_still_in():
    """The stamp belongs to the conversation, so it may only go when the last tab
    holding it does."""
    now = {"t": 1000.0}
    registry = web.SessionRegistry(max_sessions=20, idle_s=600, clock=lambda: now["t"])
    admission = _admitted(TESTER)
    conversation = web.effective_session(admission, "url")
    try:
        registry.admit("tab-1", conversation)
        registry.admit("tab-2", conversation)
        web.establish_identity(admission, conversation)
        now["t"] += 400
        registry.admit("tab-2", conversation)  # one tab keeps rerunning
        now["t"] += 400  # tab-1 is now past its window, tab-2 is not
        registry.prune()
        assert conversation in web.IDENTITIES, "the live tab's conversation was cleared"
        now["t"] += 601
        registry.prune()
        assert conversation not in web.IDENTITIES, "the last tab went and nothing was cleared"
    finally:
        web.IDENTITIES.clear()


def test_a_malformed_cap_setting_falls_back_rather_than_taking_the_page_down(monkeypatch, capsys):
    monkeypatch.setenv(web.MAX_SESSIONS_ENV, "twenty")
    web.session_registry.clear()
    try:
        assert web.session_registry().max_sessions == web.DEFAULT_MAX_SESSIONS
        assert "not a number" in capsys.readouterr().err
    finally:
        web.session_registry.clear()


def test_the_link_names_the_conversation_and_never_the_tab():
    """Two values that were one. The token comes from the link and stays in the
    address bar, so a reader can bookmark a conversation and change it for a
    fresh one. The tab's own id is minted, because the cap counts tabs and ten
    testers on one shared bookmark would otherwise register as a single tab --
    bounding nothing, and any one of them able to free the other nine's place."""
    state, params = {}, {"session": "abc123"}
    assert web.session_id(state, params) == "abc123"
    assert params["session"] == "abc123", "the conversation stays bookmarkable"

    minted = web.tab_id(state)
    assert minted != "abc123", "the link decided which tab this is"
    assert web.tab_id(state) == minted, "stable for the life of this browser session"
    assert web.tab_id({}) != minted, "a second tab is a second session"


def test_the_suite_runs_as_though_no_sign_in_were_configured():
    """The insulation `conftest` provides, pinned where it will be read.

    Without it the suite's result depends on whether the developer running it
    happens to have Google sign-in in their own `.streamlit/secrets.toml` --
    which they will, the day they set up the deployment. Sixty-four tests failed
    exactly that way, on a tree that had not changed.
    """
    assert web.identity_configured() is False


# --- each tester spends against their own budget ------------------------------------------


def test_one_tester_s_spend_does_not_close_the_door_on_another(repo, config, tmp_path):
    """The run ledger was keyed on the process-wide run label, so with a key each
    the first tester to reach the run budget refused every other tester's next
    question -- while their own credential was untouched, and the panel showed
    each of them the aggregate as if it were their own spend."""
    from scinumbers_ask import run_ledger
    from scinumbers_ask.agent import AskAgent

    store = str(tmp_path / "c.sqlite")
    one = AskAgent(repo, config, store, api_key="k1", budget_scope="acct-one")
    two = AskAgent(repo, config, store, api_key="k2", budget_scope="acct-two")

    run_ledger.add(store, one._ledger_key(), config.run_budget)
    assert one.run_spend() >= config.run_budget, "the first tester has spent their budget"
    assert two.run_spend() == 0, "and the second's is untouched"


def test_without_a_scope_the_budget_is_one_pot_exactly_as_before(repo, config, tmp_path):
    """The terminal, the evaluation harness and an unconfigured page pass no
    scope, and must keep the single deployment-wide budget they have always had."""
    from scinumbers_ask import run_ledger
    from scinumbers_ask.agent import AskAgent

    store = str(tmp_path / "c.sqlite")
    first = AskAgent(repo, config, store)
    second = AskAgent(repo, config, store)
    run_ledger.add(store, first._ledger_key(), 500)
    assert second.run_spend() == 500


def test_the_scope_is_per_account_and_says_nothing_about_who(monkeypatch):
    scope = web.account_scope(_admitted(TESTER))
    assert scope == web.account_scope(_admitted(TESTER)), "stable for one account"
    assert scope != web.account_scope(_admitted(DEV)), "and different for another"
    assert TESTER.email not in scope
    assert web.account_scope(web.Admission(web.Door.OPEN, configured=False)) is None


def test_the_agent_is_handed_the_scope_and_still_no_identity(repo, tmp_path):
    """The scope is a funding fact like the credential beside it, not a person:
    the structural guard in `test_driver_independence` still has to pass."""
    from scinumbers_ask.agent import AskAgent

    agent = AskAgent(repo, web.Config.from_env(), str(tmp_path / "c.sqlite"), budget_scope="s")
    held = {name.lower().lstrip("_") for name in vars(agent)}
    assert "budget_scope" in held
    assert not held & {"identity", "role", "email", "account", "user_role", "user_email"}


def test_a_tester_is_shown_what_the_provider_says_is_left_on_their_key(page, monkeypatch):
    monkeypatch.setattr(
        web, "_allowance", lambda key: web.allowance.Allowance(remaining=3.4, limit=5.0)
    )
    at = page(auth=True, email=TESTER.email, enrolled={TESTER.email: TESTER}).run()
    assert any("3.40" in c.value and "5.00" in c.value for c in at.sidebar.caption)


def test_an_unconfigured_deployment_is_told_nothing_about_the_operator_s_key(page, monkeypatch):
    """That balance is the operator's, not a reader's."""
    monkeypatch.setattr(
        web, "_allowance", lambda key: web.allowance.Allowance(remaining=3.4, limit=5.0)
    )
    at = page(auth=False).run()
    assert not any("3.40" in c.value for c in at.sidebar.caption)
