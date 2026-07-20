"""
hwpxlib — battle-tested primitives for safely editing HWPX (Hangul/한글) files.

Every function here mirrors a rule from the HWPX editing guide
(references/hwpx-guide.md) that was verified against real 한글 rendering or at
the byte level. The single most important one is `repack_preserve`: a
raw-preserving repacker whose no-op output is byte-identical to the source, so
"if the original opens in 한글, the edited file opens too."

Namespaces (HWPML 2011):
    hp  paragraph  — 단락/표/런/필드   http://www.hancom.co.kr/hwpml/2011/paragraph
    hh  head       — charPr/paraPr 정의 http://www.hancom.co.kr/hwpml/2011/head
    hc  core       — 인라인 이미지        http://www.hancom.co.kr/hwpml/2011/core
    opf content.hpf manifest/spine       http://www.idpf.org/2007/opf/

Requires: lxml  (pip install lxml)
"""

from __future__ import annotations

import io
import re
import struct
import copy
import zipfile
import zlib

try:
    from lxml import etree
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "hwpxlib requires lxml. Install it with:  pip install lxml"
    ) from e

# Clark-notation namespace prefixes — build tags like f"{P}tbl".
P = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"   # hp:
H = "{http://www.hancom.co.kr/hwpml/2011/head}"         # hh:
C = "{http://www.hancom.co.kr/hwpml/2011/core}"         # hc:

XML_DECL = b'<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>\n'


# ---------------------------------------------------------------------------
# §0. Format guard — HWPX only (reject legacy .hwp OLE binaries)
# ---------------------------------------------------------------------------
class NotHwpxError(Exception):
    """The file is not an HWPX. Most often a legacy .hwp OLE binary (signature
    D0 CF 11 E0), which this HWPX-only tool cannot read."""


_OLE_MAGIC = b"\xd0\xcf\x11\xe0"  # legacy .hwp (and every OLE2 / CFB file)


def ensure_hwpx(path: str) -> None:
    """Raise NotHwpxError with actionable guidance if `path` is not a zip-based
    HWPX — in particular a legacy .hwp (OLE binary, signature D0CF11E0). HWPX is
    a zip, so it must start with the PK local-file signature. This only sniffs the
    first bytes; it does not open or modify the file."""
    with open(path, "rb") as f:
        head = f.read(4)
    if head == _OLE_MAGIC:
        raise NotHwpxError(
            "This looks like a legacy .hwp (OLE binary), not an HWPX. "
            "이 파일은 구형 HWP 형식입니다. 한글에서 '다른 이름으로 저장 → "
            "HWPX(.hwpx)'로 변환한 뒤 다시 시도하세요. (이 도구는 HWPX 전용입니다.)"
        )
    if head[:2] != b"PK":
        raise NotHwpxError(
            "This is not a valid HWPX (a zip archive). "
            "이 파일은 올바른 HWPX(zip)가 아닙니다. 원본이 손상되지 않았는지, 혹은 "
            "구형 .hwp가 아닌지 확인하세요. (이 도구는 HWPX 전용입니다.)"
        )


# ---------------------------------------------------------------------------
# §2. Repack (raw-preserving) — THE most important primitive
# ---------------------------------------------------------------------------
def _parse_central(raw: bytes):
    """Parse a zip central directory into {name: record}, plus the entry order."""
    eocd = raw.rfind(b"PK\x05\x06")
    cd_size, cd_off = struct.unpack("<II", raw[eocd + 12:eocd + 20])
    recs, order, p = {}, [], cd_off
    while raw[p:p + 4] == b"PK\x01\x02":
        (sig, vmb, vn, flag, method, mt, md, crc, csize, usize,
         fnl, efl, cml, disk, iattr, eattr, loff) = struct.unpack(
            "<IHHHHHHIIIHHHHHII", raw[p:p + 46])
        name = raw[p + 46:p + 46 + fnl].decode("utf-8")
        extra = raw[p + 46 + fnl:p + 46 + fnl + efl]
        comment = raw[p + 46 + fnl + efl:p + 46 + fnl + efl + cml]
        recs[name] = dict(vmb=vmb, vn=vn, iattr=iattr, eattr=eattr, extra=extra,
                          comment=comment, flag=flag, method=method, crc=crc,
                          csize=csize, usize=usize, mt=mt, md=md, loff=loff)
        order.append(name)
        p += 46 + fnl + efl + cml
    return recs, order


def repack_preserve(src: str, changed: dict, out: str, added: dict | None = None) -> None:
    """Rebuild an HWPX, byte-copying every unchanged entry and re-deflating only
    what changed.

    Args:
        src:     path to the original .hwpx
        changed: {entry_name: new_bytes} for edited XML entries. Keep the XML
                 declaration (`XML_DECL`) at the top of each edited entry.
        out:     output .hwpx path
        added:   {entry_name: bytes} for brand-new entries (e.g. BinData images,
                 new sectionN.xml), which are DEFLATED.

    Why this exists: 한글 rejects files whose unchanged entries were re-deflated.
    Copying their local records verbatim (flag bits and all) means a no-op repack
    is byte-identical to the source. Self-check with `self_verify_identical`.

    Caveat: a file carrying an archive-level zip comment/prefix (data outside the
    entries themselves) may not be byte-identical after a no-op repack, since only
    the entries and central directory are preserved. Real 한글 HWPX has neither.
    """
    ensure_hwpx(src)
    raw = open(src, "rb").read()
    recs, order = _parse_central(raw)
    obuf, meta = io.BytesIO(), {}

    for name in order:
        rc = recs[name]
        loff = obuf.tell()
        fnb = name.encode("utf-8")
        if name in changed:
            data = changed[name]
            if rc["method"] == 8:
                co = zlib.compressobj(6, zlib.DEFLATED, -15)
                comp = co.compress(data) + co.flush()
            else:
                comp = data  # STORED (e.g. mimetype)
            crc = zipfile.crc32(data) & 0xFFFFFFFF
            obuf.write(struct.pack("<IHHHHHIIIHH", 0x04034B50, rc["vn"], 0,
                                   rc["method"], rc["mt"], rc["md"], crc,
                                   len(comp), len(data), len(fnb), 0) + fnb + comp)
            meta[name] = dict(rc, flag=0, crc=crc, csize=len(comp),
                              usize=len(data), loff=loff, extra=b"")
        else:  # byte-for-byte raw copy of the local entry
            if rc["flag"] & 0x08:
                # flag bit 3 = data descriptor: the local header's csize/crc are
                # zero and the real values trail the compressed data. Byte-copying
                # by the (zero) local csize would truncate the entry, so we refuse
                # rather than emit a corrupt zip. self_verify_identical also fails
                # on such files, so verify.py already blocks them.
                raise ValueError(
                    f"Entry {name!r} uses a zip data descriptor (flag bit 3), so "
                    "repack_preserve cannot losslessly byte-copy it. "
                    "이 파일은 data descriptor를 써서 이 도구로 편집할 수 없습니다. "
                    "한글에서 한 번 저장한 뒤 다시 시도하세요."
                )
            ho = rc["loff"]
            (sig, ver, flag, method, mt, md, crc, csize, usize, fnl, efl) = \
                struct.unpack("<IHHHHHIIIHH", raw[ho:ho + 30])
            obuf.write(raw[ho:ho + 30 + fnl + efl + csize])
            meta[name] = dict(rc, loff=loff)

    if added:
        for name, data in added.items():
            loff = obuf.tell()
            fnb = name.encode("utf-8")
            co = zlib.compressobj(6, zlib.DEFLATED, -15)
            comp = co.compress(data) + co.flush()
            crc = zipfile.crc32(data) & 0xFFFFFFFF
            obuf.write(struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, 0, 8, 0, 0,
                                   crc, len(comp), len(data), len(fnb), 0) + fnb + comp)
            meta[name] = dict(vmb=20, vn=20, flag=0, method=8, mt=0, md=0, crc=crc,
                              csize=len(comp), usize=len(data), loff=loff,
                              extra=b"", comment=b"", iattr=0, eattr=0)
            order.append(name)

    cd = obuf.tell()
    for name in order:
        m = meta[name]
        fnb = name.encode("utf-8")
        obuf.write(struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, m["vmb"], m["vn"],
                               m["flag"], m["method"], m["mt"], m["md"], m["crc"],
                               m["csize"], m["usize"], len(fnb), len(m["extra"]),
                               len(m["comment"]), 0, m["iattr"], m["eattr"],
                               m["loff"]) + fnb + m["extra"] + m["comment"])
    n = len(order)
    obuf.write(struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, n, n,
                           obuf.tell() - cd, cd, 0))
    open(out, "wb").write(obuf.getvalue())


# ---------------------------------------------------------------------------
# §1. Structure & parsing
# ---------------------------------------------------------------------------
def section_names(z: zipfile.ZipFile) -> list[str]:
    """All Contents/sectionN.xml entries, in numeric order (0..N)."""
    names = [n for n in z.namelist()
             if re.fullmatch(r"Contents/section\d+\.xml", n)]
    return sorted(names, key=lambda n: int(re.search(r"section(\d+)", n).group(1)))


def strip_pua(s: str) -> str:
    """Drop Hancom private-use-area glyphs (Unicode category Co) — custom
    bullets/numbers 한글 draws with its own font that show up as broken boxes
    once the text is extracted outside 한글 (Word, Markdown, …)."""
    import unicodedata
    return "".join(ch for ch in s if unicodedata.category(ch) != "Co")


def own(p) -> str:
    """The paragraph's *real* body text — 각주·미주·메모 본문을 제외한 진짜 본문
    (read-only extraction).

    Using itertext() (not .text) so lineBreak tails aren't dropped, and skipping
    any <hp:t> nested under footNote/endNote/fieldBegin (각주·미주·메모) so
    footnote/endnote bodies and review comments don't leak into extracted text.

    This is extraction only; editing a note (e.g. 각주↔미주 conversion) is
    separate logic that rewrites the footNote/endNote ctrl + autoNum numType.
    """
    parts = []
    for t in p.findall(f".//{P}t"):
        if not any(a.tag in (f"{P}footNote", f"{P}endNote", f"{P}fieldBegin")
                   for a in t.iterancestors()):
            parts.append("".join(t.itertext()))
    return "".join(parts)


# ---------------------------------------------------------------------------
# §3. Common edit rules (linesegarray · ids)
# ---------------------------------------------------------------------------
def strip_linesegarray(el) -> int:
    """Remove every <hp:linesegarray> under `el` (cached line layout goes stale
    after any edit; after structural edits, strip the whole section). Returns the
    number removed."""
    n = 0
    for ls in el.findall(f".//{P}linesegarray"):
        ls.getparent().remove(ls)
        n += 1
    return n


def replace_image(pic, png_bytes, disp_w):
    """Swap an <hp:pic>'s raster image and update EVERY geometry field together.

    An HWPX picture stores its size in several elements that must agree, or 한글
    mis-renders it. The one most often forgotten on an in-place swap is
    ``<hp:imgDim>``: 한글 interprets ``<hp:imgClip>`` against imgDim, so a stale
    imgDim (left over from the previous image) makes 한글 **crop the new image** —
    the bottom is cut by exactly ``new_orgH / old_imgDim_h``. A structure check
    passes; only a real 한글 render reveals the crop. This helper rewrites all of
    them at once: orgSz, curSz, sz, imgDim, imgClip, imgRect(pt0..pt3), scaMatrix.

    Args:
        pic:       the ``<hp:pic>`` element (locate via its ``<hc:img>``
                   ``binaryItemIDRef``).
        png_bytes: the new image bytes; native pixel size is read from them.
        disp_w:    display width in HWPUNIT (e.g. text-column width ~= 42520).
                   Display height is derived to preserve the aspect ratio.

    Returns:
        ``(binaryItemIDRef, png_bytes)`` — add the bytes to ``repack_preserve``'s
        ``changed`` under the BinData path that already exists in the manifest,
        e.g. ``{f"BinData/{ref}.png": png_bytes}`` (the extension may be ``.bmp``
        etc. — match the manifest ``href``). Only updates the picture geometry; it
        does NOT touch ``content.hpf`` — if the image *format* changes, also update
        that item's ``media-type`` there.

    Verify by RENDERING in 한글 (see the guide's image / §7 render-verify recipe);
    structural checks cannot catch a crop.
    """
    from PIL import Image  # optional dep — only image edits need Pillow

    pw, ph = Image.open(io.BytesIO(png_bytes)).size
    ow, oh = pw * 75, ph * 75                 # native HWPUNIT (px x 75, 96 dpi)
    dw = int(disp_w)
    dh = round(dw * ph / pw)                   # preserve aspect ratio

    def _set(el, **kw):
        if el is not None:
            for k, v in kw.items():
                el.set(k, str(v))

    # orgSz/curSz/sz/imgDim/imgClip/imgRect/img are DIRECT children of <hp:pic>
    # (per the HWPX schema) — direct finds avoid matching a caption subtree.
    _set(pic.find(f"{P}orgSz"),   width=ow, height=oh)
    _set(pic.find(f"{P}curSz"),   width=dw, height=dh)
    _set(pic.find(f"{P}sz"),      width=dw, height=dh)
    _set(pic.find(f"{P}imgDim"),  dimwidth=ow, dimheight=oh)   # <- forget => crop
    _set(pic.find(f"{P}imgClip"), left=0, right=ow, top=0, bottom=oh)
    rect = pic.find(f"{P}imgRect")
    if rect is not None:
        for nm, (x, y) in (("pt0", (0, 0)), ("pt1", (ow, 0)),
                           ("pt2", (ow, oh)), ("pt3", (0, oh))):
            _set(rect.find(f"{C}{nm}"), x=x, y=y)   # pt0..pt3 are hc:
    ri = pic.find(f"{P}renderingInfo")              # <hc:scaMatrix> lives here
    if ri is not None:
        _set(ri.find(f"{C}scaMatrix"), e1=round(dw / ow, 6), e5=round(dh / oh, 6))
    img = pic.find(f"{C}img")
    return (img.get("binaryItemIDRef") if img is not None else None, png_bytes)


_ID_ATTRS = ("id", "instId", "instid")


def pick_template(paras, style=None, need_text=True):
    """복제 템플릿으로 쓸 문단을 고른다. **secPr 보유 문단을 배제한다.**

    섹션의 첫 <hp:p>는 <hp:secPr>(용지·여백·머리말)를 품는다. 그것을 템플릿으로 쓰면
    secPr이 중복되고, run[0]이 secPr 담당이라 잉여 run을 지우는 순간 텍스트 run이
    통째로 사라진다(오류 없이 빈 문단이 된다).
    """
    for p in paras:
        if style is not None and p.get("styleIDRef") != str(style):
            continue
        if p.find(f".//{P}secPr") is not None:
            continue
        if need_text and not p.findall(f".//{P}t"):
            continue
        return p
    raise ValueError(f"조건에 맞는 템플릿 문단 없음 (style={style})")


def clone_para(template, uid, content):
    """문단을 복제해 텍스트를 채운다. 서식을 뭉개지 않는다.

    content:
      str                      단일 run 문단 — 첫 run만 남기고 텍스트를 넣는다
      [(charPrIDRef, text), …] 다중 run 문단 — 조각마다 run을 만든다

    ⚠️ 흔한 사고: 참고문헌처럼 run마다 charPr이 다른 문단(저자 bold / 제목 plain /
       저널 italic)을 "run[1:] 제거 후 t[0]에 전체 텍스트 주입"으로 복제하면
       **run[0]의 서식이 문단 전체에 먹는다.** 구조검증으로는 안 잡히고 렌더에서만 보인다.
       조각으로 넘겨서 run 단위로 채울 것. 조각 경계의 공백도 원본을 따라간다.
    """
    from lxml import etree
    if template.find(f".//{P}secPr") is not None:
        raise ValueError("secPr 보유 문단은 템플릿으로 쓸 수 없다 — pick_template()을 쓸 것")

    n = copy.deepcopy(template)
    n.set("id", str(uid()))
    strip_linesegarray(n)

    runs = n.findall(f".//{P}run")
    if not runs:
        raise ValueError("템플릿에 <hp:run>이 없다")

    if isinstance(content, str):
        content = [(runs[0].get("charPrIDRef"), content)]

    parent = runs[0].getparent()
    by_cp = {r.get("charPrIDRef"): r for r in runs}
    for r in runs:
        parent.remove(r)

    for cpid, text in content:
        base = by_cp.get(cpid, runs[0])
        r = copy.deepcopy(base)
        r.set("charPrIDRef", cpid)
        strip_linesegarray(r)
        ts = r.findall(f"{P}t")
        if not ts:
            ts = [etree.SubElement(r, P + "t")]
        ts[0].text = text
        for t in ts[1:]:
            t.getparent().remove(t)
        parent.append(r)
    return n


def run_patterns(paras):
    """문단들의 run charPr 패턴을 뽑는다. 서식 균일성 단정문에 쓴다.

        pats = run_patterns([p for p in sec if p.get('paraPrIDRef') == '59'])
        assert len(set(pats)) == 1, f"참고문헌 서식 불균일: {set(pats)}"
    """
    return [tuple(r.get("charPrIDRef") for r in p.findall(f".//{P}run")) for p in paras]


def make_uid(root):
    """Return a uid() that yields fresh, non-colliding numeric ids for `root`.

    Cloning an element with deepcopy inherits the original's id — which causes
    duplicates and instability. Call uid() for every cloned id-bearing node
    (endnote subList>p, table tbl/tc/p, etc.).

    Uniqueness is guaranteed only within the passed `root` (ids are section-
    scoped); it does not dedupe across sections.
    """
    ids = {int(v) for elx in root.iter() for a in _ID_ATTRS
           if (v := elx.get(a)) and str(v).isdigit()}
    counter = [(max(ids) + 5) if ids else 5]

    def uid():
        counter[0] += 2
        return counter[0]

    return uid


def find_duplicate_ids(root, ignore=(0, 2147483648)):
    """Return {id: count} for id/instId values that appear more than once
    (0 and the 2147483648 sentinel are ignored by default)."""
    seen = {}
    for el in root.iter():
        for a in _ID_ATTRS:
            v = el.get(a)
            if v and str(v).isdigit():
                iv = int(v)
                if iv in ignore:
                    continue
                seen[iv] = seen.get(iv, 0) + 1
    return {k: c for k, c in seen.items() if c > 1}


# ---------------------------------------------------------------------------
# §6. Structural inventory (breaks, counts) — used for §7 semantic checks
# ---------------------------------------------------------------------------
def structural_counts(root) -> dict:
    """Count the elements that §7 tells you to verify before/after an edit."""
    def n(tag):
        return len(root.findall(f".//{P}{tag}"))
    breaks = {"pageBreak": 0, "columnBreak": 0}
    for para in root.findall(f".//{P}p"):
        for attr in breaks:
            if para.get(attr) in ("1", "true"):
                breaks[attr] += 1
    return {
        "p": n("p"), "tbl": n("tbl"), "pic": n("pic"),
        "equation": n("equation"), "fieldBegin": n("fieldBegin"),
        "endNote": n("endNote"), "footNote": n("footNote"),
        "linesegarray": n("linesegarray"),
        "pageBreak_paras": breaks["pageBreak"],
        "columnBreak_paras": breaks["columnBreak"],
    }


# ---------------------------------------------------------------------------
# §7. Verification checklist
# ---------------------------------------------------------------------------
def self_verify_identical(src: str) -> bool:
    """A no-op repack must be byte-identical to the source (§7.1)."""
    tmp = io.BytesIO()
    raw = open(src, "rb").read()
    out = src + ".noop.tmp"
    repack_preserve(src, {}, out)
    same = open(out, "rb").read() == raw
    import os
    os.remove(out)
    del tmp
    return same


def check_wellformed(z: zipfile.ZipFile, extra=("Contents/content.hpf",)) -> dict:
    """Parse every sectionN.xml (+ content.hpf) and report any that fail (§7.2).
    Returns {entry: 'OK' | error-string}."""
    result = {}
    targets = section_names(z) + [e for e in extra if e in z.namelist()]
    for name in targets:
        try:
            etree.fromstring(z.read(name))
            result[name] = "OK"
        except Exception as ex:  # noqa: BLE001
            result[name] = f"MALFORMED: {ex}"
    return result


def zip_integrity(z: zipfile.ZipFile) -> dict:
    """testzip() + mimetype-first + mimetype-STORED (§7.5)."""
    names = z.namelist()
    mi = z.getinfo("mimetype") if "mimetype" in names else None
    return {
        "testzip_ok": z.testzip() is None,
        "mimetype_first": bool(names) and names[0] == "mimetype",
        "mimetype_stored": mi is not None and mi.compress_type == zipfile.ZIP_STORED,
    }


# Only these four IDRefs resolve cleanly to header ref-lists; binaryItemIDRef,
# beginIDRef, memoShape/outlineShapeIDRef, linkListIDRef point elsewhere and are
# skipped to avoid false positives (validated clean on real 한글 files).
_IDREF_TARGETS = {"charPrIDRef": "charPr", "paraPrIDRef": "paraPr",
                  "borderFillIDRef": "borderFill", "styleIDRef": "style"}


def check_idref_integrity(z: zipfile.ZipFile) -> dict:
    """Every charPr/paraPr/borderFill/style IDRef in the sections must exist in
    header.xml, and each ref-list's `itemCnt` must equal its child count — a
    dangling ref or stale itemCnt makes 한글 reject the file (§4). Returns
    {'itemcnt': [...], 'dangling': [...]}; both empty means OK."""
    hdr = etree.fromstring(z.read("Contents/header.xml"))
    idsets, itemcnt = {}, []
    for el in hdr.iter():
        cnt = el.get("itemCnt")
        if cnt is None:
            continue
        kids = list(el)
        if cnt.isdigit() and int(cnt) != len(kids):
            itemcnt.append(f"{etree.QName(el).localname}: itemCnt={cnt} vs {len(kids)} children")
        for c in kids:
            if c.get("id") is not None:
                idsets.setdefault(etree.QName(c).localname, set()).add(c.get("id"))
    dangling = []
    for name in section_names(z):
        for el in etree.fromstring(z.read(name)).iter():
            for attr, val in el.attrib.items():
                target = _IDREF_TARGETS.get(attr)
                if target and val not in idsets.get(target, set()):
                    dangling.append(f"{name}: {attr}={val} → no <{target} id={val}>")
    return {"itemcnt": itemcnt, "dangling": dangling}


def _norm(xml_bytes: bytes) -> list[str]:
    """Canonical, line-split serialization for minimal-change diffs (§7 diff)."""
    s = etree.tostring(etree.fromstring(xml_bytes), encoding="unicode")
    return re.sub("><", ">\n<", s).splitlines()


def minimal_diff(orig_xml: bytes, edited_xml: bytes) -> list[str]:
    """Return only the +/- lines between a re-serialized original and the edited
    XML, proving *only intended changes* are present (§7 bonus)."""
    import difflib
    return [ln for ln in difflib.unified_diff(_norm(orig_xml), _norm(edited_xml),
                                              lineterm="")
            if ln[:1] in "+-" and not ln.startswith(("+++", "---"))]
