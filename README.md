# KR-Data-Skills

한국 공공데이터 API를 **AI 에이전트가 직접 조회할 수 있게** 감싼 오픈소스 스킬 팩.

데이터는 이미 공개돼 있다. 아직 아무도 **AI가 쓸 수 있는 형태로** 감싸지 않았을 뿐이다.

## 뭐가 달라지나

**스킬이 없을 때**

> "이번 주 우리 회사가 넣을 만한 입찰 공고 있어?"
> → "나라장터에서 확인해 보세요."

**스킬이 있을 때**

> 에이전트가 조달청 API를 실제로 호출 → 공고 400건을 파일로 저장 →
> 업종·실적·지역 조건으로 필터
> → "3건 맞습니다. A는 마감 8/12, 추정가격 8천만원인데 실적 요건이 미달이라
> 컨소시엄이 필요합니다."

## 지금 들어 있는 것

| 스킬 | 내용 | 상태 |
|---|---|---|
| [`g2b-bid-notice`](skills/g2b-bid-notice) | 조달청 나라장터 입찰공고 — 목록·조건검색·기초금액·면허제한·참가가능지역·변경이력 (오퍼레이션 18개) | ✅ **실데이터 검증 완료** |
| [`credentials`](skills/credentials) | 인증키 안전 취급 프로토콜 | ✅ |
| [`uv`](skills/uv) | Python 실행 환경 보장 | ✅ |

`g2b-bid-notice`는 실제 인증키로 6개 오퍼레이션 계열 × 5개 업무구분을 호출해
응답 필드를 확정했다. 무엇을 확인했고 무엇이 아직 미확인인지는
[`references/fields.md`](skills/g2b-bid-notice/references/fields.md)에
구분해 적어 뒀다.

## 설치 (Claude Code)

```bash
git clone https://github.com/haemiru/KR-Data-Skills.git
cp -r KR-Data-Skills/skills/* ~/.claude/skills/
```

`~/.claude/skills/<이름>/SKILL.md` 구조가 되면 된다. Claude Code가 요청 내용에
맞는 스킬을 알아서 불러온다.

> 다른 에이전트(Antigravity/Gemini 등)는 스킬 디렉터리 경로가 다르다. 각 도구
> 문서를 확인할 것.

## 빠른 시작

```bash
# 저장소 루트에서 실행한다 (.env 를 여기 둔다)

# 1) 인증키 없이 API 경로가 살아 있는지부터 확인 (진단용)
uv run skills/g2b-bid-notice/scripts/g2b_api.py probe-endpoints

# 2) 공공데이터포털에서 인증키 발급 (자동승인, 즉시)
#    https://www.data.go.kr/data/15129394/openapi.do → 활용신청 → 개발계정
#    아래를 그대로 붙여넣고 **엔터를 친 뒤에** 키를 입력한다.
#    입력은 화면에 보이지 않는다. 키를 프롬프트 문구 안에 넣지 말 것.
printf "Enter DATA_GO_KR_SERVICE_KEY (typing hidden): " && read -s val && echo && echo "DATA_GO_KR_SERVICE_KEY=$val" >> .env && echo "Saved."

# 3) 키가 실제로 통하는지 확인 (키 값은 출력되지 않는다)
uv run skills/g2b-bid-notice/scripts/g2b_api.py check-key

# 4) 최근 7일 용역 공고 (차수 중복 제거 + 업무구분별 기본 필드)
uv run skills/g2b-bid-notice/scripts/g2b_api.py search --kind servc --days 7 \
  --dedup latest --preset core --output out/g2b.json

# 5) "충북 지역제한 용역 중 추정가격 5천만원 이상" — 지역 근거까지 붙여서
uv run skills/g2b-bid-notice/scripts/g2b_api.py search-nara --kind servc --days 7 \
  --region "충청북도" --price-from 50000000 \
  --dedup latest --join region --preset core \
  --limit 999 --output out/chungbuk.json
```

5번이 이 저장소가 노리는 지점이다. 나라장터 API는 지역으로 **필터링은 되지만
응답에 지역 필드가 없어서**, 결과가 정말 그 지역인지 응답만으로는 증명할 수 없다.
`--join region`이 참가가능지역 오퍼레이션을 붙여 근거를 만든다.

`.env.example`을 복사해 써도 된다 — `cp .env.example .env` 후 값만 채운다.
래퍼는 현재 디렉터리에서 `.git`이 있는 곳까지 거슬러 올라가며 `.env`를 찾으므로,
`cd skills/g2b-bid-notice` 후에 실행해도 루트의 `.env`를 읽는다.

`uv`가 없으면 [`skills/uv`](skills/uv)를 먼저 본다.

## 설계 원칙

이 저장소의 진짜 자산은 API 목록이 아니라 아래 네 가지다.
새 스킬을 추가할 때 반드시 계승한다.

**1. `--output` 파일 강제**
API 응답을 에이전트 컨텍스트에 쏟지 않는다. 항상 파일로 쓰고 필요한 부분만 읽는다.
응답이 크면 자동으로 잘리고 `_meta.truncated`로 알린다.

**2. 라이선스 게이트**
워크스페이스 루트에 `.licenses/<skill>_LICENSE.txt`가 없으면, 사용자에게 이용약관을
고지하고 그 문구와 타임스탬프를 파일에 기록한 뒤 진행한다.

**3. 인증키 값 비노출**
키 값을 컨텍스트·터미널·대화에 절대 출력하지 않는다. 존재만 확인한다.

```bash
grep -sq "^DATA_GO_KR_SERVICE_KEY=" .env ~/.env
```

에러 메시지에 키가 섞여 나가는 것까지 래퍼가 자동으로 마스킹한다.

키는 **저장소 루트 `.env`**에 둔다(`.gitignore` 대상). 탐색 순서는
환경변수 → 현재 디렉터리부터 저장소 루트까지의 `.env` → `~/.env`(폴백)다.

**4. MCP 서버가 아니라 CLI 래퍼**
의도적인 선택이다. 토큰 효율이 이유다. 도구 정의를 상시 로드하지 않고,
필요할 때 스킬 문서만 읽으면 된다.

### 그 밖의 규약

- 스킬 1개 = `SKILL.md`(YAML frontmatter + 지침) + `scripts/*.py` + `references/`(선택)
- 폴더명은 frontmatter의 `name`과 같게(케밥케이스). Claude Code 설치가 그대로 된다
- 의존성은 `uv` 인라인 메타데이터로. **되도록 표준 라이브러리만 쓴다**
- SKILL.md에 "직접 `curl` 쓰지 말고 제공된 래퍼를 쓸 것"을 명시한다.
  레이트리밋·재시도·에러 해석이 전부 래퍼에 있다
- **미검증 정보는 미검증이라고 쓴다.** 확인한 것과 추정한 것을 문서에서 구분한다

## 왜 CLI 래퍼가 필요한가 — 나라장터의 경우

이 API를 감싸면서 실제로 밟은 것들이다. 래퍼가 전부 처리한다.

| 함정 | 내용 |
|---|---|
| 죽은 경로가 퍼져 있음 | 블로그·예제 다수가 쓰는 `/1230000/BidPublicInfoService/...`는 폐기됐다. `/1230000/ad/`가 필요하다 |
| 인증키 이중 인코딩 | 포털이 Encoding/Decoding 키를 둘 다 준다. Encoding 키를 다시 urlencode하면 "등록되지 않은 서비스키"로 떨어진다 |
| 명세가 docx | 웹에서 읽을 수 있는 오퍼레이션 목록이 없다 → 키 없이 경로 생존을 판별하는 `probe-endpoints`를 만들었다 |
| 응답 형태가 흔들림 | `items`가 리스트/`{"item":...}`/`""`/`null`로 왔다 갔다 한다 |
| 인증 에러는 봉투가 다름 | `type=json`을 줘도 XML로 오거나 `OpenAPI_ServiceResponse` 봉투로 온다 |
| 조회기간 제한 | 장기간 조회가 거부된다 → 30일 단위 자동 분할 |
| Windows 한글 깨짐 | cp949 기본값 → stdout을 utf-8로 고정 |

자세한 내용: [`skills/g2b-bid-notice/references/endpoints.md`](skills/g2b-bid-notice/references/endpoints.md)

## 로드맵

- [x] 저장소 골격 + 공통 스킬(`credentials`, `uv`)
- [x] 나라장터 입찰공고 스킬 — 래퍼·문서·엔드포인트 실측
- [x] 실데이터 검증 → 응답 필드·`inqryDiv`·페이지네이션 확정
- [x] 검증에서 드러난 구멍 보강 — `--join` · `--dedup` · `--preset`
- [ ] 국토교통부 실거래가 (아파트·오피스텔·단독·토지 등)
- [ ] KIPRIS 특허 / 식약처 / 국가법령정보 등 확장

## 라이선스

Apache License 2.0. [LICENSE](LICENSE) 참조.

각 공공데이터 API의 이용약관은 **별개다.** 스킬이 알려 주는 약관을 각자 확인할 것.
