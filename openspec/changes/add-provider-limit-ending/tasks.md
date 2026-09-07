# Tasks

ADR block for this change: `0600`–`0640`. The table in `CLAUDE.md` is the authority and has been
reconciled — including the two evaluation blocks (`0500`–`0590`) that are spent on `dev` and have no
file on this branch, because a reader allocating from `main`'s table alone would otherwise take
`0500`.

One branch, `feat/provider-limit-ending`, off `main` rather than off `dev`: `main` was deliberately
cut before the evaluation work, and this behaviour has to reach the deployed app. It merges into
`main`, and `main` then merges into `dev` so the evaluation line inherits it.

## 1. The ending

- [x] 1.1 `EndReason.PROVIDER_LIMIT` in `events.py`, with the comment saying why it is not a flavour
      of `PROVIDER_FAILURE`: the two differ in whether asking again can come out differently.
- [x] 1.2 Add it to `messages.STOP_THE_RUN`, extending the comment there. Both drivers pick this up
      without changes — the terminal returns from its loop and the page retires its input.
- [x] 1.3 `_is_out_of_credit(exc)` in `agent.py`: `status_code == 402` and nothing else. Document
      which direction the uncertainty is pushed in and why that one is cheaper.
- [x] 1.4 Classify in the `except` around the loop, three ways: ours, out of credit, the provider's.
      Carry `reason` into the trail so the trail distinguishes them too.
- [x] 1.5 Emit the sentence as an `Answer` before the ending, the shape the run-budget refusal uses.
- [x] 1.6 Stop retrying a 402 in `_retry_on`, beside the spend-ceiling refusal already there.

## 2. What proves it

- [x] 2.1 `test_a_key_out_of_credit_says_what_happened_and_stops_the_run` — the reason, the sentence,
      `STOP_THE_RUN` membership, and `attempts == 1` for the no-retry half.
- [x] 2.2 The **other direction**, in the existing exhausted-retries test: an outage must not land in
      `STOP_THE_RUN`. This is the expensive direction, so it is asserted rather than assumed.
- [x] 2.3 `test_the_attribute_this_rule_reads_is_on_the_provider_s_own_error` — a real
      `openai.APIStatusError`, not a stand-in carrying `status_code`, so a rename in a library this
      project does not own fails here instead of silently retiring the rule.
- [x] 2.4 `OutOfCreditModel` and `out_of_credit_error()` in `agent_doubles.py`.
- [x] 2.5 `EndReason.PROVIDER_LIMIT` added to the terminal's non-zero-exit parametrisation. The web
      driver's stop test is parametrised over `STOP_THE_RUN` and extends itself.
- [x] 2.6 Fault seeding, both mutations of the rule, into a copy: `return False` fails 2.1 and 2.3;
      `return True` fails 2.2 and 2.3. Neither survives, and each is caught by the test that should
      catch it.

## 3. The record

- [x] 3.1 ADR-0600, written with the decision: the three options, why a reason rather than a flag,
      and the cost accepted.
- [x] 3.2 Spec delta — an `ADDED` requirement under `spend-control`. Nothing existing changes
      meaning, and a `MODIFIED` block would be impossible on this branch anyway: `main` was cut
      before `add-ask-agent` was archived, so `grounded-answering` and `spend-control` are not yet in
      `openspec/specs/`.
- [x] 3.3 Conformance mapping in `tests/test_spec_conformance.py`, in this change rather than later.
- [x] 3.4 `CHANGELOG.md` under Unreleased.

## Not in this change

- **Per-visitor budgets.** One run label per hosted instance means one shared pot; splitting it
  changes what a run is to the ledger and to the evaluation reading it.
- **A sentence for the other provider failures.** Silence is right for an error a retry may clear.
