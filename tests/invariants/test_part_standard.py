"""INVARIANTS of the Part standard (ADR-0008/0009) — architecture-independent.

These are the properties the interchange contract guarantees: canonical text,
assemblies-are-parts recursion, machine-enforced interface-semver, and
reproducible lock resolution. Permanent tier.
"""

from __future__ import annotations

import pytest

from gitcad.errors import GitcadError
from gitcad.part import (
    Assembly,
    Frame,
    Interface,
    Lockfile,
    PartManifest,
    Port,
    Version,
    Workspace,
    check_release,
    classify_change,
    resolve,
    satisfies,
)

pytestmark = pytest.mark.invariant


def _iface(**kw) -> Interface:
    base = dict(
        envelope={"origin": [0, 0, 0], "dx": 30, "dy": 20, "dz": 1.6},
        frames={"origin": Frame(), "mnt_1": Frame(origin=(3, 3, 0)), "mnt_2": Frame(origin=(27, 17, 0))},
        ports={"mnt_1": Port("mnt_1", "mech.bolt", "mnt_1", {"thread": "M3"}),
               "mnt_2": Port("mnt_2", "mech.bolt", "mnt_2", {"thread": "M3"})},
        properties={"mass_g": 4.2},
    )
    base.update(kw)
    return Interface(**base)


def _part(version="1.0.0", iface=None) -> PartManifest:
    return PartManifest(id="prt_0000000000000001", name="board", domain="ecad",
                        version=version, interface=iface or _iface())


# -- canonical text -----------------------------------------------------------

def test_manifest_roundtrip_is_canonical() -> None:
    p = _part()
    text = p.dumps()
    assert PartManifest.loads(text).dumps() == text
    assert p.dumps() == text
    assert PartManifest.loads(text).content_hash() == p.content_hash()


def test_port_must_reference_existing_frame() -> None:
    with pytest.raises(GitcadError):
        Interface(frames={}, ports={"p": Port("p", "mech.bolt", "nowhere")})


# -- interface-semver enforcement --------------------------------------------

def test_identical_interface_requires_patch_only() -> None:
    bump, _ = classify_change(_iface(), _iface())
    assert bump == "patch"


def test_property_change_is_patch() -> None:
    bump, _ = classify_change(_iface(), _iface(properties={"mass_g": 5.0}))
    assert bump == "patch"


def test_added_port_is_minor() -> None:
    new = _iface()
    new.frames["usb"] = Frame(origin=(15, 0, 0))
    new.ports["usb"] = Port("usb", "elec.connector", "usb", {"std": "USB-C"})
    assert classify_change(_iface(), new)[0] == "minor"


def test_removed_port_is_major() -> None:
    new = _iface()
    del new.ports["mnt_2"]
    assert classify_change(_iface(), new)[0] == "major"


def test_moved_frame_is_major() -> None:
    new = _iface()
    new.frames["mnt_1"] = Frame(origin=(4, 3, 0))  # hole moved 1mm
    assert classify_change(_iface(), new)[0] == "major"


def test_envelope_growth_is_major_shrink_is_minor() -> None:
    grown = _iface(envelope={"origin": [0, 0, 0], "dx": 31, "dy": 20, "dz": 1.6})
    shrunk = _iface(envelope={"origin": [0, 0, 0], "dx": 29, "dy": 20, "dz": 1.6})
    assert classify_change(_iface(), grown)[0] == "major"
    assert classify_change(_iface(), shrunk)[0] == "minor"


def test_release_gate_rejects_underbump() -> None:
    """The check that stops shipping a copper move as a patch."""
    new = _iface()
    new.frames["mnt_1"] = Frame(origin=(4, 3, 0))
    violations = check_release("1.0.0", "1.0.1", _iface(), new)
    assert violations and "insufficient bump" in violations[0]
    assert check_release("1.0.0", "2.0.0", _iface(), new) == []
    assert check_release("1.0.0", "1.0.0", _iface(), _iface())  # must increase


# -- constraints --------------------------------------------------------------

def test_malformed_constraint_raises() -> None:
    with pytest.raises(GitcadError):
        satisfies("1.4.2", "^1.4")  # shorthand not allowed: full MAJOR.MINOR.PATCH only


def test_caret_tilde_exact_star() -> None:
    assert satisfies("1.4.2", "^1.4.0")
    assert satisfies("1.9.9", "^1.4.0")
    assert not satisfies("2.0.0", "^1.4.0")
    assert satisfies("0.2.5", "^0.2.1")
    assert not satisfies("0.3.0", "^0.2.1")   # 0.x: minor is breaking
    assert satisfies("1.4.9", "~1.4.2")
    assert not satisfies("1.5.0", "~1.4.2")
    assert satisfies("1.4.2", "1.4.2")
    assert satisfies("9.9.9", "*")


# -- assemblies are parts (recursion) ----------------------------------------

def test_assembly_is_a_part_and_nests() -> None:
    board = _part()
    asm = Assembly("product")
    asm.add("b1", board, translate=(10, 10, 5))
    manifest = asm.to_manifest("prt_00000000000000aa", "0.1.0")
    assert manifest.domain == "assembly"
    assert manifest.deps == {board.id: "^1.0.0"}
    # envelope derived from placed instance
    assert manifest.interface.envelope["dx"] == pytest.approx(30)
    # ...and the assembly nests inside another assembly with no special cases
    outer = Assembly("system")
    outer.add("p1", manifest)
    outer_manifest = outer.to_manifest("prt_00000000000000bb")
    assert outer_manifest.deps == {manifest.id: "^0.1.0"}


# -- lockfile -----------------------------------------------------------------

def _workspace() -> tuple[Workspace, PartManifest]:
    ws = Workspace()
    for v in ("1.0.0", "1.4.2", "2.0.0"):
        ws.add(_part(version=v))
    consumer = PartManifest(id="prt_00000000000000cc", name="asm", domain="assembly",
                            version="0.1.0", deps={"prt_0000000000000001": "^1.0.0"})
    return ws, consumer


def test_resolution_picks_highest_compatible_and_is_deterministic() -> None:
    ws, consumer = _workspace()
    lock = resolve(consumer, ws)
    assert lock.locks["prt_0000000000000001"]["version"] == "1.4.2"  # not 2.0.0
    assert resolve(consumer, ws).dumps() == lock.dumps()


def test_lock_verify_catches_content_drift() -> None:
    ws, consumer = _workspace()
    lock = resolve(consumer, ws)
    assert lock.verify(ws) == []
    tampered = Lockfile.loads(lock.dumps())
    tampered.locks["prt_0000000000000001"]["content"] = "blake2b:deadbeef"
    assert tampered.verify(ws) == ["hash-mismatch:prt_0000000000000001@1.4.2"]


def test_unresolvable_constraint_raises() -> None:
    ws, consumer = _workspace()
    consumer.deps["prt_0000000000000001"] = "^3.0.0"
    with pytest.raises(GitcadError):
        resolve(consumer, ws)


def test_caret_zero_zero_is_exact() -> None:
    """^0.0.z matches only itself (npm/cargo convention; reviewed 2026-07-22)."""
    assert satisfies("0.0.3", "^0.0.3")
    assert not satisfies("0.0.4", "^0.0.3")


def test_centered_envelope_shrink_is_minor() -> None:
    """A shrink strictly inside the old box is MINOR even though the origin
    moved — containment semantics (reviewed 2026-07-22)."""
    old = _iface(envelope={"origin": [0, 0, 0], "dx": 10, "dy": 10, "dz": 10})
    new = _iface(envelope={"origin": [1, 1, 1], "dx": 8, "dy": 8, "dz": 8})
    assert classify_change(old, new)[0] == "minor"


def test_mate_failures_do_not_swallow_later_mates() -> None:
    """A ghost-instance mate must not suppress checking of subsequent mates
    (reviewed 2026-07-22)."""
    board = _part()
    asm = Assembly("t")
    asm.add("b", board)
    asm.mate("ghost.mnt_1", "b.mnt_1")          # unknown instance
    asm.mate("b.mnt_1", "b.mnt_2")              # real mate, 30mm apart
    report = asm.validate()
    assert any(v.startswith("mate:unknown-instance") for v in report.violations)
    assert any(v.startswith("mate:position-mismatch") for v in report.violations)
