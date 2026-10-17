## MODIFIED Requirements

### Requirement: The command refuses to write where git would track the corpus

The default output path is relative, so a run started from the wrong directory writes the corpus into
whichever repository the caller is standing in. Three checkouts of this project share one origin and
one of them tracks the default branch, so that is a direct route from a mistyped `cd` to 19.5 MB of
unlicensed data in a public history — the one mistake this capability can make that cannot be undone.

A `.gitignore` entry guards only the repositories someone remembered to edit. The system SHALL
therefore ask git whether it would track the output file, and SHALL refuse to run when it would,
naming the repository and exiting non-zero without writing anything. Where git reports the path as
ignored, or reports that it lies in no repository, or git is not installed, the run SHALL proceed.
Where git is installed and gives no answer -- it times out, cannot be started, or fails for any
other reason -- the system SHALL refuse in the same way, saying that git could not be asked: an
unknown is not a pass, because the mistake guarded against cannot be undone. A results or run file
that already exists on a path SHALL be checked again before it is appended to.

#### Scenario: The output would be tracked

- **WHEN** the output path lies in a repository that does not ignore it
- **THEN** the command refuses, names that repository, and writes nothing

#### Scenario: The output is ignored, or outside a repository

- **WHEN** the output path is git-ignored, or lies outside any repository
- **THEN** the command runs normally

#### Scenario: Git does not answer

- **WHEN** git is installed but times out, cannot be started, or fails other than by reporting no
  repository
- **THEN** the write is refused, the reader is told git could not be asked, and nothing is written

#### Scenario: A file already on a tracked path

- **WHEN** an existing results file lies on a path git would track
- **THEN** appending to it is refused, as creating it would have been

#### Scenario: Any caller is refused, not only the command

- **WHEN** the ingest operation is invoked directly rather than through the command
- **THEN** it refuses on the same condition, before reading the source

The refusal belongs to the operation. Placed in the command it protected exactly one caller, and the
operation invoked as a library wrote the corpus onto a committable path in silence — a bypass that
stayed invisible while the command was the only caller, and that a second caller would have taken.
