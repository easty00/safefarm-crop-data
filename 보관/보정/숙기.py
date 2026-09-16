# -*- coding: utf-8 -*-
"""
OCR 로 되살린 글에서 숙기(조·중·만생)를 찾아 `품종_숙기.csv` 의 빈칸을 메운다.

원본검수_2026-09-15.md §3 :
품종정보 첨부 PDF 191건이 글자층 없는 스캔본이라 본문이 비어 있었다. 그중 38건이
14작물(벼 20 · 양파 9 · 마늘 3 · 상추 2 · 토마토 2 · 배추 1 · 파 1)이다.
`ocr.py` 가 글자를 냈으니 이제 값을 옮긴다.

⚠ 이 스크립트는 **OCR 로 읽은 글자**를 다룬다. 원문이 아니다.
   - 채운 값은 `숙기출처 = OCR본문` 으로 표시한다. 어디서 왔는지 흐려지면 안 된다.
   - 이미 값이 있는 칸은 절대 덮지 않는다.
   - 원문 문장을 `숙기원문` 에 그대로 남긴다. 사람이 뒤에 확인할 수 있어야 한다.

⚠ 한 문서에 숙기 말이 여러 번 나오고 서로 다르다.

    양파 대관황   "숙기는 조중생으로 히구마와 비슷"     ← 숙기를 직접 말한 문장
                 "초형은 직립형이며 생육은 중생종임"    ← 생육 특성을 말하는 문장
    마늘 다산     "만생종이므로 수확시기가 늦어"        ← 숙기
                 "재배지역 확대를 위한 조중생종 품종 육성"  ← 앞으로 만들 품종 이야기다

  먼저 나오는 것을 집으면 틀린다. 문장 꼴에 등급을 매겨 가장 확실한 것을 고른다.
  등급이 같은데 값이 갈리면 채우지 않고 `갈림` 으로 남긴다 — 지어내지 않는다.

    python 숙기.py            결과/숙기_OCR후보.csv 를 만든다 (원본은 안 건드림)
    python 숙기.py --고침      품종_숙기.csv 의 빈칸을 메운다 (백업 남김)
    python 숙기.py --작물 양파   한 작물만 원문과 함께 보여준다
"""
import os
import io
import re
import csv
import shutil
import argparse
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OCR본문 = os.path.join(ROOT, "보정", "결과", "ocr본문", "품종정보", "본문")
결과 = os.path.join(ROOT, "보정", "결과")
백업 = os.path.join(결과, "숙기_백업")

대상 = [
    os.path.join(ROOT, "품종정보", "결과", "품종_숙기.csv"),
    os.path.join(ROOT, "선정작물", "결과", "14작물", "품종정보_품종_숙기.csv"),
]

# 긴 것부터 찾아야 `중만생` 이 `중생` 으로 잘리지 않는다.
숙기말 = ("극조생", "중만생", "조중생", "중조생", "조생", "중생", "만생")
# 표준 네 가지로 맞춘다. `조중생` 처럼 걸친 것은 그대로 두고 사람이 정하게 한다.
표준 = {"극조생": "극조생", "조생": "조생", "중생": "중생",
       "중만생": "중만생", "만생": "만생"}

# 등급이 높을수록 믿을 만하다. 숫자가 같은데 값이 다르면 채우지 않는다.
무늬들 = [
    (3, re.compile(r"숙기[는은]?\s*[:：]?\s*(%s)" % "|".join(숙기말))),
    (3, re.compile(r"(%s)종?\s*(?:이므로|이라|이고|이며|임)" % "|".join(숙기말))),
    (2, re.compile(r"(?:가|나|다|라|마)\.\s*(%s)종?\s*[,，]" % "|".join(숙기말))),
    (2, re.compile(r"^\s*[○ㅇo०0]\s*(%s)종?\b" % "|".join(숙기말), re.M)),
    (1, re.compile(r"(%s)종" % "|".join(숙기말))),
    (0, re.compile(r"(%s)" % "|".join(숙기말))),
]
# 등급 0 은 그냥 낱말이 스쳐 지나간 것이다. 채우지 않는다.
#   자두 퍼플퀸에서 `대석조생` 이 걸렸는데, 그건 **화분친으로 적힌 다른 품종 이름**이었다.
#   표가 섞인 OCR 글에서는 이런 일이 흔하다.
최소등급 = 1
# `준조생` 은 조생이 아니고 `조중생` 은 조생도 중생도 아니다. 표준 등급으로 접지 않는다.
# ⚠ 찾은 자리 **바로 앞 두 글자**를 본다. 앞뒤를 잘라 앞보기(lookahead)로 확인하려다
#    `준조생종` 의 `준` 뒤에 `조` 한 글자만 남아 헛돌았고, 조령이 `조생` 으로 들어갔다.
걸친앞말 = ("준", "조중", "중조", "반")
# 이 말이 든 문장의 숙기는 이 품종의 숙기가 아니다. 앞으로 만들 품종 이야기다.
남얘기 = ("육성", "보완을 요하는", "육성 목표", "개발 예정", "와 비슷한 품종",
        "대비 품종", "대조품종", "표준품종")


def 아이디(f):
    m = re.match(r"^(\d+)_", f)
    return m.group(1) if m else None


def 문장들(글):
    """문장 단위로 자른다. OCR 결과는 줄바꿈이 제멋대로라 마침표와 글머리로 자른다."""
    글 = 글.replace("\r", "")
    토막 = re.split(r"(?<=[.。])\s+|\n+|(?=\s[○ㅇ]\s)|(?=\s[가-힣]\.\s)", 글)
    return [" ".join(t.split()) for t in 토막 if t and t.strip()]


def 찾기(글):
    """문장마다 숙기를 찾고 등급을 매긴다. 가장 높은 등급만 남긴다."""
    후보 = []
    스친것 = None
    for 문장 in 문장들(글):
        if any(w in 문장 for w in 남얘기):
            continue
        for 등급, 무늬 in 무늬들:
            m = 무늬.search(문장)
            if not m:
                continue
            # `준조생종` 을 `조생` 으로 잘라 쓰면 안 된다. 논벼 조령이 그랬다.
            if 문장[max(0, m.start() - 2):m.start()].endswith(걸친앞말):
                스친것 = 스친것 or (등급, "걸친등급", 문장[:150])
                break
            후보.append((등급, m.group(1), 문장[:150]))
            break
    쓸것 = [c for c in 후보 if c[0] >= 최소등급]
    if not 쓸것:
        # 등급이 모자라거나 걸친 등급뿐이면 채우지 않고 사람에게 넘긴다
        낮은 = 후보 or ([스친것] if 스친것 else [])
        if 낮은:
            return None, "약함", 낮은[0][1], 낮은[0][2]
        return None, "", "", ""
    맨위 = max(c[0] for c in 쓸것)
    위것 = [c for c in 쓸것 if c[0] == 맨위]
    값들 = {c[1] for c in 위것}
    if len(값들) > 1:
        return None, "갈림", " / ".join(sorted(값들)), 위것[0][2]
    말 = 위것[0][1]
    return 표준.get(말), ("등급%d" % 맨위), 말, 위것[0][2]


def ocr읽기():
    나온다 = {}
    if not os.path.isdir(OCR본문):
        return 나온다
    for r, _, fs in os.walk(OCR본문):
        for f in fs:
            if not f.lower().endswith(".txt"):
                continue
            k = 아이디(f)
            if not k:
                continue
            with io.open(os.path.join(r, f), encoding="utf-8", errors="replace") as fh:
                나온다[k] = (fh.read(), os.path.relpath(os.path.join(r, f), ROOT))
    return 나온다


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--고침", action="store_true")
    ap.add_argument("--작물", default=None)
    a = ap.parse_args()

    글들 = ocr읽기()
    if not 글들:
        print("OCR 결과가 없습니다. 먼저  python ocr.py  를 돌리십시오.")
        return
    print("OCR 본문 %d건" % len(글들))

    표 = 대상[0]
    with io.open(표, encoding="utf-8-sig") as f:
        행들 = list(csv.DictReader(f))
        칸 = list(행들[0].keys())

    기록 = []
    채울것 = {}
    for r in 행들:
        k = r["cntntsNo"]
        if k not in 글들:
            continue
        글, 경로 = 글들[k]
        값, 등급, 말, 문장 = 찾기(글)
        이미 = bool(r["숙기"].strip())
        기록.append(dict(cntntsNo=k, 작물명=r["작물명"], 품종명=r["품종명"],
                        기존숙기=r["숙기"], OCR숙기=값 or "", 등급=등급,
                        찾은말=말, 원문=문장, 파일=경로,
                        할일=("이미 있음" if 이미 else
                             "채움" if 값 else
                             "사람이 볼 것" if 등급 in ("갈림", "약함") else "못 찾음")))
        if 값 and not 이미:
            채울것[k] = (값, 말, 문장, 경로)

    if a.작물:
        골라 = [r for r in 기록 if a.작물 in r["작물명"]]
        print("\n%s — %d건" % (a.작물, len(골라)))
        for r in 골라:
            print("  %-22s %-6s %-8s %s" % (r["품종명"][:22], r["OCR숙기"] or "—",
                                            r["등급"], r["할일"]))
            print("      %s" % r["원문"][:120])
        return

    print("\n할 일별")
    for k, v in collections.Counter(r["할일"] for r in 기록).most_common():
        print("   %-12s %d" % (k, v))
    print("\n작물별로 채울 것")
    for k, v in sorted(collections.Counter(
            r["작물명"] for r in 기록 if r["할일"] == "채움").items()):
        print("   %-12s %d" % (k, v))

    채움 = [r for r in 기록 if r["할일"] == "채움"]
    if 채움:
        print("\n채울 %d건 — 이 원문이 그 품종의 숙기를 말하는지 보십시오" % len(채움))
        for r in 채움:
            print("   %-8s %-20s → %-5s (%s)"
                  % (r["작물명"][:8], r["품종명"][:20], r["OCR숙기"], r["등급"]))
            print("      %s" % r["원문"][:118])

    갈림 = [r for r in 기록 if r["할일"] == "사람이 볼 것"]
    if 갈림:
        print("\n⚠ 확실하지 않아 채우지 않은 것 %d건 — 원문을 읽고 손으로 정할 것" % len(갈림))
        for r in 갈림[:10]:
            print("   %-10s %-18s %s (%s)"
                  % (r["작물명"][:10], r["품종명"][:18], r["찾은말"], r["등급"]))
            print("      %s" % r["원문"][:110])

    os.makedirs(결과, exist_ok=True)
    보고 = os.path.join(결과, "숙기_OCR후보.csv")
    if 기록:
        with io.open(보고, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(기록[0].keys()))
            w.writeheader()
            w.writerows(기록)
        print("\n→ %s" % 보고)

    if not a.고침:
        print("\n⚠ 채우기 전에 위 CSV 의 `원문` 칸을 읽으십시오. OCR 은 글자를 틀리게 읽습니다.")
        print("   실제로 채우려면  python 숙기.py --고침")
        return

    바뀜 = 0
    for p in 대상:
        if not os.path.exists(p):
            continue
        with io.open(p, encoding="utf-8-sig") as f:
            그행들 = list(csv.DictReader(f))
            그칸 = list(그행들[0].keys())
        b = os.path.join(백업, os.path.relpath(p, ROOT))
        os.makedirs(os.path.dirname(b), exist_ok=True)
        if not os.path.exists(b):
            shutil.copy2(p, b)
        for r in 그행들:
            k = r["cntntsNo"]
            if k in 채울것 and not r["숙기"].strip():
                값, 말, 문장, 경로 = 채울것[k]
                r["숙기"] = 값
                r["숙기출처"] = "OCR본문"
                r["숙기원문"] = "%s … (%s)" % (문장[:110], 경로)
                바뀜 += 1
        with io.open(p, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=그칸)
            w.writeheader()
            w.writerows(그행들)
        print("%s 고침" % os.path.relpath(p, ROOT))
    print("모두 %d칸 채움 (백업 %s)" % (바뀜, os.path.relpath(백업, ROOT)))
    print("⚠ 채운 칸은 `숙기출처=OCR본문` 이다. 원문에서 온 값과 반드시 구분할 것.")


if __name__ == "__main__":
    main()
