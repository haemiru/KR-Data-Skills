---
name: kipris-patent
description: >
  KIPRISPlus로 한국 특허·실용신안 공개·등록공보를 조회한다. 발명의 명칭·출원인·
  IPC 코드·초록으로 검색하고, 출원번호로 서지상세(청구항·발명자·IPC·법적상태)와
  공개전문 PDF 경로를 가져온다. "삼성전자 특허 찾아줘", "이 기술 관련 특허 있어?",
  "출원번호 1020070112929 어떤 특허야", "경쟁사 특허 동향", "IPC F02M 특허" 같은
  요청에 사용한다.
---

# KIPRISPlus 특허·실용 공개·등록공보

## 🔴 먼저 — 이 스킬은 data.go.kr 이 아니다

**인증 경로가 다르다.** 다른 스킬이 쓰는 `DATA_GO_KR_SERVICE_KEY` 로는 호출되지 않는다.

- 필요한 변수는 **`KIPRIS_PLUS_SERVICE_KEY`** 하나다
- 공공데이터포털의 KIPRISPlus 데이터셋은 `API 유형 = LINK` 라 **포털에서 활용신청을
  할 수 없다.** `바로가기` 버튼만 있다
- 발급: `plus.kipris.or.kr` 회원가입 → `데이터 서비스 > 서비스 신청 > Open API`
  → 장바구니에서 **`유/무료 선택`을 `무료`로 바꾼다**(기본값이 유료다)
  → `마이페이지 > API KEY 관리`

## 🔴 호출 예산 — 이 스킬의 가장 큰 제약

**무료 한도가 월 1,000회이고, 계정에 등록한 전체 상품 합산이다.** 매월 1일 초기화.

다른 스킬(일 10,000회)과 자릿수가 다르다. 그래서:

- 래퍼의 `--max-calls` 기본값이 **20** 이다. 일부러 낮게 잡았다
- 실행할 때마다 쓴 횟수를 출력한다
- **탐색적으로 여러 번 던지지 말 것.** 조건을 먼저 좁히고 한 번에 조회한다
- `probe-endpoints` 는 **5회를 쓴다**(무인증 검증이 불가능해서. 아래 참조).
  필요할 때만 돌린다

## 사전 조건

1. **`uv`** — `uv` 스킬의 Setup을 따른다.
2. **인증키** — `credentials` 스킬의 프로토콜을 따른다. **작업 시작 전에 확인할 것**:

   ```bash
   grep -sq "^KIPRIS_PLUS_SERVICE_KEY=" .env ~/.claude/.env ~/.env
   ```

   실패하면 즉시 멈추고 위 발급 절차를 안내한다.

3. **이용약관 고지** — 워크스페이스 루트에 `.licenses/kipris_patent_LICENSE.txt`가
   없으면, 이용약관을 확인하도록 고지하고 그 문구와 타임스탬프를 기록한 뒤 진행한다.

## 핵심 규칙

- **반드시 래퍼를 쓴다.** XML 파싱·중첩 배열 해석·에러 판정이 전부 래퍼에 있다.
- **`--output`은 필수다.**
- **인증키 값을 출력하지 않는다.**
- 이 스킬을 썼으면 결과 보고에 그 사실을 밝힌다.

## 명령

```bash
S=skills/kipris-patent/scripts/kipris_api.py

uv run $S check-key                       # 키 확인 (호출 1회)

# 검색 — 조건은 조합된다(AND)
uv run $S search --applicant 삼성전자 --preset brief --output out/s.json
uv run $S search --title 자동차 --ipc F02M --output out/t.json
uv run $S search --abstract 연료전지 --preset core --truncate-text 300 --output out/a.json

# 출원번호로 상세
uv run $S detail --app-no 1020070112929 --kind detail   --output out/d.json  # 서지상세
uv run $S detail --app-no 1020070112929 --kind summary  --output out/m.json  # 서지요약
uv run $S detail --app-no 1020070112929 --kind fulltext --output out/f.json  # 공개전문 PDF

uv run $S probe-endpoints                 # ⚠ 호출 5회
```

### 검색 조건

| 플래그 | API 파라미터 | 실측 |
|---|---|---|
| `--title` | `inventionTitle` | `자동차` → 124,607건 |
| `--applicant` | **`applicant`** | `삼성전자` → 325,135건 |
| `--ipc` | `ipcNumber` | `F02M` → 23,739건 |
| `--abstract` | `astrtCont` | `연료` → 79,333건 |
| `--app-no` | `applicationNumber` | 정확일치 |

### 필드 묶음

| preset | 필드 수 | 용도 |
|---|---|---|
| `brief` | 5 | 목록 |
| `core` (기본) | 9 | 초록 포함 |
| `full` | 16 | 도면 URL까지 전부 |

## 🔴 함정 — 실측으로 확인된 것들

### 1. `successYN` 이 거짓말을 한다

```xml
<successYN>Y</successYN>
<resultCode>10</resultCode>
<resultMsg>INVALID_REQUEST_PARAMETER_ERROR</resultMsg>
```

**에러인데 `successYN=Y` 다.** 판정은 **`resultCode == "00"`** 으로만 한다.
래퍼가 그렇게 한다. `raw` 응답을 직접 볼 일이 있으면 이 점을 기억할 것.

### 2. `code 10` 이 모든 실패를 뭉뚱그린다 — 키 없이 경로 검증이 안 된다

없는 서비스명 · 없는 오퍼레이션 · 인증 파라미터 이름 오류 · 키 없음
→ **넷 다 똑같이 `code 10`** 이다.

data.go.kr 계열은 `code 30`(경로 유효) vs `code 12`(경로 없음)로 갈려서 키 없이
경로를 검증할 수 있었다. **여기서는 못 한다.** 그래서 이 스킬의 `probe-endpoints`
는 실호출이고 무료 한도를 쓴다.

**`code 10` 이 나오면** 파라미터 이름 → 오퍼레이션 이름 → 인증 파라미터 순으로 의심한다.

### 3. 요청 파라미터와 응답 필드의 이름이 다르다

| 요청 | 응답 |
|---|---|
| `applicant` | `applicantName` |

응답에 보이는 `applicantName` 을 그대로 파라미터로 쓰면 **`code 10`** 이다.
래퍼가 화이트리스트로 막는다.

### 4. `docsStart` / `docsCount` 는 조용히 무시된다

외부 문서에 이 이름이 나오는데 **이 오퍼레이션에서는 먹지 않는다.**
에러도 안 나고 **항상 20건**이 온다. 올바른 이름은 **`pageNo` / `numOfRows`** 다
(500건 확인, 페이지 간 중복 0).

### 5. 서비스 경로에 오타가 있다

```
patUtiModInfoSearchSevice     ← Service 가 아니라 Sevice 다. 원문 그대로 쓴다
```

### 6. 응답이 XML 이고 서지상세는 중첩이다

```
item
 ├ biblioSummaryInfoArray > biblioSummaryInfo   발명명칭·출원일·등록상태·청구항수
 ├ ipcInfoArray           > ipcInfo             [{ipcDate, ipcNumber}, ...]
 ├ claimInfoArray · applicantInfoArray · inventorInfoArray
 ├ agentInfoArray · priorityInfoArray · legalStatusInfoArray
 └ imagePathInfo · rndInfoArray · familyInfoArray
```

래퍼가 dict/list 로 변환한다. 같은 태그가 여러 번 나오면 리스트가 된다.

### 7. 오퍼레이션 61개 중 5개만 확인됐다

포털 명세서가 REST 이름을 주지 않고 내부 ID(`soap_ADI_...`)만 준다.
**추측으로 찾을 수 없다** — `code 10` 으로는 이름 오류와 파라미터 오류가 구분되지 않는다.

확인된 것만 쓴다. 나머지 56개는 `references/endpoints.md` 에 미확인으로 적어 뒀다.
**"이 오퍼레이션은 없다"고 단정하지 말 것.** 확인을 못 한 것뿐이다.

## 사용자에게 답할 때

- **등록 여부를 단정하지 말 것.** `registerStatus` 는 `등록`·`거절`·`소멸`·`취하`
  등으로 오고, `_registered` 는 등록번호 유무일 뿐이다
- 검색 건수가 크면(수만~수십만) **그대로 읽지 말고** 조건을 좁히도록 안내한다
- 잘림 경고가 떴으면 그 사실을 그대로 전한다
- 특허 침해·권리범위 판단은 **변리사 영역**이다. 조회 결과로 단정하지 않는다

## 참고

- 포털: <https://plus.kipris.or.kr>
- 엔드포인트·에러코드: `references/endpoints.md`
- 응답 필드: `references/fields.md`
