# corpus-ingestion (delta)

## ADDED Requirements

### Requirement: An export beside a missing corpus can produce one

A reader who has downloaded the export has done the only step that cannot be automated. Requiring
them to also invoke the ingester before the agent will start is a third step whose only cause is that
nothing told the agent the file was there, and the error it gets instead — that no corpus exists at
the configured path — is accurate while the material to build one sits in the same directory.

The system SHALL provide a resolver that, given a configured corpus path, reports: the path the
corpus occupies or would occupy, the export that could produce it if one is present, and whether a
build is required. Reporting SHALL be separate from building, so that a caller can tell a reader what
is about to happen before a 27 MB read begins.

#### Scenario: A corpus is already there

- **WHEN** the configured path holds a corpus
- **THEN** the resolver reports no build is needed, and names that path

#### Scenario: An export sits beside the missing corpus

- **WHEN** the configured path holds nothing and `BioNumbers.xls` is in the same directory
- **THEN** the resolver reports that a build is needed, naming both the export and the corpus path

#### Scenario: The configured path is the export itself

- **WHEN** the configured path is an `.xls` export
- **THEN** the resolver reports the corpus path beside it, and builds there rather than in the cwd

#### Scenario: Neither is present

- **WHEN** the configured path holds nothing and no export is beside it
- **THEN** the resolver reports no build is possible, and the caller's own error stands

### Requirement: A corpus that exists is never rebuilt

The resolver SHALL NOT rebuild a corpus that is present, whatever its modification time and whatever
digest its manifest records.

A corpus someone produced deliberately — from a different export, with a row limit, or edited — being
replaced without being asked is a worse outcome than a stale one being read. Staleness is invisible
from the answer side and "the file changed under me" is the hardest class of defect to trace, so the
rule is absolute rather than heuristic. Detecting staleness, if it is ever wanted, is a report and
never an action.

#### Scenario: The corpus is older than the export

- **WHEN** a corpus exists and the export beside it is newer
- **THEN** the existing corpus is used and nothing is written

### Requirement: A build through the resolver is refused on the same terms as the command

The resolver SHALL build through the ingest operation, so that a build refused because git would
track its output is refused here too, before anything is read.

A convenience path that bypasses the refusal would be worse than no convenience path: it is the one
irreversible mistake this project can make, and it would be made by a caller who never asked to write
a file at all.

#### Scenario: The corpus path is one git would track

- **WHEN** a build is needed and the corpus path lies in a repository that does not ignore it
- **THEN** the build is refused, naming the repository, and nothing is written
