# Tasks

ADR block for this change: `1900`–`1940`. The table in `CLAUDE.md` is the authority and has been
reconciled.

One branch, `refactor/rename-to-numera`, off `dev`. Mechanical, with no behaviour change apart from
the names and the twice-retired refusal. `feat/property-names` and `feat/monitor-dashboard` are
rebased across it afterwards (decided 2026-11-19); expect conflicts there, not here.

**Keep-list: these do not change.** `src/bionumbers_ingest/` and the `bionumbers-ingest` script
(ADR-0400: the BioNumbers adapter). `numera_ask/bionumbers.py`, BNID, and every "BioNumbers" that
means the database. Accepted ADRs, `openspec/changes/archive/`, past CHANGELOG entries. The
`BIONUMBERS_ASK_*` keys of the refusal map (their *values* change, task 2.2).

**Scope every substitution to an explicit path list**, never a blanket replace: "bionumbers" is both
the old validator package and the data source, and only the first is renamed. The previous rename
was done the same way (`rename-to-scinumbers`, task 1.1).

## 1. Packages and scripts

- [ ] 1.1 `git mv src/scinumbers_ask src/numera_ask` and `git mv src/bionumbers src/numera_validator`;
      update imports across `src/`, `tests/`, `streamlit_app.py`, `review_app.py`, `probes/`
- [ ] 1.2 `pyproject.toml`: project name `numera`, every `scinumbers-*` script to `numera-*`, the
      validator's `bionumbers` script to `numera-validator`, ruff's `known-first-party`; then `uv lock`
- [ ] 1.3 The hyphenated and string forms: `cli.py`'s `prog=` and `SystemExit` prefixes, `trace.py`'s
      `LOGGER_NAME` and tag list, logger names, `agent.py`'s `_origin` frame filter (computed from
      `__file__`; confirm it still is)
- [ ] 1.4 **Assert the trace tag and logger name** under the new name; a rename nothing asserts is silent
- [ ] 1.5 `web.py`'s session-state keys and `TITLE` ("SciNumbers ask" becomes "Numera"). Renaming the
      keys drops in-flight sessions; old LangGraph checkpoints under `scinumbers_ask.*` paths stop
      loading. Both intended, both noted in the CHANGELOG
- [ ] 1.6 `tests/test_driver_independence.py`: its globs and `HARNESS` set name the new packages; the
      test that refuses a name with no file behind it must still pass
- [ ] 1.7 `.claude/rules/*.md` `paths:` front matter (`src/bionumbers/**`, `src/scinumbers_ask/**`),
      `.claude/agents/*.md`, `src/*/CLAUDE.md`, `.pre-commit-config.yaml`, `.github/workflows/*`

## 2. The environment prefix

- [ ] 2.1 Every `SCINUMBERS_*` read becomes `NUMERA_*`; `RENAMED_ENV` gains each `SCINUMBERS_*` name
      mapped to its `NUMERA_*` replacement
- [ ] 2.2 The `BIONUMBERS_ASK_*` entries now map to `NUMERA_*`, not `SCINUMBERS_*`. `WITHDRAWN_ENV`'s
      guidance names `NUMERA_QUESTION_CEILING_USD`. Test: no value in either map is itself a key
      (the twice-retired scenario), for every entry rather than one example
- [ ] 2.3 The refusal stays called from `Config.from_env` **and** from each driver before anything
      else reads the environment (spec: "The refusal precedes every other reading")
- [ ] 2.4 The validator's `BIONUMBERS_REVIEW_DB_URL` and `BIONUMBERS_OPENROUTER_API_KEY` become
      `NUMERA_REVIEW_DB_URL` and `NUMERA_OPENROUTER_API_KEY`, refused by name **inside
      `numera_validator`** where it reads them: its core may not import `numera_ask`
- [ ] 2.5 `tests/conftest.py`'s autouse fixture, every test setting an env var, pytest marker help
      text, `.streamlit/secrets.toml.example`, the README configuration table
- [ ] 2.6 `tests/test_spec_conformance.py`: map the new scenario's test under the existing
      requirement (the heading is unchanged)

## 3. Wording and docs

- [ ] 3.1 README (including `README.md:679`'s cron line, which also holds the old folder path),
      `CLAUDE.md` Architecture section and module tables, `docs/diagrams/`, `docs/roadmap.md`
- [ ] 3.2 `probes/2026-09-18-reach/calibrate.py`'s hardcoded `BioNumbers-…` path
- [ ] 3.3 CHANGELOG `[Unreleased]`: the rename, the refused names, the dropped sessions, and the
      external settings to switch at deploy time
- [ ] 3.4 ADR-1900: the project is named Numera; the validator is renamed, the ingester is not

## 4. Verify

- [ ] 4.1 Full suite green; `openspec validate --strict`
- [ ] 4.2 A grep for `scinumbers|SciNumbers|SCINUMBERS_` and for `src/bionumbers/`, `bionumbers.cli`,
      `import bionumbers\b` finds nothing outside the keep-list; every surviving hit is listed in the
      report with its reason
- [ ] 4.3 Seed one defect into a copy: drop a `SCINUMBERS_*` entry from `RENAMED_ENV`; the refusal
      test must fail
- [ ] 4.4 The app runs locally on port 8502 with `NUMERA_STORE` set, and signs in

## 5. Prepared here, switched at deploy time (not in this change)

- [ ] 5.1 Streamlit Cloud secrets, the Actions secret `SCINUMBERS_TRAIL_READ_URL` (and the workflow
      that reads it), `~/.config/scinumbers/enrol.env`: listed in the CHANGELOG and the brief with
      their new names, renamed in the same moment `deploy/streamlit-cloud` moves to this code
