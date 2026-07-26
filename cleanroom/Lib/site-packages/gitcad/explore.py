"""gitcad-explore — the branch scoreboard (ADR-0016's exploration half).

Spawn N design variants as branches, then judge them all by the same
gates: the review check-delta against base (violations introduced/fixed)
and, when the branch carries ``requirements.reqs``, the full executable
requirements suite run in a throwaway worktree of that branch. Output is
a table — the design-space comparison incumbent tools cannot make
because their files cannot branch.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from gitcad.review import review_range


def _git(repo: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", repo, *args],
                          capture_output=True, text=True)


def _branches(repo: str, base: str) -> list[str]:
    proc = _git(repo, "branch", "--format=%(refname:short)")
    return [b.strip() for b in proc.stdout.splitlines()
            if b.strip() and b.strip() != base]


def _requirements_in(repo: str, branch: str) -> str | None:
    proc = _git(repo, "show", f"{branch}:requirements.reqs")
    return proc.stdout if proc.returncode == 0 else None


def score_branches(repo: str, base: str,
                   branches: list[str] | None = None) -> dict:
    from gitcad.requirements import verify

    rows = []
    for branch in (branches or _branches(repo, base)):
        row: dict = {"branch": branch}
        review = review_range(repo, base, branch)
        row["gate"] = "PASS" if review["gate_ok"] else "FAIL"
        row["introduced"] = review["summary"]["introduced"]
        row["fixed"] = review["summary"]["fixed"]
        row["files_changed"] = review["summary"]["changed"]

        reqs_text = _requirements_in(repo, branch)
        if reqs_text is not None:
            with tempfile.TemporaryDirectory() as td:
                wt = str(Path(td) / "wt")
                added = _git(repo, "worktree", "add", "--detach", wt, branch)
                if added.returncode == 0:
                    try:
                        report = verify(reqs_text, wt)
                        row["requirements"] = (
                            f"{report['summary']['pass']}/"
                            f"{len(report['requirements'])} pass")
                        row["requirements_ok"] = report["ok"]
                    finally:
                        _git(repo, "worktree", "remove", "--force", wt)
                else:
                    row["requirements"] = "worktree failed"
                    row["requirements_ok"] = False
        else:
            row["requirements"] = "—"
            row["requirements_ok"] = None
        rows.append(row)

    # rank: gate pass first, then requirements ok, then most fixed, fewest introduced
    rows.sort(key=lambda r: (r["gate"] != "PASS",
                             r["requirements_ok"] is False,
                             -r["fixed"], r["introduced"], r["branch"]))
    return {"base": base, "rows": rows}


def to_markdown(scoreboard: dict) -> str:
    lines = [f"## branch scoreboard vs `{scoreboard['base']}`", "",
             "| branch | gate | introduced | fixed | files | requirements |",
             "|--------|------|-----------:|------:|------:|--------------|"]
    for r in scoreboard["rows"]:
        lines.append(f"| {r['branch']} | **{r['gate']}** | {r['introduced']} "
                     f"| {r['fixed']} | {r['files_changed']} | {r['requirements']} |")
    return "\n".join(lines) + "\n"


def main() -> None:  # pragma: no cover - CLI entrypoint
    import argparse

    ap = argparse.ArgumentParser(
        description="gitcad explore — judge N design branches by the same gates")
    ap.add_argument("branches", nargs="*",
                    help="branches to score (default: all except base)")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base", required=True)
    args = ap.parse_args()
    print(to_markdown(score_branches(args.repo, args.base,
                                     args.branches or None)))
