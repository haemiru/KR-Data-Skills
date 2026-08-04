---
name: credentials
description: >-
  API 키를 안전하게 다루는 표준 프로토콜. 키의 존재만 확인하고 값은 절대
  컨텍스트·터미널·대화에 노출하지 않는다. 다른 스킬이 인증키를 요구할 때 사용한다.
---

# 인증키 안전 취급 프로토콜

KR-Data-Skills의 스킬 대부분은 공공데이터포털(data.go.kr) 인증키를 요구한다.
이 문서는 그 키를 **대화 기록과 에이전트 컨텍스트에 흘리지 않고** 확인·요청하는
표준 절차를 정의한다.

## 1. 존재 확인 (값을 읽지 않는다)

인증키가 필요한 스킬이 요청과 관련 있어 보이는 **즉시**, 다른 작업을 하기 전에
키가 있는지부터 확인한다.

**핵심: 값을 출력하거나 컨텍스트에 읽어들이지 않고 확인해야 한다.**

```bash
grep -sq "^DATA_GO_KR_SERVICE_KEY=" ~/.env
```

`-q`는 내용을 출력하지 않고, `-s`는 `~/.env`가 아예 없을 때도 조용히 실패한다.
`CREDENTIAL_NAME` 자리에는 호출한 스킬이 요구하는 실제 변수명을 넣는다.

- **종료코드 0** → 키가 있다. 진행한다.
- **종료코드 0이 아님** → 키가 없다(또는 `.env`가 없다). **즉시 멈추고**
  아래 §2로 사용자에게 등록을 안내한다.

> [!CRITICAL]
> 확인에 실패하면 해당 스킬의 스크립트를 **하나도 실행하지 말 것.**
> 그리고 "키가 없습니다"라고만 말하고 턴을 끝내지 말 것.
> 반드시 §2의 명령을 만들어 사용자에게 제시해야 한다.

**절대 쓰지 말 것:** `cat ~/.env`, `grep "KEY" ~/.env`(`-q` 없이),
`echo $DATA_GO_KR_SERVICE_KEY`, `printenv`, `Get-Content ~/.env`.

## 2. 사용자에게 등록 요청하기

키가 없을 때 **채팅에 붙여넣게 하지 않는다.** 그러면 값이 대화 기록에 영구히 남는다.

대신 사용자가 **자기 터미널에서 직접 실행할** 명령을 만들어 준다.
`read -s`라 입력이 화면에 표시되지 않는다는 점을 반드시 함께 알려 준다.

```bash
printf "Enter CREDENTIAL_NAME (typing hidden): " && read -s val && echo && echo "CREDENTIAL_NAME=$val" >> ~/.env && echo "Saved."
```

제시하기 전에 `CREDENTIAL_NAME`을 실제 변수명으로 치환할 것.
`~/.env`가 없으면 이 명령이 만들어 준다.

**발급처 안내를 함께 준다.** 사용자가 키를 아직 갖고 있지 않을 수 있다.
호출한 스킬이 알려 주는 발급 링크와 절차를 그대로 전달한다.

### Windows PowerShell 사용자

이 저장소의 기본 개발기는 Windows다. Git Bash가 있으면 위 명령이 그대로 되고,
PowerShell만 쓴다면 아래를 안내한다.

```powershell
$k = Read-Host "Enter CREDENTIAL_NAME" -AsSecureString
$p = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($k))
Add-Content -Path "$HOME\.env" -Value "CREDENTIAL_NAME=$p" -Encoding utf8
"Saved."
```

## 3. 스크립트 실행

스킬의 헬퍼 스크립트는 `~/.env`에서 키를 **자동으로 읽는다.**

키를 직접 읽거나, 셸에 export하거나, CLI 인자로 넘길 **필요가 없다.**
§1로 존재만 확인했으면 스크립트를 그냥 실행하면 된다.

탐색 순서는 이렇다: 환경변수 → `~/.env` → `./.env`.

## 4. 이 저장소의 규약

- **키 이름은 데이터 제공처 단위로 하나만 쓴다.** 공공데이터포털에서 발급한
  키 하나가 여러 API에 통하므로, 모든 data.go.kr 계열 스킬은
  **`DATA_GO_KR_SERVICE_KEY`** 를 공유한다. 스킬마다 다른 이름을 만들지 말 것.
- `.env`는 절대 커밋하지 않는다. 루트 `.gitignore`에 이미 들어 있다.
- 키가 유효한지 확인해야 하면, 값을 출력하는 대신 각 스킬이 제공하는
  `check-key` 류의 진단 명령을 쓴다.

## 5. 유출했을 때

키 값이 대화나 로그에 노출됐다면 되돌릴 수 없다. 사용자에게 즉시 알리고
**재발급**을 안내한다: 공공데이터포털 → 마이페이지 → 오픈API → 해당 활용신청 →
인증키 재발급.
