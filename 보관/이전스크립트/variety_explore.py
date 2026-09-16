# 농사로 품종정보(varietyInfo)가 실제로 무엇을 주는지 확인하는 탐사 스크립트입니다.
# 자세한 사용법은 "품종정보_탐사_사용법.md" 를 읽어주세요.
#
# 수집이 아니라 탐사입니다. 품종을 전부 받아 저장하지 않고, 어떤 칸에 무슨 값이
# 들어있는지 - 특히 숙기와 수확시기가 쓸 만한 형태인지 - 만 확인합니다.

import csv
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

BASE = "http://api.nongsaro.go.kr/service/varietyInfo"
HERE = Path(__file__).resolve().parent
OUT = HERE / "탐사결과" / "품종정보"
RAW = OUT / "raw"          # API 응답 원문. 값이 이상할 때 추적용
WAIT = 0.4                 # 요청 사이 쉬는 시간(초). 정부 서버라 몰아치지 않는다
BAD_CHARS = '\\/:*?"<>|'   # 윈도 파일명에 못 쓰는 글자

# 매뉴얼 4.2.5 에 적힌 varietyList 응답 칸들.
# 이 중 무엇이 실제로 채워지는지 세어보는 것이 이 탐사의 핵심이다
FIELDS = [
    "cntntsNo", "cntntsSj", "svcCodeNm", "upperSvcCode", "mtrtSeCode", "unbrngYear",
    "unbrngInsttInfo", "mainChartrInfo", "skllSeCode", "grdlSeCode",
    "orginlFileNm", "atchFileLink", "imgFileLink", "svcDt",
]


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
    """파일 이름으로 쓸 수 있게 다듬는다."""
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

    이미 받아둔 파일이 있으면 다시 부르지 않는다 - 중간에 끊겨도 이어서 할 수 있다.
    """
    path = RAW / f"{safe(save_as)}.xml"
    if path.exists():
        return ET.fromstring(path.read_bytes())

    query = urllib.parse.urlencode({"apiKey": KEY, **params})
    data = fetch(f"{BASE}/{operation}?{query}")

    # 오류 응답을 정상인 줄 알고 저장해두면 다음 실행 때 건너뛰어 영영 모르게 된다
    root = ET.fromstring(data)
    code = root.findtext("./header/resultCode", "")
    if code != "00":
        raise RuntimeError(f"resultCode {code}: {root.findtext('./header/resultMsg', '')}")

    path.write_bytes(data)
    time.sleep(WAIT)
    return root


def rows(root: ET.Element) -> list[dict]:
    """<item> 하나를 dict 하나로 바꾼다."""
    return [{child.tag: (child.text or "").strip() for child in item} for item in root.iter("item")]


def total_count(root: ET.Element) -> int:
    return int(root.findtext(".//totalCount", "0") or 0)


def step1_codes() -> tuple[list[dict], list[dict]]:
    """대분류 -> 작물코드 목록 / 코드표(숙기·용도·재배지대) 를 훑는다.

    middleCategoryList 는 한 응답 안에 세 가지를 섞어서 돌려준다 - gubn 으로 갈린다.
        CLASS1  중분류 (벼, 맥류 …)
        CROP    실제 작물 (논벼, 감자 …)   ← 우리가 쓸 것
        YEAR    육성년도 (2025, 2024 …)
    구분하지 않으면 연도를 작물로 착각해 엉뚱한 조회를 하게 된다.
    """
    crops = []
    mains = rows(call("mainCategoryList", "main"))

    for main in mains:
        cat, cat_nm = main.get("categoryCode", ""), main.get("categoryNm", "")
        middles = rows(call("middleCategoryList", f"middle_{cat}", categoryCode=cat))
        picked = [m for m in middles if m.get("gubn") == "CROP"]
        kinds = Counter(m.get("gubn", "") for m in middles)
        print(f"  {cat_nm}({cat}) 작물 {len(picked)}종  (응답 {len(middles)}행: {dict(kinds)})")
        for m in picked:
            crops.append({
                "대분류코드": cat, "대분류명": cat_nm,
                "작물코드": m.get("code", ""), "작물명": m.get("codeNm", ""),
            })

    # subCategoryList 는 categoryCode 를 무시하고 전역 코드표를 돌려준다.
    # 대분류마다 부르면 같은 표를 6번 받게 되므로 한 번만 부른다.
    first = mains[0].get("categoryCode", "") if mains else ""
    codes = [{
        "코드그룹": s.get("codeGroup", ""), "코드": s.get("code", ""),
        "코드명": s.get("codeNm", ""),
    } for s in rows(call("subCategoryList", "sub_all", categoryCode=first))]
    print(f"  코드표 {len(codes)}행 (전역. 대분류와 무관)")

    return crops, codes


def step2_census(crops: list[dict], limit: int | None) -> list[dict]:
    """작물마다 품종이 몇 건 있는지만 센다. numOfRows=1 이라 가볍다."""
    targets = crops[:limit] if limit else crops
    for i, crop in enumerate(targets, 1):
        label = f"{crop['대분류명']}/{crop['작물명']}"
        try:
            root = call(
                "varietyList", f"cnt_{crop['작물코드']}",
                categoryCode=crop["대분류코드"], sCropsCode=crop["작물코드"],
                numOfRows=1, pageNo=1,
            )
            crop["품종수"] = total_count(root)
            print(f"  [{i}/{len(targets)}] {label} … {crop['품종수']}건")
        except Exception as err:
            crop["품종수"] = -1
            print(f"  [{i}/{len(targets)}] {label} … 실패: {err}")
    return targets


def step3_sample(crops: list[dict], per_crop: int) -> dict:
    """품종이 많은 작물 3종을 골라 실제 응답을 한 페이지씩 받아 칸을 들여다본다."""
    picked = sorted((c for c in crops if c.get("품종수", 0) > 0),
                    key=lambda c: -c["품종수"])[:3]
    filled, maturity, samples, total = Counter(), Counter(), [], 0

    for crop in picked:
        root = call(
            "varietyList", f"smp_{crop['작물코드']}",
            categoryCode=crop["대분류코드"], sCropsCode=crop["작물코드"],
            numOfRows=per_crop, pageNo=1,
        )
        items = rows(root)
        print(f"  {crop['작물명']} 표본 {len(items)}건")
        for it in items:
            total += 1
            for f in FIELDS:
                if it.get(f):
                    filled[f] += 1
            maturity[it.get("mtrtSeCode", "") or "(빈값)"] += 1
        if items:
            samples.append((crop["작물명"], items[0]))

    return {"총건수": total, "칸채움": filled, "숙기분포": maturity, "표본": samples}


def write_report(crops: list[dict], codes: list[dict], census: list[dict], sample: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    def dump(name: str, data: list[dict]) -> None:
        if not data:
            return
        with open(OUT / name, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            writer.writeheader()
            writer.writerows(data)

    dump("작물코드.csv", crops)
    dump("코드표.csv", codes)

    out = ["# 품종정보(varietyInfo) 탐사 결과", "",
           f"작물 코드 {len(crops)}종 / 코드표 {len(codes)}행"]

    # 코드명이 "-" 인 행이 섞여 있다. 빈 자리라 세는 데서 빼고 보여준다
    GROUP_NM = {"218": "용도", "219": "재배지대", "220": "숙기"}
    out += ["", "## 코드그룹", ""]
    for group in sorted({c["코드그룹"] for c in codes}):
        rows_ = [c for c in codes if c["코드그룹"] == group]
        named = [c["코드명"] for c in rows_ if c["코드명"] not in ("-", "")]
        label = GROUP_NM.get(group, "?")
        out.append(f"- {group}({label}) : {len(rows_)}행, 이름있음 {len(named)}")
        out.append(f"    {', '.join(dict.fromkeys(named))}")

    counted = [c for c in census if c.get("품종수", 0) > 0]
    out += ["", "## 품종 건수", "",
            f"- 조회한 작물 {len(census)}종 중 품종이 있는 작물 {len(counted)}종",
            f"- 총 품종 {sum(c['품종수'] for c in counted):,}건"]
    for c in sorted(counted, key=lambda c: -c["품종수"])[:15]:
        out.append(f"  - {c['대분류명']}/{c['작물명']} {c['품종수']}건")

    out += ["", "## 응답 칸이 실제로 채워지는 비율", "", f"표본 {sample['총건수']}건 기준", ""]
    for f in FIELDS:
        n = sample["칸채움"].get(f, 0)
        pct = (n / sample["총건수"] * 100) if sample["총건수"] else 0
        out.append(f"- {f:20} {n:4}/{sample['총건수']:<4} ({pct:5.1f}%)")

    out += ["", "## 숙기코드 분포(표본)", ""]
    for code, n in sample["숙기분포"].most_common():
        out.append(f"- {code} : {n}건")

    out += ["", "## 표본 원문 (작물별 첫 건)", ""]
    for crop_nm, item in sample["표본"]:
        out.append(f"### {crop_nm}")
        for k, v in item.items():
            v = " ".join(v.split())
            out.append(f"- {k}: {v[:400]}{'…' if len(v) > 400 else ''}")
        out.append("")

    (OUT / "요약.md").write_text("\n".join(out), encoding="utf-8")


def main() -> None:
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    per_crop = 20
    if "--sample" in sys.argv:
        per_crop = int(sys.argv[sys.argv.index("--sample") + 1])

    RAW.mkdir(parents=True, exist_ok=True)

    print("[1/3] 대분류·작물코드·코드표를 받습니다")
    crops, codes = step1_codes()
    print(f"  작물 {len(crops)}종 / 코드표 {len(codes)}행\n")

    print("[2/3] 작물마다 품종이 몇 건인지 셉니다")
    census = step2_census(crops, limit)
    print()

    print("[3/3] 품종이 많은 작물 3종의 실제 응답을 들여다봅니다")
    sample = step3_sample(census, per_crop)

    write_report(crops, codes, census, sample)
    print(f"\n끝났습니다. 결과: {OUT}")
    print("  요약.md 를 저에게 보여주시면 됩니다")


if __name__ == "__main__":
    KEY = api_key()
    main()
