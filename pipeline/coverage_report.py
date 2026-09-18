# 스키마 CSV 의 **어느 칸이 얼마나 비었나** 를 한 번에 센다.
#
#     PYTHONIOENCODING=utf-8 python pipeline/coverage_report.py
#     PYTHONIOENCODING=utf-8 python pipeline/coverage_report.py --빈것 guide_text
#
# ⚠ 이름이 `coverage.py` 가 아닌 까닭 — pipeline/ 은 여러 스크립트가 `sys.path` 맨 앞에
#   넣는다. 거기 `coverage.py` 가 있으면 같은 이름의 바깥 꾸러미를 가린다.
#
# ★ "지금 필요한데 안 채워진 게 뭐냐" 에 답하는 도구다. 세션마다 이 물음이 나오는데
#   그때마다 셈하는 코드를 새로 짰다. 손으로 세면 **세는 방법이 매번 달라져** 지난번과
#   비교가 안 된다 — 그래서 파일로 굳혔다.
#
# ⚠ **verify.py 와 하는 일이 다르다.** 저쪽은 "적재가 깨지나" 를 본다(NOT NULL·CHECK).
#   여기는 깨지지 않지만 **비어 있는** 칸을 본다. base_temp 처럼 nullable 로 풀린 칸은
#   verify 에서 안 걸리므로 이쪽이 아니면 빈 줄이 늘어도 아무도 모른다.
#
# ⚠ 빈 칸이 다 문제는 아니다. 화훼·버섯의 difficulty, 과수의 작형처럼 **비는 것이 맞는**
#   자리가 있다. 이 도구는 세기만 하고 판정하지 않는다 — 판정은 확정표가 한다.

import argparse
import csv
import io
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
스키마 = HERE / "out" / "스키마"
근거 = 스키마 / "근거"

# 어느 칸으로 행을 가리킬 것인가. 빈 줄을 찍을 때 이 칸을 보여준다
열쇠 = {
    "crops": ["name"],
    "crop_variants": ["crop_name", "maturity_type"],
    "crop_stages": ["crop_name", "maturity_type", "stage_order"],
    "crop_disaster_rules": ["crop_name", "rule_kind", "stage_name"],
    "varieties": ["crop_name", "name"],
    "crop_guides": ["crop_name", "section", "topic"],
}


def 읽기(경로):
    if not 경로.exists():
        return []
    with io.open(경로, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def 이름(행, 표):
    return " / ".join((행.get(c) or "-") for c in 열쇠.get(표, []))


def 막대(채움, 전체, 너비=20):
    """눈으로 보고 어느 칸이 문제인지 바로 알게. 숫자만 스무 줄이면 안 읽힌다."""
    칸 = 0 if not 전체 else round(채움 / 전체 * 너비)
    return "█" * 칸 + "·" * (너비 - 칸)


def 세기(표):
    행들 = 읽기(스키마 / f"{표}.csv")
    if not 행들:
        return None
    칸들 = list(행들[0].keys())
    return 행들, [(c, sum(1 for r in 행들 if (r.get(c) or "").strip()), len(행들)) for c in 칸들]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--빈것", help="이 칸이 빈 행을 찍는다 (예: guide_text)")
    ap.add_argument("--몇개", type=int, default=30, help="--빈것 으로 찍을 줄 수")
    args = ap.parse_args()

    if not 스키마.exists():
        raise SystemExit(f"{스키마} 가 없다. build.py 를 먼저 돌려라")

    if args.빈것:
        for 표 in 열쇠:
            행들 = 읽기(스키마 / f"{표}.csv")
            if not 행들 or args.빈것 not in 행들[0]:
                continue
            빈 = [r for r in 행들 if not (r.get(args.빈것) or "").strip()]
            print(f"\n{표}.{args.빈것} — 빈 행 {len(빈)}/{len(행들)}")
            for r in 빈[:args.몇개]:
                print(f"    {이름(r, 표)}")
            if len(빈) > args.몇개:
                print(f"    … {len(빈) - args.몇개}행 더")
        return 0

    print("스키마 채움률 — 칸마다 값이 든 행 / 전체 행\n")
    for 표 in 열쇠:
        결과 = 세기(표)
        if not 결과:
            print(f"{표}.csv — 없다\n")
            continue
        행들, 칸셈 = 결과
        print(f"{표}.csv  {len(행들)}행")
        for c, 채움, 전체 in 칸셈:
            율 = 0 if not 전체 else 채움 / 전체 * 100
            표시 = "  " if 율 >= 99.5 else ("⚠ " if 율 < 50 else "· ")
            print(f"  {표시}{c:<18} {막대(채움, 전체)} {채움:>5}/{전체:<5} {율:5.1f}%")
        print()

    # 근거 벌에만 있는 칸 — 값의 **출처**가 얼마나 확인됐나
    print("확인 여부 (근거/ 에만 있는 칸)\n")
    for 표 in ("crops", "crop_variants", "crop_stages"):
        행들 = 읽기(근거 / f"{표}.csv")
        if not 행들:
            continue
        for c in [x for x in 행들[0] if "confirmed" in x]:
            셈 = {}
            for r in 행들:
                셈[(r.get(c) or "(빔)")] = 셈.get(r.get(c) or "(빔)", 0) + 1
            안 = " · ".join(f"{k} {v}" for k, v in sorted(셈.items()))
            print(f"  {표}.{c:<24} {안}")
    print("\n⚠ 빈 칸이 다 문제는 아니다. 비는 것이 맞는 자리인지는 확정표를 본다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
