# -*- coding: utf-8 -*-
"""Render-based layout audit for an HWPX document.

Structural checks (well-formed XML, id collisions, cell-vs-source diffs) all pass
on defects that only a RENDER shows. This script catches that class:

  1. cells whose content wrapped        e.g. "4,70" / "1" after adding a comma
  2. near-empty pages                   a table footnote stranded on its own page
  3. blank pages                        nothing but the page number
  4. table-of-contents page numbers     TOC says 42, the caption is on 44
  5. cell width sums (structural)       a bad geometry edit 한글 will reject

Usage
-----
    python audit_layout.py FILE.hwpx [--pdf OUT.pdf] [--sparse 320]

With no ``--pdf`` the script renders the file itself through 한글 COM
(Windows + 한컴오피스 required) into a temporary PDF. Pass ``--pdf`` to reuse a
render you already have, or to audit on a machine without 한글.

Exit code is non-zero when any check reports a finding, so it can gate a build.
"""
import argparse
import os
import re
import sys
import tempfile
import zipfile

from lxml import etree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hwpxlib
from hwpxlib import P

PAGENO = re.compile(r"\s*[-–]\s*([0-9]+|[ivxlcdm]+)\s*[-–]\s*")
# A number can never end in a comma group of 1-2 digits — if a rendered line
# does, 한글 broke the number across lines inside a too-narrow cell.
WRAPPED_NUM = re.compile(r"(?<![\d,])\d{1,3},\d{1,2}$")


def render_pdf(hwpx_path, pdf_path):
    """Render through 한글 COM. Kept minimal on purpose — if you already have a
    render helper, pass --pdf instead."""
    import win32com.client as win32
    hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
    try:
        hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
    except Exception:
        pass
    hwp.Open(os.path.abspath(hwpx_path), "HWPX", "forceopen:true")
    hwp.SaveAs(os.path.abspath(pdf_path), "PDF")
    hwp.Quit()


def page_labels(doc):
    """{pdf_index: printed page number} read from the footer line."""
    out = {}
    for i, page in enumerate(doc):
        for line in page.get_text().splitlines():
            m = PAGENO.fullmatch(line)
            if m:
                v = m.group(1)
                out[i] = int(v) if v.isdigit() else v
                break
    return out


def check_wrapped_cells(doc):
    """Lines that are a broken-in-half number (the cell is too narrow)."""
    hits = []
    for i, page in enumerate(doc):
        lines = [ln.strip() for ln in page.get_text().splitlines()]
        for k, ln in enumerate(lines[:-1]):
            if WRAPPED_NUM.search(ln) and re.fullmatch(r"\d{1,3}", lines[k + 1]):
                hits.append((i + 1, "%s | %s  ->  %s%s"
                             % (ln, lines[k + 1], ln, lines[k + 1])))
    return hits


def check_sparse_pages(doc, threshold):
    """Pages with almost no content and no picture. A table footnote pushed onto
    its own page looks exactly like this, and reads as a mistake."""
    hits = []
    for i, page in enumerate(doc):
        text = page.get_text().strip()
        body = "\n".join(ln for ln in text.splitlines() if not PAGENO.fullmatch(ln))
        if len(body.strip()) < threshold and not page.get_images():
            head = body.strip().replace("\n", " ")[:60]
            kind = "blank" if not body.strip() else "sparse"
            hits.append((i + 1, "%s (%d chars) %s" % (kind, len(body.strip()), head)))
    return hits


def check_toc_pages(doc, labels):
    """TOC lines that end in a page number, checked against where the caption
    actually landed. Only entries of the form '[Table 3] ...  30' are checked —
    those are unambiguous."""
    body_start = next((i for i, v in labels.items() if isinstance(v, int)), 0)
    hits = []
    seen = set()
    for i in range(0, body_start):
        text = re.sub(r"\s+", " ", doc[i].get_text())
        for m in re.finditer(r"\[(Table|Figure)\s*(\d+)\][^\[]*?(\d{1,3})(?=\s|$)", text):
            kind, num, claimed = m.group(1), m.group(2), int(m.group(3))
            if (kind, num) in seen:
                continue
            seen.add((kind, num))
            actual = None
            for j in range(body_start, doc.page_count):
                if re.search(r"%s %s\." % (kind, num),
                             re.sub(r"\s+", " ", doc[j].get_text())):
                    actual = labels.get(j)
                    break
            if actual is not None and actual != claimed:
                hits.append((i + 1, "[%s %s] 목차 %d != 실제 %s" % (kind, num, claimed, actual)))
    return hits


def check_table_widths(hwpx_path):
    """Cell widths must sum to the table width in every row, or 한글 refuses the
    file. Purely structural, so it runs without a render."""
    z = zipfile.ZipFile(hwpx_path)
    hits = []
    for name in hwpxlib.section_names(z):
        root = etree.fromstring(z.read(name))
        for n, tbl in enumerate(root.iter(f"{P}tbl")):
            ok, total, sums = hwpxlib.table_width_ok(tbl)
            if not ok:
                bad = {i: s for i, s in enumerate(sums) if s != total}
                hits.append((name, "table #%d width=%d, rows off: %s"
                             % (n, total, dict(list(bad.items())[:4]))))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hwpx")
    ap.add_argument("--pdf", help="use this render instead of rendering now")
    ap.add_argument("--sparse", type=int, default=320,
                    help="pages with fewer body chars than this are reported")
    args = ap.parse_args()
    hwpxlib.ensure_hwpx(args.hwpx)

    findings = 0
    width_hits = check_table_widths(args.hwpx)
    print("== 표 폭 합계 ==")
    if width_hits:
        findings += len(width_hits)
        for where, d in width_hits:
            print("   [FAIL] %s  %s" % (where, d))
    else:
        print("   [ok] 모든 행의 셀 폭 합 = 표 폭")

    try:
        import fitz
    except ImportError:
        print("\nPyMuPDF 미설치 — 렌더 기반 검사 생략 (pip install pymupdf)")
        return 1 if findings else 0

    pdf = args.pdf
    tmp = None
    if not pdf:
        tmp = os.path.join(tempfile.gettempdir(), "_audit_layout.pdf")
        try:
            render_pdf(args.hwpx, tmp)
        except Exception as e:                                  # noqa: BLE001
            print("\n한글 COM 렌더 실패 (%s) — --pdf 로 렌더본을 넘기세요" % e)
            return 1 if findings else 0
        pdf = tmp
    doc = fitz.open(pdf)
    labels = page_labels(doc)

    for title, hits in (("셀 내용 줄바꿈(열 폭 부족)", check_wrapped_cells(doc)),
                        ("목차 페이지 번호", check_toc_pages(doc, labels))):
        print("\n== %s ==" % title)
        if hits:
            findings += len(hits)
            for pg, d in hits:
                print("   p%-4s %s" % (pg, d))
        else:
            print("   [ok] 없음")

    # 희박 페이지는 표지·그림 전용 페이지·장 마지막 페이지가 정상적으로 걸리므로
    # 실패로 세지 않고 목록만 준다. 표 각주가 혼자 넘어간 고아 페이지가 여기 섞여 있다.
    sparse = check_sparse_pages(doc, args.sparse)
    print("\n== 희박 페이지 (정상 포함 — 눈으로 걸러낼 것) ==")
    for pg, d in sparse:
        print("   p%-4s %s" % (pg, d))
    if not sparse:
        print("   없음")

    print("\n실패 %d건, 확인 필요 %d쪽" % (findings, len(sparse)))
    if tmp and os.path.exists(tmp):
        os.remove(tmp)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
