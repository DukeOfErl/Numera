# `bionumbers` — the validator prototype

Loaded when a file in this package is read. The root `CLAUDE.md` has the one-paragraph version.

A **fixed pipeline, not an agent** (ADR-0900): discovery → fetch → JATS reader → one structured
extraction call → mechanical quote check → one retry → one second-text call → JSONL under
`data/runs/<run-id>/` → Postgres → a review page. No module here builds a graph or hands the model a
tool; if the extractor seems to need to search the paper, give it the whole paper.

| Module | Holds |
|---|---|
| `records.py` | Every shape the steps exchange, as frozen pydantic models; the closed state sets (ADR-0910). Also the extraction call's output schema |
| `europepmc.py` | The client: identifier retrieval (ported), `search_open_access`, `fetch`, `licence_of`, the project `User-Agent`. "No XML" is read from the body, not the status |
| `cache.py` / `retrieval.py` | The disk cache and the typed retrieval outcomes, ported from the feasibility branch |
| `jats.py` | `read_jats` → passages with ids; table cells carry their headers; `[ref N]` tokens for bibliographic markers; `render_for_model` |
| `quotes.py` | The fold table from the retrieval probe, byte for byte, plus the micro sign; `verify` names the passage first and the paper second |
| `spend.py` | Prices for the configured model, projection through the provider's token count, `Ledger` with the $2 per-paper ceiling and the run budget |
| `extraction.py` | The instruction (no unit, no expected value), the one call, the verification pass, the states, the fingerprint, the JSONL writer behind the ingester's guard |
| `distractor.py` | The second text: candidates of five types, mechanical exclusion of the value in every form, preference order, second-occurrence fallback (ADR-0920) |
| `store.py` | `review_paper`, `review_item`, `review_decision`, `curated_entry` in SQLAlchemy Core; `record_decision` **fails closed** (ADR-0930). DDL in `sql/review.sql` |
| `review.py` | Presentation: the two texts in an uninformative order and as the paper wrote them, the whole table a cell sits in (ADR-0940), the condition rows, the decision's completeness rule |
| `harvest.py` | Harvest mode (ADR-0950): the classes of number wanted and not wanted, the instruction built from extraction's, the three model-written labels, the twenty-claim bound, one scope per domain (ADR-1500) |
| `curated.py` | The curated tier (ADR-1510): which BioNumbers entries in the slice nothing marks doubtful, and why each other one is left out |
| `cli.py` | `bionumbers discover \| harvest \| extract \| load \| curate \| status` |
| `paths.py` | `data/europepmc/`, `data/runs/`; a test asks git that both stay ignored |

**The dependency direction holds here too.** Core modules import no Streamlit and nothing from
`scinumbers_ask`; only `review.py` and the root `review_app.py` may, and
`tests/test_bionumbers_dependency_direction.py` asserts it over the source the way
`test_driver_independence.py` does for the ask package. The review page imports the ask app's
door (`web.admit` with `check_key=None`) rather than copying it, so a deployment installs both
extras.

**What the model is never shown**: a decision, a choice or a comment. Decisions measure the
extractor and cannot also be its input; the messages are built from the paper and the question only.

**Ported code is unreviewed code.** `europepmc.py`, `cache.py` and `retrieval.py` came from
`feat/grounding-validator-cytoskeleton` with two corrections made in the port itself; the commit
that brought them across lists what a review found.

