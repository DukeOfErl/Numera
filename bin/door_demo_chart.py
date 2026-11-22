#!/usr/bin/env python3
"""Draw the door demo's mouse cell-size chart, and print it.

The third example on the sign-in door shows cell volumes across mouse cell types
as a text chart. The chart is drawn here, by arithmetic, and pasted into
`src/numera_ask/door_demo.json`; it is never drawn by a model, because a
model placed every bar of a text chart in the wrong place (ADR-1210, ADR-1230).
Plotting is not a feature of the app yet: this script exists for one example.

Every entry below is one the recorded run cited, with its value as the corpus
stores it, so it can be checked against a corpus (`pytest -m corpus`,
`tests/test_door_demo_chart.py`). Two the run cited are left out because their
ranges are flagged as possibly fused: BV-2 microglia (112783, resting and
activated cells in one range) and the alpha motor neuron (112496). The red
blood cell's diameter (102927) is left out in favour of its measured volume
(104861): a disc is not a sphere, and the conversion would place it 2.5x too
high.

Run it to see the chart: `bin/door-demo-chart`.
"""

from __future__ import annotations

import math

#: (row, entry id, units as stored, low, high, cell type)
ENTRIES = (
    ("Blood & immune", 104861, "μm^3", 45.5, 45.5, "red blood cell"),
    ("Blood & immune", 100520, "μm^3", 131.4, 131.4, "T cell"),
    ("Blood & immune", 108900, "μm", 17.0, 17.0, "macrophage"),
    ("Stem & fibroblast", 108884, "μm", 10.0, 10.0, "ES cell"),
    ("Stem & fibroblast", 114286, "μm", 10.0, 20.0, "MEF"),
    ("Stem & fibroblast", 108905, "μm", 18.0, 18.0, "NIH/3T3"),
    ("Stem & fibroblast", 108979, "pL", 2.04, 2.04, "NIH/3T3"),
    ("Neuron soma", 111420, "μm", 18.0, 25.0, "cochlear-nucleus neurons"),
    ("Oocyte", 102237, "μm", 72.3, 72.3, "Graafian stage"),
    ("Oocyte", 111773, "pL", 300.0, 300.0, "post-ovulation"),
)

#: The axis: 10^1 to 10^6 μm³, eight characters to a factor of ten.
LO, HI, PER = 1, 6, 8
#: Width of the row label column.
LABEL = 19

SUPERSCRIPT = dict(zip("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹", strict=True))


def volume(units: str, value: float) -> float:
    """In μm³. A diameter is taken as a sphere's, V = (π/6)·d³; 1 pL = 1000 μm³."""
    if units == "μm^3":
        return value
    if units == "pL":
        return value * 1000
    if units == "μm":
        return math.pi / 6 * value**3
    raise ValueError(f"no conversion from {units!r}")


def _column(v: float) -> int:
    return round((math.log10(v) - LO) * PER)


def render() -> str:
    width = (HI - LO) * PER + 1
    labels = "".join(
        f"10{''.join(SUPERSCRIPT[c] for c in str(k))}".ljust(PER) for k in range(LO, HI)
    )
    header = " " * LABEL + labels + f"10{SUPERSCRIPT[str(HI)]} μm³"
    lines = [header]
    for row in dict.fromkeys(entry[0] for entry in ENTRIES):
        cells = ["·"] * width
        names: list[str] = []
        for _, _, units, low, high, name in (e for e in ENTRIES if e[0] == row):
            a, b = _column(volume(units, low)), _column(volume(units, high))
            for i in range(a, b + 1):
                if cells[i] != "●":
                    cells[i] = "━"
            if a == b:
                cells[a] = "●"
            if name not in names:
                names.append(name)
        lines.append(f"{row:<{LABEL}}{''.join(cells)}  {', '.join(names)}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(render())
