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
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

스키마 = HERE / "out" / "스키마"
테이블 = ["crops", "crop_variants", "crop_stages", "crop_disaster_rules", "varieties"]

# ─────────────────────────────────────────────────────────────────────
# 저쪽 계약 — 베낀 것이다. 저쪽이 바뀌면 여기도 바꾼다
# ─────────────────────────────────────────────────────────────────────

칸 = {
    "crops": ["name", "base_temp", "upper_temp", "difficulty"],
    "crop_variants": ["crop_name", "maturity_type", "gdd_target", "days_to_harvest",
                      "sow_method", "sow_from", "sow_to"],
    "crop_stages": ["crop_name", "maturity_type", "stage_order", "stage_name",
                    "gdd_from", "gdd_to", "water_need_mm", "fertilize_needed",
                    "guide_text"],
    # ⚠ 저쪽 `disaster_rules`(관측소·절기 기상통계)와 **다른 표**다. 섞지 말 것.
    #   2026-09-16 에 저쪽에 들어갔다 — app/models/farm/crop_disaster_rule.py
    "crop_disaster_rules": ["crop_name", "hazard", "rule_kind", "stage_name",
                            "metric", "op", "threshold_c", "duration_days", "severity"],
    "varieties": ["variety_no", "crop_group", "crop_name", "variety_group", "name",
                  "maturity_raw", "maturity_type", "use", "zone", "bred_year", "breeder",
                  "summary", "body", "source_file"],     # build.py 계약과 글자까지 같아야 한다     # build.py 계약과 글자까지 같아야 한다
}

# nullable=False 인 칸. 비면 적재가 깨진다
필수 = {
    "crops": ["name", "base_temp"],
    "crop_variants": ["crop_name", "maturity_type", "gdd_target"],
    "crop_stages": ["crop_name", "maturity_type", "stage_order", "stage_name",
                    "gdd_from", "gdd_to", "fertilize_needed"],
    "crop_disaster_rules": ["crop_name", "hazard", "rule_kind", "metric", "op",
                            "threshold_c"],
    "varieties": ["variety_no", "crop_name", "name"],
}

UNIQUE = [
    ("crops", ["name"]),
    ("crop_variants", ["crop_name", "maturity_type"]),
    ("crop_stages", ["crop_name", "maturity_type", "stage_order"]),
    ("crop_disaster_rules", ["crop_name", "rule_kind", "stage_name", "severity"]),
    ("varieties", ["variety_no"]),
]

REFS = [
    ("crop_variants", ["crop_name"], "crops", ["name"]),
    ("crop_stages", ["crop_name", "maturity_type"],
     "crop_variants", ["crop_name", "maturity_type"]),
    ("crop_disaster_rules", ["crop_name"], "crops", ["name"]),
]

# ck_crop_variants_maturity
숙기값 = ("EARLY", "MID", "LATE")

# crop_disaster_rules 의 CHECK 세 가지
hazard값 = ("frost", "heat")
metric값 = ("ta_min", "ta_max", "ta_avg")
op값 = ("lte", "gte")


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
    """
    문제 = []
    try:
        import spec
        온도표 = spec.온도()
    except Exception as e:  # noqa: BLE001
        return [f"확정표를 못 읽어 대조를 건너뛴다: {e}"]

    있는것 = {r["name"]: r for r in 자료["crops"]}
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
            문제.append(f"crops.{작물}.base_temp: CSV {r['base_temp']} ≠ 확정표 {기대}")
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
