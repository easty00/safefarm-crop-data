# 농사로 농작물재해예방정보(frcDsstrPrevnt) 를 받아 글자로 바꾸고 연도끼리 대조하는 스크립트입니다.
# 자세한 사용법은 같은 폴더의 "사용법.md" 를 읽어주세요.
#
# 이 서비스에는 네 계열이 섞여 있습니다. 월간 회보만 있는 줄 알기 쉬운데 그렇지 않습니다.
#
#   월간회보  제N호        연 12건. 종합 안내서
#   저온해    동해 예측 보고  1~5월·12월 주간. 2022~2024년 연 20건  ← 겨울 자료는 여기
#   고온해    폭염 예측 보고  수시
#   홍수해                 수시
#
# 본문은 필터로 거르지 않고 전문을 통째로 저장합니다.
# 정규식으로 "숫자+단위+비교말" 만 뽑으면 표와 정의문이 통째로 빠집니다.
# 실제로 벼 한계온도표·적산온도·침관수 감수율표가 전부 그렇게 빠졌던 적이 있습니다.

import csv
import re
import sys
import struct
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
import zlib
from collections import Counter, defaultdict
from pathlib import Path

BASE = "http://api.nongsaro.go.kr/service/frcDsstrPrevnt"
FILE_HOST = "https://www.nongsaro.go.kr"
HERE = Path(__file__).resolve().parent
OUT = HERE / "결과"
RAW = OUT / "raw"
FILES = OUT / "파일"
TEXTS = OUT / "본문"
WAIT = 0.4
BAD_CHARS = '\\/:*?"<>|'

DEFAULT_YEARS = "2023,2024,2025"      # 자료가 가장 풍부한 해 + 최근

# 문서에서 찾아볼 표 제목. 대조의 핵심이라 넓게 잡는다
TABLE_PAT = re.compile(r"<?\s*표\s*[0-9０-９]+\s*>?\s*([^\n]{4,70})")


def api_key() -> str:
    """.env 의 AGRI_API 를 읽는다. 이 폴더에 없으면 상위 폴더로 올라가며 찾는다."""
    for folder in (HERE, *HERE.parents):
        env = folder / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("AGRI_API="):
                    return line.split("=", 1)[1].strip()
    sys.exit(f".env 를 찾지 못했습니다. {HERE} 나 그 상위 폴더에 있어야 합니다.")


def safe(name: str) -> str:
    return "".join("_" if ch in BAD_CHARS else ch for ch in name).strip() or "이름없음"


def clean(text: str) -> str:
    return "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)


def fetch(url: str) -> bytes:
    last = None
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(url, timeout=180) as res:
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
    return [{c.tag: (c.text or "").strip() for c in item} for item in root.iter("item")]


# ---------- 문서 계열 ----------

def kind_of(title: str) -> str:
    """제목으로 계열을 가른다. 겨울 자료는 월간 회보가 아니라 저온해 보고에 있다."""
    if "저온해" in title or "동해" in title:
        return "저온해"
    if "고온해" in title or "폭염" in title:
        return "고온해"
    if "홍수해" in title:
        return "홍수해"
    if re.search(r"제\s*\d+\s*호", title):
        return "월간회보"
    return "기타"


def issue_no(title: str) -> str:
    """'제9호' 에서 9 를 뽑는다. 같은 달끼리 연도를 맞대려면 호수가 필요하다."""
    m = re.search(r"제\s*(\d+)\s*호", title)
    return m.group(1) if m else ""


def report_date(title: str) -> str:
    """저온해 보고 제목 끝의 '(1.9)' 같은 날짜를 뽑는다."""
    m = re.search(r"\((\d{1,2})\s*[.\-]\s*(\d{1,2})\.?\)", title)
    return f"{int(m.group(1)):02d}-{int(m.group(2)):02d}" if m else ""


# ---------- 문서 읽기 ----------

def read_pdf(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return "".join(f"\n===== p.{i} =====\n" + (pg.extract_text() or "")
                   for i, pg in enumerate(reader.pages, 1))


def read_hwpx(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if re.fullmatch(r"Contents/section\d+\.xml", n))
        out = []
        for n in names:
            raw = z.read(n).decode("utf-8", "ignore")
            raw = re.sub(r"</(hp:p|hp:tr|hp:tc)>", "\n", raw)
            raw = re.sub(r"<[^>]+>", "", raw)
            for a, b in [("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'"), ("&amp;", "&")]:
                raw = raw.replace(a, b)
            out.append(clean(re.sub(r"\n{3,}", "\n\n", raw)))
    return "\n".join(out)


def read_hwp(path: Path) -> str:
    import olefile
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
            if kind == 67:      # HWPTAG_PARA_TEXT
                chunks.append(clean(data[pos + 4: pos + 4 + size].decode("utf-16le", "ignore")))
            pos += 4 + size
    return "\n".join(chunks)


def extract(path: Path) -> str:
    """확장자가 아니라 파일 앞 4바이트로 형식을 판정한다.

    이름과 내용이 어긋난 파일이 실제로 있었다. 이름을 믿으면 판독이 실패한다.
    """
    head = path.read_bytes()[:4]
    if head[:4] == b"%PDF":
        return read_pdf(path)
    if head[:2] == b"PK":
        return read_hwpx(path)
    if head[:4] == b"\xd0\xcf\x11\xe0":
        return read_hwp(path)
    raise RuntimeError(f"모르는 형식 (앞 4바이트 {head!r})")


# ---------- 단계 ----------

def step_list(years: list[str], only: str | None) -> list[dict]:
    have = [y.get("yearCode", "") for y in rows(call("frcDsstrPrevntYear", "years"))]
    have = [y for y in have if y]
    print(f"  제공 연도 {len(have)}개: {', '.join(have)}")

    docs = []
    for y in years:
        if y not in have:
            print(f"  ! {y}년은 제공 목록에 없습니다 - 건너뜁니다")
            continue
        root = call("frcDsstrPrevntLst", f"lst_{y}", sYear=y, pageNo=1, numOfRows=200)
        got = rows(root)
        print(f"  {y}년 {len(got)}건 (totalCount={root.findtext('.//totalCount','')})")
        for r in got:
            title = r.get("cntntsSj", "")
            docs.append({
                "연도": y, "계열": kind_of(title), "호수": issue_no(title),
                "보고일": report_date(title), "제목": title,
                "등록일": r.get("svcDt", "")[:10], "cntntsNo": r.get("cntntsNo", ""),
                "원본파일명": r.get("rtnOrginlFileNm", ""),
                "파일경로": r.get("rtnFileCours", ""), "저장파일명": r.get("rtnStreFileNm", ""),
                "파일구분코드": r.get("rtnFileSeCode", ""), "파일순번": r.get("rtnFileSn", ""),
                "조회수": r.get("cntntsRdcnt", ""), "작성자": r.get("updusrEsntlNm", ""),
            })

    if only:
        keys = [k.strip() for k in only.split(",")]
        before = len(docs)
        docs = [d for d in docs if d["계열"] in keys or any(k in d["제목"] for k in keys)]
        print(f"  --only {only} → {before}건 중 {len(docs)}건")

    print(f"  계열: {dict(Counter(d['계열'] for d in docs))}")
    return docs


def file_url(doc: dict) -> str:
    """내려받을 주소를 만든다. 포털 서블릿을 쓰고, 정적 경로는 예비로 남긴다.

    정적 경로(cms_contents/44/…)는 .hwpx 만 서버가 400 으로 막는다. 파일이 멀쩡히 있어도
    주소 끝이 .hwpx 이면 거절한다. 실제로 2023~2024년 92건이 전부 이것 때문에 실패했다.
    포털이 제 사이트에서 쓰는 contentsFileDownload.do 는 세 값만 넘기면 확장자를 안 가린다.
    """
    no, code, sn = doc["cntntsNo"], doc["파일구분코드"], doc["파일순번"]
    if no and code and sn:
        return f"{FILE_HOST}/portal/contentsFileDownload.do?cntntsNo={no}&fileSeCode={code}&fileSn={sn}"
    cours, name = doc["파일경로"].strip("/"), doc["저장파일명"].strip()
    return f"{FILE_HOST}/{cours}/{name}" if cours and name else ""


def step_download(docs: list[dict]) -> list[str]:
    failed = []
    for i, d in enumerate(docs, 1):
        url = file_url(d)
        if not url:
            d["파일"] = ""
            failed.append(f"{d['연도']} {d['제목'][:40]}: 첨부 주소 없음")
            continue
        folder = FILES / safe(d["계열"]) / d["연도"]
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / safe(d["원본파일명"] or f"{d['cntntsNo']}.bin")
        if not path.exists():
            try:
                blob = fetch(url)
                # 없는 파일에도 200 과 함께 안내 페이지를 돌려준다. 그대로 저장하면
                # 다음 실행 때 받은 줄 알고 건너뛰어 영영 모르게 된다.
                if blob[:16].lstrip().lower().startswith((b"<!doctype", b"<html")):
                    raise RuntimeError("파일 대신 안내 페이지가 왔습니다")
                path.write_bytes(blob)
                time.sleep(WAIT)
            except Exception as err:
                d["파일"] = ""
                failed.append(f"{d['연도']} {d['제목'][:40]}: {err}")
                print(f"  [{i}/{len(docs)}] 실패 {d['제목'][:34]}")
                continue
        d["파일"] = str(path.relative_to(OUT))
        d["크기KB"] = round(path.stat().st_size / 1024)
        print(f"  [{i}/{len(docs)}] {d['계열']:5} {d['제목'][:38]:40} {d['크기KB']:>6}KB")
    return failed


def step_text(docs: list[dict]) -> tuple[list[dict], list[str]]:
    """전문을 통째로 글자로 바꿔 저장하고, 표 제목만 따로 뽑아 목록을 만든다.

    본문은 어떤 필터도 걸지 않는다. 걸러낸 뒤에 후회한 적이 있다.
    """
    TEXTS.mkdir(parents=True, exist_ok=True)
    tables, failed = [], []

    for i, d in enumerate(docs, 1):
        if not d.get("파일"):
            continue
        path = OUT / d["파일"]
        dest = TEXTS / (safe(f"{d['연도']}_{d['계열']}_{path.stem}") + ".txt")
        try:
            text = dest.read_text(encoding="utf-8") if dest.exists() else extract(path)
        except Exception as err:
            d["본문자수"] = 0
            failed.append(f"{d['제목'][:40]} 판독: {err}")
            print(f"  [{i}/{len(docs)}] 판독 실패 {path.name[:34]}")
            continue
        if not dest.exists():
            dest.write_text(text, encoding="utf-8")
        d["본문"] = str(dest.relative_to(OUT))
        d["본문자수"] = len(text)
        d["쪽수"] = text.count("===== p.")

        seen = set()
        for m in TABLE_PAT.finditer(" ".join(text.split())):
            name = m.group(1).strip()[:60]
            if name and name not in seen:
                seen.add(name)
                tables.append({"연도": d["연도"], "계열": d["계열"], "호수": d["호수"],
                               "제목": d["제목"], "표제목": name})
        print(f"  [{i}/{len(docs)}] {path.name[:38]:40} {len(text):>8,}자 · 표 {len(seen)}개")
    return tables, failed


# ---------- 대조 ----------

def write_compare(docs: list[dict], tables: list[dict]) -> None:
    """연도끼리 맞대본다. 표가 개정·추가·삭제됐는지가 핵심이다."""
    years = sorted({d["연도"] for d in docs})
    by_year = defaultdict(set)
    for t in tables:
        by_year[t["연도"]].add(t["표제목"])

    out = ["# 연도 대조", "", f"대상 연도: {', '.join(years)}", ""]

    out += ["## 연도별 표 개수", ""]
    for y in years:
        out.append(f"- {y}년 : 표 제목 {len(by_year[y])}가지")

    if len(years) >= 2:
        first, last = years[0], years[-1]
        only_first = sorted(by_year[first] - by_year[last])
        only_last = sorted(by_year[last] - by_year[first])
        both = by_year[first] & by_year[last]
        out += ["", f"## {first}년 ↔ {last}년", "",
                f"- 양쪽에 다 있는 표 : {len(both)}가지",
                f"- {first}년에만 있는 표 : {len(only_first)}가지",
                f"- {last}년에만 있는 표 : {len(only_last)}가지", ""]
        if only_first:
            out += [f"### {first}년에만 있는 표 (사라졌거나 이름이 바뀜)", ""]
            out += [f"- {x}" for x in only_first[:40]]
        if only_last:
            out += ["", f"### {last}년에만 있는 표 (새로 생김)", ""]
            out += [f"- {x}" for x in only_last[:40]]

    out += ["", "## 같은 호수끼리 (월간회보)", "",
            "같은 달 회보를 연도별로 맞대면 분량이 바뀌었는지 보입니다.", "",
            "| 호 | " + " | ".join(f"{y}년" for y in years) + " |",
            "|---|" + "---|" * len(years)]
    monthly = defaultdict(dict)
    for d in docs:
        if d["계열"] == "월간회보" and d["호수"]:
            monthly[int(d["호수"])][d["연도"]] = d.get("본문자수", 0)
    for no in sorted(monthly):
        cells = [f"{monthly[no].get(y, 0):,}자" if monthly[no].get(y) else "—" for y in years]
        out.append(f"| 제{no}호 | " + " | ".join(cells) + " |")

    out += ["", "## 저온해 보고 발행일", ""]
    lo = defaultdict(list)
    for d in docs:
        if d["계열"] == "저온해" and d["보고일"]:
            lo[d["연도"]].append(d["보고일"])
    for y in years:
        if lo[y]:
            out.append(f"- {y}년 {len(lo[y])}건 : {', '.join(sorted(lo[y]))}")

    (OUT / "대조.md").write_text("\n".join(out), encoding="utf-8")


def write_report(docs: list[dict], tables: list[dict], failed: list[str]) -> None:
    kinds = Counter(d["계열"] for d in docs)
    total_kb = sum(d.get("크기KB", 0) for d in docs)
    total_ch = sum(d.get("본문자수", 0) for d in docs)
    read = [d for d in docs if d.get("본문자수")]

    out = ["# 재해예방정보 수집 결과", "",
           f"문서 {len(docs)}건 · 내려받음 {sum(1 for d in docs if d.get('파일'))}건 "
           f"· 판독 {len(read)}건",
           f"용량 {total_kb/1024:.1f}MB · 본문 {total_ch:,}자 · 표 제목 {len(tables)}건", ""]

    out += ["## 계열별", ""]
    for k, n in kinds.most_common():
        kb = sum(d.get("크기KB", 0) for d in docs if d["계열"] == k)
        ch = sum(d.get("본문자수", 0) for d in docs if d["계열"] == k)
        out.append(f"- **{k}** {n}건 · {kb/1024:.1f}MB · {ch:,}자")

    out += ["", "## 연도 × 계열", "", "| 연도 | " +
            " | ".join(kinds) + " | 합계 |", "|---|" + "---|" * (len(kinds) + 1)]
    for y in sorted({d["연도"] for d in docs}):
        cells = [str(sum(1 for d in docs if d["연도"] == y and d["계열"] == k)) for k in kinds]
        out.append(f"| {y} | " + " | ".join(cells) + f" | {sum(1 for d in docs if d['연도']==y)} |")

    out += ["", "## 자주 나오는 표 (상위 40)", ""]
    for name, n in Counter(t["표제목"] for t in tables).most_common(40):
        out.append(f"- {n:>3}회  {name}")

    out += ["", "## 판독한 문서 (앞 30건)", "",
            "| 연도 | 계열 | 제목 | 쪽 | 글자 |", "|---|---|---|---|---|"]
    for d in read[:30]:
        out.append(f"| {d['연도']} | {d['계열']} | {d['제목'][:34]} | "
                   f"{d.get('쪽수','—')} | {d.get('본문자수',0):,} |")

    if failed:
        out += ["", f"## 실패 {len(failed)}건", ""] + [f"- {x}" for x in failed[:40]]

    (OUT / "요약.md").write_text("\n".join(out), encoding="utf-8")


def main() -> None:
    years = DEFAULT_YEARS
    if "--year" in sys.argv:
        years = sys.argv[sys.argv.index("--year") + 1]
    years = [y.strip() for y in years.split(",")]
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]
    skip_files = "--no-files" in sys.argv

    for folder in (OUT, RAW, FILES, TEXTS):
        folder.mkdir(parents=True, exist_ok=True)

    print(f"[1/4] 문서 목록을 받습니다 ({', '.join(years)})")
    docs = step_list(years, only)
    print(f"  총 {len(docs)}건\n")

    failed = []
    tables = []
    if skip_files:
        print("[2/4] --no-files 라서 파일은 건너뜁니다\n")
    else:
        print(f"[2/4] 파일을 내려받습니다 ({len(docs)}건)")
        failed += step_download(docs)
        print()

        print("[3/4] 전문을 글자로 바꿉니다")
        tables, f3 = step_text(docs)
        failed += f3
        print()

    print("[4/4] 연도끼리 대조합니다")
    with open(OUT / "목록.csv", "w", encoding="utf-8-sig", newline="") as f:
        keys = sorted({k for d in docs for k in d})
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(docs)
    if tables:
        with open(OUT / "표목록.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(tables[0].keys()))
            w.writeheader()
            w.writerows(tables)
    write_compare(docs, tables)
    write_report(docs, tables, failed)

    print(f"\n끝났습니다. 결과: {OUT}")
    print("  요약.md 와 대조.md 를 저에게 보여주시면 됩니다")
    if failed:
        print(f"  ! 실패 {len(failed)}건 — 요약.md 맨 아래")


if __name__ == "__main__":
    KEY = api_key()
    main()
