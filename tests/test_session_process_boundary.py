"""The session must be continuable by a process that did not create it.

`agent-session` requires this because the web interface re-runs its script on
every interaction and holds nothing between runs, so conversation across turns
rests entirely on the checkpointer. The requirement is only meaningfully proved
across a real process boundary, so this test drives two subprocesses against one
checkpoint file rather than reusing a saver in-process.

The model is faked. What is under test is persistence, not the model.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

# Each turn runs in its own interpreter. The only thing carried between them is
# the checkpoint file and the thread id -- the same two things a redeployed web
# app would have.
_TURN = """
import sys
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langgraph.checkpoint.sqlite import SqliteSaver

db, thread_id, reply, question = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

with SqliteSaver.from_conn_string(db) as saver:
    agent = create_agent(
        model=GenericFakeChatModel(messages=iter([reply])),
        tools=[],
        checkpointer=saver,
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": question}]},
        config={"configurable": {"thread_id": thread_id}},
    )

# Print the whole conversation the second process can see, so the test can assert
# on what survived rather than on what this process just produced.
for message in result["messages"]:
    print(f"{type(message).__name__}: {message.content}")
"""


def _run_turn(db: str, thread_id: str, reply: str, question: str) -> str:
    completed = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(_TURN), db, thread_id, reply, question],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout


def test_a_session_continues_in_a_process_that_did_not_create_it(tmp_path):
    db = str(tmp_path / "checkpoints.sqlite")
    thread_id = "session-under-test"

    first = _run_turn(db, thread_id, "Around 1 micrometre.", "How wide is an E. coli cell?")
    assert "How wide is an E. coli cell?" in first

    # A different interpreter, given only the checkpoint file and the thread id.
    second = _run_turn(db, thread_id, "Rather larger.", "What about yeast?")

    # The earlier turn is present, so a follow-up could resolve against it.
    assert "How wide is an E. coli cell?" in second, second
    assert "Around 1 micrometre." in second, second
    assert "What about yeast?" in second, second


def test_a_different_thread_id_does_not_inherit(tmp_path):
    db = str(tmp_path / "checkpoints.sqlite")
    _run_turn(db, "session-one", "Around 1 micrometre.", "How wide is an E. coli cell?")

    other = _run_turn(db, "session-two", "I have no earlier context.", "What about yeast?")

    # Isolation: a second session sharing the same store sees none of the first.
    assert "How wide is an E. coli cell?" not in other, other


# Spend has the same problem as the conversation and a worse failure mode: a run
# total that lives only in memory restarts at zero when a session resumes in
# another process, so the run budget silently bounds nothing. Driving the real
# AskAgent here rather than a bare create_agent, because what is under test is the
# ledger's persistence, not the checkpointer's.
_ASK_TURN = """
import sys
from agent_doubles import costing, says, scripted
from bionumbers_ask.agent import AskAgent
from bionumbers_ask.config import Config, usd
from bionumbers_ask.corpus import load
from bionumbers_ask.events import QuestionEnded
from bionumbers_ask.repository import CorpusRepository

db, thread_id, corpus, question = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

config = Config(model="fake/model", warning_threshold=usd("0.50"), run_budget=usd("1.20"))
model = scripted(costing(says("about 1 micrometre (BNID 100002)"), 0.000110))
agent = AskAgent(CorpusRepository(load(corpus)), config, db, model=model)

end = [e for e in agent.ask(thread_id, question) if isinstance(e, QuestionEnded)][0]
print(f"question={end.spend} run={end.run_spend} reason={end.reason.value}")
"""


def _ask_turn(db: str, thread_id: str, question: str) -> str:
    import os
    from pathlib import Path

    tests_dir = Path(__file__).parent
    env = {**os.environ, "PYTHONPATH": str(tests_dir)}
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            textwrap.dedent(_ASK_TURN),
            db,
            thread_id,
            str(tests_dir / "fixtures" / "corpus_sample.jsonl"),
            question,
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def test_run_spend_continues_across_a_process_boundary(tmp_path):
    db = str(tmp_path / "spend.sqlite")

    first = _ask_turn(db, "session-under-test", "How wide is an E. coli cell?")
    assert first == "question=110 run=110 reason=answered", first

    # A different interpreter, given only the checkpoint file and the thread id.
    second = _ask_turn(db, "session-under-test", "And yeast?")

    # The per-question figure resets; the run total does not.
    assert second == "question=110 run=220 reason=answered", second


def test_run_spend_does_not_leak_between_sessions_across_processes(tmp_path):
    db = str(tmp_path / "spend.sqlite")
    _ask_turn(db, "session-one", "How wide is an E. coli cell?")

    other = _ask_turn(db, "session-two", "How wide is an E. coli cell?")

    # Spend accumulated in one session is not counted against another.
    assert other == "question=110 run=110 reason=answered", other
