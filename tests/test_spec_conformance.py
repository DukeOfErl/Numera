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
SPECS = sorted((ROOT.parent / "openspec" / "changes").rglob("specs/**/spec.md"))

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

# Group 9's. Not mappable until the evaluation harness exists, so a different kind
# of gap from the one above and kept apart from it -- otherwise finishing 10.9
# would look impossible rather than merely unfinished.
AWAITING_THE_HARNESS = (
    "The question set is explicit and versioned with its answers",
    "Scoring is based on cited entries, not answer text",
    "Unsupported questions are part of the set",
    "Run-to-run variation is measured, not averaged away",
    "Results are recorded as each question completes",
    "An interrupted run resumes without repeating work",
    "A report can be produced from a partial results file",
    "Recorded results are usable by external evaluation tools",
    "Every result records the model that produced it",
    "Cost and effort are reported",
)

UNMAPPED: dict[str, str] = {
    **dict.fromkeys(TESTED_BUT_UNNAMED, "tested, but no test named yet -- task 10.9"),
    **dict.fromkeys(AWAITING_THE_HARNESS, "group 9 is unbuilt; the harness does not exist"),
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
