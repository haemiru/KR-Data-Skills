# 응답 필드 — 나라장터 입찰공고정보서비스

> [!WARNING]
> **이 문서의 검증 상태를 먼저 읽을 것.**
>
> - **봉투 구조(§1, §2)** — ✅ 실측 확인. 에러 봉투는 직접 응답을 받아 확인했고,
>   정상 봉투는 공공데이터포털 공통 규격이다.
> - **항목(item) 필드명(§3)** — ⚠️ **미검증.** 인증키가 없어 정상 응답을 아직 한 번도
>   못 받았다. 아래 목록은 공식 명세(docx)와 통용되는 예제에서 모은 것이며
>   **오타·누락·실제 부재 가능성이 있다.**
>
> 키가 준비되면 §4의 명령 하나로 실제 필드명을 확정하고 이 문서를 덮어쓸 것.
> 그때까지 필드명을 사용자에게 사실로 단정해 보고하지 말 것.

## 1. 정상 응답 봉투 ✅

```json
{
  "response": {
    "header": { "resultCode": "00", "resultMsg": "NORMAL SERVICE." },
    "body": {
      "items": [ { "...": "..." } ],
      "numOfRows": 100,
      "pageNo": 1,
      "totalCount": 412
    }
  }
}
```

`items`는 상황에 따라 형태가 흔들린다. 래퍼의 `extract_items()`가 아래를 모두
`list[dict]`로 정규화한다.

| 실제로 오는 형태 | 언제 |
|---|---|
| `[{...}, {...}]` | 일반적인 JSON 응답 |
| `{"item": [{...}]}` | XML→JSON 변환 경로 |
| `{"item": {...}}` | 결과가 1건일 때 |
| `""` 또는 `null` | 결과가 0건일 때 |

**0건과 에러를 구분할 것.** 0건은 `resultCode: "00"` + 빈 `items`다.

## 2. 에러 봉투 ✅

인증 계열 에러는 `type=json`을 줘도 **다른 봉투**로 온다.

```json
{
  "OpenAPI_ServiceResponse": {
    "cmmMsgHeader": {
      "errMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
      "returnAuthMsg": "등록되지 않은 서비스키",
      "returnReasonCode": "30"
    }
  }
}
```

XML로 오는 경우도 있다. 래퍼는 두 형태를 모두 파싱해 예외로 승격시킨다.

## 3. 항목 필드 ⚠️ 미검증

아래는 **확정된 사실이 아니다.** 검증 전까지는 참고 후보로만 쓴다.

### 식별·기본

| 필드 | 뜻 |
|---|---|
| `bidNtceNo` | 입찰공고번호 |
| `bidNtceOrd` | 입찰공고차수 |
| `bidNtceNm` | 입찰공고명 |
| `refNo` | 참조번호 |
| `ntceKindNm` | 공고종류명 (일반/변경/취소 등) |
| `bidNtceDtlUrl` | 나라장터 공고 상세 화면 URL |

### 기관

| 필드 | 뜻 |
|---|---|
| `ntceInsttNm` / `ntceInsttCd` | 공고기관명 / 코드 |
| `dminsttNm` / `dminsttCd` | 수요기관명 / 코드 |
| `ntceInsttOfclNm` | 공고기관 담당자명 |
| `ntceInsttOfclTelNo` | 담당자 전화번호 |

### 일정

| 필드 | 뜻 |
|---|---|
| `bidNtceDt` | 공고일시 |
| `bidClseDt` | 입찰마감일시 |
| `opengDt` | 개찰일시 |
| `bidBeginDt` | 입찰개시일시 |
| `rgstDt` | 등록일시 |

### 금액

| 필드 | 뜻 |
|---|---|
| `presmptPrce` | 추정가격 |
| `asignBdgtAmt` | 배정예산금액 |
| `bssamt` | 기초금액 (`basis-amount` 계열) |

### 계약·낙찰 방식

| 필드 | 뜻 |
|---|---|
| `cntrctCnclsMthdNm` | 계약체결방법명 |
| `sucsfbidMthdNm` | 낙찰방법명 |
| `bidMethdNm` | 입찰방식명 |
| `intrbidYn` | 국제입찰 여부 |

### 참가 제한

| 필드 | 뜻 |
|---|---|
| `prtcptLmtRgnNm` | 참가제한지역명 (`region-limit` 계열) |
| `indstrytyNm` / `indstrytyCd` | 업종명 / 업종코드 (`license-limit` 계열) |

## 4. 필드 확정 방법

키가 준비되면 아래로 **실제 필드명을 뽑아** 이 문서의 §3을 대체한다.

```bash
# 가장 빠른 방법 — 필드 목록이 바로 출력된다
uv run scripts/g2b_api.py check-key

# 공고가 0건이라 위에서 못 뽑히면 기간을 넓혀 1건만 받는다
uv run scripts/g2b_api.py search --kind servc --days 7 --limit 1 \
  --output /tmp/g2b_probe.json

uv run python -c "import json;d=json.load(open(r'/tmp/g2b_probe.json',encoding='utf-8'));i=d['items'];print(len(i));print('\n'.join(sorted(i[0]))) if i else None"
```

업무구분(`--kind`)과 오퍼레이션 계열마다 필드가 다르다. 최소한
`search` / `search-nara` / `basis-amount` / `license-limit` / `region-limit` /
`change-history` 여섯 계열을 각각 한 번씩 찍어 확정할 것.
