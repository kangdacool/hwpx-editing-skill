#!/usr/bin/env python3
"""
inspect_hwpx.py — dump the structure of an HWPX so you can plan an edit safely.

Usage:
    python inspect_hwpx.py FILE.hwpx [--text] [--breaks]

Shows, per section: paragraph/table/pic/equation/field counts, linesegarray
count, and paragraphs carrying pageBreak/columnBreak (the usual culprit behind
"a heading split off from its content" — see §6-A). With --text it prints the
real body text (endnotes/memos excluded via own()); with --breaks it lists every
paragraph that carries a page/column break plus its paraPrIDRef.
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Inspect HWPX structure.")
    ap.add_argument("file", help="the .hwpx to inspect")
    ap.add_argument("--text", action="store_true", help="print real body text per paragraph")
    ap.add_argument("--breaks", action="store_true", help="list paragraphs with page/column breaks")
    args = ap.parse_args()

    try:
        H.ensure_hwpx(args.file)
        z = zipfile.ZipFile(args.file)
    except H.NotHwpxError as e:
        print(str(e))
        return 2
    except zipfile.BadZipFile:
        print("This is not a valid HWPX (a zip archive). "
              "이 파일은 올바른 HWPX(zip)가 아닙니다. (이 도구는 HWPX 전용입니다.)")
        return 2
    names = H.section_names(z)
    print(f"{args.file}")
    print(f"  entries: {len(z.namelist())}  sections: {len(names)}  "
          f"BinData: {sum(1 for n in z.namelist() if n.startswith('BinData/'))}")
    print()

    for name in names:
        root = H.etree.fromstring(z.read(name))
        c = H.structural_counts(root)
        print(f"== {name} ==")
        print(f"   p={c['p']} tbl={c['tbl']} pic={c['pic']} equation={c['equation']} "
              f"fieldBegin={c['fieldBegin']} endNote={c['endNote']} "
              f"footNote={c['footNote']} linesegarray={c['linesegarray']}")
        print(f"   paragraphs w/ pageBreak={c['pageBreak_paras']}  "
              f"columnBreak={c['columnBreak_paras']}")

        if args.breaks:
            for para in root.findall(f".//{H.P}p"):
                pb = para.get("pageBreak") in ("1", "true")
                cb = para.get("columnBreak") in ("1", "true")
                if pb or cb:
                    flags = ",".join(f for f, on in
                                     (("pageBreak", pb), ("columnBreak", cb)) if on)
                    snippet = H.own(para)[:40].replace("\n", " ")
                    print(f"     [{flags}] paraPr={para.get('paraPrIDRef')} "
                          f"id={para.get('id')}  «{snippet}»")

        if args.text:
            for para in root.findall(f".//{H.P}p"):
                txt = H.own(para).strip()
                if txt:
                    print(f"     {txt[:100]}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
