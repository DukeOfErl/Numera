## Purpose

Who a reader is, what they may do, and what the system keeps about them: sign-in
and enrolment, roles and a default-deny grant table, a capped credential of each
tester's own, the panel that lets an operator see a session's trail, and the rule
that a deployment with no identity configured behaves exactly as it did before.

## ADDED Requirements

### Requirement: A reader signs in before anything is shown, and identity comes from the provider

Where identity is configured, a visitor who is not signed in SHALL be offered
sign-in and nothing else: no question can be asked, no answer is shown, and no
record of a question is written, because there is none. Who a reader is SHALL be
the account the identity provider asserts — the system does not ask for a name,
an email or a password of its own, and it accepts no credential from the reader.

Signing out SHALL end the session: the identity is forgotten and the next visit
begins at sign-in.

A visitor SHALL be able to tell, from the page, whether they are signed in and as
whom. A person reading answers under an account they did not expect is a person
whose questions are being recorded against the wrong name.

#### Scenario: A visitor arrives without signing in
- **WHEN** identity is configured and a visitor has not signed in
- **THEN** the page offers sign-in
- **AND** no question can be asked and no answer is displayed

#### Scenario: A visitor signs in
- **WHEN** the identity provider asserts an account
- **THEN** the page proceeds as that account
- **AND** the page shows which account it is

#### Scenario: A reader signs out
- **WHEN** a signed-in reader signs out
- **THEN** the identity is forgotten
- **AND** the next visit begins at sign-in

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

### Requirement: Every enrolled account holds one role, and permissions are granted by a default-deny table

There SHALL be five roles — student, scientist, senior scientist, dev, admin —
and every enrolled account SHALL hold exactly one. There SHALL be three
permissions: `read` (ask questions and see answers), `feedback` (rate an answer
and comment on it), and `dev panel` (see this session's trail). What a role may
do SHALL be stated in one grant table, and anything the table does not grant
SHALL be refused. The table is:

| Role | `read` | `feedback` | `dev panel` |
|---|---|---|---|
| student, scientist, senior scientist | granted | granted | refused |
| dev, admin | granted | granted | granted |

A signed-in account with no role SHALL hold no permission, including `read`.

A permission SHALL exist only where the application has an action to refuse. The
three tester roles are identical here and differ in the weight their judgements
will later carry; dev and admin are identical here and differ by label. That is
deliberate: a table row nobody can test is a grant that drifts.

The refusal SHALL belong to the action, not to the page that offers it. Whatever
asks the system to answer a question, record a rating or show the panel meets the
same refusal; a page that hides a control has not enforced anything.

#### Scenario: A tester reads and rates
- **WHEN** an account holding the student, scientist or senior scientist role asks a question and rates the answer
- **THEN** the question is answered and the rating is recorded

#### Scenario: A tester has no panel
- **WHEN** an account holding the student, scientist or senior scientist role views the page
- **THEN** no panel of trail records is present

#### Scenario: An operator has the panel
- **WHEN** an account holding the dev or admin role views the page
- **THEN** the panel of trail records is present

#### Scenario: An account without a role is refused everything
- **WHEN** a signed-in account holds no role
- **THEN** it may not ask, may not rate, and has no panel

#### Scenario: The refusal does not depend on who asks
- **WHEN** an action is requested for an account whose role does not grant it, by any caller
- **THEN** the action is refused the same way

### Requirement: An operator can see a session's own trail

A sidebar section, below the run status, SHALL be shown to roles granted `dev
panel` and SHALL be absent — not disabled — for every other role. It SHALL show
the trail records of this session's last five questions as a table: when, which
question, the event, and its detail. This session's only: another tester's trail
is not this permission's to show, and scoping to the session is what keeps that
true without a second rule. Nothing shown here SHALL reach the model; these are
records of questions already answered.

A session with no questions yet SHALL show an empty section rather than none, so
a dev can tell "nothing yet" from "not permitted".

#### Scenario: A dev sees the section
- **WHEN** an account granted `dev panel` views the page
- **THEN** the section is present below the run status

#### Scenario: A student's page has no such section
- **WHEN** an account not granted `dev panel` views the page
- **THEN** no such section exists on the page, disabled or otherwise

#### Scenario: The table names the question just asked
- **WHEN** an account granted `dev panel` asks a question
- **THEN** the section's table includes that question's records

#### Scenario: A fresh session shows an empty section
- **WHEN** an account granted `dev panel` opens a session and has asked nothing
- **THEN** the section is present and empty

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
action, not a reader's.

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

The statement of what is kept, already shown in the interface, SHALL name the
account and the role alongside the question, the answer and the entries — one
statement, not two.

Every record about a person SHALL be attributable to that person, so that
deleting what is kept about them is possible. The request path for deletion, and
any retention limit, are deferred: there is nobody yet to request either, and a
rule written before its first case is a rule written for the wrong case. Deferred
is not unmentioned; when either is decided it lands here.

#### Scenario: A signed-in reader's records carry their identity
- **WHEN** an enrolled account asks a question and rates the answer
- **THEN** every record of that question and rating carries the account and its role

#### Scenario: A role changed afterwards does not rewrite history
- **WHEN** an account's role is changed after it has asked and rated
- **THEN** the records already written still carry the role held at the time

#### Scenario: The interface names what is kept
- **WHEN** a signed-in reader views the page
- **THEN** the statement of what is kept names the account and the role

#### Scenario: A person's records can be found
- **WHEN** the operator looks for everything kept about one account
- **THEN** every record about that account is found by the account alone

### Requirement: A deployment with no identity configured behaves as before

Where identity is not configured, the application SHALL run exactly as it did
before identity existed: no sign-in, no roles, one credential from the
environment, records carrying no account. The page SHALL say that no sign-in is
configured, so that the state is visible rather than inferred. This is the
developer's machine, and refusing to run without an identity provider would make
the absence of sign-in an outage — the same rule the durable trail follows.

In that state the panel of trail records SHALL be shown: a session that is
nobody's is the developer's.

#### Scenario: No identity is configured
- **WHEN** the application starts with no identity provider configured
- **THEN** questions can be asked without signing in
- **AND** records carry no account
- **AND** the page says no sign-in is configured

#### Scenario: The developer sees the panel
- **WHEN** no identity provider is configured
- **THEN** the panel of trail records is present
