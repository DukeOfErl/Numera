# ADR-1230: The door's chart is drawn by a script, and says plotting is upcoming

- **Status:** accepted
- **Date:** 2026-10-04
- **Pull request:** _pending — `feat/door-demo-mouse-cells`_

## Context

The door's third example shows a distribution: cell volumes across mouse cell types,
as a text chart. ADR-1210 rejected a chart drawn by the model, because the model
placed every bar of one about five minutes to the right of its value.

Yoav proposed doing it in steps: find the entries, convert diameters to volumes, then
make a separate call to draw the plot. The first two steps went well. One live run
(2026-10-04, $0.16, 17 tool calls) found 13 mouse cell types and converted every
diameter as a sphere, and each of its nine conversions agrees with (π/6)·d³ to
rounding. A separate "now plot this" call would still be a model placing characters
on an axis, and checking its output would need the same arithmetic as drawing the
chart. Plotting as a feature, the agent returning numbers and the app drawing them,
is deferred. Yoav does not want it built yet.

## Decision

**The chart is drawn by `bin/door-demo-chart`**, a script for this one example and
not a feature of the app. It places each mark by log₁₀ of the volume on a 10¹–10⁶ μm³
axis, eight characters to a decade. Single values are `●` and ranges are `━`. There is
one row per group: blood & immune, stem & fibroblast, neuron soma, oocyte. Its
output is pasted into `door_demo.json`.

- **Every entry drawn is one the run cited.** `pytest -m corpus` checks that each value
  is the corpus value.
- **Left out:** two ranges flagged as possibly fused (BV-2 microglia 112783, the alpha
  motor neuron 112496). Also the red blood cell's diameter (102927), in favour of its
  measured volume (104861): a disc converted as a sphere lands 2.5× too high.
- **The answer ends by saying so:** "Charts like this are upcoming in SciNumbers; this
  one was drawn for the demo from the entries the answer used."

The door's renderer learns fenced blocks, drawn verbatim in a monospace face, for this
chart. A fenced block is escaped like everything else.

Tests check the placement against the axis as the chart draws it, read off its header.
They also check that the door carries exactly the script's output. Two defects were
seeded into a copy of the script, and each was caught. Natural log for log₁₀ failed
the placement test. A diameter squared rather than cubed failed the conversion test.

## Trade-off accepted

The door shows something the app cannot yet do. The closing line says so, and that
claim is the honest one. A script written for one example will not survive contact
with a second. It is a probe for the plotting work package, not a start on it. When
that package lands, this chart should be redrawn by the app and the script deleted.
