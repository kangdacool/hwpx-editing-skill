#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""서식 일관성 감사 — 실제로 쓰이는 charPr을 글꼴·크기별로 집계한다.

    python audit_typography.py FILE.hwpx [--expect-face 휴먼명조] [--expect-body-pt 10]

왜 필요한가
  구조 검사(verify.py)는 문서가 열리는지만 본다. "본문 글꼴이 통일되어 있는가",
  "영문 구간에서 글꼴이 튀지 않는가"는 잡지 못한다. 그런데 이 둘은 한글 문서에서
  가장 흔한 육안 결함이고, 대개 **소수의 charPr에만** 몰려 있어 집계하면 즉시 드러난다.

두 가지 함정을 특히 본다.

  ① fontface 배열은 lang마다 순서가 다르다.
     `<hh:fontRef hangul="6" latin="6"/>`이 같은 글꼴을 가리킨다는 보장이 없다.
     HANGUL 리스트의 6번과 LATIN 리스트의 6번은 서로 다른 글꼴일 수 있다.
     → 인덱스가 아니라 **이름으로** 비교해야 한다. 이 스크립트는 이름으로 본다.

  ② `align=JUSTIFY` + `breakLatinWord="KEEP_WORD"` = 영문 근처 자간이 벌어진다.
     긴 영문 토큰을 줄 끝에서 쪼갤 수 없으니 양쪽정렬이 단어 사이 공백을 늘린다.
     한글 본문에 영문 용어·서지가 섞이면 눈에 띄게 들쭉날쭉해진다.
     → 영문 비율이 높은 문단(참고문헌 등)은 LEFT로 두는 것이 낫다.

종료 코드: 기대값(--expect-*)을 준 경우 어긋나면 1, 아니면 0.
"""
import argparse
import re
import sys
import zipfile
from collections import Counter

from lxml import etree

H = '{http://www.hancom.co.kr/hwpml/2011/head}'
P = '{http://www.hancom.co.kr/hwpml/2011/paragraph}'
LANG_ATTR = {'HANGUL': 'hangul', 'LATIN': 'latin', 'HANJA': 'hanja',
             'JAPANESE': 'japanese', 'OTHER': 'other', 'SYMBOL': 'symbol', 'USER': 'user'}


def _sections(z):
    return sorted(n for n in z.namelist() if re.match(r'Contents/section\d+\.xml$', n))


def load(path):
    z = zipfile.ZipFile(path)
    hd = etree.fromstring(z.read('Contents/header.xml'))
    faces = {ff.get('lang'): [f.get('face') for f in ff.iter(H + 'font')]
             for ff in hd.iter(H + 'fontface')}
    charpr, parapr = {}, {}
    for cp in hd.iter(H + 'charPr'):
        fr = cp.find(H + 'fontRef')
        sp = cp.find(H + 'spacing')
        rt = cp.find(H + 'ratio')
        names = {}
        for lang, attr in LANG_ATTR.items():
            idx = fr.get(attr) if fr is not None else None
            lst = faces.get(lang) or []
            names[lang] = lst[int(idx)] if idx is not None and int(idx) < len(lst) else None
        charpr[cp.get('id')] = dict(
            pt=int(cp.get('height', 0)) / 100, face=names,
            bold=cp.find(H + 'bold') is not None, italic=cp.find(H + 'italic') is not None,
            sp=sp.get('hangul') if sp is not None else '0',
            ratio=rt.get('hangul') if rt is not None else '100')
    for pp in hd.iter(H + 'paraPr'):
        al = pp.find(H + 'align')
        bs = pp.find(H + 'breakSetting')
        parapr[pp.get('id')] = dict(
            align=al.get('horizontal') if al is not None else None,
            latin=bs.get('breakLatinWord') if bs is not None else None)
    return z, charpr, parapr


def scan(z, charpr):
    """run 단위로 charPr 사용을 세고, 문단 단위로 paraPr×영문비율을 잰다."""
    cuse, puse = Counter(), Counter()
    latin_runs = Counter()
    para_latin = {}
    for name in _sections(z):
        sec = etree.fromstring(z.read(name))
        for p in sec.iter(P + 'p'):
            pid = p.get('paraPrIDRef')
            puse[pid] += 1
            txt = ''.join(''.join(t.itertext()) for t in p.findall('.//' + P + 't'))
            if txt.strip():
                ratio = len(re.findall(r'[A-Za-z]', txt)) / max(1, len(txt))
                a, b = para_latin.get(pid, (0.0, 0))
                para_latin[pid] = (a + ratio, b + 1)
            in_tbl = any(a.tag == P + 'tc' for a in p.iterancestors())
            for r in p.iter(P + 'run'):
                cid = r.get('charPrIDRef')
                cuse[(cid, in_tbl)] += 1
                rt = ''.join(''.join(t.itertext()) for t in r.findall(P + 't'))
                if re.search(r'[A-Za-z]', rt):
                    latin_runs[cid] += 1
    return cuse, puse, latin_runs, para_latin


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('file')
    ap.add_argument('--expect-face', help='본문에 기대하는 글꼴 이름 (예: 휴먼명조)')
    ap.add_argument('--expect-body-pt', type=float, help='본문에 기대하는 크기 (예: 10)')
    a = ap.parse_args()

    z, charpr, parapr = load(a.file)
    cuse, puse, latin_runs, para_latin = scan(z, charpr)

    per_cid = Counter()
    for (cid, _), n in cuse.items():
        per_cid[cid] += n

    print(f'== charPr 사용 현황 ({a.file}) ==')
    print(f'{"charPr":>7} {"사용":>6} {"표내":>6} {"pt":>6}  한글 / 영문')
    faces_seen = Counter()
    for cid, n in per_cid.most_common():
        d = charpr.get(cid)
        if d is None:
            print(f'{cid:>7} {n:>6}  ← 정의 없음(깨진 참조)')
            continue
        intbl = cuse.get((cid, True), 0)
        fh, fl = d['face']['HANGUL'], d['face']['LATIN']
        mark = ''
        if fh != fl:
            mark += '  ← 한글/영문 글꼴 다름'
        style = ('B' if d['bold'] else '') + ('I' if d['italic'] else '')
        faces_seen[fh] += n
        print(f'{cid:>7} {n:>6} {intbl:>6} {d["pt"]:>6.1f}  {fh} / {fl} {style}{mark}')

    print('\n== 글꼴 분포(한글 기준, run 수) ==')
    for f, n in faces_seen.most_common():
        print(f'   {f}: {n}')
    problems = []
    if len(faces_seen) > 1:
        dom = faces_seen.most_common(1)[0][0]
        minor = {f: n for f, n in faces_seen.items() if f != dom}
        print(f'   ⚠ 지배 글꼴 "{dom}" 외 {len(minor)}종 혼재: {minor}')
        problems.append('글꼴 혼재')

    print('\n== JUSTIFY + KEEP_WORD 인 문단 중 영문 비율이 높은 것 ==')
    print('   (영문 근처 자간이 벌어지는 조합. 영문 비율이 높으면 LEFT 권장)')
    flagged = False
    for pid, (tot, cnt) in sorted(para_latin.items(), key=lambda x: -x[1][0] / max(1, x[1][1])):
        d = parapr.get(pid)
        if not d or cnt == 0:
            continue
        avg = tot / cnt
        if d['align'] == 'JUSTIFY' and d['latin'] == 'KEEP_WORD' and avg >= 0.30:
            print(f'   paraPr {pid:>3}  문단 {cnt:>3}개  평균 영문비율 {avg*100:>4.0f}%')
            flagged = True
    if flagged:
        problems.append('JUSTIFY+KEEP_WORD 영문 문단')
    else:
        print('   (해당 없음)')

    rc = 0
    if a.expect_face:
        bad = [f for f in faces_seen if f != a.expect_face]
        print(f'\n[기대] 글꼴 = {a.expect_face} → ' + ('OK' if not bad else f'FAIL: {bad} 혼재'))
        rc |= bool(bad)
    if a.expect_body_pt:
        body_cid = per_cid.most_common(1)[0][0]
        pt = charpr[body_cid]['pt']
        ok = abs(pt - a.expect_body_pt) < 0.01
        print(f'[기대] 본문(charPr {body_cid}) = {a.expect_body_pt}pt → '
              + ('OK' if ok else f'FAIL: {pt}pt'))
        rc |= (not ok)
    if problems and not (a.expect_face or a.expect_body_pt):
        print(f'\n요약: 점검 필요 — {", ".join(problems)}')
    return rc


if __name__ == '__main__':
    sys.exit(main())
