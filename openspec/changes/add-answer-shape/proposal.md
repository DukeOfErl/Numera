## Why

`grounded-answering` says nine things about what an answer must contain and nothing about the order
it says them in. That gap has a cost, and it showed up the moment specimen answers were put in front
of a domain reader on 2026-09-04: an answer written to satisfy every existing requirement opened with
"*E. coli* cell volume is not a single number. The corpus spans about fourfold across strains and
conditions" — two sentences that are true, careful, and withhold the answer. The reader's objection
was immediate: give the range, or a typical value, in the first line, and put the reasoning below it.

The gap is structural rather than accidental. Every requirement in force pushes toward hedging: cite
everything, refuse beyond the corpus, do not present one entry as settled, report disagreement with
its conditions, mark what the source did not claim. Each is right on its own, and together they
produce prose that leads with caveats because nothing tells it to lead with the finding. Nobody
noticed because no requirement was being violated.

## What Changes

- **An answer that states a quantity SHALL open with the quantity**, cited, before explanation,
  caveat or method. Where the quantity genuinely varies, the opening gives the range or a typical
  value together with what it varies with — a variation that is the answer, not a reason to decline
  to summarise.
- **Opening with a figure SHALL NOT displace what qualifies it.** This is the guard on the change:
  the conditions, the disagreements, the missing methods and the hedges that existing requirements
  demand stay in the answer, below the opening. A change that bought a crisp first line by dropping
  them would make the system worse in exactly the way this project exists to avoid.
- **A summary figure SHALL use the entries' own recorded numbers** rather than rounded
  approximations of them, and SHALL cite every entry whose figure it uses. Rounding 0.47 to 0.5 to
  make a tidier opening both invents precision the corpus does not carry and puts the answer's own
  headline outside the tolerance any value check would apply to it.
- The system prompt gains the instruction. Its five numbered rules are ordered by importance and
  this is a rule about form rather than grounding, so it goes below them rather than among them.

Not in scope: how long an answer should be, which is a question for the evaluation's conciseness
figures rather than for a requirement; any change to what an answer must contain; and the shape of a
refusal, which `A refusal follows a search` already governs and which the reviewer page confirmed
reads correctly as it stands.

## Capabilities

### New Capabilities

<!-- None. -->

### Modified Capabilities

- `grounded-answering`: gains two requirements about the order in which an answer says what it
  already has to say — the quantitative conclusion first, and the qualifications not displaced by it.
  No existing requirement's content changes.

## Impact

- **`src/scinumbers_ask/agent.py`**: the system prompt. One instruction added below the five
  numbered rules, and a note saying why it sits below them.
- **`tests/`**: the requirement-to-test mapping in `tests/test_spec_conformance.py`. The live-model
  check is the only test that can observe answer shape, and it can assert the weak form — that the
  first sentence of an answer to a well-covered question contains a digit and a citation — which is
  worth having and is not a proof.
- **Docs**: `CHANGELOG.md`. `README.md` only if it shows an example answer.
- **No behaviour change outside the prompt.** No module, event or limit is touched, so the
  evaluation harness and both drivers are unaffected.
- **The evaluation will measure this, and cannot yet.** `add-answer-evaluation` records the prompt's
  digest on every result and breaks its figures down by it, so a baseline taken before this change
  and one taken after will not be silently combined. Whether the new shape helps or hurts the
  citation and refusal figures is a question for that harness, not an assumption here.

## Deferred

- **A judged rubric for answer shape.** Whether the opening actually carries the conclusion is a
  judgement, and `add-answer-evaluation`'s judged layer is the place for it. **Raise this once that
  layer has passed its agreement gate** — a rubric added before then is another unvalidated
  instrument.
- **Whether the opening should adapt to the question.** A reader asking "roughly how big" wants one
  number; a reader asking "what is known about" wants the spread. The prompt is static in this build
  by design, so both get the same shape. **Raise this if the evaluation shows the fixed shape failing
  one kind of question**, which needs the question tags that harness records.
