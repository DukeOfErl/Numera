## Purpose

What the operator can see about the alpha — use, cost, how questions ended, what
readers thought, who is stuck at the door, and whether the recording itself is
working — and what that view is allowed to read, change and contact while
showing it.

## ADDED Requirements

### Requirement: The view reads the trail and who is enrolled, never a credential, and changes nothing

The monitoring view SHALL read only the trail and, of the account records, which
addresses are enrolled and whether each is disabled. It SHALL NOT be able to read
the credentials held with an account, and it SHALL NOT be able to insert, update
or delete any row anywhere.

Both limits SHALL be enforced by the database, through the identity the view
connects as, and not only by the queries the view happens to issue. A view that
is read-only because nobody wrote a write is read-only until somebody does.

#### Scenario: The view's identity tries to write
- **WHEN** a write of any kind is attempted under the identity the view connects as
- **THEN** the database refuses it
- **AND** no row is changed

#### Scenario: The view's identity tries to read account credentials
- **WHEN** a read of the credentials held with an account is attempted under the identity the view connects as
- **THEN** the database refuses it

#### Scenario: The view's identity reads who is enrolled
- **WHEN** the view asks which addresses are enrolled and whether each is disabled
- **THEN** the database answers

#### Scenario: The operator uses the view
- **WHEN** the operator opens the view and uses every part of it
- **THEN** the trail holds exactly the rows it held before

### Requirement: The view runs on the operator's machine and names the branch it reads

The view SHALL be started by the operator on their own machine and SHALL NOT
accept connections from any other machine. It shows readers' email addresses and
the comments they wrote, and it has no sign-in of its own.

The operator SHALL name the database branch to read when starting the view, and
there SHALL be no default. The branch being read SHALL be shown on every part of
the view. Development rows read as the alpha's would be a wrong picture that
looks ordinary.

#### Scenario: Started without a branch
- **WHEN** the operator starts the view without naming a branch
- **THEN** the view does not start
- **AND** it says that a branch must be named

#### Scenario: Started with a branch
- **WHEN** the operator starts the view naming a branch
- **THEN** that branch's name is shown on the view

#### Scenario: Another machine connects
- **WHEN** a machine other than the operator's tries to open the view
- **THEN** the connection is not accepted

### Requirement: Use, cost and endings are shown for a chosen period, with every rate beside its count

For a period the operator chooses, the view SHALL show the number of questions
asked, the number of distinct testers who asked them, how those questions ended,
the total spend and the spend per question, and how many questions ended at a
limit.

Every share or rate SHALL be shown together with the count it is a share of. The
alpha has a handful of testers, and "80% approved" from five ratings is a
different statement from the same figure out of five hundred.

A period with no questions SHALL be shown as a period with no questions, not as
an error and not as an empty page.

#### Scenario: A rate is shown
- **WHEN** the view shows any share or rate
- **THEN** the count it is a share of is shown with it

#### Scenario: A quiet period
- **WHEN** the operator chooses a period in which nobody asked anything
- **THEN** the view says that no questions were asked in that period

### Requirement: A question's ending is what the trail recorded, and an ending the view cannot identify is never counted as an answer

Each question SHALL be classified by the latest ending the trail recorded for
it, among the endings the view knows. Records that follow an ending — the answer
itself, its evidence, a reader's rating — SHALL NOT change the classification. A
question for which the view finds no ending it knows SHALL be shown as
unidentified, together with the last event the trail recorded for that question,
and SHALL NOT be counted as answered or as any other ending.

This covers a question still in progress, a question abandoned mid-answer, and
an ending added to the application after the view was written: the view cannot
tell these apart, and it does not need to.

The cheap direction is the one chosen. A question wrongly shown as unidentified
costs the operator a look. A question wrongly shown as answered produces a wrong
answer rate that looks ordinary.

#### Scenario: Asked and answered
- **WHEN** the trail records a question as asked and as answered
- **THEN** the view counts it as answered

#### Scenario: Asked and never ended
- **WHEN** the trail records a question as asked and records no ending for it
- **THEN** the view shows it as unidentified, naming the last event recorded for it
- **AND** does not count it as answered

#### Scenario: An ending the view does not know
- **WHEN** the trail records for a question no ending the view knows, and its last event is one the view does not recognise
- **THEN** the view shows that question as unidentified, naming that event
- **AND** does not count it as answered

#### Scenario: Records after the ending
- **WHEN** the trail records a question as answered and afterwards records the answer, its evidence and a reader's rating of it
- **THEN** the view still counts it as answered

### Requirement: Readers' judgements are shown grouped by what produced the answer

The view SHALL show approvals and disapprovals grouped by the run label recorded
with them, each group with its count, and SHALL list the comments readers wrote
alongside the question and answer they are about. It SHALL show how many answers
were recorded as ungrounded or as citing entries that were not retrieved.

Judgements recorded before sign-in existed carry no reader. They SHALL be
included and shown as unattributed, never dropped.

#### Scenario: Judgements across two run labels
- **WHEN** readers have rated answers produced under two different run labels
- **THEN** the view shows each run label's approvals and disapprovals separately, each with its count

#### Scenario: A judgement with no reader
- **WHEN** a judgement in the period has no reader recorded with it
- **THEN** it is counted and shown as unattributed

### Requirement: The view shows who is waiting at the door

The view SHALL list the addresses that asked for the confirmation email again
and the addresses refused for not being enrolled. An address that was refused and
has since been admitted SHALL NOT be listed as waiting. The rule for who is
still waiting SHALL be the same one the daily check applies.

#### Scenario: Refused, then admitted
- **WHEN** an address was refused for not being enrolled and was later admitted
- **THEN** it is not listed as waiting

#### Scenario: Refused and not yet admitted
- **WHEN** an address was refused for not being enrolled and has not been admitted since
- **THEN** it is listed as waiting to be enrolled

### Requirement: The view shows whether the recording itself is working

The view SHALL show when the trail last received a row, and how many failures
of the hosted tracer the trail recorded in the period. Recording fails open, so
a recording problem shows up as silence and not as an error. These are the
figures that tell the operator to look closer.

#### Scenario: The tracer failed during the period
- **WHEN** the trail recorded hosted-tracer failures in the period
- **THEN** the view shows how many

#### Scenario: Nothing has been recorded for a while
- **WHEN** the operator opens the view
- **THEN** the time the trail last received a row is shown

### Requirement: A question can be followed to its hosted trace without contacting the tracer

For each question, the view SHALL offer the trail's full record of that question
and a link to the question's hosted trace. The link SHALL be derived from the
question's identifier alone. The view SHALL NOT call the hosted tracer for this
or for anything else.

A link SHALL NOT be offered for a question older than the tracer's access
window, because past that window the link leads nowhere.

#### Scenario: A recent question
- **WHEN** the operator opens a question asked within the tracer's access window
- **THEN** the trail's record of that question is shown
- **AND** a link to its hosted trace is offered

#### Scenario: An old question
- **WHEN** the operator opens a question asked before the tracer's access window
- **THEN** the trail's record of that question is shown
- **AND** no link to a hosted trace is offered

#### Scenario: The view is used
- **WHEN** the operator uses every part of the view
- **THEN** no request is made to the hosted tracer

### Requirement: Leaving the view open does not keep the database awake

The view SHALL NOT query the database on a timer. Results SHALL be reused for a
period rather than fetched again on every interaction, and the operator SHALL be
able to fetch fresh results on request. A view that polls keeps a suspended
database awake, which spends its compute allowance and hides the cold-start
delay the trail exists to measure.

#### Scenario: The view is left open
- **WHEN** the view is left open with nobody using it
- **THEN** it issues no queries

#### Scenario: The operator asks for fresh figures
- **WHEN** the operator asks the view to refresh
- **THEN** the figures are fetched again from the database
