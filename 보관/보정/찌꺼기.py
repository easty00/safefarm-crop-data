# -*- coding: utf-8 -*-
"""
추출할 때 섞여 들어온 찌꺼기를 걷어낸다. 값은 건드리지 않는다.

원본검수_2026-09-15.md §4 · §5 두 건이다.

1) HTML 엔티티 865곳          `&#8228;` `&#160;` … 품종정보 CSV 6개의 `주요특성` 칸
   이 칸은 Claude 에게 문장으로 넘길 자리라 그냥 두면 농민 화면에 `&#8228;` 이 보인다.

2) hwp(OLE) 제어코드 99건     `漠杳` `氠瑢` `浴瑣` …
   HWP 내부 제어태그의 ASCII 바이트를 2바이트 UTF-16LE 로 잘못 읽어 생긴 가짜 한자다.
       漠杳 = 6F 20 67 73 = "o gs"      氠瑢 = 6C 20 74 62 = "l tb"
   글자가 아니므로 지워도 잃을 것이 없다. 다만 진짜 한자는 지우면 안 되므로
   "ASCII 로 되돌렸을 때 인쇄 가능한 글자만 나오는가" 를 따져서 그것만 지운다.

3) 생짜 마크업                `<SPAN STYLE="font-size:15pt;">` 같은 것.
   95605_대영.txt 는 91,927자 중 76%가 이것이다.

    python 찌꺼기.py            무엇이 얼마나 바뀌는지만 보여준다 (파일은 안 고침)
    python 찌꺼기.py --고침      실제로 고친다. 고치기 전 파일은 결과/찌꺼기_백업/ 에 둔다
"""
import os
import io
import re
import csv
import html
import shutil
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
백업 = os.path.join(ROOT, "보정", "결과", "찌꺼기_백업")
보고 = os.path.join(ROOT, "보정", "결과", "찌꺼기_보고.csv")

마크업 = re.compile(r"</?SPAN\b[^>]*>", re.I)
한자덩어리 = re.compile(r"[㐀-鿿]+")
지운것 = {}   # 지운 가짜한자를 모아 둔다. 진짜 한자를 지우고 있지 않은지 눈으로 보려고.


# HWP 제어태그가 가짜 한자로 새어 나온 것들. 이 목록에 있는 토막으로만 이루어진
# 덩어리를 지운다. "ASCII 로 되돌려 소문자만 나오면 지운다" 같은 규칙은 쓰면 안 된다 —
# 진짜 한자가 걸린다. 실제로 주간농사정보의 `정동(正東)에서` 가 그 규칙에 걸렸다.
#   正 U+6B63 → 63 6B = "ck"   東 U+6771 → 71 67 = "qg"   둘 다 소문자다.
# 전 자료를 훑어 모은 목록이다. 새 자료를 받으면 --낯선 으로 빠진 것이 없는지 본다.
찌꺼기토막 = {
    "氠瑢": "l tb", "漠杳": "o gs", "浴瑣": "tmct", "桤灧": "hd gp",
    "灳瑣": "sp ct", "湰灧": "np pg", "湯慴": "no ta", "湯湷": "no nw",
    "歭扯": "km bo", "潴景": "ot fo", "敤敱": "ed eq", "汤捯": "ld co",
    "捤獥": "cd se", "楴䵴": "ti Mt",
}
찌꺼기무늬 = re.compile("(?:%s)+" % "|".join(sorted(찌꺼기토막, key=len, reverse=True)))

# 한 글자짜리 찌꺼기. 표 칸의 숫자를 앞뒤로 감싸고 있다.
#     ...합 계\n浵╦288,215浵ࡦ\n22,010...
# 浵(U+6D75)·浫(U+6D6B) 은 농업 문서에 나올 일이 없는 벽자라 통째로 지워도 된다.
# ࡦ(U+0866, 사마리아 문자)도 같은 자리에 붙어 나오는 찌꺼기다.
단독찌꺼기 = re.compile("[浵浫ࡦ]")


def 가짜한자인가(덩어리):
    """알려진 제어토막만으로 이루어졌으면 찌꺼기다.

    한 토막이라도 낯선 한자가 섞여 있으면 손대지 않는다. 지우는 쪽보다
    남기는 쪽이 안전하다 — 남은 것은 눈에 띄지만 지운 것은 영영 모른다.
    """
    if len(덩어리) < 2:
        return False
    m = 찌꺼기무늬.fullmatch(덩어리)
    return m is not None


def 씻기(글):
    """엔티티 풀기 + 가짜한자 지우기 + 마크업 지우기. 무엇을 몇 번 했는지 같이 돌려준다."""
    셈 = dict(엔티티=0, 가짜한자=0, 마크업=0)

    셈["엔티티"] = len(re.findall(r"&#?\w{2,8};", 글))
    if 셈["엔티티"]:
        글 = html.unescape(글)

    셈["마크업"] = len(마크업.findall(글))
    if 셈["마크업"]:
        글 = 마크업.sub("", 글)

    def 치환(m):
        if 가짜한자인가(m.group(0)):
            치환.n += 1
            지운것[m.group(0)] = 지운것.get(m.group(0), 0) + 1
            return ""
        return m.group(0)

    치환.n = 0
    글 = 한자덩어리.sub(치환, 글)
    n단독 = len(단독찌꺼기.findall(글))
    if n단독:
        글 = 단독찌꺼기.sub("", 글)
        지운것["(한글자)"] = 지운것.get("(한글자)", 0) + n단독
    셈["가짜한자"] = 치환.n + n단독

    # ⚠ 공백은 손대지 않는다. 표를 칸 너비로 맞춰 둔 본문이 있어 줄이면 칸이 어긋난다.
    return 글, 셈


def 대상파일():
    """CSV 와 본문 txt 전부. 원본(raw/·첨부/·파일/)은 절대 건드리지 않는다."""
    나온다 = []
    for r, ds, fs in os.walk(ROOT):
        ds[:] = [d for d in ds
                 if d not in ("raw", "첨부", "파일", "보관", ".claude", "찌꺼기_백업", "ocr본문")]
        for f in fs:
            if f.lower().endswith((".csv", ".txt")) and "결과" in r:
                나온다.append(os.path.join(r, f))
    return sorted(나온다)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--고침", action="store_true", help="실제로 파일을 고친다")
    ap.add_argument("--낯선", action="store_true",
                    help="목록에 없는 한자 덩어리를 세어 본다. 새 자료를 받은 뒤 볼 것")
    a = ap.parse_args()

    if a.낯선:
        남은 = {}
        for p in 대상파일():
            try:
                with io.open(p, encoding="utf-8-sig") as f:
                    t = f.read()
            except (UnicodeDecodeError, OSError):
                continue
            for m in 한자덩어리.finditer(t):
                g = m.group(0)
                if not 가짜한자인가(g):
                    남은[g] = 남은.get(g, 0) + 1
        print("목록에 없는 한자 덩어리 %d종" % len(남은))
        print("(대부분 진짜 한자다. 소문자 ASCII 로 되돌아가는 것이 있으면 찌꺼기토막에 넣을 것)")
        for k, v in sorted(남은.items(), key=lambda x: -x[1])[:40]:
            try:
                s = k.encode("utf-16-le").decode("latin-1")
            except UnicodeEncodeError:
                s = ""
            수상 = " ← 수상함" if re.fullmatch(r"[a-z ]+", s or "x") else ""
            print("   %6d  %-16s %r%s" % (v, k[:16], s[:40], 수상))
        return

    기록 = []
    for p in 대상파일():
        try:
            with io.open(p, encoding="utf-8-sig", errors="strict") as f:
                원 = f.read()
        except (UnicodeDecodeError, OSError):
            continue
        새, 셈 = 씻기(원)
        if 새 == 원:
            continue
        기록.append(dict(파일=os.path.relpath(p, ROOT), 엔티티=셈["엔티티"],
                        가짜한자=셈["가짜한자"], 마크업=셈["마크업"],
                        전=len(원), 후=len(새), 줄어듦=len(원) - len(새)))
        if a.고침:
            bp = os.path.join(백업, os.path.relpath(p, ROOT))
            os.makedirs(os.path.dirname(bp), exist_ok=True)
            if not os.path.exists(bp):
                shutil.copy2(p, bp)
            bom = p.lower().endswith(".csv")
            with io.open(p, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as f:
                f.write(새)

    if not 기록:
        print("고칠 것이 없습니다.")
        return
    기록.sort(key=lambda r: -r["줄어듦"])
    print("%s %d개 파일" % ("고쳤습니다:" if a.고침 else "고칠 것 (미리보기):", len(기록)))
    print("%-58s %7s %7s %7s %9s" % ("파일", "엔티티", "가짜한자", "마크업", "줄어듦"))
    for r in 기록[:25]:
        print("%-58s %7d %7d %7d %9d"
              % (r["파일"][-58:], r["엔티티"], r["가짜한자"], r["마크업"], r["줄어듦"]))
    if len(기록) > 25:
        print("... 외 %d개" % (len(기록) - 25))
    print("\n합계  엔티티 %d · 가짜한자 %d · 마크업 %d"
          % (sum(r["엔티티"] for r in 기록), sum(r["가짜한자"] for r in 기록),
             sum(r["마크업"] for r in 기록)))

    if 지운것:
        print("\n지운 가짜한자 %d종 — 진짜 한자가 섞였는지 눈으로 볼 것" % len(지운것))
        for k, v in sorted(지운것.items(), key=lambda x: -x[1])[:20]:
            print("   %6d  %-14s → %r" % (v, k, k.encode("utf-16-le").decode("latin-1")))

    os.makedirs(os.path.dirname(보고), exist_ok=True)
    with io.open(보고, "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(기록[0].keys()))
        wr.writeheader()
        wr.writerows(기록)
    print("보고 → %s" % 보고)
    if not a.고침:
        print("실제로 고치려면  python 찌꺼기.py --고침")


if __name__ == "__main__":
    main()
