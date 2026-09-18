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
#   `sow_method` · `sow_from` · `sow_to` 도 2026-09-16 에 넣었다. §A 의 파종일은
#   지금까지 GDD 역산의 **입력**으로만 쓰이고 버려졌다 — 그래서 "상추 언제 심어?"
#   에 서비스가 "자료에 없습니다" 라고 답했다. 계산 재료를 남기는 칸이다.

#
# ⚠ **GDD 세 칸은 비운다.** gdd_target · gdd_from · gdd_to 는 일별 기온 역산이
#   있어야 나온다(확정표 §C — 11작물은 목표값 자체가 없고, 벼·수박은 ② 단위라
#   ③ 으로 환산해야 한다). 지어내지 않는다. verify.py 가 "아직 못 넘긴다" 고 찍는다.

import csv
import io
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "feature"))

import cropping  # noqa: E402
import spec  # noqa: E402
from crops import CROP_ALIAS, nospace  # noqa: E402
from common import era_edge, middle_day  # noqa: E402

OUT = HERE / "out"
스키마 = OUT / "스키마"
근거 = 스키마 / "근거"


# ─────────────────────────────────────────────────────────────────────
# 계약 — 저쪽 ORM 이 받는 칸. 늘리지 말 것
# ─────────────────────────────────────────────────────────────────────
계약 = {
    "crops.csv": ["name", "base_temp", "upper_temp", "difficulty"],
    "crop_variants.csv": ["crop_name", "maturity_type", "gdd_target", "days_to_harvest",
                          "sow_method", "sow_from", "sow_to"],
    "crop_stages.csv": ["crop_name", "maturity_type", "stage_order", "stage_name",
                        "gdd_from", "gdd_to", "water_need_mm", "fertilize_needed",
                        "guide_text"],
    "crop_disaster_rules.csv": ["crop_name", "hazard", "rule_kind", "stage_name",
                                "metric", "op", "threshold_c", "duration_days", "severity"],
    # 품종 카탈로그. 작물 필터 없이 2,599품종 전부 — 43작물이라 crops 와 FK 를 걸지 않는다.
    # variety_no 는 농사로 cntntsNo. 재수집해도 안 바뀌는 자연키다
    "varieties.csv": ["variety_no", "crop_group", "crop_name", "variety_group", "name",
                      "maturity_raw", "maturity_type", "use", "zone", "bred_year", "breeder",
                      "summary", "body", "source_file"],
    # 재배법·재해대책·생리특성 문장. crop_stages.guide_text(단계당 한 줄)와 달리 작물당 여러 덩이.
    # 작물 필터 없음 — crop_name 은 한글 표준이름, 저쪽이 crops.crop_id 를 찾되 못 찾아도 넣는다
    "crop_guides.csv": ["crop_name", "cultivation_type", "section", "topic",
                        "body", "source_file", "source_loc"],
}


# 근거 벌에 덧붙이는 칸. 저쪽으로 넘어가지 않는다
덧칸 = {
    # confirmed 가 둘이다 — 온도(§B-2)와 관리노력(§H)의 확인 여부가 다르다
    "crops.csv": ["confirmed", "difficulty_confirmed", "source"],
    "crop_variants.csv": ["숙기원문", "품종수", "작형", "confirmed", "source"],
    "crop_stages.csv": ["작형", "시작중앙일", "종료중앙일", "source"],
    "crop_disaster_rules.csv": ["실린호", "원본수", "출처들", "조건원문", "source"],
    # 근거 벌에만: 숙기를 어디서 읽었는지, 첨부가 무엇이었는지
    "varieties.csv": ["숙기근거", "첨부파일", "source"],
    "crop_guides.csv": [],          # 출처가 계약 안(source_file·source_loc)에 있다. 근거 벌에 더할 것이 없다
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
# 역산 결과 — gdd_backfill.py 가 만든 out/gdd.csv
# ─────────────────────────────────────────────────────────────────────

def gdd목표():
    """{작물: {gdd_target, 편차, 근거}}. out/gdd.csv 를 작물 단위로 접는다.

    ⚠ 한 작물에 여러 줄이 있다(작형·관측소). **평균을 쓴다.**
      편차가 크면 근거 벌에 남겨 나중에 볼 수 있게 한다 —
      벼 19% · 무 28% · 양파 39% 가 그렇다(확인필요.md).

    ⚠ 파일이 없으면 **조용히 빈 값을 내지 않고 알린다.** gdd_target 이 비면
      저쪽 적재가 NOT NULL 로 깨지는데, 원인이 "역산을 안 돌렸다" 인지
      "역산이 실패했다" 인지 구분이 안 된다.
    """
    경로 = OUT / "gdd.csv"
    if not 경로.exists():
        print(f"  ⚠ {경로.name} 이 없습니다 — python pipeline/gdd_backfill.py 를 먼저 돌리세요")
        return {}

    묶음 = {}
    for r in 읽기(경로):
        묶음.setdefault(r["작물"], []).append((r["관측소"], int(r["gdd"])))

    out = {}
    for 작물, 것들 in 묶음.items():
        값 = [g for _, g in 것들]
        out[작물] = {
            "gdd_target": round(sum(값) / len(값)),
            "편차": round((max(값) - min(값)) / max(값) * 100) if len(값) > 1 else 0,
            "근거": " · ".join(f"{s} {g}" for s, g in 것들),
        }
    return out

# ─────────────────────────────────────────────────────────────────────
# crops — 확정표 §B-2 가 그대로 들어간다
# ─────────────────────────────────────────────────────────────────────

def crops(온도표, 관리표, 작물들):
    """원본에 나온 작물 전부. base_temp·upper_temp 는 §B-2, difficulty 는 §H 채택값이다.

    ★ 2026-09-16 — **확정표에 줄이 있는 작물만 내보내던 것을 그만뒀다.**
      예전에는 §B-2 의 16줄이 곧 crops.csv 였다. 전체 작물로 방침이 바뀌면서
      **원본에 나온 작물이 전부 한 줄씩** 나온다. 확정표에 값이 없으면
      base_temp·upper_temp 가 빈 채로 나간다 — 그 작물은 GDD 를 못 쌓는다는 뜻이고,
      그게 사실이다. 억지로 채우지 않는다.

    ⚠ 그래서 `confirmed` 가 빈 행이 대부분이 된다. 값이 없는 것과 확인 안 된 것을
      가르려면 `source` 를 본다 — 확정표에서 온 행만 '확정표 §B-2' 라고 적힌다.

    ⚠ `difficulty` 는 확정표 어디에도 없다. 비워 둔다(저쪽 ORM 도 nullable).
      보도자료의 '재배하기 쉬운/보통/어려운' 은 §H 표를 풀어 쓰며 만든 표현이고
      원본 43쪽 어디에도 없다. 지어내면 "이 값 어디서 났냐" 에 답할 수 없다.

    ⚠ `difficulty` 가 빈 작물이 있다(§H 에 줄이 없는 것). 그것도 비워 둔다 —
      저쪽 ORM 이 nullable 이고, 억지로 채우면 §H 의 confirmed 표시가 무의미해진다.

    ⚠ **confirmed 가 두 표에서 따로 온다.** §B-2 의 온도 confirmed 와 §H 의
      difficulty confirmed 는 다른 값이다. 근거 벌에 둘 다 남긴다 —
      하나로 뭉치면 어느 값이 확인된 것인지 알 수 없게 된다.
    """
    행들 = []
    떠도는값 = sorted(set(온도표) - set(작물들))
    if 떠도는값:
        print(f"  ⚠ 확정표에 값이 있는데 원본에 안 나온 작물: {' · '.join(떠도는값)}")
    for 작물 in sorted(set(작물들) | set(온도표)):
        v = 온도표.get(작물)
        m = 관리표.get(작물)
        출처 = [x for x in ("확정표 §B-2" if v else "", "§H" if m else "") if x]
        행들.append({
            "name": 작물,
            "base_temp": (f"{v['base_temp']:.1f}"
                          if v and v["base_temp"] is not None else ""),
            "upper_temp": (f"{v['upper_temp']:.1f}"
                           if v and v["upper_temp"] is not None else ""),
            "difficulty": m["difficulty"] if m else "",
            "confirmed": v["confirmed"] if v else "",
            "difficulty_confirmed": m["confirmed"] if m else "",
            "source": " + ".join(출처) or "농사로 원본 (계산 상수 없음)",
        })
    return sorted(행들, key=lambda r: r["name"])


# ─────────────────────────────────────────────────────────────────────
# 작형 — 확정표 §A 에 없는 작물은 첨부 작형표에서 만든다
# ─────────────────────────────────────────────────────────────────────
# §A 는 사람이 손으로 적는 표라 16작물뿐이다. 전체 작물로 바뀌면서 그 표만으로는
# 나머지 140여 작물의 파종일·재배일수가 안 나온다. **자료에 있다** —
# 농작업일정 첨부의 작형표가 씨뿌림·아주심기·수확기를 순(旬)으로 적어둔다.
#
#     가지 | 촉성재배 | 씨뿌림 6.상~6.하 | 아주심기 8.하~9.상 | 수확 10.상~이듬해 6.하
#
# ⚠ **§A 가 있으면 §A 가 이긴다.** 확정표가 정본이라는 규칙 그대로다.
#   여기서 만든 줄은 §A 에 그 작물이 아예 없을 때만 쓴다.

_순쌍 = re.compile(r"(?:(\d{1,2})\s*월\s*)?([상중하])순?")


def _순들(글):
    """'12월 상순~1월 하순' → [(12,'상'), (1,'하')]. 달이 생략되면 앞의 달을 잇는다.

    ⚠ '2월 상~중순' 처럼 달을 한 번만 적는 꼴이 많다. 달을 기억해 두지 않으면
      뒤쪽 순이 통째로 빠져 재배일수가 짧게 나온다.
    """
    out, 달 = [], None
    for m in _순쌍.finditer(글 or ""):
        if m.group(1):
            달 = int(m.group(1))
        if 달 is None:
            continue
        out.append((달, m.group(2)))
    return out


def _작형_일정(일정행들, 있는작물):
    """작형표조차 없는 작물 — **생육과정 일정 그 자체**에서 파종일·재배일수를 만든다.

    ⚠ 첨부 작형표는 38작물에만 있다. 그것만으로 끊으면 나머지 100여 작물이
      crop_stages 에서 통째로 빠진다 — 일정은 있는데 단계가 안 나오는 꼴이다.

    ⚠ 작형은 정보구분 꼬리에서 온다. 꼬리가 여럿이면 **행이 가장 많은 꼬리**를 쓴다.
      첫 꼬리를 쓰면 시설 작형이 대표가 되는 작물이 생긴다.
      꼬리가 없으면 작형을 비운다 — `_작형맞나` 가 꼬리 없는 행만 받게 된다.
    """
    묶 = {}
    for r in 일정행들:
        if not (r.get("정보구분") or "").startswith("생육과정"):
            continue
        작물 = 표준작물(r.get("작물"))
        if not 작물 or 작물 in 있는작물:
            continue
        # ⚠ 작형이 `정보구분` 꼬리에만 있는 문서와 `작형` 칸에만 있는 문서가 둘 다 있다.
        #   꼬리만 보면 피망이 샌다 — 꼬리가 없어 '기본' 이 되는데 `작형` 칸에는
        #   '촉성재배' 가 적혀 있다(2026-09-18). 둘 다 보고 있는 쪽을 쓴다.
        꼬리 = (r.get("정보구분") or "").split(" - ", 1)
        작형이름 = (꼬리[1].strip() if len(꼬리) > 1 else "") or (r.get("작형") or "").strip()
        묶.setdefault((작물, 작형이름), []).append(r)

    큰것 = {}
    for (작물, 작형), 행 in 묶.items():
        앞 = 큰것.get(작물)
        if 앞 is None or len(행) > len(앞[1]):
            큰것[작물] = (작형, 행)

    out = []
    for 작물, (작형, 행) in 큰것.items():
        시작들 = [r.get("시작중앙일") for r in 행
                 if any(w in (r.get("작업명") or "") for w in 시작낱말)
                 and r.get("시작중앙일")]
        날들 = [r.get("시작중앙일") for r in 행 if r.get("시작중앙일")]
        파종일 = min(시작들) if 시작들 else (min(날들) if 날들 else "")
        if not 파종일:
            continue
        끝들 = [_상대일(r.get("종료중앙일") or r.get("시작중앙일"), 파종일) for r in 행]
        끝들 = [d for d in 끝들 if d != 999]
        out.append({
            "작물": 작물, "작물키": f"{작물}_{작형 or '기본'}", "작형": 작형,
            "지역": "", "관측소": [],
            "파종일": 파종일, "파종방법": "", "파종시작": "", "파종끝": "",
            "일수": max(끝들) if 끝들 else "",
            "출처": "농작업일정 생육과정 일정에서 역산",
        })
    return out


def _작형_자료(일정행들, 있는작물):
    """첨부 작형표 행 → §A 와 같은 꼴. 확정표에 없는 작물만 만든다."""
    out, 본것 = [], set()
    for r in 일정행들:
        작물 = 표준작물(r.get("작물"))
        if not 작물 or 작물 in 있는작물:
            continue
        심기 = (r.get("씨뿌림") or "").strip() or (r.get("아주심기") or "").strip()
        거두기 = (r.get("수확기") or "").strip() or (r.get("성출하기") or "").strip()
        심기순, 거두기순 = _순들(심기), _순들(거두기)
        if not 심기순 or not 거두기순:
            continue
        작형 = re.sub(r"\s+", " ", (r.get("작형") or "").strip()) or "기본"
        키 = f"{작물}_{작형}"
        if 키 in 본것:
            continue                      # 같은 작형이 호마다 되풀이된다. 첫 줄만
        본것.add(키)
        파종일 = middle_day(*심기순[0])
        끝 = era_edge(*거두기순[-1], last=True)
        out.append({
            "작물": 작물, "작물키": 키, "작형": 작형,
            "지역": "", "관측소": [],
            "파종일": 파종일,
            "파종방법": "씨뿌림" if (r.get("씨뿌림") or "").strip() else "아주심기",
            "파종시작": era_edge(*심기순[0]),
            "파종끝": era_edge(*심기순[-1], last=True),
            "일수": _사이일수(파종일, 끝),
            "출처": f"농작업일정 작형표 {r.get('출처파일', '')}",
        })
    return out

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


def crop_variants(작물들, 작형표, 접기, 수박표, 분할작물, 품종들):
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

    for 작물 in sorted(작물들):
        기본 = 대표.get(작물)
        일수 = int(기본["일수"]) if 기본 and 기본["일수"] else ""
        작형이름 = (기본 or {}).get("작형", "")
        # 파종 창은 days_to_harvest 와 **같은 대표 작형**에서 나온다.
        # 다른 작형에서 가져오면 "봄에 심어 가을 일수만큼 키운다" 가 된다
        창 = {
            "sow_method": (기본 or {}).get("파종방법", ""),
            "sow_from": (기본 or {}).get("파종시작", ""),
            "sow_to": (기본 or {}).get("파종끝", ""),
        }

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
                    **창,
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
                    **창,
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
            **창,
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


# 줄글로 넘길 구분. 품종요약서·품종주요특성은 카탈로그라 뺀다 —
# 넣으면 6,616행이 재배법 1,231행을 덮어 검색이 카탈로그로 쏠린다
문서구분 = ("재배법", "기상재해대책", "생리적특성")

# 병합 후 이 길이 미만이면 버린다. 제목만 남은 껍데기다
최소길이 = 40


def crop_docs(본문행들):
    """
    mid_text 파편을 '작물 × 작형 × 구분 × 절' 로 묶어 문서 행으로 만든다.

    _안내찾기 와 나누는 이유:
        저쪽은 stage_name 에 맞는 덩이 **하나** 를 고른다(1:1). 짝이 없는
        머리글(관리·물주기·병해충 방제)은 버려진다.
        여기는 전부 넘긴다(1:N). 고를 일이 없으니 어휘 불일치 문제도 없다.

    자르지 않는 이유:
        청킹은 Safe-farm 의 app/knowledge/chunker.py 가 CHUNK_SIZE=480 토큰으로
        한다. 양쪽이 각자 자르면 경계가 갈려 같은 기준으로 비교할 수 없게 된다.
        그래서 5,663자짜리도 그대로 넘긴다 — `최대=400` 을 여기 두지 않는다.
    """
    묶 = {}
    for r in 본문행들:
        if r.get("구분") not in 문서구분:
            continue
        작물 = 표준작물(r.get("작물"))
        글 = (r.get("본문") or "").strip()
        if not 작물 or not 글:
            continue

        # 원문이 작물명에 작형을 섞어 둔다: '고추(보통재배)'
        원작물 = r.get("작물") or ""
        작형 = 원작물[원작물.find("(") + 1 : 원작물.rfind(")")] if "(" in 원작물 else ""

        키 = (작물, 작형, r["구분"], r.get("절", ""))
        칸 = 묶.setdefault(키, {"조각": [], "topic": "",
                               "file": r.get("출처파일", ""), "loc": r.get("위치", "")})

        # 머리글 판정은 _안내모으기 와 같은 규칙을 쓴다 — 두 벌로 두면 갈린다
        if not 칸["topic"] and ":" not in 글 and len(글) <= 14:
            칸["topic"] = 글
        else:
            칸["조각"].append(글)

    행들 = []
    for (작물, 작형, 구분, 절), v in 묶.items():
        body = " / ".join(v["조각"])
        if len(body) < 최소길이:
            continue
        행들.append({
            "crop_name": 작물,
            "cultivation_type": 작형,
            "section": 구분,
            "topic": v["topic"] or 절 or 구분,
            "body": body,
            "source_file": v["file"],
            "source_loc": v["loc"],
        })
    return 행들


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

def _기간안(중앙일, 파종일, 일수, 여유=20):
    """단계 시작일이 그 작형의 재배 기간 안인가.

    ⚠ **작업명으로는 작형을 못 가른다.** 봄배추 '결구기'(4월)와 가을배추
      '아주심기, 웃거름'(8월)은 이름이 달라 아래 '본이름' 검사를 둘 다 통과한다.
      실제로 배추가 7단계가 됐다 — 봄 5단계 + 가을 2단계가 한 줄기로 붙었다.
      §A 에 파종일이 생겼으니(2026-09-16) 날짜로 가른다.

    ⚠ _상대일 은 **음수를 한 해 뒤로 감는다**(월동작물 때문에). 그래서 파종 전
      20일은 0~20 이 아니라 352~372 로 온다. 양쪽을 다 받아야 첫 단계가 안 잘린다.

    여유를 두는 까닭: 농작업일정은 순(旬) 단위라 중앙일이 확정표 파종일과
    최대 한 순(10일) 어긋난다. 앞뒤로 20일 열어 첫·끝 단계를 살린다.
    """
    d = _상대일(중앙일, 파종일)
    if d is None:
        return False
    return d <= 일수 + 여유 or d >= 12 * 31 - 여유

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
    
    # 작물 하나에 작형이 여럿이다(배추 봄·가을·고랭지). 첫 줄로 고정하지 않는다 —
    # raw XML 의 작형 이름이 첨부 표와 어긋나는 것이 있어서, §A 첫 줄을 쓰면
    # 단계가 두 개밖에 안 잡힌다(배추 '봄배추' 가 실은 시설재배 시기다).
    # 아래 ②에서 작형마다 돌려보고 **가장 많이 잡히는 것**을 쓴다.
    후보 = {}
    for x in 작형표:
        후보.setdefault(x["작물"], []).append(x)
    확정 = {c: v[0] for c, v in 후보.items()}   # _작형맞나 용 대표
    문서 = {}
    for r in 일정행들:
        if not (r.get("정보구분") or "").startswith("생육과정"):
            continue
        작물 = 표준작물(r.get("작물"))
        if not 작물:
            continue
        if not _작형맞나(r.get("정보구분"), (확정.get(작물) or {}).get("작형")):
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
        if not 작물 or (r.get("작물") or "") != 문서.get(작물):
            continue
        if not _작형맞나(r.get("정보구분"), (확정.get(작물) or {}).get("작형")):
            continue
        이름 = (r.get("작업명") or "").strip()
        if "▶" in 이름 or not any(w in 이름 for w in 단계낱말):
            continue                      # 표시행 · '김매기, 물주기' 같은 할 일
        # 작형마다 따로 모은다. 어느 것을 쓸지는 다 모은 뒤에 고른다
        for a in 후보.get(작물, []):
            if not _기간안(r.get("시작중앙일"), a["파종일"], a["일수"]):
                continue
            칸 = 덩이별.setdefault(작물, {}).setdefault(
                a["작물키"], {"행": [], "본이름": set(), "작형": a["작형"]}
            )
            if 이름 in 칸["본이름"]:
                continue                  # 같은 작업명의 두 번째 = 다른 해의 같은 작업
            칸["본이름"].add(이름)
            칸["행"].append(r)

    # ③ 작물마다 **단계가 가장 많이 잡힌 작형**을 쓴다.
    #    같으면 §A 에서 앞선 작형이 이긴다 — 주작형을 앞에 적어 두면 그게 뽑힌다
    차례 = {x["작물키"]: i for i, x in enumerate(작형표)}
    덩이별 = {
        작물: max(v.values(), key=lambda k: (len(k["행"]), -차례.get(k.get("작물키", ""), 0)))
        for 작물, v in 덩이별.items()
    }

    숙기별 = {}
    for v in variants:
        숙기별.setdefault(v["crop_name"], []).append(v["maturity_type"])

    행들 = []
    버린단계 = []
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

        # ⚠ **수확이 한가운데 오면 그 작물의 단계를 통째로 버린다.**
        #   작형 여럿이 한 줄기로 붙었다는 자국이다 —
        #     당근  봄재배 씨뿌림 → … → 수확 → 가을재배 씨뿌림
        #     갓    씨뿌림 → 수확 → 어린 모 시기(유묘기)
        #   순서를 손으로 고칠 수 없으니(어느 단계가 어느 작형인지 자료에 없다)
        #   **비우는 쪽이 옳다.** 단계가 없는 숙기는 verify·master_seed 둘 다
        #   정상으로 본다 — "농작업일정에 생육과정이 실린 작물만 단계가 나온다".
        if not cropping.수확이_마지막인가([n for n, _ in 본]):
            버린단계.append(작물)
            continue

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
    if 버린단계:
        print(f"  · 단계를 비운 작물 {len(버린단계)}개 — 수확이 마지막이 아니다"
              f" (작형 여럿이 붙은 자국): {' · '.join(sorted(버린단계)[:6])}"
              + (" …" if len(버린단계) > 6 else ""))
    return 행들

def 구간채우기(단계행들, variants, 작형표, 온도표):
    """crop_stages 의 gdd_from·gdd_to 를 채운다.

    단계 사이 기간을 평년 기온으로 적산해 **비중**을 내고, 그 비중대로
    gdd_target 을 나눈다.

    ⚠ 적산값을 그대로 쓰지 않는다. stage_problems 가 '마지막 gdd_to ==
      gdd_target' 을 요구하는데, 단계 시작일이 파종일과 어긋나서(배추는
      아주심기 08-25 인데 첫 단계가 08-05) 총합이 안 맞는다.

    ⚠ 첫 단계 gdd_from 은 0 으로 못박는다. 같은 까닭이다.
    """
    from gdd_backfill import 평년읽기, 전국평균, 적산, 전국   # noqa: PLC0415

    표, 차례 = 평년읽기()
    표[전국] = 전국평균(표, 차례)
    # 역산이 안 된 작물은 gdd_target 이 빈 문자열이다. 키에서 아예 빼서
    # 아래 `if not 목표값` 이 건너뛰게 한다 — int('') 는 터진다
    목표 = {}
    for v in variants:
        try:
            목표[v["crop_name"]] = int(v["gdd_target"])
        except (TypeError, ValueError):
            pass
    관측 = {x["작물"]: (x["관측소"] or [전국])[0] for x in 작형표}

    묶음 = {}
    for r in 단계행들:
        묶음.setdefault((r["crop_name"], r["maturity_type"]), []).append(r)

    for (작물, _숙기), 것들 in 묶음.items():
        목표값 = 목표.get(작물)
        온도 = 온도표.get(작물)
        if not 목표값 or not 온도:
            continue
        것들.sort(key=lambda r: int(r["stage_order"]))
        일별 = 표[관측.get(작물, 전국)]

        # 단계 i 의 길이 = 그 단계 시작 ~ 다음 단계 시작. 마지막은 종료중앙일까지
        몫 = []
        for i, r in enumerate(것들):
            시작 = r.get("시작중앙일") or ""
            끝 = 것들[i + 1].get("시작중앙일") if i + 1 < len(것들) else r.get("종료중앙일")
            일 = _사이일수(시작, 끝)
            몫.append(적산(일별, 차례, 시작, 일, 온도["base_temp"], 온도["upper_temp"])
                     if 시작 and 일 > 0 else 0.0)

        전체 = sum(몫)
        if 전체 <= 0:
            continue
        누적 = 0.0
        for i, r in enumerate(것들):
            r["gdd_from"] = round(목표값 * 누적 / 전체)
            누적 += 몫[i]
            r["gdd_to"] = round(목표값 * 누적 / 전체)
        것들[0]["gdd_from"] = 0
        것들[-1]["gdd_to"] = 목표값
    # 폭이 0인 단계는 버린다. 같은 날짜에 두 작업이 적힌 것이라 GDD 로는
    # 구분되지 않는다 — 배추의 '어린 모 시기' 와 '씨뿌림' 이 둘 다 08-05 다.
    # 저쪽 ck_crop_stages_gdd_range 가 gdd_from < gdd_to 를 요구한다.
    남길 = [r for r in 단계행들 if r.get("gdd_from") != r.get("gdd_to")]

    # stage_order 를 1부터 다시 매긴다. 구멍이 나면 stage_problems 가
    # '1부터 연속이 아니다' 로 잡는다
    다시 = {}
    for r in 남길:
        다시.setdefault((r["crop_name"], r["maturity_type"]), []).append(r)
    for 것들 in 다시.values():
        것들.sort(key=lambda r: int(r["stage_order"]))
        for i, r in enumerate(것들, 1):
            r["stage_order"] = i
    return 남길

def _사이일수(a, b):
    """'08-05' 와 '10-25' 사이 날수. 해를 넘겨도 센다(_상대일 이 감아 준다)."""
    d = _상대일(b, a)
    return d if d is not None else 0

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


# ─────────────────────────────────────────────────────────────────────
# varieties — 품종 카탈로그. 작물 필터 없음
# ─────────────────────────────────────────────────────────────────────

본문폴더 = HERE.parent / "원본" / "품종정보" / "본문"

# 첨부를 글자로 펼 때 섞여 들어오는 것. 값이 아니므로 지워도 잃을 것이 없다.
# ⚠ feature/clean_text.py 는 HTML 엔티티·가짜 한자·SPAN 만 안다. 이건 다른 종류다
_찌꺼기 = re.compile(
    r"^\s*(===== p\.\d+ =====|- \d+ -|그림입니다\.?|사각형입니다\.?|원본 그림의 (이름|크기): .*)\s*$"
)

_한글 = re.compile(r"[가-힣]")

# 줄에서 한글이 이 비율 미만이면 표가 한 줄로 펴진 것으로 본다.
# 0.2 인 근거: 품종 색인 실측에서 한글 10% 미만 292조각·10~30% 1,745조각이 전부 숫자표였고
# ('0.011.72 ± 0.060.09 ± 0.00Glucoerucin...'), 30% 이상부터 문장이 섞여 나왔다.
# 더 올리면 '25℃ 에서 10일' 같은 짧은 수치 문장이 같이 날아간다
_한글하한 = 0.2


def clean_body(text):
    """첨부 본문에서 사람이 읽을 줄만 남긴다. 자르지 않는다 — 청킹은 저쪽 chunker.py 몫이다.

    버리는 것 넷:
      찌꺼기       쪽 표시·그림 자리표시자. _찌꺼기
      표 조각      6자 이하 줄. 표를 펴면 칸 하나가 한 줄이 된다 ('93.8' '수미' '편타원')
                  문장은 6자 안에 끝나지 않으므로 잃는 것이 없다
      펴진 표 줄   한글이 _한글하한 미만인 줄. 6자 필터를 빠져나간 표가 여기 걸린다
      빈 줄

    이어 붙이는 것: PDF 는 40자쯤에서 줄을 강제로 바꾼다 ('수량 감소가 크' / '다.').
    앞 줄이 문장 끝(다. 음. 함. 임. 됨.)이 아니면 다음 줄을 공백 없이 잇는다
    """
    줄들 = []
    for 줄 in text.splitlines():
        s = 줄.strip()
        if not s or _찌꺼기.match(s) or len(s) <= 6:
            continue
        # 표가 한 줄로 펴진 것. 숫자·기호만 있는 줄은 임베딩하면 노이즈다
        if len(_한글.findall(s)) / len(s) < _한글하한:
            continue
        if 줄들 and not re.search(r"[.。]$|[다음함임됨]\s*$", 줄들[-1]):
            줄들[-1] += s          # 강제 줄바꿈 복원
        else:
            줄들.append(s)
    return "\n".join(줄들)


def varieties(품종들, 접기):
    """out/원본별/품종정보/varieties.csv + 본문 txt → 계약 행.

    ⚠ 작물을 거르지 않는다. 43작물 2,599품종 전부다.
    ⚠ maturity_type 은 접기 규칙에 있는 말만 채운다. 없으면 빈 칸 — 저쪽이 crop_variants 를
      찾을 때 "그 작물의 유일한 행" 규칙으로 푼다. 여기서 MID 를 넣으면 품종 속성과
      crop_variants 규칙이 섞인다
    """
    행들 = []
    for r in 품종들:
        # ⚠ '논벼 > 일반벼' — **1단이 작물, 2단이 세부 분류**다. 반대로 읽으면
        #   crop_name 에 '일반벼' '스프레이' 가 앉아 crops 와 영영 안 이어진다.
        #   세부 분류가 없는 작물도 많다('고구마') — 2,599 중 1,741행이 그렇다. 버리지 않는다
        작물, _, 세부 = (r.get("작물원문") or "").partition(">")
        작물 = 작물.strip()
        번호 = (r.get("cntntsNo") or "").strip()
        if not 번호 or not 작물:
            continue
        # '논벼' → '벼'. 예외표에 없으면 제 이름 그대로 (crops.py 는 더 이상 거르지 않는다)
        표준 = CROP_ALIAS.get(nospace(작물), 작물)
        숙기 = (r.get("숙기") or "").strip()
        본문 = ""
        후보 = list(본문폴더.glob(f"*/*/{번호}_*.txt"))
        if 후보:
            본문 = clean_body(후보[0].read_text(encoding="utf-8", errors="replace"))
        행들.append({
            "variety_no": 번호,
            "crop_group": 후보[0].parent.parent.name if 후보 else "",   # 본문 경로의 '식량작물'·'채소'
            "crop_name": 표준,
            "variety_group": 세부.strip(),      # '일반벼' '장류용콩'. 없으면 빈 칸
            "name": (r.get("품종명") or "").strip(),
            "maturity_raw": 숙기,
            "maturity_type": 접기.get(숙기, "") if 숙기 else "",
            "use": (r.get("용도") or "").strip(),
            "zone": (r.get("지대") or "").strip(),
            "bred_year": (r.get("육성년도") or "").strip(),
            "breeder": (r.get("육성기관") or "").strip(),
            "summary": (r.get("주요특성") or "").strip(),
            "body": 본문,
            "source_file": 후보[0].name if 후보 else "",
            # 근거 벌
            "숙기근거": r.get("숙기근거") or "",
            "첨부파일": r.get("첨부파일") or "",
            "source": "품종정보 varieties.csv" + (" + 첨부 본문" if 본문 else ""),
        })
    return 행들


def main():
    print("build — 확정표 + 중간 CSV → 스키마 3종\n")
    try:
        온도표 = spec.온도()
        관리표 = spec.관리노력()
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

    # ★ 작물 목록은 **자료가 정한다.** 예전에는 확정표 §B-2 의 16줄이 곧 작물 목록이었다.
    #   등록표(crops.py)가 화이트리스트를 그만두면서 여기도 같이 풀었다.
    작물들 = {표준작물(r.get("작물")) for r in 일정} - {""}
    if not 작물들:
        작물들 = set(온도표)

    # 확정표 §A 에 없는 작물의 작형·파종일·재배일수는 첨부 작형표에서 만든다
    # ⚠ ②③ 만 거른다. §A 는 사람이 고른 정본이라 손대지 않는다(cropping.py 맨 위)
    뺀까닭 = {}
    보탠작형 = cropping.거르기(_작형_자료(일정, {r["작물"] for r in 작형표}), 뺀까닭)
    작형표 = 작형표 + 보탠작형
    # 작형표조차 없는 작물은 일정 자체에서 역산한다. 세 층의 차례가 곧 미더움의 차례다
    역산작형 = cropping.거르기(_작형_일정(일정, {r["작물"] for r in 작형표}), 뺀까닭)
    작형표 = 작형표 + 역산작형
    print(f"  · 작형 — 확정표 §A {len(작형표) - len(보탠작형) - len(역산작형)}행"
          f" + 첨부 작형표 {len(보탠작형)}행 + 일정 역산 {len(역산작형)}행"
          f"   ({len({r['작물'] for r in 작형표})}작물)")
    if 뺀까닭:
        print(f"      뺀 작형 — 시설 {뺀까닭.get('시설', 0)}개"
              f" · {cropping.최대일수}일 이상 {뺀까닭.get('장기', 0)}개")

    c = crops(온도표, 관리표, 작물들)
    v = crop_variants(작물들, 작형표, 접기, 수박표, 분할작물, 품종들)
    # 역산값을 얹는다. crop_variants 안에서 채우지 않는 이유 —
    # gdd_target 은 작물 단위라 숙기별로 다르지 않은데, 그 함수는 숙기마다
    # 분기가 셋이라(수박 §D-3 · 3분할 · MID 한 행) 같은 줄을 세 번 쓰게 된다
    목표 = gdd목표()
    for r in v:
        t = 목표.get(r["crop_name"])
        if not t:
            continue
        r["gdd_target"] = t["gdd_target"]
        꼬리 = f" + 역산 {t['근거']}"
        if t["편차"] >= 15:
            꼬리 += f" (편차 {t['편차']}% — 확인필요.md)"
        r["source"] += 꼬리
        
    본문 = 읽기(OUT / "mid_text.csv") if (OUT / "mid_text.csv").exists() else []
    s = crop_stages(일정, v, 작형표, _안내모으기(본문))
    s = 구간채우기(s, v, 작형표, 온도표)

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
    # 품종들·접기 는 이 함수 위에서 이미 읽어 둔 값이다 (crop_variants 가 쓴다)
    내기("varieties.csv", varieties(품종들, 접기))
    내기("crop_guides.csv", crop_docs(본문))     # 본문 은 위에서 이미 읽었다

    if 제외셈:
        print("\n  · 경보로 안 넣은 규칙")
        for 종류, n in sorted(제외셈.items()):
            print(f"      {종류:10}{n:>4}행   {재해제외[종류]}")

    # ⚠ gdd_from 은 0 이 정상값이라 `not r["gdd_from"]` 로 세면 첫 단계가 늘 빈 것이 된다.
    #   빈 칸은 빈 문자열이므로 그것만 센다
    빈gdd = sum(1 for r in v if not r["gdd_target"])
    빈구간 = sum(1 for r in s if r["gdd_from"] == "" or r["gdd_to"] == "")
    if 빈gdd or 빈구간:
        print(f"\n⚠ gdd_target 이 빈 행 {빈gdd}/{len(v)} · gdd_from/to 가 빈 행 {빈구간}/{len(s)}")
        print("   일별 기온 역산이 있어야 찹니다(확정표 §C). 그 전까지는 넘기면 안 됩니다.")
    else:
        print(f"\ngdd_target {len(v)}행 · gdd 구간 {len(s)}행 전부 찼습니다")
    print("\n다음: python pipeline/verify.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
