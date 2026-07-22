"""Golden: exploded views (ADR-0014) — a projection, never a model edit.

Runs on the null kernel: the spec, apply, and auto-explode derivation are
pure geometry bookkeeping. The occt-marked test proves the drawing follows.
"""

import pytest

from gitcad.errors import GitcadError
from gitcad.part import (Assembly, ExplodedView, Frame, Interface, Port,
                         auto_explode, bought_part)


def _part(pid: str, *, port_axis=None):
    iface = Interface()
    iface.envelope = {"dx": 10, "dy": 10, "dz": 5}
    if port_axis:
        iface.frames = {"origin": Frame(), "m": Frame(z_axis=port_axis)}
        iface.ports = {"p": Port(name="p", type="mech.bolt", frame="m")}
    return bought_part(f"MPN-{pid}", "ACME", f"prt_{pid}", interface=iface)


def _asm():
    asm = Assembly("stack")
    asm.add("base", _part("base", port_axis=(0, 0, 1)))
    asm.add("mid", _part("mid", port_axis=(0, 0, 1)), translate=(0, 0, 5))
    asm.add("top", _part("topp", port_axis=(1, 0, 0)), translate=(0, 0, 10))
    asm.mate("base.p", "mid.p")
    asm.mate("base.p", "top.p")
    return asm


def test_spec_roundtrip_is_canonical():
    view = ExplodedView(assembly="stack", offsets={"mid": (0, 0, 30)})
    again = ExplodedView.loads(view.dumps())
    assert again.dumps() == view.dumps()
    assert again.offsets["mid"] == (0, 0, 30)


def test_apply_shifts_transforms_without_touching_source():
    asm = _asm()
    view = ExplodedView(assembly="stack", offsets={"mid": (0, 0, 30)})
    exploded = view.apply(asm)
    assert exploded.instances["mid"].translate == (0, 0, 35)
    assert exploded.instances["base"].translate == (0, 0, 0)
    assert asm.instances["mid"].translate == (0, 0, 5)   # source untouched


def test_apply_rejects_unknown_instances():
    view = ExplodedView(assembly="stack", offsets={"ghost": (0, 0, 1)})
    with pytest.raises(GitcadError, match="unknown instances"):
        view.apply(_asm())


def test_auto_explode_derives_from_mate_graph():
    view = auto_explode(_asm(), spacing=30.0)
    # base is the most-mated instance -> depth 0, no offset
    assert "base" not in view.offsets
    # mid and top are depth 1; each moves along ITS mated port frame z axis
    assert view.offsets["mid"] == (0.0, 0.0, 30.0)
    assert view.offsets["top"] == (30.0, 0.0, 0.0)
    # deterministic: same input, same text
    assert auto_explode(_asm(), spacing=30.0).dumps() == view.dumps()


def test_auto_explode_stacks_unmated_instances():
    asm = _asm()
    asm.add("loose", _part("loose"))
    view = auto_explode(asm, spacing=10.0)
    assert view.offsets["loose"] == (0.0, 0.0, 20.0)   # deepest(1)+1 along +Z


@pytest.mark.occt
def test_assembly_drawing_follows_exploded_view():
    from gitcad.drawing.assembly import assembly_drawing
    from gitcad.kernel.occt import OcctKernel

    kern = OcctKernel()
    asm = _asm()
    view = ExplodedView(assembly="stack", offsets={"top": (60, 0, 0)})
    plain = assembly_drawing(asm, kern)
    boom = assembly_drawing(asm, kern, exploded=view)
    # the exploded drawing is wider in WORLD mm (sheet mm / scale): top's
    # envelope moved +60 in x (auto-scale shrinks the sheet placement, so
    # compare model-space extents, not sheet-space)
    def x_extent(d):
        xs = [x for v in d.views for p in v.hidden + v.visible for x, _ in p]
        return (max(xs) - min(xs)) / d.scale
    assert x_extent(boom) == pytest.approx(x_extent(plain) + 60, rel=1e-6)
    assert asm.instances["top"].translate == (0, 0, 10)   # still untouched
