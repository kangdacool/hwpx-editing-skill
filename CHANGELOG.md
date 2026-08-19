# Changelog

이 파일은 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) 형식을 따르고,
버전은 [Semantic Versioning](https://semver.org/spec/v2.0.0.html)을 씁니다.

## [0.1.4] — 2026-08-19

### Added

- **`scripts/hwp_to_hwpx.py` — batch legacy `.hwp` → `.hwpx` (or `.pdf`) via 한글 COM.**
  The skill previously said "convert it in 한글 first", which is fine for one file and
  useless for a folder of thousands. Established against a real 5,187-file archive.
- **Password-protected `.hwp` can be converted.** 한컴 provides no API to pass a password
  to `Open()` (official forum answer) — but that is not the same as impossible, since the
  *dialog* is automatable. Three conditions must all hold, and missing any one produces
  the identical symptom (`Open()` never returns — no exception, no timeout):
  ① the security module is registered as `FilePathCheckerModule` — **not**
  `FilePathCheckerModuleExample`, the name in 한컴's own sample code, whose use raises an
  **invisible** "파일 접근 허용" dialog (`HNC_DIALOG`, `IsWindowVisible == 0`) that blocks
  forever; ② the password is typed into the edit field and submitted with **`{ENTER}`**
  (the 확인 button's `invoke()`/`click_input()` do nothing), from the **main thread**
  (a worker thread finds the window but its UIA calls silently no-op); ③
  **`SetMessageBoxMode(0x00011011)` before `Open()`** — otherwise every call *after* the
  document opens (`SaveAs`, `GetTextFile`, …) hangs on another unnamed modal.
- **Output validation, because a "successful" conversion can be unusable.** Exporting a
  locked `.hwp` to `.hwpx` keeps the protection: `Contents/section0.xml` comes out
  encrypted, so every XML tool sees binary rather than markup. The converter strips it
  by copying the body into a fresh document and then **checks that the result parses**
  (`hwpx_is_readable`) instead of trusting the exit status. PDF export is unaffected.
- **Lock detection without opening anything:** HWP 5.0's `FileHeader` stream, DWORD at
  offset 36, **bit `0x02`** = password set. `--scan` reports which files are locked; a
  five-thousand-file folder scans in minutes, which is what makes it practical to handle
  them separately instead of letting each burn a timeout.

### Changed

- SKILL.md gained a **"Legacy `.hwp` → `.hwpx`, and the 한글 COM traps"** section: COM has
  no timeouts, so four distinct causes all present as "it stopped" — diagnose by enabling
  one condition at a time. Batch hygiene documented too (one COM object per file, since a
  COM object is bound to its creating thread; per-file timeout; and the caveat that
  cleanup kills *every* `Hwp.exe`, so run one instance at a time).

## [0.1.3] — 2026-08-03

### Added

- **Guide §7: ship the file 한글 itself paginated.** Structural edits force you to drop
  `linesegarray` (the line-layout cache), and a file with none of it announces that no
  human ever saved it from 한글. Measured behaviour: 한글 *preserves* an existing cache
  but never creates one — opening and saving leaves `0 → 0`. It appears only after
  layout actually completes (`0 → 1,696`); reading the page count is the surest trigger,
  since counting pages requires pagination to finish. Two traps: the pass is
  asynchronous, so the same code produced 1,696 once and 0 the next time — count the
  result and retry; and saving over the path that is currently open does not take.
- **Guide §7: verifying a format conversion.** Render both files and compare the text —
  only a render shows what a conversion dropped. To know whether the *fields* survived
  as fields rather than as baked-in text, round-trip back (hwp → hwpx) and run
  `crossref_check.py`. Matching renders only prove the numbers look right today.
- **Guide §7: memo balloons break render-text comparison.** PDF extraction splices the
  author, date and memo body into the middle of the paragraph, so a comparator reports a
  mismatch where the document is fine. Two of two mismatches in a real run were this.

## [0.1.2] — 2026-08-03

Adds cross-references (상호참조) — the field 한글 uses to cite an endnote a second
time without duplicating it. Korean government and academic reports lean on this:
the house rule is "use endnotes, and when you cite an earlier source again, put only
the number in the body." Editing such a document as plain text quietly destroys it.

### Added

- **`crossref_check.py`** — integrity check for cross-reference fields.
  Catches the three ways they break, each of which passes every existing check:
  a field whose `fieldBegin`/`fieldEnd` pair was severed, a citation number left
  as **literal text** (right today, wrong the moment anything renumbers), and
  `RefContentType=OBJECT_TYPE_PAGE`, which does not track the endnote number at
  all. `--baseline BEFORE.hwpx` diffs the endnote↔citation map across an edit so a
  silently dropped citation is visible; `--fix-cache OUT.hwpx` recomputes the
  cached display numbers.
- **Helpers in `hwpxlib`**: `read_crossrefs`, `crossref_template`,
  `clone_crossref`, `add_crossrefs`, `sync_crossref_cache`.
- **`verify.py` check 3g** gates on cross-reference integrity.
- **Guide §4 "상호참조"** documents the field layout and the measured behaviour:
  한글 recomputes these numbers when it opens the file, so inserting an endnote in
  the middle is safe — what is not safe is losing the field.

### Fixed

- **`make_uid()` no longer issues ids at or above 2³¹.** It used to continue from
  the document's largest id, and 한글 documents routinely carry ids around
  3,1xx,xxx,xxx — so a freshly cloned endnote got an `instId` past the 32-bit
  boundary and every cross-reference pointing at it rendered as `?)`. The XML was
  well-formed, ids were unique, and `verify.py` passed; only opening the file in
  한글 showed it.

### Notes

- Two parsing traps are now handled in the helpers rather than left to the caller:
  a field can **span two runs** (한글 splits runs at formatting boundaries, so the
  `fieldBegin` sits at the end of one run and the cached number in the next —
  searching within a single run reports an empty cache), and **two consecutive
  citations can share one run**, so deleting the run removes both.

## [0.1.1] — 2026-07-30

Closes the gap between what the guide documents and what the tooling actually
enforces: two documented failure modes were described but never checked, the
checks only ran when the agent chose to run them, and nothing pinned the helpers'
output against drift.

### Added

- **A PostToolUse hook that runs the structural checks whether or not the agent
  chose to.** After any Bash command, `.hwpx` files named in it that were just
  modified are put through `verify.py`; a failure is reported back so it gets
  fixed at the moment it is introduced rather than after delivery. It costs no
  model context — the harness runs it — and stays silent when everything passes.
  Registered via `hooks/hooks.json` for plugin installs.
- **A golden-file corpus** (`corpus/`) that pins what the editing helpers actually
  produce. `selftest.py` proves the primitives behave; this proves the output hasn't
  drifted. Five cases cover row deletion, column widening, cell edits, two endnotes at
  one anchor, and section extraction. The source document is *generated in code*, so no
  real document is ever committed, and comparison is structural rather than byte-exact —
  a re-deflated entry varies with the zlib version, and CI runs on a different platform
  than development. Wired into CI; `--update` regenerates the goldens for review.
- `tbl@rowCnt` and `header.xml` `secCnt` are now **gated**, not just maintained.
  Both are documented failure modes (흔한 실패 20·21) that leave the XML
  well-formed with unique ids, so nothing else caught them. Exposed as
  `hwpxlib.rowcnt_mismatches()` / `seccnt_mismatch()` and checked by `selftest.py`.

### Fixed

- `table_width_ok()` raised `AttributeError` on a table missing `sz`/`cellSz`/
  `cellSpan`/`cellAddr`, which aborted the whole `verify.py` run instead of
  reporting. It now returns "no verdict" (`total is None`) and the check reports
  how many tables were unmeasurable. A verifier that throws on one odd table is
  worse than one that says it could not tell.
- Both new gates treat an **absent** attribute as stating nothing rather than as
  a failure, and the `secCnt` lookup no longer assumes the `hh:` prefix — a head
  element carrying a default namespace was previously invisible to it.

### Changed

- `CHANGELOG` 0.1.0 below: corrected an inaccurate claim (see that entry).

## [0.1.0] — 2026-07-30

First tagged release. The skill has been public since 2026-07-06; this collects what
is in it as of today so a version can be pinned.

### Rules and skill

- `references/hwpx-guide.md` — the field guide, §1 parsing through §7 verification.
- `SKILL.md` with trigger coverage for `.hwpx`, legacy `.hwp`, 한글 / 한컴 documents,
  table→Excel export, "file is corrupted" reports, and captions.
- Legacy `.hwp` (OLE binary, `D0CF11E0`) is detected and reported, with the conversion
  step to take in 한글 — the scripts do not attempt to parse it.
- Paragraph-cloning traps documented and then moved into `hwpxlib` helpers: cloning the
  section's first paragraph as a template, and cloning a multi-run paragraph (which
  flattens its formatting).

### Editing and repack

- `repack_preserve` — raw-preserving repack. Re-packing without changing anything
  reproduces the original byte for byte; `selftest.py` proves this on a synthetic file.
- `.tail`-safe text edits, plus memo and track-change helpers.
- Table helpers that keep row/column geometry consistent.
- `replace_image()` updates `imgDim`, so a swapped image is not cropped by 한글.
- Caption create / position / align.
- `extract_section()` handles `secCnt`, `content.hpf`, `container.rdf` and BinData
  together when splitting a section out.

### Reading and conversion

- `tables_to_xlsx.py` — every table to Excel with merged cells preserved.
- `hwpx_to_markdown.py` — body text and tables as Markdown, for LLM reading.
- `hwpx_to_docx.py` — Word export; Hancom private-use glyphs stripped.
- `data_to_hwpx_table.py` — Excel/CSV into an HWPX table, merges preserved.

### Verification and audit

- `verify.py` — runs the §7 build checklist and can gate CI. Covers IDRef/`itemCnt`
  integrity across `charPr`/`paraPr`/`borderFill`/`style`, and flags only
  newly-introduced duplicate ids (한글 legitimately reuses ids on empty paragraphs).
- A hard check for an endnote nested inside another endnote — a file that stays
  well-formed with unique ids and still errors when 한글 opens it.
  *(Corrected after release: this entry also listed `tbl@rowCnt` and `secCnt` as hard
  checks. They were not. `hwpxlib` keeps both correct when you go through its helpers —
  `extract_section()` rewrites `secCnt`, the table helpers rewrite `rowCnt` — but
  nothing verified a document where they were already wrong. Gated in Unreleased above.)*
- `audit_layout.py` — render-based audit: cell content that wrapped, near-empty and
  blank pages, table-of-contents page numbers that disagree with the caption's real
  page, and cell width sums. Checks 1–4 read the PDF only, so any rendered PDF works,
  not just HWPX.
- `audit_typography.py` — font consistency compared by name rather than `fontface`
  index (the arrays differ per language), and `JUSTIFY` + `breakLatinWord="KEEP_WORD"`
  letter-spacing blowout near Latin text.
- `remerge_check.py` — inserts an extracted chapter into the master in 한글, renders,
  and reads the caption and endnote numbering back, instead of inferring it from XML.
- `selftest.py` — verifies repack losslessness with no real document needed.

### Distribution

- `.claude-plugin/marketplace.json` — installable with `/plugin marketplace add`.
- `install.sh` / `install.ps1` for Claude Code and Desktop, Codex, Cursor, Gemini CLI
  and OpenClaw.
- CI runs `selftest.py` on push and pull request.

### Fixed

- UTF-8 console output on Windows (cp949 code pages).
- `own()` footnote filter and a data-descriptor guard in the zip reader.

[0.1.1]: https://github.com/kangdacool/hwpx-editing-skill/releases/tag/v0.1.1
[0.1.0]: https://github.com/kangdacool/hwpx-editing-skill/releases/tag/v0.1.0
