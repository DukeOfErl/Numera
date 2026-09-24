"""The evaluation driver: ask, record, resume.

A third adapter over the agent, alongside `cli` and `web`. It consumes the same
events they render and writes them down instead. Nothing here is a mode inside the
agent: it is given an `AskAgent` and drives it through the port.

**One session per question, follow-ups in their parent's.** A follow-up is only
measurable as a follow-up if it can see what came before, so a chain of questions
shares one session and the session is named for the chain's root. Every other
question gets a session of its own, which is what makes a question's recorded
context exactly the context that question produced.

**Append as each question completes, never at the end.** A run costs money and can
be interrupted -- by a budget, a provider, a person -- and a results file written
at the end would lose everything up to the interruption. So each result is a line,
flushed when it is written, and the file is readable at any moment.

**Provenance per result, not per run.** A resumed run may cross a corpus rebuild, a
prompt edit or a code change, and a header record would describe only the moment
the run started. Recording it per result is what lets a report refuse to combine
figures that are not comparable, rather than averaging them silently.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from . import messages
from .agent import SYSTEM_PROMPT, AskAgent
from .config import Config
from .events import (
    Answer,
    AnswerEntries,
    CitationWarning,
    EndReason,
    QuestionEnded,
    Retrieval,
    UngroundedRefusal,
)
from .question_set import Question

# 16 hex characters of SHA-256. A fingerprint here answers one question -- "is this
# the same prompt, the same corpus?" -- so 64 bits is ample, and a full digest on
# every record would crowd out the fields a person actually reads.
DIGEST_LENGTH = 16


def digest_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:DIGEST_LENGTH]


def digest_of_file(path: str | Path) -> str:
    """A corpus is tens of megabytes, so it is read in blocks rather than at once."""
    hashed = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            hashed.update(block)
    return hashed.hexdigest()[:DIGEST_LENGTH]


def code_version() -> str:
    """The code that produced a result, saying which kind of answer this is.

    A git commit in a checkout, the installed version in a wheel, and the string
    says which -- "git 4ccd5b2" and "package 0.1.0" are different claims and a
    reader comparing two runs needs to know which they have.

    A checkout with uncommitted changes is marked, because a commit alone would
    claim provenance the tree does not have: the most likely time to record a
    baseline is while the change that prompted it is still unstaged.
    """
    root = Path(__file__).resolve().parents[2]
    if (root / ".git").exists():
        commit = _git(root, "rev-parse", "--short", "HEAD")
        if commit:
            # `--untracked-files=no`, because untracked files are not a change to
            # the code. Without it, any stray untracked path -- the results
            # directory itself, among others -- marks every run `+modified`, and
            # the report then splits identical code into groups it refuses to
            # combine, saying they are different systems.
            modified = _git(root, "status", "--porcelain", "--untracked-files=no")
            return f"git {commit}+modified" if modified else f"git {commit}"
    try:
        return f"package {version('bionumbers')}"
    except PackageNotFoundError:
        return "unknown"


def _git(root: Path, *arguments: str) -> str:
    try:
        finished = subprocess.run(
            ["git", "-C", str(root), *arguments],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return finished.stdout.strip() if finished.returncode == 0 else ""


@dataclass(frozen=True)
class Provenance:
    """What produced a result, from what the run can see rather than declared.

    A date is a proxy for the three things that actually move the figures -- the
    corpus, the prompt and the code -- so all three are recorded beside it. The
    model settings are the ones that shape an answer; reasoning effort joins them
    as soon as `Config` carries it, and the record's shape does not have to change
    for that.
    """

    recorded_at: str
    model: str
    question_ceiling: int
    run_budget: int
    run_label: str
    prompt_digest: str
    corpus_digest: str
    corpus_entries: int
    code_version: str


def provenance_for(config: Config, corpus_path: str | Path, corpus_entries: int) -> Provenance:
    """Computed once per run: the digests do not change under a running process."""
    return Provenance(
        recorded_at=datetime.now(UTC).isoformat(timespec="seconds"),
        model=config.model,
        question_ceiling=config.question_ceiling,
        run_budget=config.run_budget,
        run_label=config.run_label,
        prompt_digest=digest_of(SYSTEM_PROMPT),
        corpus_digest=digest_of_file(corpus_path),
        corpus_entries=corpus_entries,
        code_version=code_version(),
    )


@dataclass(frozen=True)
class Result:
    """One question, one repeat: the raw material and nothing derived from it.

    No score is stored. Every figure in the report is computed from these fields,
    so a scoring rule can change without re-asking a single question -- which is
    the difference between a rule being cheap to fix and being unaffordable.
    """

    question_id: str
    repeat: int
    question: str
    answer: str
    expected_entries: tuple[int, ...] = ()
    cited: tuple[int, ...] = ()
    retrieved: tuple[int, ...] = ()
    matched: int = 0
    searches: int = 0
    # Every retrieval's tool and arguments, in order. Recorded because scoring
    # whether the agent searched for the asked organism reads exactly these, and a
    # record without them would mean re-asking every question to score it.
    retrievals: tuple[dict[str, Any], ...] = ()
    # What the agent was shown, verbatim, from the session's own transcript.
    # `None` and `()` are different statements and the spec requires them to be
    # told apart: `()` is a question that retrieved nothing, which is the normal
    # shape of a correct refusal, and `None` is a context that could not be read.
    # Collapsing them would make an unrecorded context look like proof that the
    # agent searched for nothing.
    context: tuple[str, ...] | None = None
    # The agent's own grounding warnings, counted rather than judged.
    unknown_citations: tuple[int, ...] = ()
    unretrieved_citations: tuple[int, ...] = ()
    ungrounded_refusal: bool = False
    claimed_searching: bool = False
    end_reason: str = ""
    incomplete: bool = False
    spend: int = 0
    run_spend: int = 0
    spend_ceiling: int = 0
    run_budget: int = 0
    model: str = ""
    model_calls: int = 0
    call_limit: int = 0
    tool_calls: int = 0
    tool_call_limit: int = 0
    session_id: str = ""
    # A question that raised rather than ending. Empty for every ordinary result,
    # including one that ended on a limit -- those are outcomes, not failures.
    failure: str = ""
    provenance: Provenance | None = None

    @property
    def key(self) -> tuple[str, int]:
        return (self.question_id, self.repeat)


def append_result(path: str | Path, result: Result) -> None:
    """One line, opened and closed per result.

    Deliberately not a held-open handle: an interrupted run must leave a file that
    is complete up to its last whole line, and a buffered writer loses whatever it
    was holding.
    """
    file = Path(path)
    if not file.exists():
        # Checked as the file comes into existence: that is the moment the path
        # becomes real, it costs two git calls once rather than per record, and it
        # catches a caller that reaches this function directly.
        refuse_a_committable_results_path(file)
    if file.parent != Path(""):
        file.parent.mkdir(parents=True, exist_ok=True)
    _drop_a_torn_last_line(file)
    with file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")


def _drop_a_torn_last_line(file: Path) -> None:
    """Remove a final line with no newline before appending after it.

    The failure this exists for, and it is the one the append-per-result shape was
    supposed to survive. A run killed mid-write leaves a partial record with no
    trailing newline. `read_results` tolerates that, so a resume proceeds -- and
    then the next append concatenates its JSON onto the partial line. The fused
    line is still *last*, so the newly paid-for result is silently dropped on the
    next read; one more append pushes it into the middle, and from then on every
    read raises, blaming damage after the fact for a whole run's results.

    The torn record was already unreadable, so truncating it loses nothing that
    could have been reported, and it is what keeps the file appendable.
    """
    if not file.is_file() or file.stat().st_size == 0:
        return
    with file.open("rb+") as handle:
        handle.seek(-1, 2)
        if handle.read(1) == b"\n":
            return
        handle.seek(0)
        content = handle.read()
        keep = content.rfind(b"\n") + 1
        handle.seek(keep)
        handle.truncate()


class ResultsFileError(Exception):
    """A results file that cannot be read back, and why."""


class ResultsWouldBeCommitted(Exception):
    """The results path is one git would track, and results carry corpus text.

    Its own type, so a caller can tell this from a file it merely cannot parse.
    """


def refuse_a_committable_results_path(path: str | Path) -> None:
    """Refuse to write results where git would track them.

    **Every record carries the retrieval results verbatim** -- that is what the
    spec requires of the recorded context -- so a results file holds corpus text,
    and the corpus is an external input with unresolved licensing that must never
    enter a repository (ADR-0170). The three checkouts here share one origin, so a
    leak from any of them publishes, and git history is permanent.

    A `.gitignore` entry protects only the repositories someone remembered to
    edit; asking git whether it would track the file asks the authority instead.
    That reasoning and this code are the ingester's (ADR-0250), reused rather than
    reimplemented: two copies of a guard against an irreversible mistake is one
    copy that will be fixed and one that will not.

    **No guard available means no write.** If the ingester is absent -- it lives in
    a sibling package that a branch may not have -- this refuses rather than
    proceeding unchecked, because the cheap direction for an irreversible mistake
    is to stop.
    """
    try:
        from bionumbers_ingest.guard import committable_repo_for
    except ImportError as exc:  # pragma: no cover - both packages are present here
        raise ResultsWouldBeCommitted(
            f"Cannot check whether {path} is committable: the guard lives in "
            f"`bionumbers_ingest`, which is not installed. Results carry corpus "
            f"text verbatim, so this refuses rather than writing unchecked."
        ) from exc
    repo = committable_repo_for(Path(path))
    if repo is not None:
        raise ResultsWouldBeCommitted(
            f"git would track {path} in {repo}. Every result carries the retrieval "
            f"results the agent was shown, verbatim, so a results file holds corpus "
            f"text -- which must never enter a repository (ADR-0170), and history is "
            f"permanent. Write it outside the repository, or add its directory to "
            f".gitignore."
        )


def read_results(path: str | Path) -> tuple[Result, ...]:
    """Every result recorded so far. A missing file is an empty run, not an error.

    A torn last line is tolerated and anything else is not. A run killed while
    writing leaves a partial final line, which is an interruption and the normal
    case this file exists to survive; a broken line anywhere earlier means the
    file was damaged after it was written, and reading past that would silently
    drop results the report would then be missing.
    """
    file = Path(path)
    if not file.is_file():
        return ()
    lines = [line for line in file.read_text(encoding="utf-8").splitlines() if line.strip()]
    results = []
    for number, line in enumerate(lines, start=1):
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            if number == len(lines):
                break
            raise ResultsFileError(
                f"{file}:{number} is not valid JSON: {exc}. A partial line is only "
                f"expected as the last line of an interrupted run; earlier means the "
                f"file was damaged, and reading on would drop results silently."
            ) from exc
        results.append(_result_from(raw, f"{file}:{number}"))
    return _current(results)


def _current(results: list[Result]) -> tuple[Result, ...]:
    """The last record for each question and repeat, in the order first written.

    Appending is the only write, so re-asking a question leaves the earlier record
    in place -- and `outstanding` re-asks deliberately, when a follow-up's parent
    is missing and its recorded answer belongs to a session that no longer exists.
    Returning both would have every figure count the superseded answer, and would
    show the question as unstable across "repeats" it never had, from a record the
    driver had just declared invalid.
    """
    latest: dict[tuple[str, int], Result] = {}
    for result in results:
        latest[result.key] = result
    return tuple(latest.values())


def _result_from(raw: dict[str, Any], where: str) -> Result:
    known = {f.name for f in Result.__dataclass_fields__.values()}
    unknown = sorted(set(raw) - known)
    if unknown:
        raise ResultsFileError(
            f"{where} carries {unknown}, which this reader does not know. The file "
            f"was written by a different version; report from that version or "
            f"re-run rather than reading it as if the fields matched."
        )
    provenance = raw.get("provenance")
    if provenance is not None:
        # Guarded like the record's own fields. `Provenance` is documented as
        # gaining reasoning effort as soon as `Config` carries it, so a file from a
        # later version is expected -- and `Provenance(**provenance)` unguarded
        # raised `TypeError`, which the command does not catch, so a report gave a
        # traceback instead of "written by a different version".
        unknown_provenance = sorted(set(provenance) - set(Provenance.__dataclass_fields__))
        if unknown_provenance:
            raise ResultsFileError(
                f"{where}: the provenance carries {unknown_provenance}, which this "
                f"reader does not know. The file was written by a different version; "
                f"report from that version or re-run."
            )
    fields = dict(raw)
    for name in ("expected_entries", "cited", "retrieved", "context"):
        if name in fields and fields[name] is not None:
            fields[name] = tuple(fields[name])
    for name in ("unknown_citations", "unretrieved_citations"):
        if name in fields and fields[name] is not None:
            fields[name] = tuple(fields[name])
    if "retrievals" in fields and fields["retrievals"] is not None:
        fields["retrievals"] = tuple(fields["retrievals"])
    fields["provenance"] = Provenance(**provenance) if provenance else None
    return Result(**fields)


def session_for(root_id: str, repeat: int) -> str:
    """One session per chain per repeat, named for the chain's root.

    Named rather than random so a resumed run reaches the same session, and so a
    person reading the checkpoint database can find the question a session belongs
    to.
    """
    return f"{root_id}-r{repeat}"


def _root_of(question: Question, by_id: dict[str, Question]) -> str:
    root = question
    while root.follows is not None:
        root = by_id[root.follows]
    return root.question_id


def in_order(questions: tuple[Question, ...]) -> tuple[Question, ...]:
    """Parents before children, whatever order the file used.

    The format permits any order, so a driver that trusted the file would ask a
    follow-up before the question it follows and measure it against a session that
    did not exist yet. The set is already known to be free of cycles and of
    dangling parents, so this terminates.
    """
    by_id = {question.question_id: question for question in questions}
    placed: dict[str, Question] = {}

    def place(question: Question) -> None:
        if question.question_id in placed:
            return
        if question.follows is not None:
            place(by_id[question.follows])
        placed[question.question_id] = question

    for question in questions:
        place(question)
    return tuple(placed.values())


def outstanding(
    questions: tuple[Question, ...], recorded: tuple[Result, ...], repeats: int
) -> tuple[tuple[Question, int], ...]:
    """What a resumed run still has to ask, in the order it must ask it.

    A follow-up whose parent has no result counts as missing itself, even when its
    own result is present: the parent will be asked again in a new session, so the
    recorded follow-up answer belongs to a session that no longer exists and would
    be scored against context it never had.
    """
    done = {result.key for result in recorded}
    ordered = in_order(questions)
    attempt: list[tuple[Question, int]] = []
    for repeat in range(1, repeats + 1):
        missing: set[str] = set()
        for question in ordered:
            parent_missing = question.follows is not None and question.follows in missing
            if (question.question_id, repeat) not in done or parent_missing:
                missing.add(question.question_id)
                attempt.append((question, repeat))
    return tuple(attempt)


def still_to_ask(questions: tuple[Question, ...], results_path: str | Path, repeats: int) -> int:
    """How many questions a run will actually ask, after what it resumes past.

    The same rule `run_evaluation` skips by, read the same way, so an estimate made
    before a run and the run itself cannot disagree about what is outstanding.
    """
    return len(outstanding(questions, read_results(results_path), repeats))


@dataclass
class Outcome:
    """What a run did, for the caller to report. Not a score."""

    attempted: int = 0
    recorded: int = 0
    failed: int = 0
    #: Which ending closed the run, or None if it ran to the end. A reason rather
    #: than the boolean `stopped_on_run_budget` this replaces: that name was the
    #: only closing ending there was when it was written, and the caller has to say
    #: *which* limit was reached. Raising the run budget does nothing for a key with
    #: no credit left.
    stopped_on: EndReason | None = None
    questions_skipped: int = 0
    skipped: tuple[str, ...] = field(default_factory=tuple)


def run_evaluation(
    agent: AskAgent,
    questions: tuple[Question, ...],
    results_path: str | Path,
    provenance: Provenance,
    *,
    repeats: int = 1,
    announce: Any = None,
) -> Outcome:
    """Ask every outstanding question, recording each result as it completes.

    The run stops when a question ends on the run budget: the budget bounds the
    run, not the question, so every question after it would end the same way and
    cost a model call each to say so.
    """
    if repeats < 1:
        raise ValueError("a run has at least one repeat")
    by_id = {question.question_id: question for question in questions}
    recorded = read_results(results_path)
    todo = outstanding(questions, recorded, repeats)
    outcome = Outcome()
    stopped_at: int | None = None

    for position, (question, repeat) in enumerate(todo):
        if stopped_at is not None:
            outcome.questions_skipped += 1
            outcome.skipped = outcome.skipped + (question.question_id,)
            continue
        session = session_for(_root_of(question, by_id), repeat)
        if announce:
            announce(f"[{position + 1}/{len(todo)}] {question.question_id} (repeat {repeat})")
        outcome.attempted += 1
        result = _ask_one(agent, question, repeat, session, provenance)
        append_result(results_path, result)
        outcome.recorded += 1
        if result.failure:
            outcome.failed += 1
        # Every ending after which asking again cannot come out differently, not the
        # run budget alone. `STOP_THE_RUN` is the set both interactive drivers already
        # stop on, and it is shared for exactly this reason: a third adapter deciding
        # for itself which endings are final is how they come to disagree. Left as
        # `RUN_BUDGET` only, a key that ran out of credit part-way would leave the
        # harness asking every remaining question, recording the agent's "no credit
        # left" notice as each answer and scoring each as an ungrounded non-answer --
        # a results file that reads as the model failing rather than a run that
        # stopped.
        if result.end_reason in messages.STOP_THE_RUN:
            # Back to the enum: a `Result` holds the reason as a string, because a
            # record has to be readable without this package. `Outcome` is in-memory
            # and its caller compares against members, so the string stops here.
            outcome.stopped_on = EndReason(result.end_reason)
            stopped_at = position
    return outcome


def _ask_one(
    agent: AskAgent, question: Question, repeat: int, session: str, provenance: Provenance
) -> Result:
    """One question, driven through the port, with everything it emitted kept.

    A question that raises is recorded as a failure and the run continues. An
    evaluation exists to measure a system that sometimes breaks, and a run that
    died on the first exception would measure nothing at all -- while a failure
    that vanished from the record would be indistinguishable from a question never
    asked.
    """
    result = Result(
        question_id=question.question_id,
        repeat=repeat,
        question=question.question,
        answer="",
        expected_entries=question.expected_entries,
        session_id=session,
        provenance=provenance,
    )
    try:
        for event in agent.ask(session, question.question):
            result = _record(result, event)
    except Exception as exc:  # noqa: BLE001 - the failure is the datum
        result = replace(result, failure=f"{type(exc).__name__}: {exc}")
    # Read after the question, from the session's own transcript, so it is what the
    # agent was shown rather than a re-rendering of it. Left as `None` if it cannot
    # be read, which is not the same as an empty one.
    try:
        result = replace(result, context=agent.tool_results(session))
    except Exception as exc:  # noqa: BLE001
        result = replace(result, failure=(result.failure + f" | context unread: {exc}").strip(" |"))
    return result


def _record(result: Result, event: Any) -> Result:
    """One event folded into the result. Every field here is the agent's own."""
    if isinstance(event, Retrieval):
        return replace(
            result, retrievals=result.retrievals + ({"tool": event.tool, **event.detail},)
        )
    if isinstance(event, AnswerEntries):
        return replace(
            result,
            cited=event.cited,
            retrieved=event.retrieved,
            matched=event.matched,
            searches=event.searches,
        )
    if isinstance(event, Answer):
        return replace(result, answer=event.text)
    if isinstance(event, CitationWarning):
        return replace(
            result, unknown_citations=event.unknown, unretrieved_citations=event.unretrieved
        )
    if isinstance(event, UngroundedRefusal):
        return replace(result, ungrounded_refusal=True, claimed_searching=event.claimed_searching)
    if isinstance(event, QuestionEnded):
        return replace(
            result,
            end_reason=str(event.reason),
            incomplete=event.incomplete,
            spend=event.spend,
            run_spend=event.run_spend,
            spend_ceiling=event.spend_ceiling,
            run_budget=event.run_budget,
            model=event.model,
            model_calls=event.model_calls,
            call_limit=event.call_limit,
            tool_calls=event.tool_calls,
            tool_call_limit=event.tool_call_limit,
        )
    return result
