## ADDED Requirements

### Requirement: What the interface states about a credential is the provider's own figures, or nothing

What the interface states about a reader's credential SHALL be the provider's own
figures, or nothing. Where the provider gives a figure, that figure is shown
unchanged; where the provider gives none, the interface says nothing rather than
deriving one.

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

## MODIFIED Requirements

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
