"""The evaluation's other report: every answer, and the entries that bear on it.

`report.py` gives the figures. This gives the material a person reads to decide
whether the figures mean anything -- which is what task 5.4 asks for by hand, and
what a reviewer needs when the question being asked is whether the *set* measures
the right thing (5.6). Neither is answerable from an aggregate.

**The recorded context is deliberately absent.** Three quarters of a results file
is the verbatim text the agent was shown, and it is there so a changed scoring
rule or a judge can be run again without re-asking a paid question -- not for a
reader. Reproducing it here would bury the answer it exists to support.

**It still holds corpus text**, through the entries it tabulates, so the output
path goes through the same refusal the results file does. Every later artefact of
a run carries that risk; the guard belongs to each of them, not to the command.

The table's ordering is `entries_table.rows_for`, called rather than re-derived,
so what this shows as rank is the rank a reader would actually have seen.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

from .citations import DELIMITED
from .corpus import Entry
from .entries_table import rows_for
from .evaluation import Result, refuse_a_committable_results_path
from .question_set import Question
from .repository import CorpusRepository
from .scoring import citation_score


class SheetUnavailable(Exception):
    """A PDF was asked for and the renderer that makes one is not installed."""


def write_answer_sheet(
    path: str | Path,
    results: tuple[Result, ...],
    questions: tuple[Question, ...],
    entries: tuple[Entry, ...],
) -> None:
    """Write the sheet as HTML, or as PDF when the path says `.pdf`.

    PDF needs `weasyprint`, which the `eval` extra installs but which also needs
    system libraries that a given machine may not have. So the import is made here
    rather than at module load: HTML is always available, and a missing renderer
    costs a sentence instead of making the whole module unimportable.
    """
    target = Path(path)
    refuse_a_committable_results_path(target)
    document = render_html(results, questions, entries)
    if target.suffix.lower() != ".pdf":
        target.write_text(document, encoding="utf-8")
        return
    try:
        from weasyprint import HTML
    except ImportError as exc:
        raise SheetUnavailable(
            f"Writing {target} as PDF needs weasyprint, which is not installed or "
            f"cannot load its system libraries. Ask for an .html path instead, and "
            f"print it from a browser if a PDF is wanted."
        ) from exc
    HTML(string=document).write_pdf(target)


def render_html(
    results: tuple[Result, ...],
    questions: tuple[Question, ...],
    entries: tuple[Entry, ...],
) -> str:
    by_id = {int(entry.entry_id): entry for entry in entries}
    repo = CorpusRepository(entries)
    asked = {question.question_id: question for question in questions}
    sections = [_section(result, asked, by_id, repo) for result in results]
    return _PAGE.format(
        style=_STYLE,
        count=len(results),
        front=_front_matter(results[0]) if results else "",
        sections="".join(sections),
    )


def _section(
    result: Result,
    asked: dict[str, Question],
    by_id: dict[int, Entry],
    repo: CorpusRepository,
) -> str:
    question = asked.get(result.question_id)
    if question is None:
        # A results file outlives the set that produced it. Said, not skipped.
        return (
            f"<section><h2>{html.escape(result.question_id)}</h2>"
            f'<p class="q">{html.escape(result.question)}</p>'
            f'<div class="answer">{_answer(result.answer)}</div>'
            f'<p class="note">This question is no longer in the set, so nothing here '
            f"is scored against it.</p></section>"
        )
    score = citation_score(result, question, repo)
    place = {
        row.entry_id: index + 1
        for index, row in enumerate(rows_for(repo, result.cited, result.retrieved, result.question))
    }
    expected, cited = set(result.expected_entries), set(result.cited)
    admissible = set(question.admissible_entries)
    rows = sorted(expected | admissible | cited, key=lambda e: (place.get(e, 10**6), e))
    body = "".join(_row(e, by_id, place, expected, admissible, cited, result) for e in rows)
    table = (
        # "ID", the header both drivers use. Naming the source database here would put
        # its notation in a second live string, which ADR-0420 keeps to one module.
        "<table><thead><tr><th>ID</th><th>Property</th><th>Organism</th><th>Value</th>"
        f"<th>Rank</th><th></th></tr></thead><tbody>{body}</tbody></table>"
        if body
        else '<p class="none">Nothing expected and nothing cited.</p>'
    )
    if score.expected:
        verdict = (
            "every expected entry reached the table"
            if score.all_expected_reached_the_table
            else f"{len(score.never_retrieved)} of {score.expected} never retrieved"
        )
    else:
        verdict = "no expected entries: scored on declining"
    notes = _notes(result)
    return f"""
<section>
  <h2>{html.escape(result.question_id)} <span class="rep">repeat {result.repeat} ·
      {html.escape(str(question.tier))}</span></h2>
  <p class="q">{html.escape(result.question)}</p>
  <div class="answer">{_answer(result.answer)}</div>
  <h3>Entries that bear on the score
      <span class="sub">{len(rows)} shown of {len(result.retrieved)} retrieved ·
      {verdict}</span></h3>
  {table}{notes}
  <p class="meta">{html.escape(result.end_reason)} · {result.searches} search(es),
     {result.tool_calls}/{result.tool_call_limit} tool calls,
     {result.model_calls}/{result.call_limit} model calls ·
     {result.matched} matched · ${result.spend / 1_000_000:.4f}</p>
</section>"""


def _row(entry_id, by_id, place, expected, admissible, cited, result) -> str:
    if entry_id in expected:
        if entry_id not in set(result.retrieved):
            mark, kind = "never retrieved", "miss"
        elif entry_id in cited:
            mark, kind = "cited", "hit"
        else:
            mark, kind = "in table, not cited", "table"
    elif entry_id in admissible:
        mark, kind = ("admissible, cited", "adm") if entry_id in cited else ("admissible", "adm")
    else:
        mark, kind = "cited, in neither list", "extra"
    rank = f"#{place[entry_id]}" if entry_id in place else "—"
    entry = by_id.get(entry_id)
    if entry is None:
        return (
            f'<tr class="{kind}"><td class="id">{entry_id}</td>'
            f"<td colspan=3><em>not in the corpus</em></td>"
            f'<td class="rank">{rank}</td><td class="mark">{mark}</td></tr>'
        )
    return (
        f'<tr class="{kind}"><td class="id">{entry_id}</td>'
        f"<td>{html.escape(entry.property or '')}</td>"
        f"<td>{html.escape(entry.organism or '')}</td>"
        f'<td class="num">{_value(entry)}</td>'
        f'<td class="rank">{rank}</td><td class="mark">{mark}</td></tr>'
    )


def _value(entry: Entry) -> str:
    if entry.range_low is not None and entry.range_high is not None:
        # An approximate scalar is recorded as a range whose ends are equal, and
        # printing it literally reads as a spread the source never claimed.
        core = (
            entry.range_low
            if entry.range_low == entry.range_high
            else f"{entry.range_low}–{entry.range_high}"
        )
    else:
        core = entry.value if entry.value is not None else "—"
    flags = "".join(
        mark
        for mark, on in (
            ("~", entry.range_approximate),
            ("≷", entry.range_one_sided),
            ("?", entry.range_qualified),
            ("⚯", entry.range_fused),
        )
        if on
    )
    shown = f"{core} {entry.units or ''}".strip()
    return f"{shown} <span class='flag'>{flags}</span>" if flags else shown


def _notes(result: Result) -> str:
    notes = []
    if result.cited and not result.retrieved:
        notes.append("Cited without retrieving: a follow-up, answered in its parent's session.")
    if result.unknown_citations:
        notes.append(f"Cited entries the corpus does not hold: {list(result.unknown_citations)}.")
    if result.ungrounded_refusal:
        notes.append("Refused without having searched.")
    if result.failure:
        notes.append(f"Failure: {result.failure}")
    return "".join(f'<p class="note">{html.escape(note)}</p>' for note in notes)


def _answer(text: str) -> str:
    out = []
    for block in text.split("\n\n"):
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html.escape(block))
        escaped = DELIMITED.sub(lambda m: f'<span class="cite">{m.group(1)}</span>', escaped)
        lines = escaped.split("\n")
        listed = [line for line in lines if line.strip()]
        if listed and all(line.lstrip().startswith(("-", "*")) for line in listed):
            items = "".join(f"<li>{line.lstrip(' -*')}</li>" for line in listed)
            out.append(f"<ul>{items}</ul>")
        else:
            out.append("<p>" + "<br>".join(lines) + "</p>")
    return "".join(out)


def _front_matter(first: Result) -> str:
    p = first.provenance
    if p is None:
        return ""
    return f"""<dl class="front">
<dt>Recorded</dt><dd>{html.escape(p.recorded_at)}</dd>
<dt>Model</dt><dd>{html.escape(p.model)}</dd>
<dt>Corpus</dt><dd>{p.corpus_entries} entries, digest {html.escape(p.corpus_digest)}</dd>
<dt>Prompt digest</dt><dd>{html.escape(p.prompt_digest)}</dd>
<dt>Code</dt><dd>{html.escape(p.code_version)}</dd>
<dt>Run label</dt><dd>{html.escape(p.run_label)}</dd>
</dl>"""


_STYLE = """
@page { size: A4; margin: 16mm 14mm;
        @bottom-center { content: counter(page); font: 9pt Georgia; color:#777; } }
body { font: 10.5pt/1.5 Georgia, serif; color:#1a1a1a; }
h1 { font-size: 19pt; margin: 0 0 2mm; }
h2 { font-size: 13pt; margin: 0 0 1mm; font-family:"DejaVu Sans Mono",monospace; color:#31506b; }
h2 .rep { font-family: Helvetica, sans-serif; font-size: 8pt; color:#999; font-weight:400; }
h3 { font-size: 10pt; margin: 5mm 0 1.5mm; text-transform: uppercase; letter-spacing:.06em;
     font-family: Helvetica, sans-serif; color:#666; font-weight:600; }
h3 .sub { text-transform:none; letter-spacing:0; font-weight:400; color:#999; }
section { margin-bottom: 9mm; padding-top: 3mm; border-top: 1.5pt solid #31506b; }
.q { font-size: 11.5pt; font-style: italic; margin: 0 0 3mm; }
.answer { background:#f7f6f3; padding: 3mm 4mm; border-left: 2.5pt solid #c9c2b4; }
.answer p, .answer ul { margin: 0 0 2mm; } .answer ul { padding-left: 5mm; }
.answer > *:last-child { margin-bottom: 0; }
.cite { font-family:"DejaVu Sans Mono",monospace; font-size:8.5pt; background:#e6ecf2;
        padding: 0 .8mm; border-radius:1.5pt; color:#31506b; }
table { width:100%; border-collapse:collapse; font-size:8.8pt; }
th { text-align:left; font-family:Helvetica,sans-serif; font-size:7.5pt; text-transform:uppercase;
     letter-spacing:.05em; color:#777; border-bottom:1pt solid #333; padding:1mm 1.5mm; }
td { padding:1.2mm 1.5mm; border-bottom:.4pt solid #ddd; vertical-align:top; }
td.id, td.num, td.rank { font-family:"DejaVu Sans Mono",monospace; white-space:nowrap; }
td.rank { color:#888; }
td.mark { font-family:Helvetica,sans-serif; font-size:7.5pt; white-space:nowrap; color:#555; }
tr.miss td { background:#fdf0ee; } tr.miss td.mark { color:#a33; font-weight:600; }
tr.table td { background:#f4f6f8; }
tr.extra td { background:#fbf8ec; } tr.extra td.mark { color:#8a6d00; }
tr.adm td { background:#f2f7f2; } tr.adm td.mark { color:#3d7040; }
.flag { color:#a06000; font-family:Helvetica,sans-serif; font-size:7.5pt; }
.note { font-size:8.8pt; color:#8a5000; margin:2mm 0 0; }
.none { font-size:9.5pt; color:#666; font-style:italic; }
.meta { font-family:Helvetica,sans-serif; font-size:7.8pt; color:#888; margin:2.5mm 0 0; }
.front { font-size:9.5pt; color:#555; }
.front dt { font-family:Helvetica,sans-serif; font-size:7.5pt; text-transform:uppercase;
            letter-spacing:.05em; color:#999; float:left; width:32mm; clear:left; }
.front dd { margin:0 0 1mm 32mm; font-family:"DejaVu Sans Mono",monospace; font-size:8.8pt; }
"""

_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Answer sheet</title>
<style>{style}</style></head><body>
<h1>Answer sheet — {count} results</h1>
<p class="front">Each answer, and the entries that bear on scoring it. The verbatim retrieval
context every answer was built from is not reproduced here.</p>
{front}
<p class="front"><span class="cite">nnnnnn</span> in an answer is a citation to the entry of
that id. <em>Rank</em> is the entry's place in the table a reader would have seen. Value flags:
<span class="flag">~</span> approximate, <span class="flag">≷</span> one-sided,
<span class="flag">?</span> qualified, <span class="flag">⚯</span> fused range.</p>
{sections}
</body></html>"""
