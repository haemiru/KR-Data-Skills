# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""식품의약품안전처 의약품개요정보(e약은요) CLI 래퍼.

표준 라이브러리만 쓴다. 설계 원칙은 저장소 README 참조.

이 API 는 같은 포털이지만 앞선 두 스킬과 또 다르다(2026-08-05 실측):
  - `resultCode` 가 2자리(`"00"`)다. 실거래가는 3자리(`"000"`)
  - `type=json` 을 **빼면 봉투 모양이 바뀐다**. items 가 `{"item": {...}}` 가 되고
    빈 값이 `""`, 숫자가 문자열로 온다. 항상 붙인다
  - `numOfRows` 상한이 **500** 이다. 넘기면 code 11
  - 전체가 **4,775건**뿐이라 전수 수집이 10회 호출로 끝난다
  - 같은 `itemSeq` 가 여러 행으로 온다 — **`itemImage` 만 다르다**
"""
from __future__ import annotations

import argparse
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
BASE_URL = "https://apis.data.go.kr/1471000"
OPERATION = "DrbEasyDrugInfoService/getDrbEasyDrugList"

KEY_NAME = "DATA_GO_KR_SERVICE_KEY"
LEGACY_KEY_NAMES = ("SERVICE_KEY", "DATA_GO_KR_API_KEY", "MFDS_API_KEY")

USER_AGENT = "KR-Data-Skills/0.1 (+https://github.com/haemiru/KR-Data-Skills)"

# 실측 상한. 501 이상은 code 11 로 떨어진다.
MAX_ROWS_PER_PAGE = 500
DEFAULT_QPS = 2.0

# 2026-08-05 실측 전수 건수. 0건 경고에서 "필터가 안 먹은 것 아닌가"를 판단하는 데 쓴다.
KNOWN_TOTAL = 4775

# CLI 플래그 -> API 파라미터. **이 표에 없는 이름은 보내지 않는다.**
# 이 API 는 모르는 파라미터를 조용히 무시하고 전체를 돌려준다(실측). 화이트리스트가 방어선이다.
SEARCH_PARAMS: dict[str, tuple[str, str]] = {
    "name": ("itemName", "제품명 (부분일치)"),
    "company": ("entpName", "업체명 (부분일치)"),
    "item_seq": ("itemSeq", "품목기준코드 (정확일치)"),
    "efficacy": ("efcyQesitm", "효능 본문 검색"),
    "usage": ("useMethodQesitm", "사용법 본문 검색"),
    "warning": ("atpnWarnQesitm", "경고 본문 검색"),
    "caution": ("atpnQesitm", "주의사항 본문 검색"),
    "interaction": ("intrcQesitm", "상호작용 본문 검색"),
    "side_effect": ("seQesitm", "부작용 본문 검색"),
    "storage": ("depositMethodQesitm", "보관법 본문 검색"),
    "open_date": ("openDe", "공개일자 YYYYMMDD (앞자리 일치)"),
    "updated": ("updateDe", "수정일자 (앞 8자까지만 동작. YYYY-MM-DD 는 항상 0건)"),
}

# 응답 필드 14개 (2026-08-05, 표본 4,775건 전수 확정)
ALL_FIELDS = (
    "itemSeq", "itemName", "entpName", "bizrno",
    "efcyQesitm", "useMethodQesitm", "atpnWarnQesitm", "atpnQesitm",
    "intrcQesitm", "seQesitm", "depositMethodQesitm",
    "openDe", "updateDe", "itemImage",
)

# 본문이 긴 필드. 한 건이 수천 자라 그대로 쏟으면 컨텍스트가 폭발한다.
TEXT_FIELDS = (
    "efcyQesitm", "useMethodQesitm", "atpnWarnQesitm", "atpnQesitm",
    "intrcQesitm", "seQesitm", "depositMethodQesitm",
)

PRESETS: dict[str, tuple[str, ...]] = {
    "brief": ("itemSeq", "itemName", "entpName"),
    "core": ("itemSeq", "itemName", "entpName", "efcyQesitm", "useMethodQesitm"),
    "full": ALL_FIELDS,
}

ERROR_HINTS = {
    "11": "필수 파라미터 오류로 나오지만 실제 원인은 대개 "
    f"numOfRows 가 상한({MAX_ROWS_PER_PAGE})을 넘은 것이다. 메시지 뒤쪽을 볼 것.",
    "12": "그런 경로가 없다. 오퍼레이션명을 확인할 것.",
    "20": "서비스 접근이 거부됐다. 활용신청 상태를 확인할 것.",
    "22": "일일 트래픽 한도를 초과했다(개발계정 10,000건/일).",
    "30": f"등록되지 않은 서비스키다. 저장소 루트 .env 의 {KEY_NAME} 값과, "
    "**이 데이터셋(15075057)의 활용신청 여부**를 확인할 것. "
    "포털 인증키는 하나지만 활용신청은 데이터셋마다 따로 해야 한다. "
    "발급 직후라면 반영에 최대 1시간 걸린다.",
    "31": "활용기간이 만료된 키다.",
    "32": "등록되지 않은 IP다.",
}


class MfdsError(Exception):
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
    raise MfdsError(
        f"인증키를 찾지 못했다. 저장소 루트 .env 에 {KEY_NAME} 을 등록할 것.\n"
        "  발급: https://www.data.go.kr/data/15075057/openapi.do → 활용신청 → 개발계정(자동승인)\n"
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

    def get(self, operation: str, params: dict) -> dict:
        merged = {k: v for k, v in params.items() if v not in (None, "")}
        merged["serviceKey"] = self._key
        # type=json 을 빼면 봉투 모양이 바뀐다. 절대 생략하지 않는다.
        merged["type"] = "json"
        query = urllib.parse.urlencode(merged, encoding="utf-8")
        full = f"{BASE_URL}/{operation}?{query}"

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
        raise MfdsError(_mask(f"요청 실패: {last_error}", self._raw_key))

    def _raise_api_error(self, body: str) -> None:
        found = _extract_error(body)
        if not found:
            raise MfdsError(_mask(f"알 수 없는 오류 응답: {body[:300]}", self._raw_key))
        code, err_msg, auth_msg = found
        hint = ERROR_HINTS.get(code, "")
        raise MfdsError(
            _mask(
                f"API 오류 (code {code}) {err_msg} / {auth_msg}"
                + (f"\n  → {hint}" if hint else ""),
                self._raw_key,
            )
        )

    def _parse(self, body: str) -> dict:
        stripped = body.lstrip()
        if stripped.startswith("<"):
            self._raise_api_error(body)
            raise MfdsError("XML 응답을 해석하지 못했다.")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            raise MfdsError(_mask(f"JSON 파싱 실패: {body[:300]}", self._raw_key)) from None
        if "OpenAPI_ServiceResponse" in payload or "cmmMsgHeader" in payload:
            self._raise_api_error(body)
        header = payload.get("header") or {}
        code = str(header.get("resultCode", "")).strip()
        # 이 API 는 정상이 "00" 이다. 실거래가("000")와 다르다.
        if code and code not in ("00", "000"):
            hint = ERROR_HINTS.get(code, "")
            raise MfdsError(
                f"API 오류 (resultCode {code}) {header.get('resultMsg', '')}"
                + (f"\n  → {hint}" if hint else "")
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
        if isinstance(header, dict) and str(header.get("resultCode", "")) not in ("00", "000", ""):
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
    """`body.items` 를 list[dict] 로 정규화한다.

    `type=json` 이면 항상 list 지만, 방어적으로 dict/`{"item": ...}` 형태도 받는다.
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
    except (TypeError, ValueError):
        return 0


def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _norm_open_date(value) -> str | None:
    """openDe 는 `20210129`, updateDe 는 `2024-05-09` 로 형식이 다르다.

    둘을 `YYYY-MM-DD` 로 맞춰 둬야 날짜 비교에서 사고가 안 난다.
    """
    if _blank(value):
        return None
    digits = re.sub(r"\D", "", str(value))
    if len(digits) != 8:
        return None
    return f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]}"


def merge_by_item_seq(items: list[dict]) -> tuple[list[dict], int]:
    """같은 `itemSeq` 행을 하나로 합친다.

    2026-08-05 전수 실측: 4,775행 중 14개 itemSeq 가 2~3행으로 쪼개져 있고,
    **달라지는 필드는 `itemImage` 하나뿐이다**(다른 13개 필드는 전부 동일).
    그래서 이미지를 배열로 모으면 정보 손실 없이 합칠 수 있다.
    """
    merged: dict[str, dict] = {}
    order: list[str] = []
    collapsed = 0
    for row in items:
        seq = str(row.get("itemSeq") or "")
        if not seq:
            # 키가 없는 행은 버리지 않는다. 조용히 사라지는 것보다 중복이 낫다.
            order.append(f"__nokey__{len(order)}")
            merged[order[-1]] = dict(row)
            continue
        if seq not in merged:
            merged[seq] = dict(row)
            order.append(seq)
            continue
        collapsed += 1
        target = merged[seq]
        for key, value in row.items():
            if _blank(target.get(key)) and not _blank(value):
                target[key] = value
    return [merged[k] for k in order], collapsed


def enrich(items: list[dict], *, images: dict[str, list[str]] | None = None) -> list[dict]:
    out: list[dict] = []
    for row in items:
        row = dict(row)
        row["_openDate"] = _norm_open_date(row.get("openDe"))
        row["_updateDate"] = str(row.get("updateDe")).strip() if not _blank(row.get("updateDe")) else None
        seq = str(row.get("itemSeq") or "")
        if images is not None:
            urls = images.get(seq, [])
            row["_itemImages"] = urls
            row["_imageCount"] = len(urls)
        row["_hasImage"] = bool(row.get("itemImage")) or bool(row.get("_imageCount"))
        out.append(row)
    return out


def truncate_text(items: list[dict], limit: int) -> tuple[list[dict], int]:
    """긴 본문 필드를 자른다. **자른 사실을 행마다 남긴다.**

    조용히 잘리는 게 가장 위험하다는 저장소 원칙에 따라 `_truncated` 에 필드명을 남기고
    `_meta.truncated_rows` 로도 알린다.
    """
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


def project(items: list[dict], fields: tuple[str, ...] | None) -> list[dict]:
    """필드 투영. `_` 로 시작하는 파생 필드는 항상 남긴다."""
    if not fields:
        return items
    keep = set(fields)
    out = []
    for row in items:
        out.append({k: v for k, v in row.items() if k in keep or k.startswith("_")})
    return out


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

    if meta.get("merged_rows"):
        print(
            f"   같은 itemSeq 행 {meta['merged_rows']}건을 합쳤다"
            " (itemImage 만 다른 중복. --no-merge 로 끌 수 있다)."
        )
    if meta.get("truncated_rows"):
        print(
            f"⚠ 본문을 자른 행이 {meta['truncated_rows']}건이다 "
            f"(--truncate-text {meta.get('truncate_text')}). 행의 _truncated 를 볼 것."
        )
    if meta.get("truncated"):
        reason = meta.get("truncated_by")
        knob = f"--max-items {meta.get('max_items')}" if reason == "max-items" \
            else f"--max-pages {meta.get('max_pages')}"
        print(
            f"⚠ 전체 {meta.get('total_count')}건 중 {meta.get('returned')}건만 받았다 "
            f"({knob} 에 걸림).\n"
            f"   그 값을 올리거나 조회 범위를 좁힐 것. "
            "이 결과를 '전부'라고 보고하지 말 것."
        )
    if size_kb > 500:
        has_text = any(f in TEXT_FIELDS for f in (meta.get("fields") or ()))
        if has_text:
            advice = ("본문 필드가 한 건에 수천 자다.\n"
                      "   목록만 필요하면 --preset brief, 본문이 필요하면 --truncate-text 500 을 쓸 것.")
        else:
            advice = ("건수 자체가 많다.\n"
                      "   조건을 좁히거나 --max-items 로 줄일 것.")
        print(f"⚠ 결과 파일이 크다({size_kb:.0f} KB). {advice}\n"
              "   이 파일을 통째로 읽지 말 것. 필요한 부분만 골라 읽는다.")

    total = meta.get("total_count")
    filters = meta.get("filters") or {}
    if total == 0:
        print(
            "🔴 0건이다. 이 API 는 **없는 조건에도 code 00 정상 응답**을 준다(실측).\n"
            f"   보낸 조건: {json.dumps(filters, ensure_ascii=False)}\n"
            "   '그런 약이 없다'고 단정하기 전에 조건을 확인할 것."
        )
        if "updateDe" in filters and len(str(filters["updateDe"])) > 8:
            print(
                "   → updateDe 가 8자를 넘었다. 이 API 는 9자 이상이면 무조건 0건이다(실측).\n"
                "     'YYYY-MM' 까지만 줄 것."
            )
    elif filters and total == KNOWN_TOTAL:
        print(
            f"🔴 조건을 줬는데 결과가 전체 건수({KNOWN_TOTAL})와 같다.\n"
            "   이 API 는 **모르는 파라미터를 조용히 무시**한다(실측). 필터가 안 먹었을 수 있다.\n"
            "   결과를 '조건에 맞는 것'이라고 보고하지 말 것."
        )


# ---------------------------------------------------------------------------
# 수집
# ---------------------------------------------------------------------------
def collect(client: Client, filters: dict, args) -> tuple[list[dict], dict]:
    limit = min(int(args.limit), MAX_ROWS_PER_PAGE)
    if int(args.limit) > MAX_ROWS_PER_PAGE:
        print(
            f"⚠ --limit {args.limit} 은 상한을 넘는다. {MAX_ROWS_PER_PAGE} 로 낮춰 호출한다"
            f" (실측 상한 {MAX_ROWS_PER_PAGE}, 초과 시 code 11)."
        )

    rows: list[dict] = []
    raw_pages: list[dict] = []
    grand_total = 0
    truncated_by: str | None = None
    page = 1

    while page <= args.max_pages:
        payload = client.get(OPERATION, {**filters, "pageNo": str(page), "numOfRows": str(limit)})
        if args.keep_raw:
            raw_pages.append(payload)
        if page == 1:
            grand_total = total_count(payload)
        got = extract_items(payload)
        if not got:
            break
        rows.extend(got)
        if len(rows) >= args.max_items:
            rows = rows[: args.max_items]
            truncated_by = "max-items"
            break
        if len(rows) >= grand_total:
            break
        page += 1
    else:
        # while 이 break 없이 끝났다 = --max-pages 상한에 걸렸다.
        # 사유를 max-items 로 뭉뚱그리면 사용자가 엉뚱한 값을 올리게 된다.
        if len(rows) < grand_total:
            truncated_by = "max-pages"

    meta: dict[str, object] = {
        "source": "식품의약품안전처 의약품개요정보(e약은요)",
        "dataset": "https://www.data.go.kr/data/15075057/openapi.do",
        "operation": OPERATION,
        "filters": filters,
        "total_count": grand_total,
        "returned": len(rows),
        "pages_fetched": page,
        "rows_per_page": limit,
        "api_calls": client.call_count,
        "truncated": truncated_by is not None,
        "truncated_by": truncated_by,
        "max_items": args.max_items,
        "max_pages": args.max_pages,
    }
    return rows, (meta | ({"_raw_pages": len(raw_pages)} if raw_pages else {}))


def _postprocess(rows: list[dict], meta: dict, args) -> list[dict]:
    images: dict[str, list[str]] = {}
    if not args.no_merge:
        for row in rows:
            seq = str(row.get("itemSeq") or "")
            url = row.get("itemImage")
            if seq and url and url not in images.setdefault(seq, []):
                images[seq].append(url)
        rows, collapsed = merge_by_item_seq(rows)
        meta["merged_rows"] = collapsed
        rows = enrich(rows, images=images)
    else:
        meta["merged_rows"] = 0
        rows = enrich(rows)

    rows, touched = truncate_text(rows, args.truncate_text)
    meta["truncate_text"] = args.truncate_text
    meta["truncated_rows"] = touched

    if args.fields:
        fields = tuple(f.strip() for f in args.fields.split(",") if f.strip())
        meta["preset"] = "custom"
    else:
        fields = PRESETS[args.preset]
        meta["preset"] = args.preset
    meta["fields"] = list(fields)
    return project(rows, fields)


# ---------------------------------------------------------------------------
# 명령
# ---------------------------------------------------------------------------
def cmd_search(client: Client, args) -> None:
    filters: dict[str, str] = {}
    for flag, (param, _desc) in SEARCH_PARAMS.items():
        value = getattr(args, flag, None)
        if value:
            filters[param] = str(value).strip()

    if not filters and not args.all:
        raise MfdsError(
            "조건이 하나도 없다. 전체 4,775건을 받으려면 --all 을 명시할 것.\n"
            "  조건 예: --name 타이레놀 / --efficacy 두통 / --company 유한양행"
        )
    updated = filters.get("updateDe")
    if updated and len(updated) > 8:
        raise MfdsError(
            f"--updated '{updated}' 는 {len(updated)}자다. "
            "이 API 는 updateDe 가 9자 이상이면 무조건 0건을 준다(실측).\n"
            "  'YYYY'(2024) 또는 'YYYY-MM'(2024-05) 까지만 줄 것.\n"
            "  하루 단위가 꼭 필요하면 --all 로 받아 _updateDate 로 직접 거를 것."
        )

    rows, meta = collect(client, filters, args)
    items = _postprocess(rows, meta, args)
    write_output(args.output, meta, items, [] if args.keep_raw else None)


def cmd_check_key(client: Client, args) -> None:
    payload = client.get(OPERATION, {"pageNo": "1", "numOfRows": "1"})
    items = extract_items(payload)
    total = total_count(payload)
    print("인증키 확인 결과")
    print(f"  키 형태      : {client.key_form}")
    print(f"  엔드포인트   : {BASE_URL}/{OPERATION}")
    print(f"  응답         : 정상 (resultCode 00)")
    print(f"  전체 건수    : {total:,}건")
    if items:
        print(f"  응답 필드    : {len(items[0])}개")
        print(f"  표본         : {items[0].get('itemName')} / {items[0].get('entpName')}")
    if total != KNOWN_TOTAL:
        print(
            f"  ※ 전체 건수가 실측 기준선({KNOWN_TOTAL:,})과 다르다. "
            "데이터가 갱신된 것이니 references/fields.md 의 수치를 다시 볼 것."
        )
    if args.output:
        write_output(args.output, {"total_count": total, "api_calls": client.call_count},
                     items, None)


def cmd_probe(args) -> None:
    """인증키 없이 경로 생존을 확인한다.

    이 포털은 **라우팅이 인증보다 먼저**다. 더미 키로 불러 보면
    code 30(경로는 유효, 키만 틀림) 과 code 12(경로 없음) 로 갈린다.
    """
    targets = [
        (OPERATION, "의약품개요정보(e약은요) — 이 스킬이 쓰는 경로"),
        ("DrbEasyDrugInfoService/getNoSuchOperation", "일부러 틀린 경로 (대조군)"),
    ]
    results = []
    for operation, label in targets:
        url = f"{BASE_URL}/{operation}?serviceKey=PROBE_DUMMY_KEY&type=json&numOfRows=1"
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        code, msg = "?", ""
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception as exc:  # 네트워크 자체가 안 될 때
            body = ""
            msg = f"{type(exc).__name__}"
        found = _extract_error(body) if body else None
        if found:
            code, msg = found[0], found[1]
        alive = code == "30"
        results.append({"operation": operation, "label": label, "code": code,
                        "message": msg, "path_alive": alive})
        mark = "✅ 경로 유효" if alive else ("❌ 경로 없음" if code == "12" else f"? code {code}")
        print(f"  {mark:12s} {operation}\n               {label} (code {code} {msg})")

    print("\n  code 30 = 경로는 살아 있고 키만 틀림 / code 12 = 그런 경로 없음")
    if args.output:
        out = pathlib.Path(args.output)
        if out.parent and not out.parent.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  저장: {out}")


def cmd_raw(client: Client, args) -> None:
    extra: dict = {}
    if args.params:
        try:
            extra = json.loads(args.params)
        except json.JSONDecodeError as exc:
            raise MfdsError(f"--params 가 JSON 객체가 아니다: {exc}") from None
        if not isinstance(extra, dict):
            raise MfdsError("--params 는 JSON 객체여야 한다.")
    unknown = [k for k in extra if k not in {p for p, _ in SEARCH_PARAMS.values()}
               and k not in ("pageNo", "numOfRows")]
    if unknown:
        print(
            f"⚠ 알려지지 않은 파라미터: {', '.join(unknown)}\n"
            "   이 API 는 모르는 파라미터를 **조용히 무시하고 전체를 돌려준다**(실측).\n"
            "   결과 건수가 전체와 같은지 반드시 확인할 것."
        )
    rows, meta = collect(client, extra, args)
    items = _postprocess(rows, meta, args)
    write_output(args.output, meta, items, [] if args.keep_raw else None)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", required=True, help="(필수) 결과 JSON을 쓸 파일 경로.")
    parser.add_argument("--preset", choices=sorted(PRESETS), default="core",
                        help="필드 묶음. brief=목록용 3개 / core=기본 5개 / full=14개 전부 "
                             "(기본: core). 본문이 한 건에 수천 자라 full 은 무겁다.")
    parser.add_argument("--fields", help="쉼표로 구분한 필드명. 주면 --preset 을 덮어쓴다. "
                                         "파생 필드(_로 시작)는 항상 남는다.")
    parser.add_argument("--truncate-text", type=int, default=0,
                        help="본문 필드를 N자로 자른다 (0=자르지 않음, 기본 0). "
                             "자른 행에는 _truncated 가 붙는다.")
    parser.add_argument("--no-merge", action="store_true",
                        help="같은 itemSeq 행을 합치지 않는다. 기본은 합친다 "
                             "(itemImage 만 다른 중복이 실측 14건 있다).")
    parser.add_argument("--limit", type=int, default=100,
                        help=f"페이지당 건수 (기본 100, 상한 {MAX_ROWS_PER_PAGE}).")
    parser.add_argument("--max-pages", type=int, default=10, help="최대 페이지 (기본 10).")
    parser.add_argument("--max-items", type=int, default=2000, help="총 수집 상한 (기본 2000).")
    parser.add_argument("--keep-raw", action="store_true", help="원본 응답을 _raw 에 함께 저장.")
    parser.add_argument("--qps", type=float, default=DEFAULT_QPS, help="초당 요청 수 상한.")
    parser.add_argument("--timeout", type=int, default=30, help="요청 타임아웃(초).")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mfds_api.py",
        description="식품의약품안전처 의약품개요정보(e약은요) CLI 래퍼",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("search", help="의약품 조회 (제품명·업체명·효능 등)")
    for flag, (param, desc) in SEARCH_PARAMS.items():
        p.add_argument(f"--{flag.replace('_', '-')}", dest=flag,
                       help=f"{desc} [{param}]")
    p.add_argument("--all", action="store_true",
                   help=f"조건 없이 전체를 받는다 (실측 {KNOWN_TOTAL:,}건. "
                        f"--limit {MAX_ROWS_PER_PAGE} 면 10회 호출).")
    add_common(p)
    p.set_defaults(func=cmd_search, needs_key=True)

    p = sub.add_parser("check-key", help="인증키가 통하는지 1건 호출로 확인 (키 값 출력 안 함)")
    p.add_argument("--output", help="(선택) 결과를 파일로도 저장")
    p.add_argument("--qps", type=float, default=DEFAULT_QPS)
    p.add_argument("--timeout", type=int, default=30)
    p.set_defaults(func=cmd_check_key, needs_key=True)

    p = sub.add_parser("probe-endpoints", help="인증키 없이 오퍼레이션 경로 생존 확인(진단용)")
    p.add_argument("--output", help="(선택) 결과를 파일로 저장")
    p.set_defaults(func=cmd_probe, needs_key=False)

    p = sub.add_parser("raw", help="탈출구 — 파라미터를 직접 지정")
    p.add_argument("--params", help="파라미터 JSON 객체 문자열")
    add_common(p)
    p.set_defaults(func=cmd_raw, needs_key=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not getattr(args, "needs_key", True):
            args.func(args)
            return 0
        client = Client(load_service_key(), qps=args.qps, timeout=args.timeout)
        args.func(client, args)
        return 0
    except MfdsError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("중단됨.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
