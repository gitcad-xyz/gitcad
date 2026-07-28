"""The detached project viewer: a process that OUTLIVES the agent session.

The field failure this module exists for: the MCP server ran the viewer as a
daemon thread of its own process, so the viewer died the moment the session
ended — and the agent, taught nothing better, also shut it down "when the work
was over". The contract now is:

* the viewer is a DETACHED OS process (Windows: ``DETACHED_PROCESS |
  CREATE_NEW_PROCESS_GROUP``; POSIX: ``start_new_session=True``) with stdio
  pointed at devnull/a log file — a stdio-MCP parent's pipes are never
  inherited, so closing them can neither kill nor block the viewer;
* ONE viewer per project, discovered through ``.gitcad/viewer.json``
  ({pid, port, url, root, default, started}). Re-opening probes the recorded
  server over HTTP (``/api/health`` — the pid is never trusted, so a stale
  file or a recycled port can't masquerade) and reuses it;
* NOTHING stops it implicitly. The only stops are the explicit
  ``viewer_stop`` MCP tool and ``gitcad-view --stop``, both of which POST
  ``/api/shutdown``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

__all__ = ["discovery_path", "read_state", "probe", "ensure_viewer",
           "stop_viewer", "launch_browser", "main"]

DISCOVERY = "viewer.json"


def _gitcad_dir(root: str | Path) -> Path:
    from gitcad.activity import session_dir

    return session_dir(root)


def discovery_path(root: str | Path) -> Path:
    """``<project>/.gitcad/viewer.json`` — where a running viewer registers."""
    return _gitcad_dir(root) / DISCOVERY


def read_state(root: str | Path) -> dict | None:
    try:
        st = json.loads(discovery_path(root).read_text(encoding="utf-8"))
        return st if isinstance(st, dict) else None
    except (OSError, ValueError):
        return None


def probe(state: dict | None, timeout: float = 3.0) -> dict | None:
    """Is the recorded viewer actually alive AND ours? HTTP is the only truth:
    a pid can be stale or recycled, so it is checked by asking the server who
    it is (``/api/health`` reports its root), never by signalling the pid."""
    if not state or not state.get("port"):
        return None
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{state['port']}/api/health",
                timeout=timeout) as r:
            h = json.load(r)
    except Exception:                  # noqa: BLE001 - any failure = not ours
        return None
    if not h.get("ok"):
        return None
    try:
        if Path(h.get("root", "")).resolve() != Path(state.get("root", "")).resolve():
            return None                # recycled port, someone else's server
    except OSError:
        return None
    return h


def _spawn(root: Path, port: int, review_base: str | None) -> subprocess.Popen:
    """Start the daemon truly detached. stdio is NOT inherited: stdin/stdout go
    to devnull and stderr to ``.gitcad/viewer.log`` — a stdio-MCP parent's
    JSON-RPC pipes stay untouched, and the parent's exit is invisible here."""
    log = _gitcad_dir(root) / "viewer.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "gitcad.viewer.daemon", str(root),
           "--port", str(port)]
    if review_base:
        cmd += ["--review", review_base]
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                    "cwd": str(root), "close_fds": True}
    with open(log, "ab") as logf:
        kwargs["stderr"] = logf
        if os.name == "nt":
            flags = (subprocess.DETACHED_PROCESS
                     | subprocess.CREATE_NEW_PROCESS_GROUP)
            try:
                # breakaway too, when allowed: a host that wraps the MCP server
                # in a kill-on-close job object must not reap the viewer
                return subprocess.Popen(
                    cmd, creationflags=flags | 0x01000000,  # CREATE_BREAKAWAY_FROM_JOB
                    **kwargs)
            except OSError:
                return subprocess.Popen(cmd, creationflags=flags, **kwargs)
        kwargs["start_new_session"] = True
        return subprocess.Popen(cmd, **kwargs)


def ensure_viewer(root: str | Path, port: int = 0,
                  review_base: str | None = None,
                  timeout_s: float = 40.0) -> tuple[dict, bool]:
    """The idempotent open: ``(state, reused)``. A healthy recorded viewer is
    reused (same URL); otherwise the stale record is cleared and a fresh
    detached daemon is spawned and waited for."""
    root = Path(root).resolve()
    st = read_state(root)
    if st and probe(st):
        return st, True
    dpath = discovery_path(root)
    try:
        dpath.unlink()                 # stale record (dead pid / foreign port)
    except OSError:
        pass
    proc = _spawn(root, port, review_base)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        st = read_state(root)
        if st and probe(st):
            return st, False
        if proc.poll() is not None:
            raise ValueError(
                f"viewer daemon exited with code {proc.returncode} — "
                f"see {_gitcad_dir(root) / 'viewer.log'}: {_log_tail(root)}")
        time.sleep(0.15)
    raise ValueError(f"viewer daemon did not come up within "
                     f"{float(timeout_s):.0f}s "
                     f"— see {_gitcad_dir(root) / 'viewer.log'}")


def _log_tail(root: Path, n: int = 400) -> str:
    try:
        return (_gitcad_dir(root) / "viewer.log").read_text(
            encoding="utf-8", errors="replace")[-n:].strip()
    except OSError:
        return ""


def stop_viewer(root: str | Path) -> dict:
    """The ONE explicit stop: POST /api/shutdown to the project's viewer and
    clear its discovery record. Never called implicitly by anything."""
    root = Path(root).resolve()
    st = read_state(root)
    alive = probe(st)
    dpath = discovery_path(root)
    if not alive:
        try:
            dpath.unlink()             # clear a stale record either way
        except OSError:
            pass
        return {"stopped": False, "reason": "no viewer running for "
                                            f"{root} (nothing to stop)"}
    req = urllib.request.Request(
        f"http://127.0.0.1:{st['port']}/api/shutdown", method="POST", data=b"")
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:                  # noqa: BLE001 - it may die mid-response
        pass
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline and probe(st, timeout=1.0):
        time.sleep(0.1)
    try:
        dpath.unlink()
    except OSError:
        pass
    return {"stopped": True, "url": st.get("url"), "pid": st.get("pid")}


def launch_browser(url: str) -> bool:
    """Open the user's browser on the viewer — the viewer is FOR the human, so
    opening it is part of opening it. Returns whether a launch was dispatched
    (headless machines return False; the URL in the tool result is the
    fallback). ``GITCAD_NO_BROWSER=1`` suppresses it (tests, CI)."""
    if os.environ.get("GITCAD_NO_BROWSER") == "1":
        return False
    import webbrowser

    try:
        if webbrowser.open(url):
            return True
    except Exception:                  # noqa: BLE001 - fall through to startfile
        pass
    if os.name == "nt":
        try:
            os.startfile(url)          # noqa: S606 - the Windows fallback
            return True
        except OSError:
            return False
    return False


def main() -> None:  # pragma: no cover - daemon entrypoint
    """``python -m gitcad.viewer.daemon <root>`` — bind, register, serve until
    an explicit /api/shutdown. Run detached by :func:`ensure_viewer`."""
    import argparse

    ap = argparse.ArgumentParser(
        description="gitcad detached project viewer daemon")
    ap.add_argument("root")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--review", default=None)
    args = ap.parse_args()

    from gitcad.viewer.server import serve

    root = Path(args.root).resolve()
    httpd = serve(str(root), port=args.port, review_base=args.review)
    port = httpd.server_address[1]
    handler = httpd.RequestHandlerClass
    dpath = discovery_path(root)
    dpath.parent.mkdir(parents=True, exist_ok=True)
    state = {"pid": os.getpid(), "port": port,
             "url": f"http://127.0.0.1:{port}/",
             "root": str(handler.project_root or root),
             "default": _rel(handler.path_watched,
                             handler.project_root or root),
             "started": time.time()}
    dpath.write_text(json.dumps(state, indent=1), encoding="utf-8")
    try:
        httpd.serve_forever()
    finally:
        cur = read_state(root)
        if cur and cur.get("pid") == os.getpid():
            try:
                dpath.unlink()
            except OSError:
                pass


def _rel(p: Path, root: Path) -> str:
    try:
        return p.relative_to(root).as_posix()
    except ValueError:
        return p.name


if __name__ == "__main__":  # pragma: no cover
    main()
