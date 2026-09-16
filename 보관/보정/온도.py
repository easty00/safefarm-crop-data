# -*- coding: utf-8 -*-
"""
본문에서 온도를 다시 뽑는다. 문장형까지 잡고, 무엇에 쓸 값인지 분류한다.

원본검수_2026-09-15.md §10 :
본문에 ℃ 값이 974개 있는데 `첨부_온도.csv` 에는 372행만 들어갔다(38%).
43작물이 0행이고 감자가 대표다.

    감자 농작업일정.txt:100   ❍ 씨감자 싹은 5℃ 이상에서 자라기 시작함
    감자 농작업일정.txt:102   ❍ 덩이줄기가 굵어지는 데 좋은 온도는 14~18℃

기존 `attach.py` 는 `이름 : 값` 꼴만 본다(`looks_temp(label)` 을 통과해야 한다).
위처럼 콜론도 없고 항목 이름도 없는 **문장**은 통째로 지나친다.
정정 요청서 ⑥ 에서 감자 5℃ 를 사람이 손으로 찾아 넣어야 했던 이유가 이것이다.

이 스크립트는 `attach.py` 를 고치지 않는다. 옆에서 따로 뽑아 대조표를 만든다.
파이프라인을 건드리면 이미 검증된 372행까지 흔들리기 때문이다.

⚠ 가장 중요한 것은 개수가 아니라 **분류**다. CLAUDE.md 가 못 박은 세 가지를 지킨다.

    기준온도   그 아래로는 생육이 진행되지 않는다   → crops.base_temp
    한계온도   그 아래/위로 가면 피해가 난다        → disaster_rules
    적온      가장 잘 자라는 온도                → 어느 쪽도 아님. 계산에 쓰지 말 것

    python 온도.py              결과/온도_전체.csv · 온도_기준온도후보.csv 를 만든다
    python 온도.py --작물 감자    한 작물만 원문과 함께 보여준다
    python 온도.py --빠진것       기존 첨부_온도.csv 에 없는 것만 본다
"""
import os
import io
import re
import csv
import argparse
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
결과 = os.path.join(ROOT, "보정", "결과")

# 값 읽기 ─ "25~32℃", "15.5℃~28.5℃", "-3~-4℃", "4℃"
값무늬 = re.compile(r"(-?\d+(?:\.\d+)?)\s*(?:℃)?\s*(?:~|∼|-|―|—|부터)\s*(-?\d+(?:\.\d+)?)\s*℃"
                  r"|(-?\d+(?:\.\d+)?)\s*℃")

# ── 분류 ──────────────────────────────────────────────────────────────
# 순서가 중요하다. 위에서부터 맞는 것을 쓴다.
# "저장 적온" 은 적온이 아니라 무관이어야 하므로 무관을 먼저 본다.

무관말 = ("저장", "건조", "예비저장", "본저장", "소독", "살균", "훈증", "수매용",
        "종자용", "가공용", "출하", "예냉", "저온저장", "건조기", "도정", "침종",
        "물온도", "수온", "급수", "난방", "보일러", "하우스 내부 온도 관리")

한계말 = ("한계온도", "동해", "냉해", "저온해", "고온해", "동사", "고사", "피해",
        "장해", "장애", "위험", "경보", "주의보", "얼", "언 피해")

기준말 = (
    # 생육이 시작하거나 멎는 온도. base_temp 의 정의에 맞는 것만.
    "생육최저온도", "생육최저", "발아최저온도", "발아최저", "최저한계",
    "생육정지", "생육이정지", "발육정지", "발육이정지", "자라기시작",
    "생장정지", "생육개시", "발아최저한계",
)

적온말 = ("적온", "적정온도", "최적온도", "알맞은온도", "좋은온도", "적당한온도",
        "가장적당", "잘자라는", "생육온도", "적지온", "지온")


# ⚠ `이상` 이 붙었다고 하한이 아니다. 뒤에 오는 말이 뜻을 뒤집는다.
#       25℃ 이상에서는 생육 정지   → 고온 상한 (upper_temp)
#        5℃ 이상에서 자라기 시작   → 하한 (base_temp)
#   이 둘을 같이 묶었더니 마늘·양파·시금치의 고온 상한값이 base_temp 후보로 올라왔다.
#   base_temp 자리에 25℃ 를 넣으면 적산이 통째로 어긋난다.
멈춤말 = r"(?:정지|멎|멈|생육이?\s*않|불량|휴면|억제|나빠|저하)"
# ⚠ `촉진` 은 넣지 않는다. 잘 자란다는 말이지 자라기 시작한다는 말이 아니다.
#    `18℃ 이상에서 잎 생육이 촉진` 을 base_temp 로 잡으면 마늘이 18℃ 가 된다.
시작말 = r"(?:자라기\s*시작|생육\s*시작|생장\s*시작|싹이?\s*트|발아\s*시작|자라기시작)"
# ⚠ 재배 적지를 말하는 문장을 거른다. 값은 한계온도지 기준온도가 아니다.
#    `겨울철 최저온도가 영하 6℃ 이하로 내려가지 않은 ... 지역`
적지말 = re.compile(r"(?:내려가지\s*않|떨어지지\s*않|되지\s*않는\s*(?:곳|시기|지역))")

위로멈춤 = re.compile(r"(-?\d+(?:\.\d+)?)\s*℃\s*이상[^.\n]{0,16}" + 멈춤말)
위로시작 = re.compile(r"(-?\d+(?:\.\d+)?)\s*℃\s*이상[^.\n]{0,16}" + 시작말)
아래멈춤 = re.compile(r"(-?\d+(?:\.\d+)?)\s*℃\s*이하[^.\n]{0,16}" + 멈춤말)


def 한판정(글):
    """한 덩이의 글만 보고 분류한다. 못 정하면 None."""
    합 = 글.replace(" ", "")
    if any(w in 합 for w in 무관말):
        return "무관"
    if 적지말.search(글):
        return "한계온도"
    # 문장형을 먼저 본다 — 낱말 목록에는 안 걸리지만 뜻이 가장 분명하다.
    if 위로시작.search(글):
        return "기준온도후보"
    if 아래멈춤.search(글):
        # `N℃ 이하에서 동사·고사` 는 생육 하한이 아니라 재해다
        return "한계온도" if re.search(r"이하[^.\n]{0,16}(?:동사|고사|얼|피해)", 글) else "기준온도후보"
    if 위로멈춤.search(글):
        return "상한후보"
    if any(w in 합 for w in 기준말):
        return "기준온도후보"
    if any(w in 합 for w in 적온말):
        return "적온"
    if any(w in 합 for w in 한계말):
        return "한계온도"
    return None


def 분류(이름, 원문, 절=""):
    """무엇에 쓸 값인지 정한다. 애매하면 '확인필요' 로 둔다 — 지어내지 않는다.

    ⚠ 원문을 먼저 보고, 원문으로 못 정할 때만 항목·절 이름을 본다.
       절 이름에 끌려가면 `기상재해및생리장해` 절 안의 `적정온도(18~25℃)` 가
       한계온도로 잘못 분류된다. 실제로 감자에서 그랬다.
    """
    return 한판정(원문) or 한판정(이름) or 한판정(절) or "확인필요"


# ── 문장형 잡기 ───────────────────────────────────────────────────────
# attach.py 가 못 보는 꼴만 모았다. 각 무늬 옆에 실제 원문을 적어 둔다.
문장무늬 = [
    # ❍ 씨감자 싹은 5℃ 이상에서 자라기 시작함
    (re.compile(r"([가-힣\s]{0,14}?)\s*(-?\d+(?:\.\d+)?)\s*℃\s*이상에서[^.\n]{0,20}"
                r"(?:자라기\s*시작|생육\s*시작|발아|싹)"), "생육최저온도"),
    # ㅇ 고온성 작물로 ... 17℃ 이하에서는 생육이 정지됨
    (re.compile(r"(-?\d+(?:\.\d+)?)\s*℃\s*이하에서(?:는)?[^.\n]{0,20}"
                r"(?:생육|생장|발육)[^.\n]{0,6}(?:정지|멈|않)"), "생육최저온도"),
    # ❍ 자라기에 적당한 온도는 14~23℃ / 덩이줄기가 굵어지는 데 좋은 온도는 14~18℃
    (re.compile(r"([가-힣\s]{0,20}?)(?:에\s*)?(?:좋은|적당한|알맞은)\s*온도는?\s*"
                r"(-?\d+(?:\.\d+)?\s*(?:~|∼)\s*-?\d+(?:\.\d+)?\s*℃)"), "적온"),
    # ❍ 잎과 줄기의 발육에는 21℃가 가장 적당
    (re.compile(r"([가-힣\s]{0,20}?)(?:에는|은|는)\s*(-?\d+(?:\.\d+)?)\s*℃\s*가?\s*"
                r"가장\s*적당"), "적온"),
    # ※ 주간 23~24℃, 야간 10~14℃
    (re.compile(r"(주간|낮)\s*(-?\d+(?:\.\d+)?\s*(?:~|∼)?\s*-?\d*(?:\.\d+)?\s*℃)"), "주간적온"),
    (re.compile(r"(야간|밤)\s*(-?\d+(?:\.\d+)?\s*(?:~|∼)?\s*-?\d*(?:\.\d+)?\s*℃)"), "야간적온"),
    # - 적정온도 12~18℃, 습도 80~85%     (앞 절 이름이 예비저장/본저장)
    (re.compile(r"적정\s*온도\s*(-?\d+(?:\.\d+)?\s*(?:~|∼)?\s*-?\d*(?:\.\d+)?\s*℃)"), "적정온도"),
    # (27~30℃에서는 비대 정지)
    (re.compile(r"(-?\d+(?:\.\d+)?\s*(?:~|∼)\s*-?\d+(?:\.\d+)?)\s*℃\s*에서는?\s*"
                r"([가-힣]{2,8})\s*정지"), "상한한계"),
]

# 콜론 꼴 — attach.py 와 같은 자리. 빠진 것이 없는지 대조하려고 같이 뽑는다.
콜론무늬 = re.compile(r"^[■❍○●◦\-*※·\s]*([^:：|]{1,24})[:：](.+)$")
온도말 = ("적온", "한계온도", "생육온도", "온도관리", "가능온도", "발아온도", "저장온도",
        "최적온도", "최저온도", "최고온도", "최저기온", "최고기온", "지온", "적정온도",
        "온도", "기온")


def 값읽기(s):
    """가장 먼저 나오는 온도를 최저·최고로 읽는다.

    ⚠ 괄호 안에 적산온도가 딸려오는 표기가 있다(`발아적온 20℃(적산온도 140℃)`).
       적산온도는 누적값이라 자리가 다르다. 괄호 앞만 본다. attach.py 와 같은 규칙이다.
    """
    s = re.split(r"[(（]", s)[0] if "℃" in re.split(r"[(（]", s)[0] else s
    if "℃" not in s:
        s = s + "℃"     # `27~30` 처럼 무늬가 ℃ 앞을 떼어 넘겨준 경우
    m = 값무늬.search(s)
    if not m:
        return None, None, ""
    if m.group(1) is not None:
        return float(m.group(1)), float(m.group(2)), "범위"
    v = float(m.group(3))
    뒤 = s[m.end():m.end() + 8]
    if "이상" in 뒤:
        return v, None, "이상"
    if "이하" in 뒤:
        return None, v, "이하"
    return v, v, "단일"


def 작물이름(경로):
    이름 = os.path.splitext(os.path.basename(경로))[0]
    return re.sub(r"\s*농작업\s*일정.*$", "", 이름).strip()


def 훑기(서비스):
    본문 = os.path.join(ROOT, 서비스, "결과", "본문")
    나온다 = []
    for r, _, fs in os.walk(본문):
        for f in sorted(fs):
            if not f.lower().endswith(".txt"):
                continue
            p = os.path.join(r, f)
            분류명 = os.path.relpath(r, 본문).split(os.sep)[0]
            작물 = 작물이름(p)
            앞절 = ""
            with io.open(p, encoding="utf-8", errors="replace") as fh:
                for n, raw in enumerate(fh, 1):
                    줄 = " ".join(raw.split())
                    if not 줄:
                        continue
                    if 줄.startswith("■"):
                        앞절 = 줄.lstrip("■ ").split(":")[0].strip()
                    if "℃" not in 줄:
                        continue
                    for 항목, lo, hi, 형태, 꼴 in 한줄(줄, 앞절):
                        나온다.append(dict(
                            서비스=서비스, 분류명=분류명, 작물명=작물, 파일=f, 줄=n,
                            항목=항목, 절=앞절, 쓸모=분류(항목, 줄, 앞절),
                            최저=lo, 최고=hi, 형태=형태, 꼴=꼴, 원문=줄[:160]))
    return 나온다


def 한줄(줄, 앞절):
    """한 줄에서 나올 수 있는 온도를 전부 돌려준다. 같은 값은 한 번만."""
    본 = set()
    결과들 = []

    def 담기(항목, 값글, 꼴):
        lo, hi, 형태 = 값읽기(값글)
        if lo is None and hi is None:
            return
        키 = (항목.replace(" ", ""), lo, hi)
        if 키 in 본:
            return
        본.add(키)
        결과들.append((항목.replace(" ", "") or 앞절 or "이름없음", lo, hi, 형태, 꼴))

    # 1) 콜론 꼴 — attach.py 와 같은 자리
    m = 콜론무늬.match(줄)
    if m:
        이름 = m.group(1).replace(" ", "")
        값 = m.group(2).strip()
        if any(w in 이름 for w in 온도말):
            담기(이름, 값, "콜론")
        elif 값.replace(" ", "").startswith(("온도", "기온", "지온")):
            # `❍ 싹틔우기 : 온도 15~20℃, 습도 80~90%` — 이름이 아니라 값이 온도라고 말한다
            담기(이름 + "온도", 값, "콜론")

    # 2) 문장 꼴 — 여기가 이 스크립트의 존재 이유다
    for 무늬, 기본이름 in 문장무늬:
        for mm in 무늬.finditer(줄):
            조각 = [g for g in mm.groups() if g]
            값글 = next((g for g in reversed(조각) if re.search(r"\d", g)), None)
            if not 값글:
                continue
            앞말 = next((g for g in 조각 if not re.search(r"\d", g)), "")
            앞 = 앞말.strip().replace(" ", "")
            이름 = 기본이름 if (not 앞 or 앞 in 기본이름) else 앞 + 기본이름
            담기(이름[:30], 값글, "문장")

    # 3) 위 어느 것도 안 걸렸는데 ℃ 가 있다 — 놓치지 않으려고 통째로 담아 둔다
    if not 결과들:
        담기(앞절 or "미분류", 줄, "나머지")
    return 결과들


def 기존읽기():
    p = os.path.join(ROOT, "농작업일정", "결과", "첨부_온도.csv")
    if not os.path.exists(p):
        return set()
    있다 = set()
    with io.open(p, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            있다.add((r["작물명"], r["최저"], r["최고"]))
    return 있다


def 쓰기(경로, 행들):
    if not 행들:
        return
    os.makedirs(os.path.dirname(경로), exist_ok=True)
    with io.open(경로, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(행들[0].keys()))
        w.writeheader()
        w.writerows(행들)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--서비스", default="농작업일정")
    ap.add_argument("--작물", default=None, help="이 작물만 원문과 함께 보여준다")
    ap.add_argument("--빠진것", action="store_true", help="기존 첨부_온도.csv 에 없는 것만")
    a = ap.parse_args()

    행들 = 훑기(a.서비스)
    기존 = 기존읽기()

    def 문자(v):
        return "" if v is None else ("%g" % v)

    for r in 행들:
        r["기존에있음"] = "Y" if (r["작물명"], 문자(r["최저"]), 문자(r["최고"])) in 기존 else "N"

    if a.작물:
        골라 = [r for r in 행들 if a.작물 in r["작물명"]]
        print("%s — %d건" % (a.작물, len(골라)))
        for r in 골라:
            print("  줄%-4d [%-7s] %-16s %6s~%-6s %s"
                  % (r["줄"], r["쓸모"], r["항목"][:16], 문자(r["최저"]), 문자(r["최고"]),
                     ("기존O" if r["기존에있음"] == "Y" else "새것 ")))
            print("        %s" % r["원문"][:110])
        return

    보일것 = [r for r in 행들 if r["기존에있음"] == "N"] if a.빠진것 else 행들
    쓰기(os.path.join(결과, "온도_전체.csv"), 행들)
    후보 = [r for r in 행들 if r["쓸모"] == "기준온도후보"]
    쓰기(os.path.join(결과, "온도_기준온도후보.csv"), 후보)
    상한 = [r for r in 행들 if r["쓸모"] == "상한후보"]
    쓰기(os.path.join(결과, "온도_상한후보.csv"), 상한)

    print("본문에서 뽑은 온도 %d건 (기존 첨부_온도.csv 372행)" % len(행들))
    print("  그중 기존에 없던 것 %d건" % sum(1 for r in 행들 if r["기존에있음"] == "N"))
    print()
    print("쓸모별")
    for k, v in collections.Counter(r["쓸모"] for r in 행들).most_common():
        새 = sum(1 for r in 행들 if r["쓸모"] == k and r["기존에있음"] == "N")
        print("   %-12s %5d   (새것 %d)" % (k, v, 새))
    print()
    print("꼴별")
    for k, v in collections.Counter(r["꼴"] for r in 행들).most_common():
        print("   %-8s %5d" % (k, v))
    print()
    print("★ 기준온도후보 %d건 — 작물별" % len(후보))
    for k, v in sorted(collections.Counter(r["작물명"] for r in 후보).items()):
        print("   %-22s %d" % (k, v))
    print()
    print("→ %s" % os.path.join(결과, "온도_전체.csv"))
    print("→ %s" % os.path.join(결과, "온도_기준온도후보.csv"))
    print("→ %s  (crops.upper_temp 후보 %d건)" % (os.path.join(결과, "온도_상한후보.csv"), len(상한)))
    print("\n⚠ `기준온도후보` 는 후보일 뿐이다. 원문을 읽고 사람이 정해야 한다.")
    print("   적온을 base_temp 로 쓰면 적산이 전부 어긋난다 (CLAUDE.md).")


if __name__ == "__main__":
    main()
