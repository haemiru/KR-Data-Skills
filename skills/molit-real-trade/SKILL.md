---
name: molit-real-trade
description: >
  국토교통부 실거래가(RTMS)를 조회한다. 아파트·오피스텔·연립다세대·단독다가구
  매매와 전월세, 토지·상업업무용·공장창고 매매를 지역·기간별로 다룬다.
  "우리 동네 아파트 실거래가", "○○아파트 얼마에 팔렸어", "전세 시세",
  "이 지역 매매가 추이", "상가 실거래가", "토지 거래 얼마나 됐어" 같은
  요청에 사용한다.
---

# 국토교통부 실거래가 (RTMS)

## 사전 조건

1. **`uv`** — `uv` 스킬의 Setup을 따라 `uv`가 설치돼 PATH에 있는지 확인한다.
2. **인증키** — `credentials` 스킬의 프로토콜을 따른다. 필요한 변수는
   `DATA_GO_KR_SERVICE_KEY` 하나다. **작업 시작 전에 먼저 확인할 것**:

   ```bash
   grep -sq "^DATA_GO_KR_SERVICE_KEY=" .env ~/.env
   ```

   실패하면 즉시 멈추고 사용자에게 발급을 안내한다. 스크립트를 먼저 돌리지 말 것.

   > **인증키는 하나지만 활용신청은 데이터셋마다 따로 해야 한다.**
   > 키가 나라장터에서 통한다고 여기서도 통하는 게 아니다.
   > 실거래가는 https://www.data.go.kr/data/15057511/openapi.do 계열에서
   > 활용신청(자동승인)한다. `check-key`로 확인한다.

3. **이용약관 고지** — 워크스페이스 루트에 `.licenses/molit_real_trade_LICENSE.txt`가
   없으면, 이용약관을 확인하도록 사용자에게 고지하고 그 문구와 타임스탬프를
   그 파일에 기록한 뒤 진행한다.

## 핵심 규칙

- **반드시 래퍼를 쓴다.** `curl` 직접 호출 금지. 봉투 해석·금액 파싱·입력 검증이
  전부 래퍼에 있다.
- **`--output`은 필수다.** 응답을 컨텍스트에 쏟지 않는다.
- **호출 예산** — 개발계정 일 1,000건. 이 API는 **월 하나당 최소 1회 호출**이다.
  "최근 2년"이면 24회, 지역 3곳이면 72회다. 범위를 먼저 좁힐 것.
- **인증키 값을 출력하지 않는다.** `cat .env` / `echo $KEY` 금지.
- 이 스킬을 썼으면 결과 보고에 그 사실을 밝힌다.

## 🔴 이 API의 가장 위험한 성질 — 반드시 읽을 것

**잘못된 입력에도 "정상 응답 0건"이 온다.** 2026-08-05 실측:

```
LAWD_CD=99999 (없는 지역)  → resultCode "000", totalCount 0
DEAL_YMD=2026 (형식 오류)  → resultCode "000", totalCount 0
```

에러가 아니다. 그래서 **"그 지역엔 거래가 없습니다"라고 잘못 보고하기 쉽다.**

래퍼가 두 겹으로 막는다:

1. 보내기 전에 형식을 검증한다(지역 5자리 숫자, 조회월 `YYYYMM`)
2. 결과가 0건이면 **경고를 출력**하고 보낸 값을 같이 보여 준다

> **0건 경고가 뜨면 사용자에게 "거래가 없다"고 단정하지 말 것.**
> 지역코드부터 확인한다 — `lawd-code find <지역명>`.

## 명령

전부 `skills/molit-real-trade/` 또는 저장소 루트에서 실행한다.

### 1. 실거래 조회 — `search`

```bash
uv run scripts/molit_api.py search \
  --type apt-trade --region 11110 --months 3 \
  --fields "aptNm,excluUseAr,floor,dealAmount,buildYear,umdNm" \
  --output out/apt.json
```

| 플래그 | 뜻 |
|---|---|
| `--type` | 거래 유형 (아래 표) |
| `--region` | 시군구코드 5자리 또는 **지역명**. 쉼표로 여러 개 |
| `--months N` | 이번 달 포함 최근 N개월 |
| `--from` / `--to` | `YYYYMM` 범위 |
| `--max-months` | 조회월 개수 상한 (기본 24) |
| `--max-calls` | 지역×월 예상 호출 상한 (기본 120) |

지역명으로 바로 된다 (`references/lawd-codes.json` 269개 시군구 동봉):

```bash
uv run scripts/molit_api.py search --type apt-trade --region "청주시" --months 2 --output out/x.json
uv run scripts/molit_api.py search --type apt-trade --region "11110,11140" --months 2 --output out/x.json
```

### 🔴 구가 있는 시는 상위 코드로 조회하면 0건이다

실측(2026-08-05):

```
43110 청주시(상위)   →   0건    ← 에러가 아니다. "거래 없음"으로 오해하게 된다
43111 청주시 상당구  → 173건
43113 청주시 흥덕구  → 342건
```

래퍼가 **자동으로 하위 구를 펼친다.** `--region 청주시`나 `--region 43110`을
주면 4개 구를 모두 조회하고 안내를 출력한다.

대상 13곳 — 수원·성남·안양·부천·안산·고양·용인·화성·청주·천안·포항·창원·전주.

`_meta.count_by_region`에 구별 건수가, 각 행에 `_lawdCd`·`_regionName`이 남아
어느 구에서 온 거래인지 추적된다.

> `--months 1`은 **이번 달만**이다. 월초에는 거의 비어 있다.
> 최근 실거래를 보려면 `--months 2` 이상을 쓰거나 `--from`으로 지난달을 지정한다.

#### 거래 유형

| `--type` | 내용 | 필드 수 | 상태 |
|---|---|---|---|
| `apt-trade` | 아파트 매매 | 32 | ✅ 실측 |
| `apt-rent` | 아파트 전월세 | 25 | ✅ 실측 |
| `offi-trade` / `offi-rent` | 오피스텔 매매 / 전월세 | 18 / 18 | ✅ 실측 |
| `rh-trade` / `rh-rent` | 연립다세대 매매 / 전월세 | 20 / 18 | ✅ 실측 |
| `sh-trade` / `sh-rent` | 단독다가구 매매 / 전월세 | 17 / **15** | ✅ 실측 |
| `land-trade` | 토지 매매 | 16 | ✅ 실측 |
| `nrg-trade` | 상업업무용 매매 | 22 | ✅ 실측 |
| `indu-trade` | 공장창고 매매 | 22 | ✅ 실측 |
| `apt-trade-old` | 아파트 매매(구버전 오퍼레이션) | ? | 경로 생존만. 기본은 `apt-trade` |
| `silv-trade` | 분양권 전매 | ? | ⚠️ **별도 활용신청 필요** (`code 30`) |

> **`sh-rent`(단독다가구 전월세)가 가장 빈약하다** — 층·지번·전용면적·건물명이
> 전부 없다. 위치는 읍면동까지, 규모는 연면적만 나온다. 이걸 모르고
> "몇 층이냐"고 물으면 답이 안 나온다.

### 2. 지역코드 — `lawd-code`

**표가 저장소에 동봉돼 있다**(`references/lawd-codes.json`, 269개 시군구).
그래서 `--region`에 지역명을 바로 쓸 수 있고, 추가 활용신청은 필요 없다.

```bash
uv run scripts/molit_api.py lawd-code find 청주    # 이름·코드로 찾기
```

```
43110  충청북도 청주시
43111  충청북도 청주시 상당구
43112  충청북도 청주시 서원구
43113  충청북도 청주시 흥덕구
43114  충청북도 청주시 청원구
```

표를 다시 받아야 할 때(행정구역 개편 등)만 `fetch`를 쓴다. 이때는
**행정안전부 법정동코드 데이터셋 활용신청이 필요하다**
(https://www.data.go.kr/data/15077871/openapi.do · 자동승인). 22회 호출한다.

```bash
uv run scripts/molit_api.py lawd-code fetch
```

### 3. 진단 — `check-key` / `probe-endpoints`

```bash
uv run scripts/molit_api.py check-key          # 키가 통하는지 (값 출력 안 함)
uv run scripts/molit_api.py probe-endpoints    # 키 없이 경로 생존 확인
```

`probe-endpoints`의 "경로 유효"는 **활용신청 완료를 뜻하지 않는다.**
경로가 살아 있어도 그 데이터셋을 신청 안 했으면 `code 30`이다.

### 4. 탈출구 — `raw`

```bash
uv run scripts/molit_api.py raw \
  --operation RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev \
  --params '{"LAWD_CD":"11110","DEAL_YMD":"202607"}' \
  --output out/raw.json
```

## 🔴 금액 단위 — 자릿수를 반드시 확인할 것

**원본 금액 필드는 만원 단위 + 천단위 콤마 문자열이다.**

```
dealAmount "273,000"    → 27억 3천만원   (27만 3천원이 아니다)
dealAmount "1,740,000"  → 174억
deposit    "1,000"      → 1천만원
monthlyRent "70"        → 70만원
```

래퍼가 **원 단위 파생 필드**를 붙인다. 사용자에게 보고할 땐 이쪽을 쓴다.

| 파생 필드 | 내용 |
|---|---|
| `_dealAmountWon` | 거래금액(원) |
| `_depositWon` / `_monthlyRentWon` | 보증금 / 월세(원) |
| `_preDepositWon` / `_preMonthlyRentWon` | 직전 계약 보증금 / 월세(원) |
| `_name` | 건물명 (유형마다 필드명이 달라 통일한 것) |
| `_area` / `_areaField` | 대표 면적 + 그게 어느 필드였는지 |
| `_dealDate` | `YYYY-MM-DD` 계약일 |
| `_dealYm` | 그 행이 어느 조회월에서 왔는지 |
| `_cancelled` / `_cancelledDate` | **해제된 거래인지** / 해제일 |
| `_lawdCd` / `_regionName` | 어느 시군구에서 온 거래인지 |

> `_` 로 시작하는 것은 **래퍼가 계산한 값**이다. API가 준 값이 아니다.
> `--fields`로 걸러도 파생 필드는 항상 남는다.

## 🔴 해제된 거래를 빼야 한다

실측: 표본 2,900건 중 **71건(2.45%)이 해제된 거래**다(`cdealType == "O"`).

**시세·평균가·최고가를 낼 때 반드시 빼야 한다.** 2.45%면 무시할 수 없고,
최고가는 한 건만 섞여도 답이 바뀐다.

```bash
uv run scripts/molit_api.py search --type apt-trade --region 43113 \
  --from 202607 --to 202607 --exclude-cancelled --output out/x.json
#   해제 거래 12건을 제외했다 (--exclude-cancelled).
```

**기본은 포함**이다 — 데이터를 조용히 버리지 않기 위해서. 대신 해제 건이
있으면 경고를 출력하고 `_cancelled` / `_cancelledDate` 를 붙인다.
`_meta.cancelled_count` 로도 확인할 수 있다.

## 유형마다 필드가 다르다

같은 개념인데 이름이 다르다. `_name` / `_area`를 쓰면 신경 안 써도 된다.

| 개념 | 아파트 | 오피스텔 | 연립다세대 | 단독다가구 | 토지 | 상업업무용 |
|---|---|---|---|---|---|---|
| 건물명 | `aptNm` | `offiNm` | `mhouseNm` | — | — | — |
| 면적 | `excluUseAr` | `excluUseAr` | `excluUseAr` | `totalFloorAr` | `dealArea` | `buildingAr` |

필드 개수도 다르다 — 아파트 매매 32 · 아파트 전월세 25 · 상업 22 ·
연립 20 · 오피스텔 18 · 단독 17 · 토지 16개.

> ⚠️ **아파트 매매는 `roadNm`, 전월세는 `roadnm`** — 같은 개념인데 대소문자가
> 다르다(실측). `roadNmBonbun` vs `roadnmbonbun` 식으로 도로명 계열 전체가 그렇다.
> `--fields`에 잘못 쓰면 조용히 빠진다.

## 출력 형식

```json
{
  "_meta": {
    "operation": "RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev",
    "type": "apt-trade", "type_label": "아파트 매매",
    "lawd_cd": "11110",
    "months": ["202607", "202608"],
    "count_by_month": { "202607": 29, "202608": 0 },
    "api_calls": 2, "total_count": 29, "returned": 29,
    "truncated": false
  },
  "items": [ { "aptNm": "...", "_dealAmountWon": 2730000000, "_dealDate": "2026-07-23" } ]
}
```

`count_by_month`로 **어느 달이 비었는지** 바로 보인다. 월 전체가 0이면
그 달 데이터가 아직 안 올라온 것일 수 있다(신고 기한이 있다).

## 자주 밟는 함정

| 증상 | 원인 | 해법 |
|---|---|---|
| 0건인데 이상하다 | 지역코드·조회월이 틀려도 0건이 온다 | `lawd-code find`로 코드 확인. 래퍼 경고를 읽을 것 |
| 큰 도시인데 0건 | **구가 있는 시의 상위 코드**를 썼다 | 래퍼가 자동 확장한다. 직접 코드를 넣었다면 하위 구 코드로 |
| `code 30`인데 키는 맞음 | **그 데이터셋 활용신청을 안 했다** | 해당 데이터셋에서 활용신청. 키 문제가 아니다 |
| 금액이 이상하게 작다 | 원본이 만원 단위 | `_dealAmountWon` 사용 |
| `--fields`에 넣은 필드가 없다 | 유형마다 필드가 다름·대소문자 상이 | 위 표 확인. `_name`/`_area` 사용 |
| 이번 달이 0건 | 월초라 아직 신고분이 없음 | `--months 2` 이상 |
| 호출이 너무 많다 | 월마다 1회 이상 | 범위를 좁히거나 `--max-months` 확인 |
| 지번이 `1**`, `산1*` | 개인정보 마스킹 | 원본이 그렇다. 정확한 지번은 안 준다 |

## 참고

- 오퍼레이션 13개 실측 맵: `references/endpoints.md`
- 응답 필드: `references/fields.md`
- 실측 원본: `references/endpoint-probe.json`
