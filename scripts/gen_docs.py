"""Generate the gitcad.xyz /docs/ site from the repo itself.

Sources of truth (never hand-duplicated):
- MCP tool reference: introspected from the live ``gitcad.mcp.REGISTRY`` —
  signatures and docstrings, so the reference cannot drift from the code.
- ADRs: rendered from ``docs/adr/*.md``.
- Quickstart: the one hand-written page, kept here.

Zero dependencies (tiny purpose-built markdown subset renderer). Deterministic
output. Run:  python scripts/gen_docs.py [outdir]   (default: build/docs)
"""

from __future__ import annotations

import html
import inspect
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STYLE = """
  :root{--bg:#0d1117;--ink:#c9d1d9;--dim:#8b949e;--acc:#58a6ff;--ok:#7ee787;--line:#21262d}
  @media (prefers-color-scheme: light){
    :root{--bg:#ffffff;--ink:#24292f;--dim:#57606a;--acc:#0969da;--ok:#1a7f37;--line:#d8dee4}
  }
  *{box-sizing:border-box;margin:0}
  body{background:var(--bg);color:var(--ink);
    font:15px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;
    max-width:760px;margin:0 auto;padding:40px 20px 80px}
  a{color:var(--acc);text-decoration:none} a:hover{text-decoration:underline}
  h1{font-size:20px;margin:8px 0 6px}
  h2{font-size:15px;font-weight:700;margin:36px 0 10px}
  h2::before{content:"## ";color:var(--dim)}
  h3{font-size:15px;font-weight:700;margin:24px 0 8px;color:var(--acc)}
  p,li{margin:6px 0} ul,ol{padding-left:24px}
  pre{border:1px solid var(--line);border-radius:6px;padding:12px 14px;margin:12px 0;overflow-x:auto}
  code{color:var(--ok)}
  pre code{color:var(--ink)}
  table{border-collapse:collapse;width:100%;font-size:14px;margin:12px 0}
  td,th{border:1px solid var(--line);padding:6px 10px;text-align:left}
  th{color:var(--dim)}
  blockquote{border-left:3px solid var(--line);padding-left:12px;color:var(--dim);margin:12px 0}
  .crumb{color:var(--dim);margin-bottom:24px}
  .crumb a{color:var(--dim)} .sig{color:var(--dim)}
  hr{border:0;border-top:1px solid var(--line);margin:32px 0}
  footer{margin-top:48px;color:var(--dim);font-size:13px;border-top:1px solid var(--line);padding-top:16px}
"""

FOOTER = ('<footer>generated from '
          '<a href="https://github.com/gitcad-xyz/gitcad">gitcad-xyz/gitcad</a>'
          ' — this page rebuilds on every push to main</footer>')


def page(title: str, body: str, crumb: str = "") -> str:
    nav = f'<div class="crumb"><a href="/">gitcad</a> / <a href="/docs/">docs</a>{crumb}</div>'
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{html.escape(title)} — gitcad</title><style>{STYLE}</style></head>'
            f'<body>{nav}{body}{FOOTER}</body></html>\n')


# -- tiny markdown subset renderer (headings, lists, tables, code, inline) ----

_INLINE = [
    (re.compile(r"\*\*(.+?)\*\*"), r"<b>\1</b>"),
    (re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)"), r"<i>\1</i>"),
    (re.compile(r"`([^`]+)`"), r"<code>\1</code>"),
    (re.compile(r"\[([^\]]+)\]\(([^)]+)\)"), r'<a href="\2">\1</a>'),
]


def _inline(text: str) -> str:
    out = html.escape(text, quote=False)
    for pat, rep in _INLINE:
        out = pat.sub(rep, out)
    return out


def md_to_html(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    in_list: str | None = None

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append(f"</{in_list}>")
            in_list = None

    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            close_list()
            block: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            out.append("<pre><code>" + html.escape("\n".join(block)) + "</code></pre>")
        elif line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|?$", lines[i + 1]):
            close_list()
            headers = [c.strip() for c in line.strip("|").split("|")]
            out.append("<table><tr>" + "".join(f"<th>{_inline(h)}</th>" for h in headers) + "</tr>")
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip("|").split("|")]
                out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in cells) + "</tr>")
                i += 1
            out.append("</table>")
            continue
        elif m := re.match(r"^(#{1,3})\s+(.*)", line):
            close_list()
            level = len(m.group(1))
            out.append(f"<h{level}>{_inline(m.group(2))}</h{level}>")
        elif re.match(r"^\s*[-*]\s+", line):
            if in_list != "ul":
                close_list()
                out.append("<ul>")
                in_list = "ul"
            out.append(f"<li>{_inline(re.sub(r'^\\s*[-*]\\s+', '', line))}</li>")
        elif re.match(r"^\s*\d+\.\s+", line):
            if in_list != "ol":
                close_list()
                out.append("<ol>")
                in_list = "ol"
            out.append(f"<li>{_inline(re.sub(r'^\\s*\\d+\\.\\s+', '', line))}</li>")
        elif line.startswith(">"):
            close_list()
            out.append(f"<blockquote>{_inline(line.lstrip('> '))}</blockquote>")
        elif line.strip() in ("---", "***"):
            close_list()
            out.append("<hr>")
        elif line.strip():
            close_list()
            out.append(f"<p>{_inline(line)}</p>")
        else:
            close_list()
        i += 1
    close_list()
    return "\n".join(out)


# -- pages --------------------------------------------------------------------

QUICKSTART = """
# gitcad docs

Agent-first, headless, git-native CAD. Models are canonical text; STEP,
drawings, and Gerbers are build artifacts.

## install

```
pip install gitcad            # headless core (pure Python)
pip install "gitcad[occt]"    # + the OCCT b-rep kernel (STEP, drawings)
pip install "gitcad[mcp]"     # + the MCP server (gitcad-mcp entrypoint)
```

Until the PyPI release lands: `pip install git+https://github.com/gitcad-xyz/gitcad`.

## a part in five calls

```
from gitcad.mcp.server import REGISTRY as tools

m = tools["model_new"]()["model"]
r = tools["feature_add"](model=m, op="box", params={"dx":60,"dy":40,"dz":8})
m = r["model"]

tools["model_validate"](model=m)          # machine-readable checks
tools["model_export"](model=m, path="part.step")
tools["model_drawing"](model=m, path="part.pdf")   # dimensioned 4-view drawing
```

## a board to fab

```
from gitcad.ecad import Board, MountingHole, export_fab

b = Board(name="blinky", outline=[(0,0),(30,0),(30,20),(0,20)])
b.mounting_holes += [MountingHole("mnt_1", 3, 3, 3.2, thread="M3")]
export_fab(b, "fab/")   # Gerber X2, Excellon (PTH+NPTH), pick-and-place
```

Every mounting hole is simultaneously fab data and a published `mech.bolt`
port in the board's derived `part.json` — the enclosure mates against it.
See the [Part standard](adr/0008-part-standard.html).

## the examples

- [bracket.py](https://github.com/gitcad-xyz/gitcad/blob/main/examples/bracket.py) — model → verify → STEP + drawing
- [blinky.py](https://github.com/gitcad-xyz/gitcad/blob/main/examples/blinky.py) — board → verify → full fab package
- [product.py](https://github.com/gitcad-xyz/gitcad/blob/main/examples/product.py) — cross-domain assembly with derived interfaces and the release gate

## reference

- [MCP tool reference](mcp.html) — every tool, generated from the code
- [Architecture decision records](adr/) — the durable spec
- [Competitive feature map](https://github.com/gitcad-xyz/gitcad/blob/main/docs/research/feature-map.md)
"""


def gen_mcp_reference() -> str:
    sys.path.insert(0, str(ROOT / "src"))
    from gitcad.mcp.server import REGISTRY

    body = ["<h1>MCP tool reference</h1>",
            "<p>The primary interface. Generated from the live registry — "
            "signatures and docs come from the code itself.</p>"]
    for name in sorted(REGISTRY):
        fn = REGISTRY[name]
        sig = str(inspect.signature(fn))
        doc = inspect.getdoc(fn) or ""
        body.append(f"<h3>{html.escape(name)}</h3>")
        body.append(f'<pre class="sig"><code>{html.escape(name + sig)}</code></pre>')
        body.append(f"<p>{_inline(doc)}</p>")
    return page("MCP tools", "\n".join(body), " / mcp")


def main(outdir: str = "build/docs") -> None:
    out = Path(outdir)
    (out / "adr").mkdir(parents=True, exist_ok=True)

    (out / "index.html").write_text(
        page("docs", md_to_html(QUICKSTART)), newline="\n", encoding="utf-8")
    (out / "mcp.html").write_text(gen_mcp_reference(), newline="\n", encoding="utf-8")

    adr_index = ["<h1>Architecture decision records</h1>",
                 "<p>The durable spec: decisions are recorded before code, and "
                 "superseded rather than edited (ADR-0001).</p>", "<ul>"]
    for md_file in sorted((ROOT / "docs" / "adr").glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        title = text.splitlines()[0].lstrip("# ").strip()
        slug = md_file.stem
        (out / "adr" / f"{slug}.html").write_text(
            page(title, md_to_html(text), f" / adr / {slug.split('-')[0]}"),
            newline="\n", encoding="utf-8")
        adr_index.append(f'<li><a href="{slug}.html">{html.escape(title)}</a></li>')
    adr_index.append("</ul>")
    (out / "adr" / "index.html").write_text(
        page("ADRs", "\n".join(adr_index), " / adr"), newline="\n", encoding="utf-8")

    pages = len(list(out.rglob("*.html")))
    print(f"generated {pages} pages -> {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "build/docs")
