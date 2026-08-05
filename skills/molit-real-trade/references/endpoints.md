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

실측 예 — `RTMSDataSvcSilvTrade`(분양권 전매)는 프로빙에서 `code 30`(경로 유효)이
나왔는데 **실제 키로도 `code 30`** 이었다. 키가 틀린 게 아니라 그 데이터셋을
신청하지 않았던 것이다. 신청 후에는 `resultCode 000` 으로 정상 동작했다.

즉 `code 30`은 "키가 틀렸다"가 아니라 **"이 키로 이 데이터셋을 못 쓴다"** 이다.
키를 의심하기 전에 활용신청 목록을 볼 것.

### 활용신청 URL (확인된 것)

전부 **자동승인**이라 신청 즉시 쓸 수 있다. 개발계정 트래픽은 **일 10,000건**
(나라장터 1,000건과 다르다 — 2026-08-05 포털에서 확인).

| 데이터셋 | `--type` | 활용신청 |
|---|---|---|
| 아파트 매매 실거래가 **상세** | `apt-trade` | https://www.data.go.kr/data/15126468/openapi.do |
| 아파트 매매 실거래가 | `apt-trade-old` | https://www.data.go.kr/data/15126469/openapi.do |
| 아파트 전월세 실거래가 | `apt-rent` | https://www.data.go.kr/data/15126474/openapi.do |
| **아파트 분양권전매 실거래가** | `silv-trade` | https://www.data.go.kr/data/15126471/openapi.do |
| 오피스텔 매매 실거래가 | `offi-trade` | https://www.data.go.kr/data/15126464/openapi.do |
| 단독/다가구 매매 실거래가 | `sh-trade` | https://www.data.go.kr/data/15126465/openapi.do |
| 단독/다가구 전월세 실거래가 | `sh-rent` | https://www.data.go.kr/data/15126472/openapi.do |
| 토지 매매 실거래가 | `land-trade` | https://www.data.go.kr/data/15126466/openapi.do |
| 상업업무용 부동산 매매 실거래가 | `nrg-trade` | https://www.data.go.kr/data/15126463/openapi.do |

> 오피스텔 전월세 · 연립다세대 매매/전월세 · 공장창고는 **데이터셋 번호를
> 확인하지 못했다.** 포털에서 "실거래가"로 검색하면 나온다. 추측한 번호를
> 적어 두면 헛걸음하게 되므로 비워 둔다.
>
> 구 데이터셋 번호 `15056782`(분양권전매)는 **404**다. 폐기됐다.
> 검색 결과에 아직 걸리므로 주의할 것.

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
| `RTMSDataSvcSilvTrade/getRTMSDataSvcSilvTrade` | 분양권 전매 | `silv-trade` |

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

### 🔴 구가 있는 시의 상위 코드는 0건이다

법정동코드 표에는 통합시의 상위 코드와 하위 구가 **둘 다** 있다.
그런데 실거래가 API는 **구 단위로만** 데이터를 준다. 실측(2026-08-05):

| 코드 | 지역 | 202607 아파트 매매 |
|---|---|---|
| `43110` | 충청북도 청주시 | **0건** |
| `43111` | 청주시 상당구 | 173건 |
| `43112` | 청주시 서원구 | 188건 |
| `43113` | 청주시 흥덕구 | 342건 |
| `43114` | 청주시 청원구 | 194건 |

표에 있는 코드라서 형식 검증도 통과하고, 응답도 에러가 아니다.
**"청주시에 거래가 없습니다"라는 오답이 나오기 딱 좋은 자리다.**

대상 13곳 — 수원(41110) · 성남(41130) · 안양(41170) · 부천(41190) ·
안산(41270) · 고양(41280) · 용인(41460) · 화성(41590) · 청주(43110) ·
천안(44130) · 포항(47110) · 창원(48120) · 전주(52110).

래퍼가 `_children_of()` 로 자동 확장한다.

## 지역코드 표 — `references/lawd-codes.json`

행정안전부 행정표준코드(법정동코드) API에서 받은 **269개 시군구**.
전체 20,560행 중 `umd_cd == "000"` · `ri_cd == "00"` · `sgg_cd != "000"` 인
행만 남긴 것이다.

> 접미사 문자열로 거르면 안 된다. `"2720000000"`(대구 남구)이
> `endswith("0000000")` 에 걸려 빠진다. 실제로 처음에 그렇게 짰다가 놓쳤다.

재현(해당 데이터셋 활용신청 필요 · 자동승인 · 22회 호출):

```bash
uv run scripts/molit_api.py lawd-code fetch
```

시도 분포 — 경기 55 · 전남광주통합특별시 27 · 서울 25 · 경북 24 · 경남 23 ·
강원 18 · 충남 17 · 부산 16 · 전북 16 · 충북 15 · 인천 11 · 대구 9 ·
대전 5 · 울산 5 · 제주 2 · 세종 1.

> 자료에 **`전남광주통합특별시`** 가 있다(광주광역시·전라남도가 별도로 없다).
> 행정구역 개편이 반영된 최신 자료다. 실거래가 API도 이 코드를 받는다 —
> `12110`(목포시) 180건, `12130`(여수시) 139건으로 실측 확인했다.

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
| `22` | 트래픽 초과 | **개발계정 일 10,000건**(실거래가 계열. 나라장터는 1,000건이라 다르다) |
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

개발계정 일 10,000건 기준으로도 지역을 여럿 잡으면 금방 찬다.
래퍼의 `--max-months`(기본 24)와 `--max-calls`(기본 120)가
사고를 막는 안전장치다.
