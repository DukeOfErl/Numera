"""The monitor reads the trail; it is not an adapter, and the agent cannot reach it.

`test_driver_independence.imports_of` is not reused: it strips `numera_ask.` and
answers "which sibling", where the question here is "which module of *another*
package", so it needs the full dotted path (ADR-1950).
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
MONITOR = SRC / "numera_monitor"
ASK = SRC / "numera_ask"

#: What the monitor may take from the application, and why each is there.
#: `neon` resolves a branch by name; `hosted_trace` derives a trace id; `pending`
#: is the door rule, reused so there is one copy of it; `trail_store` lends its
#: connect timeout and pool recycle rather than the monitor inventing new ones.
ALLOWED_FROM_ASK = {"neon", "hosted_trace", "pending", "trail_store"}


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _modules(package: Path) -> list[Path]:
    return sorted(p for p in package.glob("*.py"))


def test_the_monitor_takes_only_what_it_needs_from_the_application():
    reached = set()
    for path in _modules(MONITOR):
        for name in _imports(path):
            parts = name.split(".")
            if parts[0] == "numera_ask" and len(parts) > 1:
                reached.add(parts[1])
    assert reached <= ALLOWED_FROM_ASK, sorted(reached - ALLOWED_FROM_ASK)


def test_nothing_in_the_application_imports_the_monitor():
    offenders = [
        p.name
        for p in _modules(ASK)
        if any(n.split(".")[0] == "numera_monitor" for n in _imports(p))
    ]
    assert offenders == []


def test_only_the_page_imports_streamlit():
    users = {
        p.stem
        for p in _modules(MONITOR)
        if any(n.split(".")[0] == "streamlit" for n in _imports(p))
    }
    assert users <= {"app"}


def test_the_rule_sees_a_from_import_of_a_submodule(tmp_path):
    """`from numera_ask import agent` names the module in the alias, not in
    `module`; a reader that looked only at `module` would see `numera_ask` and
    pass it."""
    probe = tmp_path / "probe.py"
    probe.write_text("from numera_ask import agent\nimport numera_ask.web\n")
    assert {"numera_ask.agent", "numera_ask.web"} <= _imports(probe)
