## ADDED Requirements

### Requirement: The operator is told when a reader is first seen, once for signing in and once for asking

There SHALL be a way for the operator to learn that a reader has arrived: the first
time an account is seen signing in, and the first time it is seen asking a question.
These are two separate firsts, and a reader who signs in and asks nothing SHALL be
reported for the first and never for the second. Where both firsts for the same
reader fall inside the span asked about, they SHALL be reported together, as one
message about one person.

"First" SHALL be determined from what is already recorded about the reader — an
event of that kind inside the span, and none earlier for the same account — and
SHALL NOT depend on any record kept about the asking itself, so that asking changes
nothing and can be asked as often as the operator likes. Two spellings of one
address that differ only in letter case SHALL be one reader.

It SHALL be answerable without a browser and without a person watching, so that it
can be asked on a schedule. Asking SHALL produce nothing at all when nobody new has
arrived: an answer that reports an empty hour is one that stops being read, and the
hour it names someone is then unread too. Where the question cannot be answered —
the records cannot be reached — that SHALL be said, loudly and as a failure,
because silence otherwise means "nobody new" and would be indistinguishable from it.

Because the span asked about is a fixed length, an account first seen in one span
MAY be reported again when the next span overlaps it, and an account first seen
while a scheduled ask was skipped MAY go unreported if the spans do not overlap
enough. The first is the cheaper error and SHALL be the one the operator's chosen
span leaves room for: a repeated notice costs a line, a missed first reader costs
the moment it was worth knowing.

The operator SHALL be able to name addresses that are never reported — their own,
and the accounts used for testing — so that the notices that remain are about
other people. How far back to look SHALL be the operator's to choose, and a span
that could match nothing SHALL be refused rather than answered with silence.

#### Scenario: Nobody new has arrived
- **WHEN** the operator asks who has been first seen and nobody has
- **THEN** nothing is reported at all

#### Scenario: A reader signs in for the first time
- **WHEN** an account is seen signing in for the first time, inside the span
- **THEN** it is reported as having signed in, and not as having asked anything

#### Scenario: A reader asks their first question
- **WHEN** an account is seen asking a question for the first time, inside the span
- **THEN** it is reported as having asked

#### Scenario: Both firsts fall in the same span
- **WHEN** an account is first seen signing in and first seen asking, both inside the span
- **THEN** one message about that account reports both

#### Scenario: A reader who was seen before is not reported again for it
- **WHEN** an account signs in inside the span, having signed in before the span
- **THEN** it is not reported as having signed in

#### Scenario: Seen signing in before, asking for the first time now
- **WHEN** an account signed in before the span and asks its first question inside it
- **THEN** it is reported as having asked, and not as having signed in

#### Scenario: One address in two spellings
- **WHEN** the same address is recorded once in lower case and once in capitals, the first before the span and the second inside it
- **THEN** it is one reader, who is not reported as new

#### Scenario: An address the operator excluded
- **WHEN** an account the operator named as never to be reported is first seen
- **THEN** it is not reported

#### Scenario: Asking changes nothing
- **WHEN** the operator asks twice over the same span with nothing new recorded between
- **THEN** both answers are the same, and nothing was recorded by asking

#### Scenario: The records cannot be read
- **WHEN** the records cannot be reached
- **THEN** the failure is reported and is distinguishable from nobody new

#### Scenario: A span that can match nothing
- **WHEN** the operator asks over a span that cannot include anything
- **THEN** the request is refused rather than answered with silence

### Requirement: Whatever asks on a schedule can read the records and change none of them

The means by which the question of who is new is asked on a schedule SHALL hold a
credential that can read the one record it needs — what has been recorded about
readers — and SHALL NOT be able to alter it or reach anything else, the enrolment
records included, since nothing in answering this needs them. It SHALL NOT hold a credential with authority over the
deployment itself, such as one that could create, change or remove the database.
Whoever grants the reading credential SHALL do so once, as an operator action, and
the means for doing so SHALL ship with the change that needs it.

#### Scenario: The scheduled credential tries to write
- **WHEN** the credential held for asking is used to change or remove a record
- **THEN** the attempt is refused by the database

#### Scenario: The scheduled credential tries to reach another table
- **WHEN** the credential held for asking is used to read anything other than what has been recorded about readers
- **THEN** the attempt is refused by the database

### Requirement: A new reader's arrival reaches the operator on a schedule, with no mail account of their own

A reader's first use SHALL reach the operator without the operator asking, within
the interval the schedule runs at plus the time a delivery takes. A run in which
nobody is new SHALL deliver nothing. Delivery SHALL NOT require the operator to
hold credentials for a mail service. The message SHALL name the reader by the
address they signed in with, which is information the operator already holds about
them as an enrolled account; the deployment's privacy statement SHALL NOT need to
change because of it.

#### Scenario: A new reader arrives
- **WHEN** a reader is first seen, and the next scheduled run happens
- **THEN** the operator receives a message naming them and what was first seen

#### Scenario: Nothing new in the interval
- **WHEN** a scheduled run finds nobody new
- **THEN** the operator receives nothing from that run
