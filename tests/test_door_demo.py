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
from scinumbers_ask.door_demo import Erase, Pause, Scenario, Type


def test_every_scenario_types_the_question_it_shows():
    """The keystrokes are theatre; the answer is a record. The door types the
    question it shows -- the one asked, or a rewording of it (ADR-1220)."""
    scenarios = door_demo.scenarios()
    assert scenarios, "the door has nothing to play"
    for scenario in scenarios:
        assert door_demo.typed(scenario.steps) == (scenario.shown or scenario.asked), scenario.id


def test_a_reworded_question_names_the_one_actually_asked_in_its_edits():
    """A rewording is an edit like any other: the question the agent really got
    stays in `asked`, and `edits` says the door shows something else."""
    for scenario in door_demo.scenarios():
        if scenario.shown and scenario.shown != scenario.asked:
            assert scenario.asked in scenario.edits, scenario.id


def test_the_page_shows_the_reworded_question():
    reworded = Scenario(
        id="r",
        steps=(Type("shown?"),),
        asked="asked?",
        answer="a [[100001]]",
        model="m",
        recorded="2026-01-01",
        source="s",
        edits="asked as 'asked?'",
        shown="shown?",
    )
    (drawn,) = _examples_in(door_demo.page((reworded,)))
    assert drawn["asked"] == "shown?"


def test_a_pause_waits_without_typing():
    steps = (Type("a "), Pause(seconds=1.0), Type("b"))
    assert door_demo.keystrokes(steps) == [{"type": "a "}, {"pause": 1000}, {"type": "b"}]
    assert door_demo.typed(steps) == "a b"


def test_the_third_example_pauses_a_second_before_asking_for_the_chart():
    (mouse,) = [s for s in door_demo.scenarios() if s.id == "mouse-cell-sizes"]
    assert mouse.steps == (
        Type("How do cell sizes vary across mouse cell types? "),
        Pause(seconds=1.0),
        Type("Visualize in a strip chart"),
    )


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
        ("```\nblock never closed", "an unclosed code block"),
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
    assert '<ul><li>one</li><li>two <sup class="cite">101794</sup></li></ul>' in html


def test_rendering_joins_a_paragraph_s_lines_and_separates_paragraphs():
    html = door_demo.render("one\ntwo\n\nthree")
    assert html == "<p>one two</p><p>three</p>"


def test_a_fenced_block_is_drawn_as_it_was_written():
    """A text chart: spacing kept, nothing inside it read as markdown, and the
    markup characters inside it not mistaken for unsupported syntax."""
    markdown = "Before\n\n```\nrow  ●━━ *x* | y\n  10¹  10²\n```\n\nAfter"
    assert door_demo.unsupported(markdown) == []
    html = door_demo.render(markdown)
    assert "<pre>row  ●━━ *x* | y\n  10¹  10²</pre>" in html
    assert html.startswith("<p>Before</p>") and html.endswith("<p>After</p>")


def test_a_fenced_block_is_escaped_like_everything_else():
    html = door_demo.render("```\n<script>x</script>\n```")
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_rendering_escapes_everything_it_does_not_draw():
    """The iframe runs scripts, and Streamlit's own warning names LLM output as
    what never to hand it unescaped. These answers are reviewed and committed, but
    the escaping is on the renderer so that stays true of the next one."""
    html = door_demo.render('<script>alert("x")</script> & **<b>**')
    assert "<script>" not in html and "<b>" not in html
    assert "&lt;script&gt;" in html and "&amp;" in html


def test_the_page_is_titled_as_a_demo_and_carries_every_question():
    """Titled as a demo, outside the frame's box: the answers are shortened, so the
    page no longer claims each is a model's answer as given (ADR-1220)."""
    page = door_demo.page()
    for scenario in door_demo.scenarios():
        question = scenario.shown or scenario.asked
        assert json.dumps(question)[1:-1] in page or question in page
    assert '<div class="title">What can SciNumbers do?</div>' in page
    assert "a real answer from" not in page


def test_every_shortened_answer_says_what_was_changed():
    """The edits are recorded beside the answer, so the next person can trace each
    example back to its run and see what the door shows that the model did not."""
    for scenario in door_demo.scenarios():
        assert scenario.edits.strip(), scenario.id


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
        edits="",
        notice="",
    )
    page = door_demo.page((hostile,))
    assert page.count("</script>") == 2, "one data block and one program, nothing more"


def test_the_page_stands_still_for_a_reader_who_asked_for_less_motion():
    assert "prefers-reduced-motion" in door_demo.page()


def test_a_notice_follows_the_answer_in_its_own_colour():
    """The answer's markdown cannot carry a colour, so a notice is a field of its
    own, drawn after the answer -- and so streamed last."""
    example = Scenario(
        id="n",
        steps=(Type("q"),),
        asked="q",
        answer="an answer [[100001]]",
        model="m",
        recorded="2026-01-01",
        source="s",
        edits="",
        notice="*Charts are <coming>",
    )
    page = door_demo.page((example,))
    (drawn,) = _examples_in(page)
    assert drawn["answer"] == (
        '<p>an answer <sup class="cite">100001</sup></p>'
        f'<p class="footnote">{door_demo.CITATIONS_NOTE}</p>'
        '<p class="notice">*Charts are &lt;coming&gt;</p>'
    ), "after the answer, escaped, its asterisk kept as written"
    assert ".notice" in page and "--warn" in page


def test_an_example_without_a_notice_draws_none():
    plain = next(s for s in door_demo.scenarios() if s.id == "yeast-vs-ecoli-volume")
    assert plain.notice == ""
    (drawn,) = _examples_in(door_demo.page((plain,)))
    assert 'class="notice"' not in drawn["answer"]


def _examples_in(page: str) -> list[dict]:
    """The examples as the browser reads them: the page's data block, parsed."""
    start = page.index('<script type="application/json" id="examples">')
    body = page[page.index(">", start) + 1 : page.index("</script>", start)]
    return json.loads(body)


@pytest.mark.parametrize(
    "markdown, drawn",
    [
        ("a [[100427]] b", 'a <sup class="cite">100427</sup> b'),
        # A run of identifiers is one superscript, comma-separated, whatever the
        # model put between them: spaces, or a comma and a space.
        (
            "v [[100427]] [[100430]] [[103704]] and",
            'v <sup class="cite">100427, 100430, 103704</sup> and',
        ),
        ("v [[101794]], [[101788]].", 'v <sup class="cite">101794, 101788</sup>.'),
        # Words between them make two runs, not one.
        (
            "from [[100427]] and [[100004]],",
            'from <sup class="cite">100427</sup> and <sup class="cite">100004</sup>,',
        ),
    ],
)
def test_citations_are_set_apart_as_superscripts(markdown, drawn):
    assert door_demo.render(markdown) == f"<p>{drawn}</p>"


def test_a_citation_inside_a_chart_is_left_as_written():
    """A fenced block is verbatim; nothing in it is restyled."""
    assert "[[100427]]" in door_demo.render("```\nrow [[100427]]\n```")


def test_every_example_closes_by_saying_the_app_gives_full_citations():
    """The door shows identifiers only; a visitor is told where the rest is."""
    for drawn in _examples_in(door_demo.page()):
        assert f'<p class="footnote">{door_demo.CITATIONS_NOTE}</p>' in drawn["answer"]
    assert door_demo.CITATIONS_NOTE == "*The app itself provides full citations"


def test_the_citations_note_comes_before_an_example_s_own_notice():
    (mouse,) = [s for s in door_demo.scenarios() if s.id == "mouse-cell-sizes"]
    (drawn,) = _examples_in(door_demo.page((mouse,)))
    assert drawn["answer"].index('class="footnote"') < drawn["answer"].index('class="notice"')
