"""The live channel between a working agent and the watching human.

An agent building a design is otherwise invisible until it writes a file. This
is the other half: an append-only event log the agent narrates into, and the
viewer tails. It answers three questions a person watching wants answered —

  * what is being worked on RIGHT NOW (and which instance in the assembly),
  * what just happened (a running commentary, newest last),
  * is anything waiting on ME.

Design rules, from the project's charter:

  * The log is **disposable evidence, not source** (ADR-0004). It lives under
    ``.gitcad/`` and is never committed. Deleting it loses nothing.
  * It is **append-only JSONL**, so a reader can tail it by byte offset and a
    crash mid-write costs at most the last line.
  * Event content is **data, never instructions** (ADR-0006/0007). The viewer
    renders it as text; nothing here is executed.

The question/answer loop is deliberately the same mechanism: ``ask`` appends a
``question`` event and blocks polling for the matching ``answer``, which the
viewer POSTs when the human clicks. No socket, no daemon, no state outside the
file — so it works the same whether the agent, the viewer, or both restart.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

__all__ = ["Activity", "session_dir", "SESSION_FILE", "narrate_to", "note"]

SESSION_FILE = "activity.jsonl"

# The ambient sink. Build code calls `note(...)`; if nothing has opted in, that
# is a no-op with no import of this module's machinery and no file touched.
# Narration must never be a dependency of building — a design has to build
# identically with nobody watching.
_SINK: "Activity | None" = None


def narrate_to(root: Path | str | None) -> "Activity | None":
    """Point ambient narration at a project (or ``None`` to switch it off)."""
    global _SINK
    _SINK = None if root is None else Activity(root)
    return _SINK


def note(kind: str = "status", **fields) -> None:
    """Narrate, if anyone is listening.

    NEVER raises, and deliberately swallows everything rather than a chosen
    list of exception types. Broad catches usually hide bugs; here the opposite
    is true — a design must build identically whether or not someone is
    watching, so a full disk, a read-only tree or an unserialisable field has
    to cost the build nothing. Narration is never load-bearing.
    """
    if _SINK is None:
        return
    try:
        _SINK._append(kind, **fields)
    except Exception:                          # noqa: BLE001 - see docstring
        pass


def session_dir(start: Path | str = ".") -> Path:
    """``<git root>/.gitcad`` when there is one, else ``<start>/.gitcad``.

    Anchoring on the repo root means the agent and the viewer agree on the path
    without being told it, whichever subdirectory each was started from.
    """
    p = Path(start).resolve()
    if p.is_file():
        p = p.parent
    for cand in (p, *p.parents):
        if (cand / ".git").exists():
            return cand / ".gitcad"
    return p / ".gitcad"


class Activity:
    """Append-only narration of what an agent is doing, for a live viewer."""

    def __init__(self, root: Path | str = ".") -> None:
        self.dir = session_dir(root)
        self.path = self.dir / SESSION_FILE

    # -- writing (the agent's side) ------------------------------------------

    def _append(self, kind: str, **fields) -> dict:
        self.dir.mkdir(parents=True, exist_ok=True)
        event = {"t": time.time(), "kind": kind, "pid": os.getpid(), **fields}
        line = json.dumps(event, ensure_ascii=False, sort_keys=True)
        with open(self.path, "a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")
        return event

    def status(self, text: str, *, file: str | None = None,
               instance: str | None = None, feature: str | None = None) -> dict:
        """Narrate a step. ``instance`` names the assembly member to highlight."""
        return self._append("status", text=text, file=file, instance=instance,
                            feature=feature)

    def working(self, instance: str, *, text: str | None = None,
                file: str | None = None) -> dict:
        """Mark one assembly instance as the thing being worked on."""
        return self._append("status", text=text or f"working on {instance}",
                            file=file, instance=instance)

    def done(self, text: str = "done", **fields) -> dict:
        return self._append("done", text=text, **fields)

    def problem(self, text: str, **fields) -> dict:
        """Something went wrong. Rendered distinctly; does not stop the log."""
        return self._append("problem", text=text, **fields)

    def ask(self, text: str, options: list[str] | None = None, *,
            timeout: float = 900.0, poll: float = 0.4) -> str | None:
        """Ask the watching human a question and BLOCK until they answer.

        Returns the chosen string, or ``None`` on timeout — a timeout is a real
        answer ("nobody was watching"), and the caller must decide what to do
        with it rather than assume consent.
        """
        qid = uuid.uuid4().hex[:12]
        self._append("question", id=qid, text=text, options=list(options or []))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for ev in self.read():
                if ev.get("kind") == "answer" and ev.get("id") == qid:
                    return ev.get("choice")
            time.sleep(poll)
        self._append("problem", text=f"question timed out unanswered: {text}",
                     id=qid)
        return None

    def answer(self, qid: str, choice: str) -> dict:
        """Record a human's answer (the viewer calls this via POST /api/answer)."""
        return self._append("answer", id=qid, choice=choice)

    # -- reading (the viewer's side) -----------------------------------------

    def read(self, since: int = 0) -> list[dict]:
        """Events from index ``since`` on. A partial final line is skipped —
        the writer may be mid-append, and it will be complete next poll."""
        try:
            raw = self.path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            return []
        out = []
        for i, line in enumerate(raw.splitlines()):
            if i < since or not line.strip():
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue                       # torn last line; retry next poll
            ev["seq"] = i + 1
            out.append(ev)
        return out

    def state(self, since: int = 0) -> dict:
        """What the viewer needs in one shot: new events, the currently active
        instance, any question still waiting on a human, and ``idle_s`` — how
        long the channel has been silent. ``active`` stays exact (only ``done``
        clears it); ``idle_s`` is what lets a page stop calling a crashed
        agent "working"."""
        every = self.read(0)
        events = [e for e in every if e["seq"] > since]
        active = None
        for ev in every:
            if ev.get("kind") == "status" and ev.get("instance"):
                active = {"instance": ev["instance"], "file": ev.get("file"),
                          "text": ev.get("text"), "t": ev.get("t")}
            elif ev.get("kind") == "done":
                active = None
        answered = {e.get("id") for e in every if e.get("kind") == "answer"}
        pending = next((e for e in reversed(every)
                        if e.get("kind") == "question"
                        and e.get("id") not in answered), None)
        last_t = every[-1].get("t") if every else None
        idle = (max(0.0, time.time() - last_t)
                if isinstance(last_t, (int, float)) else None)
        return {"events": events, "seq": len(every), "active": active,
                "pending": pending, "idle_s": idle}
