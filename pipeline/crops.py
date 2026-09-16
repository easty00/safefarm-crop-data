# 작물 등록표와 작물 이름 찾기.
#
#     from crops import CROPS, WANT, CROP_ALIAS, MAIN_CROPS, is_main, crops_in_line, RICE
#
# ★ 새 작물은 이 파일의 CROPS 한 곳에만 더한다. 나머지는 전부 여기서 만들어진다.
#   예전에는 등록표와 별칭표가 따로 있어 한쪽만 적으면 그 작물이 조용히 빠졌다.

import re
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "원본"


def nospace(s):
    return "".join((s or "").split())


# 작물 등록표  ★ 새 작물은 여기 한 곳에만 더한다
#
# 예전에는 WANT 와 CROP_ALIAS 두 군데에 따로 적어야 했다. 한쪽만 적으면
# 농작업일정은 잡히는데 재해예방정보는 통째로 안 잡히고, **아무도 안 알려줬다.**
# 그래서 한 줄에 모아두고 나머지는 전부 여기서 만든다.
#
#   표준이름    파이프라인이 쓰는 하나의 이름
#   본선        True  = 제품에 넣을 작물          False = 근거 추적용으로만 뽑는다
#   다른표기     원문 표·본문에서 만나는 딴 이름    "가루쌀" 은 벼, "고추(피망)" 은 고추
#   문서         농작업일정 cntntsNo → (그쪽 이름, 본선문서인가)
#               ⚠ cntntsNo 는 원본/농작업일정/raw/lst_*.xml 에 있다. 짐작하지 말 것
#               ⚠ 여기 적은 이름이 아니라 lst_*.xml 의 이름이 mid_schedule 에 들어간다
#
# 작물을 더할 때
#   ① lst_*.xml 에서 cntntsNo 를 찾아 이 표에 한 줄 더한다
#   ② 돌린다. 등록했는데 원본에 없으면 시작할 때 경고가 뜬다
#   ③ 재해예방정보 표에 그 작물이 딴 이름으로 적혀 있으면 '다른표기' 에 더한다
# ─────────────────────────────────────────────────────────────────────

CROPS = [
    # 표준이름,    본선,  다른표기,        문서 {cntntsNo: (이름, 본선문서)}
    ("벼",        True,  ["가루쌀"],      {"30697": ("벼 기계이앙재배", True),
                                          "30698": ("벼 직파재배", False)}),
    ("배추",      True,  [],             {"30618": ("배추", True),
                                          "30619": ("배추(고랭지재배)", True)}),
    ("무",        True,  [],             {"30614": ("무", True),
                                          "30615": ("무(고랭지재배)", True)}),
    ("고추",      True,  ["고추(피망)"],   {"30600": ("고추(보통재배)", True)}),
    ("감자",      True,  [],             {"30699": ("감자", True)}),
    ("상추",      True,  [],             {"30624": ("상추", True)}),
    ("시금치",    True,  [],             {"30628": ("시금치", True)}),
    ("양파",      True,  [],             {"30633": ("양파", True)}),
    ("마늘",      True,  [],             {"30611": ("마늘", True),
                                          "30612": ("마늘(잎마늘)", False)}),
    ("수박",      True,  [],             {"30627": ("수박", True)}),
    ("방울토마토", True,  ["토마토"],       {"30646": ("토마토,방울토마토", True)}),
    # ↓ 본선이 아니다. 뽑아만 두고 build 가 거른다.
    #   잎마늘은 마늘 base_temp 4℃ 의 출처라 근거 추적에 필요해서 마늘 밑에 달아뒀다.
    ("딸기",      False, [],             {"30609": ("딸기(사계성여름재배)", False)}),
    ("옥수수",    False, [],             {"30709": ("옥수수", False)}),
]

# ─────────────────────────────────────────────────────────────────────
# 2026-09-16 에 버린 작물 넷
#
# 다섯 원본 날 자료(out/원본별/*/tables.csv · texts.csv)를 전부 뒤져 센 결과다.
# **안 읽어서가 아니라 원본에 없다.**
#
#     작물   재해 단계 고온 경보 숙기   남은 것
#     당근     0   0   0   0   0    작형6 · 일정37   달력밖에 못 준다
#     파       0   0   0   0   0    작형2 · 일정36   〃
#     쪽파      0   0   0   0   0    작형2 · 일정22   〃
#     가지      1   0   0   0   0    작형6 · 일정23   재해 1건뿐
#
# ⚠ 당근이 원본에 아주 없는 것은 아니다. 다만 쓸 수 있는 꼴이 아니다.
#     농작업일정 171번   일정·작형 (재해 규칙이 아니다)
#     병해충    123번   본문 서술. 경보 대상작물에는 0건
#     재해예방정보  2번   "대파작물 : 메밀, 녹두, 가을감자, 당근, 무, …"
#                        ← 재해 뒤 **다시 심을** 작물 목록이지 당근의 재해 규칙이 아니다
#     주간농사정보  0번 · 품종정보 0번
#
# ⚠ 가지는 base_temp 도 미결이었다. 논문 10~11 vs 국내 17 (확인필요 §2-1).
#   이번에 찾은 국내 근거도 그 17이라 확정표가 "제외" 라고 한 값이다.
#
# 되살리려면 위 CROPS 에 아래 줄을 다시 넣으면 된다. 원본은 그대로 있다.
#     ("당근", True, [], {"30605": ("당근", True)}),
#     ("파",   True, [], {"30647": ("파", True)}),
#     ("쪽파", False, [], {"30639": ("쪽파", False)}),
#     ("가지", True, [], {"30770": ("가지", True)}),
# ─────────────────────────────────────────────────────────────────────


def _build_registry():
    """등록표 하나에서 나머지를 만든다. 손으로 두 번 적지 않는다."""
    want, alias, main, std = {}, {}, set(), {}
    for 표준, 본선, 다른표기, 문서 in CROPS:
        if 본선:
            main.add(표준)
        for n in [표준, *다른표기, *(nm for nm, _ in 문서.values())]:
            key = "".join(n.split())
            if key in alias and alias[key] != 표준:
                raise ValueError(f"작물 이름이 겹칩니다: {n} → {alias[key]} / {표준}")
            alias[key] = 표준
        for no, (nm, 본선문서) in 문서.items():
            if no in want:
                raise ValueError(f"cntntsNo 가 겹칩니다: {no}")
            want[no] = (nm, 본선문서)
            std[no] = 표준
    return want, alias, main, std


# cntntsNo → (농작업일정 이름, 본선문서인가).  농작업일정 raw 를 고를 때 쓴다
# 이름(공백 지움) → 표준이름.  재해예방정보 표에서 작물을 알아볼 때 쓴다
# 본선 표준이름들.  mid_*.csv 의 '본선' 칸이 Y 가 되는 기준이다
WANT, CROP_ALIAS, MAIN_CROPS, CROP_STD = _build_registry()


def is_main(작물):
    """mid_*.csv 의 '본선' 칸. 등록표의 '본선' 하나만 본다.

    ⚠ 예전 칸 이름은 '14작물' 이었다. 수가 이름에 박혀 있어 작물을 줄이자
      20개 파일 70여 곳이 한꺼번에 낡았다. **수를 이름에 넣지 않는다.**
    """
    return "Y" if 작물 in MAIN_CROPS else ""


# ─────────────────────────────────────────────────────────────────────
# 공통
# ─────────────────────────────────────────────────────────────────────
#   무   무피복 · 무가온하우스 · 무경운
#   파   파종 · 직파 · 파열
#   가지  열매가지 · 새 가지 · "잎, 가지 등의 손상"   ← 과수의 枝. 두 글자인데도 오탐이다
AMBIGUOUS = {"무", "파", "가지"}

# 통째로 막을 것까지는 없고 특정 꼴만 빼면 되는 이름.
#   벼  "피해가 벼운 나무" 의 '벼' (가볍다) 하나뿐이다. 나머지 5천여 건은 전부 벼다.
NOT_CROP = {"벼": re.compile(r"벼(?=[운워웠슬])")}

BRACKET = re.compile(r"[(（\[]\s*([^)）\]]{1,40})\s*[)）\]]")
SPLIT_DOT = re.compile(r"[·‧・,/]| 및 |과 |와 ")


def crops_in_line(line):
    """한 줄에서 작물을 찾는다. 못 찾으면 빈 집합.

    ⚠ 괄호 안을 먼저 본다. 이 문서들은 작물을 괄호로 묶어 적는다.
        • (마늘 ‧ 양파) 배수로 정비          ❍ (양파) 25℃ 이상의 고온에 생육 저하
      괄호 밖 이름은 **겹치지 않는 이름만** 받는다.
    """
    found = set()
    for m in BRACKET.finditer(line):
        for part in SPLIT_DOT.split(m.group(1)):
            c = CROP_ALIAS.get(nospace(part))
            if c:
                found.add(c)
    flat = nospace(line)
    # 절 제목은 괄호 대신 가운뎃점으로 잇는다 — "2 여름 배추 ‧ 무", "마늘·양파"
    # 겹치는 이름이라도 옆에 다른 작물이 붙어 있으면 작물로 본다
    for m in re.finditer(r"([가-힣]{1,6})\s*[·‧・]\s*([가-힣]{1,6})", line):
        a, b = CROP_ALIAS.get(nospace(m.group(1))), CROP_ALIAS.get(nospace(m.group(2)))
        if a and b:
            found.update((a, b))
    for name, std in CROP_ALIAS.items():
        if name in AMBIGUOUS or std in AMBIGUOUS:
            continue                      # 괄호로만 인정
        if name not in flat:
            continue
        bad = NOT_CROP.get(name) or NOT_CROP.get(std)
        if bad and not re.search(rf"{re.escape(name)}(?!{bad.pattern.split('(?=')[1][:-1]})", flat):
            continue                      # 그 꼴로만 나왔다
        found.add(std)
    return found

# ⚠ 이 표에는 작물 칸이 없는 자료가 있다(벼 생육시기별 한계온도). 문서 맥락으로만 벼임을 안다.
#   이름이 바뀌어도 한 곳만 고치면 되도록 등록표에서 가져온다.
RICE = CROP_ALIAS.get("벼", "벼")


def link_raw_names():
    """원본 lst_*.xml 의 **진짜 이름**을 별칭에 잇는다. 불러오면 바로 한 번 돈다.

    ⚠ mid_schedule 에는 등록표에 적은 이름이 아니라 lst_*.xml 의 이름이 들어간다.
      둘이 어긋나면 그 작물은 표준명으로 이어지지 않는다.
      실제로 30697 을 '벼' 라 적어뒀는데 원본은 '벼 기계이앙재배' 라서
      일정 28행이 표준명 '벼' 에 안 붙었다.

    ⚠ 예전에는 crop_map() 안에서 했다. 그러면 농작업일정을 안 읽는 원본별 스크립트에서는
      이 이음이 없어 같은 이름이 원본마다 다르게 풀린다. 그래서 등록표 옆으로 옮겼다.
    """
    lst = RAW / "농작업일정" / "raw"
    if not lst.exists():
        return {}
    out = {}
    for p in sorted(lst.glob("lst_*.xml")):
        for it in ET.parse(p).getroot().findall(".//item"):
            no = (it.findtext("cntntsNo") or "").strip()
            if no not in WANT:
                continue
            실제 = (it.findtext("sj") or "").strip()
            파일 = (it.findtext("orginlFileNm") or it.findtext("fileName") or "").strip()
            out[no] = (실제, 파일)
            표준 = CROP_STD[no]
            키 = nospace(실제)
            if 키 and CROP_ALIAS.get(키, 표준) == 표준:
                CROP_ALIAS[키] = 표준
    return out


RAW_NAMES = link_raw_names()      # cntntsNo → (원본 이름, 첨부파일명)


def registry_report():
    """등록표와 원본이 어긋나면 알린다. 조용히 빠지면 못 찾는다."""
    빠짐 = [(no, nm) for no, (nm, _) in WANT.items() if no not in RAW_NAMES]
    if 빠짐:
        print("  ⚠ 등록했는데 원본 lst_*.xml 에 없는 작물:")
        for no, nm in 빠짐:
            print(f"      cntntsNo {no}  {nm}   ← 번호가 맞는지, 그 작물을 받았는지 확인하세요")
    for no, (실제, _fn) in RAW_NAMES.items():
        if 실제 != WANT[no][0]:
            print(f"  ⚠ 등록표 이름과 원본 이름이 다릅니다: cntntsNo {no}  "
                  f"적음={WANT[no][0]!r}  원본={실제!r}  → 원본 쪽을 씁니다")


def 현황(찍기=True):
    """등록표의 지금 상태. 문서에 베껴 적지 말고 이걸 부른다.

    ⚠ 작물 수를 글에 박으면 늘거나 줄 때마다 문서가 틀린다.
      실제로 '14작물' 이라는 말이 20개 파일에 70여 번 박혀 있다가 한꺼번에 낡았다.
      **수와 목록은 여기서만 만든다.**
    """
    본 = [c[0] for c in CROPS if c[1]]
    확 = [c[0] for c in CROPS if not c[1]]
    글 = [
        f"작물 {len(CROPS)} = 본선 {len(본)} + 확인용 {len(확)}   ·   등록 문서 {len(WANT)}개",
        f"  본선   {' · '.join(본)}",
        f"  확인용  {' · '.join(확)}    ← '본선' 칸이 빈칸으로 나간다",
    ]
    여럿 = [(표준, [nm for nm, _ in 문서.values()])
            for 표준, _본, _별, 문서 in CROPS if len(문서) > 1]
    if 여럿:
        글.append("  문서가 둘인 작물 (작형 갈래)")
        for 표준, 이름들 in 여럿:
            글.append(f"      {표준:8}{' · '.join(이름들)}")
    if 찍기:
        print("\n".join(글))
    return "\n".join(글)


if __name__ == "__main__":
    현황()
    registry_report()
