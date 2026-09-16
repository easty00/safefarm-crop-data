# 중간 CSV + 확정표 → Safe-farm 스키마 3종.
#
#     python pipeline/build.py
#     → pipeline/out/스키마/      crops.csv · crop_variants.csv · crop_stages.csv
#     → pipeline/out/스키마/근거/  같은 행 + source · confirmed · 출처들
#
# ★ **파일 이름이 곧 테이블 이름이다.** Safe-farm 의 seeding.py 가
#   `read_csv(directory / f"{name}.csv")` 로 읽는다. 이름을 바꾸면 안 된다.
#
# ★ **칸도 계약이다.** 저쪽 ORM 이 받는 칸만 낸다. 늘리면 적재가 깨진다.
#   그래서 `source` · `confirmed` 는 근거/ 쪽에만 둔다 — 저쪽 ORM 에 그 칸이 없다.
#   CLAUDE.md "모든 숫자에 source 와 confirmed 를 붙인다" 는 이 폴더 안에서 지킨다.
#
#   `upper_temp` 는 2026-09-16 에 계약으로 옮겼다. 저쪽 crops 에 컬럼이 생겼고
#   (app/models/farm/crop.py), gdd.ts 의 dailyGdd 가 이 값을 받아 Modified 로 간다.
#   값이 없으면 전부 Standard 로 돌아 폭염일이 15% 부풀려진다.
#
# ⚠ **GDD 세 칸은 비운다.** gdd_target · gdd_from · gdd_to 는 일별 기온 역산이
#   있어야 나온다(확정표 §C — 11작물은 목표값 자체가 없고, 벼·수박은 ② 단위라
#   ③ 으로 환산해야 한다). 지어내지 않는다. verify.py 가 "아직 못 넘긴다" 고 찍는다.

import csv
import io
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "feature"))

import spec  # noqa: E402
from crops import CROP_ALIAS, MAIN_CROPS, nospace  # noqa: E402

OUT = HERE / "out"
스키마 = OUT / "스키마"
근거 = 스키마 / "근거"


# ─────────────────────────────────────────────────────────────────────
# 계약 — 저쪽 ORM 이 받는 칸. 늘리지 말 것
# ─────────────────────────────────────────────────────────────────────
계약 = {
    "crops.csv": ["name", "base_temp", "upper_temp", "difficulty"],
    "crop_variants.csv": ["crop_name", "maturity_type", "gdd_target", "days_to_harvest"],
    "crop_stages.csv": ["crop_name", "maturity_type", "stage_order", "stage_name",
                        "gdd_from", "gdd_to", "water_need_mm", "fertilize_needed",
                        "guide_text"],
    "crop_disaster_rules.csv": ["crop_name", "hazard", "rule_kind", "stage_name",
                                "metric", "op", "threshold_c", "duration_days", "severity"],
}

# 근거 벌에 덧붙이는 칸. 저쪽으로 넘어가지 않는다
덧칸 = {
    "crops.csv": ["confirmed", "source"],
    "crop_variants.csv": ["숙기원문", "품종수", "작형", "confirmed", "source"],
    "crop_stages.csv": ["작형", "시작중앙일", "종료중앙일", "source"],
    "crop_disaster_rules.csv": ["실린호", "원본수", "출처들", "조건원문", "source"],
}


def 읽기(경로):
    with io.open(경로, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def 쓰기(이름, 행들, 칸들, 폴더):
    폴더.mkdir(parents=True, exist_ok=True)
    with (폴더 / 이름).open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=칸들, extrasaction="ignore")
        w.writeheader()
        w.writerows(행들)
    print(f"  {이름:20} {len(행들):4}행  → {폴더.name}/")


def 내기(이름, 행들):
    """계약 벌과 근거 벌을 같이 쓴다. 행은 하나에서 나온다 — 갈리지 않는다."""
    쓰기(이름, 행들, 계약[이름], 스키마)
    쓰기(이름, 행들, 계약[이름] + 덧칸[이름], 근거)


def 표준작물(이름):
    """'벼 기계이앙재배' · '배추(고랭지재배)' → '벼' · '배추'."""
    return CROP_ALIAS.get(nospace(이름 or ""), "")


# ─────────────────────────────────────────────────────────────────────
# crops — 확정표 §B-2 가 그대로 들어간다
# ─────────────────────────────────────────────────────────────────────

def crops(온도표):
    """14행. base_temp 는 확정표 §B-2 채택값이다.

    ⚠ `difficulty` 는 확정표 어디에도 없다. 비워 둔다(저쪽 ORM 도 nullable).
      지어내면 "이 숫자 어디서 났냐" 에 답할 수 없다.
    """
    행들 = []
    for 작물, v in 온도표.items():
        if 작물 not in MAIN_CROPS:
            print(f"  ⚠ 확정표에 있는데 등록표(crops.py)에 없는 작물: {작물}")
        행들.append({
            "name": 작물,
            "base_temp": f"{v['base_temp']:.1f}" if v["base_temp"] is not None else "",
            "difficulty": "",
            "upper_temp": f"{v['upper_temp']:.1f}" if v["upper_temp"] is not None else "",
            "confirmed": v["confirmed"],
            "source": "확정표 §B-2",
        })
    return sorted(행들, key=lambda r: r["name"])


# ─────────────────────────────────────────────────────────────────────
# crop_variants — 숙기 접기 + 재배일수
# ─────────────────────────────────────────────────────────────────────

def _대표작형(작형표):
    """작물 하나에 작형이 여럿이면 **§A 의 첫 행**을 대표로 쓴다.

    ⚠ UNIQUE 가 (crop_name, maturity_type) 이라 한 작물에 한 행뿐이다.
      그런데 §A 는 배추를 봄 86 · 가을 91 · 고랭지 86 셋으로 적는다.
      지금은 첫 행을 쓰고 `작형` 칸에 무엇을 골랐는지 남긴다.
      → 확정표 §A 에 '대표작형' 열이 생기면 그걸 읽도록 한 줄만 고치면 된다.
    """
    대표 = {}
    for r in 작형표:
        대표.setdefault(r["작물"], r)
    return 대표


def crop_variants(온도표, 작형표, 접기, 수박표, 분할작물, 품종들):
    """작물 × 숙기. gdd_target 은 비운다(맨 위 ⚠).

    ★ **몇 갈래로 나눌지는 확정표가 정한다. 품종정보가 아니다.**
        §D-1 표에 있는 작물(벼·감자·양파)  → EARLY/MID/LATE 3행
        수박                            → §D-3 표로 (소과종은 숙기가 아니라 과실 크기)
        나머지                           → MID 한 행 (§D-2)
      품종정보만 보고 만들었더니 배추가 세 행, 고추가 EARLY 한 행이 나왔다.
      확정표 §D-2 는 둘 다 'MID 한 행' 이라고 못박는다.
    """
    대표 = _대표작형(작형표)
    행들, 못접은것 = [], {}

    # 품종정보는 **갈래를 정하는 데 쓰지 않고**, 3분할 작물의 품종 수를 세는 데만 쓴다
    본선숙기 = {}
    for v in 품종들:
        작물, 숙기 = v.get("작물", ""), v.get("숙기", "")
        if not 숙기 or 작물 not in 분할작물:
            continue
        코드 = 접기.get(숙기)
        if 코드 is None:
            # ⚠ 확정표 §D-1 접는 규칙에 없는 숙기다. 지금은 '조중생' 하나뿐이고
            #   어느 쪽으로 접을지 안 정했다(확인필요.md §5). **버리지 않고 알린다.**
            못접은것.setdefault(숙기, {}).setdefault(작물, 0)
            못접은것[숙기][작물] += 1
            continue
        칸 = 본선숙기.setdefault(작물, {}).setdefault(코드, {"수": 0, "원문": set()})
        칸["수"] += 1
        칸["원문"].add(숙기)

    for 작물 in sorted(온도표):
        기본 = 대표.get(작물)
        일수 = int(기본["일수"]) if 기본 and 기본["일수"] else ""
        작형이름 = (기본 or {}).get("작형", "")

        # ① 수박 — 품종정보가 아니라 농작업일정 표에서 나온다 (확정표 §D-3)
        if 작물 == "수박":
            # ⚠ §D-3 은 4분할(소과종·조생·중생·만생)인데 스키마는 3분할이다.
            #   소과종과 조생종이 둘 다 EARLY 로 접혀 **같은 (작물, 숙기) 가 두 행**이 됐다.
            #   crop_variants 의 PK 가 (crop_name, maturity_type) 이라 적재가 깨진다.
            #   verify 의 '겹침(UNIQUE)' 가 잡아준 것이다.
            #   → 접은 뒤 합친다. 원문은 둘 다 '숙기원문' 에 남겨 무엇이 합쳐졌는지 보이게 한다.
            묶음 = {}
            for r in 수박표:
                코드 = 접기.get(r["숙기"]) or 접기.get(r["숙기"].replace("종", ""))
                if 코드 is None:
                    못접은것.setdefault(r["숙기"], {}).setdefault("수박", 0)
                    못접은것[r["숙기"]]["수박"] += 1
                    continue
                묶음.setdefault(코드, []).append(r)
            for 코드, 것들 in 묶음.items():
                행들.append({
                    "crop_name": 작물, "maturity_type": 코드,
                    "gdd_target": "",          # ⚠ §D-3 값은 ② 단위다. 역산 전까지 비운다
                    # ⚠ §D-3 의 일수는 **착과 후** 일수다. ORM 의 days_to_harvest 는
                    #   "파종부터 수확까지" 라 뜻이 다르다. §A 의 101일을 쓰고
                    #   착과 후 일수는 근거 쪽에만 남긴다
                    "days_to_harvest": 일수,
                    "숙기원문": " + ".join(f"{r['숙기']} (착과 후 {r['일수']}일)" for r in 것들),
                    "품종수": "", "작형": 작형이름,
                    "confirmed": 것들[0]["confirmed"], "source": "확정표 §D-3",
                })
            continue

        # ② 3분할 작물 — 확정표 §D-1 표에 이름이 있는 것만
        if 작물 in 분할작물:
            갈래 = 본선숙기.get(작물, {})
            for 코드 in ("EARLY", "MID", "LATE"):
                칸 = 갈래.get(코드)
                행들.append({
                    "crop_name": 작물, "maturity_type": 코드,
                    "gdd_target": "", "days_to_harvest": 일수,
                    "숙기원문": " · ".join(sorted(칸["원문"])) if 칸 else "",
                    "품종수": 칸["수"] if 칸 else 0, "작형": 작형이름,
                    "confirmed": "N",
                    "source": "확정표 §D-1 + 품종정보 varieties.csv",
                })
            continue

        # ③ 나머지 — MID 한 행 (확정표 §D-2)
        행들.append({
            "crop_name": 작물, "maturity_type": "MID",
            "gdd_target": "", "days_to_harvest": 일수,
            "숙기원문": "", "품종수": "", "작형": 작형이름,
            "confirmed": "N", "source": "확정표 §D-2 (MID 한 행)",
        })

    if 못접은것:
        print("  ⚠ 확정표 §D-1 접는 규칙에 없는 숙기 — 행을 만들지 않았습니다")
        for 숙기, 작물들 in sorted(못접은것.items()):
            낱 = " · ".join(f"{c} {n}" for c, n in sorted(작물들.items()))
            print(f"      {숙기}: {낱}")
        print("      → 확인필요.md §5 에서 정한 뒤 확정표 §D-1 에 한 줄 더하면 붙습니다")
    return 행들


# ─────────────────────────────────────────────────────────────────────
# guide_text — 단계별 안내
# ─────────────────────────────────────────────────────────────────────
# 테이블정의서(`docs/세이프팜_테이블정의서.xlsx` 2.컬럼정의)가 이렇게 적어뒀다.
#
#     crop_stages.guide_text  TEXT  "Claude에게 참고자료로 넘길 기본 설명"
#
# 농작업일정 재배법 본문이 그 꼴 그대로다. 머리글 한 줄 뒤에 자세한 줄이 붙는다.
#
#     씨뿌림                          ← 머리글
#     시 기 : 남부 2월 초순~2월 중순    ← 자세히
#     씨앗량 : 1㎗/10a
#     모 기르기                       ← 다음 머리글
#
# ⚠ 지어내지 않는다. 원문을 그대로 잇는다. 없으면 빈칸이다.

def _안내모으기(본문행들):
    """{작물: [(머리글, 자세한글)]}. 농작업일정 재배법에서만 모은다."""
    묶 = {}
    for r in 본문행들:
        if r.get("구분") != "재배법":
            continue
        작물 = 표준작물(r.get("작물"))
        if not 작물:
            continue
        글 = (r.get("본문") or "").strip()
        if not 글:
            continue
        칸 = 묶.setdefault(작물, [])
        # 머리글은 짧고 콜론이 없다. 자세한 줄은 '항목 : 값' 꼴이다
        머리인가 = ":" not in 글 and len(글) <= 14
        if 머리인가:
            칸.append([글, []])
        elif 칸:
            칸[-1][1].append(글)
    return 묶


def _안내찾기(안내, 작물, 단계이름, 최대=400):
    """단계 이름에 맞는 머리글을 찾아 그 아래 줄들을 잇는다. 못 찾으면 빈 문자열."""
    후보 = 안내.get(작물) or []
    단순 = nospace(단계이름)
    for 머리, 줄들 in 후보:
        if not 줄들:
            continue
        ㅁ = nospace(머리)
        if ㅁ and (ㅁ in 단순 or 단순 in ㅁ):
            글 = " / ".join(줄들)
            return 글[:최대]
    return ""


# ─────────────────────────────────────────────────────────────────────
# crop_stages — 농작업일정의 생육과정
# ─────────────────────────────────────────────────────────────────────

# 생육 단계로 볼 작업명. 김매기·물주기·웃거름·저장 같은 '할 일' 은 단계가 아니다
단계낱말 = ("씨뿌림", "씨뿌릴", "파종", "모내기", "아주심기", "정식", "발아",
            "어린 모", "어린모", "모기르기", "모 기르기", "육묘", "유묘",
            "신장", "결구", "비대", "개화", "꽃", "착과", "열매", "이삭", "출수",
            "익음", "성숙", "수확")


def _상대일(중앙일, 기준):
    """'09-25' 를 재배 시작(기준)부터 며칠째인지로 바꾼다.

    ⚠ **월동 작물은 해를 넘긴다.** 마늘·양파는 9월에 심어 이듬해 6월에 캔다.
      'MM-DD' 글자 그대로 세우면 **수확(06-05)이 씨뿌림(09-25)보다 앞**에 온다.
      실제로 양파가 '수확 → 씨뿌림 → 아주심기' 로 나왔다.
    """
    try:
        m, d = (int(x) for x in (중앙일 or "").split("-"))
        기m, 기d = (int(x) for x in (기준 or "01-01").split("-"))
    except (ValueError, TypeError):
        return 999
    날 = m * 31 + d
    시작 = 기m * 31 + 기d
    return 날 - 시작 if 날 >= 시작 else 날 - 시작 + 12 * 31


# 재배가 시작되는 단계. 이것의 날짜가 그 작물의 0일이다
시작낱말 = ("씨뿌림", "씨뿌릴", "파종", "모기르기", "모 기르기", "온상설치", "육묘", "발아")


def _작형맞나(정보구분, 확정작형):
    """`정보구분` 뒤에 붙은 작형이 확정표 §A 가 고른 작형인가.

    ⚠ 수박·방울토마토·가지는 **시설 작형이 섞여 들어온다.**
        '생육과정(주요농작업)'            ← 꼬리 없음. 노지다
        '생육과정(주요농작업) - 촉성재배'   ← 시설. 확정표 §A 가 '이름만 쓰면 시설이 섞인다' 고
                                          경고한 그것이다
      꼬리가 확정표 작형과 같거나, 꼬리가 아예 없는 것만 받는다.
    """
    꼬리 = (정보구분 or "").split(" - ", 1)
    if len(꼬리) == 1:
        return True                       # 꼬리 없음 = 기본(노지)
    꼬리 = 꼬리[1].strip()
    확정 = (확정작형 or "").strip()
    return bool(확정) and (꼬리 in 확정 or 확정 in 꼬리)


def crop_stages(일정행들, variants, 작형표, 안내=None):
    """작물 × 숙기 × 단계. gdd_from/gdd_to 는 비운다(맨 위 ⚠).

    ⚠ **작형이 섞여 있다.** `작형` 칸은 비어 있고, 봄·가을이 '봄배추 ▶' 같은
      표시 행으로만 갈린다(6작물 17행). 표시 행을 만나면 새 덩이로 끊고,
      **첫 덩이만** 쓴다 — 확정표 §A 의 첫 작형과 같은 자리다.
      표시가 없는 작물은 통째로 한 덩이다.

    ⚠ 한 작물에 숙기가 여럿이면 **같은 단계를 숙기마다 복사한다.** 숙기별 단계
      구분은 자료에 없다. GDD 가 들어오면 구간만 숙기별로 갈라지고 이름은 같다.
    """
    # ① 작물마다 문서 하나만 쓴다. 한 작물에 문서가 여럿이다 —
    #    벼는 기계이앙(30697)과 직파(30698)가 따로고, 섞으면 '모내기때' 와 '씨뿌릴때' 가
    #    한 줄기에 같이 들어와 여덟 단계가 된다. 실제로 그랬다.
    #    괄호 없는 이름(= 확정표 §A 의 첫 작형)을 고른다.
    확정작형 = {x["작물"]: x["작형"] for x in reversed(작형표)}
    문서 = {}
    for r in 일정행들:
        if not (r.get("정보구분") or "").startswith("생육과정"):
            continue
        작물 = 표준작물(r.get("작물"))
        if 작물 not in MAIN_CROPS:
            continue
        if not _작형맞나(r.get("정보구분"), 확정작형.get(작물)):
            continue
        원이름 = (r.get("작물") or "")
        고름 = 문서.get(작물)
        # 괄호가 없는 쪽이 대표다. '배추' vs '배추(고랭지재배)'
        if 고름 is None or ("(" in 고름 and "(" not in 원이름):
            문서[작물] = 원이름

    # ② 작형 갈라내기 — ▶ 표시는 맨 앞에 몰려 있어 자리로는 못 가른다.
    #    원문을 보면 **작업명마다 봄·가을이 짝으로 두 번** 나온다.
    #       봄배추 ▶ / 가을배추 ▶ / 결구기(4월) / 결구기(10월) / 어린모(1월) / 어린모(8월) …
    #    그래서 같은 작업명은 **파일에서 먼저 나온 것**만 쓴다. 그게 첫 작형이다.
    덩이별 = {}
    for r in 일정행들:
        if not (r.get("정보구분") or "").startswith("생육과정"):
            continue
        작물 = 표준작물(r.get("작물"))
        if 작물 not in MAIN_CROPS or (r.get("작물") or "") != 문서.get(작물):
            continue
        if not _작형맞나(r.get("정보구분"), 확정작형.get(작물)):
            continue
        이름 = (r.get("작업명") or "").strip()
        키 = 덩이별.setdefault(작물, {"행": [], "본이름": set(), "작형": ""})
        if "▶" in 이름:
            if not 키["작형"]:
                키["작형"] = 이름.replace("▶", "").strip()
            continue
        if not any(w in 이름 for w in 단계낱말):
            continue                      # '김매기, 물주기' 같은 할 일은 단계가 아니다
        if 이름 in 키["본이름"]:
            continue                      # 같은 작업명의 두 번째 = 다음 작형
        키["본이름"].add(이름)
        키["행"].append(r)

    숙기별 = {}
    for v in variants:
        숙기별.setdefault(v["crop_name"], []).append(v["maturity_type"])

    행들 = []
    for 작물, 묶 in sorted(덩이별.items()):
        # 시작 중앙일 차례로 세운다. 월·순 만으로는 해를 넘기는 작물이 어긋난다
        # 재배 시작 단계를 0일로 놓고 그로부터 며칠째인지로 세운다(위 ⚠)
        시작들 = [r.get("시작중앙일") for r in 묶["행"]
                 if any(w in (r.get("작업명") or "") for w in 시작낱말)]
        기준 = min(시작들) if 시작들 else "01-01"
        차례 = sorted(묶["행"], key=lambda r: _상대일(r.get("시작중앙일"), 기준))
        본 = []
        for r in 차례:
            이름 = (r.get("작업명") or "").strip()
            if 본 and 본[-1][0] == 이름:
                continue                  # 같은 이름이 잇달으면 한 단계다
            본.append((이름, r))
        for 숙기 in 숙기별.get(작물, []):
            for i, (이름, r) in enumerate(본, 1):
                행들.append({
                    "crop_name": 작물, "maturity_type": 숙기,
                    "stage_order": i, "stage_name": 이름[:40],
                    "gdd_from": "", "gdd_to": "",
                    # ⚠ water_need_mm 을 채울 자료가 없다. 농작업일정 첨부에
                    #   '수분장력' 이 있다고 CLAUDE.md 에 적혀 있으나 추출 결과에는
                    #   0건이고, '관수량' 223건은 전부 시설 관수비용표(㎥/㏊/월)다.
                    #   단계별 mm 로 쓸 수 있는 값이 아니다. 비워 둔다.
                    "water_need_mm": "", "fertilize_needed": "false",
                    "guide_text": _안내찾기(안내 or {}, 작물, 이름),
                    "작형": 묶["작형"],
                    "시작중앙일": r.get("시작중앙일", ""),
                    "종료중앙일": r.get("종료중앙일", ""),
                    "source": f"농작업일정 {r.get('출처파일', '')}",
                })
    return 행들


# ─────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────
# crop_disaster_rules — 작물별 재해 경보 기준
#
# ⚠ 저쪽에 **이미 `disaster_rules` 가 있는데 다른 것**이다. 섞지 말 것.
#
#     저쪽 disaster_rules   station · risk("01".."05") · solar_term · ta_min · tg_min
#                          "절기재해 기준값(다년 평균)" — 관측소별 기상 통계.
#                          app.core.db.Base 쪽이다(문서·기상 계열)
#     이 표                 작물 · 생육단계 · 임계온도 — **작물 생리 기준**
#                          FarmBase 쪽이다(crops · crop_variants · crop_stages 와 한 묶음)
#
#   저쪽이 "언제 그런 날씨가 오나" 를 주고, 이 표가 "그 작물이 그 온도에서 다치나" 를 준다.
#
# ★ 어휘는 저쪽을 따른다. `hazard` 는 프런트 `HazardKind`(hazards.ts) 의 말이다.
#     frost  저온재해 (절기재해 risk=01 · 특보 C 한파)
#     heat   고온재해 (절기재해 risk=02 · 특보 H 폭염)
#   프런트 `growthStage.ts` 가 지금 `frostRiskBelowC` · `heatRiskAboveC` 를
#   작물당 하나씩 상수로 박아 쓰고 있다(상추 4/26 · 토마토 6/32). 이 표가 그 자리다.
#
# ⚠ `rule_kind` 를 따로 두는 까닭 — frost 하나로 뭉치면 값이 섞인다.
#     배추 동해 -6 과 냉해 -8 은 둘 다 frost 인데 뜻이 다르다(확정표 §B-4).
#
# ⚠ **생육 최저/최고 한계는 넣지 않는다.** 확정표 §B-4 가 "경보로 쓰면 안 됨" 이라 못박았다.
#   봄배추는 1월 파종이라 최저기온 5℃ 이하인 날이 석 달 내내 있다 — 경보가 상시 울린다.
# ─────────────────────────────────────────────────────────────────────

# 우리 '재해종류' → (hazard, rule_kind)
재해갈래 = {
    "동해": ("frost", "동해"),
    "냉해": ("frost", "냉해"),
    "단계별저온": ("frost", "저온"),
    "고온해": ("heat", "고온해"),
}
# ⚠ 한 자리(작물·규칙·단계·등급)에 값이 둘인 것. 확정표가 고른 쪽만 남긴다.
#   마늘은 난지형 -5~-6 과 한지형 -7~-8 이 둘 다 원문에 있다. 표에 유형 칸이 없어
#   mid_rule 에는 두 행이 다 남는다 — 고르는 것은 여기서 한다.
#   확정표 §B-4 가 **난지형** 으로 정했다(2026-09-16). 까닭 둘 —
#     ① 국내 재배면적이 난지형 쪽이 많다
#     ② 경보는 -6 이 -8 보다 **먼저 울린다.** 한지형 지역에서 조금 이르게 울릴 뿐 놓치지 않는다
골라내기 = {("마늘", "동해"): "난지형"}

# 넣지 않는 것 — 까닭을 적어둔다
재해제외 = {
    "한계_최저": "생육 최저한계. 경보가 아니다 (확정표 §B-4)",
    "한계_최고": "생육 최고한계. 경보가 아니다 (확정표 §B-4)",
    "병해충": "병원균 발병 조건이라 작물 임계값이 아니다. 방제 시기 추천 쪽",
}


def _단계정리(단계, 종류):
    """단계 칸에 올라온 **표 머리글**을 비운다.

    한계온도표는 머리글이 `냉해온도` · `동해온도` 라, 칸을 그대로 옮기면
    생육단계가 아니라 재해 이름이 `stage_name` 에 앉는다. 그 값은 —

      · `crop_stages.stage_name` 과 영영 안 맞는다 (거기엔 그런 단계가 없다)
      · UNIQUE(crop_id, rule_kind, stage_name, severity) 를 헛돌게 한다.
        나중에 같은 작물에 진짜 단계가 붙으면 두 행이 남는다
      · ORM 주석의 약속("비면 작물 전체에 걸린다")을 깬다

    ⚠ 지울 말을 따로 적어두지 않는다. 그 행의 `재해종류` 에서 끌어낸다 —
      재해가 늘어도 `○○해온도` 꼴이면 저절로 걸린다.
    """
    깬 = " ".join((단계 or "").split())
    if not 깬:
        return ""
    if 깬 == 종류 or 깬.replace("온도", "").strip() == 종류:
        return ""
    return 깬


def crop_disaster_rules(규칙행들, crops행들):
    """mid_rule → 저쪽이 받을 수 있는 꼴로.

    ⚠ 부모(crops)에 없는 작물은 넣지 않는다. 저쪽 시더가 자연키(crop_name)로
      부모를 찾는데 없으면 적재가 깨진다.
    """
    있는작물 = {r["name"] for r in crops행들}
    행들, 제외셈 = [], {}
    for r in 규칙행들:
        종류 = r["재해종류"]
        if 종류 in 재해제외:
            제외셈[종류] = 제외셈.get(종류, 0) + 1
            continue
        갈래 = 재해갈래.get(종류)
        작물 = 표준작물(r["작물"])
        if not 갈래 or 작물 not in 있는작물:
            continue
        hazard, kind = 갈래
        고를말 = 골라내기.get((작물, 종류))
        if 고를말 and 고를말 not in (r["조건원문"] or ""):
            continue                      # 확정표가 고른 유형이 아니다
        행들.append({
            "crop_name": 작물,
            "hazard": hazard,
            "rule_kind": kind,
            # 단계가 비면 작물 전체에 걸린다
            "stage_name": _단계정리(r["생육단계"], 종류),
            "metric": {"최저기온": "ta_min", "최고기온": "ta_max",
                       "평균기온": "ta_avg"}.get(r["지표"], r["지표"]),
            "op": {"<=": "lte", ">=": "gte"}.get(r["부등호"], r["부등호"]),
            "threshold_c": r["값"],
            "duration_days": r["지속일"],
            "severity": r["등급"],
            # 근거 쪽
            "실린호": r["실린호"], "원본수": r["원본수"], "출처들": r["출처들"],
            "조건원문": r["조건원문"], "source": f"{r['출처']} · {r['출처파일']}",
        })
    return 행들, 제외셈


def main():
    print("build — 확정표 + 중간 CSV → 스키마 3종\n")
    try:
        온도표 = spec.온도()
        작형표 = spec.작형()
        접기 = spec.숙기접기()
        수박표 = spec.수박숙기()
        분할작물 = spec.숙기분할작물()
    except spec.확정표오류 as e:
        print(f"확정표를 못 읽었습니다\n  {e}")
        return 1
    print(f"확정표 — 온도 {len(온도표)}작물 · 작형 {len(작형표)}행")
    print(f"         숙기 3분할 {list(분할작물)} · 접기 {접기}\n")

    품종경로 = OUT / "원본별" / "품종정보" / "varieties.csv"
    품종들 = 읽기(품종경로) if 품종경로.exists() else []
    if not 품종들:
        print(f"  ⚠ {품종경로.name} 이 없습니다. 숙기 갈래가 전부 MID 한 행이 됩니다")
    일정경로 = OUT / "mid_schedule.csv"
    일정 = 읽기(일정경로) if 일정경로.exists() else []
    if not 일정:
        print(f"  ⚠ {일정경로.name} 이 없습니다. crop_stages 가 빕니다")

    c = crops(온도표)
    v = crop_variants(온도표, 작형표, 접기, 수박표, 분할작물, 품종들)
    본문 = 읽기(OUT / "mid_text.csv") if (OUT / "mid_text.csv").exists() else []
    s = crop_stages(일정, v, 작형표, _안내모으기(본문))

    규칙경로 = OUT / "mid_rule.csv"
    규칙 = 읽기(규칙경로) if 규칙경로.exists() else []
    if not 규칙:
        print(f"  ⚠ {규칙경로.name} 이 없습니다. crop_disaster_rules 가 빕니다")
    d, 제외셈 = crop_disaster_rules(규칙, c)

    print()
    내기("crops.csv", c)
    내기("crop_variants.csv", v)
    내기("crop_stages.csv", s)
    내기("crop_disaster_rules.csv", d)

    if 제외셈:
        print("\n  · 경보로 안 넣은 규칙")
        for 종류, n in sorted(제외셈.items()):
            print(f"      {종류:10}{n:>4}행   {재해제외[종류]}")

    빈gdd = sum(1 for r in v if not r["gdd_target"])
    print(f"\n⚠ gdd_target 이 빈 행 {빈gdd}/{len(v)} · gdd_from/to 가 빈 행 {len(s)}/{len(s)}")
    print("   일별 기온 역산이 있어야 찹니다(확정표 §C). 그 전까지는 넘기면 안 됩니다.")
    print("\n다음: python pipeline/verify.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
