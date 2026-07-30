# corpus — 골든 파일 회귀

```bash
python corpus/run_corpus.py            # 검사 (CI 게이트)
python corpus/run_corpus.py --update   # 골든 재생성
python corpus/run_corpus.py --only 001-delete-row
```

`selftest.py`가 **원시동작이 맞는가**를 본다면, 여기는 **출력이 달라지지 않았는가**를 본다.
헬퍼를 고쳤을 때 의도한 케이스의 골든만 바뀌어야 한다. 손대지 않은 케이스가 같이 바뀌면
그게 회귀다.

## 어떻게 되어 있나

| 파일 | 역할 |
|---|---|
| `fixture.py` | 원본 문서를 **코드로** 만든다 — 표 기하·미주·2개 구역을 갖춘 문서 |
| `cases.py` | 케이스 목록. 각각 헬퍼 하나를 그 문서에 적용한다 |
| `run_corpus.py` | 실행·비교·`--update` |
| `golden/*.txt` | 커밋된 기대 출력 |

**실제 문서는 커밋하지 않는다.** 원본을 코드로 생성하므로 저장소에 문서 내용이 들어갈 일이
없고, 어느 기기에서도 같은 입력이 나온다.

## 왜 바이트가 아니라 구조를 비교하나

바뀐 엔트리는 다시 deflate되고, deflate 출력은 zlib 버전에 따라 다르다 — 개발은 Windows,
CI는 ubuntu다. 바이트로 비교하면 코드가 멀쩡해도 CI가 빨개진다. 그래서 골든에 담는 것은:

- 어떤 엔트리가 **바뀌었고 / 추가됐고 / 빠졌는가**
- 안 바뀐 엔트리가 **바이트째 동일한가** — 이건 byte-copy라 결정적이므로 그대로 비교한다
- `verify.py` 하드체크 결과
- 구조 카운트(`p`/`tbl`/`lineseg`), `rowCnt`·`secCnt` 정합, 중첩 주석 수
- §7 최소변경 diff — 사람이 읽고 검토할 수 있는 형태

## 케이스 추가하기

1. `cases.py`에 함수를 쓰고 `CASES`에 한 줄 추가
2. `python corpus/run_corpus.py --update`
3. **생성된 골든을 읽는다.** 이게 이 도구의 전부다 — 골든이 틀린 동작을 박제하면
   없느니만 못하다. 그 diff가 의도한 변경인지 확인하고 커밋한다.

## 지금 잠겨 있는 것

| 케이스 | 무엇을 고정하나 |
|---|---|
| `001-delete-row` | 행 삭제가 `rowCnt`·표 높이·아래 행들의 `rowAddr`를 함께 고친다 |
| `002-widen-column` | 열 폭을 옮겨도 모든 행의 합계가 표 폭과 같다 |
| `003-edit-cell` | 셀을 고치면 그 문단의 `linesegarray`가 사라진다 |
| `004-add-two-endnotes` | 한 앵커의 미주 둘이 **형제**로 붙는다 (서로 안에 들어가면 한글이 못 연다) |
| `005-extract-section` | 구역을 떼면 `secCnt`·manifest·spine·`container.rdf`가 같이 고쳐지고, 남긴 구역은 **바이트째 그대로**다 |
