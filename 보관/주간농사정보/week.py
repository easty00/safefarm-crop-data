# 농사로 주간농사정보(weekFarmInfo) 를 받아 글자로 바꾸고 연도끼리 대조하는 스크립트입니다.
# 자세한 사용법은 같은 폴더의 "사용법.md" 를 읽어주세요.
#
# 이 서비스는 오퍼레이션이 하나뿐이고 연도로 거르는 요청 변수가 없습니다.
# 그래서 870건을 통째로 받아 목록에 다 남기고, 첨부만 연도로 골라 내려받습니다.
#
#   2010 ~ 2026년 · 주 1회 · 연 51~54건 · 모두 870건
#
# 첨부는 같은 내용의 hwp / hwpx / pdf 판본이 최대 3개씩 붙어 옵니다.
# 기본은 판본 하나만 받습니다. 셋 다 받으면 용량이 세 배가 되는데 내용이 같습니다.

import csv
import re
import struct
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
import zlib
from collections import Counter, defaultdict
from pathlib import Path

BASE = "http://api.nongsaro.go.kr/service/weekFarmInfo"
HERE = Path(__file__).resolve().parent
OUT = HERE / "결과"
RAW = OUT / "raw"
FILES = OUT / "첨부"
TEXTS = OUT / "본문"
WAIT = 0.4
PAGE = 500
BAD_CHARS = '\\/:*?"<>|'

DEFAULT_YEARS = "2023,2024,2025,2026"

# 글자가 깨끗한 순서. 같은 내용이면 이 차례로 하나만 받는다
PREFER = (".hwpx", ".hwp", ".pdf", ".zip")

# 문서 안의 항목 제목처럼 보이는 줄. 연도끼리 맞댈 때 열쇠로 쓴다
HEAD_RE = re.compile(r"^\s*(?:\d{1,2}\s*[.)]|[가-힣]\s*[.)]|[◇○□▣●▶■◆])\s*(\S.{1,28})$")


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
    out = "".join("_" if ch in BAD_CHARS else ch for ch in name).strip()
    return out[:120] or "이름없음"


def clean(text: str) -> str:
    return "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)


def fetch(url: str) -> bytes:
    last = None
    for attempt in (1, 2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=180) as res:
                return res.read()
        except Exception as err:
            last = err
            if attempt == 1:
                time.sleep(3)
    raise RuntimeError(f"두 번 모두 실패: {last}")


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
        # 오류 응답은 저장하지 않는다. 저장해두면 다음에 건너뛰어 영영 모르게 된다
        raise RuntimeError(f"resultCode {code}: {root.findtext('./header/resultMsg', '')}")
    path.write_bytes(data)
    time.sleep(WAIT)
    return root


def rows(root: ET.Element) -> list[dict]:
    return [{c.tag: (c.text or "").strip() for c in item} for item in root.iter("item")]


# ---------- 문서 읽기 ----------

class Images(Exception):
    """첨부가 글이 아니라 사진일 때. 실패가 아니라 따로 세려고 나눠둔다."""


def read_pdf(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return "".join(f"\n===== p.{i} =====\n" + (pg.extract_text() or "")
                   for i, pg in enumerate(reader.pages, 1))


def read_hwpx(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if re.fullmatch(r"Contents/section\d+\.xml", n))
        if not names:
            raise RuntimeError("hwpx 가 아니라 그냥 압축파일입니다")
        out = []
        for n in names:
            raw = z.read(n).decode("utf-8", "ignore")
            # 문단과 표 칸의 경계를 줄바꿈으로 남긴다. 지우면 숫자가 한 덩어리로 붙는다
            raw = re.sub(r"</(hp:p|hp:tr|hp:tc)>", "\n", raw)
            raw = re.sub(r"<[^>]+>", "", raw)
            for a, b in [("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'),
                         ("&apos;", "'"), ("&amp;", "&")]:
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


def read_hwp3(path: Path) -> str:
    """한글 3.0(구형식) 에서 글자를 건져낸다.

    앞이 'HWP ' 로 시작한다. 글자 하나가 2바이트 리틀엔디안 낱말로 들어있고,
    0x8000 이상이면 조합형 코드라서 빅엔디안으로 뒤집어 johab 으로 푼다.
    문단 구조까지 해석하지는 않아 기록 경계에서 몇 글자가 빠질 수 있다. 건져내기다.
    """
    b = path.read_bytes()

    def one(i: int) -> str | None:
        w = struct.unpack_from("<H", b, i)[0]
        if w in (0x0D, 0x0A, 0x09):
            return "\n"
        if 0x20 <= w < 0x7F:
            return chr(w)
        if w >= 0x8000:
            try:
                c = struct.pack(">H", w).decode("johab")
            except Exception:
                return None
            return c if "가" <= c <= "힣" else None
        return None

    runs, cur = [], []
    for i in range(0, len(b) - 1, 2):
        c = one(i)
        if c is None:
            if len(cur) >= 10:      # 짧은 조각은 바이너리가 우연히 글자로 읽힌 것
                runs.append("".join(cur))
            cur = []
        else:
            cur.append(c)
    if len(cur) >= 10:
        runs.append("".join(cur))
    return "\n".join(runs)


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
    if head[:4] == b"HWP ":
        return read_hwp3(path)
    if head[:3] in (bytes.fromhex("ffd8ff"), bytes.fromhex("89504e"), b"GIF"):
        raise Images(f"사진 파일 (앞 3바이트 {head[:3]!r})")
    raise RuntimeError(f"모르는 형식 (앞 4바이트 {head!r})")


# ---------- 목록 ----------

def issue_no(subject: str) -> str:
    """'주간농사정보 제 37호' 에서 37 을 뽑는다. 연도끼리 맞대는 열쇠다."""
    m = re.search(r"제\s*(\d+)\s*호", subject)
    return m.group(1) if m else ""


def span(subject: str) -> str:
    """'(2026.9.14.~9.20.)' 에서 기간을 뽑는다."""
    m = re.search(r"\(([^)]*~[^)]*)\)", subject)
    return " ".join(m.group(1).split()) if m else ""


def versions(item: dict) -> list[tuple[str, str]]:
    """첨부 이름과 주소를 짝지어 돌려준다.

    fileName 과 downUrlList 가 둘 다 '|' 로 이어진 목록이다. 나누지 않고 통째로 쓰면
    이름과 주소가 어긋나서, .pdf 라는 이름의 파일에 hwpx 알맹이가 담기게 된다.
    전에 실제로 그렇게 저장해 판독이 전부 실패한 적이 있다.
    """
    names = [n.strip() for n in (item.get("fileName") or "").split("|") if n.strip()]
    urls = [u.strip() for u in (item.get("downUrlList") or "").split("|") if u.strip()]
    if not urls:
        one = (item.get("downUrl") or "").strip()
        urls = [one] if one else []
    return list(zip(names, urls))       # 짝이 안 맞으면 짧은 쪽에서 끊긴다


def best(pairs: list[tuple[str, str]]) -> tuple[str, str] | None:
    """판본이 여럿이면 글자가 가장 깨끗한 형식 하나를 고른다."""
    for ext in PREFER:
        for nm, url in pairs:
            if nm.lower().endswith(ext):
                return nm, url
    return pairs[0] if pairs else None


def step_list() -> list[dict]:
    got, page, total = [], 1, None
    while True:
        root = call("weekFarmInfoList", f"list_{page}", pageNo=page, numOfRows=PAGE)
        if total is None:
            total = int(root.findtext(".//totalCount") or 0)
        batch = rows(root)
        got += batch
        print(f"  {min(page * PAGE, total):>4}/{total}")
        if page * PAGE >= total or not batch:
            break
        page += 1

    for r in got:
        subject = r.get("subject", "")
        r["연도"] = (r.get("regDt") or "")[:4]
        r["호수"] = issue_no(subject)
        r["기간"] = span(subject)
        pairs = versions(r)
        r["판본수"] = len(pairs)
        r["판본"] = " | ".join(nm for nm, _ in pairs)
        pick = best(pairs)
        r["고른파일"] = pick[0] if pick else ""
    return got


# ---------- 첨부 ----------

def step_download(items: list[dict], mode: str) -> list[str]:
    failed = []
    for i, r in enumerate(items, 1):
        pairs = versions(r)
        targets = pairs if mode == "all" else ([best(pairs)] if best(pairs) else [])
        if not targets:
            failed.append(f"{r['연도']} {r.get('subject','')[:40]}: 첨부 주소 없음")
            continue
        folder = FILES / (r["연도"] or "연도미상")
        folder.mkdir(parents=True, exist_ok=True)
        saved = []
        for nm, url in targets:
            # 호수를 앞에 붙인다. 파일 이름만으로는 몇 호인지 알기 어렵다
            path = folder / safe(f"{r['호수'] or '00'}호_{nm}")
            if path.exists() and path.stat().st_size == 0:
                path.unlink()       # 0바이트로 저장된 적이 있다. 두면 영영 빈 채로 남는다
            if not path.exists():
                try:
                    blob = fetch(url)
                    if blob[:16].lstrip().lower().startswith((b"<!doctype", b"<html")):
                        raise RuntimeError("파일 대신 안내 페이지가 왔습니다")
                    if not blob:
                        raise RuntimeError("빈 파일(0바이트)이 왔습니다")
                    path.write_bytes(blob)
                    time.sleep(WAIT)
                except Exception as err:
                    failed.append(f"{r['연도']} {nm[:40]}: {err}")
                    continue
            saved.append(path)
        if saved:
            r["첨부"] = str(saved[0].relative_to(OUT))
            r["첨부KB"] = round(sum(p.stat().st_size for p in saved) / 1024)
            print(f"  [{i}/{len(items)}] {r['연도']} 제{r['호수']:>2}호  {r['첨부KB']:>7,}KB")
    return failed


def step_text(items: list[dict]) -> tuple[list[dict], list[str], list[str]]:
    """첨부 전문을 통째로 글자로 바꾸고, 항목 제목만 따로 뽑아 목차를 만든다.

    본문에는 어떤 필터도 걸지 않는다. 걸러낸 뒤에 후회한 적이 있다.
    """
    heads, failed, images = [], [], []
    targets = [r for r in items if r.get("첨부")]
    for i, r in enumerate(targets, 1):
        src = OUT / r["첨부"]
        folder = TEXTS / (r["연도"] or "연도미상")
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / (safe(f"{r['호수'] or '00'}호_{src.stem}") + ".txt")
        try:
            text = dest.read_text(encoding="utf-8") if dest.exists() else extract(src)
        except Images as err:
            images.append(f"{r['연도']} 제{r['호수']}호: {err}")
            continue
        except Exception as err:
            failed.append(f"{r['연도']} 제{r['호수']}호 판독: {err}")
            print(f"  [{i}/{len(targets)}] 판독 실패 {src.name[:36]}")
            continue
        if not dest.exists():
            dest.write_text(text, encoding="utf-8")
        r["본문"] = str(dest.relative_to(OUT))
        r["본문자수"] = len(text)
        r["쪽수"] = text.count("===== p.")

        seen = set()
        for line in text.splitlines():
            m = HEAD_RE.match(line.rstrip())
            if not m:
                continue
            name = " ".join(m.group(1).split())
            if 2 <= len(name) <= 28 and name not in seen:
                seen.add(name)
                heads.append({"연도": r["연도"], "호수": r["호수"], "기간": r["기간"],
                              "항목": name})
        if i % 10 == 0 or i == len(targets):
            print(f"  [{i}/{len(targets)}] 판독 {sum(1 for x in targets[:i] if x.get('본문자수'))}건")
    return heads, failed, images


# ---------- 결과 ----------

def dump(path: Path, data: list[dict]) -> None:
    if not data:
        return
    keys = list(dict.fromkeys(k for d in data for k in d))
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(data)


def write_compare(items: list[dict], heads: list[dict]) -> None:
    """같은 호수를 연도별로 맞대본다. 매년 같은 내용을 다시 싣는지가 핵심 질문이다."""
    read = [r for r in items if r.get("본문자수")]
    years = sorted({r["연도"] for r in read})
    out = ["# 연도 대조", "", f"대상 연도: {', '.join(years)} · 판독 {len(read)}건", ""]

    by_year = defaultdict(set)
    for h in heads:
        by_year[h["연도"]].add(h["항목"])

    out += ["## 연도별 항목 가짓수", ""]
    for y in years:
        out.append(f"- {y}년 : {len(by_year[y])}가지")

    if len(years) >= 2:
        a, b = years[0], years[-1]
        both = by_year[a] & by_year[b]
        only_a = sorted(by_year[a] - by_year[b])
        only_b = sorted(by_year[b] - by_year[a])
        share = len(both) / max(1, len(by_year[a] | by_year[b])) * 100
        out += ["", f"## {a}년 ↔ {b}년", "",
                f"- 양쪽에 다 있는 항목 : {len(both)}가지 (합집합 대비 {share:.0f}%)",
                f"- {a}년에만 : {len(only_a)}가지",
                f"- {b}년에만 : {len(only_b)}가지", ""]
        out += ["**겹치는 비율이 높으면 매년 같은 내용을 다시 싣는다는 뜻입니다. "
                "그러면 최신 한 해만 써도 됩니다.**", ""]
        if only_b:
            out += [f"### {b}년에만 있는 항목 (새로 생김, 앞 40개)", ""]
            out += [f"- {x}" for x in only_b[:40]]
        if only_a:
            out += ["", f"### {a}년에만 있는 항목 (사라짐, 앞 40개)", ""]
            out += [f"- {x}" for x in only_a[:40]]

    out += ["", "## 같은 호수끼리 글자 수", "",
            "같은 주차를 연도별로 나란히 놓은 것입니다. 분량이 크게 바뀌었으면 개정된 것입니다.", "",
            "| 호 | " + " | ".join(f"{y}년" for y in years) + " |",
            "|---|" + "---|" * len(years)]
    table = defaultdict(dict)
    for r in read:
        if r["호수"]:
            table[int(r["호수"])][r["연도"]] = r["본문자수"]
    for no in sorted(table):
        cells = [f"{table[no].get(y, 0):,}" if table[no].get(y) else "—" for y in years]
        out.append(f"| 제{no}호 | " + " | ".join(cells) + " |")

    (OUT / "대조.md").write_text("\n".join(out), encoding="utf-8")


def write_report(items, picked, heads, failed, images) -> None:
    read = [r for r in picked if r.get("본문자수")]
    kb = sum(r.get("첨부KB", 0) for r in picked)
    ver = Counter(r.get("판본수", 0) for r in items)

    out = ["# 주간농사정보 수집 결과", "",
           f"목록 {len(items):,}건 (2010~2026년) · 이번에 받은 것 {len(picked)}건",
           f"첨부 {sum(1 for r in picked if r.get('첨부'))}건 · {kb/1024:,.0f}MB · "
           f"판독 {len(read)}건 · 본문 {sum(r.get('본문자수',0) for r in read):,}자", ""]

    out += ["## 연도별 (목록 전체)", "", "| 연도 | 목록 | 받음 | 판독 | 용량 |", "|---|---|---|---|---|"]
    for y in sorted({r["연도"] for r in items}, reverse=True):
        a = [r for r in items if r["연도"] == y]
        b = [r for r in picked if r["연도"] == y]
        out.append(f"| {y} | {len(a)} | {sum(1 for r in b if r.get('첨부'))} | "
                   f"{sum(1 for r in b if r.get('본문자수'))} | "
                   f"{sum(r.get('첨부KB',0) for r in b)/1024:,.0f}MB |")

    out += ["", "## 첨부 판본 수 (목록 870건 기준)", ""]
    for n, c in sorted(ver.items()):
        out.append(f"- 판본 {n}개 : {c}건")
    out.append("")
    out.append("같은 내용의 hwp·hwpx·pdf 판본입니다. 기본은 하나만 받습니다.")

    exts = Counter()
    for r in items:
        for nm in (r.get("판본") or "").split(" | "):
            if "." in nm:
                exts[nm.rsplit(".", 1)[-1].lower()] += 1
    out += ["", "## 첨부 형식 (목록 전체)", ""]
    for e, c in exts.most_common():
        out.append(f"- .{e} : {c}건")

    out += ["", "## 자주 나오는 항목 (상위 50)", "",
            "연도별 대조의 열쇠입니다. 여기에 작물 이름이 고르게 보이면 쓸 만합니다.", ""]
    for nm, n in Counter(h["항목"] for h in heads).most_common(50):
        out.append(f"- {n:>4}회  {nm}")

    if read:
        lens = sorted(r["본문자수"] for r in read)
        out += ["", "## 본문 분량", "",
                f"- 중앙값 {lens[len(lens)//2]:,}자 · 최소 {lens[0]:,} · 최대 {lens[-1]:,}",
                f"- 1,000자 미만 : {sum(1 for x in lens if x < 1000)}건"]

    if images:
        out += ["", f"## 첨부가 사진인 건 {len(images)}건", ""] + [f"- {x}" for x in images]
    if failed:
        out += ["", f"## 실패 {len(failed)}건", ""] + [f"- {x}" for x in failed[:50]]
        if len(failed) > 50:
            out.append(f"- … 외 {len(failed)-50}건")

    (OUT / "요약.md").write_text("\n".join(out), encoding="utf-8")


def main() -> None:
    years = DEFAULT_YEARS
    if "--year" in sys.argv:
        years = sys.argv[sys.argv.index("--year") + 1]
    years = [y.strip() for y in years.split(",") if y.strip()]
    mode = "one"
    if "--files" in sys.argv:
        mode = sys.argv[sys.argv.index("--files") + 1]

    for folder in (OUT, RAW, FILES, TEXTS):
        folder.mkdir(parents=True, exist_ok=True)

    print("[1/4] 목록을 받습니다 (연도로 거르는 요청 변수가 없어 870건을 통째로 받습니다)")
    items = step_list()
    print(f"  총 {len(items):,}건\n")

    picked = [r for r in items if r["연도"] in years] if mode != "none" else []
    print(f"[2/4] 첨부를 내려받습니다 ({', '.join(years)} · {len(picked)}건 · "
          f"판본 {'전부' if mode == 'all' else '하나씩'})")
    failed = step_download(picked, mode) if picked else []
    print()

    heads, images = [], []
    if picked:
        print("[3/4] 전문을 글자로 바꿉니다")
        heads, f3, images = step_text(picked)
        failed += f3
        print()

    print("[4/4] 연도끼리 대조합니다")
    dump(OUT / "목록.csv", items)          # 870건 전부. 받지 않은 해도 목록에는 남긴다
    dump(OUT / "목차.csv", heads)
    write_compare(picked, heads)
    write_report(items, picked, heads, failed, images)

    print(f"\n끝났습니다. 결과: {OUT}")
    print("  요약.md 와 대조.md 를 저에게 보여주시면 됩니다")
    if failed:
        print(f"  ! 실패 {len(failed)}건 — 요약.md 맨 아래")


if __name__ == "__main__":
    KEY = api_key()
    main()
