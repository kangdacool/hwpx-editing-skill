---
name: hwpx-editing
description: >-
  Safely read, edit, and convert HWPX (Hangul / 한글 .hwpx) word-processor files
  with Python + lxml without corrupting them. Use this whenever a task involves a
  .hwpx file, a 한글 / Hangul / 한컴 (Hancom Office) document, HWPML, or a Korean
  government / academic / 논문 / 보고서 document — including reading or extracting
  text and tables (e.g. exporting complex merged tables to Excel / .xlsx), editing
  paragraphs, tables, images, equations, footnotes/endnotes, or memos, adding or
  positioning captions, fixing layout (orphaned headings, blank pages, columns),
  building a table of contents, or repackaging the zip. Also trigger when a 한글
  file "won't open" / "is corrupted" (파일이 깨졌다 / 한글에서 안 열린다), or when the
  user hands you a legacy .hwp (this skill detects it and tells them to convert to
  .hwpx first). Trigger even if the user only says "edit this 한글 file" or ".hwpx"
  and doesn't mention the internals — naive edits (re-zipping, stale line caches,
  cloned ids) make 한글 refuse to open the file.
license: MIT
---

# HWPX Editing

HWPX is a **zip of XML (HWPML)**. The traps that corrupt a file aren't obvious
from the outside, so **read the relevant section of `references/hwpx-guide.md`
before editing**, and **run the scripts in `scripts/` to repack and verify** —
don't hand-roll the zip or eyeball correctness.

> **HWPX only.** This handles `.hwpx` (zip + XML) exclusively. A legacy `.hwp`
> (OLE binary, signature `D0CF11E0`) must first be converted in 한글 via
> **다른 이름으로 저장 → HWPX(.hwpx)**. The scripts detect `.hwp` and say so.

## The one rule that matters most

**Never re-zip an HWPX with a normal zip writer.** 한글 rejects a file whose
unchanged entries were re-deflated. Use the raw-preserving repacker
(`scripts/hwpxlib.py:repack_preserve`): it byte-copies every entry you didn't
touch and re-deflates only what you changed, so a no-op repack is **byte-identical
to the source** — meaning "if the original opens in 한글, your edit opens too."

## Workflow

1. **Inspect first.** `python scripts/inspect_hwpx.py FILE.hwpx --breaks` — see
   per-section counts (paragraphs, tables, `pic`, `equation`, fields) and, crucially,
   which paragraphs carry a hidden `pageBreak`/`columnBreak`. If a heading is split
   from its content or a page/column is blank, **hunt those breaks first** (§6-A) —
   don't reach for `keepWithNext`. Body-paragraph breaks are usually leftover cruft.
2. **Read the matching guide section** in `references/hwpx-guide.md` (map below).
   The XML ids/refs (`charPrIDRef`, `paraPrIDRef`, `borderFillIDRef`, …) differ per
   file — always read them from the actual file, never assume.
3. **Edit the XML with lxml**, following the invariants:
   - After editing or creating any paragraph, **remove its `<hp:linesegarray>`**
     (cached line layout goes stale → broken spacing). After *structural* edits,
     strip linesegarray from the **whole section** so 한글 fully re-lays-out.
     Use `hwpxlib.strip_linesegarray`.
   - When you **clone** a node (endnote, table, equation, image), it inherits the
     original's `id`/`instId` → duplicates → instability. Reassign fresh ids with
     `hwpxlib.make_uid`, including nested `subList>p` / `tbl`/`tc`/`p` ids.
   - **Reuse existing `charPr`/`paraPr` definitions** instead of adding new ones;
     if you must add, update the `itemCnt` or 한글 rejects the file.
4. **Repack** with `hwpxlib.repack_preserve(src, changed, out, added)`:
   `changed` = edited entries (keep the XML declaration on top), `added` = new
   entries like `BinData/imageN.png` or a new `sectionN.xml` (also register these in
   `content.hpf`).
5. **Verify every build**: `python scripts/verify.py EDITED.hwpx --orig ORIG.hwpx`.
   All hard checks must pass (byte-identity self-check, well-formed XML incl.
   `content.hpf`, zero duplicate ids, IDRef/itemCnt integrity, table cell widths,
   **no 각주/미주 nested inside another 주석**, zip integrity + mimetype first/STORED).
   It also prints a **minimal-change diff** so you can confirm *only intended changes*
   are present.
6. **Render, then look** — `python scripts/audit_layout.py FILE.hwpx`. Steps 1–5 all
   pass on defects that only a render shows: a number broken across two lines
   because its column got one character wider, a table footnote stranded alone on
   the next page, a table-of-contents number that no longer matches. **Any change to
   a table's values, widths, or footnote length needs this step** — the earlier
   checks cannot see layout.
7. **Round-trip in 한글.** LibreOffice can't render HWPX, so render-dependent
   judgments (which heading orphans, whether spacing looks right) need the user to
   open the file in 한글 and, for equations/TOC, run 도구→차례 새로 고침 or
   double-click→close to finalize. Say so.

> 재분석 후 원고의 표를 갱신할 때는 **값을 손으로 옮기지 말고 `fill_table()`로 소스에서
> 채운다** — 그래야 재실행 한 번이 전수 갱신이고, 다시 읽어 소스와 비교하는 것이 그대로
> 검증기가 된다 (§4 표 다시 채우기).

## Scripts (`scripts/`) — run these, don't reinvent

| Script | Purpose |
|---|---|
| `inspect_hwpx.py FILE [--text] [--breaks]` | Structure dump; find hidden page/column breaks. |
| `verify.py EDITED [--orig ORIG]` | The §7 checklist; non-zero exit on failure (CI-gateable). |
| `audit_layout.py FILE [--pdf X.pdf]` | **렌더 기반** 감사 — 구조검사가 통과하는 결함만 노린다(열 폭을 넘겨 두 줄로 쪼개진 숫자, 각주만 남은 희박 페이지, 목차 쪽번호 불일치). `--pdf` 없으면 한글 COM으로 렌더. |
| `audit_typography.py FILE [--expect-face 이름] [--expect-body-pt N]` | 글꼴 혼재와 JUSTIFY+KEEP_WORD 자간 벌어짐을 잡는다. `--expect-*`가 어긋나면 종료코드 1. |
| `remerge_check.py MASTER CHAPTER` | 떼어낸 장이 다시 합쳐지는지 실증 — 실제로 끼워 넣고 렌더해 번호를 읽는다(§6-E). |
| `selftest.py` | Prove the repacker is lossless without a real file. |
| `tables_to_xlsx.py` · `hwpx_to_markdown.py` · `hwpx_to_docx.py` · `data_to_hwpx_table.py` | 변환: 표→Excel, 문서→Markdown(LLM이 읽기용), →Word, Excel/CSV→한글 표. 병합셀 보존. 각각 `-h`. |

**`hwpxlib.py` — import it, don't hand-roll.** 손으로 짜면 틀리는 자리마다 헬퍼가 있다:
재압축 `repack_preserve`(+`drop`/`rename`) · 본문 읽기 `own` · 본문 편집 `replace_text`/
`insert_ctrls_after`/`find_para`(`.tail`-safe) · 문단 복제 `pick_template`/`clone_para` ·
표 `table_grid`/`cell_text`/`set_cell_text`/`fill_table`/`delete_row`/`delete_column`/
`set_column_width`/`table_width_ok` · 그림 `find_pic`/`replace_image` · 주석
`add_endnotes`/`clone_endnote`/`nested_notes` · 장 추출 `extract_section` · 메모·변경추적
`read_memos`/`delete_memo`/`read_track_changes` · 위생 `make_uid`/`strip_linesegarray`/
`find_duplicate_ids`/`structural_counts`. 각 함수의 함정은 docstring과 가이드에 있다.

Scripts need **lxml**; table→Excel also needs **openpyxl**. Python 3.10+.

## Where to read in the guide (`references/hwpx-guide.md`)

Load only the section you need — the guide opens with a **"흔한 실패 TOP" (top
failure modes)**; skim that first, then jump to:

- **§1** 네임스페이스 · `own()` · 섹션 전수 확인 · 셀 단위 텍스트 추출
- **§2** raw-preserving 재압축 (가장 중요)
- **§3** `linesegarray` 제거 · 클론 후 id 중복 제거
- **§4** 문단 · **표**(셀 폭 합 = 표 폭) · **그림**(`orgSz`·`imgDim`·재채우기) ·
  서식 · **각주/미주** · 메모 · 오타감사 스코핑 — 가장 크니 소절만 골라 읽을 것
- **§5** 다단 · 자동 목차 · 한컴 수식 스크립트(LaTeX 아님)
- **§6** 숨은 break → 제목 고아 → 빈 페이지 → 넓은 표/구역 이동 → **E. 장 추출·재병합**
- **§7** `verify.py`가 자동화하는 것과 한글 왕복 주의

## Guardrails

- This edits documents only; it never needs the user's credentials, and it doesn't
  fetch or execute remote content. Work on a **copy** and keep the original.
- Preserve the author's content: only change what the user asked for; the
  minimal-change diff in `verify.py` is your proof.
