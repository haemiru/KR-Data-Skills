# KIPRISPlus 특허·실용 공개·등록공보 — 엔드포인트

> 2026-08-05 실측. **data.go.kr 이 아니다.** 별도 가입·별도 키다.

## 경로

```
https://plus.kipris.or.kr/kipo-api/kipi/patUtiModInfoSearchSevice/<오퍼레이션>
```

- ⚠️ **서비스명에 오타가 있다 — `Sevice`**(`Service` 아님). 원문 그대로 써야 한다
- `https://` 열려 있다. (포트 80도 열려 있지만 https 를 쓴다)
- 포털 명세서에는 요청 주소가 `http://plus.kipris.or.kr/` 까지만 적혀 있다.
  **전체 경로는 실측으로 찾았다**

## 인증

| | |
|---|---|
| 파라미터 이름 | **`ServiceKey`** (대문자 S) |
| 환경변수 | `KIPRIS_PLUS_SERVICE_KEY` |
| 발급 | plus.kipris.or.kr → 데이터 서비스 > 서비스 신청 > Open API → 마이페이지 > API KEY 관리 |

🔴 **`accessKey`·`serviceKey`(소문자 s)는 통하지 않는다.** 셋 다 `code 10` 으로 떨어져
구분이 안 되므로, 이름을 틀리면 원인을 찾기 어렵다.

무료 한도 **월 1,000회 — 계정 전체 상품 합산**이다. 매월 1일 초기화.

## 오퍼레이션 ✅ 실측 확정

**판정 기준은 `resultCode == "00"` 이다**(§ 함정 1 참조).

| 오퍼레이션 | 용도 | 상태 |
|---|---|---|
| `getAdvancedSearch` | **항목별 복합 검색** — 이 스킬의 중심 | ✅ |
| `getBibliographyDetailInfoSearch` | 서지상세 (IPC·초록·국제출원 등 중첩) | ✅ |
| `getBibliographySumryInfoSearch` | 서지요약 | ✅ |
| `getPubFullTextInfoSearch` | 공개전문 PDF 경로 | ✅ |
| `getWordSearch` | 단어 검색 | ✅ 동작하나 **포털에 `폐기예정` 표시** |

> 포털 명세서 기준 이 상품의 오퍼레이션은 **총 61개**다
> (일반검색 2 · 항목별검색 25 · 서지정보 17 · 도면/전문 11 · 부가기능 6).
> 명세서가 내부 ID(`soap_ADI_...`)만 주고 REST 이름을 주지 않아,
> **위 5개만 실호출로 확정했다.** 나머지는 미확인이다.

### 대표도면은 별도 오퍼레이션이 필요 없다

검색 결과 각 행에 `drawing`(썸네일)·`bigDrawing`(대형) URL 이 이미 들어 있다.
`getRepresentativeDrawing*` 계열 이름은 셋 다 실패했다.

## `getAdvancedSearch` 검색 파라미터 ✅ 실측

| 파라미터 | 뜻 | 실측 |
|---|---|---|
| `inventionTitle` | 발명의 명칭 | ✅ `자동차` → 124,607건 |
| `astrtCont` | 초록 | ✅ `연료` → 79,333건 |
| `ipcNumber` | IPC 코드 | ✅ `F02M` → 23,739건 |
| `applicationNumber` | 출원번호 | ✅ 1건 |
| **`applicant`** | **출원인** | ✅ `삼성전자` → 20건/페이지 |
| ~~`applicantName`~~ | — | ❌ **`code 10`**. 응답 필드 이름이지 요청 파라미터가 아니다 |

🔴 **요청 파라미터와 응답 필드의 이름이 다르다.** 응답은 `applicantName` 으로 오는데
요청은 `applicant` 다. 응답 필드명을 그대로 파라미터로 쓰면 `code 10` 이다.

## 페이지네이션 ✅ 실측

| 파라미터 | 동작 |
|---|---|
| `pageNo` | ✅ 1-base. page1 ↔ page2 겹침 **0건** |
| `numOfRows` | ✅ **500 확인**. 요청한 만큼 온다 |
| ~~`docsStart`~~ / ~~`docsCount`~~ | 🔴 **조용히 무시된다.** 무엇을 넣어도 20건, 첫 행도 동일 |

`docsStart`/`docsCount` 는 외부 참고자료에 나오는 이름인데 **이 오퍼레이션에서는
먹지 않는다.** 에러도 안 난다 — 항상 20건이 와서 "원래 20건인가 보다" 하고 넘어가기 쉽다.

## 🔴 함정

### 1. `successYN` 이 거짓말을 한다 — 판정에 쓰면 안 된다

에러인데도 `successYN=Y` 가 온다:

```xml
<successYN>Y</successYN>
<resultCode>10</resultCode>
<resultMsg>INVALID_REQUEST_PARAMETER_ERROR</resultMsg>
```

`applicantName` 을 파라미터로 준 응답이다. **성공 판정은 `resultCode == "00"`
으로만 한다.** 실제로 이 함정 때문에 1차 조사에서 `applicantName` 을
"동작함"으로 잘못 기록했다가 뒤집었다.

### 2. `code 10` 이 모든 실패를 뭉뚱그린다 — 키 없이 경로 검증이 안 된다

대조군 실측. **넷 다 똑같은 응답이다.**

| 보낸 것 | 결과 |
|---|---|
| 없는 서비스명 | `code 10 INVALID_REQUEST_PARAMETER_ERROR` |
| 실서비스 + 없는 오퍼레이션 | `code 10` |
| 인증 파라미터 이름 틀림 | `code 10` |
| 키 아예 없음 | `code 10` |

data.go.kr 계열은 `code 30`(경로 유효·키만 틀림) vs `code 12`(경로 없음)로 갈려서
**키 없이 경로를 검증할 수 있었다. 여기서는 못 한다.**

그래서 이 스킬의 `probe-endpoints` 는 **키를 써서** 실호출로 확인한다.
다른 스킬의 진단 방식을 그대로 옮기면 안 된다.

또한 **오퍼레이션 이름을 추측으로 찾을 수 없다** — 이름이 틀린 건지 파라미터가
틀린 건지 응답으로 구분이 안 된다. `code 00` 이 나와야만 확정이다.

### 3. 응답이 XML 이고 중첩 배열이다

앞선 세 스킬(나라장터·실거래가·식약처)은 전부 JSON 이었다. 여기는 XML 이고,
`getBibliographyDetailInfoSearch` 는 평평한 목록이 아니라 섹션마다
`...Array > ...Info` 로 감싸여 있다:

```
item
 ├ biblioSummaryInfoArray > biblioSummaryInfo   (출원일·등록상태·발명명칭 …)
 ├ ipcInfoArray           > ipcInfo             (ipcDate, ipcNumber)
 ├ abstractInfoArray      > abstractInfo        (astrtCont)
 ├ internationalInfoArray > internationalInfo
 └ familyInfoArray        > …
```

## 다른 스킬과의 비교

| | 나라장터 | 실거래가 | e약은요 | **KIPRISPlus** |
|---|---|---|---|---|
| 포털 | data.go.kr | data.go.kr | data.go.kr | **plus.kipris.or.kr** |
| 인증 변수 | `DATA_GO_KR_SERVICE_KEY` | 〃 | 〃 | **`KIPRIS_PLUS_SERVICE_KEY`** |
| 인증 파라미터 | `serviceKey` | `serviceKey` | `serviceKey` | **`ServiceKey`** |
| 응답 | JSON | JSON | JSON | **XML** |
| 정상 코드 | `00` | `000` | `00` | `00` |
| 페이지 상한 | 999 | 1000 | 500 | 500+ |
| 한도 | 일 1,000 | 일 10,000 | 일 10,000 | **월 1,000 (합산)** |
| 키 없이 경로검증 | ✅ 30/12 | ✅ | ✅ | ❌ **불가** |
