# -*- coding: utf-8 -*-
"""
뽑아는 놓고 결과물로 안 간 값을 `crops_초안.csv` 까지 밀어 넣는다.

원본검수_2026-09-15.md §7 의 네 가지다.

 7-1  수박 숙기별 적산온도 4개가 crops_초안 에 없다
      적산온도.csv    소과종 750 · 조생종 800 · 중생종 1,000 · 만생종 1,200
      crops_초안      수박 target_sum = 800~1,000 하나뿐
 7-2  같은 표의 `열매달림 후 일수` 칸이 빠졌다  (35~38 / 38~40 / 40~45 / 45~50)
 7-3  적산온도 123행 중 쓸 값은 12행뿐 — 주간농사정보 판본마다 같은 값이 반복된다
 7-4  같은 값인데 출처에 따라 `쓸모` 판정이 갈린다 (벼 1,100~1,200)

여기에 온도.py 가 새로 찾은 `upper_temp` 후보도 같이 넣는다.

⚠ 이 스크립트는 **값을 만들어내지 않는다.** 이미 뽑혀 있는 값을 옮기고 겹친 것을 접을 뿐이다.
   없는 값은 빈칸으로 두고 `확인필요` 로 넘긴다.

    python 반영.py             무엇이 어떻게 바뀌는지만 보여준다
    python 반영.py --고침       crops_초안.csv 와 crop_variants_초안.csv 를 만든다
"""
import os
import io
import re
import csv
import shutil
import argparse
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
결과 = os.path.join(ROOT, "보정", "결과")
CROPS = os.path.join(ROOT, "선정작물", "결과", "crops_초안.csv")
적산 = os.path.join(ROOT, "적산온도", "결과", "적산온도.csv")
백업 = os.path.join(결과, "반영_백업")

# ── 7-1 · 7-2  수박 숙기별 표 ─────────────────────────────────────────
# 원문 : 농작업일정/결과/본문/채소/수박 농작업일정.txt:49~66
#     품종 | 열매달림 후 일수 | 적산온도(℃)
#     소과종 35~38 750 / 조생종 38~40 800 / 중생종 40~45 1,000 / 만생종 45~50 1,200
# ⚠ API 본문(workScheduleDtl)은 만생종을 40~45 로 적었다. 확인필요 §1-1 이
#    첨부(45~50)를 채택했으므로 그쪽을 쓴다. confirmed 는 N 이다 — 농진청 확인이 아니다.
수박표 = [
    ("소과종", 35, 38, 750, "Y"),
    ("조생종", 38, 40, 800, "Y"),
    ("중생종", 40, 45, 1000, "Y"),
    ("만생종", 45, 50, 1200, "N"),   # API 와 갈림. 확인필요 §1-1
]
수박출처 = ("농작업일정 첨부 '수박 농작업일정.hwpx' 성숙기 판정표 "
          "(본문/채소/수박 농작업일정.txt:49~66)")


def 읽기(p):
    with io.open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def 쓰기(p, 행들, 칸=None):
    if not 행들:
        return
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with io.open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=칸 or list(행들[0].keys()))
        w.writeheader()
        w.writerows(행들)


def 백업하기(p):
    b = os.path.join(백업, os.path.relpath(p, ROOT))
    os.makedirs(os.path.dirname(b), exist_ok=True)
    if not os.path.exists(b):
        shutil.copy2(p, b)


# ── 7-3  적산온도 접기 ────────────────────────────────────────────────
def 이름맞추기(이름):
    """`벼 기계이앙재배` 와 `벼` 를 같은 작물로 본다.

    자료마다 작물 이름을 다르게 적는다. 이름이 다르면 같은 값도 다른 값처럼 보여
    `벼 1,100~1,200℃` 의 판정이 자료에 따라 갈린 것을 못 찾는다(§7-4).
    """
    이름 = re.sub(r"[（(].*?[)）]", "", 이름)
    이름 = re.sub(r"\s*(기계이앙|직파|보통|조숙|촉성|반촉성|노지|시설|고랭지|평야지|"
                 r"표준가온|무가온|월동|봄|가을|여름)?\s*재배.*$", "", 이름)
    return 이름.strip() or 이름


def 판정갈림찾기(행들):
    """이름을 맞춘 뒤, 같은 작물·같은 값인데 `쓸모` 가 갈린 것을 찾는다. 고치지는 않는다."""
    묶음 = collections.defaultdict(list)
    for r in 행들:
        묶음[(이름맞추기(r["작물"]), r["값최소"], r["값최대"])].append(r)
    나온다 = []
    for 키, 무리 in 묶음.items():
        판정 = {r["쓸모"] for r in 무리}
        if len(판정) > 1:
            나온다.append((키, 판정, sorted({r["자료"] for r in 무리})))
    return 나온다


def 접기(행들):
    """같은 값이 판본마다 되풀이되는 것을 한 줄로 접는다.

    주간농사정보는 주마다 같은 문장을 다시 싣는다. 값이 늘어난 게 아니라 같은 말이
    반복된 것이므로 `작물·구분·구간·값` 이 같으면 한 줄로 본다.
    몇 번 나왔는지(`판본수`)와 어느 판본인지(`판본`)는 남긴다 — 값이 바뀐 해를 찾을 때 쓴다.
    """
    묶음 = collections.OrderedDict()
    for r in 행들:
        키 = (r["작물"], r["구분"], r["구간"], r["값최소"], r["값최대"], r["단위"])
        묶음.setdefault(키, []).append(r)
    나온다 = []
    for 키, 무리 in 묶음.items():
        첫 = dict(무리[0])
        첫["판본수"] = len(무리)
        첫["판본"] = " | ".join(sorted({r["파일"][:24] for r in 무리}))[:200]
        # 7-4  같은 값인데 판정이 갈리면 가장 확실한 쪽으로 맞춘다
        판정들 = {r["쓸모"] for r in 무리}
        if len(판정들) > 1:
            첫["쓸모"] = ("맞음" if "맞음" in 판정들
                        else "다른용도" if "다른용도" in 판정들
                        else "확인필요")
            첫["판정갈림"] = " / ".join(sorted(판정들))
        else:
            첫["판정갈림"] = ""
        나온다.append(첫)
    return 나온다


# ── 온도.py 가 찾은 upper_temp 후보 ──────────────────────────────────
def 상한후보읽기():
    p = os.path.join(결과, "온도_상한후보.csv")
    if not os.path.exists(p):
        return {}
    나온다 = {}
    for r in 읽기(p):
        이름 = re.sub(r"\(.*\)$", "", r["작물명"]).strip()
        if not r["최저"]:
            continue
        값 = float(r["최저"])
        # 같은 작물이 여러 번 나오면 가장 낮은 값을 쓴다. 상한은 낮은 쪽이 안전하다.
        if 이름 not in 나온다 or 값 < 나온다[이름][0]:
            나온다[이름] = (값, r["원문"], r["파일"], r["줄"])
    return 나온다


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--고침", action="store_true")
    a = ap.parse_args()

    crops = 읽기(CROPS)
    칸 = list(crops[0].keys())
    바뀜 = []

    # ── upper_temp 칸 만들기 ──────────────────────────────────────────
    if "upper_temp" not in 칸:
        자리 = 칸.index("base_confirmed") + 1
        for 새칸 in ("upper_confirmed", "upper_temp_출처", "upper_temp"):
            칸.insert(자리, 새칸)
        for r in crops:
            r.setdefault("upper_temp", "")
            r.setdefault("upper_temp_출처", "")
            r.setdefault("upper_confirmed", "")
        바뀜.append("crops_초안.csv 에 upper_temp · upper_temp_출처 · upper_confirmed 칸 추가")

    상한 = 상한후보읽기()
    for r in crops:
        이름 = r["작물키"].split("_")[0]
        if 이름 in 상한 and not r.get("upper_temp"):
            값, 원문, 파일, 줄 = 상한[이름]
            r["upper_temp"] = "%g" % 값
            r["upper_temp_출처"] = "%s (%s:%s)" % (원문[:70], 파일, 줄)
            r["upper_confirmed"] = "Y"
            바뀜.append("upper_temp  %-18s = %g   %s" % (r["작물키"], 값, 원문[:52]))

    # ── 7-1 · 7-2  수박 숙기별을 crop_variants 로 ──────────────────────
    수박행 = [r for r in crops if r["작물키"] == "수박"]
    변종 = []
    if 수박행:
        수 = 수박행[0]
        for 숙기, 일최소, 일최대, 목표, conf in 수박표:
            변종.append(dict(
                작물키="수박", 숙기=숙기,
                days_to_harvest=(일최소 + 일최대) // 2,
                days_min=일최소, days_max=일최대,
                gdd_target=목표, gdd_기준="열매달림(착과) 후",
                target_sum_출처=수박출처, target_confirmed=conf,
                비고=("" if conf == "Y" else
                     "API 본문은 40~45 로 다름. 첨부 채택 — 확인필요 §1-1")))
        바뀜.append("crop_variants 수박 4행 (소과종 750 · 조생종 800 · 중생종 1,000 · 만생종 1,200)")
        # crops_초안 쪽에는 숙기가 여럿이라는 사실만 적어 둔다. 값은 변종 표가 정본이다.
        표시 = "숙기 4분할 — crop_variants_초안.csv 참고"
        if 표시 not in (수.get("비고") or ""):
            수["비고"] = ((수["비고"] + " / ") if 수["비고"] else "") + 표시
            바뀜.append("crops_초안 수박 비고에 숙기 4분할 표시")

    # ── 7-3 · 7-4  적산온도 접기 ──────────────────────────────────────
    적산행 = 읽기(적산)
    접힘 = 접기(적산행)
    갈린것 = [r for r in 접힘 if r["판정갈림"]]
    바뀜.append("적산온도 %d행 → %d행으로 접음 (판정이 갈렸던 것 %d건)"
                % (len(적산행), len(접힘), len(갈린것)))

    print("바뀌는 것")
    for b in 바뀜:
        print("   " + b)
    print()
    print("적산온도 접은 결과 — 쓸모별")
    for k, v in collections.Counter(r["쓸모"] for r in 접힘).most_common():
        print("   %-8s %3d" % (k, v))
    if 갈린것:
        print("\n판정이 갈렸던 값 (접으면서 맞춤)")
        for r in 갈린것:
            print("   %-10s %6s~%-6s  %s → %s"
                  % (r["작물"], r["값최소"], r["값최대"], r["판정갈림"], r["쓸모"]))

    건너작물 = 판정갈림찾기(적산행)
    if 건너작물:
        print("\n⚠ 자료마다 판정이 다른 값 — 사람이 한쪽으로 정할 것 (§7-4)")
        for (작물, lo, hi), 판정, 자료 in 건너작물:
            print("   %-8s %6s~%-6s  판정 %s   (자료: %s)"
                  % (작물, lo, hi, " vs ".join(sorted(판정)), ", ".join(자료)))
    print("\n쓸 값 (쓸모=맞음)")
    for r in 접힘:
        if r["쓸모"] == "맞음":
            print("   %-10s %-10s %6s~%-6s (%d판본)"
                  % (r["작물"], r["구간"][:10], r["값최소"], r["값최대"], r["판본수"]))

    if not a.고침:
        print("\n실제로 반영하려면  python 반영.py --고침")
        return

    백업하기(CROPS)
    쓰기(CROPS, crops, 칸)
    쓰기(os.path.join(ROOT, "선정작물", "결과", "crop_variants_초안.csv"), 변종)
    쓰기(os.path.join(결과, "적산온도_접음.csv"), 접힘)
    print("\ncrops_초안.csv 고침 (백업 %s)" % os.path.relpath(백업, ROOT))
    print("crop_variants_초안.csv 새로 만듦 (%d행)" % len(변종))
    print("적산온도_접음.csv 만듦 (%d행)" % len(접힘))


if __name__ == "__main__":
    main()
