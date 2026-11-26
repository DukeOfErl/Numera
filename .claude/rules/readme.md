---
paths:
  - "README.md"
---

# The README is a portfolio front page

This repository is a portfolio project. Its README is read by someone seeing the work for the
first time (a reviewer, a recruiter, a curious scientist), not by a collaborator who needs to
operate it. It is not an internal developer README.

- **Value first.** What the app does and why it is interesting, then the one or two facts that make
  it credible, then the shortest path to running it, then links out.
- **Core information only.** No configuration tables, command reference, operator runbooks or
  detail that came out of one development session. Those live in `docs/development.md` and
  `docs/deployment.md`, linked from the README. A new capability worth showing off earns at most a
  line or two in "What else is in here"; its details go in a guide.
- **The web page is the interface.** Terminal use beyond the quick start belongs in the
  development guide.
- **Write for someone who has not seen the code.** Name a thing by what it is, not by its module,
  variable or in-project nickname ("the door", "the harvest store"). If a project term is needed,
  say what it is the first time. Shorthand that only makes sense with the whole codebase in context
  reads as fluent to the model that wrote it and as noise to everyone else.
- **Plain, not padded.** Short sentences, one point each. Cut caveats, history and justification a
  reader cannot act on; an ADR link carries the reasoning for whoever wants it. Keep ADR numbers
  out of the README's prose.
- **No procedural minutiae.** Shell-history hygiene, console click-paths verified on a date, API
  status-code forensics: if worth keeping at all, they go in a guide.
- **Promotional means showing value, not adjectives.**
- **Show the user the diff before rewriting or substantially editing the README.**
- One test quotes the README's prototype warning (`test_web_driver.py`); keep that claim.
