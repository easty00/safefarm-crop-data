# 농사로 병해충발생정보(dbyhsCccrrncInfo) 를 받아 글자로 바꾸고 경보 등급을 표로 뽑는 스크립트입니다.
# 자세한 사용법은 같은 폴더의 "사용법.md" 를 읽어주세요.
#
# 이 회보는 앞에서 본 다른 자료와 성격이 다릅니다. 첫 쪽에 이런 요약이 실려 있습니다.
#
#   Ⅰ. 식량작물
#   ▶ (경    보) 해충: 벼멸구, 혹명나방
#   ▶ (주 의 보) 병 : 이삭도열병, 세균벼알마름병, 깨씨무늬병
#
# 작물군 · 경보 등급 · 병/해충 구분 · 이름이 이미 갈려 있어서 표로 바로 옮길 수 있습니다.
# 본문에는 발병 조건 온도까지 들어 있습니다. 예: "발병 최적 온도는 30~35℃(최저 10, 최고 43℃)"

import csv
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

BASE = "http://api.nongsaro.go.kr/service/dbyhsCccrrncInfo"
HERE = Path(__file__).resolve().parent
OUT = HERE / "결과"
RAW = OUT / "raw"
FILES = OUT / "파일"
TEXTS = OUT / "본문"
WAIT = 0.4
BAD_CHARS = '\\/:*?"<>|'

DEFAULT_YEARS = "2023,2024,2025,2026"

# 매뉴얼에 numOfRows 가 적혀 있지 않지만 실제로는 먹는다.
# 안 주면 10건만 와서 연 15~18건인 해는 조용히 잘린다. 반드시 넉넉히 준다
ROWS = 100

GRADES = ("경보", "주의보", "예보")

# 첫 쪽 요약의 등급 줄: "▶ (주 의 보) 병 : 이삭도열병" / "▶ (예   보)" / "▶ (주의보) : 노균병"
# 등급 글자 사이에 공백이 제멋대로 들어가서 먼저 지우고 맞춘다
GRADE_RE = re.compile(r"[▶►]\s*\(\s*([가-힣\s]{2,6}?)\s*\)\s*[:：]?\s*(.*)$")
# 다음 줄로 이어지는 구분 줄: "  - 병 : 잿빛곰팡이병, 균핵병"
SUB_RE = re.compile(r"^\s*[-–ㅇ○❍]\s*([가-힣\s]{1,5}?)\s*[:：]\s*(.*)$")
# 구분은 병·해충만이 아니다. 바이러스가 따로 나온다
KINDS = ("병", "해충", "바이러스", "잡초", "선충")
# 작물군 머리: "Ⅰ. 식량작물" / "Ⅲ. 과    수"
GROUP_RE = re.compile(r"^\s*([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ])\s*[.．]\s*([가-힣\s]{2,12})\s*$")
# 본문 항목: "1  이삭도열병  <주의보>"
ITEM_RE = re.compile(r"^\s*(\d{1,2})\s+(\S[^<>]{0,24}?)\s*<\s*([가-힣\s]{2,6}?)\s*>")
# 발병 조건 온도 문장
TEMP_RE = re.compile(r"[^\n]{0,60}\d{1,2}\s*[~∼－-]?\s*\d{0,2}\s*℃[^\n]{0,60}")


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


def read_pdf(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return "".join(f"\n===== p.{i} =====\n" + (pg.extract_text() or "")
                   for i, pg in enumerate(reader.pages, 1))


def extract(path: Path) -> str:
    """확장자가 아니라 파일 앞 4바이트로 형식을 판정한다.

    지금까지 본 첨부는 전부 PDF 였지만, 옛날 호가 hwp 일 수 있어 분기를 남겨둔다.
    """
    head = path.read_bytes()[:4]
    if head[:4] == b"%PDF":
        return read_pdf(path)
    if head[:2] == b"PK":
        raise RuntimeError("hwpx 입니다 — 주간농사정보 스크립트의 추출기를 가져와야 합니다")
    if head[:4] == b"\xd0\xcf\x11\xe0":
        raise RuntimeError("hwp 입니다 — 주간농사정보 스크립트의 추출기를 가져와야 합니다")
    raise RuntimeError(f"모르는 형식 (앞 4바이트 {head!r})")


# ---------- 목록 ----------

def issue_no(subject: str) -> str:
    m = re.search(r"제\s*(\d+)\s*호", subject)
    return m.group(1) if m else ""


def span(subject: str) -> str:
    m = re.search(r"\(([^)]*~[^)]*)\)", subject)
    return " ".join(m.group(1).split()) if m else ""


def step_list(years: list[str]) -> list[dict]:
    have = [(it.findtext("yearCode") or "").strip()
            for it in call("dbyhsCccrrncInfoYear", "years").iter("item")]
    # '전체' 라는 값이 목록에 끼어 있는데 그걸로 조회하면 0건이 온다. 연도만 남긴다
    have = [y for y in have if y.isdigit()]
    print(f"  제공 연도 {len(have)}개: {', '.join(have)}")

    got = []
    for y in years:
        if y not in have:
            print(f"  ! {y}년은 제공 목록에 없습니다 - 건너뜁니다")
            continue
        root = call("dbyhsCccrrncInfoList", f"lst_{y}", sYear=y, numOfRows=ROWS)
        batch = rows(root)
        total = int(root.findtext(".//totalCount") or 0)
        if len(batch) < total:
            print(f"  ! {y}년 {len(batch)}건만 왔는데 총 {total}건이랍니다 - ROWS 를 늘리세요")
        for r in batch:
            subject = r.get("cntntsSj", "")
            r["연도"] = y
            r["호수"] = issue_no(subject)
            r["기간"] = span(subject)
        got += batch
        print(f"  {y}년 {len(batch)}건 (totalCount={total})")
    return got


def step_download(items: list[dict]) -> list[str]:
    failed = []
    for i, r in enumerate(items, 1):
        link = r.get("downFile", "")
        if not link:
            failed.append(f"{r['연도']} {r.get('cntntsSj','')[:40]}: 첨부 주소 없음")
            continue
        folder = FILES / (r["연도"] or "연도미상")
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / safe(f"{r['호수'] or '00'}호_{r.get('rtnOrginlFileNm') or '첨부.bin'}")
        if path.exists() and path.stat().st_size == 0:
            path.unlink()       # 0바이트로 저장된 적이 있다. 두면 영영 빈 채로 남는다
        if not path.exists():
            try:
                blob = fetch(link)
                if blob[:16].lstrip().lower().startswith((b"<!doctype", b"<html")):
                    raise RuntimeError("파일 대신 안내 페이지가 왔습니다")
                if not blob:
                    raise RuntimeError("빈 파일(0바이트)이 왔습니다")
                path.write_bytes(blob)
                time.sleep(WAIT)
            except Exception as err:
                failed.append(f"{r['연도']} 제{r['호수']}호: {err}")
                print(f"  [{i}/{len(items)}] 실패 제{r['호수']}호")
                continue
        r["파일"] = str(path.relative_to(OUT))
        r["파일KB"] = round(path.stat().st_size / 1024)
        print(f"  [{i}/{len(items)}] {r['연도']} 제{r['호수']:>2}호  {r['파일KB']:>7,}KB")
    return failed


# ---------- 알맹이 뽑기 ----------

def split_top(text: str) -> list[str]:
    """괄호 밖의 쉼표·가운뎃점에서만 쪼갠다.

    그냥 쪼개면 "잎마름병(마늘, 양파)" 가 "잎마름병(마늘" 과 "양파)" 로 갈린다.
    괄호 안 쉼표는 대상 작물 목록이라 끊으면 안 된다.
    """
    out, buf, depth = [], [], 0
    for ch in text:
        if ch in "(（":
            depth += 1
        elif ch in ")）":
            depth = max(0, depth - 1)
        if depth == 0 and ch in ",、·・":
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf))
    return out


def parse_summary(text: str, r: dict) -> list[dict]:
    """첫 쪽 요약에서 작물군 × 등급 × 구분 × 이름을 뽑는다.

    첫 판은 한 호만 보고 만들었다가 2023~2024년을 절반 넘게 놓쳤다.
    실제로는 네 가지 모양이 섞여 있다.

      ① 한 줄에 둘      ▶ (주 의 보) 병 : 붉은곰팡이병 / 해충 : 열대거세미나방
      ② 여러 줄로       ▶ (예   보)
                          - 병 : 잿빛곰팡이병, 균핵병
                          - 해충 : 총채벌레류
      ③ 구분 없이       ▶ (주의보) : 노균병(양파), 흑색썩음균핵병(마늘, 양파)
      ④ 줄바꿈으로 이어짐  ... 노균병, 역병,
                          딸기 꽃곰팡이병          ← 앞 줄이 쉼표로 끝나면 이어진 것

    그리고 구분이 '병'·'해충'만 있는 게 아니다. '바이러스'가 따로 나온다.
    등급과 이름 글자 사이에 공백이 들어가므로("주 의 보", "무 름 병") 지우고 맞춘다.
    """
    out, group, grade, kind = [], "", "", ""
    open_list = False          # 앞 줄이 쉼표로 끝나 다음 줄로 이어지는 중인가

    def add(names: str, src: str) -> bool:
        """이름 목록을 쪼개 담는다. 쉼표로 끝나면 다음 줄로 이어진다는 뜻이다."""
        for name in split_top(names):
            name = re.sub(r"\s+", "", name).strip(" .·/")
            if not 2 <= len(name) <= 40:
                continue
            # 뒤에 붙은 괄호는 대상 작물이다. "잎마름병(마늘,양파)" → 잎마름병 / 마늘,양파
            m = re.match(r"(.+?)[(（]([^)）]*)[)）]$", name)
            out.append({"연도": r["연도"], "호수": r["호수"], "기간": r["기간"],
                        "작물군": group, "등급": grade,
                        "구분": kind or "미분류",
                        "병해충명": m.group(1) if m else name,
                        "대상작물": m.group(2) if m else "",
                        "원문": " ".join(src.split())[:120]})
        return names.rstrip().endswith((",", "、"))

    def spread(rest: str, src: str) -> bool:
        """'병 : a, b / 해충 : c' 처럼 한 줄에 여러 구분이 붙은 것을 푼다."""
        nonlocal kind
        last = False
        for chunk in rest.split("/"):
            if not chunk.strip():
                continue
            m = re.match(r"\s*([가-힣]{1,5})\s*[:：]\s*(.*)$", chunk)
            if m and re.sub(r"\s+", "", m.group(1)) in KINDS:
                kind = re.sub(r"\s+", "", m.group(1))
                last = add(m.group(2), src)
            else:
                last = add(chunk, src)
        return last

    for raw in text.splitlines():
        line = raw.rstrip()
        # 첫 쪽 요약만 읽는다. 본문으로 넘어가면 멈춘다
        if "===== p.2" in line or "농약 안전사용기준" in line:
            break

        g = GROUP_RE.match(line)
        if g:
            group = re.sub(r"\s+", "", g.group(2))
            kind, open_list = "", False
            continue

        m = GRADE_RE.search(line)
        if m and re.sub(r"\s+", "", m.group(1)) in GRADES:
            grade = re.sub(r"\s+", "", m.group(1))
            kind, open_list = "", False
            rest = m.group(2).strip()
            if rest:                       # ① ③ — 같은 줄에 이름이 이어짐
                open_list = spread(rest, line)
            continue                       # ② — 등급만 있고 다음 줄로 넘어감

        s = SUB_RE.match(line)
        if s and grade and re.sub(r"\s+", "", s.group(1)) in KINDS:
            kind = re.sub(r"\s+", "", s.group(1))
            open_list = spread(s.group(2), line)
            continue

        if open_list and line.strip():     # ④ 줄바꿈으로 이어진 이름
            open_list = add(line, line)

    return out


def parse_items(text: str, r: dict) -> list[dict]:
    """본문 항목("1  이삭도열병  <주의보>")과 그 안의 온도 문장을 뽑는다."""
    lines = text.splitlines()
    # 항목이 시작하는 줄을 먼저 전부 찾는다. 다음 항목이 어디서 시작하는지 알아야
    # 본문을 정확히 끊을 수 있다. 줄 수로 대충 끊으면 다음 항목의 온도를 끌어온다
    marks = []
    for i, line in enumerate(lines):
        m = ITEM_RE.match(line.rstrip())
        if m and re.sub(r"\s+", "", m.group(3)) in GRADES:
            marks.append((i, m))

    out = []
    for k, (i, m) in enumerate(marks):
        end = marks[k + 1][0] if k + 1 < len(marks) else len(lines)
        body = "\n".join(lines[i + 1: end])
        temps = [" ".join(t.split()) for t in TEMP_RE.findall(body)]
        out.append({"연도": r["연도"], "호수": r["호수"], "기간": r["기간"],
                    "번호": m.group(1),
                    "병해충명": re.sub(r"\s+", "", m.group(2)),
                    "등급": re.sub(r"\s+", "", m.group(3)),
                    "본문줄수": end - i - 1,
                    "온도문장수": len(temps),
                    "온도문장": " ⁄ ".join(temps[:3])})
    return out


def step_text(items: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
    """전문을 통째로 저장하고, 요약표와 본문 항목을 따로 뽑는다.

    본문에는 어떤 필터도 걸지 않는다. 걸러낸 뒤에 후회한 적이 있다.
    """
    alerts, entries, failed = [], [], []
    targets = [r for r in items if r.get("파일")]
    for i, r in enumerate(targets, 1):
        src = OUT / r["파일"]
        folder = TEXTS / (r["연도"] or "연도미상")
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / (safe(f"{r['호수'] or '00'}호") + ".txt")
        try:
            text = dest.read_text(encoding="utf-8") if dest.exists() else extract(src)
        except Exception as err:
            failed.append(f"{r['연도']} 제{r['호수']}호 판독: {err}")
            print(f"  [{i}/{len(targets)}] 판독 실패 {src.name[:36]}")
            continue
        if not dest.exists():
            dest.write_text(text, encoding="utf-8")
        r["본문"] = str(dest.relative_to(OUT))
        r["본문자수"] = len(text)
        r["쪽수"] = text.count("===== p.")

        a, e = parse_summary(text, r), parse_items(text, r)
        alerts += a
        entries += e
        r["요약행"], r["항목행"] = len(a), len(e)
        print(f"  [{i}/{len(targets)}] {r['연도']} 제{r['호수']:>2}호  "
              f"{r['쪽수']:>3}쪽 · 요약 {len(a):>3} · 항목 {len(e):>2}")
    return alerts, entries, failed


# ---------- 결과 ----------

def dump(path: Path, data: list[dict]) -> None:
    if not data:
        return
    keys = list(dict.fromkeys(k for d in data for k in d))
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(data)


def write_compare(alerts: list[dict]) -> None:
    """연도끼리 맞대본다. 같은 달에 같은 병해충이 반복되면 달력으로 쓸 수 있다."""
    years = sorted({a["연도"] for a in alerts})
    out = ["# 연도 대조", "", f"대상 연도: {', '.join(years)}", ""]

    out += ["## 호수 × 등급별 건수", "",
            "| 호 | " + " | ".join(f"{y}년" for y in years) + " |",
            "|---|" + "---|" * len(years)]
    grid = defaultdict(lambda: defaultdict(int))
    for a in alerts:
        if a["호수"]:
            grid[int(a["호수"])][a["연도"]] += 1
    for no in sorted(grid):
        out.append(f"| 제{no}호 | " + " | ".join(str(grid[no].get(y, 0)) or "—" for y in years) + " |")

    out += ["", "## 해마다 되풀이되는 병해충", "",
            "몇 개 연도에 걸쳐 나오는지 셉니다. 연도 수가 많을수록 상시 경계 대상입니다.", "",
            "| 병해충 | 나온 연도 수 | 등장 횟수 | 주로 몇 호 |", "|---|---|---|---|"]
    per = defaultdict(lambda: {"years": set(), "n": 0, "no": Counter()})
    for a in alerts:
        d = per[a["병해충명"]]
        d["years"].add(a["연도"])
        d["n"] += 1
        if a["호수"]:
            d["no"][a["호수"]] += 1
    rank = sorted(per.items(), key=lambda kv: (-len(kv[1]["years"]), -kv[1]["n"]))
    for nm, d in rank[:45]:
        tops = ", ".join(f"{k}호" for k, _ in d["no"].most_common(3))
        out.append(f"| {nm} | {len(d['years'])} | {d['n']} | {tops} |")

    out += ["", "## 한 해에만 나온 병해충", "",
            "새로 나타났거나 그해에만 문제가 된 것입니다. 여기가 진짜 변화입니다.", ""]
    once = [(nm, next(iter(d["years"]))) for nm, d in per.items() if len(d["years"]) == 1]
    for nm, y in sorted(once, key=lambda x: x[1], reverse=True)[:50]:
        out.append(f"- {y}년 · {nm}")

    (OUT / "대조.md").write_text("\n".join(out), encoding="utf-8")


def write_report(items, picked, alerts, entries, failed) -> None:
    read = [r for r in picked if r.get("본문자수")]
    kb = sum(r.get("파일KB", 0) for r in picked)

    out = ["# 병해충발생정보 수집 결과", "",
           f"목록 {len(items)}건 · 받음 {sum(1 for r in picked if r.get('파일'))}건 "
           f"· 판독 {len(read)}건",
           f"{kb/1024:,.0f}MB · 본문 {sum(r.get('본문자수',0) for r in read):,}자",
           f"경보 요약 {len(alerts):,}행 · 본문 항목 {len(entries):,}행", ""]

    out += ["## 연도별", "", "| 연도 | 목록 | 받음 | 판독 | 요약행 | 항목행 | 용량 |",
            "|---|---|---|---|---|---|---|"]
    for y in sorted({r["연도"] for r in items}, reverse=True):
        a = [r for r in items if r["연도"] == y]
        b = [r for r in picked if r["연도"] == y]
        out.append(f"| {y} | {len(a)} | {sum(1 for r in b if r.get('파일'))} | "
                   f"{sum(1 for r in b if r.get('본문자수'))} | "
                   f"{sum(1 for x in alerts if x['연도']==y)} | "
                   f"{sum(1 for x in entries if x['연도']==y)} | "
                   f"{sum(r.get('파일KB',0) for r in b)/1024:,.0f}MB |")

    out += ["", "## 등급별", ""]
    for g in GRADES:
        n = sum(1 for a in alerts if a["등급"] == g)
        out.append(f"- **{g}** {n:,}행")
    out.append("")
    for k, n in Counter(a["구분"] for a in alerts).most_common():
        out.append(f"- {k} {n:,}행")

    out += ["", "## 작물군별", ""]
    for g, n in Counter(a["작물군"] for a in alerts).most_common():
        out.append(f"- {g or '(못 읽음)'} : {n:,}행")

    out += ["", "## 많이 나온 병해충 40", "", "| 병해충 | 횟수 | 주된 등급 |", "|---|---|---|"]
    per = defaultdict(Counter)
    for a in alerts:
        per[a["병해충명"]][a["등급"]] += 1
    for nm, n in Counter(a["병해충명"] for a in alerts).most_common(40):
        out.append(f"| {nm} | {n} | {per[nm].most_common(1)[0][0]} |")

    hot = [e for e in entries if e["온도문장수"]]
    out += ["", "## 발병 조건 온도가 적힌 항목", "",
            f"본문 항목 {len(entries):,}개 중 **{len(hot):,}개**에 ℃ 문장이 있습니다.",
            "여기가 disaster_rules 로 옮길 재료입니다.", ""]
    for e in hot[:25]:
        out.append(f"- **{e['병해충명']}** ({e['연도']} 제{e['호수']}호 · {e['등급']})  \n"
                   f"  {e['온도문장'][:150]}")

    if failed:
        out += ["", f"## 실패 {len(failed)}건", ""] + [f"- {x}" for x in failed[:40]]

    (OUT / "요약.md").write_text("\n".join(out), encoding="utf-8")


def main() -> None:
    years = DEFAULT_YEARS
    if "--year" in sys.argv:
        years = sys.argv[sys.argv.index("--year") + 1]
    years = [y.strip() for y in years.split(",") if y.strip()]
    skip = "--no-files" in sys.argv

    for folder in (OUT, RAW, FILES, TEXTS):
        folder.mkdir(parents=True, exist_ok=True)

    print(f"[1/4] 목록을 받습니다 ({', '.join(years)})")
    items = step_list(years)
    print(f"  총 {len(items)}건\n")

    failed, alerts, entries = [], [], []
    if skip:
        print("[2/4] --no-files 라서 파일은 건너뜁니다\n[3/4] 건너뜁니다\n")
    else:
        print(f"[2/4] 파일을 내려받습니다 ({len(items)}건)")
        failed += step_download(items)
        print()
        print("[3/4] 전문을 글자로 바꾸고 경보표를 뽑습니다")
        alerts, entries, f3 = step_text(items)
        failed += f3
        print()

    print("[4/4] 연도끼리 대조합니다")
    dump(OUT / "목록.csv", items)
    dump(OUT / "경보.csv", alerts)
    dump(OUT / "항목.csv", entries)
    write_compare(alerts)
    write_report(items, items, alerts, entries, failed)

    print(f"\n끝났습니다. 결과: {OUT}")
    print("  요약.md 와 대조.md 를 저에게 보여주시면 됩니다")
    if failed:
        print(f"  ! 실패 {len(failed)}건 — 요약.md 맨 아래")


if __name__ == "__main__":
    KEY = api_key()
    main()
