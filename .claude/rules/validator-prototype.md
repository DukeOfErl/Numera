---
paths:
  - "src/bionumbers/**"
  - "review_app.py"
  - "tests/test_bionumbers_*.py"
  - "tests/test_review_app*.py"
  - "openspec/changes/add-validator-prototype/**"
---

# How to report on the validator prototype

Agreed with Yoav on 2026-09-18, for `add-validator-prototype` only. The prototype
will be rebuilt; what he is deciding now is the high-level shape and what a
reviewer gets.

**Do the verification; do not narrate it.** Tests, fault seeding, mutation runs
and the canary still happen, ideally in the background, per the project's
testing rules. Reporting them is limited to one short clause ("tests and seeding
done") unless something does **not** work as expected -- a failing test, a
surviving mutant that matters, a spec scenario the code cannot meet. Those are
reported in full.

**Report decisions, not defences.** No paragraphs on what could go wrong and
which test catches it. Lead with what was built, what the reviewer sees, and any
choice that is Yoav's to make.

This is a reporting rule, not a testing rule. It changes what reaches the user,
never what gets run.
