---
name: uv
description: >-
  Python 패키지 매니저 uv가 설치돼 있는지 확인하고, 없으면 설치한다. PATH 등록까지
  보장한다. 다른 스킬이 uv를 전제로 할 때 먼저 사용한다.
---

# uv (Python 패키지 매니저)

KR-Data-Skills의 모든 Python 스크립트는 `uv`로 실행한다. 스크립트 상단의 인라인
메타데이터가 Python 버전과 의존성을 선언하므로, `uv run`만 하면 환경이 알아서
맞춰진다. 가상환경을 따로 만들 필요가 없다.

`uv`에 의존하는 스킬을 쓰기 전에 아래를 먼저 확인한다.

## 설치 확인 및 설치

1. 이미 되는지 본다: `uv --version` (PowerShell이면 `& uv --version`).
   성공하면 준비 끝 — 나머지 단계는 건너뛴다.

2. 설치는 됐는데 PATH에 없는 경우를 확인한다.

   - **Windows (PowerShell)**: `& "$HOME\.local\bin\uv.exe" --version`
   - **Unix/macOS**: `"$HOME/.local/bin/uv" --version`

   둘 중 하나가 되면 4번으로 간다.

3. 설치가 안 돼 있으면 순서대로 한다.

   (a) 사용자에게 알린다 — `uv`는 KR-Data-Skills의 Python 스크립트를 일관되게
       실행하기 위한 도구이고, 지금 설치가 필요하다는 것.

   (b) 설치한다.

   - **Windows (PowerShell)**:
     `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
   - **Unix/macOS**: `curl -LsSf https://astral.sh/uv/install.sh | sh`

4. PATH에 넣고 검증한다 (한 줄로 실행).

   - **Windows (PowerShell)**: `$env:PATH = "$HOME\.local\bin;" + $env:PATH; uv --version`
   - **Unix/macOS**: `export PATH="$HOME/.local/bin:$PATH" && uv --version`

이후로는 `uv`를 그냥 쓰면 된다.

## 실행 방법

스크립트를 담고 있는 **스킬 폴더에서** 실행한다.

```bash
uv run scripts/<script>.py <command> [flags]
```

`uv`가 스크립트 상단의 블록을 읽어 맞는 Python을 골라 온다.

```python
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
```

## 이 저장소의 규약

- **외부 의존성은 되도록 0으로 간다.** 현재 스킬들은 표준 라이브러리만 쓴다.
  네트워크가 막힌 환경에서도 돌고, 설치 실패라는 실패 모드가 사라진다.
- 의존성이 꼭 필요하면 `dependencies = [...]`에 적는다.
  `requirements.txt`나 `pyproject.toml`을 따로 만들지 않는다.
- **시스템 Python으로 직접 실행하지 말 것.** 이 개발기의 시스템 Python은 3.14인데,
  `uv`는 스크립트가 요구하는 버전을 따로 잡아 준다. 버전 차이로 깨지는 사고를
  `uv`가 막아 준다.
