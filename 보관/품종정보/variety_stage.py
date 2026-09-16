# 품종요약서에서 출수기·성숙기·숙기·생육일수를 뽑는 스크립트입니다.
# 자세한 사용법은 같은 폴더의 "생육시기추출_사용법.md" 를 읽어주세요.
#
# 새로 내려받는 것은 없습니다. 이미 받아둔 결과/첨부/ 와 결과/본문/ 을 읽기만 합니다.
#
# 첨부 2,537건의 형식이 이렇게 갈립니다. 형식마다 읽는 방법이 다릅니다.
#
#   hwp (구형식)  1,171   표 구조가 없다. 칸이 한 줄씩 흩어진 평문만 나온다
#   pdf          1,140   자리를 맞춰 읽으면 칸이 세로로 맞는다
#   hwpx           209   표가 XML 로 들어 있어 행·열을 그대로 살릴 수 있다
#   사진            14   글자가 없다
#   한글 3.0         3   조합형으로 건져낸다
#
# 과반이 hwp 라서 표를 격자로 되살릴 수 없습니다. 그래서 평문에서는 이렇게 읽습니다.
#
#   품 종 명        ← 머리 블록 시작
#   성숙기
#   (월.일)         ← 단위 표시. 여기가 머리 블록이라는 증거
#   경장
#   (cm)
#   다유            ← 값 블록 시작. 첫 품종 이름
#   10.15          ← 머리에서 성숙기가 첫 칸이므로 이 값이 성숙기
#
# **머리 블록 다음에 나오는 첫 '날짜만 있는 줄'** 을 값으로 봅니다.
# 완벽하지 않아서 신뢰도를 같이 적습니다. 숫자만 믿지 말고 원문을 같이 보세요.

import csv
import logging
import re
import struct
import sys
import time
import warnings
import zipfile
import zlib
from collections import Counter, defaultdict
from html import unescape
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
OUT = HERE / "결과"
FILES = OUT / "첨부"

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

# PDF 한 건에 자리 맞춰 읽기로 쓸 수 있는 시간. 넘기면 보통 방식으로 바꾼다
PAGE_BUDGET = 3.0
# 한 쪽이 이보다 길면 공백으로 부푼 것이다. 보통 쪽은 2~3천 자다
PAGE_CHARS = 20000
SLOW_PDF: list[str] = []

# pypdf 가 쪽마다 "Rotated text discovered" 를 찍어 진행 로그를 덮는다. 끈다
logging.getLogger("pypdf").setLevel(logging.ERROR)
warnings.filterwarnings("ignore")

# 뽑을 시기 항목. 작물마다 부르는 이름이 다르다
STAGE_WORDS = {
    "출수기": ("출수기", "출수일"),
    "성숙기": ("성숙기", "성숙일"),
    "수확기": ("수확기", "수확일"),
    "개화기": ("개화기", "개화일", "개화시"),
    "파종기": ("파종기", "파종일"),
}
UNIT_MARK = re.compile(r"^\s*[(（]\s*월\s*[.,．、]\s*일\s*[)）]\s*$")
HEAD_START = re.compile(r"^\s*품\s*종\s*명")
# 줄 전체가 날짜 하나인 것. 평문 표에서는 값이 한 줄을 차지한다
DATE_ONLY = re.compile(r"^\s*(\d{1,2})\s*[.．]\s*(\d{1,2})\s*[.．]?\s*$")
# 문장 안의 날짜. "성숙기가 10월 28일로"
DATE_IN = re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일")

# 숙기를 그대로 적은 말. '조숙' 은 작형(조숙재배)과 겹쳐서 여기 안 넣는다
# 가운뎃점으로 이은 중간 표기가 있다. "조·중생종" 은 상추 5품종이 쓴다
MATURITY_WORD = re.compile(
    r"(극조생|극만생|조\s*[·․‧∙]\s*중생|중\s*[·․‧∙]\s*만생|중만생|조생|중생|만생|중만숙)\s*종?")
# 풀어 쓴 말. "숙기가 빠른" 처럼 적힌 것이 배추·마늘에 많다
MATURITY_PHRASE = [
    (re.compile(r"숙기[가는]?\s*(?:매우\s*)?(?:빠르|이르|짧)"), "조생"),
    (re.compile(r"숙기[가는]?\s*(?:다소\s*|매우\s*)?(?:늦|길)"), "만생"),
    (re.compile(r"(?:중간|보통)\s*숙기"), "중생"),
    (re.compile(r"조기\s*수확\s*(?:가능|용)"), "조생"),
]
# 이 말이 든 줄은 숙기를 말하는 게 아니다. 뜻이 전혀 다르다
MATURITY_STOP = ("만추대", "조숙재배", "촉성재배", "억제재배", "반촉성", "비가림",
                 "성숙기의", "수확성숙기", "성숙기 색", "용 도 숙기", "숙기z",
                 "만추대성", "추대")
DAYS_RE = re.compile(r"(생육일수|등숙일수|육묘일수|재배기간|생육기간)\D{0,6}(\d{1,3})")
# 숫자 **바로 뒤**에 비교말이 붙으면 그 숫자는 대조 품종과의 차이값이다.
#   "본답생육일수는 1일 짧았음"          → 차이값. 버린다
#   "본답 생육일수는 127일로 … 7일 길고"  → 127 은 값이다. '길고' 는 뒤쪽 다른 절이다
# 그래서 '일' 다음에 조사 없이 곧바로 비교말이 오는 경우만 본다
COMPARE_AFTER = re.compile(r"^\s*일?\s*(정도\s*)?(짧|길|늦|빠르|적|많|이르)")
REGION_HEAD = re.compile(r"^\s*\d*\s*[.．]?\s*적응\s*지역")

# 이 낱말이 든 문장의 날짜는 그 시기가 아니라 '해야 할 작업' 날짜다
SENTENCE_STOP = ("모내기", "이앙", "파종은", "파종하", "완료", "이내에", "까지는",
                 "피하", "늦추", "앞당", "권장", "준수")

# hwp 판독 부산물. 표 시작 표시가 한자처럼 깨져 나온다
JUNK_RE = re.compile(r"[氠瑢漠杳捤獥汤捯-]+")
# 적응지역 안의 온도 조건. "1월 최저 평균기온 -8℃ 이상 지역"
REGION_TEMP = re.compile(r"(\d{1,2})\s*월[^.]{0,20}?(최저|최고|평균)[^.]{0,12}?기온[^.]{0,8}?"
                         r"(-|–|—|▲)?\s*(\d{1,2}(?:\.\d)?)\s*℃\s*(이상|이하|미만|초과)?")


def safe(name: str) -> str:
    return "".join("_" if ch in '\\/:*?"<>|' else ch for ch in name).strip()[:120] or "이름없음"


def clean(text: str) -> str:
    return "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)


def nospace(text: str) -> str:
    return re.sub(r"\s+", "", text)


def valid_date(mm: str, dd: str) -> bool:
    """1~12월, 1~31일만 날짜로 본다.

    이걸 안 걸면 등숙률 92.3 이나 천립중 19.5 가 날짜로 읽힌다. 실제로 그렇게 된다.
    """
    m, d = int(mm), int(dd)
    return 1 <= m <= 12 and 1 <= d <= 31


# ---------- 문서 읽기 ----------

def cell_text(tc: ET.Element) -> str:
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
                    for r in range(r0, min(r0 + rs, rows)):
                        for c in range(c0, min(c0 + cs, cols)):
                            grid[r][c] = value
                grids.append(grid)
    return grids


def read_hwpx(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if re.fullmatch(r"Contents/section\d+\.xml", n))
        out = []
        for n in names:
            raw = z.read(n).decode("utf-8", "ignore")
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
            if kind == 67:
                chunks.append(clean(data[pos + 4: pos + 4 + size].decode("utf-16le", "ignore")))
            pos += 4 + size
    return "\n".join(chunks)


def read_hwp3(path: Path) -> str:
    """한글 3.0. 2바이트 조합형으로 담긴 글자를 건져낸다."""
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
            if len(cur) >= 10:
                runs.append("".join(cur))
            cur = []
        else:
            cur.append(c)
    if len(cur) >= 10:
        runs.append("".join(cur))
    return "\n".join(runs)


def fix_mojibake(text: str) -> str:
    """CP949 를 라틴으로 잘못 읽어 깨진 글자를 되돌린다.

    1990년대 PDF 는 한글 CMap(`/KSCms-UHC-H`)을 쓰는데 pypdf 가 그걸 모른다.
    그래서 바이트를 그대로 라틴 글자로 내놓는다.

        ´ëÁß2Á¶ ´ë¸Æ1È£  →  대중2조 대맥1호

    바이트로 되돌린 뒤 cp949 로 다시 읽으면 살아난다. 한글 비율이 늘 때만 바꾼다.
    """
    if not text or not any("À" <= ch <= "ÿ" for ch in text):
        return text
    try:
        fixed = text.encode("latin-1", "ignore").decode("cp949", "ignore")
    except Exception:
        return text
    def hangul(s: str) -> int:
        return sum(1 for ch in s if "가" <= ch <= "힣")
    return fixed if hangul(fixed) > hangul(text) else text


def read_page(page, layout: bool) -> str:
    """쪽 하나를 읽는다. 옛 한글 CMap 을 모른다는 오류는 보통 방식으로 넘긴다."""
    try:
        text = page.extract_text(extraction_mode="layout") if layout else page.extract_text()
    except Exception:
        # "unknown encoding: /KSCms-UHC-H" — 1990년대 PDF. 자리 맞추기를 포기하고 읽는다
        try:
            text = page.extract_text()
        except Exception:
            return ""
    return fix_mojibake(text or "")


def read_pdf(path: Path) -> str:
    """PDF 를 칸 자리를 살려 읽되, 오래 걸리면 도중에 보통 방식으로 바꾼다.

    ⚠ `extraction_mode="layout"` 은 글자 좌표를 일일이 계산한다. 대부분은 0.1초면 끝나는데
    어떤 문서에서는 **한 건에 8분** 이 걸린다. 실제로 청보리 품종설명서 하나가 493초였다.
    쪽수 문제가 아니라 글자 배치 문제라 파일 크기로는 미리 못 거른다.

    그래서 쪽마다 시간을 재서 예산(PAGE_BUDGET)을 넘기면 남은 쪽은 보통 방식으로 읽는다.
    자리는 흐트러지지만 글자는 다 나온다. 아예 못 읽는 것보다 낫다.
    """
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    out, spent, slow = [], 0.0, False
    for i, pg in enumerate(reader.pages, 1):
        t0 = time.time()
        if slow:
            text = read_page(pg, False)
        else:
            text = read_page(pg, True)
            spent += time.time() - t0
            # 글자를 하나씩 따로 찍은 PDF 가 있다. 그런 문서에 자리를 맞추면
            # 글자 사이가 전부 공백으로 채워져 한 쪽이 6만 자로 부푼다.
            # 7쪽짜리가 42만 자가 된 적이 있고, 그 뒤 파서들이 거기서 멈췄다.
            if len(text) > PAGE_CHARS or spent > PAGE_BUDGET:
                slow = True
                text = read_page(pg, False)         # 이 쪽부터 보통 방식으로
        out.append(f"\n===== p.{i} =====\n" + text)
    if slow:
        SLOW_PDF.append(path.name)
    return "".join(out)


def load(path: Path) -> tuple[str, list, str]:
    """확장자가 아니라 앞 4바이트로 형식을 판정한다."""
    head = path.read_bytes()[:4]
    if head[:2] == b"PK":
        return read_hwpx(path), hwpx_tables(path), "hwpx"
    if head[:4] == b"%PDF":
        return read_pdf(path), [], "pdf"
    if head[:4] == b"\xd0\xcf\x11\xe0":
        return read_hwp(path), [], "hwp"
    if head[:4] == b"HWP ":
        return read_hwp3(path), [], "hwp3"
    if head[:3] in (bytes.fromhex("ffd8ff"), bytes.fromhex("89504e"), b"GIF"):
        return "", [], "사진"
    raise RuntimeError(f"모르는 형식 (앞 4바이트 {head!r})")


# ---------- 값 뽑기 ----------

def from_grid(grids: list, crop: dict) -> list[dict]:
    """hwpx 표에서 머리글과 값을 짝지어 읽는다. 자리가 확실해서 가장 믿을 만하다."""
    out = []
    for tno, grid in enumerate(grids, 1):
        if len(grid) < 2:
            continue
        head = [nospace(c.replace("\n", " ")) for c in grid[0]]
        for c, h in enumerate(head):
            for stage, words in STAGE_WORDS.items():
                if not any(w in h for w in words):
                    continue
                for r, row in enumerate(grid[1:], 1):
                    if c >= len(row):
                        continue
                    for line in row[c].split("\n"):
                        m = DATE_ONLY.match(line) or re.match(
                            r"^\s*(\d{1,2})\s*[.．]\s*(\d{1,2})", line.strip())
                        if m and valid_date(m.group(1), m.group(2)):
                            out.append({**crop, "항목": stage,
                                        "월": int(m.group(1)), "일": int(m.group(2)),
                                        "행": r, "신뢰도": "표",
                                        "원문": f"{h} = {' '.join(row[c].split())[:40]}"})
                            break
                    break       # 표의 첫 데이터 행이 그 요약서의 주인공 품종이다
    return out


def from_flat(text: str, crop: dict) -> list[dict]:
    """평문에서 머리 블록을 찾고 그 다음 첫 날짜 줄을 값으로 본다.

    hwp 는 표 구조가 없어서 이 방법밖에 없다. 그래서 신뢰도를 따로 적는다.
      머리블록 : '품종명' 과 '(월.일)' 이 같이 있는 블록 뒤의 첫 날짜 줄
      문장     : "성숙기가 10월 28일로" 처럼 문장 안에 든 것
    """
    lines = text.splitlines()
    out = []

    # ① 머리 블록 방식
    for i, line in enumerate(lines):
        if not HEAD_START.match(line):
            continue
        block = lines[i: i + 30]
        if not any(UNIT_MARK.match(x) for x in block):
            continue
        order = []              # 머리에 나온 시기 항목을 순서대로
        end = i
        for j, x in enumerate(block):
            for stage, words in STAGE_WORDS.items():
                if any(w in nospace(x) for w in words):
                    order.append(stage)
            if UNIT_MARK.match(x):
                end = i + j
        if not order:
            continue
        for x in lines[end + 1: end + 40]:
            m = DATE_ONLY.match(x)
            if m and valid_date(m.group(1), m.group(2)):
                out.append({**crop, "항목": order[0],
                            "월": int(m.group(1)), "일": int(m.group(2)),
                            "행": 1, "신뢰도": "머리블록",
                            "원문": " | ".join(y.strip() for y in lines[end - 2: end + 3])[:80]})
                break
        break

    # ② 문장 안에 든 것
    for line in lines:
        flat = nospace(line)
        # ⚠ 그 시기를 말하는 문장이 아니라 **다른 작업 날짜**를 말하는 문장이 섞인다.
        #     "출수기가 늦으므로 6월 10일 이내에 모내기를 완료하여야 하며"
        # 이걸 출수기로 읽으면 논벼 출수기가 6월이 된다. 실제로 중모1020이 그랬다.
        if any(w in flat for w in SENTENCE_STOP):
            continue
        for stage, words in STAGE_WORDS.items():
            if not any(w in flat for w in words):
                continue
            m = DATE_IN.search(line)
            if m and valid_date(m.group(1), m.group(2)):
                out.append({**crop, "항목": stage,
                            "월": int(m.group(1)), "일": int(m.group(2)),
                            "행": 0, "신뢰도": "문장",
                            "원문": " ".join(line.split())[:90]})
    return out


def norm_maturity(word: str) -> str:
    word = re.sub(r"[\s·․‧∙]", "", word)
    if word in ("조중생", "중만생", "중만숙"):
        return "중생" if word == "조중생" else "중만생"
    if "극조" in word:
        return "극조생"
    if word.startswith("중만"):
        return "중만생"
    if "조" in word:
        return "조생"
    if "만" in word:
        return "만생"
    return "중생"


def maturity_in(text: str) -> tuple[str, str]:
    """글에서 숙기를 찾는다. 찾은 문장도 같이 돌려준다.

    ⚠ 이름만 비슷하고 뜻이 다른 말이 많다. 처음엔 `조생|중생|만생` 만 찾다가
    배추 9건 중 2건, 고추 5건 중 1건밖에 못 잡았다. 반대로 넓히기만 하면 엉뚱한 게 붙는다.

        잡아야 할 것
            "숙기가 빠른 배추"                 → 조생
            "중간 숙기(정식일부터 약 60일 이후)"  → 중생
            "만생종, 숙기가 길어 결구가 늦음"     → 만생
            "극조생종(정식 후 50일 이하 수확)"    → 극조생

        잡으면 안 되는 것
            "2011년조숙재배"                  ← **작형 이름**이지 숙기가 아니다
            "만추대, 다수성 품종"               ← 꽃대가 늦다는 뜻. 숙기와 다르다
            "과실: 성숙기의 색" · "수확성숙기"    ← 그냥 '성숙기' 라는 낱말
            "품종명 용 도 숙기"                ← 표 머리글
    """
    for raw in text.splitlines():
        line = unescape(" ".join(raw.split()))
        if not line:
            continue
        for m in MATURITY_WORD.finditer(line):
            # ⚠ 금지어가 나왔다고 **줄 전체를 버리면 안 된다.**
            # 상추 설명이 "…조·중생종이며, 고온기 비가림하우스 재배시…" 라서
            # '비가림' 하나 때문에 진짜 숙기 문장 5건이 통째로 날아갔다.
            # 걸린 자리 앞뒤 12글자만 본다
            near = line[max(0, m.start() - 12): m.end() + 12]
            if any(s in near for s in MATURITY_STOP):
                continue
            return norm_maturity(m.group(1)), line[:110]
        for pat, kind in MATURITY_PHRASE:
            m = pat.search(line)
            if not m:
                continue
            near = line[max(0, m.start() - 12): m.end() + 12]
            if any(s in near for s in MATURITY_STOP):
                continue
            return kind, line[:110]
    return "", ""


def maturity_of(text: str, row: dict) -> tuple[str, str, str]:
    """숙기를 코드 → 주요특성 → 본문 순으로 찾는다. 출처와 원문을 같이 남긴다."""
    if row.get("숙기"):
        return norm_maturity(row["숙기"]), "코드", row["숙기"]
    kind, line = maturity_in(row.get("mainChartrInfo") or "")
    if kind:
        return kind, "주요특성", line
    kind, line = maturity_in(text)
    if kind:
        return kind, "본문", line
    return "", "", ""


def days_of(text: str) -> list[tuple[str, str, str]]:
    """생육일수·육묘일수를 뽑는다.

    ⚠ 품종요약서는 **대조 품종과의 차이**를 같은 말로 적는다. 그걸 일수로 읽으면 안 된다.

        "본답 생육일수는 127일로 다산보다 7일 길고"    → 127 이 맞다
        "본답생육일수는 1일 짧았음"                  → 1 은 **차이값**이지 일수가 아니다
        "생육일수는 14일, 성숙일수는 5일정도 흑남벼보다 짧고"  → 14 도 차이값

    실제로 벼 6건이 1·2·9·14 같은 값으로 들어와 있었다. 그래서 숫자 **뒤**에
    비교말이 곧바로 오면 버리고, 작물 생육으로 말이 안 되는 30일 미만도 버린다.
    """
    out = []
    for raw in text.splitlines():
        line = " ".join(raw.split())
        for m in DAYS_RE.finditer(line):
            days = int(m.group(2))
            if not 1 <= days <= 400:
                continue
            after = line[m.end(): m.end() + 14]
            if COMPARE_AFTER.search(after):     # "…는 1일 짧았음"
                continue
            # 육묘는 14일도 있지만 생육·재배 기간이 30일 미만이면 차이값일 가능성이 크다
            if m.group(1) in ("생육일수", "재배기간", "생육기간") and days < 30:
                continue
            out.append((m.group(1), m.group(2), line[:90]))
    return out


def region_of(lines: list[str]) -> str:
    """'적응 지역' 절의 내용을 가져온다. 다음 절 번호를 만나면 멈춘다."""
    for i, line in enumerate(lines):
        if not REGION_HEAD.match(line):
            continue
        body = []
        for x in lines[i + 1: i + 6]:
            x = " ".join(JUNK_RE.sub(" ", x).split())    # 판독 부산물 제거
            if not x:
                continue
            if re.match(r"^\d+\s*[.．]\s*\S", x) or "품 종 명" in x or "작물명" in x:
                break                                    # 다음 절이 시작됐다
            body.append(x)
        if body:
            return " ".join(body)[:150]
    return ""


def region_temps(region: str, crop: dict) -> list[dict]:
    """적응지역 문장에서 온도 조건을 뽑는다.

        "1월 최저 평균기온 -8℃ 이상 지역(산간 고령지 제외)"

    작물이 아니라 **품종 단위**의 재배 적지 기준이라 과수 동해 한계온도표보다 세밀하다.
    담아만 두고 아무 데도 안 쓰던 값이라 표로 꺼낸다.
    """
    out = []
    for m in REGION_TEMP.finditer(region):
        sign = -1 if m.group(3) else 1
        out.append({**crop, "기준월": int(m.group(1)),
                    "지표": m.group(2) + "기온",
                    "값": sign * float(m.group(4)),
                    "부등호": {"이상": ">=", "초과": ">", "이하": "<=", "미만": "<"}
                              .get(m.group(5) or "이상", ">="),
                    "단위": "℃", "원문": region[:140]})
    return out


# ---------- 결과 ----------

def dump(path: Path, data: list[dict]) -> None:
    if not data:
        return
    keys = list(dict.fromkeys(k for d in data for k in d))
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(data)


def write_report(rows, stages, days, kinds, failed, regions=()) -> None:
    out = ["# 품종 생육시기 추출 결과", "",
           f"품종 {len(rows):,}건 · 시기 {len(stages):,}행 · 일수 {len(days):,}행",
           f"판독 실패 {len(failed)}건", ""]

    out += ["## 형식별", ""]
    for k, n in Counter(kinds.values()).most_common():
        out.append(f"- {k} : {n:,}건")

    out += ["", "## 숙기 확보", ""]
    got = [r for r in rows if r["숙기"]]
    out.append(f"- 숙기를 찾은 품종 : **{len(got):,} / {len(rows):,}** "
               f"({len(got)/max(1,len(rows))*100:.0f}%)")
    for k, n in Counter(r["숙기출처"] for r in got).most_common():
        out.append(f"  - {k} : {n:,}건")
    out += ["", "| 숙기 | 품종 수 |", "|---|---|"]
    for k, n in Counter(r["숙기"] for r in got).most_common():
        out.append(f"| {k} | {n:,} |")

    out += ["", "## 시기 항목별", "", "| 항목 | 행 | 품종 수 | 신뢰도 표/머리/문장 |", "|---|---|---|---|"]
    for name, n in Counter(s["항목"] for s in stages).most_common():
        sub = [s for s in stages if s["항목"] == name]
        c = Counter(s["신뢰도"] for s in sub)
        out.append(f"| {name} | {n:,} | {len({s['cntntsNo'] for s in sub})} | "
                   f"{c['표']}/{c['머리블록']}/{c['문장']} |")

    out += ["", "## 작물별 확보율 (품종 20건 이상)", "",
            "| 작물 | 품종 | 숙기 | 시기 | 숙기% | 시기% |", "|---|---|---|---|---|---|"]
    bycrop = defaultdict(list)
    for r in rows:
        bycrop[r["작물명"]].append(r)
    have_stage = {s["cntntsNo"] for s in stages}
    for crop, sub in sorted(bycrop.items(), key=lambda kv: -len(kv[1])):
        if len(sub) < 20:
            continue
        mk = sum(1 for r in sub if r["숙기"])
        st = sum(1 for r in sub if r["cntntsNo"] in have_stage)
        out.append(f"| {crop} | {len(sub)} | {mk} | {st} | "
                   f"{mk/len(sub)*100:.0f}% | {st/len(sub)*100:.0f}% |")

    out += ["", "## 숙기 × 출수기 (논벼)", "",
            "숙기 3단계로 접어도 되는지 보는 표입니다. 겹치면 나누는 뜻이 없습니다.", ""]
    rice = {r["cntntsNo"]: r for r in rows if r["작물명"] == "논벼"}
    buckets = defaultdict(list)
    for s in stages:
        if s["항목"] == "출수기" and s["cntntsNo"] in rice:
            mk = rice[s["cntntsNo"]]["숙기"]
            if mk:
                buckets[mk].append(s["월"] * 100 + s["일"])
    if buckets:
        out += ["| 숙기 | 품종 수 | 가장 이른 | 중앙 | 가장 늦은 |", "|---|---|---|---|---|"]
        for mk in ("극조생", "조생", "중생", "중만생", "만생"):
            v = sorted(buckets.get(mk, []))
            if not v:
                continue
            fmt = lambda x: f"{x//100}.{x%100}"
            out.append(f"| {mk} | {len(v)} | {fmt(v[0])} | {fmt(v[len(v)//2])} | {fmt(v[-1])} |")
    else:
        out.append("논벼 출수기를 못 찾았습니다.")

    out += ["", "## 적응지역 온도 조건", "",
            f"품종 단위 재배 적지 기준입니다. **{len(regions):,}행 · "
            f"작물 {len({r['작물명'] for r in regions})}종**", ""]
    if regions:
        out += ["| 작물 | 품종 | 조건 |", "|---|---|---|"]
        for r in list(regions)[:20]:
            out.append(f"| {r['작물명'][:14]} | {r['품종명'][:16]} | "
                       f"{r['기준월']}월 {r['지표']} {r['부등호']} {r['값']}℃ |")

    out += ["", "## 일수 항목", ""]
    for k, n in Counter(d["항목"] for d in days).most_common(10):
        out.append(f"- {k} : {n:,}행")

    out += ["", "## 시기 표본 (앞 30)", "",
            "| 작물 | 품종 | 항목 | 값 | 신뢰도 | 원문 |", "|---|---|---|---|---|---|"]
    for s in stages[:30]:
        out.append(f"| {s['작물명'][:10]} | {s['품종명'][:14]} | {s['항목']} | "
                   f"{s['월']}.{s['일']} | {s['신뢰도']} | {s['원문'][:40]} |")

    if failed:
        out += ["", f"## 판독 실패 {len(failed)}건", ""] + [f"- {x}" for x in failed[:30]]

    (OUT / "생육시기_요약.md").write_text("\n".join(out), encoding="utf-8")


LOG: list[str] = []


def say(text: str) -> None:
    """화면과 로그 파일에 같이 남긴다. 오래 걸릴 때 어디쯤인지 보이라고."""
    print(text, flush=True)
    LOG.append(text)
    try:
        (OUT / "생육시기_진행로그.txt").write_text("\n".join(LOG), encoding="utf-8")
    except Exception:
        pass


def main() -> None:
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    only = None
    if "--group" in sys.argv:
        only = [g.strip() for g in sys.argv[sys.argv.index("--group") + 1].split(",")]

    listing = OUT / "품종목록.csv"
    if not listing.exists():
        sys.exit(f"{listing} 이 없습니다. 먼저 variety.py 를 돌려주세요.")
    rows = list(csv.DictReader(open(listing, encoding="utf-8-sig")))
    if only:
        rows = [r for r in rows if r["분류명"] in only]
    if limit:
        rows = rows[:limit]
    say(f"[1/3] 품종 {len(rows):,}건을 읽습니다")

    stages, days, kinds, failed = [], [], {}, []
    regions = []
    for i, r in enumerate(rows, 1):
        crop = {"분류명": r["분류명"], "작물명": r["작물명"], "세부작물": r.get("세부작물", ""),
                "cntntsNo": r["cntntsNo"], "품종명": r["cntntsSj"],
                "육성년도": r.get("unbrngYear", "")}
        text, grids = "", []
        if r.get("첨부"):
            p = OUT / r["첨부"]
            if p.exists():
                try:
                    text, grids, kind = load(p)
                    kinds[r["cntntsNo"]] = kind
                except Exception as err:
                    failed.append(f"{r['cntntsSj']}: {err}")
        lines = text.splitlines()

        r["숙기"], r["숙기출처"], r["숙기원문"] = maturity_of(text, r)
        r["적응지역"] = region_of(lines)
        regions += region_temps(r["적응지역"], crop)

        found = from_grid(grids, crop) if grids else []
        if not found:
            found = from_flat(text, crop)
        # 같은 항목이 여러 번 나오면 가장 믿을 만한 것 하나만 남긴다
        best = {}
        rank = {"표": 3, "머리블록": 2, "문장": 1}
        for s in found:
            k = s["항목"]
            if k not in best or rank[s["신뢰도"]] > rank[best[k]["신뢰도"]]:
                best[k] = s
        stages += list(best.values())

        for name, n, src in days_of(text):
            days.append({**crop, "항목": name, "일수": n, "원문": src})

        if i % 50 == 0 or i == len(rows):
            say(f"  [{i}/{len(rows)}] 시기 {len(stages):,} · 일수 {len(days):,}")

    say("\n[2/3] 표로 만듭니다")
    dump(OUT / "생육시기.csv", stages)
    dump(OUT / "생육일수.csv", days)
    dump(OUT / "적응지역_온도.csv", regions)
    dump(OUT / "품종_숙기.csv",
         [{"분류명": r["분류명"], "작물명": r["작물명"], "cntntsNo": r["cntntsNo"],
           "품종명": r["cntntsSj"], "육성년도": r.get("unbrngYear", ""),
           "숙기": r["숙기"], "숙기출처": r["숙기출처"],
           "숙기원문": r.get("숙기원문", ""), "적응지역": r["적응지역"],
           "주요특성": (r.get("mainChartrInfo") or "")[:200]} for r in rows])

    say("[3/3] 요약을 씁니다")
    write_report(rows, stages, days, kinds, failed, regions)

    if SLOW_PDF:
        say(f"  자리 맞춰 읽기가 느려 보통 방식으로 바꾼 PDF {len(SLOW_PDF)}건")
        (OUT / "느린PDF.txt").write_text("\n".join(SLOW_PDF), encoding="utf-8")
    say(f"\n끝났습니다. 결과: {OUT}")
    print("  생육시기_요약.md 를 저에게 보여주시면 됩니다")
    if failed:
        print(f"  ! 판독 실패 {len(failed)}건")


if __name__ == "__main__":
    main()
