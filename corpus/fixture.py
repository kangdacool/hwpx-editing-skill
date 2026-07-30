#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""코퍼스용 원본 문서를 결정적으로 만든다.

`selftest.py`의 fixture는 재압축 원시동작을 증명하려고 최소한으로 만든 것이라
표에 기하(`sz`/`cellSz`/`cellSpan`/`cellAddr`)가 없고 header에 charPr도 없다.
표·주석·구역 헬퍼를 실제로 통과시키려면 그 형태가 다 있어야 하므로 여기서 따로 만든다.

**실제 문서는 커밋하지 않는다.** 원본을 코드로 생성하면 (a) 저장소에 연구 내용이
들어갈 일이 없고, (b) 어느 기기에서도 같은 입력이 나온다.
"""
import zipfile

import hwpxlib as H

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HH = "http://www.hancom.co.kr/hwpml/2011/head"

TBL_W, COL_W, ROW_H = 40000, 20000, 1000
ROWS, COLS = 3, 2


def _cell(row, col, text):
    return (
        f'<hp:tc><hp:cellAddr rowAddr="{row}" colAddr="{col}"/>'
        f'<hp:cellSpan rowSpan="1" colSpan="1"/>'
        f'<hp:cellSz width="{COL_W}" height="{ROW_H}"/>'
        f'<hp:subList><hp:p id="{600 + row * COLS + col}" paraPrIDRef="0">'
        f'<hp:linesegarray/><hp:run charPrIDRef="0"><hp:t>{text}</hp:t></hp:run>'
        f'</hp:p></hp:subList></hp:tc>'
    )


def _table():
    rows = "".join(
        "<hp:tr>" + "".join(_cell(r, c, f"r{r}c{c}") for c in range(COLS)) + "</hp:tr>"
        for r in range(ROWS)
    )
    return (
        f'<hp:tbl id="500" rowCnt="{ROWS}" colCnt="{COLS}" borderFillIDRef="0">'
        f'<hp:sz width="{TBL_W}" height="{ROWS * ROW_H}"/>{rows}</hp:tbl>'
    )


def _endnote_template():
    """A well-formed 미주 to clone from — one ctrl holding one endNote."""
    return (
        '<hp:ctrl><hp:endNote number="1" instId="300"><hp:subList>'
        '<hp:p id="301" paraPrIDRef="0"><hp:run charPrIDRef="0">'
        '<hp:ctrl><hp:autoNum num="1" numType="ENDNOTE"/></hp:ctrl>'
        '<hp:t> 각주 본문.</hp:t></hp:run></hp:p></hp:subList></hp:endNote></hp:ctrl>'
    )


def _section0():
    return (
        H.XML_DECL
        + (
            f'<hs:sec xmlns:hs="{HP}" xmlns:hp="{HP}">'
            f'<hp:p id="100" paraPrIDRef="0"><hp:linesegarray/>'
            f'<hp:run charPrIDRef="0"><hp:t>첫 문단이다. 두 번째 문장.</hp:t></hp:run>'
            f'{_endnote_template()}</hp:p>'
            f'<hp:p id="110" paraPrIDRef="0"><hp:run charPrIDRef="0">'
            f'<hp:t>표 앞 문단.</hp:t></hp:run></hp:p>'
            f'<hp:p id="120" paraPrIDRef="0"><hp:run charPrIDRef="0">{_table()}</hp:run></hp:p>'
            f'</hs:sec>'
        ).encode("utf-8")
    )


def _section1():
    return (
        H.XML_DECL
        + (
            f'<hs:sec xmlns:hs="{HP}" xmlns:hp="{HP}">'
            f'<hp:p id="200" paraPrIDRef="0"><hp:run charPrIDRef="0">'
            f'<hp:t>둘째 구역의 문단.</hp:t></hp:run></hp:p></hs:sec>'
        ).encode("utf-8")
    )


def _header():
    return (
        H.XML_DECL
        + (
            f'<hh:head xmlns:hh="{HH}" secCnt="2">'
            f'<hh:refList>'
            f'<hh:charProperties itemCnt="1"><hh:charPr id="0" height="1000"/></hh:charProperties>'
            f'<hh:paraProperties itemCnt="1"><hh:paraPr id="0"/></hh:paraProperties>'
            f'<hh:borderFills itemCnt="1"><hh:borderFill id="0"/></hh:borderFills>'
            f'</hh:refList></hh:head>'
        ).encode("utf-8")
    )


def _content_hpf():
    items = "".join(
        f'<opf:item id="{i}" href="{h}" media-type="application/xml"/>'
        for i, h in (("header", "Contents/header.xml"),
                     ("section0", "Contents/section0.xml"),
                     ("section1", "Contents/section1.xml"))
    )
    return (H.XML_DECL + (
        '<opf:package xmlns:opf="http://www.idpf.org/2007/opf/">'
        f'<opf:manifest>{items}</opf:manifest>'
        '<opf:spine><opf:itemref idref="section0"/><opf:itemref idref="section1"/>'
        '</opf:spine></opf:package>').encode("utf-8"))


def build(path: str) -> str:
    """Write the corpus source document to `path` and return it."""
    with zipfile.ZipFile(path, "w") as zf:
        mt = zipfile.ZipInfo("mimetype")
        mt.compress_type = zipfile.ZIP_STORED
        zf.writestr(mt, b"application/hwp+zip")
        zf.writestr("Contents/header.xml", _header())
        zf.writestr("Contents/section0.xml", _section0())
        zf.writestr("Contents/section1.xml", _section1())
        zf.writestr("Contents/content.hpf", _content_hpf())
        zf.writestr("META-INF/container.rdf", H.XML_DECL + b"<rdf/>")
    return path
