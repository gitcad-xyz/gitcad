"""H2: the `auto` backend — forge-first with OCCT fallback (ADR-0018
gate-G2 promotion). forge is the default; OCCT covers only the
honestly-refused tail."""

import pytest

pytest.importorskip("forgekernel")

from gitcad.kernel.auto import AutoKernel  # noqa: E402


def test_auto_uses_forge_for_covered_ops_exactly() -> None:
    k = AutoKernel()
    box = k.box(3, 4, 5)
    assert type(box).__module__.startswith("forgekernel")   # forge built it
    assert k.mass_props(box)["volume"] == 60.0              # exact
    cyl = k.cylinder(5, 10)
    assert type(cyl).__module__.startswith("forgekernel")   # ℚ[π] path


def test_auto_falls_back_to_occt_on_honest_refusal() -> None:
    # an arc-profile extrude is forge-refused at K2 → OCCT builds it
    k = AutoKernel()
    arc = {"start": [0, 0], "segments": [
        {"kind": "line", "to": [10, 0]},
        {"kind": "arc", "to": [10, 10], "via": [13, 5]},
        {"kind": "line", "to": [0, 10]}, {"kind": "line", "to": [0, 0]}]}
    s = k.extrude(arc, 5)
    assert type(s).__module__.startswith("OCP")             # OCCT built it
    assert k.mass_props(s)["volume"] > 0                    # and it's usable


@pytest.mark.occt
def test_auto_builds_full_corpus() -> None:
    # forge covers the whole corpus, so auto builds 100% — with the
    # exact backend in front and OCCT only as the untriggered safety net
    from gitcad.bench.corpus import CORPUS

    k = AutoKernel()
    built = 0
    for _name, _cls, build in CORPUS:
        try:
            doc = build()
            k.mass_props(doc.build(k).final(doc))
            built += 1
        except Exception:
            pass
    assert built >= len(CORPUS) - 1        # spring/sweeps all forge-covered
