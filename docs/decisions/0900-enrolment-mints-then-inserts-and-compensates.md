# ADR-0900: Enrolment mints, then inserts, and withdraws the credential if it cannot

- **Status:** accepted
- **Date:** 2026-09-18
- **Pull request:** _pending — `feat/open-enrolment`_

## Context

ADR-0780 left a helper script for minting keys and inserting rows as "a later
convenience, not part of this decision", and `docs/roadmap.md` §WP3 repeated it.
Until now enrolling a tester was three steps in three consoles: list the address
as a Google test user, mint a capped key at OpenRouter, insert the row in Neon.
ADR-0880 removes the first. This decision is about the other two.

They are two systems with no transaction between them, so a failure between them
leaves something behind, and which something is a choice.

The database is also a choice. A Neon project has one branch per environment —
`dev` for a laptop, `alpha` for the deployed app's testers — each with its own
URL, and `.streamlit/secrets.toml.example` allows exactly one URL per checkout,
the branch that checkout writes to. On an operator's laptop that is `dev`.

## Decision

**`scinumbers-enrol EMAIL ROLE --limit-usd N --branch NAME`**, implemented in
`enrol.py` with the Neon control-plane calls in `neon.py`.

**Mint, then insert, and revoke if the insert fails.** The other order writes a
row with no key, which is a door of its own (`NO_CREDENTIAL`): the tester signs
in and is told no credential has been issued, while the operator sees an account
that looks deliberately keyless rather than half-made. A minted key nobody refers
to costs nothing while it exists and is withdrawn on the way out. Where the
withdrawal also fails, `KeyLeftBehind` names the hash — the one outcome that
leaves work for a person, so it must not be silent.

**Every refusal is in `enrol()`, not in `main()`.** The command keeps the
wording; the operation keeps the refusal, so a test or a script an operator
writes meets the same guards. The one with teeth: **nothing issues an uncapped
credential**, because ADR-0780's case for storing keys in the clear rests
entirely on every key having a cap. A cap that is missing, zero or negative is
refused before anything is called.

**Verified against the live provider on 2026-09-26.** One enrolment of a
throwaway address into the `dev` branch with a `$0.01` cap: the key was minted,
the row was written, and `GET /api/v1/keys` then reported
`"limit": 0.01, "limit_reset": "monthly"` for it. So **OpenRouter honours
`limit_reset` on create**, and the `PATCH` retry below has never run against the
real provider — it is exercised by tests and by seeded mutants, and is
unexercised in anger. Recorded because "there is a retry" and "the retry has been
seen to work" are different claims, and only the first is true here. Whether it
earns its twenty lines is worth asking again if OpenRouter's behaviour is stable
for a while; the case for keeping it is that a provider which stopped honouring
the field would otherwise block every enrolment rather than cost one extra call.

The same run confirmed the operator path end to end: an organisation-scoped Neon
API key reaches both control-plane endpoints with no `org_id`, and the
`--database` and `--role-name` defaults (`neondb`, `neondb_owner`) suit a
default project.

**The echo is checked.** A credential whose returned `limit` is not the amount
asked for is revoked rather than handed out — what is verified is not that the
call succeeded but that the key has the property the storage decision depends on.
A `limit_reset` the create call did not honour is retried once as a `PATCH` —
which, per the live run above, it has not yet had to be; a `limit` that comes
back wrong is not retried, because a provider disagreeing about the number is not
a provider to argue with.

**The branch is named every time and has no default.** Without `--branch` the
command refuses before doing anything, with a sentence saying the row has to land
where the deployed app reads and that none is assumed. The name is resolved
through Neon's API — `GET /projects/{id}/branches?search=` then `GET
.../connection_uri` — and `search` matches partially, so the match is narrowed to
**exactly one branch whose name is equal**; none or several is a refusal listing
what was found. The command does not read `.streamlit/secrets.toml`.

**Nothing prints the credential.** Not on success, not in any refusal; the hash
appears only in `KeyLeftBehind`, where a person needs it to revoke by hand.

## Trade-off accepted

**Two more secrets in the operator's shell** — a Neon API key and the project id,
beside the OpenRouter management key. The Neon key can read every branch's
password. It lives in a shell for one command and is never stored beside the app,
which is the same standing the management key already had. The alternative was a
pasted database URL: no second secret, and nothing at all stopping the `dev` URL
being pasted, which is the failure this design exists to make impossible.

**A default branch would be more convenient and is refused on purpose.** The
operator will not be sure which environment is which exactly when they are adding
a tester, and a default is wrong precisely then. The symptom of getting it wrong
appears somewhere else entirely: the tester is told they are not enrolled while
the operator is looking at their row.

**No withdrawal, re-keying or role change from the command.** Each is an `update`
with a template in `sql/accounts.sql`. This command does the one thing that needs
two systems to agree.

**A key can still be left behind** — minted, then neither recorded nor revoked,
if OpenRouter is unreachable at exactly that moment. It is capped, it is named in
the error, and it can be revoked from the dashboard. That is the residue of
having no transaction across two services, and it is bounded rather than removed.

## What was measured

Five defects seeded into a copy against a green baseline of 119:

| Mutant | Killed |
|---|---|
| `>= 0` in place of `> 0` for the cap | `test_a_credential_is_never_issued_without_a_cap[0]`, `[0.0]` — and rightly not `[-1]` or `[None]` |
| the revoke removed from the insert-failure path | all three of the could-not-be-written tests |
| the cap echo unchecked | `test_a_cap_that_comes_back_wrong_is_revoked_and_refused` |
| nothing minted at all | four, including the happy path |
| `import streamlit` in `enrol.py` | `test_only_the_web_driver_knows_the_web_framework` |

A read-only verifier then seeded against the same module and found four things
the list above missed. All are closed, and each fix was re-seeded:

| Mutant | Was | Now |
|---|---|---|
| `_same_amount` with strict `==` | **survived the whole suite** | killed by an echo of `"5"` |
| an echo that is not a number at all | never executed | killed |
| `_revoke_quietly`'s failure path | never executed, behind a docstring claiming the original failure is not hidden | killed |
| every `enrol`-level refusal through `main` | never executed | killed |

The survivor is the one worth remembering: `5 == 5.0` in Python, so a fixture
built from ints and floats cannot tell `float(a) == float(b)` from `a == b`, and
a function whose whole stated purpose is comparing across JSON's number types had
no test that varied the type. The same pass also caught a test whose doubles were
narrower than its own assertion — deleting the `--branch` guard let an unmarked
test out to the real Neon control plane.

A high-effort code review then found two holes in the compensation guarantee
itself, both now closed and seeded:

- **A hash returned with no key** raised `MintFailed` without revoking, although
  the handle needed to revoke was in hand. A capped credential existed at the
  provider and this process was the only thing that knew its name.
- **A `PATCH` that could not be sent** escaped `mint` with the key still live.
  The two *checked* failures revoked; the transport failure between them did
  not, and `enrol` could not compensate because no `Minted` was ever returned.

The pattern is worth naming: both paths were written as answers to *what the
provider said*, and neither covered *the call failing to complete*. A guarantee
about undoing side effects has to hold for how the call fails, not only for what
it answers.

The same review moved the cap and role checks ahead of the branch resolution.
They belong to `enrol` and `enrol` still runs them; the command runs the same
expression first so that `--limit-usd 0` does not spend two live control-plane
calls before anything says no. Diagram 3c had drawn that order before the code
did.

**The first harness could not have found any of this, and said so only because a
canary died.** It copied `tests/` but set no `PYTHONPATH`, so the static
dependency guard — which reads `parents[1]/src` by path — saw the seeded copy
while every runtime test imported the real package. Four mutants "survived" and
the table was clean. The streamlit seed dying while the others did not is what
exposed it. The harness now requires both, and aborts rather than print a table
it did not earn.
