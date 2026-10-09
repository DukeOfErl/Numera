"""What the review page shows, asserted without a browser.

Everything here is a pure function of one `ReviewItem`, which is the point of `bionumbers.review`
existing at all: the page is a script Streamlit re-runs from the top, and only the order and
lifetime of its elements need `AppTest` (`tests/test_review_app.py`).

The builders below take every field a rule reads as a parameter -- the item id, the value, the
provenance, the location -- rather than filling them from a shared default. A rule reading a field
the fixture holds constant has no negative case at all, and the test looks thorough
(`.claude/rules/testing.md`).
"""

from __future__ import annotations

import dataclasses

import pytest

from bionumbers import review
from bionumbers.records import (
    CONDITION_FIELDS,
    CandidateKind,
    Claim,
    ClaimKind,
    ConditionField,
    DistractorType,
    Fingerprint,
    Location,
    Paper,
    Provenance,
    Quote,
    ReviewItem,
    SecondTextKind,
    TableCell,
    TableView,
)

QUESTION = "doubling time of Escherichia coli"
FP = Fingerprint(model="opus", instruction_sha256="abc123", article_id="PMC1", run_id="run-1")


def a_claim(
    *,
    value: str = "39",
    unit: str = "min",
    conditions: tuple[ConditionField, ...] = (),
) -> Claim:
    return Claim(
        claim_id="c1",
        property_asked="doubling time",
        property_in_paper="generation time",
        value=value,
        unit=unit,
        kind=ClaimKind.SINGLE,
        candidate_kind=CandidateKind.MEASURED,
        quote=Quote(text="a doubling time of 39 min", location=Location(passage_id="p1")),
        conditions=conditions,
        fingerprint=FP,
    )


def an_item(
    item_id: str = "i1",
    *,
    claim: Claim | None = None,
    supporting: Quote | None = None,
    second: Quote | None = None,
    second_kind: SecondTextKind = SecondTextKind.DISTRACTOR,
    distractor_type: DistractorType | None = DistractorType.ADJACENT_CONDITION,
) -> ReviewItem:
    return ReviewItem(
        item_id=item_id,
        question=QUESTION,
        claim=claim or a_claim(),
        paper=Paper(pmcid="PMC1", pmid="39123456", doi="10.1/abc", title="A paper", year=2026),
        supporting=supporting
        or Quote(
            text="the doubling time was 39 min",
            location=Location(passage_id="p1", section_path=("Results", "Growth")),
        ),
        second=second
        or Quote(
            text="63 min in minimal medium",
            location=Location(passage_id="p2", section_path=("Results", "Growth")),
        ),
        second_kind=second_kind,
        distractor_type=distractor_type,
    )


def an_id_showing_the_supporting_text_as(label: str) -> str:
    """An item id whose supporting text is drawn as `label`.

    Searched rather than written down: the order is a hash of the id, so a literal here would be a
    string nobody could check, and a test that pinned one would be pinning the hash rather than the
    rule. Bounded, so a broken order fails as an assertion instead of hanging.
    """
    for n in range(1000):
        item = an_item(f"item-{n}")
        supporting = next(text for text in review.texts_in_order(item) if text.is_supporting)
        if supporting.label == label:
            return item.item_id
    raise AssertionError(f"no item id in 1000 puts the supporting text at {label}")


# --- the two texts and their order ----------------------------------------------------------


def test_the_texts_are_labelled_a_and_b_and_exactly_one_of_them_supports_the_value():
    first, second = review.texts_in_order(an_item())

    assert (first.label, second.label) == ("A", "B")
    assert [first.is_supporting, second.is_supporting].count(True) == 1


def test_the_order_is_the_same_every_time_one_item_is_drawn():
    """The page reruns on every click. An order that moved between the reviewer's choice and the
    click that saves it would record the opposite of what they said, and look ordinary."""
    item = an_item("stable-id")

    first = review.texts_in_order(item)
    again = review.texts_in_order(item)

    assert [(text.label, text.text) for text in first] == [
        (text.label, text.text) for text in again
    ]


def test_the_supporting_text_is_not_always_the_first_one():
    """The negative case for "uninformative": the two items differ only in their id, which is the
    field the rule reads. A rule that always put the supporting text first would pass every other
    test in this file."""
    as_a = an_item(an_id_showing_the_supporting_text_as("A"))
    as_b = an_item(an_id_showing_the_supporting_text_as("B"))

    assert review.texts_in_order(as_a)[0].is_supporting
    assert review.texts_in_order(as_b)[1].is_supporting


def test_each_text_carries_its_own_words_and_its_own_location():
    item = an_item(
        supporting=Quote(
            text="the doubling time was 39 min",
            location=Location(passage_id="p1", section_path=("Results", "Growth")),
        ),
        second=Quote(
            text="63 min in minimal medium",
            location=Location(passage_id="p2", section_path=("Discussion",)),
        ),
    )

    shown = {text.text: text.location_line for text in review.texts_in_order(item)}

    assert shown["the doubling time was 39 min"] == "Results > Growth"
    assert shown["63 min in minimal medium"] == "Discussion"


# --- the texts as the paper wrote them ------------------------------------------------------


def test_the_value_is_never_emphasised_in_a_text():
    """ADR-0940: a text is shown as the paper wrote it. Emphasis on the value would point the
    reviewer at the number they are asked to find, and would make a text that states it look
    different from one that merely mentions a number."""
    item = an_item(
        supporting=Quote(text="a doubling time of 39 ± 1 min", location=Location(passage_id="p1"))
    )
    for shown in review.texts_in_order(item):
        rendered = review.as_markdown(shown.text)
        assert "**" not in rendered and "<b>" not in rendered and "<mark>" not in rendered
        assert rendered.replace("\\", "") == shown.text


def test_a_citation_marker_stays_visible():
    """The marker beside a number is what separates a measured value from a cited one, so it has
    to survive the renderer: unescaped, markdown reads `[ref 27]` as the start of a link."""
    rendered = review.as_markdown("as reported before [ref 27], 39 min")

    assert "[ref 27]" in rendered.replace("\\", "")
    assert "\\[ref 27\\]" in rendered


def test_the_paper_s_own_markdown_characters_are_shown_not_interpreted():
    """An asterisk, an underscore or a dollar sign in a paper's sentence is the paper's, and
    Streamlit's renderer would otherwise read them as emphasis or mathematics."""
    rendered = review.as_markdown("p < 0.05 (*) for strain_A at $37")

    assert rendered == "p < 0.05 (\\*) for strain\\_A at \\$37"


# --- the whole table beneath the texts -------------------------------------------------------


def a_table(*, cell_a: str = "t1r1c2", cell_b: str = "t1r1c3") -> TableView:
    """Table 1 of `spanning_headers.xml`, by hand: a spanning group header, a row header
    spanning two rows, and the two cells the texts come from named by parameter."""
    th, td = TableCell, TableCell
    return TableView(
        label="Table 1",
        caption="Doubling times in two media.",
        foot="a Mean of three cultures.",
        rows=(
            (
                th(text="Strain", header=True, rowspan=2),
                th(text="Doubling time (min)", header=True, colspan=2),
            ),
            (th(text="Glucose", header=True), th(text="Acetate", header=True)),
            (
                th(text="MG1655", header=True, rowspan=2),
                td(text="39", passage_id=cell_a),
                td(text="55", passage_id=cell_b),
            ),
            (td(text="41", passage_id="t1r2c2"), td(text="57 < 60", passage_id="t1r2c3")),
        ),
    )


def a_table_item(**overrides) -> ReviewItem:
    supporting = Quote(text="39", location=Location(passage_id="t1r1c2", kind="td"))
    second = Quote(text="55", location=Location(passage_id="t1r1c3", kind="td"))
    item = an_item(supporting=supporting, second=second)
    return item.model_copy(update={"tables": (a_table(),), **overrides})


def test_the_whole_table_is_shown_with_its_label_caption_and_footnotes():
    (rendered,) = review.tables_html(a_table_item())

    assert "<caption>Table 1 Doubling times in two media.</caption>" in rendered
    assert "a Mean of three cultures." in rendered
    for text in ("Strain", "Glucose", "Acetate", "MG1655", "39", "55", "41"):
        assert f">{text}<" in rendered or f">{text}</" in rendered, text


def test_the_paper_s_layout_survives_spans_and_all():
    (rendered,) = review.tables_html(a_table_item())

    assert '<th rowspan="2">Strain</th>' in rendered
    assert '<th colspan="2">Doubling time (min)</th>' in rendered
    assert rendered.count("<tr>") == 4


def test_both_texts_cells_are_marked_alike_with_their_labels():
    """The marks orient the reviewer; they must not answer for them. Each of A and B is marked
    the same way, with its own label, and nothing marks the value."""
    item = a_table_item()
    labels = {shown.passage_id: shown.label for shown in review.texts_in_order(item)}
    (rendered,) = review.tables_html(item)

    for passage_id, cell in (("t1r1c2", "39"), ("t1r1c3", "55")):
        assert (
            f'<td class="bn-mark">{cell}<span class="bn-badge">{labels[passage_id]}</span></td>'
            in rendered
        )
    assert rendered.count('class="bn-mark"') == 2
    assert "<b>" not in rendered and "<mark>" not in rendered


def test_a_cell_that_is_neither_text_carries_no_mark():
    """The negative of the marks: the rule reads the passage id, so a table whose cells are not
    the texts' is drawn bare."""
    item = a_table_item(tables=(a_table(cell_a="t9r9c9", cell_b="t9r9c8"),))

    (rendered,) = review.tables_html(item)

    assert 'class="bn-mark"' not in rendered and 'class="bn-badge"' not in rendered


def test_a_cell_s_text_is_escaped_not_interpreted():
    (rendered,) = review.tables_html(a_table_item())

    assert "<td>57 &lt; 60</td>" in rendered


def test_two_prose_texts_bring_no_table():
    assert review.tables_html(an_item()) == ()


# --- locations ------------------------------------------------------------------------------


def test_a_table_cell_is_located_by_its_row_and_column_headers():
    """The spec's scenario: the cell with its headers, and not the full table. The headers are what
    say which condition the number belongs to."""
    line = review.location_line(
        Location(
            passage_id="t1-r2-c3",
            section_path=("Results", "Table 1"),
            kind="td",
            row_headers=("LB, 37 °C",),
            column_headers=("Doubling time (min)",),
        )
    )

    assert line == "Results > Table 1 · row: LB, 37 °C · column: Doubling time (min)"


def test_a_paragraph_is_located_by_its_section_path_alone():
    """The negative case for the headers: a passage that has none must not grow empty `row:` and
    `column:` parts, which would read as a table cell whose headers were lost."""
    line = review.location_line(Location(passage_id="p7", section_path=("Results", "Growth")))

    assert line == "Results > Growth"


def test_a_passage_with_no_section_path_is_still_findable():
    assert review.location_line(Location(passage_id="p7")) == "p7"


# --- the condition block --------------------------------------------------------------------


def test_every_condition_field_is_listed_even_where_the_paper_states_none():
    """A field the paper never states is a finding about the paper, and the reviewer is being asked
    whether the value came from it *under these conditions*. An absent row and a row reading "not
    stated" are the same fact, and only one of them is visible."""
    rows = review.condition_rows(a_claim(conditions=()))

    assert len(rows) == len(CONDITION_FIELDS)
    assert [name.lower().replace(" ", "_") for name, _, _ in rows] == list(CONDITION_FIELDS)
    assert {provenance for _, provenance, _ in rows} == {"not stated"}
    assert {quote for _, _, quote in rows} == {"—"}


def test_a_stated_field_shows_its_quote_and_where_it_came_from():
    """The negative case for the row above: one field differs from the others only in its
    provenance and quote, which are the two fields the rule reads."""
    rows = review.condition_rows(
        a_claim(
            conditions=(
                ConditionField(
                    name="temperature",
                    provenance=Provenance.FROM_METHODS,
                    quote="cultures were kept at 37 °C",
                ),
            )
        )
    )

    stated = [row for row in rows if row[0] == "Temperature"]

    assert stated == [("Temperature", "from Methods", "cultures were kept at 37 °C")]
    assert len(rows) == len(CONDITION_FIELDS)


def test_a_field_the_paper_offloaded_to_another_work_says_so_and_names_it():
    """`BY_REFERENCE` exists because a real paper puts its culture conditions in a citation. An
    empty cell beside it would read as "the paper does not say"."""
    rows = review.condition_rows(
        a_claim(
            conditions=(
                ConditionField(
                    name="medium",
                    provenance=Provenance.BY_REFERENCE,
                    reference="[ref 12]",
                ),
            )
        )
    )

    assert ("Medium", "by reference to another paper", "[ref 12]") in rows


def test_every_provenance_state_has_words_a_reviewer_can_read():
    """Every state, because a missing one would raise while a reviewer was mid-item; and none of
    them rendered as the token the record stores, which is ours and not a fact about the paper."""
    assert set(review.PROVENANCE_LABELS) == set(Provenance)
    assert not set(review.PROVENANCE_LABELS.values()) & {state.name for state in Provenance}
    # The one state that is a fact about this prototype's reach rather than about the paper
    # (ADR-0050): a reviewer must not read it as "the paper does not say".
    assert "not read" in review.PROVENANCE_LABELS[Provenance.SUPPLEMENTARY_ONLY]


# --- the citation ---------------------------------------------------------------------------


def test_the_citation_carries_the_title_year_and_every_identifier():
    line = review.citation_line(
        Paper(pmcid="PMC12345", pmid="39123456", doi="10.1/abc", title="A paper", year=2026)
    )

    assert line == "A paper (2026) · PMC12345 · PMID 39123456 · doi:10.1/abc"


def test_the_citation_omits_what_the_index_did_not_carry():
    """The negative case: the same call with the empty fields the record allows. A blank between
    two separators reads as data missing about the paper, where it means the index never had it."""
    line = review.citation_line(Paper(pmcid="PMC12345"))

    assert line == "PMC12345"


# --- the decision ---------------------------------------------------------------------------


def test_a_verdict_without_a_choice_does_not_complete_the_item():
    """The spec's scenario, and the reason the choice is checked first: a reviewer who approves
    without choosing a text has answered the question that feels like the question."""
    with pytest.raises(review.Incomplete) as raised:
        review.decision_from(an_item(), None, review.APPROVE, "")

    assert raised.value.message == review.CHOICE_REQUIRED


def test_a_choice_without_a_verdict_does_not_complete_the_item():
    with pytest.raises(review.Incomplete) as raised:
        review.decision_from(an_item(), "A", None, "")

    assert raised.value.message == review.VERDICT_REQUIRED


def test_the_chosen_label_is_recorded_as_whether_it_was_the_supporting_text():
    """Both orders, because the label alone is meaningless in the record: an item drawn the other
    way round must turn the same "A" into the opposite answer."""
    as_a = an_item(an_id_showing_the_supporting_text_as("A"))
    as_b = an_item(an_id_showing_the_supporting_text_as("B"))

    assert review.decision_from(as_a, "A", review.APPROVE, "").chosen_supporting is True
    assert review.decision_from(as_a, "B", review.APPROVE, "").chosen_supporting is False
    assert review.decision_from(as_b, "A", review.APPROVE, "").chosen_supporting is False
    assert review.decision_from(as_b, "B", review.APPROVE, "").chosen_supporting is True


def test_the_first_step_needs_a_text_and_a_value():
    """The choice first, then the value: each refusal names the half missing, and the value is
    refused before anything is revealed (ADR-0970)."""
    with pytest.raises(review.Incomplete) as no_choice:
        review.first_step_from(an_item(), None, "39 min")
    assert no_choice.value.message == review.CHOICE_REQUIRED

    for blank in ("", "   "):
        with pytest.raises(review.Incomplete) as no_value:
            review.first_step_from(an_item(), "A", blank)
        assert no_value.value.message == review.VALUE_REQUIRED


def test_the_first_step_records_the_label_as_whether_it_was_the_supporting_text():
    as_a = an_item(an_id_showing_the_supporting_text_as("A"))
    as_b = an_item(an_id_showing_the_supporting_text_as("B"))

    first = review.first_step_from(as_a, "A", "39 min")
    assert (first.chosen_label, first.chosen_supporting, first.value_read) == ("A", True, "39 min")
    assert review.first_step_from(as_a, "B", "x").chosen_supporting is False
    assert review.first_step_from(as_b, "A", "x").chosen_supporting is False
    assert review.first_step_from(as_b, "B", "x").chosen_supporting is True
    assert review.chosen_label(as_a, True) == "A"
    assert review.chosen_label(as_b, True) == "B"


def test_a_verdict_is_approve_or_disapprove_and_nothing_else():
    assert review.verdict_from(review.APPROVE) is True
    assert review.verdict_from(review.DISAPPROVE) is False
    with pytest.raises(review.Incomplete) as none:
        review.verdict_from(None)
    assert none.value.message == review.VERDICT_REQUIRED
    with pytest.raises(ValueError):
        review.verdict_from("Maybe")


def test_an_issue_needs_its_text():
    assert review.issue_from("the unit is wrong") == "the unit is wrong"
    with pytest.raises(review.Incomplete) as blank:
        review.issue_from("  ")
    assert blank.value.message == review.ISSUE_REQUIRED


def test_a_disapproval_is_recorded_as_one_and_keeps_the_comment():
    decision = review.decision_from(an_item(), "A", review.DISAPPROVE, "the strain differs")

    assert decision.approved is False
    assert decision.comment == "the strain differs"
    assert decision.chosen_label == "A"


def test_a_verdict_nobody_gave_is_refused_rather_than_read_as_disapproval():
    """The dimension the rule reads is the verdict string itself. `approved = verdict == APPROVE`
    passes every test above and records an unrecognised value as a disapproval -- a judgement
    nobody gave, and one nothing downstream could tell from a real one."""
    with pytest.raises(ValueError):
        review.decision_from(an_item(), "A", "maybe", "")

    with pytest.raises(ValueError):
        review.decision_from(an_item(), "C", review.APPROVE, "")


# --- what the reviewer is never told --------------------------------------------------------

#: The tokens that would give the answer away. Checked as the record writes them -- upper case,
#: verbatim -- so that ordinary prose containing the word "cited" is not a false positive while the
#: enum's own `CITED` is caught.
NEVER_SHOWN = (
    {kind.value for kind in SecondTextKind}
    | {kind.name for kind in SecondTextKind}
    | {distractor.value for distractor in DistractorType}
    | {distractor.name for distractor in DistractorType}
)


@pytest.mark.parametrize(
    ("second_kind", "distractor_type"),
    [
        (SecondTextKind.DISTRACTOR, DistractorType.ADJACENT_CONDITION),
        (SecondTextKind.SECOND_OCCURRENCE, None),
    ],
)
def test_nothing_the_page_is_given_names_the_second_text_s_kind(second_kind, distractor_type):
    """Design D5: the kind is recorded and never shown, so an item whose second text is a
    legitimate second occurrence looks exactly like one whose second text is a distractor. If the
    screen differed between them, the reviewer's choice would measure the screen."""
    item = an_item(second_kind=second_kind, distractor_type=distractor_type)

    rendered = [
        *(f"{text.label} {text.text} {text.location_line}" for text in review.texts_in_order(item)),
        review.as_markdown(item.second.text),
        *review.tables_html(a_table_item(second_kind=second_kind, distractor_type=distractor_type)),
        review.citation_line(item.paper),
        *(" ".join(row) for row in review.condition_rows(item.claim)),
    ]

    for line in rendered:
        assert not [token for token in NEVER_SHOWN if token in line], line


def test_the_shown_text_carries_no_field_that_could_leak_the_kind():
    """The structural half: a field named here is one a page could render by accident, and a page
    is where the leak would be invisible to every test above."""
    fields = {field.name for field in dataclasses.fields(review.Shown)}

    # `passage_id` is where the text sits, for the table's marks; a location carries no kind.
    assert fields == {"label", "text", "location_line", "is_supporting", "passage_id"}


class TestStoreEngine:
    """Where the page finds its database: secrets first, a plain URL from the environment second."""

    def test_a_plain_url_serves_a_machine_with_no_secrets(self, monkeypatch, tmp_path):
        from bionumbers import review

        monkeypatch.setattr(review.web, "trail_destination", lambda: None)
        monkeypatch.setenv(review.DB_URL_ENV, f"sqlite:///{tmp_path}/review.sqlite")

        engine = review.store_engine()

        assert engine is not None and engine.url.get_backend_name() == "sqlite"

    def test_secrets_win_over_the_environment(self, monkeypatch, tmp_path):
        from bionumbers import review

        configured = object()
        monkeypatch.setattr(review.web, "trail_destination", lambda: configured)
        monkeypatch.setenv(review.DB_URL_ENV, f"sqlite:///{tmp_path}/other.sqlite")

        assert review.store_engine() is configured

    def test_neither_means_none(self, monkeypatch):
        from bionumbers import review

        monkeypatch.setattr(review.web, "trail_destination", lambda: None)
        monkeypatch.delenv(review.DB_URL_ENV, raising=False)

        assert review.store_engine() is None


def test_outside_biology_only_the_conditions_the_paper_states_are_listed():
    """A lattice constant has no growth medium. The eight biological fields read "not stated"
    on every physics paper and say nothing; only what the extractor recorded is shown."""
    stated = an_item().claim.model_copy(
        update={
            "conditions": (
                ConditionField(
                    name="temperature", provenance=Provenance.BESIDE_VALUE, quote="at 300 K"
                ),
                ConditionField(name="medium", provenance=Provenance.NOT_STATED),
                ConditionField(
                    name="pressure", provenance=Provenance.FROM_METHODS, quote="ambient"
                ),
            )
        }
    )

    physics = review.condition_rows(stated, "physics")
    biology = review.condition_rows(stated, "biology")

    assert [row[0] for row in physics] == ["Temperature", "Pressure"]
    assert [row[0] for row in biology][:3] == ["Organism", "Strain", "Medium"]
    assert len(biology) == len(review.CONDITION_FIELDS) + 1
    assert review.condition_rows(stated, "") == biology, "runs before scopes are biology"
