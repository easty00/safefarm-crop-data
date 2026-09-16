# 주간농사정보 에서 중간 CSV 를 뽑습니다.
#
#     python pipeline/src_week.py
#     → pipeline/out/원본별/주간농사정보/mid_*.csv
#
# weekFarmInfo. 첨부 192개(2023~2026 전수). 전부 hwpx.
#
# ★ 여기서만 나오는 것 — 벼 숙기표(조·중·만생종 일수). 22개 호에 되풀이된다.
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
    COLS, N, OUT, RAW, SUM_WORD, TEMP_RANGE, clear_read_cache, crops_with_pos,
    dump_raw, fix_pdf_cols, limit_table, nospace, read_doc, rows_out, set_out,
    temp_from_sentence, tidy, to_num,
)
from crops import CROP_ALIAS, RICE, crops_in_line, is_main  # noqa: E402


# ─────────────────────────────────────────────────────────────────────
# 4. 주간농사정보 첨부 — 벼 숙기표 · 한계온도표 합본판 · 본문
#
# 192개 전부 hwpx. 2023~2026 전수다(목록 870건 중 이 기간이 192건).
# 표 11,533개 · 본문 496만 자. 무엇이 있는지는 pipeline/안읽은것.md §3 에 전수로 적었다.
#
# ★ 여기서만 나오는 것 — 벼 숙기표. 22개 호에 되풀이된다.
#       품 종            출수기        출수 후 일수
#       조 생 종          8월 초        45∼50일
#       중 생 종          8월 상순      50∼55일
#       중만생종 또는 만식   8월 중순 이후   55∼60일
#     ※ 출수 후 수확기 적산온도 (1,100 ∼ 1,200℃)   ← 표 밖 문장이다. 본문에서 잡는다
#
# ⚠ 한계온도표가 여기에도 있다. 판이 셋이고 값은 재해예방정보와 같다.
#   새 값은 없고 실린호(근거 세기)만 늘어난다.
#       작물별 ¦ 모기를때 ¦ 꽃눈생기기전 ¦ 꽃필때 ¦ 동해온도      8호  과채류
#       작물별 ¦ 모기를때 ¦ 꽃눈생기기전 ¦ 냉해온도 ¦ 비고        8호  엽채류
#       작물별 ¦ 작물별 ¦ 한계온도(℃)×4                    6호  ★ 합본. 머리글 2줄 + 작물군 칸
# ─────────────────────────────────────────────────────────────────────

RICE_MATURITY = re.compile(r"(조\s*생\s*종|중\s*생\s*종|중\s*만\s*생\s*종|만\s*식)")


# ⚠ 같은 숙기를 호마다 달리 적는다. 그대로 두면 한 숙기가 두 줄로 갈린다.
#     "중만생종 또는 만식"  /  "중만생종 또는 만식재배"
#   확정표 §D 가 조·중·만 세 칸으로 나누므로 그 세 개로 모은다. 원문은 '원문' 칸에 남는다.
def rice_maturity(name):
    n = nospace(name)
    if "중만생" in n or "만식" in n or "만생" in n:
        return "만생종"
    if "중생" in n:
        return "중생종"
    if "조생" in n:
        return "조생종"
    return n


def rice_maturity_table(g, gi, fname):
    """벼 출수기별 수확적기. crop_variants 의 숙기 3종이 여기서 나온다.

        품 종 ¦ 출수기 ¦ 출수 후 일수
    """
    out = []
    for ri, row in enumerate(g[1:], 1):
        숙기 = tidy(row[0]) if row else ""
        if not RICE_MATURITY.search(숙기):
            continue
        일수 = tidy(row[2]) if len(row) > 2 else ""
        if not re.search(r"\d", 일수):
            continue
        out.append({
            "작물": RICE, "품종숙기": rice_maturity(숙기), "일수": 일수,
            "적산온도": "", "구간": "출수 후",
            "원문": " ¦ ".join(tidy(c) for c in row)[:200],
            "출처파일": fname, "위치": f"표{gi}/행{ri}",
        })
    return out


def merged_limit_table(g, gi, fname):
    """한계온도표 합본판. 과채류와 엽근채류를 한 표에 담은 것.

    ⚠ 머리글이 두 줄이고 작물군 칸이 따로 있다. 다른 판과 모양이 다르다.
        행0  작물별 ¦ 작물별 ¦ 한계온도(℃) ¦ 〃 ¦ 〃 ¦ 〃
        행1  작물별 ¦ 작물별 ¦ 모기를때 ¦ 꽃눈생기기전 ¦ 꽃필때 ¦ 동해온도
        행2  과채류  ¦ 딸기/토마토/… ¦ 10/10/… ¦ …
                   └ 작물이 칸 안에 줄로. limit_table 과 같은 꼴이지만 칸이 하나 밀려 있다

    ⚠ **마지막 '동해온도' 칸은 규칙으로 만들지 않는다.** 원판 둘과 일관되게 안 맞는다.

        합본 과채류    0 / -1~-2 / 0~2 / 0~2 / 0~2 / 0~2
          = 재해예방정보 **과채류 한계온도표**(냉해)와 한 칸도 다르지 않다
        합본 엽근채류   0 / -6 / -5 / -10 / -5 / 0
          = 엽채류 한계온도표와 같은 칸 모양인데 **배추만 -6**(생육및장애표 = 동해 값)

      한쪽으로 몰면 다른 쪽이 깨진다 —
        전부 냉해로 보면   딸기 0 은 맞고  배추 -6 이 냉해 -8 과 어긋난다
        전부 동해로 보면   배추 -6 은 맞고  딸기 0 이 동해 -5 와 어긋난다
      농진청이 합치면서 배추 값을 바꿔 적은 것으로 보이나 어느 쪽이 맞는지 알 수 없다.

      **원판(재해예방정보)이 이미 두 값을 제대로 갈라 담고 있으므로 여기서는 안 담는다.**
      값을 잃는 것이 아니다 — tables.csv 에 원문이 그대로 있고, 실린호만 안 는다.
      (확인필요.md §1-3)
    """
    if len(g) < 3:
        return []
    sub = [nospace(c) for c in g[1]]
    out = []
    for ri, row in enumerate(g[2:], 2):
        if len(row) < 3:
            continue
        작물들 = [c.strip() for c in row[1].split("\n")]
        for k, 원문이름 in enumerate(작물들):
            작물 = CROP_ALIAS.get(nospace(원문이름))
            for ci in range(2, len(row)):
                항목 = sub[ci] if ci < len(sub) else ""
                if "동해" in 항목 or "냉해" in 항목:
                    continue              # 위 설명 — 원판과 일관되게 안 맞아 규칙으로 안 만든다
                elif 항목:
                    종류, 지표, 부등호 = "단계별저온", "최저기온", "<="
                else:
                    continue
                줄 = row[ci].split("\n")
                v = 줄[k].strip() if k < len(줄) else ""
                m = TEMP_RANGE.search(v) or re.match(rf"\s*(-?{N})", v)
                if not v or v == "-" or not m:
                    continue
                out.append({
                    "작물": 작물 or tidy(원문이름), "본선": is_main(작물),
                    "재해종류": 종류, "생육단계": 항목,
                    "지표": 지표, "부등호": 부등호,
                    "값": to_num(m.group(1)), "단위": "℃", "지속일": "", "등급": "",
                    "조건원문": v[:120], "출처": "한계온도표(합본)",
                    "출처파일": fname, "위치": f"표{gi}/행{ri}/{k}",
                })
    return out


def from_weekfarm():
    """주간농사정보 192개. 표 + 본문."""
    rule, sumt, temp, table, text = [], [], [], [], []
    base = RAW / "주간농사정보" / "첨부"
    if not base.exists():
        print("  주간농사정보 첨부가 없습니다. 건너뜁니다")
        return rule, sumt, temp, table, text
    for p in sorted(q for q in base.rglob("*") if q.is_file()):
        try:
            _, grids = read_doc(p)
        except Exception:  # noqa: BLE001
            grids = []
        for gi, g in enumerate(grids):
            while g and all(len(r) > 1 and not r[0].strip() for r in g):
                g = [r[1:] for r in g]
            if not g or len(g) < 2:
                continue
            head = [nospace(c) for c in g[0]]
            flat = nospace("".join("".join(r) for r in g))
            h0 = head[0] if head else ""

            if "품종" in h0 and "출수기" in flat and "출수후일수" in flat:
                sumt += rice_maturity_table(g, gi, p.name)
            elif "작물별" in h0 and "한계온도" in nospace(" ".join(head)):
                rule += merged_limit_table(g, gi, p.name)      # 합본판
            elif "작물별" in h0 and "℃" not in flat[:20]:
                is_생육장애 = "한량계" in flat or "장애온도" in flat
                rule += limit_table(fix_pdf_cols(g), gi, p.name, is_생육장애)
            else:
                continue
            for ri, row in enumerate(g):
                table.append({
                    "작물": "", "출처파일": p.name, "위치": f"표{gi}/행{ri}",
                    "칸수": len(row),
                    "내용": " ¦ ".join(c.replace("\n", "/") for c in row)[:600],
                })

        # ─ 본문 ─────────────────────────────────────────────────
        # ⚠ 재해예방정보 본문은 값이 없어 되돌렸지만 여기는 다르다. 문서 성격이 다르다.
        #   주간 회보는 작물별로 그 주 할 일을 적어서 작물 옆에 값이 붙는다.
        #       * 동해 한계 온도: 난지형 마늘 –5∼-6℃, 한지형 마늘 –7∼-8℃, 양파 –8∼-9℃
        #       ❍ (양파) 25℃ 이상의 고온에 생육 저하, 고온 지속 시 생육정지
        #   작물 판정은 crops_in_line 이 한다 — 이름만으로 찾으면 '파종' 의 '파' 가 걸린다.
        본문, _ = read_doc(p)
        최근작물, 몇줄전 = "", 999
        for i, ln in enumerate(본문.split("\n")):
            본줄 = crops_in_line(ln)
            if 본줄:
                최근작물, 몇줄전 = sorted(본줄)[0], 0
            else:
                몇줄전 += 1
            if "℃" not in ln:
                continue
            for 조각 in re.split(r"(?<=[.。])\s+|(?=[❍○ㅇ•▪*])", ln):
                조각 = tidy(조각)
                if "℃" not in 조각 or len(조각) < 8:
                    continue
                작물들 = crops_in_line(조각)
                if not 작물들:
                    # ⚠ 값만 있고 작물 이름이 없는 줄이 있다. 이름은 표 제목에 있다.
                    #     줄357  <벼 출수기별 수확적기>
                    #     …      (표 안의 칸들 — 품종 · 출수기 · 일수)
                    #     줄370  * 출수 후 수확기 적산온도(1,100∼1,200℃)   ← 여기엔 '벼' 가 없다
                    #   문단 나누기를 고치면서 이 값이 통째로 사라졌었다.
                    #
                    # ⚠ 그렇다고 작물을 무한정 이어쓰면 안 된다. 재해예방정보에서
                    #   한 번 '가지' 로 잡히면 뒤 수백 줄이 가지가 된 적이 있다.
                    #   **적산온도 줄에만, 가까이(20줄 안) 있을 때만** 이어쓴다.
                    #
                    # ⚠ 그래도 긴 서술문은 받으면 안 된다. 배(果) 문장의 값이 딸기에 붙었다.
                    #     "'신고'의 경우 … 적산온도는 약 3,480±50℃ 정도가 좋음"   ← 120자 서술
                    #   표 밑 각주는 짧다. 60자를 넘으면 딴 얘기로 본다.
                    if not (SUM_WORD.search(조각) and 최근작물
                            and 몇줄전 <= 20 and len(조각) <= 60):
                        continue
                    작물들 = {최근작물}
                # ⚠ 한 줄에 작물이 여럿이면 값마다 **바로 앞의 작물**에 붙인다.
                #   그냥 작물별로 돌리면 양파에 마늘 값까지 붙는다. 실제로 그랬다.
                #     "난지형 마늘 -5~-6℃, 한지형 마늘 -7~-8℃, 양파 -8~-9℃"
                자리 = crops_with_pos(조각)
                if len(set(c for _p, c in 자리)) > 1:
                    t, s = temp_from_sentence(조각, sorted(작물들)[0],
                                              p.name, f"본문줄{i}", 자리)
                    temp += t
                    sumt += s
                else:
                    for 작물 in 작물들:
                        t, s = temp_from_sentence(조각, 작물, p.name, f"본문줄{i}")
                        temp += t
                        sumt += s
    return rule, sumt, temp, table, text


def run():
    """표(벼 숙기·한계온도) + 본문."""
    rule, sumt, temp, table, text = from_weekfarm()
    return {"mid_rule.csv": rule, "mid_sumtemp.csv": sumt, "mid_temp.csv": temp,
            "mid_table.csv": table, "mid_text.csv": text}


def 원본파일들():
    b = RAW / "주간농사정보" / "첨부"
    return sorted(q for q in b.rglob("*") if q.is_file()) if b.exists() else []


def 계열(p):
    b = RAW / "주간농사정보" / "첨부"
    return p.relative_to(b).parts[0]      # 연도


# 이 파일만 따로 돌릴 때 쓴다. extract.py 는 run() 을 바로 부른다.
NAME = "주간농사정보"


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
