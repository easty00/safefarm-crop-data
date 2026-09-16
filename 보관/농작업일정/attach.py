# 농작업일정 첨부 170개를 글자로 바꾸고, 표를 격자 그대로 뜯어내는 스크립트입니다.
# 자세한 사용법은 같은 폴더의 "첨부추출_사용법.md" 를 읽어주세요.
#
# 새로 내려받는 것은 없습니다. 이미 받아둔 결과/첨부/ 를 읽기만 합니다.
#
# 이 첨부에는 API HTML 에 없는 것이 들어 있습니다. 고추 한 건만 봐도 이렇습니다.
#
#   생육온도  발아적온 25~32℃ / 모 기르기 적온 22~30℃ / 개화적온 18~23℃
#            생육적온 20~30℃ / 과비대적온 18~23℃ / 저장적온 4℃
#   모 기르기 기간 80~90일, 개화·착과 가능온도 15.5~28.5℃
#
# 로드맵 §7 에 "고추 과비대 적온 값을 못 구했다"고 적혀 있던 그 값입니다.
#
# hwpx 는 표가 XML 로 들어 있어 행·열을 그대로 살릴 수 있습니다. 글자로만 풀면
# 칸이 한 줄씩 흩어져 어느 값이 어느 항목인지 알 수 없게 됩니다. 그래서 표는
# 격자로 따로 뜯고, 본문은 본문대로 전문을 남깁니다.

import csv
import re
import struct
import sys
import zipfile
import zlib
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
OUT = HERE / "결과"
FILES = OUT / "첨부"
TEXTS = OUT / "본문"

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

# 온도 항목 이름. 170건을 훑어 실제로 나온 것만 모았다.
# 띄어쓰기가 제각각이라("모 기르기 적온"·"모기르기적온") 공백을 지우고 맞춘다
TEMP_WORDS = ("적온", "한계온도", "생육온도", "온도관리", "가능온도", "발아온도",
              "저장온도", "최적온도", "한계", "지온",
              # ⚠ 아래 넷이 빠져 있어서 '발아 최저온도 10℃' 같은 값이 통째로 걸러졌다.
              # 적온이 아니라 **최저온도**가 base_temp 후보이므로 가장 중요한 이름이다
              "최저온도", "최고온도", "최저기온", "최고기온")
# 위 낱말이 들어가도 온도 항목이 아닌 것들. "난방기 등을 가동하여 적온 유지" 같은 문장
TEMP_STOP = ("가동", "유지하", "관리하", "맞추", "유의", "주의")

# 값에서 온도를 읽어낸다. "25~32℃", "15.5℃~28.5℃", "4℃", "30℃ 이상"
RANGE_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*℃?\s*[~∼－—-]\s*(-?\d+(?:\.\d+)?)\s*℃")
ONE_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*℃")

# 일수: "모 기르기 기간 : 80~90일", "정식 후 45일"
DAY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:[~∼－—-]\s*(\d+(?:\.\d+)?)\s*)?일")

# 본문 절 제목
H1_RE = re.compile(r"^\s*[■□▣]\s*(\S.{0,30})$")
H2_RE = re.compile(r"^\s*[❍○●◦]\s*(\S.*)$")
H3_RE = re.compile(r"^\s*[-*※·]\s*(\S.*)$")


def safe(name: str) -> str:
    return "".join("_" if ch in '\\/:*?"<>|' else ch for ch in name).strip()[:120] or "이름없음"


def clean(text: str) -> str:
    return "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)


def nospace(text: str) -> str:
    return re.sub(r"\s+", "", text)


# ---------- 문서 읽기 ----------

def cell_text(node: ET.Element) -> str:
    """표 한 칸 안의 글자를 모은다. 칸 안에서 줄이 나뉘면 공백으로 잇는다."""
    parts = []
    for t in node.iter(HP + "t"):
        if t.text:
            parts.append(t.text)
    return " ".join(" ".join(parts).split())


def hwpx_tables(path: Path) -> list[list[list[str]]]:
    """hwpx 안의 표를 행·열 격자 그대로 꺼낸다.

    글자로만 풀면 칸이 한 줄씩 흩어져서 "발아적온" 과 "25~32℃" 가 서로 다른 줄이 된다.
    어느 값이 어느 항목인지 알려면 격자가 있어야 한다.
    병합된 칸은 차지하는 자리를 같은 값으로 채운다. 그래야 항목 이름이 아래로 이어진다.
    """
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
                    r0 = int(addr.get("rowAddr") or 0)
                    c0 = int(addr.get("colAddr") or 0)
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
            # 문단과 표 칸의 경계를 남긴다. 지우면 숫자가 한 덩어리로 붙는다
            raw = re.sub(r"</hp:tc>", " | ", raw)
            raw = re.sub(r"</(hp:p|hp:tr)>", "\n", raw)
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


def read_pdf(path: Path) -> str:
    """PDF 를 칸 자리를 살려 읽는다.

    PDF 에는 표라는 구조가 아예 없다. hwpx 처럼 '여기부터 표' 라는 표시가 없고,
    글자마다 '이 좌표에 이 글자를 그려라' 만 들어 있다. 그래서 XML 도구로는 못 연다.

    대신 pypdf 의 layout 방식으로 읽으면 좌표를 공백으로 바꿔줘서 칸이 세로로 맞는다.

        재배유형        지대별     파종시기      수확시기
        콩 단작         중북부     6월 상순     10월 상·중순

    이러면 공백 두 칸 이상을 칸 경계로 보고 다시 쪼갤 수 있다.
    """
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return "".join(f"\n===== p.{i} =====\n" + (pg.extract_text(extraction_mode="layout") or "")
                   for i, pg in enumerate(reader.pages, 1))


def pdf_tables(text: str) -> list[list[list[str]]]:
    """자리가 맞춰진 PDF 글자에서 표처럼 생긴 덩어리를 찾아낸다.

    공백 두 칸 이상을 칸 경계로 본다. 다만 layout 방식은 문장 안에도 공백을 넣기 때문에
    ("사양토,     양토,     식양토가") 그냥 쪼개면 문장이 전부 표가 된다. 그래서 세 가지를 건다.

      ① 글머리표(◯ - * ※)로 시작하는 줄은 문장이다
      ② 칸이 3개 이상이어야 한다
      ③ 같은 칸 수인 줄이 2줄 이상 이어져야 표다
    """
    blocks, cur = [], []

    def flush() -> None:
        if len(cur) >= 2:
            width = max(len(r) for r in cur)
            blocks.append([r + [""] * (width - len(r)) for r in cur])
        cur.clear()

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip()[0] in "◯○❍●-*※□■=":
            flush()
            continue
        cells = [c.strip() for c in re.split(r"\s{2,}", line.strip()) if c.strip()]
        # 칸이 너무 길면 문장을 잘못 쪼갠 것이다
        if len(cells) >= 3 and sum(len(c) for c in cells) / len(cells) <= 22:
            if cur and abs(len(cells) - len(cur[-1])) > 1:
                flush()
            cur.append(cells)
        else:
            flush()
    flush()
    return blocks


def extract(path: Path) -> tuple[str, list]:
    """확장자가 아니라 앞 4바이트로 형식을 판정한다. 표 격자는 hwpx 에서만 나온다."""
    head = path.read_bytes()[:4]
    if head[:2] == b"PK":
        return read_hwpx(path), hwpx_tables(path)
    if head[:4] == b"\xd0\xcf\x11\xe0":
        return read_hwp(path), []
    if head[:4] == b"%PDF":
        text = read_pdf(path)
        return text, pdf_tables(text)
    if head[:4] == b"HWP ":
        raise RuntimeError("한글 3.0 형식 — 품종정보 스크립트의 추출기를 가져오세요")
    raise RuntimeError(f"모르는 형식 (앞 4바이트 {head!r})")


# ---------- 값 읽어내기 ----------

def temps_of(value: str) -> tuple[str, str, str]:
    """온도 값에서 최저·최고를 읽는다. 범위가 아니면 한쪽만 채운다."""
    # ⚠ 괄호 안에 적산온도가 딸려오는 표기가 있다.
    #     "발아적온 : 20℃(발아 적산온도 : 140℃~150℃)"
    # 그대로 읽으면 발아적온이 140~150℃ 가 된다. 실제로 보리 두 건이 그랬다.
    # 적산온도는 누적값이라 단위가 같아도 자리가 다르다. 괄호 앞만 쓴다.
    if "적산" in value:
        cut = re.split(r"[(（]", value, 1)[0]
        if ONE_RE.search(cut):
            value = cut

    m = RANGE_RE.search(value)
    if m:
        lo, hi = m.group(1), m.group(2)
        # "-7∼-9℃" 처럼 낮은 쪽을 뒤에 쓰는 표기가 있다. 음수에서만 생긴다
        if float(lo) > float(hi):
            lo, hi = hi, lo
        return lo, hi, "범위"
    hits = ONE_RE.findall(value)
    if not hits:
        return "", "", ""
    if "이상" in value:
        return hits[0], "", "이상"
    if "이하" in value:
        return "", hits[0], "이하"
    return hits[0], hits[0], "단일"


def looks_temp(label: str) -> bool:
    if any(s in label for s in TEMP_STOP):
        return False
    return any(w in label for w in TEMP_WORDS)


def walk_grid(grid: list[list[str]]) -> list[tuple[str, str]]:
    """한 행에서 (항목 이름, 값) 쌍을 뽑는다.

    ⚠ 한 행에 쌍이 **두 개씩** 들어 있는 표가 있다. 실제 고추 표가 이렇다.

        생육온도 ¦ 발아적온 ¦ 25~32℃ ¦ 모 기르기 적온 ¦ 22~30℃

    마지막 칸만 값으로 보면 발아적온 25~32℃ 를 통째로 잃는다.
    처음에 그렇게 만들었다가 한 작물에서 온도 6개 중 3개를 놓쳤다.

    그래서 이렇게 센다. 병합으로 반복된 칸을 하나로 줄인 뒤,
    칸 수가 홀수면 맨 앞이 행 이름(생육온도)이고 나머지를 둘씩 짝짓는다.
    짝수면 앞에서부터 그냥 둘씩 짝짓는다.
    """
    out = []
    for row in grid:
        uniq = []
        for c in (x.strip() for x in row):
            if c and (not uniq or uniq[-1] != c):
                uniq.append(c)
        if len(uniq) < 2:
            continue
        head, rest = ("", uniq) if len(uniq) % 2 == 0 else (uniq[0], uniq[1:])
        for i in range(0, len(rest) - 1, 2):
            label = f"{head} > {rest[i]}" if head else rest[i]
            out.append((label, rest[i + 1]))
    return out


def grid_rows(grid: list[list[str]]) -> list[tuple[str, str]]:
    """머리행이 있는 표를 (머리, 값) 으로 편다.

    '작형별 출하시기' 처럼 열이 여럿인 표는 이름-값 짝으로는 제대로 안 읽힌다.

        작형   ¦ 씨뿌림      ¦ 아주심기   ¦ 수확기     ¦ 성출하기
        반촉성 ¦ 11월 하순~  ¦ 2월 중순~ ¦ 3월 상순~ ¦ 7월 상순~

    어느 쪽이 맞는 해석인지 표마다 다르므로 **두 가지로 다 뽑아 둔다.**
    격자 원본(첨부_표.csv)도 그대로 남으니 잃는 것은 없다.
    """
    if len(grid) < 2:
        return []
    header = [c.strip() for c in grid[0]]
    out = []
    for r, row in enumerate(grid[1:], 1):
        seen = set()
        for c, value in enumerate(row):
            value = value.strip()
            if not value:
                continue
            key = header[c] if c < len(header) and header[c] else f"열{c}"
            if (key, value) in seen:      # 병합으로 같은 값이 반복된 것
                continue
            seen.add((key, value))
            out.append((f"{r}행 {key}", value))
    return out


def parse_sections(text: str, crop: dict) -> list[dict]:
    """■ / ❍ / - 계층을 살려 본문 절을 담는다. 버리는 줄 없이 전부 담는다."""
    out, h1, h2 = [], "", ""
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or set(line.strip()) <= {"|", " "}:
            continue
        m1 = H1_RE.match(line)
        if m1:
            h1, h2 = " ".join(m1.group(1).split()), ""
            continue
        m2 = H2_RE.match(line)
        if m2:
            h2 = " ".join(m2.group(1).split())
            out.append({**crop, "절": h1, "항목": h2, "깊이": 2, "내용": ""})
            continue
        m3 = H3_RE.match(line)
        depth = 3 if m3 else 4
        body = " ".join((m3.group(1) if m3 else line).split())
        out.append({**crop, "절": h1, "항목": h2, "깊이": depth, "내용": body})
    return out


def parse_temps(pairs: list[tuple[str, str]], rowpairs: list[tuple[str, str]],
                text: str, crop: dict) -> list[dict]:
    """표와 본문 양쪽에서 온도를 뽑는다. 원문 문장을 반드시 같이 남긴다.

    표는 두 가지로 읽는다. 짝 보기(이름=값)만 보면 **머리행이 있는 표를 통째로 놓친다.**
    실제로 들깨의 `발아 최저온도 10℃` · `생육 최저온도 5℃` 가 그렇게 빠졌는데,
    이건 base_temp 후보라 놓치면 안 되는 값이었다.
    """
    out = []
    seen = set()

    def add(label: str, value: str, source: str) -> None:
        short = label.split(" > ")[-1]
        short = re.sub(r"^\d+행\s*", "", short)      # 행 보기는 '3행 생육 최저온도' 꼴이다
        if not looks_temp(nospace(short)) and not looks_temp(nospace(label)):
            return
        if "℃" not in value:
            return
        # ⚠ 값 자리에 **머리글이 들어온 경우**가 있다. 시금치 표가 그랬다.
        #     항목 '최적온도(℃)'  값 '최고온도(℃)'   → 숫자가 없는데 ℃ 만 있다
        # 숫자가 하나도 없으면 값이 아니라 이름이다
        if not re.search(r"\d", value):
            return
        lo, hi, kind = temps_of(value)
        key = (nospace(short), lo, hi)
        if key in seen:                              # 두 보기에 같은 값이 겹쳐 나온다
            return
        seen.add(key)
        out.append({**crop, "출처": source, "항목": nospace(short), "항목전체": label,
                    "최저": lo, "최고": hi, "형태": kind, "원문": value[:120]})

    for label, value in pairs:
        add(label, value, "표")
    for label, value in rowpairs:
        add(label, value, "표행")

    for raw in text.splitlines():
        line = " ".join(raw.split())
        if "℃" not in line:
            continue
        # "❍ 온도관리 : 낮 22~30℃ / 밤 15℃ 이상" 처럼 이름과 값이 한 줄에 있는 경우
        m = re.match(r"^[■❍○●◦\-*※·\s]*([^:：|]{1,20})[:：](.+)$", line)
        label = nospace(m.group(1)) if m else ""
        value = (m.group(2) if m else line).strip()
        if not looks_temp(label):
            continue
        lo, hi, kind = temps_of(value)
        if not lo and not hi:
            continue
        out.append({**crop, "출처": "본문", "항목": label, "항목전체": label,
                    "최저": lo, "최고": hi, "형태": kind, "원문": line[:120]})
    return out


# 일수를 찾을 때 쓸 낱말. '후' 는 넣지 않는다 — 아래 이유
DAY_WORDS = ("기간", "일수", "소요", "동안", "모 기르기", "육묘", "정식 후", "아주심기 후")
# 이 말이 든 줄의 일수는 재배 기간이 아니라 **작업 간격**이다
DAY_STOP = ("제초제", "방제", "살포", "처리", "약제", "소독", "침지", "물떼기",
            "물대기", "담수", "배수", "경엽", "토양처리", "웃거름")


def parse_days(text: str, crop: dict) -> list[dict]:
    """생육·육묘 일수를 뽑는다. 적산온도 구간을 잡을 때 쓸 값이다.

    ⚠ 처음엔 '후' 를 찾는 낱말에 넣었더니 **벼 29건 중 27건이 제초제 살포 간격**이었다.

        "2회 뿌림(기본방제 + 이앙 후 10~15일경, 토양처리 제초제)"   ← 재배 기간이 아니다
        "완전물떼기 : 이삭팬 후 30~35일 전후"                    ← 물 관리 일정

    쓸 수 있는 건 '모 기르기 일수 70~80일' 같은 것뿐이다. 그래서 '후' 를 빼고,
    방제·물관리 낱말이 든 줄은 통째로 거른다.
    """
    out = []
    section, item = "", ""
    for raw in text.splitlines():
        line = " ".join(raw.split())
        # ⚠ 절과 항목을 같이 담는다. 이게 없으면 "무엇의 일수인지" 를 알 수 없어
        # 파일끼리 값을 맞대볼 수가 없다. 검수의 파일 간 대조가 이 칸을 쓴다
        m1 = H1_RE.match(raw.rstrip())
        if m1:
            section, item = " ".join(m1.group(1).split()), ""
            continue
        m2 = H2_RE.match(raw.rstrip())
        if m2:
            item = " ".join(m2.group(1).split())[:40]
        if "일" not in line:
            continue
        if any(w in line for w in DAY_STOP):
            continue
        if not any(w in line for w in DAY_WORDS):
            continue
        for m in DAY_RE.finditer(line):
            lo, hi = m.group(1), m.group(2) or m.group(1)
            if float(hi) > 400:          # 날짜·연도 등이 걸린 것
                continue
            # 무엇의 일수인지. 항목이 있으면 항목, 없으면 절 이름을 쓴다
            name = item or section
            out.append({**crop, "절": section, "항목": name[:40],
                        "최소일": lo, "최대일": hi, "원문": line[:140]})
            break                        # 한 줄에서 하나만. 나머지는 원문에 남는다
    return out


# ---------- 결과 ----------

def dump(path: Path, data: list[dict]) -> None:
    if not data:
        return
    keys = list(dict.fromkeys(k for d in data for k in d))
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(data)


def write_report(files, texts, cells, pairs, temps, days, sections, failed) -> None:
    lens = sorted(len(t) for t in texts.values())
    out = ["# 농작업일정 첨부 추출 결과", "",
           f"첨부 {len(files)}개 · 판독 {len(texts)}개 · 실패 {len(failed)}개",
           f"본문 {sum(lens):,}자 (중앙값 {lens[len(lens)//2]:,} · 최소 {lens[0]:,} · 최대 {lens[-1]:,})",
           f"표 칸 {len(cells):,} · 항목-값 쌍 {len(pairs):,} · "
           f"온도 {len(temps):,} · 일수 {len(days):,} · 절 {len(sections):,}", ""]

    out += ["## 온도 항목별 건수", "",
            "이름이 띄어쓰기만 다른 것은 공백을 지워 묶었습니다.", "",
            "| 항목 | 건수 | 작물 수 | 최저 중앙 | 최고 중앙 |", "|---|---|---|---|---|"]
    per = defaultdict(list)
    for t in temps:
        per[t["항목"]].append(t)
    for name, rows_ in sorted(per.items(), key=lambda kv: -len(kv[1]))[:30]:
        los = sorted(float(x["최저"]) for x in rows_ if x["최저"])
        his = sorted(float(x["최고"]) for x in rows_ if x["최고"])
        out.append(f"| {name} | {len(rows_)} | {len({x['작물명'] for x in rows_})} | "
                   f"{los[len(los)//2] if los else '—'} | {his[len(his)//2] if his else '—'} |")

    out += ["", "## 분류별", "", "| 분류 | 첨부 | 온도 | 일수 | 표칸 |", "|---|---|---|---|---|"]
    for g in sorted({f.parent.name for f in files}):
        n = sum(1 for f in files if f.parent.name == g)
        out.append(f"| {g} | {n} | {sum(1 for t in temps if t['분류명']==g)} | "
                   f"{sum(1 for d in days if d['분류명']==g)} | "
                   f"{sum(1 for c in cells if c['분류명']==g)} |")

    out += ["", "## 온도를 하나도 못 뽑은 첨부", ""]
    # 파일 이름으로 맞댄다. 작물명은 작물목록.csv 쪽 이름이라 파일명과 다르다
    have = {t["파일"] for t in temps}
    miss = sorted(f.name for f in files if f.name not in have)
    out.append(f"**{len(miss)}개 / {len(files)}개**")
    if miss:
        out += ["", "| 첨부 | 표 있나 | 글자 수 |", "|---|---|---|"]
        cell_files = {c["파일"] for c in cells}
        for name in miss[:60]:
            f = next(x for x in files if x.name == name)
            out.append(f"| {name[:46]} | {'있음' if name in cell_files else '없음'} | "
                       f"{len(texts.get(f, '')):,} |")
        if len(miss) > 60:
            out.append(f"| … 외 {len(miss)-60}개 | | |")

    out += ["", "## 온도가 나온 첨부", "",
            f"**{len(have)}개 / {len(files)}개** · 온도 {len(temps)}건"]

    out += ["", "## 자주 나오는 표 항목 (상위 40)", "",
            "표에서 뽑은 '항목 > 값' 의 항목 쪽입니다. 무엇을 더 캘 수 있는지 보여줍니다.", ""]
    for name, n in Counter(p["항목"] for p in pairs).most_common(40):
        out.append(f"- {n:>4}회  {name}")

    out += ["", "## 온도 표본 (앞 40)", "", "| 작물 | 항목 | 최저 | 최고 | 원문 |", "|---|---|---|---|---|"]
    for t in temps[:40]:
        out.append(f"| {t['작물명'][:18]} | {t['항목']} | {t['최저']} | {t['최고']} | {t['원문'][:40]} |")

    if failed:
        out += ["", f"## 실패 {len(failed)}건", ""] + [f"- {x}" for x in failed]

    (OUT / "첨부_요약.md").write_text("\n".join(out), encoding="utf-8")


def main() -> None:
    only = None
    if "--group" in sys.argv:
        only = [g.strip() for g in sys.argv[sys.argv.index("--group") + 1].split(",")]
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    if not FILES.exists():
        sys.exit(f"{FILES} 가 없습니다. 먼저 farmwork.py 로 첨부를 받아주세요.")

    # 작물목록.csv 로 분류·작물명·cntntsNo 를 잇는다
    link = {}
    listing = OUT / "작물목록.csv"
    if listing.exists():
        for r in csv.DictReader(open(listing, encoding="utf-8-sig")):
            if r.get("첨부파일명"):
                link[r["첨부파일명"].strip()] = r
    print(f"[1/4] 작물목록에서 {len(link)}건을 이어붙일 준비를 했습니다")

    files = sorted(p for p in FILES.rglob("*.*") if p.is_file())
    if only:
        files = [f for f in files if f.parent.name in only]
    if limit:
        files = files[:limit]
    print(f"[2/4] 첨부 {len(files)}개를 읽습니다")

    TEXTS.mkdir(parents=True, exist_ok=True)
    texts, cells, pairs, rowviews = {}, [], [], []
    temps, days, sections, failed = [], [], [], []

    for i, f in enumerate(files, 1):
        row = link.get(f.name, {})
        crop = {"분류명": row.get("분류명") or f.parent.name,
                "작물명": row.get("작물명") or f.stem,
                "cntntsNo": row.get("cntntsNo", ""),
                "파일": f.name}
        try:
            text, grids = extract(f)
        except Exception as err:
            failed.append(f"{f.name}: {err}")
            print(f"  [{i}/{len(files)}] 실패 {f.name[:40]}")
            continue
        texts[f] = text

        dest = TEXTS / safe(f.parent.name) / (safe(f.stem) + ".txt")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")

        mine, mine_row = [], []        # 이 파일에서 나온 항목-값 쌍만 따로 모은다
        for tno, grid in enumerate(grids, 1):
            for rno, rowvals in enumerate(grid):
                for cno, v in enumerate(rowvals):
                    if v:
                        cells.append({**crop, "표번호": tno, "행": rno, "열": cno, "값": v})
            for label, value in walk_grid(grid):
                pairs.append({**crop, "표번호": tno, "보기": "짝", "항목": label, "값": value})
                mine.append((label, value))
            for label, value in grid_rows(grid):
                rowviews.append({**crop, "표번호": tno, "보기": "행", "항목": label, "값": value})
                mine_row.append((label, value))

        temps += parse_temps(mine, mine_row, text, crop)
        days += parse_days(text, crop)
        sections += parse_sections(text, crop)

        if i % 20 == 0 or i == len(files):
            print(f"  [{i}/{len(files)}] 온도 {len(temps)} · 일수 {len(days)} · 표칸 {len(cells)}")

    print("\n[3/4] 표로 만듭니다")
    dump(OUT / "첨부_표.csv", cells)
    dump(OUT / "첨부_항목.csv", pairs)
    dump(OUT / "첨부_표행.csv", rowviews)
    dump(OUT / "첨부_온도.csv", temps)
    dump(OUT / "첨부_일수.csv", days)
    dump(OUT / "첨부_절.csv", sections)

    print("[4/4] 요약을 씁니다")
    write_report(files, texts, cells, pairs, temps, days, sections, failed)

    print(f"\n끝났습니다. 결과: {OUT}")
    print("  첨부_요약.md 를 저에게 보여주시면 됩니다")
    if failed:
        print(f"  ! 실패 {len(failed)}건")


if __name__ == "__main__":
    main()
