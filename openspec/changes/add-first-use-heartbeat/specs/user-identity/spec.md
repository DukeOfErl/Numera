## MODIFIED Requirements

### Requirement: A new reader's arrival reaches the operator on a schedule, with no mail account of their own

A reader's first use SHALL reach the operator without the operator asking, within
the interval the schedule runs at plus the time a delivery takes. A run in which
nobody is new SHALL deliver nothing, with one exception: when seven days have passed
since the operator was last sent anything by this check, the run SHALL deliver one
message saying that the check found no new reader in that time. Delivery SHALL NOT
require the operator to hold credentials for a mail service. The message SHALL name
the reader by the address they signed in with, which is information the operator
already holds about them as an enrolled account; the deployment's privacy statement
SHALL NOT need to change because of it.

That second message exists so that a quiet week can be told apart from a check that
has stopped working, which silence alone cannot. It SHALL say what the check found
rather than claim that no reader exists — it reports an observation, and says that if
someone was expected, the check itself may be at fault — and it SHALL say how many
checks completed in those seven days and when the last one ran. The seven days SHALL
be counted from the last thing delivered to the operator, whatever it was, so that a
report of a new reader, or an earlier message of this kind, restarts them; and it
SHALL NOT be repeated until seven days have passed again. Where nothing has yet been
delivered to count from, it SHALL NOT be sent. It SHALL reach the operator the same
way a report of a new reader does, and a check that could not read the records SHALL
NOT send it, because it would then be saying something the check did not find.

#### Scenario: A new reader arrives
- **WHEN** a reader is first seen, and the next scheduled run happens
- **THEN** the operator receives a message naming them and what was first seen

#### Scenario: Nothing new in the interval
- **WHEN** a scheduled run finds nobody new, and the operator was sent something by this check less than seven days ago
- **THEN** the operator receives nothing from that run

#### Scenario: A quiet week
- **WHEN** a scheduled run finds nobody new, and seven days have passed since the operator was last sent anything by this check
- **THEN** the operator receives one message saying that the check found no new reader in that time

#### Scenario: What the quiet-week message says
- **WHEN** the quiet-week message is delivered
- **THEN** it says that the check found no new reader, how many checks completed in the seven days and when the last one ran, and that the check may be at fault if someone was expected, and it does not say that no reader exists

#### Scenario: A delivery of any kind restarts the seven days
- **WHEN** the operator is sent a report of a new reader, a test message, or a quiet-week message
- **THEN** no quiet-week message is sent until seven days after it

#### Scenario: It is not repeated run after run
- **WHEN** a quiet-week message has been delivered and later runs within the next seven days find nobody new
- **THEN** none of those runs delivers anything

#### Scenario: Nothing has been delivered yet
- **WHEN** a run finds nobody new and nothing has ever been delivered to the operator by this check
- **THEN** no quiet-week message is sent

#### Scenario: A check that could not read the records
- **WHEN** a run could not read the records
- **THEN** no quiet-week message is sent, and the failure is reported as a failure
