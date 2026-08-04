---
name: g2b-bid-notice
description: >
  조달청 나라장터(G2B) 입찰공고를 조회한다. 물품·용역·공사·외자·기타 업무구분별
  공고 목록, 공고명·발주기관·지역·업종·추정가격 조건 검색, 기초금액, 면허제한,
  참가가능지역, 변경이력을 다룬다. "이번 주 입찰공고", "우리가 넣을 만한 공고",
  "나라장터 공고 찾아줘", "관급 공사 발주 현황", "특정 기관 발주 내역",
  "추정가격 N억 이상 용역" 같은 요청에 사용한다.
---

# 나라장터 입찰공고 (조달청 G2B)

## 사전 조건

1. **`uv`** — `uv` 스킬의 Setup을 따라 `uv`가 설치돼 PATH에 있는지 확인한다.
2. **인증키** — `credentials` 스킬의 프로토콜을 따른다. 필요한 변수는
   `DATA_GO_KR_SERVICE_KEY` 하나다. **작업 시작 전에 먼저 확인할 것**:

   ```bash
   grep -sq "^DATA_GO_KR_SERVICE_KEY=" .env ~/.env
   ```

   **`.env`는 저장소 루트에 둔다.** 위 명령은 루트에서 실행하는 걸 전제한다.
   래퍼는 현재 디렉터리에서 `.git`이 있는 곳까지 거슬러 올라가며 `.env`를 찾으므로,
   스크립트 자체는 `skills/g2b-bid-notice/` 안에서 실행해도 된다.

   실패하면(비0 종료코드) 즉시 멈추고 아래 "인증키 발급"을 사용자에게 안내한다.
   스크립트를 먼저 돌려 보지 말 것.

3. **이용약관 고지** — 워크스페이스 루트에 `.licenses/g2b_bid_notice_LICENSE.txt`가
   없으면, (1) https://www.data.go.kr/data/15129394/openapi.do 의 이용약관을
   확인하도록 사용자에게 눈에 띄게 고지하고, (2) 고지 문구와 타임스탬프를 그
   파일에 기록한 뒤 진행한다.

## 인증키 발급 (없을 때만)

1. https://www.data.go.kr 회원가입 (공동인증서 없이 이메일로 가능)
2. https://www.data.go.kr/data/15129394/openapi.do → **활용신청**
   → **개발계정**. 심의는 **자동승인**이라 즉시 발급된다.
3. 마이페이지 → 오픈API → 개발계정 상세에서 **일반 인증키**를 복사한다.
   `Encoding` / `Decoding` 두 형태가 보이는데 **어느 쪽이든 상관없다** —
   래퍼가 자동 판별한다.
4. 사용자에게 아래 명령을 **저장소 루트에서 직접** 실행하도록 안내한다.
   키를 채팅에 붙여넣게 하지 말 것. 입력은 화면에 표시되지 않는다.

   ```bash
   printf "Enter DATA_GO_KR_SERVICE_KEY (typing hidden): " && read -s val && echo && echo "DATA_GO_KR_SERVICE_KEY=$val" >> .env && echo "Saved."
   ```

   > [!WARNING]
   > **명령을 그대로 붙여넣고, 엔터를 친 뒤에 키를 입력하라고 명시할 것.**
   > 프롬프트 문자열(`"Enter … : "`) 안에 키를 넣으면 `read -s`가 무의미해지고
   > 키가 기록에 남는다. 게다가 `read`가 입력을 못 받으면 `&&` 체인이 끊겨
   > **저장도 안 된다.** `"Saved."`가 안 찍혔으면 실패한 것이다.

5. 검증 — 키 값을 출력하지 않고 실제 호출 1건으로 확인한다:

   ```bash
   uv run scripts/g2b_api.py check-key
   ```

> [!NOTE]
> 발급 직후 키가 반영되기까지 **최대 1시간** 걸릴 수 있다. 방금 발급했는데
> `code 30`이 나오면 키를 의심하기 전에 시간을 두고 재시도할 것.

## 핵심 규칙

- **반드시 래퍼를 쓴다.** `curl`로 직접 호출하지 말 것. 레이트리밋, 재시도,
  인증키 형태 자동 판별, 기간 분할, 에러코드 해석이 전부 래퍼에 있다.
- **`--output`은 필수다.** 응답을 컨텍스트에 쏟지 않는다. 파일로 쓴 뒤
  필요한 부분만 읽는다.
- **`--fields`로 먼저 줄인다.** 공고 1건에 필드가 수십 개다. 필요한 것만 남겨야
  파일이 작아지고 읽기 쉽다.
- **호출 예산을 아낀다.** 개발계정은 **일 1,000건**이다. `--max-pages`는 기본 1이고,
  올린 만큼 호출이 늘어난다. 먼저 좁은 기간으로 `_meta.total_count`를 확인하고
  범위를 정할 것.
- **인증키 값을 출력하지 않는다.** `cat .env`, `echo $DATA_GO_KR_SERVICE_KEY`
  같은 명령을 절대 쓰지 말 것. 존재 확인은 `grep -sq`로만 한다.
- 이 스킬을 썼으면 결과 보고에 그 사실을 밝힌다.

## 명령

전부 `skills/g2b-bid-notice/` 에서 실행한다.

### 1. 업무구분별 공고 목록 — `search`

가장 기본. 기간 안에 올라온 공고를 업무구분으로 훑는다.

```bash
uv run scripts/g2b_api.py search \
  --kind servc \
  --days 7 \
  --fields "bidNtceNo,bidNtceNm,ntceInsttNm,dminsttNm,bidNtceDt,bidClseDt,presmptPrce,bidNtceDtlUrl" \
  --limit 100 --max-pages 3 \
  --output /tmp/g2b_servc_7d.json
```

- `--kind` — `thng`(물품) `servc`(용역) `cnstwk`(공사) `frgcpt`(외자) `etc`(기타)
- `--days N` — 오늘 포함 최근 N일. 또는 `--from 2026-07-01 --to 2026-07-31`

### 2. 조건 검색 — `search-nara`

나라장터 검색조건 계열(`...PPSSrch`). 공고명·기관·지역·업종·가격으로 좁힌다.
**대상이 특정돼 있으면 `search`보다 이쪽이 호출 예산을 훨씬 아낀다.**

```bash
uv run scripts/g2b_api.py search-nara \
  --kind cnstwk \
  --region "충청북도" \
  --title "청소" \
  --price-from 50000000 \
  --days 30 \
  --fields "bidNtceNo,bidNtceNm,ntceInsttNm,bidClseDt,presmptPrce" \
  --output /tmp/g2b_cheongju.json
```

| 플래그 | API 파라미터 | 뜻 |
|---|---|---|
| `--title` | `bidNtceNm` | 공고명 포함 |
| `--notice-inst` | `ntceInsttNm` | 공고기관명 |
| `--demand-inst` | `dminsttNm` | 수요기관명 |
| `--region` | `prtcptLmtRgnNm` | 참가제한지역명 (예: `충청북도`) |
| `--industry-name` / `--industry-code` | `indstrytyNm` / `indstrytyCd` | 업종명 / 업종코드 |
| `--price-from` / `--price-to` | `presmptPrceBgn` / `presmptPrceEnd` | 추정가격 범위 |
| `--ref-no` | `refNo` | 참조번호 |

> ⚠️ **`--region` / `--industry-*`는 필터로는 동작하지만 응답에 되돌아오지 않는다.**
> `prtcptLmtRgnNm` `indstrytyNm` `indstrytyCd`는 요청 전용 파라미터라서
> 결과 항목에 그 필드가 없다. 사용자에게 "이 공고의 제한지역은 ○○"라고
> 보고하려면 `region-limit`·`license-limit`을 따로 호출해
> `bidNtceNo`+`bidNtceOrd`로 조인해야 한다. (공사 `cnstwk`는 예외 —
> 응답에 `cnstrtsiteRgnNm`(공사현장 지역명)이 있다)
>
> **`--price-from`은 부가세 제외 금액이다.** `presmptPrce` 기준이고,
> `presmptPrce + VAT = asignBdgtAmt`(배정예산)가 표본 전건에서 성립했다.
> 사용자가 "예산 1억"이라고 하면 어느 쪽인지 확인할 것.

### 3. 기초금액 — `basis-amount`

낙찰가 예측·투찰 판단의 재료. **`--kind`는 `thng`/`servc`/`cnstwk`만 된다.**

```bash
uv run scripts/g2b_api.py basis-amount --kind cnstwk --days 7 \
  --output /tmp/g2b_basis.json
```

### 4. 면허제한 — `license-limit`

우리 회사 면허로 들어갈 수 있는 공고인지 거르는 데 쓴다. 업무구분 인자 없음.

```bash
uv run scripts/g2b_api.py license-limit --days 7 --output /tmp/g2b_license.json
```

### 5. 참가가능지역 — `region-limit`

지역제한 공고를 거른다. 업무구분 인자 없음.

```bash
uv run scripts/g2b_api.py region-limit --days 7 --output /tmp/g2b_region.json
```

### 6. 변경이력 — `change-history`

마감일 연기·금액 정정 등을 추적한다. **`thng`/`servc`/`cnstwk`만 지원한다.**

```bash
uv run scripts/g2b_api.py change-history --kind servc --days 7 \
  --output /tmp/g2b_changes.json
```

### 7. 탈출구 — `raw`

위 명령이 못 덮는 조합이 필요할 때만.

```bash
uv run scripts/g2b_api.py raw \
  --operation getBidPblancListInfoServc \
  --params '{"inqryDiv":"1","inqryBgnDt":"202608010000","inqryEndDt":"202608042359"}' \
  --output /tmp/g2b_raw.json
```

### 8. 진단 — `check-key` / `probe-endpoints`

```bash
uv run scripts/g2b_api.py check-key          # 키가 실제로 통하는지 (키 값 출력 안 함)
uv run scripts/g2b_api.py probe-endpoints    # 키 없이 오퍼레이션 경로 생존 확인
```

`probe-endpoints`는 인증키가 필요 없다. 명세가 docx로만 배포돼 경로가 바뀌는
API라, `code 12`(경로 없음)와 `code 30`(경로는 살아있고 키만 틀림)의 차이로
18개 오퍼레이션의 생존을 확인한다.

> 이 두 명령은 데이터가 아니라 진단 결과를 돌려주므로 `--output`이 선택이다.
> 데이터를 가져오는 나머지 모든 명령에서는 필수다.

## 출력 형식

래퍼는 API의 중첩 봉투를 벗기고 아래 모양으로 정규화해 저장한다.

```json
{
  "_meta": {
    "operation": "getBidPblancListInfoServc",
    "inqry_bgn_dt": "202607290000",
    "inqry_end_dt": "202608042359",
    "date_chunks": 1,
    "api_calls": 3,
    "pages_fetched": 3,
    "total_count": 412,
    "returned": 300,
    "truncated": false
  },
  "items": [ { "bidNtceNo": "...", "bidNtceNm": "..." } ]
}
```

- `total_count` — API가 알려 준 전체 건수. `returned`보다 크면 아직 안 가져온 게 있다.
- `truncated: true` — `--max-items`(기본 2000)에 걸려 잘렸다는 뜻.
- 파일에서 읽을 때는 `items[*]`의 필요한 필드만 볼 것. 전체를 통째로 읽지 말 것.

### 🔴 보고 전에 반드시 중복 제거

**같은 공고번호가 차수(`bidNtceOrd`)만 다르게 여러 행으로 온다.**
실측에서 300건 중 8건이 `000`/`001` 쌍이었다(공고명 동일, 공고일시만 몇 시간 차이).

- 행 단위 유일 키 = **`(bidNtceNo, bidNtceOrd)`**
- **사용자에게 공고 목록을 보고할 때는 `bidNtceNo`로 묶어 `bidNtceOrd`
  최댓값(=최신 차수)만 남긴다.** 안 그러면 같은 공고를 두 번 보고하게 된다

```bash
uv run python -c "
import json,sys; sys.stdout.reconfigure(encoding='utf-8')
d=json.load(open(r'/tmp/g2b.json',encoding='utf-8'))
latest={}
for i in d['items']:
    k=i['bidNtceNo']
    if k not in latest or i['bidNtceOrd']>latest[k]['bidNtceOrd']: latest[k]=i
print(len(d['items']),'행 ->',len(latest),'공고')
"
```

정렬은 `bidNtceDt` 내림차순이 **아니다**(실측). 순서를 믿고 앞부분만 읽지 말 것.

### 업무구분을 바꾸면 `--fields`도 바꾼다

필드 집합이 업무구분마다 다르다 — 용역 113 · 공사 143 · 물품 101 ·
외자 97 · 기타 38개. 없는 필드를 `--fields`에 넣으면 **조용히 빠진다.**
특히 `etc`(기타)는 `dminsttCd` · `ntceInsttOfclTelNo` · `sucsfbidMthdNm`조차
없고, 외자(`frgcpt`)에는 `VAT` · `asignBdgtAmt`가 없다.
자세한 차이는 `references/fields.md` §11.

`jq`가 없는 환경이면(이 저장소의 기본 개발기가 그렇다) 파이썬으로 읽는다:

```bash
uv run python -c "import json;d=json.load(open(r'/tmp/g2b.json',encoding='utf-8'));print(d['_meta']['total_count']);[print(i.get('bidNtceNm')) for i in d['items'][:10]]"
```

## 자주 밟는 함정

| 증상 | 원인 | 해법 |
|---|---|---|
| `code 12` NO_OPENAPI_SERVICE_ERROR | 옛 경로 `/1230000/BidPublicInfoService/...` 사용. **폐기됐다** | `/1230000/ad/`가 들어간 현재 경로. 래퍼는 이미 맞다 |
| `code 30` 등록되지 않은 서비스키 | Encoding 키를 다시 urlencode해 **이중 인코딩** | 래퍼가 자동 판별한다. 직접 curl 쓰지 말 것 |
| `code 30`인데 키는 맞음 | 발급 직후 미반영 | 최대 1시간 기다렸다 재시도 |
| `code 22` | 일 1,000건 한도 초과 | 다음 날까지 대기, 또는 운영계정 신청 |
| 결과 0건인데 에러는 아님 | `--inqry-div 2`를 썼다 | **`2`는 날짜 범위로 항상 0건이다**(실측). 일반 조회는 `1`(기본값), 변경공고만 보려면 `3` |
| 같은 공고가 두 번 보임 | `bidNtceOrd`가 다른 행 | `bidNtceNo`로 묶어 최신 차수만 남길 것 (위 "중복 제거") |
| 제한지역·업종을 결과에서 못 찾음 | 요청 전용 파라미터라 응답 필드에 없음 | `region-limit` / `license-limit`을 따로 호출해 조인 |
| 긴 기간 조회 실패 | API가 장기간 조회를 거부 | 래퍼가 기본 30일 단위로 자동 분할한다(`--chunk-days`) |
| 한글이 깨짐 | Windows cp949 | 래퍼가 stdout을 utf-8로 고정한다. 직접 스크립트를 짤 땐 `encoding="utf-8"` 명시 |

## 참고

- 오퍼레이션 18개 전체 목록과 실측 근거: `references/endpoints.md`
- **응답 필드: `references/fields.md` — 실측 확정(2026-08-05).**
  업무구분별 필드 차이(§11), 조인 관계(§12), 남은 미확인 항목(§13)까지 있다.
  필드 뜻을 사용자에게 단정해 말하기 전에 §13을 확인할 것
- 실측 원본: `references/endpoint-probe.json`
- 데이터셋: https://www.data.go.kr/data/15129394/openapi.do
