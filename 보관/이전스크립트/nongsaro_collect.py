# 농사로 농작업일정정보(farmWorkingPlanNew)를 전수 수집하는 스크립트입니다.
# 자세한 사용법은 "농작업일정_수집_사용법.md" 를 읽어주세요.

import csv
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = "http://api.nongsaro.go.kr/service/farmWorkingPlanNew"
HERE = Path(__file__).resolve().parent
OUT = HERE / "수집결과"
RAW = OUT / "raw"          # API 응답 원문. 값이 이상할 때 추적용
FILES = OUT / "첨부파일"
WAIT = 0.4                 # 요청 사이 쉬는 시간(초). 정부 서버라 몰아치지 않는다
BAD_CHARS = '\\/:*?"<>|'   # 윈도 파일명에 못 쓰는 글자


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
    """폴더·파일 이름으로 쓸 수 있게 다듬는다."""
    return "".join("_" if ch in BAD_CHARS else ch for ch in name).strip() or "이름없음"


def fetch(url: str) -> bytes:
    """한 번 실패하면 3초 쉬고 한 번 더 시도한다."""
    last = None
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(url, timeout=90) as res:
                return res.read()
        except Exception as err:  # 네트워크는 가끔 그냥 끊긴다
            last = err
            if attempt == 1:
                time.sleep(3)
    raise RuntimeError(f"두 번 모두 실패: {url}\n  {last}")


def call(operation: str, save_as: str, **params) -> ET.Element:
    """API 를 부르고 원문을 raw 에 저장한 뒤 파싱해 돌려준다.

    이미 받아둔 파일이 있으면 다시 부르지 않는다 — 중간에 끊겨도 이어서 할 수 있다.
    """
    path = RAW / f"{save_as}.xml"
    if path.exists():
        return ET.fromstring(path.read_bytes())

    query = urllib.parse.urlencode({"apiKey": KEY, **params})
    data = fetch(f"{BASE}/{operation}?{query}")

    # 서버가 오류를 XML 로 돌려주는 경우가 있다. 그걸 정상 응답으로 저장해두면
    # 다음 실행 때 건너뛰어 버려서 영영 모르게 된다 — 저장 전에 결과코드를 본다
    root = ET.fromstring(data)
    code = root.findtext("./header/resultCode", "")
    if code != "00":
        message = root.findtext("./header/resultMsg", "")
        raise RuntimeError(f"resultCode {code}: {message}")

    path.write_bytes(data)
    time.sleep(WAIT)
    return root


def rows(root: ET.Element) -> list[dict]:
    """<item> 하나를 dict 하나로 바꾼다."""
    return [{child.tag: (child.text or "").strip() for child in item} for item in root.iter("item")]


def build_index() -> list[dict]:
    """대분류 10개를 훑어 작물 목록을 만든다."""
    index = []
    for cat in rows(call("workScheduleGrpList", "grp")):
        code, name = cat["kidofcomdtySeCode"], cat["codeNm"]
        crops = rows(call("workScheduleLst", f"lst_{code}", kidofcomdtySeCode=code))
        print(f"  {name}({code}) {len(crops)}건")
        for crop in crops:
            index.append(
                {
                    "분류코드": code,
                    "분류명": name,
                    "작물명": crop.get("sj", ""),
                    "cntntsNo": crop.get("cntntsNo", ""),
                    "첨부파일명": crop.get("orginlFileNm", ""),
                    "첨부링크": crop.get("fileDownUrlInfo", ""),
                }
            )
    return index


def download(row: dict) -> str:
    """첨부파일을 분류별 폴더에 내려받는다. 이미 있으면 건너뛴다."""
    url, name = row["첨부링크"], row["첨부파일명"]
    if not url or not name:
        return "없음"

    folder = FILES / safe(row["분류명"])
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / safe(name)
    if path.exists():
        return "이미있음"

    path.write_bytes(fetch(url))
    time.sleep(WAIT)
    return "받음"


def main() -> None:
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    skip_files = "--no-files" in sys.argv

    for folder in (OUT, RAW, FILES):
        folder.mkdir(parents=True, exist_ok=True)

    print("[1/3] 작물 목록을 받습니다")
    index = build_index()
    print(f"  총 {len(index)}건\n")

    targets = index[:limit] if limit else index
    what = "상세 정보" if skip_files else "상세 정보와 첨부파일"
    print(f"[2/3] {what}을 받습니다 ({len(targets)}건)")

    failed = []
    for i, row in enumerate(targets, 1):
        no = row["cntntsNo"]
        label = f"{row['분류명']}/{row['작물명']}"
        try:
            call("workScheduleDtl", f"dtl_{no}", cntntsNo=no)           # 재배법(HTML)
            call("workScheduleEraInfoLst", f"era_{no}", cntntsNo=no)    # 월별 캘린더(HTML)
            state = "건너뜀" if skip_files else download(row)
            print(f"  [{i}/{len(targets)}] {label} … 상세 OK, 첨부 {state}")
        except Exception as err:
            failed.append(f"{label} (cntntsNo={no}): {err}")
            print(f"  [{i}/{len(targets)}] {label} … 실패")

    print("\n[3/3] 목록을 CSV 로 저장합니다")
    with open(OUT / "작물목록.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(index[0].keys()))
        writer.writeheader()
        writer.writerows(index)

    if failed:
        (OUT / "실패목록.txt").write_text("\n".join(failed), encoding="utf-8")
        print(f"  실패 {len(failed)}건 → 수집결과/실패목록.txt (다시 실행하면 실패한 것만 재시도합니다)")

    print(f"\n끝났습니다. 결과: {OUT}")


if __name__ == "__main__":
    KEY = api_key()
    main()
