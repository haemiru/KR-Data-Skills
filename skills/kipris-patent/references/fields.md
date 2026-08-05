# KIPRISPlus 특허·실용 공개·등록공보 — 필드

> 2026-08-05 실측. 응답은 **XML** 이고 래퍼가 dict/list 로 바꾼다.

## 0. 먼저 알아야 할 것 3가지

1. **요청 파라미터와 응답 필드의 이름이 다르다** — 요청 `applicant` / 응답 `applicantName`
2. **검색 결과는 평평하고, 서지상세는 중첩**이다(`...Array > ...Info`)
3. **호출 한도가 월 1,000회 계정 합산**이라, 표본을 크게 잡을 수 없다.
   아래 채움률은 **표본 100건 기준**이다 — 전수가 아니다

## 1. 검색 결과 필드 (`getAdvancedSearch`) ✅ 실측 16개

표본 100건(`--applicant 삼성전자`) 기준 채움률.

| 필드 | 뜻 | 형식 | 채움률 |
|---|---|---|---|
| `applicationNumber` | 출원번호 | 13자리 숫자 문자열 | 100% |
| `applicationDate` | 출원일 | `YYYYMMDD` | 100% |
| `inventionTitle` | 발명의 명칭 | 문자열 | 100% |
| `registerStatus` | 등록상태 | `등록`/`거절`/`소멸`/`취하` 등 | 100% |
| `applicantName` | 출원인 | 문자열 | 99% |
| `openDate` | 공개일 | `YYYYMMDD` | 99% |
| `registerDate` | 등록일 | `YYYYMMDD` | **43%** |
| `openNumber` | 공개번호 | 숫자 문자열 | — |
| `registerNumber` | 등록번호 | 숫자 문자열 | — |
| `publicationNumber` · `publicationDate` | 공고번호·공고일 | | — |
| `ipcNumber` | IPC | `F02M 61/18\|F02M 45/08` — **`\|` 로 여러 개** | — |
| `astrtCont` | 초록 | 서술형(길다) | — |
| `drawing` · `bigDrawing` | 도면 URL | `fileToss.jsp?arg=...` | — |
| `indexNo` | 결과 내 순번 | 숫자 | — |

> **`registerDate` 가 43% 다.** 출원했으나 등록되지 않은 건(거절·소멸·취하)이
> 많기 때문이다. **비어 있다고 "등록일 정보가 없다"고 하지 말고
> "등록되지 않았다"로 읽어야** 맞는 경우가 대부분이다.

> **`ipcNumber` 는 파이프(`|`)로 여러 코드가 이어진다.** 하나로 취급하면 안 된다.

## 2. 파생 필드 (래퍼가 계산)

`_` 로 시작하는 것은 API 가 준 값이 아니다.

| 필드 | 계산 |
|---|---|
| `_applicationDate` · `_registerDate` · `_openDate` | `YYYYMMDD` → `YYYY-MM-DD` |
| `_registered` | `registerNumber` 가 비어 있지 않으면 `true` |
| `_hasDrawing` | `drawing` 또는 `bigDrawing` 이 있으면 `true` |
| `_truncated` | `--truncate-text` 로 잘린 필드명 배열 |

> ⚠️ `_registered` 는 **등록번호 유무**일 뿐이다. 권리의 현재 유효 여부가 아니다.
> 소멸·무효도 등록번호는 남는다. 정확한 상태는 `registerStatus` 와
> 서지상세의 `legalStatusInfoArray` 를 봐야 한다.

## 3. 서지상세 (`getBibliographyDetailInfoSearch`) ✅ 실측

**중첩 구조다.** 섹션마다 `...Array` 로 감싸고 그 안에 `...Info` 가 들어간다.

출원번호 `1020070112929` 실측 — 15개 섹션 중 **4개가 비어 있었다**:

| 섹션 | 내용 | 이 표본 |
|---|---|---|
| `biblioSummaryInfoArray` | 발명명칭·출원일·등록상태·청구항수·심사관명·최종처분 | ✅ |
| `ipcInfoArray` | `[{ipcDate, ipcNumber}, ...]` — **리스트다** | ✅ |
| `abstractInfoArray` | `astrtCont` | ✅ |
| `claimInfoArray` | 청구항 | ✅ |
| `applicantInfoArray` | 출원인 | ✅ |
| `inventorInfoArray` | 발명자 | ✅ |
| `familyInfoArray` | 패밀리 | ✅ |
| `internationalInfoArray` | 국제출원 | ✅ |
| `priorArtDocumentsInfoArray` | 선행기술문헌 | ✅ |
| `legalStatusInfoArray` | 법적상태 이력 | ✅ |
| `imagePathInfo` | 도면 경로 | ✅ |
| `agentInfoArray` | 대리인 | ❌ 비어 있음 |
| `priorityInfoArray` | 우선권 | ❌ 비어 있음 |
| `designatedStateInfoArray` | 지정국 | ❌ 비어 있음 |
| `rndInfoArray` | 국가연구개발사업 | ❌ 비어 있음 |

> **비어 있는 섹션은 `null` 로 온다.** "그런 정보가 없는 출원"이라는 뜻이지
> API 오류가 아니다. 개인 출원이라 대리인이 없고, 국내 단독 출원이라 우선권·지정국이
> 없는 표본이었다.

> **같은 태그가 여러 번 나오면 래퍼가 리스트로 만든다.** `ipcInfo` 가 1개일 때는
> dict, 2개 이상이면 list 다. **코드에서 둘 다 처리해야 한다.**

## 4. 공개전문 (`getPubFullTextInfoSearch`) ✅ 실측

```json
{"docName": "1020070112929.pdf",
 "path": "http://plus.kipris.or.kr/openapi/fileToss.jsp?arg=<긴 토큰>"}
```

- `path` 가 **`http://`** 다(https 아님). 다운로드할 때 주의
- `totalCount` 가 0 으로 오는데 `item` 은 있다. **건수로 판정하지 말 것**

## 5. 검색 파라미터 ✅ 실측

| 파라미터 | 예 | 결과 |
|---|---|---|
| `inventionTitle` | 자동차 | 124,607 |
| `applicant` | 삼성전자 | 325,135 |
| `astrtCont` | 연료 | 79,333 |
| `ipcNumber` | F02M | 23,739 |
| `applicationNumber` | 1020070112929 | 1 |

### ❌ 먹지 않는 것

| | 결과 |
|---|---|
| `applicantName` | **`code 10`** — 응답 필드명이지 요청 파라미터가 아니다 |
| `docsStart` / `docsCount` | **조용히 무시.** 항상 20건, 첫 행도 동일 |

## 6. 페이지네이션 ✅ 실측

| | |
|---|---|
| `pageNo` | 1-base. page1 ↔ page2 겹침 **0건** |
| `numOfRows` | **500 확인** |

100건 수집 시 고유 출원번호 100개 / 중복 0 — **출원번호가 유일 키로 동작한다**
(나라장터의 `(공고번호, 차수)`, 식약처의 `itemImage` 중복 같은 문제가 여기엔 없다.
단, 표본 100건 기준이다).

## 7. 미확인

| 항목 | 상태 |
|---|---|
| 오퍼레이션 61개 중 56개 | ❌ REST 이름 미확인. 명세서가 내부 ID만 준다 |
| `getAdvancedSearch` 의 나머지 파라미터 | 🟡 5개만 확인. 명세상 항목별검색은 25종이다 |
| `registerStatus` 값 목록 | 🟡 `등록`·`거절`·`소멸`·`취하` 관측. 전체 목록 미확인 |
| 채움률 일반화 | 🟡 표본 100건(출원인 1곳)이라 편향 가능 |
| `numOfRows` 실제 상한 | 🟡 500 까지만 확인. 그 위는 안 봤다 |
| 정렬 기준 | ❌ 미확인. **순서를 믿고 앞부분만 읽지 말 것** |
