# hwpx · hwp · pdf 문서에서 **표를 격자로** 읽어내는 도구입니다.
# 이 파일은 도구만 담습니다. "무엇을 규칙으로 삼을지" 는 pipeline/build.py 가 정합니다.
#
# 출처 : 보관/재해규칙/rules.py 에서 표 읽기·파싱 부분만 떼어낸 것입니다.
#        나머지(규칙 만들기)는 등록 작물 기준으로 새로 씁니다 — 옛 판에 두 가지 결함이 있었습니다.
#          ① 생육 최저한계를 저온해 경보로 넣어 봄배추가 석 달 내내 경보를 냈습니다
#          ② "토마토"/"방울토마토" 이름이 갈려 조인이 0건이 됐습니다
#
# ─────────────────────────────────────────────────────────────────────
# 왜 따로 도구로 두는가
#
# hwpx 표는 **한 칸 안에 줄이 여럿** 들어 있는 경우가 있습니다. 실제로 이렇습니다.
#
#     작 물 별 ¦ 모기를 때 ¦ 동해온도
#     딸기      ¦ 10       ¦ 0
#     토마토     ¦ 10       ¦ -1~-2      ← 이 세 줄이 '한 칸' 안에 있습니다
#
# 공백으로 이어붙이면 "딸기 토마토 오이" 와 "10 10 12" 가 되어 짝을 잃습니다.
# cell_text() 가 칸 안의 줄바꿈을 살리고, col_split() 이 그것을 다시 행으로 폅니다.
# 한계온도표가 통째로 깨지는 자리라 검증된 코드를 그대로 씁니다.
#
# ─────────────────────────────────────────────────────────────────────
# 쓰는 법
#
#     from feature.hwpx_table import grids_of, parse_threshold
#
#     src, grids = grids_of(Path("원본/재해예방정보/첨부/2026_월간회보_....hwpx"))
#     for grid in grids:                  # grid = [[칸, 칸, …], …]
#         ...
#
#     parse_threshold("≤-2.8℃ (주의) ≤-5.0℃ (위험)", "최저기온")
#     → [{"부등호": "<=", "값": -2.8, "등급": "주의"}, {"부등호": "<=", "값": -5.0, "등급": "위험"}]
#
# 필요 : pip install olefile pypdf

import re
import struct
import zipfile
import zlib
from pathlib import Path
from xml.etree import ElementTree as ET

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

# 위험 등급. 재해예방정보 저온해·고온해 보고가 이 말을 씁니다
GRADES = ("관심", "주의", "경계", "경고", "위험", "심각")
GRADE_RE = re.compile(r"([^()]*?)\(\s*(" + "|".join(GRADES) + r")\s*\)")

METRIC_RE = re.compile(r"(최고기온|최저기온|평균기온|최고온도|최저온도|평균온도|지온|수온)")
TEMP_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*℃")
DAYS_RE = re.compile(r"(\d+)\s*일\s*이상")
LOW_OPS = ("≤", "≦", "이하", "미만", "아래")
HIGH_OPS = ("≥", "≧", "이상", "초과", "넘")


def safe(name: str) -> str:
    return "".join("_" if ch in '\\/:*?"<>|' else ch for ch in name).strip()[:120] or "이름없음"


def clean(text: str) -> str:
    return "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)


def nospace(text: str) -> str:
    return re.sub(r"\s+", "", text)


# ---------- 표 격자 ----------

def cell_text(tc: ET.Element) -> str:
    """표 한 칸의 글자를 읽되 **칸 안의 줄바꿈을 살린다.**

    한 칸에 작물 이름 여섯 개가 줄로 나뉘어 들어 있는 표가 있다. 실제로 이렇다.

        작 물 별 ¦ 모기를 때 ¦ 꽃눈생기기전 ¦ 동해온도
        딸기      ¦ 10       ¦ 3~5        ¦ 0
        토마토     ¦ 10       ¦ 5          ¦ -1~-2      ← 이 세 줄이 '한 칸' 안에 있다

    공백으로 이어붙이면 "딸기 토마토 오이" 와 "10 10 12" 가 되어 짝을 잃는다.
    줄을 살려두면 다시 세로로 짝지을 수 있다.
    """
    lines = []
    for p in tc.iter(HP + "p"):
        parts = [t.text for t in p.iter(HP + "t") if t.text]
        line = " ".join("".join(parts).split())
        if line:
            lines.append(line)
    return "\n".join(lines)


def hwpx_tables(path: Path) -> list[list[list[str]]]:
    grids = []
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if re.fullmatch(r"Contents/section\d+\.xml", n))
        for n in names:
            root = ET.fromstring(z.read(n))
            for tbl in root.iter(HP + "tbl"):
                rows = int(tbl.get("rowCnt") or 0)
                cols = int(tbl.get("colCnt") or 0)
                if not rows or not cols:
                    continue
                grid = [["" for _ in range(cols)] for _ in range(rows)]
                for tc in tbl.iter(HP + "tc"):
                    addr = tc.find(HP + "cellAddr")
                    span = tc.find(HP + "cellSpan")
                    if addr is None:
                        continue
                    r0, c0 = int(addr.get("rowAddr") or 0), int(addr.get("colAddr") or 0)
                    rs = int((span.get("rowSpan") if span is not None else 1) or 1)
                    cs = int((span.get("colSpan") if span is not None else 1) or 1)
                    value = cell_text(tc)
                    # 병합된 칸은 차지하는 자리를 같은 값으로 채운다. 이름이 아래로 이어지게
                    for r in range(r0, min(r0 + rs, rows)):
                        for c in range(c0, min(c0 + cs, cols)):
                            grid[r][c] = value
                grids.append(grid)
    return grids


def col_split(block: list[str]) -> list[list[str]]:
    """여러 줄을 **세로로 뚫린 공백 자리**에서 쪼갠다.

    ⚠ 줄마다 따로 쪼개면 안 된다. 이 문서들은 글자 사이에도 공백을 넣기 때문에
    (`발   아`, `생육  시기`) 줄 단위로 나누면 낱말이 토막난다.
    대신 **모든 줄에서 공백인 칸**을 찾으면 그게 진짜 열 경계다.
    """
    width = max(len(line) for line in block)
    pad = [line.ljust(width) for line in block]
    blank = [all(p[i] == " " for p in pad) for i in range(width)]

    cuts, i = [0], 0
    while i < width:
        if not blank[i]:
            i += 1
            continue
        j = i
        while j < width and blank[j]:
            j += 1
        if j - i >= 2:          # 공백이 두 칸 이상 이어져야 열 경계로 본다
            cuts.append(j)
        i = j
    return [[p[a:b].strip() for a, b in zip(cuts, cuts[1:] + [width])] for p in pad]


def pdf_tables(text: str) -> list[list[list[str]]]:
    """자리를 맞춰 읽은 PDF 글자에서 표처럼 생긴 덩어리를 찾는다.

    PDF 에는 표라는 구조가 없다. 좌표를 공백으로 바꿔 세로가 맞은 것을 다시 쪼갤 뿐이다.
    글머리표로 시작하는 줄은 문장이므로 거른다.
    """
    blocks, cur = [], []

    def flush() -> None:
        if len(cur) >= 2:
            grid = col_split(cur)
            if grid and len(grid[0]) >= 2:
                blocks.append(grid)
        cur.clear()

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip()[0] in "◯○❍●-*※□■=":
            flush()
            continue
        # 열이 2개 이상으로 보이고, 문장이 아닌 줄만 표 후보로 모은다
        cells = [c for c in re.split(r"\s{3,}", line.strip()) if c.strip()]
        if len(cells) >= 2 and len(line.strip()) <= 120:
            cur.append(line)
        else:
            flush()
    flush()
    return blocks


def read_pdf(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return "".join(f"\n===== p.{i} =====\n" + (pg.extract_text(extraction_mode="layout") or "")
                   for i, pg in enumerate(reader.pages, 1))


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
            if kind == 67:
                chunks.append(clean(data[pos + 4: pos + 4 + size].decode("utf-16le", "ignore")))
            pos += 4 + size
    return "\n".join(chunks)


def read_any(path: Path) -> str:
    """문서 전체를 **글자로**. hwpx · hwp · 한글3.0 · PDF 를 형식으로 갈라 읽는다.

    `grids_of` 는 표만 준다. 표가 없는 문서는 이쪽으로 읽는다.
    품종정보 hwp 401개가 표 0개라 본문으로만 읽어야 한다(pipeline/안읽은것.md §3).

    ⚠ 확장자를 믿지 않는다. 파일 앞 4바이트로 판정한다(CLAUDE.md).
    ⚠ 못 읽으면 빈 문자열이다. 사진(FFD8FF)은 글자가 없는 게 맞다 — 실패가 아니다.
      부르는 쪽에서 '읽은 것' 과 '빈 것' 을 따로 세라.
    """
    head = path.read_bytes()[:4]
    try:
        if head[:4] == b"%PDF":
            return read_pdf(path)
        if head[:2] == b"PK":
            # hwpx 는 ZIP 안 section*.xml. 태그를 지우되 문단/칸 경계는 줄로 남긴다.
            z = zipfile.ZipFile(path)
            raw = "".join(
                z.read(n).decode("utf-8", "replace")
                for n in z.namelist() if "section" in n.lower()
            )
            # ⚠ hwpx 태그에는 이름공간이 붙는다 — </hp:p> · </hp:tc> · </hp:tr>.
            #   이름공간을 빼고 찾으면 **하나도 안 잡혀 문서 하나가 몇 줄로 뭉친다.**
            #   실제로 </hp:p> 가 165개인 문서가 5줄로 나왔다. 줄 단위로 다시 캐려면 안 된다.
            raw = re.sub(r"</(?:\w+:)?(?:p|tc|tr)>", "\n", raw)
            raw = re.sub(r"<[^>]+>", " ", raw)
            return "\n".join(
                ln for ln in (re.sub(r"\s+", " ", x).strip() for x in raw.split("\n")) if ln
            )
        if head[:4] == b"\xd0\xcf\x11\xe0":
            return read_hwp(path)
        if head[:4] == b"HWP ":
            # ⚠ 부르는 쪽이 경로를 어떻게 잡았는지 모른다. 둘 다 받아야 한다.
            #   pipeline/src_*.py 는 `feature/` **자체**를 sys.path 에 넣는다.
            #   그 상태에서 `feature.hwp3_pdf` 는 ModuleNotFoundError 가 나는데
            #   read_any 가 예외를 삼켜 **한글 3.0 파일이 조용히 0자가 됐다.**
            #   품종정보 '남천벼' 1,855자가 그렇게 통째로 빠져 있었다.
            try:
                from hwp3_pdf import read_hwp3
            except ImportError:
                from feature.hwp3_pdf import read_hwp3
            return read_hwp3(path)
    except Exception:  # noqa: BLE001
        return ""
    return ""


def grids_of(path: Path) -> tuple[str, list]:
    """확장자가 아니라 앞 4바이트로 형식을 판정한다."""
    head = path.read_bytes()[:4]
    if head[:2] == b"PK":
        return "", hwpx_tables(path)
    if head[:4] == b"%PDF":
        text = read_pdf(path)
        return text, pdf_tables(text)
    if head[:4] == b"\xd0\xcf\x11\xe0":
        return read_hwp(path), []
    raise RuntimeError(f"모르는 형식 (앞 4바이트 {head!r})")


# ---------- 기준값 읽기 ----------

def parse_threshold(cell: str, default_metric: str) -> list[dict]:
    """기준 칸 하나에서 등급별 조건을 뽑는다.

    두 가지 적는 방식이 있다.
        ≤-25℃ (주의) ≤-30℃ (위험)
        최고기온 33℃ 이상 2일이상 지속(주의), 최고기온 35℃ 이상 2일이상 지속(위험)

    등급 표시 앞의 토막을 하나씩 떼어 읽는다.
    """
    text = " ".join(cell.split())
    out = []
    for chunk, grade in GRADE_RE.findall(text):
        temp = TEMP_RE.search(chunk)
        if not temp:
            continue
        m = METRIC_RE.search(chunk)
        metric = m.group(1) if m else default_metric
        if any(op in chunk for op in LOW_OPS):
            op = "<="
        elif any(op in chunk for op in HIGH_OPS):
            op = ">="
        else:                       # 부등호가 없으면 재해 종류로 방향을 정한다
            op = "<=" if "최저" in metric else ">="
        days = DAYS_RE.search(chunk)
        out.append({"지표": metric, "부등호": op, "값": temp.group(1), "단위": "℃",
                    "지속일": days.group(1) if days else "", "등급": grade,
                    "조건원문": chunk.strip(" ,")[:80]})
    if out:
        return out
    # 등급 표시가 없는 칸. 값만이라도 남긴다
    temp = TEMP_RE.search(text)
    if temp:
        m = METRIC_RE.search(text)
        return [{"지표": m.group(1) if m else default_metric,
                 "부등호": "<=" if any(o in text for o in LOW_OPS) else ">=",
                 "값": temp.group(1), "단위": "℃", "지속일": "", "등급": "",
                 "조건원문": text[:80]}]
    return []


def header_of(grid: list[list[str]]) -> str:
    return nospace(" ".join(c.replace("\n", " ") for c in grid[0] if c))


# ---------- 표 알아보기 ----------
