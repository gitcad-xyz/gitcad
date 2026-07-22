"""GOLDEN: exact interference — collisions measured, contact allowed."""

from __future__ import annotations

import pytest

from gitcad.part import check_interference

pytestmark = pytest.mark.occt


@pytest.fixture(scope="module")
def kernel():
    from gitcad.kernel.occt import OcctKernel

    return OcctKernel()


def test_overlap_is_measured_exactly(kernel) -> None:
    a = kernel.box(10, 10, 10)
    b = kernel.box(10, 10, 10)
    r = check_interference(kernel, {
        "a": (a, (0, 0, 0), 0.0),
        "b": (b, (5, 0, 0), 0.0),      # overlaps 5x10x10 = 500 mm3
    })
    assert not r.ok
    assert "overlap=500.000mm3" in r.violations[0]


def test_face_contact_is_not_a_collision(kernel) -> None:
    a = kernel.box(10, 10, 10)
    b = kernel.box(10, 10, 10)
    r = check_interference(kernel, {
        "a": (a, (0, 0, 0), 0.0),
        "b": (b, (10, 0, 0), 0.0),     # share the x=10 face exactly
    })
    assert r.ok, r.violations


def test_separated_parts_skip_expensive_boolean(kernel) -> None:
    a = kernel.box(10, 10, 10)
    b = kernel.box(10, 10, 10)
    r = check_interference(kernel, {
        "a": (a, (0, 0, 0), 0.0),
        "b": (b, (50, 0, 0), 0.0),
    })
    assert r.ok and r.checks["pairs_intersected"] == 0   # AABB pre-filter


def test_intentional_contact_pairs_can_be_ignored(kernel) -> None:
    a = kernel.box(10, 10, 10)
    b = kernel.box(10, 10, 10)
    r = check_interference(kernel, {
        "a": (a, (0, 0, 0), 0.0), "b": (b, (5, 0, 0), 0.0),
    }, ignore={frozenset({"a", "b"})})
    assert r.ok


def test_board_in_enclosure_pocket_fits(kernel) -> None:
    """The co-design scenario: a board in an enclosure pocket — fits when the
    pocket is deep enough, collides (with measured volume) when it is not."""
    enclosure = kernel.boolean("cut", kernel.box(60, 40, 12),
                               kernel.transform(kernel.box(34, 24, 4),
                                                translate=(13, 8, 8)))
    board = kernel.box(30, 20, 1.6)
    fits = check_interference(kernel, {
        "enc": (enclosure, (0, 0, 0), 0.0),
        "pcb": (board, (15, 10, 8.5), 0.0),   # inside the pocket
    })
    assert fits.ok, fits.violations
    collides = check_interference(kernel, {
        "enc": (enclosure, (0, 0, 0), 0.0),
        "pcb": (board, (15, 10, 5.0), 0.0),   # sunk 3mm into solid material
    })
    assert not collides.ok
    assert "overlap=" in collides.violations[0]
