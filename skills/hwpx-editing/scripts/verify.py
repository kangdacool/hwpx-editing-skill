#!/usr/bin/env python3
"""
verify.py — run the §7 HWPX build checklist.

Usage:
    python verify.py EDITED.hwpx [--orig ORIGINAL.hwpx]

What it checks (each must pass before you ship a file):
    1. no-op repack is byte-identical to the original          (needs --orig)
    2. every sectionN.xml + content.hpf is well-formed XML
    3. zero duplicate ids (0 / 2147483648 sentinels ignored), IDRef/itemCnt integrity,
       table cell widths, no 각주/미주 nested inside another 주석, tbl@rowCnt vs the
       real row count, header.xml secCnt vs the number of sections, and
       cross-reference (상호참조) field integrity
    4. linesegarray inventory (informational)
    5. zip integrity: testzip ok, mimetype first & STORED
    6. structural inventory (pic/tbl/equation/breaks) — compared to --orig if given

Exit code is non-zero if any hard check fails, so you can gate a build on it.
"""
import argparse
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


def _p(ok, label, detail=""):
    mark = "PASS" if ok else "FAIL"
    line = f"[{mark}] {label}"
    if detail:
        line += f"  — {detail}"
    print(line)
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the §7 HWPX build checklist.")
    ap.add_argument("edited", help="the edited .hwpx to check")
    ap.add_argument("--orig", help="original .hwpx (enables byte-identity + diff checks)")
    args = ap.parse_args()

    hard_ok = True
    try:
        H.ensure_hwpx(args.edited)
        if args.orig:
            H.ensure_hwpx(args.orig)
        z = zipfile.ZipFile(args.edited)
    except H.NotHwpxError as e:
        print(str(e))
        return 2
    except zipfile.BadZipFile:
        print("This is not a valid HWPX (a zip archive). "
              "이 파일은 올바른 HWPX(zip)가 아닙니다. (이 도구는 HWPX 전용입니다.)")
        return 2

    # 1. byte-identity self-check on the ORIGINAL (proves the repacker is lossless)
    if args.orig:
        ok = H.self_verify_identical(args.orig)
        hard_ok &= _p(ok, "1. no-op repack byte-identical to original",
                      "" if ok else "repacker changed unchanged bytes — DO NOT ship")

    # 2. well-formed XML for all sections + content.hpf
    wf = H.check_wellformed(z)
    bad = [f"{k}: {v}" for k, v in wf.items() if v != "OK"]
    hard_ok &= _p(not bad, "2. all XML well-formed (sections + content.hpf)",
                  "; ".join(bad) if bad else f"{len(wf)} entries OK")

    # 3. duplicate ids. 한글 legitimately reuses ids on empty structural
    #    paragraphs, so a real file can ship pre-existing duplicates. Only ids the
    #    EDIT newly duplicated are a hard failure; with --orig we separate the two,
    #    without --orig we can only report duplicates informationally.
    edited_dups = {}
    for name in H.section_names(z):
        root = H.etree.fromstring(z.read(name))
        for k, c in H.find_duplicate_ids(root).items():
            edited_dups[k] = edited_dups.get(k, 0) + c
    if args.orig:
        orig_dups = set()
        zo3 = zipfile.ZipFile(args.orig)
        for name in H.section_names(zo3):
            orig_dups.update(H.find_duplicate_ids(H.etree.fromstring(zo3.read(name))).keys())
        new_dups = {k: v for k, v in edited_dups.items() if k not in orig_dups}
        inherited = {k: v for k, v in edited_dups.items() if k in orig_dups}
        detail = "" if not new_dups else f"edit-introduced dupes: {dict(list(new_dups.items())[:8])}"
        if inherited:
            note = f"{len(inherited)} pre-existing in orig, ignored"
            detail = f"{detail}  [{note}]" if detail else f"({note})"
        hard_ok &= _p(not new_dups, "3. no edit-introduced duplicate ids", detail)
    elif edited_dups:
        print(f"[info] 3. duplicate ids present (informational; pass --orig to gate "
              f"on edit-introduced ones): {dict(list(edited_dups.items())[:8])}")
    else:
        _p(True, "3. no duplicate ids")

    # 3b. IDRef/itemCnt integrity: dangling charPr/paraPr/borderFill/style refs or a
    #     stale itemCnt make 한글 reject the file (§4 "added a charPr, forgot itemCnt").
    ir = H.check_idref_integrity(z)
    ir_bad = ir["itemcnt"] + ir["dangling"]
    hard_ok &= _p(not ir_bad, "3b. IDRef/itemCnt integrity (charPr/paraPr/borderFill/style)",
                  "" if not ir_bad else "; ".join(ir_bad[:6]))

    # 3c. Table geometry: every row's cell widths must sum to the table width
    #     (한글 rejects a table whose columns do not add up). Any column
    #     insert/delete/resize can break this, and nothing else here catches it.
    width_bad, width_skipped = [], 0
    for name in H.section_names(z):
        root = H.etree.fromstring(z.read(name))
        for n, tbl in enumerate(root.iter(f"{H.P}tbl")):
            ok, total, sums = H.table_width_ok(tbl)
            if total is None:
                width_skipped += 1
                continue
            if not ok:
                off = {i: s for i, s in enumerate(sums) if s != total}
                width_bad.append(f"{name} tbl#{n} width={total} rows={dict(list(off.items())[:3])}")
    hard_ok &= _p(not width_bad, "3c. table cell widths sum to table width",
                  "; ".join(width_bad[:4]) if width_bad
                  else (f"{width_skipped} table(s) had no measurable geometry"
                        if width_skipped else ""))

    # 3d. Footnote/endnote nesting: 한글 cannot represent a 주석 inside another 주석,
    #     and such a file errors on open. It happens when a second endnote is inserted
    #     at the same anchor and the target run handle still points INSIDE the endnote
    #     that was just built (lxml's .//hp:run / .//hp:p descend into subList).
    #     Everything else here passes on it — the XML is well-formed with unique ids —
    #     so this needs its own check. Real case: 신부전 제7장 미주 36, 2026-07-23.
    nested_bad, autonum_odd = [], []
    for name in H.section_names(z):
        root = H.etree.fromstring(z.read(name))
        for note in root.iter(f"{H.P}endNote", f"{H.P}footNote"):
            inner = [x for x in note.iter(f"{H.P}endNote", f"{H.P}footNote") if x is not note]
            if inner:
                nested_bad.append(
                    f"{name} {H.etree.QName(note).localname}[{note.get('number')}] contains "
                    f"{len(inner)} nested 주석 (instId "
                    f"{', '.join(str(x.get('instId')) for x in inner[:3])})")
            num = note.get("number")
            an = note.find(f"{H.P}subList/{H.P}p/{H.P}run/{H.P}ctrl/{H.P}autoNum")
            if an is not None and num and an.get("num") not in (None, num):
                autonum_odd.append(f"{name} [{num}] autoNum num={an.get('num')}")
    hard_ok &= _p(not nested_bad, "3d. no 각주/미주 nested inside another 주석",
                  "" if not nested_bad else "; ".join(nested_bad[:4]))
    if autonum_odd:
        print(f"[warn] 3d'. autoNum num != endNote number on {len(autonum_odd)} 주석 "
              f"(한글 recalculates on open; harmless unless you gate on it): "
              f"{'; '.join(autonum_odd[:3])}")

    # 3e. tbl@rowCnt vs the actual <hp:tr> count. 한글 reads the table by the
    #     declared count, so a mismatch collapses the whole document onto one page
    #     (§4-표, 흔한 실패 20). Every other check here passes on it: the XML is
    #     well-formed, ids are unique, and the cell widths still add up.
    rowcnt_bad = []
    for name in H.section_names(z):
        root = H.etree.fromstring(z.read(name))
        for n, declared, actual in H.rowcnt_mismatches(root):
            rowcnt_bad.append(f"{name} tbl#{n} rowCnt={declared} but {actual} <hp:tr>")
    hard_ok &= _p(not rowcnt_bad, "3e. tbl@rowCnt matches the actual row count",
                  "" if not rowcnt_bad else "; ".join(rowcnt_bad[:4]))

    # 3f. header.xml's secCnt vs the number of sectionN.xml entries. Extract a 장
    #     from a merged report and leave secCnt alone and the file still OPENS —
    #     it just shows a single blank page (§6-E, 흔한 실패 21).
    #     Absence is not a failure: the attribute is optional and the head element
    #     may carry a default namespace instead of the hh: prefix. Only a stated
    #     count that contradicts the entries is a hard failure.
    mismatch = H.seccnt_mismatch(z)
    hard_ok &= _p(mismatch is None, "3f. header.xml secCnt matches the section count",
                  "" if mismatch is None else
                  f"secCnt={mismatch[0]} but {mismatch[1]} sectionN.xml "
                  f"({', '.join(H.section_names(z)[:4])})")

    # 3g. Cross-reference fields (상호참조). 재인용을 미주 번호에 묶는 필드는 본문을
    #     통째로 치환하면 ctrl 쌍째 사라지고, 인용번호가 리터럴로 남아 있으면 번호가
    #     밀릴 때만 틀린다 — 둘 다 XML 검사·렌더 한 번으로는 안 보인다.
    #     상세·수리는 crossref_check.py (--baseline / --fix-cache).
    try:
        import crossref_check as X
        xerr, xwarn, xinfo = [], [], []
        for name in H.section_names(z):
            X.check_section(name, H.etree.fromstring(z.read(name)), xerr, xwarn, xinfo)
        hard_ok &= _p(not xerr, "3g. 상호참조(CROSSREF) 무결성",
                      "" if not xerr else "; ".join(xerr[:3]))
        if xwarn:
            print(f"[warn] 3g'. 리터럴 인용번호 후보 {len(xwarn)}건 — "
                  f"crossref_check.py로 확인: {xwarn[0][:110]}")
    except Exception as e:  # 검사기 자체 문제로 빌드를 막지는 않는다
        print(f"[warn] 3g. 상호참조 검사를 건너뜀 ({type(e).__name__}: {e})")

    # 5. zip integrity (report before 4/6 which are informational)
    zi = H.zip_integrity(z)
    hard_ok &= _p(zi["testzip_ok"], "5a. zip testzip() ok")
    hard_ok &= _p(zi["mimetype_first"], "5b. mimetype is first entry")
    hard_ok &= _p(zi["mimetype_stored"], "5c. mimetype is STORED")

    # 4 & 6. informational inventories
    print("\n--- informational (§7.4 linesegarray, §7.6 structure) ---")
    for name in H.section_names(z):
        root = H.etree.fromstring(z.read(name))
        c = H.structural_counts(root)
        print(f"  {name}: p={c['p']} tbl={c['tbl']} pic={c['pic']} "
              f"eq={c['equation']} field={c['fieldBegin']} "
              f"lineseg={c['linesegarray']} "
              f"pageBreak={c['pageBreak_paras']} colBreak={c['columnBreak_paras']}")

    if args.orig:
        print("\n--- §7 minimal-change diff (edited vs re-serialized original) ---")
        zo = zipfile.ZipFile(args.orig)
        for name in H.section_names(z):
            if name in zo.namelist():
                diff = H.minimal_diff(zo.read(name), z.read(name))
                if diff:
                    print(f"  {name}: {len(diff)} changed lines "
                          f"(first few below)")
                    for ln in diff[:6]:
                        print(f"     {ln}")
                else:
                    print(f"  {name}: no changes")

    print()
    if hard_ok:
        print("RESULT: all hard checks PASSED — safe to open in 한글 for a round-trip.")
        return 0
    print("RESULT: one or more hard checks FAILED — fix before shipping.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
