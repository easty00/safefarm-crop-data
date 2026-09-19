# 스키마 3종이 Safe-farm 에 들어갈 수 있는지 검사합니다.
#
#     python pipeline/verify.py
#
# ★ **여기서 통과 = 저기서 적재 성공** 이 되게 하는 것이 이 파일의 목적이다.
#   그래서 저쪽 검사를 그대로 옮겨왔다. 저쪽이 바뀌면 여기도 같이 고쳐야 한다.
#
#     Safe-farm/ai-service/pipeline/prep/check.py        duplicates() · refs()
#     Safe-farm/ai-service/pipeline/farm/master_seed_farm_db.py
#                                                        UNIQUE · REFS · stage_problems()
#     Safe-farm/ai-service/app/models/farm/*.py          NOT NULL · CHECK
#
# ⚠ DB 에 붙지 않는다. CSV 만 본다. identity id 는 적재 때 정해지므로 자연키로 본다.
#
# 검사를 만나는 대로 멈추지 않는다. 전부 모아서 한 번에 찍는다 —
# 하나씩 멈추면 고치고 다시 돌리기를 문제 종류만큼 되풀이하게 된다(저쪽 check.py 와 같은 뜻).

import csv
import io
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

스키마 = HERE / "out" / "스키마"
테이블 = ["crops", "crop_variants", "crop_stages", "crop_disaster_rules", "varieties", "crop_guides"]

# ─────────────────────────────────────────────────────────────────────
# 저쪽 계약 — 베낀 것이다. 저쪽이 바뀌면 여기도 바꾼다
# ─────────────────────────────────────────────────────────────────────

칸 = {
    "crops": ["name", "base_temp", "upper_temp", "difficulty"],
    "crop_variants": ["crop_name", "maturity_type", "gdd_target", "days_to_harvest",
                      "sow_method", "sow_from", "sow_to",
                      # 2026-09-18 — 씨앗/모종 창을 따로. 저쪽 crop_variant.py · 시더와 같이 늘렸다
                      "seed_from", "seed_to", "plant_from", "plant_to"],
    # 2026-09-19 — irrigate_needed · stage_tasks · stage_hazards 추가.
    #   저쪽 crop_stage.py · 마이그레이션 · 시더와 같이 늘린다.
    # ⚠ `water_need_mm` 은 **버린 칸이다. 늘 비어 있는 것이 정상**이라 `필수` 에 넣지 않는다.
    #   까닭은 build.py 의 `계약` 주석(⚠⚠)에 있다. 칸은 저쪽 ORM 과 맞추려고 남긴다.
    "crop_stages": ["crop_name", "maturity_type", "stage_order", "stage_name",
                    "gdd_from", "gdd_to", "water_need_mm", "fertilize_needed",
                    "irrigate_needed", "stage_tasks", "stage_hazards", "guide_text"],
    # ⚠ 저쪽 `disaster_rules`(관측소·절기 기상통계)와 **다른 표**다. 섞지 말 것.
    #   2026-09-16 에 저쪽에 들어갔다 — app/models/farm/crop_disaster_rule.py
    "crop_disaster_rules": ["crop_name", "hazard", "rule_kind", "stage_name",
                            "metric", "op", "threshold_c", "duration_days", "severity"],
    "varieties": ["variety_no", "crop_group", "crop_name", "variety_group", "name",
                  "maturity_raw", "maturity_type", "use", "zone", "bred_year", "breeder",
                  "summary", "body", "source_file"],     # build.py 계약과 글자까지 같아야 한다     # build.py 계약과 글자까지 같아야 한다
    "crop_guides": ["crop_name", "cultivation_type", "section", "topic",
                    "body", "source_file", "source_loc"],
}

# nullable=False 인 칸. 비면 적재가 깨진다
# ⚠ base_temp·gdd_target 은 **여기 없는 것이 맞다.** 저쪽이 2026-09-17 에 nullable 로
#   바꿨다(ai-service/app/models/farm/crop.py `⚠ nullable 이다(2026-09-17). 이 표의 역할이
#   "GDD 엔진 테이블" 에서 "작물 사전" 으로` · crop_variant.py `gdd_target = Column(Integer)`).
#   전체 작물로 방침이 바뀌면서 값이 없는 작물이 정상이 됐기 때문이다.
#   ⚠ 뺀다고 감시가 사라지지 않는다 — 아래 `· §B-2 에 없어 base_temp 가 빈 작물 N개` 가
#     따로 세어 알린다. NOT NULL 에서 빼는 것은 "적재가 깨지느냐" 의 판정에서 빼는 것이지
#     "값이 비었다" 는 사실을 감추는 것이 아니다.
필수 = {
    "crops": ["name"],
    "crop_variants": ["crop_name", "maturity_type"],
    "crop_stages": ["crop_name", "maturity_type", "stage_order", "stage_name",
                    "gdd_from", "gdd_to", "fertilize_needed"],
    "crop_disaster_rules": ["crop_name", "hazard", "rule_kind", "metric", "op",
                            "threshold_c"],
    "varieties": ["variety_no", "crop_name", "name"],
    "crop_guides": ["crop_name", "section", "topic", "body"],
}

UNIQUE = [
    ("crops", ["name"]),
    ("crop_variants", ["crop_name", "maturity_type"]),
    ("crop_stages", ["crop_name", "maturity_type", "stage_order"]),
    ("crop_disaster_rules", ["crop_name", "rule_kind", "stage_name", "severity"]),
    ("varieties", ["variety_no"]),
    ("crop_guides", ["crop_name", "cultivation_type", "section", "topic"]),
]

REFS = [
    ("crop_variants", ["crop_name"], "crops", ["name"]),
    ("crop_stages", ["crop_name", "maturity_type"],
     "crop_variants", ["crop_name", "maturity_type"]),
    ("crop_disaster_rules", ["crop_name"], "crops", ["name"]),
]

# ck_crop_variants_maturity
숙기값 = ("EARLY", "MID", "LATE")

# ck_crops_difficulty — 2026-09-18 에 `강·중·약` 에서 바뀌었다.
# 저쪽 프런트(cropOption.ts)가 쓰는 낱말에 맞춘 것이다. 저쪽 모델도 같이 바뀌어야 한다.
난이도값 = ("쉬움", "보통", "어려움")

# sow_from · sow_to 의 꼴. **'MM-DD' 뿐이다.**
#   저쪽 crop_variant.py 주석이 "'MM-DD' 두 개다(연도 없음)" 라고 약속한 그대로다.
#
# ⚠ 안쪽에는 `+MM-DD`(이듬해) 표기가 있다(common.py era_edge). 그게 CSV 까지 새어
#   나오면 받는 쪽이 날짜로 파싱할 때 그 행에서만 깨진다 — build 의 `_시기()` 가
#   내보내기 직전에 뗀다. 여기서 '+' 를 **막아** 그 마개가 빠졌는지 알아챈다.
# ⚠ 해를 넘는 창은 `sow_to < sow_from` 으로 읽는다(셀러리 12-01 ~ 02-28).
시기꼴 = re.compile(r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")

# crop_disaster_rules 의 CHECK 세 가지
hazard값 = ("frost", "heat")
metric값 = ("ta_min", "ta_max", "ta_avg")
op값 = ("lte", "gte")

# ck_crop_guides_section. build.py 의 문서구분 을 import 하지 않고 한 번 더 적는다 —
# 검사가 검사 대상을 import 하면 둘이 같이 틀릴 수 있다
section값 = ("재배법", "기상재해대책", "생리적특성")


def 읽기():
    """<테이블>.csv 를 전부 읽는다. 파일명이 곧 테이블명이라는 저쪽 약속에 기댄다."""
    자료, 문제 = {}, []
    for 이름 in 테이블:
        p = 스키마 / f"{이름}.csv"
        if not p.exists():
            문제.append(f"{이름}: {p} 가 없다. build.py 를 먼저 돌려라")
            자료[이름] = []
            continue
        with io.open(p, encoding="utf-8-sig", newline="") as fh:
            자료[이름] = list(csv.DictReader(fh))
    return 자료, 문제


def _정수(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _열쇠(행, 칸들):
    return 행[칸들[0]] if len(칸들) == 1 else tuple(행[c] for c in 칸들)


# ─────────────────────────────────────────────────────────────────────
# 검사
# ─────────────────────────────────────────────────────────────────────

def 헤더(자료):
    """칸 이름과 차례가 계약과 같은가. 다르면 저쪽이 KeyError 로 죽는다."""
    문제 = []
    for 이름 in 테이블:
        행들 = 자료[이름]
        if not 행들:
            continue
        있는것 = list(행들[0].keys())
        if 있는것 != 칸[이름]:
            빠짐 = [c for c in 칸[이름] if c not in 있는것]
            군더더기 = [c for c in 있는것 if c not in 칸[이름]]
            말 = []
            if 빠짐:
                말.append(f"없는 칸 {빠짐}")
            if 군더더기:
                # ⚠ 칸이 남아도 문제다. 저쪽 load() 가 행을 그대로 ORM 에 넘긴다
                말.append(f"계약에 없는 칸 {군더더기}")
            if not 말:
                말.append(f"차례가 다르다 {있는것}")
            문제.append(f"{이름}: " + " · ".join(말))
    return 문제


def 빈칸(자료):
    """nullable=False 인 칸이 비었는가."""
    문제 = []
    for 이름 in 테이블:
        for c in 필수[이름]:
            빈 = [i for i, r in enumerate(자료[이름], 2) if not (r.get(c) or "").strip()]
            if 빈:
                자리 = ", ".join(map(str, 빈[:5])) + (" …" if len(빈) > 5 else "")
                문제.append(f"{이름}.{c}: 빈 칸 {len(빈)}행 (줄 {자리})")
    return 문제


def 제약(자료):
    """DB CHECK 와 자료형. 여기서 안 걸리면 적재 때 통째로 롤백된다."""
    문제 = []
    나쁜숙기 = sorted({r["maturity_type"] for r in 자료["crop_variants"]
                     if r.get("maturity_type") and r["maturity_type"] not in 숙기값})
    if 나쁜숙기:
        문제.append(
            f"crop_variants.maturity_type: EARLY/MID/LATE 가 아닌 값 {나쁜숙기}"
            "  (ck_crop_variants_maturity 에 걸린다)")
    나쁜숙기2 = sorted({r["maturity_type"] for r in 자료["crop_stages"]
                      if r.get("maturity_type") and r["maturity_type"] not in 숙기값})
    if 나쁜숙기2:
        문제.append(f"crop_stages.maturity_type: EARLY/MID/LATE 가 아닌 값 {나쁜숙기2}")

    나쁜숙기3 = sorted({r["maturity_type"] for r in 자료.get("varieties", [])
                      if r.get("maturity_type") and r["maturity_type"] not in 숙기값})
    if 나쁜숙기3:
        문제.append(f"varieties.maturity_type: EARLY/MID/LATE 가 아니거나 빈 값이 아닌 값 {나쁜숙기3}")

    for 칸이름, 허용 in [("hazard", hazard값), ("metric", metric값), ("op", op값)]:
        나쁨 = sorted({r[칸이름] for r in 자료.get("crop_disaster_rules", [])
                      if r.get(칸이름) and r[칸이름] not in 허용})
        if 나쁨:
            문제.append(f"crop_disaster_rules.{칸이름}: {'/'.join(허용)} 가 아닌 값 {나쁨}")

    나쁜시기 = sorted({(c, r[c]) for r in 자료["crop_variants"] for c in ("sow_from", "sow_to")
                     if (r.get(c) or "").strip() and not 시기꼴.match(r[c].strip())})
    if 나쁜시기:
        문제.append(f"crop_variants sow_from/sow_to: 'MM-DD' 가 아닌 값 {나쁜시기}"
                    "  ('+' 가 보이면 build 의 _시기() 를 안 거친 것이다)")

    나쁜난이도 = sorted({r["difficulty"] for r in 자료["crops"]
                       if r.get("difficulty") and r["difficulty"] not in 난이도값})
    if 나쁜난이도:
        문제.append(f"crops.difficulty: {'/'.join(난이도값)} 가 아닌 값 {나쁜난이도}"
                    "  (ck_crops_difficulty 에 걸린다)")

    나쁜구분 = sorted({r["section"] for r in 자료.get("crop_guides", [])
                     if r.get("section") and r["section"] not in section값})
    if 나쁜구분:
        문제.append(f"crop_guides.section: {'/'.join(section값)} 가 아닌 값 {나쁜구분}"
                    "  (ck_crop_guides_section 에 걸린다)")

    for i, r in enumerate(자료["crop_stages"], 2):
        a, b = _정수(r.get("gdd_from")), _정수(r.get("gdd_to"))
        if a is not None and b is not None and not a < b:
            문제.append(f"crop_stages 줄 {i}: gdd_from {a} < gdd_to {b} 가 아니다"
                        "  (ck_crop_stages_gdd_range)")
    for i, r in enumerate(자료["crops"], 2):
        v = (r.get("base_temp") or "").strip()
        if v:
            try:
                f = float(v)
            except ValueError:
                문제.append(f"crops 줄 {i}: base_temp 가 숫자가 아니다 {v!r}")
                continue
            # Numeric(4,1) — 소수 한 자리, 정수부 세 자리
            if round(f, 1) != f or abs(f) >= 1000:
                문제.append(f"crops 줄 {i}: base_temp {v} 가 Numeric(4,1) 에 안 맞는다")
    return 문제


def 겹침(자료):
    """CSV 안에서 자연키가 겹치는가. 저쪽 check.duplicates 와 같은 규칙."""
    문제 = []
    for 이름, 칸들 in UNIQUE:
        행들 = 자료[이름]
        if not 행들:
            continue
        본것, 겹친것 = set(), set()
        for r in 행들:
            try:
                k = _열쇠(r, 칸들)
            except KeyError:
                break                     # 헤더 검사가 이미 잡았다
            (겹친것 if k in 본것 else 본것).add(k)
        if 겹친것:
            문제.append(f"{이름}: {'+'.join(칸들)} 겹침 {sorted(map(str, 겹친것))}")
    return 문제


def 이음(자료):
    """자식이 가리키는 값이 부모에 있는가. identity id 는 적재 때 정해지므로 자연키로 본다."""
    문제 = []
    for 자식, 자식칸, 부모, 부모칸 in REFS:
        if not 자료[자식] or not 자료[부모]:
            continue
        try:
            아는것 = {_열쇠(r, 부모칸) for r in 자료[부모]}
            없는것 = sorted({str(_열쇠(r, 자식칸)) for r in 자료[자식]
                           if _열쇠(r, 자식칸) not in 아는것})
        except KeyError:
            continue
        if 없는것:
            문제.append(f"{자식} → {부모}: 없는 대상 {없는것}")
    return 문제


def 수확차례(자료):
    """단계 차례에서 **수확이 맨 끝인가.** 아니면 작형 여럿이 붙은 것이다.

    ⚠ 숫자로는 멀쩡해 보인다 — 빈칸도 끊김도 없다. 그런데 뜻이 깨져 있다.
        당근  봄재배 씨뿌림 → … → 수확 → **가을재배 씨뿌림**
        갓    씨뿌림 → 수확 → **어린 모 시기(유묘기)**
      이대로 시딩하면 밭 상세에 "수확 다음 정식포준비" 가 뜨고
      할 일 카드가 그 단계명으로 만들어진다 (2026-09-18 검토에서 25숙기 발견).

    ⚠ 수확이 **아예 없는** 것은 어긋남이 아니다. 잎을 계속 따는 산채가 그렇다.
      가려내려는 것은 수확 뒤에 파종·육묘 단계가 오는 꼴이다.
    """
    수확낱말 = ("수확", "거두기", "수매")
    # ⚠ 수확이 **아닌데** 수확 글자가 든 말. 체리의 `착과수확보`(착과·수확 확보)가
    #   수확으로 잡혀 여기서 오탐이 났다(2026-09-18).
    #   pipeline/cropping.py 에 같은 목록이 있지만 **일부러 한 번 더 적는다** —
    #   검사가 검사 대상을 import 하면 둘이 같이 틀릴 수 있다(이 파일 맨 위 원칙).
    수확아님 = ("수확보", "수확확보", "수확예정", "수확기예상")
    # ★ 2026-09-19 — 다년생은 수확하고 나서 낙엽 → 휴면으로 한 해를 닫는다.
    #   그건 "다음 작형이 붙은 자국" 이 아니므로 맨 뒤의 이 꼴은 세지 않는다.
    #   (cropping.다년생꼬리 와 같은 목록. 위 원칙대로 일부러 따로 적는다)
    다년생꼬리 = ("휴면", "낙엽", "월동", "뿌리활동", "수액이동")
    단계 = {}
    for r in 자료["crop_stages"]:
        단계.setdefault((r.get("crop_name"), r.get("maturity_type")), []).append(r)

    문제 = []
    for 열쇠, 행들 in sorted(단계.items()):
        행들 = sorted(행들, key=lambda r: int(r.get("stage_order") or 0))
        이름들 = [(r.get("stage_name") or "") for r in 행들]
        자리 = [
            i for i, n in enumerate(이름들)
            if any(w in n for w in 수확낱말)
            and not any(w in re.sub(r"\s", "", n) for w in 수확아님)
        ]
        끝 = len(이름들)
        while 자리 and 끝 > 자리[-1] + 1 and any(w in 이름들[끝 - 1] for w in 다년생꼬리):
            끝 -= 1
        if 자리 and 자리[-1] != 끝 - 1:
            뒤 = " → ".join(이름들[자리[-1]:])
            문제.append(f"{열쇠[0]}/{열쇠[1]}: 수확 뒤에 단계가 더 있다 — {뒤[:60]}")
    return 문제


def 단계연속(자료):
    """저쪽 stage_problems() 를 그대로 옮긴 것.

    ⚠ DB 는 행 하나씩만 본다(ck_crop_stages_gdd_range). 구간에 구멍이 뚫린 채
      들어가면 그 구간에 걸린 밭이 단계 판정에서 통째로 빠진다. DB 가 못 잡는다.
    """
    단계 = {}
    for r in 자료["crop_stages"]:
        단계.setdefault((r.get("crop_name"), r.get("maturity_type")), []).append(r)

    문제 = []
    없음 = 0
    for v in 자료["crop_variants"]:
        열쇠 = (v.get("crop_name"), v.get("maturity_type"))
        이름 = f"{열쇠[0]}/{열쇠[1]}"
        행들 = 단계.get(열쇠)
        if not 행들:
            # 단계가 없는 것은 이제 정상이다. 농작업일정 erajson 에 생육과정이 실린 작물만
            # crop_stages 가 나온다. 나머지는 GDD 판정만 못 할 뿐 카탈로그·검색에는 다 있다.
            # 이름을 하나하나 늘어놓으면 120줄이 화면을 덮어 진짜 문제가 묻힌다
            없음 += 1
            continue
        나쁜 = [c for c in ("stage_order", "gdd_from", "gdd_to")
               if any(_정수(r.get(c)) is None for r in 행들)]
        if 나쁜:
            문제.append(f"{이름}: 정수가 아닌 값이 있다 {나쁜}")
            continue
        행들.sort(key=lambda r: _정수(r["stage_order"]))
        차례 = [_정수(r["stage_order"]) for r in 행들]
        if 차례 != list(range(1, len(차례) + 1)):
            문제.append(f"{이름}: stage_order 가 1부터 연속이 아니다 {차례}")
        if _정수(행들[0]["gdd_from"]) != 0:
            문제.append(f"{이름}: 첫 단계 gdd_from {행들[0]['gdd_from']}, 0 이어야 한다")
        for 앞, 뒤 in zip(행들, 행들[1:], strict=False):
            if _정수(앞["gdd_to"]) != _정수(뒤["gdd_from"]):
                문제.append(f"{이름} {뒤['stage_order']}단계: gdd_from {뒤['gdd_from']}, "
                            f"앞 단계 gdd_to {앞['gdd_to']}")
        목표 = _정수(v.get("gdd_target"))
        if 목표 is None:
            문제.append(f"{이름}: gdd_target 이 정수가 아니다 {v.get('gdd_target')!r}")
        elif _정수(행들[-1]["gdd_to"]) != 목표:
            문제.append(f"{이름}: 마지막 gdd_to {행들[-1]['gdd_to']}, gdd_target {목표}")
    # spec.온도() 와 같은 방식 — 빠진 이름 대신 덮은 넓이를 알린다
    if 없음:
        print(f"  · 생육단계가 없는 숙기 {없음}/{len(자료['crop_variants'])}"
              f" — 농작업일정에 생육과정이 실린 작물만 단계가 나온다")
    return 문제


def 확정표대조(자료):
    """이쪽에만 있는 검사 — 값이 확정표와 같은가. 저쪽은 이걸 못 본다.

    CLAUDE.md "CSV 와 확정표가 다르면 확정표가 맞다. CSV 를 확정표에 맞춘다."

    ★ 2026-09-18 — **일부러 비우는 경우가 생겼다**(사료작물 10개). 논문에 값이 있는데도
      서비스가 안 다루는 작물이라 build 가 온도를 빼고 내보낸다.

      그렇다고 여기에 사료작물 목록을 또 적지는 않는다. 같은 목록이 두 파일에 있으면
      한쪽만 고쳤을 때 **검사가 조용히 무의미해진다.** 대신 `근거/crops.csv` 의
      `source` 칸을 본다 — build 가 거기에 까닭을 적게 되어 있고, 이 검사는
      **"까닭이 적혀 있는가" 를 확인한다.** 까닭 없이 비면 여전히 사고다.

      이 프로젝트의 "모든 숫자에 source 를 붙인다" 가 검사로 쓰이는 첫 자리다.
    """
    문제 = []
    try:
        import spec
        온도표 = spec.온도()
    except Exception as e:  # noqa: BLE001
        return [f"확정표를 못 읽어 대조를 건너뛴다: {e}"]

    # 근거 벌은 스키마와 같은 행이고 source 칸이 더 있다. 없으면 대조를 그냥 엄격하게 한다
    근거경로 = 스키마 / "근거" / "crops.csv"
    까닭 = {}
    if 근거경로.exists():
        with io.open(근거경로, encoding="utf-8-sig", newline="") as fh:
            까닭 = {r["name"]: (r.get("source") or "") for r in csv.DictReader(fh)}

    있는것 = {r["name"]: r for r in 자료["crops"]}
    일부러뺌 = 0
    for 작물, v in 온도표.items():
        r = 있는것.get(작물)
        if r is None:
            문제.append(f"crops: 확정표 §B-2 에 있는 {작물} 이 CSV 에 없다")
            continue
        기대 = v["base_temp"]
        본것 = None
        try:
            본것 = float(r["base_temp"])
        except (TypeError, ValueError):
            pass
        if 기대 is not None and 본것 != 기대:
            # 비었고 근거에 까닭이 적혀 있으면 일부러 뺀 것이다 (build 의 `사료작물`)
            if 본것 is None and "뺌" in 까닭.get(작물, ""):
                일부러뺌 += 1
                continue
            문제.append(f"crops.{작물}.base_temp: CSV {r['base_temp']} ≠ 확정표 {기대}")
    if 일부러뺌:
        print(f"  · 확정표에 값이 있는데 일부러 뺀 작물 {일부러뺌}개 — 근거/crops.csv 의 source 참고")
    남는것 = [n for n in 있는것 if n not in 온도표]
    if 남는것:
        # §B-2 에 없는 쪽이 이제 정상이다(spec.온도() 와 같은 판단). 원본에 있는 작물이
        # 전부 들어오므로 확정표 16작물이 덮는 범위가 오히려 좁다.
        # ⚠ 반대 방향 — "§B-2 에 있는데 CSV 에 없다" 는 위에서 여전히 문제로 잡는다.
        #   값이 있는데 안 실린 것이므로 그건 진짜 사고다
        print(f"  · §B-2 에 없어 base_temp 가 빈 작물 {len(남는것)}개 — 적산온도를 못 쌓는다")
    return 문제


# ─────────────────────────────────────────────────────────────────────

def main():
    자료, 문제 = 읽기()
    print(f"verify — {스키마}\n")
    for 이름 in 테이블:
        print(f"  {이름:16s} {len(자료[이름]):4d}행")
    print()

    묶음 = [
        ("헤더", 헤더(자료)),
        ("빈칸 (NOT NULL)", 빈칸(자료)),
        ("제약 (CHECK·자료형)", 제약(자료)),
        ("겹침 (UNIQUE)", 겹침(자료)),
        ("이음 (REFS)", 이음(자료)),
        ("단계 연속", 단계연속(자료)),
        ("수확이 마지막", 수확차례(자료)),
        ("확정표 대조", 확정표대조(자료)),
    ]
    총 = list(문제)
    for 제목, 것들 in 묶음:
        표시 = "통과" if not 것들 else f"{len(것들)}건"
        print(f"  [{표시:>4}] {제목}")
        for x in 것들[:12]:
            print(f"         - {x}")
        if len(것들) > 12:
            print(f"         … 그 밖에 {len(것들) - 12}건")
        총 += 것들

    print()
    if 총:
        print(f"검사 실패 {len(총)}건 — 지금 넘기면 적재가 깨집니다")
        print("  Safe-farm/ai-service/data/master/ 로 복사하지 마세요")
        return 1
    print("검사 통과 — 세 파일을 Safe-farm 으로 넘겨도 됩니다")
    print("  → Safe-farm/ai-service/data/master/ 에 놓고")
    print("     py -m pipeline.farm.master_seed_farm_db --check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
