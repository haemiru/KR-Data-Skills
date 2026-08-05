# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""KIPRISPlus 특허·실용 공개·등록공보 CLI 래퍼.

표준 라이브러리만 쓴다. 설계 원칙은 저장소 README 참조.

**data.go.kr 이 아니다.** 별도 가입·별도 키(`KIPRIS_PLUS_SERVICE_KEY`)다.
앞선 세 스킬과 다른 점(2026-08-05 실측):

  - 응답이 **XML** 이다 (앞선 셋은 전부 JSON)
  - 인증 파라미터가 **`ServiceKey`**(대문자 S) — `serviceKey` 는 안 된다
  - 🔴 **`successYN` 이 거짓말을 한다.** 에러인데 `Y` 가 온다.
    성공 판정은 `resultCode == "00"` 으로만 한다
  - 🔴 **`code 10` 이 모든 실패를 뭉뚱그린다.** 경로 오류·파라미터 오류·키 없음이
    구분되지 않아, 키 없이 경로를 검증할 수 없다
  - 🔴 무료 한도가 **월 1,000회이고 계정 전체 합산**이다. 호출 예산이 빡빡하다
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

try:  # Windows cp949 에서 한글이 깨지는 것을 막는다
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # pragma: no cover
    pass


# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------
# 서비스명의 `Sevice` 는 오타가 아니다 — 원문이 그렇다.
BASE_URL = "https://plus.kipris.or.kr/kipo-api/kipi/patUtiModInfoSearchSevice"

KEY_NAME = "KIPRIS_PLUS_SERVICE_KEY"
LEGACY_KEY_NAMES = ("KIPRIS_PLUS_API_KEY", "KIPRIS_SERVICE_KEY")

USER_AGENT = "KR-Data-Skills/0.1 (+https://github.com/haemiru/KR-Data-Skills)"

# 실호출로 resultCode 00 을 확인한 것만 적는다. 포털 명세 기준 총 61개 중 5개다.
OPERATIONS: dict[str, str] = {
    "getAdvancedSearch": "항목별 복합 검색",
    "getBibliographyDetailInfoSearch": "서지상세",
    "getBibliographySumryInfoSearch": "서지요약",
    "getPubFullTextInfoSearch": "공개전문 PDF 경로",
    "getWordSearch": "단어 검색 (포털에 폐기예정 표시)",
}

# CLI 플래그 -> getAdvancedSearch 파라미터. 화이트리스트가 방어선이다.
# 🔴 요청 파라미터와 응답 필드의 이름이 다르다: 요청 `applicant` / 응답 `applicantName`.
SEARCH_PARAMS: dict[str, tuple[str, str]] = {
    "title": ("inventionTitle", "발명의 명칭"),
    "abstract": ("astrtCont", "초록 본문"),
    "ipc": ("ipcNumber", "IPC 코드 (예: F02M)"),
    "applicant": ("applicant", "출원인 (응답 필드는 applicantName 이다)"),
    "app_no": ("applicationNumber", "출원번호"),
}

# 검색 결과 필드 (실측)
SEARCH_FIELDS = (
    "applicationNumber", "inventionTitle", "applicantName", "applicationDate",
    "registerStatus", "registerNumber", "registerDate",
    "openNumber", "openDate", "publicationNumber", "publicationDate",
    "ipcNumber", "astrtCont", "drawing", "bigDrawing", "indexNo",
)
TEXT_FIELDS = ("astrtCont",)

PRESETS: dict[str, tuple[str, ...]] = {
    "brief": ("applicationNumber", "inventionTitle", "applicantName",
              "applicationDate", "registerStatus"),
    "core": ("applicationNumber", "inventionTitle", "applicantName", "applicationDate",
             "registerStatus", "registerNumber", "openDate", "ipcNumber", "astrtCont"),
    "full": SEARCH_FIELDS,
}

MAX_ROWS_PER_PAGE = 500
DEFAULT_QPS = 1.0

# 무료 한도가 월 1,000회이고 계정 전체 합산이라 기본 상한을 낮게 잡는다.
DEFAULT_MAX_CALLS = 20
MONTHLY_FREE_QUOTA = 1000

ERROR_HINTS = {
    "10": "이 API 는 code 10 하나로 **경로 오류·파라미터 오류·키 없음**을 전부 표현한다.\n"
    "     구분이 안 되므로 다음을 차례로 의심할 것:\n"
    "       1) 파라미터 이름 — 응답 필드명과 다를 수 있다(applicant vs applicantName)\n"
    "       2) 오퍼레이션 이름 — 실측 확인된 것만 쓴다\n"
    f"       3) 인증 파라미터는 ServiceKey(대문자 S)이고 값은 {KEY_NAME} 이다",
}


class KiprisError(Exception):
    """사용자에게 보여 줄 오류. 메시지에 인증키 값을 담지 않는다."""


# ---------------------------------------------------------------------------
# 인증키 — 값은 절대 반환/출력하지 않는다
# ---------------------------------------------------------------------------
def _parse_env_file(path: pathlib.Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name:
            out[name] = value
    return out


def _env_file_candidates() -> list[pathlib.Path]:
    """`.env` 탐색 경로.

    두 가지 실행 형태를 다 지원해야 한다:
      1) 저장소 안에서 개발할 때 — 현재 디렉터리에서 `.git` 이 있는 곳까지 거슬러 올라간다
      2) `~/.claude/skills/` 에 설치해서 쓸 때 — 사용자의 CWD 는 남의 프로젝트다

    2026-08-05 설치 검증에서 2번이 키를 못 찾는 것을 확인하고
    **스크립트 위치 기준 경로와 `~/.claude/.env` 를 추가**했다.

    우선순위: 환경변수 > 현재 디렉터리~저장소 루트 > 스크립트 위치~상위
              > `~/.claude/.env` > `~/.env`
    """
    out: list[pathlib.Path] = []

    def walk_up(start: pathlib.Path, limit: int = 5) -> None:
        for depth, directory in enumerate((start, *start.parents)):
            candidate = directory / ".env"
            if candidate not in out:
                out.append(candidate)
            if (directory / ".git").exists() or depth >= limit:
                break

    try:
        walk_up(pathlib.Path.cwd().resolve())
    except OSError:
        pass
    try:  # 설치돼서 실행될 때는 이쪽이 유일한 단서다
        walk_up(pathlib.Path(__file__).resolve().parent)
    except (OSError, NameError):
        pass
    for extra in (pathlib.Path.home() / ".claude" / ".env", pathlib.Path.home() / ".env"):
        if extra not in out:
            out.append(extra)
    return out


def load_service_key() -> str:
    names = (KEY_NAME, *LEGACY_KEY_NAMES)
    for name in names:
        value = os.environ.get(name)
        if value:
            return value.strip()
    for candidate in _env_file_candidates():
        env = _parse_env_file(candidate)
        for name in names:
            if env.get(name):
                return env[name].strip()
    raise KiprisError(
        f"인증키를 찾지 못했다. {KEY_NAME} 을 아래 중 한 곳에 등록할 것.\n"
        "  · 저장소에서 개발 중이면    → 저장소 루트의 .env\n"
        "  · 스킬을 설치해 쓰는 중이면 → ~/.claude/.env  (권장)\n"
        "  · 또는 환경변수로 직접 지정\n"
        "  ⚠️ 이 API 는 data.go.kr 이 아니다. DATA_GO_KR_SERVICE_KEY 로는 호출되지 않는다.\n"
        "  발급: https://plus.kipris.or.kr → 회원가입 → 데이터 서비스 > 서비스 신청 > Open API\n"
        "        → 장바구니에서 '유/무료 선택'을 **무료**로 (기본값이 유료다)\n"
        "        → 마이페이지 > API KEY 관리\n"
        "  등록(저장소 루트에서. 붙여넣고 엔터를 친 뒤에 키를 입력한다):\n"
        f'    printf "Enter {KEY_NAME} (typing hidden): " && read -s val && echo '
        f'&& echo "{KEY_NAME}=$val" >> ~/.claude/.env && echo "Saved."'
    )


def _mask(text: str, secret: str | None) -> str:
    if not secret:
        return text
    masked = text
    for form in {secret, urllib.parse.quote(secret, safe=""), urllib.parse.unquote(secret)}:
        if form:
            masked = masked.replace(form, "***SERVICE_KEY***")
    return masked


# ---------------------------------------------------------------------------
# XML -> dict
# ---------------------------------------------------------------------------
def _el_to_obj(el: ET.Element):
    """XML 엘리먼트를 dict/list 로 바꾼다.

    이 API 는 섹션마다 `...Array > ...Info` 로 감싼다(서지상세). 같은 태그가
    여러 번 나오면 리스트로 모은다.
    """
    children = list(el)
    if not children:
        text = (el.text or "").strip()
        return text or None
    out: dict[str, object] = {}
    for child in children:
        value = _el_to_obj(child)
        tag = child.tag
        if tag in out:
            if not isinstance(out[tag], list):
                out[tag] = [out[tag]]
            out[tag].append(value)  # type: ignore[union-attr]
        else:
            out[tag] = value
    return out


def parse_response(body: str) -> tuple[dict, list[dict], int]:
    """(header, items, totalCount) 로 정규화한다."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise KiprisError(f"XML 파싱 실패: {exc}") from None
    header_el = root.find("header")
    header = _el_to_obj(header_el) if header_el is not None else {}
    if not isinstance(header, dict):
        header = {}

    items: list[dict] = []
    total = 0
    body_el = root.find("body")
    if body_el is not None:
        count_el = body_el.find("count")
        if count_el is not None:
            obj = _el_to_obj(count_el)
            if isinstance(obj, dict):
                try:
                    total = int(str(obj.get("totalCount") or 0))
                except ValueError:
                    total = 0
        for item_el in body_el.iter("item"):
            obj = _el_to_obj(item_el)
            if isinstance(obj, dict):
                items.append(obj)
    if not total:
        for el in root.iter("totalCount"):
            try:
                total = int((el.text or "0").strip())
            except ValueError:
                total = 0
            break
    return header, items, total


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
class Client:
    def __init__(self, key: str, *, qps: float = DEFAULT_QPS, timeout: int = 30,
                 max_calls: int = DEFAULT_MAX_CALLS):
        self._raw_key = key
        self._min_interval = 1.0 / qps if qps > 0 else 0.0
        self._last = 0.0
        self.timeout = timeout
        self.call_count = 0
        self.max_calls = max_calls

    def _wait(self) -> None:
        if self._min_interval <= 0:
            return
        gap = time.monotonic() - self._last
        if gap < self._min_interval:
            time.sleep(self._min_interval - gap)
        self._last = time.monotonic()

    def get(self, operation: str, params: dict) -> tuple[dict, list[dict], int]:
        if self.call_count >= self.max_calls:
            raise KiprisError(
                f"호출 상한 --max-calls {self.max_calls} 에 도달했다.\n"
                f"  이 API 의 무료 한도는 **월 {MONTHLY_FREE_QUOTA:,}회이고 계정 전체 합산**이다.\n"
                "  상한을 올리기 전에 조회 범위를 좁힐 수 있는지 먼저 볼 것."
            )
        merged = {k: v for k, v in params.items() if v not in (None, "")}
        # 대문자 S 다. serviceKey / accessKey 는 code 10 으로 떨어진다.
        merged["ServiceKey"] = self._raw_key
        full = f"{BASE_URL}/{operation}?{urllib.parse.urlencode(merged, encoding='utf-8')}"

        last_error: Exception | None = None
        for attempt in range(3):
            self._wait()
            request = urllib.request.Request(full, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    body = response.read().decode("utf-8", errors="replace")
                self.call_count += 1
                return self._check(body)
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                self.call_count += 1
                return self._check(body)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                time.sleep(1.5 * (attempt + 1))
        raise KiprisError(_mask(f"요청 실패: {last_error}", self._raw_key))

    def _check(self, body: str) -> tuple[dict, list[dict], int]:
        stripped = body.lstrip()
        if stripped.startswith("<!DOCTYPE") or stripped[:200].lower().find("<html") >= 0:
            raise KiprisError(
                "HTML 이 돌아왔다 — 경로가 틀렸을 가능성이 높다.\n"
                f"  베이스: {BASE_URL}\n"
                "  서비스명의 'Sevice' 는 오타가 아니라 원문이다."
            )
        header, items, total = parse_response(body)
        code = str(header.get("resultCode") or "").strip()
        # 🔴 successYN 은 에러에도 Y 가 온다. resultCode 로만 판정한다.
        if code and code != "00":
            msg = str(header.get("resultMsg") or "")
            hint = ERROR_HINTS.get(code, "")
            raise KiprisError(
                _mask(f"API 오류 (resultCode {code}) {msg}"
                      + (f"\n  → {hint}" if hint else ""), self._raw_key)
            )
        return header, items, total


# ---------------------------------------------------------------------------
# 후처리
# ---------------------------------------------------------------------------
def truncate_text(items: list[dict], limit: int) -> tuple[list[dict], int]:
    if limit <= 0:
        return items, 0
    touched = 0
    out: list[dict] = []
    for row in items:
        row = dict(row)
        cut: list[str] = []
        for field in TEXT_FIELDS:
            value = row.get(field)
            if isinstance(value, str) and len(value) > limit:
                row[field] = value[:limit] + f"…(총 {len(value)}자, --truncate-text 로 잘림)"
                cut.append(field)
        if cut:
            row["_truncated"] = cut
            touched += 1
        out.append(row)
    return out, touched


def _norm_date(value) -> str | None:
    if not value:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if len(digits) != 8:
        return None
    return f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]}"


def enrich(items: list[dict]) -> list[dict]:
    out = []
    for row in items:
        row = dict(row)
        row["_applicationDate"] = _norm_date(row.get("applicationDate"))
        row["_registerDate"] = _norm_date(row.get("registerDate"))
        row["_openDate"] = _norm_date(row.get("openDate"))
        row["_registered"] = bool(str(row.get("registerNumber") or "").strip())
        row["_hasDrawing"] = bool(row.get("drawing") or row.get("bigDrawing"))
        out.append(row)
    return out


def project(items: list[dict], fields: tuple[str, ...] | None) -> list[dict]:
    if not fields:
        return items
    keep = set(fields)
    return [{k: v for k, v in row.items() if k in keep or k.startswith("_")} for row in items]


def write_output(path: str, meta: dict, items: list[dict]) -> None:
    out = pathlib.Path(path)
    if out.parent and not out.parent.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        json.dump({"_meta": meta, "items": items}, fh, ensure_ascii=False, indent=2)
    size_kb = out.stat().st_size / 1024
    calls = meta.get("api_calls", 0)
    print(f"저장 완료: {out}  ({len(items)}건 / 전체 {meta.get('total_count', '?')}건, "
          f"{size_kb:.1f} KB, API 호출 {calls}회)")
    print(f"   💳 무료 한도는 월 {MONTHLY_FREE_QUOTA:,}회 — **계정 전체 상품 합산**이다. "
          "이번 실행에서 위 횟수를 썼다.")
    if meta.get("truncated_rows"):
        print(f"⚠ 초록을 자른 행이 {meta['truncated_rows']}건이다. 행의 _truncated 를 볼 것.")
    if meta.get("truncated"):
        print(f"⚠ 전체 {meta.get('total_count')}건 중 {meta.get('returned')}건만 받았다 "
              f"({meta.get('truncated_by')} 에 걸림).\n"
              "   이 결과를 '전부'라고 보고하지 말 것.")
    if meta.get("total_count") == 0:
        print("🔴 0건이다. 조건을 확인할 것.\n"
              f"   보낸 조건: {json.dumps(meta.get('filters') or {}, ensure_ascii=False)}")


# ---------------------------------------------------------------------------
# 명령
# ---------------------------------------------------------------------------
def cmd_search(client: Client, args) -> None:
    filters: dict[str, str] = {}
    for flag, (param, _d) in SEARCH_PARAMS.items():
        value = getattr(args, flag, None)
        if value:
            filters[param] = str(value).strip()
    if not filters:
        raise KiprisError(
            "조건이 하나도 없다. 최소 하나는 줄 것.\n"
            "  예: --title 자동차 / --applicant 삼성전자 / --ipc F02M / --abstract 연료\n"
            "  ⚠️ --applicant 의 API 파라미터는 applicant 다. "
            "응답 필드명(applicantName)을 파라미터로 쓰면 code 10 이다."
        )

    rows_per_page = min(int(args.limit), MAX_ROWS_PER_PAGE)
    rows: list[dict] = []
    total = 0
    truncated_by: str | None = None
    page = 1
    while page <= args.max_pages:
        _hdr, items, tot = client.get(
            "getAdvancedSearch", {**filters, "pageNo": str(page), "numOfRows": str(rows_per_page)}
        )
        if page == 1:
            total = tot
        if not items:
            break
        rows.extend(items)
        if len(rows) >= args.max_items:
            rows = rows[: args.max_items]
            truncated_by = f"--max-items {args.max_items}"
            break
        if len(rows) >= total:
            break
        page += 1
    else:
        if len(rows) < total:
            truncated_by = f"--max-pages {args.max_pages}"

    meta: dict[str, object] = {
        "source": "KIPRISPlus 특허·실용 공개·등록공보",
        "portal": "https://plus.kipris.or.kr",
        "operation": "getAdvancedSearch",
        "filters": filters,
        "total_count": total,
        "returned": len(rows),
        "api_calls": client.call_count,
        "truncated": truncated_by is not None,
        "truncated_by": truncated_by,
    }
    rows = enrich(rows)
    rows, touched = truncate_text(rows, args.truncate_text)
    meta["truncated_rows"] = touched
    fields = tuple(f.strip() for f in args.fields.split(",")) if args.fields else PRESETS[args.preset]
    meta["preset"] = "custom" if args.fields else args.preset
    write_output(args.output, meta, project(rows, fields))


def cmd_detail(client: Client, args) -> None:
    op = {"detail": "getBibliographyDetailInfoSearch",
          "summary": "getBibliographySumryInfoSearch",
          "fulltext": "getPubFullTextInfoSearch"}[args.kind]
    _hdr, items, total = client.get(op, {"applicationNumber": args.app_no})
    meta = {
        "source": "KIPRISPlus 특허·실용 공개·등록공보",
        "operation": op,
        "filters": {"applicationNumber": args.app_no},
        "total_count": total or len(items),
        "returned": len(items),
        "api_calls": client.call_count,
    }
    write_output(args.output, meta, items)


def cmd_check_key(client: Client, args) -> None:
    _hdr, items, total = client.get("getAdvancedSearch",
                                    {"inventionTitle": "자동차", "pageNo": "1", "numOfRows": "1"})
    print("인증키 확인 결과")
    print(f"  변수         : {KEY_NAME} (data.go.kr 키가 아니다)")
    print(f"  엔드포인트   : {BASE_URL}")
    print(f"  인증 파라미터: ServiceKey (대문자 S)")
    print(f"  응답         : 정상 (resultCode 00)")
    print(f"  표본 총건수  : {total:,}건")
    if items:
        print(f"  응답 필드    : {len(items[0])}개")
    print(f"  💳 이번 확인에 호출 1회를 썼다. 무료 한도 월 {MONTHLY_FREE_QUOTA:,}회(계정 합산).")


def cmd_probe(client: Client, args) -> None:
    """오퍼레이션 생존 확인.

    🔴 다른 스킬과 달리 **키가 필요하다.** 이 API 는 code 10 하나로
    경로 오류·파라미터 오류·키 없음을 전부 표현해서, 키 없이는 구분이 안 된다.
    """
    print("⚠ 이 스킬의 probe 는 실호출이다. 오퍼레이션 수만큼 무료 한도를 쓴다.")
    probes = [
        ("getAdvancedSearch", {"inventionTitle": "자동차", "numOfRows": "1"}),
        ("getBibliographyDetailInfoSearch", {"applicationNumber": args.app_no}),
        ("getBibliographySumryInfoSearch", {"applicationNumber": args.app_no}),
        ("getPubFullTextInfoSearch", {"applicationNumber": args.app_no}),
        ("getWordSearch", {"word": "자동차", "numOfRows": "1"}),
    ]
    results = []
    for operation, params in probes:
        try:
            _h, items, total = client.get(operation, params)
            ok, note = True, f"items={len(items)} total={total}"
        except KiprisError as exc:
            ok, note = False, str(exc).splitlines()[0]
        results.append({"operation": operation, "ok": ok, "note": note,
                        "label": OPERATIONS.get(operation, "")})
        print(f"  {'✅' if ok else '❌'} {operation:32s} {OPERATIONS.get(operation,'')}  {note}")
    print(f"\n  💳 호출 {client.call_count}회를 썼다.")
    if args.output:
        pathlib.Path(args.output).write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  저장: {args.output}")


def cmd_raw(client: Client, args) -> None:
    extra: dict = {}
    if args.params:
        try:
            extra = json.loads(args.params)
        except json.JSONDecodeError as exc:
            raise KiprisError(f"--params 가 JSON 객체가 아니다: {exc}") from None
    if args.operation not in OPERATIONS:
        print(f"⚠ '{args.operation}' 은 실측 확인된 오퍼레이션이 아니다.\n"
              "   이 API 는 code 10 하나로 모든 실패를 표현해서, 실패해도 원인을 알 수 없다.\n"
              f"   확인된 것: {', '.join(OPERATIONS)}")
    _hdr, items, total = client.get(args.operation, extra)
    meta = {"operation": args.operation, "filters": extra, "total_count": total,
            "returned": len(items), "api_calls": client.call_count}
    write_output(args.output, meta, items)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def add_budget(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS,
                        help=f"이번 실행의 API 호출 상한 (기본 {DEFAULT_MAX_CALLS}). "
                             f"무료 한도가 월 {MONTHLY_FREE_QUOTA:,}회 계정 합산이라 낮게 잡았다.")
    parser.add_argument("--qps", type=float, default=DEFAULT_QPS)
    parser.add_argument("--timeout", type=int, default=30)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kipris_api.py",
        description="KIPRISPlus 특허·실용 공개·등록공보 CLI 래퍼 (data.go.kr 아님)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("search", help="특허·실용 검색 (getAdvancedSearch)")
    for flag, (param, desc) in SEARCH_PARAMS.items():
        p.add_argument(f"--{flag.replace('_', '-')}", dest=flag, help=f"{desc} [{param}]")
    p.add_argument("--output", required=True, help="(필수) 결과 JSON 경로.")
    p.add_argument("--preset", choices=sorted(PRESETS), default="core",
                   help="필드 묶음 (기본 core). brief=5개 / core=9개 / full=16개")
    p.add_argument("--fields", help="쉼표로 구분한 필드명. --preset 을 덮어쓴다.")
    p.add_argument("--truncate-text", type=int, default=0,
                   help="초록(astrtCont)을 N자로 자른다 (0=자르지 않음).")
    p.add_argument("--limit", type=int, default=100,
                   help=f"페이지당 건수 (기본 100, 상한 {MAX_ROWS_PER_PAGE}).")
    p.add_argument("--max-pages", type=int, default=3, help="최대 페이지 (기본 3).")
    p.add_argument("--max-items", type=int, default=300, help="총 수집 상한 (기본 300).")
    add_budget(p)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("detail", help="출원번호로 서지·전문 조회")
    p.add_argument("--app-no", required=True, help="출원번호 (예: 1020070112929)")
    p.add_argument("--kind", choices=("detail", "summary", "fulltext"), default="detail",
                   help="detail=서지상세 / summary=서지요약 / fulltext=공개전문PDF 경로")
    p.add_argument("--output", required=True)
    add_budget(p)
    p.set_defaults(func=cmd_detail)

    p = sub.add_parser("check-key", help="인증키가 통하는지 1건 호출로 확인 (키 값 출력 안 함)")
    add_budget(p)
    p.set_defaults(func=cmd_check_key)

    p = sub.add_parser("probe-endpoints",
                       help="오퍼레이션 생존 확인 (⚠ 키를 쓴다 — code 10 때문에 무인증 검증 불가)")
    p.add_argument("--app-no", default="1020070112929", help="검사에 쓸 출원번호")
    p.add_argument("--output", help="(선택) 결과 저장 경로")
    add_budget(p)
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("raw", help="탈출구 — 오퍼레이션과 파라미터를 직접 지정")
    p.add_argument("--operation", required=True, help=f"확인된 것: {', '.join(OPERATIONS)}")
    p.add_argument("--params", help="파라미터 JSON 객체 문자열")
    p.add_argument("--output", required=True)
    add_budget(p)
    p.set_defaults(func=cmd_raw)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        client = Client(load_service_key(), qps=args.qps, timeout=args.timeout,
                        max_calls=args.max_calls)
        args.func(client, args)
        return 0
    except KiprisError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("중단됨.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
