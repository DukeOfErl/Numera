"""No text reaches Streamlit's markdown without passing the escaping boundary.

Streamlit renders every caption, markdown and warning as markdown, where `$` opens
inline mathematics. Two of them in one string typeset the middle as an equation and
consume both signs, so "$0.008181 (run $0.008181)" arrived as an italic fragment
with no currency on it at all.

That has now happened twice -- the ending line, then the side panel's "$1.20 of
$1.20" -- and both times the string was built at the point of drawing, outside
`as_text`. The second occurrence is the reason this file exists: one bug is a
mistake, the same bug in a second caption is a missing rule.

Checked over the source rather than by rendering, because the failure is silent by
construction: the page still draws, the text still reads as English, and only the
missing character says anything is wrong. A test that rendered and looked would
have to know which strings were meant to carry a dollar.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [ROOT / "src" / "scinumbers_ask" / "web.py", ROOT / "streamlit_app.py"]

# Streamlit calls whose first argument is rendered as markdown. Two kinds: the
# body of a text element, and the *label* of a widget or container -- Streamlit
# renders both, so a `$` is eaten either way.
#
# The labels were missing, and the omission was invisible until a call moved from
# one group to the other: folding the uncited rows into an expander turned
# `st.markdown("**Possibly relevant…**")` into `st.expander("Possibly relevant…")`
# and the scan stopped checking it, with nothing failing. The count of collected
# parameters went down by one, which is the only thing that said so.
#
# Listed wider than what the page uses today, deliberately. A name here that is
# never called costs nothing; a name missing costs a silent hole exactly like the
# one above, and "widen it when a new call appears" is a rule nobody will apply,
# for the same reason this whole file exists.
RENDERS_MARKDOWN = {
    # Text elements: the argument is the text.
    "markdown",
    "caption",
    "warning",
    "error",
    "info",
    "success",
    "header",
    "subheader",
    "title",
    "toast",
    # Containers and widgets: the argument is the label, rendered the same way.
    "expander",
    "status",
    "popover",
    "button",
    "form_submit_button",
    "download_button",
    "link_button",
    "checkbox",
    "toggle",
    "radio",
    "selectbox",
    "multiselect",
    "slider",
    "select_slider",
    "text_input",
    "text_area",
    "number_input",
    "date_input",
    "time_input",
    "file_uploader",
    "color_picker",
    "metric",
}

# `st.progress` is deliberately absent, and it is the one call that proves the
# scan keys on the *first argument*: progress takes a number there and puts its
# label in `text=`. Including it failed on `st.progress(spent / cap)`, which is
# the widening moving something in the direction nobody looks at. A `$` in a
# progress label would still be eaten; nothing passes one today, and covering
# keyword labels is a different scan from this one.

# `as_text` is the boundary; `st.markdown` with a literal is the page's own HTML and
# carries no corpus text. A call is safe when its first argument is a plain literal,
# or is wrapped in one of these.
ESCAPERS = {"as_text"}


# The page's own HTML, drawn with unsafe_allow_html. Markdown escaping does not
# apply to it and `as_text` would put a backslash into the markup. Listed by line
# content rather than by number so it cannot silently start covering something else.
RAW_HTML_MARKERS = ("bn-caveat", "PROTOTYPE_BANNER_CSS", "FEEDBACK_CSS")


def rendering_calls(path: Path):
    """Every st.<render>(...) call in a file, with the line it is on."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in RENDERS_MARKDOWN or not node.args:
            continue
        if any(kw.arg == "unsafe_allow_html" for kw in node.keywords):
            source = ast.unparse(node)
            assert any(marker in source for marker in RAW_HTML_MARKERS), (
                f"{path.name}:{node.lineno} passes unsafe_allow_html but is not one of the "
                "page's own HTML elements. Escaping does not apply there, so it must be "
                "listed in RAW_HTML_MARKERS with a reason, or not use raw HTML."
            )
            continue
        yield node, node.args[0], path


def is_escaped(arg: ast.expr) -> bool:
    """Whether this argument cannot carry an unescaped dollar to the page."""
    # A plain string literal is written here, so a `$` in it is deliberate.
    if isinstance(arg, ast.Constant):
        return True
    # A constant-only f-string carries nothing from outside either.
    if isinstance(arg, ast.JoinedStr) and all(isinstance(v, ast.Constant) for v in arg.values):
        return True
    # A module-level constant of this project's own words.
    if isinstance(arg, ast.Name) and arg.id.isupper():
        return True
    if isinstance(arg, ast.Attribute) and arg.attr.isupper():
        return True
    # Wrapped: as_text(...) or web.as_text(...).
    if isinstance(arg, ast.Call):
        func = arg.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name in ESCAPERS:
            return True
        # A string method on something already escaped, e.g. as_text(x).strip().
        if isinstance(func, ast.Attribute):
            return is_escaped(func.value)
    # "literal " + as_text(x), either way round.
    if isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Add):
        return is_escaped(arg.left) and is_escaped(arg.right)
    # f"...{as_text(x)}..." -- every interpolation escaped.
    if isinstance(arg, ast.JoinedStr):
        return all(
            isinstance(v, ast.Constant)
            or (isinstance(v, ast.FormattedValue) and is_escaped(v.value))
            for v in arg.values
        )
    return False


CALLS = [
    pytest.param(node, arg, path, id=f"{path.name}:{node.lineno}")
    for path in SOURCES
    for node, arg, path in rendering_calls(path)
]


def test_the_scan_found_the_calls_it_is_meant_to_check():
    """A path typo or a renamed method would otherwise make every check below pass
    over nothing -- the same silence this file exists to prevent."""
    assert len(CALLS) > 15, f"only {len(CALLS)} rendering calls found; the scan is not working"


@pytest.mark.parametrize("node,arg,path", CALLS)
def test_no_text_reaches_the_page_unescaped(node, arg, path):
    assert is_escaped(arg), (
        f"{path.name}:{node.lineno} draws st.{node.func.attr}(...) with text that did not "
        "pass through as_text. A '$' in it opens inline mathematics and both the sign and "
        "the text between are eaten -- silently, and only in the browser."
    )
