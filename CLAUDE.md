# CLAUDE.md — KR-Data-Skills

한국 공공데이터 API를 AI 에이전트용 스킬로 감싼 오픈소스 팩.
현재 상태와 다음 할 일은 **`docs/NEXT.md`가 단일 기준점**이다. 먼저 읽을 것.

## 🔴 git

이 폴더는 **자체 `.git`을 가진 독립 저장소**다. 부모 `D:\Claude-prj`는 로컬 전용
모노레포이고 원격이 없다.

- git 작업은 **이 폴더 안에서만** 한다. 부모에서 `git add .` 금지
- 커밋 전에 `git rev-parse --show-toplevel`이 `D:/Claude-prj/KR-Data-Skills`인지 확인
- `.env`는 절대 커밋하지 않는다 (`.gitignore`에 있음)

## 범위

**이 저장소는 스킬 팩(=1층)만 다룬다.** 그 위에 올릴 업종별 SaaS(=2층)는
별도 프로젝트다. 여기에 만들지 말 것.

## 새 스킬을 추가할 때 — 반드시 지킬 4가지

기존 `skills/g2b-bid-notice`를 그대로 베끼는 게 가장 빠르다.

1. **`--output` 필수** — API 응답을 컨텍스트에 쏟지 않는다. 파일로 쓰고
   필요한 부분만 읽는다. `--max-items`로 잘리면 `_meta.truncated`로 알린다
2. **라이선스 게이트** — `.licenses/<skill>_LICENSE.txt`가 없으면 약관 고지 후
   문구+타임스탬프를 기록하고 진행. SKILL.md 사전조건에 명시한다
3. **인증키 값 비노출** — `grep -sq`로 존재만 확인. 에러 메시지 마스킹까지 구현.
   `cat ~/.env` / `echo $KEY` 절대 금지
4. **MCP가 아니라 CLI 래퍼** — 토큰 효율 때문에 의도적으로 택한 구조다

### 구조

```
skills/<kebab-name>/          # 폴더명 = frontmatter의 name (Claude Code 설치용)
  SKILL.md                    # YAML frontmatter + 에이전트 지침
  scripts/*.py                # uv 인라인 메타데이터, 표준 라이브러리만
  references/*.md             # 선택. 스키마·필드·함정 기록
```

- **data.go.kr 계열은 `DATA_GO_KR_SERVICE_KEY` 하나를 공유한다.** 스킬마다
  다른 키 이름을 만들지 말 것
- 외부 의존성은 되도록 0. 네트워크 막힌 환경에서도 돌아야 한다
- SKILL.md의 `description`에 **사용자가 실제로 쓸 한국어 표현**을 넣는다.
  그게 스킬 자동 호출의 트리거다

## 이 개발기 특성 (Windows)

- **`jq`가 없다.** 문서에 `jq` 예제를 쓰지 말 것.
  `uv run python -c "import json; ..."`로 안내한다
- **cp949 한글 깨짐** — 스크립트에서 stdout을 utf-8로 재설정하고,
  파일 입출력에 `encoding="utf-8"`을 명시한다
- 시스템 Python은 3.14. `uv`가 스크립트에 맞는 버전(3.12)을 따로 잡는다
- **Bash 툴에서 포트 80(http)이 타임아웃된다.** 모든 API 호출은 `https://`로

## 검증 습관

인증키 없이도 확인할 수 있는 것이 많다. 추측으로 문서를 쓰지 말 것.

- data.go.kr은 **라우팅이 인증보다 먼저**다. 더미 키로 호출하면
  `code 30`(경로 유효·키만 틀림) vs `code 12`(경로 없음)로 갈린다.
  `probe-endpoints`가 이걸 쓴다
- **확인한 것과 추정한 것을 문서에서 구분한다.** 미검증이면 미검증이라고 쓴다.
  `references/fields.md` 상단의 경고 블록이 그 예다
