# Protocol — 2026-09-09 probe

Six corpus entries, two arms, one subagent per entry per arm. Twelve agents,
Opus, one run, no repeats. The entries were **chosen to stress interesting
cases, not sampled at random** — every number below describes these six and
generalises to nothing.

## The two arms, and which one matters

**Sourced arm (the question).** The agent is given the property, the organism
and the paper's full text as local XML, and must report the value with a
**verbatim quote** from the source. It is told explicitly that `NOT_IN_SOURCE`
is a correct answer and not a failure. Every quote is then checked
mechanically by `check_quote.py`; the agent never grades itself.

**Blind arm (a control, secondary).** The agent is given the property and the
organism only — no paper, no tools — and must state a value, a band and a
confidence. This measures how much of a sourced answer pre-training could
explain, BioNumbers being public. It tells us about the model's recall, not
about the validator's job.

Reporting the arms as equals overstates the blind one. It earned its cost
exactly once (Finding 3 in ADR-0040), and that is the honest weight to give it.

## Priming toward refusal is the configuration, not a confound

The sourced prompt's instruction that refusal is correct is what production
will carry: refusal *is* the desired behaviour when a source lacks a value. The
probe therefore measured the harness we intend to build. What follows is only
that "zero false confirmations" describes a *primed* harness, and still needs
re-measuring at n greater than six.

## Corrections adopted for the next runs

From this probe's own failures. Cheap, and not optional if a rate is to mean
anything.

- **Do not supply expected units.** For an unfamiliar paper we do not know its
  units in advance, so supplying them leaks the shape of the answer and makes
  the task easier than the real one. Both entries whose value was *not* in the
  paper had units supplied, and both produced a derivation rather than stopping
  at refusal.
- **Keep prompts byte-identical within an arm.** Differences belong between
  arms, never inside one. One sourced agent (115327) alone was told the
  property may have several parts, so that entry is not comparable with the
  other five.
- **Tell blind agents nothing about other participants**, and give them no
  reason to look.
- **Prevent inter-agent communication, or verify its absence.** Preferably
  separate sessions, or a harness giving the answering agent no message bus.
  Where that is impossible, capture every agent's tool-call record and treat
  **any** tool call by a blind agent as a contamination flag — a blind agent has
  no legitimate reason to call one, so the check is cheap and unambiguous.
  Subagent transcripts were not persisted this time (the session's task
  directory was empty), so isolation could be argued but not proven. A rate run
  must capture them.

## Isolation, as actually evidenced

The arms ran as named subagents in one session, which share a message bus, so
contamination was possible in principle and no transcript exists to rule it out.
The evidence is circumstantial and recorded as such:

- All six blind agents finished (11:46:23-11:46:39) before the first sourced
  result existed (11:47:22). In that direction there was nothing to leak.
- Blind agents were fresh general-purpose agents, not forks — no experiment
  context, not told other agents existed, and they would have had to enumerate
  agents first. All six self-reported `TOOLS_USED: no`.
- The arms **disagree**: 65 vs 40 min, 40% vs 13-15%, 200-1000 vs 65 fg C/um^3.
  Leakage predicts convergence.

The disagreement is the load-bearing part, being the falsifiable one. Note that
the tool-call evidence is self-reported, which is exactly the weakness the
correction above fixes.

## Next probes, in priority order

The first two decide whether the validator is worth building at the recommended
scope; the third is what makes any rate credible.

1. **Reach** — supplementary files and figure images, where the missing ~78%
   lives (see `COVERAGE.md`). The only open question that could still make the
   validator infeasible at useful scale.
2. **Papers published after the training cutoff**, where recall cannot
   contribute. This is the condition the validator actually faces, and no entry
   here tested it — every source predates the cutoff.
3. **An honest rate**, on a random sample rather than chosen cases, with
   repeats so variance is visible.

### One dead end, recorded so it is not re-explored

A string-level pre-classification of whether a target number appears in its
source was attempted and **discarded as unreliable**: false negatives on
`19,042` (comma) and `46.4298 kDa` (unit form), plus coincidental matches. The
agent is the measurement; a cheap string test is not a cheaper version of it.

Also dead: preprints. Only 8 entries in the entire corpus cite one, and they are
oddities (supplemental Excel links; one marked "to be approved once article is
peer-reviewd").
