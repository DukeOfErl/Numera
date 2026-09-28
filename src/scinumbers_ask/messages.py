"""What a warning says, in words, shared by the drivers.

Every driver renders the same events, and a warning is the one kind whose wording
is a claim rather than a layout: "cited without being retrieved" means something,
and two drivers that phrase it differently are two different statements about the
same fact. The terminal prefixes these with a marker and the web page puts them in
a coloured box; neither owns the sentence.

Deliberately not on the events themselves. `events.py` is the port -- what the
agent knows -- and how a fact is put to a person is not something the agent should
carry. Deliberately not in `cli.py` either, which is one adapter among several.
"""

from __future__ import annotations

from . import bionumbers
from .config import format_usd
from .events import (
    CitationWarning,
    ConversationWarning,
    CostProjection,
    EndReason,
    Event,
    QuestionEnded,
    Retrieval,
    SpendWarning,
    UngroundedRefusal,
)

# One line, and deliberately not an enumeration.
#
# It named the question, the answer, the entries and -- once there was sign-in --
# the account and the role. That is the honest list and it was too long to read:
# a standing notice nobody finishes tells nobody anything, and it sat above the
# controls a reader actually came for. So it says the thing that matters, which
# is that what passes through here is recorded and why.
#
# **The fuller disclaimer arrived** as `PRIVACY` below, earlier than the "real
# users rather than invited testers" condition that was to reopen it: Google will
# not publish a consent screen without a policy at a public address. It is offered
# rather than shown once before use -- a collapsed expander beside this line and on
# the door -- because a notice a reader must dismiss to proceed is dismissed.
#
# The same sentence whether or not sign-in is configured. It was a function of
# that for one release; with both variants identical the parameter only invited
# a caller to believe it changed something.
RECORDS_NOTE = "All app exchange is logged for product development."

# Whose money the questions cost. It lived on the deployment branch for a release,
# on the reasoning that someone running the app locally pays for their own calls --
# but locally the developer *is* the developer, and once a tester's key is minted
# by the operator the sentence is true wherever the app runs. A page that says
# something different depending on which branch built it is the drift this project
# has now decided against: what a reader sees is the same everywhere, and only
# deployment mechanics differ.
BUDGET_NOTE = (
    "Model usage is paid for by the developer — please keep questions "
    "purposeful, and don't abuse budget."
)

#: Where a reader is told to write. Published on a public page, so it is a
#: deliberate disclosure rather than a detail: change it here and it changes in
#: both places the policy is drawn.
PRIVACY_CONTACT = "yoavpol@gmail.com"

#: The standing statement about what is kept, in full rather than in a line.
#:
#: `RECORDS_NOTE` says *that* exchanges are logged, which is the right length for
#: a sidebar caption and too short to be a privacy policy. This is the long form,
#: behind a collapsed expander so that it is reachable without being imposed.
#: Written now because Google requires a policy at a public address before it will
#: take a consent screen out of testing, and the app's own address is the one the
#: consent screen points at (ADR-1100).
#:
#: **It must be readable without signing in**, which is why it is drawn on the
#: door as well as in the panel: the app's own address is what the consent screen
#: links to, and a visitor following that link is by definition not signed in.
#:
#: Every service named here is one this app actually hands something to. Naming
#: them is the part a reader cannot discover for themselves, and the part that
#: dates fastest -- a new sink means a line here, in the same change.
PRIVACY_HEADING = "What this prototype keeps about you"
PRIVACY = f"""SciNumbers Ask is a research prototype, run by one person and offered by
invitation. Using it means the following is recorded.

- **Your email address**, as the sign-in provider reports it, and the role you were
  enrolled under.
- **Your questions, the answers given and the corpus entries behind them**, together
  with any rating or comment you leave on an answer.
- **Timestamps, and identifiers for the session and for each question**, so one
  conversation can be told from another.

This is kept in a hosted Postgres database, and is used to run the app, to keep it
inside the developer's budget, and to find where its answers go wrong. Your questions,
and the corpus entries looked up for them, are sent to a model provider to be answered.

What it passes through: Auth0 (sign-in), Neon (the database), and OpenRouter with the
model provider it routes to; where tracing is switched on, Langfuse receives the same
material. Nothing is sold, and nothing is shared beyond those.

Records are kept for as long as the prototype runs. To see what is held about you, or
to have it deleted, email {PRIVACY_CONTACT}."""

# The door, before anything else is drawn. Each is a different sentence because
# each asks the reader to do a different thing -- and "not enrolled" during an
# outage would send a person to the operator, who finds them already enrolled.
# Says *why* there is a door rather than what to do about it. The button beside it
# already says what to do, and a visitor who was not invited needs the reason more
# than the instruction: without it the refusal reads as a system that has not
# recognised them yet, and they try again. Naming the budget is the honest form --
# this is one person's money, which is also why every account is capped.
SIGN_IN_NEEDED = "Use of this app is by invitation only since you are using the developer's budget"
#: What each configured provider's button says. Keyed by the name the provider
#: has in secrets -- `"default"` for the section's own credentials, a sub-table's
#: name otherwise -- so adding a third provider is a secrets edit and, at most, a
#: row here. A name with no row gets "Sign in with <name>" rather than a
#: KeyError: an operator who adds `[auth.okta]` should meet a plain button, not a
#: blank page.
SIGN_IN_LABELS = {
    "default": "Sign in with Google",
    # `google` as a *named* provider, which is how the Google client is written
    # when the buttons need to be in an order other than "default first". Moving
    # it out of `[auth]`'s own keys into `[auth.google]` is a secrets change and
    # nothing else -- the same label, reached by the other route.
    "google": "Sign in with Google",
    # Just "Sign in", because it is the only button on the door. "Sign in with
    # email" distinguished it from the Google button beside it, and that button is
    # gone (ADR-1100); naming the method now invites the question of what the other
    # methods are, when the provider's own page answers it.
    "auth0": "Sign in",
}


def sign_in_label(provider: str) -> str:
    """The button's words for one provider."""
    return SIGN_IN_LABELS.get(provider, f"Sign in with {provider}")


# Distinct from NOT_ENROLLED on purpose: the reader's next step differs. Here it
# is theirs to take and it will work; there it is the operator's and nothing on
# this page helps. A single sentence for both would send half of each group to
# the wrong place.
# Three goes at this one, and the failures are the useful part.
#
# The first named "your sign-in provider" and "the link it emailed you": accurate,
# and inert. The reader who met it had the email and did not look, because nobody
# thinks of Auth0 as their sign-in provider.
#
# The second said what to do and explained why at length, which reads as a system
# addressing its operator rather than a person trying to ask a question.
#
# The third -- this one -- is a reader's own wording. "A confirmation email has
# been sent" was resisted on the grounds that this page cannot know it, and that
# was wrong: the sentence does not claim *just now*, and sign-up does send one,
# whether that was five minutes or five days ago. The objection had conflated "was
# sent" with "was just sent". Recorded because the useful correction came from the
# person meeting the sentence cold, twice, and both times the fault was in
# explaining rather than in the facts.
UNVERIFIED = (
    "A confirmation email has been sent to your address (check your spam folder too). "
    "Please confirm it, then use the button below."
)

#: The way back in without signing out. `st.login` has no already-signed-in guard
#: (read from the installed Streamlit 1.61.1): it redirects to the provider, which
#: sees its own session and issues a fresh token carrying the now-confirmed
#: address. So the reader clicks once and is admitted, with no password to retype
#: and no apparent sign-out -- which is the difference between a door and a dead
#: end.
CONFIRMED_IT = "I have confirmed my email"

#: The other thing a reader on that door might need, and the only dead end left in
#: it: the email never arrived. Resending it needs an Auth0 Management credential
#: with `update:users`, which can also create accounts and change addresses -- far
#: more power than one message is worth, and the first credential this app would
#: hold that acts on other people's accounts. So the button records a request
#: instead, and the operator resends from the provider's dashboard.
RESEND_REQUEST = "I did not get the email"

#: Deliberately not "an email is on its way": nothing was sent from here, and a
#: person told to wait for a message nobody has sent waits twice.
#:
#: The second sentence is the honest part. The request goes to the trail, where the
#: operator finds it by looking (`sql/signin.sql`) -- so the wait is however long
#: until they look. This is a prototype run by one person, and saying so while
#: inviting a direct message is truer than implying a support desk.
RESEND_NOTED = (
    "Your issue has been recorded. Since this is a prototype, please also contact the "
    "developer personally."
)
NOT_ENROLLED = (
    "This account is not enrolled. Ask whoever runs this to enrol it; there is nothing to do here."
)
NO_ACCOUNTS_DATABASE = (
    "Sign-in is configured but the account list is not, so nobody can be admitted. "
    "That is for whoever runs this deployment to fix; waiting will not help."
)
ENROLMENT_CHECK_UNAVAILABLE = (
    "Enrolment cannot be checked right now, so nobody can be admitted. Try again shortly."
)
NO_CREDENTIAL = (
    "No credential has been issued for this account yet, so it cannot ask a question. "
    "Ask whoever runs this deployment to issue one — it is theirs to do, and nothing "
    "here can."
)
CREDENTIAL_REJECTED = (
    "The credential issued for this account was refused by the model provider, so no "
    "question can be asked with it. Ask whoever runs this deployment to reissue it — "
    "nothing here can, and asking anyway would only produce an answer with nothing "
    "behind it."
)
NO_SIGN_IN_CONFIGURED = (
    "No sign-in is configured: anyone with this address can ask, and records carry no account."
)
# Just who, and as what. The sign-out button sits beside it, which is what says
# this is your account rather than a fact about somebody.
SIGNED_IN_AS = "{email}  \n({role})"
TRY_LATER = (
    "Too many sessions are open right now, so this one cannot start. "
    "Try again in a few minutes; nobody's session is ended to make room."
)

# Endings after which asking again cannot produce a different answer. What these
# share is that they are not about the question just asked: a spent run budget
# stays spent, and a conversation over its token bound only grows. The per-question
# ceiling is deliberately absent -- that one refreshes.
#
# Shared because it is a fact about the ending rather than a rendering of it. The
# terminal quit on these and the web went on accepting questions, replaying the
# same refusal indefinitely; two drivers disagreeing about whether the door is shut
# is the divergence `messages` exists to prevent.
#
# A provider out of credit is here for the same reason, and is the only member a
# reader cannot fix themselves: the key funding the run has no balance, so every
# further question fails identically until somebody tops it up. PROVIDER_FAILURE
# stays out -- a gateway that failed once may well answer the next call.
STOP_THE_RUN = frozenset(
    {
        EndReason.RUN_BUDGET,
        EndReason.CONVERSATION_BOUND,
        EndReason.NOT_CONFIGURED,
        EndReason.PROVIDER_LIMIT,
    }
)


# What to do about a shut door, where "start a new session" is the wrong answer.
#
# Each driver has its own generic line for a run that is over, and for a spent run
# budget or a full conversation that line is right: a fresh session does refresh
# both. A key with no credit is different in kind -- the next session's first
# question meets the same refusal -- so the generic advice sends the reader round a
# loop, and it is the last thing on screen, under an answer that has just told them
# the opposite.
#
# Shared for the reason the rest of this module is: the terminal and the page are
# answering one question, "may I ask again, and if not what would help", and two
# drivers phrasing that differently are two claims about one fact.
# Each sentence has to read correctly to *both* readers this project has: someone
# using a hosted instance, and the developer running the same code on their own key.
# "Ask whoever deployed the app" was the first wording and told the second reader to
# contact themselves -- the exact absurdity that moving the sentence out of the agent
# was supposed to avoid. Naming the remedy without addressing anyone works for both.
RUN_OVER_ADVICE: dict[EndReason, str] = {
    EndReason.PROVIDER_LIMIT: (
        "The key that pays for this app's model calls has reached its usage limit, so a "
        "new session will not help — the limit has to be raised by whoever funds it."
    ),
    # Here for the same reason, and it was wrong before this change too: a missing
    # credential or a spend that cannot be accounted for meets the reader again on
    # the first question of any new session. The ending's own answer carries the
    # specifics -- which variable, what to set -- so this only has to stop the page
    # advising something that cannot work.
    EndReason.NOT_CONFIGURED: (
        "A new session will not help: this run stopped because something the app needs "
        "is not configured, and that has to be fixed where the app runs."
    ),
}


# The same two endings, for a reader who is *not* the funder: a signed-in tester
# on a hosted deployment, whose key was issued by an operator with a monthly cap.
# Here the second person is right, because there is someone to ask who is not
# the reader -- the absurdity the paragraph above avoids is exactly the case the
# page can now tell apart (`web.identity_configured`). The terminal and the
# harness never pass `signed_in`, so their wording is unchanged.
SIGNED_IN_ADVICE: dict[EndReason, str] = {
    EndReason.PROVIDER_LIMIT: (
        "Your account's allowance for this app is spent, so a new session will not help. "
        "It renews on its monthly schedule; to ask again sooner, ask whoever runs this "
        "deployment to raise it."
    ),
    EndReason.NOT_CONFIGURED: (
        "A new session will not help: this run stopped because something the app needs "
        "is not configured. Tell whoever runs this deployment; there is nothing to do here."
    ),
}


def run_over_advice(reason: EndReason, *, signed_in: bool = False) -> str | None:
    """What a driver should say about this ending, beyond its own generic line.

    `None` for every ending with no advice of its own, which is most of them: a
    driver falls back to its own wording rather than being handed a sentence for a
    case where its existing one is already correct.

    `signed_in` selects the wording for a reader who is not the funder -- an
    enrolled tester -- and is the web driver's to pass; nothing else has a reader
    who could be one.
    """
    if signed_in:
        return SIGNED_IN_ADVICE.get(reason) or RUN_OVER_ADVICE.get(reason)
    return RUN_OVER_ADVICE.get(reason)


def warning_text(event: Event) -> str | None:
    """The sentence for a warning event, or None if the event is not one."""
    if isinstance(event, ConversationWarning):
        return (
            f"this session holds {event.tokens:,} of {event.bound:,} tokens; "
            "it will stop taking questions at the bound"
        )
    if isinstance(event, SpendWarning):
        return (
            f"spent {format_usd(event.spent)}, past the "
            f"{format_usd(event.threshold)} warning threshold"
        )
    if isinstance(event, CostProjection):
        return (
            f"this question could cost up to {format_usd(event.projected)}, "
            f"above the {format_usd(event.threshold)} threshold (an estimate)"
        )
    if isinstance(event, UngroundedRefusal):
        if event.claimed_searching:
            return (
                "this answer describes searching that did not happen: no retrieval "
                "was made, so it says nothing about what the corpus holds"
            )
        return (
            "nothing was retrieved for this question, so this answer is not grounded "
            "in the corpus -- it says only what the model expected to find"
        )
    if isinstance(event, CitationWarning):
        parts = []
        if event.unknown:
            parts.append(f"not in the corpus: {', '.join(map(bionumbers.label, event.unknown))}")
        if event.unretrieved:
            parts.append(
                "cited without being retrieved: "
                + ", ".join(map(bionumbers.label, event.unretrieved))
            )
        return "; ".join(parts)
    return None


# Carried for the entries table and the citation check, not for a person to read:
# fifty identifiers on a progress line would bury what the search was for.
UNRENDERED_DETAIL = {"entry_ids"}


def retrieval_text(event: Retrieval) -> str:
    """What a retrieval was, in words: the tool and what it was asked."""
    detail = " ".join(
        f"{k}={v!r}"
        for k, v in event.detail.items()
        if v is not None and k not in UNRENDERED_DETAIL
    )
    return f"{event.tool} {detail}".rstrip()


def _run_clause(event: QuestionEnded) -> str:
    """Run spend, against the run's cap where the ending carries one.

    The cap is shown on every ending rather than only when it is reached, because
    unlike the per-question ceiling it is not refreshed by asking again: spend
    accumulates until the run stops taking questions at all. A reader watching a
    number climb needs to know what it is climbing towards, and the moment it is
    worth knowing is before the run ends, not at it.
    """
    if not event.run_budget:
        return f"(run {format_usd(event.run_spend)})"
    return f"(run {format_usd(event.run_spend)} of {format_usd(event.run_budget)})"


def ending_text(event: QuestionEnded) -> str:
    """Why a question ended, what it consumed, and against which limits.

    Shared because it is a report, not a layout: the terminal prefixes it with a
    dash and the page draws it as a caption, and a driver that quietly left a
    clause out would be under-reporting rather than restyling. The web driver had
    already dropped the retrieval-bound clause that way.

    Both bound clauses appear only where the bound was reached. Printed on every
    answer they would put a number nobody needs beside the ones they do; printed
    where there was no room left for another call, each says something a reader
    cannot otherwise see.
    """
    mark = " (incomplete)" if event.incomplete else ""
    parts = [
        f"{event.reason.value}{mark}",
        format_usd(event.spend),
        _run_clause(event),
        event.model,
        f"{event.tool_calls} tool calls",
    ]
    line = " · ".join(parts[:1] + [" ".join(parts[1:3])] + parts[3:])
    if event.at_retrieval_bound:
        line += f" · {event.model_calls} of {event.call_limit} model calls"
    if event.at_tool_bound:
        line += f" · {event.tool_calls} of {event.tool_call_limit} retrievals"
    # Only where the question answered: an ending that already names the ceiling
    # as its reason does not need telling twice.
    if event.at_spend_ceiling and not event.incomplete:
        line += f" · at the {format_usd(event.spend_ceiling)} ceiling"
    return line
