#!/usr/bin/env python3
"""
remerge_check.py — prove that an extracted 장/구역 re-merges with correct numbering.

    python remerge_check.py MASTER.hwpx CHAPTER.hwpx [--out DIR]

Why this exists
    `extract_section()` gives you a standalone chapter whose 표/그림 캡션 numbers have
    restarted at 1. "They come back when it's merged" is an inference from the XML
    (`secPr/startNum tbl="0"`, `endNotePr/numbering type="ON_SECTION"`), not a fact —
    and the thing that would break it is invisible in the XML: whether 한글 keeps the
    inserted file's 구역. Paste into the body instead of inserting with 「구역 유지」
    and the chapter's endnotes continue from the previous chapter's numbering.

    So: actually insert it, actually render, and read the numbers back.

What it does
    Opens MASTER in 한글, appends CHAPTER at the end via the InsertFile action with
    KeepSection=1, saves, renders to PDF, and reports the caption/endnote numbers the
    appended copy ended up with. Nothing is written back to MASTER.

Reading the result
    · 표/그림 번호가 **앞 장에서 이어지면** 정상 (1부터 다시면 구역이 합쳐진 것).
    · 미주가 **1)부터 다시 시작하면** 정상 (이어지면 구역이 합쳐진 것).
    Both wrong at once = the insert lost the 구역. Check KeepSection and the
    chapter's own secPr.

Needs 한글 (Windows COM) + pypdf. Renders through the project's hwp_render helper
when it is importable, else a direct COM SaveAs.
"""
import argparse
import os
import re
import sys
import tempfile
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass


def _hwp():
    """A registered HwpObject. Prefer the lab helper (it self-heals the security
    module registration); fall back to raw COM."""
    for p in (r"D:\onedrive\claude\agent\tools",):
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)
    try:
        from hwp_render import make_hwp
        return make_hwp()
    except Exception:
        import win32com.client as win32
        h = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
        h.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
        return h


def remerge(master: str, chapter: str, out_dir: str) -> str:
    """Append `chapter` to `master` (구역 유지) and return the saved .hwpx path."""
    master, chapter = os.path.abspath(master), os.path.abspath(chapter)
    out = os.path.join(out_dir, "_remerge_check.hwpx")
    if os.path.exists(out):
        os.remove(out)

    hwp = _hwp()
    hwp.Open(master, "HWPX", "forceopen:true")
    hwp.MovePos(3)                                   # end of document
    act = hwp.CreateAction("InsertFile")
    pset = act.CreateSet()
    act.GetDefault(pset)
    pset.SetItem("FileName", chapter)
    pset.SetItem("KeepSection", 1)                   # ← the whole point
    pset.SetItem("KeepCharshape", 1)
    pset.SetItem("KeepParashape", 1)
    pset.SetItem("KeepStyle", 1)
    if not act.Execute(pset):
        raise SystemExit("[FAIL] InsertFile 실패 — 경로/권한을 확인할 것")
    hwp.SaveAs(out, "HWPX", "")
    hwp.Clear(1)
    hwp.Quit()
    time.sleep(1)
    return out


def render(path: str, pdf: str) -> str:
    try:
        from hwp_render import render_pdf
        render_pdf(path, pdf)
        return pdf
    except Exception:
        hwp = _hwp()
        hwp.Open(path, "HWPX", "forceopen:true")
        hwp.SaveAs(pdf, "PDF", "")
        hwp.Clear(1)
        hwp.Quit()
        return pdf


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Insert a chapter into a master report and check the numbering.")
    ap.add_argument("master", help="the merged report (.hwpx)")
    ap.add_argument("chapter", help="the standalone chapter to append (.hwpx)")
    ap.add_argument("--out", default=None, help="working directory (default: temp)")
    ap.add_argument("--tail-pages", type=int, default=0,
                    help="how many trailing pages the chapter occupies "
                         "(default: auto — from the chapter's own render)")
    args = ap.parse_args()
    work = args.out or tempfile.mkdtemp(prefix="remerge_")
    os.makedirs(work, exist_ok=True)

    from pypdf import PdfReader

    n_tail = args.tail_pages
    if not n_tail:
        solo = render(args.chapter, os.path.join(work, "_chapter_solo.pdf"))
        n_tail = len(PdfReader(solo).pages)
        print(f"단독본 {n_tail}쪽")

    merged = remerge(args.master, args.chapter, work)
    pdf = render(merged, os.path.join(work, "_remerge_check.pdf"))
    pages = PdfReader(pdf).pages
    print(f"병합 결과 {len(pages)}쪽  (master {len(pages) - n_tail} + chapter {n_tail})")

    tail = "".join((p.extract_text() or "") for p in pages[-n_tail:])
    tbl = [int(x) for x in re.findall(r"<표\s*(\d+)>", tail)]
    pic = [int(x) for x in re.findall(r"<그림\s*(\d+)>", tail)]
    notes = [int(x) for x in re.findall(r"(?m)^\s*(\d+)\)\s", tail)]

    ok = True

    def verdict(label, got, restarts_expected):
        nonlocal ok
        if not got:
            print(f"  [--] {label}: 없음")
            return
        lo = min(got)
        restarted = lo == 1
        good = restarted if restarts_expected else not restarted
        ok &= good
        want = "1부터 다시" if restarts_expected else "앞 장에서 이어받음"
        print(f"  [{'ok' if good else 'FAIL'}] {label}: {lo}~{max(got)} "
              f"({len(got)}개) — 기대 {want}")

    print("\n끼워 넣은 장의 번호:")
    verdict("표 캡션", tbl, restarts_expected=False)
    verdict("그림 캡션", pic, restarts_expected=False)
    verdict("미주", notes, restarts_expected=True)

    toc = len(re.findall(r"·{5,}", "".join(
        (p.extract_text() or "") for p in pages[:6])))
    if toc:
        print(f"\n[note] 앞쪽에 점선 목차 {toc}줄이 있다. 자동 목차 필드가 아니면 "
              f"병합 후 쪽번호를 손으로 갱신해야 한다 — fieldBegin type을 확인할 것.")

    print(f"\n작업물: {work}")
    print("RESULT:", "번호 정상 — 이 장은 그대로 보내도 된다." if ok
          else "번호 이상 — 구역이 합쳐졌을 수 있다(KeepSection / 장의 secPr 확인).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
