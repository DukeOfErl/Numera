## MODIFIED Requirements

### Requirement: A rating names the question it is about, and outlives the session

Every rating SHALL record which question it concerns, using the same identifier
the deterministic trail records for that question, so a rating can be read
alongside what the question actually retrieved.

A rating SHALL NOT be identified by its position in the conversation. Position is
not stable: a conversation reloaded from its identifier begins counting again
while the conversation itself continues, so the same position names two different
questions.

Ratings SHALL outlive the process that collected them, and SHALL be retained
where a restart or redeployment does not discard them. A rating that is lost on
the next deploy is not evidence.

A rating SHALL record the person who gave it and the role they held at the time,
where the system knows who that is, and SHALL leave that space empty where it
does not. Both are written when the rating is written and never looked up
afterwards: a role changed later does not change the weight a rating carried
when it was given. A record written before identity exists is the one that can
never be attributed afterwards, which is why the space was kept from the start.

#### Scenario: A rating is recorded
- **WHEN** a reader rates an answer
- **THEN** the record names the question that answer came from
- **AND** that identifier is the one the question's trail records

#### Scenario: Two answers in one conversation are rated
- **WHEN** a reader rates two different answers in the same conversation
- **THEN** the two records name different questions

#### Scenario: A conversation is reopened and an answer rated
- **WHEN** a conversation is reopened from its identifier and a new answer is rated
- **THEN** the record does not collide with a rating from before the reopening

#### Scenario: The application is redeployed
- **WHEN** the application is restarted or redeployed
- **THEN** ratings recorded beforehand remain readable

#### Scenario: A signed-in reader rates an answer
- **WHEN** identity is configured and an enrolled account rates an answer
- **THEN** the record carries the account and the role it held at the time

#### Scenario: The rater's role changes afterwards
- **WHEN** an account's role is changed after it has rated
- **THEN** the rating still carries the role held when it was given
