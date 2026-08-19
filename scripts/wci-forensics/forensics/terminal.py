"""Render the Markdown report into terminal-friendly text.

Transforms the single Markdown source (headers, tables, bullets, code fences,
links, `code`/**bold**) into aligned, optionally ANSI-colored terminal output —
so stdout is readable while report.md stays shareable Markdown.
"""
from __future__ import annotations

import re
import shutil


class _C:
    def __init__(self, on):
        self.on = on

    def _w(self, code, s):
        return f"\033[{code}m{s}\033[0m" if self.on else s

    def bold(self, s):   return self._w("1", s)
    def dim(self, s):    return self._w("2", s)
    def red(self, s):    return self._w("31", s)
    def green(self, s):  return self._w("32", s)
    def yellow(self, s): return self._w("33", s)
    def cyan(self, s):   return self._w("36", s)


_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_CODE = re.compile(r"`([^`]+)`")


def _inline(s: str, c: _C) -> str:
    s = _LINK.sub(lambda m: f"{m.group(1)} {c.dim(m.group(2))}", s)
    s = _BOLD.sub(lambda m: c.bold(m.group(1)), s)
    s = _CODE.sub(lambda m: c.cyan(m.group(1)), s)
    return s


def _plain(s: str) -> str:
    """Strip inline markdown for width measurement / table cells."""
    s = _LINK.sub(r"\1 \2", s)
    s = _BOLD.sub(r"\1", s)
    s = _CODE.sub(r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


def _tint(line: str, c: _C) -> str:
    if not c.on:
        return line
    for tok, fn in (("FAILED", c.red), ("MISMATCH", c.red), ("PASS", c.green)):
        line = line.replace(tok, fn(tok))
    return line


def _render_table(rows, c: _C, max_width: int):
    header, body = rows[0], rows[2:]  # rows[1] is the |---| separator
    ncol = len(header)
    header = [_plain(x) for x in header]
    body = [[_plain(x) for x in (r + [""] * ncol)[:ncol]] for r in body]

    widths = [max([len(header[i])] + [len(r[i]) for r in body]) for i in range(ncol)]
    # Shrink widest columns until the table fits the terminal.
    gutter = 2 * (ncol - 1)
    while sum(widths) + gutter > max_width and max(widths) > 12:
        widths[widths.index(max(widths))] -= 1

    def clip(s, w):
        return s if len(s) <= w else s[: w - 1] + "…"

    def row(cells, bold=False):
        out = "  ".join(clip(cells[i], widths[i]).ljust(widths[i]) for i in range(ncol))
        return c.bold(out) if bold else _tint(out, c)

    lines = [row(header, bold=True), "  ".join("─" * widths[i] for i in range(ncol))]
    lines += [row(r) for r in body]
    return lines


def to_terminal(md: str, color: bool = True, width: int = None) -> str:
    c = _C(color)
    width = width or shutil.get_terminal_size(fallback=(120, 24)).columns
    src = md.splitlines()
    out = []
    i = 0
    in_code = False
    while i < len(src):
        line = src[i]
        if line.strip().startswith("```"):
            in_code = not in_code
            i += 1
            continue
        if in_code:
            out.append(line)
            i += 1
            continue
        # Table block: consecutive lines that start with '|'.
        if line.lstrip().startswith("|"):
            block = []
            while i < len(src) and src[i].lstrip().startswith("|"):
                block.append([cell.strip() for cell in src[i].strip().strip("|").split("|")])
                i += 1
            if len(block) >= 2:
                out += _render_table(block, c, width)
            continue
        stripped = line.strip()
        if (len(stripped) > 2 and stripped[0] == "_" and stripped[-1] == "_"
                and stripped[1] != "_" and stripped[-2] != "_"):
            out.append(c.dim(_inline(stripped[1:-1], c)))
        elif line.startswith("### "):
            out.append(c.bold(line[4:]))
        elif line.startswith("## "):
            t = line[3:]
            out += ["", c.bold(_tint(t, c)), c.dim("─" * min(len(_plain(t)), width))]
        elif line.startswith("# "):
            t = line[2:]
            out += [c.bold(t), c.dim("═" * min(len(_plain(t)), width))]
        elif line.lstrip().startswith("> "):
            indent = line[: len(line) - len(line.lstrip())]
            out.append(indent + c.yellow(_inline(line.lstrip()[2:], c)))
        else:
            out.append(_tint(_inline(line, c), c))
        i += 1
    return "\n".join(out)
