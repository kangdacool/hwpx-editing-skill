---
name: hwpx-editing
description: >-
  Safely read and edit HWPX (Hangul / 한글 .hwpx) word-processor files with
  Python + lxml without corrupting them. Use this whenever the task involves a
  .hwpx file, a 한글/Hangul document, HWPML, or Korean government/academic
  documents — including reading or extracting text/tables, editing paragraphs,
  tables, images, equations, footnotes/endnotes, or memos, fixing layout
  (orphaned headings, blank pages, columns), building a table of contents, or
  repackaging the zip. Trigger this even if the user only says "edit this 한글
  file" or ".hwpx" and doesn't mention the internals, because naive edits
  (re-zipping, stale line caches, cloned ids) make 한글 refuse to open the file.
license: MIT
---

# HWPX Editing

HWPX is a **zip of XML (HWPML)**. The traps that corrupt a file aren't obvious
from the outside, so **read the relevant section of `references/hwpx-guide.md`
before editing**, and **run the scripts in `scripts/` to repack and verify** —
don't hand-roll the zip or eyeball correctness.

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
6. **Round-trip in 한글.** LibreOffice can't render HWPX, so render-dependent
   judgments (which heading orphans, whether spacing looks right) need the user to
   open the file in 한글 and, for equations/TOC, run 도구→차례 새로 고침 or
   double-click→close to finalize. Say so.

## Scripts (`scripts/`) — run these, don't reinvent

| Script | Purpose |
|---|---|
| `hwpxlib.py` | Library: `repack_preserve`, `own` (real body text, excludes 각주·미주·메모 / footnote·endnote·memo), `make_uid`, `strip_linesegarray`, `find_duplicate_ids`, `structural_counts`, plus §7 verify helpers. Import it. |
| `inspect_hwpx.py FILE [--text] [--breaks]` | Structure dump; find hidden page/column breaks. |
| `verify.py EDITED [--orig ORIG]` | Run the full §7 checklist; non-zero exit on failure (CI-gateable). |
| `selftest.py` | Prove the repacker is lossless without a real file. |

Scripts need **lxml** (`pip install lxml`). Python 3.10+.

## Where to read in the guide (`references/hwpx-guide.md`)

Load only the section you need — the guide opens with a **"흔한 실패 TOP" (top
failure modes)**; skim that first, then jump to:

- **§1 Structure & parsing** — namespaces, `own()`, "check all sections", table
  text per-cell (not bulk `itertext`).
- **§2 Repack (raw-preserving)** — the crown-jewel repacker. Mirrors `hwpxlib`.
- **§3 Common rules** — `linesegarray` removal, id-dedup after cloning.
- **§4 Content editing** — paragraphs, tables (cell width sums must equal table
  width or 한글 rejects it; merges), **images** (`orgSz`=px×75, size math, verify by
  *content* not extraction order, matplotlib legibility "small figure, big text"),
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
