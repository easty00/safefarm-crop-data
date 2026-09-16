# 이미 받아둔 자료 셋에서 재해 판정 규칙을 뽑아 한 표로 모으는 스크립트입니다.
# 자세한 사용법은 같은 폴더의 "사용법.md" 를 읽어주세요.
#
# 새로 내려받는 것은 없습니다. 인터넷을 쓰지 않고 .env 도 필요 없습니다.
#
#   재해예방정보/결과/파일/     저온해·고온해 기준표, 과수 동해 한계온도, 벼 한계온도, 감수율표
#   병해충발생정보/결과/*.csv    경보 등급 1,339행 + 발병 조건 온도 196개
#   농작업일정/결과/첨부_표.csv   작물별 기상재해·생리장해 대책
#
# 가장 값진 것은 저온해 보고에 실린 이 표입니다. 42개 문서에 들어 있습니다.
#
#   작물종류 ¦ 품종            ¦ 위험발령 생육단계 ¦ 위험발령 기준(최저기온)        ¦ 재해종류
#   사과    ¦ 조생종 중생종 (만생종) ¦ 발아기       ¦ ≤-2.8℃ (주의) ≤-5.0℃ (위험) ¦ 저온해
#
# 작물·숙기·생육단계·등급별 기준값이 이미 다 갈려 있습니다. 옮기기만 하면 됩니다.

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
ROOT = HERE.parent
OUT = HERE / "결과"

DISASTER = ROOT / "재해예방정보" / "결과" / "파일"
PEST = ROOT / "병해충발생정보" / "결과"
FARM = ROOT / "농작업일정" / "결과"

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

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

def rule_crop_stage(grid, src) -> list[dict]:
    """작물종류 · 생육단계 · 기준온도 표. 저온해·고온해 보고의 핵심이다."""
    head = [nospace(c.replace("\n", " ")) for c in grid[0]]
    if not head or not head[0].startswith("작물종류"):
        return []
    # 열이 어디에 있는지 머리글로 찾는다. 표마다 열 수가 다르다(3열·5열)
    def find(*words):
        for i, h in enumerate(head):
            if any(w in h for w in words):
                return i
        return -1
    i_var = find("품종")
    i_stage = find("생육단계", "발령생육단계")
    i_base = find("기준온도", "발령기준", "기준")
    i_kind = find("재해종류", "재해")
    if i_stage < 0 or i_base < 0:
        return []
    default = "최저기온" if "최저기온" in head[i_base] else "최고기온"
    out = []
    for row in grid[1:]:
        crop = " ".join(row[0].replace("\n", " ").split())
        if not crop or nospace(crop).startswith("작물종류"):
            continue
        stage = " ".join(row[i_stage].replace("\n", " ").split())
        kind = " ".join(row[i_kind].replace("\n", " ").split()) if i_kind >= 0 else ""
        variety = " ".join(row[i_var].replace("\n", " ").split()) if i_var >= 0 else ""
        for r in parse_threshold(row[i_base], default):
            out.append({**src, "작물": crop, "품종숙기": variety, "생육단계": stage,
                        "재해종류": kind or ("저온해" if default == "최저기온" else "고온해"),
                        **r, "표종류": "작물별 위험발령 기준", "confirmed": "Y"})
    return out


def rule_fruit_winter(grid, src) -> list[dict]:
    """종류 · 연평균기온 · 동해 한계온도 · 재배지역 표 (과수)."""
    head = [nospace(c.replace("\n", " ")) for c in grid[0]]
    if not any("동해한계온도" in h for h in head):
        return []
    i_lim = next(i for i, h in enumerate(head) if "동해한계온도" in h)
    i_avg = next((i for i, h in enumerate(head) if "연평균기온" in h), -1)
    i_reg = next((i for i, h in enumerate(head) if "재배지역" in h), -1)
    out = []
    for row in grid[1:]:
        crop = " ".join(row[0].replace("\n", " ").split())
        if not crop or nospace(crop) in ("종류", ""):
            continue
        cell = " ".join(row[i_lim].replace("\n", " ").split())
        # 이 표는 단위가 머리글(동해 한계온도 (℃))에 있어서 칸에는 숫자만 들어 있다.
        # ℃ 를 찾는 규칙만 쓰면 한 행도 못 읽는다. 실제로 그래서 0행이 나온 적이 있다.
        found = parse_threshold(cell, "최저기온")
        if not found:
            for m in re.finditer(r"(-?\d+(?:\.\d+)?)", cell):
                found.append({"지표": "최저기온", "부등호": "<=", "값": m.group(1),
                              "단위": "℃", "지속일": "", "등급": "",
                              "조건원문": cell[:80]})
        for r in found:
            r["부등호"] = "<="
            note = " / ".join(x for x in (
                " ".join((row[i_avg] if i_avg >= 0 else "").split()),
                " ".join((row[i_reg] if i_reg >= 0 else "").split())) if x)
            out.append({**src, "작물": crop, "품종숙기": "", "생육단계": "휴면기",
                        "재해종류": "동해", **r, "표종류": "과수 동해 한계온도",
                        "비고": note, "confirmed": "Y"})
    return out


def rule_stacked(grid, src) -> list[dict]:
    """한 칸 안에 여러 줄이 든 표. 과채류·엽채류 최저 한계 온도가 이 모양이다.

        작 물 별 ¦ 모기를 때 ¦ 꽃눈생기기전 ¦ 동해온도
        딸기      ¦ 10      ¦ 3~5        ¦ 0
        토마토     ¦ 10      ¦ 5          ¦ -1~-2     ← 세 줄이 한 칸 안에 들어 있다

    칸 안의 줄을 살려 두었으므로 세로로 다시 짝지을 수 있다.
    """
    head = [nospace(c.replace("\n", " ")) for c in grid[0]]
    if not head or head[0] not in ("작물별", "작물"):
        return []
    if not any(("동해온도" in h) or ("냉해온도" in h) or ("한계온도" in h) for h in head):
        return []
    body = grid[1] if len(grid) > 1 else []
    cols = [c.split("\n") for c in body]
    if not cols or len(cols[0]) < 2:
        return []
    n = len(cols[0])
    out = []
    for i in range(n):
        crop = cols[0][i].strip() if i < len(cols[0]) else ""
        crop = nospace(crop)
        if not crop:
            continue
        for c in range(1, len(cols)):
            if i >= len(cols[c]):
                continue
            value = cols[c][i].strip()
            if not value or not re.search(r"-?\d", value):
                continue
            m = re.search(r"(-?\d+(?:\.\d+)?)", value)
            stage = head[c] if c < len(head) else f"열{c}"
            out.append({**src, "작물": crop, "품종숙기": "", "생육단계": stage,
                        "재해종류": "동해" if "동해" in stage else
                                   ("냉해" if "냉해" in stage else "저온해"),
                        "지표": "최저기온", "부등호": "<=", "값": m.group(1), "단위": "℃",
                        "지속일": "", "등급": "", "조건원문": value[:60],
                        "표종류": "작물별 최저 한계온도", "confirmed": "Y"})
    return out


def rule_veg_range(grid, src) -> list[dict]:
    """「채소류의 생육 및 장애온도」 표. **한 표에 다섯 가지 온도**가 다 들어 있다.

        작 물 별 ¦ 최고한량계 ¦ 적온(낮) ¦ 적온(밤) ¦ 최저량계 ¦ 동해온도 ¦ 장애온도
        토마토    ¦ 35       ¦ 25~20   ¦ 13~8    ¦ 5      ¦ -1~-2  ¦ 30℃이상 : 공동과발생
        가지      ¦ 35       ¦ 28~23   ¦ 18~13   ¦ 10     ¦ 0~2    ¦ 35℃이상 : 낙화·낙과

    2023~2026년 **17개 호에 그대로 재수록**된다(GDD_작업인계 §3-2).
    `rule_stacked` 와 같이 한 칸에 작물 여러 개가 줄로 들어 있는 꼴이라
    줄을 살려 세로로 짝지어야 한다.

    ⚠ `최저` 칸은 **재배 한계**이지 base_temp 가 아니다. 상추 국내 8 ↔ 논문 3.5~4.5.
    그래서 전부 재해 판정용으로만 담는다.
    """
    head = [nospace(c.replace("\n", " ")) for c in grid[0]]
    head2 = [nospace(c.replace("\n", " ")) for c in grid[1]] if len(grid) > 1 else []
    if not head or head[0] not in ("작물별", "작물"):
        return []
    if not any("장애온도" in h for h in head):
        return []

    # 열마다 무엇인지. 머리 두 줄을 합쳐 본다
    def role(i: int) -> tuple[str, str, str]:
        a = head[i] if i < len(head) else ""
        b = head2[i] if i < len(head2) else ""
        both = a + b
        if "최고" in both:
            return "고온해", "최고기온", ">="
        if "동해" in both:
            return "동해", "최저기온", "<="
        if "최저" in both:
            return "저온해", "최저기온", "<="
        if "적온" in both:
            return "적온", "", ""         # 적온은 규칙이 아니다. 담지 않는다
        if "장애" in both:
            return "장애", "", ""         # 문장이라 따로 푼다
        return "", "", ""

    body = grid[2] if len(grid) > 2 else []
    out = []
    for row in grid[2:]:
        names = [nospace(x) for x in row[0].split("\n")]
        if not names or not names[0]:
            continue
        for c in range(1, len(row)):
            kind, metric, op = role(c)
            lines = row[c].split("\n")
            for i, crop in enumerate(names):
                if not crop or i >= len(lines):
                    continue
                cell = lines[i].strip()
                if not cell:
                    continue
                if kind in ("고온해", "동해", "저온해"):
                    m = re.search(r"(-?\d+(?:\.\d+)?)", cell)
                    if not m:
                        continue
                    out.append({**src, "작물": crop, "품종숙기": "",
                                "생육단계": head[c].replace("\n", " ") or f"열{c}",
                                "재해종류": kind, "지표": metric, "부등호": op,
                                "값": m.group(1), "단위": "℃", "지속일": "", "등급": "",
                                "조건원문": cell[:60],
                                "표종류": "채소류 생육 및 장애온도", "confirmed": "Y"})
                elif kind == "장애":
                    # "30℃이상 : 공동과발생" 처럼 조건과 증상이 콜론으로 갈린다
                    for part in re.split(r"[,、]|(?<=\))\s+", cell):
                        m = re.match(r"\s*(-?\d+(?:\.\d+)?)\s*℃\s*(이상|이하)\s*[:：]?\s*(.*)",
                                     part.strip())
                        if not m:
                            continue
                        out.append({**src, "작물": crop, "품종숙기": "", "생육단계": "",
                                    "재해종류": "고온해" if m.group(2) == "이상" else "저온해",
                                    "지표": "최고기온" if m.group(2) == "이상" else "최저기온",
                                    "부등호": ">=" if m.group(2) == "이상" else "<=",
                                    "값": m.group(1), "단위": "℃", "지속일": "", "등급": "",
                                    "조건원문": part.strip()[:60],
                                    "비고": m.group(3)[:60],
                                    "표종류": "채소류 장애온도", "confirmed": "Y"})
    return out


def rule_rice_stage(grid, src) -> list[dict]:
    """생육시기 × 최적·최저·최고 온도 표 (벼)."""
    if len(grid) < 3:
        return []
    h0 = [nospace(c.replace("\n", " ")) for c in grid[0]]
    h1 = [nospace(c.replace("\n", " ")) for c in grid[1]]
    if not any("온도" in h for h in h0):
        return []
    if not ({"최적", "최저", "최고"} <= set(h1)):
        return []
    out = []
    for row in grid[2:]:
        stage = " ".join(" ".join(row[:2]).replace("\n", " ").split())
        stage = nospace(stage)
        if not stage:
            continue
        for c, kind in enumerate(h1):
            if kind not in ("최저", "최고"):
                continue
            value = row[c] if c < len(row) else ""
            m = re.search(r"(-?\d+(?:\.\d+)?)", value)
            if not m:
                continue
            out.append({**src, "작물": "벼", "품종숙기": "", "생육단계": stage,
                        "재해종류": "저온해" if kind == "최저" else "고온해",
                        "지표": "최저기온" if kind == "최저" else "최고기온",
                        "부등호": "<=" if kind == "최저" else ">=",
                        "값": m.group(1), "단위": "℃", "지속일": "", "등급": "",
                        "조건원문": " ".join(value.split())[:60],
                        "표종류": "벼 생육시기별 한계온도", "confirmed": "Y"})
    return out


def rule_damage_rate(grid, src) -> list[dict]:
    """피해율 표 가운데 **판정에 쓸 수 있는 것**만 규칙으로 옮긴다.

    감수율·부패율 표는 대부분 "몇 ℃면 경보" 꼴이 아니라 참고표로만 담았다.
    그런데 아래 셋은 왼쪽 칸이 곧 판정 기준이라 규칙이 된다.

      최저기온 × 품종 × 수체부위 동해 피해율   → 단감 품종별 내한성. 품종 단위다
      우박 크기 × 부위별 피해율                → 우박 지름이 기준
      토양습도 × 일소 피해율                   → 습도가 기준
    """
    head = [nospace(c.replace("\n", " ")) for c in grid[0]]
    head2 = [nospace(c.replace("\n", " ")) for c in grid[1]] if len(grid) > 1 else []
    flat = " ".join(head + head2)

    if "동해피해율" in flat and "최저기온" in flat:
        kind, metric, unit = "동해", "최저기온", "℃"
    elif "우박피해율" in flat:
        kind, metric, unit = "우박", "우박크기", "mm"
    elif "일소피해율" in flat:
        kind, metric, unit = "일소", "토양습도", "%"
    else:
        return []

    # 기준값이 든 열을 머리글로 찾는다. 첫 칸이 지역명인 표가 있어서 0 으로 두면 놓친다
    # (단감 품종별 동해 피해율표: 구분(나주) ¦ 최저기온(℃) ¦ 품종 ¦ 원줄기 …)
    key_word = {"최저기온": "최저기온", "우박크기": "우박", "토양습도": "토양습도"}[metric]
    i_key = next((i for i, h in enumerate(head) if key_word in h), 0)
    i_var = next((i for i, h in enumerate(head) if "품종" in h or "품 종" in h), -1)
    # 값이 든 열은 머리 두 줄을 합쳐 이름으로 쓴다
    parts = []
    for i, h in enumerate(head):
        sub = head2[i] if i < len(head2) and head2[i] and head2[i] != h else ""
        parts.append(f"{h} {sub}".strip())

    out = []
    start = 2 if head2 and head2 != head else 1
    for row in grid[start:]:
        key = " ".join(row[i_key].replace("\n", " ").split())
        if not key or nospace(key) in ("구분", "구 분", "우박크기"):
            continue
        m = re.search(r"(-?\d+(?:\.\d+)?)", key)
        if not m:
            continue
        variety = " ".join(row[i_var].replace("\n", " ").split()) if i_var >= 0 else ""
        for c, value in enumerate(row):
            if c in (i_key, i_var) or c == 0:
                continue
            value = " ".join(value.replace("\n", " ").split())
            if not re.fullmatch(r"\d+(?:\.\d+)?\*?", value):
                continue
            out.append({**src, "작물": "", "품종숙기": variety,
                        "생육단계": parts[c] if c < len(parts) else f"열{c}",
                        "재해종류": kind, "지표": metric,
                        "부등호": "<=" if metric == "최저기온" else ">=",
                        "값": m.group(1), "단위": unit, "지속일": "", "등급": "",
                        "조건원문": f"{key} → 피해율 {value}%",
                        "표종류": f"{kind} 피해율표", "비고": f"피해율 {value}%",
                        "confirmed": "Y"})
    return out


def rule_month_stage(grid, src) -> list[dict]:
    """월별 × 주요생육단계 × 중점관리 표. 규칙이 아니라 생육단계 달력이다."""
    head = [nospace(c.replace("\n", " ")) for c in grid[0]]
    if not ("월별" in head and any("생육단계" in h for h in head)):
        return []
    i_m = head.index("월별")
    i_s = next(i for i, h in enumerate(head) if "생육단계" in h)
    i_n = next((i for i, h in enumerate(head) if "관리" in h), -1)
    out = []
    for row in grid[1:]:
        month = " ".join(row[i_m].replace("\n", " ").split())
        m = re.search(r"(\d{1,2})\s*월", month)
        if not m:
            continue
        out.append({**src, "작물": "", "품종숙기": "",
                    "생육단계": " ".join(row[i_s].replace("\n", " ").split()),
                    "재해종류": "", "지표": "월", "부등호": "=", "값": m.group(1),
                    "단위": "월", "지속일": "", "등급": "",
                    "조건원문": " ".join(row[i_n].replace("\n", " ").split())[:100]
                               if i_n >= 0 else "",
                    "표종류": "월별 생육단계", "confirmed": "Y"})
    return out


RECOGNIZERS = (rule_crop_stage, rule_fruit_winter, rule_stacked, rule_veg_range, rule_rice_stage,
               rule_damage_rate, rule_month_stage)

def collect_zones(grid, src) -> list[dict]:
    """농업지대 20구분과 대표 관측지점을 뽑는다.

    처음엔 이 표를 '기상요소 평년편차' 로만 보고 잡음으로 흘렸는데, 왼쪽 두 칸이
    농진청이 쓰는 **농업지대 20구분과 지대별 관측지점**이다.

        1.태백고냉     대관령
        13.중서부평야  서울,인천,수원,서산,강화,천안,보령

    로드맵 §7 미결의 '작물별 대표 지역(주산지) 선정' 은 이 구분을 따르면 된다.
    우리가 임의로 고르면 기상 담당자와 지역 기준이 어긋난다.
    """
    head = [nospace(c.replace("\n", " ")) for c in grid[0]]
    if not head or head[0] != "농업지대" or len(head) < 2 or "지역" not in head[1]:
        return []
    out = []
    for row in grid[1:]:
        name = " ".join(row[0].replace("\n", " ").split())
        m = re.match(r"(\d{1,2})\s*[.．]\s*(\S.*)$", name)
        if not m:
            continue
        spots = [s.strip() for s in re.split(r"[,、·]", row[1].replace("\n", " ")) if s.strip()]
        out.append({"지대번호": int(m.group(1)), "지대명": m.group(2).strip(),
                    "관측지점": ", ".join(spots), "지점수": len(spots),
                    "출처파일": src.get("출처파일", "")})
    return out


# 판정 규칙은 아니지만 값이 든 표. 버리지 않고 긴 꼴로 담아둔다
REF_WORDS = ("감수율", "피해율", "부패율", "수량지수", "경감", "저항성", "발생률", "수량")


def collect_reference(grid, src) -> list[dict]:
    flat = " ".join(c.replace("\n", " ") for r in grid for c in r)
    if not any(w in flat for w in REF_WORDS):
        return []
    if "%" not in flat and "℃" not in flat:
        return []
    head = [" ".join(c.replace("\n", " ").split()) for c in grid[0]]
    out = []
    for r, row in enumerate(grid[1:], 1):
        for c, value in enumerate(row):
            value = " ".join(value.replace("\n", " ").split())
            if not value:
                continue
            out.append({**src, "표머리": head[c] if c < len(head) else f"열{c}",
                        "행": r, "열": c, "값": value[:100]})
    return out


# ---------- 다른 자료 ----------

# 발병 조건이 아니라 '이번 주 날씨' 를 말하는 문장. 이런 건 규칙이 될 수 없다
WEATHER_STOP = ("(기온)", "평년", "전망", "경과", "기상 경과", "예상되", "겠음", "겠고",
                "높았음", "낮았음", "기준(", "주차")
# 발병 조건임을 알려주는 말. 하나라도 있어야 규칙으로 본다
ONSET_WORDS = ("발병", "발생", "감염", "생육", "번식", "월동", "활동", "증식", "부화", "적온")


def from_pest() -> tuple[list[dict], list[dict]]:
    """병해충 경보 등급과 발병 조건 온도를 가져온다.

    ⚠ `항목.csv` 의 온도 문장 절반이 **이번 주 날씨 전망**이다.

        ❍ (기온) 아침 기온은 9~17℃, 낮 기온은 20~24℃로 평년과 비슷하겠음

    이걸 발병 조건으로 담으면 "과수화상병은 9℃ 이상이면 발생" 같은 엉터리 규칙이 된다.
    그래서 날씨 말이 들어간 문장은 빼고, 발병을 가리키는 말이 있는 것만 남긴다.

    그리고 병해충 이름으로 `경보.csv` 의 대상작물을 붙인다. 작물이 비어 있으면
    어느 작물에 적용할 규칙인지 알 수 없어 쓸모가 없다.
    """
    rules, alerts = [], []
    apath, ipath = PEST / "경보.csv", PEST / "항목.csv"
    crop_of, group_of = defaultdict(set), defaultdict(set)

    if apath.exists():
        for x in csv.DictReader(open(apath, encoding="utf-8-sig")):
            name = x["병해충명"]
            alerts.append({"출처파일": f"병해충 {x['연도']} 제{x['호수']}호", "계열": "병해충",
                           "작물군": x.get("작물군", ""), "작물": x.get("대상작물", ""),
                           "병해충명": name, "구분": x.get("구분", ""),
                           "등급": x["등급"], "기간": x.get("기간", "")})
            if x.get("대상작물"):
                crop_of[name].update(c.strip() for c in x["대상작물"].split(",") if c.strip())
            if x.get("작물군"):
                group_of[name].add(x["작물군"])

    def crops_for(pest: str) -> tuple[str, str]:
        """병해충 이름으로 작물을 찾는다. 이름이 '탄저병·사과갈색무늬병' 처럼 붙어 오기도 한다."""
        parts = [p.strip() for p in re.split(r"[,·・、]", pest) if p.strip()]
        crops, groups = set(), set()
        for p in parts + [pest]:
            crops |= crop_of.get(p, set())
            groups |= group_of.get(p, set())
        return ", ".join(sorted(crops)), ", ".join(sorted(groups))

    if ipath.exists():
        for x in csv.DictReader(open(ipath, encoding="utf-8-sig")):
            if not x.get("온도문장"):
                continue
            crops, groups = crops_for(x["병해충명"])
            for part in x["온도문장"].split(" ⁄ "):
                if any(w in part for w in WEATHER_STOP):
                    continue
                if not any(w in part for w in ONSET_WORDS):
                    continue
                for r in parse_threshold(part, "평균기온") or []:
                    rules.append({"출처파일": f"병해충 {x['연도']} 제{x['호수']}호",
                                  "계열": "병해충", "작물": crops, "품종숙기": "",
                                  "생육단계": "", "재해종류": x["병해충명"], **r,
                                  "표종류": "발병 조건(문장)", "비고": f"작물군 {groups}",
                                  # 문장에서 캐낸 값이라 표만큼 믿을 수 없다
                                  "confirmed": "N"})
    return rules, alerts


# 재해 대책이 아닌 항목. '재배적 특성' 표가 같이 걸려 들어온다
ACTION_STOP = ("학명", "분류", "생리적특성", "생리적 특성", "주요기술", "재배적지",
               "생육온도", "작형", "비료명", "품종")


def from_farmwork() -> list[dict]:
    """농작업일정 첨부의 '기상재해 및 생리장해 대책' 표를 가져온다.

    ⚠ 표를 고르는 조건에 '피해' 를 넣었더니 **'재배적 특성' 표까지 걸렸다.**
    그 표에는 `생리적특성` 칸에 "…피해를 받기 쉬움" 같은 문장이 있어서다.
    그 결과 학명·분류·주요기술이 재해 대책으로 담겼다. 항목 이름으로 거른다.
    """
    path = FARM / "첨부_표.csv"
    if not path.exists():
        return []
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    bykey = defaultdict(list)
    for x in rows:
        bykey[(x["파일"], x["표번호"])].append(x)
    out = []
    for (fname, tno), cells in bykey.items():
        flat = " ".join(c["값"] for c in cells)
        if "기상재해" not in flat and "생리장해" not in flat and "피해" not in flat:
            continue
        grid = defaultdict(dict)
        for c in cells:
            grid[int(c["행"])][int(c["열"])] = c["값"]
        for r in sorted(grid):
            cols = grid[r]
            if len(cols) < 2:
                continue
            item = " ".join(cols.get(0, "").split())
            body = " ".join(cols.get(max(cols), "").split())
            if not item or item == body or nospace(item) in ("항목", "항 목", "구분"):
                continue
            if any(s in nospace(item) for s in (nospace(w) for w in ACTION_STOP)):
                continue
            out.append({"작물": cells[0]["작물명"], "분류명": cells[0]["분류명"],
                        "출처파일": fname, "항목": item[:40], "대책": body[:300]})
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


def write_report(rules, refs, alerts, actions, files, failed) -> None:
    out = ["# 재해 판정 규칙 정리 결과", "",
           f"읽은 문서 {len(files)}개 · 판독 실패 {len(failed)}개",
           f"**판정 규칙 {len(rules):,}행** · 참고 수치표 {len(refs):,}행 · "
           f"병해충 경보 {len(alerts):,}행 · 작물별 대책 {len(actions):,}행", ""]

    conf = Counter(r["confirmed"] for r in rules)
    out += ["## 규칙의 근거", "",
            f"- `confirmed=Y` (표에서 그대로 옮김) : {conf['Y']:,}행",
            f"- `confirmed=N` (문장에서 캐냄) : {conf['N']:,}행", ""]

    out += ["## 표 종류별", "", "| 표 종류 | 규칙 | 작물 수 |", "|---|---|---|"]
    for name, n in Counter(r["표종류"] for r in rules).most_common():
        crops = {r["작물"] for r in rules if r["표종류"] == name and r["작물"]}
        out.append(f"| {name} | {n:,} | {len(crops)} |")

    out += ["", "## 재해 종류별", ""]
    for name, n in Counter(r["재해종류"] for r in rules).most_common(15):
        out.append(f"- {name or '(없음)'} : {n:,}행")

    out += ["", "## 작물별 규칙 수 (상위 30)", "", "| 작물 | 규칙 | 생육단계 | 재해종류 |",
            "|---|---|---|---|"]
    for crop, n in Counter(r["작물"] for r in rules if r["작물"]).most_common(30):
        sub = [r for r in rules if r["작물"] == crop]
        out.append(f"| {crop} | {n} | {len({r['생육단계'] for r in sub})} | "
                   f"{', '.join(sorted({r['재해종류'] for r in sub if r['재해종류']}))[:40]} |")

    out += ["", "## 등급이 붙은 규칙", ""]
    for g, n in Counter(r["등급"] for r in rules if r["등급"]).most_common():
        out.append(f"- {g} : {n:,}행")

    out += ["", "## 규칙 표본 (앞 40)", "",
            "| 작물 | 숙기 | 생육단계 | 재해 | 조건 | 등급 |", "|---|---|---|---|---|---|"]
    for r in rules[:40]:
        out.append(f"| {r['작물'][:12]} | {r['품종숙기'][:14]} | {r['생육단계'][:16]} | "
                   f"{r['재해종류'][:8]} | {r['지표']} {r['부등호']} {r['값']}{r['단위']}"
                   f"{(' ' + r['지속일'] + '일이상') if r['지속일'] else ''} | {r['등급']} |")

    if alerts:
        out += ["", "## 병해충 경보 (등급별)", ""]
        for g, n in Counter(a["등급"] for a in alerts).most_common():
            out.append(f"- {g} : {n:,}행")
        out += ["", "많이 나온 병해충 15", ""]
        for nm, n in Counter(a["병해충명"] for a in alerts).most_common(15):
            out.append(f"- {nm} : {n}회")

    if failed:
        out += ["", f"## 판독 실패 {len(failed)}건", ""] + [f"- {x}" for x in failed[:30]]

    (OUT / "요약.md").write_text("\n".join(out), encoding="utf-8")


def main() -> None:
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    OUT.mkdir(parents=True, exist_ok=True)
    for path, label in ((DISASTER, "재해예방정보"), (PEST, "병해충발생정보"), (FARM, "농작업일정")):
        if not path.exists():
            sys.exit(f"{label} 결과가 없습니다: {path}\n먼저 그 폴더의 스크립트를 돌려주세요.")

    files = sorted(p for p in DISASTER.rglob("*.*") if p.is_file())
    if limit:
        files = files[:limit]
    print(f"[1/4] 재해예방정보 {len(files)}개에서 표를 뜯습니다")

    rules, refs, zones, failed = [], [], [], []
    for i, f in enumerate(files, 1):
        src = {"출처파일": f.name, "계열": f.parent.parent.name, "연도": f.parent.name}
        try:
            _, grids = grids_of(f)
        except Exception as err:
            failed.append(f"{f.name}: {err}")
            continue
        for tno, grid in enumerate(grids, 1):
            if not grid or not grid[0]:
                continue
            s = {**src, "표번호": tno}
            for fn in RECOGNIZERS:
                try:
                    rules += fn(grid, s)
                except Exception:
                    pass        # 모양이 다른 표 하나 때문에 전체가 멈추면 안 된다
            refs += collect_reference(grid, s)
            zones += collect_zones(grid, s)
        if i % 20 == 0 or i == len(files):
            print(f"  [{i}/{len(files)}] 규칙 {len(rules):,} · 참고 {len(refs):,}")

    print("\n[2/4] 병해충발생정보를 가져옵니다")
    pest_rules, alerts = from_pest()
    rules += pest_rules
    print(f"  경보 {len(alerts):,}행 · 발병조건 {len(pest_rules):,}행")

    print("\n[3/4] 농작업일정 대책표를 가져옵니다")
    actions = from_farmwork()
    print(f"  {len(actions):,}행")

    print("\n[4/4] 표로 만듭니다")
    # 같은 표가 여러 호에 재수록되므로 같은 규칙이 여러 번 나온다. 중복을 표시만 해둔다
    seen = Counter()
    for r in rules:
        key = (r["작물"], r["생육단계"], r["재해종류"], r["지표"], r["부등호"],
               r["값"], r["등급"])
        seen[key] += 1
        r["중복수"] = seen[key]
    uniq = [r for r in rules if r["중복수"] == 1]

    dump(OUT / "disaster_rules.csv", uniq)
    dump(OUT / "disaster_rules_전체.csv", rules)
    # 같은 지대 구분이 23개 문서에 똑같이 실린다. 지대번호로 한 벌만 남긴다
    best = {}
    for z in zones:
        if z["지대번호"] not in best or z["지점수"] > best[z["지대번호"]]["지점수"]:
            best[z["지대번호"]] = z
    dump(OUT / "농업지대.csv", [best[k] for k in sorted(best)])
    dump(OUT / "참고수치표.csv", refs)
    dump(OUT / "병해충경보.csv", alerts)
    dump(OUT / "작물별대책.csv", actions)
    write_report(uniq, refs, alerts, actions, files, failed)

    print(f"\n끝났습니다. 결과: {OUT}")
    print(f"  규칙 {len(rules):,}행 중 중복을 뺀 {len(uniq):,}행이 disaster_rules.csv 입니다")
    print("  요약.md 를 저에게 보여주시면 됩니다")
    if failed:
        print(f"  ! 판독 실패 {len(failed)}건")


if __name__ == "__main__":
    main()
