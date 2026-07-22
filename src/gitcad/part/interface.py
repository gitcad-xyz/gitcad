"""The domain-neutral part interface, and the interface-semver enforcer.

The interface is what assemblies and other parts may depend on: envelope,
named frames, typed ports, informational properties (ADR-0008).

:func:`classify_change` computes the *required* semver bump between two
interfaces — the machine check that makes "patch releases cannot break you" a
guarantee instead of a convention (ADR-0009). :func:`check_release` is the CI
gate built on it.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from gitcad.errors import GitcadError
from gitcad.part.semver import BUMPS, Version

_TOL = 1e-6  # positional tolerance (mm) below which a move is float noise


@dataclass(frozen=True)
class Frame:
    """A named coordinate frame: origin + z axis + x axis (y derived)."""
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    z_axis: tuple[float, float, float] = (0.0, 0.0, 1.0)
    x_axis: tuple[float, float, float] = (1.0, 0.0, 0.0)


@dataclass(frozen=True)
class Port:
    """A typed connection point bound to a frame.

    ``type`` uses an open, namespaced vocabulary: ``mech.bolt``,
    ``elec.pin``, ``elec.connector``, ... Core standardizes the structure;
    domains extend the vocabulary (ADR-0008).
    """
    name: str
    type: str
    frame: str                      # name of a Frame in the same interface
    spec: dict = field(default_factory=dict)


@dataclass
class Interface:
    """The domain-neutral projection of a part."""
    envelope: dict | None = None    # {"origin":[x,y,z], "dx":..,"dy":..,"dz":..}
    frames: dict[str, Frame] = field(default_factory=dict)
    ports: dict[str, Port] = field(default_factory=dict)
    properties: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, port in self.ports.items():
            if port.name != name:
                raise GitcadError(f"port key {name!r} != port.name {port.name!r}")
            if port.frame not in self.frames:
                raise GitcadError(f"port {name!r} references unknown frame {port.frame!r}")

    def to_dict(self) -> dict:
        return {
            "envelope": self.envelope,
            "frames": {k: asdict(v) for k, v in sorted(self.frames.items())},
            "ports": {k: asdict(v) for k, v in sorted(self.ports.items())},
            "properties": self.properties,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Interface":
        return cls(
            envelope=d.get("envelope"),
            frames={k: Frame(tuple(v["origin"]), tuple(v["z_axis"]), tuple(v["x_axis"]))
                    for k, v in d.get("frames", {}).items()},
            ports={k: Port(v["name"], v["type"], v["frame"], dict(v.get("spec", {})))
                   for k, v in d.get("ports", {}).items()},
            properties=dict(d.get("properties", {})),
        )

    def canonical(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


# -- the semver enforcer ------------------------------------------------------

def _moved(a: Frame, b: Frame) -> bool:
    def far(p, q) -> bool:
        return any(abs(x - y) > _TOL for x, y in zip(p, q))
    return far(a.origin, b.origin) or far(a.z_axis, b.z_axis) or far(a.x_axis, b.x_axis)


def classify_change(old: Interface, new: Interface) -> tuple[str, list[str]]:
    """Required bump ('major'|'minor'|'patch') + human-readable reasons.

    Rules (ADR-0009): removed/moved frame, removed/retyped/re-specced port, or
    envelope growth → MAJOR. Added frame/port or envelope shrink → MINOR.
    Interface identical (properties may differ) → PATCH.
    """
    reasons: list[str] = []
    level = 0  # index into BUMPS

    def require(bump: str, reason: str) -> None:
        nonlocal level
        reasons.append(f"{bump.upper()}: {reason}")
        level = max(level, BUMPS.index(bump))

    for name in old.frames:
        if name not in new.frames:
            require("major", f"frame removed: {name}")
        elif _moved(old.frames[name], new.frames[name]):
            require("major", f"frame moved: {name}")
    for name in new.frames:
        if name not in old.frames:
            require("minor", f"frame added: {name}")

    for name, port in old.ports.items():
        if name not in new.ports:
            require("major", f"port removed: {name}")
            continue
        np = new.ports[name]
        if np.type != port.type:
            require("major", f"port type changed: {name} ({port.type} -> {np.type})")
        if np.spec != port.spec:
            require("major", f"port spec changed: {name}")
        if np.frame != port.frame:
            require("major", f"port re-anchored: {name} ({port.frame} -> {np.frame})")
    for name in new.ports:
        if name not in old.ports:
            require("minor", f"port added: {name}")

    if old.envelope != new.envelope:
        if old.envelope is None:
            require("minor", "envelope added")
        elif new.envelope is None:
            require("major", "envelope removed")
        else:
            grew = any(new.envelope.get(k, 0) > old.envelope.get(k, 0) + _TOL
                       for k in ("dx", "dy", "dz"))
            origin_moved = any(abs(a - b) > _TOL for a, b in
                               zip(new.envelope.get("origin", (0, 0, 0)),
                                   old.envelope.get("origin", (0, 0, 0))))
            if grew or origin_moved:
                require("major", "envelope grew or moved")
            else:
                require("minor", "envelope shrank")

    if not reasons:
        reasons.append("PATCH: interface identical")
    return BUMPS[level], reasons


def check_release(old_version: str, new_version: str,
                  old_iface: Interface, new_iface: Interface) -> list[str]:
    """The CI release gate. Returns violations (empty = release is sound).

    Rejects a version bump smaller than the interface change requires — the
    check that stops an agent (or human) shipping a copper move as a patch.
    """
    ov, nv = Version.parse(old_version), Version.parse(new_version)
    required, reasons = classify_change(old_iface, new_iface)
    actual = nv.actual_bump_from(ov)
    violations: list[str] = []
    if actual is None:
        violations.append(f"version must increase: {ov} -> {nv}")
    elif BUMPS.index(actual) < BUMPS.index(required):
        violations.append(
            f"insufficient bump: {ov} -> {nv} is {actual.upper()}, interface requires "
            f"{required.upper()} ({'; '.join(r for r in reasons if r.startswith(required.upper()))})"
        )
    return violations
