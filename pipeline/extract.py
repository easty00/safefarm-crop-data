# 원본별로 뽑은 중간 CSV 를 모아 한 벌로 만듭니다.
#
#     python pipeline/extract.py                   원본 다섯을 차례로 돌려 모은다
#     python pipeline/extract.py --only 주간농사정보   그것만 다시 돌려 모은다
#     python pipeline/extract.py --merge            다시 안 돌리고 있는 것만 모은다
#
# 원본 하나만 고치고 싶으면 그 파일을 따로 돌려도 됩니다.
#
#     python pipeline/src_farmwork.py     농작업일정
#     python pipeline/src_disaster.py     재해예방정보
#     python pipeline/src_week.py         주간농사정보
#     python pipeline/src_pest.py         병해충발생정보   (PDF 57개라 3분쯤)
#     python pipeline/src_variety.py      품종정보         ⚠ 첨부 655개라 1분쯤
#
# 그 다음 `--merge` 로 모으면 됩니다.
#
# ─────────────────────────────────────────────────────────────────────
# 이 파일이 하는 일은 셋뿐입니다
#
#     ① 원본별 스크립트를 부른다 (또는 out/원본별/ 에 있는 것을 읽는다)
#     ② 같은 값을 접고 **실린호** 를 센다
#     ③ out/mid_*.csv 로 쓴다
#
# ⚠ **접는 것은 여기서만 합니다.** 원본별 스크립트는 날 행을 그대로 씁니다.
#   같은 표가 여러 원본에 실리기 때문입니다 —
#   한계온도표는 재해예방정보 18개 호와 주간농사정보 22개 호에 다 있습니다.
#   원본별로 접으면 같은 규칙의 근거 세기가 18과 22로 갈립니다.
#
# ⚠ 판단(무엇을 규칙으로 삼을지)은 원본별 파일에 있습니다. 여기에 넣지 마세요.
#   1,500줄짜리 한 파일이었다가 이렇게 나눈 까닭입니다.
# ─────────────────────────────────────────────────────────────────────

import csv
import importlib
import io
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "feature"))

from common import (  # noqa: E402
    CONFLICT_COLS, COLS, OUT, dedup_rule, dedup_simple,
    find_conflicts, rows_out, set_out,
)

# 원본 이름 → 그 원본을 맡은 모듈. 새 원본을 더하면 여기 한 줄.
SOURCES = {
    "농작업일정": "src_farmwork",
    "재해예방정보": "src_disaster",
    "주간농사정보": "src_week",
    "병해충발생정보": "src_pest",
    "품종정보": "src_variety",      # 품종·숙기. 파일이 없으면 조용히 건너뛴다
}


def 원본별폴더(이름):
    return OUT / "원본별" / 이름


def 뽑기(이름):
    """원본별 모듈을 불러 돌리고, 그 결과를 out/원본별/<이름>/ 에도 남긴다."""
    모듈이름 = SOURCES[이름]
    try:
        m = importlib.import_module(모듈이름)
    except ModuleNotFoundError:
        print(f"  · {이름} — {모듈이름}.py 가 아직 없습니다. 건너뜁니다")
        return {}
    m.main()
    return 읽기(이름)


def 읽기(이름):
    """out/원본별/<이름>/ 에 이미 있는 중간 CSV 를 읽는다."""
    d = 원본별폴더(이름)
    if not d.exists():
        return {}
    표 = {}
    for f in COLS:
        p = d / f
        if not p.exists():
            continue
        with io.open(p, encoding="utf-8-sig", newline="") as fh:
            표[f] = list(csv.DictReader(fh))
    return 표


def main():
    인자 = sys.argv[1:]
    모으기만 = "--merge" in 인자
    고를것 = list(SOURCES)
    if "--only" in 인자:
        고를것 = 인자[인자.index("--only") + 1].split(",")
        나쁜것 = [x for x in 고를것 if x not in SOURCES]
        if 나쁜것:
            print(f"모르는 원본: {', '.join(나쁜것)}")
            print(f"고를 수 있는 것: {', '.join(SOURCES)}")
            return

    모음 = {f: [] for f in COLS}
    for 이름 in SOURCES:
        if 모으기만 or 이름 not in 고를것:
            표 = 읽기(이름)          # 다시 안 돌리고 있는 것만 읽는다
            if 표:
                print(f"  · {이름} — 있는 것을 읽음")
        else:
            표 = 뽑기(이름)
        for f, 행들 in 표.items():
            모음[f] += 행들

    # ★ 여기서 한 번만 접는다. 원본을 가로질러 같은 값이면 한 줄로 모으고 실린호를 센다.
    print("\n접는 중 (원본을 가로질러 같은 값을 모읍니다)")
    모음["mid_rule.csv"] = dedup_rule(모음["mid_rule.csv"])
    모음["mid_temp.csv"] = dedup_simple(
        모음["mid_temp.csv"], ["작물", "종류", "항목", "값최소", "값최대"])
    # ⚠ 원문을 열쇠에 넣으면 띄어쓰기만 달라도 다른 값으로 센다.
    #   "가루쌀" 과 "가루 쌀" 이 따로 세어졌다. 값으로만 접는다.
    모음["mid_sumtemp.csv"] = dedup_simple(
        모음["mid_sumtemp.csv"], ["작물", "품종숙기", "적산온도", "구간"])
    모음["mid_text.csv"] = dedup_simple(모음["mid_text.csv"], ["작물", "구분", "본문"])

    # ⚠ 원본별 스크립트가 set_out 으로 자기 폴더를 가리켜 둔 채 끝난다. 그 값은 모듈 전역이다.
    #   되돌리지 않으면 **최종 결과가 마지막 원본 폴더에 쓰인다.** 실제로 그랬다 —
    #   out/원본별/병해충발생정보/ 에 최종 6종이 덮어써지고 병해충 본래 66행이 사라졌다.
    set_out(None)

    print("\n쓰는 중")
    for f in COLS:
        rows_out(f, 모음[f], COLS[f])

    # ★ 값이 갈리는 곳을 따로 뽑아둔다. 접기는 값이 같을 때만 하므로
    #   값이 다르면 두 행이 남는데, 그게 다른 사실인지 어긋난 것인지 표에는 표시가 없다.
    충돌 = find_conflicts(모음["mid_rule.csv"])
    rows_out("충돌.csv", 충돌, CONFLICT_COLS)
    if 충돌:
        묶 = len({(r["작물"], r["재해종류"], r["생육단계"]) for r in 충돌})
        print(f"\n  ⚠ 같은 자리에 값이 갈리는 곳 {묶}군데 — out/충돌.csv 를 보세요")
        print("    (동해/냉해처럼 원래 다른 값인 것도 섞여 있습니다. 사람이 가려야 합니다)")

    print("\n끝. 값이 이상하면 '출처파일' 과 '위치' 로 원문을 찾으세요.")
    print("    어느 원본들이 같은 말을 했는지는 '출처들' 칸에 있습니다.")


if __name__ == "__main__":
    main()
