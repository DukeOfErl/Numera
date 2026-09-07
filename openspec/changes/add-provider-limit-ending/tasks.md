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
- [x] 1.5 Present whatever the model established, substituting the agent's own statement only where
      there is none — the shape the spend-ceiling branch beside it already uses.
- [x] 1.6 Stop retrying a 402 in `_retry_on`, beside the spend-ceiling refusal already there.

## 1b. What the review found (all three MEDIUMs and both LOWs)

- [x] 1b.1 The first version yielded a canned notice *as* the answer, discarding the model's partial
      text. A 402 usually lands part-way through a question whose earlier hops were paid for, so that
      was the common case, not a corner.
- [x] 1b.2 `evidence()` gained `judge_the_prose`. It was analysing the discarded text: a citation
      warning accusing prose the reader never saw, or `UngroundedRefusal` about a system notice, with
      `answer.ungrounded` in the trail for a question the model never answered. The entries table
      still goes out — retrieval is not a judgement about prose.
- [x] 1b.3 `messages.run_over_advice(reason)` and `web.run_over_advice(transcript)`: the deployment
      sentence moved out of the agent, and the page's "start a new session" banner — wrong for a spent
      key, and the last thing on screen — is replaced rather than contradicted. The terminal prints
      the same sentence before exiting.
- [x] 1b.4 The negative cases in the attribute test were status-less exceptions, so `status_code is
      not None` passed the entire suite while turning every 429 and 502 into a closed run. Real
      `APIStatusError`s at 429, 502 and 401 now pin it.
- [x] 1b.5 The spec said "no further question is accepted until the limit is raised". `run_is_over`
      reads session state, so it is per session; the scenario now says so, and ADR-0600 records why
      closing it process-wide is not in this build.
- [ ] 1b.6 **When `main` merges into `dev`:** `evaluation.py:492` stops on
      `EndReason.RUN_BUDGET` alone, not on `STOP_THE_RUN`. A key spent mid-run would otherwise leave
      the harness asking every remaining question, recording the agent's statement as the answer and
      scoring each as an ungrounded non-answer — a results file that reads as the model failing rather
      than as a run that aborted. Widen that check to `messages.STOP_THE_RUN` in the merge.

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
- [x] 2.6 Fault seeding into a copy, five mutants, each dying against the test that should catch it:
      `return False` → the out-of-credit tests; `return True` → the exhausted-retries test;
      `status_code is not None` → the attribute test (this one **survived** the first round, which is
      what sent 1b.4 back); always substituting the notice → the keeps-the-answer test; always judging
      the prose → the never-saw test.
- [x] 2.7 Both drivers, because the advice is a shared claim and a driver that dropped it would be
      under-reporting: the terminal prints it before exiting, the page replaces its own banner, and an
      ending with no advice adds no line in either.

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
