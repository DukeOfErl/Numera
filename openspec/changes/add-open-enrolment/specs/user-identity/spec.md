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
role and the credential's cap. It SHALL issue a credential of the account's own,
capped at the amount given and renewing monthly, and SHALL record the account
with that credential so that the account's next sign-in proceeds.

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
- **THEN** what is reported names the account and role
- **AND** the credential does not appear in it
