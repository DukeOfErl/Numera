## MODIFIED Requirements

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
