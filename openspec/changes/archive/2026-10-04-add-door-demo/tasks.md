ADR block: `1200`–`1240` (see the allocation table in `CLAUDE.md`).

## 1. Examples

- [x] 1.1 Run the ribosome comparison live and check the answer against the corpus
- [x] 1.2 Take the yeast-vs-E. coli volume answer from `opus47-x3-2026-09-17`, repeat 2
- [x] 1.3 Try a distribution example live; rejected on evidence (ADR-1210)
- [x] 1.4 Commit both answers verbatim in `door_demo.json` (ADR-1200)

## 2. The door

- [x] 2.1 `door_demo`: steps, keystrokes, the markdown subset, the page
- [x] 2.2 `web.draw_examples` on the sign-in door only
- [x] 2.3 Tests, including the driver tests and the dependency-direction set
- [x] 2.4 Drive it in a browser: typing, erasing, streaming, pause, reduced motion, dark, phone

## 3. Records

- [x] 3.1 Spec delta and conformance mapping
- [x] 3.2 ADR-1200, ADR-1210
- [x] 3.5 Shorten both answers as Yoav asked, record the edits, title the frame "Demo",
  shorten the pause (ADR-1220)
- [x] 3.3 README, CHANGELOG, CLAUDE.md, roadmap
- [x] 3.4 After merge: bring the deploy branch level, so the door reads the same there

## 4. The third example: mouse cell sizes, with a chart (`feat/door-demo-mouse-cells`)

- [x] 4.1 Live run: "How do cell sizes vary across mouse cell types? Convert diameters
  to volumes so they can be compared." Recompute every sphere volume it states
- [x] 4.2 `bin/door-demo-chart` draws the chart from entries the run cited (ADR-1230)
- [x] 4.3 Fenced blocks in the door's renderer, revealed by the stream
- [x] 4.4 Tests: placement against the drawn axis, the exact chart on the door, the
  upcoming note, the corpus values; two seeded defects each caught
- [x] 4.5 Look at it in Chromium: wide, phone, light, dark; glyph widths equal
- [x] 4.6 Citations as grey superscripts, runs comma-separated; "*The app itself provides
  full citations" under every example (ADR-1240)
- [x] 4.7 The same citation style in the app itself, on a chore branch (`chore/app-citation-superscripts`)
