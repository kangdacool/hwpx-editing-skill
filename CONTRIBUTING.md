# Contributing

Thanks for helping make HWPX editing safer for everyone. / HWPX 편집을 더 안전하게 만드는 데 함께해 주셔서 감사합니다.

## What's most valuable

- **Real-world edge cases**, with a minimal `.hwpx` that reproduces the problem (strip
  it of anything sensitive first).
- **Fixes verified in 한글** — since LibreOffice can't render HWPX, a fix is only "done"
  once you've opened the result in 한글 and confirmed it. Please say so in the PR.
- New primitives for `scripts/hwpxlib.py` that follow the guide's invariants
  (raw-preserving repack, linesegarray removal, id-dedup, itemCnt discipline).
- Guide corrections in `skills/hwpx-editing/references/hwpx-guide.md`.

## Ground rules

- **Every claim must be verified**, at the byte level or in 한글. Don't add rules you
  haven't confirmed; this guide's whole value is that it only contains verified things.
- Keep `SKILL.md` tight (the operational layer). Deep detail goes in `references/`.
- Run `python skills/hwpx-editing/scripts/selftest.py` before opening a PR — it must
  print `RESULT: ALL PASS`. If you touched the repacker or verifier, add a case.
- No secrets, tokens, or personal data in commits, issues, or sample files.

## Dev setup

```bash
git clone https://github.com/<your-username>/hwpx-editing-skill.git
cd hwpx-editing-skill
pip install lxml
python skills/hwpx-editing/scripts/selftest.py
```

## PR checklist

- [ ] `selftest.py` passes.
- [ ] If behavior changed, the guide and `SKILL.md` were updated to match.
- [ ] Verified in 한글 (describe how) if it affects output files.
- [ ] No sensitive content in sample files.
