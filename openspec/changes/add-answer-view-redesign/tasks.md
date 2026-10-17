ADR block: `1850`–`1890` (CLAUDE.md is the authority).

## 1. Chrome and layout

- [ ] 1.1 Sidebar collapsed; account, budget, data credit and the trail ("Dev") there; no entries,
      no tab strip
- [ ] 1.2 Header: title, data subtitle, amber prototype line in the page (the pinned banner goes);
      under the question box, the records note and who is signed in
- [ ] 1.3 ADR-1850, written with the first slice

## 2. Pills and numbering

- [ ] 2.1 `entry_numbers(transcript)`, pure, tested over several turns and a rerun
- [ ] 2.2 `answer_markdown` draws pills (number, stars, `sim`, ⚠, id on hover); an unknown id stays as
      written; a corpus-file pill is the number alone
- [ ] 2.3 `sim` replaces `#` in `trust_marks`; the legend's dispute line says to open the entry

## 3. Evidence list

- [ ] 3.1 HTML table (#, Entry with organism · short reference, Value with units and marks, Trust, ID),
      escaped, value cells unbroken; no Trust column for a corpus file
- [ ] 3.2 Legend under it, marks present only; uncited entries in one expander; the summary of what
      was not shown
- [ ] 3.3 Remove the dataframe, `COLUMN_WIDTHS`, the sidebar entries and their tests

## 4. The open entry

- [ ] 4.1 `st.pills`, or `st.selectbox` above twelve, keyed by question, seated after the answer on
      the live path, disabled on older turns while answering
- [ ] 4.2 The record: number and id, stars and who approved, property and organism, full reference
      with DOI / PubMed links, value, objections, method, quote, the paper's wording, conditions, not
      stated, calculated from, domain

## 5. Short reference

- [ ] 5.1 First author and year from CSL-JSON (one, two, three or more authors)
- [ ] 5.2 From BioNumbers' reference string; measured over the 423 curated references in both
      directions before use

## 6. Search line, feedback, first view

- [ ] 6.1 The finished retrieval box reads "Searched “…” · N retrieved, M cited"
- [ ] 6.2 First view: heading, paragraph, example questions that ask themselves, the evidence
      placeholder
- [ ] 6.3 Through whole script runs (`.claude/rules/streamlit-driver.md`): pills, list, record,
      first view, for a store and a corpus file

## 7. Records and hand-over

- [ ] 7.1 README, `docs/diagrams/architecture.md`, CLAUDE.md, CHANGELOG, roadmap (the door's
      superscripts)
- [ ] 7.2 Spec conformance; `openspec validate --strict`; full suite
- [ ] 7.3 Yoav looks at the page over the real store, locally
