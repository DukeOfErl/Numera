## MODIFIED Requirements

### Requirement: A reader signs in before anything is shown, and identity comes from the provider

Where identity is configured, a visitor who is not signed in SHALL be offered
sign-in and nothing else: no question can be asked, no answer is shown, and no
record of a question is written, because there is none. Who a reader is SHALL be
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
- **AND** no question can be asked and no answer is displayed

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
