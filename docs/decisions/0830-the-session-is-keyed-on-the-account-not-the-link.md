# ADR-0830: Under sign-in, the session is keyed on the account and not on the link

- **Status:** accepted
- **Date:** 2026-09-16
- **Pull request:** _pending — `feat/user-identity`_

## Context

The web driver has always identified a conversation by a token it keeps in two
places: `st.session_state`, which is per tab, and `?session=` in the URL, which
survives a reload and makes a session something a person can bookmark. The
token's own docstring says what it is: *recovered* from the URL, never decided
there, and **shared by anyone given the link**.

That was harmless while the token named nothing but a conversation. `add-user-identity`
made it the key for three more things — the identity stamped onto every trail
record, the dev panel's rows, and the deployment's session cap — and a key that
the reader supplies is the wrong key for all three. A code review found the
consequences, each of them silent:

- **Two accounts on one link overwrite each other.** A second reader opening a
  shared link signs in, the registry entry for that token becomes theirs, and the
  first reader's next question, its evidence and its ratings are recorded against
  the second reader's account and role. The first reader's sidebar still names
  them. The weighting queries in `sql/feedback.sql` then read those ratings under
  the wrong role with nothing in the data to show it.
- **A dev on a shared link sees another reader's trail.** The panel is scoped by
  the same token, and the token is not the reader's alone.
- **The OAuth redirect strands the session.** Streamlit's login callback and
  `st.logout` both return to the bare base URL, dropping the query string, so the
  token a visitor arrived with is gone on the rerun after sign-in. The
  pre-sign-in visit kept its place in the cap until the idle window passed, and
  the bookmark did not continue the conversation the reader had been in.

An earlier fix cleared the registry entry before each lookup, which stopped a
*refusal* being stamped with the previous account but left every case above
standing: the entry was still shared, and the tab that had already been admitted
short-cut the lookup and never re-asserted anything.

## Decision

**Where identity is configured and an account is signed in, the session key is
derived from the account** — `acct:` plus the first 16 hex characters of the
SHA-256 of the email — **and the URL token is not consulted.** Where identity is
not configured, the URL token remains the session, so a developer's machine keeps
today's bookmarkable behaviour exactly.

`web.effective_session(admission, url_session)` is the one place that decides
this, and everything downstream takes that key: the identity stamp, the panel's
sink, the cap's heartbeat, and the conversation thread the agent checkpoints
under.

Three consequences follow by construction rather than by care:

- Two accounts on one link get two sessions, so neither can see or overwrite the
  other's anything.
- The key survives the redirect that drops the query string, so a sign-in does
  not strand the session it came from.
- One account is one conversation, across tabs and reloads.

Two further changes belong to the same decision, because both were defects of
keying and ordering rather than of the model:

- **Identity is re-established on every rerun of an open page**
  (`web.establish_identity`), not once at sign-in. A session pruned for idleness
  loses its stamp; without this, the tab's next question was recorded with no
  account at all while the page still named one.
- **The cap counts at the door, not before it** — only sessions that have been
  admitted and will hold an agent. Counting earlier meant every abandoned
  sign-in page held a place for the idle window, and the redirect above
  guaranteed one such page per sign-in.

## Trade-off accepted

**A signed-in reader cannot hold two independent conversations, and cannot share
one.** Two tabs under one account are one session; a link handed to a colleague
starts them in their own. Both were possible before and neither is promised by
the spec. For an alpha whose whole point is attributing ratings to the person who
gave them, a conversation that follows the account is the behaviour wanted, and
the alternative — letting a reader mint conversations — is what made the
attribution forgeable.

**The key is derived, so it cannot be looked up backwards from the trail.** A
`session_id` of `acct:9f86d081…` does not say whose it is; `user_email` on the
same row does, which is the column written for exactly that purpose. The hash is
not a security measure — the email is in the next column — it is there so the
session id, which is shown in the page's caption and carried in the URL of a
screenshot, is not itself an address.

**Two tabs under one account share a checkpoint thread**, so they share the
model's memory while showing different on-screen transcripts — and, if both are
asked at once, write that thread concurrently. The transcript was already per tab
and the checkpoint already per session id; what changed is that the two tabs now
agree on the id, which before this was impossible. SQLite serialises the writes
and the turns interleave rather than corrupt, but a reader asking in two tabs at
once gets one conversation with both questions in it. Accepted: it is the honest
consequence of "one account is one conversation", and a reader who wants two
conversations has always had the option of two accounts. A fresh conversation is
a sign-out, or the operator clearing the thread.

**The cap is keyed on the tab, not on this** (ADR-0790). Counting conversations
would count accounts, and the cap is there to bound what the host actually
carries — one Streamlit session and one agent per tab.

**The URL still carries a token that no longer decides anything under sign-in.**
It is left in place because it is what an unconfigured deployment runs on, and
removing it there would cost the bookmark that a developer actually uses.
