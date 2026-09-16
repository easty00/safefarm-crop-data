# 농사로 주간농사정보(weekFarmInfo)와 병해충발생정보(dbyhsCccrrncInfo)를 확인하는 탐사 스크립트입니다.
# 자세한 사용법은 "주간농사정보_병해충_탐사_사용법.md" 를 읽어주세요.
#
# 두 서비스는 구조가 같습니다 - 목록 + 첨부파일뿐인 게시판형입니다.
# 그래서 하나의 프로그램으로 둘 다 훑습니다.
#
# 확인하려는 것: 얼마나 자주 올라오는가 / 첨부에 작물과 숫자가 들어있는가.
# 판정 규칙의 출처가 될지, LLM 참고자료에 그칠지를 가르는 게 목적입니다.

import csv
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path

HOST = "http://api.nongsaro.go.kr/service"
FILE_HOST = "https://www.nongsaro.go.kr"
HERE = Path(__file__).resolve().parent
OUT = HERE / "탐사결과" / "주간농사정보_병해충"
RAW = OUT / "raw"
FILES = OUT / "첨부"
WAIT = 0.4
BAD_CHARS = '\\/:*?"<>|'

UNIT = r"(?:℃|도|㎜|mm|%|일|시간|㎝|cm|마리)"
COMPARE = r"(?:이상|이하|초과|미만|넘으면|넘어서면|되면|지속|계속|부터)"
RULE = re.compile(rf"\d+(?:\.\d+)?\s*{UNIT}.{{0,40}}?{COMPARE}")

# 문장을 자르는 기준. 숫자 사이의 마침표(29.3℃)는 문장 끝이 아니므로 건드리지 않는다
SPLIT = re.compile(r"(?<!\d)\.(?!\d)|[。\n]|[○●□■◇▪❍⇒]|[【】]|\*{1,2}")

# 한 글자 이름(배·무·벼·콩)은 배수·무더위·무름병처럼 다른 낱말에 묻혀서
# 그냥 세면 수백 회로 부풀어 오른다. 뒤에 조사가 오거나 한글이 아닐 때만 센다
CROPS = ["벼", "배추", "무", "고추", "마늘", "양파", "감자", "고구마", "콩", "옥수수",
         "참깨", "들깨", "사과", "배", "포도", "단감", "복숭아", "자두", "감귤",
         "딸기", "수박", "참외", "토마토", "오이", "호박", "상추", "인삼", "버섯"]
JOSA = "은는이가을를의에도와과로만나며랑"
CROP_RE = {
    c: re.compile(rf"(?<![가-힣]){re.escape(c)}(?:(?![가-힣])|(?=[{JOSA}]))") if len(c) == 1
    else re.compile(re.escape(c))
    for c in CROPS
}

# 같은 문서가 hwpx·hwp·pdf 세 판본으로 올라온다. 글자가 가장 잘 나오는 순서로 고른다
PREFER = [".pdf", ".hwpx", ".hwp"]

SERVICES = {
    "주간농사정보": {
        "service": "weekFarmInfo",
        "list_op": "weekFarmInfoList",
        "year_op": None,
        "list_params": {"pageNo": 1, "numOfRows": 100},
        "title": "subject",
        "date": "regDt",
        "file_name": "fileName",
        "file_url": "downUrlList",
    },
    "병해충발생정보": {
        "service": "dbyhsCccrrncInfo",
        "list_op": "dbyhsCccrrncInfoList",
        # 매뉴얼 요청변수에 pageNo/numOfRows 가 없다. 한 번 부르면 10건만 온다.
        # 대신 sYear 가 있으므로 연도 목록을 받아 연도마다 부른다
        "year_op": "dbyhsCccrrncInfoYear",
        "list_params": {},
        "title": "cntntsSj",
        "date": "svcDt",
        "file_name": "rtnOrginlFileNm",
        "file_url": "downFile",
    },
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
    """한 번 실패하면 3초 쉬고 한 번 더 시도한다."""
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


def call(service: str, operation: str, save_as: str, **params) -> ET.Element:
    """API 를 부르고 원문을 raw 에 저장한 뒤 파싱해 돌려준다. 이미 있으면 다시 안 부른다."""
    path = RAW / f"{safe(save_as)}.xml"
    if path.exists():
        return ET.fromstring(path.read_bytes())

    query = urllib.parse.urlencode({"apiKey": KEY, **params})
    data = fetch(f"{HOST}/{service}/{operation}?{query}")

    root = ET.fromstring(data)
    code = root.findtext("./header/resultCode", "")
    if code != "00":
        raise RuntimeError(f"resultCode {code}: {root.findtext('./header/resultMsg', '')}")

    path.write_bytes(data)
    time.sleep(WAIT)
    return root


def rows(root: ET.Element) -> list[dict]:
    return [{child.tag: (child.text or "").strip() for child in item} for item in root.iter("item")]


def count_crops(text: str) -> Counter:
    return Counter({c: n for c in CROPS if (n := len(CROP_RE[c].findall(text)))})


def crops_in(text: str) -> list[str]:
    return [c for c in CROPS if CROP_RE[c].search(text)]


# ---------- 첨부파일 ----------

def attachments(row: dict, spec: dict) -> list[tuple[str, str]]:
    """(파일명, 주소) 목록. 한 글에 hwpx·hwp·pdf 가 함께 붙어 파이프로 묶여 온다."""
    names = [n.strip() for n in (row.get(spec["file_name"]) or "").split("|") if n.strip()]
    urls = [u.strip() for u in (row.get(spec["file_url"]) or "").split("|") if u.strip()]
    urls = [u if u.startswith("http") else f"{FILE_HOST}/{u.lstrip('/')}" for u in urls]

    if not urls:
        return []
    if len(names) != len(urls):      # 짝이 안 맞으면 순서대로만 잇는다
        names = names[:len(urls)] + [f"첨부{i+1}" for i in range(len(names), len(urls))]
    return list(zip(names, urls))


def best_one(pairs: list[tuple[str, str]]) -> tuple[str, str] | None:
    """같은 문서의 여러 판본 중 글자가 제일 잘 나오는 하나를 고른다."""
    for ext in PREFER:
        for name, url in pairs:
            if name.lower().endswith(ext):
                return name, url
    return pairs[0] if pairs else None


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
    """구형 .hwp. olefile 이 없으면 그 파일만 건너뛴다."""
    try:
        import olefile
    except ImportError:
        raise RuntimeError("olefile 이 없어 건너뜁니다 (pip install olefile)")
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


READERS = {".hwpx": read_hwpx, ".pdf": read_pdf, ".hwp": read_hwp}


def extract(path: Path) -> str:
    """확장자를 믿지 않고 파일 앞 4바이트로 형식을 확인한 뒤 읽는다.

    주간농사정보는 이름과 실제 내용이 어긋난 적이 있어서, 이름보다 내용을 먼저 본다.
    """
    head = path.read_bytes()[:4]
    if head[:4] == b"%PDF":
        return read_pdf(path)
    if head[:2] == b"PK":
        return read_hwpx(path)
    if head[:4] == b"\xd0\xcf\x11\xe0":   # OLE - 구형 hwp
        return read_hwp(path)
    reader = READERS.get(path.suffix.lower())
    if not reader:
        raise RuntimeError(f"읽는 방법을 모르는 형식입니다 (앞 4바이트 {head!r})")
    return reader(path)


# ---------- 단계 ----------

def step1_list(name: str, spec: dict) -> list[dict]:
    items = []
    if spec["year_op"]:
        years = [y.get("yearVal") or y.get("yearCode", "")
                 for y in rows(call(spec["service"], spec["year_op"], f"years_{spec['service']}"))]
        years = [y for y in years if y]
        print(f"  {name} 제공 연도 {len(years)}개: {', '.join(years[:12])}{' …' if len(years) > 12 else ''}")
        for y in years:
            got = rows(call(spec["service"], spec["list_op"], f"lst_{spec['service']}_{y}", sYear=y))
            for it in got:
                it["_서비스"] = name
            items += got
            print(f"    {y}년 {len(got)}건")
    else:
        root = call(spec["service"], spec["list_op"], f"lst_{spec['service']}", **spec["list_params"])
        items = rows(root)
        total = root.findtext(".//totalCount", "")
        print(f"  {name} {len(items)}건 (totalCount={total or '없음'})")
        for it in items:
            it["_서비스"] = name
    return items


def step2_download(items: list[dict], spec: dict, limit: int) -> list[tuple[dict, Path]]:
    if not items:
        return []
    folder = FILES / safe(items[0]["_서비스"])
    folder.mkdir(parents=True, exist_ok=True)
    got, shown = [], min(limit, len(items))

    for i, row in enumerate(items[:limit], 1):
        title = row.get(spec["title"], "제목없음")
        pick = best_one(attachments(row, spec))
        if not pick:
            print(f"  [{i}/{shown}] {title} … 첨부 없음")
            continue
        name, url = pick
        path = folder / safe(name)
        if not path.exists():
            try:
                path.write_bytes(fetch(url))
                time.sleep(WAIT)
                state = "받음"
            except Exception as err:
                print(f"  [{i}/{shown}] {title} … 실패: {err}")
                continue
        else:
            state = "이미있음"
        print(f"  [{i}/{shown}] {title} … {state} [{name}] ({path.stat().st_size/1024:.0f}KB)")
        got.append((row, path))
    return got


def step3_scan(files: list[tuple[dict, Path]], spec: dict) -> dict:
    crop_hits, candidates, chars, failed = Counter(), [], 0, []
    seen = set()

    for row, path in files:
        try:
            text = extract(path)
        except Exception as err:
            failed.append(f"{path.name}: {err}")
            print(f"    {path.name} … 읽기 실패: {err}")
            continue
        chars += len(text)
        crop_hits += count_crops(text)

        for piece in SPLIT.split(text):
            sentence = " ".join(piece.split())
            if len(sentence) < 10 or not RULE.search(sentence):
                continue
            # 표에서 떨어져 나온 숫자 나열은 규칙이 아니다. 한글이 어느 정도 있어야 문장
            hangul = sum(1 for ch in sentence if "가" <= ch <= "힣")
            if hangul < len(sentence) * 0.3:
                continue
            key = sentence[:80]
            if key in seen:      # 회보끼리 같은 문단을 그대로 반복한다
                continue
            seen.add(key)
            candidates.append({
                "서비스": row.get("_서비스", ""),
                "제목": row.get(spec["title"], ""),
                "파일": path.name,
                "문장": sentence[:300],
                "작물후보": ",".join(crops_in(sentence)),
            })
        print(f"    {path.name} … {len(text):,}자")

    return {"작물": crop_hits, "후보": candidates, "글자수": chars, "실패": failed}


def write_report(collected: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    every = [r for v in collected.values() for r in v["목록"]]
    if every:
        keys = sorted({k for r in every for k in r})
        with open(OUT / "목록.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(every)

    cands = [c for v in collected.values() for c in v["스캔"]["후보"]]
    if cands:
        with open(OUT / "규칙후보.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(cands[0].keys()))
            w.writeheader()
            w.writerows(cands)

    out = ["# 주간농사정보 · 병해충발생정보 탐사 결과", ""]

    for name, data in collected.items():
        items, spec, scan = data["목록"], data["spec"], data["스캔"]
        out += [f"## {name} ({spec['service']})", "", f"- 목록 {len(items)}건"]

        dates = sorted(d for d in (r.get(spec["date"], "")[:10] for r in items) if d)
        if dates:
            out.append(f"- 등록일 범위 {dates[0]} ~ {dates[-1]}")
            gaps = []
            for a, b in zip(dates, dates[1:]):
                try:
                    gaps.append((datetime.fromisoformat(b) - datetime.fromisoformat(a)).days)
                except ValueError:
                    pass
            if gaps:
                mid = sorted(gaps)[len(gaps) // 2]
                out.append(f"- 올라오는 간격 중앙값 {mid}일 → {'주 단위' if mid <= 10 else '월 단위 이상'}")

        # 한 글에 여러 판본이 붙으므로 파일 단위로 센다
        exts = Counter(Path(n).suffix.lower()
                       for r in items for n, _ in attachments(r, spec))
        per_post = Counter(len(attachments(r, spec)) for r in items)
        out.append(f"- 첨부 파일 확장자 {dict(exts)}")
        out.append(f"- 글 하나에 붙은 첨부 수 {dict(per_post)}")

        out += ["", f"### 받아서 읽은 첨부 {len(data['파일'])}건 ({scan['글자수']:,}자)", ""]
        for _, path in data["파일"]:
            out.append(f"- {path.name} ({path.stat().st_size/1024:.0f}KB)")
        if scan["실패"]:
            out += ["", "읽기 실패:"] + [f"- {x}" for x in scan["실패"]]

        out += ["", "### 언급된 작물", ""]
        hits = [(c, n) for c, n in scan["작물"].most_common() if n]
        out.append(", ".join(f"{c} {n}회" for c, n in hits[:20]) if hits else "(없음)")

        out += ["", f"### 숫자 조건 문장 {len(scan['후보'])}개 (회보끼리 중복은 제외)", ""]
        withcrop = [c for c in scan["후보"] if c["작물후보"]]
        out += [f"그중 작물명이 같이 나온 것 {len(withcrop)}개", ""]
        for c in (withcrop or scan["후보"])[:25]:
            mark = f"`{c['작물후보']}` " if c["작물후보"] else ""
            out.append(f"- {mark}{c['문장'][:200]}")
        out.append("")

    (OUT / "요약.md").write_text("\n".join(out), encoding="utf-8")


def main() -> None:
    limit = 3
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    skip_files = "--no-files" in sys.argv
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]

    RAW.mkdir(parents=True, exist_ok=True)
    collected = {}

    targets = {k: v for k, v in SERVICES.items() if not only or only in (k, v["service"])}
    if not targets:
        sys.exit(f"--only 값이 이상합니다: {only}  (쓸 수 있는 값: 주간농사정보 / 병해충발생정보)")

    print("[1/3] 두 서비스의 목록을 받습니다")
    for name, spec in targets.items():
        try:
            collected[name] = {"spec": spec, "목록": step1_list(name, spec)}
        except Exception as err:
            print(f"  {name} … 실패: {err}")
    print()

    print(f"[2/3] 서비스마다 첨부파일을 {limit}건씩 받습니다")
    for name, data in collected.items():
        print(f"  [{name}]")
        data["파일"] = [] if skip_files else step2_download(data["목록"], data["spec"], limit)
    print()

    print("[3/3] 첨부 본문에서 작물과 숫자 조건을 찾습니다")
    for name, data in collected.items():
        print(f"  [{name}]")
        data["스캔"] = step3_scan(data["파일"], data["spec"])

    write_report(collected)
    print(f"\n끝났습니다. 결과: {OUT}")
    print("  요약.md 를 저에게 보여주시면 됩니다")


if __name__ == "__main__":
    KEY = api_key()
    main()
