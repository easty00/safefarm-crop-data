# 원본별 추출기(src_*.py)가 함께 쓰는 부품입니다.
#
#     from common import tidy, NUM, TEMP_RANGE, temp_from_sentence, limit_table, rows_out
#
# ⚠ **여기에는 "무엇을 규칙으로 삼을지" 를 넣지 않습니다.** 그 판단은 원본별 파일에 있습니다.
#   여기 있는 것은 어느 원본에서나 같은 뜻인 것들뿐입니다 —
#   글자 다듬기 · 숫자 읽기 · 온도 문장 해석 · 표 읽기 · 접기 · 파일 쓰기.
#
# ⚠ 한 원본에서만 쓰는 것은 그 원본 파일에 두세요. 여기가 다시 비대해집니다.

import csv
import re
from collections import Counter
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RAW = ROOT / "원본"
OUT = HERE / "out"
sys.path.insert(0, str(ROOT / "feature"))

from crops import AMBIGUOUS, CROP_ALIAS, is_main, nospace  # noqa: E402
from hwpx_table import grids_of, read_any  # noqa: E402

# 산출물을 어디에 쓸지. 원본별 스크립트는 out/원본별/<이름>/ 을 가리킨다.
# ⚠ 이건 모듈 전역이다. 원본별 스크립트를 부른 뒤 되돌리지 않으면
#   **최종 결과가 마지막 원본 폴더에 쓰인다.** 실제로 그랬다 — extract.py 가 set_out(None) 한다.
OUT_DIR = None


# 중간 CSV 의 칸. 원본이 달라도 같은 이름·같은 차례를 쓴다.
# ⚠ 맨 앞 '원본' 은 어느 폴더에서 온 값인지다. 접을 때 '출처들' 을 세는 데 쓴다.
#   이게 없으면 합쳐진 뒤 "배추 -8 을 어느 원본들이 말했나" 를 답할 수 없다.
# ⚠ 이게 어긋나면 extract.py 가 모을 때 칸이 밀린다. 바꿀 일이 있으면 common.py 에서 한 번에.
COLS = {
    "mid_schedule.csv": ["원본", "작물", "cntntsNo", "작형", "정보구분", "분류", "작업명",
                         "시작월", "시작순", "종료월", "종료순", "종료이듬해", "원본종료월",
                         "시작순번", "종료순번", "지속순수", "시작중앙일", "종료중앙일",
                         "씨뿌림", "아주심기", "수확기", "성출하기", "출처", "출처파일", "위치"],
    "mid_temp.csv": ["원본", "작물", "종류", "항목", "값최소", "값최대", "단위",
                     "실린호", "원본수", "출처들", "원문", "출처파일", "위치"],
    "mid_sumtemp.csv": ["원본", "작물", "품종숙기", "일수", "적산온도", "구간",
                        "실린호", "원본수", "출처들", "원문", "출처파일", "위치"],
    "mid_rule.csv": ["원본", "작물", "본선", "재해종류", "생육단계", "지표", "부등호", "값", "단위",
                     "지속일", "등급", "실린호", "원본수", "출처들", "출처파일수",
                     "조건원문", "출처", "출처파일", "위치"],
    "mid_text.csv": ["원본", "작물", "구분", "절", "항목", "깊이", "실린호", "원본수", "출처들", "본문", "출처파일", "위치"],
    "mid_table.csv": ["원본", "작물", "칸수", "내용", "출처파일", "위치"],
}


def set_out(d):
    """산출물을 어디에 쓸지 정한다."""
    global OUT_DIR
    OUT_DIR = d


# ⚠ 빼기표는 한 가지가 아니다. 원문에 온갖 대시가 섞여 있다.
#     "–5∼-6℃"  ← 앞은 EN DASH(U+2013), 뒤는 보통 하이픈
#   NUM 은 하이픈만 받으므로 그냥 두면 **음수가 양수로 읽힌다.**
#   실제로 마늘 동해한계 -5~-6 이 "5 ~ -6" 으로 들어갔다.
DASH = re.compile(r"[‐‑‒–—―−－]")


def tidy(s):
    return DASH.sub("-", re.sub(r"\s+", " ", s or "")).strip()


# ─────────────────────────────────────────────────────────────────────
# 원본 읽기 — 한 번 읽어 표와 본문을 둘 다 얻는다
# ─────────────────────────────────────────────────────────────────────

# 한 번 읽은 문서를 들고 있는다. dump_raw 와 추출기가 같은 파일을 두 번 읽지 않게.
# ⚠ 병해충 PDF 는 파일당 3초다. 두 번 읽으면 3분이 6분이 된다.
#   한 원본을 끝내면 clear_read_cache() 로 비운다 — 안 비우면 메모리에 계속 쌓인다.
_READ = {}
READ_FAIL = []      # 읽다 넘어진 파일. dump_raw 가 끝에 알린다


def clear_read_cache():
    _READ.clear()
    READ_FAIL.clear()


def doc_kind(p):
    """파일 앞 4바이트로 형식을 본다. 확장자를 믿지 않는다(CLAUDE.md)."""
    h = p.read_bytes()[:4]
    if h[:4] == b"%PDF":
        return "PDF"
    if h[:2] == b"PK":
        return "hwpx"
    if h[:4] == b"\xd0\xcf\x11\xe0":
        return "hwp"
    if h[:4] == b"HWP ":
        return "\ud55c\uae00 3.0"
    if h[:3] == b"\xff\xd8\xff" or h[:4] == b"\x89PNG" or h[:3] == b"GIF":
        return "\uc0ac\uc9c4"
    return "?"


def read_doc(p):
    """문서 하나에서 (본문글자, 표격자목록) 을 얻는다. 같은 파일은 한 번만 읽는다.

    ⚠ 형식마다 어느 쪽이 공짜인지 다르다. 두 번 읽지 않도록 갈라 쓴다.
        PDF    grids_of 가 글자와 표를 함께 준다 (pypdf 가 비싸다 — 파일당 3초)
        hwpx   grids_of 는 표만. 글자는 read_any 로 따로 (둘 다 싸다)
        hwp    grids_of 가 글자만, 표는 없다
    """
    if p in _READ:
        return _READ[p]
    형식 = doc_kind(p)
    표실패 = ""
    try:
        글, 표 = grids_of(p)
    except Exception as e:  # noqa: BLE001
        글, 표, 표실패 = "", [], f"{type(e).__name__}: {e}"
    if not 글:
        try:
            글 = read_any(p)
        except Exception as e:  # noqa: BLE001
            글 = ""
            READ_FAIL.append((p.name, f"글자 {type(e).__name__}: {e}"))
    # ⚠ 실패를 조용히 삼키면 그 파일이 1층에서 통째로 사라진다. 사라진 줄도 모른다.
    #   다만 **없는 게 맞는 것을 실패로 세면 안 된다** (CLAUDE.md 문서 파싱 도구 절).
    #       사진(JPEG 등)   글자도 표도 없는 게 맞다
    #       한글 3.0        표 구조가 없다. 글자만 건져내는 게 맞다
    #       hwp(OLE)       표를 격자로 못 읽는다. 글자만 나오는 게 맞다
    #   진짜 실패만 남겨야 경고가 쓸모 있다.
    if 형식 == "사진":
        pass                                  # 글자가 없는 게 맞다
    elif 표실패 and not 글:
        READ_FAIL.append((p.name, f"표·글자 모두 실패 — {표실패}"))
    elif 표실패 and 형식 not in ("한글 3.0", "hwp"):
        READ_FAIL.append((p.name, f"표 실패(글자는 나옴) — {표실패}"))
    _READ[p] = (글, 표)
    return 글, 표


# 표 한 행을 CSV 한 칸에 담을 때 쓰는 구분자.
#
# ⚠ 칸 안의 줄바꿈을 '/' 로 바꾸면 **되살릴 수 없다.** 원문 칸에 '/' 가 원래 들어 있다.
#   줄바꿈과 '/' 를 둘 다 가진 칸이 1,382개였다.
#   한계온도표는 **한 칸 안의 줄**로 작물을 나누는 표라, 다시 캘 때 그 칸들이 깨진다.
#   그래서 원문에 한 번도 안 나오는 글자를 쓴다 (1층 4,100만 자에서 0번).
CELL = " ¦ "          # 칸 사이
NL = "↵"              # 칸 안의 줄바꿈


def split_cells(내용):
    """tables.csv 의 '내용' 을 원래 격자 한 행으로 되돌린다. [[줄, …], …]

    다시 캘 때 이걸 쓴다. 원본을 열지 않아도 격자가 그대로 살아난다.
    """
    return [c.split(NL) for c in 내용.split(CELL)]


def dump_raw(원본, 파일들, 계열주기=None):
    """★ 그 원본의 **표 전부와 본문 전부** 를 날것 그대로 남긴다.

    왜 남기나 —
      mid_*.csv 는 우리가 **알아본 것만** 담는다. 재해예방정보만 해도 표가 10,395개인데
      알아보는 건 몇 종류뿐이다. 나머지를 버리면 나중에 낱말을 바꿔 다시 캘 수 없다.
      `안읽은것.md` 가 "없다" 와 "안 읽었다" 를 가르려고 쓴 문서인데,
      이 파일이 있으면 그 물음에 **파일로** 답할 수 있다.

    ⚠ 자르지 않는다. mid_table 은 600자에서 자르지만 여기는 원문 그대로다.
    ⚠ 읽기는 이 함수가 한 번만 한다. 부르는 쪽은 여기서 받은 것을 쓴다.

    돌려주는 것 : {파일경로: (본문글자, 표격자목록)}  — 부르는 쪽이 다시 안 읽게
    """
    표행, 글행, 읽은것 = [], [], {}
    for p in 파일들:
        계열 = 계열주기(p) if 계열주기 else ""
        글, 표 = read_doc(p)
        읽은것[p] = (글, 표)
        for gi, g in enumerate(표):
            for ri, row in enumerate(g):
                표행.append({
                    "원본": 원본, "계열": 계열, "출처파일": p.name,
                    "표번호": gi, "행번호": ri, "칸수": len(row),
                    "내용": CELL.join(c.replace("\n", NL) for c in row),
                })
        # ⚠ 줄 앞 공백을 지우지 않는다. PDF 배치 글자는 **앞 공백이 칸 자리**다.
        #   지우면 표가 어떻게 놓였는지가 사라진다. 빈 줄만 건너뛴다.
        # ⚠ '줄번호' 는 read_doc 이 낸 글자에서의 자리다. 원본 문서의 쪽·줄이 아니다.
        #   빈 줄을 건너뛰므로 번호에 구멍이 생기는 것이 정상이다.
        for i, ln in enumerate(글.split("\n")):
            if ln.strip():
                글행.append({"원본": 원본, "계열": 계열, "출처파일": p.name,
                            "줄번호": i, "본문": ln.rstrip()})
    rows_out("tables.csv", 표행, RAW_COLS["tables.csv"])
    rows_out("texts.csv", 글행, RAW_COLS["texts.csv"])

    # 빠진 것이 있으면 소리내어 알린다. 1층은 "다 담았다" 가 전제라 조용하면 안 된다.
    담긴파일 = {r["출처파일"] for r in 표행} | {r["출처파일"] for r in 글행}
    사진 = [p.name for p in 파일들 if doc_kind(p) == "사진"]
    사라짐 = [p.name for p in 파일들
              if p.name not in 담긴파일 and p.name not in 사진]
    if 사라짐:
        print(f"  ⚠ 1층에 흔적이 없는 파일 {len(사라짐)}개 — 읽기가 실패했습니다")
        for n in 사라짐[:5]:
            print(f"      {n}")
    if 사진:
        print(f"  · 사진 {len(사진)}개는 글자가 없는 게 맞습니다 (실패가 아닙니다)")
    if READ_FAIL:
        print(f"  ⚠ 읽다 넘어진 파일 {len(READ_FAIL)}개")
        for n, why in READ_FAIL[:5]:
            print(f"      {n[:44]}  {why[:60]}")
    표없음 = len(파일들) - len({r["출처파일"] for r in 표행})
    글없음 = len(파일들) - len({r["출처파일"] for r in 글행})
    print(f"  날 자료: 파일 {len(파일들)} · 표 {len(표행):,}행 · 본문 {len(글행):,}줄"
          f"  (표 없는 파일 {표없음} · 글자 없는 파일 {글없음})")
    return 읽은것


# 날 자료 칸. mid_*.csv 와 달리 **자르지 않는다.**
RAW_COLS = {
    "tables.csv": ["원본", "계열", "출처파일", "표번호", "행번호", "칸수", "내용"],
    "texts.csv": ["원본", "계열", "출처파일", "줄번호", "본문"],
}


# ─────────────────────────────────────────────────────────────────────
# 순(旬) → 순번 · 날짜
#
# 원본은 시기를 '4월 상순' 처럼 순으로 준다. 적산온도를 쌓으려면 **날짜**가 있어야 한다.
# 출처 : 원본/농작업일정/farmwork.py (수집 스크립트). 되찾아 옮겼다.
# ─────────────────────────────────────────────────────────────────────

ERA_ORDER = {"상": 0, "중": 1, "하": 2}
ERA_DAY = {"상": 5, "중": 15, "하": 25}     # 로드맵 §6-2 의 순 → 날짜 규칙


def sun_index(month, era):
    """'4월 상순' 을 0~35 번호로. 1월 상순이 0, 12월 하순이 35.

    ⚠ **해를 넘기는 작업은 종료월이 13~18 로 온다.** 13 이 이듬해 1월, 18 이 이듬해 6월이다.
      마늘·양파·시금치 같은 월동작물이 전부 이걸 쓴다.
      1~12 만 받으면 **월동작물의 작업 기간이 통째로 끊긴다.**
      실제로 29작물 94행의 종료순번·지속순수·종료중앙일이 전부 비었던 적이 있다.
      36 을 더해 이듬해임을 살린다(36~71 = 이듬해).
    """
    try:
        m = int(month)
    except (TypeError, ValueError):
        return ""
    if era not in ERA_ORDER or not 1 <= m <= 24:
        return ""
    wrap = 36 if m > 12 else 0
    if m > 12:
        m -= 12
    return wrap + (m - 1) * 3 + ERA_ORDER[era]


def middle_day(month, era):
    """순을 날짜로. 상순 5일 · 중순 15일 · 하순 25일.

    이듬해로 넘어간 달은 `+04-15` 처럼 앞에 `+` 를 붙여 구분한다.
    """
    day = ERA_DAY.get(era)
    try:
        m = int(month)
    except (TypeError, ValueError):
        return ""
    if not day or not 1 <= m <= 24:
        return ""
    mark = "+" if m > 12 else ""
    if m > 12:
        m -= 12
    return f"{mark}{m:02d}-{day:02d}"


def month_fix(m):
    """13~18월은 해를 넘긴 표기다. 13=1월 … 18=6월.

    마늘·양파·시금치 같은 월동 작물이 전부 이걸 쓴다. 그냥 쓰면 기간 계산이 깨진다.
    (월, 이듬해인가) 로 돌려준다.
    """
    try:
        m = int(m)
    except (TypeError, ValueError):
        return None, False
    if 13 <= m <= 24:
        return m - 12, True
    return (m, False) if 1 <= m <= 12 else (None, False)


def rows_out(name, rows, cols):
    out = OUT_DIR or OUT
    out.mkdir(parents=True, exist_ok=True)
    with (out / name).open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"  {name:22}{len(rows):6}행")


# ⚠ 천 단위 쉼표를 반드시 받아야 한다. 안 그러면 값이 조용히 깨진다.
#     "1,400~1700℃"  →  400~1700   (1,400 이 400 으로)
#     "800~1,000℃"   →  000~000    (완전히 깨짐)
#   적산온도가 네 자리라 전부 이 함정에 걸린다.
NUM = r"-?\d{1,3}(?:,\d{3})+|-?\d+(?:\.\d+)?"
# ⚠ NUM 은 '|' 가 든 교체식이다. 다른 패턴에 이어붙일 때는 반드시 이쪽을 쓴다.
#   감싸지 않으면 "^\s*-?" + NUM + "\s*…" 가 통째로 두 갈래로 쪼개져 엉뚱하게 맞는다.


# ⚠ NUM 은 '|' 가 든 교체식이다. 다른 패턴에 이어붙일 때는 반드시 이쪽을 쓴다.
#   감싸지 않으면 "^\s*-?" + NUM + "\s*…" 가 통째로 두 갈래로 쪼개져 엉뚱하게 맞는다.
N = f"(?:{NUM})"


TEMP_RANGE = re.compile(rf"({NUM})\s*(?:[~～∼-]\s*({NUM}))?\s*℃")


def to_num(s):
    """'1,400' → '1400'. 쉼표를 지운다."""
    return (s or "").replace(",", "")


# ⚠ 적산온도(누적값)와 생육온도는 뜻도 자릿수도 다르다. 같은 정규식으로 뽑으면 섞인다.
#   "개화에서 성숙까지의 적산온도 : 800~1,000℃"  ← 이건 온도가 아니라 누적값이다


# ⚠ 적산온도(누적값)와 생육온도는 뜻도 자릿수도 다르다. 같은 정규식으로 뽑으면 섞인다.
#   "개화에서 성숙까지의 적산온도 : 800~1,000℃"  ← 이건 온도가 아니라 누적값이다
SUM_WORD = re.compile(r"적산\s*온도")
# ⚠ '적산온도' 라고 다 생육 적산온도가 아니다.
#     "침종 기간은 물의 적산온도 100℃를 기준으로"   ← 볍씨 담그는 물 온도의 누적
#   그대로 담으면 벼 목표 적산온도 자리에 20·100·15 가 들어간다. 실제로 그랬다.
SUM_NOT = re.compile(r"(물의?\s*적산|침종|온탕|소독|담[가그])")


# 방향 판정 — '이상' 이 붙었다고 하한이 아니다. 뒤에 오는 말이 뜻을 뒤집는다.
#   '생육의 정지' 처럼 조사가 끼는 경우가 있어 사이를 느슨하게 둔다.
UP_STOP = re.compile(r"(생육\S{0,2}\s*(정지|저하|불량|억제)|발아\s*장애|발아율\S*\s*(저하|감소)"
                     r"|더위에\s*약|웃자람|도장|휴면|낙화|낙과|고온\s*장해)")


LOW_GO = re.compile(r"(자라기\s*시작|생육\s*시작|생장\s*시작|싹이?\s*트|자람)")


LOW_STOP = re.compile(r"(생육\S{0,2}\s*(정지|불량|저하)|고사|얼어|동사)")

# ⚠ '촉진' 은 base_temp 가 아니다.
#     "18℃ 이상에서 잎 생육이 촉진"  = 그 위면 빨라진다
#     "5℃ 이상에서 자라기 시작"      = 그 아래로는 안 자란다   ← 이것만 base_temp
#   둘을 같은 '하한후보' 로 묶으면 build 에서 잘못 쓴다.


SPEED_UP = re.compile(r"(촉진|빨라|왕성)")

# ★ 항목 이름이 방향을 그대로 말해주는 경우. '이상/이하' 가 없어도 뜻이 분명하다.
#     "생육온도 : 생육적온(25~30℃, 생육최저온도 10℃)"        수박 base_temp 10 의 원문
#     "생육온도 ¦ 잎 생육적온 ¦ 18~20℃ ¦ 생육 최저 ¦ 4℃"      마늘 base_temp 4 의 원문
#     "구분 ¦ 최저온도(℃) ¦ 최적온도(℃) ¦ 최고온도(℃)"        시금치 표
#
# ⚠ 이 셋이 전부 '미분류' 로 빠져 있었다. 확정표 §B-2 는 셋 다 confirmed=Y 로 적어뒀는데
#   파이프라인은 그 근거를 안 담고 있었다 — "확보" 와 "반영" 이 어긋난 상태였다.
# ⚠ '최저한계온도' 는 여기 넣지 않는다. 한계온도는 경보용이지 기준온도가 아니다(CLAUDE.md).
LOW_LABEL = re.compile(r"(생육\s*최저\s*온도|발아\s*최저\s*온도|생육\s*최저(?!\s*한계)"
                       r"|발아\s*최저(?!\s*한계)|최저\s*온도)")
HIGH_LABEL = re.compile(r"(생육\s*최고\s*온도|발아\s*최고\s*온도|최고\s*온도)")
OPT_LABEL = re.compile(r"(적\s*온|최적\s*온도|알맞은\s*온도)")

# 피해를 말하는 낱말. 이것이 붙으면 기준온도가 아니라 경보 규칙이다


# 피해를 말하는 낱말. 이것이 붙으면 기준온도가 아니라 경보 규칙이다
DAMAGE = re.compile(r"(동해|냉해|저온\s*피해|언\s*피해|서리|한해|상해)")

# 생육 이야기가 아닌 온도. 이것이 붙으면 종류를 정하지 않고 '미분류' 로 둔다


# 생육 이야기가 아닌 온도. 이것이 붙으면 종류를 정하지 않고 '미분류' 로 둔다
# ⚠ '건조기' 라는 낱말이 없어도 말리는 이야기다.
#     "벼는 높은 온도에서 말리면 … 종자용은 40℃ 이하"  → '벼 단계별저온 40℃' 가 됐었다
OFF_TOPIC = re.compile(r"(저장|보관|저온저장|건조기?|말리|말려|예건|소독|온탕|침종|담[가그]|훈증"
                       r"|축사|가축|한육우|젖소|돼지|병아리|봉군|벌집|배지|수분함량)")

# ⚠ 한국어는 '이상/이하' 없이도 방향을 드러낸다. 그것만 보면 진짜 근거를 놓친다.
#     "4℃에서도 발아하고"              ← 하한. 시금치 base_temp 의 실제 출처다
#     "10℃ 정도면 발아에 지장이 없으나"   ← 하한
#     "지온이 20℃ 내외가 파종 적기"      ← 파종 기준
#   확정표가 시금치 4℃ 를 confirmed=Y 로 잡은 근거가 바로 이 문장인데,
#   방향말이 없어 '미분류' 로 빠졌던 적이 있다.


BARE_LOW = re.compile(r"(에서도\s*(발아|생육|자라)|정도\S{0,2}\s*(발아|생육)\S{0,4}\s*지장이?\s*없"
                      r"|부터\s*(발아|생육|자라)|넘으면\s*(발아|생육))")


def temp_kind(around, has_ge, has_le, tail="", 앞=""):
    """온도 한 건의 '종류' 를 정한다. 사용법.md §2 참조.

    ⚠ 문장 전체가 아니라 **그 숫자 주변**만 본다.
      한 문장에 하한과 상한이 같이 나오기 때문이다.

        "4℃에서도 발아하고 … 고온에서는 발아장해를 받아 30℃ 이상에서는 발아율이 50% 이하"
         ↑ 하한                                        ↑ 상한

      문장 전체로 판정하면 앞의 '발아하고' 가 걸려 30℃ 가 하한후보로 뒤집힌다.

    ⚠ 판정이 안 되면 **비운다(미분류).** 짐작해서 채우지 않는다.
      없는 값은 build.py 가 논문으로 보충하고 confirmed=N 을 붙인다.
      여기서 억지로 채우면 그 값이 '원문 근거 있음' 으로 둔갑한다.
    """
    # ⚠ 생육 이야기가 아닌 온도가 섞여 든다. 주간농사정보에서 드러났다.
    #     "벼 저장은 함수율 15% 이하, 온도 15℃ 이하"        → 저장고 온도지 저온해가 아니다
    #     "물 온도 60℃에 10분간 담가 소독"                 → 종자소독
    #     "건조기 온도를 55℃로 하여 48시간"                 → 건조기
    #   그대로 두면 '벼 단계별저온 15℃' 같은 가짜 규칙이 생긴다. 실제로 그랬다.
    if OFF_TOPIC.search(around):
        return "미분류"
    # ⚠ 피해를 말하는 문장은 base_temp 가 아니다. 경보 규칙이다.
    #   "0℃ 이하로 내려가면 동해의 우려가 있어" 가 하한후보로 갔었다.
    #   같은 문장에 '고사'(잎·줄기가 고사된 다음 수확)가 있어서 LOW_STOP 이 먼저 걸렸다.
    #   피해말이 있으면 그쪽을 먼저 본다.
    # 항목 이름이 방향을 말해주면 그것을 먼저 믿는다.
    # ⚠ **숫자 바로 앞**만 본다. 창 전체를 보면 한 문장 안의 적온까지 하한후보가 된다.
    #     "생육적온(25~30℃, 생육최저온도 10℃)"  →  25~30 도 하한후보가 됐었다
    if 앞 and not DAMAGE.search(앞):
        if OPT_LABEL.search(앞):
            return "적온"
        if LOW_LABEL.search(앞):
            return "하한후보"
        if HIGH_LABEL.search(앞):
            return "상한후보"
    if has_le and DAMAGE.search(around):
        return "단계별저온"
    if has_ge and UP_STOP.search(around):
        return "상한후보"
    if has_ge and SPEED_UP.search(around):
        return "생육촉진"          # base_temp 아님. 참고값
    if has_ge and LOW_GO.search(around):
        return "하한후보"
    if has_le and LOW_STOP.search(around):
        return "하한후보"
    if has_le:
        return "단계별저온"
    # 방향말이 없어도 한국어가 방향을 드러내는 꼴
    if not has_ge and not has_le and BARE_LOW.search(tail or around):
        return "하한후보"
    if has_ge:
        return "상한후보?"          # 방향말은 있는데 뜻이 안 잡힌 것. 사람이 볼 것
    return "미분류"


def crops_with_pos(line):
    """줄 안에서 작물이 **어디에** 나왔는지까지 돌려준다. [(자리, 작물), …]

    값과 짝지으려면 자리가 있어야 한다. 한 줄에 작물이 여럿일 때 쓴다.

    ⚠ 겹치는 이름은 긴 쪽을 쓴다. '양파' 의 '파' 가 따로 잡히면
      "… 양파 -8~-9℃" 에서 '파'(43) 가 '양파'(42) 보다 가까워 값을 가로챈다. 실제로 그랬다.

    ⚠ 일반 명사와 겹치는 이름(무·파·가지)은 여기서 안 찾는다.
      괄호가 붙은 꼴만 인정해야 하는데 그 판단은 crops_in_line 이 한다.
    """
    자리 = []
    for name, std in CROP_ALIAS.items():
        if name in AMBIGUOUS or std in AMBIGUOUS:
            continue
        i = 0
        while True:
            j = line.find(name, i)
            if j < 0:
                break
            자리.append((j, j + len(name), std))
            i = j + 1
    자리.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    남길것 = []
    for a, b, std in 자리:
        if any(x <= a and b <= y for x, y, _ in 남길것):
            continue                      # 더 긴 이름 안에 든 것
        남길것.append((a, b, std))
    return [(a, std) for a, _b, std in 남길것]


def temp_from_sentence(text, crop, src, loc, 작물자리=None):
    """본문 문장에서 온도·적산온도를 캔다. 표에 없는 값이 여기 있다.

    감자 base_temp 는 표가 아니라 이 문장에 있다.
        ❍ 씨감자 싹은 5℃ 이상에서 자라기 시작함
    표만 읽으면 통째로 놓친다. 옛 attach.py 가 38%만 뽑았던 이유다.

    돌려주는 것 : (온도행, 적산온도행)
    """
    temps, sums = [], []
    for line in re.split(r"[\nㅇ○❍]", text):
        line = tidy(line)
        if "℃" not in line:
            continue
        is_sum = bool(SUM_WORD.search(line)) and not SUM_NOT.search(line)
        for m in TEMP_RANGE.finditer(line):
            lo, hi = to_num(m.group(1)), to_num(m.group(2) or m.group(1))
            if is_sum:
                # 적산온도는 온도가 아니라 누적값이다. 다른 표로 보낸다
                sums.append({
                    "작물": crop, "품종숙기": "", "일수": "",
                    "적산온도": lo if lo == hi else f"{lo}~{hi}",
                    "구간": "", "원문": line[:200],
                    "출처파일": src, "위치": loc,
                })
                continue
            # 숫자 주변만 본다. 앞 25자 · 뒤 40자
            around = line[max(0, m.start() - 25):m.end() + 40]
            tail = line[m.end():m.end() + 40]
            앞 = line[max(0, m.start() - 14):m.start()]      # 숫자 바로 앞. 항목 이름이 여기 있다
            # ⚠ 방향은 숫자 주변만 보고 정하지만, **문장이 통째로 딴 얘기인지**는
            #   문장 전체를 봐야 안다. 창이 좁아 '저장' 을 못 보고
            #   "벼 저장은 … 온도 15℃ 이하" 가 '벼 단계별저온 15℃' 가 된 적이 있다.
            if OFF_TOPIC.search(line):
                around = line
            has_ge = bool(re.match(r"\s*(이상|초과|넘)", tail))
            has_le = bool(re.match(r"\s*(이하|미만|아래)", tail))
            # ⚠ 한 줄에 작물이 여럿이면 값이 **모든 작물에** 붙는다.
            #     "난지형 마늘 -5~-6℃, 한지형 마늘 -7~-8℃, 양파 -8~-9℃"
            #   → 양파에 마늘 값 -5~-6 까지 붙었다. 값마다 **바로 앞의 작물**에 붙인다.
            이작물 = crop
            if 작물자리:
                앞작물 = [c for pos, c in 작물자리 if pos <= m.start()]
                if 앞작물:
                    이작물 = 앞작물[-1]
            temps.append({
                "작물": 이작물,
                "종류": temp_kind(around, has_ge, has_le, tail, 앞),
                "항목": "",
                "값최소": lo, "값최대": hi,
                "단위": "℃",
                "원문": line[:200], "출처파일": src, "위치": loc,
            })
    return temps, sums


def dedup_simple(rows, keys):
    """같은 값이 호마다 · 원본마다 되풀이된다. 접고 근거를 남긴다.

    ⚠ dedup_rule 과 같은 기록을 남긴다. 예전에는 여기만 '출처들' 을 안 세어서
      같은 값을 두 원본이 말해도 먼저 온 쪽 파일만 남았다.
      양파 25℃ 를 농작업일정과 주간농사정보가 다 말하는데 농작업일정만 적혀 있었다.
    """
    seen = {}
    for r in rows:
        k = tuple(nospace(str(r.get(x, ""))) for x in keys)
        if k in seen:
            seen[k]["실린호"] += 1
            seen[k]["_srcs"].append(r.get("원본", ""))
        else:
            r = dict(r)
            r["실린호"] = 1
            r["_srcs"] = [r.get("원본", "")]
            seen[k] = r
    out = []
    for r in seen.values():
        c = Counter(x for x in r.pop("_srcs") if x)
        r["출처들"] = " · ".join(f"{k}:{v}" for k, v in c.most_common())
        r["원본수"] = len(c)
        out.append(r)
    return out


# 등록 작물이 0건이라 읽지 않는 계열.
#
# ⚠ 이건 '지금 등록된 작물' 기준의 판단이다. 작물을 더하면 틀릴 수 있다.
#   그래서 이름만 적어두고 끝내지 않는다 — 돌릴 때마다 본문을 훑어 다시 확인한다.
#   맞으면 조용히 건너뛰고, 등록 작물이 나오면 경고를 내고 읽는다.
#   (저온해 43개는 사과·배·복숭아·매실·포도 5작물 고정이었다. 사용법.md §3-3)


def dedup_rule(rows):
    """같은 규칙이 호마다 · 원본마다 되풀이된다. 하나로 접고 근거를 남긴다.

    ⚠ 접기 전에 몇 호에 실렸는지를 세어 남긴다. 그 숫자가 근거의 무게다.
      17개 호에 똑같이 실린 표는 믿을 만하고, 1개 호에만 있는 값은 확인이 필요하다.

    ⚠ 표기만 다르고 값이 같은 것도 접는다.
        "30℃ 이상(주의)"  와  "최고기온 30℃ 이상(주의)"  는 같은 규칙이다
        (고온해 표가 6~7월 호는 머리글에 '(최고온도)' 를 달고 8월~ 호는 안 단다)

    ★ '출처들' 칸에 **어느 원본이 몇 호에서 말했는지** 를 남긴다.
      예전에는 출처파일 하나만 남아서, 배추 냉해 -8 을 재해예방정보 18호와
      주간농사정보 8호가 다 말하는데도 CSV 에는 재해예방정보 한 파일만 적혀 있었다.
      "이 숫자 어디서 났냐" 에 정직하게 답하려면 이 칸이 있어야 한다(CLAUDE.md 설계원칙).
    """
    seen = {}
    for r in rows:
        key = (r["작물"], r["재해종류"], nospace(r["생육단계"]),
               r["지표"], r["부등호"], r["값"], r["지속일"], r["등급"])
        if key in seen:
            seen[key]["실린호"] += 1
            seen[key]["_files"].append(r["출처파일"])
            seen[key]["_srcs"].append(r.get("원본", ""))
        else:
            r = dict(r)
            r["실린호"] = 1
            r["_files"] = [r["출처파일"]]
            r["_srcs"] = [r.get("원본", "")]
            seen[key] = r
    out = []
    for r in seen.values():
        r["출처파일수"] = len(set(r.pop("_files")))
        c = Counter(x for x in r.pop("_srcs") if x)
        r["출처들"] = " · ".join(f"{k}:{v}" for k, v in c.most_common())
        r["원본수"] = len(c)
        out.append(r)
    return out


def find_conflicts(rows):
    """같은 것을 가리키는데 값이 다른 행을 찾는다.

    ⚠ 접기는 값이 같을 때만 한다. 값이 다르면 두 행으로 남는데,
      그게 **다른 사실인지 서로 어긋난 것인지** 표에는 표시가 없다.

    ⚠ 다른 값인 게 당연한 것들을 충돌로 세면 안 된다. 19군데 중 15군데가 그랬다.
        등급     고온해는 주의 30℃ · 위험 32℃ 가 한 쌍이다   → 등급을 열쇠에 넣는다
        유형     마늘 난지형 -6 · 한지형 -8                 → 조건원문에 적혀 있다
        작물 없음  병해충 조건은 작물이 빈 행이 많다            → 견줄 수 없으니 뺀다

    남는 것이 **사람이 봐야 할 것**이다.
    """
    묶음 = {}
    for r in rows:
        if not r.get("작물", "").strip():
            continue                      # 작물이 없으면 무엇과 견줄지 알 수 없다
        k = (r["작물"], r["재해종류"], nospace(r["생육단계"]),
             r["지표"], r.get("등급", ""))
        묶음.setdefault(k, []).append(r)
    out = []
    for (작물, 종류, 단계, 지표, 등급), 것들 in 묶음.items():
        if len({r["값"] for r in 것들}) < 2:
            continue
        for r in sorted(것들, key=lambda x: -int(x.get("실린호", 1) or 1)):
            out.append({
                "작물": 작물, "재해종류": 종류, "생육단계": 단계, "지표": 지표,
                "등급": 등급, "값": r["값"], "실린호": r.get("실린호", ""),
                "출처": r.get("출처", ""), "출처들": r.get("출처들", ""),
                "조건원문": r.get("조건원문", ""), "출처파일": r.get("출처파일", ""),
            })
    return out


CONFLICT_COLS = ["작물", "재해종류", "생육단계", "지표", "등급", "값", "실린호",
                 "출처", "출처들", "조건원문", "출처파일"]


def fix_pdf_cols(g):
    """PDF 표의 칸 쪼개짐을 되붙인다.

    PDF 는 머리글 한 칸이 두 칸으로 갈라지는 일이 있다. 갈라진 앞쪽은
    **데이터 행이 통째로 비어 있다** — 그게 표시다.

        머리글  '작물별' ¦ '모기를때' ¦ '꽃눈생기기전' ¦ '꽃필때' ¦ '언' ¦ '피해 온도' ¦ '비' ¦ '고'
        데이터  '배  추' ¦ '10'      ¦ '5'          ¦ ''      ¦ ''  ¦ '-8'       ¦ ''  ¦ ''
                                                            └ 비었다 → '언' 은 조각

    그대로 두면 '피해온도' 로 읽혀 냉해가 아니라 단계별저온이 된다(2026 제3호).
    데이터가 전부 빈 칸은 떼고, 그 머리글은 다음 칸 앞에 붙인다.
    """
    if len(g) < 2:
        return g
    w = max(len(r) for r in g)
    body = g[1:]
    keep, carry = [], ""
    for j in range(w):
        비었다 = all(j >= len(r) or not r[j].strip() for r in body)
        머리 = g[0][j].strip() if j < len(g[0]) else ""
        if j > 0 and 비었다:
            carry += 머리                      # 조각. 다음 칸에 넘긴다
            continue
        keep.append((j, carry + 머리))
        carry = ""
    if len(keep) == w:
        return g
    out = [[h for _, h in keep]]
    for r in body:
        out.append([r[j] if j < len(r) else "" for j, _ in keep])
    return out


def limit_table(g, gi, fname, is_생육장애):
    """한계온도표 한 장을 규칙으로 편다.

    ⚠ 장애온도 칸은 줄 수가 안 맞는다. 작물 7개인데 장애온도는 5줄이다.
      줄 번호로 짝지으면 엉뚱한 작물에 붙는다 — 실제로 이렇게 틀렸었다.

        고추 ← "25℃이상 : 화분기능상실"   (원문은 가지 줄)
        무   ← "10℃이하 : 순멎이"        (원문은 오이 줄)

      게다가 원문 상당수가 '이하' 인데 부등호를 '>=' 로 넣어 방향까지 뒤집혔다.
      → **장애온도 칸은 규칙으로 만들지 않는다.** mid_table 에 원문만 남긴다.

    ⚠ 적온도 규칙이 아니다. mid_rule 은 재해 규칙 표다. 적온은 여기 들어오면 안 된다.

    ⚠ 같은 '동해온도' 라도 어느 표에서 왔는지로 뜻이 갈린다.
        생육및장애온도표의 동해온도   배추 -6   → 동해
        엽채류 한계온도표의 동해온도   배추 -8   → 냉해   (확정표 §B-4 기준)
    """
    out = []
    for ri, row in enumerate(g[1:], 1):
        cols = [c.split("\n") for c in row]
        n = max(len(c) for c in cols)
        # ⚠ hwpx 는 한 칸 안에 작물이 여러 줄이라 n>=2 다. PDF 는 한 행에 작물 하나라 n==1.
        #   n<2 를 통째로 건너뛰면 PDF 판본에서 단 한 줄도 안 읽힌다.
        #   다만 아무 행이나 받으면 머리글·주석이 섞이므로, 첫 칸이 아는 작물일 때만 받는다.
        if n < 2 and not CROP_ALIAS.get(nospace(cols[0][0] if cols and cols[0] else "")):
            continue
        for k in range(n):
            def cell(j, _k=k, _cols=cols):
                return _cols[j][_k].strip() if j < len(_cols) and _k < len(_cols[j]) else ""
            작물원문 = cell(0)
            if not 작물원문:
                continue
            작물 = CROP_ALIAS.get(nospace(작물원문))
            for ci in range(1, len(row)):
                항목 = tidy(g[0][ci]) if ci < len(g[0]) else ""
                항목N = nospace(항목)
                # 규칙으로 만들지 않는 칸
                if "장애" in 항목N or "장해" in 항목N:
                    continue                     # 줄 짝이 안 맞는다. 원문만 남긴다
                if "적온" in 항목N:
                    continue                     # 재해 규칙이 아니다
                v = cell(ci)
                m = TEMP_RANGE.search(v) or re.match(rf"\s*({NUM})", v)
                if not v or not m:
                    continue
                if "최고" in 항목N:
                    종류, 지표, 부등호 = "한계_최고", "최고기온", ">="
                elif "최저" in 항목N:
                    종류, 지표, 부등호 = "한계_최저", "최저기온", "<="
                elif "동해" in 항목N or "냉해" in 항목N or "언피해" in 항목N:
                    # ⚠ 표에 따라 뜻이 갈린다.
                    #     생육및장애온도표의 동해온도   배추 -6
                    #     엽채류 한계온도표의 동해온도   배추 -8   ← 이건 냉해다
                    #   확정표 §B-4 가 그렇게 갈라뒀다.
                    #
                    # ⚠ 그리고 같은 칸인데 호마다 머리글이 다르다.
                    #     2023 제11호  "냉해온도"
                    #     2025 제2호   "동해온도"
                    #     2026 제3호   "언피해온도"   ← PDF 판본
                    #   항목명을 그대로 쓰면 같은 값이 두 행으로 갈린다. 실제로 그랬다.
                    #   → 출처표로 종류를 정하고, 생육단계는 종류로 덮어쓴다.
                    종류 = "동해" if is_생육장애 else "냉해"
                    지표, 부등호 = "최저기온", "<="
                    항목 = f"{종류}온도"
                else:
                    종류, 지표, 부등호 = "단계별저온", "최저기온", "<="
                out.append({
                    "작물": 작물 or 작물원문, "본선": is_main(작물),
                    "재해종류": 종류, "생육단계": 항목,
                    "지표": 지표, "부등호": 부등호,
                    "값": to_num(m.group(1)), "단위": "℃", "지속일": "", "등급": "",
                    "조건원문": v[:120],
                    "출처": "생육및장애온도표" if is_생육장애 else "한계온도표",
                    "출처파일": fname, "위치": f"표{gi}/행{ri}/{k}",
                })
    return out


# ⚠ 벼 생육단계 이름이 호마다 다르다. 통일하지 않으면 같은 단계가 따로 세어진다.
#     "새끼 칠 때" = 분얼기 · "감수분얼기" = 감수분열기(오타) · "출아" = 육묘 출아
#   호를 하나만 보고 만들면 이걸 못 본다. 여러 호를 펼쳐야 드러난다.
# ⚠ 이 표에는 작물 칸이 없다. 문서 맥락에서만 벼임을 안다.
#   등록표에서 이름을 가져온다 — 나중에 '벼' 표기가 바뀌어도 한 곳만 고치면 된다.
