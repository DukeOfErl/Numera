ADR block: `1600`–`1690` (reserved in `CLAUDE.md`, the source of truth — widen there first).
Write each ADR with the task that makes its decision, not at the end.

Test data is **invented**: a small SQLite store built in a fixture with the real schema
(`bionumbers.store`) and made-up passages. Paper text and corpus text never enter the repository —
some of the store's papers are NC/ND. The real store is read only in local checks, never committed.

## 1. Base and plumbing

- [x] 1.1 Rebase onto `dev` once harvest and review have merged (until then `feat/simulated-review`)
      and confirm `bionumbers.tiers` is present and its tests pass. This branch's base lacks 134
      commits of `dev` (2026-10-15), among them the grey-superscript citations (ADR-1240); after the
      rebase, re-read every module this design names against `dev` before building on it — the
      first draft was read against the stale base and missed the superscripts. Done 2026-10-16 by
      merging `feat/simulated-review` (which then held `dev`) and `dev` itself, not by rebasing:
      one conflict resolution instead of one per commit. Modules re-read against the merged tree
- [x] 1.2 Name `pydantic` in the `ask` extra; add a test that importing `scinumbers_ask.corpus`,
      `repository`, `tools` and `agent` with a corpus file does not import `bionumbers` (D8)
- [x] 1.3 ADR-1600: the ask package depends on `bionumbers` for the tier rule and the value
      parser — the direction, the import footprint measured, the alternatives rejected (D8); and
      that with hosted tracing on, store passages reach the tracer as corpus text does today

## 2. Entry and identifiers

- [x] 2.1 `EntryId = int | str`; widen every entry-identifier annotation (`repository.get`,
      `tools.get_entry`, `trace`, `events`, `scoring`); suite green with no behaviour change
- [x] 2.2 `Harvest` and `Condition` records, and `Entry.harvest` / `Entry.trust` defaulting to
      `None`; a corpus-file load yields both `None` (D2)
- [x] 2.3 `citations` reads `[[PMC2652108-1]]` and `[[PMC2652108-1.2]]` as string labels, before
      the digit rules; tests for both forms, a list of two, a mixed list with a BNID, and that
      `[[PMC1-2-3]]` and `[[Table 1]]` are still refused (D3)
- [x] 2.4 `bionumbers.label` labels only integers as BNIDs; a string identifier is shown as itself
- [x] 2.5 `Entry.record_id`: the store's item id for a harvested entry, the BNID otherwise. The
      `Answer` event, the trail's per-entry rows and the question-and-answer records write
      `record_id` with the label beside it; a test per record kind that a harvested citation is
      saved under its item id, and that a corpus-file run's records are unchanged
- [x] 2.6 ADR-1610: two identifiers — a short label the model types, the store's item id that is
      saved; the suffix rule for re-extractions; the full-id, integer-range and refuse-on-duplicate
      alternatives and why they lost (D3)

## 3. The store loader

- [x] 3.1 Fixture: a store built with `bionumbers.store`'s tables, holding invented curated entries,
      harvested items of each `kind` and `candidate_kind`, items in two domains, and decisions
      that exercise every tier, a dispute and a simulated tier
- [x] 3.2 `store_corpus.load(url)` opens the store read-only (`mode=ro`) and returns curated and
      harvested entries; a test proves a write through its connection fails, and that the store
      file is byte-identical after a load
- [x] 3.3 Curated rows become `Entry` with their BNID and `Trust` of tier `CURATED`
- [x] 3.4 Harvested items become `Entry` with the flat fields mapped as D2 says, `Harvest` filled
      (quote, stated conditions, not-stated names, paper, domain, topic, origin, inputs) and
      `trust` from `tiers.trust_of`; items with no decision get tier `NONE`
- [x] 3.5 Value reading against `kind` per D4's table: fitting readings set value or range;
      disagreements set `reading_uncertain` and leave the numbers `None`; `value_display` returns
      the paper's text for a harvested entry. Assertions come from D4's table, not from running
      the loader
- [x] 3.6 Labels per D3: the fixture holds one paper under two runs with different values for the
      same counter; the earlier run's value is `PMC…-1`, the later `PMC…-1.2`; both are entries.
      A duplicate label (forced in the fixture) stops the load naming it; missing or unreadable
      store → a `CorpusUnavailable` naming what was configured, nothing substituted
- [x] 3.7 A record saved citing the first run's value, then a reload with the second run added:
      the saved item id still resolves to the first run's value; and with an *older* run added
      later, the cited value keeps its label (load order) and the saved item id still resolves. A cited label no loaded entry
      carries is reported unknown, never matched to a near one
- [x] 3.8 A test that the loaded entries carry none of: the review's test text (`second`),
      `distractor_type`, `property_asked`, any reviewer's comment, issue or value read — asserted
      over every string field of every entry, using marker strings planted in the fixture
- [x] 3.9 Local check against the real store (not committed): 875 entries, 452 harvested with
      unique identifiers, 38 `reading_uncertain`, five domains; record the command and its output
      in the PR description. Run 2026-10-15: 875 entries (423 curated, 452 harvested), 452 unique
      labels, none suffixed, 38 uncertain, five domains (191/133/44/43/41), origins 203/200/49,
      tiers 321 approved unopposed / 76 approved and disputed / 55 disputed only

## 4. Search and the model's view

- [x] 4.1 `keywords` carry domain, topic, the quote and the stated conditions' quotes; a keyword
      found only in a passage finds the entry. Check the repository's keyword match on passages
      that long before relying on it, and say what was found. Found: `search` matches a keyword as
      a substring of each keyword, so a whole passage held as one keyword is searched like any
      other; no change to the repository was needed
- [x] 4.2 `get_entry` shows a harvested entry's quote, conditions, not-stated list, paper, origin,
      calculated-from passages and tier text (D5); a corpus-file entry's output is unchanged
      (snapshot of today's output taken before the change, not after)
- [x] 4.3 `_caveats` adds the `reading_uncertain` caution and a calculated-value line
- [x] 4.4 Search rows carry the tier token for store entries and nothing new for file entries
- [x] 4.5 System prompt (D5): decide relevance first and never let a tier make an entry relevant;
      among relevant entries for one quantity prefer the better-reviewed; say when an answer rests
      on a disputed or unreviewed entry; no instruction to write stars. Regenerate the agent
      graph diagram only if middleware changed (it should not). Done: rule 6; also the opening line
      says "scientific quantities" and "a corpus of entries" (the store spans five domains and is
      not all curated) and rule 1 says "the identifier", not "the number". Middleware unchanged
- [x] 4.6 ADR-1620: harvested values are stated as the paper wrote them, and numbers are trusted
      only where the reading fits the recorded kind — which direction is cheap (D4)

## 5. Stars on both drivers

- [x] 5.1 Presentation module: tier → stars per D6's table, `#` for simulated, `⚠` for disputed,
      empty for `None`, and the legend text; add it to `PRESENTATION` in
      `test_driver_independence.py`
- [x] 5.2 Web: `answer_markdown`'s citation run reads every form `citations` reads (built from
      `citations.DELIMITED`, not a second pattern), so `[[PMC2652108-1]]` becomes a superscript; each
      identifier in the superscript is followed by its stars and tier marks. Terminal: stars after
      each `[[id]]`. The stored and recorded answer text is unchanged; stars the model wrote do not
      change the tier shown; with no store both drivers draw exactly what they drew before. The legend
      line for `#` is escaped so it is not drawn as a heading (a test over the page's legend)
- [x] 5.3 Entries table: a trust column on CLI and web; the legend under the answer whenever any
      shown entry has a tier; nothing shown for a corpus file. Column order (user, 2026-10-16):
      marks, Property, Organism, Value, Units, Trust, ID, Reference; Organism, ID and Reference
      narrowed on the web so the table fits its column
- [x] 5.3a Caveat column (D6a): markers move from the property's prefix to a narrow first column
      with an empty header, on CLI and web; empty cell where no caveat applies; the property cell
      holds only the property. Add `?` (`reading_uncertain`) and `∴` (calculated) to
      `Row.markers()` with legend lines. Existing marker tests assert the column, not the prefix
- [ ] 5.4 Through a whole script run (`.claude/rules/streamlit-driver.md`): the web page shows
      stars inside the citation superscripts and in the table, the caveat column first, with the
      legend, for a fixture store and for a corpus file. Judge on the page whether four starred
      identifiers in one superscript still read; if not, try stars on first mention only (D6).
      The whole-script runs are `tests/test_web_driver_store.py`; the visual judgement needs a
      real answer on screen and is made in 7.3
- [x] 5.5 ADR-1630: tiers are drawn by the application and never written by the model; the scale,
      the separate dispute and simulated marks (D6), the caveat column (D6a), citing ADR-0990 and
      ADR-0960

## 6. Configuration

- [x] 6.1 `SCINUMBERS_STORE` / `--store`; both it and `SCINUMBERS_CORPUS` set → refusal naming both;
      `autobuild` bypassed for the store (D7)
- [x] 6.2 The Streamlit app loads the store under the same cache as the corpus; restart picks up
      new decisions
- [x] 6.3 Evaluation and the answer sheet refuse a store with a message saying they read a corpus
      file and naming the roadmap's "Evaluation over the store" (non-goal, stated rather than
      silently half-working)

## 7. Verification and documentation

- [ ] 7.1 Map every new requirement in `tests/test_spec_conformance.py`
- [ ] 7.2 Fault seeding over `store_corpus.py` and the `citations` change (copies, never the working
      tree): drop a condition's quote, swap `MEASURED`/`DERIVED`, let a disagreeing reading through
      as a number, leak `second` into a field, read `PMC…-n` as an integer, order runs newest
      first, save the label instead of the item id — each must fail exactly the intended test
- [ ] 7.3 Ask the demo's questions against the real store in the web app and look at the stars,
      legend and cautions; probe the OpenRouter key's remaining credit before any live call
- [ ] 7.4 README, `docs/diagrams/architecture.md` (a store adapter beside the corpus file),
      `CLAUDE.md`'s module table (`store_corpus.py`, the presentation module), CHANGELOG
- [ ] 7.5 `openspec validate --all --strict`; full suite green
