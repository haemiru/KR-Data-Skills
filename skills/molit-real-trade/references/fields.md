# 응답 필드 — 국토교통부 실거래가(RTMS)

> **검증 상태: 실측 (2026-08-05).**
> 유효한 인증키로 서울 종로구(`11110`) / `202607` 을 호출해 확인했다.
> 필드명은 실제 응답에서 그대로 뽑은 것이라 오타가 없다.
> 다만 **필드의 "뜻"은 이름과 관측된 값에서 추론한 것**이 대부분이다.
>
> 표본이 한 지역·한 달이라 **채움률은 일반화하지 말 것.**
> 필드 집합은 이 API가 값이 비어도 키를 반환하므로 신뢰도가 높다.

## 0. 먼저 알아야 할 것 3가지

### 🔴 (1) 금액은 만원 단위 문자열이다

```
dealAmount  "273,000"    → 2,730,000,000원  (27억 3천만)
dealAmount  "1,740,000"  → 17,400,000,000원 (174억)
dealAmount  "172"        → 1,720,000원      (토지 소액 거래)
deposit     "1,000"      → 10,000,000원
monthlyRent "70"         → 700,000원
```

천단위 콤마가 들어간 **문자열**이고 단위가 **만원**이다.
그대로 `int()` 하면 터지고, 콤마만 지우면 자릿수가 4자리 틀린다.

래퍼가 `_dealAmountWon` · `_depositWon` · `_monthlyRentWon` ·
`_preDepositWon` · `_preMonthlyRentWon` 을 원 단위로 붙인다.

### 🔴 (2) 빈 값이 공백 한 칸(`" "`)이다

`""` 가 아니다. `if not value` 로는 안 걸러진다. `.strip()` 후 판단할 것.

### 🔴 (3) 같은 개념인데 이름이 다르다

| 개념 | 아파트매매 | 아파트전월세 | 오피스텔 | 연립다세대 | 단독다가구 | 토지 | 상업업무용 |
|---|---|---|---|---|---|---|---|
| 건물명 | `aptNm` | `aptNm` | `offiNm` | `mhouseNm` | — | — | — |
| 대표면적 | `excluUseAr` | `excluUseAr` | `excluUseAr` | `excluUseAr` | `totalFloorAr` | `dealArea` | `buildingAr` |
| 도로명 | `roadNm` | **`roadnm`** | — | — | — | — | — |
| 시군구명 | — | — | `sggNm` | — | — | `sggNm` | `sggNm` |

**아파트 매매는 `roadNm`, 전월세는 `roadnm`** — 대소문자가 다르다.
도로명 계열 전체가 그렇다(`roadNmBonbun` vs `roadnmbonbun`).

래퍼가 `_name` · `_area` · `_areaField` 로 통일해 준다. 이걸 쓰면 안 헷갈린다.

## 1. 매매 6종 공통 필드 ✅ 실측

아파트·오피스텔·연립다세대·단독다가구·토지·상업업무용 **전부**에 있다.

| 필드 | 뜻 | 관측값 |
|---|---|---|
| `dealAmount` | 거래금액 (**만원**) | `110,000` |
| `dealYear` / `dealMonth` / `dealDay` | 계약 연 / 월 / 일 | `2026` / `7` / `27` |
| `dealingGbn` | 거래유형 | **`중개거래` `직거래`** |
| `estateAgentSggNm` | 중개사무소 소재 시군구 | `서울 종로구` (직거래면 공란) |
| `cdealType` / `cdealDay` | 해제여부 / 해제사유 발생일 | 보통 공란 |
| `jibun` | 지번 | **마스킹됨** — `1**` `산1*` `*` |
| `sggCd` | 시군구코드 5자리 | `11110` |
| `umdNm` | 읍면동명 | `숭인동` |

> **`estateAgentSggNm`을 매물 소재지로 쓰지 말 것.** 중개사무소 위치다.
> 매물 지역은 `sggCd` + `umdNm` 이다.
>
> **지번은 마스킹된다.** 정확한 번지를 원하는 요청에는 이 API로 답할 수 없다.

## 2. 아파트 매매 — 32개 ✅

`RTMSDataSvcAptTradeDev` 기준. 위 공통 11개 + 아래.

| 필드 | 뜻 | 관측값 |
|---|---|---|
| `aptNm` | 아파트명 | `종로센트레빌` |
| `aptSeq` | 단지 일련번호 | `11110-2224` |
| `aptDong` | 동 | 공란인 경우가 많다 |
| `excluUseAr` | 전용면적(㎡) | `59.92` |
| `floor` | 층 | `6` |
| `buildYear` | 건축년도 | `2008` |
| `buyerGbn` / `slerGbn` | 매수자 / 매도자 구분 | **`개인` `법인`** |
| `umdCd` | 읍면동 코드 | `17500` |
| `bonbun` / `bubun` | 본번 / 부번 | `0002` / `0001` |
| `landCd` | 대지구분코드 | `1` |
| `landLeaseholdGbn` | 토지임대부 여부 | `N` |
| `rgstDate` | 등기일자 | 공란 많음 |
| `roadNm` | 도로명 | `동망산길` |
| `roadNmCd` · `roadNmSggCd` · `roadNmBonbun` · `roadNmBubun` · `roadNmSeq` · `roadNmbCd` | 도로명 코드 계열 | |

## 3. 아파트 전월세 — 25개 ✅

`RTMSDataSvcAptRent`. **매매와 달리 `dealAmount`가 없다.**

| 필드 | 뜻 | 관측값 |
|---|---|---|
| `deposit` | 보증금 (**만원**) | `1,000` |
| `monthlyRent` | 월세 (**만원**). `0`이면 전세 | `70` |
| `preDeposit` / `preMonthlyRent` | **직전 계약** 보증금 / 월세 | `1,000` / `70` |
| `contractTerm` | 계약기간 | `26.07~27.07` |
| `contractType` | 계약구분 | **`갱신` `신규`** |
| `useRRRight` | 갱신요구권 사용 여부 | 공란 또는 `사용` |
| `aptNm` · `aptSeq` · `buildYear` · `excluUseAr` · `floor` · `jibun` · `sggCd` · `umdNm` | 매매와 동일 | |
| `roadnm` · `roadnmcd` · `roadnmsggcd` · `roadnmbonbun` · `roadnmbubun` · `roadnmseq` · `roadnmbcd` | 도로명 계열 — **전부 소문자** | `종로66길 28` |

> `preDeposit`/`preMonthlyRent`/`contractType`/`useRRRight` 덕분에
> **갱신 계약의 인상률을 계산할 수 있다.** 전월세 분석의 핵심 필드다.
>
> **매매 공통 필드(`dealingGbn` `estateAgentSggNm` `cdealType` 등)가 없다.**
> 전월세에 `--fields`를 재사용하면 조용히 빠진다.

## 4. 오피스텔 매매 — 18개 ✅

공통 11개 + `offiNm`(오피스텔명) · `excluUseAr` · `floor` · `buildYear` ·
`buyerGbn` · `slerGbn` · `sggNm`(시군구명)

## 5. 연립다세대 매매 — 20개 ✅

공통 11개 + `mhouseNm`(건물명) · `houseType`(**`다세대` `연립`**) ·
`excluUseAr`(전용면적) · `landAr`(대지권면적) · `floor` · `buildYear` ·
`buyerGbn` · `slerGbn` · `rgstDate`

## 6. 단독다가구 매매 — 17개 ✅

공통 11개 + `houseType`(**`다가구` `단독`**) · `totalFloorAr`(연면적) ·
`plottageAr`(대지면적) · `buildYear` · `buyerGbn` · `slerGbn`

> **건물명도 전용면적도 없다.** 대표 면적은 `totalFloorAr`(연면적)다.

## 7. 토지 매매 — 16개 ✅

공통 11개 + `dealArea`(거래면적 ㎡) · `jimok`(지목, **`임야` `대` `전` `답`**) ·
`landUse`(용도지역, `개발제한구역` `제3종일반주거`) ·
`shareDealingType`(**`지분`** 여부) · `sggNm`

> `shareDealingType`이 `지분`이면 **필지 전체가 아니라 지분 거래**다.
> 단가를 낼 때 이걸 무시하면 결과가 틀어진다.

## 8. 상업업무용 매매 — 22개 ✅

공통 11개 + `buildingAr`(건물면적) · `plottageAr`(대지면적) ·
`buildingType`(**`일반` `집합`**) · `buildingUse`(**`기타`** 등) ·
`landUse` · `floor` · `buildYear` · `buyerGbn` · `slerGbn` ·
`shareDealingType` · `sggNm`

## 9. 공장창고 매매 — 22개 ✅

`RTMSDataSvcInduTrade`. **상업업무용과 필드 집합이 같다.**
서울 종로구엔 거래가 없어서 시흥시(`41390`)로 확인했다.

공통 11개 + `buildingAr` · `plottageAr` · `buildingType`(**`집합` `일반`**) ·
`buildingUse`(**`공장`** 등) · `landUse`(`준주거` 등) · `floor` · `buildYear` ·
`buyerGbn` · `slerGbn`(**`기타`** 값도 있다) · `shareDealingType` · `sggNm`

## 10. 전월세 4종 비교 ✅

아파트 25 · 오피스텔 18 · 연립다세대 18 · 단독다가구 **15**개.

| 필드 | 아파트 | 오피스텔 | 연립다세대 | 단독다가구 |
|---|---|---|---|---|
| `deposit` · `monthlyRent` | ✅ | ✅ | ✅ | ✅ |
| `preDeposit` · `preMonthlyRent` | ✅ | ✅ | ✅ | ✅ |
| `contractTerm` · `contractType` · `useRRRight` | ✅ | ✅ | ✅ | ✅ |
| `buildYear` · `sggCd` · `umdNm` | ✅ | ✅ | ✅ | ✅ |
| 건물명 | `aptNm` | `offiNm` | `mhouseNm` | **없음** |
| `excluUseAr`(전용면적) | ✅ | ✅ | ✅ | **없음** → `totalFloorAr` |
| `floor` | ✅ | ✅ | ✅ | **없음** |
| `jibun` | ✅ | ✅ | ✅ | **없음** |
| `sggNm` | 없음 | ✅ | 없음 | 없음 |
| `houseType` | 없음 | 없음 | ✅ (`다세대`) | ✅ (`단독`) |
| 도로명 계열(`roadnm*`) | ✅ | 없음 | 없음 | 없음 |
| `aptSeq` | ✅ | 없음 | 없음 | 없음 |

> **단독다가구 전월세가 가장 빈약하다** — 층·지번·전용면적·건물명이 전부 없다.
> 위치는 `umdNm`(읍면동)까지만, 규모는 `totalFloorAr`(연면적)만 나온다.
> 그래서 `_name` 파생 필드도 생기지 않는다.
>
> **도로명 필드는 아파트 전월세에만 있다.** 나머지 3종엔 아예 없다.
>
> `mhouseNm`이 `(1-833)` 처럼 **지번 형태로 오는 경우가 있다.** 건물명이
> 등록 안 된 다세대가 그렇다. 건물명으로 알고 그대로 보여 주면 이상해 보인다.

## 11. 🔴 해제된 거래 — `cdealType` ✅ 실측

값이 확정됐다.

| `cdealType` | 뜻 | 실측 비율 |
|---|---|---|
| `` (공란) | 정상 거래 | 2,829 / 2,900 |
| `O` | **해제된 거래** | **71 / 2,900 = 2.45%** |

`cdealDay`는 해제일이고 형식이 **`26.07.13`(YY.MM.DD)** 이다 —
`_dealDate`(`YYYY-MM-DD`)와도, `DEAL_YMD`(`YYYYMM`)와도 다른 세 번째 형식이다.

```
계약 2026-07-25  →  해제 2026-08-04   525,000,000원
계약 2026-07-10  →  해제 2026-07-13   663,000,000원
```

> **시세·평균가·최고가를 낼 때 해제 거래를 빼야 한다.**
> 2.45%면 무시할 수 없고, 특히 최고가는 한 건만 섞여도 답이 바뀐다.
>
> 래퍼가 `_cancelled`(bool) · `_cancelledDate`(정규화)를 붙이고,
> 해제 건이 있으면 **경고를 출력**한다. `--exclude-cancelled` 로 제외한다.
> **기본은 포함**이다 — 데이터를 조용히 버리지 않기 위해서다.

## 12. 미확인

정직하게 적어 둔다.

| 항목 | 상태 |
|---|---|
| 분양권 전매(`silv-trade`) 필드 | ❌ **해당 데이터셋 활용신청 미완료**(`code 30`). 신청하면 즉시 확인 가능 |
| `apt-trade-old`(구버전) 필드 차이 | ❌ 경로 생존만 확인 |
| `buildingUse` · `jimok` · `landUse` 값 목록 | 🟡 일부만 관측 |
| `useRRRight`(갱신요구권) 값 목록 | 🟡 표본에서 대부분 공란 |
| 채움률 전반 | 🟡 표본이 좁아 일반화 불가 |

## 10. 파생 필드 (래퍼가 계산)

`_` 로 시작하는 것은 **API가 준 값이 아니다.**

| 필드 | 계산 |
|---|---|
| `_dealAmountWon` | `dealAmount` 콤마 제거 × 10,000 |
| `_depositWon` · `_monthlyRentWon` · `_preDepositWon` · `_preMonthlyRentWon` | 위와 동일 |
| `_name` | `aptNm` → `offiNm` → `mhouseNm` 순으로 처음 채워진 것 |
| `_area` / `_areaField` | `excluUseAr` → `dealArea` → `totalFloorAr` → `buildingAr` → `plottageAr` 순, 그리고 어느 것을 썼는지 |
| `_dealDate` | `dealYear`-`dealMonth`-`dealDay` 를 `YYYY-MM-DD`로 |
| `_dealYm` | 그 행을 가져온 조회월 |
| `_cancelled` | `cdealType == "O"` 이면 `true` — **해제된 거래** |
| `_cancelledDate` | `cdealDay`(`26.07.13`)를 `2026-07-13` 로 |
| `_lawdCd` / `_regionName` | 그 행을 가져온 시군구 코드 / 이름 |

`--fields`로 필드를 걸러도 파생 필드는 항상 남는다.
