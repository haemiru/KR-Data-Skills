# 응답 필드 — 나라장터 입찰공고정보서비스

> **검증 상태: 실측 완료 (2026-08-05).**
> 유효한 인증키로 6개 오퍼레이션 계열 + 5개 업무구분을 직접 호출해 확인했다.
> 총 API 호출 25회. 표본은 아래 §0에 적었다.
>
> 필드명은 **실제 응답에서 그대로 뽑은 것**이라 오타가 없다.
> 다만 **필드의 "뜻"은 대부분 이름과 관측된 값에서 추론한 것**이다.
> 값으로 확인된 것과 이름만 보고 추론한 것을 §3에서 구분해 표시했다.

## 0. 표본과 재현

| 구분 | 표본 |
|---|---|
| 조회 기간 | 최근 7일 (2026-07-30 ~ 2026-08-05) |
| 용역(`servc`) 필드 채움률 | **35건** (기본 조회 + `inqryDiv=3` + 필터 4종을 합침) |
| 업무구분별 필드 집합 | 각 **5건** (`servc` `cnstwk` `thng` `frgcpt` `etc`) |
| 페이지네이션 | 300건 (100건 × 3페이지) |

재현:

```bash
uv run scripts/g2b_api.py search --kind servc --days 7 --limit 5 \
  --output /tmp/g2b_probe.json

uv run python -c "import json,sys;sys.stdout.reconfigure(encoding='utf-8');d=json.load(open(r'/tmp/g2b_probe.json',encoding='utf-8'));print('\n'.join(sorted({k for i in d['items'] for k in i})))"
```

> **이 API는 값이 비어 있어도 키를 반환한다.** 용역 표본에서 22개 필드가
> 35건 전부 공란이었지만 키는 존재했다. 따라서 아래 "필드 집합"은
> 표본 크기에 거의 영향받지 않는다. 반면 **채움률은 표본 의존적**이다.

## 1. 정상 응답 봉투 ✅

```json
{
  "response": {
    "header": { "resultCode": "00", "resultMsg": "NORMAL SERVICE." },
    "body": {
      "items": [ { "...": "..." } ],
      "numOfRows": 100,
      "pageNo": 1,
      "totalCount": 2447
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
실제로 `inqryDiv=2`로 조회하면 이 형태(정상 응답 + 0건)가 나온다(§5).

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

## 3. `search` / `search-nara` 항목 필드 ✅ 실측

두 명령은 **완전히 같은 필드 집합**을 준다(용역 113개, 동일 표본에서 확인).
차이는 요청 파라미터뿐이다(§4).

채움률은 **용역 35건 표본** 기준이다. `35/35`는 항상 채워짐, `0/35`는 항상 공란.

### 3.1 식별·번호

| 필드 | 뜻 | 채움 | 관측값 |
|---|---|---|---|
| `bidNtceNo` | 입찰공고번호 | 35/35 | `R26BK01653578` |
| `bidNtceOrd` | 입찰공고차수 | 35/35 | `000` `001` |
| `bidNtceNm` | 입찰공고명 | 35/35 | |
| `refNo` | 참조번호 (기관 자체 문서번호) | 34/35 | `2026-034` `학생과-7715` |
| `untyNtceNo` | 통합공고번호 | 35/35 | `R26BM00902623` |
| `orderPlanUntyNo` | 발주계획 통합번호 | 29/35 | `R26DD20829594` |
| `bfSpecRgstNo` | 사전규격 등록번호 | 26/35 | `R26BD00256691` |
| `befBidBbancNo` | 직전 입찰 공고번호 ※이름 추론 | 2/35 | `R26BK01620234` |
| `ntceKindNm` | 공고종류명 | 35/35 | **`등록공고` `재공고` `취소공고`** |
| `reNtceYn` | 재공고 여부 | 35/35 | `N` `Y` |
| `rgstTyNm` | 등록유형명 | 35/35 | `조달청 또는 나라장터 자체 공고건` |

> 번호 접두어가 계열을 나눈다 — `R26BK`=공고, `R26BM`=통합공고,
> `R26DD`=발주계획, `R26BD`=사전규격. (관측 기반, 명세로 확인한 것은 아님)

### 3.2 기관·담당자

| 필드 | 뜻 | 채움 | 관측값 |
|---|---|---|---|
| `ntceInsttCd` / `ntceInsttNm` | 공고기관 코드 / 명 | 35/35 | `7008285` |
| `dminsttCd` / `dminsttNm` | 수요기관 코드 / 명 | 35/35 | |
| `ntceInsttOfclNm` | 공고기관 담당자명 | 35/35 | |
| `ntceInsttOfclTelNo` | 담당자 전화번호 | 35/35 | `043-841-5030` |
| `exctvNm` | 집행관명 ※표본에서 담당자명과 동일 | 35/35 | |
| `crdtrNm` | 계약담당자/발주처장 (직위까지 붙는다) | 35/35 | `강서구청` `경복초등학교장` |
| `ntceInsttOfclEmailAdrs` | 공고기관 담당자 이메일 | **0/35** | 항상 공란 |
| `dminsttOfclEmailAdrs` | 수요기관 담당자 이메일 | **0/35** | 항상 공란 |

> **이메일은 못 쓴다.** 두 필드 모두 표본 35건 전부 공란이었다.
> 연락 수단은 `ntceInsttOfclTelNo` 뿐이다.

### 3.3 일정

| 필드 | 뜻 | 채움 | 형식 |
|---|---|---|---|
| `bidNtceDt` | 공고일시 | 35/35 | `2026-07-30 07:44:25` |
| `rgstDt` | 등록일시 ※표본에서 `bidNtceDt`와 동일 | 35/35 | |
| `bidBeginDt` | 입찰개시일시 | 35/35 | |
| `bidClseDt` | 입찰마감일시 | 35/35 | |
| `opengDt` | 개찰일시 | 35/35 | |
| `rbidOpengDt` | 재입찰 개찰일시 ※표본에서 `opengDt`와 동일 | 35/35 | |
| `bidQlfctRgstDt` | 입찰참가자격 등록마감 | 35/35 | `2026-08-09 18:00` (분 단위) |
| `chgDt` | 변경일시 | **5/35** | `inqryDiv=3`으로 뽑은 건에서만 채워짐 |
| `cmmnSpldmdAgrmntClseDt` | 공동수급협정 마감일시 | 7/35 | |
| `arsltReqstdocRcptDt` · `pqApplDocRcptDt` · `tpEvalApplClseDt` · `dcmtgOprtnDt` | 실적/PQ/기술평가/설명회 일시 | **0/35** | 용역 표본에선 전부 공란 |

> 날짜 형식이 **초 단위(`YYYY-MM-DD HH:MM:SS`)와 분 단위(`YYYY-MM-DD HH:MM`)로
> 섞여 있다.** `bidQlfctRgstDt`가 분 단위다. 파싱할 때 둘 다 받아야 한다.
> 요청 파라미터(`inqryBgnDt`)의 `YYYYMMDDHHMM`과도 형식이 다르다.

### 3.4 금액 — 산술 관계 확인됨 ✅

| 필드 | 뜻 | 채움 | 관측값 |
|---|---|---|---|
| `presmptPrce` | 추정가격 (부가세 **제외**) | 35/35 | `136363636` |
| `VAT` | 부가가치세 | 35/35 | `13636364` |
| `asignBdgtAmt` | 배정예산금액 (부가세 **포함**) | 35/35 | `150000000` |
| `bidPrtcptFee` | 입찰참가수수료 | 35/35 | `0` |
| `sucsfbidLwltRate` | 낙찰하한율(%) | 12/35 | `87.745` `88` |
| `indutyVAT` | (용도 불명) | **0/35** | 항상 공란 |

**표본 35건 전부에서 성립한 관계 (예외 0건):**

```
presmptPrce + VAT == asignBdgtAmt
VAT == round(presmptPrce * 0.1)
```

> 즉 **`presmptPrce`는 부가세 제외 금액이다.** 사용자가 "예산 1억 이상"이라고
> 말할 때 어느 쪽을 뜻하는지 확인해야 한다. `search-nara --price-from`은
> `presmptPrce` 기준이므로 **부가세 제외 금액으로 넣어야 한다.**

### 3.5 계약·낙찰 방식

| 필드 | 뜻 | 채움 | 관측값 |
|---|---|---|---|
| `cntrctCnclsMthdNm` | 계약체결방법명 | 35/35 | **`일반경쟁` `제한경쟁` `수의계약`** |
| `bidMethdNm` | 입찰방식명 | 35/35 | **`전자입찰` `전자시담`** |
| `sucsfbidMthdCd` | 낙찰방법코드 | 35/35 | `낙030001` `낙030002` `낙030005` |
| `sucsfbidMthdNm` | 낙찰방법명 | 35/35 | `협상에의한계약-…` `수의시담-수의시담` |
| `prearngPrceDcsnMthdNm` | 예정가격 결정방법 | 35/35 | **`복수예가` `단일예가` `비예가`** |
| `totPrdprcNum` | 총 예비가격 개수 | 25/35 | `15` `1` |
| `drwtPrdprcNum` | 추첨 예비가격 개수 | 25/35 | `4` `0` |
| `rsrvtnPrceReMkngMthdNm` | 예비가격 재작성 방법 | 18/35 | |
| `rbidPermsnYn` | 재입찰 허용여부 | 22/35 | `N` `Y` |
| `intrbidYn` | 국제입찰 여부 | 35/35 | `N` |
| `sucsfbidMthdAppStd` | 낙찰방법 적용기준 | 1/35 | `관리규정외(기타)` |
| `opengPlce` | 개찰장소 | 34/35 | `국가종합전자조달시스템(나라장터)` |

### 3.6 평가 비율 — 합이 100 ✅

| 필드 | 뜻 | 채움 | 관측값 |
|---|---|---|---|
| `bidPrceEvlRt` | 가격 평가비율(%) | 13/35 | `10` `20` `30` |
| `techAbltEvlRt` | 기술능력 평가비율(%) | 13/35 | `90` `80` `70` |

둘 다 채워진 13건 **전부**에서 `bidPrceEvlRt + techAbltEvlRt == 100` 이었다.
협상에 의한 계약 등 기술평가가 있는 건에서만 채워진다.

### 3.7 참가 제한 — ⚠️ 여기가 함정이다

| 필드 | 뜻 | 채움 | 관측값 |
|---|---|---|---|
| `indstrytyLmtYn` | 업종제한 **여부만** | 35/35 | `N` `Y` |
| `bidPrtcptLmtYn` | 입찰참가제한 여부 | 35/35 | `N` |
| `prdctClsfcLmtYn` | 물품분류제한 여부 | 35/35 | `N` |
| `rgnLmtBidLocplcJdgmBssCd` / `…Nm` | 지역제한 소재지 판단기준 | 10/35 | `본사또는참여지사소재지` |
| `cmmnSpldmdCorpRgnLmtYn` | 공동수급체 지역제한 여부 | 35/35 | `N` `Y` |
| `jntcontrctDutyRgnNm1~3` | 공동도급 의무지역명 | **0/35** | 용역 표본 전부 공란 |
| `rgnDutyJntcontrctRt` | 지역의무공동도급 비율 | **0/35** | 항상 공란 |

> ### 🔴 `prtcptLmtRgnNm` · `indstrytyNm` · `indstrytyCd` 는 응답 필드가 아니다
>
> 이전 문서가 이 셋을 응답 필드로 적어 뒀는데 **틀렸다.**
> 실제 응답 113개 키 어디에도 없다. 셋 다 **요청 파라미터 전용**이다(§4).
>
> **결과적으로 `search`/`search-nara` 응답만으로는 그 공고의 제한지역명과
> 업종명을 알 수 없다.** 알 수 있는 건 "제한이 걸려 있나"(`indstrytyLmtYn`)와
> "소재지를 어떻게 판단하나"(`rgnLmtBidLocplcJdgmBssNm`)까지다.
>
> 실제 지역명·업종명이 필요하면 **별도 오퍼레이션을 붙여야 한다** —
> `region-limit`(`prtcptPsblRgnNm`) · `license-limit`(`lcnsLmtNm`).
> 조인 키는 `bidNtceNo` + `bidNtceOrd`다.

### 3.8 공동수급

| 필드 | 뜻 | 채움 | 관측값 |
|---|---|---|---|
| `cmmnSpldmdMethdCd` | 공동수급방식 코드 | 7/35 | `공500001` `공500002` |
| `cmmnSpldmdMethdNm` | 공동수급방식명 | 35/35 | `(전자)공동이행` `(없음)공동수급불허` |
| `cmmnSpldmdAgrmntRcptdocMethd` | 협정서 접수방법 | 35/35 | `전자` `수기` `없음` |

### 3.9 조달 품목 분류 (용역·물품 계열)

| 필드 | 뜻 | 채움 | 관측값 |
|---|---|---|---|
| `pubPrcrmntClsfcNo` | 조달품목 분류번호 (8자리) | 35/35 | `90151890` `76111501` |
| `pubPrcrmntClsfcNm` | 분류명 | 35/35 | `건물청소서비스` |
| `pubPrcrmntLrgClsfcNm` | 대분류명 | 35/35 | `ICT 서비스` |
| `pubPrcrmntMidClsfcNm` | 중분류명 | 35/35 | `SW 및 시스템 개발` |
| `srvceDivNm` | 용역구분명 (**용역 전용**) | 35/35 | `일반용역` |
| `purchsObjPrdctList` | 구매대상 물품목록 | 1/35 | `[1^8111159901^정보시스템개발서비스]` |

### 3.10 첨부 문서 URL

| 필드 | 뜻 | 채움 |
|---|---|---|
| `bidNtceDtlUrl` / `bidNtceUrl` | 나라장터 공고 상세 화면 (표본에서 값 동일) | 35/35 |
| `stdNtceDocUrl` | 표준 공고서 | 33/35 |
| `ntceSpecDocUrl1` ~ `10` | 규격서 파일 URL (번호별 슬롯) | 1·2번 34/35, 3번 25/35, 이후 급감, 9·10번 0/35 |
| `ntceSpecFileNm1` ~ `10` | 규격서 파일명 (`.hwp` `.pdf` `.xlsx`) | 위와 동일 |

> URL 슬롯은 **1번부터 순서대로 채워지고 중간에 비지 않는다**(표본 기준).
> 첨부가 있는지 보려면 `ntceSpecFileNm1`만 확인하면 된다.

### 3.11 기타 Y/N 플래그

| 필드 | 뜻 | 채움 |
|---|---|---|
| `arsltCmptYn` | 실적경쟁 여부 | 35/35 (`N`) |
| `dsgntCmptYn` | 지명경쟁 여부 | 35/35 (`N`) |
| `ppswGnrlSrvceYn` | 조달청 일반용역 여부 | 35/35 (`N` `Y`) |
| `infoBizYn` | 정보화사업 여부 | 1/35 |
| `tpEvalYn` | 기술제안 평가 여부 | 1/35 |
| `chgNtceRsn` | 변경공고 사유 | 1/35 (`[취소공고] …`) |
| `bidGrntymnyPaymntYn` · `bidPrtcptFeePaymntYn` · `brffcBidprcPermsnYn` · `dtlsBidYn` · `mnfctYn` · `ntceDscrptYn` · `pqEvalYn` | — | **0/35** 전부 공란 |
| `arsltApplDocRcptMthdNm` · `pqApplDocRcptMthdNm` · `tpEvalApplMthdNm` · `dcmtgOprtnPlce` | — | **0/35** 전부 공란 |

## 4. 요청 파라미터 ≠ 응답 필드 ✅ 실측

`search-nara`(`...PPSSrch`) 필터는 **서버에서 실제로 동작한다.**
용역 7일 기준선 2447건에서:

| 필터 | API 파라미터 | 결과 | 응답 필드로 존재하나 |
|---|---|---|---|
| `--title 청소` | `bidNtceNm` | **29건** | ✅ `bidNtceNm` |
| `--region 충청북도` | `prtcptLmtRgnNm` | **52건** | ❌ **없음** |
| `--price-from 100000000` | `presmptPrceBgn` | **897건** | ✅ `presmptPrce` |
| `--demand-inst 서울특별시` | `dminsttNm` | **103건** | ✅ `dminsttNm` |

> **`--region`은 먹지만 검증은 안 된다.** 응답에 지역 필드가 없으므로
> 결과가 정말 그 지역인지 응답만으로는 확인할 수 없다. 교차검증하려면
> `region-limit`을 따로 호출해 `bidNtceNo`로 조인해야 한다.
>
> 다만 실사용 시나리오에서 `--region 충청북도`로 뽑은 31건의 상위 결과가
> 전부 충북 소재 기관(한국농어촌공사 충북지역본부·충청북도 청주시·
> 충북과학기술혁신원)이었으므로, 필터 자체는 의도대로 동작한다고 본다.

## 5. `inqryDiv` 확정 ✅ 실측

용역 7일 창에서 값만 바꿔 호출한 결과:

| 값 | 결과 | 의미 | 근거 |
|---|---|---|---|
| **`1`** (래퍼 기본값) | **2447건** | **공고게시일시 기준.** 일반 조회는 이걸 쓴다 | `chgDt`가 전부 공란 |
| `2` | **0건** | 날짜 범위로는 아무것도 안 나온다. 다른 파라미터(공고번호 등)를 요구하는 모드로 보인다 ※미확정 | 정상 응답(`resultCode 00`) + `totalCount 0` |
| **`3`** | **12건** | **변경일시 기준.** 기간 내에 변경된 공고만 | `chgDt`가 전부 채워짐 |

**`inqryDiv=3`과 `change-history`는 같은 공고 집합이다** — 같은 창에서
양쪽 다 12건이었고, 공고번호 집합이 **완전히 일치**했다(교집합 12, 차집합 0).

용도가 다르다:

| | 주는 것 |
|---|---|
| `search --inqry-div 3` | 변경된 공고의 **전체 필드**(113개) |
| `change-history` | **무엇이 어떻게 바뀌었는지** (`chgItemNm` `bfchgVal` `afchgVal`) |

> `inqryDiv=2`는 0건이 정상 응답으로 온다. **에러가 아니다.**
> 이걸 "조회 실패"로 오해하지 말 것.

## 6. 페이지네이션 ✅ 실측

`search --kind servc --days 7 --limit 100 --max-pages 3`:

| 항목 | 결과 |
|---|---|
| API 호출 | 3회 (페이지당 1회) |
| 수집 | 300건 / 전체 2447건 |
| `(bidNtceNo, bidNtceOrd)` 고유 | **300** — 중복 0 |
| `bidNtceNo`만 고유 | **292** — 8건이 같은 공고번호 |

### 🔴 중복 제거 키는 `bidNtceNo` 하나가 아니다

같은 공고번호가 **차수(`bidNtceOrd`)만 다르게 여러 행**으로 온다.
관측된 8건 모두 `000`과 `001` 쌍이었고, 공고명은 같고 `bidNtceDt`만 몇 시간 차이였다.

```
R26BK01657716  ord=000  2026-07-30 09:37:01  4-2 2026년 KNU-대구앵커 …
R26BK01657716  ord=001  2026-07-30 15:20:48  4-2 2026년 KNU-대구앵커 …
```

- **행 단위 유일 키 = `(bidNtceNo, bidNtceOrd)`**
- **공고 1건당 최신본만 필요하면** `bidNtceNo`로 묶어 `bidNtceOrd` 최댓값을 취한다
- 이걸 안 하면 사용자에게 같은 공고를 두 번 보고하게 된다

> 정렬은 `bidNtceDt` 내림차순이 **아니다**(실측). 페이지 경계에서 누락·중복은
> 없었지만, 순서를 신뢰하고 조기 종료하지 말 것.

## 7. `basis-amount` 항목 필드 ✅ 실측

용역 26개 / 공사 32개. **공사에만 6개가 더 있다.**

### 공통 (용역·공사)

| 필드 | 뜻 | 관측값 |
|---|---|---|
| `bidNtceNo` / `bidNtceOrd` | 공고번호 / 차수 | 조인 키 |
| `bidClsfcNo` | 입찰분류번호 | `0` |
| `bidNtceNm` | 공고명 | |
| `bssamt` | **기초금액** | `133760000` |
| `bssamtOpenDt` | 기초금액 공개일시 | `2026-07-30 06:20:40` |
| `inptDt` | 입력일시 | |
| `evlBssAmt` | 평가기준금액 | `0` |
| `rsrvtnPrceRngBgnRate` / `…EndRate` | 예비가격 범위(%) | **`-3` / `+3`** |
| `usefulAmt` | 순공사(용역)원가 ※이름 추론 | `0` |
| `mrfnHealthInsrprm` | 건강보험료 | `0` |
| `npnInsrprm` | 국민연금보험료 | `0` |
| `odsnLngtrmrcprInsrprm` | 노인장기요양보험료 | `0` |
| `rtrfundNon` | 퇴직공제부금비 | `0` |
| `envCnsrvcst` | 환경보전비 | `0` |
| `sftyMngcst` / `sftyChckMngcst` | 안전관리비 / 안전점검비 | `0` |
| `scontrctPayprcePayGrntyFee` | 하도급대금 지급보증 수수료 | `0` |
| `lbrcstBssRate` · `gnrlMngcstBssRate` · `etcGnrlexpnsBssRate` · `prftBssRate` | 노무비·일반관리비·기타경비·이윤 기준요율 | 공란 |
| `dfcltydgrCfcnt` | 난이도 계수 | 공란 |
| `rmrk1` / `rmrk2` | 비고 | 공란 |

### 공사(`cnstwk`) 전용 6개

`bidPrceCalclAYn` · `bssAmtPurcnstcst`(순공사원가) · `qltyMngcst`(품질관리비) ·
`qltyMngcstAObjYn` · `smkpAmt` · `smkpAmtYn`

> `rsrvtnPrceRngBgnRate/EndRate`가 **`-3` / `+3`** 으로 관측됐다.
> 복수예가 범위(±3%)를 뜻하는 것으로 보인다.

### `bssamt` 와 `presmptPrce` 의 관계 ✅ 실측 (2026-08-05, 2차)

`--join basis`로 붙인 32쌍 중 **`bssamt`가 0이 아닌 31쌍 전부**에서:

```
bssamt == presmptPrce * 1.1        (= 추정가격 + 부가세)
```

비율이 정확히 `1.100`이었다(오차 없음). 나머지 1건은 `bssamt = 0`
(방위사업 체계개발 건 — 기초금액 미공개로 보인다).

> 이 관계는 **조인이 올바른 행을 붙였는지 검증하는 데 쓸 수 있다.**
> 엉뚱한 행이 붙으면 비율이 흩어진다. 실제로 조인 구현을 이걸로 검증했다.

## 8. `license-limit` 항목 필드 ✅ 실측 (9개)

| 필드 | 뜻 | 관측값 |
|---|---|---|
| `bidNtceNo` / `bidNtceOrd` | 공고번호 / 차수 | 조인 키 |
| `bsnsDivNm` | 업무구분명 | `물품` `용역` `공사` |
| `lcnsLmtNm` | **면허제한명 (+코드)** | `소독업신고증/0036` |
| `lmtGrpNo` | 제한 그룹번호 | `1` |
| `lmtSno` | 제한 일련번호 | `1` |
| `permsnIndstrytyList` | 허용 업종 목록 | 공란(표본) |
| `indstrytyMfrcFldList` | 업종 주력분야 목록 | 공란(표본) |
| `rgstDt` | 등록일시 | |

> `lcnsLmtNm`은 `면허명/코드` 형태로 **한 필드에 붙어 온다.** 파싱하려면 `/`로 쪼갠다.
> `lmtGrpNo`가 있는 것으로 보아 **한 공고에 여러 면허 조건이 그룹으로 걸린다.**
> 공고 1건 = 행 1건이 아니다.

## 9. `region-limit` 항목 필드 ✅ 실측 (6개)

| 필드 | 뜻 | 관측값 |
|---|---|---|
| `bidNtceNo` / `bidNtceOrd` | 공고번호 / 차수 | 조인 키 |
| `bsnsDivNm` | 업무구분명 | `물품` |
| `prtcptPsblRgnNm` | **참가가능지역명** | `경기도` |
| `lmtSno` | 제한 일련번호 | `1` |
| `rgstDt` | 등록일시 | |

> **지역명의 정답은 `prtcptPsblRgnNm`이다** (`prtcptLmtRgnNm`이 아니다 — 그건
> 요청 파라미터 이름이다). 한 공고에 여러 지역이 붙으면 `lmtSno`로 늘어난다.

## 10. `change-history` 항목 필드 ✅ 실측 (11개)

| 필드 | 뜻 | 관측값 |
|---|---|---|
| `bidNtceNo` / `bidNtceOrd` | 공고번호 / 차수 | 조인 키 |
| `bidClsfcNo` | 입찰분류번호 | `0` |
| `bsnsDivNm` | 업무구분명 | `용역` |
| `chgDt` | 변경일시 | `2026-07-30 08:12:56` |
| `chgDataDivNm` | 변경데이터 구분명 | `입찰공고` |
| `chgItemNm` | **변경 항목명** | `개찰일시` |
| `bfchgVal` | **변경 전 값** | `2026/08/05 18:00` |
| `afchgVal` | **변경 후 값** | `202607300900` |
| `rbidNo` | 재입찰번호 | `000` |
| `lcnsLmtCdRgstList` | 면허제한코드 등록목록 | 공란(표본) |

> ### 🔴 `bfchgVal` / `afchgVal` 의 날짜 형식이 서로 다르다
>
> 실측 표본에서 변경 전은 `2026/08/05 18:00`(슬래시), 변경 후는
> `202607300900`(붙임)이었다. **같은 항목인데 형식이 다르다.**
> 값을 날짜로 파싱할 거면 두 형식을 모두 처리해야 한다.
>
> 또한 이 필드들은 **어떤 항목이냐에 따라 날짜일 수도 금액일 수도 있다.**
> `chgItemNm`을 먼저 보고 형을 정할 것.
>
> 표본 12건의 `chgItemNm`은 **전부 `개찰일시`** 였다. 다른 값이 무엇인지는
> 표본에 안 잡혔다 — 미확인.

## 11. 업무구분별 필드 집합 차이 ✅ 실측

각 5건 표본 기준 필드 개수:

| 업무구분 | 필드 수 | 7일 건수 | 성격 |
|---|---|---|---|
| `servc` 용역 | **113** | 2447 | 기준으로 삼음 |
| `cnstwk` 공사 | **143** | 1656 | 가장 많다 |
| `thng` 물품 | **101** | 2237 | |
| `frgcpt` 외자 | **97** | 25 | 물품과 유사, **`VAT` 없음** |
| `etc` 기타 | **38** | 103 | **집합이 확 다르다** |

### 공사(`cnstwk`) 전용 — 용역에 없는 48개 중 핵심

| 필드 | 뜻 |
|---|---|
| `mainCnsttyNm` / `mainCnsttyPresmptPrce` / `mainCnsttyCnstwkPrearngAmt` | 주공종명 / 추정가격 / 공사예정금액 |
| `subsiCnsttyNm1~9` / `subsiCnsttyIndstrytyEvlRt1~9` | 부공종명 / 부공종 업종평가비율 (슬롯 9개) |
| `cnstrtsiteRgnNm` | **공사현장 지역명** ← 공사는 지역 정보가 응답에 있다 |
| `cnstrtnAbltyEvlAmtList` | 시공능력 평가액 목록 |
| `cnsttyAccotShreRateList` | 공종별 지분율 목록 |
| `govsplyAmt` / `govcnstrtnGovsplyMtrlAmt` / `contrctrcnstrtnGovsplyMtrlAmt` | 관급자재 금액 계열 |
| `rgnDutyJntcontrctYn` | 지역의무 공동도급 여부 |
| `incntvRgnNm1~4` | 지역가점 지역명 (슬롯 4개) |
| `indstrytyEvlRt` / `indstrytyMfrcFldEvlYn` | 업종 평가비율 / 주력분야 평가여부 |
| `mtltyAdvcPsblYn` / `mtltyAdvcPsblYnCnstwkNm` | 상호시장 진출 가능여부 / 공사명 |
| `sptDscrptDocUrl1~5` | 현장설명 문서 URL |
| `bdgtAmt` | 예산금액 |
| `ciblAplYn` · `aplBssCntnts` · `cmmnSpldmdCnum` | 적격심사 적용여부 · 적용기준 · 공동수급 업체수 |
| `bidWgrnteeRcptClseDt` · `arsltApplDocRcptDt` | 입찰보증금 접수마감 · 실적신청서 접수 |

> **공사는 `cnstrtsiteRgnNm`(공사현장 지역명)이 응답에 있다.**
> 용역·물품과 달리 공사에서는 지역을 응답만으로 확인할 수 있다.

### 물품(`thng`)·외자(`frgcpt`) 전용

`dlvrTmlmtDt`(납품기한) · `dlvrDaynum`(납품일수) · `dlvryCndtnNm`(납품조건명) ·
`prdctQty`(수량) · `prdctUnit`(단위) · `prdctUprc`(단가) · `prdctSpecNm`(규격명) ·
`dtilPrdctClsfcNo` / `…NoNm`(세부품명번호/명) · `prdctSno`(외자 전용, 물품일련번호)

용역의 `pubPrcrmnt*` 분류 4종은 **물품·외자에 없다.** 대신 `dtilPrdctClsfcNo` 계열을 쓴다.

> **외자(`frgcpt`)에는 `VAT`와 `asignBdgtAmt`가 없다.** §3.4의 산술 관계를
> 외자에 적용하면 안 된다.

### 기타(`etc`) — 38개뿐

용역 113개 중 **79개가 없다.** `presmptPrce` `bidClseDt` 같은 기본 필드는 있지만
`dminsttCd` · `ntceInsttOfclNm` · `ntceInsttOfclTelNo` · `sucsfbidMthdNm` ·
`prearngPrceDcsnMthdNm` · `stdNtceDocUrl` 등이 **전부 빠진다.**
`etc` 전용으로 `bidGrntymnyPaymntObjYn` · `bidQlfctRgstCntnts` ·
`cmmnSpldmdYn` · `rmrkCntnts` 4개가 있다.

> **업무구분을 바꿔 조회할 때 `--fields`를 그대로 재사용하지 말 것.**
> 없는 필드를 지정하면 그 키는 결과에서 조용히 빠진다.

## 12. 조인 관계 정리

모든 보조 오퍼레이션은 **`bidNtceNo` + `bidNtceOrd`** 로 공고에 붙는다.

```
search / search-nara  (공고 본문 113~143 필드)
      │
      ├── basis-amount    → bssamt (기초금액), 예비가격 범위
      ├── license-limit   → lcnsLmtNm (면허제한명)      ※ 1:N (lmtGrpNo/lmtSno)
      ├── region-limit    → prtcptPsblRgnNm (참가가능지역) ※ 1:N (lmtSno)
      └── change-history  → chgItemNm/bfchgVal/afchgVal  ※ 1:N
```

**보조 오퍼레이션은 전부 1:N이다.** 공고 1건에 행이 여러 개 붙을 수 있으므로
단순 조인 후 건수를 세면 부풀려진다.

### 래퍼가 대신 해 준다 — `--join` ✅ 구현·검증됨 (2026-08-05, 2차)

```bash
uv run scripts/g2b_api.py search-nara --kind servc --days 7 \
  --region "충청북도" --join region --dedup latest --preset core \
  --output out/x.json
```

`_region[]` · `_license[]` · `_basis[]` 로 붙는다(항상 배열, 없으면 빈 배열).

**보조 오퍼레이션은 공고번호로 좁히는 파라미터가 없다**(실측). 그래서 래퍼는
같은 기간을 통째로 훑어 메모리에서 인덱싱한다. **호출 비용이 크다** —
7일 창 참가가능지역이 6,000행대(7페이지)다.

검증 결과:

| 확인 | 결과 |
|---|---|
| `--region 충청북도` 결과에 `region` 조인 | **28/28 매칭(100%)**, 전부 충북 계열 지역 |
| 붙은 행의 `(bidNtceNo, bidNtceOrd)` 일치 | **불일치 0건** |
| `bssamt / presmptPrce` 비율 | **전 건 정확히 1.100** — 올바른 행이 붙었다는 증거 |
| `--join-max-pages 1`로 강제 절단 | 매칭 0% + `join_incomplete` 경고 정상 발생 |

> 매칭률이 100%가 아닌 건 정상이다. 지역제한·면허제한·기초금액이 모든 공고에
> 있는 게 아니다(실측: 지역 22% · 면허 62% · 기초금액 15%).
> **문제 신호는 매칭률이 아니라 `_meta.join_incomplete` 다.**

## 13. 남은 미확인 항목

정직하게 적어 둔다. 이 문서에서 **확정하지 못한 것**:

| 항목 | 상태 |
|---|---|
| `inqryDiv=2`의 정확한 용도 | 날짜 범위로는 0건. 어떤 파라미터를 원하는지 미확인 |
| `chgItemNm`의 값 목록 | 표본 12건이 전부 `개찰일시`. 다른 값 미관측 |
| 0/35 공란 필드 22개의 채워지는 조건 | 용역 표본에서 안 나옴. 다른 업무구분·조건에서 나올 수 있음 |
| `permsnIndstrytyList` · `indstrytyMfrcFldList` · `cnstrtnAbltyEvlAmtList` 등 `*List` 필드의 구분자 | 표본에서 공란이라 형식 미확인. `purchsObjPrdctList`는 `[1^코드^명]` 형태로 관측됨 |
| `usefulAmt` · `befBidBbancNo` · `exctvNm`의 정확한 정의 | 이름과 값에서 추론. 명세 미확인 |
| 업무구분별 필드 집합 (5건 표본) | 이 API는 공란도 키를 반환하므로 신뢰도가 높지만, 표본이 5건이라는 한계는 있음 |
