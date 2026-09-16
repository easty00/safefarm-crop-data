# -*- coding: utf-8 -*-
"""
원본검수가 "범위 밖" 이라며 넘긴 것들을 실제로 본다.

원본검수_2026-09-15.md §11 의 네 가지다. 나머지 둘(스캔 PDF 내용·라이선스)은
ocr.py 와 사람 몫이다.

  ① 주간농사정보 첨부 192건    글자는 다 뽑혔으나 원본과 값 대조를 안 했다
  ② 14작물 밖 82작물           형식만 봤고 값은 안 봤다
  ③ 참고수치표 15,525칸        점검결과.md ⑤ 가 지적한 그대로 아직 아무도 안 읽었다
  ④ 검수 ⑦ 오탐 93%           열 번호가 아니라 행 이름으로 맞대야 한다 (확인필요 §4-1)

    python 대조.py            넷 다
    python 대조.py --주간      ① 만
    python 대조.py --작물       ② 만
    python 대조.py --참고표     ③ 만
"""
import os
import io
import re
import csv
import zipfile
import html
import argparse
import collections
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
결과 = os.path.join(ROOT, "보정", "결과")


def 쓰기(p, 행들):
    if not 행들:
        return
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with io.open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(행들[0].keys()))
        w.writeheader()
        w.writerows(행들)


# ── ① 주간농사정보 첨부 ↔ 본문 ───────────────────────────────────────
def hwpx조각(p):
    """hwpx 를 직접 풀어 글자 조각을 돌려준다. 저장된 본문과 맞대려고 따로 뽑는 것이다."""
    with zipfile.ZipFile(p) as z:
        이름들 = sorted(n for n in z.namelist() if re.match(r"Contents/section\d+\.xml", n))
        xml = "".join(z.read(n).decode("utf-8", "replace") for n in 이름들)
    조각 = re.findall(r"<hp:t[^>]*>(.*?)</hp:t>", xml, re.S)
    표수 = len(re.findall(r"<hp:tbl[ >]", xml))
    return [html.unescape(re.sub(r"<[^>]+>", "", c)) for c in 조각], 표수


def 주간대조():
    첨부 = os.path.join(ROOT, "주간농사정보", "결과", "첨부")
    본문 = os.path.join(ROOT, "주간농사정보", "결과", "본문")
    # ⚠ 본문 파일명은 `11호_11호_주간농사정보 제11호 (…).txt` 처럼 호수가 겹쳐 붙어 있다.
    #    첨부는 `11호_주간농사정보 제11호 (…).hwpx` 다. 이름을 통째로 맞대면 192건 전부
    #    "짝 없음" 이 된다. 연도 폴더 + 뒤쪽이 맞는지로 짝을 짓는다.
    def 씨앗(경로, 밑):
        해 = os.path.relpath(os.path.dirname(경로), 밑).split(os.sep)[0]
        줄기 = os.path.splitext(os.path.basename(경로))[0]
        줄기 = re.sub(r"^(\d+호_)(?=\1)", "", 줄기)     # 겹친 `11호_11호_` 를 한 번만
        return (해, 줄기)

    짝 = {}
    for r, _, fs in os.walk(첨부):
        for f in fs:
            p = os.path.join(r, f)
            짝.setdefault(씨앗(p, 첨부), [None, None])[0] = p
    for r, _, fs in os.walk(본문):
        for f in fs:
            p = os.path.join(r, f)
            k = 씨앗(p, 본문)
            if k in 짝:
                짝[k][1] = p
    기록 = []
    누락말 = collections.Counter()
    for k, (ap, tp) in sorted(짝.items()):
        이름 = "%s/%s" % k
        if not ap or not tp:
            기록.append(dict(파일=이름, 조각=0, 누락=0, 회수율="", 표=0, 비고="짝 없음"))
            continue
        try:
            조각, 표수 = hwpx조각(ap)
        except Exception as e:
            기록.append(dict(파일=이름, 조각=0, 누락=0, 회수율="", 표=0, 비고="풀기 실패 %s" % e))
            continue
        with io.open(tp, encoding="utf-8", errors="replace") as f:
            글 = html.unescape(f.read())
        볼것 = [c for c in 조각 if len(c.strip()) > 4]
        빠진 = [c for c in 볼것 if c.strip() not in 글]
        for c in 빠진:
            # 그림 설명문인지 값이 든 글인지 갈라 센다
            종류 = ("그림설명" if ("그림입니다" in c or "pixel" in c or "사각형입니다" in c)
                  else "숫자있음" if re.search(r"\d", c) else "글자만")
            누락말[종류] += 1
        기록.append(dict(파일=이름[:60], 조각=len(볼것), 누락=len(빠진),
                        회수율="%.3f" % (1 - len(빠진) / max(len(볼것), 1)),
                        표=표수, 비고=""))
    좋음 = [r for r in 기록 if r["회수율"]]
    print("① 주간농사정보 첨부 %d건 대조" % len(기록))
    if 좋음:
        비율 = [float(r["회수율"]) for r in 좋음]
        print("   조각 회수율  최소 %.1f%% · 중앙 %.1f%%" % (min(비율) * 100,
                                                    statistics.median(비율) * 100))
        print("   조각 %d개 중 본문에서 못 찾은 것 %d개 (%.2f%%)"
              % (sum(r["조각"] for r in 좋음), sum(r["누락"] for r in 좋음),
                 sum(r["누락"] for r in 좋음) * 100 / max(sum(r["조각"] for r in 좋음), 1)))
        print("   못 찾은 조각의 종류 : %s" % dict(누락말))
        print("   hwpx 안의 표 %d개" % sum(r["표"] for r in 좋음))
        나쁨 = sorted(좋음, key=lambda r: float(r["회수율"]))[:8]
        print("   회수율 낮은 것")
        for r in 나쁨:
            print("      %.1f%%  조각%4d 누락%3d  %s"
                  % (float(r["회수율"]) * 100, r["조각"], r["누락"], r["파일"][:46]))
    탈 = [r for r in 기록 if r["비고"]]
    if 탈:
        print("   ⚠ 짝이 없거나 못 푼 것 %d건" % len(탈))
        for r in 탈[:6]:
            print("      %s — %s" % (r["파일"][:46], r["비고"]))
    쓰기(os.path.join(결과, "대조_주간농사정보.csv"), 기록)
    print("   → 대조_주간농사정보.csv\n")


# ── ② 14작물 밖 82작물 ───────────────────────────────────────────────
# 값이 범위를 벗어났는지 본다. ⚠ 범위 안이면 뜻이 틀려도 안 걸린다(점검결과.md ④와 같다).
범위 = {"온도": (-60, 60), "월": (1, 12), "일": (1, 31), "일수": (1, 400),
       "적산온도": (50, 5000)}


def 작물검사():
    열넷 = set()
    p14 = os.path.join(ROOT, "선정작물", "결과", "14작물")
    for f in os.listdir(p14):
        if not f.endswith(".csv"):
            continue
        with io.open(os.path.join(p14, f), encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                if r.get("_선정작물"):
                    열넷.update(x.strip() for x in r["_선정작물"].split("|"))

    이상 = []
    셈 = collections.Counter()
    볼것 = [
        (os.path.join(ROOT, "농작업일정", "결과", "첨부_온도.csv"), "작물명",
         [("최저", "온도"), ("최고", "온도")]),
        (os.path.join(ROOT, "적산온도", "결과", "적산온도.csv"), "작물",
         [("값최소", "적산온도"), ("값최대", "적산온도"),
          ("일수최소", "일수"), ("일수최대", "일수")]),
        (os.path.join(ROOT, "농작업일정", "결과", "첨부_일수.csv"), "작물명",
         [("최소", "일수"), ("최대", "일수")]),
        (os.path.join(ROOT, "품종정보", "결과", "생육일수.csv"), "작물명",
         [("일수", "일수")]),
    ]
    for p, 작물칸, 칸들 in 볼것:
        if not os.path.exists(p):
            continue
        with io.open(p, encoding="utf-8-sig") as fh:
            for n, r in enumerate(csv.DictReader(fh), 2):
                작물 = (r.get(작물칸) or "").strip()
                밖 = 작물 not in 열넷
                셈["밖" if 밖 else "안"] += 1
                for 칸, 종류 in 칸들:
                    v = (r.get(칸) or "").strip()
                    if not v:
                        continue
                    try:
                        x = float(v)
                    except ValueError:
                        이상.append(dict(파일=os.path.basename(p), 줄=n, 작물=작물,
                                       칸=칸, 값=v, 왜="숫자가 아님",
                                       범위="14작물 밖" if 밖 else "14작물"))
                        continue
                    lo, hi = 범위[종류]
                    if not (lo <= x <= hi):
                        이상.append(dict(파일=os.path.basename(p), 줄=n, 작물=작물,
                                       칸=칸, 값=v, 왜="%s 범위 %g~%g 밖" % (종류, lo, hi),
                                       범위="14작물 밖" if 밖 else "14작물"))
    print("② 14작물 밖까지 값 검사")
    print("   검사한 행 : 14작물 %d · 그 밖 %d" % (셈["안"], 셈["밖"]))
    print("   범위를 벗어난 값 %d건" % len(이상))
    # 같은 작물·같은 값이 판본마다 되풀이된다. 접어서 보인다 — 전부는 CSV 에 있다.
    묶음 = collections.Counter((r["범위"], r["작물"], r["파일"], r["값"], r["왜"]) for r in 이상)
    for (범위칸, 작물, 파일, 값, 왜), n in 묶음.most_common(12):
        print("      [%s] %-10s %-20s = %-8s %s  (%d곳)"
              % (범위칸, 작물[:10], 파일[:20], 값, 왜, n))
    if len(묶음) > 12:
        print("      ... 외 %d종" % (len(묶음) - 12))
    print("   ⚠ 범위 안이면 뜻이 틀려도 여기 안 걸린다. 그건 사람이 원문을 읽어야 한다.")
    쓰기(os.path.join(결과, "대조_값범위.csv"), 이상)
    print("   → 대조_값범위.csv\n")


# ── ③ 참고수치표 15,525칸 ────────────────────────────────────────────
규칙될말 = ("이상", "이하", "미만", "초과", "℃", "이내", "위험", "주의", "경보",
         "발령", "한계", "기준")


def 참고표():
    p = os.path.join(ROOT, "재해규칙", "결과", "참고수치표.csv")
    with io.open(p, encoding="utf-8-sig") as f:
        행들 = list(csv.DictReader(f))
    표들 = collections.defaultdict(list)
    for r in 행들:
        표들[(r["출처파일"], r["표번호"])].append(r)

    후보 = []
    for (파일, 번호), 칸들 in 표들.items():
        머리 = sorted({c["표머리"] for c in 칸들 if c["표머리"]})
        값들 = [c["값"] for c in 칸들]
        점수 = sum(1 for v in 값들 if any(w in v for w in 규칙될말))
        온도수 = sum(1 for v in 값들 if "℃" in v)
        후보.append(dict(출처파일=파일[:60], 표번호=번호, 칸수=len(칸들),
                       표머리=" | ".join(머리)[:90], 규칙될칸=점수, 온도칸=온도수,
                       계열=칸들[0]["계열"], 연도=칸들[0]["연도"]))
    후보.sort(key=lambda r: (-r["온도칸"], -r["규칙될칸"]))
    쓸만 = [r for r in 후보 if r["온도칸"] >= 3 or r["규칙될칸"] >= 5]
    # 월간회보는 같은 표를 달마다 다시 싣는다. 표머리로 접지 않으면 같은 표가 12번 보인다.
    종류 = collections.OrderedDict()
    for r in 쓸만:
        키 = (r["표머리"], r["칸수"])
        종류.setdefault(키, {**r, "판본수": 0, "연도들": set()})
        종류[키]["판본수"] += 1
        종류[키]["연도들"].add(r["연도"])
    print("③ 참고수치표 %d칸 / 표 %d개" % (len(행들), len(표들)))
    print("   규칙으로 바꿀 만한 표 %d개 → 종류로 접으면 %d가지"
          % (len(쓸만), len(종류)))
    print("   %-5s %-5s %-6s %-6s %s" % ("온도", "조건", "칸수", "판본", "표머리"))
    for r in list(종류.values())[:20]:
        print("   %-5d %-5d %-6d %-6d %s"
              % (r["온도칸"], r["규칙될칸"], r["칸수"], r["판본수"], r["표머리"][:68]))
    if len(종류) > 20:
        print("   ... 외 %d가지" % (len(종류) - 20))
    쓰기(os.path.join(결과, "대조_참고표_후보.csv"), 후보)
    print("   → 대조_참고표_후보.csv  (전체 %d개 표, 온도칸 많은 순)\n" % len(후보))


# ── ④ 검수 ⑦ 을 행 이름으로 다시 ─────────────────────────────────────
def 고르기(s):
    """글머리표·공백·물결표 모양 차이를 지운다. 이것 때문에 오탐 93% 가 났다(확인필요 §4-1).

    API 는 글머리를 떼고 싣고 첨부는 `o` `ㅇ` `○` 를 붙여 싣는다. 같은 문장인데 다르게 보인다.
    `4~5` 와 `4-5` 도 같은 값이다. 숫자의 쉼표도 표기 차이일 뿐이다.
    """
    s = re.sub(r"[ \t]+", "", s)
    s = re.sub(r"[oㅇ○●◦▪·・∙]", "", s)
    s = s.replace("∼", "~").replace("－", "-").replace("—", "-").replace("–", "-")
    s = re.sub(r"(?<=\d)-(?=\d)", "~", s)
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)
    return s


def 격자():
    """열 번호 대신 행 이름으로 맞대면 오탐이 얼마나 줄어드는지 보인다 (확인필요 §4-1).

    API 본문 표와 첨부 표를 같은 작물·같은 표제목끼리 모아, **행 이름이 같은 줄끼리만**
    값을 맞댄다. 병합 칸이 밀렸거나 글머리표가 다른 것은 이름이 같으면 자동으로 맞는다.
    """
    def 표읽기(p, 작물칸, 표칸, 행칸, 열칸, 값칸, 제목칸=None):
        표 = collections.defaultdict(dict)
        with io.open(p, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                키 = (r[작물칸], r.get(제목칸, "") if 제목칸 else "", r[표칸])
                표[키][(r[행칸], r[열칸])] = r[값칸]
        return 표

    api = os.path.join(ROOT, "농작업일정", "결과", "재배법_표.csv")
    첨 = os.path.join(ROOT, "농작업일정", "결과", "첨부_표.csv")
    if not (os.path.exists(api) and os.path.exists(첨)):
        print("④ 표 파일이 없어 건너뜀\n")
        return
    A = 표읽기(api, "작물명", "표번호", "행", "열", "값", "표제목")
    B = 표읽기(첨, "작물명", "표번호", "행", "열", "값")

    def 행이름표(칸들):
        """{행이름: {열번호: 값}} 로 바꾼다. 0열을 행 이름으로 본다."""
        행들 = collections.defaultdict(dict)
        이름 = {}
        for (행, 열), v in 칸들.items():
            if 열 == "0":
                이름[행] = v.strip()
        for (행, 열), v in 칸들.items():
            n = 이름.get(행, "행%s" % 행)
            if 열 != "0":
                행들[n][열] = v.strip()
        return 행들

    작물별A = collections.defaultdict(list)
    for (작물, 제목, 번호), 칸 in A.items():
        작물별A[작물].append(행이름표(칸))
    작물별B = collections.defaultdict(list)
    for (작물, _, 번호), 칸 in B.items():
        작물별B[작물].append(행이름표(칸))

    열번호식 = 이름식 = 0
    다름 = []
    for 작물 in set(작물별A) & set(작물별B):
        가 = {n: v for t in 작물별A[작물] for n, v in t.items()}
        나 = {n: v for t in 작물별B[작물] for n, v in t.items()}
        for 이름 in set(가) & set(나):
            if not 이름:
                continue
            이름식 += 1
            왼 = " ".join(가[이름].get(k, "") for k in sorted(가[이름]))
            오 = " ".join(나[이름].get(k, "") for k in sorted(나[이름]))
            if 고르기(왼) != 고르기(오):
                다름.append(dict(작물=작물, 행이름=이름[:30], API=왼[:70], 첨부=오[:70]))
        열번호식 += len(set(가) | set(나))
    print("④ 표 대조를 행 이름으로 다시 (확인필요 §4-1)")
    print("   이름이 양쪽에 다 있는 행 %d개 / 그중 값이 다른 것 %d개" % (이름식, len(다름)))
    for r in 다름[:12]:
        print("      %-14s %-24s API %-32s 첨부 %s"
              % (r["작물"][:14], r["행이름"][:24], r["API"][:32], r["첨부"][:32]))
    if len(다름) > 12:
        print("      ... 외 %d건" % (len(다름) - 12))
    쓰기(os.path.join(결과, "대조_표_행이름.csv"), 다름)
    print("   → 대조_표_행이름.csv\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--주간", action="store_true")
    ap.add_argument("--작물", action="store_true")
    ap.add_argument("--참고표", action="store_true")
    ap.add_argument("--격자", action="store_true")
    a = ap.parse_args()
    다 = not (a.주간 or a.작물 or a.참고표 or a.격자)
    if a.주간 or 다:
        주간대조()
    if a.작물 or 다:
        작물검사()
    if a.참고표 or 다:
        참고표()
    if a.격자 or 다:
        격자()


if __name__ == "__main__":
    main()
