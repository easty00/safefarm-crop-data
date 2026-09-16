# 농작업일정의 다섯 번째 오퍼레이션(workScheduleEraInfoJsonLst)을 수집하는 스크립트입니다.
# 자세한 사용법은 "농작업일정_JSON_수집_사용법.md" 를 읽어주세요.
#
# 이 오퍼레이션은 지금까지 한 번도 부른 적이 없습니다.
# farmWorkingPlanNew 폴더의 활용가이드 docx 안에만 적혀 있고, 샘플소스에는 없습니다.
#
# 기존 workScheduleEraInfoLst 는 월별 달력을 HTML 표로 줍니다. 칸을 세어서
# 시기를 알아내야 하는데, 이 오퍼레이션은 시작월·시작순·종료월·종료순을
# 숫자로 바로 줍니다. 작형(farmWorkFlag)과 동영상 주소도 여기에만 있습니다.

import csv
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

BASE = "http://api.nongsaro.go.kr/service/farmWorkingPlanNew"
HERE = Path(__file__).resolve().parent
OUT = HERE / "수집결과"
RAW = OUT / "raw"
WAIT = 0.4
BAD_CHARS = '\\/:*?"<>|'

# 매뉴얼(활용가이드 docx 5항)에 적힌 응답 칸
FIELDS = ["cntntsNo", "kidofcomdtySeCode", "kidofcomdtySeCodeNm", "farmWorkFlag",
          "infoSeCode", "infoSeCodeNm", "opertNm",
          "beginMon", "beginEra", "endMon", "endEra", "reqreMonth", "vodUrl"]

ERA_ORDER = {"상": 0, "중": 1, "하": 2}


def api_key() -> str:
    """.env 의 AGRI_API 값을 읽는다. 키를 코드에 적어두지 않기 위해서다."""
    env = HERE / ".env"
    if not env.exists():
        sys.exit(f".env 가 없습니다: {env}")
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("AGRI_API="):
            return line.split("=", 1)[1].strip()
    sys.exit(".env 안에서 AGRI_API 를 찾지 못했습니다.")


def safe(name: str) -> str:
    return "".join("_" if ch in BAD_CHARS else ch for ch in name).strip() or "이름없음"


def fetch(url: str) -> bytes:
    """한 번 실패하면 3초 쉬고 한 번 더 시도한다."""
    last = None
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(url, timeout=90) as res:
                return res.read()
        except Exception as err:
            last = err
            if attempt == 1:
                time.sleep(3)
    raise RuntimeError(f"두 번 모두 실패: {url}\n  {last}")


def call(operation: str, save_as: str, **params) -> ET.Element:
    """API 를 부르고 원문을 raw 에 저장한 뒤 파싱해 돌려준다. 이미 있으면 다시 안 부른다."""
    path = RAW / f"{safe(save_as)}.xml"
    if path.exists():
        return ET.fromstring(path.read_bytes())

    query = urllib.parse.urlencode({"apiKey": KEY, **params})
    data = fetch(f"{BASE}/{operation}?{query}")

    root = ET.fromstring(data)
    code = root.findtext("./header/resultCode", "")
    if code != "00":
        raise RuntimeError(f"resultCode {code}: {root.findtext('./header/resultMsg', '')}")

    path.write_bytes(data)
    time.sleep(WAIT)
    return root


def rows(root: ET.Element) -> list[dict]:
    return [{child.tag: (child.text or "").strip() for child in item} for item in root.iter("item")]


def sun_index(month: str, era: str) -> int:
    """'4월 상순' 을 0~35 번호로 바꾼다. 1월 상순이 0, 12월 하순이 35.

    날짜 계산과 정렬을 하려면 월과 순을 하나의 숫자로 합쳐두는 편이 편하다.
    """
    try:
        m = int(month)
    except (TypeError, ValueError):
        return -1
    if not 1 <= m <= 12 or era not in ERA_ORDER:
        return -1
    return (m - 1) * 3 + ERA_ORDER[era]


def middle_day(month: str, era: str) -> str:
    """순을 날짜로 바꾼다. 로드맵 §6-2 규칙대로 상순 5일·중순 15일·하순 25일."""
    day = {"상": 5, "중": 15, "하": 25}.get(era)
    try:
        m = int(month)
    except (TypeError, ValueError):
        return ""
    if not day or not 1 <= m <= 12:      # 13월 같은 값이 그대로 나가지 않도록 막는다
        return ""
    return f"{m:02d}-{day:02d}"


def load_index() -> list[dict]:
    """작물목록.csv 가 있으면 쓰고, 없으면 API 로 목록을 다시 만든다."""
    path = OUT / "작물목록.csv"
    if path.exists():
        with open(path, encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    print("  작물목록.csv 가 없어 목록부터 받습니다")
    index = []
    for cat in rows(call("workScheduleGrpList", "grp")):
        code, name = cat["kidofcomdtySeCode"], cat["codeNm"]
        for crop in rows(call("workScheduleLst", f"lst_{code}", kidofcomdtySeCode=code)):
            index.append({"분류코드": code, "분류명": name,
                          "작물명": crop.get("sj", ""), "cntntsNo": crop.get("cntntsNo", "")})
    return index


def collect(index: list[dict], limit: int | None) -> tuple[list[dict], list[str]]:
    targets = index[:limit] if limit else index
    out, failed = [], []

    for i, crop in enumerate(targets, 1):
        no = crop.get("cntntsNo", "")
        label = f"{crop.get('분류명','')}/{crop.get('작물명','')}"
        if not no:
            continue
        try:
            got = rows(call("workScheduleEraInfoJsonLst", f"erajson_{no}", cntntsNo=no))
        except Exception as err:
            failed.append(f"{label} (cntntsNo={no}): {err}")
            print(f"  [{i}/{len(targets)}] {label} … 실패: {err}")
            continue

        for r in got:
            begin, end = sun_index(r.get("beginMon"), r.get("beginEra")), sun_index(r.get("endMon"), r.get("endEra"))
            out.append({
                "분류명": crop.get("분류명", ""), "작물명": crop.get("작물명", ""),
                **{k: r.get(k, "") for k in FIELDS},
                "시작순번": begin, "종료순번": end,
                "지속순수": (end - begin + 1) if begin >= 0 and end >= begin else "",
                "시작중앙일": middle_day(r.get("beginMon"), r.get("beginEra")),
                "종료중앙일": middle_day(r.get("endMon"), r.get("endEra")),
            })
        print(f"  [{i}/{len(targets)}] {label} … {len(got)}건")

    return out, failed


def write_report(items: list[dict], failed: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if items:
        with open(OUT / "농작업시기.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(items[0].keys()))
            w.writeheader()
            w.writerows(items)

    kinds = Counter(x["infoSeCodeNm"] for x in items)
    flags = Counter(x["farmWorkFlag"] for x in items if x["farmWorkFlag"])
    crops = {(x["분류명"], x["작물명"]) for x in items}

    out = ["# 농작업일정 시기정보(workScheduleEraInfoJsonLst) 수집 결과", "",
           f"작물 {len(crops)}종 / 시기 항목 {len(items)}건", "",
           "## 정보 구분(infoSeCodeNm)", ""]
    for k, n in kinds.most_common():
        out.append(f"- {k or '(빈값)'} : {n}건")

    out += ["", "## 작형(farmWorkFlag)", "", f"값이 있는 항목 {sum(flags.values())}건 / 종류 {len(flags)}가지", ""]
    for k, n in flags.most_common(30):
        out.append(f"- {k} : {n}건")

    withvod = sum(1 for x in items if x["vodUrl"])
    out += ["", "## 그 밖에", "",
            f"- 동영상 주소가 있는 항목 {withvod}건",
            f"- 순 번호 변환 실패(월·순 값이 이상) {sum(1 for x in items if x['시작순번'] == -1)}건"]

    out += ["", "## 표본 (앞 25건)", "",
            "| 작물 | 구분 | 작업 | 시작 | 종료 | 순수 |", "|---|---|---|---|---|---|"]
    for x in items[:25]:
        out.append(f"| {x['작물명']} | {x['infoSeCodeNm']} | {x['opertNm']} | "
                   f"{x['beginMon']}월 {x['beginEra']} | {x['endMon']}월 {x['endEra']} | {x['지속순수']} |")

    if failed:
        out += ["", "## 실패", ""] + [f"- {x}" for x in failed]

    (OUT / "농작업시기_요약.md").write_text("\n".join(out), encoding="utf-8")


def main() -> None:
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    RAW.mkdir(parents=True, exist_ok=True)

    print("[1/2] 작물 목록을 준비합니다")
    index = load_index()
    print(f"  {len(index)}건\n")

    print("[2/2] 작물마다 시기 정보를 받습니다")
    items, failed = collect(index, limit)

    write_report(items, failed)
    print(f"\n끝났습니다. 결과: {OUT}")
    print("  농작업시기_요약.md 와 농작업시기.csv 를 저에게 보여주시면 됩니다")


if __name__ == "__main__":
    KEY = api_key()
    main()
