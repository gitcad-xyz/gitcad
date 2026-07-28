"""Subprocess launches that do not flash a console window.

Field bug, reported twice by the repo owner: "I keep getting command line
windows popping up" and, after a first pass, "man you still are doing tons of
cmd popups and closing them".

On Windows every ``subprocess.run(["git", ...])`` from a GUI-less parent
allocates a new console for the child, which appears as a black window that
flashes and vanishes. gitcad shells out to ``git`` constantly — a drawing's
title block reads the commit, the lockfile resolves refs, the review tools
diff, ``lots`` records provenance — so a single drawing render or test run
produces a burst of them. Individually harmless, collectively unusable.

``CREATE_NO_WINDOW`` (0x08000000) tells Windows to run the child with no
console at all. stdout/stderr still pipe normally, so every caller that reads
``capture_output`` keeps working unchanged.

Use :func:`run` and :func:`popen` instead of ``subprocess.run``/``Popen``
anywhere in gitcad. The only launch that legitimately needs different flags is
the detached viewer daemon (it also needs DETACHED_PROCESS and
CREATE_BREAKAWAY_FROM_JOB to outlive the agent session, per the viewer
contract); it passes its own ``creationflags`` and this module leaves an
explicit value alone.

No-op on POSIX, where a child never gets a console it did not ask for.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

#: Windows: run the child with no console. Not exported by the stdlib on
#: non-Windows builds, so it is spelled out rather than imported.
CREATE_NO_WINDOW = 0x08000000

_WINDOWS = sys.platform == "win32"


def _flagged(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Add the no-window flag unless the caller chose its own flags.

    A caller that passes ``creationflags`` explicitly (the viewer daemon) has
    a reason; silently OR-ing into it would be the kind of hidden coupling
    that makes a later change to the daemon fail somewhere else.
    """
    if _WINDOWS and "creationflags" not in kwargs:
        kwargs["creationflags"] = CREATE_NO_WINDOW
    return kwargs


def run(*args: Any, **kwargs: Any) -> "subprocess.CompletedProcess":
    """``subprocess.run`` that does not flash a console on Windows."""
    return subprocess.run(*args, **_flagged(kwargs))


def popen(*args: Any, **kwargs: Any) -> "subprocess.Popen":
    """``subprocess.Popen`` that does not flash a console on Windows."""
    return subprocess.Popen(*args, **_flagged(kwargs))
