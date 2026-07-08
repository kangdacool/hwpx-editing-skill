#!/usr/bin/env python3
"""
hwpx_to_markdown.py — extract an HWPX's readable content as Markdown, so an LLM
can read/summarize the document (or so you can diff it).

Usage:
    python hwpx_to_markdown.py FILE.hwpx [OUT.md]   # no OUT → prints to stdout

Body paragraphs become text; tables become Markdown tables (a 1x1 layout frame is
inlined as plain text); footnotes/endnotes are appended inline as (각주: …) /
(미주: …); an image/equation-only cell shows [그림] / [수식]. Extraction uses the
real body text, so headers/footers and cached line layout are ignored.

Merged cells: Markdown has no cell spans, so a merged cell's text sits in its
top-left position and the spanned-over cells are blank. Requires: lxml.
"""
import argparse
import sys
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

import hwpxlib as H

P = H.P
_SKIP = (f"{P}tc", f"{P}footNote", f"{P}endNote", f"{P}fieldBegin")


def _para_text(p) -> str:
    """The paragraph's own text — excludes table-cell, footnote/endnote, field text."""
    return "".join("".join(t.itertext()) for t in p.findall(f".//{P}t")
                   if not any(a.tag in _SKIP for a in t.iterancestors())).strip()


def _cell_text(tc) -> str:
    parts = ["".join(t.itertext()) for t in tc.findall(f".//{P}t")
             if next((a for a in t.iterancestors() if a.tag == f"{P}tc"), None) is tc]
    txt = " ".join(" ".join(parts).split())
    if not txt and tc.find(f".//{P}equation") is not None:
        txt = "[수식]"
    if not txt and tc.find(f".//{P}pic") is not None:
        txt = "[그림]"
    return txt


def _table_md(tbl) -> str:
    rc = int(tbl.get("rowCnt") or 0)
    cc = int(tbl.get("colCnt") or 0)
    grid = [["" for _ in range(cc)] for _ in range(rc)]
    for tc in tbl.findall(f".//{P}tc"):
        if next((a for a in tc.iterancestors() if a.tag == f"{P}tc"), None) is not None:
            continue
        addr = tc.find(f"{P}cellAddr")
        r, c = int(addr.get("rowAddr")), int(addr.get("colAddr"))
        if r < rc and c < cc:
            grid[r][c] = _cell_text(tc).replace("|", "\\|")
    rows = []
    for i, row in enumerate(grid):
        rows.append("| " + " | ".join(row) + " |")
        if i == 0:
            rows.append("| " + " | ".join(["---"] * cc) + " |")
    return "\n".join(rows)


def _notes(p) -> str:
    out = ""
    for tag, label in ((f"{P}footNote", "각주"), (f"{P}endNote", "미주")):
        for note in p.findall(f".//{tag}"):
            txt = " ".join("".join(note.itertext()).split())
            if txt:
                out += f" ({label}: {txt})"
    return out


def to_markdown(path: str) -> str:
    """Return the document's body as Markdown."""
    H.ensure_hwpx(path)
    z = zipfile.ZipFile(path)
    blocks = []
    for name in H.section_names(z):
        root = H.etree.fromstring(z.read(name))
        for p in root.findall(f"{P}p"):  # top-level paragraphs = the body flow
            text = (_para_text(p) + _notes(p)).strip()
            if text:
                blocks.append(text)
            for tbl in p.findall(f".//{P}tbl"):
                if next((a for a in tbl.iterancestors() if a.tag == f"{P}tbl"), None) is not None:
                    continue  # nested table — rendered by its container cell
                rc = int(tbl.get("rowCnt") or 0)
                cc = int(tbl.get("colCnt") or 0)
                if rc <= 1 and cc <= 1:  # 1x1 layout frame → inline as text
                    one = tbl.find(f".//{P}tc")
                    cell = _cell_text(one) if one is not None else ""
                    if cell and not text:
                        blocks.append(cell)
                else:
                    md = _table_md(tbl).strip()
                    if md:
                        blocks.append(md)
    return "\n\n".join(blocks)


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract HWPX content as Markdown.")
    ap.add_argument("file", help="the .hwpx to read")
    ap.add_argument("out", nargs="?", help="output .md (default: print to stdout)")
    args = ap.parse_args()
    try:
        md = to_markdown(args.file)
    except H.NotHwpxError as e:
        print(str(e))
        return 2
    except FileNotFoundError:
        print(f"File not found: {args.file}")
        return 2
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(md + "\n")
        print(f"Wrote {args.out}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
