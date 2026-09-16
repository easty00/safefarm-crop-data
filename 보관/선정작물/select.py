# 선정한 14작물의 crops.csv 초안을 만드는 스크립트입니다.
# 자세한 사용법은 같은 폴더의 "사용법.md" 를 읽어주세요.
#
# 새로 내려받는 것은 없습니다. 인터넷도 .env 도 필요 없습니다.
#
#   농작업일정/결과/농작업시기.csv   작형별 파종·수확 시기
#   적산온도/결과/*.csv            목표 적산온도 · 기준온도
#   재해규칙/결과/*.csv            재해 규칙 · 병해충 경보 건수
#
# ⚠ 작형은 추측하지 않고 아래 SPEC 에 사람이 손으로 못 박았습니다.
#   "노지 작형만 쓴다" 는 결정이 자동으로 판정되지 않기 때문입니다. 근거는 두 가지입니다.
#     ① 작물 이름에 촉성·반촉성이 박힌 것        → 고추(촉성재배)
#     ② 농작업시기.csv 의 '정보구분' 칸에 붙은 작형 → "생육과정(주요농작업) - 노지재배"
#   ②가 붙은 작물은 11종뿐이고 나머지는 단일 작형이라 이름과 시기로 사람이 판단했습니다.
#
# ⚠ 작업명이 작물마다 다릅니다. 정규식 하나로는 못 잡습니다.
#     벼   "모내기때"   ← '이앙' 도 '심기' 도 안 들어 있다
#     무   "씨뿌림"     ← '씨뿌리' 로 찾으면 안 걸린다
#   그래서 SPEC 에 작물별로 어느 작업명을 시작점으로 볼지 적어두었습니다.

import csv
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "결과"

# 작물키: (농사로작물명, 작형, 시작작업 정규식, 시작월, 수확 시작월, 지역, 메모)
#
# ⚠ 시작월·수확월을 사람이 못 박은 이유.
#   배추·무·상추·감자·당근은 한 문서에 봄·가을 작형이 **라벨 없이 섞여** 있습니다.
#   기계가 첫 파종과 마지막 수확을 집으면 "1월 파종 → 12월 수확 = 324일" 이 나옵니다.
#   실제로 그렇게 나왔었습니다. 짝은 사람이 지어야 합니다.
SPEC = [
    ("벼",          "벼 기계이앙재배",  "",             r"모내기",  5, 10, "김제·철원",  ""),
    ("배추_봄",      "배추",           "",             r"씨뿌림",  1,  4, "전국",      ""),
    ("배추_가을",     "배추",           "",             r"씨뿌림",  8, 10, "해남·전국",  ""),
    ("배추_고랭지",    "배추(고랭지재배)",   "",             r"씨뿌림",  4,  7, "평창·영월",  ""),
    ("무_봄",       "무",            "",             r"씨뿌림",  1,  4, "전국",      ""),
    ("무_가을",      "무",            "",             r"씨뿌림",  7, 10, "제주·전국",  ""),
    ("무_고랭지",     "무(고랭지재배)",    "고랭지(1기작)",    r"씨뿌림",  5,  7, "평창",      ""),
    ("상추_봄",      "상추",           "",             r"아주심기", 2,  3, "전국",      ""),
    ("상추_가을",     "상추",           "",             r"아주심기", 8,  9, "전국",      ""),
    ("시금치_월동",    "시금치",          "",             r"씨뿌림",  9,  1, "포항·남해",  "월동"),
    ("당근_봄",      "당근",           "",             r"씨뿌림",  3,  5, "제주·평창",  ""),
    ("당근_가을",     "당근",           "",             r"씨뿌림",  7, 10, "제주",      ""),
    ("수박",        "수박",           "노지재배",        r"아주심기", 4,  7, "고창·함안",  ""),
    ("마늘",        "마늘",           "",             r"씨뿌림",  9,  6, "제주·의성",  "저온요구도. 적산 모델 부적합(로드맵 6-4)"),
    ("양파",        "양파",           "",             r"아주심기", 10, 6, "무안·제주",  "월동. ①②를 가르는 작물"),
    ("감자_봄",      "감자",           "",             r"파종",    3,  6, "평야",      "통계청 분류는 채소가 아니라 서류"),
    ("감자_가을",     "감자",           "",             r"파종",    8, 11, "평야",      ""),
    ("고추",        "고추(보통재배)",     "",             r"아주심기", 3,  7, "전국",      ""),
    ("파",         "파",            "",             r"아주심기", 6, 11, "전남",      ""),
    ("가지",        "가지",           "봄재배(조숙,노지)",   r"아주심기", 5,  6, "전국",      "텃밭 수요"),
    ("방울토마토",     "토마토,방울토마토",   "조숙재배",        r"아주심기", 5,  6, "전국",      "텃밭 수요"),
    ("방울토마토_고랭지", "토마토,방울토마토",  "고랭지재배",       r"아주심기", 5,  7, "평창",      "텃밭 수요"),
]

SUN = {"상": 5, "중": 15, "하": 25}


def load(path):
    p = ROOT / path
    return list(csv.DictReader(p.open(encoding="utf-8-sig"))) if p.exists() else []


def midday(month, sun):
    """순(旬)을 날짜로. 상순 5일·중순 15일·하순 25일 — 로드맵 6-2 규칙."""
    try:
        m = int(month)
    except (TypeError, ValueError):
        return None
    # 13~18월은 해를 넘긴 표기다. 13=1월 … 18=6월. 월동 작물이 전부 이걸 쓴다.
    year = 0
    if m > 12:
        m -= 12
        year = 1
    return year * 365 + (m - 1) * 30.4 + SUN.get(sun, 15)


def mid_of(row):
    """한 작업 구간의 한가운데 날짜. 시작과 종료의 중앙을 쓴다."""
    a = midday(row["시작월"], row["시작순"])
    b = midday(row["종료월"], row["종료순"])
    if a is None or b is None:
        return None
    if b < a:
        b += 365
    return (a + b) / 2


def tag_of(info):
    return info.split("-")[1].strip() if "-" in info else ""


def main():
    sched = load("농작업일정/결과/농작업시기.csv")
    sums = [r for r in load("적산온도/결과/적산온도.csv") if r["쓸모"] in ("맞음", "확인필요")]
    bases = load("적산온도/결과/기준온도후보.csv")
    temps = load("농작업일정/결과/첨부_온도.csv")
    rules = load("재해규칙/결과/disaster_rules.csv")
    pests = load("재해규칙/결과/병해충경보.csv")

    def base_of(key):
        """기준온도. 적온·한계온도는 쓰지 않는다 (CLAUDE.md)."""
        out = []
        for r in bases:
            if r["작물"] and r["작물"].startswith(key):
                lo, hi = r["값최소"], r["값최대"]
                out.append((f"{lo}~{hi}" if lo != hi else lo, r["항목"], r["파일"]))
        for r in temps:
            it = r["항목"].replace(" ", "")
            if not r["작물명"].startswith(key):
                continue
            if any(w in it for w in ("최저", "정지")) and not any(
                w in it for w in ("적온", "한계", "야간")
            ):
                out.append((f'{r["최저"]}~{r["최고"]}', it, r["파일"]))
        return out

    def sum_of(key):
        return [
            (f'{float(r["값최소"]):,.0f}~{float(r["값최대"]):,.0f}'
             if r["값최소"] != r["값최대"] else f'{float(r["값최소"]):,.0f}',
             r["구간"], r["자료"])
            for r in sums if r["작물"] and r["작물"].startswith(key)
        ]

    rows = []
    for key, nm, tag, startpat, m_sow, m_har, region, memo in SPEC:
        base_key = key.split("_")[0]
        pat = re.compile(startpat)
        sow, har = [], []
        for r in sched:
            if r["작물명"] != nm:
                continue
            if tag and tag_of(r["정보구분"]) != tag:
                continue
            if not r["정보구분"].startswith("생육과정"):
                continue
            if pat.search(r["작업명"]) and r["시작월"] == str(m_sow):
                sow.append(r)
            elif "수확" in r["작업명"] and r["시작월"] == str(m_har):
                har.append(r)
        s = sow[0] if sow else None
        h = har[0] if har else None
        # 재배일수는 **구간의 중앙끼리** 잇는다.
        #   파종 시작 ~ 수확 종료로 재면 작형 범위의 양 끝이라 최장값이 나온다.
        #   봄배추가 142일로 나왔었는데 실제 봄배추는 80~90일이다.
        #   그 142일은 "1월 중순에 뿌린 포기가 6월 초에 수확될 때까지" 이지
        #   "한 포기가 자라는 데 걸리는 날" 이 아니다.
        days = ""
        if s and h:
            a = mid_of(s)
            b = mid_of(h)
            if a is not None and b is not None:
                d = b - a
                if d < 0:
                    d += 365          # 해를 넘긴 작형 (마늘·양파·시금치)
                days = round(d)
        b = base_of(base_key)
        t = sum_of(base_key)
        rows.append({
            "작물키": key,
            "농사로작물명": nm,
            "작형": tag or "(단일)",
            "지역후보": region,
            "파종·정식": f'{s["작업명"][:10]} {s["시작월"]}.{s["시작순"]}~{s["종료월"]}.{s["종료순"]}' if s else "",
            "수확": f'{h["시작월"]}.{h["시작순"]}~{h["종료월"]}.{h["종료순"]}' if h else "",
            "재배일수": days,
            "base_temp": b[0][0] if b else "",
            "base_temp_출처": f"{b[0][1]} · {b[0][2]}" if b else "",
            "base_confirmed": "Y" if b else "",
            "target_sum": t[0][0] if t else "",
            "target_sum_구간": t[0][1] if t else "",
            "target_sum_출처": t[0][2] if t else "",
            "target_confirmed": "Y" if t else "",
            "재해규칙": sum(1 for r in rules if r["작물"] == base_key),
            "병해충": sum(1 for r in pests if r["작물"] == base_key),
            "비고": memo,
        })

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "crops_초안.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # 빈칸 목록
    L = ["# 선정 14작물 — 채워진 것과 빈 것", "",
         f"작형 기준 {len(rows)}행입니다. 작물 하나가 작형 여럿을 가지면 행이 나뉩니다.", "",
         "## 한눈에", "",
         "| 작물 | 작형 | 파종·정식 | 수확 | 일수 | 기준온도 | 목표적산 | 재해 | 병해충 |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f'| {r["작물키"]} | {r["작형"]} | {r["파종·정식"]} | {r["수확"]} | {r["재배일수"]} | '
                 f'{r["base_temp"] or "—"} | {r["target_sum"] or "—"} | '
                 f'{r["재해규칙"] or "—"} | {r["병해충"] or "—"} |')
    nb = sorted({r["작물키"].split("_")[0] for r in rows if not r["base_temp"]})
    nt = sorted({r["작물키"].split("_")[0] for r in rows if not r["target_sum"]})
    L += ["", "## 기준온도가 없는 작물 — 국제 표에서 찾을 것", "",
          f"**{len(nb)}종**: " + " · ".join(nb), "",
          "## 목표 적산온도가 없는 작물 — 역산해야 함 (confirmed=N)", "",
          f"**{len(nt)}종**: " + " · ".join(nt), ""]
    (OUT / "빈칸.md").write_text("\n".join(L), encoding="utf-8")
    print(f"{len(rows)}행 · 기준온도 빈칸 {len(nb)}종 · 목표값 빈칸 {len(nt)}종")


if __name__ == "__main__":
    main()
