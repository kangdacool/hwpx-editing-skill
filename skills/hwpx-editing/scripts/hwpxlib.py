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


def repack_preserve(src: str, changed: dict, out: str, added: dict | None = None,
                    drop=None, rename: dict | None = None) -> None:
    """Rebuild an HWPX, byte-copying every unchanged entry and re-deflating only
    what changed.

    Args:
        src:     path to the original .hwpx
        changed: {entry_name: new_bytes} for edited XML entries. Keep the XML
                 declaration (`XML_DECL`) at the top of each edited entry.
        out:     output .hwpx path
        added:   {entry_name: bytes} for brand-new entries (e.g. BinData images,
                 new sectionN.xml), which are DEFLATED.
        drop:    iterable of entry names to leave out entirely.
        rename:  {old_entry_name: new_entry_name}. Renamed entries are re-deflated
                 (the name lives in both the local and central headers).

    `drop` + `rename` exist for **pulling one 장/구역 out of a merged report** —
    keep `Contents/sectionN.xml`, rename it to `section0.xml`, drop the other
    sections and the BinData they own. You must also rewrite `Contents/content.hpf`
    (manifest + spine) and `META-INF/container.rdf`, which enumerate the entries —
    see `extract_section()`.

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
    drop = set(drop or ())
    rename = dict(rename or {})
    changed = dict(changed)
    order = [n for n in order if n not in drop]
    if rename:
        # A rename rewrites the entry name in both headers, so the entry can no
        # longer be byte-copied. Re-deflate it with its original bytes unless the
        # caller already supplied new content for it.
        with zipfile.ZipFile(src) as _z:
            for n in rename:
                if n in order and n not in changed:
                    changed[n] = _z.read(n)
    out_names = [rename.get(n, n) for n in order]

    for name in order:
        rc = recs[name]
        loff = obuf.tell()
        fnb = rename.get(name, name).encode("utf-8")
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
            meta[rename.get(name, name)] = dict(rc, flag=0, crc=crc, csize=len(comp),
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
            out_names.append(name)

    cd = obuf.tell()
    for name in out_names:
        m = meta[name]
        fnb = name.encode("utf-8")
        obuf.write(struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, m["vmb"], m["vn"],
                               m["flag"], m["method"], m["mt"], m["md"], m["crc"],
                               m["csize"], m["usize"], len(fnb), len(m["extra"]),
                               len(m["comment"]), 0, m["iattr"], m["eattr"],
                               m["loff"]) + fnb + m["extra"] + m["comment"])
    n = len(out_names)
    obuf.write(struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, n, n,
                           obuf.tell() - cd, cd, 0))
    open(out, "wb").write(obuf.getvalue())


# ---------------------------------------------------------------------------
# §1. Structure & parsing
# ---------------------------------------------------------------------------
def extract_section(src: str, keep: str, out: str, title: str | None = None) -> dict:
    """Pull ONE 구역/장 out of a merged HWPX into a standalone, openable document.

    `keep` = the entry to keep (e.g. "Contents/section8.xml"); it becomes
    `Contents/section0.xml` in `out`. Everything the kept section doesn't reference
    is dropped: the other sections, their BinData, and the stale preview image.
    `header.xml` is kept whole — its charPr/paraPr/style/fontface ids are what the
    section refers to, and pruning them would break every IDRef.

    Rewrites the two files that enumerate package entries — `Contents/content.hpf`
    (manifest + spine, and `<opf:title>` if `title` is given) and
    `META-INF/container.rdf`. Forgetting either makes 한글 refuse the file.

    Returns {"binaries": [...], "dropped": n} for logging.

    ⚠️ Document-wide autoNum (표·그림 캡션 번호) restarts at 1 in the extracted file,
    because "이게 전체에서 78번째 표"는 병합본만 안다. That is expected and correct —
    the numbers come back when the 취합 담당자 merges it. **번호를 손으로 채우지 말 것**
    (autoNum과 겹쳐 이중 표기가 된다). 미주는 구역별로 매겨지므로 그대로 살아남는다.
    """
    with zipfile.ZipFile(src) as z:
        names = z.namelist()
        if keep not in names:
            raise ValueError(f"{keep!r} not in {src}")
        sec = etree.fromstring(z.read(keep))
        hpf = z.read("Contents/content.hpf").decode("utf-8")
        rdf = z.read("META-INF/container.rdf").decode("utf-8")
        hdr_raw = z.read("Contents/header.xml")
        set_raw = z.read("settings.xml") if "settings.xml" in names else None

    # The binaryItemIDRef → file mapping lives in content.hpf's manifest, NOT in
    # header.xml (header has no <hh:binaryItem> in files 한글 writes today).
    item_re = re.compile(r'<opf:item id="([^"]+)" href="([^"]+)"[^>]*/>')
    manifest = {m.group(1): m.group(0) for m in item_re.finditer(hpf)}
    hrefs = {m.group(1): m.group(2) for m in item_re.finditer(hpf)}
    refs = {e.get("binaryItemIDRef") for e in sec.iter()
            if e.get("binaryItemIDRef")}
    keep_bin = {hrefs[r] for r in refs if r in hrefs}
    unresolved = sorted(r for r in refs if r not in hrefs)
    if unresolved:
        raise ValueError(f"binaryItemIDRef not in content.hpf manifest: {unresolved}")

    drop = {n for n in names
            if (n.startswith("Contents/section") and n != keep)
            or (n.startswith("BinData/") and n not in keep_bin)
            or n == "Preview/PrvImage.png"}

    # content.hpf — manifest + spine list every entry; rebuild both. Reuse each kept
    # BinData item's original line so its media-type survives verbatim.
    items = ['<opf:item id="header" href="Contents/header.xml" media-type="application/xml"/>',
             '<opf:item id="section0" href="Contents/section0.xml" media-type="application/xml"/>']
    items += [manifest[i] for i in sorted(refs) if hrefs.get(i) in keep_bin]
    hpf = re.sub(r"<opf:manifest>.*?</opf:manifest>",
                 "<opf:manifest>" + "".join(items) + "</opf:manifest>", hpf, flags=re.S)
    hpf = re.sub(r"<opf:spine>.*?</opf:spine>",
                 '<opf:spine><opf:itemref idref="header" linear="yes"/>'
                 '<opf:itemref idref="section0" linear="yes"/></opf:spine>', hpf, flags=re.S)
    if title:
        hpf = re.sub(r"<opf:title>.*?</opf:title>",
                     f"<opf:title>{title}</opf:title>", hpf, flags=re.S)

    # container.rdf — drops one hasPart/Description pair per section.
    rdf = re.sub(r'<rdf:Description rdf:about="">(?:(?!</rdf:Description>).)*?'
                 r'rdf:resource="Contents/section(?!0\.xml")[^"]*"/></rdf:Description>'
                 r'<rdf:Description rdf:about="Contents/section(?!0\.xml")[^"]*">'
                 r'(?:(?!</rdf:Description>).)*?</rdf:Description>', "", rdf, flags=re.S)

    # 🔴 header.xml declares how many 구역 the document has. Leave `secCnt` at the
    #    merged file's value and 한글 opens the file, passes every structure check —
    #    and renders ONE BLANK PAGE. Patch it in place (byte regex, so the rest of
    #    the header is untouched).
    hdr_new = re.sub(rb'(<hh:head[^>]*?secCnt=")\d+(")', rb'\g<1>1\g<2>',
                     hdr_raw, count=1)
    if hdr_new == hdr_raw:
        raise ValueError("header.xml에 secCnt 속성이 없다 — 구조가 예상과 다르다")

    changed = {"Contents/content.hpf": XML_DECL + hpf.split("?>", 1)[1].encode("utf-8"),
               "META-INF/container.rdf": XML_DECL + rdf.split("?>", 1)[1].encode("utf-8"),
               "Contents/header.xml": hdr_new}
    if set_raw is not None:
        # the saved caret points at a paragraph id that no longer exists
        changed["settings.xml"] = re.sub(rb'paraIDRef="\d+" pos="\d+"',
                                         b'paraIDRef="0" pos="0"', set_raw)
    if "Preview/PrvText.txt" in names:
        head = "\n".join(t for p in list(sec.iter(f"{P}p"))[:40]
                         if (t := own(p).strip()))[:800]
        changed["Preview/PrvText.txt"] = head.encode("utf-8")
    repack_preserve(src, changed, out, drop=drop,
                    rename={keep: "Contents/section0.xml"})
    return {"binaries": sorted(keep_bin), "dropped": len(drop)}


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
# §3-bis. Write-side text edits (.tail-safe) — the counterpart to own()
#   Run text lives in <hp:t>.text AND in the .tail of inline children
#   (lineBreak, markpenBegin/End, …). A find/replace that only reads .text
#   silently misses everything after a <hp:lineBreak/>. own() already avoids
#   this on the read side (itertext); these give edits the same safety so you
#   never hand-roll a t.text-only helper again.
# ---------------------------------------------------------------------------
def _text_nodes(p, body_only=True):
    """Yield (node, attr) for every text-bearing position under `p`: each
    <hp:t>.text plus the .tail of its inline descendants. body_only skips text
    nested in 각주·미주·메모 (footNote/endNote/fieldBegin), matching own()."""
    skip = (f"{P}footNote", f"{P}endNote", f"{P}fieldBegin")
    for t in p.findall(f".//{P}t"):
        if body_only and any(a.tag in skip for a in t.iterancestors()):
            continue
        if t.text:
            yield t, "text"
        for d in t.iterdescendants():
            if d.tail:
                yield d, "tail"


def replace_text(p, old, new, count=0):
    """Replace `old`→`new` in a paragraph's real body text, .tail-safe.
    count=0 replaces all occurrences; otherwise up to `count`. Returns the number
    replaced. A match that straddles an inline-child boundary (rare) is NOT
    handled — pick a shorter anchor or edit structurally."""
    done = 0
    for node, attr in _text_nodes(p):
        s = getattr(node, attr)
        if not s or old not in s:
            continue
        k = s.count(old) if count == 0 else min(s.count(old), count - done)
        if k <= 0:
            break
        setattr(node, attr, s.replace(old, new, k))
        done += k
        if count and done >= count:
            break
    return done


def insert_ctrls_after(p, phrase, ctrls):
    """Insert inline ctrl nodes (e.g. cloned endnote <hp:ctrl>s — clone with fresh
    ids yourself first) right after the first `phrase`, splitting the host <hp:t>
    so trailing text survives. Anchors on <hp:t>.text only. Returns True on
    success; False if `phrase` isn't in any plain .text (e.g. it lands after a
    lineBreak) — choose another anchor or handle the tail case explicitly."""
    skip = (f"{P}footNote", f"{P}endNote", f"{P}fieldBegin")
    for t in p.findall(f".//{P}t"):
        if any(a.tag in skip for a in t.iterancestors()):
            continue
        if t.text and phrase in t.text:
            i = t.text.index(phrase) + len(phrase)
            before, after = t.text[:i], t.text[i:]
            run = t.getparent(); pos = list(run).index(t)
            t.text = before; k = pos + 1
            for c in ctrls:
                run.insert(k, c); k += 1
            if after:
                nt = etree.Element(f"{P}t"); nt.text = after; run.insert(k, nt)
            return True
    return False


def nested_notes(root):
    """Return [(note, [inner notes])] for every 각주/미주 that contains another one.

    한글 cannot represent a 주석 inside a 주석 and errors when opening such a file,
    but nothing else catches it: the XML is well-formed and the ids are unique.
    It happens when you insert a SECOND note at the same anchor and the run handle
    you append to still points inside the note you just built — `.//hp:run`,
    `.//hp:p` and `.//hp:endNote` all descend into <hp:subList>.
    Use add_endnotes() below instead of hand-rolling that loop; verify.py check 3d
    gates on this. (Real case: 신부전 제7장 미주 36 → 260723·260727·260728 all carried it.)
    """
    out = []
    for note in root.iter(f"{P}endNote", f"{P}footNote"):
        inner = [x for x in note.iter(f"{P}endNote", f"{P}footNote") if x is not note]
        if inner:
            out.append((note, inner))
    return out


def clone_endnote(template_ctrl, text, uid):
    """Clone an existing endnote/footnote <hp:ctrl> with fresh ids and new text.

    `template_ctrl` is the <hp:ctrl> wrapping an <hp:endNote>/<hp:footNote> — grab one
    from the document rather than building the XML by hand, so charPr/paraPr/autoNum
    formatting matches. `uid` comes from make_uid(section_root).

    Returns a detached <hp:ctrl> ready to hand to insert_ctrls_after()/add_endnotes().
    Never append the result to a run you obtained from INSIDE another note.
    """
    ctrl = copy.deepcopy(template_ctrl)
    for el in ctrl.iter():
        for a in _ID_ATTRS:
            if el.get(a) is not None:
                el.set(a, str(uid()))
    for ls in ctrl.findall(f".//{P}linesegarray"):
        ls.getparent().remove(ls)
    note = ctrl.find(f"{P}endNote")
    if note is None:
        note = ctrl.find(f"{P}footNote")
    if note is None:
        raise ValueError("template_ctrl does not wrap an endNote/footNote")
    if nested_notes(ctrl):
        raise ValueError("template_ctrl already contains a nested 주석 — "
                         "pick a clean template (see nested_notes())")
    ts = note.findall(f".//{P}t")
    if not ts:
        raise ValueError("template note has no <hp:t> to carry the citation")
    ts[0].text = text
    for t in ts[1:]:
        t.text = ""
    return ctrl


def add_endnotes(p, phrase, template_ctrl, texts, uid):
    """Attach one or more endnotes/footnotes to a BODY paragraph, right after `phrase`.

    This is the safe path for the multi-note case. Each note is cloned from
    `template_ctrl` with fresh ids, then all of them are inserted as siblings in the
    host run via insert_ctrls_after() — which anchors only on real body text, so a
    note can never land inside another note's <hp:subList>.

    Raises if `p` is not a body paragraph (i.e. it sits inside a subList) or if
    `phrase` isn't found in plain body text. Returns the list of inserted <hp:ctrl>.
    """
    if any(a.tag == f"{P}subList" for a in p.iterancestors()):
        raise ValueError("target paragraph is inside a subList (주석/표 셀), not body text")
    ctrls = [clone_endnote(template_ctrl, t, uid) for t in texts]
    if not insert_ctrls_after(p, phrase, ctrls):
        raise ValueError(f"anchor phrase not found in body text: {phrase!r}")
    return ctrls


def find_para(root_or_paras, contains=None, starts=None):
    """First <hp:p> whose own() text contains / startswith the given string.
    Prefer a SHORT, ASCII-safe anchor: long Korean phrases break on Unicode
    lookalikes — 가운뎃점 ·(U+00B7/2027/318D/30FB), –—dashes, NBSP(U+00A0)."""
    paras = root_or_paras.iter(f"{P}p") if hasattr(root_or_paras, "iter") \
        else root_or_paras
    for p in paras:
        s = own(p)
        if contains is not None and contains in s:
            return p
        if starts is not None and s.strip().startswith(starts):
            return p
    return None


# ---------------------------------------------------------------------------
# §4-T. Tables — read and edit cells without hand-rolling the XML
# ---------------------------------------------------------------------------
def table_rows(tbl):
    """The table's <hp:tr> elements, in order."""
    return tbl.findall(f"{P}tr")


def table_cells(tr):
    """A row's <hp:tc> elements, in order (merged cells appear once, at their
    top-left position, so a row's cell count can be smaller than colCnt)."""
    return tr.findall(f"{P}tc")


def cell_text(tc, para_sep="\n"):
    """Plain text of one cell.

    ``para_sep`` matters: a cell can hold several <hp:p>, which render as
    separate LINES. Joining them with "" invents typos — `US adults,` + `n=43`
    reads as ``US adults,n=43`` and looks like a missing space that is not there.
    Keep the separator unless you truly want the glued form.
    """
    sub = tc.find(f"{P}subList")
    if sub is None:
        return ""
    return para_sep.join(
        "".join("".join(t.itertext()) for t in cp.findall(f".//{P}t"))
        for cp in sub.findall(f"{P}p"))


def table_grid(tbl, para_sep="\n"):
    """The whole table as a list of rows of cell strings (see `cell_text`)."""
    return [[cell_text(tc, para_sep) for tc in table_cells(tr)] for tr in table_rows(tbl)]


def set_cell_text(tc, text, keep_runs=False):
    """Replace a cell's content with a single line of `text`.

    Keeps the first paragraph's paraPr and the first run's charPr, drops the
    extra paragraphs/runs, and strips the stale linesegarray. Pass
    ``keep_runs=True`` when the cell's later runs carry formatting you need
    (e.g. a superscript marker) and you only want the first run's text changed.
    """
    sub = tc.find(f"{P}subList")
    ps = sub.findall(f"{P}p")
    for extra in ps[1:]:
        sub.remove(extra)
    p = ps[0]
    runs = p.findall(f"{P}run")
    if not runs:
        raise ValueError("cell paragraph has no run to inherit formatting from")
    if not keep_runs:
        for extra in runs[1:]:
            p.remove(extra)
    run = runs[0]
    for ch in list(run):
        run.remove(ch)
    etree.SubElement(run, f"{P}t").text = text
    strip_linesegarray(p)
    return tc


def fill_table(tbl, rows, row_offset=0, col_offset=0, cols=None):
    """Write `rows` (list of lists of str) into the table body.

    This is the helper that makes "numbers are generated, never re-typed" cheap:
    read the authoritative CSV, hand the values here, and a re-analysis becomes
    one re-run instead of a hand-transcription pass. Reading the table back with
    `table_grid` and diffing against the same source is then your verifier.

    `cols` optionally maps source position -> cell index within the row, for
    tables whose first column is a label you do not want to overwrite.
    Raises if a row has fewer cells than the write needs (a silent short write
    is how a stale value survives).
    """
    trs = table_rows(tbl)
    n = 0
    for r, values in enumerate(rows):
        tr = trs[row_offset + r]
        tcs = table_cells(tr)
        for i, v in enumerate(values):
            j = cols[i] if cols else col_offset + i
            if j >= len(tcs):
                raise IndexError("row %d has %d cells; cannot write index %d"
                                 % (row_offset + r, len(tcs), j))
            set_cell_text(tcs[j], v)
            n += 1
    return n


def table_width_ok(tbl):
    """(ok, table_width, per-row widths) — every row's cell widths must sum to
    the table width or 한글 rejects the file. Check this after ANY geometry edit.

    Rows under a vertical merge carry no <hp:tc> for the covered columns, so
    their own widths sum short; the carried width is added back here. Forgetting
    that turns every header with a rowSpan into a false alarm.

    A table missing the geometry elements this reads (`sz`, `cellSz`, `cellSpan`,
    `cellAddr`) yields `(True, None, [])` — "no verdict" rather than an exception.
    Callers gate builds on this, and a verifier that raises on an odd table stops
    the whole run instead of reporting it; `total is None` says it was unmeasurable.
    """
    sz = tbl.find(f"{P}sz")
    if sz is None or sz.get("width") is None:
        return True, None, []
    total = int(sz.get("width"))
    sums = []
    pending = {}                       # colAddr -> [rows still covered, width]
    for tr in table_rows(tbl):
        carried = sum(w for _rows, w in pending.values())
        try:
            own = sum(int(tc.find(f"{P}cellSz").get("width")) for tc in table_cells(tr))
        except (AttributeError, TypeError, ValueError):
            return True, None, []
        sums.append(own + carried)
        for addr in list(pending):
            pending[addr][0] -= 1
            if pending[addr][0] <= 0:
                del pending[addr]
        for tc in table_cells(tr):
            span_el, addr_el = tc.find(f"{P}cellSpan"), tc.find(f"{P}cellAddr")
            if span_el is None or addr_el is None:
                return True, None, []
            span = int(span_el.get("rowSpan"))
            if span > 1:
                pending[int(addr_el.get("colAddr"))] = \
                    [span - 1, int(tc.find(f"{P}cellSz").get("width"))]
    return all(s == total for s in sums), total, sums


def rowcnt_mismatches(root):
    """[(index, declared, actual)] for every <hp:tbl> whose rowCnt disagrees with
    its real <hp:tr> count.

    한글 reads the table by the declared count, so a mismatch collapses the whole
    document onto one page — and nothing else catches it: the XML is well-formed,
    the ids are unique, and the cell widths still add up (§4-표, 흔한 실패 20).
    A table with no rowCnt attribute states nothing, so it is not a mismatch.
    """
    out = []
    for i, tbl in enumerate(root.iter(f"{P}tbl")):
        declared = tbl.get("rowCnt")
        if declared is None or not declared.isdigit():
            continue
        actual = len(table_rows(tbl))
        if int(declared) != actual:
            out.append((i, int(declared), actual))
    return out


def seccnt_mismatch(z: zipfile.ZipFile):
    """(declared, actual) when header.xml's secCnt contradicts the number of
    sectionN.xml entries, else None.

    Pull a 장 out of a merged report and leave secCnt alone and the file still
    OPENS — it just shows one blank page (§6-E, 흔한 실패 21). Returns None when
    the attribute is absent: it is optional, and the head element may carry a
    default namespace rather than the hh: prefix, so absence states nothing.
    """
    try:
        hdr = z.read("Contents/header.xml")
    except KeyError:
        return None
    m = re.search(rb'<(?:\w+:)?head\b[^>]*?\bsecCnt="(\d+)"', hdr)
    if not m:
        return None
    declared, actual = int(m.group(1)), len(section_names(z))
    return None if declared == actual else (declared, actual)


def set_column_width(tbl, col_addr, delta, take_from=()):
    """Widen (or narrow) one column by `delta` HWPUNIT, taking it back from the
    columns in `take_from` so the row total is preserved.

    Needed more often than it looks: making a cell's text longer (e.g. 4701 ->
    4,701) can push it past the column width, and 한글 then WRAPS it — "4,70"
    on one line and "1" on the next. No structural check sees that; only a
    render does. `delta` is split evenly across `take_from`.
    """
    if take_from and delta % len(take_from):
        raise ValueError("delta must divide evenly across take_from columns")
    share = delta // len(take_from) if take_from else 0
    for tr in table_rows(tbl):
        for tc in table_cells(tr):
            addr = int(tc.find(f"{P}cellAddr").get("colAddr"))
            w = tc.find(f"{P}cellSz")
            if addr == col_addr:
                w.set("width", str(int(w.get("width")) + delta))
            elif addr in take_from:
                w.set("width", str(int(w.get("width")) - share))
    return table_width_ok(tbl)


def delete_row(tbl, row_idx):
    """Remove a row and renumber the rowAddr of every row below it.

    Also shrinks the cached table height by the removed row's height, so 한글
    does not lay out against a stale total.
    """
    trs = table_rows(tbl)
    dead = trs[row_idx]
    height = int(table_cells(dead)[0].find(f"{P}cellSz").get("height"))
    tbl.remove(dead)
    for tr in table_rows(tbl):
        for tc in table_cells(tr):
            ca = tc.find(f"{P}cellAddr")
            ra = int(ca.get("rowAddr"))
            if ra > row_idx:
                ca.set("rowAddr", str(ra - 1))
    tbl.set("rowCnt", str(len(table_rows(tbl))))
    sz = tbl.find(f"{P}sz")
    sz.set("height", str(int(sz.get("height")) - height))
    return len(table_rows(tbl))


def delete_column(tbl, col_addr, give_width_to=0):
    """Remove one column: drop its <hp:tc> from every row, shift the colAddr of
    the columns to its right, shrink colCnt, and hand the freed width to the
    column at `give_width_to` so each row still sums to the table width.

    Full-width merged rows (title/footnote) are not deleted — their colSpan is
    decremented instead.
    """
    col_cnt = int(tbl.get("colCnt"))
    freed = None
    for tr in table_rows(tbl):
        tcs = table_cells(tr)
        first = tcs[0]
        span = first.find(f"{P}cellSpan")
        if int(span.get("colSpan")) >= col_cnt:          # merged across the table
            span.set("colSpan", str(col_cnt - 1))
            continue
        for tc in tcs:
            if int(tc.find(f"{P}cellAddr").get("colAddr")) == col_addr:
                freed = int(tc.find(f"{P}cellSz").get("width"))
                tr.remove(tc)
                break
        for tc in table_cells(tr):
            ca = tc.find(f"{P}cellAddr")
            a = int(ca.get("colAddr"))
            if a > col_addr:
                ca.set("colAddr", str(a - 1))
    if freed is None:
        raise ValueError("column %d not found" % col_addr)
    for tr in table_rows(tbl):
        tcs = table_cells(tr)
        first = tcs[0]
        if int(first.find(f"{P}cellSpan").get("colSpan")) >= col_cnt - 1:
            continue
        w = tcs[give_width_to].find(f"{P}cellSz")
        w.set("width", str(int(w.get("width")) + freed))
    tbl.set("colCnt", str(col_cnt - 1))
    return table_width_ok(tbl)


def find_pic(root, binary_item_id_ref):
    """The <hp:pic> whose <hc:img> points at `binary_item_id_ref` (e.g. "image3").
    Addressing pictures by BinData id survives paragraph reordering; addressing
    them by paragraph index does not."""
    for pic in root.iter(f"{P}pic"):
        img = pic.find(f".//{C}img")
        if img is not None and img.get("binaryItemIDRef") == binary_item_id_ref:
            return pic
    return None


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


def read_memos(sec):
    """검토 메모(reviewer memo)를 읽는다. 반환: [{id, fieldid, author, date, text}, ...].

    ⚠️ 메모는 `<hp:memo>`가 아니라 **`<hp:fieldBegin type="MEMO">`** 이다
       (`.//hp:memo`로 찾으면 0개 — 흔한 오진). 구조:
         <hp:ctrl><hp:fieldBegin type="MEMO" id=X fieldid=Y>
             <hp:parameters>…Author, CreateDateTime…</hp:parameters>
             <hp:subList>…메모 텍스트…</hp:subList></hp:fieldBegin></hp:ctrl>
           <hp:t>걸린 본문</hp:t>
         <hp:ctrl><hp:fieldEnd beginIDRef=X fieldid=Y/></hp:ctrl>
    """
    out = []
    for fb in sec.iter(f"{P}fieldBegin"):
        if fb.get("type") != "MEMO":
            continue
        params = {sp.get("name"): sp.text for sp in fb.findall(f".//{P}stringParam")}
        text = "".join("".join(t.itertext())
                       for t in fb.findall(f".//{P}subList//{P}t")).strip()
        out.append({"id": fb.get("id"), "fieldid": fb.get("fieldid"),
                    "author": params.get("Author", ""),
                    "date": params.get("CreateDateTime", ""), "text": text})
    return out


def delete_memo(sec, memo_id=None):
    """메모 제거 — MEMO fieldBegin ctrl + 매칭 fieldEnd ctrl 제거, 걸린 본문 <hp:t>는 유지.

    memo_id=None이면 섹션 내 모든 메모 삭제. 한글의 '메모 삭제' 결과와 본문 텍스트 동일함을 검증함
    (header의 memoProperties 도형 정의는 건드리지 않는다 — 무해). 반환: 제거한 메모 수.
    """
    def _drop(el):                       # ctrl로 감싸졌으면 ctrl째, 아니면 el만
        parent = el.getparent()
        if parent is not None and etree.QName(parent).localname == "ctrl":
            parent.getparent().remove(parent)
        elif parent is not None:
            parent.remove(el)

    removed = 0
    for fb in list(sec.iter(f"{P}fieldBegin")):
        if fb.get("type") != "MEMO" or (memo_id and fb.get("id") != memo_id):
            continue
        fid = fb.get("id")
        _drop(fb)
        for fe in list(sec.iter(f"{P}fieldEnd")):
            if fe.get("beginIDRef") == fid:
                _drop(fe)
        removed += 1
    return removed


def read_track_changes(sec):
    """변경추적(reviewer)을 읽는다. 반환: {"insert": [텍스트…], "delete": [텍스트…]}.

    삽입=`<hp:insertBegin/>…텍스트…<hp:insertEnd/>`, 삭제=`<hp:deleteBegin/>…<hp:deleteEnd/>`
    (빈 마커=문단분리/서식). 작성자·시각은 header.xml `<hp:trackChange type="Insert/Delete/
    CharShape" date author…/>`. ⚠️ **수용/거부는 XML로 하지 말 것**(마커+삭제내용 제거가 까다로워
    파일 손상 위험). **한글 COM으로**:
        hwp.HAction.Run("TrackChangeApplyAll")   # 전부 수용
        hwp.HAction.Run("TrackChangeCancelAll")  # 전부 거부
      ★ 반환값이 False여도 실제 적용됨 — insertBegin/deleteBegin 카운트가 0인지로 검증할 것.
      (전 문서 적용이므로, 특정 장만 처리하려면 사본에서 하거나 해당 범위만 남기고 작업)
    """
    import re
    xml = etree.tostring(sec, encoding="unicode")
    strip = lambda s: re.sub(r"<[^>]+>", "", s)
    ins = [strip(m.group(1)) for m in
           re.finditer(r"<[a-z]+:insertBegin[^>]*/>(.*?)<[a-z]+:insertEnd", xml, re.S)]
    dele = [strip(m.group(1)) for m in
            re.finditer(r"<[a-z]+:deleteBegin[^>]*/>(.*?)<[a-z]+:deleteEnd", xml, re.S)]
    return {"insert": [t for t in ins if t.strip()],
            "delete": [t for t in dele if t.strip()]}


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
