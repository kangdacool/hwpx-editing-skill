#!/usr/bin/env python3
"""
verify.py — run the §7 HWPX build checklist.

Usage:
    python verify.py EDITED.hwpx [--orig ORIGINAL.hwpx]

What it checks (each must pass before you ship a file):
    1. no-op repack is byte-identical to the original          (needs --orig)
    2. every sectionN.xml + content.hpf is well-formed XML
    3. zero duplicate ids (0 / 2147483648 sentinels ignored)
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

    # 3. duplicate ids across all sections
    dups_total = {}
    for name in H.section_names(z):
        root = H.etree.fromstring(z.read(name))
        for k, c in H.find_duplicate_ids(root).items():
            dups_total[k] = dups_total.get(k, 0) + c
    hard_ok &= _p(not dups_total, "3. no duplicate ids",
                  "" if not dups_total else f"dupes: {dict(list(dups_total.items())[:8])}")

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
