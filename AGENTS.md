# AGENTS.md

This repository is an **Agent Skill** for editing HWPX (한글 / Hangul `.hwpx`) files.
If you are an AI coding agent working in this repo — or the user pointed you here to
work on a `.hwpx` file — use the skill instead of guessing.

## When to use it

Any task touching a `.hwpx` file, a 한글/Hangul document, HWPML, or a Korean
government/academic document: reading/extracting text or tables, editing paragraphs,
tables, images, equations, footnotes/endnotes, memos; fixing layout (orphaned headings,
blank pages, columns); building a table of contents; repackaging the zip.

## How to use it

1. Read the skill: **`skills/hwpx-editing/SKILL.md`**. It contains the workflow and
   points to the detailed guide and scripts.
2. Read the relevant section of **`skills/hwpx-editing/references/hwpx-guide.md`** for
   the specific operation.
3. Use the scripts in **`skills/hwpx-editing/scripts/`** — do **not** hand-roll zip
   repacking:
   - `inspect_hwpx.py FILE.hwpx --breaks` — inspect structure and hidden page/column breaks
   - `hwpxlib.py` — `repack_preserve`, `own`, `make_uid`, `strip_linesegarray`, verify helpers
   - `verify.py EDITED.hwpx --orig ORIG.hwpx` — run the §7 build checklist
   - `selftest.py` — prove the repacker is lossless
4. Dependency: `pip install lxml` (Python 3.10+).

## The non-negotiable rule

Never re-zip an HWPX with a normal zip writer — 한글 will reject it. Use
`repack_preserve`, which byte-copies unchanged entries and re-deflates only what you
changed. Verify every build; then ask the user to round-trip the file in 한글, since
LibreOffice cannot render HWPX.

## Installing the skill elsewhere

To install this skill into an agent's global skills directory, run `./install.sh <agent>`
(or see `docs/INSTALL_LLM.md`). Do not handle the user's credentials; if publishing or
auth is needed, ask the user to do it.
