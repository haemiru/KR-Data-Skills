# 식약처 의약품개요정보(e약은요) — 엔드포인트

> 2026-08-05 실측.

## 경로

```
https://apis.data.go.kr/1471000/DrbEasyDrugInfoService/getDrbEasyDrugList
```

- 기관코드 `1471000` = 식품의약품안전처
- **오퍼레이션이 하나뿐이다.** 목록 조회 겸 상세 조회다
  (`itemSeq`로 좁히면 단건이 나온다)
- **`https://`를 쓴다.** 이 개발기는 포트 80이 막혀 있어 `http://`가 타임아웃 난다

## 활용신청

| 데이터셋 | 포털 URL | 상태 |
|---|---|---|
| 의약품개요정보(e약은요) | <https://www.data.go.kr/data/15075057/openapi.do> | ✅ 신청 완료 (2026-08-05) |

- **개발계정은 자동승인**이다
- 트래픽 **일 10,000건**. 운영계정은 활용사례 등록 후 증액 신청 가능
- **인증키는 계정당 하나지만 활용신청은 데이터셋 단위다.**
  다른 식약처 API를 쓰려면 그 데이터셋을 따로 신청해야 한다

## 경로 검증 — 키 없이 된다

이 포털은 **라우팅이 인증보다 먼저**라, 더미 키로 불러 보면 경로 유효성만 갈라진다.

```bash
uv run skills/mfds-drug-info/scripts/mfds_api.py probe-endpoints
```

실측 결과:

```
✅ 경로 유효   DrbEasyDrugInfoService/getDrbEasyDrugList      (code 30)
❌ 경로 없음   DrbEasyDrugInfoService/getNoSuchOperation      (code 12)
```

- **`code 30`** = 경로는 살아 있고 키만 틀림 → 경로 유효
- **`code 12`** = 그런 오픈API가 없거나 폐기됨 → 경로 무효

## 요청 파라미터

| 이름 | 필수 | 비고 |
|---|---|---|
| `serviceKey` | ✅ | Encoding/Decoding 두 형태가 있다. 래퍼가 자동 판별한다 |
| `type` | — | **사실상 필수.** `json`을 빼면 봉투 모양이 바뀐다 |
| `pageNo` | — | 기본 1. 범위를 넘겨도 에러가 아니라 빈 배열 |
| `numOfRows` | — | 기본 10, **상한 500** |
| 검색 조건 12개 | — | `references/fields.md` §6 |

> 파라미터 이름이 **camelCase**다. 실거래가의 `LAWD_CD` 같은 UPPER_SNAKE가 아니다.

## 에러 코드 실측

| code | HTTP | 메시지 | 뜻 |
|---|---|---|---|
| `00` | 200 | NORMAL SERVICE. | 정상 (**2자리**다. 실거래가는 `000`) |
| `11` | 200 | NO MANDATORY REQUEST PARAMETERS ERROR! | 🔴 **메시지가 원인과 다르다.** 실제로는 `numOfRows`가 500 초과. 뒤에 `numOfRows maximum is =[500]`이 붙는다 |
| `12` | 400 | NO_OPENAPI_SERVICE_ERROR | 경로 없음/폐기 |
| `30` | 403 | SERVICE_KEY_IS_NOT_REGISTERED_ERROR | 키 미등록 **또는 이 데이터셋 미신청** |

에러 봉투는 정상 응답과 형태가 다르다:

```json
{"OpenAPI_ServiceResponse": {"cmmMsgHeader": {
  "errMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
  "returnAuthMsg": "등록되지 않은 서비스키",
  "returnReasonCode": "30"}}}
```

래퍼가 양쪽을 다 해석하고, **에러 메시지에서 인증키 값을 마스킹**한다.

## 🔴 에러가 아닌데 틀린 응답

이 API는 다음을 **전부 `code 00` 정상 응답**으로 돌려준다.
에러 코드로 걸러낼 수 없다는 뜻이다.

| 상황 | 응답 |
|---|---|
| 없는 제품명 | `totalCount 0` |
| 모르는 파라미터 (`bizrno`, 오타 등) | **`totalCount 4775`** — 필터가 통째로 무시된다 |
| `updateDe`가 9자 이상 | `totalCount 0` (실제로는 데이터가 있는데도) |
| `pageNo` 범위 초과 | `items` 빈 배열 |

래퍼가 셋 다 탐지해 경고한다. `fields.md` §3·§6 참조.

## 다른 포털 API와 다른 점

같은 data.go.kr인데 스킬마다 규약이 다르다. **베끼기 전에 확인할 것.**

| | 나라장터 | 실거래가 | **e약은요** |
|---|---|---|---|
| `response` 래퍼 | 있음 | 없음 | **없음** |
| 정상 resultCode | `"00"` | `"000"` | **`"00"`** |
| 파라미터 표기 | camelCase | UPPER_SNAKE | **camelCase** |
| `numOfRows` 상한 | 999 | 1000 | **500** |
| 일 트래픽 | 1,000 | 10,000 | **10,000** |
| 빈 값 | `""` | `" "`(공백) | `null` (`type=json` 기준) |
