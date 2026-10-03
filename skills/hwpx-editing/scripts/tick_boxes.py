# -*- coding: utf-8 -*-
"""tick_boxes.py — HWPX 양식의 체크칸(□)을 ☑ 로 바꾼다. 문단을 «지정해서», 개수를 «세면서».

    python tick_boxes.py FORM.hwpx --list                       # 체크칸이 있는 문단을 번호와 함께 본다
    python tick_boxes.py FORM.hwpx OUT.hwpx --plan "7,9,12:1,14-27" --expect 20

--plan 문법:  `7`      그 문단의 □ 전부
              `12:1`   그 문단의 □ 가운데 «앞에서 1개»만 (예: 「□ 원저, □ 종설, □ 사례보고」에서 원저만)
              `14-27`  범위(각 문단의 □ 전부)
--expect N:   바뀐 개수가 N 이 아니면 «쓰지 않고» 죽는다. 생략하지 말 것 — 아래 함정 때문이다.

## 왜 있나 (2026-09-21 자체충족률논문, JAMCH 자가점검표)

일회용 스크립트로 `hp:t` 의 `.text` 만 바꿨더니 **20칸 중 7칸만** 체크됐다. 오류도 경고도 없었다.
한글은 탭 뒤의 글자를 `<hp:t>앞<hp:tab/>뒤</hp:t>` 로 저장하므로, 「뒤」는 `hp:t.text` 가 아니라
**탭 노드의 `.tail`** 에 있다. 양식 문서는 탭으로 줄을 맞추므로 체크칸의 절반이 거기 산다.
→ 이 도구는 `.text` 와 자식 노드들의 `.tail` 을 모두 훑고, **문단마다 남은 □ 개수를 기대값과 대조**한다.

⛔ 체크는 «사실 확인»이다. 칸마다 원고에서 확인한 뒤에 --plan 에 넣는다 — 전부 체크하는 도구가 아니다.
   판단이 들어간 칸(규정과 어긋나지만 연구자 결정으로 체크하는 칸)은 보고에 따로 적는다.

서명은 이 도구의 일이 아니다 → PDF 로 낸 뒤 `agent/tools/stamp_signature.py`.
"""
import argparse
import os
import sys
import zipfile

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hwpxlib                      # noqa: E402
from lxml import etree              # noqa: E402

NS = {"hp": "http://www.hancom.co.kr/hwpml/2011/paragraph"}
BOX, TICK = "□", "☑"


def parse_plan(s):
    """'7,9,12:1,14-27' -> {7: None, 9: None, 12: 1, 14: None, ...}"""
    plan = {}
    for part in [x.strip() for x in s.split(",") if x.strip()]:
        if ":" in part:
            a, b = part.split(":")
            plan[int(a)] = int(b)
        elif "-" in part:
            a, b = part.split("-")
            for i in range(int(a), int(b) + 1):
                plan[i] = None
        else:
            plan[int(part)] = None
    return plan


def slots(p):
    """문단 안에서 글자가 사는 자리를 전부: (node, 'text'|'tail')."""
    out = []
    for t in p.findall(".//hp:t", NS):
        out.append((t, "text"))
        out += [(c, "tail") for c in t.iter() if c is not t]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--plan")
    ap.add_argument("--expect", type=int)
    ap.add_argument("--section", default="Contents/section0.xml")
    a = ap.parse_args()

    root = etree.fromstring(zipfile.ZipFile(a.src).read(a.section))
    paras = root.findall(".//hp:p", NS)

    if a.list:
        for i, p in enumerate(paras):
            s = "".join(p.itertext())
            if BOX in s or TICK in s:
                print(f"{i:3}  □×{s.count(BOX)} ☑×{s.count(TICK)}  {s.strip()[:80]}")
        return
    if not (a.out and a.plan):
        ap.error("OUT 과 --plan 이 필요하다(또는 --list)")
    if a.expect is None:
        ap.error("--expect 를 생략하지 말 것 — 조용히 덜 바뀌는 것이 이 도구가 막으려는 사고다")

    done = 0
    for idx, limit in parse_plan(a.plan).items():
        p = paras[idx]
        before = "".join(p.itertext()).count(BOX)
        left = before if limit is None else limit
        if left > before:
            raise SystemExit(f"⛔ 문단 {idx}: □ 가 {before}개뿐인데 {limit}개를 바꾸라고 했다")
        for node, attr in slots(p):
            s = getattr(node, attr)
            if not s or BOX not in s or left <= 0:
                continue
            take = min(s.count(BOX), left)
            setattr(node, attr, s.replace(BOX, TICK, take))
            left -= take
            done += take
        after = "".join(p.itertext()).count(BOX)
        want = 0 if limit is None else before - limit
        if after != want:
            raise SystemExit(f"⛔ 문단 {idx}: □ 가 {after}개 남았다(기대 {want}) — 쓰지 않는다")

    if done != a.expect:
        raise SystemExit(f"⛔ {done}칸이 바뀌었다 — --expect {a.expect} 와 다르다. 쓰지 않는다")

    hwpxlib.strip_linesegarray(root)
    decl = hwpxlib.XML_DECL
    data = (decl if isinstance(decl, str) else decl.decode()) + etree.tostring(root, encoding="unicode")
    hwpxlib.repack_preserve(a.src, {a.section: data.encode("utf-8")}, a.out)
    print(f"체크 {done}칸 → {a.out}")
    print("다음: python verify.py OUT --orig SRC  ·  그리고 렌더해서 ☑ 글립이 깨지지 않았는지 «본다»")


if __name__ == "__main__":
    main()
