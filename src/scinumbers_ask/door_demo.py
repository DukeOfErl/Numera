"""The recorded examples the sign-in door plays: a question typed, an answer streamed.

**Presentation, not core.** Nothing here reaches the agent, the corpus or a model;
the answers are text recorded from real runs and committed beside this module
(`door_demo.json`), under the bounded exception ADR-1200 makes to ADR-0170.

Every example is a real question and the real answer it got, verbatim (ADR-1210).
The keystrokes are theatre -- a question typed, words taken back, others typed in
their place -- and `typed` is what holds them to the record: the text they end on
must be the question the answer was recorded for, or the door shows an answer to
a question nobody asked.

The animation runs in the browser, inside the one iframe `web.draw_closed_door`
draws. Python decides everything that can be wrong -- what a word is, what the
answer says, how it is escaped -- and hands the browser characters to type, a
count to delete, and finished HTML to reveal.
"""

from __future__ import annotations

import datetime
import html
import json
import re
from dataclasses import dataclass
from importlib import resources

#: The frame's height in CSS pixels. Fixed rather than Streamlit's `"content"`,
#: because the content grows as the answer streams and a frame that grew with it
#: would push the privacy note down the page on every example.
HEIGHT = 520


@dataclass(frozen=True)
class Type:
    """Characters typed into the input."""

    text: str


@dataclass(frozen=True)
class Erase:
    """Whole words taken back from the end of what has been typed."""

    words: int


Step = Type | Erase


@dataclass(frozen=True)
class Scenario:
    id: str
    steps: tuple[Step, ...]
    #: The question exactly as it was put to the agent.
    asked: str
    #: The answer exactly as the agent gave it: markdown, citations as `[[nnnnnn]]`.
    answer: str
    model: str
    #: ISO date the answer was recorded.
    recorded: str
    #: Where the answer was taken from, so it can be traced back to its run.
    source: str


def _step(raw: dict) -> Step:
    if set(raw) == {"type"}:
        return Type(raw["type"])
    if set(raw) == {"erase_words"}:
        return Erase(raw["erase_words"])
    raise ValueError(f"not a step: {raw!r}")


def scenarios() -> tuple[Scenario, ...]:
    """The examples, in the order the door plays them."""
    raw = json.loads(resources.files(__package__).joinpath("door_demo.json").read_text("utf-8"))
    return tuple(
        Scenario(**{**item, "steps": tuple(_step(step) for step in item["steps"])}) for item in raw
    )


def keystrokes(steps: tuple[Step, ...]) -> list[dict]:
    """What the browser does: characters to type, or a count of characters to delete.

    The browser knows nothing about words. A word is decided here, once, so the
    text the browser ends on and the text `typed` reports cannot come apart.
    """
    text = ""
    out: list[dict] = []
    for step in steps:
        if isinstance(step, Type):
            text += step.text
            out.append({"type": step.text})
        else:
            words = list(re.finditer(r"\S+", text))
            if step.words > len(words):
                raise ValueError(f"cannot erase {step.words} words from {text!r}")
            cut = words[-step.words].start()
            out.append({"erase": len(text) - cut})
            text = text[:cut]
    return out


def typed(steps: tuple[Step, ...]) -> str:
    """The text in the input once every step has run."""
    text = ""
    for key in keystrokes(steps):
        text = text + key["type"] if "type" in key else text[: len(text) - key["erase"]]
    return text


# --- markdown ------------------------------------------------------------------
#
# Hand-written, and deliberately small. The project has no markdown library and
# the door needs one for two committed answers; `unsupported` fails a test for any
# example that goes beyond this subset, so the cost of the choice is a failing test
# rather than raw asterisks on the door.

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<![\*\w])\*(?!\s)(.+?)(?<!\s)\*(?![\*\w])")

# `[ \t]`, never `\s`, at the start of a line: `\s` crosses the newline of a blank
# line, which made every list after a paragraph read as nested.
_UNSUPPORTED = (
    ("inline code", re.compile(r"`")),
    ("a table", re.compile(r"^[ \t]*\|", re.M)),
    ("a link", re.compile(r"\]\(")),
    ("a numbered list", re.compile(r"^[ \t]*\d+\.\s", re.M)),
    ("a quotation", re.compile(r"^[ \t]*>", re.M)),
    ("a top-level heading", re.compile(r"^# ", re.M)),
    ("a deep heading", re.compile(r"^#{4,} ", re.M)),
    ("a nested list", re.compile(r"^[ \t]+[-*+]\s", re.M)),
    ("a list not marked with a hyphen", re.compile(r"^[*+]\s", re.M)),
    ("a horizontal rule", re.compile(r"^[ \t]*(-{3,}|\*{3,}|_{3,})[ \t]*$", re.M)),
    ("underscore emphasis", re.compile(r"(?<!\w)_[^_\s][^_]*_(?!\w)")),
)


def _inline(text: str) -> str:
    """Escaped first, emphasis second -- so nothing in the text can become markup."""
    escaped = html.escape(text)
    return _ITALIC.sub(r"<em>\1</em>", _BOLD.sub(r"<strong>\1</strong>", escaped))


def unsupported(markdown: str) -> list[str]:
    """The markdown `render` would draw wrongly, named. Empty when all of it is drawable."""
    found = [name for name, pattern in _UNSUPPORTED if pattern.search(markdown)]
    for line in markdown.split("\n"):
        body = line[2:] if line.startswith("- ") else line.lstrip("#").strip()
        if "*" in _inline(body):
            found.append("an unmatched asterisk")
            break
    return found


def render(markdown: str) -> str:
    """HTML for the subset: `##`/`###` headings, `- ` lists, bold, italic, paragraphs."""
    blocks: list[str] = []
    paragraph: list[str] = []
    items: list[str] = []

    def close_paragraph() -> None:
        if paragraph:
            blocks.append(f"<p>{' '.join(paragraph)}</p>")
            paragraph.clear()

    def close_list() -> None:
        if items:
            blocks.append("<ul>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>")
            items.clear()

    for line in markdown.split("\n"):
        stripped = line.strip()
        if not stripped:
            close_paragraph()
            close_list()
        elif stripped.startswith(("## ", "### ")):
            close_paragraph()
            close_list()
            blocks.append(f"<h3>{_inline(stripped.lstrip('#').strip())}</h3>")
        elif line.startswith("- "):
            close_paragraph()
            items.append(_inline(line[2:].strip()))
        else:
            close_list()
            paragraph.append(_inline(stripped))
    close_paragraph()
    close_list()
    return "".join(blocks)


# --- the page ------------------------------------------------------------------


def _label(scenario: Scenario) -> str:
    day = datetime.date.fromisoformat(scenario.recorded)
    return f"Recorded example · a real answer from {scenario.model}, {day.day} {day:%b %Y}"


def page(examples: tuple[Scenario, ...] | None = None) -> str:
    """The whole frame: markup, style, the examples as data, and the program."""
    examples = scenarios() if examples is None else examples
    payload = [
        {
            "asked": s.asked,
            "keys": keystrokes(s.steps),
            "answer": render(s.answer),
            "label": _label(s),
        }
        for s in examples
    ]
    # `<` as an escape, not a character: an answer holding `</script>` would
    # otherwise end the data block and run the rest as markup. The JSON is equal.
    data = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    return _PAGE.replace("__DATA__", data)


_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<style>
:root {
  --bg: #ffffff; --panel: #f0f2f6; --text: #31333f; --muted: #6b6f7b;
  --user: #ff4b4b; --bot: #ffbd45; --line: #d6d9e0;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0e1117; --panel: #262730; --text: #fafafa; --muted: #a3a8b8;
    --user: #ff6c6c; --bot: #ffbd45; --line: #3b3d48;
  }
}
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; background: var(--bg); color: var(--text);
  font: 15px/1.55 "Source Sans Pro", "Source Sans 3", system-ui, sans-serif; }
.demo { height: 100%; display: flex; flex-direction: column; gap: 10px;
  border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px;
  transition: opacity .5s; }
.demo.fading { opacity: 0; }
.label { font-size: 12.5px; color: var(--muted); }
.thread { flex: 1; overflow-y: auto; scrollbar-width: thin; display: flex;
  flex-direction: column; gap: 12px; }
.msg { display: flex; gap: 10px; align-items: flex-start; }
.msg[hidden] { display: none; }
.avatar { flex: none; width: 28px; height: 28px; border-radius: 7px; display: grid;
  place-items: center; color: #fff; font-size: 13px; font-weight: 600; }
.user .avatar { background: var(--user); }
.bot .avatar { background: var(--bot); color: #31333f; }
.user .text { background: var(--panel); border-radius: 8px; padding: 4px 10px; }
.body { min-width: 0; }
.body h3 { font-size: 16px; margin: 2px 0 6px; }
.body p, .body ul { margin: 0 0 8px; }
.body ul { padding-left: 20px; }
.body .pending { display: none; }
.dots span { display: inline-block; width: 6px; height: 6px; margin-right: 4px;
  border-radius: 50%; background: var(--muted); animation: blink 1s infinite; }
.dots span:nth-child(2) { animation-delay: .2s; }
.dots span:nth-child(3) { animation-delay: .4s; }
@keyframes blink { 50% { opacity: .2; } }
.input { display: flex; align-items: center; gap: 8px; background: var(--panel);
  border-radius: 10px; padding: 10px 12px; min-height: 44px; }
.typing { flex: 1; white-space: pre-wrap; }
.typing.empty::before { content: "Ask a question"; color: var(--muted); }
.caret { width: 1.5px; height: 18px; background: var(--text);
  animation: blink 1s steps(1) infinite; }
.send { color: var(--muted); font-size: 16px; }
@media (prefers-reduced-motion: reduce) {
  .demo, .dots span, .caret { transition: none; animation: none; }
}
</style></head>
<body>
<div class="demo" id="demo" role="region"
     aria-label="A recorded example of a question and its answer">
  <div class="label" id="label"></div>
  <div class="thread" id="thread">
    <div class="msg user" id="user" hidden>
      <div class="avatar" aria-hidden="true">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
          <circle cx="8" cy="5" r="3"/><path d="M2 15c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5z"/>
        </svg>
      </div>
      <div class="text" id="asked"></div>
    </div>
    <div class="msg bot" id="bot" hidden>
      <div class="avatar" aria-hidden="true">SN</div>
      <div class="body" id="answer"></div>
    </div>
  </div>
  <div class="input" aria-hidden="true">
    <span class="typing empty" id="typing"></span><span class="caret"></span>
    <span class="send">&#10148;</span>
  </div>
</div>
<script type="application/json" id="examples">__DATA__</script>
<script>
const examples = JSON.parse(document.getElementById("examples").textContent);
const $ = (id) => document.getElementById(id);
const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
const sleep = (ms) => new Promise((done) => setTimeout(done, ms));
const jitter = (low, high) => low + Math.random() * (high - low);

// A reader who points at the frame is reading it: the loop waits for them, and a
// reader who scrolls up is not dragged back down by the stream.
let reading = false;
let following = true;
$("demo").addEventListener("pointerenter", () => (reading = true));
$("demo").addEventListener("pointerleave", () => (reading = false));
$("thread").addEventListener("wheel", () => (following = false));
$("thread").addEventListener("touchmove", () => (following = false));

async function hold(ms) {
  const until = Date.now() + ms;
  while (Date.now() < until || reading) await sleep(200);
}

function setTyping(text) {
  $("typing").textContent = text;
  $("typing").classList.toggle("empty", text === "");
}

function reset(example) {
  $("label").textContent = example.label;
  $("user").hidden = true;
  $("bot").hidden = true;
  $("answer").innerHTML = "";
  $("thread").scrollTop = 0;
  following = true;
  setTyping("");
}

function showWhole(example) {
  reset(example);
  $("asked").textContent = example.asked;
  $("answer").innerHTML = example.answer;
  $("user").hidden = false;
  $("bot").hidden = false;
}

async function type(example) {
  let text = "";
  for (const key of example.keys) {
    if ("type" in key) {
      for (const ch of key.type) {
        text += ch;
        setTyping(text);
        await sleep(ch === " " ? jitter(60, 140) : jitter(35, 95));
      }
    } else {
      await sleep(700);
      for (let i = 0; i < key.erase; i++) {
        text = text.slice(0, -1);
        setTyping(text);
        await sleep(40);
      }
      await sleep(350);
    }
  }
  await sleep(500);
}

async function stream(example) {
  const body = $("answer");
  body.innerHTML = example.answer;
  const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  const full = nodes.map((node) => node.nodeValue);
  nodes.forEach((node) => (node.nodeValue = ""));
  body.querySelectorAll("h3, p, li").forEach((block) => block.classList.add("pending"));
  for (let n = 0; n < nodes.length; n++) {
    const block = nodes[n].parentElement.closest("h3, p, li");
    if (block) block.classList.remove("pending");
    const words = full[n].match(/\\S+\\s*|\\s+/g) || [];
    for (let w = 0; w < words.length; w += 2) {
      nodes[n].nodeValue += words.slice(w, w + 2).join("");
      if (following) $("thread").scrollTop = $("thread").scrollHeight;
      await sleep(jitter(25, 60));
    }
  }
}

async function play(example) {
  reset(example);
  await sleep(600);
  await type(example);
  $("asked").textContent = example.asked;
  $("user").hidden = false;
  setTyping("");
  $("answer").innerHTML = '<span class="dots"><span></span><span></span><span></span></span>';
  $("bot").hidden = false;
  await sleep(1400);
  await stream(example);
  await hold(9000);
  $("demo").classList.add("fading");
  await sleep(600);
  $("demo").classList.remove("fading");
}

(async () => {
  for (let i = 0; ; i = (i + 1) % examples.length) {
    if (still) {
      showWhole(examples[i]);
      await hold(15000);
    } else {
      await play(examples[i]);
    }
  }
})();
</script>
</body></html>
"""
