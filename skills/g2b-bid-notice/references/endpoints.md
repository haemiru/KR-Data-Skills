# 오퍼레이션 맵 — 나라장터 입찰공고정보서비스

**베이스 URL**

```
https://apis.data.go.kr/1230000/ad/BidPublicInfoService
```

## 어떻게 확인했나 (실측 · 2026-08-04)

이 API의 상세 명세는 공공데이터포털에서 **docx 파일로만** 배포된다. 웹에서 읽을 수
있는 오퍼레이션 목록이 없어 블로그마다 경로가 다르게 돌아다닌다. 그래서 **인증키
없이** 경로 생존 여부를 판별하는 방법을 썼다.

더미 인증키로 호출하면 응답 코드가 두 갈래로 갈린다.

| 응답 | 뜻 |
|---|---|
| HTTP 403 · `returnReasonCode: 30` · `SERVICE_KEY_IS_NOT_REGISTERED_ERROR` | **경로는 유효하다.** 인증 단계까지 도달했고 키만 틀렸다 |
| HTTP 400 · `returnReasonCode: 12` · `NO_OPENAPI_SERVICE_ERROR` | **그런 경로가 없다** |

즉 라우팅이 인증보다 먼저 일어나므로, 키가 없어도 경로의 존재를 확정할 수 있다.

재현:

```bash
uv run scripts/g2b_api.py probe-endpoints --output references/endpoint-probe.json
```

## ⚠️ 옛 경로는 죽었다

한국어 블로그·예제에 널리 퍼져 있는 아래 경로는 **더 이상 동작하지 않는다**
(`code 12`로 떨어진다).

```
https://apis.data.go.kr/1230000/BidPublicInfoService/...     ← 폐기
https://apis.data.go.kr/1230000/ad/BidPublicInfoService/...  ← 현재
```

`/ad/` 세그먼트가 필수다. 실측으로 양쪽 다 확인했다.

## HTTP가 아니라 HTTPS를 쓴다

포털 예제는 `http://`로 적혀 있지만, 이 저장소의 개발 환경에서는 포트 80이
타임아웃된다. `https://`는 정상 동작한다. 래퍼는 https로 고정돼 있다.

## 생존 확인된 오퍼레이션 18개

### 업무구분별 공고 목록 (5)

| 오퍼레이션 | 업무구분 | 래퍼 명령 |
|---|---|---|
| `getBidPblancListInfoThng` | 물품 | `search --kind thng` |
| `getBidPblancListInfoServc` | 용역 | `search --kind servc` |
| `getBidPblancListInfoCnstwk` | 공사 | `search --kind cnstwk` |
| `getBidPblancListInfoFrgcpt` | 외자 | `search --kind frgcpt` |
| `getBidPblancListInfoEtc` | 기타 | `search --kind etc` |

### 나라장터 검색조건 (5)

공고명·기관명·지역·업종·추정가격 필터를 받는다.

| 오퍼레이션 | 업무구분 | 래퍼 명령 |
|---|---|---|
| `getBidPblancListInfoThngPPSSrch` | 물품 | `search-nara --kind thng` |
| `getBidPblancListInfoServcPPSSrch` | 용역 | `search-nara --kind servc` |
| `getBidPblancListInfoCnstwkPPSSrch` | 공사 | `search-nara --kind cnstwk` |
| `getBidPblancListInfoFrgcptPPSSrch` | 외자 | `search-nara --kind frgcpt` |
| `getBidPblancListInfoEtcPPSSrch` | 기타 | `search-nara --kind etc` |

### 기초금액 (3) — 물품·용역·공사만

| 오퍼레이션 | 래퍼 명령 |
|---|---|
| `getBidPblancListInfoThngBsisAmount` | `basis-amount --kind thng` |
| `getBidPblancListInfoServcBsisAmount` | `basis-amount --kind servc` |
| `getBidPblancListInfoCnstwkBsisAmount` | `basis-amount --kind cnstwk` |

외자·기타는 대응 오퍼레이션이 **없다**(`code 12`로 확인).

### 변경이력 (3) — 물품·용역·공사만

이름 어순이 다른 계열과 **반대**다. `...ChgHstry{업무구분}` 순서다.

| 오퍼레이션 | 래퍼 명령 |
|---|---|
| `getBidPblancListInfoChgHstryThng` | `change-history --kind thng` |
| `getBidPblancListInfoChgHstryServc` | `change-history --kind servc` |
| `getBidPblancListInfoChgHstryCnstwk` | `change-history --kind cnstwk` |

`getBidPblancListInfoThngChgHstry`(어순 뒤집은 형태)는 **없다**. 확인된 오답이다.
`ChgHstryFrgcpt` · `ChgHstryEtc`도 없다.

### 업무구분 없는 단일 오퍼레이션 (2)

| 오퍼레이션 | 내용 | 래퍼 명령 |
|---|---|---|
| `getBidPblancListInfoLicenseLimit` | 면허제한 | `license-limit` |
| `getBidPblancListInfoPrtcptPsblRgn` | 참가가능지역 | `region-limit` |

업무구분 접미사를 붙인 형태(`...CnstwkLicenseLimit` 등)는 **없다**.

## 확인된 오답 (다시 시도하지 말 것)

`code 12`로 부재가 확정된 이름들:

```
getBidPblancListInfoChgHstry            getBidPblancListInfoBsisAmount
getBidPblancListInfoThngChgHstry        getBidPblancListInfoFrgcptBsisAmount
getBidPblancListInfoServcChgHstry       getBidPblancListInfoEtcBsisAmount
getBidPblancListInfoCnstwkChgHstry      getBidPblancListInfoChgHstryFrgcpt
getBidPblancListInfoCnstwkLicenseLimit  getBidPblancListInfoChgHstryEtc
getBidPblancListInfoServcLicenseLimit   getBidPblancListInfoPrtcptPsblRgnPPSSrch
getBidPblancListInfoCnstwkPrtcptPsblRgn getBidPblancListInfoLicenseLimitPPSSrch
getBidPblancListInfoServcPrtcptPsblRgn  getBidPblancListInfoChangeHistory
```

## 공통 요청 파라미터

| 파라미터 | 필수 | 설명 |
|---|---|---|
| `serviceKey` | ✅ | 인증키. 래퍼가 Encoding/Decoding 형태를 자동 판별한다 |
| `type` | | `json` (기본값은 XML이다. 래퍼는 항상 json을 보낸다) |
| `inqryDiv` | ✅ | 조회구분. 래퍼 기본값 `1`. **실측 확정 — 아래 표 참조** |
| `inqryBgnDt` / `inqryEndDt` | ✅ | 조회 기간. `YYYYMMDDHHMM` |
| `pageNo` | | 페이지 번호 (1부터) |
| `numOfRows` | | 페이지당 건수. **상한 999**. 1000 이상은 에러 |

### `inqryDiv` — 실측 확정 (2026-08-05, 용역 7일 창)

| 값 | 결과 | 의미 |
|---|---|---|
| `1` | 2447건 | **공고게시일시 기준.** 일반 조회는 이것 |
| `2` | 0건 (정상 응답) | 날짜 범위로는 아무것도 안 나온다. 다른 파라미터를 요구하는 모드로 추정 — **미확정** |
| `3` | 12건 | **변경일시 기준.** `chgDt`가 채워진다 |

`inqryDiv=3`의 결과 집합은 `change-history`와 **완전히 일치**한다(공고번호 기준
교집합 12 / 차집합 0). 차이는 3이 공고 전체 필드를, `change-history`가
변경 항목(`chgItemNm`/`bfchgVal`/`afchgVal`)을 준다는 점이다.

### `...PPSSrch` 계열 추가 파라미터 — 실측 동작 확인

`bidNtceNm` `ntceInsttNm` `dminsttNm` `prtcptLmtRgnNm` `indstrytyNm`
`indstrytyCd` `presmptPrceBgn` `presmptPrceEnd` `refNo`

용역 7일 기준선 2447건에서 실제로 좁혀지는 것을 확인했다:
`bidNtceNm=청소` → 29건 · `prtcptLmtRgnNm=충청북도` → 52건 ·
`presmptPrceBgn=100000000` → 897건 · `dminsttNm=서울특별시` → 103건.

> ⚠️ **`prtcptLmtRgnNm` `indstrytyNm` `indstrytyCd`는 요청 전용이다.**
> 응답 필드에는 없다. 필터는 먹지만 결과에서 그 값을 되읽을 수 없다.
> 자세한 내용과 우회 방법은 `fields.md` §3.7·§4.

## 에러 코드

| 코드 | 의미 | 대응 |
|---|---|---|
| `12` | NO_OPENAPI_SERVICE_ERROR | 경로/오퍼레이션명 오류 |
| `20` | 서비스 접근 거부 | 활용신청 상태 확인 |
| `22` | 트래픽 초과 | 개발계정 일 1,000건. 다음 날 대기 또는 운영계정 신청 |
| `30` | 등록되지 않은 서비스키 | 키 오타 / 이중 인코딩 / 발급 직후 미반영(최대 1시간) |
| `31` | 활용기간 만료 | 연장 신청 |
| `32` | 등록되지 않은 IP | 포털에서 IP 등록 확인 |

## 계정 한도

- 심의: **개발단계·운영단계 모두 자동승인**
- 개발계정 트래픽: **1,000건/일**
- 운영계정: 활용사례 등록 후 신청하면 증량 가능
