#!/usr/bin/env python3
"""조달청 나라장터 입찰공고정보서비스 CLI 래퍼.

공공데이터포털(data.go.kr) 오픈API를 에이전트가 안전하게 쓰도록 감싼다.

설계 원칙
  1. 응답은 항상 파일로 쓴다(`--output` 필수). 컨텍스트에 쏟지 않는다.
  2. 인증키 값은 어떤 경로로도 출력하지 않는다(에러 메시지 포함, 자동 마스킹).
  3. 표준 라이브러리만 쓴다. 외부 의존성 0.

데이터셋: https://www.data.go.kr/data/15129394/openapi.do
"""

# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# ---------------------------------------------------------------------------
# 한글 출력이 cp949로 깨지는 것을 막는다 (Windows 기본 콘솔 인코딩 대응)
# ---------------------------------------------------------------------------
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover - 구버전/리다이렉트
        pass

BASE_URL = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService"
KEY_NAME = "DATA_GO_KR_SERVICE_KEY"
LEGACY_KEY_NAMES = ("SERVICE_KEY", "DATA_GO_KR_API_KEY")

USER_AGENT = "KR-Data-Skills/0.1 (+https://github.com/haemiru/KR-Data-Skills)"

# 업무구분 -> 오퍼레이션 접미사. 2026-08-04 실측 확인.
KINDS = {
    "thng": ("Thng", "물품"),
    "servc": ("Servc", "용역"),
    "cnstwk": ("Cnstwk", "공사"),
    "frgcpt": ("Frgcpt", "외자"),
    "etc": ("Etc", "기타"),
}

# 명령별 지원 업무구분 (실측: 일부 오퍼레이션은 업무구분이 없거나 일부만 존재)
BASIS_AMOUNT_KINDS = ("thng", "servc", "cnstwk")
CHG_HSTRY_KINDS = ("thng", "servc", "cnstwk")

MAX_ROWS_PER_PAGE = 999  # API 상한. 1000 이상 요청 시 에러.
DEFAULT_QPS = 2.0
DEFAULT_CHUNK_DAYS = 30

# data.go.kr 공통 에러코드 -> 사람이 읽을 설명
ERROR_HINTS = {
    "1": "애플리케이션 에러 — 잠시 후 재시도.",
    "4": "HTTP 에러.",
    "12": "해당 오픈API가 없다. 엔드포인트 경로/오퍼레이션명을 확인할 것. "
    "(옛 경로 /1230000/BidPublicInfoService/... 는 폐기됐다. /1230000/ad/ 가 필요하다)",
    "20": "서비스 접근이 거부됐다. 활용신청 상태를 확인할 것.",
    "22": "일일 트래픽 한도를 초과했다(개발계정 기본 1,000건/일).",
    "30": f"등록되지 않은 서비스키다. 저장소 루트 .env 의 {KEY_NAME} 값과 "
    "활용신청 승인 여부를 확인할 것. 발급 직후 반영에 최대 1시간 걸릴 수 있다.",
    "31": "활용기간이 만료된 키다.",
    "32": "등록되지 않은 IP다.",
    "99": "기타 에러.",
}


class G2BError(Exception):
    """래퍼가 명시적으로 잡아 사용자에게 보여 주는 에러."""


# ---------------------------------------------------------------------------
# 인증키 — 값은 절대 반환/출력하지 않는다
# ---------------------------------------------------------------------------
def _parse_env_file(path: pathlib.Path) -> dict[str, str]:
    """.env 파일을 파싱한다. 실패해도 조용히 빈 dict를 준다."""
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
    """`.env` 탐색 경로를 우선순위 순으로 만든다.

    현재 디렉터리에서 위로 올라가며 찾고, 마지막에 홈 디렉터리를 본다.
    위로 올라가는 이유: 스크립트를 `skills/<name>/` 안에서 실행해도
    **저장소 루트의 `.env`**를 찾아야 하기 때문이다.
    `.git`이 있는 디렉터리까지만 올라간다 — 저장소 밖의 남의 `.env`를
    주워 오지 않으려고.
    """
    out: list[pathlib.Path] = []
    try:
        cwd = pathlib.Path.cwd().resolve()
    except OSError:
        cwd = None
    if cwd is not None:
        for depth, directory in enumerate((cwd, *cwd.parents)):
            out.append(directory / ".env")
            if (directory / ".git").exists() or depth >= 5:
                break
    home = pathlib.Path.home() / ".env"
    if home not in out:
        out.append(home)
    return out


def load_service_key() -> str:
    """환경변수 -> 프로젝트 `.env`(상위로 탐색) -> `~/.env` 순으로 찾는다.

    프로젝트 로컬이 홈보다 **우선**이다. 저장소마다 다른 키를 쓸 수 있어야 하고,
    홈에 묵은 키가 남아 있어도 프로젝트 설정이 이기는 쪽이 덜 놀랍다.

    Returns:
      인증키 문자열.

    Raises:
      G2BError: 어디에도 키가 없을 때. 메시지에 키 값은 담기지 않는다.
    """
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

    raise G2BError(
        f"인증키를 찾지 못했다. 저장소 루트의 .env 에 {KEY_NAME} 을 등록할 것.\n"
        "  발급: https://www.data.go.kr/data/15129394/openapi.do 에서 활용신청(자동승인)\n"
        "  등록(터미널에서 직접 실행, 입력은 화면에 안 보인다):\n"
        f'    printf "Enter {KEY_NAME} (typing hidden): " && read -s val && echo '
        f'&& echo "{KEY_NAME}=$val" >> .env && echo "Saved."\n'
        "  (저장소 루트에서 실행할 것. 하위 폴더에서 실행하면 거기에 .env 가 생긴다)"
    )


def _mask(text: str, secret: str | None) -> str:
    """에러 메시지 등에서 인증키가 새는 것을 막는다."""
    if not secret:
        return text
    masked = text
    for form in {secret, urllib.parse.quote(secret, safe=""), urllib.parse.unquote(secret)}:
        if form:
            masked = masked.replace(form, "***SERVICE_KEY***")
    return masked


def _service_key_pair(key: str) -> tuple[str, bool]:
    """Encoding 키/Decoding 키를 자동 판별한다.

    공공데이터포털은 같은 키를 두 형태로 준다.
      - Decoding 키: 원문. `+` `/` `=` 가 그대로 들어 있다.
      - Encoding 키: 위를 퍼센트 인코딩한 것. `%2B` `%2F` `%3D` 가 보인다.

    Encoding 키를 다시 urlencode 하면 이중 인코딩이 되어 code 30(등록되지 않은
    서비스키)으로 떨어진다. 가장 흔한 실패 원인이라 여기서 자동으로 처리한다.

    Returns:
      (쿼리스트링에 그대로 붙일 문자열, 이미 인코딩된 키였는지 여부)
    """
    if re.search(r"%[0-9A-Fa-f]{2}", key):
        return key, True  # 이미 인코딩됨 — 그대로 붙인다
    return urllib.parse.quote(key, safe=""), False


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
class Client:
    """레이트리밋 + 재시도를 강제하는 최소 HTTP 클라이언트."""

    def __init__(self, service_key: str, qps: float = DEFAULT_QPS, timeout: int = 30,
                 retries: int = 3):
        self._key_qs, self.key_was_encoded = _service_key_pair(service_key)
        self._raw_key = service_key
        self._min_interval = 1.0 / qps if qps > 0 else 0.0
        self._last_call = 0.0
        self.timeout = timeout
        self.retries = retries
        self.call_count = 0

    def _throttle(self) -> None:
        gap = time.monotonic() - self._last_call
        if gap < self._min_interval:
            time.sleep(self._min_interval - gap)
        self._last_call = time.monotonic()

    def get(self, operation: str, params: dict[str, object]) -> dict:
        """오퍼레이션을 호출하고 파싱된 JSON을 돌려준다."""
        query = urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None and v != ""},
            quote_via=urllib.parse.quote,
        )
        url = f"{BASE_URL}/{operation}?serviceKey={self._key_qs}&{query}"

        last_error: str | None = None
        for attempt in range(self.retries):
            self._throttle()
            self.call_count += 1
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                return self._parse(body)
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                # data.go.kr 은 인증 에러도 4xx 바디에 담아 보낸다. 파싱해서 해석한다.
                try:
                    return self._parse(body)
                except G2BError:
                    raise
                except Exception:  # pylint: disable=broad-except
                    last_error = f"HTTP {exc.code}: {body[:300]}"
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = f"네트워크 오류: {exc}"
            if attempt < self.retries - 1:
                time.sleep(1.5 * (2**attempt))

        raise G2BError(_mask(f"{self.retries}회 재시도 후 실패했다. {last_error}", self._raw_key))

    def _parse(self, body: str) -> dict:
        """응답 본문을 파싱하고 API 레벨 에러를 예외로 승격시킨다."""
        text = body.strip()

        # 인증 실패 등은 type=json 을 줘도 XML 로 오는 경우가 있다.
        if text.startswith("<"):
            err = _xml_error(text)
            if err:
                raise G2BError(_mask(_format_api_error(*err), self._raw_key))
            raise G2BError(
                _mask("JSON 대신 XML이 왔는데 에러 코드를 못 읽었다.\n" + text[:400], self._raw_key)
            )

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise G2BError(
                _mask(f"응답을 JSON으로 못 읽었다({exc}).\n{text[:400]}", self._raw_key)
            ) from exc

        # 공통 에러 봉투: {"OpenAPI_ServiceResponse": {"cmmMsgHeader": {...}}}
        common = data.get("OpenAPI_ServiceResponse", {}).get("cmmMsgHeader")
        if common:
            raise G2BError(
                _mask(
                    _format_api_error(
                        str(common.get("returnReasonCode", "?")),
                        str(common.get("errMsg", "")),
                        str(common.get("returnAuthMsg", "")),
                    ),
                    self._raw_key,
                )
            )

        # 정상 봉투: {"response": {"header": {...}, "body": {...}}}
        header = data.get("response", {}).get("header", {})
        code = str(header.get("resultCode", "")).lstrip("0") or "0"
        if header and code != "0":
            raise G2BError(
                _mask(
                    _format_api_error(code, str(header.get("resultMsg", "")), ""),
                    self._raw_key,
                )
            )
        return data


def _xml_error(text: str) -> tuple[str, str, str] | None:
    """XML 에러 응답에서 (코드, errMsg, authMsg)를 뽑는다."""
    code = re.search(r"<returnReasonCode>([^<]*)</returnReasonCode>", text)
    msg = re.search(r"<errMsg>([^<]*)</errMsg>", text)
    auth = re.search(r"<returnAuthMsg>([^<]*)</returnAuthMsg>", text)
    result_code = re.search(r"<resultCode>([^<]*)</resultCode>", text)
    result_msg = re.search(r"<resultMsg>([^<]*)</resultMsg>", text)
    if code or msg:
        return (
            (code.group(1) if code else "?"),
            (msg.group(1) if msg else ""),
            (auth.group(1) if auth else ""),
        )
    if result_code and result_code.group(1).lstrip("0"):
        return (result_code.group(1), result_msg.group(1) if result_msg else "", "")
    return None


def _format_api_error(code: str, err_msg: str, auth_msg: str) -> str:
    hint = ERROR_HINTS.get(code.lstrip("0") or code, "")
    parts = [f"API 에러 (code {code})"]
    if err_msg:
        parts.append(err_msg)
    if auth_msg:
        parts.append(auth_msg)
    line = " — ".join(parts)
    return f"{line}\n  → {hint}" if hint else line


# ---------------------------------------------------------------------------
# 응답 정규화
# ---------------------------------------------------------------------------
def extract_items(payload: dict) -> list[dict]:
    """items 를 항상 list[dict] 로 정규화한다.

    data.go.kr 은 상황에 따라 items 를 list / {"item": [...]} / {"item": {...}} /
    "" / None 으로 준다. 이 흔들림을 여기서 흡수한다.
    """
    body = payload.get("response", {}).get("body", {})
    items = body.get("items")
    if items in (None, "", [], {}):
        return []
    if isinstance(items, dict):
        inner = items.get("item", [])
        if isinstance(inner, dict):
            return [inner]
        return list(inner) if isinstance(inner, list) else []
    if isinstance(items, list):
        return [i for i in items if isinstance(i, dict)]
    return []


def total_count(payload: dict) -> int:
    body = payload.get("response", {}).get("body", {})
    try:
        return int(body.get("totalCount", 0))
    except (TypeError, ValueError):
        return 0


def project(items: list[dict], fields: str | None) -> list[dict]:
    """--fields 로 지정한 키만 남긴다. 파일 크기를 줄이는 용도.

    `_` 로 시작하는 키(조인 결과)는 항상 살린다. 안 그러면 `--join` 과
    `--fields` 를 같이 썼을 때 조인 결과가 조용히 사라진다.
    """
    if not fields:
        return items
    keep = [f.strip() for f in fields.split(",") if f.strip()]
    out = []
    for item in items:
        row = {k: item.get(k) for k in keep if k in item}
        row.update({k: v for k, v in item.items() if k.startswith("_")})
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# 날짜
# ---------------------------------------------------------------------------
def to_api_datetime(value: str, *, end: bool) -> str:
    """사람이 쓴 날짜를 API가 받는 YYYYMMDDHHMM 으로 바꾼다.

    허용: 2026-08-01 / 20260801 / 202608010930 / 2026-08-01 09:30
    """
    digits = re.sub(r"\D", "", value)
    if len(digits) == 12:
        return digits
    if len(digits) == 8:
        return digits + ("2359" if end else "0000")
    raise G2BError(
        f"날짜 형식을 못 읽었다: {value!r}. YYYY-MM-DD 또는 YYYYMMDDHHMM 으로 줄 것."
    )


def resolve_range(args) -> tuple[str, str]:
    """--days 또는 --from/--to 를 (시작, 종료) 문자열로 확정한다."""
    if args.days is not None:
        today = _dt.date.today()
        start = today - _dt.timedelta(days=args.days - 1)
        return start.strftime("%Y%m%d") + "0000", today.strftime("%Y%m%d") + "2359"
    if not args.date_from or not args.date_to:
        raise G2BError("--days 또는 --from 과 --to 중 하나는 반드시 줘야 한다.")
    return (
        to_api_datetime(args.date_from, end=False),
        to_api_datetime(args.date_to, end=True),
    )


def split_range(start: str, end: str, chunk_days: int) -> list[tuple[str, str]]:
    """조회기간을 chunk_days 이하 구간으로 쪼갠다.

    나라장터 API는 장기간 조회를 거부하는 경우가 있다. 미리 쪼개서 회피한다.
    """
    if chunk_days <= 0:
        return [(start, end)]
    fmt = "%Y%m%d%H%M"
    s = _dt.datetime.strptime(start, fmt)
    e = _dt.datetime.strptime(end, fmt)
    if e < s:
        raise G2BError("조회 종료일시가 시작일시보다 빠르다.")
    chunks: list[tuple[str, str]] = []
    cursor = s
    while cursor <= e:
        stop = min(cursor + _dt.timedelta(days=chunk_days) - _dt.timedelta(minutes=1), e)
        chunks.append((cursor.strftime(fmt), stop.strftime(fmt)))
        cursor = stop + _dt.timedelta(minutes=1)
    return chunks


# ---------------------------------------------------------------------------
# 출력
# ---------------------------------------------------------------------------
def write_output(path: str, meta: dict, items: list[dict], raw: list[dict] | None) -> None:
    payload: dict[str, object] = {"_meta": meta, "items": items}
    if raw is not None:
        payload["_raw"] = raw
    out = pathlib.Path(path)
    if out.parent and not out.parent.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    size_kb = out.stat().st_size / 1024
    print(
        f"저장 완료: {out}  ({len(items)}건 / 전체 {meta.get('total_count', '?')}건, "
        f"{size_kb:.1f} KB, API 호출 {meta.get('api_calls')}회)"
    )
    if meta.get("truncated"):
        print(
            f"⚠ --max-items {meta.get('max_items')} 에 걸려 잘렸다. "
            "전체가 필요하면 값을 올리거나 조회기간을 좁힐 것."
        )
    if meta.get("dedup") == "latest":
        removed = meta.get("dedup_removed", 0)
        print(
            f"   중복 제거: {meta.get('fetched')}행 -> {len(items)}공고 "
            f"(차수 중복 {removed}건 제거)"
        )
    for name, st in (meta.get("join_stats") or {}).items():
        rate = st.get("match_rate")
        rate_txt = f"{rate:.0%}" if isinstance(rate, float) else "-"
        print(
            f"   조인 {name}: {st['rows_fetched']}행 수집({st['pages']}페이지) "
            f"-> {st['matched_items']}건 매칭 ({rate_txt})"
        )
    if meta.get("join_incomplete"):
        print(
            f"🔴 조인이 불완전하다 — {', '.join(meta['join_incomplete'])} 가 "
            f"--join-max-pages 상한에 걸렸다. 붙지 않은 공고가 있을 수 있다.\n"
            "   조회기간을 좁히거나 --join-max-pages 를 올릴 것."
        )


# ---------------------------------------------------------------------------
# 결과 가공 — 중복 제거 / 조인 / 필드 프리셋
# ---------------------------------------------------------------------------
# 공고 1건을 가리키는 유일 키. 2026-08-05 실측:
# 300건 중 8건이 같은 bidNtceNo 에 차수(000/001)만 다른 행이었다.
# bidNtceNo 만으로 묶으면 같은 공고를 두 번 보고하게 된다.
ROW_KEY = ("bidNtceNo", "bidNtceOrd")


def _row_key(row: dict) -> tuple[str, str] | None:
    """(공고번호, 차수) 키를 뽑는다. 둘 중 하나라도 없으면 None."""
    no = str(row.get("bidNtceNo") or "").strip()
    ord_ = str(row.get("bidNtceOrd") or "").strip()
    if not no or not ord_:
        return None
    return no, ord_


def dedup_latest(items: list[dict]) -> tuple[list[dict], int]:
    """공고번호별로 차수(bidNtceOrd) 최댓값 1건만 남긴다.

    키를 못 뽑는 행은 **버리지 않고 그대로 통과**시킨다.
    조용히 사라지는 것보다 중복이 낫다.

    Returns:
      (남은 items, 제거된 건수)
    """
    latest: dict[str, dict] = {}
    passthrough: list[dict] = []
    order: list[str] = []
    for row in items:
        key = _row_key(row)
        if key is None:
            passthrough.append(row)
            continue
        no, ord_ = key
        if no not in latest:
            latest[no] = row
            order.append(no)
        elif ord_ > str(latest[no].get("bidNtceOrd") or ""):
            latest[no] = row
    kept = [latest[no] for no in order] + passthrough
    return kept, len(items) - len(kept)


# 조인 대상 보조 오퍼레이션. 전부 (bidNtceNo, bidNtceOrd) 로 공고에 붙는다.
# 전부 1:N 이다 — 공고 1건에 행이 여러 개 붙을 수 있어 항상 배열로 담는다.
JOIN_SPECS = {
    "region": {
        "operation": "getBidPblancListInfoPrtcptPsblRgn",
        "kinds": None,
        "attr": "_region",
        "desc": "참가가능지역 (prtcptPsblRgnNm)",
    },
    "license": {
        "operation": "getBidPblancListInfoLicenseLimit",
        "kinds": None,
        "attr": "_license",
        "desc": "면허제한 (lcnsLmtNm)",
    },
    "basis": {
        "operation": None,  # 업무구분 의존 — _operation_for 로 만든다
        "kinds": BASIS_AMOUNT_KINDS,
        "attr": "_basis",
        "desc": "기초금액 (bssamt)",
    },
}

# 조인용 보조 조회의 기본 페이지 상한. 7일 창 기준 참가가능지역이 6,000행대라
# 999행/페이지로 7페이지쯤 든다. 넉넉히 잡되 무한정 돌지 않게 막는다.
DEFAULT_JOIN_MAX_PAGES = 12


def _fetch_join_rows(
    client: Client, operation: str, args, max_pages: int
) -> tuple[list[dict], int, bool]:
    """조인용 보조 오퍼레이션을 같은 기간으로 전량 훑는다.

    보조 오퍼레이션은 공고번호로 좁히는 파라미터가 없다(실측). 그래서
    같은 기간을 통째로 받아 메모리에서 인덱싱하는 수밖에 없다. 비싸다.

    조인은 `inqryDiv=1`(등록일시 기준)로 고정한다. 보조 행은 자기 rgstDt 로
    색인되므로 본 조회의 inqryDiv 를 따라가면 매칭이 어긋난다.

    Returns:
      (행 목록, 사용한 페이지 수, 상한에 걸렸는지)
    """
    start, end = resolve_range(args)
    rows: list[dict] = []
    pages = 0
    truncated = False
    for chunk_start, chunk_end in split_range(start, end, args.chunk_days):
        page = 1
        while page <= max_pages:
            payload = client.get(
                operation,
                {
                    "inqryDiv": "1",
                    "inqryBgnDt": chunk_start,
                    "inqryEndDt": chunk_end,
                    "pageNo": page,
                    "numOfRows": MAX_ROWS_PER_PAGE,
                    "type": "json",
                },
            )
            pages += 1
            page_rows = extract_items(payload)
            rows.extend(page_rows)
            if len(page_rows) < MAX_ROWS_PER_PAGE:
                break
            page += 1
        else:
            # while 조건으로 빠져나옴 = 아직 더 남아 있다
            truncated = True
    return rows, pages, truncated


def apply_joins(client: Client, items: list[dict], args) -> dict:
    """보조 오퍼레이션을 붙이고 조인 통계를 돌려준다.

    각 item 에 `_region` / `_license` / `_basis` 를 **배열로** 붙인다.
    붙을 게 없으면 빈 배열이다 — 키 자체를 빼지 않는다. 그래야
    "조인을 안 한 것"과 "조인했는데 없는 것"이 구분된다.
    """
    names = [n.strip() for n in (args.join or "").split(",") if n.strip()]
    if not names:
        return {}

    unknown = [n for n in names if n not in JOIN_SPECS]
    if unknown:
        raise G2BError(
            f"모르는 --join 대상: {', '.join(unknown)}. "
            f"가능한 값: {', '.join(JOIN_SPECS)}"
        )

    index: dict[str, dict[tuple[str, str], list[dict]]] = {}
    stats: dict[str, object] = {}
    incomplete: list[str] = []

    for name in names:
        spec = JOIN_SPECS[name]
        kind = getattr(args, "kind", None)
        if spec["kinds"] and kind not in spec["kinds"]:
            raise G2BError(
                f"--join {name} 은 --kind {'/'.join(spec['kinds'])} 만 지원한다"
                f"(요청: {kind}). 해당 오퍼레이션이 API에 없다."
            )
        operation = spec["operation"] or (
            _operation_for("getBidPblancListInfo", kind, spec["kinds"]) + "BsisAmount"
        )
        rows, pages, truncated = _fetch_join_rows(
            client, operation, args, args.join_max_pages
        )
        bucket: dict[tuple[str, str], list[dict]] = {}
        keyless = 0
        for row in rows:
            key = _row_key(row)
            if key is None:
                keyless += 1
                continue
            bucket.setdefault(key, []).append(row)
        index[name] = bucket
        stats[name] = {
            "operation": operation,
            "rows_fetched": len(rows),
            "pages": pages,
            "keyed_notices": len(bucket),
            "rows_without_key": keyless,
            "truncated": truncated,
        }
        if truncated:
            incomplete.append(name)

    matched = {name: 0 for name in names}
    for item in items:
        key = _row_key(item)
        for name in names:
            attr = JOIN_SPECS[name]["attr"]
            hits = index[name].get(key, []) if key else []
            item[attr] = hits
            if hits:
                matched[name] += 1

    for name in names:
        stats[name]["matched_items"] = matched[name]
        stats[name]["match_rate"] = (
            round(matched[name] / len(items), 3) if items else None
        )

    return {
        "join": names,
        "join_stats": stats,
        "join_incomplete": incomplete,
    }


# --fields 프리셋. 2026-08-05 실측으로 5개 업무구분 전부에 존재함을 확인한 것만 넣었다.
PRESET_CORE = (
    "bidNtceNo", "bidNtceOrd", "bidNtceNm", "ntceKindNm",
    "ntceInsttNm", "dminsttNm",
    "bidNtceDt", "bidClseDt", "opengDt",
    "presmptPrce", "cntrctCnclsMthdNm", "bidNtceDtlUrl",
)

# 업무구분별 추가 필드. 필드 집합이 업무구분마다 달라서
# (용역 113 / 공사 143 / 물품 101 / 외자 97 / 기타 38) 하나로 못 묶는다.
PRESET_EXTRA = {
    "servc": ("asignBdgtAmt", "srvceDivNm", "sucsfbidMthdNm",
              "indstrytyLmtYn", "rgnLmtBidLocplcJdgmBssNm"),
    "cnstwk": ("bdgtAmt", "cnstrtsiteRgnNm", "mainCnsttyNm",
               "rgnDutyJntcontrctYn", "sucsfbidMthdNm", "indstrytyLmtYn"),
    "thng": ("asignBdgtAmt", "dlvrTmlmtDt", "prdctQty", "prdctUnit",
             "dtilPrdctClsfcNoNm", "sucsfbidMthdNm"),
    "frgcpt": ("dlvrTmlmtDt", "prdctQty", "prdctUnit",
               "dtilPrdctClsfcNoNm", "sucsfbidMthdNm"),
    "etc": ("bidQlfctRgstCntnts", "rmrkCntnts", "cmmnSpldmdYn"),
}


def resolve_fields(args) -> str | None:
    """--fields 를 확정한다. 명시한 --fields 가 --preset 을 이긴다."""
    if getattr(args, "fields", None):
        return args.fields
    preset = getattr(args, "preset", "none")
    if preset != "core":
        return None
    kind = getattr(args, "kind", None)
    return ",".join(PRESET_CORE + PRESET_EXTRA.get(kind, ()))


# ---------------------------------------------------------------------------
# 수집 루프
# ---------------------------------------------------------------------------
def collect(
    client: Client, operation: str, base_params: dict, args
) -> tuple[list[dict], dict, list[dict] | None]:
    """기간 분할 + 페이지네이션을 돌며 items 를 모은다.

    Returns:
      (정규화된 items, _meta, 원본 응답 목록 또는 None)
    """
    start, end = resolve_range(args)
    chunks = split_range(start, end, args.chunk_days)

    items: list[dict] = []
    raw_pages: list[dict] = []
    grand_total = 0
    truncated = False
    pages_fetched = 0

    for chunk_start, chunk_end in chunks:
        page = 1
        while page <= args.max_pages:
            params = dict(base_params)
            params.update(
                {
                    "inqryDiv": args.inqry_div,
                    "inqryBgnDt": chunk_start,
                    "inqryEndDt": chunk_end,
                    "pageNo": page,
                    "numOfRows": min(args.limit, MAX_ROWS_PER_PAGE),
                    "type": "json",
                }
            )
            payload = client.get(operation, params)
            pages_fetched += 1
            if args.keep_raw:
                raw_pages.append(payload)

            page_items = extract_items(payload)
            grand_total += total_count(payload) if page == 1 else 0
            items.extend(page_items)

            if args.max_items and len(items) > args.max_items:
                items = items[: args.max_items]
                truncated = True
                break
            if len(page_items) < min(args.limit, MAX_ROWS_PER_PAGE):
                break  # 마지막 페이지
            page += 1
        if truncated:
            break

    fetched = len(items)

    # 순서가 중요하다: 중복 제거 -> 조인 -> 투영.
    # dedup 은 bidNtceOrd 가, join 은 bidNtceNo 가 필요한데 투영이 그걸 지울 수 있다.
    dedup_removed = 0
    if getattr(args, "dedup", "none") == "latest":
        items, dedup_removed = dedup_latest(items)

    join_meta: dict = {}
    if getattr(args, "join", None):
        join_meta = apply_joins(client, items, args)

    meta = {
        "operation": operation,
        "endpoint": f"{BASE_URL}/{operation}",
        "inqry_bgn_dt": start,
        "inqry_end_dt": end,
        "date_chunks": len(chunks),
        "params": {k: v for k, v in base_params.items() if v not in (None, "")},
        "requested_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "api_calls": client.call_count,
        "pages_fetched": pages_fetched,
        "total_count": grand_total,
        "fetched": fetched,
        "returned": len(items),
        "truncated": truncated,
        "max_items": args.max_items,
    }
    if getattr(args, "dedup", "none") == "latest":
        meta["dedup"] = "latest"
        meta["dedup_removed"] = dedup_removed
    meta.update(join_meta)
    return project(items, resolve_fields(args)), meta, (raw_pages if args.keep_raw else None)


# ---------------------------------------------------------------------------
# 명령
# ---------------------------------------------------------------------------
def _operation_for(prefix: str, kind: str, allowed: tuple[str, ...] | None = None) -> str:
    if allowed and kind not in allowed:
        raise G2BError(
            f"이 명령은 --kind {'/'.join(allowed)} 만 지원한다(요청: {kind}). "
            "나머지 업무구분은 해당 오퍼레이션이 API에 없다."
        )
    suffix, _ = KINDS[kind]
    return f"{prefix}{suffix}"


def cmd_search(client: Client, args) -> None:
    operation = _operation_for("getBidPblancListInfo", args.kind)
    items, meta, raw = collect(client, operation, {}, args)
    meta["kind"] = f"{args.kind} ({KINDS[args.kind][1]})"
    write_output(args.output, meta, items, raw)


def cmd_search_nara(client: Client, args) -> None:
    """나라장터 검색조건 계열(...PPSSrch). 공고명·기관명·지역·업종으로 좁힌다."""
    operation = _operation_for("getBidPblancListInfo", args.kind) + "PPSSrch"
    base = {
        "bidNtceNm": args.title,
        "ntceInsttNm": args.notice_inst,
        "dminsttNm": args.demand_inst,
        "prtcptLmtRgnNm": args.region,
        "indstrytyNm": args.industry_name,
        "indstrytyCd": args.industry_code,
        "presmptPrceBgn": args.price_from,
        "presmptPrceEnd": args.price_to,
        "refNo": args.ref_no,
    }
    items, meta, raw = collect(client, operation, base, args)
    meta["kind"] = f"{args.kind} ({KINDS[args.kind][1]})"
    write_output(args.output, meta, items, raw)


def cmd_basis_amount(client: Client, args) -> None:
    operation = _operation_for("getBidPblancListInfo", args.kind, BASIS_AMOUNT_KINDS) + "BsisAmount"
    items, meta, raw = collect(client, operation, {}, args)
    write_output(args.output, meta, items, raw)


def cmd_license_limit(client: Client, args) -> None:
    items, meta, raw = collect(client, "getBidPblancListInfoLicenseLimit", {}, args)
    write_output(args.output, meta, items, raw)


def cmd_region_limit(client: Client, args) -> None:
    items, meta, raw = collect(client, "getBidPblancListInfoPrtcptPsblRgn", {}, args)
    write_output(args.output, meta, items, raw)


def cmd_change_history(client: Client, args) -> None:
    suffix, _ = KINDS[args.kind]
    if args.kind not in CHG_HSTRY_KINDS:
        raise G2BError(
            f"변경이력은 --kind {'/'.join(CHG_HSTRY_KINDS)} 만 지원한다(요청: {args.kind})."
        )
    items, meta, raw = collect(client, f"getBidPblancListInfoChgHstry{suffix}", {}, args)
    write_output(args.output, meta, items, raw)


def cmd_raw(client: Client, args) -> None:
    """탈출구. 위 명령이 못 덮는 오퍼레이션/파라미터를 직접 호출한다."""
    try:
        extra = json.loads(args.params) if args.params else {}
    except json.JSONDecodeError as exc:
        raise G2BError(f"--params 가 올바른 JSON이 아니다: {exc}") from exc
    if not isinstance(extra, dict):
        raise G2BError("--params 는 JSON 객체여야 한다. 예: '{\"bidNtceNm\":\"청소\"}'")
    extra.setdefault("type", "json")
    extra.setdefault("pageNo", 1)
    extra.setdefault("numOfRows", min(args.limit, MAX_ROWS_PER_PAGE))
    payload = client.get(args.operation, extra)
    meta = {
        "operation": args.operation,
        "endpoint": f"{BASE_URL}/{args.operation}",
        "params": extra,
        "requested_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "api_calls": client.call_count,
        "total_count": total_count(payload),
        "returned": len(extract_items(payload)),
        "truncated": False,
    }
    write_output(
        args.output,
        meta,
        project(extract_items(payload), args.fields),
        [payload] if args.keep_raw else None,
    )


def cmd_check_key(client: Client, args) -> None:
    """키가 실제로 통하는지 1건만 호출해 확인한다. 키 값은 출력하지 않는다."""
    today = _dt.date.today().strftime("%Y%m%d")
    payload = client.get(
        "getBidPblancListInfoServc",
        {
            "type": "json",
            "inqryDiv": "1",
            "inqryBgnDt": today + "0000",
            "inqryEndDt": today + "2359",
            "pageNo": 1,
            "numOfRows": 1,
        },
    )
    form = "Encoding 키(퍼센트 인코딩됨)" if client.key_was_encoded else "Decoding 키(원문)"
    print("✅ 인증키 정상. API 호출 성공.")
    print(f"   키 형태: {form} — 래퍼가 자동 판별해 처리했다.")
    print(f"   오늘({today}) 용역 공고 totalCount = {total_count(payload)}")
    fields = sorted(extract_items(payload)[0].keys()) if extract_items(payload) else []
    if fields:
        print(f"   응답 필드 {len(fields)}개: {', '.join(fields)}")
    else:
        print("   (오늘 공고가 0건이라 필드 목록은 못 뽑았다. --days 를 늘려 search 로 확인할 것)")
    if args.output:
        write_output(
            args.output,
            {
                "operation": "getBidPblancListInfoServc",
                "check": "ok",
                "key_form": form,
                "api_calls": client.call_count,
                "total_count": total_count(payload),
                "fields": fields,
            },
            extract_items(payload),
            None,
        )


def cmd_probe_endpoints(args) -> None:
    """인증키 없이 오퍼레이션 경로의 생존 여부를 확인한다.

    유효 경로 + 잘못된 키 -> code 30, 없는 경로 -> code 12. 이 차이로 판별한다.
    API 명세가 docx로만 배포돼 경로가 흔들릴 때 쓰는 진단 도구다.
    """
    operations = [
        f"getBidPblancListInfo{s}" for s, _ in KINDS.values()
    ] + [
        f"getBidPblancListInfo{s}PPSSrch" for s, _ in KINDS.values()
    ] + [
        f"getBidPblancListInfo{KINDS[k][0]}BsisAmount" for k in BASIS_AMOUNT_KINDS
    ] + [
        f"getBidPblancListInfoChgHstry{KINDS[k][0]}" for k in CHG_HSTRY_KINDS
    ] + [
        "getBidPblancListInfoLicenseLimit",
        "getBidPblancListInfoPrtcptPsblRgn",
    ]
    if args.operation:
        operations = [args.operation]

    results = []
    for op in operations:
        url = f"{BASE_URL}/{op}?serviceKey=PROBE&type=json&pageNo=1&numOfRows=1"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        code = "?"
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            body = f"network error: {exc}"
        found = re.search(r'"?returnReasonCode"?\s*[:>]\s*"?([0-9]+)', body)
        if found:
            code = found.group(1)
        alive = code == "30"
        results.append({"operation": op, "return_reason_code": code, "alive": alive})
        print(f"{'OK   ' if alive else '-    '} {op}  (code {code})")
        time.sleep(0.3)

    alive_n = sum(1 for r in results if r["alive"])
    print(f"\n생존 {alive_n} / 확인 {len(results)}")
    if args.output:
        write_output(
            args.output,
            {
                "check": "probe-endpoints",
                "base_url": BASE_URL,
                "note": "code 30 = 경로 유효(키만 틀림), code 12 = 경로 없음",
                "requested_at": _dt.datetime.now().isoformat(timespec="seconds"),
                "api_calls": len(results),
                "total_count": len(results),
                "returned": len(results),
            },
            results,
            None,
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def add_common(parser: argparse.ArgumentParser, *, needs_range: bool = True) -> None:
    parser.add_argument("--output", required=True, help="(필수) 결과 JSON을 쓸 파일 경로.")
    parser.add_argument("--fields", help="쉼표로 구분한 필드명. 지정하면 그 키만 남겨 파일을 줄인다.")
    parser.add_argument("--limit", type=int, default=100,
                        help=f"페이지당 건수 (1~{MAX_ROWS_PER_PAGE}, 기본 100).")
    parser.add_argument("--max-pages", type=int, default=1,
                        help="구간당 최대 페이지 수 (기본 1). 올리면 API 호출이 그만큼 늘어난다.")
    parser.add_argument("--max-items", type=int, default=2000,
                        help="총 수집 상한 (기본 2000). 넘으면 잘리고 _meta.truncated=true.")
    parser.add_argument("--keep-raw", action="store_true",
                        help="원본 응답 봉투를 _raw 에 함께 저장(디버깅용, 파일이 커진다).")
    parser.add_argument("--qps", type=float, default=DEFAULT_QPS, help="초당 요청 수 상한.")
    parser.add_argument("--timeout", type=int, default=30, help="요청 타임아웃(초).")
    if needs_range:
        parser.add_argument("--days", type=int, help="오늘 포함 최근 N일. --from/--to 대신 쓴다.")
        parser.add_argument("--from", dest="date_from", help="조회 시작 (YYYY-MM-DD 또는 YYYYMMDDHHMM).")
        parser.add_argument("--to", dest="date_to", help="조회 종료 (YYYY-MM-DD 또는 YYYYMMDDHHMM).")
        parser.add_argument("--inqry-div", default="1",
                            help="조회구분 (기본 1). 업무구분별 의미가 다르니 명세 확인.")
        parser.add_argument("--chunk-days", type=int, default=DEFAULT_CHUNK_DAYS,
                            help=f"조회기간 분할 단위(일, 기본 {DEFAULT_CHUNK_DAYS}). 0이면 분할 안 함.")


def add_result_shaping(parser: argparse.ArgumentParser) -> None:
    """공고 목록 계열에만 붙는 가공 옵션 (중복 제거 · 조인 · 필드 프리셋).

    보조 오퍼레이션(면허·지역·기초금액·변경이력)에는 붙이지 않는다.
    그쪽은 1:N 이 정상이라 중복 제거가 오히려 데이터를 망친다.
    """
    parser.add_argument(
        "--dedup", choices=("none", "latest"), default="none",
        help="latest: 같은 bidNtceNo 중 차수(bidNtceOrd) 최신 1건만 남긴다. "
             "사용자에게 목록을 보고하기 전에 권장.",
    )
    parser.add_argument(
        "--join",
        help="보조 정보를 (bidNtceNo,bidNtceOrd)로 붙인다. 쉼표 구분: "
             + ", ".join(f"{k}={v['desc']}" for k, v in JOIN_SPECS.items())
             + ". 결과는 _region/_license/_basis 배열. "
               "⚠ 보조 조회는 기간 전체를 훑어서 API 호출이 크게 는다.",
    )
    parser.add_argument(
        "--join-max-pages", type=int, default=DEFAULT_JOIN_MAX_PAGES,
        help=f"조인 보조 조회의 페이지 상한 (기본 {DEFAULT_JOIN_MAX_PAGES}). "
             "상한에 걸리면 조인이 불완전하다고 경고한다.",
    )
    parser.add_argument(
        "--preset", choices=("none", "core"), default="none",
        help="core: 업무구분에 맞는 기본 필드 묶음을 쓴다(실측 확인된 필드만). "
             "--fields 를 직접 주면 그쪽이 이긴다.",
    )


def add_kind(parser: argparse.ArgumentParser, default: str = "servc") -> None:
    parser.add_argument(
        "--kind", choices=sorted(KINDS), default=default,
        help="업무구분: " + ", ".join(f"{k}={v[1]}" for k, v in KINDS.items()),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="g2b_api.py",
        description="조달청 나라장터 입찰공고정보서비스 CLI 래퍼",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("search", help="업무구분별 입찰공고 목록")
    add_kind(p)
    add_result_shaping(p)
    add_common(p)
    p.set_defaults(func=cmd_search, needs_key=True)

    p = sub.add_parser("search-nara", help="나라장터 검색조건으로 입찰공고 조회(공고명·기관·지역·업종)")
    add_kind(p)
    p.add_argument("--title", help="공고명 포함 검색 (bidNtceNm)")
    p.add_argument("--notice-inst", help="공고기관명 (ntceInsttNm)")
    p.add_argument("--demand-inst", help="수요기관명 (dminsttNm)")
    p.add_argument("--region", help="참가제한지역명 (prtcptLmtRgnNm), 예: 충청북도")
    p.add_argument("--industry-name", help="업종명 (indstrytyNm)")
    p.add_argument("--industry-code", help="업종코드 (indstrytyCd)")
    p.add_argument("--price-from", help="추정가격 하한 (presmptPrceBgn)")
    p.add_argument("--price-to", help="추정가격 상한 (presmptPrceEnd)")
    p.add_argument("--ref-no", help="참조번호 (refNo)")
    add_result_shaping(p)
    add_common(p)
    p.set_defaults(func=cmd_search_nara, needs_key=True)

    p = sub.add_parser("basis-amount", help="기초금액 정보 (물품/용역/공사)")
    add_kind(p)
    add_common(p)
    p.set_defaults(func=cmd_basis_amount, needs_key=True)

    p = sub.add_parser("license-limit", help="면허제한 정보")
    add_common(p)
    p.set_defaults(func=cmd_license_limit, needs_key=True)

    p = sub.add_parser("region-limit", help="참가가능지역 정보")
    add_common(p)
    p.set_defaults(func=cmd_region_limit, needs_key=True)

    p = sub.add_parser("change-history", help="입찰공고 변경이력 (물품/용역/공사)")
    add_kind(p)
    add_common(p)
    p.set_defaults(func=cmd_change_history, needs_key=True)

    p = sub.add_parser("raw", help="탈출구 — 오퍼레이션과 파라미터를 직접 지정")
    p.add_argument("--operation", required=True, help="오퍼레이션명 (예: getBidPblancListInfoServc)")
    p.add_argument("--params", help="추가 파라미터 JSON 객체 문자열")
    add_common(p, needs_range=False)
    p.set_defaults(func=cmd_raw, needs_key=True)

    p = sub.add_parser("check-key", help="인증키가 실제로 통하는지 1건 호출로 확인 (키 값은 출력 안 함)")
    p.add_argument("--output", help="(선택) 확인 결과를 파일로도 저장")
    p.add_argument("--qps", type=float, default=DEFAULT_QPS)
    p.add_argument("--timeout", type=int, default=30)
    p.set_defaults(func=cmd_check_key, needs_key=True)

    p = sub.add_parser("probe-endpoints", help="인증키 없이 오퍼레이션 경로 생존 확인(진단용)")
    p.add_argument("--operation", help="특정 오퍼레이션 하나만 확인")
    p.add_argument("--output", help="(선택) 결과를 파일로 저장")
    p.set_defaults(func=cmd_probe_endpoints, needs_key=False)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not getattr(args, "needs_key", True):
            cmd_probe_endpoints(args)
            return 0
        client = Client(load_service_key(), qps=args.qps, timeout=args.timeout)
        args.func(client, args)
        return 0
    except G2BError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("중단됨.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
