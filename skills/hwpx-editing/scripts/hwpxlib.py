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


_ID_ATTRS = ("id", "instId", "instid")


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
