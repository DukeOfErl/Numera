# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project aims to follow it going forward. Dates are ISO 8601 (YYYY-MM-DD).
Versions are git tags (`vX.Y.Z`) using [semver](https://semver.org/)'s
pre-release convention: `0.y.z` while the app's shape may still change with
any release; `1.0.0` when it stabilizes.

## [Unreleased]

### Added

- **Each harvested paper carries its bibliographic record.** Authors in the paper's order,
  journal, volume, issue, pages, date and identifiers, read from the JATS front matter the
  harvest already parses and kept as one CSL-JSON item (`review_paper.csl_json`), so the
  application can format a citation in any style without a model writing one (ADR-1750).
  `bionumbers upgrade-store --data` fills the record for a store loaded before the column
  existed, from the cached full text.

### Changed

- **Caveat marks have a column of their own**, first in both entries tables, instead of a prefix
  on the property. On the web the table gains a Trust column between Units and ID where entries
  have tiers; Organism, ID and Reference are narrower so it still fits.
- **Citations drawn as superscripts read every citation form** — a `PMC…` label as well as a
  BNID, and several identifiers in one bracket — because the pattern is now `citations.DELIMITED`
  rather than a second, digits-only copy.
- The terminal's ID column widens to the longest identifier shown, since a terminal cannot open a
  truncated cell.
- The system prompt speaks of "scientific quantities" and "a corpus of entries", and asks for "the
  identifier" in a citation rather than "the number".
- **A harvested entry shows its full property name** -- the measure and what it is of -- where
  the store holds one (`review_item.property`, harden-harvest), with the paper's own wording in the
  full entry and still reached by search.
- **An answer cites entries, never papers.** The prompt tells the model the identifier is the
  only citation and to name no author, title, journal, year or DOI; each entry's reference is in
  the entries table, and asked for one, it says where the reference is. On the web the Trust
  column took 12px from Units.
- **A harvested entry opens with its fields apart.** The full entry shows the supporting quote,
  each condition under its name (conditions quoting one passage named together), what the paper
  does not state and what a calculated value came from -- not the search keywords, which packed
  them all into one line.
- A harvest store passed where a corpus file is expected is refused by name instead of reported as
  a corrupt line, and the evaluation command says why it cannot read the store yet.
- **One model call under the ledger.** The extractor and the simulated review made the same
  eight-step call in two copies; both now go through `spend.call`, so a guard fixed in one is
  fixed in the other. The two things the review page takes from its deployment, the database and
  a person's rung, moved to `bionumbers.deployment`, so the review module is core and the
  simulated review installs without the ask extra. The runner filters items by share before
  parsing them rather than after.

- **Citations in an answer are grey superscripts.** A run of `[[nnnnnn]]` is drawn as one small grey superscript, its identifiers comma-separated, so the prose reads through them; the stored answer, the trail and the evaluation still use `[[nnnnnn]]`. HTML is turned on for these alone, after the answer is escaped, in one function (`web.answer_markdown`). Same style as the sign-in door's demo (ADR-1240).
- The test loop's default is three parallel workers, not six: six is faster with memory free but was killed for lack of memory once on an 8 GB machine, mid-commit. `SCINUMBERS_TEST_WORKERS` still overrides. See ADR-1300.
- The test loop is two tiers. A commit runs only the tests it reaches (pytest-testmon), falling back to the full suite when a staged file is not Python under `src/` or `tests/` and is not known to be read by no test; push, merge and CI run the full suite in parallel (pytest-xdist, six workers by default). `bin/testloop.py` carries both. `uv run pre-commit install` again in an existing clone to pick up the push and merge hooks.

### Fixed

- **The git-tracking guard refuses when git gives no answer.** A timeout or a git that could not
  be started was read as "no git" and the write allowed; it is now refused, and the reader told to
  run it again. An evaluation results file is checked on every append, not only when created.
  Outside any repository, or with no git installed, writes go ahead as before (ADR-1800).
- **A harvested value that states a bound is no longer read as a number.** `>500`, "up to 260"
  and "70 and 100" were stated to the model as 500, 260 and 70; they are now cautioned and given
  only in the paper's words (10 of the store's 452 values). A unit holding a scale factor is no
  longer applied to the value (ADR-1620).
- On the web, a harvested value whose reading is uncertain shows the paper's words in the Value
  cell instead of a blank and "no scalar value recorded".
- An item the store reader cannot read, or a paper record citeproc cannot format, is a sentence
  or the plain reference, not a traceback. A citation run holding a group that is not a citation
  still draws the citations beside it.
- **The validator's quote check no longer passes a wrong value as verified** (code review of 2026-10-15). A quote of a table cell matches only a table cell under the headers it names, so "cell: 39" in a Kd column no longer verifies against "isolated in 1939" elsewhere. A quote that begins or ends on a digit must begin or end where the paper's number does, so "39" is not quoted from "139" or "39.4". A number that ends a sentence ("was 2.4.") is now read. MathML exponents keep their meaning (`10<msup>…8` reads 10⁸, not 108) in the 22 of 130 cached papers that use them, and a formula given as both MathML and TeX is read once. Re-checked against all 2,643 quotes in the demo database: none was a wrong value let through; five quoting a formula now read its exponent marked.
- **A publisher's terms page is no longer taken for a licence.** A paper's own licence link counts only if it is a Creative Commons licence or public-domain dedication; 10 of 130 cached papers had been credited with `rupress.org/terms` or Nature's editorial policies. None of the demo's papers was affected.
- **A paper flagged by OpenRouter's moderation fails on its own** instead of stopping the whole run as if the account had been refused.
- The commit hook no longer fails a commit made from a worktree. Git sets `GIT_DIR` for its hooks, and `bin/testloop.py` handed it on to pytest, so every test asking git about a temporary directory got an answer about this repository: 61 false failures whenever the full suite ran. Pytest now starts without the variables `git rev-parse --local-env-vars` names.
- The first-use notice's window follows GitHub's real schedule: it looks back to the start of the previous successful run (plus six minutes) instead of a fixed 70 minutes, which saw about a quarter of arrivals because the "hourly" schedule fires every 4-7 hours. The command's own default is now seven hours. See ADR-1290.
- The keepalive no longer reports a failure when a page reload lands mid-poll after waking the app, installs its browser from the same pinned Playwright it then runs under (`--install-browser`), runs on `ubuntu-24.04` rather than the floating `ubuntu-latest` that migrates to Ubuntu 26 on 2026-10-19, and its comments no longer promise a per-run failure mail.

### Added

- **A harvested value's reference names its authors**, in Chicago author-date, in the entries
  table and the full entry: read from the paper's CSL-JSON record in the store and formatted by
  citeproc-py, with the title as the paper wrote it. The model is never handed it (ADR-1640).
- **The ask agent answers from the harvest store** (`SCINUMBERS_STORE`, or `--store` on the
  command line): curated BioNumbers entries and every harvested value in every domain, read-only.
  A harvested value is cited `[[PMC2652108-1]]`, a later extraction of the same paper
  `[[PMC2652108-1.2]]`; what is saved is the store's own id (ADR-1610). Each entry carries its
  passage, stated and unstated conditions, paper, and whether it was measured or calculated; a
  value is stated as a number only where its reading fits the recorded kind (ADR-1620).
- **Every citation and table row from the store shows its trust tier as stars**, drawn by the
  application, with `#` for a simulated review and `⚠` for a dispute, and a legend wherever they
  appear (ADR-1630). The model is told the tier in words and to decide relevance before trust.
- **Two new caveat marks**: `?` for a value that could not be read with certainty, `∴` for a
  calculated one.
- **Why an entry is disputed**: its Trust cell carries what each objecting reviewer wrote, after
  the stars (double click to read it all); the terminal lists the objections under its table. The
  model never sees them.

- **A validator prototype: from a property question to reviewed numbers** (`bionumbers`,
  the `validator` extra). `bionumbers discover` searches Europe PMC for open-access research
  articles and fetches their XML; `bionumbers extract` makes one structured extraction call per
  paper under a $2 ceiling, checks every quote mechanically against the paper, and chooses a second
  text for each claim; `bionumbers load` puts the items in Postgres; `review_app.py` shows a reviewer
  one claim at a time with two texts and records which fits and whether the value is approved,
  failing closed on the write ([ADR-1520], [ADR-1530], [ADR-1540], [ADR-0930]). Each text is
  shown as the paper wrote it, and a table cell brings its whole table, caption included, beneath
  the two texts ([ADR-0940]). Extraction
  reaches the model through OpenRouter on its own key, `BIONUMBERS_OPENROUTER_API_KEY`, so the
  prototype's spend is readable apart from the ask app's.
- **Harvest mode for the validator** (`bionumbers harvest <run> --pmcids ...`, then `extract`):
  a run starts from a list of papers, and each is asked once for its reusable numbers in seven
  classes instead of for one question's answer; every claim is named by its own property and
  species ([ADR-0950]). The second text is asked never to be another source's value for the same
  property in the same organism, which is a second answer rather than a wrong one.
  A value must be a finding: the size of the animals a study happened to use, given to explain a
  method, is not asked for. Each domain names its own condition fields (a glass: material, preparation, pressure, phase).
  `--topic` names what the papers are about, for a reviewer to choose by.
  `--scope biology|organismal|biophysics|chemistry|physics` asks for one domain's classes of value, and the
  domain is recorded on every claim ([ADR-1500]). A value reported beside others of its kind is
  named by its condition (growth state, construct, tissue, position), the control by nothing; and
  every paper and claim records the model the provider says answered, beside the one asked for.
- **The quote check reads signs**: a value of "−16.6" is no longer verified by a quote reading
  "16.6", nor "10^-3" by "10^3". None of the 523 claims verified so far changes. Discovery takes a
  paper's licence from Europe PMC's index as harvest does, and the default model is GPT-6.1 Sol.
- **The curated tier** (`bionumbers curate`): BioNumbers' yeast and cytoskeleton entries that are
  measured, referenced and undoubted — 423 of 492 — loaded beside the harvested entries as the
  top of the trust order ([ADR-1510]).
- **A simulated review: models stand in for reviewers** (`bionumbers simulate-review --reviewer
  ROLE=MODEL@SHARE`). Each role (AI, student, scientist, senior scientist) is played by a model
  over its own fixed share of the items; a model is shown exactly what the review page shows a
  person and answers the same two questions. Every row it writes records the role and the model,
  and its reviewer name begins `simulated-`, so no figure can pass these off as people's. A
  reviewer can now also **raise an issue** in place of a choice and a verdict; the store records
  it with its text ([ADR-0960]).
- **A decision is taken in two steps, and the value is withheld until the text is chosen**
  ([ADR-0970]). The review page first shows the quantity, the paper and the two texts; the
  reviewer chooses the text that states a value for the quantity and writes the value they read,
  and only then is the stored entry — value, the paper's term, conditions — revealed for the
  verdict. The value read is recorded before the reveal. An issue can be raised at either step. The
  simulated reviewers take the same two steps as two calls and record which model answered each.
- **The value a reviewer types is compared with the stored one**, loosely and the same way for a
  person and a model: ±, ~ and "about", number words, thousands separators, exponents in either
  notation, `um` for µm and convertible units are all read as the same number. The result (matches,
  same number in another unit, differs, unreadable) is recorded with the choice and said in one
  line at the reveal; raising an issue is now two clicks with a cancel; outside biology only the
  conditions the paper states are listed, and each domain's own fields are listed once its papers
  are extracted with them.
- **A person's decisions count on their account's rung**: the review page records the
  signed-in reviewer's role (student, scientist, senior scientist) from the account table on every
  choice and issue, so a person's approval sets a tier as a model's does; `dev` and `admin`
  record none.
- **One trust-tier rule for every reader** (`bionumbers.tiers`, [ADR-0990]): an entry's tier is
  the highest role that approved it with no issue, or curated, or none; whether anyone disapproved
  or raised an issue is a separate flag that does not lower the tier. The dashboards and the ask
  agent both read this one function, and a tier set by a simulated reviewer says so.
- **A human reviewer can choose a domain or a topic, and set a paper aside** ([ADR-0980]). The
  page offers the domains and topics the loaded papers carry and a "Skip this paper" button; a
  skip is recorded and the paper is not offered to that reviewer again. The simulated reviewers
  get none of this and keep reviewing their assigned subsets. `bionumbers upgrade-store` brings a
  review database loaded under an earlier schema up to date in place.
- **Every OpenRouter price is a price at one provider, and the request is pinned to it.** A model
  served by several providers at several rates is otherwise projected at one price and billed at
  another; the request now names the provider the price table was read from and allows no fallback.
- **The Europe PMC client from the feasibility branch, ported and corrected**: an article without
  XML is now recognised from the response body rather than a 404 status, because the service
  answers 500 today; and the article check reads the root element rather than searching for
  `<article`, which an HTML error page also contains.
- The first-use check sends one message after seven days with nothing delivered, saying it found no new readers (with its own time and how many checks completed), so a quiet week can be told apart from a broken check. Measured from the standing issue's last comment; the command itself still prints nothing when nobody is new. See ADR-1350.
- `scinumbers-first-use`, and an hourly workflow that runs it: the operator is told once per reader when they are first seen signing in and when they first ask a question (one line when both fall in the same window), by a comment on one standing issue that opens with an @mention of the owner, and hears nothing when nobody is new. It holds a read-only database role (`sql/first_use_reader.sql`), not the Neon API key. `keepalive-digest` now also covers this workflow, so a failing or silent run is reported once a day. See ADR-1250 to ADR-1280.
- An hourly keepalive (`.github/workflows/keepalive.yml`, `bin/keepalive.py`): a headless browser visits the deployed app, clicks the sleep screen's button if it is showing, and fails unless the door renders, so Community Cloud's 12-hour hibernation no longer costs the first reader a cold start. A scheduled workflow runs from `main` only, so it starts once merged there. A daily `keepalive-digest` workflow replaces GitHub's per-run failure mail with one comment on a standing issue, and also reports a day with no runs at all.

### Changed

- **The door says why there is a door, and offers one way in.** It reads "Use of
  this app is by invitation only since you are using the developer's budget" — the
  button already says what to do, and a stranger needs the reason. The Google button
  is withdrawn because Auth0 signs a reader in with their Google account anyway, so
  the remaining button says just "Sign in". **The Google client stays configured and
  none of the multi-provider machinery is removed**; which providers the door draws
  is one tuple, and restoring it is that tuple
  ([ADR-1100](docs/decisions/1100-one-way-in-with-the-others-kept.md)).

### Fixed

- **The privacy policy now names every store and every recipient.** It said the
  material is kept in a hosted Postgres database, while the conversation's own
  checkpoints and the trail's log file sit on the app's filesystem — so a reader
  exercising the deletion right it grants would have had their database rows
  removed and those files left. Its list of services named the four the code calls
  by name and missed the three it does not: the host (Streamlit Community Cloud),
  the provider behind the provider (Google, which Auth0 federates sign-in to), and
  those two files. Google was the omission that mattered most, being the party whose
  consent screen the policy exists to satisfy.

- **The policy is reachable from the session-cap page too.** That page refuses a
  reader *after* their sign-in has been recorded, and it was the one door with no
  statement on it.

- **A sign-in button's label follows the number of buttons**, rather than being
  written for today's arrangement. Auth0's label had been shortened to "Sign in" in
  place, which made the promise that restoring the Google button is one tuple false:
  it would have drawn "Sign in with Google" beside an unqualified "Sign in".

- **A provider configured without its `client_id` is reported.** Half a credential
  in the secrets box is invisible to `providers()`, so the door widened back to the
  withdrawn Google button with nothing said in the app or the trail. It still widens
  — a door with no button is never right — but the operator is now told.

- **An address that nothing could ever match can no longer be enrolled.** A
  trailing newline off a heredoc, or spaces off a pasted line, went into the
  accounts table verbatim — producing an account that exists, is enabled, looks
  right in every listing that prints it unquoted, and admits nobody, because no
  provider will assert a claim that matches it. The person meets "not enrolled",
  the operator sees their row sitting there, and neither side is told why.
  Surrounding whitespace is now trimmed; whitespace or a control character inside
  an address, or something that is not an address at all, is refused with a
  sentence that quotes it so an invisible character is visible. The guard is in
  `accounts.insert`, so every caller gets it, and in `enrol` before the key is
  minted, so a typo costs no live call.

### Added

- **The sign-in door shows what is behind it.** Under the button, an example
  plays on a loop: a question is typed into a mock input letter by letter, and a
  real answer streams back. The first example takes back the last three words of
  its question and retypes them as a comparison with budding yeast. It is headed
  "What can SciNumbers do?". Each finished answer stays up for 7 s with the caret
  blinking, so a visitor can see the next question is coming. Every example is a
  question actually put to the agent and its answer, shortened for the door with
  every edit recorded beside it. Reduced motion shows each example whole. The third
  example shows cell volumes across mouse cell types as a text chart. The figures
  come from a live run, but the chart is drawn by a script, because the model drew
  every bar of one in the wrong place; a red note says charts are an upcoming feature. Citations on the door are grey superscripts, a run of them comma-separated, and every example ends "*The app itself provides full citations" (ADR-1240)
  (ADR-1200, ADR-1210, ADR-1220, ADR-1230).

- **Enrolling an address that was withdrawn says so**, rather than "already
  enrolled" — which is true of a withdrawn row and reads as though the person has
  access. It names the state and the next step, in one line.
  Reinstating from the command is deferred deliberately: as a side effect of
  enrolling, a mistyped address matching a withdrawn one would issue a credential
  nobody meant to.

- **`scinumbers-withdraw`, one command to end one account's access.** It disables
  the row and revokes the credential at OpenRouter, in that order — either alone
  leaves access open, since a key held in the clear and handed to a tester can be
  spent without the app, and a revoked key under an admitted account reads as the
  app being broken. The row is kept rather than deleted, so the trail rows that
  account wrote keep their attribution. This needed a new column: OpenRouter
  deletes a key by a handle returned once, at creation, which enrolment used for
  its compensating revoke and then discarded
  ([ADR-1150](docs/decisions/1150-withdrawing-an-account-keeps-the-row.md)).


- **The page says what is kept about a reader, in full.** Every door carries a
  collapsed statement: what is recorded, what it is used for, which services it
  passes through, how long it is kept, and where to write to see it or have it
  deleted. **Every** door, so a visitor who has not signed in — and a reader who was
  refused, whose address the attempt already recorded — can read it. Not the side
  panel, which is where a reader works. It is served by the app at its own address
  rather than by a second host, because the door was always the public page
  ([ADR-1110](docs/decisions/1110-the-privacy-policy-is-the-door-itself.md)).

- **A successful sign-in is recorded.** The trail held only refusals at the door, so
  "nobody tried today" and "everybody got in" looked the same, and a reader who
  signed in without asking anything left no trace of having got through. It is
  written once per arrival and carries the account and role like every other record
  of a signed-in session.

- **`scinumbers-pending`, a daily check for readers stuck at the door.** It reads
  the trail for people who said their confirmation email never came and for
  verified accounts waiting to be enrolled, and **prints nothing when nothing is
  waiting** — which is what makes it usable from `cron`, since a monitor that
  reports a quiet day every morning is one whose output stops being read. A problem
  that resolved itself stops appearing, and nothing is tracked to achieve that:
  whether a reader got past verification is derived from records the app already
  writes, and whether an account is enrolled is read from the accounts table rather
  than inferred from the reader returning — which they may never do.

- **The sign-in buttons can be put in any order.** A provider is "the default",
  and therefore drawn first, only because its credentials sit among `[auth]`'s own
  keys; moving them into a sub-table of its own makes it an ordinary named
  provider and secrets order decides. A secrets change with no code change, and
  the Google button keeps its label either way.

- **Sign-in with any address, not only a Google one.** Any OpenID Connect
  provider is a sub-table in secrets and gets its own button on the door; the
  Google client stays exactly where it was, and a tester who signs in through a
  second provider keeps the role and the conversation they had, because the
  address is the identity
  ([ADR-0880](docs/decisions/0880-a-second-provider-beside-the-first.md)).

- **A refused operator credential says which one and what to do.** A 401 or 403
  from OpenRouter names the management key and where to make a new one, and adds
  the consequence nobody guesses: the same key withdraws a tester's credential,
  so that stops working too while it is refused. One from Neon names
  `NEON_API_KEY` and `NEON_PROJECT_ID` rather than blaming the branch name. Any
  other status is still reported as itself, because a 502 read as an expired key
  sends the operator to replace a key that is fine. The README also says where
  to keep those three values, and why not on the command line or in `~/.bashrc`.

- **README says where the console scripts are and how to reach them.** `uv sync`
  installs them into the project's virtualenv rather than onto `PATH`, so a bare
  `scinumbers-enrol` is `command not found` until you say otherwise — the three
  ways are listed, and the table notes that `bionumbers` is a declared entry
  point for a package this repository does not yet contain.

- **`scinumbers-enrol`, one command to enrol a tester.** It mints a capped
  OpenRouter key and inserts the accounts row in one step, naming the database
  branch every time and resolving it through Neon's API so no database URL is
  kept on disk. Nothing is issued without a positive cap, an address already
  enrolled keeps its row, and a key minted for a row that could not be written is
  withdrawn again
  ([ADR-0900](docs/decisions/0900-enrolment-mints-then-inserts-and-compensates.md)).


- **Hosted tracing to Langfuse Cloud, off unless the project says so.** With
  `SCINUMBERS_TRACING=langfuse` and the three Langfuse keys, each question becomes
  one trace — its model turns, tool calls, tokens and timings — whose id is derived
  from the question's own identifier, so a trail row or a rating leads straight to
  it. Readers appear only as an opaque per-account digest; ratings are copied as
  scores; evaluation runs are tagged `eval`. Anything short of the setting sends
  nothing, and a tracer that fails costs traces and never an answer
  ([ADR-1000], [ADR-1010], [ADR-1020]).
- **An evaluation run shows the tracer's monthly usage and its own estimated cost
  before asking anything,** and waits for a typed `yes` when more than half the
  free allowance is used, when the run would not fit, or when a figure cannot be
  counted. Anything else ends it with nothing asked or recorded.

- **The SciNumbers mark, beside the page's title** — on the conversation and on
  the sign-in and refusal pages, so the app looks like itself before a reader is
  admitted. Inlined rather than linked, so its strokes take the reader's own text
  colour: nothing here pins a theme, and a near-black mark would be invisible to
  anyone reading in a dark one. A missing asset costs the mark and nothing else.


- **Sign-in, enrolment and a credential per tester, for hosted deployments.** With
  `[auth]` in secrets every visitor signs in with Google and must be enrolled — a
  row the operator inserts in an `accounts` table beside the trail, naming the
  role and the tester's own capped OpenRouter key — before anything is drawn.
  Signed in but not enrolled is refused with one sentence and recorded; an
  unreadable accounts table admits nobody and says a different sentence, because
  a check that failed open would let an outage open the door. Each session gets
  an agent funded by its own credential; an enrolled account with no credential is
  told so and no agent is built. Configure nothing and the app runs exactly as it
  did ([ADR-0780], [ADR-0820]).
- **Every record of a signed-in session carries the account and the role it held
  at the time**, written when the row is and never looked up afterwards, so a
  later change of role cannot rewrite what a rating weighed. `user_role` joins
  `user_email` as a column; the first schema change since the table was created,
  applied idempotently on every start. The role and the account are stamped onto
  the trail at the sink by the web driver — the agent, the tracer and the feedback
  module never hold them, and a test parses their source to keep it that way
  ([ADR-0810]).
- **Five roles and a default-deny grant table with one permission.** Student,
  scientist, senior scientist, dev and admin; the table grants `dev panel` to dev
  and admin and refuses it to the three tester roles, and lists nothing else,
  because a permission exists only where some role is refused it. Reading and
  rating are what enrolment grants ([ADR-0800]).
- **A Dev tab in the side panel**, beside the entries, for dev and admin — and for a developer's
  machine with no sign-in configured — showing this session's trail for its last
  five questions. Absent, not disabled, for everyone else. Nothing in it reaches
  the model.
- **A cap on open sessions**, `SCINUMBERS_MAX_SESSIONS` (default 20), counted by
  heartbeat and never by client address. The next visitor is told to try again
  shortly; no open session is ended. It protects the host, not the budget, which
  each tester's credential already bounds ([ADR-0790]).

### Changed

- **The unverified-address refusal is a way back in, not a dead end.** It asks the
  reader to confirm their address and offers one button to continue with — no
  signing out and no password to retype, because a fresh login through the same
  provider is enough. Sign out stays beside it, as the only way back for someone
  who signed in with the wrong address.

- **A reader whose confirmation email never arrived can say so**, and the request
  reaches the durable trail where the operator finds it (`sql/signin.sql`, which
  also lists those who gave up without asking, and the enrolment queue). Nothing is
  sent from the app: resending needs a provider credential that could also create
  accounts, which is not a trade worth making for one message.

- **Only an address the identity provider says it has verified is admitted**, and
  a provider that says nothing counts as unverified. Where sign-up is open this is
  the one thing standing between an enrolled tester and anyone who registers their
  address. The refusal has its own sentence, separate from "not enrolled", because
  the reader's next step is different
  ([ADR-0890](docs/decisions/0890-only-a-verified-address-opens-the-door.md)).

- **The default model is `anthropic/claude-opus-4.7`**, where it was
  `anthropic/claude-haiku-4.5`. Development ran on a cheap instruction-follower
  while the shape of the app was still moving; what is read now is answers. It
  costs five times as much per token in both directions, so a budget buys fewer
  questions — the per-question ceiling and the run budget are unchanged and still
  bind. Override with `SCINUMBERS_MODEL`; the evaluation harness names the model
  per run. What it buys, over three repeats of ten questions: 65% of expected
  entries reach the entries table against Haiku's 53%, and all of that lead is in
  the `compound` questions (62% against 31%) — on `basic` ones the two are a tie.
  Haiku also answered two of the six unsupported questions with a quantity, where
  Opus declined all six ([the run](docs/evaluations/2026-09-17-three-models.md)).


- The side panel's spend is one line rather than two: the run budget, with what
  the provider still honours on the reader's own key in the parenthesis behind it
  — "$0 of $2.00 ($4.89 on key of weekly $5.00)". Two captions in two registers
  left a reader working out which of the two would stop them first.
- The sign-out button shares a row with the account it belongs to, which is set
  over two lines — the email, and the role beneath it. The row is a horizontal
  container rather than two columns, so the button stays beside the name however
  wide the panel is, and it keeps its own width when the panel is narrow. The side
  panel has a minimum width, because it could be dragged narrower than its
  contents can survive.
- The page says whose money the questions cost — "Model usage is paid for by the
  developer" — wherever it runs, rather than only on the deployment branch. What a
  reader sees does not depend on which branch built the page.
- The data credit is behind a "Data: BioNumbers (Milo et al.)" popover rather than a standing
  caption, and it is now shown wherever the app runs rather than only where it is
  deployed. Attribution has to be present on every page view; it does not have to
  be read on every page view.
- Headings no longer offer a link to themselves. Streamlit gives every heading an
  anchor and a chain icon on hover; this page is one screen with one reading order.
- The entry count and the conversation's identifier are shown only to the roles
  that hold the dev panel. They are diagnostics, and they sat above what a tester
  came for.
- The side panel names the signed-in account and role without the "Signed in as"
  preamble — the sign-out button beside it says that — and its spend figure is
  headed "Session budget", which is what it now scopes.
- The side panel's statement of what is kept is one line — "All app exchange is
  logged for product development" — rather than an enumeration of the
  fields, which was accurate and too long to read. The fuller statement, shown
  once before use, is deferred until there are users rather than invited testers.
  The prototype caveat no longer appears twice: it stays in the pinned banner.
- A signed-in tester whose allowance is spent, or who has no credential yet, is
  told to ask whoever runs the deployment, and that the allowance renews monthly.
  The funder-neutral wording stays for a developer on their own key.
- **With sign-in configured, a session is keyed on the account rather than on the
  `?session=` link.** The link is supplied by whoever holds it, and it had become
  the key for the identity stamped on every record, the dev panel's rows and the
  session cap — so two readers on one link overwrote each other's attribution, a
  dev on a shared link could see another reader's trail, and the sign-in redirect,
  which drops the query string, stranded the session it came from. One account is
  now one conversation; a deployment without sign-in keeps the link as the session
  ([ADR-0830]).
- An enrolled account with no credential now meets a door of its own rather than a
  page with its input removed, so the page has one gate and no code path can build
  an agent that falls back on the deployment's own key.
- Enrolment matches an address without regard to case, and the session cap counts
  a reader once they are through the door rather than when they arrive — an
  abandoned sign-in page no longer holds a place ([ADR-0790]).

- **A credential the model provider refuses is caught at sign-in**, with a
  sentence saying whose job it is to reissue. It used to surface only when a
  reader asked something: the model call failed, nothing was retrieved, and the
  answer reported finding nothing in the corpus — a broken key wearing the face
  of a thin corpus. An unreachable provider is deliberately not treated the same
  way, since that would lock every tester out over a blip.
- **Each tester's run budget is their own**, keyed to the account that pays for
  the questions rather than shared across the deployment, and the side panel
  shows what the model provider says is left on that tester's key.

### Fixed

- **A reviewer needs no API key**: the shared door admits an enrolled account without one to the
  review page, which makes no model call, and the ask page's refusal now says that reviewing is
  still open to the account. Before, a reviewer had to hold a key they would never use.
- **A reading in scientific notation, or beside a parenthesis, is compared at its written
  precision**: `1.2 x 10^9` against a stored `1.23 × 10⁹` matches (it was two digits against
  ten), a bare `10⁻³` is read, and `39 min (n = 3-5)` or a stored `39 (30–45)` is 39 and not the
  range in the parenthesis. Over the demo database 21 readings move from "differs" to "matches"
  and none the other way. A row from before the two steps keeps no agreement rather than
  "unreadable"; an issue after a verdict is refused like a second choice; an interrupted SQLite
  rebuild is refused rather than read as an empty store; the skip is not offered at the reveal.
- **`LANGSMITH_TRACING` no longer sends anything.** `langsmith` arrives with
  `langchain-core`, and that one variable, set by anyone, used to ship prompts and
  corpus text to a third party. It is now refused inside the agent for every caller
  ([ADR-1010]).

- A session pruned for idleness and returned to kept drawing "signed in as" while
  recording no account at all; identity is re-established on every rerun.
- Signing out cleared the identity but left the dev panel's rows, so the next
  account on that tab could be shown the previous reader's questions. Ending a
  session is now one operation over all three per-session stores.
- A signed-in reader who filled a conversation could not start another: the
  conversation key was a pure function of their address and is also the thread
  the length limit applies to, so a full conversation refused every further
  question with no way out. A fresh link starts a fresh conversation again.
- One tester reaching the run budget refused every other tester's next question,
  although each funds their own with a separate capped key.
- A reader mid-conversation could be turned away at the cap after their heartbeat
  was pruned, contradicting the promise that no open session is ended.
- The enrolment-unavailable page offered nothing to click, so the retry it
  promised needed a manual reload.
- `authlib>=1.3.2` joins the `ask` extra, for `st.login`.

- **The trail records the question as asked, the answer as given, and the entries
  the answer stood on.** A rating collected before this said "answer
  `c23c83c16324` was wrong" and there was no way to learn what it was answering.
  Three records on the existing table, under the question's own identifier, with
  no migration: the question written when the question *starts*, so a run that
  hits a spend ceiling or a missing key still leaves a record of what was asked.
  Cited and retrieved entries stay separable, and the retrieved set is the whole
  one rather than the head the page displays. Both interfaces now say that
  questions and answers are kept, and why ([ADR-0840]).
- **The structured trail can outlive the container that wrote it.** The trail was
  written to a file inside a hosted container whose disk does not survive a
  reboot or redeploy, so every search, alias resolution and spend increment from
  every real session was discarded — the requirement to log under a per-question
  identifier satisfied, and its stated purpose, being investigable after the
  fact, defeated. A Postgres destination can now be configured alongside the
  file, and the table is created on first use. Configure nothing and the app
  behaves exactly as before; refusing to start without a telemetry database would
  make the absence of telemetry an outage ([ADR-0700]).
- **A failed recording never fails a question**, which is the deliberate opposite
  of the spend limits. A spend limit fails closed because proceeding costs
  unbounded real money; recording fails open because proceeding costs one row of
  a dataset read by eye. One attempt, no retry — an unreachable database hangs
  rather than failing fast, and a question held open to record a row is worse for
  the reader than the missing row. Failures are reported to the operator and
  counted, never shown to the person asking ([ADR-0710]).
- **Records name the session as well as the question**, so a sequence of
  questions asked by one person can be reassembled. Without it, one person asking
  ten questions is indistinguishable from ten people asking one. The session also
  reaches the metadata a tracing tool reads, so one added later inherits it.
- **What the page draws names the question that produced it.** Each rendered item
  carries its question's identifier, which is what a rating on an answer will
  have to name. Neither this nor the session above can be added to records
  already written, which is why both precede the feature that needs them.
- **An answer can be rated, and rating is optional.** A thumbs up or down sits at
  the foot of each answer's prose, beside the entries it rests on rather than
  below them. Recording one is never required: an answer nobody rates behaves
  exactly as it does today, and the rating is committed on the click, because
  most people who rate will do nothing else and a design that waits for a second
  action collects nothing from them. A rating is final once given, and the
  control shows it as settled ([ADR-0740]).
- **Disapproval — and only disapproval — invites a comment.** The box asks what
  was wrong, which is unanswerable about an answer somebody has just approved of,
  so approval is recorded, acknowledged, and asks for nothing further. The hint
  asks a reader to name the identifier of any entry they believe is wrong:
  per-entry rating is deliberately not built, and what readers choose to write
  about entries is the evidence for whether it should be.
- **Comments are read by whoever operates the system, and are never sent to the
  model.** Not to the conversation, not to a prompt, not to the state a later
  question is answered from. A comment is the one input to this system authored to
  be read by the people running it, so text asking the model to disregard its
  instructions must not arrive by that route; an agent that reacted to disapproval
  would also answer differently depending on who was watching, and its recorded
  trail would stop describing what it does ([ADR-0750]).
- **Ratings outlive the deployment that collected them**, in the same append-only
  table as the trail and under the same question identifier — so a judgement can
  be read beside what that question actually retrieved. Recording a rating fails
  open like every other record: a failed write is never shown to the reader and
  never interrupts the conversation. Space for who gave the rating is recorded and
  left empty, because the system has no notion of who that is yet, and a record
  written before identity exists can never be attributed afterwards.
- **An answer is shown as two columns** — the prose and its rating on the left, the
  entries it rests on to the right — so a reader checking a number against the row
  it came from sees both at once instead of scrolling between them. Entries the
  answer did not cite are folded away under their own heading; the cited ones
  never are, because they are what the prose stands on ([ADR-0760]).

- **A spent API key ends a question as a limit, and says whose limit it is.** Where
  the provider refuses a request for lack of credit, the question ends as
  `provider_limit` rather than as an indistinguishable `provider_failure`, and both
  drivers say that the remedy lies with whoever pays for the deployment — replacing
  the page's "start a new session" advice, which a spent key makes useless. Further
  questions are refused, since asking again cannot come out differently, and the
  request is no longer retried, because a key acquires no balance during a backoff.
  Whatever the answer had established before the refusal is kept rather than replaced
  by the notice ([ADR-0600]).
- **An evaluation harness: `scinumbers-eval`.** A third adapter over the same agent,
  with no mode flag — it asks a committed question set, records one line per answer
  as the answer completes, resumes an interrupted run without re-asking, and reports
  figures that are never combined across model, prompt or corpus. `check` validates a
  set against a corpus before a run costs anything; `report --sheet` writes every
  answer beside the entries that bear on it, as HTML or PDF.
- **No result holds a score.** Each record carries the question, the answer, the
  entries cited and retrieved, the context the agent was shown and what produced it.
  Every figure is computed from those, so a scoring rule can be corrected and a whole
  baseline re-scored without asking a paid question again — which has already paid for
  itself twice, once for a rule and twice for a mis-built expected list
  (`--expected-from-set`).
- **An expected entry is scored by reaching the reader's table, not the prose**
  ([ADR-0530]). The table lists every retrieved entry, so reaching it is what a reader
  gets; requiring prose citation of every expected entry fails every good answer to a
  question the corpus answers ten times over. The rank within that table is reported
  beside it, because an entry ranked fortieth is one nobody sees, and a ranking failure
  needs a different fix from a search failure.
- **Questions carry a tier** — `basic`, `compound`, `declining` — and the report gives
  its figures per tier, so a gain on hard questions cannot be paid for out of the
  simple ones without showing. On the first baseline the aggregate read 51% while
  `basic` stood at 66% and `compound` at 31%.
- **A cited entry at odds with its peers is flagged, where "peer" is now meaningful**
  ([ADR-0540], superseding [ADR-0520]). Peers are the question's own expected entries
  for the cited entry's organism and unit; the previous definition — the corpus's other
  entries with an identical property string — judged 0 of 91 citations on the first
  baseline, because `property` is free text and four entries rarely share a spelling.
- **A first answer baseline**, ten questions over three repeats, recorded in
  `docs/evaluations/`.
- **The evaluation refuses to write its results where git would track them.**
  Every record carries the retrieval results the agent was shown, verbatim, so a
  results file holds corpus text — the same unlicensed data the corpus itself is.
  The refusal asks git directly, in the write path rather than the command, and
  `evaluations/` is gitignored as well.
- **`scinumbers-eval report`** — reads a results file and gives its figures:
  expected entries cited, and the two ways an expected entry can be missed
  (retrieved and passed over, or never retrieved) reported apart; whether the
  agent searched for the asked organism and property, kept separate from what it
  settled on citing; whether unsupported questions were declined, with every
  answer flagged as stating a quantity listed for reading; the agent's own
  grounding warnings; cited entries whose value sits far outside the interval
  their peers occupy; how often each limit was reached; and cost, with this
  session's spend apart from the run's total. Figures are never combined across a
  different model, prompt or corpus, a partial file says so before any figure,
  and a comparison that could not be made is said rather than left as a silence.
  Figures per question tag and per entry shape on request.
- **`scinumbers-eval run`** — asks a question set and appends one record per
  question as it completes, so an interrupted run keeps everything it finished.
  Each record carries the question, the answer, the entries cited, retrieved and
  expected, every retrieval's arguments, the context the agent was actually shown,
  the agent's own grounding warnings, and what produced it: the model and its
  settings, a digest of the prompt, a digest and entry count of the corpus, the
  code version, and the time. Re-running resumes: only the questions and repeats
  with no result are asked. A question that fails is recorded as a failure and the
  run carries on; a question that ends on the run budget stops the run and says
  how many were left unasked.
- **A question set for evaluating answers**, and `scinumbers-eval check` to
  validate one. Each question records what it asks — the property and the
  organisms, in the corpus's own vocabulary, and more than one of each where the
  question is a comparison — the entry identifiers that should support its
  answer, whether the corpus can answer it at all, the question it follows, and
  tags for what it exercises. The check refuses a set that could
  only produce misleading figures: a misspelled key, a quoted identifier, a
  repeated question id, a follow-up whose parent is absent, an expected entry
  the corpus does not hold, or a set whose expected entries are all complete
  and so measure the happy path alone.
- **SciNumbers ask** — an agent answering natural-language questions about
  biological quantities from a supplied JSONL corpus, citing an entry for every
  number and saying it could not find one rather than answering from the model's
  own knowledge.
- **Two drivers over one agent** — a terminal (`scinumbers-ask`) and a web page
  (`streamlit run streamlit_app.py`), both rendering the same events. The agent is
  not told which is calling it.
- **Entries beside every answer** — cited first, then others the search found and
  the answer passed over, with the counts of what was retrieved and what matched.
- **Marks for what the source did not claim** — no measurement method, no scalar
  value, cited-but-not-retrieved, a bound or approximation reported as exact, two
  bounds that may be different quantities, and a range spanning more than a
  millionfold. Each is shown to the reader and told to the model.
- **Dimensional checking** — values are compared only where their units measure the
  same kind of thing, with an unrecognised unit reported as unknown rather than
  assumed compatible.
- **Sessions that survive a restart** — LangGraph checkpoints keyed by a session
  identifier published to the page's URL.
- **Limits said where they bind** — a per-question spend ceiling with a warning
  derived at 80 per cent, a run budget, a conversation bounded by token count, a
  model-call limit and a retrieval limit. Every question ends with a stated reason,
  what it cost, and which bounds it reached.
- **A warning when an answer is not grounded** — a citation to an entry no tool call
  returned, and an answer produced with no retrieval behind it.

### Known gaps

- No judged layer yet: the deterministic scoring works and a baseline has been
  recorded, but nothing judges whether a *sentence* is true. Deferred to
  `add-judged-faithfulness`, because the hand-labelled reference a judge must be
  validated against came back 29 sound of 30 and cannot gate anything.

- **`bionumbers-ingest`** — a command that turns the published BioNumbers export
  (an HTML table served as `.xls`) into a JSONL corpus. The export is fetched by
  the reader and nothing derived from it is ever committed, so a corpus stops
  being an artefact only its author possesses ([ADR-0200]).
- **A manifest beside every corpus**, recording the source's checksum, size and
  modification time, when the run happened, which version ran, and every count
  from the report. Each record also carries twelve characters of that checksum.
  The export has no date or version anywhere in it, so without this two corpus
  files cannot be told apart or dated ([ADR-0240]).
- **A run report** of what could not be interpreted, with a count per flag —
  zeroes stated rather than omitted.
- **`range_fused`** on every record: the stored bounds may come from two
  different quantities, because bounds are the lowest and highest number in the
  cell. 1,418 records of the current export ([ADR-0230]).
- **`range_percent_deviation`** in `parse_flags` where the bounds came from a
  relative uncertainty: `±23%` is a fraction of the value, not a quantity, and
  reading it as one gave a 46-unit interval around a value of 0.488.
- **`range_one_sided`** and **`range_approximate`** on every record: which kind
  of hedge the source used, because the two need different words in front of a
  reader. 594 and 1,639 records; together they partition `range_qualified`.
- **`range_qualified`** on every record: the source did not state a closed
  interval. `<0.001` stored as the interval 0.001–0.001 asserts an exact equality
  where the source said *less than*. 2,233 records.
- **A resolver** that reports whether a corpus is present, or whether an export
  beside it could produce one, so a driver can offer to build it rather than
  failing with "no corpus at that path" while the export sits in the same
  directory. Reporting is separate from building, so the caller can say what is
  about to happen before a 27 MB read. A corpus that exists is never rebuilt.
- **The ingest operation refuses to run where git would track its output**, naming
  the repository, rather than writing unlicensed data onto a committable path. In
  the operation rather than the command, so every caller inherits it ([ADR-0250]).

### Changed

- **Citations are written `[[100002]]`.** The model was asked for `BNID 100002`, in
  a package no longer named for that database. The delimiters mean the parser has no
  rules about an identifier's shape left — the width floor, the run rule and the
  digit-count continuation existed only to infer where an identifier ended
  ([ADR-0410]). The prompt now produces the form from the parser's own definition
  instead of restating it, which it had done for the project's whole life with
  nothing tying the two together.
- The parser still accepts `BNID 100002`. Not for the model's sake — an entry
  rendered to it no longer contains that form — but for the reader's: someone who
  knows BioNumbers types it into a question, follow-ups inherit the conversation,
  and from then on answers are written in it. Rejecting it would mark those
  well-cited answers unsupported.
- **An entry's own cross-references are restated only where the model reads them.**
  BioNumbers writes `See BNID 102065, 104333` in its entry text; the copy handed to
  the model says `See [[102065]], [[104333]]`. The stored corpus and every surface a
  person sees keep the source's words, so an entry stays quotable and a view of the
  unprocessed record remains possible ([ADR-0420]). Rewriting at ingest was
  rejected for that reason.
- **The identifier field and corpus key are `entry_id`.** Still an integer;
  [ADR-0430] records what a widening to a string would touch rather than building
  for a source that does not exist yet.
- Trace records name `entry_id` and `entry_ids` where they named `bnid` and `bnids`.
  A `logs/trace.jsonl` written before this reads differently to anything parsing
  those keys.
- **Renamed to `scinumbers`.** The package is `scinumbers_ask`, the console script
  is `scinumbers-ask`, and the environment variables are `SCINUMBERS_*`. The app
  has called itself SciNumbers on every surface a reader sees since the README was
  written; the code now agrees ([ADR-0400]). `bionumbers-ingest` keeps its name —
  it is the BioNumbers adapter, and that is what it is called.
- A `BIONUMBERS_ASK_*` variable now **stops the run** and names its replacement,
  rather than being ignored. Ignoring one is configuration that silently stops
  being read — a ceiling that no longer binds, a run label that quietly becomes
  `dev` and mixes an evaluation's spend into a person's — and each of those looks
  like a working run.
- The whole export is processed by default; a row limit must be asked for and is
  recorded in the manifest. A sampled corpus looks complete and is not.
- The corpus appears at its destination only after the last record is written, so
  a failed run leaves the previous corpus or nothing — never a short one.
- JSONL is the only output format; the parquet output and `pyarrow` are dropped,
  since a second serialization path is a second place the contract can drift
  silently ([ADR-0220]).

### Fixed

- **A question that searched for nothing no longer shows an empty "Retrieval" box.**
  The page opened the box before the first event arrived, so a question answered
  without a single tool call — a refusal, a spent key, an answer the model gave
  straight — left a collapsed box on screen claiming a search that never happened.
  It is opened by the first retrieval now, as the replay path has always done.
- **An ending that speaks for the agent is no longer reported as a bad answer.** Where
  a question stops on its spend ceiling, on an unpriceable response, on the retrieval
  bound, or with no answer at all, the sentence the reader sees is the agent's own —
  and it was being run through the citation and grounding checks, so a reader could be
  told "this answer is not grounded in the corpus" about a system notice, with
  `answer.ungrounded` written to the trail for a question the model never answered.
  What retrieval found is still reported: that is evidence, not a judgement about
  prose.
- **A molecular mass no longer compares as unknown against a length.** The unit
  table classified the symbol `kDa` but not the spelled-out `kDalton`, and
  `Copies/cell` but not `ribosomes/cell`, so the check that exists to refuse a
  comparison between two kinds of quantity stayed silent on exactly the case it
  was written for. Eleven unit spellings across 73 entries now classify;
  no previously classified unit changed dimension. The per-cell family is
  enumerated rather than matched by a rule, because "anything per cell is a
  count" would file `pg/cell`, `fg/cell` and `g/cell` — 38 entries — as counts,
  and a mass per cell would then read as compatible with a ribosome count.

Defects in the ported first-pass ingester, each of which produced a plausible
number rather than an error:

- Markup was stripped before entities were unescaped, and the export's injected
  markup arrives escaped — so the strip matched nothing, the unescape
  manufactured a live tag, and 10,206 of 14,294 records carried `<IMG …>` in
  their keywords while the flag meant to report it read **zero**, because its
  condition was unreachable.
- Any angle bracket was treated as markup, deleting scientific content: variable
  notation (`<D>`, `<Csat>`) and whole clauses after a less-than sign, including
  a p-value and a DOI fragment, out of `Comments`.
- `2×10^5` was read as three numbers and `150,000` as two, inflating the
  fused-range counts by nearly a third.
- The plus-or-minus deviation was the first number in the cell rather than the
  one after the sign, and 138 cells with more than one `±` collapsed into a
  single fabricated interval, unflagged.
- A hyphen after a unit was read as a sign, so `5%-10%` gave −10 to 5 on 203
  records; a number without a leading zero lost its decimal point on 20.
- Bounds written after a "Table link" URL were discarded on 10 records.
- Three cells wrote an exponent once for both bounds — `1-2×10^9 cells/ml` stored
  as 1 to 2,000,000,000 — now flagged rather than corrected.

[ADR-0410]: docs/decisions/0410-one-delimited-citation-form.md
[ADR-0420]: docs/decisions/0420-rewrite-notation-when-rendering.md
[ADR-0430]: docs/decisions/0430-the-entry-identifier-stays-an-integer.md
[ADR-0400]: docs/decisions/0400-the-package-is-named-for-the-question.md
[ADR-0200]: docs/decisions/0200-ship-an-ingester-not-a-prepared-corpus.md
[ADR-0210]: docs/decisions/0210-verifying-a-contract-owned-by-another-branch.md
[ADR-0220]: docs/decisions/0220-jsonl-only.md
[ADR-0230]: docs/decisions/0230-flag-and-count-never-correct.md
[ADR-0240]: docs/decisions/0240-stamp-every-ingest.md
[ADR-0250]: docs/decisions/0250-guards-belong-to-the-operation.md
[ADR-0600]: docs/decisions/0600-a-spent-key-is-its-own-ending.md
[ADR-0520]: docs/decisions/0520-the-outlier-check-compares-an-interval.md
[ADR-0530]: docs/decisions/0530-an-expected-entry-must-reach-the-table.md
[ADR-0540]: docs/decisions/0540-peers-come-from-the-expected-entries.md
[ADR-0700]: docs/decisions/0700-neon-for-the-durable-trail.md
[ADR-0710]: docs/decisions/0710-recording-fails-open.md
[ADR-0740]: docs/decisions/0740-native-st-feedback.md
[ADR-0750]: docs/decisions/0750-feedback-is-recorded-here-not-at-the-tracer.md
[ADR-0760]: docs/decisions/0760-an-answer-is-two-columns.md
[ADR-0780]: docs/decisions/0780-accounts-live-in-the-trail-database.md
[ADR-0790]: docs/decisions/0790-the-session-cap-is-a-heartbeat-registry.md
[ADR-0800]: docs/decisions/0800-default-deny-and-the-pruning-rule.md
[ADR-0810]: docs/decisions/0810-the-role-is-written-at-record-time.md
[ADR-0830]: docs/decisions/0830-the-session-is-keyed-on-the-account-not-the-link.md
[ADR-0820]: docs/decisions/0820-one-agent-per-session-handed-a-credential-not-an-identity.md
[ADR-0840]: docs/decisions/0840-what-a-question-s-trail-keeps.md

[ADR-1520]: docs/decisions/1520-a-fixed-pipeline-not-an-agent-loop.md
[ADR-1530]: docs/decisions/1530-named-terminal-states-not-confidence.md
[ADR-1540]: docs/decisions/1540-the-second-text-always-two-kind-recorded.md
[ADR-0930]: docs/decisions/0930-the-review-store-fails-closed.md
[ADR-0940]: docs/decisions/0940-texts-as-written-and-the-whole-table.md
[ADR-0950]: docs/decisions/0950-harvest-first-ask-later.md
[ADR-1500]: docs/decisions/1500-a-domain-is-a-scope-in-the-user-turn.md
[ADR-1510]: docs/decisions/1510-the-curated-tier-admits-only-undoubted-entries.md
[ADR-0960]: docs/decisions/0960-a-simulated-review-says-it-is-one.md
[ADR-0970]: docs/decisions/0970-the-value-is-withheld-until-the-text-is-chosen.md
[ADR-0980]: docs/decisions/0980-what-a-person-may-choose-and-a-model-may-not.md
[ADR-0990]: docs/decisions/0990-one-trust-tier-rule-with-a-separate-dispute-flag.md
[ADR-1000]: docs/decisions/1000-langfuse-cloud-eu-over-langsmith.md
[ADR-1010]: docs/decisions/1010-tracing-is-a-project-setting.md
[ADR-1020]: docs/decisions/1020-attribution-is-an-opaque-digest-attached-by-the-driver.md
