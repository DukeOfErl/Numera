"""Every requirement is named by a test, or is explicitly recorded as unmapped.

The failure this exists for is not a wrong test. It is a requirement that nothing
checks, which is indistinguishable from a satisfied one: the suite is green, the
spec validates, and the two are describing different systems.

That happened here. `grounded-answering` had always required bounding "the number
of tool calls made in answering a single question". The code bounded *model* calls
and reported those. On most questions the two move together, so nothing noticed
until a model batched several tool calls into one hop and twelve model calls
bought twenty-nine retrievals -- $0.27 on one question. `openspec validate
--strict` passed throughout, because it validates the shape of a spec and not
whether anything implements it.

**What this catches and what it does not.** It catches a requirement no test
claims, and a claim naming a test that does not exist (a rename, a typo, a deleted
test). It does not prove conformance: a test can claim a requirement and check the
wrong thing, which is exactly what the retrieval-bound tests did for months. What
it buys is that the requirement's own words sit next to the name of the test
asserting them, where a reader comparing the two can see the mismatch. That is a
review aid, not a proof, and it should not be described as more.

Deliberately a mapping file rather than a marker on each test. A marker would need
touching every test to be complete and would still leave the gaps invisible until
someone counted; here the gaps are a list, in one place, that has to be edited to
grow.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
OPENSPEC = ROOT.parent / "openspec"

#: The promoted spec, plus the deltas of changes still open. Deliberately **not**
#: `changes/` recursively, which is what this read until the project's first archive:
#: archiving moves a change under `changes/archive/` and promotes its requirements
#: into `specs/`, so a recursive read would count both -- and, once a second change
#: modifies a requirement, would keep finding the superseded wording next to the name
#: of the test asserting the current one. Comparing those two is the only thing this
#: file buys, so it has to read the version that is in force. The `*/specs/` glob is
#: one level deep and so cannot reach `archive/<change>/specs/`.
SPECS = sorted(OPENSPEC.joinpath("specs").rglob("spec.md")) + sorted(
    OPENSPEC.joinpath("changes").glob("*/specs/**/spec.md")
)

# requirement name -> the tests that assert it.
COVERED: dict[str, tuple[str, ...]] = {
    "The agent communicates through events and commands only": (
        "test_driver_independence.py::test_the_agent_takes_no_parameter_naming_its_caller",
        "test_driver_independence.py::test_no_agent_module_reaches_for_a_driver",
    ),
    "Unattended operation is a driver, not a mode": (
        "test_driver_independence.py::test_both_drivers_put_questions_to_the_same_agent",
    ),
    "Session state survives a process boundary": (
        "test_session_process_boundary.py::test_a_session_continues_in_a_process_that_did_not_create_it",
    ),
    "Sessions are isolated from one another": ("test_agent.py::test_two_sessions_share_nothing",),
    # Partly, and the part matters: of the requirement's five scenarios, these
    # tests hold two -- "A question records what it asks" and "Incomplete entries
    # are in the set" -- plus the sentence about failing without a set. **Three are
    # not held.** "Question set supplied -> each question is asked and scored" needs
    # the driver (group 3); "Figures per tag" and the per-shape figures need the
    # report (group 4). Nor does anything assert that question sets are not
    # generated at evaluation time; that one is structural rather than testable, and
    # saying so here is better than implying a test covers it.
    #
    # An earlier version of this entry also named a test asserting the *command's*
    # structure-only wording, which appears in no clause of the requirement. A
    # mapping that names a test checking something else is exactly the failure this
    # file admits it cannot detect, so it is worth not making by hand.
    # Remapped when 4.13 landed. It was a recorded gap while ADR-0530's rewrite was
    # unbuilt, because the tests then present asserted the superseded semantics --
    # prose citation -- and would have read as covering three clauses they never
    # mentioned.
    "Scoring is based on entry identifiers, not answer text": (
        "test_scoring.py::test_every_expected_entry_reaching_the_table_is_the_pass",
        "test_scoring.py::test_an_expected_entry_never_reaching_the_table_fails_the_check",
        "test_scoring.py::test_an_entry_cited_without_being_retrieved_has_still_reached_the_table",
        "test_scoring.py::test_the_rank_of_each_expected_entry_in_the_table_is_reported",
        "test_scoring.py::test_an_admissible_citation_is_neither_a_hit_nor_unexpected",
        "test_scoring.py::test_a_question_expecting_nothing_does_not_pass_the_table_check",
        "test_report.py::test_the_two_kinds_of_missed_entry_are_reported_apart",
        "test_report.py::test_an_unexpected_citation_is_reported_as_not_an_error",
    ),
    "The asked property and organism are recognised": (
        "test_scoring.py::test_an_abbreviated_search_counts_as_searching_for_the_organism",
        "test_scoring.py::test_searching_for_another_organism_does_not_count",
        "test_scoring.py::test_a_keyword_counts_as_looking_for_the_property",
        "test_scoring.py::test_what_the_agent_settled_on_is_counted_apart_from_what_it_searched",
        "test_repository.py::test_resolution_is_what_search_uses_not_a_copy_of_it",
    ),
    # The scoring half. That the *set* must contain unsupported questions is
    # checked by `test_question_set.py`'s flag validation; that the corpus cannot
    # answer them is 4.11's check, listed here because a set whose flag is wrong
    # makes this requirement's figures meaningless.
    "Unsupported questions are part of the set": (
        "test_scoring.py::test_an_unsupported_question_answered_with_a_figure_is_a_fabrication",
        "test_scoring.py::test_an_unsupported_question_declined_in_words_alone_is_a_decline",
        "test_scoring.py::test_the_quantity_rule_over_flags_and_that_is_the_direction_chosen",
        "test_question_set.py::test_an_unsupported_question_the_corpus_can_answer_is_refused",
        "test_report.py::test_a_fabrication_on_an_unsupported_question_is_listed_with_its_answer",
    ),
    "The agent's own grounding warnings are scored": (
        "test_scoring.py::test_the_agents_warnings_are_counted_not_recomputed",
        "test_scoring.py::test_a_refusal_with_no_search_behind_it_is_never_a_correct_decline",
        "test_scoring.py::test_a_refusal_that_searched_first_is_a_correct_decline",
    ),
    "A cited entry at odds with its peers is flagged": (
        "test_scoring.py::test_the_entry_that_motivated_the_check_is_flagged",
        "test_scoring.py::test_an_entry_inside_its_peers_interval_is_not_flagged",
        "test_scoring.py::test_peers_are_the_same_organism",
        "test_scoring.py::test_peers_must_share_the_unit_as_well_as_the_organism",
        "test_scoring.py::test_an_entry_the_question_does_not_expect_is_not_a_peer",
        "test_scoring.py::test_an_unexpected_citation_is_still_judged_against_what_was_expected",
        "test_scoring.py::test_a_citation_with_too_few_peers_is_reported_as_unjudged",
        "test_report.py::test_an_outlier_is_listed_with_the_interval_its_peers_occupy",
        "test_report.py::test_a_comparison_that_could_not_be_made_is_said_rather_than_omitted",
    ),
    "Run-to-run variation is measured, not averaged away": (
        "test_evaluation.py::test_each_question_is_asked_once_per_repeat_in_its_own_session",
        "test_scoring.py::test_a_question_citing_different_entries_across_repeats_is_unstable",
        "test_scoring.py::test_a_spread_over_no_values_is_unknown_rather_than_zero",
    ),
    "A report can be produced from a partial results file": (
        "test_report.py::test_a_partial_run_says_so_before_any_figure",
        "test_report.py::test_an_empty_results_file_is_reported_as_empty_not_as_zeros",
        "test_report.py::test_a_run_stopped_on_its_budget_is_distinguished_from_a_completed_one",
        "test_report.py::test_figures_are_never_combined_across_a_different_prompt_or_corpus",
    ),
    "Cost and effort are reported": (
        "test_report.py::test_spend_in_this_session_is_reported_apart_from_the_runs_total",
        "test_report.py::test_how_often_each_bound_was_reached_is_reported",
    ),
    "Results are recorded as each question completes": (
        "test_evaluation.py::test_each_result_is_on_disk_before_the_next_question_is_asked",
        "test_evaluation.py::test_a_question_that_raises_is_recorded_as_a_failure_and_the_run_goes_on",
        "test_evaluation.py::test_a_partial_last_line_is_an_interruption_and_is_tolerated",
    ),
    # The first scenario only. The second -- spend in this session reported apart
    # from total spend across the run -- is the report's, in group 4; the record
    # carries both figures and nothing yet reads them out.
    "An interrupted run resumes without repeating work": (
        "test_evaluation.py::test_only_the_questions_with_no_result_are_asked_again",
        "test_evaluation.py::test_resumption_counts_a_repeat_as_its_own_attempt",
        "test_evaluation.py::test_a_follow_up_whose_parent_is_missing_is_asked_again",
    ),
    "Recorded results are usable by external evaluation tools": (
        "test_evaluation.py::test_a_record_is_readable_without_this_projects_reader",
        "test_evaluation.py::test_a_results_file_from_another_version_is_refused",
    ),
    "Every result records what produced it": (
        "test_evaluation.py::test_every_result_carries_the_provenance_of_the_run",
        "test_evaluation.py::test_provenance_records_the_three_things_that_move_the_figures",
        "test_evaluation.py::test_a_different_corpus_gets_a_different_digest",
        "test_evaluation.py::test_the_code_version_says_which_kind_of_answer_it_is",
    ),
    "The context shown to the agent is recorded verbatim": (
        "test_evaluation.py::test_the_context_recorded_is_what_the_agent_was_shown",
        "test_evaluation.py::test_a_question_that_retrieved_nothing_records_an_empty_context",
        "test_evaluation.py::test_a_context_that_could_not_be_read_is_not_recorded_as_empty",
        "test_agent.py::test_the_context_a_session_was_shown_is_readable_from_it",
        "test_agent.py::test_a_search_that_matched_nothing_is_recorded_rather_than_dropped",
    ),
    "The question set is explicit and versioned with its answers": (
        "test_question_set.py::test_a_supported_question_reads_back_as_it_was_written",
        "test_question_set.py::test_no_question_set_is_refused_with_an_explanation",
        "test_question_set.py::test_a_question_records_the_property_and_organism_it_asks",
        "test_question_set.py::test_a_comparison_question_records_every_organism_it_asks_about",
        "test_question_set.py::test_a_set_of_complete_entries_alone_is_refused",
        "test_question_set.py::test_a_set_read_from_a_file_can_satisfy_the_corpus_check",
    ),
    "The corpus is read-only": ("test_repository.py::test_entries_cannot_be_mutated",),
    "Retrieval effort is bounded and reported": (
        "test_agent.py::test_retrieval_stops_at_its_own_bound_not_at_the_model_call_limit",
        "test_agent.py::test_a_declined_call_is_still_reported_as_something_that_happened",
    ),
    "A build is announced before it begins, not after it ends": (
        "test_corpus_autobuild.py::test_the_build_is_announced_before_it_happens",
        "test_corpus_autobuild.py::test_an_existing_corpus_is_used_and_never_rebuilt",
    ),
    "A corpus that cannot be built is explained, not raised": (
        "test_corpus_autobuild.py::test_a_refused_destination_reaches_the_reader_as_a_message",
        "test_corpus_autobuild.py::test_without_the_ingester_the_error_still_names_the_export",
        "test_corpus_autobuild.py::test_nothing_to_build_from_leaves_the_ordinary_error",
        "test_corpus_autobuild.py::test_the_terminal_shows_the_refusal_rather_than_a_traceback",
        "test_corpus_autobuild.py::test_the_page_shows_the_refusal_rather_than_a_traceback",
    ),
    "A refusal follows a search": (
        "test_agent.py::test_an_answer_with_no_retrieval_behind_it_is_reported",
        "test_agent.py::test_an_answer_claiming_searches_it_never_made_is_reported_as_such",
        "test_agent.py::test_an_answer_that_searched_is_not_reported",
    ),
    "Values are compared only when dimensionally compatible": (
        "test_units.py::test_an_unrecognised_unit_is_not_guessed_at",
        "test_units.py::test_a_recognised_unit_names_what_it_measures",
    ),
    "Conversation growth is bounded, and the bound is announced before it bites": (
        "test_agent.py::test_a_session_at_the_bound_refuses_rather_than_dropping_context",
        "test_agent.py::test_the_user_is_warned_before_the_conversation_bound_bites",
    ),
    "Per-question limits reset within a session; run limits do not": (
        "test_spend.py::test_a_resumed_session_warns_against_its_own_ceiling_not_the_environment",
    ),
    # add-provider-limit-ending's, mapped with the change that adds it. One test per
    # claim the requirement makes, and the last three are the ones a reader comparing
    # words to tests should look at hardest: what must *not* be classified as a spent
    # key, and that both drivers say the same thing about the remedy.
    "A refused-for-credit request ends the question as a limit, not a failure": (
        "test_agent.py::test_a_key_out_of_credit_says_what_happened_and_stops_the_run",
        "test_agent.py::test_a_key_out_of_credit_keeps_the_answer_it_had_already_paid_for",
        "test_agent.py::test_what_retrieval_found_before_the_refusal_is_still_shown",
        "test_agent.py::test_nothing_is_judged_about_prose_the_reader_never_saw",
        "test_agent.py::test_the_attribute_this_rule_reads_is_on_the_provider_s_own_error",
        "test_agent.py::test_exhausted_retries_end_the_question_as_a_provider_failure",
        "test_terminal_driver.py::test_a_spent_key_names_the_remedy_before_the_terminal_exits",
        "test_web_driver.py::test_an_ending_a_new_session_cannot_fix_replaces_that_advice",
        "test_web_driver.py::test_the_advice_names_the_remedy_without_addressing_anyone",
    ),
    # add-durable-trail's, mapped with the change that adds it. The requirement
    # inverts the spend gate deliberately (ADR-0710), so the tests to compare
    # against its words hardest are the two failure ones: they vary *where* the
    # write failed, which is the dimension the code branches on.
    #
    # There were three, and the third was withdrawn rather than kept. It passed a
    # `TimeoutError` while leaving the double's delay at zero, so what it varied
    # was the exception class and not the duration -- the `_is_out_of_credit`
    # shape recorded in CLAUDE.md, found by a review pass and not by the suite.
    #
    # The "destination is slow" scenario is closed by the `network` tests at the
    # end of this list rather than by a faked one, because `record` has no
    # client-side deadline to exercise: a slow write is bounded by `SET LOCAL
    # statement_timeout`, which the *server* enforces, so a sleep in a double
    # would have measured the double. Those four are deselected by default
    # (`pytest -m network`), so this requirement is the one place in this file
    # where part of the evidence does not run in an ordinary green suite.
    "Recording is best-effort and never fails a question": (
        "test_trail_store.py::test_a_failure_to_open_the_transaction_is_swallowed_and_counted",
        "test_trail_store.py::test_a_failure_to_execute_the_statement_is_swallowed_and_counted",
        "test_trail_store.py::test_a_failed_write_is_attempted_exactly_once",
        "test_trail_store.py::test_no_exception_type_escapes_record",
        "test_trail_store.py::test_a_direct_caller_needs_no_error_handling",
        "test_trail_store.py::test_the_failure_counter_answers_whether_anything_is_landing",
        "test_trail_store.py::test_the_process_wide_counter_sees_failures_from_any_store",
        "test_trail_store.py::test_a_dropped_record_is_reported_to_stderr",
        "test_trail_store.py::test_the_report_carries_no_traceback",
        "test_trail_store.py::test_a_schema_failure_is_reported_and_counted_apart_from_dropped_writes",
        "test_trail_store.py::test_the_handler_never_raises_so_logging_never_reaches_handle_error",
        "test_trail_store.py::test_install_attaches_a_handler_even_when_the_schema_cannot_be_created",
        "test_trail_store.py::test_a_store_that_cannot_reach_its_destination_does_not_connect_per_call",
        "test_trail_store.py::test_a_destination_that_was_asleep_at_startup_is_used_once_it_wakes",
        "test_trail_store_live.py::test_a_statement_that_runs_too_long_is_cancelled_rather_than_waited_out",
        "test_trail_store_live.py::test_the_timeout_does_not_leak_onto_the_next_pooled_transaction",
        "test_trail_store_live.py::test_an_unreachable_host_does_not_raise_out_of_record",
        "test_trail_store_live.py::test_the_schema_and_the_insert_are_valid_sql",
    ),
    # add-answer-feedback's, mapped with the change that adds them. Only the two
    # that are genuinely asserted; the other three are in AWAITING_THE_WIDGET
    # until the real script can be driven.
    #
    # The second is the one to compare against its words hardest. It is stated as
    # what the model was *shown*, because the alternative phrasing -- "the next
    # answer is unchanged" -- is a counterfactual about a non-deterministic run
    # that nothing can assert. Its test carries a positive control for the same
    # reason: every other assertion in it is a `not in`, which an empty haystack
    # satisfies.
    # Three of four scenarios. "A conversation is reopened and an answer rated"
    # is **not** held: `test_one_session_s_ratings_do_not_suppress_another_s` is
    # two session dictionaries sharing one identifier, which is state isolation
    # and not the position-instability the scenario is about. Recorded here rather
    # than left to read as covered, because that scenario needs the driver.
    "A rating names the question it is about, and outlives the session": (
        "test_feedback.py::test_a_verdict_is_recorded_against_its_question",
        "test_feedback.py::test_two_answers_rated_in_one_session_name_different_questions",
        "test_feedback.py::test_a_comment_is_a_second_record_naming_the_same_question",
        "test_feedback.py::test_the_identifier_recorded_is_the_one_the_question_s_trail_uses",
        "test_feedback.py::test_a_verdict_reaches_the_durable_store",
        "test_trail_store_live.py::test_the_schema_and_the_insert_are_valid_sql",
    ),
    # "An answer is rated down -> no further retrieval or model call is made on
    # account of the rating" is not separately asserted; it holds structurally,
    # since `feedback` cannot reach the agent at all, which is what the
    # independence test pins.
    # The three that were AWAITING_THE_WIDGET. Each is mapped to the driver tests
    # that answer the half a function cannot: what is *offered*, and where.
    "A reader can rate an answer, and rating is never required": (
        "test_web_driver_feedback.py::test_an_answered_question_offers_a_rating",
        "test_web_driver_feedback.py::test_the_control_appears_on_the_run_that_answered",
        "test_web_driver_feedback.py::test_each_answer_is_offered_exactly_one_control",
        "test_web_driver_feedback.py::test_the_rating_sits_with_the_prose_and_not_with_the_evidence",
        "test_web_driver_feedback.py::test_a_redrawn_turn_puts_the_rating_in_the_same_place",
        "test_web_driver_feedback.py::test_an_unrated_answer_records_nothing_and_the_page_goes_on",
        "test_feedback.py::test_a_verdict_is_recorded_against_its_question",
    ),
    "A rating may carry a comment, offered only once an answer has been disapproved of": (
        "test_web_driver_feedback.py::test_a_comment_box_appears_only_after_a_rating",
        "test_web_driver_feedback.py::test_approval_is_not_asked_what_went_wrong",
        "test_web_driver_feedback.py::test_approval_is_still_recorded",
        "test_web_driver_feedback.py::test_the_control_is_settled_once_a_rating_is_given",
        "test_web_driver_feedback.py::test_the_comment_and_its_button_submit_together",
        "test_web_driver_feedback.py::test_a_comment_is_recorded_against_the_same_answer",
        "test_feedback.py::test_a_comment_without_a_rating_is_refused",
    ),
    "Recording a rating never disrupts the reader": (
        "test_web_driver_feedback.py::"
        "test_a_store_that_cannot_be_written_to_does_not_reach_the_reader",
        "test_web_driver_feedback.py::test_the_page_survives_a_rating",
        "test_feedback.py::test_a_rating_that_cannot_be_stored_does_not_raise",
        "test_feedback.py::test_a_handler_that_raises_does_not_reach_the_reader",
        "test_feedback.py::test_rating_the_same_answer_again_records_nothing",
    ),
    "The model is never shown a rating or a comment": (
        "test_feedback.py::test_neither_a_verdict_nor_a_comment_reaches_the_model",
        "test_feedback.py::test_a_comment_written_as_an_instruction_is_stored_as_given",
        "test_driver_independence.py::test_the_agent_cannot_reach_a_reader_s_feedback",
        "test_driver_independence.py::test_no_agent_module_reaches_for_presentation",
    ),
    # `add-question-and-answer-records`. Eleven scenarios. A scenario that merely
    # executes is a gap, not a pass, so which is which is written out:
    #
    # **Passes (8).** "A question is answered", "Two questions ask different
    # things", "An answer rests on retrieved entries", "A question ends without an
    # answer", "The records cannot be written", "A further question follows a
    # recorded one", "Two questions run in one session", "No durable destination is
    # configured" (`test_trail_store.py::
    # test_install_with_no_engine_returns_none_and_adds_no_handler`). The
    # requirement's prose obligation -- that a reader can learn from the interface
    # what is kept -- is held by the two interface tests named below.
    #
    # **Gaps (3)**, all pre-dating this change and none of them made worse by it:
    # "A search was truncated" and "Two questions in one session are related
    # afterwards" run inside `test_trace_tagging.py` but are asserted against the
    # trail's shape rather than against these words; "The process that wrote the
    # records is replaced" needs a real restart against a real database and lives
    # behind the `network` marker, which the offline suite deselects.
    # `add-user-identity`. Every requirement is claimed below; the scenarios that
    # are *executed but not asserted* -- gaps, by this file's own rule -- are:
    #   - "A reader signs out ... the next visit begins at sign-in": `st.logout`
    #     is offered and its callback forgets the registry entry, but AppTest
    #     cannot click through an OIDC logout; the next-visit half is unasserted.
    #   - "An account is enrolled after being refused ... proceeds": the refusal
    #     is held per session, so this needs a new session; not driven.
    #   - "One tester's cap is exhausted ... another's is answered as usual": the
    #     ending exists (ADR-0600) and keys are per agent, but the two are not
    #     driven together against a 402 in one deployment.
    #   - "A person's records can be found": `sql/feedback.sql` query 8, run by
    #     hand against Neon, not a test.
    #   - "The credential is never shown": asserted over the elements the tests
    #     draw, not over every page state.
    "A reader signs in before anything is shown, and identity comes from the provider": (
        "test_web_driver_identity.py::"
        "test_a_visitor_who_is_not_signed_in_is_offered_sign_in_and_nothing_else",
        "test_web_driver_identity.py::"
        "test_an_enrolled_account_is_admitted_and_its_records_carry_who_and_as_what",
        "test_web_driver_identity.py::test_the_sidebar_says_who_is_signed_in_and_offers_sign_out",
        "test_web_driver_identity.py::test_signing_out_forgets_the_session_s_identity",
        "test_web_driver_identity.py::test_signed_in_email_is_none_without_is_logged_in",
    ),
    "An account must be enrolled, and enrolment happens outside the application": (
        "test_web_driver_identity.py::"
        "test_a_signed_in_account_that_is_not_enrolled_is_refused_and_recorded",
        "test_web_driver_identity.py::test_a_refusal_is_recorded_once_per_session_not_once_per_rerun",
        "test_web_driver_identity.py::"
        "test_an_unreadable_accounts_table_admits_nobody_and_says_a_different_sentence",
        "test_web_driver_identity.py::test_an_unavailable_check_is_retried_on_the_next_rerun",
        "test_web_driver_identity.py::test_no_database_at_all_says_so_rather_than_asking_the_reader_to_wait",
        "test_accounts.py::test_an_unreadable_table_raises_rather_than_answering_none",
        "test_accounts.py::test_a_disabled_account_is_none_exactly_as_an_absent_one_is",
    ),
    "Every enrolled account holds one role, and permissions are granted by a default-deny table": (
        "test_permissions.py::test_dev_and_admin_are_granted_the_dev_panel",
        "test_permissions.py::test_each_tester_role_is_refused_the_dev_panel",
        "test_permissions.py::test_no_identity_is_refused",
        "test_permissions.py::test_the_two_populations_partition_the_roles",
        "test_permissions.py::test_the_table_has_a_row_for_every_role_and_names_only_known_permissions",
        "test_permissions.py::test_every_permission_is_refused_to_some_role",
        "test_permissions.py::test_the_refusal_names_the_permission_and_nothing_about_the_account",
        "test_identity_never_reaches_the_agent.py::"
        "test_the_same_question_under_two_roles_hands_the_model_identical_inputs",
        "test_driver_independence.py::test_identity_never_enters_the_agent_the_trail_or_the_feedback",
        "test_web_driver_dev_panel.py::test_the_refusal_does_not_depend_on_the_caller",
        "test_web_driver_dev_panel.py::test_a_tester_s_page_has_no_such_section",
    ),
    "Each tester's questions are funded by a credential of their own, capped, and never shown "
    "to them": (
        "test_identity_never_reaches_the_agent.py::test_two_agents_with_two_keys_send_two_keys",
        "test_web_driver_identity.py::"
        "test_an_enrolled_account_with_no_credential_meets_a_door_of_its_own",
        "test_web_driver_identity.py::test_the_no_credential_door_is_its_own_state_not_an_open_one",
        "test_web_driver_identity.py::"
        "test_agent_for_refuses_rather_than_falling_back_to_the_environment",
        "test_web_driver_identity.py::test_the_credential_is_never_on_the_page",
        "test_web_driver_identity.py::test_two_sessions_get_two_agents_and_one_repository",
    ),
    "What is kept about a person, and that they are told": (
        "test_identity_never_reaches_the_agent.py::"
        "test_two_sessions_under_two_identities_each_carry_their_own",
        "test_web_driver_identity.py::test_two_accounts_on_one_shared_link_get_two_sessions",
        "test_web_driver_identity.py::"
        "test_a_session_pruned_for_idleness_is_stamped_again_when_its_reader_returns",
        "test_web_driver_identity.py::"
        "test_ending_a_session_clears_the_identity_the_panel_and_the_place",
        "test_identity_never_reaches_the_agent.py::test_the_role_is_written_as_it_was_at_record_time",
        "test_identity_never_reaches_the_agent.py::"
        "test_a_verdict_in_a_signed_in_session_carries_the_identity",
        "test_trail_store.py::test_the_handler_carries_the_role_beside_the_email",
        "test_web_driver_identity.py::test_the_sidebar_says_who_is_signed_in_and_offers_sign_out",
        "test_web_driver_identity.py::test_the_note_is_one_short_sentence_whatever_is_configured",
    ),
    "An operator can see a session's own trail": (
        "test_web_driver_dev_panel.py::test_an_operator_s_page_has_the_section",
        "test_web_driver_dev_panel.py::test_a_tester_s_page_has_no_such_section",
        "test_web_driver_dev_panel.py::test_a_fresh_operator_session_shows_the_section_empty",
        "test_web_driver_dev_panel.py::test_the_table_names_the_question_just_asked",
        "test_web_driver_dev_panel.py::test_the_entries_come_first_and_the_trail_second",
        "test_web_driver_dev_panel.py::test_the_strip_is_below_the_run_status",
        "test_web_driver_dev_panel.py::test_two_sessions_panels_show_only_their_own_records",
        "test_web_driver_dev_panel.py::test_the_panel_s_contents_do_not_reach_the_model",
    ),
    "Concurrent sessions are capped for the whole deployment, not per client address": (
        "test_web_driver_session_cap.py::test_the_session_past_the_cap_is_told_to_try_later",
        "test_web_driver_session_cap.py::test_an_admitted_session_is_never_ended_to_make_room",
        "test_web_driver_session_cap.py::test_a_session_that_goes_idle_frees_a_place",
        "test_web_driver_session_cap.py::test_nothing_reads_the_client_s_address",
        "test_web_driver_session_cap.py::test_a_refused_visitor_holds_no_place",
        "test_web_driver_session_cap.py::"
        "test_a_session_mid_conversation_is_not_turned_away_when_the_cap_fills",
        "test_web_driver_session_cap.py::test_a_genuinely_new_session_is_still_refused_at_the_cap",
        "test_web_driver_session_cap.py::test_a_visitor_who_has_not_passed_the_door_holds_no_place",
    ),
    "A deployment with no identity configured behaves as before": (
        "test_web_driver_identity.py::"
        "test_with_no_identity_configured_a_question_is_answered_without_signing_in",
        "test_web_driver_identity.py::test_with_no_identity_configured_the_page_says_so",
        "test_web_driver_dev_panel.py::test_the_developer_s_machine_sees_the_panel",
        "test_identity_never_reaches_the_agent.py::test_no_key_reads_the_environment_exactly_as_before",
        "test_identity_never_reaches_the_agent.py::"
        "test_a_session_nobody_is_signed_in_to_writes_null_for_both",
    ),
    "The deterministic layer is logged under a per-question identifier": (
        "test_question_and_answer_records.py::"
        "test_two_different_questions_record_what_each_actually_asked",
        "test_question_and_answer_records.py::"
        "test_a_question_that_ends_without_an_answer_still_recorded_what_was_asked",
        "test_question_and_answer_records.py::"
        "test_the_question_is_recorded_before_the_work_that_might_fail",
        "test_question_and_answer_records.py::"
        "test_two_different_answers_are_recorded_under_the_questions_that_produced_them",
        "test_question_and_answer_records.py::"
        "test_the_answer_is_recorded_verbatim_rather_than_shortened",
        "test_question_and_answer_records.py::test_every_ending_that_gives_an_answer_records_it",
        "test_question_and_answer_records.py::"
        "test_the_answer_is_recorded_even_when_the_driver_abandons_the_generator",
        "test_question_and_answer_records.py::"
        "test_the_cited_set_and_the_retrieved_set_stay_apart_in_the_record",
        "test_question_and_answer_records.py::"
        "test_the_whole_retrieved_set_is_recorded_not_the_head_the_driver_shows",
        "test_question_and_answer_records.py::"
        "test_a_question_that_retrieved_nothing_records_no_evidence_row",
        "test_question_and_answer_records.py::test_nothing_recorded_here_reaches_the_model",
        "test_question_and_answer_records.py::"
        "test_a_destination_that_cannot_be_written_does_not_fail_a_question",
        "test_question_and_answer_records.py::"
        "test_the_records_reach_the_durable_store_under_the_question_s_own_identifier",
        "test_question_and_answer_records.py::test_no_driver_records_the_question_as_well",
        "test_question_and_answer_records.py::"
        "test_the_page_says_that_questions_and_answers_are_kept",
        "test_question_and_answer_records.py::"
        "test_the_terminal_says_it_too_including_for_a_single_question",
        "test_trace_tagging.py::test_every_record_carries_the_run_label",
    ),
}

# Requirements with no test named yet. Listed rather than omitted: the point of this
# file is that a gap is written down, not that there are none. Completing the
# mapping is task 10.9.
TESTED_BUT_UNNAMED = (
    "Events carry enough detail to show progress and to explain an ending",
    "A transient failure does not end a question",
    "Follow-up questions inherit the conversation",
    "Citations in a follow-up stand on their own",
    "Search returns compact rows, bounded in number",
    "A stored value is presented as what it measures",
    "A search records which entries it returned",
    "Organism and property matching is tolerant, not exact",
    "A keyword search reaches an entry's own keywords",
    "The corpus vocabulary is discoverable",
    "Common naming variants resolve without a round trip",
    "Full entries are retrieved individually and expose their cross-references",
    "Every quantitative claim cites its entries",
    "Citations use one stated format",
    "Every answer is accompanied by the entries behind it",
    "Answers come only from the corpus",
    "Disagreement is reported with its conditions",
    "Computed values are shown with their inputs",
    "Spend is taken from what the provider reports",
    "A pre-request gate stops work before the ceiling is crossed",
    "A configurable ceiling, with the warning derived from it",
    "An answer that ran to its ceiling says so",
    "A question ended on the ceiling reports what it established",
    "A run of questions carries its own budget",
    "A run stopped on budget is distinguishable from a completed run",
    "Spend state persists across processes",
    "An expensive question is flagged before work begins",
    "Spend is always reported",
)

# add-corpus-ingestion's. The ingester's requirements, mapped the same way — added
# with the merge that made them visible here, which is the rule this file states.
COVERED.update(
    {
        "Ingest the published export into a JSONL corpus": (
            "test_command.py::test_the_command_writes_a_corpus_a_manifest_and_a_report",
            "test_parsing.py::test_headers_and_row_count",
        ),
        "The output satisfies the ask agent's corpus contract": (
            "test_corpus_contract.py::test_every_line_carries_every_required_key_with_an_accepted_type",
            "test_corpus_contract.py::test_round_trip_through_the_real_loader",
        ),
        "The same source produces the same corpus": (
            "test_provenance.py::test_the_same_source_produces_a_byte_identical_corpus",
        ),
        "The command refuses to write where git would track the corpus": (
            "test_command.py::test_it_refuses_to_write_a_corpus_where_git_would_track_it",
            "test_command.py::test_the_guard_covers_the_manifest_as_well_as_the_corpus",
            "test_command.py::test_the_guard_covers_the_partial_files_a_run_writes_through",
            "test_guard.py::test_the_library_call_refuses_where_git_would_track_the_output",
            "test_guard.py::test_it_refuses_before_reading_the_source",
            "test_guard.py::test_every_file_a_run_can_create_is_checked",
        ),
        "Each key carries the value of its own column": (
            "test_cleaning.py::test_each_column_reaches_its_own_field",
            "test_cleaning.py::test_the_numeric_columns_reach_their_own_fields",
            "test_cleaning.py::test_the_keyword_column_reaches_the_keyword_field",
        ),
        "Every line stands on its own": (
            "test_io.py::test_one_json_object_per_line",
            "test_corpus_contract.py::test_one_unusable_line_costs_the_whole_corpus",
        ),
        "A run that does not finish leaves no corpus behind": (
            "test_io.py::test_a_run_that_raises_partway_leaves_no_file",
            "test_io.py::test_a_failed_run_leaves_a_previous_corpus_untouched",
        ),
        "The whole export is processed by default": (
            "test_command.py::test_the_whole_file_is_the_default_and_a_limit_must_be_asked_for",
            "test_command.py::test_a_limit_below_one_is_rejected_rather_than_writing_one_row",
        ),
        "The corpus cannot be committed by accident": (
            "test_command.py::test_it_writes_where_git_ignores_the_path",
            "test_command.py::test_it_writes_outside_any_repository",
        ),
        "Every input row is accounted for": (
            "test_provenance.py::test_records_written_plus_skipped_equals_rows_read",
            "test_provenance.py::test_accounting_that_does_not_add_up_is_reported_as_a_warning",
        ),
        "A run reports what it could not interpret": (
            "test_command.py::test_the_report_counts_each_flag_that_was_raised",
            "test_provenance.py::test_the_report_counts_are_asserted_against_real_values",
        ),
        "Duplicate identifiers are reported, not resolved": (
            "test_command.py::test_duplicate_identifiers_are_reported_and_both_records_kept",
        ),
        "Every corpus records which file it came from and when": (
            "test_provenance.py::test_the_manifest_sits_beside_the_corpus_and_records_the_run",
            "test_provenance.py::test_a_records_stamp_matches_its_own_manifest",
            "test_provenance.py::test_the_recorded_time_is_the_sources_mtime_not_the_run_time",
        ),
        "A sampled run's fingerprint still describes the whole file": (
            "test_provenance.py::test_a_limited_run_fingerprints_the_whole_file_anyway",
            "test_provenance.py::test_a_limited_run_says_so_in_its_manifest",
        ),
        "A source that cannot be read whole is an error": (
            "test_parsing.py::test_a_truncated_table_is_an_error_not_a_short_corpus",
            "test_parsing.py::test_a_table_cut_between_two_rows_is_an_error_too",
            "test_parsing.py::test_a_row_with_the_wrong_cell_count_is_an_error",
            "test_parsing.py::test_a_renamed_column_is_an_error_rather_than_an_empty_corpus",
        ),
        "A flag that cannot fire is worse than no flag": (
            "test_command.py::test_the_report_states_its_zeroes_rather_than_omitting_them",
            "test_command.py::test_a_run_that_raised_no_flags_says_so_rather_than_printing_nothing",
        ),
        "Parse flags travel with the record": (
            "test_io.py::test_the_predicate_and_the_flags_are_on_every_line",
            "test_corpus_contract.py::test_the_predicate_and_the_flags_are_present_on_every_line",
        ),
        "The fused-range predicate is a field, not a naming convention": (
            "test_cleaning.py::test_range_fused_is_false_for_flags_that_do_not_concern_fusion",
            "test_cleaning.py::test_hedging_is_a_separate_predicate_from_fusion",
            "test_corpus_contract.py::test_the_hedge_kind_is_a_field_not_a_flag_name",
            "test_corpus_contract.py::test_the_two_hedge_kinds_partition_the_qualified_field",
        ),
        "A range is normalized to a low and a high bound": (
            "test_cleaning.py::test_signed_range_parsing",
            "test_cleaning.py::test_scientific_and_grouped_numbers_are_one_number_each",
        ),
        "A unit's exponent is not a measurement": (
            "test_cleaning.py::test_a_unit_exponent_does_not_become_a_bound",
            "test_cleaning.py::test_a_unit_exponent_between_the_bounds_does_not_stop_the_scan",
        ),
        "A sign is told apart from a separator": (
            "test_cleaning.py::test_a_hyphen_after_a_unit_is_a_separator_not_a_sign",
            "test_cleaning.py::test_a_multi_word_unit_before_a_hyphen_is_still_a_separator",
            "test_cleaning.py::test_a_micrometre_is_a_unit_the_sign_test_can_step_over",
            "test_cleaning.py::test_the_unit_walk_stops_at_a_conjunction",
            "test_cleaning.py::test_the_unit_walk_does_not_cross_prose_to_find_a_digit",
            "test_cleaning.py::test_an_en_dash_between_two_numbers_is_a_separator_not_a_sign",
        ),
        "Plus-or-minus is uncertainty, not a bound": (
            "test_cleaning.py::test_plus_minus_is_uncertainty_around_value",
            "test_cleaning.py::test_the_plus_minus_deviation_is_the_number_after_the_sign",
            "test_cleaning.py::test_more_than_one_plus_minus_is_more_than_one_measurement",
            "test_cleaning.py::test_a_percentage_deviation_is_a_fraction_of_the_value_not_a_quantity",
        ),
        "A value cell that is not a number does not become one": (
            "test_cleaning.py::test_a_value_that_is_not_a_bare_number_is_flagged",
            "test_cleaning.py::test_an_unparseable_value_is_flagged",
            "test_cleaning.py::test_a_non_finite_value_is_not_a_measurement",
        ),
        "A range that may fuse two quantities is flagged": (
            "test_cleaning.py::test_more_than_two_numbers_is_flagged_and_bounds_unchanged",
            "test_cleaning.py::test_prose_between_the_bounds_is_flagged",
            "test_cleaning.py::test_a_repeated_unit_alone_does_not_make_two_quantities_one_range",
            "test_cleaning.py::test_a_shared_exponent_is_flagged_and_the_bounds_left_alone",
        ),
        "A range the source did not state as an interval says so": (
            "test_cleaning.py::test_a_hedged_range_is_flagged_and_marked_not_exact",
            "test_cleaning.py::test_a_plainly_stated_range_is_not_marked_hedged",
            "test_cleaning.py::test_a_hedged_value_reaches_the_contract_not_just_the_flags",
        ),
        "A row whose range is only a link is kept": (
            "test_cleaning.py::test_a_link_and_nothing_else_is_kept_with_no_bounds",
            "test_cleaning.py::test_a_link_beside_a_range_keeps_both_and_no_url_digit_becomes_a_bound",
        ),
        "Units and text are normalized across the source's encodings": (
            "test_cleaning.py::test_the_micro_sign_is_folded_into_the_greek_mu",
            "test_cleaning.py::test_an_entity_encoded_micrometre_normalises_the_same_way",
        ),
        "Injected markup is stripped and reported": (
            "test_cleaning.py::test_injected_markup_is_removed_and_flagged_in_either_form",
            "test_cleaning.py::test_no_emitted_field_ever_contains_a_tag",
            "test_cleaning.py::test_multiply_escaped_markup_does_not_survive_one_pass",
        ),
        "An angle bracket is not evidence of markup": (
            "test_cleaning.py::test_angle_bracket_content_is_not_treated_as_markup",
            "test_cleaning.py::test_a_less_than_clause_in_the_range_column_keeps_its_numbers",
            "test_cleaning.py::test_real_html_elements_are_still_stripped",
        ),
        "Padding rows are not records": (
            "test_cleaning.py::test_padding_rows_are_not_data_rows",
            "test_parsing.py::test_padding_row_is_yielded_not_dropped",
        ),
    }
)

# add-corpus-autobuild's.
COVERED.update(
    {
        "An export beside a missing corpus can produce one": (
            "test_resolve.py::test_an_export_beside_a_missing_corpus_is_found",
            "test_resolve.py::test_the_configured_path_may_be_the_export_itself",
            "test_resolve.py::test_a_corpus_that_is_there_needs_no_build",
            "test_resolve.py::test_nothing_to_build_from_is_reported_as_nothing",
        ),
        "A corpus that exists is never rebuilt": (
            "test_resolve.py::test_a_corpus_is_never_rebuilt_however_stale",
            "test_resolve.py::test_an_export_whose_corpus_already_exists_is_not_rebuilt",
        ),
        "A build through the resolver is refused on the same terms as the command": (
            "test_resolve.py::test_a_build_is_refused_where_git_would_track_the_corpus",
        ),
    }
)

# `rename-to-scinumbers`.
COVERED.update(
    {
        "A retired configuration name stops the run and names its replacement": (
            "test_config.py::test_a_renamed_variable_is_refused_and_its_replacement_named",
            "test_config.py::test_a_withdrawn_variable_is_refused_without_being_called_a_rename",
            "test_config.py::test_a_setting_read_without_a_driver_is_still_refused",
            "test_config.py::test_the_replacement_named_is_one_the_code_actually_reads",
            "test_config.py::test_no_retired_name_is_still_being_read",
            "test_terminal_driver.py::test_a_retired_variable_is_refused_before_the_corpus_is_looked_for",
            "test_web_driver.py::test_the_page_refuses_a_retired_variable_before_it_looks_for_a_corpus",
        ),
        "Citations use one stated format": (
            "test_citation_form.py::test_the_written_form_is_the_form_that_parses",
            "test_citation_form.py::test_the_prompt_asks_for_the_form_this_module_parses",
            "test_citation_form.py::test_a_bare_number_is_not_a_citation",
            "test_citation_form.py::test_no_width_floor_and_no_run_rule_apply_to_this_form",
            "test_citation_form.py::test_a_bracket_group_holding_no_identifier_is_recorded_not_dropped",
            "test_citation_form.py::test_the_source_form_is_accepted_in_an_answer",
            "test_citation_form.py::test_the_two_notations_are_ordered_by_where_they_appear",
        ),
        "An entry handed to the model carries one citation notation": (
            "test_bionumbers_notation.py::test_the_corpus_keeps_the_sources_words_and_the_model_gets_ours",
            "test_bionumbers_notation.py::test_a_run_is_restated_with_every_identifier_delimited",
            "test_bionumbers_notation.py::test_what_is_not_an_identifier_is_left_exactly_as_the_source_wrote_it",
            "test_bionumbers_notation.py::test_a_person_is_told_which_database_the_identifier_belongs_to",
        ),
        "A corpus written to a superseded contract is refused by name": (
            "test_corpus.py::test_a_corpus_from_an_older_ingester_is_refused_by_name",
            "test_corpus.py::test_the_refusal_is_reported_the_way_every_other_corpus_failure_is",
            "test_corpus.py::test_a_line_with_no_identifier_at_all_is_still_the_general_failure",
        ),
    }
)

# `add-answer-evaluation`'s (formerly `add-ask-agent`'s group 9). What is left here
# is the judged layer alone: groups 2, 3 and 4 built everything else, and each
# requirement left this list as its tests landed. A different kind of gap from the
# one above and kept apart from it -- otherwise finishing 10.9 would look
# impossible rather than merely unfinished.
# Renamed from AWAITING_THE_HARNESS: the harness is built, and these four moved
# out of `add-answer-evaluation` into `add-judged-faithfulness` on 2026-09-16.
# They are still read from that change's open delta, so they still need a bucket.
AWAITING_THE_JUDGE = (
    "Faithfulness is judged per claim, with a reason",
    "The judged layer is secondary and optional",
    "A judge is trusted only after measured agreement",
    "Every judgement records the judge model and its cost",
)

# `add-answer-shape`'s. A third kind of gap again: these await a change to the
# system prompt, not a harness, and the live-model check can only ever assert the
# weak form of them -- that an opening is quantitative and attributed, not that it
# carries the right conclusion. Kept apart so the list says which gap is which.
# `add-answer-feedback`'s three widget requirements were listed here while the
# widget did not exist -- the recording side was asserted, and what a reader is
# *offered* needs the real script. Groups 3 and 4 built it, so they are mapped
# above rather than recorded as gaps. The comment saying why they could not be is
# gone with them; `git log` has it.

AWAITING_THE_PROMPT = (
    "An answer leads with its quantitative conclusion",
    "Leading with a figure does not displace what qualifies it",
)

UNMAPPED: dict[str, str] = {
    **dict.fromkeys(TESTED_BUT_UNNAMED, "tested, but no test named yet -- task 10.9"),
    **dict.fromkeys(AWAITING_THE_JUDGE, "deferred to add-judged-faithfulness; no judge yet"),
    **dict.fromkeys(AWAITING_THE_PROMPT, "add-answer-shape is unbuilt; the prompt is unchanged"),
}


def requirement_names() -> list[str]:
    names = []
    for spec in SPECS:
        names += re.findall(r"^### Requirement: (.+)$", spec.read_text(), re.M)
    return names


def test_specs_were_found():
    """A path typo would make every check below pass over nothing."""
    assert len(SPECS) >= 4 and len(requirement_names()) > 20


def test_every_requirement_is_either_covered_or_recorded_as_a_gap():
    missing = [name for name in requirement_names() if name not in COVERED and name not in UNMAPPED]
    assert not missing, (
        "these requirements are neither claimed by a test nor recorded as unmapped:\n  "
        + "\n  ".join(missing)
        + "\n\nAdd them to COVERED with the tests that assert them, or to UNMAPPED with a "
        "reason. A requirement nothing checks reads exactly like one that is satisfied."
    )


def collect_test_names() -> set[str]:
    found = set()
    for path in ROOT.glob("test_*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                found.add(f"{path.name}::{node.name}")
    return found


def test_every_claimed_test_exists():
    """A renamed or deleted test would otherwise leave a requirement looking covered
    by something that is no longer there -- silently, since nothing reads this map
    at run time."""
    existing = collect_test_names()
    dangling = sorted({name for names in COVERED.values() for name in names} - existing)
    assert not dangling, (
        "these tests are claimed to cover a requirement and do not exist:\n  "
        + "\n  ".join(dangling)
    )


def test_no_requirement_is_claimed_that_the_specs_do_not_contain():
    """The other direction: a requirement renamed in the spec leaves a claim here
    pointing at nothing, and the requirement itself becomes uncovered without
    anything saying so."""
    names = set(requirement_names())
    stale = sorted((set(COVERED) | set(UNMAPPED)) - names)
    assert not stale, (
        "these are mapped but appear in no spec -- renamed or removed:\n  " + "\n  ".join(stale)
    )


@pytest.mark.parametrize("name", sorted(UNMAPPED))
def test_a_gap_carries_a_reason(name):
    assert UNMAPPED[name].strip(), f"{name} is listed as unmapped with no reason given"
