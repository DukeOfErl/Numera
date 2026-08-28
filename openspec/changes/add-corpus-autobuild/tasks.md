# Tasks

ADR block for this change: `0300`–`0340`. `0250` went to ADR-0250 on `add-corpus-ingestion`, which
spent its block; the table in `CLAUDE.md` is the authority and has been reconciled.

## 1. The resolver

- [x] 1.1 `plan_corpus(configured)` reports what to do without doing it: the corpus path, the export
      that would build it, and whether a build is needed. No I/O beyond looking for the files, and no
      printing — the caller announces
- [x] 1.2 Accept the configured path pointing straight at an `.xls`, and write the corpus beside it
- [x] 1.3 Find `BioNumbers.xls` beside a missing corpus, case-insensitively, and nothing else — a
      directory of exports is ambiguous and this returns nothing rather than guessing
- [x] 1.4 `build_corpus(plan)` performs the build and returns the corpus path
- [x] 1.5 An existing corpus is never rebuilt, whatever its age or digest

## 2. Verification

- [x] 2.1 Tests for each of the above, including that the git refusal reaches the caller from the
      resolver's build path rather than being swallowed
- [x] 2.2 Fault seeding over the resolver: a seeded defect in the never-rebuild rule must fail a test.
      **5 seeds, 5 caught by the intended test.** The harness aborted twice before reporting
      anything, both times correctly: its copy was missing root files the merged suite reads
- [x] 2.3 Round-trip: a directory holding only the export yields a corpus the consumer's loader reads

## 3. Documentation

- [ ] 3.1 `README.md`: the two-step becomes "download, then run the app", with the manual route kept.
      **Held until `add-ask-agent` wires the drivers** — the resolver alone changes nothing a reader
      can see, and a README promising a build that no call site performs is worse than the old one
- [x] 3.2 `CLAUDE.md`: `resolve.py` in the module table
- [x] 3.3 `CHANGELOG.md`
