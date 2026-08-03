# HWPX 편집 가이드 v7.1

> 한글(HWPX)을 Python/lxml로 안전하게 편집하는 실전 가이드. 모든 항목은 한글 렌더링 또는 바이트 수준으로 **검증된 것**만 담았다.
> **v6→v7**: 다단·목차·수식(§5)과 페이지·단·구조 편집(§6)을 통합. 나머지는 v6의 핵심만 압축.
> **v7→v7.1**: **상호참조(CROSSREF, 재인용)** 절 신설(§4) + 흔한 실패 23·24 + `crossref_check.py`.

---

## ⚠️ 흔한 실패 TOP (먼저 읽을 것)

1. **재압축 시 원본 엔트리를 재deflate → 한글이 거부.** 변경 안 한 엔트리는 바이트째 복사하는 **raw-preserving 재압축**(§2)을 쓴다.
2. **`linesegarray`를 안 지움 → 자간·줄간격 깨짐.** 편집·신규 문단은 제거. **구조 편집 후엔 전면 제거**(§6).
3. **클론(미주·표·수식·그림)이 원본 id를 물려받아 중복 → 불안정.** 클론 후 **id 중복 제거 pass**(§3).
4. **레이아웃 이상인데 keepWithNext부터 만짐.** **숨은 `pageBreak`/`columnBreak`부터 전수조사**(§6-A). 본문 문단의 break는 원저자 잔재일 때가 많다.
5. **content.hpf를 raw 문자열로 편집 → 백슬래시 오염으로 파일이 안 열림.** **XML로 파싱 검증**(§7).
6. **이미지를 추출 순서대로 배치 → 뒤바뀜.** **내용으로 검증**(§5-수식/그림).
7. **header.xml에 charPr/paraPr 추가 후 `itemCnt` 미갱신 → 거부.** 되도록 **기존 정의 재사용**(§4).
8. **일괄 정규식 치환(띄어쓰기 등) → 코드·표 인접 셀 파괴.** 단위별 스캔·섹션 스코핑(§4).
9. **텍스트 추출을 `.text`로만 → `itertext()` 미사용, 표 셀·메모 혼입.** `own()`으로 각주·미주·메모 제외, 셀은 개별 순회(§1).
10. **컬럼폭 초과 표를 2단에 둠 → 잘림.** 1단 구역으로, 순서 유지는 secPr 블록 이동(§6-D).
11. **이미지 in-place 교체 시 `imgDim` 미갱신 → 그림 아래 잘림.** 한글이 `imgClip`을 **옛 `imgDim`** 기준으로 해석(잘림비=새orgH/옛imgDimH). orgSz만 고치고 imgDim/scaMatrix를 빼먹기 쉽다 → **`hwpxlib.replace_image()`로 전 필드 일괄 갱신**(§4). 구조검증은 잘림을 못 잡으니 **한글로 렌더해 확인**(§7).
12. **`fontRef`의 lang별 인덱스를 같은 글꼴로 착각.** fontface 배열은 **lang마다 순서가 다르다** — `hangul="6"`과 `latin="6"`이 서로 다른 글꼴을 가리킬 수 있다. **인덱스가 아니라 이름으로 비교**(§4-서식 감사).
13. **문단을 손으로 복제 → 서식 뭉갬·secPr 중복.** run마다 charPr이 다른 문단(참고문헌 등)에서 "run[1:] 제거 후 t[0]에 전체 텍스트"를 하면 **run[0] 서식이 문단 전체에 먹고**, 섹션 첫 문단을 템플릿으로 쓰면 **secPr이 중복되며 텍스트 run이 사라진다**. → **`hwpxlib.pick_template()` + `clone_para()`를 쓴다**(§3).
15. **`align=JUSTIFY` + `breakLatinWord="KEEP_WORD"` → 영문 근처 자간이 벌어짐.** 긴 영문 토큰을 줄 끝에서 못 쪼개니 양쪽정렬이 단어 사이 공백을 늘린다. 한글 본문에 영문 용어·서지가 섞이면 눈에 띄게 들쭉날쭉해진다. **표 셀에서는 더 심해서** 줄바꿈된 셀이 `N o n - H i s p a n i c` 처럼 글자 단위로 벌어진다 — 셀 문단만 LEFT로 돌리면 없어진다(§4-서식 감사).
16. **셀 텍스트를 문단 구분 없이 이어붙임 → 없는 오타를 만든다.** 한 셀의 여러 `hp:p`는 **줄바꿈**이다. 그냥 join하면 `US adults,` + `n=43` 이 `US adults,n=43` 이 되어 "띄어쓰기 오류"로 보인다(실제 감사에서 오탐 4건, 고칠 뻔했다). **`hwpxlib.cell_text()`/`table_grid()`의 `para_sep`을 쓸 것**(§1).
17. **표 값 서식을 바꾸고 렌더를 안 봄 → 숫자가 두 줄로 쪼개짐.** `4701`→`4,701` 한 글자가 열 폭을 넘겨 `4,70`/`1`로 줄바꿈된다. **XML 검사도 셀↔소스 대조도 전부 통과하고 렌더에서만 보인다.** `hwpxlib.set_column_width()`로 다른 열에서 폭을 옮기고 **`audit_layout.py`로 확인**(§4·§7).
18. **표 각주 길이를 바꾼 뒤 페이지를 안 봄 → 고아 페이지.** 각주가 혼자 다음 장으로 넘어가 거의 빈 페이지가 된다. 각주를 늘리거나 줄였으면 재렌더해 희박 페이지를 확인(§7).
19. **한 앵커에 미주를 둘 이상 달다가 방금 만든 미주 **안에** 다음 미주를 넣음 → 한글이 열 때 오류.** `.//hp:run`·`.//hp:p`·`.//hp:endNote`가 `subList`를 타고 들어가므로, 첫 미주를 만든 뒤 run 핸들이 그 미주 내부를 가리킨 채 남는다. **`hwpxlib.add_endnotes()`로 문단 수준 형제로만 삽입**하고, `verify.py` 3d(`nested_notes()`)로 게이트(§4-주석).
20. **`<hp:tbl rowCnt>`를 실제 `<hp:tr>` 수와 안 맞춤 → 문서 전체가 한 쪽으로 무너짐.** 행을 추가·삭제했으면 `rowCnt`(및 `colCnt`)를 갱신한다(§4-표).
21. **구역을 지우거나 떼어낸 뒤 `header.xml`의 `<hh:head secCnt>`를 안 고침 → 열리기는 하는데 빈 한 쪽만 나온다.** 병합본에서 한 장만 추출할 때 특히. `secCnt`는 실제 `sectionN.xml` 개수와 같아야 한다. `content.hpf`(manifest+spine)와 `META-INF/container.rdf`도 함께 고쳐야 한다 — **`hwpxlib.extract_section()`이 셋을 다 처리한다**(§6-E).

22. **여러 장을 합치는 보고서인데 미주 배치가 `END_OF_DOCUMENT`.** 합치는 순간 그 장의 미주가 **보고서 맨 끝으로 몰리고 「참고문헌」 표제는 빈 채로 남는다.** 단독으로 열면 멀쩡해 보인다. `secPr/endNotePr`을 `ON_SECTION`·`END_OF_SECTION`으로(§6-E).

23. **본문을 통째로 갈아끼워 상호참조(CROSSREF) 필드 쌍을 날림 → 재인용 번호가 사라진다.** 재인용은 「미주 번호를 따라가는 필드」다(`fieldBegin` + 캐시 `<hp:t>` + `fieldEnd`). 문단 텍스트를 통째 치환하면 `ctrl` 쌍이 함께 지워진다. **인용번호가 리터럴 텍스트로 남아 있는 것도 같은 부류** — 지금은 맞아 보이고 번호가 밀리는 «그때» 틀린다. `crossref_check.py`로 편집 전·후 각각 확인(§4-상호참조).

24. **새로 만든 미주의 `instId`가 2³¹을 넘음 → 그것을 가리키는 상호참조가 본문에 「?)」로 찍힌다.** 한글 문서에는 `3,1xx,xxx,xxx` 같은 id가 흔해서, 최대값에서 이어 발급하면 바로 넘어간다. **XML well-formed·id 중복 0·verify 전항목 PASS인데 렌더에서만 보인다.** `make_uid()`는 2³¹ 아래에서만 발급한다 — 직접 만든 발급기를 쓸 때만 주의(§4-상호참조).

> 19·20·21·22·23·24는 같은 부류다 — **XML은 well-formed, id 중복 없음, 하드체크 전부 PASS. 한글로 열어야만 드러난다.** 22는 한 술 더 떠서 **단독 렌더도 통과하고 합쳐야 드러난다.** 구조·표·주석·구역·**필드**를 건드렸으면 렌더까지, 취합될 원고라면 **합쳐서** 렌더까지 가야 끝난 것이다(§7).

---

## §1. 구조 & 파싱

HWPX = **zip + XML(HWPML)**. 엔트리: `mimetype`(첫 엔트리·STORED) · `Contents/header.xml`(charPr·paraPr·borderFill 정의) · `Contents/section0.xml~N`(본문) · `Contents/content.hpf`(manifest) · `BinData/`(이미지).
네임스페이스: `hp`=paragraph(단락·표·런·필드) · `hc`=core(인라인 이미지 `<hc:img>`) · `hh`=header 정의 · `opf`=content.hpf.

```python
from lxml import etree
import zipfile
P='{http://www.hancom.co.kr/hwpml/2011/paragraph}'
H='{http://www.hancom.co.kr/hwpml/2011/head}'
z=zipfile.ZipFile('file.hwpx'); root=etree.fromstring(z.read('Contents/section0.xml'))

def own(p):   # 각주(footNote)·미주(endNote)·메모(fieldBegin) 내부 텍스트 제외한 '진짜 본문'
    return ''.join(''.join(t.itertext()) for t in p.findall(f'.//{P}t')
                   if not any(a.tag in (f'{P}footNote',f'{P}endNote',f'{P}fieldBegin') for a in t.iterancestors()))
```

규칙: **본문은 section0~N 전부 확인** · 텍스트는 **`itertext()`**(lineBreak tail 누락 방지) · 그림 존재는 **`<hp:pic>` 직접 검색** · 표 텍스트는 **`<hp:tc>` 셀별로**(itertext로 한 번에 뽑으면 인접 셀이 붙어 거짓양성) · `styleIDRef`/`paraPrIDRef`/`charPrIDRef`/`borderFillIDRef`는 **파일마다 다르니 실제 파일에서 읽어** 쓴다.

---

## §2. 재압축 (raw-preserving) — ★가장 중요

변경 안 한 엔트리의 로컬 엔트리를 **바이트째 복사**(flag_bits 보존), 바꾼 XML만 재deflate. no-op 재압축이 **원본과 바이트 동일**해 원본이 열리면 편집본도 열린다.

```python
import struct, io, zlib
def _parse_central(raw):
    eocd=raw.rfind(b'PK\x05\x06'); cd_size,cd_off=struct.unpack('<II', raw[eocd+12:eocd+20])
    recs={}; order=[]; p=cd_off
    while raw[p:p+4]==b'PK\x01\x02':
        (sig,vmb,vn,flag,method,mt,md,crc,csize,usize,fnl,efl,cml,disk,iattr,eattr,loff)=struct.unpack('<IHHHHHHIIIHHHHHII', raw[p:p+46])
        name=raw[p+46:p+46+fnl].decode('utf-8')
        extra=raw[p+46+fnl:p+46+fnl+efl]; comment=raw[p+46+fnl+efl:p+46+fnl+efl+cml]
        recs[name]=dict(vmb=vmb,vn=vn,iattr=iattr,eattr=eattr,extra=extra,comment=comment,flag=flag,
                        method=method,crc=crc,csize=csize,usize=usize,mt=mt,md=md,loff=loff)
        order.append(name); p+=46+fnl+efl+cml
    return recs, order

def repack_preserve(src, changed, out, added=None):
    raw=open(src,'rb').read(); recs, order=_parse_central(raw); obuf=io.BytesIO(); meta={}
    for name in order:
        rc=recs[name]; loff=obuf.tell(); fnb=name.encode('utf-8')
        if name in changed:
            data=changed[name]
            if rc['method']==8:
                co=zlib.compressobj(6,zlib.DEFLATED,-15); comp=co.compress(data)+co.flush()
            else:
                comp=data
            crc=zipfile.crc32(data)&0xffffffff
            obuf.write(struct.pack('<IHHHHHIIIHH',0x04034b50,rc['vn'],0,rc['method'],rc['mt'],rc['md'],crc,len(comp),len(data),len(fnb),0)+fnb+comp)
            meta[name]=dict(rc, flag=0, crc=crc, csize=len(comp), usize=len(data), loff=loff, extra=b'')
        else:                       # raw copy
            ho=rc['loff']; (sig,ver,flag,method,mt,md,crc,csize,usize,fnl,efl)=struct.unpack('<IHHHHHIIIHH', raw[ho:ho+30])
            obuf.write(raw[ho:ho+30+fnl+efl+csize]); meta[name]=dict(rc, loff=loff)
    if added:                       # 신규 BinData/섹션 (DEFLATED)
        for name, data in added.items():
            loff=obuf.tell(); fnb=name.encode('utf-8')
            co=zlib.compressobj(6,zlib.DEFLATED,-15); comp=co.compress(data)+co.flush(); crc=zipfile.crc32(data)&0xffffffff
            obuf.write(struct.pack('<IHHHHHIIIHH',0x04034b50,20,0,8,0,0,crc,len(comp),len(data),len(fnb),0)+fnb+comp)
            meta[name]=dict(vmb=20,vn=20,flag=0,method=8,mt=0,md=0,crc=crc,csize=len(comp),usize=len(data),loff=loff,extra=b'',comment=b'',iattr=0,eattr=0)
            order.append(name)
    cd=obuf.tell()
    for name in order:
        m=meta[name]; fnb=name.encode('utf-8')
        obuf.write(struct.pack('<IHHHHHHIIIHHHHHII',0x02014b50,m['vmb'],m['vn'],m['flag'],m['method'],m['mt'],m['md'],m['crc'],m['csize'],m['usize'],len(fnb),len(m['extra']),len(m['comment']),0,m['iattr'],m['eattr'],m['loff'])+fnb+m['extra']+m['comment'])
    n=len(order); obuf.write(struct.pack('<IHHHHIIH',0x06054b50,0,0,n,n,obuf.tell()-cd,cd,0)); open(out,'wb').write(obuf.getvalue())
```

- 바꾼 XML 앞엔 `<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>\n` 유지. 바꾼 것만 `changed`, 신규는 `added`.
- **자가검증**: `repack_preserve(src,{},out)` → 원본과 바이트 동일.

---

## §3. 편집 공통 규칙 (linesegarray · id)

- **linesegarray 제거**: 문단을 편집·신규 생성하면 `<hp:linesegarray>`(캐시된 줄배치)가 stale → 반드시 제거. 문단별로 찔끔 지우지 말고, **구조 편집 후엔 관련 섹션 전체를 전면 제거**해 한글이 열 때 완전 재조판(§6-B).
  ```python
  for ls in sec.findall(f'.//{P}linesegarray'): ls.getparent().remove(ls)
  ```
  삽입 단락이 주변과 **동일 charPr·paraPr**(특히 정렬 JUSTIFY)이면 한글 재조판 시 주변과 자간이 일치한다. linesegarray 없는 단락은 **한글에서 열어 저장(Ctrl+S)하기 전**엔 외부 미리보기에서 자간이 달라 보일 수 있다(저장하면 확정). 부차 원인: charPr의 script별 장평(`<hh:ratio>`)·자간(`<hh:spacing>`) 오매핑 → **새 charPr 만들지 말고 기존 재사용**.
- **linesegarray 재출현 = 사람이 한글에서 열어 저장한 신호(역진단).** 네가 섹션 전체의 linesegarray를 0개로 지웠는데 다음에 파일을 열었을 때 다시 있으면(예: 562개), 그 사이 **사람이 한글에서 열어 저장(=재조판)**한 것이다. 사용자가 "내가 고친 걸 base로"라고 하면 네 in-memory/직전 저장 상태를 믿지 말고 **디스크 파일을 다시 읽어** 그 위에 쌓아라. mtime·미주 개수 변화도 함께 확인(사람이 텍스트만 고쳤는지, 구조까지 바꿨는지 구분).
- **id 중복 제거**: 요소를 deepcopy하면 원본 id를 물려받는다. 클론 후 새 id 발급 + 검증.
  ```python
  def make_uid(root):
      ids={int(v) for el in root.iter() for a in ('id','instId','instid') if (v:=el.get(a)) and str(v).isdigit()}
      c=[max(ids)+5]
      def uid(): c[0]+=2; return c[0]
      return uid
  ```
  미주 클론은 내부 `subList>p`의 id까지, 표 클론은 `tbl`·`tc`·`p` id까지 새로 준다.
- **문단 복제는 `hwpxlib`의 헬퍼로.** 직접 복제하면 두 가지가 조용히 깨진다 — (a) run마다 charPr이 다른 문단(저자 bold / 제목 plain / 저널 italic)을 한 덩어리로 채우면 **run[0] 서식이 전체에 먹고**, (b) 섹션 첫 문단은 `secPr` 보유자라 템플릿으로 쓰면 **secPr 중복 + 텍스트 run 소실**. 둘 다 구조검증은 통과하고 렌더에서만 보인다.
  ```python
  from hwpxlib import pick_template, clone_para, run_patterns
  tpl = pick_template(list(sec), style='11')            # secPr 보유 문단을 알아서 배제
  p1  = clone_para(tpl, uid, "단일 run 문단 텍스트")
  p2  = clone_para(tpl, uid, [('46', 저자연도), ('47', ' '+제목+' '), ('48', 저널), ('47', 나머지)])
  assert len(set(run_patterns(참고문헌들))) == 1        # 서식 균일성 게이트
  ```
  조각 경계의 **공백도 원본을 따라간다** — 저널명 앞 공백을 빼먹으면 `studies.BMJ Open`처럼 붙는다.

---

## §4. 콘텐츠 편집 (단락·표·이미지·서식·메모)

**단락/텍스트**: `<hp:t>.text` 교체. 새 단락은 `paraPrIDRef`(문단 서식)·run `charPrIDRef`(글자 서식)를 **기존 정의에서 골라** 지정. 삭제는 `getparent().remove()`.

**표(tbl)**: `tbl(rowCnt,colCnt,sz.width)` > `tr` > `tc(cellAddr,cellSpan,cellSz,borderFillIDRef) > subList > p > run > t`.
- 셀 클론 시 **`cellSz.height`**=본문 282(헤더 0/282), **각 행 열폭 합 = 표 sz.width**(안 맞으면 거부).
- 헤더 음영은 `borderFillIDRef` 분리(예 헤더 25, 본문 3). 긴 셀은 paraPr JUSTIFY+vertAlign TOP.
- **병합**: 세로(rowSpan)=시작 tc `cellSpan rowSpan=N`, 이후 행은 **가려지는 col의 tc 생략** / 가로(colSpan)=시작 tc `colSpan` 키우고 **가려지는 tc 제거 + 너비 합산**.
- **행을 더하거나 지웠으면 `tbl@rowCnt`(및 `colCnt`)를 실제 개수에 맞출 것.** 안 맞으면 한글이 표를 못 읽어 **문서 전체가 한 쪽으로 무너진다** — 구조검사는 전부 통과한다(흔한 실패 20).

**표 다시 채우기 (재분석 후 원고 표 갱신)** — 문서에 붙여넣은 표는 **붙여넣은 순간의 분석 결과에 얼어붙는다.** 재분석하면 본문은 사람이 고쳐 쓰지만 표는 따라오지 않아, 표와 본문이 서로 다른 분석을 담은 채 공존한다. 값을 손으로 옮기지 말고 소스에서 채운다:

```python
rows = [r[1:] for r in csv.reader(open(SRC, encoding="utf-8"))][1:]
hwpxlib.fill_table(tbl, rows, row_offset=3, col_offset=1)   # 헤더 3행 · 라벨 열 보존
```

그러면 (a) 재실행 한 번이 전수 갱신이고, (b) `table_grid()`로 다시 읽어 같은 소스와 비교하는 것이 그대로 검증기가 된다. 열을 지우거나 넓혀야 하면 `delete_column`/`set_column_width`를 쓴다 — 폭 합계를 손으로 맞추면 한글이 파일을 거부한다. 값·폭·각주 길이를 바꿨으면 **`audit_layout.py`로 렌더까지 확인**(흔한 실패 17·18).
- 캡션(표/그림): **텍스트 편집**=`<hp:caption>` 안 마지막 `<hp:t>` 교체. **신규 생성**=`<hp:outMargin>` **직후**에 `<hp:caption side gap width lastWidth fullSz="0">` 삽입(ShapeObject 순서 `sz·pos·outMargin·caption·…` — 표는 caption 뒤 `inMargin·tr`, 그림은 caption 뒤 `shapeComment`). 본문은 **실제 셀 `subList` 복제** → 안의 `<hp:p>` run에 `<hp:t>` 세팅 후 `linesegarray` 제거. **위치**=`side` `TOP/BOTTOM/LEFT/RIGHT`(LEFT/RIGHT는 `width`가 캡션 열폭). **정렬**=캡션 `<hp:p>`의 `paraPrIDRef`(원하는 정렬의 기존 paraPr 재사용; 없으면 새 paraPr 추가 + `itemCnt` 갱신). `autoNum`은 한글 자동 번호. 표 각주는 표 밖 별도 단락(작은 charPr).
- **추출 섹션 vs 병합본 — 문서 전역 번호(표·그림 캡션 `autoNum`, 미주)는 병합본에서만 해결된다.** 큰 병합 문서에서 한 장(章=한 section)만 떼어내 편집하면, 캡션 `autoNum`은 "이게 전체에서 78번째 표"임을 알 수 없어 단독 파일에선 비거나 다른 번호로 보인다 → **캡션 번호를 손으로 채우지 말 것**(autoNum과 겹쳐 이중 표기). 다시 병합하면 자동으로 맞춰진다. **본문 평문 참조**("<표 78>는", "(그림 18)")는 autoNum이 아니라 고정 텍스트라 자동 갱신 안 됨 → 정석은 병합본에서 **교차참조(cross-ref)**, 정 안 되면 **확정 번호를 수동 기입**을 기본으로. 편집 전 `find`로 본문 참조를 전수 조사해 개수를 먼저 세라(신부전: 전체에 `<표 78>`·`(그림 18)` 딱 2개, 나머지 `<표 >`는 전부 캡션이었다).
- **표 폭을 일괄 통일하지 마라 — 기존 폭 변이는 대개 의도(설계)다.** 셀 너비 합=표 `sz.width`는 *기술적* 제약이지, "모든 표를 본문 단 전체폭으로"가 아니다. 한 보고서 안에 현황표(넓게)와 정의성/소표(의도적으로 좁게)가 공존하며, **들여쓰기(문단 좌여백) 안에 놓인 표는 단 전체폭이 아니라 그만큼 좁아야** 한다. 폭이 44000 vs 31372로 갈려 있으면 "불일치"라 단정 말고 **의도인지 먼저 의심**하라. 시각적 폭 조정은 XML 일괄보다 **한글에서 표별 수동**이 정답(안질환 2026-07-24: 12표를 48190으로 밀었다가 청구정의표까지 늘려 사용자가 표별로 되돌림). 리사이즈가 정말 필요하면 각 행 셀을 비례 재계산 후 행합을 검증(그건 유효했음).

**열 수 바꾸는 신규 표(2열→5×5 완전 예제)** — 담는 단락째 clone → tbl 초기화 → 헤더/본문 셀 템플릿 재조립:
```python
import copy
newpara=copy.deepcopy(template_para); newpara.set('id',str(uid()))
ntbl=newpara.find(f'.//{P}tbl'); ntbl.set('rowCnt','5'); ntbl.set('colCnt','5')
ntbl.find(f'{P}sz').set('width','41954')                      # 표폭
for tr in ntbl.findall(f'{P}tr'): ntbl.remove(tr)            # 기존 행 제거
hdr_tpl=copy.deepcopy(원본_헤더_tc)   # borderFillIDRef 25(음영)
body_tpl=copy.deepcopy(원본_본문_tc)  # borderFillIDRef 3
W=[3800,6200,6800,13000,12154]                               # ★열폭 합 = 표폭(41954)
def make_cell(tpl,col,row,text,paraPr,valign,bfill):
    tc=copy.deepcopy(tpl); tc.set('borderFillIDRef',bfill)
    tc.find(f'{P}subList').set('vertAlign',valign)            # 긴 셀 TOP, 짧은 셀 CENTER
    p=tc.find(f'.//{P}p'); p.set('id',str(uid())); p.set('paraPrIDRef',paraPr)
    for ls in p.findall(f'{P}linesegarray'): p.remove(ls)     # ★linesegarray 제거
    r=p.find(f'{P}run'); r.set('charPrIDRef','22')
    for ch in list(r):
        if ch.tag==f'{P}t': r.remove(ch)
    etree.SubElement(r,f'{P}t').text=text
    tc.find(f'{P}cellAddr').set('colAddr',str(col)); tc.find(f'{P}cellAddr').set('rowAddr',str(row))
    sp=tc.find(f'{P}cellSpan'); sp.set('colSpan','1'); sp.set('rowSpan','1')
    cs=tc.find(f'{P}cellSz'); cs.set('width',str(W[col])); cs.set('height','282')  # ★본문 282
    return tc
for row,vals in enumerate(all_rows):
    tr=etree.SubElement(ntbl,f'{P}tr')
    for col,txt in enumerate(vals):
        paraPr='19' if col in 긴열 else '31'                 # 19=JUSTIFY, 31=CENTER
        valign='TOP' if col in 긴열 else 'CENTER'
        tr.append(make_cell(hdr_tpl if row==0 else body_tpl, col,row,txt,paraPr,valign,'25' if row==0 else '3'))
```
검증: `rowCnt`/`colCnt`, **각 행 셀 수=colCnt**, **각 행 열폭 합=표 sz.width**, 셀 텍스트, tbl 수 증가 + **id 중복 제거 pass**(§3, 클론 tbl이 원본 id 상속).

**이미지**: 인라인 `<hc:img binaryItemIDRef="imageN">`(hc 네임스페이스).
- **담는 단락째 clone** 후 `<hp:pic>` 교체: `binaryItemIDRef`·`id`·`instid` 새로, **크기(HWPUNIT)** — `orgSz`=native(**px×75**), `curSz`=`sz`=표시크기, `imgRect`/`imgClip`/**`imgDim`**=native 좌표, `scaMatrix e1=e5`=표시폭/native폭. linesegarray 제거.
- **기존 그림만 교체(단락 유지)**: `hwpxlib.replace_image(pic, png_bytes, disp_w)` — orgSz·curSz·sz·**imgDim**·imgClip·imgRect·scaMatrix를 **한 번에** 갱신하고 `(binItemId, png_bytes)` 반환 → `repack_preserve(..., changed={f"BinData/{ref}.png": png_bytes, ...})`. ⚠️ **`imgDim`을 빼먹으면 한글이 `imgClip`을 옛 imgDim 기준으로 해석해 그림 아래를 자른다**(구조검증 통과, 렌더에서만 드러남). 손으로 필드를 고치지 말고 이 helper를 쓸 것.
- 등록: content.hpf `<opf:manifest>`에 `<opf:item id="imageN" href="BinData/imageN.png" media-type="image/png" isEmbeded="1"/>`, 파일은 `added`로.
- **표시폭 상한 ≈ 단폭**(2단 ≈ 26363), `DH=round(DW*native_h/native_w)`.
- **내용으로 검증**: 추출 순서 ≠ 시각 순서일 수 있음. 밝기(그래프 vs 수식박스)·형태(막대 중앙 빈틈=Bimodal)로 확인 후 배치.
- **한글 렌더 검증(그림·레이아웃 필수, Windows+한컴)**: LibreOffice는 hwpx 렌더 불가 → 구조검증만으론 잘림·여백·페이지깨짐을 못 잡는다. 한글 COM으로 PDF를 뽑아 **눈으로** 볼 것. 편집 전 `taskkill /F /IM Hwp.exe`로 파일락 해제.
  ```python
  import win32com.client as w, fitz            # pip install pywin32 pymupdf
  hwp=w.Dispatch("HWPFrame.HwpObject"); hwp.RegisterModule("FilePathCheckDLL","SecurityModule")
  hwp.Open(path,"HWPX","forceopen:true"); hwp.SaveAs(pdf,"PDF",""); hwp.Quit()
  page=fitz.open(pdf)[i]
  for im in page.get_images(full=True):        # 박힌 px 실측 → 잘림 진단
      d=fitz.open(pdf).extract_image(im[0]); print(d['width'],d['height'])
  page.get_pixmap(dpi=150).save("check.png")    # 사람이 볼 이미지
  ```
- **이미지 생성(matplotlib) 가독성**: 문서상 글씨크기 ≈ `png_폰트pt × (표시폭/캔버스폭)`. 표시폭이 캔버스폭보다 작으면 그만큼 축소됨 → **캔버스는 작게, 폰트는 크게**("그림 작게, 글씨 크게"). 텍스트 넘침은 `get_window_extent()`로 박스폭과 사전 비교. 한글 폰트는 `NotoSansCJK-*.ttc`를 `FontProperties(fname=…)`로 지정(Bold 별도 파일).

**글자·문단 서식**: charPr=글자(색 `textColor`, 굵기 `<hh:bold>` 유무, 크기 `height`=pt×100), paraPr=문단(정렬·개요수준·줄간격). **기존 정의 재사용이 가장 안전** — 새로 추가하면 `<hh:charProperties>`/`<hh:paraProperties>`의 `itemCnt` 갱신 필수(불일치 시 거부). placeholder·강조에서 복사한 텍스트는 색·굵기를 물려받으니 **최종 서식 charPr로 교체**.

**서식 감사 (글꼴·크기 일관성)** — 구조검증(verify.py)이 못 잡는 대표 육안 결함. `python scripts/audit_typography.py FILE.hwpx [--expect-face 휴먼명조] [--expect-body-pt 10]`으로 **실제 사용되는 charPr을 사용횟수·크기·글꼴로 집계**한다. 결함은 대개 소수 charPr에만 몰려 있어 집계하면 즉시 드러난다.
- **fontface 인덱스는 lang마다 배열이 다르다.** `<hh:fontface lang="HANGUL">`과 `lang="LATIN"`의 `<hh:font>` 순서가 서로 달라서, `<hh:fontRef hangul="6" latin="6"/>`이 **같은 글꼴이라는 보장이 없다.** 반드시 각 lang 배열을 따로 인덱싱해 **이름으로** 비교할 것. 글꼴을 바꿀 때도 lang별로 인덱스를 다시 찾아 넣는다.
  ```python
  faces={ff.get('lang'):[f.get('face') for f in ff.iter(H+'font')] for ff in hd.iter(H+'fontface')}
  han_i=faces['HANGUL'].index('휴먼명조'); lat_i=faces['LATIN'].index('휴먼명조')   # 값이 다를 수 있다
  ```
- **영문 근처 자간 깨짐** = `align=JUSTIFY` + `breakSetting/@breakLatinWord="KEEP_WORD"`. 긴 영문 토큰을 줄 끝에서 못 쪼개니 양쪽정렬이 공백을 늘려 벌린다. 참고문헌처럼 **영문 비율이 높은 문단은 해당 paraPr을 LEFT로**. 바꾸기 전 **그 paraPr이 대상 문단 전용인지 사용 횟수를 세어 확인**하면 새 정의 추가(=`itemCnt` 갱신) 없이 안전하다.
- 본문 글꼴이 섞이는 전형적 위치: **참고문헌·그림 캡션·빈 문단**. 다른 문서에서 붙여넣은 흔적이 여기 남는다. 빈 문단도 고쳐 둘 것 — 나중에 글자를 넣는 순간 글꼴이 튄다.
- 크기는 **제목과 본문이 같은 pt면 위계가 없다**. 본문을 줄일 때 제목 charPr을 함께 건드리지 않도록 id를 분리해 확인한다.

**미주·각주(endNote/footNote)**: **`<hp:ctrl>` 래핑 필수.** 한 run 안에서 **`[t 앞][ctrl>endNote][t 뒤]`로 인라인 삽입**(기존 미주 run을 clone하면 구조 보장). 번호는 한글이 위치 기준 자동 재계산 → 순서대로 삽입. 각주는 `endNote`→`footNote`, autoNum `numType`을 `ENDNOTE`→`FOOTNOTE`로만 변경. **클론 함정**: `endNote`의 `instId`뿐 아니라 내부 `subList>p`의 **id도 새로 부여**(안 하면 중복 → 불안정). 본문 추출은 `own()`으로 제외(§1).

🔴 **흔한 실패 — 방금 만든 미주 안에 다음 미주를 넣는다.** 한 문장에 두 문헌을 달 때, 첫 미주를 만든 뒤 그 미주 내부를 가리키는 run에 두 번째 ctrl을 `append` 하면 미주 안에 미주가 생긴다. 한글은 이를 표현할 수 없어 **파일을 열 때 오류**를 낸다. `.//hp:run`·`.//hp:p`·`.//hp:endNote`가 전부 `subList`를 타고 들어가는 것이 원인이다.

```xml
<!-- 잘못된 결과 -->
<hp:endNote number="36" instId="...80">          <!-- Harrison's -->
  <hp:subList><hp:p><hp:run>
    <hp:ctrl><hp:autoNum num="36" numType="ENDNOTE"/></hp:ctrl>
    <hp:t> Loscalzo J, … Harrison's …; 2022.</hp:t>
    <hp:ctrl><hp:endNote number="1" instId="...81">…KDIGO…</hp:endNote></hp:ctrl>  <!-- ★ -->
  </hp:run></hp:p></hp:subList>
</hp:endNote>
```

**증상 진단**: 중첩된 것의 `instId`가 바깥 것의 **바로 다음 번호**, 안쪽 `autoNum num`이 **바깥과 동일** → deepcopy-후-append 패턴이 확정된다. **`verify.py`·`audit_*` 전부 PASS한다**(well-formed·id 중복 없음). 실사례: 신부전 제7장 미주 36(2026-07-23) → 이후 병합본 3개로 전파, 발견까지 5일.

```python
# 안전한 길 — 문단 수준 형제로만 삽입, 본문 문단인지 가드
uid  = hwpxlib.make_uid(sec)
tmpl = next(e.getparent() for e in sec.iter(f"{P}endNote") if "Naesens" in "".join(e.itertext()))
hwpxlib.add_endnotes(para, "…확립된 합병증으로 다룬다.", tmpl,
                     ["Loscalzo J, … 2022.", "KDIGO … Kidney Int Suppl. 2012;2(1):1-138."], uid)
# 검사: hwpxlib.nested_notes(sec) 는 항상 [] 여야 한다 (verify.py 3d)
```

이미 중첩된 파일을 고칠 때는 **지우지 말고 꺼낸다** — 그 미주는 대개 정상 인용이 자리를 잘못 잡은 것이다. 안쪽 `<hp:ctrl>`을 통째로 떼어 본문 run의 해당 문장 뒤로 옮기고 재번호한 뒤, 본문 텍스트가 한 글자도 안 바뀌었음을 `own()` 비교로 확인한다.

**메모(MEMO)**: 검토 주석이 `fieldBegin type="MEMO" > subList`에 저장됨(⚠️ `<hp:memo>`가 **아니다** — `.//hp:memo`로 찾으면 0개인 흔한 오진). `parameters`에 Author·CreateDateTime, `subList`에 메모 텍스트. `fieldBegin`/`fieldEnd`는 `beginIDRef`로 페어링(다른 단락에 걸칠 수 있음), 제거 시 **양쪽 `<hp:ctrl>` 모두 제거**(걸린 본문 `<hp:t>`는 유지). 본문 추출 시 `own()`으로 제외. → **`hwpxlib.read_memos(sec)`**(id·author·date·text) / **`hwpxlib.delete_memo(sec, memo_id=None)`**(한글 '메모 삭제'와 동일 결과 검증됨). 검토자가 accept한 제안은 tracking·메모 모두 삭제, reject는 메모로 남긴다는 관행에 유의.

**상호참조(CROSSREF) — 같은 문헌을 다시 인용할 때**: 정부·학술 보고서에서 「미주를 쓰되, 앞에 쓴 문헌을 계속 인용해야 하면 본문에 번호만 적는다」를 구현하는 것이 한글의 **상호참조**다. 중복 미주를 만들지 않고 **번호가 대상 미주를 따라간다**.

```xml
<hp:run charPrIDRef="54">                        <!-- 54=위첨자 -->
  <hp:ctrl><hp:fieldBegin id="…" type="CROSSREF" fieldid="…">
    <hp:parameters>
      <hp:stringParam name="Command">?#1153878366;4;1;0;0;</hp:stringParam>
      <hp:stringParam name="RefPath">?#1153878366;</hp:stringParam>   <!-- 대상 endNote instId -->
      <hp:stringParam name="RefType">TARGET_ENDNOTE</hp:stringParam>
      <hp:stringParam name="RefContentType">OBJECT_TYPE_NUMBER</hp:stringParam>
    </hp:parameters></hp:fieldBegin></hp:ctrl>
  <hp:t>3</hp:t>                                  <!-- 캐시된 표시 번호 -->
  <hp:ctrl><hp:fieldEnd beginIDRef="…" fieldid="…"/></hp:ctrl>
  <hp:t>)</hp:t>                                  <!-- 리터럴 괄호(필드 밖) -->
</hp:run>
```

- **한글은 파일을 열 때 번호를 다시 계산한다** — 실측: 미주를 앞에 하나 끼우자 본문 재인용이 `1)2)` → `2)3)`으로 정확히 밀렸다. 그러니 **미주를 중간에 추가해도 안전하다.** 캐시는 한글을 거치지 않는 검사·추출 경로를 위해 `sync_crossref_cache()`로 맞춰 둔다.
- **`RefContentType`이 `OBJECT_TYPE_NUMBER`가 아니면 번호를 따라가지 않는다.** `_PAGE`로 걸린 것을 실제로 만났는데, 그 문서에서는 우연히 맞는 숫자가 찍혀 있다가 번호를 밀자 한쪽만 안 움직였다(`1)2)` → `2)2)`). `Command`의 세 번째 값도 `1`(번호)이어야 한다.
- **필드는 run 경계를 넘는다.** `fieldBegin`이 본문 run 끝에 있고 캐시 `<hp:t>`와 `fieldEnd`가 다음 run에 있는 배치가 흔하다(한글이 서식 경계에서 run을 쪼갠다). run 안에서만 짝을 찾으면 **캐시가 빈 것으로 오진**한다 → `read_crossrefs()`는 문단 단위로 훑는다.
- **연속 인용 두 개가 한 run을 공유**하기도 한다(`[fb][t][fe][t)][fb][t][fe][t)]`). run째 지우면 둘 다 사라진다.
- 한 문단에 미주와 재인용을 함께 달 때는 **번호 순서**를 확인할 것. `add_endnotes()`는 앵커 문구 바로 뒤(=그 run 안)에 넣으므로, 문단 끝에 이미 재인용이 붙어 있으면 새 미주가 그 앞에 놓여 `14)3)`처럼 역순이 된다. 그럴 땐 문단 «맨 끝»에 새 run으로 붙인다.

```python
xrs = hwpxlib.read_crossrefs(sec)          # 무엇이 무엇을 가리키는지
tmpl = hwpxlib.crossref_template(sec)      # 자기완결형 run 하나를 템플릿으로
hwpxlib.add_crossrefs(para, [inst_id], uid, template=tmpl)   # 재인용 붙이기
hwpxlib.sync_crossref_cache(sec)           # 캐시 번호 재계산
```

검사는 **`crossref_check.py FILE.hwpx`** — 페어링·고아 참조·캐시 불일치·`_PAGE` 오설정·**리터럴로 남은 인용번호 후보**를 한 번에 본다. `--baseline BEFORE.hwpx`로 편집 전후의 «미주↔재인용 대응표»를 기계 대조하고, `--fix-cache OUT.hwpx`로 캐시를 맞춘다. `verify.py` 3e가 같은 검사를 하드 게이트로 돌린다.

**변경추적(track change, reviewer 수정)**: 삽입=`<hp:insertBegin Id TcId/>…텍스트…<hp:insertEnd .../>`, 삭제=`<hp:deleteBegin/>…<hp:deleteEnd/>`(빈 마커=문단분리/서식만). 작성자·시각·종류는 **`header.xml`의 `<hp:trackChanges itemCnt><hp:trackChange type="Insert/Delete/CharShape" date author…/>`**. 읽기: **`hwpxlib.read_track_changes(sec)`** → `{"insert":[…],"delete":[…]}`. ⚠️ **수용/거부는 XML로 하지 말 것**(마커+삭제내용 정확 제거가 까다로워 손상 위험) — **한글 COM**으로: `hwp.HAction.Run("TrackChangeApplyAll")`(수용) / `"TrackChangeCancelAll"`(거부). ★ **반환값이 False여도 실제 적용됨** → `insertBegin`/`deleteBegin` 카운트 0으로 검증. COM은 **전 문서 적용**이라 특정 장만 처리하려면 사본에서. (pyhwpx에 `TrackChange*` 메서드군; `IsTrackChange`=추적모드 on/off.)

**스코핑·오타 감사**: 텍스트 매치 편집은 동일 문구가 다른 절에도 있으니 **섹션 범위로 한정**. 띄어쓰기 일괄 정규식(`[가-힣][0-9]` 등) 금지 — 셀·단락 단위 스캔 + 조사(은/는/이/가…)/코드(J코드·N17·IgA신증·KDIGO 등) 화이트리스트로 거짓양성 차단. 실제 오류(어미·단어가 숫자·영문에 직접 붙음, 예 `호소13건`)는 **구체 치환 dict**로 `el.text`·`el.tail` 적용 후 **각 키 적용수>0** 확인. **참고문헌/미주 일관성**(같은 문헌의 대소문자·doi 표기 통일). **항·장 재번호 시 `절N`·`표N`·`그림N` 상호참조가 stale** → 점검하거나 명칭 기반으로 견고화.

---

## §5. 다단 · 목차 · 수식

**다단(colPr)**: **구역 첫 문단**의 `<hp:run>` 안 `secPr` 뒤 `<hp:ctrl><hp:colPr colCount="2" type="NEWSPAPER" sameGap="2268"><hp:colLine/></hp:colPr>`. 단수 변경은 `colCount` 수정. **컬럼폭 초과 표/그림은 `colCount="1"` 구역으로**(§6-D).

**목차(TABLEOFCONTENTS)**: 자동 필드. Command에 `ContentsLevel:2`(수집 수준)·`ContentsLeader:3`(점선)·`ContentsHyperlink:1`. **원천 = 개요 수준 문단**(paraPr: OUTLINE level 0=장, 1=절…). 쪽번호·목차 줄은 손대지 말고 **본문 제목만 개요 수준으로** 넣은 뒤 한글에서 **[도구→차례→차례 새로 고침]**으로 재생성.

**수식(equation)**: 인라인 `<hp:equation>` 안 `<hp:script>`에 **한컴 수식 스크립트**(LaTeX 아님). 새 수식은 **기존 수식 run을 clone → script·id만 교체**.

| 구조 | 스크립트 | 구조 | 스크립트 |
|---|---|---|---|
| 분수 | `{a} over {b}` | 적분 | `int_{하}^{상}{f} dx` |
| 위/아래첨자 | `x^2` / `X_i` | 합 | `sum_{}^{}{ }` |
| 근호 | `sqrt{ }` | 극한 | `lim_{n rarrow INF}{ }` |
| 무한대 | `INF` | 분포~ | `SIM` |
| 평균막대 | `bar{X}` | 자동괄호 | `LEFT( … RIGHT)` |
| 그리스 | `mu sigma pi GAMMA` | 조합 ₙCk | `C_k LSUB {n}` |

- **sz 주의**: clone하면 원본 크기를 상속 → 실제와 안 맞으면 줄 겹침/여백. 높이를 복잡도로 맞추되(분수 2400, 이중분수·적분 2800~3000, 단순 1250) **과하게 키우지 말 것**. 정확 확정은 한글에서 **더블클릭→닫기**.

---

## §6. 페이지·단 관리 (v7 핵심)

### A. 숨은 break 먼저 (최우선)
제목-내용이 갈라지거나 단/페이지가 비면 **keepWithNext/columnBreak 만지기 전에** 그 구간 문단의 `pageBreak`/`columnBreak`를 전수조사. **본문 문단(paraPr=10)에 붙은 `pageBreak="1"`은 대개 원저자 잔재**로 제목과 내용을 강제로 찢는다 → `0`으로 제거.

### B. 제목 고아 방지
① 제목 paraPr(11/12/18)에 **`keepWithNext="1"`**(원본 기본값 0). ② **제목 바로 뒤 빈 문단 금지**(keepWithNext가 빈 문단하고만 붙음). ③ **`columnBreak="1"`로 주요 소제목을 다음 단 맨 위에서 시작**(원저자 컨벤션) — 단 **뒤에 pageBreak가 없고, 제목+내용이 한 단에 들어갈 때만**. 뒤에 큰 표/그림이 있으면 역효과.
> 구조 편집 후엔 **linesegarray를 전면 제거**해야 keepWithNext가 문서 전역에 적용됨(문단별로만 지우면 캐시가 섞여 국소 재조판).

### C. 빈 페이지·빈 단·여백
- 빈 페이지/단은 대개 **섹션·챕터 끝 꼬리 빈 문단**(특히 columnBreak 보유 빈 문단) 때문 → 청소.
- 여백 조정은 **빈 문단 제거 우선**(수식 높이·이미지 크기 건드리기보다 부작용 적음).

### D. 컬럼폭 초과 표 & 섹션 경계 블록 이동
- 폭 > 단폭이면 2단에서 잘림 → **1단 구역(colCount=1)**으로(1단 사용폭 ≈ 페이지폭−좌우여백).
- 문서 순서를 지키려면 블록을 섹션 경계로 이동. **섹션 첫 문단이 secPr를 보유**하므로, 블록을 다른 섹션 앞으로 옮길 땐 **secPr run을 새 첫 문단으로 이전**:
  ```python
  secrun=[r for r in old_first.findall(f'{P}run') if r.find(f'{P}secPr') is not None][0]
  old_first.remove(secrun); moved_block[0].insert(0, secrun)
  ```
  이동 후 **첫 문단 secPr 보유·colCount 유지·이미지 수 일치** 검증. 새 섹션은 매니페스트 `<opf:item>`+spine `<opf:itemref>` 둘 다 등록.

### E. 병합 보고서에서 한 장만 떼어내기 (취합 담당자에게 보낼 때)

여러 사람이 장을 나눠 쓰고 한 사람이 합치는 보고서에서는 **"전체 파일 말고 자기 장만"** 을 요구받는다. 장 = 구역(`secPr`) 하나면 떼어낼 수 있다 — `hwpxlib.extract_section(src, "Contents/sectionN.xml", out, title=...)`.

**떼어내기 전 확인 세 가지** (하나라도 어긋나면 손대지 말 것)
1. 그 장이 **구역 하나**인가 — `len(sec.findall('.//hp:secPr')) == 1`. 장 경계와 구역 경계가 어긋나면 자동 추출이 불가능하다.
2. 본문에 **하드코딩된 표·그림 번호**가 있는가 — `<표 78>는` 같은 평문 참조는 떼어내는 순간 전부 틀린 번호가 된다. `<표 >`(캡션 autoNum)만 있어야 안전하다. 있으면 먼저 `아래 표는` 식 위치 지시어로 바꾼다.
3. 그 장이 참조하는 **BinData** — `binaryItemIDRef` → 파일 매핑은 `header.xml`이 **아니라** `content.hpf`의 manifest에 있다(요즘 한글 파일에는 `<hh:binaryItem>`이 아예 없다). 여기를 헛짚으면 그림이 통째로 빠진다.

`extract_section()`이 함께 고치는 것 — **넷 다 해야 한다**: `header.xml`의 `secCnt`(← 안 고치면 열리는데 **빈 한 쪽**), `content.hpf`의 manifest+spine, `META-INF/container.rdf`, 그리고 안 쓰는 BinData·옛 미리보기 제거.

**떼어내면 번호가 어떻게 되는가 (실측 확인함)**
- 표·그림 캡션 `autoNum`은 **1부터 다시 매겨진다.** "이게 전체에서 78번째 표"는 병합본만 안다. **손으로 채우지 말 것** — 자동번호와 겹쳐 이중 표기가 된다.
- 미주는 `<hp:endNotePr><hp:numbering type="ON_SECTION" newNum="1">` + `placement END_OF_SECTION`이면 구역 단위라 **그대로 살아남는다.**
- 쪽 번호도 1부터 시작한다.

**다시 합치면 복원되는가 — 예. 단 「구역 유지」로 넣어야 한다.**
한글 `InsertFile` 액션에 `KeepSection=1`을 주면 (UI의 「끼워넣기 → 구역 유지」) 붙인 장이 자기 구역을 유지한다. 실측: 160쪽 병합본 끝에 20쪽 단독본을 붙였더니 표가 `<표 93>`~`<표 104>`, 그림이 `<그림 22>`·`<그림 23>`로 **앞에서 이어받고**, 미주는 그 장 안에서 **1)~46)으로 다시 시작**해 장 끝에 붙었다. `secPr`의 `startNum tbl="0" pic="0"`이 "새로 시작하지 않고 이어받음"이라 그렇다.
**구역 유지 없이 본문에 복사·붙여넣기 하면 구역이 합쳐져 미주가 앞 장 번호에 이어져 버린다.** 취합 담당자에게 이 한 줄을 반드시 같이 보낼 것.

**🔴 미주 배치를 먼저 확인할 것 — 장을 떼어내지 않아도 걸린다.** `secPr/endNotePr`의
`<hp:placement place>`가 `END_OF_DOCUMENT`(+ `numbering CONTINUOUS`)면, 그 장을 다른 장과 합치는 순간 **미주가 보고서 맨 끝으로 몰리고 「참고문헌」 표제는 빈 채로 남는다.** 단독으로 열면 표제 바로 뒤에 보여서 멀쩡해 보이고, `verify.py`·`audit_layout.py`도 전부 통과한다 — **합쳐서 렌더해야만 드러난다.**
실사례(2026-07-29 안질환): 표제는 24쪽, 미주 40개는 48~49쪽에 찍혔다. 고치는 것은 두 속성뿐이다.

```python
num.set("type", "ON_SECTION"); num.set("newNum", "1")     # 구역마다 1번부터
pl.set("place", "END_OF_SECTION")                          # 그 구역 끝에
```

그 장의 **마지막 문단이 「참고문헌」 표제**여야 표제와 미주가 맞물린다. 확인 후 바꾼다.

**자동 목차는 별개다.** 정적 텍스트로 만들어진 목차(점선+쪽번호)는 병합해도 갱신되지 않는다. 필드 종류를 먼저 확인하고(`fieldBegin type`), `TABLEOFCONTENTS`가 없으면 취합 담당자가 손으로 맞춰야 한다고 알린다.

**검사기의 지표는 그 문서에만 있는 문자열로.** 두 문서를 합쳐 경계를 판정할 때 뒤 문서의 시작 지표로 흔한 단어를 쓰면 앞 문서에서 먼저 걸려 **고친 뒤에도 FAIL이 난다**(실제로 `아토피피부염`으로 그랬다). 절 표제처럼 유일한 문자열을 쓰고, 고르기 전에 반대쪽에 몇 건 있는지 세라.

**검증은 재병합 렌더로.** 단독본이 혼자 잘 열리는 것은 증거가 아니다 — `scripts/remerge_check.py MASTER.hwpx CHAPTER.hwpx` 가 실제로 끼워 넣고 렌더해 번호를 대조한다.

---

## §7. 검증 체크리스트 (매 빌드)

전부 통과해야 출고:
1. **무손실 자가검증**: `repack_preserve(src,{},out)` → 원본과 바이트 동일.
2. **모든 XML well-formed** — 섹션들 **+ content.hpf**(raw 문자열 편집 시 백슬래시 오염 확인).
3. **id 중복 0** (0/2147483648 sentinel 제외).
4. **linesegarray** 의도대로(신규/편집 문단엔 없음, 또는 전면 제거).
5. **zip 무결성**: `testzip()==None`, **mimetype 첫 엔트리·STORED**.
6. **의미 검증**: pic·tbl·equation·fieldBegin 수, columnBreak/pageBreak 값, secPr 보유 등 기대대로.

> **한계**: LibreOffice는 HWPX 미지원 → 렌더 검증 불가. 대신 위 구조 검증 + 한글에서 실제로 열어 확인(라운드트립)을 요청. 어느 제목이 고아 되는지 등 **렌더 의존 판단은 사용자 피드백으로** 처리.

**부가 검증 — 변경 최소성 diff**: "원본 sectionN.xml 무수정 재직렬화" vs "편집본"을 정규화 후 줄단위 diff해 **의도한 변경만** 있는지 증명(원본이 열리면 편집본도 안전).
```python
import re, difflib
def norm(b): return re.sub('><','>\n<', etree.tostring(etree.fromstring(b), encoding='unicode')).splitlines()
diff=[l for l in difflib.unified_diff(norm(orig), norm(edited), lineterm='') if l[:1] in '+-' and not l.startswith(('+++','---'))]
```

---

## 요약 (한 줄 규칙)

재압축=raw-preserving · 클론=id 중복 제거 · 편집/구조편집=linesegarray 제거(후자는 전면) · 레이아웃 이상=**숨은 break 먼저** · 제목=keepWithNext+뒤 빈문단 금지+(조건부)columnBreak · 여백=빈줄 제거 우선 · 이미지=내용 검증 · content.hpf=XML 파싱 검증 · 넓은 표=1단 구역+secPr 블록 이동 · 서식=기존 정의 재사용(itemCnt) · 목차/수식=한글에서 새로고침/더블클릭으로 확정.
