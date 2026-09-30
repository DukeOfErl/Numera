"""The recorded examples the sign-in door plays (`door_demo`).

What matters here is that the door can only ever show what was really asked and
really answered, and that it shows where each answer came from. The animation
itself is the browser's; it is looked at, not asserted.
"""

from __future__ import annotations

import json
import re

import pytest

from scinumbers_ask import door_demo
from scinumbers_ask.door_demo import Erase, Scenario, Type


def test_every_scenario_types_exactly_the_question_its_answer_was_recorded_for():
    """The keystrokes are theatre; the answer is a record. If the two drift, the
    door shows an answer to a question nobody asked."""
    scenarios = door_demo.scenarios()
    assert scenarios, "the door has nothing to play"
    for scenario in scenarios:
        assert door_demo.typed(scenario.steps) == scenario.asked, scenario.id


def test_erasing_words_takes_back_whole_words_and_leaves_the_space_before_them():
    steps = (Type("ribosomes in an e.coli cell?"), Erase(words=3), Type("yeast?"))
    assert door_demo.typed(steps) == "ribosomes in yeast?"


def test_erasing_more_words_than_were_typed_is_refused():
    with pytest.raises(ValueError, match="erase"):
        door_demo.keystrokes((Type("two words"), Erase(words=3)))


def test_keystrokes_carry_only_characters_to_type_and_counts_to_delete():
    """The browser deletes a count of characters and knows nothing about words, so
    the rule for what a word is lives in one place: here."""
    steps = (Type("in an e.coli cell?"), Erase(words=2), Type("x"))
    assert door_demo.keystrokes(steps) == [
        {"type": "in an e.coli cell?"},
        {"erase": len("e.coli cell?")},
        {"type": "x"},
    ]


def test_the_first_example_is_the_revised_ribosome_question():
    """The one the door was asked for: a question typed, its last three words taken
    back, and a comparison typed in their place."""
    first = door_demo.scenarios()[0]
    assert first.steps[0] == Type("What is the number of ribosomes in an e.coli cell?")
    assert first.steps[1] == Erase(words=3)
    assert first.asked == "What is the number of ribosomes in e.coli vs a budding yeast cell?"


def test_every_scenario_says_which_model_answered_and_when():
    for scenario in door_demo.scenarios():
        assert scenario.model and scenario.recorded and scenario.source, scenario.id
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", scenario.recorded), scenario.recorded


def test_every_answer_cites_the_corpus():
    """A recorded answer with no citation would be an example of the one thing the
    agent is built never to do."""
    for scenario in door_demo.scenarios():
        assert re.search(r"\[\[\d{6}\]\]", scenario.answer), scenario.id


def test_every_answer_uses_only_the_markdown_the_door_can_draw():
    """The renderer covers a subset, chosen from the recorded answers. A new example
    that goes beyond it fails here rather than reaching the door as raw asterisks."""
    for scenario in door_demo.scenarios():
        assert door_demo.unsupported(scenario.answer) == [], scenario.id


@pytest.mark.parametrize(
    "markdown, found",
    [
        ("see `code`", "inline code"),
        ("| a | b |", "a table"),
        ("[a link](http://example.org)", "a link"),
        ("1. first", "a numbered list"),
        ("> quoted", "a quotation"),
        ("# Top heading", "a top-level heading"),
        ("```\nblock\n```", "inline code"),
        ("  - nested", "a nested list"),
    ],
)
def test_unsupported_markdown_is_named(markdown, found):
    assert found in door_demo.unsupported(markdown)


def test_a_list_after_a_blank_line_is_not_mistaken_for_a_nested_one():
    """The shape of nearly every recorded answer: a paragraph, a blank line, a list."""
    assert door_demo.unsupported("A paragraph.\n\n- an item\n- another") == []


def test_rendering_draws_headings_lists_and_emphasis():
    html = door_demo.render("## Heading\n\n**Bold** and *italic*\n- one\n- two [[101794]]")
    assert "<h3>Heading</h3>" in html
    assert "<strong>Bold</strong>" in html
    assert "<em>italic</em>" in html
    assert "<ul><li>one</li><li>two [[101794]]</li></ul>" in html


def test_rendering_joins_a_paragraph_s_lines_and_separates_paragraphs():
    html = door_demo.render("one\ntwo\n\nthree")
    assert html == "<p>one two</p><p>three</p>"


def test_rendering_escapes_everything_it_does_not_draw():
    """The iframe runs scripts, and Streamlit's own warning names LLM output as
    what never to hand it unescaped. These answers are reviewed and committed, but
    the escaping is on the renderer so that stays true of the next one."""
    html = door_demo.render('<script>alert("x")</script> & **<b>**')
    assert "<script>" not in html and "<b>" not in html
    assert "&lt;script&gt;" in html and "&amp;" in html


def test_the_page_carries_every_scenario_and_its_provenance():
    page = door_demo.page()
    for scenario in door_demo.scenarios():
        assert json.dumps(scenario.asked)[1:-1] in page or scenario.asked in page
        assert scenario.model in page
    assert "Recorded" in page


def test_the_page_cannot_be_closed_early_by_what_it_carries():
    """A question containing `</script>` would end the script holding the data and
    run the rest as markup. The question, not the answer: `render` escapes an answer
    before it reaches the data, so an answer never tested this -- a seeded removal
    of the data's own escaping survived while the hostile text sat there."""
    hostile_text = "</script><script>alert(1)</script>"
    hostile = Scenario(
        id="x",
        steps=(Type(hostile_text),),
        asked=hostile_text,
        answer="an answer [[100001]]",
        model="m",
        recorded="2026-01-01",
        source="s",
    )
    page = door_demo.page((hostile,))
    assert page.count("</script>") == 2, "one data block and one program, nothing more"


def test_the_page_stands_still_for_a_reader_who_asked_for_less_motion():
    assert "prefers-reduced-motion" in door_demo.page()
