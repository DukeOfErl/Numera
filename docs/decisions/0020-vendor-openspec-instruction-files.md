# ADR-0020: Vendor OpenSpec instruction files in the repository

- **Status:** accepted
- **Date:** 2026-08-08
- **Pull request:** _(not yet opened — branch `chore/third-party-notices`)_

## Context

Adopting OpenSpec ([ADR-0010](0010-adopt-openspec-for-spec-driven-development.md)) causes
`openspec init` to generate roughly 2,300 lines of agent-facing instruction files into the working
tree: the `/opsx:*` slash commands under `.claude/commands/opsx/` and the workflow skills under
`.claude/skills/openspec-*/`. None of them contain anything specific to this project, and
`openspec update` regenerates them on demand, so they resemble vendored dependencies that would
normally be gitignored.

They differ from ordinary dependencies in one respect: they are read directly out of the working
tree by coding agents, and they define how those agents behave. They are configuration, not build
output.

A licensing question also applies. OpenSpec is distributed under the MIT license, whose sole
obligation is that the copyright and permission notice accompany "all copies or substantial
portions of the Software". Committing 2,300 lines of the package's content into a repository that
may be published plausibly constitutes a substantial portion.

## Decision

Keep the generated files committed, and add `.claude/THIRD-PARTY-NOTICES.md` reproducing the
OpenSpec MIT license and linking to <https://github.com/Fission-AI/OpenSpec>. Keep the notice in
step if OpenSpec's license changes, or if other tooling starts vendoring generated files here.

## Trade-off accepted

Vendor noise enters the history, and every OpenSpec upgrade produces churn in files nobody on the
project wrote. In exchange, an upgrade that changes agent workflow arrives as a reviewable diff
rather than as silent behavioural drift after a CLI update, and a fresh clone gives agents working
commands with no install step. Gitignoring them would have been defensible and would also have
removed the attribution obligation, but unreviewable changes to agent behaviour were judged the
worse failure mode.
