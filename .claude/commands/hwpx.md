---
name: hwpx
description: Safely inspect or edit an HWPX (한글 .hwpx) file using the hwpx-editing skill.
---

Work on the HWPX task described in: $ARGUMENTS

Follow the `hwpx-editing` skill strictly:

1. Read `skills/hwpx-editing/SKILL.md` (or the installed copy) and the relevant section
   of `references/hwpx-guide.md` for this operation before editing anything.
2. Always start by inspecting the file:
   `python <skill>/scripts/inspect_hwpx.py <file>.hwpx --breaks`
   If layout is the problem, check hidden `pageBreak`/`columnBreak` first (§6-A).
3. Edit the XML with lxml. Remove `linesegarray` after edits; reassign ids on any clone;
   reuse existing charPr/paraPr.
4. Repack **only** with `hwpxlib.repack_preserve` (never a normal zip writer).
5. Verify: `python <skill>/scripts/verify.py <edited>.hwpx --orig <original>.hwpx` — all
   hard checks must pass, and the minimal-change diff should show only intended changes.
6. Work on a copy, keep the original, and remind the user to round-trip the result in 한글
   (LibreOffice can't render HWPX).
