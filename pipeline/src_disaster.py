# 재해예방정보 에서 중간 CSV 를 뽑습니다.
#
#     python pipeline/src_disaster.py
#     → pipeline/out/원본별/재해예방정보/mid_*.csv
#
# frcDsstrPrevnt. 첨부 69개(저온해 삭제됨).
#
# 표만 읽는다. 본문 680만 자는 읽어봤고 값이 없어 되돌렸다(안읽은것.md §2-3).
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
    COLS, N, NUM, OUT, RAW, TEMP_RANGE, clear_read_cache, dump_raw, fix_pdf_cols,
    limit_table, nospace, read_doc, rows_out, set_out, temp_from_sentence, tidy, to_num,
)
from crops import ALL_CROPS, CROP_ALIAS, RICE  # noqa: E402
from hwpx_table import parse_threshold  # noqa: E402


# 등록 작물이 0건이라 읽지 않는 계열.
#
# ⚠ 이건 '지금 등록된 작물' 기준의 판단이다. 작물을 더하면 틀릴 수 있다.
#   그래서 이름만 적어두고 끝내지 않는다 — 돌릴 때마다 본문을 훑어 다시 확인한다.
#   맞으면 조용히 건너뛰고, 등록 작물이 나오면 경고를 내고 읽는다.
#   (저온해 43개는 사과·배·복숭아·매실·포도 5작물 고정이었다. 사용법.md §3-3)
SKIP_SERIES = {"저온해"}


def series_crop_hit(p):
    """건너뛸 계열의 파일에 작물이 실제로 없는지 본다. 있으면 그 이름을 돌려준다.

    ⚠ 한 글자 작물(벼·무·파)은 아무 데나 걸린다. '배수' 의 '배', '파종' 의 '파'.
      그래서 한 글자는 괄호나 조사가 붙은 꼴만 인정한다.
    """
    글, _ = read_doc(p)
    if not 글:
        return ""
    for 이름 in sorted(ALL_CROPS, key=len, reverse=True):
        if len(이름) == 1:
            if re.search(rf"[(（]\s*{이름}\s*[)）]|{이름}(?:는|은|의|가|를|에|와|과)", 글):
                return 이름
        elif 이름 in 글:
            return 이름
    return ""


def disorder_body_table(g, gi, fname):
    """생육및장애온도표의 **본체**. PDF 판본에서만 이 모양으로 나온다.

    PDF 는 이 표의 머리글과 본체가 서로 다른 격자로 갈라진다.
        격자 85  머리글만 2줄. 게다가 '장','애','온','도' 로 조각남
        격자 86  본체 14행. 머리글이 없다
    둘 다 '작물별' 조건에 안 걸려 통째로 빠져 있었다.

    ★ 그런데 이 본체가 hwpx 보다 낫다. **장애온도가 행마다 짝이 맞는다.**

        '가    지' ¦ '35' ¦ '28～23 18～13' ¦ '10' ¦ '0～2  25℃ 이상 : 화분 기능 상실'

      hwpx 는 작물 7개가 한 칸에 줄로 들어 있는데 장애온도는 5줄뿐이라 짝을 잃는다.
      줄 수가 안 맞는 까닭은 파싱 실패가 아니라 **토마토가 장애온도를 둘 갖기 때문**이다
      (30℃이상 공동과발생 · 35℃이상 낙화낙과). 그래서 위치로는 영영 못 맞춘다.
      PDF 본체는 행이 곧 작물이라 이 문제가 없다.

    칸 자리는 이 표에서 고정이다.
        0 작물 ¦ 1 최고한량계 ¦ 2 적온(낮 밤) ¦ 3 최저량계 ¦ 4~ 동해온도 + 장애온도

    돌려주는 것 : (규칙행, 온도행)   장애온도는 온도행으로 보낸다(사용법.md §2)
    """
    rule, temp = [], []
    for ri, row in enumerate(g):
        if len(row) < 4:
            continue
        작물 = CROP_ALIAS.get(nospace(row[0]))
        if not 작물:
            continue
        def one(v):
            m = re.match(rf"\s*(-?{NUM})", tidy(v))
            return to_num(m.group(1)) if m else ""
        for ci, 항목, 지표, 부등호, 종류 in (
            (1, "최고한량계", "최고기온", ">=", "한계_최고"),
            (3, "최저량계", "최저기온", "<=", "한계_최저"),
        ):
            v = one(row[ci]) if ci < len(row) else ""
            if v != "":
                rule.append({
                    "작물": 작물, "재해종류": 종류, "생육단계": 항목,
                    "지표": 지표, "부등호": 부등호, "값": v, "단위": "℃",
                    "지속일": "", "등급": "", "조건원문": tidy(row[ci])[:120],
                    "출처": "생육및장애온도표", "출처파일": fname,
                    "위치": f"표{gi}/행{ri}/{ci}",
                })
        꼬리 = tidy(" ".join(row[4:]))
        동해 = one(꼬리)
        if 동해 != "":
            rule.append({
                "작물": 작물, "재해종류": "동해", "생육단계": "동해온도",
                "지표": "최저기온", "부등호": "<=", "값": 동해, "단위": "℃",
                "지속일": "", "등급": "", "조건원문": 꼬리[:120],
                "출처": "생육및장애온도표", "출처파일": fname,
                "위치": f"표{gi}/행{ri}/4",
            })
        # 동해 값을 떼고 남은 것이 장애온도 문장이다.
        # ⚠ '-?\d*' 로 뭉뚱그리면 뒤따르는 온도까지 먹는다.
        #     '-10 25℃ 이상 : 생육 정지'  →  '℃ 이상 : 생육 정지'   (시금치·상추·딸기가 사라졌다)
        #   앞머리 숫자(범위 포함) 하나만 정확히 떼어낸다.
        머리 = re.match(rf"\s*-?{N}(?:\s*[~～∼]\s*-?{N})?", 꼬리)
        장애 = 꼬리[머리.end():] if 머리 else 꼬리
        if "℃" in 장애:
            t, _ = temp_from_sentence(장애, 작물, fname, f"표{gi}/행{ri}/장애온도")
            for r in t:
                r["항목"] = "장애온도"
            temp += t
    return rule, temp


def winter_limit_table(g, gi, fname):
    """월동작물 동해한계온도표. 마늘·양파의 유일한 동해 근거다.

    ⚠ 머리글이 두 줄이다. 윗줄이 생육단계, 아랫줄이 월이다.
        행0  생육단계/작물별 ¦ 생육정지기․휴면기 ¦ 〃 ¦ 〃 ¦ 생육재생기 ¦ 〃 ¦ 개화유과기
        행1  생육단계/작물별 ¦ 12월            ¦ 1  ¦ 2  ¦ 3         ¦ 4  ¦ 5
      limit_table 로 보내면 행1이 데이터로 읽혀 **월 숫자 12·1·2·3·4·5 가 온도로** 들어간다.
      실제로 작물이 '생육단계' 인 행 6개가 그렇게 생겼다.

    ⚠ 작물 이름과 값이 다른 행에 있다.
        행9  '마 늘'      ¦ (전부 빈칸)
        행10 '(난 지 형)'  ¦ -5～6 …
        행11 '(한 지 형)'  ¦ -7～8 …
      값이 없는 행의 이름을 들고 있다가 괄호 행에 붙인다. 안 그러면 마늘이 통째로 빠진다.

    ⚠ 같은 단계 이름이 여러 칸에 걸쳐 있다(12월·1월·2월이 모두 '생육정지기․휴면기').
      칸마다 담으면 한 파일에서 같은 값이 3번 세어져 실린호가 48 이 된다. 실제로 그랬다.
      → (작물, 단계) 하나에 한 줄. 값은 가장 낮은 것을 쓴다(경보는 가장 추운 쪽이 기준).
    """
    if len(g) < 3:
        return []
    단계들 = [tidy(c) for c in g[0]]
    best = {}                                  # (작물, 단계) → (값, 원문, 위치)
    이름보류 = ""
    for ri, row in enumerate(g[2:], 2):
        원문이름 = tidy(row[0]) if row else ""
        if not 원문이름:
            continue
        값있나 = any(TEMP_RANGE.search(c) or re.match(rf"\s*-?{N}", c) for c in row[1:])
        if not 값있나:
            이름보류 = 원문이름                  # '마 늘' 처럼 이름만 있는 행
            continue
        이름 = 원문이름
        if 원문이름.startswith("(") and 이름보류:
            이름 = f"{이름보류}{원문이름}"        # 마늘(난지형)
        작물 = CROP_ALIAS.get(nospace(이름).split("(")[0])
        if not 작물:
            continue                           # 맥류·과수·목초는 등록 작물 밖
        for ci in range(1, len(row)):
            v = tidy(row[ci])
            m = TEMP_RANGE.search(v) or re.match(rf"\s*(-?{NUM})", v)
            if not v or v == "-" or not m:
                continue
            단계 = 단계들[ci] if ci < len(단계들) else ""
            # '-8～9' 는 -8 ~ -9 를 뜻한다. 더 낮은 쪽을 경보 기준으로 쓴다
            숫자 = [float(x) for x in re.findall(rf"-?{N}", v.replace(",", ""))]
            값 = -max(abs(x) for x in 숫자) if 숫자 and 숫자[0] < 0 else (숫자[0] if 숫자 else None)
            if 값 is None:
                continue
            # ⚠ 마늘은 난지형 -5~6 · 한지형 -7~8 로 갈린다. 합치면 한쪽이 사라진다.
            #   유형을 키에 넣어 둘 다 남긴다. 어느 쪽을 쓸지는 build 가 정한다.
            유형 = nospace(원문이름) if 원문이름.startswith("(") else ""
            key = (작물, 단계, 유형)
            if key not in best or 값 < best[key][0]:
                best[key] = (값, v, f"표{gi}/행{ri}/칸{ci}")
    out = []
    for (작물, 단계, 유형), (값, 원문, 위치) in best.items():
        out.append({
            "작물": 작물,
            "재해종류": "동해", "생육단계": 단계,
            "지표": "최저기온", "부등호": "<=",
            "값": f"{값:g}", "단위": "℃", "지속일": "", "등급": "",
            "조건원문": (f"{유형} {원문}" if 유형 else 원문)[:120],
            "출처": "월동작물동해한계표",
            "출처파일": fname, "위치": 위치,
        })
    return out


RICE_STAGE_ALIAS = {
    "출아": "육묘 출아", "녹화": "육묘 녹화", "경화": "육묘 경화",
    "새끼칠때": "분얼기", "새끼치기": "분얼기",
    "감수분얼기": "감수분열기",
}


def rice_stage_table(g, gi, fname):
    """벼 생육시기별 최적·최저·최고 한계온도. 10단계.

        생육시기 ¦ 생육시기 ¦ 온도(℃) ¦ 온도(℃) ¦ 온도(℃)
        생육시기 ¦ 생육시기 ¦ 최적    ¦ 최저    ¦ 최고
        발아    ¦ 발아    ¦ 30∼32  ¦ 10     ¦ 45

    ⚠ 이 표에는 작물 칸이 없다. 벼 전용이라 문서 맥락에서만 벼임을 안다.
      '작물별' 칸을 찾는 조건으로는 절대 안 걸린다.

    ⚠ 등숙 최적 21~22℃ 가 여기 있다.
      벼 목표값 1,100~1,200 이 ② 단위임을 검산할 때 쓴 값이다(GDD_작업인계 §3-4).

    최적 칸은 규칙이 아니라 참고값이므로 담지 않는다.
    """
    # 머리글 둘째 줄에서 최적/최저/최고 칸 위치를 찾는다
    sub = g[1] if len(g) > 1 else []
    pos = {}
    for ci, c in enumerate(sub):
        n = nospace(c)
        if n in ("최적", "최저", "최고"):
            pos[n] = ci
    if "최저" not in pos and "최고" not in pos:
        return []
    out = []
    for ri, row in enumerate(g[2:], 2):
        단계 = tidy(row[0])
        if not 단계 or nospace(단계) == "생육시기":
            continue
        # 앞 두 칸이 같은 값이면(병합된 칸) 뒤엣것을 덧붙인다.
        # ⚠ 단 둘째 칸이 숫자면 그건 단계 이름이 아니라 온도값이다.
        #   호마다 표 모양이 달라서, 그냥 붙이면 "발아 30∼32" 같은 단계명이 생긴다.
        #   그러면 같은 단계가 두 꼴로 중복된다. 실제로 그렇게 나왔었다.
        second = tidy(row[1]) if len(row) > 1 else ""
        if second and second != 단계 and not re.search(r"\d", second):
            단계 = f"{단계} {second}"
        단계 = RICE_STAGE_ALIAS.get(nospace(단계), 단계)
        for key, (종류, 지표, 부등호) in (
            ("최저", ("한계_최저", "최저기온", "<=")),
            ("최고", ("한계_최고", "최고기온", ">=")),
        ):
            ci = pos.get(key)
            if ci is None or ci >= len(row):
                continue
            v = tidy(row[ci])
            m = re.search(rf"({NUM})", v)
            if not v or not m:
                continue
            out.append({
                "작물": RICE,
                "재해종류": 종류, "생육단계": 단계,
                "지표": 지표, "부등호": 부등호,
                "값": to_num(m.group(1)), "단위": "℃", "지속일": "", "등급": "",
                "조건원문": v[:120], "출처": "벼생육시기별한계온도",
                "출처파일": fname, "위치": f"표{gi}/행{ri}",
            })
    return out


def from_disaster():
    """재해예방정보 첨부 112개에서 **표만** 읽는다. 본문은 읽지 않는다(위 주석 참고).

    ⚠ 저온해 43개는 등록 작물이 0건이라 통째로 건너뛴다(사과·배·복숭아·매실·포도 고정).
    """
    rule, table, temp = [], [], []
    base = RAW / "재해예방정보" / "첨부"
    for p in sorted(base.rglob("*")):
        if not p.is_file():
            continue
        계열 = p.relative_to(base).parts[0]
        if 계열 in SKIP_SERIES:
            찾음 = series_crop_hit(p)
            if not 찾음:
                continue                  # 확인함. 등록 작물이 없다
            print(f"  ⚠ {계열} 에 '{찾음}' 이(가) 있습니다. 건너뛰지 않고 읽습니다 — {p.name}")

        try:
            _, grids = read_doc(p)
        except Exception:  # noqa: BLE001
            continue

        for gi, g in enumerate(grids):
            # ⚠ PDF 판본은 맨 앞에 빈 칸이 한 줄 더 붙는다. 머리글이 g[0][0] 에 없어
            #   '작물별' 조건이 통째로 빗나갔다. 18개 호 중 PDF 2개를 놓치고 있었다.
            #   모든 행에서 비어 있는 앞 칸은 떼고 본다.
            while g and all(len(r) > 1 and not r[0].strip() for r in g):
                g = [r[1:] for r in g]
            flat = nospace("".join("".join(r) for r in g))
            head = [nospace(c) for c in g[0]]

            # ① 고온해 위험발령 기준 — 등급(주의/위험)이 붙는 유일한 자료
            if "작물종류" in flat and ("주의" in flat and "위험" in flat):
                for ri, row in enumerate(g[1:], 1):
                    if len(row) < 3 or not row[0].strip():
                        continue
                    작물 = CROP_ALIAS.get(nospace(row[0]))
                    for t in parse_threshold(row[2], "최고기온"):
                        rule.append({
                            "작물": 작물 or tidy(row[0]),
                            "재해종류": "고온해", "생육단계": tidy(row[1]),
                            "지표": t.get("지표", ""), "부등호": t.get("부등호", ""),
                            "값": t.get("값", ""), "단위": t.get("단위", "℃"),
                            "지속일": t.get("지속일", ""), "등급": t.get("등급", ""),
                            "조건원문": tidy(row[2])[:200], "출처": "고온해기준표",
                            "출처파일": p.name, "위치": f"표{gi}/행{ri}",
                        })

            # ② 한계온도표 — 작물 여럿이 한 칸 안에 줄로 들어 있다
            #    ⚠ 공백으로 이어붙이면 짝을 잃는다. 칸 안 줄바꿈으로 나눠 편다
            # ①-b 생육및장애온도표의 **머리글만 온 격자** (PDF 판에서만 생긴다)
            #     ⚠ '작물별' 이 행0 에 없다. 행1 에 있고, 2023 판은 '작' / '물 별' 로 쪼개진다.
            #       그래서 head[0] 을 보는 조건으로는 영영 안 걸린다.
            #     ⚠ hwpx 판도 2행이지만 그쪽은 행1 이 데이터라 숫자가 있다.
            #       숫자가 하나도 없는 것이 '머리글만' 이라는 표시다.
            if (len(g) <= 2 and "작물별" in flat
                    and ("한량계" in flat or "장애온도" in flat)
                    and not re.search(r"\d", flat)
                    and gi + 1 < len(grids)):
                r3, t3 = disorder_body_table(grids[gi + 1], gi + 1, p.name)
                rule += r3
                temp += t3
                continue

            if ("작물별" in nospace(head[0] if head else "")) and "℃" not in flat[:20]:
                # ⚠ 머리글이 '생육단계/작물별' 인 것은 월동작물 동해한계표다.
                #   모양이 달라서 limit_table 로 보내면 월 숫자가 온도로 들어간다.
                if "생육단계" in nospace(head[0]):
                    rule += winter_limit_table(g, gi, p.name)
                else:
                    is_생육장애 = "한량계" in flat or "장애온도" in flat
                    rule += limit_table(fix_pdf_cols(g), gi, p.name, is_생육장애)
                for ri, row in enumerate(g):
                    table.append({
                        "작물": "", "출처파일": p.name, "위치": f"표{gi}/행{ri}",
                        "칸수": len(row),
                        "내용": " ¦ ".join(c.replace("\n", "/") for c in row)[:600],
                    })

            # ③ 벼 생육시기별 한계온도 — 표 안에 작물 이름이 없다
            #    ⚠ ①② 는 '작물별' 칸이 있는 표만 잡는다. 이 표는 벼 전용이라 그 칸이 없어
            #      통째로 빠져 있었다. "표에 작물 이름이 있다" 는 전제를 깨야 한다.
            if head[:1] == ["생육시기"] and "온도" in flat and len(g) >= 8:
                rule += rice_stage_table(g, gi, p.name)
                for ri, row in enumerate(g):
                    table.append({
                        "작물": RICE, "출처파일": p.name, "위치": f"표{gi}/행{ri}",
                        "칸수": len(row),
                        "내용": " ¦ ".join(c.replace("\n", "/") for c in row)[:600],
                    })
    # ⚠ 여기서 접지 않는다. 한계온도표는 주간농사정보에도 있어서
    #   원본마다 접으면 같은 규칙의 실린호가 18과 22 로 따로 세어진다.
    #   main 이 다 모은 뒤 한 번만 접는다.
    return rule, table, temp


def run():
    """첨부 표만 읽는다. 본문은 읽지 않는다(안읽은것.md §2-3)."""
    rule, table, temp = from_disaster()
    return {"mid_rule.csv": rule, "mid_temp.csv": temp, "mid_table.csv": table}


def 원본파일들():
    """⚠ 저온해는 여기서도 거르지 않는다. **날 자료는 다 남긴다.**
    등록 작물이 0건이라 규칙으로 안 만들 뿐이고, 원문은 남아 있어야 한다."""
    b = RAW / "재해예방정보" / "첨부"
    return sorted(q for q in b.rglob("*") if q.is_file()) if b.exists() else []


def 계열(p):
    b = RAW / "재해예방정보" / "첨부"
    return p.relative_to(b).parts[0]


# 이 파일만 따로 돌릴 때 쓴다. extract.py 는 run() 을 바로 부른다.
NAME = "재해예방정보"


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
