# 농작업일정 첨부의 '작형별 출하시기' 표를 읽습니다. build.py 의 입력입니다.
#
#     from forms import 작형시기
#
# ★ **값을 베껴 적지 않는다.** 확정표 §A 는 "어느 작형을 쓸지" 만 정하고
#   시기(씨뿌림·수확)는 원본 표에서 읽는다. §A 에 베낀 값이 틀려 있었다 —
#   배추_봄 의 '씨뿌림 1.중' 은 사실 **시설재배** 시기였다(표4 행1).
#
# ⚠ 표 위치가 작물마다 다르다(표3·표4·표5). **차례로 찾지 않고 머리글로 찾는다.**
# ⚠ 고추 표4 는 `작 형 | 육묘일수 | 모종 크기` 라 시기표가 아니다. 시기 칸이
#   하나도 없으면 건너뛴다 — 안 그러면 '70~80일' 을 날짜로 읽으려다 터진다.

import csv
import io
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from common import middle_day  # noqa: E402

MID = HERE / "out" / "mid_table.csv"
OUT = HERE / "out" / "mid_form.csv"

# 머리글 이름 → 우리 칸. 띄어쓰기를 지운 뒤 맞춰 본다
칸이름 = {
    "씨뿌림": "씨뿌림", "모기르기": "씨뿌림",   # 딸기는 '모 기르기' 로 시작한다
    "아주심기": "아주심기",
    "수확기": "수확기",
    "성출하기": "성출하기",
}

# ⚠ '순' 자가 빠진 표기가 있다 — 무 가을무의 '9월상~12월 중순'.
#   순을 요구하면 앞을 놓치고 뒤(12월 중순)를 잡아 수확이 석 달 밀린다.
_순 = re.compile(r"(\d{1,2})\s*월\s*([상중하])순?")

def _납작(s):
    """'시 설 재 배' · '씨 뿌 림' → 공백 없는 글자. 원문 띄어쓰기가 제멋대로다.

    ⚠ '/' 는 표 칸 안의 줄바꿈이다. 공백과 같이 지운다 —
      무(고랭지)의 '여름/재배' 가 '여름재배' 가 되어야 §A 와 맞는다.
    """
    return re.sub(r"[\s/]+", "", s or "")

def _첫날(칸):
    """'3월 중순~/4월 하순' → '03-15'. 범위면 **앞쪽**을 쓴다.

    ⚠ '/' 는 원문 줄바꿈이다. 지우지 않으면 '중순~/4월' 이 한 덩이로 붙는다.
    ⚠ 못 읽으면 빈 값을 돌려준다 — '-' 나 '8월~9월'(순이 없는 것)이 실제로 있다.
    """
    m = _순.search((칸 or "").replace("/", " "))
    return middle_day(m.group(1), m.group(2)) if m else ""


def 작형시기(경로=None):
    """[{작물, 작형, 씨뿌림, 아주심기, 수확기, 성출하기, 출처파일}].

    농작업일정 첨부의 표만 본다. 한 작물에 작형이 여럿이라 줄이 여럿이다.
    """
    경로 = 경로 or MID
    if not 경로.exists():
        raise SystemExit(f"{경로} 가 없습니다 — python pipeline/extract.py 를 먼저 돌리세요")

    # 표 단위로 묶는다. 위치가 '표4/행2' 꼴이다
    표 = {}
    with io.open(경로, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if "농작업일정" not in r["출처파일"]:
                continue
            m = re.match(r"(표\d+)/행(\d+)", r["위치"] or "")
            if m:
                표.setdefault((r["작물"], r["출처파일"], m.group(1)), []).append(
                    (int(m.group(2)), r["내용"])
                )

    행들 = []
    for (작물, 파일, _t), 것들 in 표.items():
        것들.sort()
        머리 = [_납작(c) for c in 것들[0][1].split("¦")]
        if not any("작형" in h for h in 머리):
            continue
        # 머리글 이름으로 칸 자리를 찾는다. 위치로 찾으면 작물마다 어긋난다
        자리 = {칸이름[h]: i for i, h in enumerate(머리) if h in 칸이름}
        if not 자리:
            continue                      # 고추 표4 처럼 시기표가 아닌 것
        작형자리 = [i for i, h in enumerate(머리) if "작형" in h]

        for _, 줄 in 것들[1:]:
            칸들 = [c.strip() for c in 줄.split("¦")]
            if len(칸들) < len(머리):
                continue
            # 무(고랭지)는 작형 칸이 둘이다 — '여름재배 + 준고랭지2기작'
            이름 = " ".join(_납작(칸들[i]) for i in 작형자리 if 칸들[i] not in ("", "-"))
            if not 이름:
                continue
            행 = {"작물": 작물, "작형": 이름, "출처파일": 파일}
            for 칸, i in 자리.items():
                행[칸] = _첫날(칸들[i])
            행들.append(행)
    return 행들


def main():
    행들 = 작형시기()
    칸 = ["작물", "작형", "씨뿌림", "아주심기", "수확기", "성출하기", "출처파일"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=칸, extrasaction="ignore")
        w.writeheader()
        for r in 행들:
            w.writerow({k: r.get(k, "") for k in 칸})
    print(f"{len(행들)}행 → {OUT}")


if __name__ == "__main__":
    main()
