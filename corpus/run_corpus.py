#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""골든 파일 회귀 — 헬퍼가 문서를 «전과 똑같은 방식으로» 고치는지 본다.

    python corpus/run_corpus.py            # 검사 (CI 게이트, 실패 시 exit 1)
    python corpus/run_corpus.py --update   # 골든 재생성 (diff를 눈으로 보고 커밋)

`selftest.py`가 «원시동작이 맞는가»를 본다면 이쪽은 «출력이 달라지지 않았는가»를 본다.
헬퍼를 고쳤을 때 의도한 케이스만 골든이 바뀌어야 하고, 엉뚱한 케이스가 같이 바뀌면
그게 회귀다.

바이트가 아니라 **구조**를 비교한다. 바뀐 엔트리는 다시 deflate되는데 deflate 출력은
zlib 버전에 따라 달라진다 — 개발은 Windows, CI는 ubuntu다. 그래서 골든에 담는 것은:
  · 어떤 엔트리가 바뀌었고/추가됐고/빠졌는가
  · 안 바뀐 엔트리가 바이트째 동일한가 (이건 결정적이라 그대로 비교한다)
  · verify.py 하드체크 결과
  · 구조 카운트와 §7 최소변경 diff (사람이 읽고 검토할 수 있는 형태)
"""
import argparse
import difflib
import os
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "skills", "hwpx-editing", "scripts")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

import hwpxlib as H          # noqa: E402
import cases as CASES_MOD    # noqa: E402
import fixture               # noqa: E402

GOLDEN_DIR = os.path.join(HERE, "golden")
VERIFY = os.path.join(SCRIPTS, "verify.py")


def _entries(path):
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist()}


def _verify(path):
    r = subprocess.run([sys.executable, VERIFY, path], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    fails = [l.strip() for l in (r.stdout or "").splitlines() if l.startswith("[FAIL]")]
    return r.returncode, fails


def describe(src, out) -> str:
    """골든에 담길 텍스트를 만든다 — 전부 결정적인 값이어야 한다."""
    a, b = _entries(src), _entries(out)
    added = sorted(set(b) - set(a))
    dropped = sorted(set(a) - set(b))
    common = sorted(set(a) & set(b))
    changed = [n for n in common if a[n] != b[n]]
    same = [n for n in common if a[n] == b[n]]

    lines = []
    lines.append(f"entries changed:   {', '.join(changed) or '(none)'}")
    lines.append(f"entries added:     {', '.join(added) or '(none)'}")
    lines.append(f"entries dropped:   {', '.join(dropped) or '(none)'}")
    lines.append(f"byte-identical:    {', '.join(same) or '(none)'}")

    code, fails = _verify(out)
    lines.append(f"verify hard checks: {'PASS' if code == 0 else 'FAIL'}")
    for f in fails:
        lines.append(f"  {f}")

    with zipfile.ZipFile(out) as z:
        mismatch = H.seccnt_mismatch(z)
        lines.append(f"seccnt:            {'ok' if mismatch is None else mismatch}")
        for name in H.section_names(z):
            root = H.etree.fromstring(z.read(name))
            c = H.structural_counts(root)
            lines.append(
                f"structure {name}: p={c['p']} tbl={c['tbl']} pic={c['pic']} "
                f"eq={c['equation']} lineseg={c['linesegarray']}")
            rc = H.rowcnt_mismatches(root)
            lines.append(f"  rowcnt mismatches: {rc or 'none'}")
            lines.append(f"  nested 주석:        {len(H.nested_notes(root))}")

    for name in changed:
        if not name.endswith((".xml", ".hpf", ".rdf")):
            continue
        lines.append(f"--- minimal diff: {name}")
        for d in H.minimal_diff(a[name], b[name]):
            lines.append(f"  {d}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="rewrite the golden files")
    ap.add_argument("--only", help="run one case by name")
    args = ap.parse_args()

    os.makedirs(GOLDEN_DIR, exist_ok=True)
    tmp = tempfile.mkdtemp()
    src = fixture.build(os.path.join(tmp, "source.hwpx"))

    code, fails = _verify(src)
    if code != 0:
        print("the corpus source itself does not pass verify — fix the fixture first")
        for f in fails:
            print(f"  {f}")
        return 1

    failures = 0
    for name, fn in CASES_MOD.CASES:
        if args.only and args.only != name:
            continue
        out = os.path.join(tmp, f"{name}.hwpx")
        try:
            fn(src, out)
        except Exception as e:                       # noqa: BLE001 — report, don't abort
            print(f"[ERROR] {name}: {type(e).__name__}: {e}")
            failures += 1
            continue

        actual = describe(src, out)
        path = os.path.join(GOLDEN_DIR, f"{name}.txt")

        if args.update:
            existed = os.path.exists(path)
            prior = open(path, encoding="utf-8").read() if existed else ""
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(actual)
            state = "unchanged" if prior == actual else ("updated" if existed else "new")
            print(f"[{state:>9}] {name}")
            continue

        if not os.path.exists(path):
            print(f"[  MISSING] {name} — run with --update to create the golden")
            failures += 1
            continue
        expected = open(path, encoding="utf-8").read()
        if expected == actual:
            print(f"[     PASS] {name}")
        else:
            failures += 1
            print(f"[     FAIL] {name} — output differs from the golden:")
            for d in difflib.unified_diff(expected.splitlines(), actual.splitlines(),
                                          "golden", "actual", lineterm="", n=1):
                print(f"    {d}")

    print()
    if args.update:
        print("goldens written — read the diff before committing.")
        return 0
    print("RESULT:", "ALL PASS" if not failures else f"{failures} FAILED")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
