# ADR-0040: What the validator feasibility probe established, and what it did not

- **Status:** proposed — this ADR records **findings and a recommendation**, not a
  settled decision. Nothing here constrains the validator's scope yet; the
  "Recommendation" section is what the evidence supports, and it is open to
  revision by the further probes listed under "Next probes".
- **Date:** 2026-09-10
- **Pull request:** — (not yet opened)

## Context

Before building a grounding validator we wanted to know whether its core act is
possible at all: given a corpus entry and the paper it cites, can an agent find
the number and attribute it? A deliberately cheap, code-free probe ran on
2026-09-09 — twelve subagents (Opus), six corpus entries, two arms each.

**The question that matters is the sourced one:** does an agent retrieve the
right number from a source, with an attributable quote? A second, blind arm
(property and organism only, no paper, no tools) was run to check how much of a
sourced answer could be explained by pre-training knowledge of BioNumbers,
which is public. That arm is a control, and secondary — it tells us about the
model's recall, not about the validator's job.

### Finding 1 — retrieval works; coverage is the binding constraint

Sourced arm: three exact finds, two derivations landing within 1% of the
curator's value, one partial. Fifteen quotes reported, fifteen verified verbatim
against the source by a mechanical checker, zero fabricated.

Against that, the ceiling on machine-readable full text is roughly **22%**,
measured on 126 papers drawn from the *favourable* slice of the corpus (a value
present, a verbatim quote in `measurement_method`, a page/table locator,
reference year >=2005 — 1,177 of 14,294 entries). `isOpenAccess=Y` predicted XML
availability exactly, 28/28 and 0/44, so that flag is a reliable pre-filter. On
the whole corpus the reachable fraction is lower.

The missing material clusters in two structural places, not at random:
supplementary files (for BNID 108345 and 108346 every quantitative table is
Supplementary S1-S8, absent from the XML) and figure images (per-depth values
for BNID 115327; the spread for 109252).

### Finding 2 — the database's defect is discarded uncertainty, not wrong numbers

Every entry probed was defensible. What was missing was the qualification:

- Two values are the curator's own arithmetic over supplementary data, presented
  as measurements.
- BNID 109252 fuses this paper's 65 min with the authors' *earlier published*
  ~55 min estimate for different growth conditions into one "~55 to 65" range.
- BNID 114567 holds only for one named substrain under one named light
  condition, and is partly stated, partly derived.
- BNID 115327's source contradicts itself between abstract and results.

On BNID 108346 the agent derived 2.29 mM, declared it a *floor* because the
derivation assumes 413 quantified proteins are the whole proteome when the paper
says they cover 60% of ORFs, and reported low confidence with a 2-4 mM band. The
corpus records 2.305 mM — four significant figures, no uncertainty. The agent
was better calibrated than the database.

### Finding 3 — a famous number outcompetes the cited one, confidently

The blind arm's self-reported confidence tracked correctness in five of six, so
the model is mostly honest about not knowing. The exception is the dangerous
shape: on E. coli replication time it answered "~40 min" at **high** confidence,
citing Cooper & Helmstetter — the canonical textbook figure, which contradicts
the cited paper. The failure mode is not ignorance but a well-known value
displacing a specific one, delivered with more confidence than the correct
answer.

This is the one respect in which the blind arm earned its cost, and it argues
for suppressing prior knowledge in the validator's own prompt.

## Recommendation

Offered as the reading the evidence supports, to be confirmed or overturned by
the next probes.

- **Frame the product as provenance and uncertainty restoration**, not error
  detection. That is what the evidence supports, it is defensible, and it does
  not depend on BioNumbers being wrong.
- **Treat "cannot confirm as stated" as a first-class verdict**, distinct from
  "disagrees with the source". Two of six entries needed it, and a validator
  obliged to emit a number would have emitted plausible wrong ones.
- **Label a derived value as derived**, carrying its inputs and the direction of
  its own bias where the derivation rests on an assumption the paper
  contradicts.
- **Require a mechanically checked verbatim quote for every claim.** The checker
  normalises whitespace and folds unicode dashes, quotes and spaces, and strips
  XML tags from both sides; it does nothing that would excuse paraphrase. It was
  canary-tested — a one-digit change to a real quote must fail, and does.
- **Suppress prior knowledge in the prompt, and test the suppression**, per
  Finding 3.
- **Filter coverage before attempting retrieval**, on `isOpenAccess`. An entry
  whose source is unreachable is *out of scope*, never *unconfirmed* — those are
  different facts about an entry and must not share a verdict.

### Costs this recommendation accepts

**About a fifth of the corpus.** Filtering on `isOpenAccess` buys a reachable,
quotable source and gives up the rest — disproportionately the older literature
that many long-standing entries rest on. Extending reach means parsing
supplementary files and reading figure images: a larger project than this one.

**Refusal is cheap; over-refusal is invisible.** A first-class "cannot confirm"
means declining entries a more determined reader could ground. That direction is
chosen knowingly: a wrongly-unconfirmed entry costs a footnote, a
wrongly-confirmed one costs a wrong answer that looks ordinary, so the cheap
direction absorbs the uncertainty. **Both directions must be measured** — a
change that reduces over-refusal will start producing false confirmations, and
only the second is dangerous.

## What this probe did not establish

Recorded because the findings will otherwise be read as stronger than they are.

- **n = 6, chosen to stress interesting cases, not sampled at random**, one
  model, one run, no repeats. Read the retrieval result as "not blocked", never
  as a rate. Zero fabrications in fifteen quotes with no repetition supports no
  interval worth quoting.
- **The sourced prompt supplied the expected units**, which leaks that a value
  in those units exists. Both entries whose value was *not* in the paper had
  units supplied, and both produced a derivation rather than stopping at
  refusal. This is a genuine confound and the fix is in "Next probes".
- **Prompting was not uniform within an arm.** One sourced agent (115327) was
  told the property may have several parts; the other five were not. That entry
  is not comparable with the rest.
- **Every source paper predates the model's training cutoff**, so no entry
  tested retrieval in the absence of prior knowledge — the condition the
  validator will actually face on new literature.
- **Arm isolation was argued, not enforced.** See the note below.
- **The grader was less reliable than the graded.** Ground truth was
  hand-built and wrong on BNID 114567 — recorded as unstated from the curator's
  note ("Calculated from the measured data, not shown in the paper"), when the
  paper does state "up to c. 40% of dry weight" and the corpus range's upper
  bound is 40.4. The agent found the stated form and corroborated it
  arithmetically. Any scored validator needs an answer key built more carefully
  than this one, or it will mark correct answers wrong. **This is the finding
  most likely to sink a rate measurement**, and it is a cost in curator time,
  not in compute.

### One thing that is not a confound

**Priming the sourced arm toward refusal was correct, not a flaw.** Its prompt
said NOT_IN_SOURCE is a correct answer and not a failure. The validator will
carry that same instruction in production — refusal *is* the desired behaviour
when a source lacks a value — so the probe measured the intended configuration
rather than contaminating it. What follows is only that the "zero false
confirmations" result describes a primed harness, which is the harness we
intend to build, and still needs re-measuring at n greater than six.

## Note on isolation between the arms

The arms ran as named subagents in one session, which share a message bus, so
contamination was possible in principle, and no subagent transcript was
persisted to rule it out from logs. The evidence is circumstantial and recorded
as such:

- All six blind agents finished (11:46:23-11:46:39) before the first sourced
  result existed (11:47:22): in that direction there was nothing to leak.
- Blind agents were fresh general-purpose agents, not forks — no experiment
  context, not told other agents existed, and they would have had to enumerate
  agents first. All six reported using no tools.
- The arms *disagree*: 65 vs 40 min, 40% vs 13-15%, 200-1000 vs 65 fg C/um^3.
  Leakage predicts convergence.

The disagreement is the load-bearing part, being the falsifiable one.

## Next probes

In priority order. The first two decide whether the validator is worth building
at the recommended scope; the third is what makes any rate credible.

1. **Reach.** Probe the supplementary-file and figure-image paths, since that is
   where the missing 78% lives and it is the only open question that could still
   make the validator infeasible at useful scale.
2. **Papers with no prior knowledge.** Repeat the sourced arm on literature
   published after the model's training cutoff, where recall cannot contribute.
   This is the condition the validator actually faces, and no entry in this
   probe tested it.
3. **An honest rate**, on a random sample rather than chosen cases, with repeats
   so variance is visible.

### Protocol corrections for those runs

Adopted from this probe's own failures; they are cheap and they are not
optional if a rate is to mean anything.

- **Do not supply expected units.** For a paper we have no prior knowledge of we
  do not know in advance which units it uses, so supplying them both leaks the
  answer's shape and makes the task easier than the real one.
- **Keep prompts byte-identical within an arm.** Differences belong between
  arms, never inside one.
- **Tell blind agents nothing about other participants**, and give them no
  reason to look.
- **Prevent inter-agent communication, or verify its absence.** Preferably run
  the arms in separate sessions, or in a harness that gives the answering agent
  no message bus. Where that is not possible, capture each agent's tool-call
  record and treat *any* tool call by a blind agent as a contamination flag —
  a blind agent has no legitimate reason to call a tool, so the check is cheap
  and unambiguous. Subagent transcripts were not persisted this time; a rate run
  must capture them.
