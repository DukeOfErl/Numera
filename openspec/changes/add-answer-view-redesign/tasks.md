ADR block: `1850`–`1890` (CLAUDE.md is the authority).

## 1. Chrome and layout

- [x] 1.1 Sidebar collapsed; account, budget, data credit and the trail ("Dev") there; no entries,
      no tab strip
- [x] 1.2 Header: title, data subtitle, amber prototype line in the page (the pinned banner goes);
      under the question box, the records note and who is signed in
- [x] 1.3 ADR-1850, written with the first slice

## 2. Pills and numbering

- [x] 2.1 `entry_numbers(transcript)`, pure, tested over several turns and a rerun
- [x] 2.2 `answer_markdown` draws pills (number, stars, `sim`, ⚠, id on hover); an unknown id stays as
      written; a corpus-file pill is the number alone
- [x] 2.3 `sim` replaces `#` in `trust_marks`; the legend's dispute line says to open the entry

## 3. Evidence list

- [x] 3.1 HTML table (#, Entry with organism · short reference, Value with units and marks, Trust, ID),
      escaped, value cells unbroken; no Trust column for a corpus file
- [x] 3.2 Legend under it, marks present only; uncited entries in one expander; the summary of what
      was not shown
- [x] 3.3 Remove the dataframe, `COLUMN_WIDTHS`, the sidebar entries and their tests

## 4. The open entry

- [x] 4.1 `st.pills`, or `st.selectbox` above twelve, keyed by question, seated after the answer on
      the live path, disabled on older turns while answering
- [x] 4.2 The record: number and id, stars and who approved, property and organism, full reference
      with DOI / PubMed links, value, objections, method, quote, the paper's wording, conditions, not
      stated, calculated from, domain

## 5. Short reference

- [x] 5.1 First author and year from CSL-JSON (one, two, three or more authors)
- [x] 5.2 From BioNumbers' reference string; measured over the 423 curated references in both
      directions before use: 330 distinct, 270 given, 60 none; widening for particles, "Jr" and
      "X et al." gained 22 (all right on reading), lost and changed none; where a reference holds
      several years the first after the authors was the publication year in all seven

## 6. Search line, feedback, first view

- [x] 6.1 The finished retrieval box reads "Searched “…” · N retrieved, M cited"
- [x] 6.2 First view: heading, paragraph, example questions that ask themselves, the evidence
      placeholder
- [x] 6.3 Through whole script runs (`.claude/rules/streamlit-driver.md`): pills, list, record,
      first view, for a store and a corpus file

## 7. Records and hand-over

- [x] 7.1 README, `docs/diagrams/architecture.md`, CLAUDE.md, CHANGELOG, roadmap (the door's
      superscripts)
- [x] 7.2 Spec conformance; `openspec validate --strict`; full suite
- [ ] 7.3 Yoav looks at the page over the real store, locally
