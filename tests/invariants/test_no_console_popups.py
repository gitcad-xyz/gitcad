"""No gitcad subprocess may flash a console window on Windows.

Field bug, reported by the repo owner twice — "I keep getting command line
windows popping up", then "man you still are doing tons of cmd popups and
closing them" after a partial fix. gitcad shells out to ``git`` constantly (a
drawing's title block reads the commit, the lockfile resolves refs, review
diffs, lot provenance), and on Windows each launch from a GUI-less parent
allocates a console the user sees flash. One drawing render is a burst of
them.

This is an INVARIANT rather than a regression test because the failure mode is
additive: the code is correct today, and the way it breaks is someone writing
a perfectly ordinary ``subprocess.run(["git", ...])`` in a new module months
from now. A grep-style guard is the only thing that catches that, and it costs
nothing to keep.

Two independent mechanisms, because either alone leaves a gap:
  * ``gitcad.proc.run``/``popen`` add CREATE_NO_WINDOW;
  * the detached viewer daemon additionally runs under ``pythonw.exe``,
    since ``python.exe`` is a console-subsystem binary that Windows gives a
    console to regardless of flags.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
SRC_DIRS = sorted((REPO / "packages").glob("*/src"))

#: the ONE module allowed to call subprocess directly — it is the wrapper,
#: and the daemon, which needs its own detach flags (and passes them, which
#: gitcad.proc deliberately leaves alone).
ALLOWED = {"gitcad/proc.py", "gitcad/viewer/daemon.py"}


def _py_files():
    for src in SRC_DIRS:
        for p in src.rglob("*.py"):
            yield p


def _rel(p: pathlib.Path) -> str:
    for src in SRC_DIRS:
        try:
            return p.relative_to(src).as_posix()
        except ValueError:
            continue
    return p.as_posix()


def test_packages_exist():
    """Guard the guard: a bad path would make every assertion below vacuous."""
    assert SRC_DIRS, "no packages/*/src found — this test proves nothing"
    assert sum(1 for _ in _py_files()) > 50


def test_no_module_calls_subprocess_directly():
    offenders = []
    for path in _py_files():
        rel = _rel(path)
        if rel in ALLOWED:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:                       # pragma: no cover
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if (isinstance(fn, ast.Attribute)
                    and isinstance(fn.value, ast.Name)
                    and fn.value.id == "subprocess"
                    and fn.attr in {"run", "Popen", "call", "check_output",
                                    "check_call"}):
                offenders.append(f"{rel}:{node.lineno} subprocess.{fn.attr}")
    assert not offenders, (
        "these launch a subprocess directly and will flash a console window "
        "on Windows — use `from gitcad import proc as _proc` and "
        "`_proc.run(...)`/`_proc.popen(...)` instead:\n  "
        + "\n  ".join(offenders))


def test_the_wrapper_adds_the_no_window_flag():
    from gitcad import proc

    assert proc.CREATE_NO_WINDOW == 0x08000000
    flags = proc._flagged({}).get("creationflags")
    if proc._WINDOWS:
        assert flags == proc.CREATE_NO_WINDOW
    else:
        assert flags is None, "POSIX must not grow Windows flags"


def test_an_explicit_creationflags_is_left_alone():
    """The viewer daemon needs DETACHED_PROCESS | CREATE_BREAKAWAY_FROM_JOB to
    outlive the agent session (viewer contract). Silently OR-ing into a
    caller's chosen flags would be hidden coupling."""
    from gitcad import proc

    assert proc._flagged({"creationflags": 0x8})["creationflags"] == 0x8


def test_the_wrapper_still_captures_output():
    """A no-window child must still pipe stdout — every caller reads it."""
    import sys

    from gitcad import proc

    r = proc.run([sys.executable, "-c", "print('ok')"],
                 capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "ok"


def test_the_viewer_daemon_avoids_the_console_interpreter():
    """``python.exe`` is console-subsystem: Windows gives it a console no
    matter what flags are passed, so the detached viewer would leave a black
    window open for its whole life. ``pythonw.exe`` never gets one."""
    import os
    import sys

    from gitcad.viewer.daemon import _daemon_python

    chosen = _daemon_python()
    if os.name != "nt":
        assert chosen == sys.executable
        return
    expected = pathlib.Path(sys.executable).with_name("pythonw.exe")
    assert chosen == (str(expected) if expected.exists() else sys.executable)


def test_the_daemon_spawn_asks_for_no_window():
    """Pin the flag in the source of the one module allowed its own flags."""
    src = (REPO / "packages/gitcad/src/gitcad/viewer/daemon.py").read_text(
        encoding="utf-8")
    assert "0x08000000" in src, "daemon lost CREATE_NO_WINDOW"
    assert "DETACHED_PROCESS" in src, "daemon must still outlive the session"
