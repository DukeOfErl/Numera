# ADR-1800: The git-tracking guard refuses when git gives no answer

- **Status:** accepted
- **Date:** 2026-10-17
- **Pull request:** not yet opened — branch `fix/guard-fails-closed` (`fix-guard-fails-closed`)

## Context

`bionumbers_ingest.guard.committable_repo_for` asks git whether it would track a file before the
corpus, an evaluation's results or a validator run is written (ADR-0200, ADR-0250). It returned
`None`, meaning "allowed", in three cases: the path is ignored, it is outside any repository, or git
"cannot be consulted". The last case covered a timeout and any failure to start git, and
`rev-parse` failing for any reason was read as "not a repository".

On 2026-10-16 a parallel test run under memory pressure wrote a results file inside this
repository. The test that wrote it was the one asserting it would be refused. The run was slow
enough for git to time out, and the guard read that as "no git". The file then stayed where it was.
`append_result` checks only a file it is creating, so the next run appended to it unchecked.

Options:

1. **Leave it.** Timeouts are rare. But a false all-clear here is the one mistake this project
   cannot undo, and the failure shows up only as a file that does not look wrong.
2. **Retry, then allow.** This narrows the window but keeps the expensive direction.
3. **Refuse an unknown.** A guard that cannot tell refuses. The cost is a rerun.

## Decision

Option 3. `committable_repo_for` raises `GitDidNotAnswer` when git is installed and gives no
answer: a timeout, a failure to start, a `rev-parse` failure other than "not a git repository",
or a `check-ignore` status other than 0 or 1. Git runs in the C locale, so "not a git repository"
is matched in git's own untranslated words. Each caller turns the exception into its own refusal
and its own message: the ingest command, the evaluation's results and answer sheet, and the
validator's two run-file guards. Autobuild's catch-all already renders it as a sentence.

Two cases still allow the write:

- **Git says the path is in no repository.** That is an answer.
- **Git is not installed.** A machine without git cannot commit the file, and a deployment that
  builds its corpus has no checkout to commit it to.

The second is a judgement call, and it is the one exception to "an unknown refuses".

An evaluation results file is checked on every append, not only when it is created. That is two
git calls per result, beside a model call per result. The test asserting the refusal now deletes
the file whatever happens, so one regression cannot poison the next run.

## Trade-off accepted

A slow machine may refuse a write that would have been safe, and the reader has to run it again.
A repository git will not read, such as one with dubious ownership, is now refused with git's own
reason, where before the write went ahead. Both are cheap next to a committed corpus.
