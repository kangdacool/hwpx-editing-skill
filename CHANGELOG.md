# Changelog

이 파일은 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) 형식을 따르고,
버전은 [Semantic Versioning](https://semver.org/spec/v2.0.0.html)을 씁니다.

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
