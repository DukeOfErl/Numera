## MODIFIED Requirements

### Requirement: A retired configuration name stops the run and names its replacement

Where a configuration variable has been renamed or withdrawn, the system SHALL refuse to start,
reporting the retired name and what to set instead. It SHALL NOT ignore a retired name.

A renamed variable that is merely ignored is configuration that silently stops being read. Every
setting this system takes from the environment changes what a run does: a spend ceiling that no
longer binds, a run label that quietly becomes the default and mixes an evaluation's spend into a
person's, a corpus path that falls back to none. Each of those produces a run that looks like it is
working, which is worse than one that will not start.

The refusal SHALL be reported as misconfiguration a person can fix, not as a fault — the message is
the point, and a traceback buries it.

Where a variable was withdrawn rather than renamed, the refusal SHALL NOT describe it as a rename.
A limit whose meaning changed cannot have its value carried across: a threshold read as a ceiling
stops work below where it used to give notice, so telling the reader to move the value would tighten
their limit while appearing to preserve it.

#### Scenario: A renamed variable is set
- **WHEN** a run is started with a retired variable name present in the environment
- **THEN** the run does not start
- **AND** the message names both the retired variable and its replacement

#### Scenario: The refusal precedes every other reading of the environment
- **WHEN** the only retired variable set is the one naming the corpus, and no current name is set
- **THEN** the run is refused for the retired name
- **AND** it is not reported as a missing or unsupplied corpus

#### Scenario: A setting is read outside any driver
- **WHEN** a caller that is not one of the shipped drivers reads a configuration setting
- **THEN** a retired name present in the environment still refuses the run

#### Scenario: A withdrawn variable is set
- **WHEN** a run is started with a variable that was withdrawn rather than renamed
- **THEN** the run does not start
- **AND** the message does not instruct the reader to rename it

#### Scenario: A name retired twice names the current replacement
- **WHEN** a run is started with a variable that was renamed, and whose replacement was itself later renamed
- **THEN** the run does not start
- **AND** the message names the variable to set now, not the intermediate name that is also retired
