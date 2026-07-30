#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PostToolUse 훅 — 방금 만든 .hwpx가 깨졌으면 그 자리에서 알린다.

    등록: hooks/hooks.json (플러그인) 또는 settings.json 의 PostToolUse

에이전트는 §7 검증을 «돌리기로 선택해야» 돌린다. 안 돌리면 깨진 파일이 그대로
사용자에게 간다. 이 훅은 그 선택을 없앤다 — Bash 명령이 끝날 때마다 그 명령에
등장한 `.hwpx` 중 **방금 수정된 것**만 골라 `verify.py`의 구조 하드체크를 돌리고,
실패하면 stderr로 사유를 내보낸다. PostToolUse의 exit 2는 도구를 막지는 못하지만
(이미 실행됐다) 그 사유가 Claude에게 전달되므로, Claude가 스스로 고친다.

조용한 것이 기본이다. 통과하면 아무것도 출력하지 않는다.

무엇을 검사하지 않는가
    · 오래된 파일 — mtime이 FRESH_SECONDS 밖이면 이번 명령이 만든 게 아니다.
      읽기만 하는 `inspect_hwpx.py`는 mtime을 안 바꾸므로 자동으로 걸러진다.
    · `verify.py` 자신을 부르는 명령 — 무한 반복 방지.
    · 렌더 감사(`audit_layout.py`) — 한글 COM이 필요해 훅에서 돌리기엔 느리고,
      Windows+한컴이 없는 기기에서는 아예 못 돈다. 구조 검사만 한다.
"""
import json
import os
import re
import subprocess
import sys

# 이 훅은 한국어 사유를 stderr로 낸다. Windows cp949 콘솔에서 그대로 쓰면
# UnicodeEncodeError로 훅이 죽고, 죽은 훅은 «조용히 통과»와 구별되지 않는다.
# verify.py와 같은 가드를 둔다.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

FRESH_SECONDS = 180        # 이 명령이 만졌다고 볼 시간 창
MAX_FILES = 4              # 한 번에 검사할 파일 수 상한 (훅 지연 방지)
PER_FILE_TIMEOUT = 45

HERE = os.path.dirname(os.path.abspath(__file__))
VERIFY = os.path.join(HERE, "verify.py")

# 따옴표로 감싼 경로를 먼저 — 공백 있는 경로가 잘리지 않게.
QUOTED = [re.compile(r'"([^"]+?\.hwpx)"'), re.compile(r"'([^']+?\.hwpx)'")]
BARE = re.compile(r'(?:^|[\s=])((?:[A-Za-z]:)?[^\s"\';|&><]+\.hwpx)')


def candidates(command: str) -> list[str]:
    found, seen = [], set()
    for rx in QUOTED:
        for m in rx.finditer(command):
            if m.group(1) not in seen:
                seen.add(m.group(1)); found.append(m.group(1))
    stripped = command
    for rx in QUOTED:
        stripped = rx.sub(" ", stripped)
    for m in BARE.finditer(stripped):
        if m.group(1) not in seen:
            seen.add(m.group(1)); found.append(m.group(1))
    return found


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0                                   # 훅 입력이 이상하면 조용히 통과

    if event.get("tool_name") != "Bash":
        return 0
    command = (event.get("tool_input") or {}).get("command") or ""
    if not command or "verify.py" in command or "hwpx_guard" in command:
        return 0

    cwd = event.get("cwd") or os.getcwd()
    import time
    now = time.time()

    targets = []
    for raw in candidates(command):
        path = raw if os.path.isabs(raw) else os.path.join(cwd, raw)
        try:
            if not os.path.isfile(path):
                continue
            if now - os.path.getmtime(path) > FRESH_SECONDS:
                continue                            # 이번 명령이 만든 게 아니다
        except OSError:
            continue
        targets.append(path)
        if len(targets) >= MAX_FILES:
            break

    if not targets or not os.path.exists(VERIFY):
        return 0

    problems = []
    for path in targets:
        try:
            r = subprocess.run([sys.executable, VERIFY, path],
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace",
                               timeout=PER_FILE_TIMEOUT)
        except (subprocess.TimeoutExpired, OSError):
            continue                                # 검사기가 못 돌면 통과시킨다
        if r.returncode != 1:
            continue        # 0 = 통과, 2 = HWPX가 아님(중간 산출물일 수 있다)
        fails = [ln for ln in (r.stdout or "").splitlines() if ln.startswith("[FAIL]")]
        problems.append((path, fails))

    if not problems:
        return 0

    print("hwpx-editing: 방금 쓴 파일이 §7 구조 검사를 통과하지 못했습니다. "
          "이 상태로 전달하면 한글에서 열리지 않거나 잘못 조판됩니다.", file=sys.stderr)
    for path, fails in problems:
        print(f"\n  {path}", file=sys.stderr)
        for ln in fails[:6]:
            print(f"    {ln}", file=sys.stderr)
    print("\n  전체 출력: python skills/hwpx-editing/scripts/verify.py <파일> "
          "--orig <원본>", file=sys.stderr)
    return 2                                        # stderr가 Claude에게 전달된다


if __name__ == "__main__":
    sys.exit(main())
