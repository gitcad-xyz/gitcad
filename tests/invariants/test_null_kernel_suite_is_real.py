"""The null-kernel suite must stay substantial, or green means nothing.

CLAUDE.md: "Base suite runs with no kernel installed (null backend)." That job
is the only thing checking ADR-0002's seam boundary actually holds with no
geometry behind it. It had quietly stopped working — ADR-0018's
`@pytest.mark.occt` was deleted in #107 and nothing replaced it, so there was
no way left to say "this test needs geometry". Collection aborted, the job went
red, and it stayed red while local runs (which always have the kernel) were
green.

The repair marks kernel-dependent tests automatically (see tests/conftest.py).
Automatic marking has an obvious failure mode: a rule that marks EVERYTHING
makes the job pass by testing nothing. This is the floor that stops that.

Reproduce the job locally with GITCAD_FORCE_NULL_KERNEL=1.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Set from the measured 468 with headroom. If a legitimate change drops the
# count below this, that is a conversation, not a number to quietly lower.
FLOOR = 400


@pytest.mark.invariant
def test_the_null_kernel_suite_still_covers_a_real_body_of_tests() -> None:
    env = dict(os.environ, GITCAD_FORCE_NULL_KERNEL="1")
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "--collect-only", "-m", "not kernel", str(ROOT / "tests")],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    tail = out.stdout.strip().splitlines()[-1] if out.stdout.strip() else ""
    # pytest reports either "N tests collected" or, when -m deselects,
    # "N/TOTAL tests collected (D deselected)" — parse both.
    m = re.search(r"(\d+)(?:/\d+)? tests? collected", tail)
    n = int(m.group(1)) if m else 0
    assert n >= FLOOR, (
        f"only {n} tests survive without a kernel (floor {FLOOR}). Either the "
        "auto-marking rule in tests/conftest.py has become too broad — in "
        "which case the null-kernel job is passing by testing nothing — or "
        f"real coverage was lost.\n{tail}")


@pytest.mark.invariant
def test_the_seam_contracts_are_among_what_survives() -> None:
    """Coverage is not only a count. The whole point of the null backend is
    that the SEAM works without geometry, so those tests specifically must be
    in the surviving set — a floor met entirely by unrelated ECAD tests would
    satisfy the count and miss the claim."""
    env = dict(os.environ, GITCAD_FORCE_NULL_KERNEL="1")
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "--collect-only", "-m", "not kernel", str(ROOT / "tests")],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    text = out.stdout
    for needed in ("test_seam_enforcement", "test_document", "test_part"):
        assert needed in text, (
            f"{needed} no longer runs without a kernel — the base suite has "
            "stopped testing the thing it exists to test")
