# ADR-1110: The privacy policy is served by the door, not by a second host

- **Status:** accepted
- **Date:** 2026-09-28
- **Pull request:** _pending — `feat/one-way-in`_

## Context

Google will not move an OAuth consent screen out of Testing without an App domain
and a privacy policy at a public address. Testing is not a sustainable state: it
admits only hand-added test users, caps them at 100, and expires consent every
seven days — a tester who signed in last week is silently asked again this week
and reads it as the app being broken.

So the policy became load-bearing for enrolment, which is why it arrives now
rather than at the "real users rather than invited testers" point where
`user-identity` had deferred it.

The obstacle: this app admits nobody without sign-in, so the obvious home for a
policy — a page inside it — looked unreachable to the visitor who most needs it.
Three options:

- **A second host.** GitHub Pages, one markdown file, and `dukeoferl.github.io`
  added to the authorised domains. It works, and it puts the statement about what
  this app keeps somewhere the app does not know about: two places to change, and
  the one that gets forgotten is the one a reader was pointed at.
- **A `/privacy` route in the app.** Streamlit's multipage support gives a real
  URL. It also gives the app a navigation structure it does not otherwise have,
  and every page then needs its own identity guard — which is the exact shape of
  the mistake that serves a page to someone who was refused.
- **The door.**

## Decision

**The policy is drawn by the app, at its own address, on the door and in the side
panel.** `messages.PRIVACY` holds the text and `web.draw_privacy()` draws it,
called from `draw_closed_door` and from the panel.

The door was never behind the sign-in wall — it *is* the unauthenticated page, and
it already loads for anyone at `https://scinumbers.streamlit.app`. Nothing had to be
exposed; what was needed was already public and merely empty. So the home page and
the privacy policy are the same URL, which Google accepts where that page carries
the policy.

**Under every door, not only the sign-in one.** A person refused at the door has
already had their address recorded by the attempt, so the moment they are told
"no" is the moment "what do you keep about me" is most reasonable — and that door
is the one with nobody on it to ask.

**Collapsed, and drawn in both places.** Offered rather than imposed: a notice a
reader must dismiss to proceed is a notice that gets dismissed. Both places
because neither audience can reach the other's copy — a visitor following the
consent screen's link is not signed in and sees only the door, and a reader who
signed in weeks ago never meets the door again.

The contact address in the text is a deliberate publication, which is why it is
its own constant rather than a word in a paragraph.

**Naming what receives the material is the part that was got wrong first**, and
it is worth recording how. The first draft named Auth0, Neon, OpenRouter and
Langfuse — four services the code calls explicitly — and missed three that it does
not: the **host** (everything runs on Streamlit Community Cloud), the provider
**behind** a provider (Auth0 federates to Google, so a reader signing in with a
Google account is handing Google the request), and the **stores that are not the
database** (the conversation's own sqlite checkpoints and the trail's log file,
both on the app's filesystem). The pattern is that a recipient reached by calling
an API gets named and one reached by running at all does not — and the omission
that mattered most was Google, the party whose consent screen this document exists
to satisfy.

## Trade-off accepted

**The policy is code, so changing it is a deployment.** A statement of this kind
should arguably be editable without a release. Against that: it is *about* what
the code does, and a copy that can drift from the code is a copy that will —
which is precisely the objection to the second host, and it applies to a database
row just as well.

**No `/privacy` URL.** Anyone linking to the policy links to the app and opens an
expander. Acceptable while the policy is one screen and the app is one page;
if either stops being true, the multipage route is still there, and the guard
question comes with it.

**The retention limit is still deferred.** The policy says records are kept for as
long as the prototype runs, which is true and is not a limit. There is nobody yet
whose records are old enough for one to bind; `user-identity` carries the
deferral, and the first person to ask is the case that decides it.
