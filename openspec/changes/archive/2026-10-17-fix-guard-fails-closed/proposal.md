## Why

On 2026-10-16 a parallel test run under memory pressure wrote a results file inside the
repository. The test that wrote it was the one asserting that write would be refused. Corpus
text must never enter a repository, and this guard is what stops that.

Two holes let it through:

- **A git that does not answer was read as "no git".** `committable_repo_for` returned `None` when
  git timed out, could not be started, or failed for any reason. So the guard allowed the write in
  exactly the case where it could not know the answer.
- **An evaluation results file was checked only as it came into existence.** Once one sat on a
  tracked path, every later append went in unchecked, and so did every resumed run. The next run
  of that test appended to the file unchallenged and failed for that reason.

## What Changes

- **An unknown is a refusal.** When git is installed but gives no answer about a path, the guard
  raises `GitDidNotAnswer` and nothing is written. "Gives no answer" means a timeout, a failure to
  start, or any failure other than "not a git repository". Two cases still let the write proceed:
  - git reports the path as outside any repository (read in the C locale, so the words are git's
    own);
  - git is not installed, so nothing on that machine can commit the file.
- Every caller turns the new exception into its own refusal, with a message that says to run it
  again:
  - the ingest command;
  - autobuild (already, through its catch-all);
  - the evaluation's results file and the answer sheet;
  - the validator's run files.
- A results file is checked on every append.

## Capabilities

### Modified Capabilities
- `corpus-ingestion`: "The command refuses to write where git would track the corpus". When git
  cannot be consulted, that is now a refusal rather than a pass, unless git is not installed.

## Impact

- `src/bionumbers_ingest/guard.py`, `src/bionumbers_ingest/cli.py`,
  `src/scinumbers_ask/evaluation.py`, `src/bionumbers/extraction.py`, `src/bionumbers/cli.py`.
- No data change. A run in a repository git will not read (dubious ownership) is now refused with
  git's own reason, where before it was allowed.
