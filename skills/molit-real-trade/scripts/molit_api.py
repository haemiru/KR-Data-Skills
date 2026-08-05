# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""국토교통부 실거래가 공개시스템(RTMS) CLI 래퍼.

표준 라이브러리만 쓴다. 설계 원칙은 저장소 README 참조.

이 API는 조달청 나라장터와 **봉투도 파라미터도 다르다**:
  - `{"response": {...}}` 래퍼가 없다. 최상위가 곧 `{"header":..., "body":...}`
  - `resultCode` 가 3자리(`"000"`)다. 나라장터는 2자리(`"00"`)
  - 요청 파라미터가 대문자 스네이크(`LAWD_CD`, `DEAL_YMD`)다
  - 조회 단위가 **월(YYYYMM) 하나**다. 기간 조회가 없어 월별로 반복 호출한다
"""
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

try:  # Windows cp949 에서 한글이 깨지는 것을 막는다
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # pragma: no cover
    pass


# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------
BASE_URL = "https://apis.data.go.kr/1613000"
STANREGIN_URL = "https://apis.data.go.kr/1741000/StanReginCd/getStanReginCdList"

KEY_NAME = "DATA_GO_KR_SERVICE_KEY"
LEGACY_KEY_NAMES = ("SERVICE_KEY", "DATA_GO_KR_API_KEY", "MOLIT_API_KEY")

USER_AGENT = "KR-Data-Skills/0.1 (+https://github.com/haemiru/KR-Data-Skills)"

# 거래 유형 -> (오퍼레이션 경로, 한글 이름, 구독 여부)
# 2026-08-05 실측: 13개 경로 전부 생존. apt-trade-old 만 필드 미확인.
TYPES: dict[str, tuple[str, str]] = {
    "apt-trade": ("RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev", "아파트 매매"),
    "apt-trade-old": ("RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade", "아파트 매매(구버전)"),
    "apt-rent": ("RTMSDataSvcAptRent/getRTMSDataSvcAptRent", "아파트 전월세"),
    "offi-trade": ("RTMSDataSvcOffiTrade/getRTMSDataSvcOffiTrade", "오피스텔 매매"),
    "offi-rent": ("RTMSDataSvcOffiRent/getRTMSDataSvcOffiRent", "오피스텔 전월세"),
    "rh-trade": ("RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade", "연립다세대 매매"),
    "rh-rent": ("RTMSDataSvcRHRent/getRTMSDataSvcRHRent", "연립다세대 전월세"),
    "sh-trade": ("RTMSDataSvcSHTrade/getRTMSDataSvcSHTrade", "단독다가구 매매"),
    "sh-rent": ("RTMSDataSvcSHRent/getRTMSDataSvcSHRent", "단독다가구 전월세"),
    "land-trade": ("RTMSDataSvcLandTrade/getRTMSDataSvcLandTrade", "토지 매매"),
    "nrg-trade": ("RTMSDataSvcNrgTrade/getRTMSDataSvcNrgTrade", "상업업무용 매매"),
    "indu-trade": ("RTMSDataSvcInduTrade/getRTMSDataSvcInduTrade", "공장창고 매매"),
    "silv-trade": ("RTMSDataSvcSilvTrade/getRTMSDataSvcSilvTrade", "분양권 전매"),
}

MAX_ROWS_PER_PAGE = 1000
DEFAULT_QPS = 2.0

# 오퍼레이션마다 건물명 필드 이름이 다르다(실측). 파생 필드 `_name` 으로 통일한다.
NAME_FIELDS = ("aptNm", "offiNm", "mhouseNm", "bldgNm", "buildingName")

# 대표 면적도 유형마다 다르다(실측).
AREA_FIELDS = ("excluUseAr", "dealArea", "totalFloorAr", "buildingAr", "plottageAr")

# 만원 단위 금액 필드. 콤마가 섞인 문자열로 온다("110,000" = 11억).
AMOUNT_FIELDS = ("dealAmount", "deposit", "monthlyRent", "preDeposit", "preMonthlyRent")

ERROR_HINTS = {
    "12": "그런 경로가 없다. 오퍼레이션명을 확인할 것.",
    "20": "서비스 접근이 거부됐다. 활용신청 상태를 확인할 것.",
    "22": "일일 트래픽 한도를 초과했다(실거래가 계열 개발계정 10,000건/일).",
    "30": f"등록되지 않은 서비스키다. 저장소 루트 .env 의 {KEY_NAME} 값과, "
    "**해당 데이터셋의 활용신청 여부**를 확인할 것. "
    "포털 인증키는 하나지만 활용신청은 데이터셋마다 따로 해야 한다. "
    "발급 직후라면 반영에 최대 1시간 걸린다.",
    "31": "활용기간이 만료된 키다.",
    "32": "등록되지 않은 IP다.",
}


class MolitError(Exception):
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
    """`.env` 탐색 경로. 프로젝트 로컬이 홈보다 우선한다.

    현재 디렉터리에서 `.git` 이 있는 곳(저장소 루트)까지 거슬러 올라간다.
    `skills/<name>/` 안에서 실행해도 루트의 `.env` 를 찾기 위한 것이다.
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
    raise MolitError(
        f"인증키를 찾지 못했다. 저장소 루트 .env 에 {KEY_NAME} 을 등록할 것.\n"
        "  발급: https://www.data.go.kr → 활용신청 → 개발계정(자동승인)\n"
        "  등록(저장소 루트에서 실행. 붙여넣고 엔터를 친 뒤에 키를 입력한다):\n"
        f'    printf "Enter {KEY_NAME} (typing hidden): " && read -s val && echo '
        f'&& echo "{KEY_NAME}=$val" >> .env && echo "Saved."'
    )


def _mask(text: str, secret: str | None) -> str:
    if not secret:
        return text
    masked = text
    for form in {secret, urllib.parse.quote(secret, safe=""), urllib.parse.unquote(secret)}:
        if form:
            masked = masked.replace(form, "***SERVICE_KEY***")
    return masked


def _service_key_pair(key: str) -> tuple[str, bool]:
    """Encoding 키인지 Decoding 키인지 판별한다.

    포털이 두 형태를 다 주는데, Encoding 키를 다시 urlencode 하면
    "등록되지 않은 서비스키"로 떨어진다. `%` 가 들어 있으면 이미 인코딩된 것으로 본다.
    """
    if "%" in key:
        return urllib.parse.unquote(key), True
    return key, False


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
class Client:
    def __init__(self, key: str, *, qps: float = DEFAULT_QPS, timeout: int = 30):
        self._raw_key = key
        self._key, self._was_encoded = _service_key_pair(key)
        self._min_interval = 1.0 / qps if qps > 0 else 0.0
        self._last = 0.0
        self.timeout = timeout
        self.call_count = 0

    @property
    def key_form(self) -> str:
        return "Encoding 키(URL 인코딩됨)" if self._was_encoded else "Decoding 키(원문)"

    def _wait(self) -> None:
        if self._min_interval <= 0:
            return
        gap = time.monotonic() - self._last
        if gap < self._min_interval:
            time.sleep(self._min_interval - gap)
        self._last = time.monotonic()

    def get(self, url: str, params: dict) -> dict:
        merged = {k: v for k, v in params.items() if v not in (None, "")}
        merged["serviceKey"] = self._key
        merged.setdefault("type", "json")
        query = urllib.parse.urlencode(merged, encoding="utf-8")
        full = f"{url}?{query}"

        last_error: Exception | None = None
        for attempt in range(3):
            self._wait()
            request = urllib.request.Request(full, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    body = response.read().decode("utf-8", errors="replace")
                self.call_count += 1
                return self._parse(body)
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                self.call_count += 1
                # 인증 계열 에러는 HTTP 403 으로 오지만 본문에 사유가 들어 있다
                self._raise_api_error(body)
                last_error = exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                time.sleep(1.5 * (attempt + 1))
        raise MolitError(_mask(f"요청 실패: {last_error}", self._raw_key))

    def _raise_api_error(self, body: str) -> None:
        found = _extract_error(body)
        if not found:
            raise MolitError(_mask(f"알 수 없는 오류 응답: {body[:300]}", self._raw_key))
        code, err_msg, auth_msg = found
        hint = ERROR_HINTS.get(code, "")
        raise MolitError(
            _mask(
                f"API 오류 (code {code}) {err_msg} / {auth_msg}"
                + (f"\n  → {hint}" if hint else ""),
                self._raw_key,
            )
        )

    def _parse(self, body: str) -> dict:
        stripped = body.lstrip()
        if stripped.startswith("<"):
            # 에러는 XML 로 오는 경우가 있다. 정상 응답은 type=json 이면 JSON 이다.
            self._raise_api_error(body)
            raise MolitError("XML 응답을 해석하지 못했다.")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            raise MolitError(_mask(f"JSON 파싱 실패: {body[:300]}", self._raw_key)) from None
        if "OpenAPI_ServiceResponse" in payload or "cmmMsgHeader" in payload:
            self._raise_api_error(body)
        header = payload.get("header") or {}
        code = str(header.get("resultCode", "")).strip()
        # 이 API 는 정상이 "000" 이다. 나라장터("00")와 다르다.
        if code and code not in ("000", "00"):
            raise MolitError(
                f"API 오류 (resultCode {code}) {header.get('resultMsg', '')}"
            )
        return payload


def _extract_error(body: str) -> tuple[str, str, str] | None:
    """JSON/XML 양쪽 에러 봉투에서 (코드, errMsg, returnAuthMsg) 를 뽑는다."""
    try:
        data = json.loads(body)
        node = data.get("OpenAPI_ServiceResponse", data)
        head = node.get("cmmMsgHeader", node)
        if "returnReasonCode" in head:
            return (
                str(head.get("returnReasonCode", "")),
                str(head.get("errMsg", "")),
                str(head.get("returnAuthMsg", "")),
            )
        header = data.get("header")
        if isinstance(header, dict) and str(header.get("resultCode", "")) not in ("000", "00", ""):
            return (str(header.get("resultCode")), str(header.get("resultMsg", "")), "")
    except Exception:
        pass
    code = re.search(r"<returnReasonCode>([^<]*)</returnReasonCode>", body)
    if code:
        err = re.search(r"<errMsg>([^<]*)</errMsg>", body)
        auth = re.search(r"<returnAuthMsg>([^<]*)</returnAuthMsg>", body)
        return (
            code.group(1),
            err.group(1) if err else "",
            auth.group(1) if auth else "",
        )
    return None


# ---------------------------------------------------------------------------
# 응답 정규화
# ---------------------------------------------------------------------------
def extract_items(payload: dict) -> list[dict]:
    """`body.items` 의 흔들리는 형태를 list[dict] 로 정규화한다.

    실측된 형태: `{"item": [...]}` / `{"item": {...}}`(1건) / `""`(0건).
    """
    body = payload.get("body")
    if not isinstance(body, dict):
        return []
    items = body.get("items")
    if isinstance(items, dict):
        items = items.get("item")
    if items in (None, "", []):
        return []
    if isinstance(items, dict):
        return [items]
    if isinstance(items, list):
        return [i for i in items if isinstance(i, dict)]
    return []


def total_count(payload: dict) -> int:
    body = payload.get("body")
    if not isinstance(body, dict):
        return 0
    try:
        return int(str(body.get("totalCount", 0)).strip() or 0)
    except ValueError:
        return 0


def _clean(value) -> str:
    """이 API 는 빈 값을 공백 한 칸(`" "`)으로 준다. 실측 확인."""
    return str(value if value is not None else "").strip()


def _manwon_to_won(text: str) -> int | None:
    """`"110,000"`(만원) -> 1_100_000_000(원). 값이 없으면 None."""
    cleaned = _clean(text).replace(",", "")
    if not cleaned or not re.fullmatch(r"-?\d+(\.\d+)?", cleaned):
        return None
    return int(round(float(cleaned) * 10_000))


def enrich(items: list[dict]) -> list[dict]:
    """파생 필드를 붙인다. 원본 필드는 건드리지 않는다.

    `_` 로 시작하는 것이 래퍼가 계산한 값이다. API 가 준 값이 아니다.

    금액을 파생하는 이유가 있다. `dealAmount` 가 `"110,000"` 으로 오는데
    이건 **11만원이 아니라 11억**이다(만원 단위 + 천단위 콤마).
    사람도 에이전트도 자릿수를 틀린다.
    """
    out = []
    for item in items:
        row = dict(item)
        for field in AMOUNT_FIELDS:
            if field in row:
                won = _manwon_to_won(row[field])
                if won is not None:
                    row[f"_{field}Won"] = won
        for field in NAME_FIELDS:
            if _clean(row.get(field)):
                row["_name"] = _clean(row[field])
                break
        for field in AREA_FIELDS:
            if _clean(row.get(field)):
                row["_area"] = _clean(row[field])
                row["_areaField"] = field
                break
        year, month, day = (_clean(row.get(k)) for k in ("dealYear", "dealMonth", "dealDay"))
        if year and month and day:
            row["_dealDate"] = f"{year}-{int(month):02d}-{int(day):02d}"
        # 해제된 거래. 실측(2026-08-05): 표본 2,900건 중 71건(2.45%)이 해제다.
        # 시세 분석에 섞이면 결과가 틀어진다 — 특히 최고가·평균가.
        if _clean(row.get("cdealType")).upper() == "O":
            row["_cancelled"] = True
            row["_cancelledDate"] = _norm_short_date(row.get("cdealDay"))
        elif "cdealType" in row:
            row["_cancelled"] = False
        out.append(row)
    return out


def _norm_short_date(value) -> str | None:
    """`cdealDay` 는 `26.07.13`(YY.MM.DD)로 온다. 다른 날짜 필드와 형식이 또 다르다."""
    text = _clean(value)
    match = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{2})", text)
    if not match:
        return text or None
    yy, mm, dd = match.groups()
    return f"20{yy}-{mm}-{dd}"


def project(items: list[dict], fields: str | None) -> list[dict]:
    """--fields 로 지정한 키만 남긴다. `_` 로 시작하는 파생 필드는 항상 살린다."""
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
# 입력 검증 — 이 API 는 잘못된 입력에도 "정상 0건"을 준다
# ---------------------------------------------------------------------------
LAWD_RE = re.compile(r"^\d{5}$")
YM_RE = re.compile(r"^(19|20)\d{2}(0[1-9]|1[0-2])$")


def validate_lawd(code: str) -> str:
    """시군구코드 형식 검증.

    🔴 이 검증이 왜 필요한가 — 실측(2026-08-05):
      LAWD_CD=99999 -> resultCode "000", totalCount 0
      DEAL_YMD=2026 -> resultCode "000", totalCount 0
    **잘못된 입력이 에러가 아니라 "거래 없음"으로 온다.** 응답만으로는
    구분할 수 없으므로 보내기 전에 걸러야 한다.
    """
    code = _clean(code)
    if not LAWD_RE.match(code):
        raise MolitError(
            f"지역코드가 5자리 숫자가 아니다: {code!r}\n"
            "  법정동코드 앞 5자리(시군구코드)를 쓴다. 예: 11110(서울 종로구)\n"
            "  이름으로 찾으려면: molit_api.py lawd-code find 청주"
        )
    return code


def validate_ym(value: str) -> str:
    value = _clean(value)
    if not YM_RE.match(value):
        raise MolitError(
            f"조회월 형식이 YYYYMM 이 아니다: {value!r} (예: 202607)\n"
            "  이 API 는 형식이 틀려도 에러 대신 0건을 주므로 미리 막는다."
        )
    return value


def month_range(args) -> list[str]:
    """조회할 YYYYMM 목록. 이 API 는 월 하나씩만 받는다."""
    if args.months is not None:
        if args.months < 1:
            raise MolitError("--months 는 1 이상이어야 한다.")
        today = _dt.date.today().replace(day=1)
        out = []
        year, month = today.year, today.month
        for _ in range(args.months):
            out.append(f"{year}{month:02d}")
            month -= 1
            if month == 0:
                year, month = year - 1, 12
        return list(reversed(out))
    if not args.ym_from:
        raise MolitError("--months 또는 --from/--to 중 하나가 필요하다.")
    start = validate_ym(args.ym_from)
    end = validate_ym(args.ym_to or args.ym_from)
    if start > end:
        start, end = end, start
    out = []
    year, month = int(start[:4]), int(start[4:])
    while f"{year}{month:02d}" <= end:
        out.append(f"{year}{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
        if len(out) > 600:
            raise MolitError("조회 범위가 너무 넓다(50년 초과).")
    return out


# ---------------------------------------------------------------------------
# 지역코드 표
# ---------------------------------------------------------------------------
def lawd_table_path() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent / "references" / "lawd-codes.json"


def load_lawd_table() -> list[dict]:
    path = lawd_table_path()
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("regions", [])
    except Exception:
        return []


def _children_of(code: str, table: list[dict]) -> list[dict]:
    """그 시군구 아래에 '구'가 있으면 돌려준다.

    🔴 이게 왜 필요한가 — 실측(2026-08-05):
      43110 청주시(상위)   -> 0건
      43111 청주시 상당구  -> 173건
      43113 청주시 흥덕구  -> 342건
    **구가 있는 시는 상위 코드로 조회하면 0건이 온다.** 그런데 에러가 아니라
    "정상 0건"이라 "그 도시엔 거래가 없다"는 오답을 낳는다. 자동으로 펼친다.
    """
    by_code = {r["code"]: r["name"] for r in table}
    name = by_code.get(code)
    if not name:
        return []
    depth = name.count(" ")
    return [
        r
        for r in table
        if r["code"] != code
        and r["name"].startswith(name + " ")
        and r["name"].count(" ") == depth + 1
    ]


def resolve_regions(value: str) -> tuple[list[dict], list[tuple[str, str]]]:
    """`--region` 을 조회할 시군구 목록으로 확정한다.

    쉼표로 여러 개를 받는다. 코드면 그대로, 이름이면 표에서 찾는다.
    구가 있는 시는 하위 구로 자동 확장한다.

    Returns:
      (조회할 [{code, name}] 목록, 확장 안내 [(원래이름, 확장결과)] 목록)
    """
    table = load_lawd_table()
    by_code = {r["code"]: r["name"] for r in table}
    wanted: list[dict] = []
    notes: list[tuple[str, str]] = []

    for token in [t.strip() for t in _clean(value).split(",") if t.strip()]:
        if LAWD_RE.match(token):
            code = token
        elif not table:
            raise MolitError(
                f"지역명 {token!r} 을 코드로 바꿀 표가 없다.\n"
                "  5자리 시군구코드를 직접 주거나, 먼저 표를 받을 것:\n"
                "    molit_api.py lawd-code fetch\n"
                "  (행정안전부 법정동코드 API 활용신청이 필요하다 — 자동승인)\n"
                "  https://www.data.go.kr/data/15077871/openapi.do"
            )
        else:
            hits = [r for r in table if token in r["name"]]
            # 정확히 일치하는 이름이 있으면 그것을 고른다("청주시" vs "청주시 상당구")
            exact = [r for r in hits if r["name"].split()[-1] == token]
            if len(exact) == 1:
                hits = exact
            if not hits:
                raise MolitError(
                    f"지역명 {token!r} 에 맞는 시군구가 없다. lawd-code find 로 찾아볼 것."
                )
            if len(hits) > 1:
                listing = "\n".join(f"    {r['code']}  {r['name']}" for r in hits[:12])
                raise MolitError(
                    f"지역명 {token!r} 이 {len(hits)}곳과 일치한다. 코드를 직접 지정할 것:\n"
                    f"{listing}"
                )
            code = hits[0]["code"]

        children = _children_of(code, table)
        if children:
            notes.append(
                (
                    by_code.get(code, code),
                    ", ".join(c["name"].split()[-1] for c in children),
                )
            )
            wanted.extend(children)
        else:
            wanted.append({"code": validate_lawd(code), "name": by_code.get(code, code)})

    # 중복 제거(순서 유지)
    seen: set[str] = set()
    out = []
    for r in wanted:
        if r["code"] not in seen:
            seen.add(r["code"])
            out.append(r)
    if not out:
        raise MolitError("--region 이 비어 있다.")
    return out, notes


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
            "값을 올리거나 조회 범위를 좁힐 것."
        )
    cancelled = meta.get("cancelled_count") or 0
    if cancelled:
        if meta.get("cancelled_excluded"):
            print(f"   해제 거래 {cancelled}건을 제외했다 (--exclude-cancelled).")
        else:
            print(
                f"⚠ 해제된 거래가 {cancelled}건 섞여 있다 "
                "(cdealType='O', _cancelled=true).\n"
                "   시세·평균가·최고가를 낼 때 빼야 한다. --exclude-cancelled 를 쓰거나\n"
                "   items 에서 _cancelled 가 true 인 행을 걸러낼 것."
            )
    if meta.get("total_count") == 0:
        print(
            "🔴 0건이다. 다만 이 API 는 **잘못된 지역코드·조회월에도 0건을 정상 응답으로 준다**(실측).\n"
            f"   보낸 값: 지역={', '.join(meta.get('regions', []))} "
            f"월={','.join(meta.get('months', []))}\n"
            "   '거래가 없다'고 단정하기 전에 코드와 월을 확인할 것.\n"
            "   지역코드 확인: molit_api.py lawd-code find <지역명>"
        )


# ---------------------------------------------------------------------------
# 수집
# ---------------------------------------------------------------------------
def collect(client: Client, operation: str, regions: list[dict], months: list[str], args):
    items: list[dict] = []
    raw_pages: list[dict] = []
    grand_total = 0
    truncated = False
    pages_fetched = 0
    per_region: dict[str, int] = {}
    per_month: dict[str, int] = {ym: 0 for ym in months}

    for region in regions:
        lawd = region["code"]
        region_total = 0
        for ym in months:
            page = 1
            while page <= args.max_pages:
                payload = client.get(
                    f"{BASE_URL}/{operation}",
                    {
                        "LAWD_CD": lawd,
                        "DEAL_YMD": ym,
                        "pageNo": page,
                        "numOfRows": min(args.limit, MAX_ROWS_PER_PAGE),
                    },
                )
                pages_fetched += 1
                if args.keep_raw:
                    raw_pages.append(payload)
                page_items = extract_items(payload)
                if page == 1:
                    count = total_count(payload)
                    grand_total += count
                    region_total += count
                    per_month[ym] = per_month.get(ym, 0) + count
                for row in page_items:
                    row.setdefault("_dealYm", ym)
                    row.setdefault("_lawdCd", lawd)
                    row.setdefault("_regionName", region["name"])
                items.extend(page_items)
                if args.max_items and len(items) > args.max_items:
                    items = items[: args.max_items]
                    truncated = True
                    break
                if len(page_items) < min(args.limit, MAX_ROWS_PER_PAGE):
                    break
                page += 1
            if truncated:
                break
        per_region[f"{lawd} {region['name']}"] = region_total
        if truncated:
            break

    enriched = enrich(items)
    cancelled = sum(1 for r in enriched if r.get("_cancelled"))
    if getattr(args, "exclude_cancelled", False):
        enriched = [r for r in enriched if not r.get("_cancelled")]

    meta = {
        "operation": operation,
        "endpoint": f"{BASE_URL}/{operation}",
        "type": args.type,
        "type_label": TYPES[args.type][1],
        "regions": [f"{r['code']} {r['name']}" for r in regions],
        "months": months,
        "count_by_region": per_region,
        "count_by_month": per_month,
        "requested_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "api_calls": client.call_count,
        "pages_fetched": pages_fetched,
        "total_count": grand_total,
        "fetched": len(items),
        "returned": len(enriched),
        "cancelled_count": cancelled,
        "cancelled_excluded": bool(getattr(args, "exclude_cancelled", False)),
        "truncated": truncated,
        "max_items": args.max_items,
    }
    return project(enriched, args.fields), meta, (raw_pages if args.keep_raw else None)


# ---------------------------------------------------------------------------
# 명령
# ---------------------------------------------------------------------------
def cmd_search(client: Client, args) -> None:
    operation, _label = TYPES[args.type]
    regions, expanded = resolve_regions(args.region)
    months = month_range(args)
    for parent, kids in expanded:
        print(f"ℹ {parent} 는 구가 있어 하위로 펼쳤다 → {kids}")
        print("   (실측: 구가 있는 시는 상위 코드로 조회하면 0건이 온다)")
    if len(months) > args.max_months:
        raise MolitError(
            f"조회월이 {len(months)}개다(상한 {args.max_months}). "
            "이 API 는 월 하나당 최소 1회 호출이라 예산을 크게 먹는다. "
            "--max-months 를 올리거나 범위를 좁힐 것."
        )
    planned = len(regions) * len(months)
    if planned > args.max_calls:
        raise MolitError(
            f"예상 호출이 최소 {planned}회다(지역 {len(regions)} × 월 {len(months)}, "
            f"상한 {args.max_calls}). 실거래가 개발계정은 일 10,000건이다.\n"
            "  범위를 좁히거나 --max-calls 를 올릴 것."
        )
    if planned >= 20:
        print(f"ℹ 지역 {len(regions)}곳 × {len(months)}개월 = 최소 {planned}회 호출한다.")
    items, meta, raw = collect(client, operation, regions, months, args)
    write_output(args.output, meta, items, raw)


def cmd_check_key(client: Client, args) -> None:
    """키가 통하는지 1건 호출로 확인한다. 키 값은 출력하지 않는다."""
    operation, label = TYPES["apt-trade"]
    today = _dt.date.today().replace(day=1) - _dt.timedelta(days=1)
    ym = f"{today.year}{today.month:02d}"
    payload = client.get(
        f"{BASE_URL}/{operation}",
        {"LAWD_CD": "11110", "DEAL_YMD": ym, "pageNo": 1, "numOfRows": 1},
    )
    items = extract_items(payload)
    print("✅ 인증키 정상. API 호출 성공.")
    print(f"   키 형태: {client.key_form} — 래퍼가 자동 판별해 처리했다.")
    print(f"   {label} / 서울 종로구(11110) / {ym} totalCount = {total_count(payload)}")
    if items:
        print(f"   응답 필드 {len(items[0])}개: {', '.join(sorted(items[0]))}")
    if args.output:
        write_output(
            args.output,
            {"check": "ok", "api_calls": client.call_count, "total_count": total_count(payload)},
            enrich(items),
            None,
        )


def cmd_probe(args) -> None:
    """인증키 없이 오퍼레이션 경로 생존을 확인한다.

    data.go.kr 은 라우팅이 인증보다 먼저다. 더미 키로 호출하면
    code 30(경로 유효·키만 틀림) 과 code 12(경로 없음) 로 갈린다.
    """
    results = []
    for name, (path, label) in TYPES.items():
        query = urllib.parse.urlencode(
            {
                "serviceKey": "DUMMY_KEY_FOR_PATH_PROBE",
                "LAWD_CD": "11110",
                "DEAL_YMD": "202601",
                "pageNo": "1",
                "numOfRows": "1",
                "type": "json",
            }
        )
        url = f"{BASE_URL}/{path}?{query}"
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=25) as response:
                body = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001
            results.append({"type": name, "path": path, "verdict": "error", "detail": str(exc)[:80]})
            print(f"  ?    {name:14s} {label}")
            continue
        found = _extract_error(body)
        code = found[0] if found else "?"
        verdict = "alive" if code == "30" else "missing" if code == "12" else "unknown"
        mark = {"alive": "OK ", "missing": "없음", "unknown": "?  "}[verdict]
        results.append({"type": name, "path": path, "label": label, "code": code, "verdict": verdict})
        print(f"  {mark}  {name:14s} {label}")
    alive = sum(1 for r in results if r.get("verdict") == "alive")
    print(f"\n경로 유효 {alive}/{len(results)}")
    print("※ '경로 유효'는 그 데이터셋의 활용신청 완료를 뜻하지 않는다. check-key 로 별도 확인할 것.")
    if args.output:
        out = pathlib.Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps({"probed_at": _dt.datetime.now().isoformat(timespec="seconds"),
                        "results": results}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"저장: {args.output}")


def cmd_lawd_code(client: Client | None, args) -> None:
    if args.action == "find":
        table = load_lawd_table()
        if not table:
            raise MolitError(
                "지역코드 표가 없다. 먼저 받을 것: molit_api.py lawd-code fetch\n"
                "  (행정안전부 법정동코드 API 활용신청 필요 — 자동승인, 즉시)\n"
                "  https://www.data.go.kr/data/15077871/openapi.do"
            )
        query = _clean(args.query)
        hits = [r for r in table if query in r["name"] or query == r["code"]]
        if not hits:
            print(f"'{query}' 에 맞는 시군구가 없다. (표 {len(table)}건)")
            return
        for r in hits[:40]:
            print(f"  {r['code']}  {r['name']}")
        if len(hits) > 40:
            print(f"  ... 외 {len(hits) - 40}건")
        return

    # fetch — 행정안전부 법정동코드 API 에서 받아 표를 만든다
    assert client is not None
    regions: dict[str, str] = {}
    seen_rows = 0
    page = 1
    while page <= args.max_pages:
        payload = client.get(STANREGIN_URL, {"pageNo": page, "numOfRows": 1000, "type": "json"})
        rows = _stanregin_rows(payload)
        if not rows:
            break
        seen_rows += len(rows)
        for row in rows:
            # region_cd 10자리 = 시도(2) + 시군구(3) + 읍면동(3) + 리(2)
            # 시군구 단위 = 읍면동·리가 모두 0 이고 시군구가 0 이 아닌 것.
            # 문자열 접미사로 판별하면 "2720000000"(대구 남구) 같은 것이 새어 나간다.
            if _clean(row.get("umd_cd")) != "000":
                continue
            if _clean(row.get("ri_cd")) != "00":
                continue
            if _clean(row.get("sgg_cd")) in ("", "000"):
                continue
            code = _clean(row.get("region_cd"))
            name = _clean(row.get("locatadd_nm"))
            if len(code) == 10 and name:
                regions[code[:5]] = name
        print(f"  page {page}: 누적 {seen_rows}행 -> 시군구 {len(regions)}개", file=sys.stderr)
        page += 1
    else:
        print(
            f"⚠ --max-pages {args.max_pages} 에 걸려 멈췄다. 표가 불완전할 수 있다.",
            file=sys.stderr,
        )
    if not regions:
        raise MolitError("법정동코드 응답에서 시군구를 못 뽑았다. --keep-raw 로 원본을 확인할 것.")
    table = [{"code": c, "name": n} for c, n in sorted(regions.items())]
    path = lawd_table_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "source": "행정안전부 행정표준코드 법정동코드 (data.go.kr 15077871)",
                "fetched_at": _dt.datetime.now().isoformat(timespec="seconds"),
                "count": len(table),
                "regions": table,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"지역코드 표 저장: {path}  ({len(table)}개 시군구, API 호출 {client.call_count}회)")


def _stanregin_rows(payload: dict) -> list[dict]:
    """StanReginCd 응답은 봉투가 또 다르다. 실측 후 조정할 것."""
    node = payload.get("StanReginCd")
    if isinstance(node, list):
        for part in node:
            if isinstance(part, dict) and "row" in part:
                rows = part["row"]
                return rows if isinstance(rows, list) else [rows]
    if isinstance(node, dict) and "row" in node:
        rows = node["row"]
        return rows if isinstance(rows, list) else [rows]
    return []


def cmd_raw(client: Client, args) -> None:
    extra = json.loads(args.params) if args.params else {}
    if not isinstance(extra, dict):
        raise MolitError("--params 는 JSON 객체여야 한다.")
    payload = client.get(f"{BASE_URL}/{args.operation}", extra)
    items = enrich(extract_items(payload))
    meta = {
        "operation": args.operation,
        "params": extra,
        "api_calls": client.call_count,
        "total_count": total_count(payload),
        "returned": len(items),
    }
    write_output(args.output, meta, project(items, args.fields), [payload] if args.keep_raw else None)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", required=True, help="(필수) 결과 JSON을 쓸 파일 경로.")
    parser.add_argument("--fields", help="쉼표로 구분한 필드명. 파생 필드(_로 시작)는 항상 남는다.")
    parser.add_argument("--limit", type=int, default=1000, help="페이지당 건수 (기본 1000).")
    parser.add_argument("--max-pages", type=int, default=5, help="월당 최대 페이지 (기본 5).")
    parser.add_argument("--max-items", type=int, default=5000, help="총 수집 상한 (기본 5000).")
    parser.add_argument("--keep-raw", action="store_true", help="원본 응답을 _raw 에 함께 저장.")
    # argparse 는 help 문자열에 %-포매팅을 적용한다. 퍼센트 기호는 %% 로 써야 한다.
    # "2.45%가" 로 뒀다가 `search --help` 가 통째로 죽었다.
    parser.add_argument("--exclude-cancelled", action="store_true",
                        help="해제된 거래(cdealType='O')를 제외한다. "
                             "시세·평균가를 낼 때 권장. 실측 2.45%% 가 해제 거래다.")
    parser.add_argument("--qps", type=float, default=DEFAULT_QPS, help="초당 요청 수 상한.")
    parser.add_argument("--timeout", type=int, default=30, help="요청 타임아웃(초).")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="molit_api.py",
        description="국토교통부 실거래가(RTMS) CLI 래퍼",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("search", help="실거래 조회 (유형 × 지역 × 월)")
    p.add_argument("--type", choices=sorted(TYPES), default="apt-trade",
                   help="거래 유형: " + ", ".join(f"{k}={v[1]}" for k, v in TYPES.items()))
    p.add_argument("--region", required=True,
                   help="시군구코드 5자리(예: 11110) 또는 지역명. 쉼표로 여러 개. "
                        "구가 있는 시(청주시·수원시 등)는 하위 구로 자동 확장한다.")
    p.add_argument("--months", type=int, help="이번 달 포함 최근 N개월.")
    p.add_argument("--from", dest="ym_from", help="조회 시작월 YYYYMM.")
    p.add_argument("--to", dest="ym_to", help="조회 종료월 YYYYMM.")
    p.add_argument("--max-months", type=int, default=24,
                   help="조회월 개수 상한 (기본 24). 월마다 최소 1회 호출이다.")
    p.add_argument("--max-calls", type=int, default=120,
                   help="지역×월 예상 호출 상한 (기본 120). 예산 사고 방지용.")
    add_common(p)
    p.set_defaults(func=cmd_search, needs_key=True)

    p = sub.add_parser("lawd-code", help="시군구 지역코드 표 받기/찾기")
    p.add_argument("action", choices=("fetch", "find"), help="fetch: 표 내려받기 / find: 이름으로 찾기")
    p.add_argument("query", nargs="?", default="", help="find 에 쓸 지역명 또는 코드")
    p.add_argument("--max-pages", type=int, default=30, help="fetch 시 페이지 상한.")
    p.add_argument("--qps", type=float, default=DEFAULT_QPS)
    p.add_argument("--timeout", type=int, default=30)
    p.set_defaults(func=cmd_lawd_code, needs_key=True)

    p = sub.add_parser("check-key", help="인증키가 통하는지 1건 호출로 확인 (키 값 출력 안 함)")
    p.add_argument("--output", help="(선택) 결과를 파일로도 저장")
    p.add_argument("--qps", type=float, default=DEFAULT_QPS)
    p.add_argument("--timeout", type=int, default=30)
    p.set_defaults(func=cmd_check_key, needs_key=True)

    p = sub.add_parser("probe-endpoints", help="인증키 없이 오퍼레이션 경로 생존 확인(진단용)")
    p.add_argument("--output", help="(선택) 결과를 파일로 저장")
    p.set_defaults(func=cmd_probe, needs_key=False)

    p = sub.add_parser("raw", help="탈출구 — 오퍼레이션과 파라미터를 직접 지정")
    p.add_argument("--operation", required=True, help="예: RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev")
    p.add_argument("--params", help="추가 파라미터 JSON 객체 문자열")
    add_common(p)
    p.set_defaults(func=cmd_raw, needs_key=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not getattr(args, "needs_key", True):
            args.func(args)
            return 0
        if args.command == "lawd-code" and args.action == "find":
            cmd_lawd_code(None, args)
            return 0
        client = Client(load_service_key(), qps=args.qps, timeout=args.timeout)
        args.func(client, args)
        return 0
    except MolitError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("중단됨.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
