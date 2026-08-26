"""Render the Markdown report into terminal-friendly text.

Transforms the single Markdown source (headers, tables, bullets, code fences,
links, `code`/**bold**) into aligned, optionally ANSI-colored terminal output —
so stdout is readable while report.md stays shareable Markdown.
"""

from __future__ import annotations

import re
import shutil


class _C:
    def __init__(self, on, links=None):
        self.on = on
        self.links = on if links is None else links

    def _w(self, code, s):
        return f"\033[{code}m{s}\033[0m" if self.on else s

    def bold(self, s):
        return self._w("1", s)

    def dim(self, s):
        return self._w("2", s)

    def red(self, s):
        return self._w("31", s)

    def green(self, s):
        return self._w("32", s)

    def yellow(self, s):
        return self._w("33", s)

    def cyan(self, s):
        return self._w("36", s)

    def link(self, text, url):
        # OSC-8 hyperlink, styled underline+blue so it clearly reads as clickable.
        # Terminals without OSC-8 support still show the styled `text`.
        styled = self._w("4;94", text)
        return f"\033]8;;{url}\033\\{styled}\033]8;;\033\\" if self.links else styled


_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_CODE = re.compile(r"`([^`]+)`")


def _inline(s: str, c: _C) -> str:
    s = _LINK.sub(lambda m: c.link(m.group(1), m.group(2)), s)
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


def _cell_visible(s: str) -> str:
    """Visible text of a table cell (markdown link -> its label), for width math."""
    s = _LINK.sub(r"\1", s)
    s = _BOLD.sub(r"\1", s)
    s = _CODE.sub(r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


def _cell_render(s: str, c: _C) -> str:
    """Rendered cell: markdown link -> OSC-8 hyperlink, `code`/**bold** stripped."""
    s = re.sub(r"\s+", " ", s).strip()
    s = _LINK.sub(lambda m: c.link(m.group(1), m.group(2)), s)
    s = _BOLD.sub(r"\1", s)
    s = _CODE.sub(r"\1", s)
    return s


def _render_table(rows, c: _C, max_width: int):
    header_raw, body_raw = rows[0], rows[2:]  # rows[1] is the |---| separator
    ncol = len(header_raw)
    vh = [_cell_visible(x) for x in header_raw]
    vb = [[_cell_visible(x) for x in (r + [""] * ncol)[:ncol]] for r in body_raw]

    widths = [max([len(vh[i])] + [len(r[i]) for r in vb]) for i in range(ncol)]
    gutter = 2 * (ncol - 1)
    while sum(widths) + gutter > max_width and max(widths) > 12:
        widths[widths.index(max(widths))] -= 1

    def cell(raw, w, header):
        v = _cell_visible(raw)
        if len(v) > w:  # clip long cells (drop any link), width == w exactly
            txt = v[: w - 1] + "…"
            return c.bold(txt) if header else _tint(txt, c)
        rendered = _cell_render(raw, c)
        rendered = c.bold(rendered) if header else _tint(rendered, c)
        return rendered + " " * (w - len(v))  # pad by visible length

    def row(cells, header=False):
        cells = (cells + [""] * ncol)[:ncol]
        return "  ".join(cell(cells[i], widths[i], header) for i in range(ncol))

    lines = [row(header_raw, header=True), "  ".join("─" * widths[i] for i in range(ncol))]
    lines += [row(r) for r in body_raw]
    return lines


def to_terminal(md: str, color: bool = True, width: int = None, links: bool = None) -> str:
    c = _C(color, links)
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
        if (
            len(stripped) > 2
            and stripped[0] == "_"
            and stripped[-1] == "_"
            and stripped[1] != "_"
            and stripped[-2] != "_"
        ):
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
