# 농사로 농작업일정정보(farmWorkingPlanNew) 전체를 수집하는 스크립트입니다.
# 자세한 사용법은 같은 폴더의 "사용법.md" 를 읽어주세요.
#
# 이 서비스 하나만 맡습니다. 오퍼레이션 5개를 모두 씁니다.
#
#   workScheduleGrpList         품목 분류 10개
#   workScheduleLst             작물 176건 목록 + 첨부파일 링크
#   workScheduleEraInfoJsonLst  시기 정보 (구조화)   ★ 이 스크립트의 핵심
#   workScheduleDtl             재배법 상세 (HTML)
#   workScheduleEraInfoLst      월별 달력 (HTML)     JSON 과 대조하기 위해 원문만 보관

import csv
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

BASE = "http://api.nongsaro.go.kr/service/farmWorkingPlanNew"
IMG_HOST = "https://www.nongsaro.go.kr"   # 본문에 박힌 그림의 상대주소 앞에 붙인다
HERE = Path(__file__).resolve().parent
OUT = HERE / "결과"
RAW = OUT / "raw"                 # API 응답 원문. 값이 이상할 때 추적용
FILES = OUT / "첨부"
WAIT = 0.4                        # 요청 사이 쉬는 시간(초). 정부 서버라 몰아치지 않는다
BAD_CHARS = '\\/:*?"<>|'          # 윈도 파일명에 못 쓰는 글자

ERA_ORDER = {"상": 0, "중": 1, "하": 2}
ERA_DAY = {"상": 5, "중": 15, "하": 25}    # 로드맵 §6-2 의 순(旬) → 날짜 변환 규칙

# 첨부파일 고르기.
# 기본값은 all - 일단 다 받는다. 무엇을 버릴지는 받아서 내용을 본 뒤에 정한다.
#   pick 은 아래 두 가지만 받는 좁은 모드다.
#     전략작물 가이드북 PDF  API 상세에 없는 내용이 8~10쪽 들어있음
#     구형 .hwp             완두·사과·국화 3건뿐
#   "○○ 농작업일정.hwpx" 160건은 벼 한 건에서 API 상세와 94.8% 겹쳤지만
#   표본 1건이라 일반화할 수 없다. 그래서 기본값에서는 빼지 않는다.
PICK_KEEP = ("전략작물 가이드북", )
PICK_EXTS = (".hwp", )

# 외국인근로자 번역본 6건은 어느 모드에서도 받지 않는다.
# 같은 농작업일정을 라오어·몽골어·베트남어·영어·크메르어·태국어로 옮긴 것이라
# 새로운 작물 데이터가 없다. 목록(작물목록.csv)에는 그대로 남는다.
SKIP_ALWAYS = ("외국인근로자", )


def api_key() -> str:
    """.env 의 AGRI_API 를 읽는다. 이 폴더에 없으면 상위 폴더로 올라가며 찾는다.

    키 파일을 여러 곳에 복사해두면 관리가 어려워지므로 원본 하나만 둔다.
    """
    for folder in (HERE, *HERE.parents):
        env = folder / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("AGRI_API="):
                    return line.split("=", 1)[1].strip()
    sys.exit(f".env 를 찾지 못했습니다. {HERE} 나 그 상위 폴더에 있어야 합니다.")


def safe(name: str) -> str:
    """폴더·파일 이름으로 쓸 수 있게 다듬는다."""
    return "".join("_" if ch in BAD_CHARS else ch for ch in name).strip() or "이름없음"


def tidy(text: str) -> str:
    """API 가 값 안에 섞어 보내는 태그와 겹친 공백을 지운다.

    opertNm 에 <br /> 이 그대로 들어오므로 저장 전에 반드시 거쳐야 한다.
    """
    text = re.sub(r"<[^>]+>", " ", text or "")
    for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"')]:
        text = text.replace(a, b)
    return " ".join(text.split())


def fetch(url: str) -> bytes:
    """한 번 실패하면 3초 쉬고 한 번 더 시도한다."""
    last = None
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(url, timeout=120) as res:
                return res.read()
        except Exception as err:      # 네트워크는 가끔 그냥 끊긴다
            last = err
            if attempt == 1:
                time.sleep(3)
    raise RuntimeError(f"두 번 모두 실패: {url}\n  {last}")


def call(operation: str, save_as: str, **params) -> ET.Element:
    """API 를 부르고 원문을 raw 에 저장한 뒤 파싱해 돌려준다.

    이미 받아둔 파일이 있으면 다시 부르지 않는다 - 중간에 끊겨도 이어서 할 수 있다.
    오류 응답은 저장하지 않는다. 정상인 줄 알고 저장해두면 다음 실행 때 건너뛰어
    영영 모르게 되기 때문이다.
    """
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
    """<item> 하나를 dict 하나로 바꾼다."""
    return [{child.tag: (child.text or "").strip() for child in item} for item in root.iter("item")]


def sun_index(month: str, era: str) -> int:
    """'4월 상순' 을 0~35 번호로 바꾼다. 1월 상순이 0, 12월 하순이 35.

    정렬과 기간 계산을 하려면 월과 순을 하나의 숫자로 합쳐두는 편이 편하다.

    ⚠ **해를 넘기는 작업은 종료월이 13~18 로 온다.** 13 이 이듬해 1월, 18 이 이듬해 6월이다.
    밀 '월동' 이 `12.하 → 13.하`, 맥주보리 붉은곰팡이병이 `10.상 → 16.중` 인 식이다.
    이걸 모르고 1~12 만 받으면 **월동작물의 작업 기간이 통째로 끊긴다.**
    실제로 29작물 94행의 종료순번·지속순수·종료중앙일이 전부 비어 있었다.
    그래서 36 을 더해 이듬해임을 살린다(36~71 = 이듬해).
    """
    try:
        m = int(month)
    except (TypeError, ValueError):
        return -1
    if era not in ERA_ORDER or not 1 <= m <= 24:
        return -1
    wrap = 36 if m > 12 else 0          # 13월 이상은 이듬해
    if m > 12:
        m -= 12
    return wrap + (m - 1) * 3 + ERA_ORDER[era]


def middle_day(month: str, era: str) -> str:
    """순을 날짜로 바꾼다. 상순 5일 · 중순 15일 · 하순 25일.

    이듬해로 넘어간 달은 `+04-15` 처럼 앞에 `+` 를 붙여 구분한다.
    """
    day = ERA_DAY.get(era)
    try:
        m = int(month)
    except (TypeError, ValueError):
        return ""
    if not day or not 1 <= m <= 24:
        return ""
    mark = "+" if m > 12 else ""        # 이듬해 표시
    if m > 12:
        m -= 12
    return f"{mark}{m:02d}-{day:02d}"


# ---------- 1. 작물 목록 ----------

def step_index() -> list[dict]:
    index = []
    for cat in rows(call("workScheduleGrpList", "grp")):
        code, name = cat.get("kidofcomdtySeCode", ""), cat.get("codeNm", "")
        crops = rows(call("workScheduleLst", f"lst_{code}", kidofcomdtySeCode=code))
        print(f"  {name}({code}) {len(crops)}건")
        for crop in crops:
            index.append({
                "분류코드": code, "분류명": name, "분류순서": cat.get("sort", ""),
                "작물명": crop.get("sj", ""), "cntntsNo": crop.get("cntntsNo", ""),
                "첨부파일명": crop.get("orginlFileNm", ""),
                "저장파일명": crop.get("fileName", ""), "파일구분코드": crop.get("fileSeCode", ""),
                "첨부링크": crop.get("fileDownUrlInfo", ""),
            })
    return index


# ---------- 2. 시기 정보 (핵심) ----------

def step_schedule(index: list[dict]) -> tuple[list[dict], list[str]]:
    out, failed = [], []
    for i, crop in enumerate(index, 1):
        no, label = crop["cntntsNo"], f"{crop['분류명']}/{crop['작물명']}"
        if not no:
            continue
        try:
            got = rows(call("workScheduleEraInfoJsonLst", f"erajson_{no}", cntntsNo=no))
        except Exception as err:
            failed.append(f"{label} (cntntsNo={no}): {err}")
            print(f"  [{i}/{len(index)}] {label} … 실패: {err}")
            continue

        for r in got:
            begin = sun_index(r.get("beginMon"), r.get("beginEra"))
            end = sun_index(r.get("endMon"), r.get("endEra"))
            out.append({
                # --- 응답 13칸 전부 그대로 ---
                "분류명": crop["분류명"], "작물명": crop["작물명"], "cntntsNo": no,
                "품목코드": r.get("kidofcomdtySeCode", ""), "품목명": r.get("kidofcomdtySeCodeNm", ""),
                "작업구분": tidy(r.get("farmWorkFlag", "")),
                "정보구분코드": r.get("infoSeCode", ""), "정보구분": tidy(r.get("infoSeCodeNm", "")),
                "작업명": tidy(r.get("opertNm", "")),      # <br /> 가 섞여 오므로 반드시 tidy
                "시작월": r.get("beginMon", ""), "시작순": r.get("beginEra", ""),
                "종료월": r.get("endMon", ""), "종료순": r.get("endEra", ""),
                "소요순수": r.get("reqreMonth", ""),
                "동영상": r.get("vodUrl", ""),
                # --- 아래 넷은 계산해 넣은 값 ---
                "시작순번": begin, "종료순번": end,
                "지속순수": (end - begin + 1) if begin >= 0 and end >= begin else "",
                "시작중앙일": middle_day(r.get("beginMon"), r.get("beginEra")),
                "종료중앙일": middle_day(r.get("endMon"), r.get("endEra")),
            })
        print(f"  [{i}/{len(index)}] {label} … {len(got)}건")
    return out, failed


# ---------- 3. 재배법 상세 ----------

def table_text(html: str) -> str:
    """표의 칸 경계를 살려서 글자로 바꾼다. 경계를 지우면 숫자가 한 덩어리로 붙는다."""
    html = re.sub(r"</t[dh]>", " | ", html or "")
    html = re.sub(r"</tr>", "\n", html)
    return tidy(html)


def html_tables(html: str, crop: dict) -> list[dict]:
    """본문 안의 `<table>` 을 **행·열 격자 그대로** 뜯는다.

    ⚠ `table_text()` 로 ' | ' 이어붙인 것만 `재배법.csv` 에 담았더니, CSV 한 칸에
    들어가면서 줄바꿈이 사라져 **표가 한 줄로 눌렸다.** 사람 눈엔 읽히지만 기계로는
    어디서 행이 끝나는지 알 수 없어 못 쓴다. 실제로 이런 게 묻혀 있었다.

        수박 과실의 성숙기 판정
        품 종  ¦ 열매달림 후 일수 ¦ 적산온도(℃)
        조생종  ¦ 38~40        ¦ 800
        중생종  ¦ 40~45        ¦ 1,000
        만생종  ¦ 40~45        ¦ 1,200

    **숙기별 목표 적산온도**가 그대로 있는데 "수박은 숙기 자료가 없다"고 보고했다.
    hwpx·PDF 는 격자로 뜯어놓고 정작 API HTML 만 안 뜯은 탓이다.

    `<caption>` 에 표 이름이 있고 `colspan`·`rowspan` 도 그대로라 hwpx 보다 쉽다.
    """
    out = []
    for tno, m in enumerate(re.finditer(r"<table[^>]*>.*?</table>", html or "", re.S), 1):
        block = m.group(0)
        cap = re.search(r"<caption[^>]*>(.*?)</caption>", block, re.S)
        title = tidy(cap.group(1)) if cap else ""
        grid: dict[int, dict[int, str]] = {}
        taken: set[tuple[int, int]] = set()
        for rno, tr in enumerate(re.findall(r"<tr[^>]*>.*?</tr>", block, re.S)):
            col = 0
            for cell in re.findall(r"<t([hd])([^>]*)>(.*?)</t[hd]>", tr, re.S):
                kind, attrs, body = cell
                while (rno, col) in taken:      # 위에서 rowspan 이 내려온 자리
                    col += 1
                cs = int((re.search(r'colspan="?(\d+)', attrs) or [0, 1])[1])
                rs = int((re.search(r'rowspan="?(\d+)', attrs) or [0, 1])[1])
                value = tidy(body)
                for r in range(rno, rno + rs):
                    for c in range(col, col + cs):
                        grid.setdefault(r, {})[c] = value
                        taken.add((r, c))
                col += cs
        for r in sorted(grid):
            for c in sorted(grid[r]):
                if grid[r][c]:
                    out.append({**crop, "표번호": tno, "표제목": title,
                                "행": r, "열": c, "값": grid[r][c]})
    return out


def images(html: str) -> str:
    """본문에 박힌 그림 주소를 모은다.

    글자만 뽑으면 그림이 통째로 사라진다. 돼지(번식)·동하계 사료작물 작부체계는
    재배법이 그림 한 장뿐이라, 주소를 안 남기면 그 작물은 내용이 아예 없어진다.
    주소가 /ps/img/... 로 시작하면 농사로 도메인을 붙여 바로 열 수 있게 한다.
    """
    srcs = re.findall(r'<img[^>]+src="([^"]+)"', html or "")
    full = [s if s.startswith("http") else f"{IMG_HOST}/{s.lstrip('/')}" for s in srcs]
    return " | ".join(dict.fromkeys(full))


def split_sections(html: str) -> list[tuple[str, str, str]]:
    """재배법 HTML 을 제목 기준으로 잘라 (제목, 내용, 그림주소) 목록으로 만든다.

    통째로 두면 '벼베기 적기' 같은 값을 찾기 어렵다. 섹션으로 나눠야 검색이 된다.

    주의: workScheduleDtl 의 제목은 <h3> 다. <h2> 는 월별 달력(EraInfoLst) 쪽에만 있다.
    둘을 헷갈리면 아무것도 안 잡히므로 h2·h3·h4 를 모두 받는다.
    첫 제목 앞에 오는 내용도 버리지 않고 '(머리말)' 로 남긴다.
    글자가 없고 그림만 있는 작물도 한 줄은 남긴다.
    """
    parts = re.split(r"<h[234][^>]*>(.*?)</h[234]>", html or "", flags=re.S)
    out = []

    head, head_img = table_text(parts[0]), images(parts[0])
    if head or head_img:
        out.append(("(머리말)" if head else "(그림만)", head, head_img))

    for i in range(1, len(parts), 2):
        out.append((tidy(parts[i]), table_text(parts[i + 1]), images(parts[i + 1])))
    return out


def step_detail(index: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
    out, tables, failed = [], [], []
    for i, crop in enumerate(index, 1):
        no, label = crop["cntntsNo"], f"{crop['분류명']}/{crop['작물명']}"
        if not no:
            continue
        try:
            got = rows(call("workScheduleDtl", f"dtl_{no}", cntntsNo=no))
        except Exception as err:
            failed.append(f"{label} 상세 (cntntsNo={no}): {err}")
            continue
        count = 0
        for r in got:
            cn = r.get("cn", "")
            # 표는 글자로 누르지 말고 격자 그대로도 따로 담는다
            tables += html_tables(cn, {"분류명": crop["분류명"], "작물명": crop["작물명"],
                                       "cntntsNo": no})
            sections = split_sections(cn)
            count += len(sections)
            for order, (title, body, img) in enumerate(sections, 1):
                out.append({
                    "분류명": crop["분류명"], "작물명": crop["작물명"], "cntntsNo": no,
                    "제목": r.get("cntntsSj", ""),          # 응답의 cntntsSj
                    "품목코드": r.get("kidofcomdtySeCode", ""),
                    "품목명": r.get("kidofcomdtySeCodeNm", ""),
                    "순서": order, "섹션": title, "내용": body, "그림주소": img,
                })
        if count == 0:
            failed.append(f"{label} 상세: 섹션 0개 — 제목 태그가 바뀌었을 수 있음")
        print(f"  [{i}/{len(index)}] {label} … 섹션 {count}개")
    return out, tables, failed


# ---------- 4. 월별 달력 (대조용) ----------

def parse_calendar(html: str) -> list[dict]:
    """월별 달력 HTML 을 칸 단위로 전부 풀어낸다.

    표는 항상 36열이다 (12개월 × 상·중·하순). colspan 을 더해가며 위치를 세면
    '4월 상순부터 5월 중순까지' 를 순 번호로 알 수 있다.

    라벨 칸을 버리지 않는다. 기상재해 표에는 '가뭄 →' 처럼 앞쪽 빈 달을 빌려
    행 이름을 적어둔 칸이 있는데, 시기로 읽으면 틀린 값이 된다. 지우는 대신
    '라벨로보임' 칸에 표시만 해두고 판단은 나중으로 미룬다.
    """
    out = []
    parts = re.split(r"<h2[^>]*>(.*?)</h2>", html or "", flags=re.S)
    blocks = [("(제목없음)", parts[0])] if tidy(parts[0]) else []
    blocks += [(tidy(parts[i]), parts[i + 1]) for i in range(1, len(parts), 2)]

    for section, body in blocks:
        for line, tr in enumerate(re.findall(r"<tr>(.*?)</tr>", body, re.S), 1):
            col = 0
            for m in re.finditer(r"<t([dh])([^>]*)>(.*?)</t[dh]>", tr, re.S):
                attr, inner = m.group(2), m.group(3)
                span = int(re.search(r'colspan="(\d+)"', attr).group(1)) if "colspan" in attr else 1
                text = tidy(inner)
                cls = (re.search(r'class="([^"]*)"', attr) or [None, ""])[1]
                if text and "calTd" in cls and col + span <= 36:
                    out.append({
                        "섹션": section, "행": line,
                        "시작순번": col, "종료순번": col + span - 1, "지속순수": span,
                        "시작월": col // 3 + 1, "시작순": "상중하"[col % 3],
                        "종료월": (col + span - 1) // 3 + 1, "종료순": "상중하"[(col + span - 1) % 3],
                        "내용": text, "색상": cls.replace("calTd", "").strip(),
                        "라벨로보임": "Y" if text.rstrip().endswith(("→", "⇒")) else "",
                    })
                col += span
    return out


def step_calendar(index: list[dict]) -> tuple[list[dict], list[str]]:
    """HTML 달력을 받아 원문 보관 + 칸 단위로 풀어 CSV 로 남긴다.

    JSON 오퍼레이션과 대조하려면 원문만 두면 안 되고 같은 모양으로 풀어놔야 한다.
    """
    out, failed = [], []
    for i, crop in enumerate(index, 1):
        no, label = crop["cntntsNo"], f"{crop['분류명']}/{crop['작물명']}"
        if not no:
            continue
        try:
            got = rows(call("workScheduleEraInfoLst", f"era_{no}", cntntsNo=no))
        except Exception as err:
            failed.append(f"{label} 달력: {err}")
            continue
        for r in got:
            for cell in parse_calendar(r.get("htmlCn", "")):
                out.append({"분류명": crop["분류명"], "작물명": crop["작물명"],
                            "cntntsNo": no, **cell})
        if i % 10 == 0 or i == len(index):
            print(f"  {i}/{len(index)}")
    return out, failed


# ---------- 5. 첨부파일 ----------

def wanted(name: str, mode: str) -> bool:
    """받을 첨부인지 고른다. 외국인근로자 번역본만 어느 모드에서도 제외한다."""
    if not name or any(s in name for s in SKIP_ALWAYS):
        return False
    if mode == "all":
        return True
    return any(k in name for k in PICK_KEEP) or name.lower().endswith(PICK_EXTS)


def step_files(index: list[dict], mode: str) -> tuple[int, list[str]]:
    got, failed = 0, []
    targets = [c for c in index if wanted(c["첨부파일명"], mode) and c["첨부링크"]]
    print(f"  받을 대상 {len(targets)}건 (모드: {mode})")

    for i, crop in enumerate(targets, 1):
        folder = FILES / safe(crop["분류명"])
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / safe(crop["첨부파일명"])
        if path.exists():
            print(f"  [{i}/{len(targets)}] {crop['작물명']} … 이미있음")
            got += 1
            continue
        try:
            path.write_bytes(fetch(crop["첨부링크"]))
            time.sleep(WAIT)
        except Exception as err:
            failed.append(f"{crop['분류명']}/{crop['작물명']} 첨부: {err}")
            print(f"  [{i}/{len(targets)}] {crop['작물명']} … 실패")
            continue
        print(f"  [{i}/{len(targets)}] {crop['작물명']} … 받음 ({path.stat().st_size/1024/1024:.1f}MB)")
        got += 1
    return got, failed


# ---------- 결과 정리 ----------

def dump(name: str, data: list[dict]) -> None:
    if not data:
        return
    with open(OUT / name, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(data[0].keys()))
        w.writeheader()
        w.writerows(data)


def compare(sched: list[dict], calendar: list[dict]) -> list[str]:
    """JSON 오퍼레이션과 HTML 달력이 같은 값을 주는지 작물별로 맞춰본다.

    같은 작업명이 양쪽에 있는데 순 번호가 다르면 둘 중 하나가 틀린 것이다.
    어느 쪽이 맞는지는 사람이 판단해야 하므로 여기서는 어긋난 것만 모아 보여준다.
    """
    left = {(x["cntntsNo"], x["작업명"]): (x["시작순번"], x["종료순번"]) for x in sched}
    diff = []
    for c in calendar:
        if c["라벨로보임"]:          # 라벨 칸은 애초에 시기가 아니므로 비교 대상이 아니다
            continue
        key = (c["cntntsNo"], c["내용"])
        if key in left and left[key] != (c["시작순번"], c["종료순번"]):
            diff.append(f"{c['작물명']} / {c['내용'][:24]} — "
                        f"JSON {left[key][0]}~{left[key][1]} vs 달력 {c['시작순번']}~{c['종료순번']}")
    return diff


def write_report(index, sched, detail, calendar, files_n, failed) -> None:
    kinds = Counter(x["정보구분"] for x in sched)
    flags = Counter(x["작업구분"] for x in sched if x["작업구분"])
    crops_done = {x["cntntsNo"] for x in sched}
    bad_sun = sum(1 for x in sched if x["시작순번"] == -1)
    sections = Counter(x["섹션"] for x in detail)
    no_section = {x["작물명"] for x in detail if x["섹션"] == "(머리말)"}
    labels = [x for x in calendar if x["라벨로보임"]]
    diff = compare(sched, calendar)

    out = ["# 농작업일정(farmWorkingPlanNew) 수집 결과", "",
           f"작물 목록 {len(index)}건 · 시기 정보를 받은 작물 {len(crops_done)}종 · 시기 항목 {len(sched)}건",
           f"재배법 섹션 {len(detail)}건 · 달력 칸 {len(calendar)}개 · 첨부 {files_n}건", ""]

    out += ["## 분류별 작물 수", ""]
    for k, n in Counter(x["분류명"] for x in index).most_common():
        out.append(f"- {k} : {n}건")

    out += ["", "## 정보 구분", ""]
    for k, n in kinds.most_common():
        out.append(f"- {k or '(빈값)'} : {n}건")

    out += ["", "## 작업구분(farmWorkFlag) 값", "",
            f"값이 있는 항목 {sum(flags.values())}건 / 종류 {len(flags)}가지", ""]
    for k, n in flags.most_common(40):
        out.append(f"- {k} : {n}건")
    if len(flags) > 40:
        out.append(f"- … 외 {len(flags)-40}가지")

    out += ["", "## 점검", "",
            f"- 순 번호 변환 실패: {bad_sun}건  (0이어야 정상)",
            f"- 동영상 주소가 있는 항목: {sum(1 for x in sched if x['동영상'])}건",
            f"- 시기 정보가 0건인 작물: {len(index) - len(crops_done)}종",
            f"- 재배법에 제목이 하나도 없어 '(머리말)' 만 나온 작물: {len(no_section)}종",
            f"- 달력에서 라벨로 보이는 칸(→ 로 끝남): {len(labels)}개 — 버리지 않고 표시만 해둠"]

    out += ["", "## JSON 과 HTML 달력 대조", "",
            f"두 오퍼레이션이 같은 작업에 대해 다른 시기를 주는 경우: **{len(diff)}건**", ""]
    if diff:
        out += ["어느 쪽이 맞는지는 원문을 봐야 합니다.", ""] + [f"- {x}" for x in diff[:40]]
        if len(diff) > 40:
            out.append(f"- … 외 {len(diff)-40}건 (달력.csv 와 농작업시기.csv 대조)")
    else:
        out.append("어긋난 것이 없습니다. 두 방식이 같은 답을 줍니다.")

    if labels:
        out += ["", "### 라벨로 보이는 달력 칸 (앞 20개)", ""]
        for x in labels[:20]:
            out.append(f"- {x['작물명']} / {x['섹션']} — `{x['내용'][:30]}` "
                       f"({x['시작월']}월 {x['시작순']}~{x['종료월']}월 {x['종료순']})")

    out += ["", "## 재배법에 많이 나오는 섹션 (상위 30)", ""]
    for k, n in sections.most_common(30):
        out.append(f"- {k} : {n}개 작물")

    out += ["", "## 표본 — 시기 정보 앞 20건", "",
            "| 작물 | 정보구분 | 작업 | 시작 | 종료 | 순수 |", "|---|---|---|---|---|---|"]
    for x in sched[:20]:
        out.append(f"| {x['작물명']} | {x['정보구분']} | {x['작업명'][:28]} | "
                   f"{x['시작월']}월 {x['시작순']} | {x['종료월']}월 {x['종료순']} | {x['지속순수']} |")

    if failed:
        out += ["", f"## 실패 {len(failed)}건", ""] + [f"- {x}" for x in failed[:40]]

    (OUT / "요약.md").write_text("\n".join(out), encoding="utf-8")


def main() -> None:
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    mode = "all"          # 기본값은 전부 받기. 버리는 판단은 내용을 본 뒤에 한다
    if "--files" in sys.argv:
        mode = sys.argv[sys.argv.index("--files") + 1]
    if mode not in ("none", "pick", "all"):
        sys.exit("--files 는 none / pick / all 중 하나여야 합니다")
    skip_detail = "--no-detail" in sys.argv

    for folder in (OUT, RAW, FILES):
        folder.mkdir(parents=True, exist_ok=True)

    failed = []

    print("[1/5] 작물 목록을 받습니다")
    index = step_index()
    print(f"  총 {len(index)}건\n")
    targets = index[:limit] if limit else index

    print(f"[2/5] 시기 정보를 받습니다 ({len(targets)}건)  ★ 핵심")
    sched, f2 = step_schedule(targets)
    failed += f2
    print()

    detail, detail_tables = [], []
    if skip_detail:
        print("[3/5] --no-detail 이라 재배법은 건너뜁니다\n")
    else:
        print(f"[3/5] 재배법 상세를 받습니다 ({len(targets)}건)")
        detail, detail_tables, f3 = step_detail(targets)
        failed += f3
        print()

    print(f"[4/5] 월별 달력을 받아 칸 단위로 풉니다 ({len(targets)}건)")
    calendar, f4 = step_calendar(targets)
    failed += f4
    print(f"  칸 {len(calendar)}개\n")

    files_n = 0
    if mode == "none":
        print("[5/5] --files none 이라 첨부는 건너뜁니다\n")
    else:
        print("[5/5] 첨부파일을 받습니다")
        files_n, f5 = step_files(targets, mode)
        failed += f5
        print()

    dump("작물목록.csv", index)
    dump("농작업시기.csv", sched)
    dump("재배법.csv", detail)
    dump("재배법_표.csv", detail_tables)
    dump("달력.csv", calendar)
    write_report(index, sched, detail, calendar, files_n, failed)

    print(f"끝났습니다. 결과: {OUT}")
    print("  요약.md 를 저에게 보여주시면 됩니다")
    if failed:
        print(f"  ! 실패 {len(failed)}건 — 요약.md 맨 아래에 있습니다")


if __name__ == "__main__":
    KEY = api_key()
    main()
