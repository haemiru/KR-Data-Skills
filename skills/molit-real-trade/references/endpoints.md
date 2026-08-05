# 오퍼레이션 맵 — 국토교통부 실거래가(RTMS)

**베이스 URL**

```
https://apis.data.go.kr/1613000
```

> 포털 예제는 `http://`로 적혀 있지만 환경에 따라 포트 80이 막힌다.
> 래퍼는 `https://`로 고정돼 있다.

## 어떻게 확인했나 (실측 · 2026-08-05)

data.go.kr은 **라우팅이 인증보다 먼저** 일어난다. 더미 키로 호출하면
응답이 두 갈래로 갈린다.

| 응답 | 뜻 |
|---|---|
| HTTP 403 · `returnReasonCode: 30` | **경로 유효.** 인증까지 도달했고 키만 틀림 |
| HTTP 400 · `returnReasonCode: 12` | **그런 경로 없음** |

재현:

```bash
uv run scripts/molit_api.py probe-endpoints --output references/endpoint-probe.json
```

## 🔴 "경로 유효" ≠ "쓸 수 있음"

**포털 인증키는 계정당 하나지만, 활용신청은 데이터셋마다 따로 한다.**

프로빙은 경로 존재만 알려 준다. 그 데이터셋을 신청하지 않았으면
**실제 키로도 `code 30`** 이 나온다. 실측 예:

- `RTMSDataSvcSilvTrade` — 프로빙 `code 30`(경로 유효), 실제 키로도 `code 30`
  → 이 계정이 **분양권 전매 데이터셋을 신청하지 않았다**
- 나머지 12개 — 실제 키로 `resultCode 000` 정상

즉 `code 30`은 "키가 틀렸다"가 아니라 **"이 키로 이 데이터셋을 못 쓴다"** 이다.
키를 의심하기 전에 활용신청 목록을 볼 것.

## 생존 확인된 오퍼레이션 13개

### 매매

| 오퍼레이션 | 내용 | `--type` |
|---|---|---|
| `RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev` | 아파트 매매 | `apt-trade` |
| `RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade` | 아파트 매매(구버전) | `apt-trade-old` |
| `RTMSDataSvcOffiTrade/getRTMSDataSvcOffiTrade` | 오피스텔 매매 | `offi-trade` |
| `RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade` | 연립다세대 매매 | `rh-trade` |
| `RTMSDataSvcSHTrade/getRTMSDataSvcSHTrade` | 단독다가구 매매 | `sh-trade` |
| `RTMSDataSvcLandTrade/getRTMSDataSvcLandTrade` | 토지 매매 | `land-trade` |
| `RTMSDataSvcNrgTrade/getRTMSDataSvcNrgTrade` | 상업업무용 매매 | `nrg-trade` |
| `RTMSDataSvcInduTrade/getRTMSDataSvcInduTrade` | 공장창고 매매 | `indu-trade` |
| `RTMSDataSvcSilvTrade/getRTMSDataSvcSilvTrade` | 분양권 전매 | `silv-trade` ⚠️ 미신청 |

### 전월세

| 오퍼레이션 | 내용 | `--type` |
|---|---|---|
| `RTMSDataSvcAptRent/getRTMSDataSvcAptRent` | 아파트 전월세 | `apt-rent` |
| `RTMSDataSvcOffiRent/getRTMSDataSvcOffiRent` | 오피스텔 전월세 | `offi-rent` |
| `RTMSDataSvcRHRent/getRTMSDataSvcRHRent` | 연립다세대 전월세 | `rh-rent` |
| `RTMSDataSvcSHRent/getRTMSDataSvcSHRent` | 단독다가구 전월세 | `sh-rent` |

`AptTradeDev`와 `AptTrade`가 **둘 다 살아 있다.** 래퍼 기본값은
필드가 더 많은 `AptTradeDev`(32개)다.

## 요청 파라미터

**나라장터와 달리 대문자 스네이크다.** 소문자로 보내면 무시되고 0건이 온다.

| 파라미터 | 필수 | 설명 |
|---|---|---|
| `serviceKey` | ✅ | 인증키. 래퍼가 Encoding/Decoding을 자동 판별 |
| `LAWD_CD` | ✅ | **시군구코드 5자리**(법정동코드 앞 5자리). 예: `11110` |
| `DEAL_YMD` | ✅ | **조회월 `YYYYMM`**. 기간 조회가 없다 — 월 하나씩 |
| `pageNo` / `numOfRows` | | 페이지 / 페이지당 건수 |
| `type` | | `json`. 안 주면 XML이 온다 |

### 🔴 잘못된 값도 에러가 아니다

```
LAWD_CD=99999 → {"header":{"resultCode":"000","resultMsg":"OK"},
                 "body":{"items":"","numOfRows":"3","pageNo":"1","totalCount":"0"}}
DEAL_YMD=2026 → 위와 동일
```

**"데이터 없음"과 "잘못 물어봄"을 응답으로 구분할 수 없다.**
래퍼가 보내기 전에 형식을 검증하고, 0건이면 경고를 출력하는 이유다.

## 응답 봉투 — 나라장터와 다르다

```json
{
  "header": { "resultCode": "000", "resultMsg": "OK" },
  "body": { "items": { "item": [ ... ] },
            "numOfRows": "3", "pageNo": "1", "totalCount": "29" }
}
```

| | 나라장터(G2B) | 실거래가(RTMS) |
|---|---|---|
| 최상위 | `{"response": {...}}` 래퍼 있음 | **래퍼 없음.** 바로 `header`/`body` |
| 정상 코드 | `"00"` (2자리) | **`"000"` (3자리)** |
| 파라미터 | camelCase (`inqryDiv`) | **UPPER_SNAKE (`LAWD_CD`)** |
| 기간 조회 | 시작~종료 지원 | **없음.** 월 하나씩 |
| 빈 값 | `""` | **`" "` (공백 한 칸)** |
| 0건일 때 `items` | `""` 또는 `null` | `""` |

인증 에러 봉투는 양쪽이 같다:

```json
{ "OpenAPI_ServiceResponse": { "cmmMsgHeader": {
    "errMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
    "returnAuthMsg": "등록되지 않은 서비스키",
    "returnReasonCode": "30" } } }
```

## 에러 코드

| 코드 | 의미 | 대응 |
|---|---|---|
| `12` | NO_OPENAPI_SERVICE_ERROR | 경로/오퍼레이션명 오류 |
| `20` | 서비스 접근 거부 | 활용신청 상태 확인 |
| `22` | 트래픽 초과 | 개발계정 일 1,000건 |
| `30` | 등록되지 않은 서비스키 | **키 오류가 아니라 데이터셋 미신청일 가능성이 높다** |
| `31` | 활용기간 만료 | 연장 신청 |
| `32` | 등록되지 않은 IP | 포털에서 IP 등록 확인 |

## 호출 예산

기간 조회가 없어서 **조회월 하나당 최소 1회**다.

```
지역 1곳 × 최근 12개월           = 12회
지역 3곳 × 최근 12개월           = 36회
지역 1곳 × 5년(60개월)           = 60회
```

개발계정 일 1,000건 기준으로 금방 찬다. 래퍼의 `--max-months`(기본 24)가
사고를 막는 안전장치다.
