#!/usr/bin/env python3
"""
crossref_check.py — 상호참조(CROSSREF) 필드의 무결성을 검사한다.

    python crossref_check.py FILE.hwpx
    python crossref_check.py FILE.hwpx --baseline BEFORE.hwpx
    python crossref_check.py FILE.hwpx --fix-cache OUT.hwpx

무엇을 보는가
    한글의 「상호참조」는 재인용을 «미주 번호를 따라가는 필드»로 만든다. 구조는

        <hp:run>
          <hp:ctrl><hp:fieldBegin type="CROSSREF" id=…>
              <hp:parameters>… RefPath=?#<instId>; RefType=TARGET_ENDNOTE
                               RefContentType=OBJECT_TYPE_NUMBER …
          </hp:fieldBegin></hp:ctrl>
          <hp:t>3</hp:t>                       ← 캐시된 «표시 번호»
          <hp:ctrl><hp:fieldEnd beginIDRef=…/></hp:ctrl>
          <hp:t>)</hp:t>                       ← 리터럴 괄호
        </hp:run>

    한글은 파일을 열 때 이 번호를 다시 계산한다(실측: 미주를 앞에 끼우면
    본문 재인용이 1)2) → 2)3)으로 정확히 밀린다). 그래서 «깨지는» 경우는 셋뿐이다.

      1. 필드가 통째로 사라진다 — 문단 텍스트를 통째 치환하면 ctrl 쌍이 날아간다.
         이것이 "클로드로 본문을 고치면 상호참조가 깨진다"의 정체다.
      2. 인용번호가 애초에 «리터럴 텍스트»다 — 재번호돼도 그 자리만 안 따라간다.
         XML도 verify도 통과하고, 번호가 밀리는 순간에만 틀린 값이 찍힌다.
      3. RefContentType이 OBJECT_TYPE_NUMBER가 아니다(예: _PAGE) — 대상 미주의
         번호를 «따라가지 않는다». 실측: 앞에 미주를 하나 끼우자 1)2) → 2)«2»)로
         한쪽만 밀리고 다른 쪽은 멈춰 있었다.

    2·3은 지금 파일에서는 우연히 맞아 보인다. 번호가 움직이는 순간 틀린다.
    그래서 편집 «전»에 한 번, «후»에 한 번 돌린다.

검사 항목
    [E] fieldBegin ↔ fieldEnd 페어링 (beginIDRef·fieldid)
    [E] RefPath가 실존 대상(instId)을 가리키는가 — 고아 참조
    [E] 캐시된 표시 번호 == 대상 미주의 섹션 내 서수
    [E] RefType=TARGET_ENDNOTE인데 RefContentType이 NUMBER가 아님
    [W] 본문에 남은 리터럴 인용번호 후보 (`…한다.12)` 꼴)
    [W] 한 번도 인용되지 않은 미주
    --baseline : 두 파일의 «미주 서지 ↔ 인용 앵커 수» 대응표를 기계 대조
    --fix-cache: 캐시 번호를 대상 서수로 다시 써넣는다(한글을 거치지 않는 경로용)

종료코드 0 = [E] 없음.
"""
import argparse
import os
import re
import sys
import zipfile

from lxml import etree

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

P = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
XML_DECL = b'<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>\n'

# 「…한다.12)」처럼 문장 끝에 붙은 리터럴 인용번호.
#   · 문단 첫머리의 「1) 질병의 정의와 원인」 → 앞에 마침표가 없어 안 걸린다.
#   · 표 셀의 「459 (49.9)」 → 여는 괄호가 있어 안 걸린다.
#   · 신뢰구간 「1.20–1.38)」 → 마침표 앞이 숫자라 (?<![0-9]) 로 배제한다.
LITERAL_CITE = re.compile(r"(?<![0-9])[.。．]\s*(\d{1,2})\)")


# ---------------------------------------------------------------------------
# 읽기
# ---------------------------------------------------------------------------
def section_names(z):
    return sorted(n for n in z.namelist()
                  if re.fullmatch(r"Contents/section\d+\.xml", n))


def deep_text(el):
    out = []
    for node in el.iter(f"{P}t"):
        out.append(node.text or "")
        for c in node:
            if c.tail:
                out.append(c.tail)
    return "".join(out)


def is_body(p):
    """본문 문단인가 — 주석/메모 subList 안이면 아니다."""
    return not any(a.tag in (f"{P}endNote", f"{P}footNote", f"{P}subList")
                   for a in p.iterancestors())


def field_params(fb):
    out = {}
    for tag in ("stringParam", "integerParam", "booleanParam"):
        for el in fb.findall(f".//{P}{tag}"):
            out[el.get("name")] = el.text or ""
    return out


def notes_in_order(root):
    """섹션 내 미주/각주를 문서 순서로. [(ordinal, instId, 서지텍스트)]"""
    out = []
    for i, n in enumerate(root.iter(f"{P}endNote", f"{P}footNote"), 1):
        out.append((i, n.get("instId"), " ".join(deep_text(n).split())))
    return out


def para_stream(p):
    """문단의 run 자식들을 «순서대로» 평탄화한다.

    ⚠️ 필드는 run 경계를 넘는다 — fieldBegin이 한 run의 끝에 있고 캐시된 <hp:t>와
    fieldEnd가 «다음 run»에 있는 배치가 실제로 흔하다(한글이 글자서식이 바뀌는
    지점에서 run을 쪼갠다). run 안에서만 찾으면 캐시가 비어 보인다.
    """
    for run in p.findall(f"{P}run"):
        for node in run:
            yield node


def crossrefs(root):
    """[(fieldBegin, para, cached_text, cached_nodes, params)] — CROSSREF만."""
    out = []
    for p in root.iter(f"{P}p"):
        nodes = list(para_stream(p))
        for idx, node in enumerate(nodes):
            if node.tag != f"{P}ctrl":
                continue
            fb = node.find(f"{P}fieldBegin")
            if fb is None or fb.get("type") != "CROSSREF":
                continue
            fid = fb.get("id")
            cached_nodes = []
            for nxt in nodes[idx + 1:]:
                if nxt.tag == f"{P}ctrl":
                    fe = nxt.find(f"{P}fieldEnd")
                    if fe is not None and fe.get("beginIDRef") == fid:
                        break
                elif nxt.tag == f"{P}t":
                    cached_nodes.append(nxt)
            cached = "".join(t.text or "" for t in cached_nodes)
            out.append((fb, p, cached, cached_nodes, field_params(fb)))
    return out


# ---------------------------------------------------------------------------
# 검사
# ---------------------------------------------------------------------------
def check_section(name, root, errors, warns, info):
    notes = notes_in_order(root)
    ordinal = {inst: i for i, inst, _ in notes}
    # instId를 가진 모든 요소 — 미주가 아닌 대상(책갈피·표 등)도 고아 판정에서 제외
    all_inst = {el.get("instId") for el in root.iter() if el.get("instId")}

    # --- 페어링 ---
    begins, ends = {}, {}
    for fb in root.iter(f"{P}fieldBegin"):
        begins[fb.get("id")] = fb
    for fe in root.iter(f"{P}fieldEnd"):
        ends.setdefault(fe.get("beginIDRef"), []).append(fe)
    for fid, fb in begins.items():
        if fid not in ends:
            errors.append(f"{name}: fieldBegin id={fid} type={fb.get('type')} — "
                          f"짝이 되는 fieldEnd 없음")
        else:
            for fe in ends[fid]:
                if fe.get("fieldid") != fb.get("fieldid"):
                    errors.append(f"{name}: fieldBegin id={fid} 의 fieldid "
                                  f"{fb.get('fieldid')} != fieldEnd {fe.get('fieldid')}")
    for bid in ends:
        if bid not in begins:
            errors.append(f"{name}: fieldEnd beginIDRef={bid} — 대응하는 fieldBegin 없음")

    # --- CROSSREF 본체 ---
    refcount = {}
    for fb, run, cached, cnodes, prm in crossrefs(root):
        tgt = (prm.get("RefPath") or "").strip("?#;")
        rtype = prm.get("RefType", "")
        ctype = prm.get("RefContentType", "")
        where = f"{name}: CROSSREF id={fb.get('id')} -> {tgt}"

        if tgt not in all_inst:
            errors.append(f"{where} — 고아 참조(대상 instId가 문서에 없음)")
            continue
        refcount[tgt] = refcount.get(tgt, 0) + 1

        if rtype in ("TARGET_ENDNOTE", "TARGET_FOOTNOTE"):
            if ctype != "OBJECT_TYPE_NUMBER":
                errors.append(f"{where} — RefContentType={ctype} "
                              f"(미주 번호를 따라가지 않는다; OBJECT_TYPE_NUMBER 여야 함)")
            cmd = prm.get("Command", "")
            parts = cmd.strip("?#;").split(";")
            if len(parts) >= 3 and parts[2] not in ("1",):
                errors.append(f"{where} — Command={cmd} (3번째 값이 1이 아니다 = 번호 아님)")
            want = ordinal.get(tgt)
            if want is not None and cached.strip() != str(want):
                errors.append(f"{where} — 캐시 표시번호 {cached.strip()!r} != 대상 서수 {want}")
        else:
            info.append(f"{where} — RefType={ctype and rtype or rtype} (미주 참조 아님, 검사 제외)")

    # --- 리터럴 인용번호 후보 ---
    # CROSSREF 필드 «안»의 캐시 숫자는 정상이므로 제외한다. 메모(MEMO) 필드는 본문
    # 텍스트에 걸쳐 있으므로 제외하면 안 된다 — 필드 종류로 갈라야 한다.
    for p in root.iter(f"{P}p"):
        if not is_body(p):
            continue
        parts, skip_until = [], None
        for node in para_stream(p):
            if node.tag == f"{P}ctrl":
                fb = node.find(f"{P}fieldBegin")
                fe = node.find(f"{P}fieldEnd")
                if fb is not None and fb.get("type") == "CROSSREF":
                    skip_until = fb.get("id")
                elif fe is not None and fe.get("beginIDRef") == skip_until:
                    skip_until = None
            elif node.tag == f"{P}t" and skip_until is None:
                parts.append((node.text or "") + "".join(c.tail or "" for c in node))
        plain = "".join(parts)
        hits = LITERAL_CITE.findall(plain)
        if hits:
            ctx = " ".join(plain.split())
            warns.append(f"{name}: 리터럴 인용번호 후보 {hits} — …{ctx[-70:]!r}")


def fingerprint(path):
    """{섹션: {서지텍스트: 재인용 수}} + 미주 순서 — baseline 대조용."""
    z = zipfile.ZipFile(path)
    out = {}
    for name in section_names(z):
        root = etree.fromstring(z.read(name))
        notes = notes_in_order(root)
        refcount = {}
        for fb, run, cached, cnodes, prm in crossrefs(root):
            tgt = (prm.get("RefPath") or "").strip("?#;")
            refcount[tgt] = refcount.get(tgt, 0) + 1
        out[name] = [(txt, refcount.get(inst, 0)) for _, inst, txt in notes]
    return out


def key_of(txt, n=60):
    """서지 앞부분 — 판본 차이에 견디도록 축약 키."""
    return re.sub(r"\s+", " ", txt).strip()[:n]


def do_baseline(cur_path, base_path):
    cur, base = fingerprint(cur_path), fingerprint(base_path)
    print("\n=== baseline 대조 (%s → %s) ===" % (os.path.basename(base_path),
                                                os.path.basename(cur_path)))
    for name in sorted(set(cur) | set(base)):
        c = {key_of(t): n for t, n in cur.get(name, [])}
        b = {key_of(t): n for t, n in base.get(name, [])}
        print(f"\n-- {name}: 미주 {len(b)} → {len(c)} · "
              f"재인용 {sum(b.values())} → {sum(c.values())}")
        for k in b:
            if k not in c:
                print(f"   [사라짐] {k}  (재인용 {b[k]})")
        for k in c:
            if k not in b:
                print(f"   [새로]   {k}  (재인용 {c[k]})")
        for k in c:
            if k in b and c[k] != b[k]:
                print(f"   [재인용 수 변화] {b[k]} → {c[k]}  {k}")


def do_fix_cache(src, out):
    z = zipfile.ZipFile(src)
    changed, fixed = {}, 0
    for name in section_names(z):
        root = etree.fromstring(z.read(name))
        ordinal = {inst: i for i, inst, _ in notes_in_order(root)}
        touched = False
        for fb, run, cached, cnodes, prm in crossrefs(root):
            tgt = (prm.get("RefPath") or "").strip("?#;")
            want = ordinal.get(tgt)
            if want is None or not cnodes:
                continue
            if cached.strip() == str(want):
                continue
            cnodes[0].text = str(want)
            for t in cnodes[1:]:
                t.text = ""
            touched, fixed = True, fixed + 1
        if touched:
            changed[name] = XML_DECL + etree.tostring(root, encoding="UTF-8")
    if not changed:
        print("[fix-cache] 고칠 것 없음.")
        return 0
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import hwpxlib as H
    H.repack_preserve(src, changed, out)
    print(f"[fix-cache] 캐시 {fixed}개 갱신 → {out}")
    return fixed


def main():
    ap = argparse.ArgumentParser(description="HWPX 상호참조 무결성 검사")
    ap.add_argument("file")
    ap.add_argument("--baseline", help="편집 전 파일과 미주·재인용 대응표를 대조")
    ap.add_argument("--fix-cache", metavar="OUT", help="캐시 표시번호를 재계산해 저장")
    ap.add_argument("--strict", action="store_true", help="경고도 실패로 취급")
    a = ap.parse_args()

    z = zipfile.ZipFile(a.file)
    errors, warns, info = [], [], []
    print("=== %s ===" % os.path.basename(a.file))
    for name in section_names(z):
        root = etree.fromstring(z.read(name))
        notes = notes_in_order(root)
        xr = crossrefs(root)
        print(f"{name}: 미주/각주 {len(notes)} · 상호참조 {len(xr)}")
        check_section(name, root, errors, warns, info)

    for label, items in (("ERROR", errors), ("WARN", warns), ("INFO", info)):
        if items:
            print(f"\n--- {label} ({len(items)}) ---")
            for s in items:
                print(f"  [{label[0]}] {s}")

    if a.baseline:
        do_baseline(a.file, a.baseline)
    if a.fix_cache:
        do_fix_cache(a.file, a.fix_cache)

    bad = bool(errors) or (a.strict and bool(warns))
    print("\nRESULT:", "FAIL" if bad else "OK",
          f"(E={len(errors)} W={len(warns)})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
