#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""코퍼스 케이스 — 각각 «헬퍼 하나를 실제 문서에 적용»한다.

케이스를 추가하려면 아래 CASES에 (이름, 함수) 한 줄을 더하고
`python corpus/run_corpus.py --update`로 골든을 만든 뒤, 그 diff를 눈으로 확인하고
커밋한다. 골든이 바뀌었는데 의도한 변경이 아니면 그게 회귀다.
"""
import zipfile

import hwpxlib as H

P = H.P


def _section(src, name="Contents/section0.xml"):
    with zipfile.ZipFile(src) as z:
        return H.etree.fromstring(z.read(name)), name


def _first_table(root):
    return next(root.iter(f"{P}tbl"))


def delete_row(src, out):
    """행 하나를 지운다 — rowCnt·rowAddr·표 높이가 함께 따라와야 한다."""
    root, name = _section(src)
    H.delete_row(_first_table(root), 1)
    H.repack_preserve(src, {name: H.XML_DECL + H.etree.tostring(root)}, out)


def widen_column(src, out):
    """한 열을 넓히고 다른 열에서 그만큼 빼앗는다 — 행 합계가 유지돼야 한다."""
    root, name = _section(src)
    H.set_column_width(_first_table(root), 0, 3000, take_from=(1,))
    H.repack_preserve(src, {name: H.XML_DECL + H.etree.tostring(root)}, out)


def edit_cell(src, out):
    """셀 값을 바꾼다 — 그 문단의 linesegarray가 사라져야 한다."""
    root, name = _section(src)
    tbl = _first_table(root)
    tc = H.table_cells(H.table_rows(tbl)[0])[0]
    H.set_cell_text(tc, "4,701")
    H.repack_preserve(src, {name: H.XML_DECL + H.etree.tostring(root)}, out)


def add_two_endnotes(src, out):
    """한 앵커에 미주 둘 — 형제로 붙어야 하고, 절대 서로 안에 들어가면 안 된다."""
    root, name = _section(src)
    template = root.find(f".//{P}ctrl[{P}endNote]")
    para = H.find_para(root, contains="첫 문단이다")
    uid = H.make_uid(root)
    H.add_endnotes(para, "첫 문단이다.", template, ["Ref A.", "Ref B."], uid)
    H.repack_preserve(src, {name: H.XML_DECL + H.etree.tostring(root)}, out)


def extract_first_section(src, out):
    """구역 하나만 떼어낸다 — secCnt·content.hpf·container.rdf가 같이 고쳐져야 한다."""
    H.extract_section(src, "Contents/section0.xml", out)


CASES = [
    ("001-delete-row", delete_row),
    ("002-widen-column", widen_column),
    ("003-edit-cell", edit_cell),
    ("004-add-two-endnotes", add_two_endnotes),
    ("005-extract-section", extract_first_section),
]
