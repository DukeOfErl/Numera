# user-identity Specification

## Purpose
Who a reader is, what they may do, and what the system keeps about them: sign-in
and enrolment, roles and a default-deny grant table that the agent never sees, a
capped credential of each tester's own, the panel that lets an operator see a
session's trail, and the rule that a deployment with no identity configured
behaves exactly as it did before.
## Requirements
### Requirement: A reader signs in before anything is shown, and identity comes from the provider

Where identity is configured, a visitor who is not signed in SHALL be offered
sign-in and nothing else: no question can be asked, no answer is produced or shown
for them, and no record of a question is written, because there is none. The one
exception is the recorded examples the sign-in door may play, which are recordings
of answers given to someone else and never an answer produced for the visitor. Who a reader is SHALL be
the account the identity provider asserts — the system does not ask for a name,
an email or a password of its own, and it accepts no credential from the reader.

More than one identity provider MAY be configured, and which of them a visitor is
offered SHALL be the deployment's to decide — a provider may be configured and not
offered, so that it can be restored without being re-established. A visitor SHALL
always be offered at least one way in: a door with no way through it is a refusal
that names no reason and admits no appeal. An account SHALL be the same account
whichever provider asserted it: the address is the identity, and a reader who
signs in through a second provider continues as the reader they were.

An account SHALL open the door only where the provider has verified its address.
An account whose address the provider has not verified, or says nothing about,
SHALL be refused and told that its address has to be verified first — a
different sentence from "not enrolled", because the reader's next step is
different. Nothing further is offered. A provider that lets anyone register an
address would otherwise let anyone sign in as an enrolled tester.

Signing out SHALL end the session: the identity is forgotten and the next visit
begins at sign-in.

A visitor SHALL be able to tell, from the page, whether they are signed in and as
whom. A person reading answers under an account they did not expect is a person
whose questions are being recorded against the wrong name.

#### Scenario: A visitor arrives without signing in
- **WHEN** identity is configured and a visitor has not signed in
- **THEN** the page offers sign-in
- **AND** no question can be asked and no answer is produced for the visitor
- **AND** no answer is displayed other than the door's recorded examples

#### Scenario: A visitor signs in
- **WHEN** the identity provider asserts an account
- **THEN** the page proceeds as that account
- **AND** the page shows which account it is

#### Scenario: A reader signs out
- **WHEN** a signed-in reader signs out
- **THEN** the identity is forgotten
- **AND** the next visit begins at sign-in

#### Scenario: Two providers are configured
- **WHEN** identity is configured with two providers and the deployment offers one of them
- **THEN** the page offers that one and not the other
- **AND** the provider that is not offered remains configured

#### Scenario: Nothing configured is offered
- **WHEN** identity is configured and none of its providers is one the deployment offers
- **THEN** the page offers every configured provider rather than none

#### Scenario: One provider is configured
- **WHEN** identity is configured with one provider, and it is offered
- **THEN** the page offers that one way in and no other

#### Scenario: The same address arrives through a second provider
- **WHEN** an enrolled account signs in through a provider other than the one it used before
- **THEN** the page proceeds as the same account, with the same role and the same conversation

#### Scenario: The provider has not verified the address
- **WHEN** a provider asserts an account and states that its address is not verified
- **THEN** the page says the address has to be verified first
- **AND** no question can be asked
- **AND** the sentence is not the one shown for an account that is not enrolled

#### Scenario: The provider says nothing about verification
- **WHEN** a provider asserts an account and carries no statement about whether its address is verified
- **THEN** the account is refused as unverified

#### Scenario: A verified address that is not enrolled
- **WHEN** a provider asserts a verified address the operator has not enrolled
- **THEN** the page says the account is not enrolled, as before

### Requirement: An account must be enrolled, and enrolment happens outside the application

Signing in SHALL NOT be enough. An account the operator has not enrolled SHALL be
refused, told that the account is not enrolled, and offered nothing further —
not the answers, not the feedback controls, not the ability to ask. Enrolment —
adding an account, assigning its role, issuing its credential — SHALL be an
operator action performed outside the application; there is no page for it, and
so no permission gates it.

A refused sign-in SHALL be recorded, with the account and the time, so the
operator can enrol someone who tried. This is the one thing kept about a person
who is not enrolled, and it is kept so that they can be.

When enrolment cannot be read, the refusal SHALL preserve what could not be read,
so that a misconfigured address, an unreachable host and a refused password are
distinguishable to whoever runs the app.

#### Scenario: A signed-in account is not enrolled
- **WHEN** an account the operator has not enrolled signs in
- **THEN** the page says the account is not enrolled
- **AND** no question can be asked
- **AND** the attempt is recorded with the account and the time

#### Scenario: An enrolled account signs in
- **WHEN** an account the operator has enrolled signs in
- **THEN** the page proceeds with that account's role

#### Scenario: An account is enrolled after being refused
- **WHEN** an account that was refused is enrolled and signs in again
- **THEN** the page proceeds
- **AND** nothing in the application was used to enrol it

#### Scenario: Enrolment cannot be read
- **WHEN** enrolment cannot be read for an account signing in
- **THEN** the refusal carries what could not be read

#### Scenario: Two unreadable enrolments have different causes
- **WHEN** enrolment is unreadable once because the address is misconfigured and once because the host cannot be reached
- **THEN** whoever runs the app can tell the two apart from what the refusal carried

### Requirement: Every enrolled account holds one role, and permissions are granted by a default-deny table

There SHALL be five roles — student, scientist, senior scientist, dev, admin —
and every enrolled account SHALL hold exactly one. Reading answers and giving
feedback are what enrolment grants; they are not permissions a role can lack, and
the table does not list them. A permission SHALL exist only where some role is
refused it, so that the refusal can be tested against a real role rather than
against nobody. Today that is one permission: `dev panel`, to see this session's
trail. What a role may do SHALL be stated in one grant table, and anything the
table does not grant SHALL be refused:

| Role | `dev panel` |
|---|---|
| student, scientist, senior scientist | refused |
| dev, admin | granted |

Where there is no identity, nothing SHALL be granted.

The three tester roles are identical here and differ in the weight their
judgements will later carry; dev and admin are identical here and differ by
label. That is deliberate: a table row nobody can test is a grant that drifts.

The role SHALL NOT reach the agent, and neither SHALL the account. What the agent
is handed about a question SHALL be identical whoever asks it. Where the agent
must one day know what is permitted — a question whose scope needs allowing, a
calculation — it SHALL be handed the permissions, never the role, so that an
answer can depend on what is allowed and never on who is asking.

The refusal SHALL belong to the action, not to the page that offers it. Whatever
asks the system to show the panel meets the same refusal; a page that hides a
control has not enforced anything.

#### Scenario: A tester reads and rates
- **WHEN** an enrolled account holding the student, scientist or senior scientist role asks a question and rates the answer
- **THEN** the question is answered and the rating is recorded

#### Scenario: A tester has no panel
- **WHEN** an account holding the student, scientist or senior scientist role views the page
- **THEN** no panel of trail records is present

#### Scenario: An operator has the panel
- **WHEN** an account holding the dev or admin role views the page
- **THEN** the panel of trail records is present

#### Scenario: No identity holds the permission
- **WHEN** the panel is requested with no identity
- **THEN** it is refused

#### Scenario: The agent is handed the same question whoever asks
- **WHEN** the same question is asked under two different roles
- **THEN** what the agent and the model are given is identical
- **AND** neither the account nor the role appears in it

#### Scenario: The refusal does not depend on who asks
- **WHEN** the panel is requested for an account whose role does not grant it, by any caller
- **THEN** it is refused the same way

### Requirement: An operator can see a session's own trail

The sidebar SHALL carry its views as a tab strip below the run status: the
entries behind the newest answer first, and this session's trail second. The
trail tab SHALL be shown to roles granted `dev panel` and SHALL be absent — not
disabled — for every other role; where it is absent the sidebar SHALL show no
strip at all, because a strip whose second tab is missing still tells a reader
there is a view they may not open. The trail tab SHALL show the records of this
session's last five questions as a table: when, which question, the event, and
its detail. This session's only: another tester's trail
is not this permission's to show, and scoping to the session is what keeps that
true without a second rule. Nothing shown here SHALL reach the model; these are
records of questions already answered.

A session with no questions yet SHALL show an empty section rather than none, so
a dev can tell "nothing yet" from "not permitted".

#### Scenario: A dev sees the trail tab
- **WHEN** an account granted `dev panel` views the page
- **THEN** the sidebar's tab strip is present below the run status
- **AND** its tabs are the entries first and the trail second

#### Scenario: A student's page has no such tab
- **WHEN** an account not granted `dev panel` views the page
- **THEN** no such tab exists on the page, disabled or otherwise
- **AND** the sidebar shows no tab strip at all

#### Scenario: The table names the question just asked
- **WHEN** an account granted `dev panel` asks a question
- **THEN** the trail tab's table includes that question's records

#### Scenario: A fresh session shows an empty tab
- **WHEN** an account granted `dev panel` opens a session and has asked nothing
- **THEN** the trail tab is present and empty

#### Scenario: Another session's trail is not shown
- **WHEN** two sessions are open under accounts granted `dev panel`
- **THEN** each panel shows only its own session's records

### Requirement: Each tester's questions are funded by a credential of their own, capped, and never shown to them

Every enrolled account SHALL be issued its own model-provider credential by the
operator, with its own spending cap that renews on a schedule, so that one
tester's questions cannot spend another's allowance and an exhausted cap recovers
without the operator's hand. The credential SHALL be looked up by the system and
SHALL never be displayed to, or accepted from, the reader.

A question whose credential has no allowance left SHALL end the way a spent key
already ends, naming the condition, and SHALL leave every other tester's
questions unaffected. An enrolled account with no credential issued SHALL be
refused asking, and told that no credential has been issued for it — an operator
action, not a reader's — and that reviewing, which needs no credential, remains open
to it.

#### Scenario: Two testers spend separately
- **WHEN** two enrolled accounts each ask a question
- **THEN** each question is charged to its own account's credential

#### Scenario: One tester's cap is exhausted
- **WHEN** an account's credential has no allowance left
- **THEN** its question ends naming the spent credential
- **AND** another account's question in the same deployment is answered as usual

#### Scenario: The credential is never shown
- **WHEN** a signed-in reader views any page of the application
- **THEN** no credential appears on it

#### Scenario: An enrolled account has no credential
- **WHEN** an enrolled account with no credential issued asks a question
- **THEN** the question is refused, naming the missing credential as the operator's to issue
- **AND** the refusal says that reviewing remains open to the account

### Requirement: Concurrent sessions are capped for the whole deployment, not per client address

The deployment SHALL refuse to open more than a configured number of sessions at
once. A visitor arriving at the cap SHALL be told to try again shortly; no
existing session SHALL be ended to make room. The cap SHALL NOT be keyed on the
client's network address: the address is supplied by the client and is not
evidence of anything.

The cap protects the host — memory, compute, the number of model calls in
flight — and not the budget, which every tester's credential already bounds.

#### Scenario: The cap is reached
- **WHEN** the configured number of sessions is already open and a visitor arrives
- **THEN** the visitor is told to try again shortly
- **AND** no open session is ended

#### Scenario: A session ends and room opens
- **WHEN** a session ends while the deployment is at its cap
- **THEN** the next visitor is admitted

### Requirement: What is kept about a person, and that they are told

Where identity is configured, every record written during a session SHALL carry
the account it was written under and the role that account held at the time,
recorded when the record is written and never looked up afterwards. A role
changed later SHALL NOT change records already written: a judgement's weight is
the weight it carried when given.

The interface SHALL state that what passes through the app is recorded, and why.
A standing side-panel notice carries the short form; it SHALL NOT be obliged to
enumerate the fields, because one long enough to list the question, the answer,
the entries, the account and the role is one a reader stops finishing — which
tells them nothing while appearing to tell them everything.

The interface SHALL also carry the full statement: what is recorded, what it is
used for, which services it passes through, and how long it is kept. It SHALL be
offered rather than imposed — a reader who wants it can open it, and a reader who
does not is not made to scroll past it — and it SHALL be readable **without
signing in**, because a visitor sent to it by a sign-in provider's consent screen
has not signed in and cannot be made to.

Every record about a person SHALL be attributable to that person, so that
deleting what is kept about them is possible, and the full statement SHALL name
how to ask for that. A retention limit is deferred: there is nobody yet whose
records are old enough for one to bind, and a rule written before its first case
is a rule written for the wrong case. Deferred is not unmentioned; when it is
decided it lands here.

#### Scenario: A signed-in reader's records carry their identity
- **WHEN** an enrolled account asks a question and rates the answer
- **THEN** every record of that question and rating carries the account and its role

#### Scenario: A role changed afterwards does not rewrite history
- **WHEN** an account's role is changed after it has asked and rated
- **THEN** the records already written still carry the role held at the time

#### Scenario: The interface says that what passes through it is recorded
- **WHEN** a reader views the page
- **THEN** the page states that exchanges in the app are logged, and why

#### Scenario: A person's records can be found
- **WHEN** the operator looks for everything kept about one account
- **THEN** every record about that account is found by the account alone

#### Scenario: A visitor who has not signed in reads what would be kept
- **WHEN** a visitor who is not signed in views the page
- **THEN** the full statement is reachable from that page
- **AND** it is closed until the visitor opens it

#### Scenario: A reader who is refused reads it too
- **WHEN** an account is refused at the door
- **THEN** the full statement is reachable from the page that refuses it

#### Scenario: A reader asks for what is kept about them to be deleted
- **WHEN** a reader reads the full statement
- **THEN** it names where to write to see what is held, or to have it deleted

### Requirement: A deployment with no identity configured behaves as before

Where identity is not configured, the application SHALL run exactly as it did
before identity existed: no sign-in, no roles, one credential from the
environment, records carrying no account. The page SHALL say that no sign-in is
configured, so that the state is visible rather than inferred. This is the
developer's machine, and refusing to run without an identity provider would make
the absence of sign-in an outage — the same rule the durable trail follows.

In that state the panel of trail records SHALL be shown, for as long as it
carries nothing but the session's own records: a session that is nobody's is the
developer's. This is a decision to revisit, not a settled one — before the panel
shows anything more sensitive than the session's own trail, whether an
unconfigured deployment still sees it SHALL be decided again.

#### Scenario: No identity is configured
- **WHEN** the application starts with no identity provider configured
- **THEN** questions can be asked without signing in
- **AND** records carry no account
- **AND** the page says no sign-in is configured

#### Scenario: The developer sees the panel
- **WHEN** no identity provider is configured
- **THEN** the panel of trail records is present

### Requirement: What the interface states about a credential is the provider's own figures, or nothing

What the interface states about a reader's credential SHALL be the provider's own
figures. Where the provider states a figure, the interface SHALL state that
figure unchanged rather than one derived from the provider's other figures. Where
the provider states neither a figure nor the figures it would follow from, the
interface SHALL say nothing rather than supply one.

#### Scenario: The provider names a renewal period
- **WHEN** the provider's answer about a credential names the period on which it renews
- **THEN** the interface states that period as the provider gave it

#### Scenario: The provider names no renewal period
- **WHEN** the provider's answer carries no renewal period, or none that can be read as one
- **THEN** the interface says nothing about renewal

#### Scenario: The provider answers about a credential
- **WHEN** the provider answers about a credential
- **THEN** every figure it gave is a figure the interface has to state

#### Scenario: The provider's remaining disagrees with its own cap and usage
- **WHEN** the provider gives a remaining figure that is not its cap less its usage
- **THEN** the interface states the provider's own remaining figure
- **AND** it does not state the figure worked out from the cap and the usage

#### Scenario: The provider states a cap and a usage but no remaining
- **WHEN** the provider states no remaining figure, and states the cap and the usage it would follow from
- **THEN** the interface states what is left, worked out from those two

### Requirement: Enrolling an account is one operator action, and it never issues an uncapped credential

Enrolling an account — issuing its credential, recording its address and role —
SHALL be one operator action outside the application, given the address, the
role, the credential's cap and the environment the account is enrolled into.
It SHALL issue a credential of the account's own, capped at the amount given and
renewing monthly, and SHALL record the account with that credential in the named
environment so that the account's next sign-in there proceeds.

The environment SHALL be named every time; there is no default. An enrolment
that names none SHALL be refused before anything is issued or recorded, and the
refusal SHALL say that the account has to be recorded where the deployment reads
and that no environment is assumed. An enrolment that names an environment that
does not exist SHALL be refused the same way, saying which do.

It SHALL refuse to issue a credential with no cap or a cap that is not positive:
the case for keeping credentials where they are kept rests on every one of them
being capped. It SHALL refuse an address that is already enrolled, and say so,
rather than issue a second credential or alter the row. If the account cannot
be recorded after the credential was issued, the credential SHALL be withdrawn,
so that a failed enrolment leaves no credential behind that nothing refers to;
if it cannot be withdrawn, the operator SHALL be told which one.

It SHALL record whatever is needed to withdraw that credential later. A
deployment that holds a credential it cannot revoke through any interface of its
own has no way to end access except by hand, and the thing needed is available
only at the moment of issue.

What it reports back SHALL name the account and its role and SHALL NOT show the
credential: the credential is looked up by the system and seen by nobody.

#### Scenario: A new tester is enrolled
- **WHEN** the operator enrols an address with a role and a positive cap
- **THEN** a credential capped at that amount, renewing monthly, is issued to that account
- **AND** the account is recorded with it
- **AND** the account's next sign-in proceeds with that role

#### Scenario: What is needed to withdraw the credential is kept
- **WHEN** an enrolment succeeds
- **THEN** what is recorded is enough to revoke that credential later
- **AND** it is not the credential itself

#### Scenario: No environment is named
- **WHEN** the operator enrols an address without naming the environment
- **THEN** no credential is issued and nothing is recorded
- **AND** the refusal says no environment is assumed and one has to be named

#### Scenario: The named environment does not exist
- **WHEN** the operator names an environment the deployment does not have
- **THEN** no credential is issued and nothing is recorded
- **AND** the refusal names the environments that do exist

#### Scenario: The cap is missing or not positive
- **WHEN** the operator enrols an address with no cap, a zero cap or a negative cap
- **THEN** no credential is issued and nothing is recorded
- **AND** the refusal names the cap

#### Scenario: The address is already enrolled
- **WHEN** the operator enrols an address that already has a row
- **THEN** no credential is issued and the row is unchanged
- **AND** the refusal says the address is already enrolled

#### Scenario: The account cannot be recorded
- **WHEN** a credential has been issued and the account cannot be recorded
- **THEN** the credential is withdrawn
- **AND** the operator is told that nothing was enrolled

#### Scenario: The credential cannot be withdrawn either
- **WHEN** a credential has been issued, the account cannot be recorded, and the credential cannot be withdrawn
- **THEN** the operator is told which credential is left behind

#### Scenario: The report shows no credential
- **WHEN** an enrolment succeeds
- **THEN** what is reported names the account, the role and the environment
- **AND** the credential does not appear in it

### Requirement: The operator can see who is stuck at the door, and only who is still stuck

There SHALL be a way for the operator to ask who is waiting on them: a reader whose
confirmation message never arrived and who has not since been verified, and a
verified account that is not enrolled. It SHALL be answerable without a browser and
without a person watching, so that it can be asked on a schedule.

Asking SHALL produce nothing at all when nobody is waiting. An answer that names an
empty queue is an answer that stops being read, and the next one that names a full
queue is then unread too. Where the question cannot be answered — the records cannot
be reached — that SHALL be said, loudly and as a failure, because silence otherwise
means "nobody is waiting" and would be indistinguishable from it.

A problem that has resolved SHALL NOT be reported. Whether a reader got past
verification SHALL be determined from what is recorded about them; whether an
account is enrolled SHALL be determined from the enrolment record itself and never
inferred from the reader returning, because a reader may be enrolled and never come
back, and an enrolled account with no credential cannot come back at all. A
withdrawn account SHALL count as not enrolled, as it does everywhere else.

How far back to look SHALL be the operator's to choose, and a span that could match
nothing SHALL be refused rather than answered with silence.

#### Scenario: Nobody is waiting
- **WHEN** the operator asks who is stuck and nobody is
- **THEN** nothing is reported at all

#### Scenario: Somebody never received their confirmation message
- **WHEN** a reader has said their confirmation message never arrived, and has not since been verified
- **THEN** they are reported, with how long they have been waiting

#### Scenario: They were verified afterwards
- **WHEN** a reader who said that has since been verified
- **THEN** they are not reported as waiting for it

#### Scenario: A verified account is not enrolled
- **WHEN** a verified account has no enrolment record
- **THEN** it is reported as waiting to be enrolled

#### Scenario: An account is enrolled and does not return
- **WHEN** an account is enrolled after being refused, and never signs in again
- **THEN** it is not reported as waiting to be enrolled

#### Scenario: A withdrawn account tries again
- **WHEN** an account whose enrolment has been withdrawn is refused
- **THEN** it is reported as waiting to be enrolled

#### Scenario: The records cannot be read
- **WHEN** the records cannot be reached
- **THEN** the failure is reported and is distinguishable from nobody waiting

#### Scenario: A span that can match nothing
- **WHEN** the operator asks over a span that cannot include anything
- **THEN** the request is refused rather than answered with silence

### Requirement: Withdrawing an account is one operator action, and it ends both halves of access

Withdrawing an account SHALL be one operator action outside the application,
given the address and the environment. It SHALL refuse the account from then on
**and** revoke the credential it was funded by: either alone leaves access open.
An account refused with a live credential can still spend it, because the
credential is held in the clear and was given to the person; a credential revoked
under an account still admitted reads to that person as the application being
broken rather than as access ending.

The environment SHALL be named every time, with no default, refused as an
enrolment with none is: withdrawing from the wrong environment reports success
while the account it was meant to refuse goes on working.

The account's records SHALL survive its withdrawal, attributed as they were. What
a person wrote is not undone by their access ending, and an operator SHALL still
be able to see that the account existed and what it held.

Where the two halves cannot both be done, **the account SHALL be refused and the
operator told the credential was not withdrawn**, naming it so a person can. The
order is not incidental: the state left behind by a partial withdrawal is the one
the system chooses, and a refused account with a live credential is recoverable
by hand while an admitted account with none is a person meeting an error they
cannot act on.

Withdrawing an account that is not there SHALL be refused, saying so, rather than
reported as a withdrawal.

#### Scenario: An account is withdrawn
- **WHEN** the operator withdraws an enrolled address in the environment it was enrolled into
- **THEN** the account is refused from then on
- **AND** its credential is revoked
- **AND** what it reports names both

#### Scenario: The records it wrote survive
- **WHEN** an account that has asked questions is withdrawn
- **THEN** the records it wrote keep the account and role they carried

#### Scenario: No environment is named
- **WHEN** the operator withdraws an address without naming the environment
- **THEN** nothing is refused and nothing is revoked
- **AND** the refusal says no environment is assumed and one has to be named

#### Scenario: The address is not enrolled here
- **WHEN** the operator withdraws an address that has no row in that environment
- **THEN** nothing is revoked
- **AND** the refusal says there is no such account there

#### Scenario: The credential cannot be revoked
- **WHEN** the account is refused and its credential cannot be revoked
- **THEN** the account stays refused
- **AND** the operator is told which credential is still live

#### Scenario: The account carries nothing that can revoke its credential
- **WHEN** an account recorded before withdrawal was possible is withdrawn
- **THEN** the account is refused from then on
- **AND** the operator is told the credential has to be revoked by hand

### Requirement: The operator is told when a reader is first seen, once for signing in and once for asking

There SHALL be a way for the operator to learn that a reader has arrived: the first
time an account is seen signing in, and the first time it is seen asking a question.
These are two separate firsts, and a reader who signs in and asks nothing SHALL be
reported for the first and never for the second. Where both firsts for the same
reader fall inside the span asked about, they SHALL be reported together, as one
message about one person.

"First" SHALL be determined from what is already recorded about the reader — an
event of that kind inside the span, and none earlier for the same account — and
SHALL NOT depend on any record kept about the asking itself, so that asking changes
nothing and can be asked as often as the operator likes. Two spellings of one
address that differ only in letter case SHALL be one reader.

It SHALL be answerable without a browser and without a person watching, so that it
can be asked on a schedule. Asking SHALL produce nothing at all when nobody new has
arrived: an answer that reports an empty hour is one that stops being read, and the
hour it names someone is then unread too. Where the question cannot be answered —
the records cannot be reached — that SHALL be said, loudly and as a failure,
because silence otherwise means "nobody new" and would be indistinguishable from it.

Because the span asked about is a fixed length, an account first seen in one span
MAY be reported again when the next span overlaps it, and an account first seen
while a scheduled ask was skipped MAY go unreported if the spans do not overlap
enough. The first is the cheaper error and SHALL be the one the operator's chosen
span leaves room for: a repeated notice costs a line, a missed first reader costs
the moment it was worth knowing.

The operator SHALL be able to name addresses that are never reported — their own,
and the accounts used for testing — so that the notices that remain are about
other people. How far back to look SHALL be the operator's to choose, and a span
that could match nothing SHALL be refused rather than answered with silence.

#### Scenario: Nobody new has arrived
- **WHEN** the operator asks who has been first seen and nobody has
- **THEN** nothing is reported at all

#### Scenario: A reader signs in for the first time
- **WHEN** an account is seen signing in for the first time, inside the span
- **THEN** it is reported as having signed in, and not as having asked anything

#### Scenario: A reader asks their first question
- **WHEN** an account is seen asking a question for the first time, inside the span
- **THEN** it is reported as having asked

#### Scenario: Both firsts fall in the same span
- **WHEN** an account is first seen signing in and first seen asking, both inside the span
- **THEN** one message about that account reports both

#### Scenario: A reader who was seen before is not reported again for it
- **WHEN** an account signs in inside the span, having signed in before the span
- **THEN** it is not reported as having signed in

#### Scenario: Seen signing in before, asking for the first time now
- **WHEN** an account signed in before the span and asks its first question inside it
- **THEN** it is reported as having asked, and not as having signed in

#### Scenario: One address in two spellings
- **WHEN** the same address is recorded once in lower case and once in capitals, the first before the span and the second inside it
- **THEN** it is one reader, who is not reported as new

#### Scenario: An address the operator excluded
- **WHEN** an account the operator named as never to be reported is first seen
- **THEN** it is not reported

#### Scenario: Asking changes nothing
- **WHEN** the operator asks twice over the same span with nothing new recorded between
- **THEN** both answers are the same, and nothing was recorded by asking

#### Scenario: The records cannot be read
- **WHEN** the records cannot be reached
- **THEN** the failure is reported and is distinguishable from nobody new

#### Scenario: A span that can match nothing
- **WHEN** the operator asks over a span that cannot include anything
- **THEN** the request is refused rather than answered with silence

### Requirement: Whatever asks on a schedule can read the records and change none of them

The means by which the question of who is new is asked on a schedule SHALL hold a
credential that can read the one record it needs — what has been recorded about
readers — and SHALL NOT be able to alter it or reach anything else, the enrolment
records included, since nothing in answering this needs them. It SHALL NOT hold a credential with authority over the
deployment itself, such as one that could create, change or remove the database.
Whoever grants the reading credential SHALL do so once, as an operator action, and
the means for doing so SHALL ship with the change that needs it.

#### Scenario: The scheduled credential tries to write
- **WHEN** the credential held for asking is used to change or remove a record
- **THEN** the attempt is refused by the database

#### Scenario: The scheduled credential tries to reach another table
- **WHEN** the credential held for asking is used to read anything other than what has been recorded about readers
- **THEN** the attempt is refused by the database

### Requirement: A new reader's arrival reaches the operator on a schedule, with no mail account of their own

A reader's first use SHALL reach the operator without the operator asking, within
the interval the schedule runs at plus the time a delivery takes. A run in which
nobody is new SHALL deliver nothing, with one exception: when seven days have passed
since the operator was last sent anything by this check, the run SHALL deliver one
message saying that the check found no new reader in that time. Delivery SHALL NOT
require the operator to hold credentials for a mail service. The message SHALL name
the reader by the address they signed in with, which is information the operator
already holds about them as an enrolled account; the deployment's privacy statement
SHALL NOT need to change because of it.

That second message exists so that a quiet week can be told apart from a check that
has stopped working, which silence alone cannot. It SHALL say what the check found
rather than claim that no reader exists — it reports an observation, and says that if
someone was expected, the check itself may be at fault — and it SHALL say how many
checks completed in those seven days and when the last one ran. The seven days SHALL
be counted from the last thing delivered to the operator, whatever it was, so that a
report of a new reader, or an earlier message of this kind, restarts them; and it
SHALL NOT be repeated until seven days have passed again. Where nothing has yet been
delivered to count from, it SHALL NOT be sent. It SHALL reach the operator the same
way a report of a new reader does, and a check that could not read the records SHALL
NOT send it, because it would then be saying something the check did not find.

#### Scenario: A new reader arrives
- **WHEN** a reader is first seen, and the next scheduled run happens
- **THEN** the operator receives a message naming them and what was first seen

#### Scenario: Nothing new in the interval
- **WHEN** a scheduled run finds nobody new, and the operator was sent something by this check less than seven days ago
- **THEN** the operator receives nothing from that run

#### Scenario: A quiet week
- **WHEN** a scheduled run finds nobody new, and seven days have passed since the operator was last sent anything by this check
- **THEN** the operator receives one message saying that the check found no new reader in that time

#### Scenario: What the quiet-week message says
- **WHEN** the quiet-week message is delivered
- **THEN** it says that the check found no new reader, how many checks completed in the seven days and when the last one ran, and that the check may be at fault if someone was expected, and it does not say that no reader exists

#### Scenario: A delivery of any kind restarts the seven days
- **WHEN** the operator is sent a report of a new reader, a test message, or a quiet-week message
- **THEN** no quiet-week message is sent until seven days after it

#### Scenario: It is not repeated run after run
- **WHEN** a quiet-week message has been delivered and later runs within the next seven days find nobody new
- **THEN** none of those runs delivers anything

#### Scenario: Nothing has been delivered yet
- **WHEN** a run finds nobody new and nothing has ever been delivered to the operator by this check
- **THEN** no quiet-week message is sent

#### Scenario: A check that could not read the records
- **WHEN** a run could not read the records
- **THEN** no quiet-week message is sent, and the failure is reported as a failure

### Requirement: The sign-in door may play a demo drawn from real answers

Where identity is configured, the sign-in door MAY play examples of a question being
asked and answered, so that a visitor can see what lies behind the door before
signing in.

Each example SHALL be a question actually put to the agent and the answer it gave.
The answer MAY be shortened for the door. Every figure it keeps SHALL be one the
corpus holds, any computed figure SHALL be recomputed from the figures kept, and
every edit SHALL be recorded beside the example where it can be traced to its run.
The examples SHALL be titled as a demo. However the question is typed, including
words taken back, pauses, and words retyped, the text it ends on SHALL be the question
the answer was recorded for, or a rewording of it. A reworded question SHALL be
recorded beside the example, together with the question actually asked.

A chart in an example SHALL be drawn from the figures the answer's run cited, and
never by a model, and SHALL say that charts are not yet something the application
does.

The door SHALL show citations as entry identifiers set apart from the prose, and every
example SHALL say that the application itself gives full citations.

The examples SHALL accept nothing from the visitor: there is no input a question
could go through, and nothing a visitor does to them reaches the agent or writes a
record. They SHALL be played on the sign-in door only, not on a door that refuses an
account, whose sentence is what that reader needs, and not to a reader who has
signed in. A visitor who has asked their browser for reduced motion SHALL be shown
the examples without animation.

#### Scenario: A visitor at the sign-in door sees the demo
- **WHEN** identity is configured and a visitor has not signed in
- **THEN** the door plays a question and its answer under a heading that presents it as a demonstration of the app
- **AND** no question can be asked and no record is written

#### Scenario: An example shows a chart
- **WHEN** an example's answer includes a chart
- **THEN** every mark in it sits where its value places it on the chart's own axis
- **AND** every value drawn is one the run cited, as the corpus stores it
- **AND** the example says charts are upcoming

#### Scenario: Citations are set apart, and the full ones are elsewhere
- **WHEN** an example's answer cites entries
- **THEN** the identifiers are drawn apart from the prose, a run of them together
- **AND** the example ends by saying the application gives full citations

#### Scenario: A shortened answer says what was changed
- **WHEN** an example's answer differs from the one its run recorded
- **THEN** what was cut, reworded or recomputed is recorded beside the example

#### Scenario: A reworded question
- **WHEN** the door shows a question worded differently from the one the answer was recorded for
- **THEN** the question actually asked is recorded beside the example, in its edits

#### Scenario: The typed question is the one that was answered
- **WHEN** an example types a question, takes words back and types others
- **THEN** the text it ends on is the question the shown answer was recorded for

#### Scenario: A refused account sees no examples
- **WHEN** a signed-in account is refused at the door, as unverified or not enrolled
- **THEN** the door plays no examples

#### Scenario: A signed-in reader sees no examples
- **WHEN** an enrolled account is admitted
- **THEN** the page plays no examples

#### Scenario: A visitor who asked for less motion
- **WHEN** the visitor's browser asks for reduced motion
- **THEN** each example is shown whole, without typing or streaming

