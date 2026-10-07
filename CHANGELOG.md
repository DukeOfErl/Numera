# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project aims to follow it going forward. Dates are ISO 8601 (YYYY-MM-DD).
Versions are git tags (`vX.Y.Z`) using [semver](https://semver.org/)'s
pre-release convention: `0.y.z` while the app's shape may still change with
any release; `1.0.0` when it stabilizes.

## [Unreleased]

### Added

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
  `--scope biology|biophysics|chemistry|physics` asks for one domain's classes of value, and the
  domain is recorded on every claim ([ADR-1500]). A value reported beside others of its kind is
  named by its condition (growth state, construct, tissue, position), the control by nothing; and
  every paper and claim records the model the provider says answered, beside the one asked for.
- **The curated tier** (`bionumbers curate`): BioNumbers' yeast and cytoskeleton entries that are
  measured, referenced and undoubted — 423 of 492 — loaded beside the harvested entries as the
  top of the trust order ([ADR-1510]).
- **The Europe PMC client from the feasibility branch, ported and corrected**: an article without
  XML is now recognised from the response body rather than a 404 status, because the service
  answers 500 today; and the article check reads the root element rather than searching for
  `<article`, which an HTML error page also contains.
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
