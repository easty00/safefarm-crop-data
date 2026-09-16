# 이미 받아둔 본문 전체에서 "적산온도 목표값" 과 "기준온도 후보" 를 캐내는 스크립트입니다.
# 자세한 사용법은 같은 폴더의 "사용법.md" 를 읽어주세요.
#
# 새로 내려받는 것은 없습니다. 인터넷을 쓰지 않고 .env 도 필요 없습니다.
#
#   농작업일정/결과/본문/      170개  ← 작물별 재배환경 절에 적산온도·생육최저온도가 있다
#   주간농사정보/결과/본문/     192개  ← 벼 벼베기 적기, 배 수확 적기
#   재해예방정보/결과/본문/     112개  ← 가루쌀 수발아 적산온도
#   품종정보/결과/본문/       2,523개
#   병해충발생정보/결과/본문/    57개
#
# 왜 따로 만들었나.
#   농작업일정/attach.py 가 뽑은 "첨부_온도.csv" 는 '적온·한계온도' 처럼 **온도 한 점**을
#   담는 표라서, 적산온도(누적값, 단위가 ℃·day 에 가깝다)를 담을 칸이 없다.
#   실제로 381행 중 적산온도는 2행뿐이었다. 값이 있는데 표에 안 들어간 것이라 새로 뽑는다.
#
# 함정 셋. 전부 '적산온도' 라는 말이 붙어 있지만 우리가 쓰려는 값이 아니다.
#
#   침종 적산온도 100℃     볍씨를 담근 '물' 의 누적온도다. 생육과 무관하다
#   블루베리 적산온도 800시간  단위가 시간이다. 이름만 적산온도이고 실제로는 저온요구도
#                          (chill hours, 7.2℃ 이하에 머문 시간)다. 로드맵 6-4 참조
#   발아 적산온도 140℃      싹틀 때까지만의 값이라 생육기간 목표값과 자리가 다르다
#
#   → 구분 칸에 따로 적어 남긴다. 지우지 않는다. 지우면 다음 사람이 또 캔다.
#
# 기준온도 후보에 대하여.
#   CLAUDE.md 가 못 박은 대로 '적온' 과 '한계온도' 는 기준온도가 아니다. 여기서는
#   **생육최저온도 / 발아최저온도 / 움트기최저온도** 만 골라 담는다. 이것이 "그 아래로는
#   자라지 않는다" 는 뜻에 가장 가까운 국내 1차 표현이다.

import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "결과"

SERVICES = [
    ("농작업일정", ROOT / "농작업일정" / "결과" / "본문"),
    ("주간농사정보", ROOT / "주간농사정보" / "결과" / "본문"),
    ("재해예방정보", ROOT / "재해예방정보" / "결과" / "본문"),
    ("병해충발생정보", ROOT / "병해충발생정보" / "결과" / "본문"),
    ("품종정보", ROOT / "품종정보" / "결과" / "본문"),
]

CROPLIST = ROOT / "농작업일정" / "결과" / "작물목록.csv"

# 숫자: 1,100 / 3,480 / 700 / 4.5
NUM = r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?"
# 범위: 1,100∼1,200 / 800~1,000 / 3,480±50
RANGE_RE = re.compile(
    rf"({NUM})\s*(?:[~∼〜-]\s*({NUM})|±\s*({NUM}))?\s*(℃|도|시간)"
)
DAYS_RE = re.compile(rf"({NUM})\s*(?:[~∼〜-]\s*({NUM}))?\s*일")

# 문장 경계로 쓸 글자들. hwpx·pdf 본문은 마침표가 잘 안 찍혀 있어 글머리표를 쓴다.
BULLET = "❍○∙·▶※*■【】\n\t|"

BASE_ITEMS = [
    "생육최저온도",
    "생육 최저온도",
    "생육최저 온도",
    "생육 최저 온도",
    "발아최저온도",
    "발아 최저온도",
    "움트기최저온도",
    "움트기 최저온도",
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def nospace(s: str) -> str:
    return re.sub(r"\s+", "", s)


def tidy(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def to_f(s):
    if s is None:
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def load_crops():
    """작물 이름 사전. 저장파일명 → 작물명 도 같이 만든다."""
    names, by_file = set(), {}
    if CROPLIST.exists():
        with CROPLIST.open(encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                crop = (row.get("작물명") or "").strip()
                if not crop:
                    continue
                names.add(crop)
                names.add(re.sub(r"\([^)]*\)", "", crop).strip())
                stem = Path((row.get("저장파일명") or "").strip()).stem
                if stem:
                    by_file[stem] = (crop, (row.get("분류명") or "").strip())
    # 목록에 없지만 본문에 자주 나오는 것들
    names |= {"벼", "가루쌀", "배", "사과", "포도", "복숭아", "단감", "감귤", "자두",
              "블루베리", "무화과", "상추", "수박", "참깨", "땅콩", "보리", "밀", "콩"}
    names.discard("")
    return sorted(names, key=len, reverse=True), by_file


# 한 글자 작물(벼·배·무·콩·팥·조)은 아무 데나 걸린다. '배수'의 '배', '조생종'의 '조'.
# 그래서 뒤에 조사나 띄어쓰기가 붙은 것만 인정한다.
# 띄어쓰기만 붙은 것은 인정하지 않는다. "물 배 수" 의 '배', "중 생 종" 의 '조' 가 걸린다.
ONE_CHAR_OK = re.compile(r"^(?:는|은|가|이|의|를|을|도|와|과|만|\s?베기|알|농사|재배|나무|밭|논)")


def crop_of(path: Path, by_file: dict, names, window: str, wide: str = ""):
    """① 파일 이름이 작물별 문서면 그걸 쓴다  ② 아니면 앞쪽 글에서 가장 가까운 작물을 찾는다.

    주간농사정보·재해예방정보는 한 파일에 작물이 수십 개라 파일명으로는 못 정한다.
    문장만 봐서도 안 된다. "* 출수 후 수확기 적산온도(1,100∼1,200℃)" 안에는 '벼'가 없다.
    → 앞쪽 글까지 넓혀서 **적산온도라는 말에 가장 가까운** 작물 이름을 고른다.
      틀릴 수 있으므로 '작물출처' 칸에 문장이라고 적어 사람이 되짚을 수 있게 남긴다.
    """
    stem = path.stem
    if stem in by_file:
        return by_file[stem][0], by_file[stem][1], "파일명"
    stem2 = re.sub(r"\s*농작업\s*일정$", "", stem).strip()
    if stem2 in by_file:
        return by_file[stem2][0], by_file[stem2][1], "파일명"

    hay = wide or window
    anchor = hay.find("적산")
    if anchor < 0:
        anchor = len(hay) // 2
    best = None
    for n in names:
        if not n:
            continue
        for m in re.finditer(re.escape(n), hay):
            if len(n) == 1 and not ONE_CHAR_OK.match(hay[m.end():m.end() + 2]):
                continue
            before = m.start() <= anchor
            dist = abs(m.start() - anchor)
            # 앞쪽에 있는 것을 먼저, 그다음 가까운 것을, 그다음 긴 이름을
            score = (0 if before else 1, dist, -len(n))
            if best is None or score < best[0]:
                best = (score, n)
    if best:
        return best[1], "", "문장"
    return "", "", ""


def sentence_at(text: str, pos: int, back=180, fwd=200) -> str:
    """글머리표를 경계 삼아 그 숫자가 실린 한 토막을 떼어낸다."""
    s = max(0, pos - back)
    e = min(len(text), pos + fwd)
    left = text[s:pos]
    right = text[pos:e]
    for ch in BULLET:
        i = left.rfind(ch)
        if i != -1:
            left = left[i + 1:]
    cut = len(right)
    for ch in BULLET:
        i = right.find(ch, 1)
        if i != -1:
            cut = min(cut, i)
    return tidy(left + right[:cut])


def classify(window: str, unit: str):
    """구분 칸. 함정 세 가지를 여기서 갈라낸다."""
    flat = nospace(window)
    if unit == "시간" or "저온요구" in flat or "휴면타파" in flat:
        return "저온요구도(시간)", "아님"
    if "침종" in flat or "싹틔우기" in flat and "물" in flat:
        return "침종(물온도)", "아님"
    if "발아적산온도" in flat or "발아 적산" in window:
        return "발아까지", "부분"
    return "생육", "맞음"


def phase_of(window: str):
    """어느 구간의 누적인지. 출발점이 다르면 값을 섞을 수 없다."""
    flat = nospace(window)
    for key, label in [
        ("출수후", "출수 후"), ("이삭팬후", "출수 후"), ("만개후", "만개 후"),
        ("개화~성숙", "개화~성숙"), ("개화∼성숙", "개화~성숙"),
        ("열매달림후", "착과 후"), ("전생육기간", "전 생육기간"),
        ("생육기간중", "전 생육기간"), ("생육기간", "전 생육기간"),
        ("꽃대신장", "추대까지"), ("적숙기", "만개 후"),
    ]:
        if key in flat:
            return label
    return ""


# 목표 적산온도가 아닌 구간. 값은 맞지만 **쓰임새가 다르다**
NOT_TARGET = {
    "추대까지": "추대(꽃대신장) 경보값. 수확 목표가 아님",
    "만개 후": "과수 저장성 판정용",
}


def verdict(how: str, label: str) -> str:
    """이 값을 목표 적산온도로 쓸 수 있는지 판정한다.

    ⚠ 상추 1,400~1,700℃ 를 '맞음' 으로 표시하고 있었다. 그런데 이 값은
    **꽃대가 올라오는 시점**이지 수확 목표가 아니다. 상추는 그 전에 거둔다.
    구간 이름이 곧 쓰임새이므로 구간으로 가른다.
    """
    if label in NOT_TARGET:
        return "다른용도"
    return "맞음" if how == "파일명" else "확인필요"


def grids(text: str):
    """본문 txt 안의 표를 격자로 되살린다.

    추출기가 표를 이렇게 적어둔다. 칸마다 줄이 바뀌고, ' | ' 만 있는 줄이 행의 끝이다.

        품  종\n | 열매달림 후 일수\n | 적산온도(℃)\n | \n
        소과종\n | 35~38\n | 750\n | \n

    문장만 훑으면 이 표가 통째로 빠진다. 수박 품종별 적산온도(750/800/1,000/1,200)와
    시금치 발아·생육 최저온도(4 / 3~4)가 전부 여기에 있다.
    """
    out, row, cur = [], [], []
    for raw in text.split("\n"):
        line = raw.strip()
        if line == "|":
            if cur:
                row.append(tidy(" ".join(cur)))
                cur = []
            if row:
                out.append(row)
                row = []
            continue
        if line.startswith("|"):
            if cur:
                row.append(tidy(" ".join(cur)))
            cur = [line.lstrip("| ").strip()]
        elif row or cur:
            cur.append(line)
        else:
            cur = [line] if line else []
    if cur:
        row.append(tidy(" ".join(cur)))
    if row:
        out.append(row)
    # 이어진 행들을 한 표로 묶는다 (칸 수가 같은 것끼리)
    tables, block = [], []
    for r in out:
        if block and len(r) != len(block[-1]):
            if len(block) >= 2:
                tables.append(block)
            block = []
        block.append(r)
    if len(block) >= 2:
        tables.append(block)
    return tables


def scan_grids(text, path, by_file, names, rows, base_rows, svc):
    """표에서 적산온도·최저온도 칸을 찾아 행 이름과 짝지어 담는다."""
    for tb in grids(text):
        head = tb[0]
        if len(head) < 2:
            continue          # 한 칸짜리는 표가 아니라 그냥 문단이다
        for col, cell in enumerate(head):
            if len(cell) > 24:
                continue      # 머리글 자리에 본문이 통째로 들어온 경우
            flat = nospace(cell)
            is_sum = "적산온도" in flat
            is_base = "최저온도" in flat
            if not (is_sum or is_base):
                continue
            for r in tb[1:]:
                if col >= len(r):
                    continue
                label = r[0]
                h = RANGE_RE.search(r[col] + "℃")
                if not h:
                    continue
                lo, hi = to_f(h.group(1)), to_f(h.group(2))
                if hi is None:
                    hi = lo
                win = f"[표] {' | '.join(head)} :: {' | '.join(r)}"
                crop, group, how = crop_of(path, by_file, names, win, text[:4000])
                if is_sum:
                    d = DAYS_RE.search(" ".join(r))
                    d_lo = to_f(d.group(1)) if d else None
                    d_hi = to_f(d.group(2)) if d and d.group(2) else d_lo
                    mid_s, mid_d = (lo + hi) / 2, ((d_lo + d_hi) / 2 if d_lo else None)
                    rows.append({
                        "자료": svc, "작물": crop, "분류": group, "작물출처": how,
                        "구분": "생육",
                        "쓸모": verdict(how, label),
                        "구간": label,
                        "값최소": lo, "값최대": hi, "단위": "℃",
                        "일수최소": d_lo or "", "일수최대": d_hi or "",
                        "함축일평균": round(mid_s / mid_d, 1) if mid_d else "",
                        "파일": path.name, "원문": win,
                    })
                else:
                    # 표 모양이 두 가지다. 어느 쪽이냐에 따라 항목 이름을 다르게 짓는다.
                    #   가로형  발아 적온 ¦ 발아 최저온도 ¦ 생육 적온 ¦ 생육 최저온도   ← 머리글이 이미 온전함
                    #           15~20℃   ¦ 10℃         ¦ 20~30℃  ¦ 5℃
                    #   세로형  구 분 ¦ 최저온도(℃) ¦ 최적온도(℃)                   ← 행 이름을 붙여야 뜻이 생김
                    #           발아  ¦ 4          ¦ 15~20
                    bare = nospace(cell).strip("()℃")
                    item = nospace(cell) if bare != "최저온도" else f"{nospace(label)}최저온도"
                    base_rows.append({
                        "자료": svc, "작물": crop, "분류": group, "작물출처": how,
                        "항목": item, "값최소": lo, "값최대": hi,
                        "단위": "℃", "파일": path.name, "원문": win,
                    })


def main():
    names, by_file = load_crops()
    rows, base_rows = [], []
    scanned = 0

    for svc, folder in SERVICES:
        if not folder.exists():
            print(f"  ! 없음: {folder}", file=sys.stderr)
            continue
        for path in sorted(folder.rglob("*.txt")):
            text = read(path)
            scanned += 1

            # ---------- 적산온도 ----------
            for m in re.finditer(r"적산\s*온도", text):
                win = sentence_at(text, m.start())
                wide = text[max(0, m.start() - 1500):m.start() + 200]
                crop, group, how = crop_of(path, by_file, names, win, wide)
                # 적산온도 라는 말 뒤쪽 숫자를 쓴다. 한 문장에 여럿이면 전부 담는다.
                #   "적산온도 : 소립종 (2,850℃), 대립종 (3,450℃)"  ← 둘 다 필요하다
                #   앞엣것만 담았다가 대립종 3,450 을 놓쳤었다.
                anchor = win.find("적산")
                hits = [h for h in RANGE_RE.finditer(win) if h.start() >= anchor][:3]
                if not hits:
                    continue
                for h in hits:
                    lo, hi, pm = to_f(h.group(1)), to_f(h.group(2)), to_f(h.group(3))
                    unit = h.group(4)
                    if pm is not None:
                        hi, lo = lo + pm, lo - pm
                    if hi is None:
                        hi = lo
                    kind, useful = classify(win, unit)
                    if useful == "맞음" and how != "파일명":
                        useful = "확인필요"   # 작물을 문장에서 짐작한 것이라 사람이 되짚어야 한다
                    # 값 바로 앞에 붙은 이름표(소립종·대립종 …)를 구간 칸에 살려둔다
                    tag = win[max(anchor, h.start() - 14):h.start()]
                    tag = re.sub(r"[^가-힣]", "", tag)
                    tag = re.sub(r"^(?:적?산?온?도?)", "", tag)[-6:]
                    d = DAYS_RE.search(win[h.start():h.start() + 40]) or DAYS_RE.search(win)
                    d_lo = to_f(d.group(1)) if d else None
                    d_hi = to_f(d.group(2)) if d and d.group(2) else d_lo
                    mid_sum = (lo + hi) / 2 if lo is not None else None
                    mid_day = (d_lo + d_hi) / 2 if d_lo else None
                    implied = round(mid_sum / mid_day, 1) if mid_sum and mid_day else ""
                    rows.append({
                        "자료": svc,
                        "작물": crop,
                        "분류": group,
                        "작물출처": how,
                        "구분": kind,
                        "쓸모": (verdict(how, phase_of(win) or tag)
                                 if kind == "생육" else useful),
                        "구간": phase_of(win) or tag,
                        "값최소": lo,
                        "값최대": hi,
                        "단위": unit,
                        "일수최소": d_lo or "",
                        "일수최대": d_hi or "",
                        "함축일평균": implied,
                        "파일": path.name,
                        "원문": win,
                    })

            # ---------- 표 ----------
            if svc == "농작업일정":
                scan_grids(text, path, by_file, names, rows, base_rows, svc)

            # ---------- 기준온도 후보 ----------
            flat_pos = 0
            for item in BASE_ITEMS:
                for m in re.finditer(re.escape(item), text):
                    win = sentence_at(text, m.start(), back=60, fwd=90)
                    crop, group, how = crop_of(path, by_file, names, win)
                    after = text[m.end():m.end() + 60]
                    h = RANGE_RE.search(after)
                    if not h:
                        continue
                    # 표의 '머리글 줄' 이면 항목 이름 다음에 또 항목 이름이 온다.
                    #   발아 적온 | 발아 최저온도 | 생육 적온 | 생육 최저온도 | 개화 한계일장
                    #   → 여기서 숫자를 찾으면 다음 줄(값 줄)의 첫 칸을 엉뚱하게 집어온다.
                    #     들깨 생육최저온도를 5℃ 가 아니라 15~20℃ 로 읽었던 자리다.
                    #     표는 아래 scan_grids 가 격자로 제대로 읽으므로 여기서는 건너뛴다.
                    if re.search(r"(적온|온도|일장)", after[:h.start()]):
                        continue
                    lo, hi = to_f(h.group(1)), to_f(h.group(2))
                    base_rows.append({
                        "자료": svc,
                        "작물": crop,
                        "분류": group,
                        "작물출처": how,
                        "항목": re.sub(r"\s+", "", item),
                        "값최소": lo,
                        "값최대": hi if hi is not None else lo,
                        "단위": h.group(3),
                        "파일": path.name,
                        "원문": win,
                    })
            flat_pos += 1

    OUT.mkdir(parents=True, exist_ok=True)
    write(OUT / "적산온도.csv", rows)
    write(OUT / "기준온도후보.csv", dedup(base_rows))
    summary(rows, dedup(base_rows), scanned)
    print(f"본문 {scanned}개 · 적산온도 {len(rows)}행 · 기준온도후보 {len(dedup(base_rows))}행")


def dedup(rows):
    seen, out = set(), []
    for r in rows:
        k = (r["작물"], r["항목"], r["값최소"], r["값최대"], r["파일"])
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def write(path: Path, rows):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def summary(rows, base_rows, scanned):
    lines = ["# 적산온도 · 기준온도 캐낸 결과", ""]
    lines.append(f"본문 {scanned}개를 훑어 **적산온도 {len(rows)}행** · "
                 f"**기준온도 후보 {len(base_rows)}행**을 얻었습니다.")
    lines.append("")
    lines.append("## 구분별")
    lines.append("")
    lines.append("| 구분 | 행 | 쓸모 |")
    lines.append("|---|---|---|")
    for k, v in Counter(r["구분"] for r in rows).most_common():
        u = "/".join(sorted({r["쓸모"] for r in rows if r["구분"] == k}))
        lines.append(f"| {k} | {v} | {u} |")
    lines.append("")

    def val(r):
        lo, hi = r["값최소"], r["값최대"]
        return f"{lo:,.0f}" if lo == hi else f"{lo:,.0f}~{hi:,.0f}"

    def day(r):
        lo, hi = r["일수최소"], r["일수최대"]
        if not lo:
            return ""
        return f"{lo:.0f}" if lo == hi else f"{lo:.0f}~{hi:.0f}"

    lines.append("## 확정 — 작물이 파일 이름으로 정해지는 것")
    lines.append("")
    lines.append("문서 하나가 작물 하나를 다루므로 작물을 헷갈릴 일이 없습니다.")
    lines.append("")
    lines.append("| 작물 | 구간 | 값(℃) | 일수 | 함축 일평균 | 파일 |")
    lines.append("|---|---|---|---|---|---|")
    seen = set()
    for r in sorted([r for r in rows if r["쓸모"] == "맞음"],
                    key=lambda r: (r["작물"], r["값최소"])):
        k = (r["작물"], r["구간"], r["값최소"], r["값최대"])
        if k in seen:
            continue
        seen.add(k)
        lines.append(f"| {r['작물']} | {r['구간']} | {val(r)} | {day(r)} | "
                     f"{r['함축일평균']} | {r['파일']} |")
    lines.append("")

    lines.append("## 확인 필요 — 작물을 문장에서 짐작한 것")
    lines.append("")
    lines.append("한 문서가 작물 수십 개를 다루는 주간농사정보·재해예방정보입니다.")
    lines.append("숫자는 원문 그대로지만 **작물 이름이 틀릴 수 있습니다.** 원문을 보고 고쳐주세요.")
    lines.append("")
    lines.append("| 짐작한 작물 | 값(℃) | 일수 | 함축 일평균 | 원문 |")
    lines.append("|---|---|---|---|---|")
    seen = set()
    for r in sorted([r for r in rows if r["쓸모"] == "확인필요"],
                    key=lambda r: (r["값최소"])):
        k = (r["값최소"], r["값최대"], r["원문"][:40])
        if k in seen:
            continue
        seen.add(k)
        txt = r["원문"][:70].replace("|", "¦")
        lines.append(f"| {r['작물'] or '(미상)'} | {val(r)} | {day(r)} | "
                     f"{r['함축일평균']} | {txt} |")
    lines.append("")

    lines.append("## 쓰면 안 되는 것 — 이름만 적산온도인 값")
    lines.append("")
    lines.append("| 구분 | 값 | 왜 아닌가 | 원문 |")
    lines.append("|---|---|---|---|")
    seen = set()
    for r in rows:
        if r["쓸모"] not in ("아님", "부분"):
            continue
        k = (r["구분"], r["값최소"])
        if k in seen:
            continue
        seen.add(k)
        why = {"침종(물온도)": "볍씨를 담근 물의 누적온도. 생육과 무관",
               "저온요구도(시간)": "단위가 시간. 휴면타파용 저온요구도(chill hours)",
               "발아까지": "싹틀 때까지만의 값이라 생육기간 목표값과 자리가 다름"}
        lines.append(f"| {r['구분']} | {val(r)}{r['단위']} | {why.get(r['구분'], '')} | "
                     f"{r['원문'][:50].replace('|', '¦')} |")
    lines.append("")

    lines.append("## 기준온도 후보")
    lines.append("")
    lines.append("적온·한계온도는 **넣지 않았습니다.** 기준온도가 아니기 때문입니다(CLAUDE.md).")
    lines.append("생육최저온도·발아최저온도만 담았습니다.")
    lines.append("")
    lines.append("| 작물 | 항목 | 값(℃) | 파일 |")
    lines.append("|---|---|---|---|")
    for r in sorted(base_rows, key=lambda r: (r["작물"], r["항목"])):
        lo, hi = r["값최소"], r["값최대"]
        v = f"{lo:g}" if lo == hi else f"{lo:g}~{hi:g}"
        lines.append(f"| {r['작물'] or '(미상)'} | {r['항목']} | {v} | {r['파일']} |")
    lines.append("")
    (OUT / "요약.md").write_text(chr(10).join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
