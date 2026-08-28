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


### Requirement: A build is announced before it begins, not after it ends

Where a driver builds a corpus rather than failing, it SHALL say so before the
build starts, and SHALL name both the export being read and the path being
written.

A build takes about a minute. Announced afterwards, or not at all, the first
launch is indistinguishable from a hang -- and a page shows an empty frame for the
whole of it. Both paths are named because the build can be refused on its
destination, and a reader told only what was read cannot tell which path was
rejected.

#### Scenario: A corpus is built on first launch
- **WHEN** a driver finds an export and no corpus
- **THEN** the notice appears before any building work is done
- **AND** it names the export it will read and the path it will write

#### Scenario: A corpus is already present
- **WHEN** a driver finds a corpus at the configured path
- **THEN** nothing is announced, because nothing is built

### Requirement: A corpus that cannot be built is explained, not raised

A driver SHALL report a refused or impossible build the way it reports a missing
corpus: as a message a person can act on, never as a traceback.

Three conditions reach a reader here -- the destination is somewhere git would
track the corpus, the ingestion component is not installed, or there is no export
to build from -- and all three are configuration a person can fix. The second SHALL
name the export that was found and how to use it without that component, since an
answer of "not installed" is less useful than one that says what to do with the
file already present.

#### Scenario: The destination would be committed
- **WHEN** the build is refused because git would track the corpus
- **THEN** the driver states the path and the repository, and does not raise

#### Scenario: The ingestion component is absent
- **WHEN** an export is present and the component is not installed
- **THEN** the message names the export and the command that would convert it

#### Scenario: There is nothing to build from
- **WHEN** neither a corpus nor an export is present
- **THEN** the ordinary missing-corpus message stands, unembellished
