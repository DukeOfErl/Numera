"""The `bionumbers` command: discover, extract, load, status.

One driver over the pipeline's steps, in the order the design fixes them (D1, ADR-1520):
discovery writes what may be read, extraction reads it under the two ceilings and writes what
came out, the loader moves a finished run into the store, and status reads a run back without
touching a network or a model. The steps are separate commands rather than one because each
leaves a file the next reads: a run can be inspected between steps, re-extracted without
re-discovering, and re-loaded without re-spending (design D11).

Nothing here decides anything about a paper. Every judgement -- what is a claim, what verifies,
what is admissible as a second text, when a ceiling stops a call -- is made in the module that
owns it, and this file only carries records from one to the next and to disk.

The two seams a test needs are module-level functions, `_europepmc` and `_model`, because both
default to a live service and a test monkeypatches the seam rather than the network.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bionumbers import curated, harvest, paths, store
from bionumbers.cache import DocumentCache
from bionumbers.distractor import choose_second_text
from bionumbers.europepmc import (
    EuropePMC,
    FullText,
    NoFullText,
    http_client,
    licence_of,
)
from bionumbers.extraction import (
    INSTRUCTION,
    MAX_TOKENS,
    RESULTS_FILE,
    ProviderRefused,
    RunFileWouldBeCommitted,
    extract,
    instruction_sha256,
    read_results,
    write_results,
)
from bionumbers.jats import JatsUnreadable, read_jats
from bionumbers.openrouter import API_KEY_ENV, DEFAULT_MODEL, NoCredential, OpenRouterModel
from bionumbers.records import (
    UNLICENSED,
    Discovery,
    Fingerprint,
    NotReviewable,
    Paper,
    PaperResult,
    PaperState,
    ReviewItem,
    Spend,
)
from bionumbers.spend import PRICES, Ceiling, CeilingReached, Ledger

DB_URL_ENV = "BIONUMBERS_REVIEW_DB_URL"

REQUEST_FILE = "run.json"
"""The question, the organism and the search window, as given to `discover`.

Its own file because `records.Discovery` has no organism field and `extract` needs one: the
instruction names the property and the organism (design D7), and asking for the organism again
on the command line would let a run be extracted for a different organism than it was
discovered for, silently.
"""
DISCOVERY_FILE = "discovery.json"
PAPERS_FILE = "papers.jsonl"
ITEMS_FILE = "items.jsonl"
NOT_REVIEWABLE_FILE = "not_reviewable.jsonl"
SUMMARY_FILE = "summary.json"

#: Every file a run directory may hold. The guard below walks this list, so a file added to the
#: command must be added here or it is the one file written unchecked.
RUN_FILES = (
    REQUEST_FILE,
    DISCOVERY_FILE,
    PAPERS_FILE,
    RESULTS_FILE,
    ITEMS_FILE,
    NOT_REVIEWABLE_FILE,
    SUMMARY_FILE,
)

UNLICENSED_PREFIX = "unlicensed: text not kept; "


# --- the two seams ---------------------------------------------------------------------------


def _europepmc(data_dir: Path) -> EuropePMC:
    """The service, over the disk cache under `data_dir`. A test replaces this function."""
    return EuropePMC(http_client(), cache=DocumentCache(data_dir))


def _model(model_id: str) -> Any:
    """The model behind extraction and the second text. A test replaces this function.

    OpenRouter rather than the Anthropic SDK by decision (2026-09-18): the project is not to be
    tied to one provider, and `extraction.AnthropicModel` stays as the alternative, not the
    default. Raises `NoCredential` when no key is in the environment, which the command turns
    into one sentence before any paper is fetched.
    """
    return OpenRouterModel(model=model_id)


def _engine(url: str) -> Any:
    return store.engine_from_url(url)


# --- the guard -------------------------------------------------------------------------------


def _refuse_a_committable_run_dir(directory: Path) -> None:
    """Refuse the whole run directory before any file in it is opened.

    `extraction.write_results` guards its own file, but that guard runs at the end of an
    extraction, after the spend. The command asks the same question of every file it will write,
    up front, so a refused path costs nothing and leaves nothing behind. Through the ingester's
    guard rather than a copy of it, for the reason `extraction` gives: two guards against an
    irreversible mistake is one that gets fixed and one that does not, and no guard means no
    write.
    """
    try:
        from bionumbers_ingest.guard import committable_repo_for
    except ImportError as absent:  # pragma: no cover - both packages are installed here
        raise RunFileWouldBeCommitted(
            f"Cannot check whether {directory} is committable: the guard lives in "
            f"`bionumbers_ingest`, which is not installed. A run file quotes the article, "
            f"so this refuses rather than writing unchecked."
        ) from absent

    for name in RUN_FILES:
        candidate = directory / name
        repo = committable_repo_for(candidate)
        if repo is not None:
            raise RunFileWouldBeCommitted(
                f"git would track {candidate} in {repo}. A run file carries the article's "
                f"text verbatim in every quote, and history is permanent. Write it outside "
                f"the repository, or add its directory to .gitignore."
            )


# --- files ----------------------------------------------------------------------------------


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_lines(path: Path, records: Iterable[Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(record.model_dump_json() + "\n")


def _read_lines(path: Path, record: type) -> list[Any]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return [record.model_validate_json(line) for line in text.splitlines() if line.strip()]


def _run_id(question: str, organism: str) -> str:
    """A slug of the request and the UTC date, so two runs of one question on different days
    are two directories and the same question twice in a day is one, overwritten -- which is
    the re-run case the cache exists for."""
    slug = re.sub(r"[^a-z0-9]+", "-", f"{question} {organism}".lower()).strip("-")[:60]
    return f"{slug}-{datetime.now(UTC):%Y-%m-%d}"


def _status_of(absent: NoFullText) -> str:
    # `unreachable` carries no status at all, and "(HTTP None)" would read as a status.
    if absent.status is None:
        return absent.reason
    return f"{absent.reason} (HTTP {absent.status})"


# --- discover ---------------------------------------------------------------------------------


def discover(args: argparse.Namespace) -> int:
    run_id = args.run_id or _run_id(args.question, args.organism)
    run_dir = Path(args.runs) / run_id
    _refuse_a_committable_run_dir(run_dir)

    provider = _europepmc(Path(args.data))
    sections = tuple(part for part in args.sections.split(",") if part) if args.sections else ()
    terms = f'"{args.question}" AND "{args.organism}"'
    found = provider.search_open_access(
        terms, since_year=args.since, limit=args.limit, sections=sections
    )
    discovery = Discovery(
        run_id=run_id,
        question=args.question,
        query=found.query,
        limit=args.limit,
        more_existed=found.more_existed,
        kept=found.kept,
        excluded=found.excluded,
    )

    papers: list[Paper] = []
    for paper in found.kept:
        fetched = provider.fetch(paper.pmcid)
        if isinstance(fetched, FullText):
            papers.append(
                paper.model_copy(
                    update={"licence": licence_of(None, fetched.xml), "source_url": fetched.url}
                )
            )
        else:
            papers.append(paper.model_copy(update={"full_text_status": _status_of(fetched)}))

    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        run_dir / REQUEST_FILE,
        {
            "question": args.question,
            "organism": args.organism,
            "since_year": args.since,
            "sections": list(sections),
        },
    )
    (run_dir / DISCOVERY_FILE).write_text(discovery.model_dump_json(indent=2) + "\n", "utf-8")
    _write_lines(run_dir / PAPERS_FILE, papers)

    without_text = sum(1 for paper in papers if paper.full_text_status)
    print(f"query: {found.query}")
    print(
        f"kept {len(found.kept)}, excluded {len(found.excluded)}, "
        f"no full text {without_text}" + (", more existed" if found.more_existed else "")
    )
    print(f"run id: {run_id}")
    return 0


# --- harvest ----------------------------------------------------------------------------------

HARVEST_MODE = "harvest"
#: What a harvested run records where a question would be. Shown by `status` and stored on the
#: paper rows; every item carries its own question (`harvest.question_of`).
HARVEST_QUESTION = "harvest: reusable quantitative values"


def harvest_run(args: argparse.Namespace) -> int:
    """A run from a list of articles rather than from a search: `extract` then reads each
    one in harvest mode. Discovery's other half -- fetch, licence, the typed absence -- is the
    same, because the same facts about access and terms are needed whoever chose the paper."""
    run_dir = Path(args.runs) / args.run_id
    _refuse_a_committable_run_dir(run_dir)
    pmcids = [part.strip() for part in args.pmcids.split(",") if part.strip()]
    if args.pmcid_file:
        lines = Path(args.pmcid_file).read_text(encoding="utf-8").splitlines()
        pmcids += [line.split()[0] for line in lines if line.strip() and line[0] != "#"]
    if not pmcids:
        print("Give --pmcids or --pmcid-file with at least one PMCID.", file=sys.stderr)
        return 2

    provider = _europepmc(Path(args.data))
    papers: list[Paper] = []
    for pmcid in dict.fromkeys(pmcids):
        fetched = provider.fetch(pmcid)
        if not isinstance(fetched, FullText):
            papers.append(Paper(pmcid=pmcid, full_text_status=_status_of(fetched)))
            continue
        try:
            doc = read_jats(fetched.xml)
        except JatsUnreadable as why:
            papers.append(Paper(pmcid=pmcid, full_text_status=f"not a JATS article: {why}"))
            continue
        papers.append(
            Paper(
                pmcid=pmcid,
                pmid=doc.pmid,
                doi=doc.doi,
                title=doc.title,
                year=doc.year,
                licence=licence_of(provider.index_record(pmcid), fetched.xml),
                source_url=fetched.url,
            )
        )

    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        run_dir / REQUEST_FILE,
        {"mode": HARVEST_MODE, "question": HARVEST_QUESTION, "organism": "", "scope": args.scope},
    )
    _write_lines(run_dir / PAPERS_FILE, papers)
    without_text = sum(1 for paper in papers if paper.full_text_status)
    unlicensed = sum(1 for p in papers if not p.full_text_status and p.licence == UNLICENSED)
    print(f"{len(papers)} paper(s), no full text {without_text}, unlicensed {unlicensed}")
    print(f"run id: {args.run_id}")
    return 0


# --- extract ----------------------------------------------------------------------------------


class _RunLedger(Ledger):
    """The ledger, remembering whether the run bound was the one that refused.

    Both `extract` and `choose_second_text` swallow `CeilingReached` and report an ending --
    rightly, since a paper's stop is one record among many -- but in doing so they drop its
    scope, and the run's stop is the one ending that has to end the loop. Recording it at the
    refusal itself is the one place both callers pass through.
    """

    def __init__(self, ceiling: Ceiling) -> None:
        super().__init__(ceiling)
        self.run_exhausted = False

    def check(self, article_id: str, projected_usd: float) -> None:
        try:
            super().check(article_id, projected_usd)
        except CeilingReached as reached:
            if reached.scope == "run":
                self.run_exhausted = True
            raise


def _unreadable(paper: Paper, reason: str, fingerprint: Fingerprint) -> PaperResult:
    return PaperResult(
        paper=paper, state=PaperState.UNREADABLE, reason=reason, fingerprint=fingerprint
    )


def _one_paper(
    paper: Paper,
    *,
    provider: EuropePMC,
    model: Any,
    model_id: str,
    question: str,
    organism: str,
    run_id: str,
    ledger: Ledger,
    harvesting: bool = False,
    scope: str = "",
) -> tuple[PaperResult, list[ReviewItem], list[NotReviewable]]:
    instruction = harvest.HARVEST_INSTRUCTION if harvesting else INSTRUCTION
    fingerprint = Fingerprint(
        model=model_id,
        instruction_sha256=instruction_sha256(instruction),
        article_id=paper.pmcid,
        run_id=run_id,
        scope=scope,
    )
    # Through the cached provider rather than the cache alone: a paper discovery found no XML
    # for is asked about once more, because the service has served XML later for articles it
    # first answered 500 on. A hit costs no request; a miss records the typed absence.
    fetched = provider.fetch(paper.pmcid)
    if isinstance(fetched, NoFullText):
        return (
            _unreadable(paper, paper.full_text_status or _status_of(fetched), fingerprint),
            [],
            [],
        )
    try:
        doc = read_jats(fetched.xml)
    except JatsUnreadable as why:
        return _unreadable(paper, f"not a JATS article: {why}", fingerprint), [], []

    result = extract(
        model,
        doc,
        paper,
        question="" if harvesting else question,
        organism=organism,
        run_id=run_id,
        ledger=ledger,
        model_id=model_id,
        instruction=instruction,
        user=harvest.user_turn(scope) if harvesting else None,
        max_tokens=harvest.MAX_TOKENS if harvesting else MAX_TOKENS,
        scope=scope,
    )
    if paper.licence == UNLICENSED:
        # Extraction ran and its spend stands, but nothing quoted leaves the cache: the spec's
        # "no text from it is written to the record". The state is kept so the run can say the
        # paper was read; the reason says why it looks empty.
        stripped = result.model_copy(
            update={"claims": (), "rejected": (), "reason": UNLICENSED_PREFIX + result.reason}
        )
        return stripped, [], []

    items: list[ReviewItem] = []
    not_reviewable: list[NotReviewable] = []
    for claim in result.claims:
        try:
            chosen = choose_second_text(
                model,
                doc,
                claim,
                paper,
                # A harvested claim answers no question, so it is judged against its own name.
                question=harvest.question_of(claim) if harvesting else question,
                ledger=ledger,
                model_id=model_id,
            )
        except ProviderRefused:
            raise
        except Exception as failure:
            # `extract` takes the same decision for the same reason: a run is tens of papers, and
            # one timeout on a second-text call must cost one claim its item, not the run its
            # results -- which are in memory until the loop ends.
            chosen = NotReviewable(
                claim_id=claim.claim_id, reason=f"{type(failure).__name__}: {failure}"
            )
        if isinstance(chosen, ReviewItem):
            items.append(chosen)
        else:
            not_reviewable.append(chosen)
    # `extract` snapshots the paper's spend at its own ending, before the second-text calls have
    # been made; the record has to carry what the paper cost in all, or `status` under-reports
    # every paper with claims by exactly the calls the reviewer's items cost.
    result = result.model_copy(update={"spend": ledger.paper(paper.pmcid)})
    return result, items, not_reviewable


def extract_run(args: argparse.Namespace) -> int:
    run_dir = Path(args.runs) / args.run_id
    _refuse_a_committable_run_dir(run_dir)
    try:
        model = _model(args.model)
    except NoCredential:
        print(f"Set {API_KEY_ENV} in the environment before running extract.", file=sys.stderr)
        return 2
    if args.model not in PRICES:
        # The ledger would refuse the projection paper by paper, ending every one FAILED and
        # overwriting the run's results with a column of failures (code review of 2026-09-21,
        # finding 9). One sentence here, before any paper is fetched.
        known = ", ".join(sorted(PRICES))
        print(f"No prices are configured for {args.model!r}; known: {known}.", file=sys.stderr)
        return 2

    request = json.loads((run_dir / REQUEST_FILE).read_text(encoding="utf-8"))
    papers = _read_lines(run_dir / PAPERS_FILE, Paper)
    provider = _europepmc(Path(args.data))
    ledger = _RunLedger(Ceiling(per_paper=args.ceiling, per_run=args.budget))

    results: list[PaperResult] = []
    items: list[ReviewItem] = []
    not_reviewable: list[NotReviewable] = []
    unlicensed = 0
    papers_left_unread = 0
    stopped = ""
    harvesting = request.get("mode") == HARVEST_MODE
    # A harvested run from before scopes existed was asked in what is now `biology`.
    scope = request.get("scope", harvest.DEFAULT_SCOPE) if harvesting else ""
    for index, paper in enumerate(papers):
        if ledger.run_exhausted:
            papers_left_unread = len(papers) - index
            break
        try:
            result, paper_items, paper_not_reviewable = _one_paper(
                paper,
                provider=provider,
                model=model,
                model_id=args.model,
                question=request["question"],
                organism=request["organism"],
                run_id=args.run_id,
                ledger=ledger,
                harvesting=harvesting,
                scope=scope,
            )
        except ProviderRefused as refused:
            # The account, not the paper: this paper ends FAILED with the provider's words, the
            # rest are left unread rather than failed one by one, and the command says so.
            stopped = str(refused)
            results.append(
                PaperResult(
                    paper=paper,
                    state=PaperState.FAILED,
                    reason=stopped,
                    spend=ledger.paper(paper.pmcid),
                    fingerprint=Fingerprint(
                        model=args.model,
                        instruction_sha256=instruction_sha256(),
                        article_id=paper.pmcid,
                        run_id=args.run_id,
                        scope=scope,
                    ),
                )
            )
            papers_left_unread = len(papers) - index - 1
            break
        results.append(result)
        items.extend(paper_items)
        not_reviewable.extend(paper_not_reviewable)
        if paper.licence == UNLICENSED and result.state != PaperState.UNREADABLE:
            unlicensed += 1

    write_results(results, run_dir)
    _write_lines(run_dir / ITEMS_FILE, items)
    _write_lines(run_dir / NOT_REVIEWABLE_FILE, not_reviewable)
    summary = {
        "run_id": args.run_id,
        "model": args.model,
        "states": dict(sorted(Counter(result.state.value for result in results).items())),
        "spend_usd": ledger.run.usd,
        "cached_fraction": ledger.cached_fraction(),
        "papers": len(papers),
        "papers_left_unread": papers_left_unread,
        "items": len(items),
        "not_reviewable": len(not_reviewable),
        "unlicensed": unlicensed,
        "stopped": stopped,
    }
    _write_json(run_dir / SUMMARY_FILE, summary)
    print(json.dumps(summary, indent=2))
    if stopped:
        print(f"Stopped: {stopped}. Re-run extract once the account is in order.", file=sys.stderr)
        return 3
    return 0


# --- load and status --------------------------------------------------------------------------


def load(args: argparse.Namespace) -> int:
    url = args.db_url or os.environ.get(DB_URL_ENV, "")
    if not url:
        print(f"Give --db-url or set {DB_URL_ENV} to the review database.", file=sys.stderr)
        return 2
    run_dir = Path(args.runs) / args.run_id
    request = json.loads((run_dir / REQUEST_FILE).read_text(encoding="utf-8"))
    results = read_results(run_dir / RESULTS_FILE)
    items = _read_lines(run_dir / ITEMS_FILE, ReviewItem)
    inserted = store.load_run(
        _engine(url), results, items, question=request["question"], run_id=args.run_id
    )
    print(f"{inserted} item(s) loaded from run {args.run_id}")
    return 0


#: The ask app's name for the corpus path, read here too so one export serves both.
CORPUS_ENV = "SCINUMBERS_CORPUS"


def curate(args: argparse.Namespace) -> int:
    """Load the curated tier: BioNumbers' entries in the slice that nothing marks doubtful."""
    url = args.db_url or os.environ.get(DB_URL_ENV, "")
    corpus = args.corpus or os.environ.get(CORPUS_ENV, "")
    if not url or not corpus:
        print(f"Give --db-url (or {DB_URL_ENV}) and --corpus (or {CORPUS_ENV}).", file=sys.stderr)
        return 2
    kept, refused = curated.select(curated.read_corpus(corpus))
    loaded = store.load_curated(_engine(url), kept)
    in_slice = loaded + sum(n for r, n in refused.items() if r != curated.Refusal.OUT_OF_SCOPE)
    print(f"{loaded} curated entr{'y' if loaded == 1 else 'ies'} of {in_slice} in the slice")
    for reason, count in refused.most_common():
        if reason != curated.Refusal.OUT_OF_SCOPE:
            print(f"  {count:>4} left out: {reason.value}")
    return 0


def status(args: argparse.Namespace) -> int:
    run_dir = Path(args.runs) / args.run_id
    results = read_results(run_dir / RESULTS_FILE)
    items = _read_lines(run_dir / ITEMS_FILE, ReviewItem)

    states = Counter(result.state.value for result in results)
    print("states: " + ", ".join(f"{state} {count}" for state, count in sorted(states.items())))
    total = Spend()
    for result in results:
        total = total.plus(result.spend)
        print(
            f"{result.paper.pmcid:<14} {result.state.value:<24} "
            f"${result.spend.usd:.4f} ({result.spend.calls} call(s))"
        )
    seen = total.input_tokens + total.cache_write_tokens + total.cache_read_tokens
    cached = total.cache_read_tokens / seen if seen else 0.0
    print(
        f"total: ${total.usd:.4f} over {len(results)} paper(s); "
        f"cached fraction {cached:.2f}; {len(items)} item(s)"
    )
    return 0


# --- the parser -------------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bionumbers", description="From a property question to reviewed numbers."
    )
    commands = parser.add_subparsers(dest="command_name", required=True)

    def run_dirs(command: argparse.ArgumentParser) -> None:
        command.add_argument(
            "--runs", default=str(paths.RUNS_DIR), help="where run directories are written"
        )

    def data_dir(command: argparse.ArgumentParser) -> None:
        command.add_argument(
            "--data", default=str(paths.EUROPEPMC_DIR), help="the Europe PMC disk cache"
        )

    discover_cmd = commands.add_parser("discover", help="find open-access papers for a question")
    discover_cmd.add_argument("question", help='the property, e.g. "doubling time"')
    discover_cmd.add_argument("--organism", required=True)
    discover_cmd.add_argument("--since", type=int, default=2005, help="earliest publication year")
    discover_cmd.add_argument("--limit", type=int, default=50, help="candidates kept, at most")
    discover_cmd.add_argument(
        "--sections", default="", help="comma-separated JATS sections to search, e.g. RESULTS,TABLE"
    )
    discover_cmd.add_argument("--run-id", default=None)
    data_dir(discover_cmd)
    run_dirs(discover_cmd)
    discover_cmd.set_defaults(command=discover)

    harvest_cmd = commands.add_parser(
        "harvest", help="start a run from a list of PMCIDs, to be extracted without a question"
    )
    harvest_cmd.add_argument("run_id")
    harvest_cmd.add_argument("--pmcids", default="", help="comma-separated PMCIDs")
    harvest_cmd.add_argument("--pmcid-file", default=None, help="one PMCID per line; # comments")
    harvest_cmd.add_argument(
        "--scope",
        choices=sorted(harvest.SCOPES),
        default=harvest.DEFAULT_SCOPE,
        help="the domain whose classes of value are wanted",
    )
    data_dir(harvest_cmd)
    run_dirs(harvest_cmd)
    harvest_cmd.set_defaults(command=harvest_run)

    extract_cmd = commands.add_parser("extract", help="extract claims from a discovered run")
    extract_cmd.add_argument("run_id")
    extract_cmd.add_argument(
        "--ceiling", type=float, default=Ceiling().per_paper, help="USD per paper"
    )
    extract_cmd.add_argument("--budget", type=float, default=Ceiling().per_run, help="USD per run")
    extract_cmd.add_argument("--model", default=DEFAULT_MODEL, help="the OpenRouter model id")
    data_dir(extract_cmd)
    run_dirs(extract_cmd)
    extract_cmd.set_defaults(command=extract_run)

    load_cmd = commands.add_parser("load", help="load a run's results and items into the store")
    load_cmd.add_argument("run_id")
    load_cmd.add_argument("--db-url", default=None, help=f"else {DB_URL_ENV}")
    run_dirs(load_cmd)
    load_cmd.set_defaults(command=load)

    curate_cmd = commands.add_parser(
        "curate", help="load BioNumbers' undoubted entries in the slice as the curated tier"
    )
    curate_cmd.add_argument("--corpus", default=None, help=f"the corpus JSONL, else {CORPUS_ENV}")
    curate_cmd.add_argument("--db-url", default=None, help=f"else {DB_URL_ENV}")
    curate_cmd.set_defaults(command=curate)

    status_cmd = commands.add_parser("status", help="states, spend and items of a run, from disk")
    status_cmd.add_argument("run_id")
    run_dirs(status_cmd)
    status_cmd.set_defaults(command=status)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.command(args)
    except RunFileWouldBeCommitted as refused:
        print(str(refused), file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
