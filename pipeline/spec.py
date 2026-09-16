# 확정표(`GDD계산관련/작물_확정표.md`)를 읽습니다. build.py 의 입력입니다.
#
#     from spec import 온도, 작형, 숙기접기, 수박숙기
#
# ★ **값을 여기에 베껴 적지 않는다.** 확정표의 표를 그대로 읽는다.
#   베끼면 확정표와 코드가 갈리고, 그러면 어느 쪽이 정본인지 모르게 된다 —
#   이 프로젝트가 이미 겪은 사고다(CLAUDE.md 정본 규칙).
#   확정표를 고치면 다음 build 부터 그 값이 나온다.
#
# ⚠ **표를 못 찾으면 조용히 건너뛰지 말고 크게 터뜨린다.** 확정표는 사람이 고치는
#   문서라 칸 이름이 바뀔 수 있다. 조용히 빈 값을 내면 build 가 빈 CSV 를 만들고,
#   그게 통과하면 "값이 없다" 와 "표를 못 읽었다" 를 구분할 수 없게 된다.

import re
import sys
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from crops import CROP_ALIAS, MAIN_CROPS  # noqa: E402
from common import middle_day  # noqa: E402

정본 = HERE.parent / "GDD계산관련" / "작물_확정표.md"


class 확정표오류(Exception):
    """확정표를 못 읽었다. 값이 없는 것과 다르다."""


def _본문():
    if not 정본.exists():
        raise 확정표오류(f"확정표가 없습니다: {정본}")
    return 정본.read_text(encoding="utf-8")


def _칸(줄):
    """'| a | b |' → ['a', 'b']"""
    return [c.strip() for c in 줄.strip().strip("|").split("|")]


def 표들(글=None):
    """마크다운 표를 전부 (머리글, 행들) 로 읽는다.

    ⚠ 구분선(|---|---|)을 건너뛴다. 이걸 행으로 세면 첫 행이 전부 '---' 가 된다.
    """
    글 = _본문() if 글 is None else 글
    표, 덩이 = [], []
    for 줄 in 글.split("\n"):
        if 줄.strip().startswith("|"):
            덩이.append(줄)
        elif 덩이:
            표.append(덩이)
            덩이 = []
    if 덩이:
        표.append(덩이)

    결과 = []
    for 덩이 in 표:
        칸들 = [_칸(x) for x in 덩이]
        머리 = 칸들[0]
        행들 = [r for r in 칸들[1:] if not all(set(c) <= set("-: ") for c in r)]
        결과.append((머리, 행들))
    return 결과


def 표찾기(머리조건, 글=None):
    """머리글에 이 칸들이 다 있는 표를 찾는다. 없으면 터뜨린다.

    ⚠ 표 차례(몇 번째 표)로 찾지 않는다. 확정표에 절이 하나 늘면 차례가 밀린다.
      칸 이름으로 찾으면 절을 옮겨도 계속 맞는다.
    """
    후보 = [(h, r) for h, r in 표들(글) if all(c in h for c in 머리조건)]
    if not 후보:
        raise 확정표오류(
            f"확정표에서 표를 못 찾았습니다. 찾던 칸: {머리조건}\n"
            f"  → {정본.name} 의 칸 이름이 바뀌었는지 보세요"
        )
    if len(후보) > 1:
        raise 확정표오류(f"표가 여럿 걸립니다: {머리조건} — {len(후보)}개. 조건을 좁히세요")
    머리, 행들 = 후보[0]
    return [dict(zip(머리, r, strict=False)) for r in 행들]


def _수(s, 칸=""):
    """'**12**' · '5' → 12.0. 굵게 표시(**)를 벗긴다."""
    s = re.sub(r"[*`\s]", "", s or "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        raise 확정표오류(f"숫자가 아닙니다: {칸}={s!r}") from None


# ─────────────────────────────────────────────────────────────────────
# §B-2 온도 채택값 — crops.base_temp
# ─────────────────────────────────────────────────────────────────────

def 온도():
    """{작물: {base_temp, upper_temp, confirmed, 근거}}. 등록된 작물만.

    ⚠ **확정표에 있다고 다 쓰는 게 아니다.** 무엇을 쓸지는 `crops.py` 의 등록표가 정한다.
      버린 작물의 연구값(논문 Tbase 등)은 확정표에 그대로 남겨둔다 —
      되살릴 때 다시 찾지 않아도 되고, 왜 그 값이었는지도 남는다.

    ⚠ 등록했는데 확정표에 줄이 없으면 **조용히 넘기지 않고 알린다.**
      그 작물은 base_temp 가 없어 적산온도를 못 쌓는다.
    """
    행들 = 표찾기(["작물", "base_temp", "upper_temp", "confirmed"])
    out = {}
    for r in 행들:
        작물 = re.sub(r"[*`~\s]", "", r["작물"])
        if not 작물 or 작물 not in CROP_ALIAS:
            continue                      # 등록표에 없는 작물 — 확정표에만 남은 연구값
        out[작물] = {
            "base_temp": _수(r["base_temp"], f"{작물}.base_temp"),
            "upper_temp": _수(r["upper_temp"], f"{작물}.upper_temp"),
            # ⚠ 'N ⚠' 처럼 표시가 붙은 칸이 있다. 첫 글자만 본다
            "confirmed": "Y" if re.sub(r"[*`\s]", "", r["confirmed"])[:1] == "Y" else "N",
            "근거": r.get("근거", ""),
        }
    if not out:
        raise 확정표오류("§B-2 채택값 표가 비었습니다")
    빠짐 = sorted(MAIN_CROPS - set(out))
    if 빠짐:
        print(f"  ⚠ 확정표 §B-2 에 줄이 없는 본선 작물: {', '.join(빠짐)}")
        print("      base_temp 가 없어 적산온도를 못 쌓습니다")
    return out

# ─────────────────────────────────────────────────────────────────────
# §H 관리 노력 — crops.care_level
# ─────────────────────────────────────────────────────────────────────

_등급 = {"강", "중", "약"}


def 관리노력():
    """{작물: {care_level, confirmed, 근거}}. 등록된 작물만.

    ⚠ **난이도가 아니다.** '얼마나 자주 돌보나' 다(강=거의 매일 · 중=주 1~2회 ·
      약=월 1~2회). 원본에 난이도(쉬움·보통·어려움) 표는 없다 — §H 참고.

    ⚠ 등급이 셋 중 하나가 아니면 **조용히 넘기지 않고 터뜨린다.** 확정표는 사람이
      고치는 문서라 '중하' 같은 딴 척도가 섞여 들어올 수 있다. 그대로 흘려보내면
      저쪽 CHECK 제약에서 적재가 통째로 깨진다.
    """
    행들 = 표찾기(["작물", "care_level", "confirmed"])
    out = {}
    for r in 행들:
        작물 = re.sub(r"[*`~\s]", "", r["작물"])
        if not 작물 or 작물 not in CROP_ALIAS:
            continue                      # 등록표에 없는 작물
        등급 = re.sub(r"[*`\s]", "", r["care_level"])
        if not 등급 or 등급 == "—":
            continue                      # 비워 둔 작물. 값이 없는 것이 맞다
        if 등급 not in _등급:
            raise 확정표오류(
                f"{작물}.care_level 이 '{등급}' 입니다 — 강·중·약 셋 중 하나여야 합니다"
            )
        out[작물] = {
            "care_level": 등급,
            "confirmed": "Y" if re.sub(r"[*`\s]", "", r["confirmed"])[:1] == "Y" else "N",
            "근거": r.get("근거", ""),
        }
    if not out:
        raise 확정표오류("§H 관리 노력 표가 비었습니다")
    빠짐 = sorted(MAIN_CROPS - set(out))
    if 빠짐:
        print(f"  ⚠ 확정표 §H 에 줄이 없는 본선 작물: {', '.join(빠짐)}")
    return out


# ─────────────────────────────────────────────────────────────────────
# §A 작형 등
# ─────────────────────────────────────────────────────────────────────

# '씨뿌림 1.중~3.상' · '아주심기 5.상' → 시작 순의 중앙일
# ⚠ 범위면 **앞쪽**을 쓴다. 추천 파종일의 시작이고, 뒤쪽은 늦심기 한계다.
_파종순 = re.compile(r"(\d{1,2})\.([상중하])")


def _파종일(글, 키):
    """'씨뿌림 1.중~3.상' → '01-15'. 못 읽으면 터뜨린다.

    common.middle_day 를 쓴다 — 상순 5일 · 중순 15일 · 하순 25일 규칙이
    농작업일정 추출과 같아야 mid_schedule 의 시작중앙일과 대조가 된다.
    """
    m = _파종순.search(글 or "")
    if not m:
        raise 확정표오류(f"{키}: 파종·정식에서 순(旬)을 못 읽었습니다 — {글!r}")
    return middle_day(m.group(1), m.group(2))

def 작형():
    """[{작물, 작물키, 작형, 지역, 관측소, 파종일, 일수}]. 등록된 작물만.

    ⚠ 작물키가 '배추_봄' 처럼 작형까지 담는다. 작물 이름은 '_' 앞이다.
      스키마에는 작형 칸이 없다(확정표 §A "작형은 crops 의 칸이 아니다").

    ⚠ **§A 에 줄이 있다고 다 쓰는 게 아니다.** §B-2 와 마찬가지로 등록표가 정한다.
      버린 작물의 작형·일수는 확정표에 `~~취소선~~` 으로 남겨둔다 —
      되살릴 때 다시 조사하지 않아도 되고, 왜 그 값이었는지도 남는다.
      그래서 §A 가 §B-2 보다 줄이 많아도 어긋난 것이 아니다.
    """
    행들 = 표찾기(["작물키", "농사로 작물명", "작형", "파종·정식", "일수"])
    out = []
    for r in 행들:
        원문 = r["작물키"]
        # ~~취소선~~ 은 버린 작형이다. **작물은 살아 있는데 그 작형만 버릴 때** 쓴다
        # (배추_봄 같은 겨울 파종). 작물째 버린 것(당근·파)은 아래 등록표에서 걸리지만
        # 작형만 버린 건 작물 이름이 등록표에 있어서 여기서 걸러야 한다
        if "~~" in 원문:
            continue
        키 = re.sub(r"[*`~\s]", "", 원문)
        if not 키 or 키.split("_")[0] not in CROP_ALIAS:
            continue                      # 등록표에 없는 작물 — 확정표에만 남은 값

        out.append({
            "작물": 키.split("_")[0],
            "작물키": 키,
            "작형": re.sub(r"[*`]", "", r["작형"]).strip(),
            "지역": r.get("지역 후보", ""),
            # 여럿이면 '·' 로 이어져 온다. 비면 전국 평균으로 역산한다
            "관측소": [s for s in re.split(r"[·,]", r.get("관측소", "")) if s.strip()],
            "파종일": _파종일(r["파종·정식"], 키),
            "일수": _수(r["일수"], f"{키}.일수"),
        })
    if not out:
        raise 확정표오류("§A 작형 표가 비었습니다")
    return out


# ─────────────────────────────────────────────────────────────────────
# §D 숙기 — crop_variants.maturity_type
# ─────────────────────────────────────────────────────────────────────

# ★ 접는 규칙도 확정표에서 읽는다. §D-1 의 코드블록이 이렇게 생겼다.
#
#     극조생 · 조생  → EARLY
#     중생          → MID
#     중만생 · 만생  → LATE
#
# ⚠ `조중생` 은 이 규칙에 없다. 없는 채로 두는 게 맞다 —
#   어느 쪽으로 접을지 아직 안 정했다(`확인필요.md §5`).
#   build 가 "규칙에 없는 숙기" 로 걸러내고 사람에게 알린다.
_접기줄 = re.compile(r"^\s*([가-힣·\s]+?)\s*→\s*(EARLY|MID|LATE)\s*$", re.M)


def 숙기접기():
    """{한국어숙기: EARLY|MID|LATE}. 확정표 §D-1 의 접는 규칙.

    ⚠ '종' 이 붙은 꼴과 안 붙은 꼴을 **둘 다** 넣는다.
      확정표는 '극조생 · 조생' 처럼 안 붙여 적기도 하고 '소과종' 처럼 붙여 적기도 한다.
      부르는 쪽도 원문 그대로 찾기도 하고 '종' 을 떼고 찾기도 한다.
      한쪽만 넣었다가 소과종이 조용히 안 접힌 적이 있다.
    """
    out = {}
    for 왼쪽, 코드 in _접기줄.findall(_본문()):
        for 낱말 in re.split(r"[·,]", 왼쪽):
            낱말 = 낱말.strip()
            if not 낱말:
                continue
            out[낱말] = 코드
            out[낱말.replace("종", "")] = 코드
            out[낱말 if 낱말.endswith("종") else 낱말 + "종"] = 코드
    if not out:
        raise 확정표오류(
            "§D-1 의 접는 규칙(극조생 · 조생 → EARLY …)을 못 찾았습니다"
        )
    return out


def 숙기분할작물():
    """§D-1 이 3분할로 정한 작물 {작물: 품종수}. 지금은 벼·감자·양파 셋뿐이다.

    ★ **여기 없는 작물은 MID 한 행이다**(§D-2). 품종정보에 숙기가 몇 건 있든
      상관없다 — 확정표가 정본이다(CLAUDE.md "CSV 와 확정표가 다르면 확정표가 맞다").
      실제로 품종정보만 보고 만들었더니 배추가 EARLY/MID/LATE 세 행이 나왔다.

    ⚠ 이름이 '벼(논벼)' 로 적혀 있다. 괄호를 떼야 등록표 이름과 맞는다.
    """
    행들 = 표찾기(["작물", "품종 수", "숙기 분포"])
    out = {}
    for r in 행들:
        작물 = re.sub(r"[*`\s]", "", r["작물"])
        작물 = re.sub(r"[(（].*", "", 작물)      # '벼(논벼)' → '벼'
        수 = re.sub(r"[^\d]", "", r["품종 수"] or "")
        if 작물:
            out[작물] = int(수) if 수 else None
    if not out:
        raise 확정표오류("§D-1 3분할 작물 표가 비었습니다")
    return out


def 수박숙기():
    """[{숙기, 일수, gdd_target, confirmed}]. §D-3 수박 4분할.

    ⚠ 수박만 품종정보가 아니라 **농작업일정 표**에서 나온다(§D-3).
    """
    행들 = 표찾기(["숙기", "착과 후 일수", "gdd_target"])
    out = []
    for r in 행들:
        숙기 = re.sub(r"[*`\s]", "", r["숙기"])
        if not 숙기:
            continue
        # '36 (35~38)' → 36 · '1,200' → 1200
        일수 = re.match(r"\s*(\d+)", r["착과 후 일수"] or "")
        목표 = re.sub(r"[*`\s,]", "", r["gdd_target"] or "")
        out.append({
            "숙기": 숙기,
            "일수": int(일수.group(1)) if 일수 else None,
            "gdd_target": int(목표) if 목표.isdigit() else None,
            "confirmed": "Y" if re.sub(r"[*`\s]", "", r["confirmed"])[:1] == "Y" else "N",
        })
    if not out:
        raise 확정표오류("§D-3 수박 숙기 표가 비었습니다")
    return out


def 점검():
    """확정표를 다 읽어보고 몇 건씩 나오는지 찍는다. 단독 실행용."""
    t, a, f, w = 온도(), 작형(), 숙기접기(), 수박숙기()
    m = 관리노력()
    print(f"확정표 {정본.name}")
    print(f"  §B-2 온도      {len(t)}작물")
    print(f"  §A  작형       {len(a)}행 · 작물 {len({x['작물'] for x in a})}종")
    print(f"  §D-1 숙기접기   {f}")
    print(f"  §D-3 수박숙기   {len(w)}행")
    print(f"  §H  관리노력    {len(m)}작물")
    빠진 = [c for c in t if c not in {x["작물"] for x in a}]
    if 빠진:
        print(f"  ⚠ §B-2 에 있는데 §A 에 없는 작물: {빠진}")
    return t, a, f, w

if __name__ == "__main__":
    try:
        점검()
    except 확정표오류 as e:
        print(f"확정표를 못 읽었습니다\n  {e}")
        sys.exit(1)
