## Context

The ask agent reads a JSONL corpus into `Entry` records (`corpus.load`), indexes them
(`repository.CorpusRepository`) and hands them to the model through three tools (`tools.py`). Every
`Entry` today is a BioNumbers record: an integer identifier, numeric value or range, method and
comments.

The harvest store (`BioNumbers-review/harvest-demo.sqlite`, owned by the entry-review session and
written by it while we run) holds something shaped differently:

| Table | Rows (2026-10-13) | What it is |
|---|---|---|
| `curated_entry` | 423 | BioNumbers entries that passed `curated.refusal` (ADR-1510) — nearly the `Entry` shape |
| `review_item` | 452 | One harvested value each, from 48 papers in five domains; `item_json` holds the claim, the paper, and the review's test text |
| `review_decision` | 967 | Simulated reviewers' verdicts, read by `bionumbers.tiers` (ADR-0990) |
| `review_paper` | 66 | Paper metadata, `domain`, `topic` |

A harvested claim's value is text (`488`, `7.1 ± 0.4`, `1,100–2,100`, `62 (40–100)`, `3.2∶1`), its
context is a supporting quote, a list of named conditions each with a quote or `NOT_STATED`, the
paper, and `candidate_kind` (`MEASURED` 203, `DERIVED` 200, `DERIVED_FROM_PUBLISHED` 49) with the
`inputs` passages a calculated value came from. Condition names vary by domain but share one shape,
and `method` is a condition in every domain.

## Goals / Non-Goals

**Goals:**
- The agent answers from the store, all domains, read-only, with the JSONL path unchanged.
- Each harvested value is one entry, cited as `[[PMC2652108-1]]`.
- A reader sees each cited entry's trust tier as stars, from the store, with a caution where
  disputed and a mark where simulated.
- The tier rule and the value parser each keep one definition.

**Non-Goals:**
- Authors, emails and an author tier (deferred by decision, not forgotten).
- Live tiers: decisions made after the store was loaded appear after a restart.
- Evaluation runs and the answer sheet over the store; they keep reading a corpus file. The plan
  for them is a separate work package, recorded in `docs/roadmap.md` ("Evaluation over the store").
- Changing the value parser (`bionumbers.readings`); disagreements are cautioned, not repaired.
- Writing to the store, or copying it into any repository.

## Decisions

### D1. A second loader, producing the same `Entry`, not a second agent

`store_corpus.load(url)` returns `tuple[Entry, ...]`, exactly like `corpus.load(path)`. Everything
downstream — repository, tools, middleware, drivers — keeps one code path; only what an `Entry`
may carry grows. The alternative, a store-specific repository and tool set, would fork the tool
surface the specs describe as deliberately small, and two tool sets drift.

It opens SQLite with `mode=ro` (a URI `file:…?mode=ro`), reads once at start and closes. Read-only
is enforced by the connection, not by the loader's good behaviour: a second caller gets the same
refusal (the guard belongs to the operation).

**Pattern:** this is the *adapter* side of ports and adapters for the corpus — the store is a second
adapter onto the one `Entry` port.

### D2. Two optional parts on `Entry`, not a wider flat record

`Entry` gains `harvest: Harvest | None` and `trust: Trust | None`, both default `None`.

- `Harvest` (frozen): `value_text`, `quote`, `conditions: tuple[Condition, ...]` (stated, each with
  its quote), `not_stated: tuple[str, ...]`, `origin` (`measured` / `calculated` /
  `calculated_from_published`), `inputs: tuple[str, ...]`, `paper` (title, year, DOI, PMID, licence),
  `domain`, `topic`, `reading_uncertain: bool`.
- `trust` is `bionumbers.tiers.Trust` itself, not a copy — one type, one rule.

The flat fields are filled so existing code keeps working unchanged: `property` ←
`property_in_paper`; `organism` ← `organism_name`; `units` ← unit; `value`/`range_low`/`range_high`
← the reading (D4); `reference` ← "title (year). doi"; `reference_pubmed_id` ← PMID;
`measurement_method` ← the `method` condition's quote, or empty — so the existing "no method
recorded" mark (grounded-answering) applies to harvested entries for free; `keywords` ← domain,
topic, the supporting quote and each stated condition's quote — so a keyword search for
"lamellipodial" reaches an entry whose property, as the paper words it, is only "F-actin
concentration". Whether the repository's keyword match suits passages that long is checked in the
first task that indexes them, not assumed.

A corpus-file `Entry` has both parts `None`, which is what lets every surface tell "no tier" from
"zero stars". Rejected: adding ~15 flat optional fields — every reader of `Entry` would have to know
which belong to which source.

`ingest`'s contract test restates `Entry`'s twelve keys. The two new fields are optional and absent
from the JSONL, so the contract with `add-corpus-ingestion` is unchanged; the docstring's
"message to that branch" clause does not trigger.

### D3. Two identifiers: a label the model types, the store's id that is saved

A curated entry keeps its integer BNID, which is both its label and its saved id.

A harvested entry has a **label** — `entry_id`, what the repository is keyed by, what the model sees
and cites — and `Harvest.item_id`, the store's own `review_item.item_id`
(`{run_id}-{pmcid}-{n}-item`), which names one value forever. The store is insert-only and a
re-extraction is a new run with new item ids (confirmed with the seeding session, 2026-10-15), so
the saved id is stable by construction; the label is not, because a re-extraction reuses `n`.

**Labels.** `f"{pmcid}-{n}"`, `n` being the claim's counter within its run. The loader groups a
paper's items by run, orders runs by creation time, and gives the first run bare labels and the
k-th run `f"{pmcid}-{n}.{k}"`. All 452 are bare today (no paper has two runs). A duplicate label
after this rule is a bug, and stops the load by name.

**A label is valid for one load and is never resolved again.** Ordering by creation time is stable
only while runs arrive in the order they were made. A restore, a backfill, or a run copied in from
`~/scinumbers-data/runs` can add a run older than one already loaded; it then takes the bare labels
and the existing entries become `.2` (pointed out by the seeding session, 2026-10-15). That is
harmless only because nothing saved is ever looked up by its label — the item id is the key, and
the saved label records what the reader was shown. **Do not add a path that re-resolves a saved
label** (a "cited entries" view over old answers, a trail replay, an evaluation reading old
results): resolve by `record_id`. Rejected: ordering by load time instead, which would keep labels
fixed but needs a load timestamp per run that the store does not keep and this branch must not
write.

**Saved records.** `Entry.record_id` returns `harvest.item_id` for a harvested entry and the BNID
otherwise — one property, so no recorder computes it. Wherever an identifier leaves the process —
the `Answer` event's `cited` and `retrieved`, the trail's per-entry rows, the question-and-answer
records — it is written as `record_id`, with the label beside it for a reader. Resolution from
label to entry happens once, in the agent, against the repository as loaded, at the point
`citations()` returns: a label naming nothing is `unknown`, as today; nothing is matched loosely.

**Parsing.** `citations._identifiers` today refuses a group with two digit runs, which is exactly
what `PMC2652108-1` is. It gains one recognised shape, `PMC\d+-\d+(\.\d+)?`, read *before* the
digit rules and returned as a string. A group matching neither shape is still refused.
`bionumbers.label` returns `BNID n` only for integers; a label is shown as itself — it is not a BNID
and must not be labelled one (ADR-0420's attribution would become a false one).

Every `int` annotation and `int(...)` coercion on an entry identifier (`tools.get_entry`,
`repository.get`, `agent`'s retrieval tracking, `trace`, `events`, `scoring`) becomes
`EntryId = int | str`. The tool's argument schema is what the model sees; it changes from integer
to string-or-integer.

Rejected: the model citing the full item id (about 50 characters naming the run and the model;
models copy long ids unreliably, and each miscopy is a citation of nothing — the seeding session
proposed it and withdrew it for this design); synthetic integers in a range BNIDs do not use (a
reader cannot tell a harvested entry from a BNID — the user preferred the PMCID form); refusing to
load on a re-extraction (the first re-extraction would stop the app).

### D4. Value: the paper's text is stated; numbers are used only where the reading fits

`bionumbers.readings.parse(value + " " + unit)` gives `numbers`, `uncertainty`, `approximate`. The
loader compares the reading's shape with the claim's `kind`:

| `kind` | Fits when | Otherwise |
|---|---|---|
| `SINGLE` | one number | `reading_uncertain` |
| `WITH_UNCERTAINTY` | one number and an uncertainty | `reading_uncertain` |
| `RANGE_OVER_CONDITIONS` | two numbers | `reading_uncertain` |

Over today's store that cautions 38 of 452 (21 `SINGLE` read as two numbers, 13 `WITH_UNCERTAINTY`
read as a range, 3 with no uncertainty read — one of them the ratio `3.2∶1` —, 1 range read as one
number). Where it fits, `value` or
`range_low`/`range_high` are set from the reading; where it does not, all three stay `None` and
`value_display` returns `value_text`. `tools._caveats` adds one caution for `reading_uncertain`.

**Which direction is cheap, said in the code:** a correct reading cautioned costs a sentence; a
misread number stated with confidence is a wrong answer that looks like a right one. So any
disagreement cautions, whichever side is wrong.

`value_text` is what is *shown* in every case, so `7.1 ± 0.4 nm` keeps its uncertainty in the table
and in the model's view.

### D5. What the model is shown, and what never reaches it

`get_entry` for a harvested entry adds: `quote`, one `condition: name — "quote"` line per stated
condition, `not stated: temperature, medium…`, `paper: …`, `domain/topic`, `origin`, and for a
calculated value `calculated from:` with the input passages. Search rows add the tier only (one
short token), so a search costs little more than today.

The tier reaches the model as text, e.g. `trust: 3 of 5 (scientist, simulated review); disputed`.
The system prompt gains three sentences: decide which entries bear on the question first, and never
let a tier make an entry relevant; among relevant entries about the same quantity, prefer the
better-reviewed one; say so when an answer rests on a disputed or unreviewed entry. It is **not**
told to write stars. The order matters: told only to prefer trusted entries, a model can lead with a
five-star value about a neighbouring quantity. A prompt sentence is a guard, not a mechanism; the
two-step version (an explicit shortlist, then ordering by tier) is "Relevance before trust" in
`docs/roadmap.md`.

Never loaded at all, so no later tool can leak them: `item_json.second` (the review's test text),
`distractor_type`, `supporting` (equal to the claim's quote in all 452 items, checked 2026-10-13; kept out so there is
one source),
`property_asked`, and every column of `review_decision` other than what `tiers.trust_of` reads. The
model sees `disputed`, never a reviewer's issue or comment — the same line `feedback.py` draws.

### D6. Stars are drawn by one presentation function, used by both drivers

A presentation module (beside `entries_table`) owns the scale:

| Tier | Stars |
|---|---|
| `CURATED` | ★★★★★ |
| `SENIOR_SCIENTIST` | ★★★★☆ |
| `SCIENTIST` | ★★★☆☆ |
| `STUDENT` | ★★☆☆☆ |
| `AI` | ★☆☆☆☆ |
| `NONE` | ☆☆☆☆☆ |

`$` after the stars marks a simulated tier; `⚠` marks a dispute. Both qualify the *tier*, so they
travel with the stars — beside a citation in the prose and in the trust column alike. A legend under
the answer states the scale, `$` and `⚠`. `None` trust renders as the empty string. (`†` was the
first choice and is taken: it already means "no measurement method recorded". `$` was chosen by
the user, for its likeness to an *s*.)

`$` needs care on the web: Streamlit's markdown reads a `$` as the start of inline mathematics, and
an answer that also mentions a cost would pair the two and typeset what lies between. `as_text`
already escapes `$` in text the drivers write; the `$` this module puts inside the citation
superscript is inserted *after* that escaping, so it is written as the HTML entity `&#36;`, which
markdown does not read as a delimiter. A reader may also take `$` for a price in an app that shows
spend; the legend says what it means wherever it appears.

**In the web app, the stars go inside the citation's grey superscript.** On `dev` the web driver
already draws an answer's citations as grey superscripts (ADR-1240, `web.answer_markdown`): a run of
`[[nnnnnn]]` becomes one `<sup>` with its identifiers comma-separated, after escaping. This branch's
base predates that merge, which is why the first draft of this design said `[[id]]` — the design was
read against a stale `web.py`. Built on `dev`, the superscript carries each identifier followed by
its stars and tier marks — one `<sup>` holding `100002 ★★★★★, PMC2652108-1 ★★★☆☆$⚠` — all in the
same grey, smaller size.
Two changes to `answer_markdown` follow:

- `_CITATION_RUN` matches `\[\[\d+\]\]` only, so a `[[PMC2652108-1]]` citation would be left as
  raw brackets. It must match every form `citations` reads — better, be built from
  `citations.DELIMITED` rather than restating a pattern (ADR-0410's one-definition rule, which
  `_CITATION_RUN` already bends).
- The superscript needs each identifier's trust, so `answer_markdown` takes a lookup from identifier
  to `Trust` (from the loaded entries); with no store it draws exactly what it draws today.

Five stars per identifier at superscript size gets wide when a run cites four entries; whether that
reads well is judged on the page in task 5.4, and a compact fallback (stars only on the first
mention of an identifier in an answer) is the first thing to try if it does not.

The terminal has no superscript and keeps `[[id]]`; the stars follow it there. In both drivers the
model's text is not altered where it is stored or recorded, only where it is displayed. Star
characters the model writes are left as written; the drawn ones are the tier.
The entries table gains a trust column on both drivers. Stars only, per the user's choice, with the
legend carrying the role words.

`test_driver_independence` gets the new module under `PRESENTATION`.

### D6a. Caveat marks get a column of their own

Today `Row.markers()` (`‡ † ° ≈ ¡`, and `§` on the web) is prefixed to the property, on both drivers.
They move to a separate, narrow first column with an empty header; a row with no caveat has an
empty cell. Reasons: a reader scanning properties no longer reads past symbols, the marks line up
so a column of `†` is visible at a glance, and the new marks below would otherwise lengthen the
prefix further.

Two marks are added to `Row.markers()` for harvested entries, each with a legend line:

| Mark | Means |
|---|---|
| `?` | the value could not be read with certainty; the paper's text is shown (`reading_uncertain`, D4) |
| `∴` | calculated, not measured — by the paper's authors or from values published elsewhere |

The tier marks (`$`, `⚠`) stay with the stars and do not go in this column: they qualify the tier,
not the entry's value, and splitting them from the stars would leave the stars unqualified.

The side panel's one-line collapsed label (`web._row_label`) is not a table and keeps its prefix.
The terminal's fixed-width `COLUMNS` gains a width-2 first column; the web dataframe gains a first
column whose width is the narrowest Streamlit offers — checked against the installed Streamlit's
`TextColumn` when the task is done, not assumed.

### D7. Configuration: a separate setting, never both

`SCINUMBERS_STORE` (and `--store` on the CLI) names the store. Setting it together with
`SCINUMBERS_CORPUS` is a refusal naming both, not a precedence rule: a reader who set both did not
mean one of them, and silently answering from the other is a wrong-corpus answer that looks right.
`autobuild` is bypassed for the store. The Streamlit app caches the loaded corpus as it does now.

### D8. The new dependency direction, and its import footprint

`scinumbers_ask` imports `bionumbers.tiers` and `bionumbers.readings`. Measured on 2026-10-13: those
pull in `bionumbers.store`, `curated`, `records`, `quotes` — SQLAlchemy and pydantic, no
`anthropic`, `httpx`, `lxml`, `pint` or Streamlit. SQLAlchemy is already in `ask`; pydantic is
transitive through LangChain and is named in `ask` explicitly so a resolver cannot drop it.

The imports are confined to `store_corpus.py` and the presentation module, so a JSONL-only run
never imports `bionumbers`. The reverse rule (`bionumbers` core never imports `scinumbers_ask`)
is untouched. An ADR records the direction and why (one rule, one parser).

## Checked against `dev` (2026-10-15)

This branch's base is 134 commits behind `dev`. Every module this design names was compared
between the common ancestor (`f934cfe`) and `dev`:

| Module | On `dev` | Effect on this design |
|---|---|---|
| `corpus`, `citations`, `tools`, `repository`, `entries_table`, `cli`, `trace` | unchanged | none — D1–D6a stand as written |
| `web.py` | grey superscript citations (ADR-1240), the door, sign-in | D6 rewritten to put the stars inside the superscript; `_CITATION_RUN` reads digits only and must be widened. The entries table and its markers are unchanged, so D6a stands |
| `door_demo.py` | new; its own copy of the superscript pattern, for two recorded BNID-only answers | untouched: the door shows recorded examples, no store and no stars |
| `agent.py` | the stream runs inside `hosted_trace.Isolated`; the tracer is attached per question | none for the agent's logic; see the tracer below |
| `hosted_trace.py` | new: Langfuse, off unless `SCINUMBERS_TRACING=langfuse` (ADR-1000–1020) | when on, the model's inputs — tool results included — go to Langfuse Cloud, so paper passages from the store would too, as BioNumbers text does today. Nothing is changed for it; it is stated in ADR-1600 so the choice is visible. Reviewer text cannot reach it, because it never reaches the model (spec) |
| `test_driver_independence.py` | `HARNESS`, `PRESENTATION` and `IDENTITY_FREE` widened | the new presentation module joins `PRESENTATION`; `store_corpus` is core |
| `evaluation.py`, `eval_cli.py` | tracer cost and approval | the store refusal (6.3) goes in `eval_cli` beside them |
| `pyproject.toml` | `langfuse` in `ask`, test tooling | none beyond naming `pydantic` |
| `messages.py`, `feedback.py`, `trail_store.py`, `accounts.py`, new `enrol`/`pending`/`first_use`/`neon` | sign-in, enrolment, notices | none |
| `docs/roadmap.md` | other sections | this branch's additions are in "Deferred, deliberately"; a textual merge at rebase, no conflict of substance |
| `openspec/specs/grounded-answering`, `corpus-query` | unchanged | the deltas apply as written |

## Risks / Trade-offs

- **The store moves under us** (entry-review keeps writing) → read once at start; tiers are a
  snapshot; the legend says "as of" the load time.
- **A re-extraction reuses a paper's value numbers** → later runs are suffixed (D3), and only the
  store's item id is saved, so an old record never comes to name a new value.
- **The parser misreads a value the kind check passes** (e.g. a `SINGLE` read as one wrong number)
  → `value_text` is always what is shown; the parsed numbers only feed search and unit comparison.
- **Base branch is rebased again** (onto `dev` after harvest/review merge) → no code depends on a
  commit hash; rebase before implementing past the loader.
- **Shown tiers are simulated** → `$` on every simulated tier and the legend, per ADR-0960.

## Migration Plan

None for corpus-file users: the store is opt-in through a new setting. Rollback is unsetting
`SCINUMBERS_STORE`.

## Open Questions

None blocking. Evaluation and the answer sheet over the store are deferred to their own work
package (`docs/roadmap.md`); until then they refuse a store with a message rather than run over it.
