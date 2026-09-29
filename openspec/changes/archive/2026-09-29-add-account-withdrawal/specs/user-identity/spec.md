## ADDED Requirements

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

## MODIFIED Requirements

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
