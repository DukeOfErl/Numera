## Purpose

What a reader may record about an answer they have been given, what must be kept
alongside it so the judgement can be understood later, and what the system must
not do with it. Feedback is the only judgement available here that is not
mechanical: every other check can say an answer cited nothing or compared
incompatible units, and none can say it was wrong in a way that mattered.

## ADDED Requirements

### Requirement: A reader can rate an answer, and rating is never required

Every answer SHALL offer the reader a way to record approval or disapproval of
it. Recording one SHALL be optional, and an answer that is never rated SHALL
behave exactly as it does today.

It SHALL be offered at the foot of the answer's prose, and SHALL NOT be placed
after the entries presented alongside it. A reader forms a view at the end of the
prose, and that is where the control should be waiting; a control below the
entries is one they have to go looking for at exactly that moment.

A rating SHALL be recorded at the moment it is given, and SHALL NOT depend on the
reader completing any further step. Most people who rate will do nothing else,
and a design that waits for a second action to commit the first collects nothing
from them.

#### Scenario: An answer is given
- **WHEN** an answer is shown to a reader
- **THEN** a way to record approval or disapproval is offered with it
- **AND** it is offered below that answer's prose, not below the entries shown alongside it

#### Scenario: A reader rates and does nothing further
- **WHEN** a reader records a rating and takes no further action
- **THEN** the rating is kept

#### Scenario: A reader ignores the rating entirely
- **WHEN** a reader reads an answer without rating it
- **THEN** nothing is recorded for that answer
- **AND** the answer, the conversation and the next question are unaffected

### Requirement: A rating may carry a comment, offered only once an answer has been disapproved of

A reader who has recorded disapproval of an answer SHALL be able to add free text
about it. That opportunity SHALL NOT be presented before a rating has been given:
an empty text box beside every answer is a standing demand on the reader's
attention, and the rating is the cheap signal that most people will give.

It SHALL NOT be presented after approval either. The invitation asks what was
wrong, which is a question nobody can answer about an answer they have just
approved — a reader who approves and is then asked what went wrong reads it as
the click not having registered. Approval is the cheap signal, and the point of
it being cheap is that it asks for nothing further. Free text about an answer
that was right is not what this exists to collect.

Sending a comment SHALL take one action of the reader's. A text box whose send
must be pressed once to commit the text and again to send it loses the comments
of everyone who presses once and believes they are done — and those are comments
from readers who had already decided to write, the most expensive ones to lose.

The invitation to comment SHALL ask the reader to name the identifier of any
entry they believe is wrong. Per-entry rating is not built, and what readers
choose to write about entries is the evidence for whether it should be.

A rating, once recorded, SHALL be final for that answer, and the interface SHALL
show it as settled rather than appearing to invite a change. Two contradicting
ratings of one answer would need a rule about which counts, the store is
append-only so both would persist, and no reader has asked to change their mind.

A comment in progress SHALL NOT be lost when the page is redrawn. The page is
redrawn on every interaction, including the reader's own first keystroke
elsewhere, so a draft held only by the interface is a draft that disappears while
being written.

#### Scenario: A reader has not yet rated
- **WHEN** an answer has not been rated
- **THEN** no means of commenting on it is presented

#### Scenario: A reader disapproves of an answer
- **WHEN** a reader records disapproval
- **THEN** they are invited to add free text about that answer
- **AND** the invitation asks them to name the identifier of any entry they believe is wrong

#### Scenario: A reader approves of an answer
- **WHEN** a reader records approval
- **THEN** no means of commenting on it is presented
- **AND** the approval is recorded and acknowledged

#### Scenario: A reader writes a comment and sends it
- **WHEN** a reader has written a comment and performs the action that sends it
- **THEN** the comment is recorded without any further action from them

#### Scenario: A reader tries to change a rating already given
- **WHEN** an answer has been rated and the reader attempts to rate it again
- **THEN** the recorded rating does not change
- **AND** no second rating is recorded for that answer

#### Scenario: The page is redrawn while a comment is being written
- **WHEN** a reader has written part of a comment and the page is redrawn
- **THEN** the text they have written so far is still there

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

A rating SHALL record space for the person who gave it, left empty while the
system has no notion of who that is. A record written before identity exists is
the one that can never be attributed afterwards.

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

### Requirement: Recording a rating never disrupts the reader

A failure to record a rating SHALL NOT raise an error to the reader, interrupt
the conversation, or prevent further questions. The reader SHALL be told that
their rating was received.

This follows the same policy as the deterministic trail and for the same reason:
the cost of losing one rating is one missing row, and the cost of failing closed
is a reader blocked from asking anything further by a telemetry fault. The
contrast with the spend limits, which must fail closed, is deliberate.

A rating SHALL NOT be recorded more than once for one act of rating. The page is
redrawn whenever the reader interacts with it, and a redraw is not a new
judgement.

#### Scenario: The store cannot be written to
- **WHEN** a reader rates an answer and the rating cannot be recorded
- **THEN** no error is shown to the reader
- **AND** the conversation continues to accept questions

#### Scenario: The page is redrawn after a rating
- **WHEN** a reader rates an answer and then interacts with the page again
- **THEN** the rating is not recorded a second time

#### Scenario: A rating is given
- **WHEN** a reader records a rating
- **THEN** the interface acknowledges it

### Requirement: The model is never shown a rating or a comment

Neither a rating nor the text accompanying it SHALL reach the model. It SHALL NOT
be added to the conversation, included in a prompt, or carried in the state a
later question is answered from.

Stated as what the model is *shown* rather than as how it behaves, because the
second cannot be checked. "The next answer is what it would have been anyway" is
a claim about a counterfactual run of a non-deterministic system; no test can
assert it, and a requirement nothing can fail is a guarantee in appearance only.
What can be established is whether the rating is in the material the model
received.

Three reasons, and the first alone is sufficient:

- **A comment is text a stranger wrote.** Everything else the model is given is
  either the corpus or a question; feedback is the one input authored to be read
  by the people running the system. Text asking the model to disregard its
  instructions must not arrive by this route, in a tool whose wrong answers look
  no different from its right ones.
- **An agent that reacts to disapproval answers differently depending on who is
  watching**, and its recorded trail stops describing what it does.
- **A reader criticising an answer is addressing the people who built it.** Using
  that text as model input is not what they were offered.

A rating SHALL NOT cause the answer to be retried, revised, re-retrieved or
withdrawn.

#### Scenario: An answer is rated down
- **WHEN** a reader records disapproval of an answer
- **THEN** the answer shown is unchanged
- **AND** no further retrieval or model call is made on account of the rating

#### Scenario: A later question follows a rating and a comment
- **WHEN** an answer is rated and commented on, and a further question is asked
- **THEN** neither the rating nor the comment appears in what the model is shown
- **AND** neither appears in the stored conversation the question is answered from

#### Scenario: A comment contains an instruction addressed to the model
- **WHEN** a comment is written that reads as an instruction to the model
- **THEN** it is stored as given
- **AND** it is not included in any prompt
