# ⚠ 이 파일은 «복사본»이다. 정본은 docx-editing 스킬의 같은 파일이고,
#   docx·pptx·hwpx 가 각각 자기 안에 두어 «스킬 하나만 받아도» 동작하게 한다
#   (ops3 공개 조건 1: 자족성). 고칠 일이 생기면 정본을 고치고 셋에 다시 복사할 것 —
#   `ops3_status.py` 가 갈라지면 알려 준다.
"""표 열 폭 기본값 — 균등 분할 금지, 내용량 비례.

⭐ 유래(2026-09-09, ebm-board): 빌더가 모든 열을 균등 분할(본문폭/열수)로 내보내자
창업자가 회의자료 표 20개 중 12개의 폭을 손으로 재배분했다 — 반복 지적("표 width는
내가 맨날 하는 말"). 역산한 규칙이 일관됐다:

    번호·라벨 열은 내용에 딱 맞게(snug), 최장 서술 열이 나머지를 전부 흡수,
    내용이 고른 표(빈 결정표·균질한 가격표)만 균등 유지.

data_table·add_journal_table 의 docstring 은 이걸 «사람에게» 시키고 있었다("Always
pass these"). 기억하는 규칙은 매 세션 리셋된다 — 그래서 여기 코드로 둔다. 명시적
widths 인자는 언제나 이 기본값을 이긴다.

순수 계산 모듈이다(docx 의존 없음) — 어느 빌더에서든 순환 없이 import 할 수 있다.

⚠ **자매 함수와 역할이 갈린다 — 합치지 말 것(2026-09-09 판정):**
`manuscript_table.col_widths_for()`는 **영문 저널 표** 전담(문자수 기반·감쇠·water-filling,
2026-09-03부터 원고 파이프라인들이 명시 호출 중이라 동작을 못 바꾼다). 이 모듈은
**국문·격자 장르** 전담 — CJK 표시폭(한글=2)과 «균등 유지» 판정은 저쪽에 없다.
add_journal_table 기본값 = col_widths_for / brief·회의자료 기본값 = content_col_widths.
"""
import re

# ⭐ 규칙은 «바뀔 수 있다». 상수를 흩어 두지 말고 한 프로필로 모은다 —
#    호출마다 `profile=` 로 덮어쓰고, `fit_col_profile.py` 로 사람의 선택에서 역산한다.
DEFAULT_PROFILE = {
    "max_snug_units": 40,    # snug 폭 계산의 가중치 상한(이보다 길면 어차피 여러 줄)
    "ratio_threshold": 1.6,  # 최장/최단 내용비가 이 미만이면 균등 유지
    "dominant_frac": 0.6,    # 최장 내용의 60% 이상인 열 = 지배 열(남은 폭을 나눠 가짐)
    "cm_per_unit": 0.18,     # 9pt 맑은고딕 실측 근사(한글 1자 = 2 units)
    "pad_cm": 0.35,
    "min_cm": 0.8,
    "max_snug_cm": 5.0,
    "cjk_weight": 2.0,       # 한글·CJK 한 글자
    "latin_weight": 0.85,    # 라틴·숫자 한 글자 (2026-09-09 역산)
    "other_weight": 1.0,
}

_MAX_SNUG_UNITS = DEFAULT_PROFILE["max_snug_units"]
_RATIO_THRESHOLD = DEFAULT_PROFILE["ratio_threshold"]
_DOMINANT_FRAC = DEFAULT_PROFILE["dominant_frac"]
_CM_PER_UNIT = DEFAULT_PROFILE["cm_per_unit"]
_PAD_CM = DEFAULT_PROFILE["pad_cm"]
_MIN_CM, _MAX_SNUG_CM = DEFAULT_PROFILE["min_cm"], DEFAULT_PROFILE["max_snug_cm"]


def _P(profile):
    p = dict(DEFAULT_PROFILE)
    if profile:
        p.update(profile)
    return p
_MD_RE = re.compile(r"\*\*|`|\*")


def visual_units(text, profile=None):
    """표시 폭(단위). 한글·CJK=2, 라틴·숫자=0.85, 그 밖의 ASCII=1.

    ⚠ 라틴을 1.0 으로 세면 «영문이 긴 열»이 과대해진다(2026-09-09 실측: SIGN 체크리스트를
      영문 원문으로 바꾸자 항목 열이 8.3cm 로 계산됐는데 사람은 6.9cm 를 주었다).
      9pt 맑은고딕에서 한글 1자 ≈ 0.32cm, 라틴 소문자 ≈ 0.15cm — 비가 2 : 0.85 에 가깝다.
    """
    p = _P(profile)
    t = _MD_RE.sub("", str(text)).strip()
    w = 0.0
    for ch in t:
        if ord(ch) > 0x2E80:
            w += p["cjk_weight"]
        elif ch.isalnum():
            w += p["latin_weight"]
        else:
            w += p["other_weight"]
    return w


def line_units(text, profile=None):
    """줄바꿈이 박힌 칸의 «가장 긴 줄» 표시폭 — 그 줄이 끊기면 읽히지 않는다."""
    return max((visual_units(ln, profile) for ln in str(text).split("\n")), default=0)


def content_col_widths(rows, total_cm, ncols=None, profile=None):
    """행들(머리행 포함, 셀 문자열)에서 열 폭(cm 리스트)을 계산한다.

    rows      list of list of str — 머리행 포함 전체 행
    total_cm  표가 차지할 본문 폭(cm). 문서 여백에서 계산해 넘길 것
    ncols     열 수(생략 시 최장 행 기준)

    반환 리스트의 합 == total_cm. 내용비가 낮으면 균등 리스트를 돌려준다.
    """
    p = _P(profile)
    if ncols is None:
        ncols = max(len(r) for r in rows) if rows else 1
    even = [total_cm / ncols] * ncols
    units = [2] * ncols
    floors = [0.0] * ncols     # 줄바꿈이 박힌 칸의 «가장 긴 줄» — 이보다 좁으면 안 된다
    for row in rows:
        for j in range(min(ncols, len(row))):
            units[j] = max(units[j], visual_units(row[j], profile))
            if "\n" in str(row[j]):
                floors[j] = max(floors[j], line_units(row[j], profile))
    if max(units) < p["ratio_threshold"] * min(units):
        return even
    dom = [j for j in range(ncols) if units[j] >= p["dominant_frac"] * max(units)]
    snug = {j: min(max(min(units[j], p["max_snug_units"]) * p["cm_per_unit"] + p["pad_cm"],
                       p["min_cm"]), p["max_snug_cm"])
            for j in range(ncols) if j not in dom}
    remainder = total_cm - sum(snug.values())
    if remainder >= 2.0 * len(dom):
        dom_total = float(sum(units[j] for j in dom))
        out = [snug[j] if j in snug else remainder * units[j] / dom_total
               for j in range(ncols)]
    else:
        # 지배 열 몫이 너무 작으면 단순 비례로 후퇴
        total_u = float(sum(units))
        out = [max(total_cm * u / total_u, _MIN_CM) for u in units]
    return _apply_floors(out, floors, dom, total_cm, p)


def _apply_floors(widths, floors, dom, total_cm, p=None):
    p = _P(p)
    """줄바꿈 칸의 «가장 긴 줄»이 들어가도록 폭을 올리고, 지배 열에서 갚는다."""
    need = [(j, min(f * p["cm_per_unit"] + p["pad_cm"], total_cm * 0.5) - widths[j])
            for j, f in enumerate(floors)
            if f and min(f * p["cm_per_unit"] + p["pad_cm"], total_cm * 0.5) > widths[j]]
    if not need:
        return widths
    w = list(widths)
    taken = {j for j, _ in need}
    donors = [j for j in dom if j not in taken] or \
             [max(range(len(w)), key=lambda k: w[k])]
    for j, gap in need:
        w[j] += gap
        for d in donors:
            w[d] = max(w[d] - gap / len(donors), p["min_cm"])
    scale = total_cm / sum(w)
    return [x * scale for x in w]


def doc_text_width_cm(doc):
    """문서 첫 섹션의 본문 폭(cm) — 표 total_cm 의 기본값으로 쓴다."""
    s = doc.sections[0]
    return (s.page_width - s.left_margin - s.right_margin) / 360000  # EMU -> cm
