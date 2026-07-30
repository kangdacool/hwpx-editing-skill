# Changelog

이 파일은 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) 형식을 따르고,
버전은 [Semantic Versioning](https://semver.org/spec/v2.0.0.html)을 씁니다.

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
- Hard checks for the failures that pass every structural check and surface only when
  한글 opens the file: an endnote nested inside an endnote, `tbl@rowCnt` disagreeing
  with the actual row count, and a stale `secCnt` after a section is extracted.
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

[0.1.0]: https://github.com/kangdacool/hwpx-editing-skill/releases/tag/v0.1.0
