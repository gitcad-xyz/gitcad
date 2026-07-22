"""Minimal s-expression parser for KiCad file formats.

KiCad's .kicad_pcb/.kicad_sch/.kicad_mod are nested s-expressions. This parses
them into nested Python lists of str/float tokens — no dependencies, no
surprises. Numbers become floats when they look like numbers; everything else
stays a string (quoted strings are unescaped).
"""

from __future__ import annotations

import re

from gitcad.errors import GitcadError

_TOKEN = re.compile(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()]+')

Node = "list | str | float"


def parse(text: str):
    """Parse one top-level s-expression."""
    tokens = _TOKEN.findall(text)
    pos = 0

    def read():
        nonlocal pos
        if pos >= len(tokens):
            raise GitcadError("unexpected end of s-expression")
        tok = tokens[pos]
        pos += 1
        if tok == "(":
            node = []
            while pos < len(tokens) and tokens[pos] != ")":
                node.append(read())
            if pos >= len(tokens):
                raise GitcadError("unbalanced s-expression (missing ')')")
            pos += 1  # consume ')'
            return node
        if tok == ")":
            raise GitcadError("unbalanced s-expression (stray ')')")
        return _atom(tok)

    node = read()
    return node


def _atom(tok: str):
    if tok.startswith('"'):
        return tok[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    try:
        return float(tok)
    except ValueError:
        return tok


def find_all(node, tag: str):
    """All direct children of ``node`` that are lists starting with ``tag``."""
    return [c for c in node if isinstance(c, list) and c and c[0] == tag]


def find_one(node, tag: str):
    matches = find_all(node, tag)
    return matches[0] if matches else None


def value_of(node, tag: str, index: int = 1, default=None):
    """The nth value of a child list ``(tag v1 v2 ...)``, or default."""
    child = find_one(node, tag)
    if child is None or len(child) <= index:
        return default
    return child[index]
