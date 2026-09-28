## MODIFIED Requirements

### Requirement: A reader signs in before anything is shown, and identity comes from the provider

Where identity is configured, a visitor who is not signed in SHALL be offered
sign-in and nothing else: no question can be asked, no answer is shown, and no
record of a question is written, because there is none. Who a reader is SHALL be
the account the identity provider asserts — the system does not ask for a name,
an email or a password of its own, and it accepts no credential from the reader.

More than one identity provider MAY be offered, and the visitor SHALL be offered
each configured provider as its own way in. An account SHALL be the same account
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
- **WHEN** identity is configured with two providers and a visitor has not signed in
- **THEN** the page offers each provider as its own way in

#### Scenario: One provider is configured
- **WHEN** identity is configured with one provider
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

## ADDED Requirements

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

What it reports back SHALL name the account and its role and SHALL NOT show the
credential: the credential is looked up by the system and seen by nobody.

#### Scenario: A new tester is enrolled
- **WHEN** the operator enrols an address with a role and a positive cap
- **THEN** a credential capped at that amount, renewing monthly, is issued to that account
- **AND** the account is recorded with it
- **AND** the account's next sign-in proceeds with that role

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
