---
name: mfds-drug-info
description: >
  식품의약품안전처 의약품개요정보(e약은요)를 조회한다. 일반의약품·전문의약품의
  효능, 사용법, 주의사항, 상호작용, 부작용, 보관법을 제품명·업체명·증상으로 찾는다.
  "타이레놀 효능 알려줘", "두통에 먹는 약 뭐 있어", "이 약 부작용", "이 약 같이 먹어도 돼?",
  "임신했는데 먹어도 되는 약", "유한양행 약 목록", "약 보관법" 같은 요청에 사용한다.
---

# 식약처 의약품개요정보 (e약은요)

## 🔴 먼저 읽을 것 — 이 데이터의 성격

**이건 의약품 허가정보가 아니라 "일반인용 복약 안내문"이다.** 식약처가 소비자용으로
쉽게 풀어 쓴 문장이 그대로 들어 있다. 성분·함량·보험코드·허가일자 같은
전문 정보는 **없다**.

- 전체가 **4,775건**뿐이다(2026-08-05 실측). 국내 허가 의약품 전체가 아니다
- 필드 14개 전부가 서술형 문장이다. 구조화된 코드값이 거의 없다
- **의학적 판단의 근거로 쓰면 안 된다.** 사용자에게 답할 때 반드시
  "식약처 e약은요 안내문 기준"임을 밝히고, 복용 판단은 의사·약사와 상의하도록 안내한다

## 사전 조건

1. **`uv`** — `uv` 스킬의 Setup을 따라 `uv`가 설치돼 PATH에 있는지 확인한다.
2. **인증키** — `credentials` 스킬의 프로토콜을 따른다. 필요한 변수는
   `DATA_GO_KR_SERVICE_KEY` 하나다. **작업 시작 전에 먼저 확인할 것**:

   ```bash
   grep -sq "^DATA_GO_KR_SERVICE_KEY=" .env ~/.env
   ```

   실패하면 즉시 멈추고 사용자에게 발급을 안내한다. 스크립트를 먼저 돌리지 말 것.

   > **인증키는 하나지만 활용신청은 데이터셋마다 따로 해야 한다.**
   > 이 스킬은 <https://www.data.go.kr/data/15075057/openapi.do> 활용신청이 필요하다.
   > 개발계정은 자동승인이다. `check-key`로 확인한다.

3. **이용약관 고지** — 워크스페이스 루트에 `.licenses/mfds_drug_info_LICENSE.txt`가
   없으면, 이용약관을 확인하도록 사용자에게 고지하고 그 문구와 타임스탬프를
   그 파일에 기록한 뒤 진행한다.

## 핵심 규칙

- **반드시 래퍼를 쓴다.** `curl` 직접 호출 금지. 봉투 해석·중복 병합·입력 검증이
  전부 래퍼에 있다.
- **`--output`은 필수다.** 응답을 컨텍스트에 쏟지 않는다.
- **결과 파일을 통째로 읽지 말 것.** 한 건의 본문이 수천 자다. 7건짜리 `--preset full`이
  29 KB다. 필요한 필드만 골라 읽는다.
- **호출 예산** — 개발계정 **일 10,000건**. 전수 수집도 10회면 끝나서 여유롭다.
- **인증키 값을 출력하지 않는다.** `cat .env` / `echo $KEY` 금지.
- 이 스킬을 썼으면 결과 보고에 그 사실을 밝힌다.

## 명령

```bash
S=skills/mfds-drug-info/scripts/mfds_api.py

# 진단
uv run $S check-key                     # 키가 통하는지 (키 값은 출력 안 함)
uv run $S probe-endpoints               # 키 없이 경로 생존 확인

# 조회 — 조건은 조합할 수 있다(AND)
uv run $S search --name 타이레놀 --output out/t.json
uv run $S search --efficacy 두통 --preset brief --output out/h.json
uv run $S search --company 유한양행 --preset brief --limit 500 --output out/y.json
uv run $S search --item-seq 195700020 --preset full --output out/one.json

# 전수 (4,775건 / 10회 호출)
uv run $S search --all --preset brief --limit 500 --max-pages 12 --max-items 6000 \
  --output out/all.json

# 탈출구
uv run $S raw --params '{"itemName":"타이레놀"}' --output out/r.json
```

### 조회 조건

| 플래그 | API 파라미터 | 성격 |
|---|---|---|
| `--name` | `itemName` | 제품명 **부분일치** |
| `--company` | `entpName` | 업체명 **부분일치** |
| `--item-seq` | `itemSeq` | 품목기준코드 정확일치 |
| `--efficacy` | `efcyQesitm` | **효능 본문 검색** — 증상으로 약을 찾는 핵심 기능 |
| `--usage` | `useMethodQesitm` | 사용법 본문 |
| `--warning` | `atpnWarnQesitm` | 경고 본문 |
| `--caution` | `atpnQesitm` | 주의사항 본문 |
| `--interaction` | `intrcQesitm` | 상호작용 본문 |
| `--side-effect` | `seQesitm` | 부작용 본문 |
| `--storage` | `depositMethodQesitm` | 보관법 본문 |
| `--open-date` | `openDe` | 공개일자 `YYYYMMDD` 앞자리 일치 |
| `--updated` | `updateDe` | 수정일자 — **8자까지만 동작**(아래 함정 참조) |

### 필드 묶음 (`--preset`)

본문이 길어서 프리셋 선택이 곧 컨텍스트 예산이다. 같은 7건 기준 실측:

| preset | 필드 | 크기 |
|---|---|---|
| `brief` | itemSeq, itemName, entpName | **3.1 KB** |
| `core` (기본) | brief + efcyQesitm, useMethodQesitm | 6.5 KB |
| `full` | 14개 전부 | **29.0 KB** |

**목록을 보여 줄 때는 `brief`, 특정 약을 설명할 때만 `full`을 쓴다.**
본문이 필요하지만 건수가 많으면 `--truncate-text 500`을 쓴다(자른 행에 `_truncated`가 붙는다).

## 🔴 함정 — 실측으로 확인된 것들

### 1. 잘못된 조건에도 "정상 0건"이 온다

```
--name 존재하지않는약XYZ  →  resultCode "00", totalCount 0
```

에러가 아니다. **"그런 약은 없습니다"라고 단정하지 말 것.** 오타·띄어쓰기·
제품명 표기 차이를 먼저 의심한다. 래퍼가 0건이면 보낸 조건을 같이 출력한다.

### 2. 🔴 모르는 파라미터는 조용히 무시된다

```
bizrno=1108100102  →  totalCount 4775 (전체 그대로)
```

필터가 안 먹었는데 정상 응답이다. 래퍼는 **화이트리스트로 막고**, 결과 건수가
전체(4,775)와 같으면 경고를 띄운다. **이 경고가 보이면 결과를 "조건에 맞는 것"이라고
보고하지 말 것.**

### 3. 🔴 `updateDe`는 9자 이상이면 무조건 0건이다

실측 (로컬 전수 집계와 대조):

| 값 | 길이 | API | 실제 |
|---|---|---|---|
| `2021` | 4자 | 1,931 | 1,931 ✅ |
| `2021-01` | 7자 | 1,157 | 1,157 ✅ |
| `2021-01-` | 8자 | 1,157 | 1,157 ✅ |
| `2021-01-2` | 9자 | **0** | 1,157 🔴 |
| `2021-01-29` | 10자 | **0** | 1,157 🔴 |

**응답에는 `2024-05-09` 형태로 오는데 그 값으로 검색하면 0건이다.**
래퍼가 전송 전에 막는다. 하루 단위가 필요하면 `--all`로 받아 `_updateDate`로 거른다.

### 4. 같은 `itemSeq`가 여러 행으로 온다

전수 4,775행 중 **14개 품목이 2~3행**으로 쪼개져 있다. 달라지는 필드는
**`itemImage` 하나뿐**이고 나머지 13개는 전부 같다 — 이미지가 여러 장인 약이다.

래퍼가 **기본으로 병합**하고 이미지를 `_itemImages` 배열로 모은다
(4,775행 → 4,758건, 합친 행 17건). 정보 손실이 없어서 기본값으로 뒀다.
원본 행이 필요하면 `--no-merge`.

### 5. 날짜 필드 두 개의 형식이 다르다

```
openDe    "20210129"     (하이픈 없음)
updateDe  "2024-05-09"   (하이픈 있음)
```

래퍼가 `_openDate` · `_updateDate`로 둘 다 `YYYY-MM-DD`로 맞춰 준다.
**원본 필드로 날짜를 비교하지 말 것.**

### 6. 채움률이 필드마다 크게 다르다

표본 500건 실측. **없는 걸 "해당 없음"으로 오해하면 안 된다.**

| 필드 | 채움률 |
|---|---|
| entpName · itemName · itemSeq · openDe · updateDe · bizrno | 100% |
| efcyQesitm(효능) · useMethodQesitm(사용법) | 99% |
| depositMethodQesitm(보관) · atpnQesitm(주의) | 98% |
| seQesitm(부작용) | 90% |
| intrcQesitm(상호작용) | 58% |
| itemImage | 54% |
| **atpnWarnQesitm(경고)** | **16%** |

`intrcQesitm`이 비어 있다고 **"상호작용이 없다"고 말하면 안 된다.**
안내문에 안 적혀 있을 뿐이다.

### 7. `numOfRows` 상한은 500이다

넘기면 `code 11 NO MANDATORY REQUEST PARAMETERS ERROR!`가 오는데
**메시지가 실제 원인과 다르다.** 뒤쪽에 `numOfRows maximum is =[500]`이 붙어 있다.
래퍼가 500으로 낮춰 호출하고 알린다.

### 8. `type=json`을 빼면 봉투가 바뀐다

| | `type=json` | 생략 |
|---|---|---|
| `items` | 배열 (1건이어도) | `{"item": {...}}` — 1건이면 dict |
| 빈 값 | `null` | `""` |
| 숫자 | `1` | `"1"` |

래퍼가 항상 붙인다. `raw`를 쓸 때도 자동으로 들어간다.

## 사용자에게 답할 때

- **출처를 밝힌다** — "식약처 e약은요 안내문 기준"
- **복약 판단은 의사·약사와 상의**하도록 안내한다. 특히 상호작용·임부·수유부 관련
- 필드가 비어 있으면 **"정보 없음"**이라고 하고 "해당 없음"으로 바꿔 말하지 않는다
- 잘림·무시 경고가 떴으면 **그 사실을 사용자에게 그대로 전한다**

## 참고

- 데이터셋: <https://www.data.go.kr/data/15075057/openapi.do>
- 필드 상세·실측 수치: `references/fields.md`
- 엔드포인트·에러코드: `references/endpoints.md`
