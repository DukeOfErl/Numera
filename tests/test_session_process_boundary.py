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
_TURN = '''
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
'''


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
