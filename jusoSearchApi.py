"""도로명주소 API 조회 결과에 성공 여부를 포함해 CSV로 출력한다.

사용 예시:
    python jusoSearchApi.py --input addresses.csv --output result.csv

승인키는 스크립트와 같은 폴더의 ``.env`` 파일에 아래처럼 설정한다.
    JUSO_API_KEY=발급받은_승인키

입력 CSV의 필수 컬럼은 ``pk,addrnm`` 이다. 헤더가 있는 CSV와 없는 CSV 모두
지원한다. API 검색 결과가 하나 이상이면 조회성공은 TRUE이며, 그 중 반환된
도로명주소가 입력과 동일하면 정확일치도 TRUE이다.
"""

import argparse
import csv
import html
import logging
import os
import re
import time
from pathlib import Path

import requests


logger = logging.getLogger("jusoSearchApi")

# 행정안전부 도로명주소 변환 API 정보
API_URL = "https://business.juso.go.kr/addrlink/addrLinkApi.do"
ENV_FILE = Path(__file__).with_name(".env")
OUTPUT_FIELDS = (
    "pk",
    "addrnm",
    "조회성공",
    "정확일치",
    "상태",
    "반환도로명주소",
    "반환지번주소",
    "오류코드",
    "오류메시지",
)


def normalize_address(address: str) -> str:
    """공백과 괄호 속 참고정보를 제외해 API 반환 주소와 비교한다."""
    return re.sub(r"\s+", "", re.sub(r"\([^)]*\)", "", address or ""))


def error_result(status: str, message: str = "", code: str = "") -> dict:
    """CSV 출력 형식에 맞는 실패 결과를 만든다."""
    return {
        "조회성공": False,
        "정확일치": False,
        "상태": status,
        "반환도로명주소": "",
        "반환지번주소": "",
        "오류코드": code,
        "오류메시지": message,
    }


def load_env_file(path: Path = ENV_FILE) -> None:
    """간단한 KEY=VALUE 형식의 환경설정 파일을 불러온다.

    운영체제에 이미 설정된 환경변수는 ``.env`` 값으로 덮어쓰지 않는다.
    """
    if not path.is_file():
        return

    with path.open("r", encoding="utf-8-sig") as file:
        for line_number, raw_line in enumerate(file, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()
            if "=" not in line:
                logger.warning("%s:%d의 환경설정을 무시합니다.", path, line_number)
                continue

            name, value = (part.strip() for part in line.split("=", 1))
            if not name:
                continue
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            os.environ.setdefault(name, value)


def resolve_api_key(api_key: str | None = None) -> str:
    """명시한 키, 환경변수 또는 ``.env`` 순서로 승인키를 선택한다."""
    load_env_file()
    return (api_key or os.getenv("JUSO_API_KEY") or "").strip()


def lookup_address(
    road_address: str,
    *,
    api_key: str | None = None,
    session: requests.Session | None = None,
    timeout: float = 15,
    max_retries: int = 3,
) -> dict:
    """주소 조회 결과와 성공 여부를 반환한다.

    ``조회성공``은 API가 검색 결과를 하나 이상 반환했는지, ``정확일치``는
    반환된 도로명주소 중 입력 주소와 일치하는 주소가 있는지를 뜻한다.
    """
    road_address = road_address.strip()
    if not road_address:
        return error_result("입력오류", "주소가 비어 있습니다.", "INPUT_EMPTY")

    resolved_api_key = resolve_api_key(api_key)
    if not resolved_api_key:
        return error_result(
            "설정오류",
            "--api-key 또는 JUSO_API_KEY 환경변수로 승인키를 지정하세요.",
            "API_KEY_MISSING",
        )

    params = {
        "confmKey": resolved_api_key,
        "currentPage": 1,
        "countPerPage": 10,
        "keyword": road_address,
        "resultType": "json",
        "hstryYn": "N",
        "firstSort": "road",
        "addInfoYn": "N",
    }

    client = session or requests
    for attempt in range(max_retries + 1):
        try:
            response = client.get(API_URL, params=params, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            results = data["results"]
            common = results["common"]
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            if attempt < max_retries:
                time.sleep(0.5 * (2**attempt))
                continue
            return error_result("API_통신오류", str(exc), "HTTP_OR_RESPONSE_ERROR")

        error_code = str(common.get("errorCode", ""))
        if error_code == "E0007" and attempt < max_retries:
            time.sleep(0.5 * (2**attempt))
            continue
        if error_code != "0":
            error_message = common.get("errorMessage") or common.get("errorMsg")
            return error_result(
                "API_오류",
                error_message or "알 수 없는 API 오류",
                error_code,
            )
        break

    items = results.get("juso") or []
    road_addrs = [
        html.unescape(item.get("roadAddr", "")) for item in items if isinstance(item, dict)
    ]
    land_addrs = [
        html.unescape(item.get("jibunAddr", "")) for item in items if isinstance(item, dict)
    ]
    if not items:
        return error_result("검색결과없음")

    target = normalize_address(road_address)
    exact_match = any(normalize_address(address) == target for address in road_addrs)
    return {
        "조회성공": True,
        "정확일치": exact_match,
        "상태": "정확일치" if exact_match else "유사결과",
        "반환도로명주소": " | ".join(road_addrs),
        "반환지번주소": " | ".join(land_addrs),
        "오류코드": "",
        "오류메시지": "",
    }


def convert_road_to_land(road_address: str, **lookup_options):
    """기존 호출부 호환용: 성공 시 지번주소 목록, 실패 시 None을 반환한다."""
    result = lookup_address(road_address, **lookup_options)
    return result["반환지번주소"].split(" | ") if result["조회성공"] else None


def read_addresses(input_path: Path):
    with input_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        rows = list(reader)

    if rows and [cell.strip().lower() for cell in rows[0][:2]] == ["pk", "addrnm"]:
        rows = rows[1:]
    for row in rows:
        if len(row) < 2:
            continue
        yield row[0].strip(), row[1].strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path, help="pk,addrnm 형식 CSV")
    parser.add_argument("--output", type=Path, help="결과 CSV 경로 (없으면 화면 출력)")
    parser.add_argument(
        "--api-key",
        help="도로명주소 검색 API 승인키 (미지정 시 환경변수 또는 .env 사용)",
    )
    parser.add_argument(
        "--request-interval",
        type=float,
        default=0.1,
        help="서로 다른 주소 조회 사이의 대기 시간(초, 기본값: 0.1)",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
        help="로그 상세 수준 (기본값: INFO)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    started_at = time.monotonic()
    logger.info("작업 시작: 입력=%s, 출력=%s", args.input, args.output or "표준출력")

    try:
        addresses = list(read_addresses(args.input))
    except (OSError, UnicodeError, csv.Error):
        logger.exception("입력 CSV를 읽지 못했습니다: %s", args.input)
        raise

    total = len(addresses)
    logger.info("조회 대상 %d건을 읽었습니다.", total)

    api_key = resolve_api_key(args.api_key)
    if not api_key:
        parser.error(".env, JUSO_API_KEY 환경변수 또는 --api-key로 승인키를 지정하세요.")
    if args.request_interval < 0:
        parser.error("--request-interval은 0 이상이어야 합니다.")

    output = args.output.open("w", encoding="utf-8-sig", newline="") if args.output else None
    session = requests.Session()
    cache = {}
    try:
        writer = csv.DictWriter(output or __import__("sys").stdout, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for index, (pk, address) in enumerate(addresses, start=1):
            item_started_at = time.monotonic()
            logger.info("[%d/%d] 조회 시작: pk=%s, 주소=%s", index, total, pk, address)
            cache_key = normalize_address(address)
            if cache_key in cache:
                lookup_result = cache[cache_key]
                logger.debug("[%d/%d] 중복 주소 캐시 사용: %s", index, total, address)
            else:
                lookup_result = lookup_address(address, api_key=api_key, session=session)
                cache[cache_key] = lookup_result
                if args.request_interval and index < total:
                    time.sleep(args.request_interval)
            result = {"pk": pk, "addrnm": address, **lookup_result}
            writer.writerow(result)
            if output:
                output.flush()
            logger.info(
                "[%d/%d] 조회 완료: pk=%s, 상태=%s, 소요=%.2f초",
                index,
                total,
                pk,
                result["상태"],
                time.monotonic() - item_started_at,
            )
    finally:
        session.close()
        if output:
            output.close()

    logger.info(
        "작업 완료: 전체=%d건, 총 소요=%.2f초, 출력=%s",
        total,
        time.monotonic() - started_at,
        args.output or "표준출력",
    )


if __name__ == "__main__":
    main()
