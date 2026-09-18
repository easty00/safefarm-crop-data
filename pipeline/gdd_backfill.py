# 평년 기온으로 목표 적산온도(gdd_target)를 역산한다.
#
#     python pipeline/gdd_backfill.py
#     → pipeline/out/gdd.csv      작형 한 줄씩. build.py 가 읽는다
#
# ★ **운영과 같은 식이어야 한다.** Safe-farm 의 src/features/report/domain/gdd.ts
#   dailyGdd 와 한 글자도 다르면 안 된다. 목표값과 누적식이 다른 자로 재지면
#   "며칠 남았나" 가 통째로 어긋난다 (GDD_작업인계.md §1-1a 마지막 경고).
#
# ⚠ **평년값에는 연도가 없다.** 월·일 366칸이 도는 고리다. 마늘 249일 ·
#   양파 223일 · 시금치 117일은 해를 넘으므로 12/31 다음에 1/1 로 돌아가야 한다.
#   날짜 계산(date + timedelta)으로 풀면 윤년에서 어긋난다 — 인덱스로 돈다.

import csv
import io
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import spec  # noqa: E402

평년값 = HERE.parent / "기준표" / "평년값.csv"
OUT = HERE / "out" / "gdd.csv"

전국 = "전국평균"


def 평년읽기():
    """{관측소: {(월,일): (최고, 최저)}} 와 날짜 차례를 함께 돌려준다.

    ⚠ 날짜 차례가 따로 필요하다. dict 는 순서를 지키지만 **어느 날이 몇 번째인지**
      알아야 파종일에서 시작해 n일을 셀 수 있다.
    """
    표 = {}
    차례 = []
    with io.open(평년값, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            키 = (int(r["month"]), int(r["day"]))
            표.setdefault(r["station"], {})[키] = (
                float(r["tmax_normal"]), float(r["tmin_normal"])
            )
            if 키 not in 차례:
                차례.append(키)
    if not 표:
        raise SystemExit(f"평년값이 비었습니다: {평년값}")
    차례.sort()
    return 표, 차례


def 전국평균(표, 차례):
    """관측소가 정해지지 않은 작형용. 같은 날짜를 모든 관측소에서 평균낸다.

    ⚠ 결측이 있는 관측소는 그 날짜만 빠진다. 지금 평년값은 결측 0 이지만
      다음 갱신 때 생길 수 있어 개수를 세어 나눈다.
    """
    평균 = {}
    for 날 in 차례:
        값 = [v[날] for v in 표.values() if 날 in v]
        평균[날] = (
            sum(x for x, _ in 값) / len(값),
            sum(y for _, y in 값) / len(값),
        )
    return 평균


def 하루(최고, 최저, base, upper):
    """하루치 GDD. Safe-farm 의 gdd.ts dailyGdd 와 같은 식이다.

        상한 없음 — Standard
            max((Tmax + Tmin)/2 − Tbase, 0)

        상한 있음 — Modified (Tmax·Tmin 개별 클램프)
            Tmax' = min(Tmax, Tupper) · Tmin' = max(Tmin, Tbase)
            max((Tmax' + Tmin')/2 − Tbase, 0)

    ⚠ Tmin 클램프는 **상한이 있을 때만** 건다. 상한 없이 Tmin 만 자르면 일반 GDD 와
      어긋난다 (상추 18/2 → 6 이 아니라 7). 두 줄을 분기 밖으로 빼지 말 것.
    """
    if upper is None:
        return max(0.0, (최고 + 최저) / 2 - base)
    return max(0.0, (min(최고, upper) + max(최저, base)) / 2 - base)


def 적산(일별, 차례, 파종일, 일수, base, upper):
    """파종일부터 일수만큼 쌓는다. 366칸을 고리처럼 돈다.

    ⚠ 파종일이 차례에 없으면(2/29 파종 같은) 터뜨린다. 조용히 건너뛰면
      그 작형만 값이 비는데 원인을 못 찾는다.
    """
    월, 일 = int(파종일[:2]), int(파종일[3:5])
    시작 = 차례.index((월, 일))
    합 = 0.0
    for i in range(int(일수)):
        최고, 최저 = 일별[차례[(시작 + i) % len(차례)]]
        합 += 하루(최고, 최저, base, upper)
    return 합


def 작형전부():
    """build.py 와 **똑같은 3층 작형**을 만든다.

    ⚠ 예전에는 `spec.작형()`(확정표 §A) 25행만 봤다. §A 는 사람이 손으로 적는 표라
      19작물뿐이라서, base_temp 를 89작물로 늘려도 역산이 33행에서 안 늘었다.
      build 는 같은 자리에서 세 층을 쌓는데 여기만 1층을 봤던 것이다.

        ① 확정표 §A          25행   사람이 적은 정본
        ② 첨부 작형표         94행   농작업일정 첨부의 씨뿌림·수확기 표
        ③ 생육과정 일정 역산    74행   작형표조차 없는 작물

      차례가 곧 미더움의 차례다 — 뒤 층은 앞 층에 **없는 작물만** 만든다(build 와 같은 규칙).

    ⚠ build 를 import 하지만 순환이 아니다. 작형 조립은 gdd.csv 를 읽지 않는다.
      build 는 `if __name__ == "__main__"` 가드가 있어 import 만으로는 아무것도 안 돈다.
    """
    import build  # noqa: PLC0415 — 순환 아님(위 주석). 맨 위로 올리면 spec 보다 먼저 로드된다

    작형표 = list(spec.작형())
    일정경로 = build.OUT / "mid_schedule.csv"
    if 일정경로.exists():
        일정 = build.읽기(일정경로)
        작형표 += build._작형_자료(일정, {r["작물"] for r in 작형표})
        작형표 += build._작형_일정(일정, {r["작물"] for r in 작형표})
    return 작형표


def main():
    표, 차례 = 평년읽기()
    표[전국] = 전국평균(표, 차례)
    온도표 = spec.온도()

    행들 = []
    건너뜀 = {"온도없음": 0, "일수없음": 0}
    for a in 작형전부():
        온도 = 온도표.get(a["작물"])
        if not 온도 or 온도.get("base_temp") is None:
            건너뜀["온도없음"] += 1
            continue
        # ②③ 은 일정에서 만든 값이라 파종일·일수가 비는 작형이 있다. §A 에는 없던 일이다
        if not a.get("파종일") or not str(a.get("일수") or "").strip():
            건너뜀["일수없음"] += 1
            continue
        # 관측소가 비면 전국 평균 한 줄. 여럿이면 각각 한 줄씩 낸다 —
        # 값이 모이는지 보는 것이 검증이다 (GDD_작업인계 §5-3)
        for stn in a["관측소"] or [전국]:
            if stn not in 표:
                raise SystemExit(f"{a['작물키']}: 평년값에 없는 관측소 {stn}")
            행들.append({
                "작물키": a["작물키"],
                "작물": a["작물"],
                "관측소": stn,
                "파종일": a["파종일"],
                "일수": int(a["일수"]),
                "base_temp": 온도["base_temp"],
                "upper_temp": 온도["upper_temp"],
                "gdd": round(적산(
                    표[stn], 차례, a["파종일"], a["일수"],
                    온도["base_temp"], 온도["upper_temp"],
                )),
            })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(행들[0]))
        w.writeheader()
        w.writerows(행들)
    print(f"{len(행들)}행 → {OUT}")
    print(f"  건너뜀 — base_temp 없음 {건너뜀['온도없음']}작형"
          f" · 파종일/일수 없음 {건너뜀['일수없음']}작형")


if __name__ == "__main__":
    main()
