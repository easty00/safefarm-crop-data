# 병해충발생정보 에서 중간 CSV 를 뽑습니다.
#
#     python pipeline/src_pest.py
#     → pipeline/out/원본별/병해충발생정보/mid_*.csv
#
# dbyhsCccrrncInfo. 첨부 57개. 전부 PDF 라 파일당 3초쯤 걸린다.
#
# ⚠ 작물 생육온도는 한 건도 없다. 가져오는 것은 병원균 발병 조건 온도뿐이다.
# ⚠ 경보 등급은 extract_pest_alert.py 가 따로 맡는다.
#
# ⚠ **접지 않고 날 행 그대로 쓴다.** 같은 표가 여러 원본에 실리므로
#   원본별로 접으면 근거 세기(실린호)가 갈린다. 접는 것은 extract.py 가 한 번만 한다.

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "feature"))

from common import (  # noqa: E402
    COLS, OUT, RAW, TEMP_RANGE, clear_read_cache, dump_raw, read_doc, rows_out, set_out,
    tidy, to_num,
)
from crops import crops_in_line  # noqa: E402


# 병해충 이름은 '○○병' '○○벌레' '○○나방' 처럼 끝이 정해져 있다
PEST_NAME = re.compile(r"([가-힣]{2,12}(?:병|벌레류?|나방|매미충?|가루이|응애류?|진딧물|선충|좀류?|파리))")
# ★ 이름은 제목 줄에 있고 조건은 다음 줄에 있다. 조각만 보면 이름이 빈다.
#     "5 벼 잎도열병 <주의보>"                        ← 제목. 번호 + 이름 + 등급
#     "❍ 분생포자에 의해 … 15∼28℃에서 많이 발생"       ← 조건
#   제목을 들고 가야 그 온도가 어느 병해충의 것인지 안다. 실제로 10행 전부 이름이 비었었다.
PEST_HEAD = re.compile(r"^\s*(\d{1,2})\s+([가-힣·․‧\s]{2,26}?)\s*[<〈]\s*(경보|주의보|예보)\s*[>〉]")
# 발병 조건을 말하는 문장인가. 그해 기상 전망은 아니어야 한다


# 발병 조건을 말하는 문장인가. 그해 기상 전망은 아니어야 한다
PEST_COND = re.compile(r"(발병|발생|감염|증식|전염|월동|비행|날아)")


PEST_NOT = re.compile(r"(평년|아침\s*기온|낮\s*기온|평균기온은|주차|전망|예보확률|기상청)")


def from_pest():
    """병해충발생정보 57개에서 병원균 온도조건만 캔다."""
    rule, text = [], []
    base = RAW / "병해충발생정보" / "첨부"
    if not base.exists():
        print("  병해충발생정보 첨부가 없습니다. 건너뜁니다")
        return rule, text
    for p in sorted(q for q in base.rglob("*") if q.is_file()):
        본문, _ = read_doc(p)
        이름들고 = ""
        for i, ln in enumerate(본문.split("\n")):
            제목 = PEST_HEAD.match(ln)
            if 제목:
                이름들고 = tidy(제목.group(2))
            if "℃" not in ln:
                continue
            for 조각 in re.split(r"(?<=[.。])\s+|(?=[❍○ㅇ•▪⇒*])", ln):
                조각 = tidy(조각)
                if "℃" not in 조각 or len(조각) < 8:
                    continue
                if PEST_NOT.search(조각) or not PEST_COND.search(조각):
                    continue
                이름 = PEST_NAME.search(조각)
                병해충명 = 이름.group(1) if 이름 else 이름들고
                작물들 = crops_in_line(조각)
                m = TEMP_RANGE.search(조각)
                if not m:
                    continue
                lo, hi = to_num(m.group(1)), to_num(m.group(2) or m.group(1))
                for 작물 in (작물들 or {""}):
                    rule.append({
                        "작물": 작물,
                        "재해종류": "병해충", "생육단계": 병해충명,
                        "지표": "평균기온", "부등호": "~",
                        "값": lo if lo == hi else f"{lo}~{hi}", "단위": "℃",
                        "지속일": "", "등급": "",
                        "조건원문": 조각[:200], "출처": "병해충발병조건",
                        "출처파일": p.name, "위치": f"본문줄{i}",
                    })
    return rule, text


def run():
    """병원균 온도조건만. 경보 등급은 extract_pest_alert.py 가 맡는다."""
    rule, text = from_pest()
    return {"mid_rule.csv": rule, "mid_text.csv": text}


def 원본파일들():
    b = RAW / "병해충발생정보" / "첨부"
    return sorted(q for q in b.rglob("*") if q.is_file()) if b.exists() else []


def 계열(p):
    b = RAW / "병해충발생정보" / "첨부"
    return p.relative_to(b).parts[0]      # 연도


# 이 파일만 따로 돌릴 때 쓴다. extract.py 는 run() 을 바로 부른다.
NAME = "병해충발생정보"


def main():
    out = OUT / "원본별" / NAME
    set_out(out)
    print(f"{NAME} …")

    # ★ 먼저 날 자료를 통째로 남긴다. mid_*.csv 는 우리가 알아본 것만 담기 때문이다.
    #   나중에 낱말을 바꿔 다시 캘 때 원본을 안 열어도 되고,
    #   "없다" 와 "안 읽었다" 를 파일로 가를 수 있다.
    dump_raw(NAME, 원본파일들(), 계열)

    표 = run()
    for 이름, 행 in 표.items():
        for r in 행:                      # 어느 원본이 말한 값인지 찍는다
            r["원본"] = NAME
        rows_out(이름, 행, COLS[이름])
    clear_read_cache()
    print(f"  → {out}")


if __name__ == "__main__":
    main()
