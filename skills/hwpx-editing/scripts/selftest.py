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

    print()
    print("RESULT:", "ALL PASS" if ok else "FAILURES PRESENT")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
