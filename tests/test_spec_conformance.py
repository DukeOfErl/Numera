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
}

# Requirements with no test named yet. Listed rather than omitted: the point of this
# file is that a gap is written down, not that there are none. Completing the
# mapping is task 10.9.
TESTED_BUT_UNNAMED = (
    "Events carry enough detail to show progress and to explain an ending",
    "A transient failure does not end a question",
    "The deterministic layer is logged under a per-question identifier",
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

# `add-answer-evaluation`'s (formerly `add-ask-agent`'s group 9). Not mappable until
# the evaluation harness exists, so a different kind of gap from the one above and
# kept apart from it -- otherwise finishing 10.9 would look impossible rather than
# merely unfinished. The last seven cover the outlier check and the judged layer.
AWAITING_THE_HARNESS = (
    "The question set is explicit and versioned with its answers",
    "Scoring is based on cited entries, not answer text",
    "Unsupported questions are part of the set",
    "Run-to-run variation is measured, not averaged away",
    "Results are recorded as each question completes",
    "An interrupted run resumes without repeating work",
    "A report can be produced from a partial results file",
    "Recorded results are usable by external evaluation tools",
    "Every result records what produced it",
    "Cost and effort are reported",
    "The context shown to the agent is recorded verbatim",
    "The asked property and organism are recognised",
    "The agent's own grounding warnings are scored",
    "A cited entry at odds with its peers is flagged",
    "Faithfulness is judged per claim, with a reason",
    "The judged layer is secondary and optional",
    "A judge is trusted only after measured agreement",
    "Every judgement records the judge model and its cost",
)

UNMAPPED: dict[str, str] = {
    **dict.fromkeys(TESTED_BUT_UNNAMED, "tested, but no test named yet -- task 10.9"),
    **dict.fromkeys(AWAITING_THE_HARNESS, "add-answer-evaluation is unbuilt; no harness yet"),
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
