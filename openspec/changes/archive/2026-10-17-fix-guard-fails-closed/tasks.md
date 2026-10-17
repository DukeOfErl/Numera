ADR block: `1800`–`1840` (CLAUDE.md is the authority).

## 1. The guard

- [x] 1.1 Tests first: a timeout, a failure to start, an unreadable repository and a failed
      check-ignore each refuse; "not a git repository" and no git installed still allow. Eleven new
      tests failed against the old guard
- [x] 1.2 `GitDidNotAnswer`; git run in the C locale; translated by every caller
- [x] 1.3 A results file checked on every append; the test that asserts the refusal cleans up
      after itself
- [x] 1.4 Six defects seeded into copies, each caught: a timeout or a failed start allowed, any
      rev-parse failure read as "no repository", "no repository" refused, a failed check-ignore
      allowed, an existing results file skipped. Baseline green first

## 2. Records

- [x] 2.1 ADR-1800; the spec delta; conformance; CHANGELOG; `src/bionumbers_ingest/CLAUDE.md`
- [x] 2.2 Full suite; `openspec validate --strict`; archive
