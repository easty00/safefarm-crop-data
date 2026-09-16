# 품종요약서(품종정보 varietyList 의 첨부파일)를 받아 글자로 바꾸는 스크립트입니다.
# 자세한 사용법은 "품종요약서_수집_사용법.md" 를 읽어주세요.
#
# 품종요약서에는 벼의 '출수기(월.일)' 가 날짜로 적혀 있습니다.
# 로드맵 §5-3 의 벼 검증은 '출수 중앙일'이 필요한데 지금까지 그것이 우리 가정이었습니다.
# 여기에 품종별 실측 출수일이 있으므로 가정을 관측값으로 바꿀 수 있습니다.
#
# 다만 파일 하나가 2~8MB 라 전부 받으면 1GB 를 넘습니다. 작물을 골라서 받습니다.

import csv
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path

BASE = "http://api.nongsaro.go.kr/service/varietyInfo"
HERE = Path(__file__).resolve().parent
OUT = HERE / "탐사결과" / "품종요약서"
RAW = OUT / "raw"
FILES = OUT / "원본"
TEXTS = OUT / "본문"
WAIT = 0.4
BAD_CHARS = '\\/:*?"<>|'

# 요약서에서 찾아볼 값들. 작물마다 표 컬럼이 다르므로 있는 것만 잡힌다
PATTERNS = {
    "출수기": r"출수기[^\n]{0,40}",
    "성숙기": r"성숙기[^\n]{0,40}",
    "재배기간": r"\d+\s*일\s*재배|보통기\s*\d+\s*일",
    "휴면기간": r"휴면기간[^\n]{0,30}",
    "수량": r"(?:쌀수량|상품수량|수량)[^\n]{0,30}",
    "적응지역": r"적응지역[^\n]{0,60}",
    "온도": r"\d+(?:\.\d+)?\s*℃[^\n]{0,30}",
}


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
    last = None
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(url, timeout=120) as res:
                return res.read()
        except Exception as err:
            last = err
            if attempt == 1:
                time.sleep(3)
    raise RuntimeError(f"두 번 모두 실패: {url}\n  {last}")


def call(operation: str, save_as: str, **params) -> ET.Element:
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


# ---------- 문서 읽기 ----------

def clean(text: str) -> str:
    return "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)


def read_hwpx(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if re.fullmatch(r"Contents/section\d+\.xml", n))
        out = []
        for name in names:
            raw = z.read(name).decode("utf-8", errors="ignore")
            raw = re.sub(r"</(hp:p|hp:tr|hp:tc)>", "\n", raw)
            raw = re.sub(r"<[^>]+>", "", raw)
            for a, b in [("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'"), ("&amp;", "&")]:
                raw = raw.replace(a, b)
            out.append(clean(raw))
    return "\n".join(out)


def read_pdf(path: Path) -> str:
    from pypdf import PdfReader
    return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)


def read_hwp(path: Path) -> str:
    import olefile
    import struct
    import zlib

    ole = olefile.OleFileIO(str(path))
    compressed = (ole.openstream("FileHeader").read()[36] & 1) == 1
    sections = sorted(int(e[1][len("Section"):]) for e in ole.listdir() if e[0] == "BodyText")
    chunks = []
    for num in sections:
        raw = ole.openstream(f"BodyText/Section{num}").read()
        data = zlib.decompress(raw, -15) if compressed else raw
        pos = 0
        while pos < len(data):
            head = struct.unpack_from("<I", data, pos)[0]
            kind, size = head & 0x3FF, (head >> 20) & 0xFFF
            if kind == 67:  # HWPTAG_PARA_TEXT
                chunks.append(clean(data[pos + 4: pos + 4 + size].decode("utf-16le", "ignore")))
            pos += 4 + size
    return "\n".join(chunks)


def extract(path: Path) -> str:
    """확장자가 아니라 파일 앞 4바이트로 형식을 판정한다. 이름과 내용이 어긋난 적이 있다."""
    head = path.read_bytes()[:4]
    if head[:4] == b"%PDF":
        return read_pdf(path)
    if head[:2] == b"PK":
        return read_hwpx(path)
    if head[:4] == b"\xd0\xcf\x11\xe0":
        return read_hwp(path)
    raise RuntimeError(f"모르는 형식 (앞 4바이트 {head!r})")


# ---------- 단계 ----------

def find_crop(only: str) -> list[dict]:
    """대분류를 훑어 이름이 맞는 작물을 찾는다.

    middleCategoryList 는 한 응답에 CLASS1(중분류)·CROP(작물)·YEAR(연도)를 섞어 준다.
    gubn 으로 걸러야 연도를 작물로 착각하지 않는다.
    """
    found = []
    for main in rows(call("mainCategoryList", "main")):
        cat = main.get("categoryCode", "")
        for m in rows(call("middleCategoryList", f"middle_{cat}", categoryCode=cat)):
            if m.get("gubn") != "CROP":
                continue
            if only and only not in m.get("codeNm", ""):
                continue
            found.append({"대분류코드": cat, "대분류명": main.get("categoryNm", ""),
                          "작물코드": m.get("code", ""), "작물명": m.get("codeNm", "")})
    return found


def collect(crops: list[dict], per_crop: int) -> list[dict]:
    FILES.mkdir(parents=True, exist_ok=True)
    TEXTS.mkdir(parents=True, exist_ok=True)
    got = []

    for crop in crops:
        try:
            items = rows(call("varietyList", f"list_{crop['작물코드']}",
                              categoryCode=crop["대분류코드"], sCropsCode=crop["작물코드"],
                              numOfRows=per_crop, pageNo=1))
        except Exception as err:
            print(f"  {crop['작물명']} … 목록 실패: {err}")
            continue

        print(f"  [{crop['작물명']}] 품종 {len(items)}건")
        for it in items:
            url, name = (it.get("atchFileLink") or "").strip(), (it.get("orginlFileNm") or "").strip()
            row = {"작물명": crop["작물명"], "품종명": it.get("cntntsSj", ""),
                   "숙기코드": it.get("mtrtSeCode", ""), "육성년도": it.get("unbrngYear", ""),
                   "육성기관": it.get("unbrngInsttInfo", ""), "파일명": name,
                   "크기KB": "", "본문자수": "", "상태": ""}
            if not url or not name:
                row["상태"] = "첨부없음"
                got.append(row)
                continue

            path = FILES / safe(f"{crop['작물명']}_{name}")
            if not path.exists():
                try:
                    path.write_bytes(fetch(url))
                    time.sleep(WAIT)
                except Exception as err:
                    row["상태"] = f"내려받기 실패: {err}"
                    got.append(row)
                    print(f"    {row['품종명']} … 실패")
                    continue
            row["크기KB"] = round(path.stat().st_size / 1024)

            try:
                text = extract(path)
            except Exception as err:
                row["상태"] = f"읽기 실패: {err}"
                got.append(row)
                continue

            (TEXTS / (path.stem + ".txt")).write_text(text, encoding="utf-8")
            row["본문자수"] = len(text)
            row["상태"] = "정상"
            flat = " ".join(text.split())
            for label, pat in PATTERNS.items():
                hits = re.findall(pat, flat)
                row[label] = " | ".join(dict.fromkeys(hits))[:200]
            got.append(row)
            print(f"    {row['품종명']} … {row['크기KB']}KB, 본문 {len(text):,}자")
    return got


def write_report(got: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if got:
        keys = sorted({k for r in got for k in r})
        with open(OUT / "품종요약서.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(got)

    ok = [r for r in got if r.get("상태") == "정상"]
    out = ["# 품종요약서 수집 결과", "",
           f"품종 {len(got)}건 / 본문을 읽은 것 {len(ok)}건", "",
           "## 상태", ""]
    for k, n in Counter(r.get("상태", "") for r in got).most_common():
        out.append(f"- {k} : {n}건")

    out += ["", "## 찾아낸 값이 있는 비율", ""]
    for label in PATTERNS:
        n = sum(1 for r in ok if r.get(label))
        pct = (n / len(ok) * 100) if ok else 0
        out.append(f"- {label:8} {n:3}/{len(ok):<3} ({pct:5.1f}%)")

    out += ["", "## 품종별로 찾아낸 값 (앞 40건)", ""]
    for r in ok[:40]:
        bits = [f"{k}={r[k]}" for k in PATTERNS if r.get(k)]
        out.append(f"- **{r['작물명']} / {r['품종명']}** ({r['육성년도']}) — " + ("; ".join(bits) or "찾은 값 없음"))

    total = sum(r["크기KB"] for r in got if isinstance(r.get("크기KB"), int))
    out += ["", "## 용량", "", f"- 내려받은 원본 합계 약 {total/1024:.1f}MB"]

    (OUT / "요약.md").write_text("\n".join(out), encoding="utf-8")


def main() -> None:
    only = ""
    if "--crop" in sys.argv:
        only = sys.argv[sys.argv.index("--crop") + 1]
    per_crop = 10
    if "--count" in sys.argv:
        per_crop = int(sys.argv[sys.argv.index("--count") + 1])

    if not only:
        sys.exit("어떤 작물을 받을지 정해주세요. 예) python variety_summary.py --crop 논벼\n"
                 "  (요약서 한 건이 2~8MB 라 전부 받으면 1GB 가 넘습니다)")

    RAW.mkdir(parents=True, exist_ok=True)

    print(f"[1/2] '{only}' 이(가) 들어간 작물을 찾습니다")
    crops = find_crop(only)
    if not crops:
        sys.exit(f"  '{only}' 에 해당하는 작물이 없습니다")
    for c in crops:
        print(f"  {c['대분류명']} / {c['작물명']} ({c['작물코드']})")
    print()

    print(f"[2/2] 작물마다 품종 {per_crop}건씩 요약서를 받아 글자로 바꿉니다")
    got = collect(crops, per_crop)

    write_report(got)
    print(f"\n끝났습니다. 결과: {OUT}")
    print("  요약.md 를 저에게 보여주시면 됩니다")


if __name__ == "__main__":
    KEY = api_key()
    main()
