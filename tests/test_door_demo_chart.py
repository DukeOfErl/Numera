"""The mouse cell-size chart on the door, drawn by `bin/door-demo-chart` (ADR-1230).

The chart is drawn by code, not by a model, because a model misplaced every bar
of a text chart on its own axis (ADR-1210). Code can be wrong too, so the
placement is checked here against the axis as the chart itself declares it: the
decade labels' columns, read off the header, and the logarithm of each volume.
"""

from __future__ import annotations

import math
import os
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

import pytest

from numera_ask import door_demo

#: The code behind `bin/door-demo-chart`. The `.py` file, not the extensionless command: testmon
#: fails with an INTERNALERROR on an executed file with no suffix.
SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "door_demo_chart.py"


def _chart_module():
    loader = SourceFileLoader("door_demo_chart", str(SCRIPT))
    module = module_from_spec(spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


chart = _chart_module()


def _decade_columns(header: str) -> dict[int, int]:
    """Where each decade's label starts, read from the drawn header."""
    supers = {"¹": 1, "²": 2, "³": 3, "⁴": 4, "⁵": 5, "⁶": 6}
    return {supers[header[i + 2]]: i for i in range(len(header) - 2) if header[i : i + 2] == "10"}


def test_every_mark_sits_where_its_volume_is_on_the_drawn_axis():
    lines = chart.render().split("\n")
    header, rows = lines[0], {line[: chart.LABEL].strip(): line for line in lines[1:]}
    decades = _decade_columns(header)
    per_decade = decades[2] - decades[1]
    for group, _, units, low, high, _ in chart.ENTRIES:
        row = rows[group]
        for value in {low, high}:
            volume = chart.volume(units, value)
            column = decades[1] + round((math.log10(volume) - 1) * per_decade)
            assert row[column] in "●━", (group, value, volume, row)


def test_conversions_follow_the_stated_formulas():
    assert chart.volume("μm^3", 45.5) == 45.5
    assert chart.volume("pL", 2.04) == pytest.approx(2040)
    assert chart.volume("μm", 18) == pytest.approx(math.pi / 6 * 18**3)


def test_the_door_shows_exactly_the_chart_the_script_draws():
    (mouse,) = [s for s in door_demo.scenarios() if s.id == "mouse-cell-sizes"]
    assert f"```\n{chart.render()}\n```" in mouse.answer


def test_the_chart_says_charts_are_not_yet_a_feature():
    """The visitor must not take the chart for something the app does today."""
    (mouse,) = [s for s in door_demo.scenarios() if s.id == "mouse-cell-sizes"]
    assert "upcoming" in mouse.notice.lower()


@pytest.mark.corpus
def test_every_value_drawn_is_the_corpus_value():
    configured = os.environ.get("NUMERA_CORPUS")
    if not configured:
        pytest.skip("set NUMERA_CORPUS to a real corpus")
    from numera_ask.corpus import load

    entries = {e.entry_id: e for e in load(configured)}
    for _, entry_id, units, low, high, _ in chart.ENTRIES:
        e = entries[entry_id]
        stored = (e.value, e.value) if e.value is not None else (e.range_low, e.range_high)
        assert stored == (low, high), entry_id
        assert e.units == units, entry_id
