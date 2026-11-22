## Why

The project is going public under the name **Numera**. Today it answers to three names: SciNumbers on
every surface a reader sees (the page title "SciNumbers ask", the README), `scinumbers_ask` and
`SCINUMBERS_*` wherever a developer looks, and `bionumbers` for the project itself and for the
grounding validator. The checkout folders were renamed to `Numera` on 2026-11-18; the code has not
followed.

`bionumbers` as the validator's name is the same false coupling ADR-0400 removed from the ask
package: the validator checks numbers harvested from papers and has nothing BioNumbers-specific in
it. ADR-0400 left it alone only because it lived on an unmerged branch. It is on `dev` now.

## What changes

**The project and two packages are renamed.** The distribution `bionumbers` becomes `numera`.
`src/scinumbers_ask/` becomes `src/numera_ask/` and `src/bionumbers/` (the validator) becomes
`src/numera_validator/`. Every console script follows: `scinumbers-ask`, `-eval`, `-enrol`,
`-withdraw`, `-pending`, `-first-use` become `numera-*`, and the validator's `bionumbers` becomes
`numera-validator`.

**The environment prefix becomes `NUMERA_*`.** Every `SCINUMBERS_*` variable, and the validator's
`BIONUMBERS_REVIEW_DB_URL` and `BIONUMBERS_OPENROUTER_API_KEY`, are renamed. Each retired name is
**refused by name**, extending the existing map in `config.py`. A name retired by the earlier rename
(`BIONUMBERS_ASK_*`) now names its *current* replacement, never the intermediate `SCINUMBERS_*` one,
which is itself retired. The validator's two names are refused inside the validator, where it reads
them: its core may not import the ask package.

**The wording follows.** The page title, README, `CLAUDE.md` files, diagrams and live specs say
Numera. "SciNumbers" goes from the code and the UI entirely.

## What does not change

**BioNumbers as the data source keeps its name.** `bionumbers_ingest` and its `bionumbers-ingest`
command stay, as ADR-0400 decided: it is the BioNumbers adapter, and that is correct naming rather
than coupling. So do `numera_ask/bionumbers.py`, the BNID notation, and every sentence that means
the database.

**History is not rewritten.** Accepted ADRs, archived changes and past CHANGELOG entries keep the
names they were written under.

**The deployed app does not move here.** It runs from `deploy/streamlit-cloud`, which keeps the old
names until the GitHub rename (a later step). This change lists the external settings that must be
renamed in the same moment (Streamlit Cloud secrets, the Actions secret `SCINUMBERS_TRAIL_READ_URL`,
`~/.config/scinumbers/enrol.env`), so that switch is planned rather than discovered.

No behaviour changes apart from the names. In-flight Streamlit sessions and LangGraph checkpoints
written under the old module paths are dropped, as they were in the previous rename.
