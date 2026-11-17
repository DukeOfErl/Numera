## MODIFIED Requirements

### Requirement: An operator can see a session's own trail

The sidebar SHALL carry this session's trail below the run status, under its own
heading, for roles granted `dev panel`, and SHALL NOT show it -- absent, not
disabled -- for every other role. The entries behind an answer are not in the
sidebar (they are opened beside the answer), so there is one view and no tab
strip: a strip whose only other tab is missing would still tell a reader there
is a view they may not open. The trail SHALL show the records of this
session's last five questions as a table: when, which question, the event, and
its detail. This session's only: another tester's trail
is not this permission's to show, and scoping to the session is what keeps that
true without a second rule. Nothing shown here SHALL reach the model; these are
records of questions already answered.

A session with no questions yet SHALL show an empty section rather than none, so
a dev can tell "nothing yet" from "not permitted".

#### Scenario: A dev sees the trail tab
- **WHEN** an account granted `dev panel` views the page
- **THEN** the trail is shown in the sidebar below the run status

#### Scenario: A student's page has no such tab
- **WHEN** an account not granted `dev panel` views the page
- **THEN** no trail is shown on the page, disabled or otherwise
- **AND** the sidebar shows no tab strip at all

#### Scenario: The table names the question just asked
- **WHEN** an account granted `dev panel` asks a question
- **THEN** the trail's table includes that question's records

#### Scenario: A fresh session shows an empty tab
- **WHEN** an account granted `dev panel` opens a session and has asked nothing
- **THEN** the trail tab is present and empty

#### Scenario: Another session's trail is not shown
- **WHEN** two sessions are open under accounts granted `dev panel`
- **THEN** each panel shows only its own session's records
