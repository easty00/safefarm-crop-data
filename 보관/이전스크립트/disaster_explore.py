# 농사로 농작물재해예방정보(frcDsstrPrevnt)가 실제로 무엇을 주는지 확인하는 탐사 스크립트입니다.
# 자세한 사용법은 "재해예방정보_탐사_사용법.md" 를 읽어주세요.
#
# 이 회보의 숫자는 표가 아니라 줄글 안에 섞여 있습니다. 그래서 이 스크립트는
# "규칙으로 옮길 수 있는 문장"이 몇 개나 되는지를 세는 데 목적을 둡니다.

import csv
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

BASE = "http://api.nongsaro.go.kr/service/frcDsstrPrevnt"
FILE_HOST = "https://www.nongsaro.go.kr"
HERE = Path(__file__).resolve().parent
OUT = HERE / "탐사결과" / "재해예방정보"
RAW = OUT / "raw"          # API 응답 원문. 값이 이상할 때 추적용
PDFS = OUT / "pdf"
WAIT = 0.4                 # 요청 사이 쉬는 시간(초). 정부 서버라 몰아치지 않는다
BAD_CHARS = '\\/:*?"<>|'

# 숫자 + 단위 + 비교말 이 한 문장 안에 같이 있으면 "규칙 후보"로 본다.
# 예) "30℃ 이상 고온이 5일 이상 계속되면" / "일평균기온 25℃ 이상이면 생육이 정지"
UNIT = r"(?:℃|도|㎜|mm|%|일|시간|㎝|cm)"
COMPARE = r"(?:이상|이하|초과|미만|넘으면|넘어서면|되면|지속|계속|부터)"
RULE = re.compile(rf"\d+(?:\.\d+)?\s*{UNIT}.{{0,40}}?{COMPARE}")

# 문장을 자르는 기준. 숫자 사이의 마침표(29.3℃)는 문장 끝이 아니므로 건드리지 않는다.
# 이걸 빼먹으면 "29.3℃ 초과"가 "29" 와 "3℃ 초과" 로 쪼개진다
SPLIT = re.compile(r"(?<!\d)\.(?!\d)|[。\n]|[○●□■◇▪]|[【】]|\*{1,2}")

# 회보가 어떤 작물을 다루는지 세기 위한 목록.
# 한 글자 이름(배·무·벼·콩·팥)은 배수·무더위·무름병처럼 다른 낱말에 묻혀서
# 그냥 세면 수백 회로 부풀어 오른다. 뒤에 조사가 오거나 한글이 아닐 때만 센다
CROPS = ["벼", "배추", "무", "고추", "마늘", "양파", "감자", "고구마", "콩", "옥수수",
         "참깨", "들깨", "사과", "배", "포도", "단감", "복숭아", "자두", "감귤",
         "딸기", "수박", "참외", "토마토", "오이", "호박", "상추", "인삼", "버섯",
         "목초", "사료작물", "축산", "한우", "돼지", "닭"]
JOSA = "은는이가을를의에도와과로만과나며랑"
CROP_RE = {
    c: re.compile(rf"(?<![가-힣]){re.escape(c)}(?![가-힣])" if len(c) == 1
                  else re.escape(c)) if len(c) > 1 else
       re.compile(rf"(?<![가-힣]){re.escape(c)}(?:(?![가-힣])|(?=[{JOSA}]))")
    for c in CROPS
}


def crops_in(text: str) -> list[str]:
    """이 글에 나오는 작물 이름을 골라낸다."""
    return [c for c in CROPS if CROP_RE[c].search(text)]


def count_crops(text: str) -> Counter:
    return Counter({c: n for c in CROPS if (n := len(CROP_RE[c].findall(text)))})


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
            with urllib.request.urlopen(url, timeout=120) as res:
                return res.read()
        except Exception as err:  # 네트워크는 가끔 그냥 끊긴다
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

    # 오류 응답을 정상인 줄 알고 저장해두면 다음 실행 때 건너뛰어 영영 모르게 된다
    root = ET.fromstring(data)
    code = root.findtext("./header/resultCode", "")
    if code != "00":
        raise RuntimeError(f"resultCode {code}: {root.findtext('./header/resultMsg', '')}")

    path.write_bytes(data)
    time.sleep(WAIT)
    return root


def rows(root: ET.Element) -> list[dict]:
    return [{child.tag: (child.text or "").strip() for child in item} for item in root.iter("item")]


def pdf_url(row: dict) -> str:
    """첨부 PDF 주소를 만든다. 인증 없이 바로 받아진다."""
    cours = (row.get("rtnFileCours") or "").strip("/")
    name = (row.get("rtnStreFileNm") or "").strip()
    return f"{FILE_HOST}/{cours}/{name}" if cours and name else ""


def pdf_text(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    parts = []
    for no, page in enumerate(reader.pages, 1):
        parts.append(f"\n[[p.{no}]]\n" + (page.extract_text() or ""))
    return "".join(parts)


def kind_of(title: str) -> str:
    """제목으로 문서 계열을 가른다. 이 서비스에는 네 계열이 섞여 있다.

    월간 회보만 있는 줄 알기 쉬운데, 재해별 전문 예측 보고가 따로 있다.
    특히 저온해(동해) 보고는 1~5월과 12월에 주간으로 나오며 2022~2024년에
    연 20건씩 있다. 겨울 자료는 월간 회보보다 이쪽에 있다.
    """
    if "저온해" in title or "동해" in title:
        return "저온해"
    if "고온해" in title or "폭염" in title:
        return "고온해"
    if "홍수해" in title:
        return "홍수해"
    if re.search(r"제\s*\d+\s*호", title):
        return "월간회보"
    return "기타"


def step1_list(year: str | None, only: str | None) -> list[dict]:
    """연도 목록을 받고, 연도별 회보 목록을 모은다.

    --year 는 쉼표로 여러 해를 받는다. 예) --year 2023,2024,2025
    """
    years = [y.get("yearCode", "") for y in rows(call("frcDsstrPrevntYear", "years"))]
    years = [y for y in years if y]
    print(f"  제공 연도 {len(years)}개: {', '.join(years)}")

    targets = [y.strip() for y in year.split(",")] if year else years
    issues = []
    for y in targets:
        if y not in years:
            print(f"  ! {y}년은 제공 목록에 없습니다 - 건너뜁니다")
            continue
        root = call("frcDsstrPrevntLst", f"lst_{y}", sYear=y, pageNo=1, numOfRows=100)
        got = rows(root)
        total = root.findtext(".//totalCount", "")
        print(f"  {y}년 {len(got)}건 (totalCount={total})")
        for r in got:
            r["_year"] = y
            r["_kind"] = kind_of(r.get("cntntsSj", ""))
            issues.append(r)

    if only:
        keys = [k.strip() for k in only.split(",")]
        before = len(issues)
        issues = [r for r in issues if r["_kind"] in keys or any(k in r.get("cntntsSj", "") for k in keys)]
        print(f"  --only {only} → {before}건 중 {len(issues)}건")

    kinds = Counter(r["_kind"] for r in issues)
    print(f"  계열: {dict(kinds)}")
    return issues


def step2_download(issues: list[dict], limit: int | None) -> list[tuple[dict, Path]]:
    """회보 PDF 를 내려받는다. 이미 있으면 건너뛴다."""
    PDFS.mkdir(parents=True, exist_ok=True)
    targets = issues[:limit] if limit else issues
    got = []
    for i, row in enumerate(targets, 1):
        url = pdf_url(row)
        title = row.get("cntntsSj", "제목없음")
        if not url:
            print(f"  [{i}/{len(targets)}] {title} … 첨부 없음")
            continue
        name = safe(row.get("rtnOrginlFileNm") or f"{row.get('cntntsNo','')}.pdf")
        path = PDFS / name
        if not path.exists():
            try:
                path.write_bytes(fetch(url))
                time.sleep(WAIT)
                state = "받음"
            except Exception as err:
                print(f"  [{i}/{len(targets)}] {title} … 실패: {err}")
                continue
        else:
            state = "이미있음"
        print(f"  [{i}/{len(targets)}] {title} … {state} ({path.stat().st_size/1024/1024:.1f}MB)")
        got.append((row, path))
    return got


def step3_scan(files: list[tuple[dict, Path]]) -> tuple[list[dict], Counter, int]:
    """PDF 본문에서 규칙 후보 문장을 뽑고, 작물이 몇 번 언급되는지 센다."""
    candidates, crop_hits, pages = [], Counter(), 0

    for row, path in files:
        try:
            text = pdf_text(path)
        except Exception as err:
            print(f"  {path.name} … 텍스트 추출 실패: {err}")
            continue
        pages += text.count("[[p.")

        page_no = "?"
        for chunk in text.split("[[p."):
            head, _, body = chunk.partition("]]")
            if body:
                page_no = head
            for piece in SPLIT.split(body or chunk):
                sentence = " ".join(piece.split())
                if len(sentence) < 10 or not RULE.search(sentence):
                    continue
                # 표에서 떨어져 나온 숫자 나열("10 20 30 60")은 규칙이 아니다.
                # 한글이 일정 비율 이상 있어야 문장으로 본다
                hangul = sum(1 for ch in sentence if "가" <= ch <= "힣")
                if hangul < len(sentence) * 0.3:
                    continue
                candidates.append({
                    "회보": row.get("cntntsSj", ""),
                    "연도": row.get("_year", ""),
                    "쪽": page_no,
                    "문장": sentence[:300],
                    "작물후보": ",".join(crops_in(sentence)),
                })
        crop_hits += count_crops(text)

    print(f"  본문 {pages}쪽에서 규칙 후보 {len(candidates)}문장")
    return candidates, crop_hits, pages


def write_report(issues, files, candidates, crop_hits, pages) -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    if issues:
        with open(OUT / "회보목록.csv", "w", encoding="utf-8-sig", newline="") as f:
            keys = list(issues[0].keys())
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(issues)

    if candidates:
        with open(OUT / "규칙후보.csv", "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(candidates[0].keys()))
            writer.writeheader()
            writer.writerows(candidates)

    out = ["# 농작물재해예방정보(frcDsstrPrevnt) 탐사 결과", "",
           f"회보 {len(issues)}건 / 내려받은 PDF {len(files)}건 / 본문 {pages}쪽", ""]

    out += ["## 연도별 회보 수", ""]
    for y, n in sorted(Counter(r.get("_year", "") for r in issues).items(), reverse=True):
        out.append(f"- {y}년 : {n}건")

    out += ["", "## 받은 회보", ""]
    for row, path in files:
        out.append(f"- {row.get('_year','')} {row.get('cntntsSj','')} — {path.name} "
                   f"({path.stat().st_size/1024/1024:.1f}MB)")

    out += ["", "## 규칙으로 옮길 수 있을 것 같은 문장", "",
            f"숫자와 비교말(이상/이하/계속되면 등)이 한 문장에 같이 있는 것만 뽑았습니다.",
            f"**총 {len(candidates)}문장**", ""]
    withcrop = [c for c in candidates if c["작물후보"]]
    out.append(f"- 그중 작물명이 같이 나온 문장 {len(withcrop)}개")
    out.append("")
    out.append("### 작물명이 같이 나온 문장 (앞 40개)")
    out.append("")
    for c in withcrop[:40]:
        out.append(f"- `{c['작물후보']}` p.{c['쪽']} — {c['문장'][:200]}")
    out += ["", "### 작물명 없는 문장 (앞 20개)", ""]
    for c in [x for x in candidates if not x["작물후보"]][:20]:
        out.append(f"- p.{c['쪽']} — {c['문장'][:200]}")

    out += ["", "## 회보가 다루는 작물 (본문 등장 횟수)", ""]
    for crop, n in crop_hits.most_common(25):
        if n:
            out.append(f"- {crop} : {n}회")

    (OUT / "요약.md").write_text("\n".join(out), encoding="utf-8")


def main() -> None:
    year = None
    if "--year" in sys.argv:
        year = sys.argv[sys.argv.index("--year") + 1]
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]
    skip_files = "--no-files" in sys.argv

    RAW.mkdir(parents=True, exist_ok=True)

    print("[1/3] 회보 목록을 받습니다")
    issues = step1_list(year, only)
    print(f"  총 {len(issues)}건\n")

    if skip_files:
        print("[2/3] --no-files 라서 PDF 는 건너뜁니다\n")
        files = []
    else:
        print("[2/3] 회보 PDF 를 내려받습니다")
        files = step2_download(issues, limit)
        print()

    print("[3/3] 본문에서 숫자 조건 문장을 찾습니다")
    candidates, crop_hits, pages = step3_scan(files)

    write_report(issues, files, candidates, crop_hits, pages)
    print(f"\n끝났습니다. 결과: {OUT}")
    print("  요약.md 를 저에게 보여주시면 됩니다")


if __name__ == "__main__":
    KEY = api_key()
    main()
