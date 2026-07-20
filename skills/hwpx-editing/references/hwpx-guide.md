# HWPX 편집 가이드 v7

> 한글(HWPX)을 Python/lxml로 안전하게 편집하는 실전 가이드. 모든 항목은 한글 렌더링 또는 바이트 수준으로 **검증된 것**만 담았다.
> **v6→v7**: 다단·목차·수식(§5)과 페이지·단·구조 편집(§6)을 통합. 나머지는 v6의 핵심만 압축.

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
13. **`align=JUSTIFY` + `breakLatinWord="KEEP_WORD"` → 영문 근처 자간이 벌어짐.** 긴 영문 토큰을 줄 끝에서 못 쪼개니 양쪽정렬이 단어 사이 공백을 늘린다. 한글 본문에 영문 용어·서지가 섞이면 눈에 띄게 들쭉날쭉해진다(§4-서식 감사).

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
- **id 중복 제거**: 요소를 deepcopy하면 원본 id를 물려받는다. 클론 후 새 id 발급 + 검증.
  ```python
  def make_uid(root):
      ids={int(v) for el in root.iter() for a in ('id','instId','instid') if (v:=el.get(a)) and str(v).isdigit()}
      c=[max(ids)+5]
      def uid(): c[0]+=2; return c[0]
      return uid
  ```
  미주 클론은 내부 `subList>p`의 id까지, 표 클론은 `tbl`·`tc`·`p` id까지 새로 준다.

---

## §4. 콘텐츠 편집 (단락·표·이미지·서식·메모)

**단락/텍스트**: `<hp:t>.text` 교체. 새 단락은 `paraPrIDRef`(문단 서식)·run `charPrIDRef`(글자 서식)를 **기존 정의에서 골라** 지정. 삭제는 `getparent().remove()`.

**표(tbl)**: `tbl(rowCnt,colCnt,sz.width)` > `tr` > `tc(cellAddr,cellSpan,cellSz,borderFillIDRef) > subList > p > run > t`.
- 셀 클론 시 **`cellSz.height`**=본문 282(헤더 0/282), **각 행 열폭 합 = 표 sz.width**(안 맞으면 거부).
- 헤더 음영은 `borderFillIDRef` 분리(예 헤더 25, 본문 3). 긴 셀은 paraPr JUSTIFY+vertAlign TOP.
- **병합**: 세로(rowSpan)=시작 tc `cellSpan rowSpan=N`, 이후 행은 **가려지는 col의 tc 생략** / 가로(colSpan)=시작 tc `colSpan` 키우고 **가려지는 tc 제거 + 너비 합산**.
- 캡션(표/그림): **텍스트 편집**=`<hp:caption>` 안 마지막 `<hp:t>` 교체. **신규 생성**=`<hp:outMargin>` **직후**에 `<hp:caption side gap width lastWidth fullSz="0">` 삽입(ShapeObject 순서 `sz·pos·outMargin·caption·…` — 표는 caption 뒤 `inMargin·tr`, 그림은 caption 뒤 `shapeComment`). 본문은 **실제 셀 `subList` 복제** → 안의 `<hp:p>` run에 `<hp:t>` 세팅 후 `linesegarray` 제거. **위치**=`side` `TOP/BOTTOM/LEFT/RIGHT`(LEFT/RIGHT는 `width`가 캡션 열폭). **정렬**=캡션 `<hp:p>`의 `paraPrIDRef`(원하는 정렬의 기존 paraPr 재사용; 없으면 새 paraPr 추가 + `itemCnt` 갱신). `autoNum`은 한글 자동 번호. 표 각주는 표 밖 별도 단락(작은 charPr).

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

**메모(MEMO)**: 검토 주석이 `fieldBegin type="MEMO" > subList`에 저장됨 → 본문 추출 시 `own()`으로 제외. `fieldBegin`/`fieldEnd`는 `beginIDRef`로 페어링(다른 단락에 걸칠 수 있음), 제거 시 **양쪽 `<hp:ctrl>` 모두 제거**(걸린 본문 `<hp:t>`는 유지).

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
