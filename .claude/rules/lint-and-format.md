---
paths:
  - "pyproject.toml"
  - ".pre-commit-config.yaml"
  - ".github/workflows/**"
---

<!-- Moved out of CLAUDE.md, which targets under 200 lines. The paired pin only
     matters to someone editing one of the two files that carry it, or CI. -->

# Lint and format: automatic, and pinned in two places

`ruff check` and `ruff format` run at every commit through `.pre-commit-config.yaml`, and in CI
(`.github/workflows/checks.yml`) over the whole tree. A fresh clone or a new worktree needs
`uv run pre-commit install` once — the hook lives in `.git/hooks`, which worktrees share, so one
install covers all of them.

**The rev in `.pre-commit-config.yaml` and the `ruff` pin in `pyproject.toml` must move together.**
Ruff's formatter output can change between minor releases, so a range in one place and a pin in the
other is how eight files came to be unformatted while `ruff check` stayed green for weeks. The
pre-commit rev is the arbiter: CI runs the hooks, not the venv's ruff, so a local ruff that has
wandered is reported rather than silently committing churn.

CI **reports, it does not gate.** Streamlit Cloud deploys a branch tip whether or not the checks
pass, so a green tick is a smoke alarm and not a lock. It also cannot run the two marked suites,
which is the point of the paragraph below.
