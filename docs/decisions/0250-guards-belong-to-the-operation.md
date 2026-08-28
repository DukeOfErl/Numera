# ADR-0250: The refusal to write a committable corpus belongs to the operation

- **Status:** accepted
- **Date:** 2026-08-28
- **Pull request:** _(merged to `dev` as part of `feat/corpus-ingestion`, commit `140d53a`; this
  record was written the day after the change rather than with it — see the note at the end)_

## Context

ADR-0200 names the one mistake this project can make that cannot be undone: 19.5 MB of
unresolved-licence data entering a git history. The corpus path is relative by default, three
checkouts here share one origin, and one of them tracks `main`, so a run started from the wrong
directory is all it takes.

The guard against that was written into `cli.py`: before doing anything, the command asked git
whether it would track the output and refused if so. It was tested, and the tests passed.

It protected exactly one caller. `ingest()`, invoked as a library, wrote wherever it was told.
Nothing called it that way, so the hole was invisible — and it was found not by seven passes of code
review over the module but by a *design question*: could the ask agent build a corpus when it finds
an export beside a missing one? The answer required a second caller, and the second caller would have
gone straight past the refusal. A convenience feature would have been the thing that made the
irreversible mistake, on behalf of a user who never asked to write a file.

Reproduced before deciding anything: a fresh `git init`, a library call, a corpus on a committable
path, no complaint.

Two options were on the table. Repeat the check in each new caller — cheap now, and it fails the
first time someone adds a caller without knowing the guard exists, which is precisely how the
situation arose. Or move it into the operation.

## Decision

**The refusal lives in the operation.** `guard.py` holds it, `ingest()` calls it before reading the
source, and every caller inherits it — the command, the resolver, a test, anything added later.

The command keeps the *wording* and the exit code; the operation keeps the *refusal*. That split is
the general form: a driver owns how a failure is presented to its own kind of user, and the operation
owns whether the failure happens at all.

It fires **before the 27 MB read**, not after. Refusing at the end would spend the work to discover
the destination was never allowed, and — the real reason — it is the check that decides whether the
run may proceed, so it belongs where a run begins.

The exception carries the offending path and the repository as attributes rather than a formatted
string, so each driver can render it the way it renders its other failures.

## Trade-off accepted

**A caller cannot deliberately write a corpus into a repository, even one that wants to.** There is
no override flag, and adding one would restore the hole under a different name. If a legitimate need
appears — a fixture-sized corpus committed on purpose — it will have to be met by writing outside the
repository and copying in, which is a visible act rather than a silent one.

**Every caller pays two `git` subprocesses**, on four candidate paths, before any work. Measured in
milliseconds and irrelevant beside a 27 MB parse, but it is now on a path that a web driver may hit
during a page load rather than only on a deliberate command.

**A guard in the core is harder to see from the driver.** Someone reading `cli.py` no longer finds
the check there. Mitigated by the exception being caught and named explicitly in the command, so the
behaviour is still legible from the caller — but it is a real cost of moving policy inward, and the
same cost would apply to the next guard moved this way.

## Note on when this was written

The conventions in `CLAUDE.md` say to write an ADR with the change that makes the decision, and this
one was written the day after `140d53a` merged. The reasoning above is not reconstructed — the
rejected option and the reproduction are a day old — but the ordering was wrong, and the reason it
was wrong is instructive: the change *looked* like a bug fix, and bug fixes do not usually get ADRs.
It was a bug fix that also set a convention, and the convention is the part worth recording.
