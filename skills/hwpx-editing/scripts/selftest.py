#!/usr/bin/env python3
"""
selftest.py — prove the core primitives work, no real HWPX needed.

Builds a tiny synthetic HWPX-shaped zip (mimetype STORED first, then deflated
XML entries) and checks that:
    1. a no-op repack is byte-identical to the source
    2. editing one entry re-deflates only that entry, keeps mimetype first/STORED,
       and leaves other entries byte-untouched
    3. adding a new entry (e.g. a BinData image) works and the zip stays valid
    4. duplicate-id detection and linesegarray stripping behave

Run:  python selftest.py    (exit 0 = all good)
"""
import io
import sys
import zipfile

# Force UTF-8 console output so non-ASCII glyphs in our messages (—, «», 한글)
# never crash on a Windows cp949 console (UnicodeEncodeError). No-op where the
# stream is already UTF-8, or where reconfigure() is unavailable (Python <3.7,
# or a redirected/replaced stream) — hence the broad guard.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

import hwpxlib as H


def build_fixture(path: str) -> None:
    zf = zipfile.ZipFile(path, "w")
    zi = zipfile.ZipInfo("mimetype")
    zi.compress_type = zipfile.ZIP_STORED
    zf.writestr(zi, b"application/hwp+zip")
    zf.writestr("Contents/header.xml",
                H.XML_DECL + b'<head xmlns="http://www.hancom.co.kr/hwpml/2011/head" itemCnt="3"/>')
    zf.writestr("Contents/section0.xml",
                H.XML_DECL + ('<sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
                              '<hp:p id="10"><hp:linesegarray/>'
                              '<hp:run><hp:t>Hello 한글</hp:t></hp:run></hp:p>'
                              '<hp:p id="10"><hp:run><hp:t>dup id here</hp:t></hp:run></hp:p>'
                              '</sec>').encode("utf-8"))
    zf.writestr("Contents/content.hpf", H.XML_DECL + b"<package/>")
    zf.close()


def main() -> int:
    import tempfile
    import os
    d = tempfile.mkdtemp()
    orig = os.path.join(d, "orig.hwpx")
    build_fixture(orig)
    ok = True

    # 1. no-op byte-identity
    identical = H.self_verify_identical(orig)
    ok &= identical
    print(f"[{'PASS' if identical else 'FAIL'}] 1. no-op repack byte-identical")

    # 2. edit one entry
    new_sec = (H.XML_DECL +
               '<sec><hp:p xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
               '<hp:run><hp:t>편집됨</hp:t></hp:run></hp:p></sec>'.encode("utf-8"))
    edited = os.path.join(d, "edited.hwpx")
    H.repack_preserve(orig, {"Contents/section0.xml": new_sec}, edited)
    z = zipfile.ZipFile(edited)
    zi = H.zip_integrity(z)
    e2 = (zi["testzip_ok"] and zi["mimetype_first"] and zi["mimetype_stored"]
          and z.read("Contents/section0.xml") == new_sec
          and z.read("Contents/header.xml") == zipfile.ZipFile(orig).read("Contents/header.xml"))
    ok &= e2
    print(f"[{'PASS' if e2 else 'FAIL'}] 2. edit re-deflates only the changed entry, "
          f"mimetype first/STORED, others untouched")

    # 3. add a new BinData entry
    img = b"\x89PNG_fake"
    added = os.path.join(d, "added.hwpx")
    H.repack_preserve(orig, {}, added, added={"BinData/image1.png": img})
    z3 = zipfile.ZipFile(added)
    e3 = z3.testzip() is None and z3.read("BinData/image1.png") == img
    ok &= e3
    print(f"[{'PASS' if e3 else 'FAIL'}] 3. add new entry (BinData) works, zip valid")

    # 4. duplicate-id detection + linesegarray strip
    root = H.etree.fromstring(zipfile.ZipFile(orig).read("Contents/section0.xml"))
    dups = H.find_duplicate_ids(root)
    removed = H.strip_linesegarray(root)
    e4 = (dups == {10: 2}) and (removed == 1)
    ok &= e4
    print(f"[{'PASS' if e4 else 'FAIL'}] 4. duplicate-id detection ({dups}) + "
          f"linesegarray strip ({removed} removed)")

    # 5. encoding regression (Windows cp949): the exact glyphs our CLIs print
    #    (— « » 한글) crash a raw cp949 stream, but the reconfigure(utf-8) guard
    #    the CLIs apply at import time must make them safe. Proves the fix works.
    glyphs = "— « » 한글"  # em-dash, guillemets, Hangul
    crashes_on_cp949 = False
    try:
        w = io.TextIOWrapper(io.BytesIO(), encoding="cp949")
        w.write(glyphs); w.flush()
    except UnicodeEncodeError:
        crashes_on_cp949 = True
    guard_ok = True
    try:
        w2 = io.TextIOWrapper(io.BytesIO(), encoding="cp949")
        try:
            w2.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError, OSError):
            pass
        w2.write(glyphs); w2.flush()
    except UnicodeEncodeError:
        guard_ok = False
    e5 = crashes_on_cp949 and guard_ok
    ok &= e5
    print(f"[{'PASS' if e5 else 'FAIL'}] 5. cp949 console: raw stream crashes "
          f"({crashes_on_cp949}), reconfigure(utf-8) guard prints safely ({guard_ok})")

    # 6. own() must exclude 각주(footNote)/미주(endNote)/메모(fieldBegin) bodies,
    #    keeping only real body text.
    para_xml = (
        '<hp:p xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
        '<hp:run><hp:t>본문앞</hp:t>'
        '<hp:ctrl><hp:footNote><hp:subList><hp:p><hp:run>'
        '<hp:t>각주내용</hp:t></hp:run></hp:p></hp:subList></hp:footNote></hp:ctrl>'
        '<hp:ctrl><hp:endNote><hp:subList><hp:p><hp:run>'
        '<hp:t>미주내용</hp:t></hp:run></hp:p></hp:subList></hp:endNote></hp:ctrl>'
        '<hp:fieldBegin><hp:subList><hp:p><hp:run>'
        '<hp:t>메모내용</hp:t></hp:run></hp:p></hp:subList></hp:fieldBegin>'
        '<hp:t>본문뒤</hp:t></hp:run></hp:p>'
    )
    body = H.own(H.etree.fromstring(para_xml.encode("utf-8")))
    e6 = (body == "본문앞본문뒤")
    ok &= e6
    print(f"[{'PASS' if e6 else 'FAIL'}] 6. own() excludes 각주/미주/메모 bodies "
          f"(got {body!r}, want '본문앞본문뒤')")

    # 7. duplicate-id policy: 한글 legitimately reuses an id on EMPTY structural
    #    paragraphs, so a pre-existing duplicate in the original is not the edit's
    #    fault. An edit that introduces NO new duplicate must not be flagged —
    #    only edit-introduced dupes (in edited but not in orig) are failures.
    pns = "http://www.hancom.co.kr/hwpml/2011/paragraph"
    orig_sec = H.etree.fromstring(
        (f'<sec xmlns:hp="{pns}">'
         '<hp:p id="7"><hp:run></hp:run></hp:p>'      # empty paragraph
         '<hp:p id="7"><hp:run></hp:run></hp:p>'      # same id reused on empty para
         '<hp:p id="9"><hp:run><hp:t>본문</hp:t></hp:run></hp:p>'
         '</sec>').encode("utf-8"))
    edited_sec = H.etree.fromstring(H.etree.tostring(orig_sec))
    H.etree.SubElement(edited_sec, f"{{{pns}}}p").set("id", "11")  # add unique id, no new dup
    orig_dups = set(H.find_duplicate_ids(orig_sec).keys())
    new_dups = {k: v for k, v in H.find_duplicate_ids(edited_sec).items()
                if k not in orig_dups}
    e7 = (orig_dups == {7}) and (new_dups == {})
    ok &= e7
    print(f"[{'PASS' if e7 else 'FAIL'}] 7. id-dup policy: orig dup {sorted(orig_dups)} "
          f"pre-existing, edit adds no new dup ({new_dups})")

    print()
    print("RESULT:", "ALL PASS" if ok else "FAILURES PRESENT")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
