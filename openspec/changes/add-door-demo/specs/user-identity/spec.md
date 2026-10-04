## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: The sign-in door may play a demo drawn from real answers

Where identity is configured, the sign-in door MAY play examples of a question being
asked and answered, so that a visitor can see what lies behind the door before
signing in.

Each example SHALL be a question actually put to the agent and the answer it gave.
The answer MAY be shortened for the door. Every figure it keeps SHALL be one the
corpus holds, any computed figure SHALL be recomputed from the figures kept, and
every edit SHALL be recorded beside the example where it can be traced to its run.
The examples SHALL be titled as a demo. However the question is typed, including
words taken back and retyped, the text it ends on SHALL be the question the answer
was recorded for.

A chart in an example SHALL be drawn from the figures the answer's run cited, and
never by a model, and SHALL say that charts are not yet something the application
does.

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
- **AND** the answer says charts are upcoming

#### Scenario: A shortened answer says what was changed
- **WHEN** an example's answer differs from the one its run recorded
- **THEN** what was cut, reworded or recomputed is recorded beside the example

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
