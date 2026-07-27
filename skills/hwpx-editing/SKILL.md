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
   `content.hpf`, zero duplicate ids, zip integrity + mimetype first/STORED). It
   also prints a **minimal-change diff** so you can confirm *only intended changes*
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

### 표를 다시 채울 때 (재분석 후 원고 표 갱신)

문서에 붙여넣은 표는 **붙여넣은 순간의 분석 결과에 얼어붙는다.** 재분석을 하면 본문은
사람이 고쳐 쓰지만 표는 따라오지 않아, 표와 본문이 서로 다른 분석을 담은 채 공존한다.
값을 손으로 옮기지 말고 소스에서 채운다:

```python
rows = [r[1:] for r in csv.reader(open(SRC, encoding="utf-8"))][1:]
hwpxlib.fill_table(tbl, rows, row_offset=3, col_offset=1)   # 헤더 3행 · 라벨 열 보존
```

그러면 (a) 재실행 한 번이 전수 갱신이고, (b) `table_grid()` 로 다시 읽어 같은 소스와
비교하는 것이 그대로 검증기가 된다. 열을 지우거나 넓혀야 하면 `delete_column` /
`set_column_width` 를 쓴다 — 폭 합계를 손으로 맞추면 한글이 파일을 거부한다.

## Scripts (`scripts/`) — run these, don't reinvent

| Script | Purpose |
|---|---|
| `hwpxlib.py` | Library: `repack_preserve`, `pick_template`/`clone_para`/`run_patterns` (문단 복제 — 직접 하지 말 것), `own` (real body text, excludes 각주·미주·메모 / footnote·endnote·memo), `replace_text`/`insert_ctrls_after`/`find_para` (**`.tail`-safe** 본문 편집 — run 텍스트는 `<hp:t>.text` **및** 인라인 자식(`lineBreak`…)의 `.tail`에 나뉘어 있어 `t.text`만 보면 `lineBreak` 뒤 글자를 통째로 놓침; 손으로 짜지 말 것), **표 편집** `table_grid`/`cell_text` (셀 안 문단 = 줄바꿈이므로 **구분자 보존** 추출), `set_cell_text`, `fill_table` (소스 데이터 → 표 본문), `delete_row`/`delete_column`/`set_column_width`/`table_width_ok` (폭 합계·rowAddr 자동 보존), `find_pic` (문단 위치 말고 BinData id로 그림 찾기), `read_memos`/`delete_memo` (검토 메모 = `fieldBegin type="MEMO"`, NOT `hp:memo`), `read_track_changes` (변경추적 읽기; accept/reject는 한글 COM `TrackChangeApplyAll`/`CancelAll`), `make_uid`, `strip_linesegarray`, `find_duplicate_ids`, `structural_counts`, `replace_image` (swap a picture + update every geometry field incl. the easy-to-forget `imgDim`), plus §7 verify helpers. Import it. |
| `inspect_hwpx.py FILE [--text] [--breaks]` | Structure dump; find hidden page/column breaks. |
| `verify.py EDITED [--orig ORIG]` | Run the full §7 checklist; non-zero exit on failure (CI-gateable). |
| `selftest.py` | Prove the repacker is lossless without a real file. |
| `tables_to_xlsx.py FILE [OUT]` | Export tables to Excel (.xlsx), merged cells preserved (needs `openpyxl`). Cells with only an image/equation → `[그림]`/`[수식]`; legacy `.hwp` is refused with guidance. |
| `audit_typography.py FILE [--expect-face 이름] [--expect-body-pt N]` | 서식 일관성 감사: 실제 쓰이는 charPr을 사용횟수·크기·글꼴로 집계. **글꼴 혼재**와 **JUSTIFY+KEEP_WORD 영문 문단**(자간 벌어짐)을 잡는다. `--expect-*`를 주면 어긋날 때 종료코드 1. |
| `audit_layout.py FILE [--pdf RENDER.pdf]` | **렌더 기반** 감사 — 구조검사가 통과하는 결함만 노린다: 셀 내용이 열 폭을 넘겨 **숫자가 두 줄로 쪼개진 것**(`4,70`/`1`), 표 각주가 혼자 넘어간 **희박 페이지**, **목차 페이지 번호 ↔ 실제 페이지** 불일치, 표 폭 합계. `--pdf` 없으면 한글 COM으로 직접 렌더. |
| `hwpx_to_markdown.py FILE [OUT.md]` | Extract the document's text + tables as Markdown (for an LLM to read/summarize; no OUT → stdout). |
| `hwpx_to_docx.py FILE [OUT.docx]` | Export to Word (.docx), tables + merged cells preserved (needs `python-docx`; for journals / non-한글 co-authors). |
| `data_to_hwpx_table.py DATA.(xlsx\|csv) TARGET.hwpx [OUT] [--sheet]` | Insert an Excel/CSV table into a 한글 doc, merged cells preserved (needs `openpyxl` for xlsx; TARGET must contain a table for cell styling; CSV encoding auto). |

Scripts need **lxml** (`pip install lxml`); the table→Excel export also needs **openpyxl**. Python 3.10+.

## Where to read in the guide (`references/hwpx-guide.md`)

Load only the section you need — the guide opens with a **"흔한 실패 TOP" (top
failure modes)**; skim that first, then jump to:

- **§1 Structure & parsing** — namespaces, `own()`, "check all sections", table
  text per-cell (not bulk `itertext`).
- **§2 Repack (raw-preserving)** — the crown-jewel repacker. Mirrors `hwpxlib`.
- **§3 Common rules** — `linesegarray` removal, id-dedup after cloning.
- **§4 Content editing** — paragraphs, tables (cell width sums must equal table
  width or 한글 rejects it; merges), **images** (`orgSz`=px×75, size math, swap via
  `replace_image` so `imgDim` is never forgotten — a stale imgDim crops the picture;
  verify by *content*/한글-render not extraction order, matplotlib legibility "small figure, big text"),
  formatting, **endnotes/footnotes** (`<hp:ctrl>` wrapping required), **memos**,
  and typo-audit scoping (no blanket regex).
- **§5 Columns · TOC · equations** — `colPr`, `TABLEOFCONTENTS` from outline-level
  paragraphs, 한컴 equation script (not LaTeX; table of forms).
- **§6 Page/column management** — **hidden breaks first**, orphaned-heading
  prevention (`keepWithNext`, no empty paragraph after a heading, conditional
  `columnBreak`), blank-page cleanup, wide tables → 1-column region + moving a
  `secPr` block across section boundaries.
- **§7 Verification checklist** — what `verify.py` automates, plus the round-trip
  caveat.

## Guardrails

- This edits documents only; it never needs the user's credentials, and it doesn't
  fetch or execute remote content. Work on a **copy** and keep the original.
- Preserve the author's content: only change what the user asked for; the
  minimal-change diff in `verify.py` is your proof.
