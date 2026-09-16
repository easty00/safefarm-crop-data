# 농사로 품종정보(varietyInfo) 를 작물 가리지 않고 전부 받아 글자로 바꾸는 스크립트입니다.
# 자세한 사용법은 같은 폴더의 "사용법.md" 를 읽어주세요.
#
# 여섯 분류 2,599품종이 전부 대상입니다. 벼나 식량작물로 좁히지 않습니다.
#
#   FC 식량작물 1,018   FL 화훼 839   IC 특용작물 266
#   VC 채소       247   FT 과수 221   FG 녹비작물  8
#
# 목록 응답의 주요특성(mainChartrInfo)은 두세 줄짜리 요약입니다.
# 출수기·성숙기 같은 실제 날짜는 첨부된 품종요약서 안에 있습니다. 그래서 첨부를 받습니다.

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

BASE = "http://api.nongsaro.go.kr/service/varietyInfo"
HERE = Path(__file__).resolve().parent
OUT = HERE / "결과"
RAW = OUT / "raw"
FILES = OUT / "첨부"
TEXTS = OUT / "본문"
WAIT = 0.4
PAGE = 200
BAD_CHARS = '\\/:*?"<>|'

# 분류 코드는 mainCategoryList 로 받지만, 건수를 미리 알아야 진행률을 보여줄 수 있어 적어둔다
KNOWN = {"FC": 1018, "FL": 839, "IC": 266, "VC": 247, "FT": 221, "FG": 8}

# 코드 묶음별 뜻. subCategoryList 가 돌려주는 codeGroup 번호다
GROUP_NAME = {"218": "기능", "219": "지대", "220": "숙기"}


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

    2010년 이전 품종요약서 몇 건이 이 형식이다. OLE 도 ZIP 도 아니라 앞이 'HWP ' 로 시작한다.
    글자 하나가 2바이트 리틀엔디안 낱말로 들어있고, 0x8000 이상이면 조합형 코드라서
    빅엔디안으로 뒤집어 johab 으로 푼다.

    다만 문단 구조까지 해석하지는 않는다. 글자처럼 읽히는 구간만 이어붙이는 방식이라
    기록 경계에서 몇 글자가 빠질 수 있다. 완전한 판독이 아니라 건져내기다.
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
            if len(cur) >= 10:          # 짧은 조각은 바이너리가 우연히 글자로 읽힌 것
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
        # 요약서 자리에 사진이 올라온 경우가 있다. 이름이 .pdf 라도 내용이 사진이다.
        # 글자가 없는 게 맞으니 오류로 세지 않고 사진이라고 적어둔다
        raise Images(f"사진 파일 (앞 3바이트 {head[:3]!r})")
    raise RuntimeError(f"모르는 형식 (앞 4바이트 {head!r})")


# ---------- 단계 ----------

def step_codes() -> tuple[list[dict], list[dict], dict]:
    """분류·작물·코드표를 받는다.

    subCategoryList 는 categoryCode 를 무엇으로 주든 같은 124개를 돌려준다.
    (FC·VC·FC010101 로 각각 불러 같은 결과임을 확인했다.) 그래서 한 번만 부른다.
    """
    cats = rows(call("mainCategoryList", "main"))
    print(f"  분류 {len(cats)}개: " + ", ".join(f"{c['categoryCode']} {c['categoryNm']}" for c in cats))

    crops, mids = [], []
    for c in cats:
        code = c["categoryCode"]
        for r in rows(call("middleCategoryList", f"middle_{code}", categoryCode=code)):
            r["분류코드"], r["분류명"] = code, c["categoryNm"]
            mids.append(r)
            # gubn 이 CLASS1·CROP·YEAR 세 가지로 섞여 나온다.
            # 예전에 이걸 안 갈라서 육성년도(2016~2025)를 작물로 세었던 적이 있다
            if r.get("gubn") == "CROP":
                crops.append({"분류코드": code, "분류명": c["categoryNm"],
                              "작물코드": r.get("code", ""), "작물명": r.get("codeNm", "")})
    print(f"  작물 {len(crops)}종 (중분류 응답 {len(mids)}행 중 gubn=CROP 만)")

    names = {}
    for r in rows(call("subCategoryList", "sub_all", categoryCode="FC")):
        code, nm = r.get("code", ""), r.get("codeNm", "")
        if code and nm and nm != "-":
            names[code] = nm
    print(f"  코드표 {len(names)}개 (이름 없는 코드는 그대로 둔다)")
    return cats, crops, names


def step_list(cats: list[dict], only_cats: list[str] | None) -> list[dict]:
    got = []
    for c in cats:
        code, nm = c["categoryCode"], c["categoryNm"]
        if only_cats and code not in only_cats:
            continue
        page, total = 1, None
        while True:
            root = call("varietyList", f"list_{code}_{page}",
                        categoryCode=code, pageNo=page, numOfRows=PAGE)
            if total is None:
                total = int(root.findtext(".//totalCount") or 0)
            batch = rows(root)
            for r in batch:
                r["분류코드"], r["분류명"] = code, nm
            got += batch
            print(f"  {code} {nm:6} {min(page * PAGE, total):>5}/{total}")
            if page * PAGE >= total or not batch:
                break
            page += 1
    return got


def enrich(items: list[dict], names: dict) -> None:
    """코드에 이름을 붙인다. 원래 코드 칸은 지우지 않고 그대로 남긴다."""
    for r in items:
        r["숙기"] = names.get(r.get("mtrtSeCode", ""), "")
        r["지대"] = names.get(r.get("grdlSeCode", ""), "")
        # 기능 구분은 '218044|218046' 처럼 여러 개가 붙어서 온다
        r["기능"] = " | ".join(names.get(c, c) for c in r.get("skllSeCode", "").split("|") if c)
        # '콩 > 장류두부콩' 을 작물과 세부로 나눠둔다. 나중에 작물 단위로 묶을 때 쓴다
        parts = [p.strip() for p in (r.get("svcCodeNm") or "").split(">")]
        r["작물명"] = parts[0] if parts else ""
        r["세부작물"] = parts[1] if len(parts) > 1 else ""


def step_traits(items: list[dict]) -> list[dict]:
    """주요특성 글을 '가. 용도 : …' 단위로 쪼갠다.

    쪼개도 원문(mainChartrInfo)은 품종목록.csv 에 통째로 남겨둔다.
    항목 이름이 '용도'·'용 도'·'용    도' 처럼 제각각이라 띄어쓰기를 지워 맞춘다.
    """
    head = re.compile(r"(?:^|\n)\s*[가-힣]\s*\.\s*([^:：\n]{1,20})\s*[:：]\s*")
    out = []
    for r in items:
        text = (r.get("mainChartrInfo") or "").strip()
        if not text:
            continue
        marks = list(head.finditer(text))
        if not marks:
            out.append({"cntntsNo": r["cntntsNo"], "분류명": r["분류명"], "작물명": r["작물명"],
                        "품종명": r["cntntsSj"], "항목": "(구분없음)",
                        "내용": " ".join(text.split())})
            continue
        for i, m in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
            out.append({"cntntsNo": r["cntntsNo"], "분류명": r["분류명"], "작물명": r["작물명"],
                        "품종명": r["cntntsSj"],
                        "항목": re.sub(r"\s+", "", m.group(1)),
                        "내용": " ".join(text[m.end():end].split())})
    return out


def step_download(items: list[dict]) -> list[str]:
    failed = []
    for i, r in enumerate(items, 1):
        link = r.get("atchFileLink", "")
        if not link:
            failed.append(f"{r['작물명']} {r['cntntsSj']}: 첨부 주소 없음")
            continue
        folder = FILES / safe(r["분류명"]) / safe(r["작물명"] or "미분류")
        folder.mkdir(parents=True, exist_ok=True)
        # 품종이 달라도 파일명이 겹치는 경우가 있어 컨텐츠 번호를 앞에 붙인다
        path = folder / safe(f"{r['cntntsNo']}_{r.get('orginlFileNm') or '첨부.bin'}")
        # 0바이트로 저장된 적이 있다. 있다고 건너뛰면 영영 빈 채로 남는다
        if path.exists() and path.stat().st_size == 0:
            path.unlink()
        if not path.exists():
            try:
                blob = fetch(link)
                # 없는 파일에 200 과 안내 페이지를 돌려주는 서버가 있다.
                # 그대로 저장하면 다음 실행 때 받은 줄 알고 건너뛴다
                if blob[:16].lstrip().lower().startswith((b"<!doctype", b"<html")):
                    raise RuntimeError("파일 대신 안내 페이지가 왔습니다")
                if not blob:
                    raise RuntimeError("빈 파일(0바이트)이 왔습니다")
                path.write_bytes(blob)
                time.sleep(WAIT)
            except Exception as err:
                failed.append(f"{r['작물명']} {r['cntntsSj']}: {err}")
                print(f"  [{i}/{len(items)}] 실패 {r['cntntsSj'][:30]}")
                continue
        r["첨부"] = str(path.relative_to(OUT))
        r["첨부KB"] = round(path.stat().st_size / 1024)
        if i % 25 == 0 or i == len(items):
            done = sum(1 for x in items[:i] if x.get("첨부"))
            mb = sum(x.get("첨부KB", 0) for x in items[:i]) / 1024
            print(f"  [{i}/{len(items)}] 받음 {done}건 · {mb:,.0f}MB")
    return failed


def step_text(items: list[dict]) -> list[str]:
    """첨부 전문을 통째로 글자로 바꿔 저장한다. 어떤 필터도 걸지 않는다."""
    TEXTS.mkdir(parents=True, exist_ok=True)
    failed, images = [], []
    targets = [r for r in items if r.get("첨부")]
    for i, r in enumerate(targets, 1):
        src = OUT / r["첨부"]
        # 첨부와 같은 갈래로 폴더를 나눈다. 작물 하나를 볼 때 한 곳만 열면 되도록
        folder = TEXTS / safe(r["분류명"]) / safe(r["작물명"] or "미분류")
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / (safe(f"{r['cntntsNo']}_{r['cntntsSj']}") + ".txt")
        try:
            text = dest.read_text(encoding="utf-8") if dest.exists() else extract(src)
        except Images as err:
            r["첨부종류"] = "사진"
            images.append(f"{r['작물명']} {r['cntntsSj']}: {err}")
            continue
        except Exception as err:
            failed.append(f"{r['cntntsSj']} 판독: {err}")
            continue
        if not dest.exists():
            dest.write_text(text, encoding="utf-8")
        r["본문"] = str(dest.relative_to(OUT))
        r["본문자수"] = len(text)
        if i % 25 == 0 or i == len(targets):
            print(f"  [{i}/{len(targets)}] 판독 {sum(1 for x in targets[:i] if x.get('본문자수'))}건")
    if images:
        print(f"  첨부가 사진이라 글자가 없는 품종 {len(images)}건")
    return failed, images


# ---------- 결과 ----------

def dump(path: Path, data: list[dict]) -> None:
    if not data:
        return
    keys = list(dict.fromkeys(k for d in data for k in d))
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(data)


def write_report(items, crops, traits, names, failed, images) -> None:
    by_cat = Counter(r["분류명"] for r in items)
    by_crop = Counter(r["작물명"] for r in items)
    read = [r for r in items if r.get("본문자수")]
    mb = sum(r.get("첨부KB", 0) for r in items) / 1024

    out = ["# 품종정보 수집 결과", "",
           f"품종 {len(items):,}건 · 작물 {len(by_crop)}종 · 분류 {len(by_cat)}개",
           f"첨부 {sum(1 for r in items if r.get('첨부')):,}건 · {mb:,.0f}MB · "
           f"판독 {len(read):,}건 · 본문 {sum(r.get('본문자수',0) for r in read):,}자", ""]

    out += ["## 분류별", "", "| 분류 | 품종 | 작물 | 첨부 | 용량 |", "|---|---|---|---|---|"]
    for nm, n in by_cat.most_common():
        sub = [r for r in items if r["분류명"] == nm]
        out.append(f"| {nm} | {n:,} | {len({r['작물명'] for r in sub})} | "
                   f"{sum(1 for r in sub if r.get('첨부')):,} | "
                   f"{sum(r.get('첨부KB',0) for r in sub)/1024:,.0f}MB |")

    out += ["", "## 품종이 많은 작물 40", "", "| 작물 | 품종 수 |", "|---|---|"]
    for nm, n in by_crop.most_common(40):
        out.append(f"| {nm} | {n:,} |")

    zero = sorted({c["작물명"] for c in crops} - set(by_crop))
    out += ["", f"## 품종이 0건인 작물 {len(zero)}종", "",
            ", ".join(zero) if zero else "없음"]

    out += ["", "## 주요특성 항목 이름 (상위 30)", "",
            "항목 이름이 작물마다 달라서, 표로 만들 때 이 목록을 보고 맞춰야 합니다.", ""]
    for nm, n in Counter(t["항목"] for t in traits).most_common(30):
        out.append(f"- {n:>4}회  {nm}")

    out += ["", "## 코드가 채워진 비율", ""]
    for col in ("숙기", "지대", "기능"):
        out.append(f"- {col} : {sum(1 for r in items if r.get(col)):,}/{len(items):,}건")
    out.append(f"- 코드표에 이름이 있는 코드 : {len(names)}개")

    out += ["", "## 육성년도 분포", ""]
    years = Counter(r.get("unbrngYear", "") for r in items if r.get("unbrngYear"))
    recent = sorted(years.items(), reverse=True)[:15]
    out += [f"- {y}년 : {n:,}건" for y, n in recent]

    if images:
        out += ["", f"## 첨부가 사진인 품종 {len(images)}건", "",
                "요약서 자리에 사진이 올라와 있습니다. 글자가 없는 게 맞아서 실패로 세지 않습니다.", ""]
        out += [f"- {x}" for x in images]

    if failed:
        out += ["", f"## 실패 {len(failed)}건", ""] + [f"- {x}" for x in failed[:60]]
        if len(failed) > 60:
            out.append(f"- … 외 {len(failed)-60}건")

    (OUT / "요약.md").write_text("\n".join(out), encoding="utf-8")


def main() -> None:
    only_cats = None
    if "--cat" in sys.argv:
        only_cats = [c.strip().upper() for c in sys.argv[sys.argv.index("--cat") + 1].split(",")]
    mode = "all"
    if "--files" in sys.argv:
        mode = sys.argv[sys.argv.index("--files") + 1]
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    for folder in (OUT, RAW, FILES, TEXTS):
        folder.mkdir(parents=True, exist_ok=True)

    print("[1/5] 분류·작물·코드표를 받습니다")
    cats, crops, names = step_codes()
    dump(OUT / "분류목록.csv", cats)
    dump(OUT / "작물목록.csv", crops)
    dump(OUT / "코드표.csv",
         [{"코드": c, "이름": n, "묶음": GROUP_NAME.get(c[:3], "")} for c, n in sorted(names.items())])

    expect = sum(KNOWN.get(c["categoryCode"], 0) for c in cats
                 if not only_cats or c["categoryCode"] in only_cats)
    print(f"\n[2/5] 품종 목록을 받습니다 (약 {expect:,}건)")
    items = step_list(cats, only_cats)
    enrich(items, names)
    if limit:
        items = items[:limit]
        print(f"  --limit {limit} 이라 앞에서 {len(items)}건만 씁니다")
    print(f"  총 {len(items):,}건\n")

    print("[3/5] 주요특성을 항목별로 쪼갭니다")
    traits = step_traits(items)
    dump(OUT / "특성.csv", traits)
    print(f"  {len(traits):,}행\n")

    failed, images = [], []
    if mode == "none":
        print("[4/5] --files none 이라 첨부는 건너뜁니다\n[5/5] 건너뜁니다\n")
    else:
        print(f"[4/5] 첨부를 내려받습니다 ({len(items):,}건)")
        failed += step_download(items)
        print()
        print("[5/5] 첨부 전문을 글자로 바꿉니다")
        f5, images = step_text(items)
        failed += f5
        print()

    dump(OUT / "품종목록.csv", items)
    write_report(items, crops, traits, names, failed, images)

    print(f"끝났습니다. 결과: {OUT}")
    print("  요약.md 를 저에게 보여주시면 됩니다")
    if failed:
        print(f"  ! 실패 {len(failed)}건 — 요약.md 맨 아래")


if __name__ == "__main__":
    KEY = api_key()
    main()
