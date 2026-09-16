# 병해충 발생정보 PDF 첫 쪽의 **요약표**를 읽는 도구입니다.
#
#   parse_summary    작물군 · 경보등급 · 병/해충/바이러스 구분 · 이름 · 대상작물
#   split_top        괄호 밖 쉼표에서만 쪼갠다
#
# 출처 : 보관/병해충발생정보/pest.py
#
# ⚠ 요약표 모양이 네 가지로 섞여 있습니다. 한 호만 보고 파서를 만들었다가
#   2023~2024년을 절반 넘게 놓친 적이 있습니다 (269행 → 고친 뒤 1,339행).
#
#     ① 한 줄에 둘    ▶ (주 의 보) 병 : 붉은곰팡이병 / 해충 : 열대거세미나방
#     ② 여러 줄로     ▶ (예   보)  다음 줄에  - 병 : …  - 해충 : …
#     ③ 구분 없이     ▶ (주의보) : 노균병(양파), 흑색썩음균핵병(마늘, 양파)
#     ④ 줄바꿈 이어짐  … 노균병, 역병,   다음 줄에  딸기 꽃곰팡이병
#
# ⚠ 그냥 쉼표로 쪼개면 "잎마름병(마늘, 양파)" 가 둘로 갈립니다.
#   괄호 안은 대상 작물이므로 split_top 으로 괄호 밖에서만 쪼갭니다.

import re

GRADES = ("경보", "주의보", "예보")


GRADE_RE = re.compile(r"[▶►]\s*\(\s*([가-힣\s]{2,6}?)\s*\)\s*[:：]?\s*(.*)$")


def grade_of(line: str):
    """`▶` 뒤에서 등급과 나머지를 떼어냅니다. 돌려주는 것 : (등급, 나머지)

    ⚠ PDF 판에 따라 등급 글자가 괄호 안팎으로 옮겨 다닙니다. 세 가지를 다 겪었습니다.

        ▶ (주 의 보) 병 : 잎마름병(마늘, 양파)      정상
        ▶ (            )주  의  보                괄호 밖 뒤   ← 2026 제5호 layout
        ▶ 예    보( )  병 붉은곰팡이병: 맥류( )       괄호 밖 앞   ← 같은 호 plain

    괄호 위치로 찾지 말고 **등급 낱말 자체**를 찾습니다. 글자 사이 공백도 견딥니다
    ("주 의 보"). 이 한 호가 통째로 0행이었습니다.
    """
    m = re.search(r"[▶►]", line)
    if not m:
        return "", ""
    tail = line[m.end():]
    for g in GRADES:                       # 경보 · 주의보 · 예보
        mm = re.search(r"\s*".join(g), tail[:30])
        if not mm:
            continue
        cut = mm.end()
        par = tail.find(")", 0, cut + 8)   # 등급 곁의 닫는 괄호까지 버린다
        if par >= 0:
            cut = max(cut, par + 1)
        return g, tail[cut:].lstrip(" :：")
    return "", ""
# 다음 줄로 이어지는 구분 줄: "  - 병 : 잿빛곰팡이병, 균핵병"


GROUP_RE = re.compile(r"^\s*([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ])\s*[.．]\s*([가-힣\s]{2,12})\s*$")
# 본문 항목: "1  이삭도열병  <주의보>"


KINDS = ("병", "해충", "바이러스", "잡초", "선충")
# 작물군 머리: "Ⅰ. 식량작물" / "Ⅲ. 과    수"


SUB_RE = re.compile(r"^\s*[-–ㅇ○❍]\s*([가-힣\s]{1,5}?)\s*[:：]\s*(.*)$")
# 구분은 병·해충만이 아니다. 바이러스가 따로 나온다


def split_top(text: str) -> list[str]:
    """괄호 밖의 쉼표·가운뎃점에서만 쪼갠다.

    그냥 쪼개면 "잎마름병(마늘, 양파)" 가 "잎마름병(마늘" 과 "양파)" 로 갈린다.
    괄호 안 쉼표는 대상 작물 목록이라 끊으면 안 된다.
    """
    out, buf, depth = [], [], 0
    for ch in text:
        if ch in "(（":
            depth += 1
        elif ch in ")）":
            depth = max(0, depth - 1)
        if depth == 0 and ch in ",、·・":
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf))
    return out


def parse_summary(text: str, r: dict) -> list[dict]:
    """첫 쪽 요약에서 작물군 × 등급 × 구분 × 이름을 뽑는다.

    첫 판은 한 호만 보고 만들었다가 2023~2024년을 절반 넘게 놓쳤다.
    실제로는 네 가지 모양이 섞여 있다.

      ① 한 줄에 둘      ▶ (주 의 보) 병 : 붉은곰팡이병 / 해충 : 열대거세미나방
      ② 여러 줄로       ▶ (예   보)
                          - 병 : 잿빛곰팡이병, 균핵병
                          - 해충 : 총채벌레류
      ③ 구분 없이       ▶ (주의보) : 노균병(양파), 흑색썩음균핵병(마늘, 양파)
      ④ 줄바꿈으로 이어짐  ... 노균병, 역병,
                          딸기 꽃곰팡이병          ← 앞 줄이 쉼표로 끝나면 이어진 것

    그리고 구분이 '병'·'해충'만 있는 게 아니다. '바이러스'가 따로 나온다.
    등급과 이름 글자 사이에 공백이 들어가므로("주 의 보", "무 름 병") 지우고 맞춘다.
    """
    out, group, grade, kind = [], "", "", ""
    open_list = False          # 앞 줄이 쉼표로 끝나 다음 줄로 이어지는 중인가

    def add(names: str, src: str) -> bool:
        """이름 목록을 쪼개 담는다. 쉼표로 끝나면 다음 줄로 이어진다는 뜻이다."""
        for name in split_top(names):
            name = re.sub(r"\s+", "", name).strip(" .·/")
            if not 2 <= len(name) <= 40:
                continue
            # 뒤에 붙은 괄호는 대상 작물이다. "잎마름병(마늘,양파)" → 잎마름병 / 마늘,양파
            # ⚠ 이 가르기를 **먼저** 해야 한다. 꼬리 정리를 앞에 두었다가
            #   닫는 괄호가 먼저 지워져 대상작물이 1,464행 전부 빈 적이 있다.
            m = re.match(r"(.+?)[(（]([^)）]*)[)）]$", name)
            병해충명, 대상작물 = (m.group(1), m.group(2)) if m else (name, "")
            # 가른 뒤에 목록 끝의 '등' 과 짝 잃은 괄호를 떼어낸다.
            #   "가루이류 등" → '가루이류등' · "꽃매미 등)" → '꽃매미등)' 처럼 남는다.
            #   이름이 갈리면 같은 병해충이 두 가지로 세어진다.
            병해충명 = re.sub(r"등$", "", re.sub(r"[()（）]+$", "", 병해충명)).strip(" .·/")
            if not 2 <= len(병해충명) <= 40:
                continue
            out.append({"연도": r["연도"], "호수": r["호수"], "기간": r["기간"],
                        "작물군": group, "등급": grade,
                        "구분": kind or "미분류",
                        "병해충명": 병해충명,
                        "대상작물": 대상작물,
                        "원문": " ".join(src.split())[:120]})
        return names.rstrip().endswith((",", "、"))

    def spread(rest: str, src: str) -> bool:
        """'병 : a, b / 해충 : c' 처럼 한 줄에 여러 구분이 붙은 것을 푼다."""
        nonlocal kind
        last = False
        for chunk in rest.split("/"):
            if not chunk.strip():
                continue
            m = re.match(r"\s*([가-힣]{1,5})\s*[:：]\s*(.*)$", chunk)
            if m and re.sub(r"\s+", "", m.group(1)) in KINDS:
                kind = re.sub(r"\s+", "", m.group(1))
                last = add(m.group(2), src)
            else:
                last = add(chunk, src)
        return last

    for raw in text.splitlines():
        line = raw.rstrip()
        # 첫 쪽 요약만 읽는다. 본문으로 넘어가면 멈춘다
        if "===== p.2" in line or "농약 안전사용기준" in line:
            break

        g = GROUP_RE.match(line)
        if g:
            group = re.sub(r"\s+", "", g.group(2))
            kind, open_list = "", False
            continue

        g, rest = grade_of(line)
        if g:
            grade = g
            kind, open_list = "", False
            rest = rest.strip()
            if rest:                       # ① ③ — 같은 줄에 이름이 이어짐
                open_list = spread(rest, line)
            continue                       # ② — 등급만 있고 다음 줄로 넘어감

        s = SUB_RE.match(line)
        if s and grade and re.sub(r"\s+", "", s.group(1)) in KINDS:
            kind = re.sub(r"\s+", "", s.group(1))
            open_list = spread(s.group(2), line)
            continue

        if open_list and line.strip():     # ④ 줄바꿈으로 이어진 이름
            open_list = add(line, line)

    return out
