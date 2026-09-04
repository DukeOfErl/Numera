# Tasks

ADR block for this change: `0560`–`0590`, allocated in the table in `CLAUDE.md`, which is the
authority. This change probably owes one ADR at most; write it with the decision, not at the end.

Small and self-contained: one instruction in the system prompt, one assertion, and the documentation.
Nothing outside `agent.py`'s prompt changes, so both drivers and the evaluation harness are
untouched.

## 1. The instruction

- [ ] 1.1 Add the answer-shape instruction to `SYSTEM_PROMPT` in `agent.py`, **below** the five
      numbered rules rather than among them, with a comment saying why: the numbered rules are ordered
      by importance and are about grounding, and this one is about form. A rule about form placed above
      a rule about grounding invites the model to trade the second for the first
- [ ] 1.2 State both halves in the instruction, because the second is the guard on the first: open with
      the quantity asked for, cited, giving the range and what it varies with where it varies; and do
      not buy that opening by dropping the conditions, hedges and computed-value inputs, which stay
      below it
- [ ] 1.3 Say in the instruction that a summary figure reuses the entries' own numbers rather than
      rounding them, and cites each entry it draws on

## 2. What can be asserted

- [ ] 2.1 Extend the `network`-marked live-model check: for a question the fixture corpus covers, assert
      the answer's first sentence contains a digit and a citation. **Be honest in the docstring about
      what this proves** — that the opening is quantitative and attributed, not that it carries the
      right conclusion. The latter is a judgement and belongs to `add-answer-evaluation`'s judged layer
- [ ] 2.2 Add the requirement-to-test mapping in `tests/test_spec_conformance.py` in the same commit as
      2.1, and record the part 2.1 cannot cover as an explicit gap rather than letting the mapping imply
      more than it checks

## 3. Documentation

- [ ] 3.1 `CHANGELOG.md`: the changed answer shape under `## [Unreleased]`, as Changed rather than
      Added — it alters what every answer looks like
- [ ] 3.2 Update `README.md` only if it shows an example answer whose shape is now wrong
- [ ] 3.3 Write the ADR only if a decision here is worth remembering. The candidate is the placement
      of a form rule below the grounding rules, and the reasoning behind it; if that ends up being a
      sentence in a code comment and nothing more, no ADR is owed

## 4. Before archiving

- [ ] 4.1 Note in the change that the prompt digest recorded by `add-answer-evaluation` is what keeps a
      baseline taken before this change from being combined with one taken after. Whether the new shape
      helps or hurts is a measurement for that harness and is **not** claimed here
- [ ] 4.2 Reconcile the ADR block against `CLAUDE.md`
