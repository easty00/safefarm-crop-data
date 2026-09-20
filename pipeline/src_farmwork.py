# 농작업일정 에서 중간 CSV 를 뽑습니다.
#
#     python pipeline/src_farmwork.py
#     → pipeline/out/원본별/농작업일정/mid_*.csv
#
# farmWorkingPlanNew. raw 539 + 첨부 20.
#
# 여기서만 나오는 것 — 파종·수확 순(旬) 시기. 첨부에 없고 raw 응답에만 있다.
# 첨부 hwpx 의 표 172개가 여섯 종류로 일정하다 — 작형표·재배적특성·적산온도·대책표.
#
# ⚠ **접지 않고 날 행 그대로 쓴다.** 같은 표가 여러 원본에 실리므로
#   원본별로 접으면 근거 세기(실린호)가 갈린다. 접는 것은 extract.py 가 한 번만 한다.

import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent

#: 값 안에 섞여 오는 태그·실체참조. 원본/농작업일정/farmwork.py 의 `tidy` 와 같은 규칙이다.
#:
#: ⚠ **두 곳에 같은 규칙이 있다.** 저쪽은 API 로 받아 저장할 때, 이쪽은 저장된 raw 를
#:   다시 읽을 때다. 한쪽만 고치면 경로에 따라 값이 갈린다 — 실제로 그랬다.
_실체 = (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'))


def _태그없이(글):
    """`<br />` 같은 태그를 지우고 겹친 공백을 하나로."""
    글 = re.sub(r"<[^>]+>", " ", 글 or "")
    for a, b in _실체:
        글 = 글.replace(a, b)
    return " ".join(글.split())
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "feature"))

from common import (  # noqa: E402
    middle_day,
    sun_index,
    COLS, NUM, OUT, RAW, TEMP_RANGE, temp_kind, clear_read_cache, dump_raw, month_fix, nospace,
    read_doc, rows_out, set_out, temp_from_sentence, tidy, to_num,
)
from crops import RAW_NAMES, registry_report  # noqa: E402
from sections import parse_sections  # noqa: E402


# ─────────────────────────────────────────────────────────────────────
# 1. 농작업일정 raw — 작물 지도와 시기
# ─────────────────────────────────────────────────────────────────────

def crop_map():
    """cntntsNo → (작물명, 첨부파일명).

    ⚠ 실제 읽기와 별칭 잇기는 `crops.py` 가 한다. 여기서는 받아 쓰기만 한다.
      예전에는 이 함수 안에서 별칭을 이었는데, 그러면 농작업일정을 안 읽는
      다른 원본 스크립트에서는 그 이음이 없어 같은 이름이 원본마다 다르게 풀린다.

    ⚠ 등록했는데 원본에 없으면 그 작물은 통째로 빠진다. 조용히 빠지면 못 찾는다.
    """
    registry_report()
    out = dict(RAW_NAMES)
    없는첨부 = [nm for _no, (nm, fn) in out.items()
                if not (RAW / "농작업일정" / "첨부" / fn).exists()]
    if 없는첨부:
        print(f"  ⚠ 첨부 파일이 없는 작물 {len(없는첨부)}개: {', '.join(없는첨부)}")
        print("      raw 만으로는 온도·적산온도가 안 나옵니다")
    return out


def schedule_from_raw(cmap):
    """erajson_*.xml — 파종·수확 시기. 첨부에 없는 유일한 자료다.

    ⚠ 작업명이 작물마다 다르다. 정규식 하나로 못 잡는다.
        벼   "모내기때"      ← '이앙' 도 '심기' 도 없다
        무   "씨뿌림"        ← '씨뿌리' 로 찾으면 안 걸린다
        감자  "밭준비 및 파종"
      그래서 여기서는 **작업명을 가르지 않고 전부 담는다.** 고르는 것은 build 가 한다.
    """
    rows = []
    for no, (crop, _) in cmap.items():
        p = RAW / "농작업일정" / "raw" / f"erajson_{no}.xml"
        if not p.exists():
            continue
        for it in ET.parse(p).getroot().findall(".//item"):
            g = lambda t: (it.findtext(t) or "").strip()  # noqa: E731
            info = g("infoSeCodeNm")
            bm, b_next = month_fix(g("beginMon"))
            em, e_next = month_fix(g("endMon"))
            시작순번 = sun_index(g("beginMon"), g("beginEra"))
            종료순번 = sun_index(g("endMon"), g("endEra"))
            rows.append({
                "작물": crop, "cntntsNo": no,
                # 작형은 정보구분 꼬리에 붙는다 — "생육과정(주요농작업) - 노지재배"
                # ⚠ 꼬리라고 다 작형이 아니다. "예상되는 문제점 - 환경" 의 '환경' 은 작형이 아니다.
                #   그대로 받아 가지·토마토에 작형 '병'·'해충'·'환경' 이 생겼었다.
                #   머리가 생육과정일 때만 꼬리를 작형으로 본다.
                "작형": (info.split("-", 1)[1].strip()
                        if "-" in info and "생육과정" in info.split("-", 1)[0] else ""),
                "정보구분": info,
                "분류": g("kidofcomdtySeCodeNm"),
                # ⚠ **태그를 지운다.** `opertNm` 에 `<br />` 이 그대로 들어온다 —
                #   원본/농작업일정/farmwork.py 의 `tidy` 가 같은 까닭으로 있는데,
                #   이쪽(raw 를 다시 읽는 길)에는 없어 93건이 새고 있었다(2026-09-20).
                #   이 값은 crop_stages.stage_name 이 되어 **화면에 그대로 나가고**
                #   할 일 카드 제목도 이 글자로 만들어진다.
                "작업명": _태그없이(g("opertNm")),
                "시작월": bm, "시작순": g("beginEra"),
                "종료월": em, "종료순": g("endEra"),
                "종료이듬해": "Y" if e_next else "",
                "원본종료월": g("endMon"), "출처": "erajson",
                # ★ 순(旬)을 순번과 날짜로. 적산온도를 쌓으려면 날짜가 있어야 한다.
                #   ⚠ 원본 월(13~18 그대로)을 넘긴다. month_fix 로 고친 값을 넘기면
                #     이듬해 표시가 사라져 월동작물의 기간이 끊긴다.
                "시작순번": 시작순번, "종료순번": 종료순번,
                "지속순수": (종료순번 - 시작순번 + 1)
                            if isinstance(시작순번, int) and isinstance(종료순번, int)
                            and 종료순번 >= 시작순번 else "",
                "시작중앙일": middle_day(g("beginMon"), g("beginEra")),
                "종료중앙일": middle_day(g("endMon"), g("endEra")),
                "출처파일": p.name, "위치": "erajson",
            })
    return rows


def text_from_raw(cmap):
    """dtl_*.xml 의 재배법 HTML → 글자 + 온도.

    ⚠ 예전에는 글자만 담고 **온도를 캐지 않았다.**
      수박 base_temp 10℃ 의 원문이 여기 있는데 mid_temp 에 안 갔다.
          ❍ 생육온도 : 생육적온(25~30℃, 생육최저온도 10℃)
      첨부 표에는 적온 넷뿐이고 최저온도가 없다. 이 본문에만 있다.
      확정표 §B-2 는 수박 10 을 confirmed=Y 로 적어뒀는데 근거가 안 담겨 있었다.

    돌려주는 것 : (본문행, 온도행, 적산온도행)
    """
    rows, temp, sumt = [], [], []
    for no, (crop, _) in cmap.items():
        p = RAW / "농작업일정" / "raw" / f"dtl_{no}.xml"
        if not p.exists():
            continue
        for it in ET.parse(p).getroot().findall(".//item"):
            cn = it.findtext("cn") or ""
            txt = re.sub(r"<[^>]+>", "\n", cn)
            txt = re.sub(r"&nbsp;?", " ", txt)
            for i, sec in enumerate(parse_sections(txt, {"작물": crop, "구분": "재배법"})):
                본문 = tidy(sec.get("내용", ""))
                rows.append({
                    **sec, "본문": 본문[:1500],
                    "출처파일": p.name, "위치": f"절{i}",
                })
                if "℃" in 본문:
                    t, s = temp_from_sentence(본문, crop, p.name, f"절{i}")
                    temp += t
                    sumt += s
    return rows, temp, sumt


def from_farmwork_attach(cmap):
    """첨부 hwpx 21개. 표 172개가 여섯 종류로 일정하다."""
    sched, temp, sumt, rule, text, table = [], [], [], [], [], []
    att = RAW / "농작업일정" / "첨부"
    byfile = {f: c for _no, (c, f) in cmap.items() if f}

    for p in sorted(att.iterdir()):
        if not p.is_file():
            continue
        crop = byfile.get(p.name)
        if crop is None:
            # 파일명이 목록과 다를 때가 있다. 이름 앞부분으로 견준다
            stem = re.sub(r"\s*농작업\s*일정.*$", "", p.stem)
            crop = next((c for _, (c, _f) in cmap.items() if nospace(c).startswith(nospace(stem))), None)
        if crop is None:
            print(f"  ! 작물 미상: {p.name}", file=sys.stderr)
            continue

        try:
            _, grids = read_doc(p)
        except Exception as e:  # noqa: BLE001
            print(f"  ! 표 읽기 실패 {p.name}: {e}", file=sys.stderr)
            grids = []

        for gi, g in enumerate(grids):
            head = [nospace(c) for c in g[0]]
            flat = nospace("".join("".join(r) for r in g))

            # 표 원문은 통째로 남긴다. 값이 이상할 때 여기로 돌아온다
            for ri, row in enumerate(g):
                table.append({
                    "작물": crop, "출처파일": p.name, "위치": f"표{gi}/행{ri}",
                    "칸수": len(row), "내용": " ¦ ".join(c.replace("\n", "/") for c in row)[:600],
                })

            # ① 작형별 출하시기 — 작형 이름이 여기 있다
            #    ⚠ 머리글이 작물마다 다르다. 하나로 가정하면 절반이 빠진다.
            #        "작 형 ¦ 씨뿌림 ¦ 아주심기 ¦ 수 확 기 ¦ 성출하기"
            #        "재배 형태 ¦ 재배 지역 ¦ 재배 기간"
            #        "작 형 ¦ 육묘일수 ¦ 아주심을 모종의 크기"      ← 고추. '수확' 이 없다
            #        "재배유형 ¦ 재배방법 ¦ 재배지역 ¦ 파종기 …"    ← 옥수수. '작형' 도 없다
            #    벼는 작형표 자체가 없다(논벼는 작형이 하나라 표를 안 만든다).
            #
            #    ⚠ 자리로 맞추면 안 된다. 칸 차례가 작물마다 다르다.
            #        당근 "작형 ¦ 씨뿌림 ¦ 수확기 ¦ 주산지"
            #        → 3번 칸을 수확기로 읽으면 '남해안'(주산지)이 수확기가 된다. 실제로 그랬다.
            #      머리글 이름으로 칸을 찾는다.
            #
            #    ⚠ 머리글이 두 줄인 표가 있다(감자 "재배 형태 ¦ 재배 지역 ¦ 재배 기간 ¦ 재배 기간"
            #      + "… ¦ 파종 시기 ¦ 수확 시기"). 첫 칸이 되풀이되는 것이 표시다.
            #      아랫줄을 데이터로 읽으면 작형 '재배 형태' 같은 행이 생긴다.
            #
            #    ⚠ 머리글에 '작형' 이 있다고 작형표가 아니다.
            #      감자 표0 은 "작형 ¦ 3요소량 ¦ 시비량" 짜리 **비료표**다.
            #      시기 칸이 하나도 없으면 작형표가 아니다.
            if (head and any(k in head[0] for k in ("작형", "재배형태", "재배유형"))
                    and len(g) > 1):
                hd = [tidy(c) for c in g[0]]
                start = 1
                if len(g) > 2 and tidy(g[1][0]) == hd[0]:
                    hd = [f"{tidy(a)}{tidy(b)}" if tidy(a) != tidy(b) else tidy(a)
                          for a, b in zip(g[0], list(g[1]) + [""] * len(g[0]))]
                    start = 2

                def col(*words, _hd=hd):
                    for j, h in enumerate(_hd):
                        if j and any(w in nospace(h) for w in words):
                            return j
                    return -1

                c씨, c아 = col("씨뿌림", "파종"), col("아주심", "정식")
                c수, c성 = col("수확"), col("성출하")
                if max(c씨, c아, c수, c성) < 0:
                    pass                      # 시기 칸이 없다 → 비료표 따위. 작형표가 아니다
                else:
                    def at(row, j):
                        return tidy(row[j]) if 0 <= j < len(row) else ""
                    for row in g[start:]:
                        if not row or not row[0].strip():
                            continue
                        sched.append({
                            "작물": crop, "작형": tidy(row[0]), "출처": "첨부작형표",
                            "씨뿌림": at(row, c씨), "아주심기": at(row, c아),
                            "수확기": at(row, c수), "성출하기": at(row, c성),
                            "출처파일": p.name, "위치": f"표{gi}",
                        })

            # ② 품종별 적산온도 (수박)
            if "적산온도" in flat and any("품" in h for h in head):
                for ri, row in enumerate(g[1:], 1):
                    if len(row) < 3 or not row[0].strip():
                        continue
                    sumt.append({
                        "작물": crop, "품종숙기": tidy(row[0]),
                        "일수": tidy(row[1]),
                        # ⚠ 표 쪽도 쉼표를 지운다. "1,200" 그대로 두면 build 에서 터진다
                        "적산온도": to_num(tidy(row[2])),
                        "구간": "착과 후", "출처파일": p.name, "위치": f"표{gi}/행{ri}",
                    })

            # ③ 재배적 특성표의 생육온도 행
            #    ⚠ 예전에는 종류를 '적온' 으로 박아뒀다. 그런데 이 행에 적온만 있는 게 아니다.
            #        마늘(잎마늘)  "생육온도 ¦ 잎 생육적온 ¦ 18~20℃ ¦ 생육 최저 ¦ 4℃"
            #      그래서 **마늘 base_temp 4℃ 의 원문 근거가 '적온' 으로 묻혀 있었다.**
            #      확정표 §B-2 는 마늘 4 를 confirmed=Y 로 적어뒀는데 파이프라인은 그 근거를
            #      안 담고 있었다 — "확보" 와 "반영" 이 어긋난 상태였다.
            #    항목 이름으로 종류를 정한다. 적온은 여전히 적온으로 담는다(버리지 않는다).
            for ri, row in enumerate(g):
                if not row or "생육온도" not in nospace(row[0]):
                    continue
                for ci in range(1, len(row) - 1, 2):
                    항목, 값 = tidy(row[ci]), tidy(row[ci + 1])
                    m = TEMP_RANGE.search(값)
                    if 항목 and m:
                        temp.append({
                            "작물": crop,
                            "종류": temp_kind(항목, False, False, "", 항목),
                            "항목": 항목,
                            "값최소": to_num(m.group(1)),
                            "값최대": to_num(m.group(2) or m.group(1)),
                            "단위": "℃", "원문": f"{항목} {값}",
                            "출처파일": p.name, "위치": f"표{gi}/행{ri}",
                        })

            # ③-b 최저 · 최적 · 최고 를 칸으로 나눈 표 (시금치)
            #        구 분 ¦ 최저온도(℃) ¦ 최적온도(℃) ¦ 최고온도(℃)
            #        발아  ¦ 4          ¦ 15~20      ¦ 30
            #        생육  ¦ 3~4        ¦ 15~20      ¦ 25
            #    ⚠ 칸에 ℃ 기호가 없다. 머리글에만 있다. 문장 규칙으로는 한 건도 안 잡힌다.
            #      시금치 base_temp 3~4 · upper_temp 25 가 여기서 나온다.
            if (len(g) > 1 and len(g[0]) >= 3
                    and any("최저온도" in nospace(c) for c in g[0])
                    and any("최고온도" in nospace(c) for c in g[0])):
                hd = [nospace(c) for c in g[0]]
                for ri, row in enumerate(g[1:], 1):
                    단계 = tidy(row[0]) if row else ""
                    if not 단계:
                        continue
                    for ci in range(1, len(row)):
                        이름 = hd[ci] if ci < len(hd) else ""
                        값 = tidy(row[ci])
                        m = re.match(rf"\s*({NUM})\s*(?:[~～∼-]\s*({NUM}))?\s*$", 값)
                        if not 이름 or not m:
                            continue
                        temp.append({
                            "작물": crop,
                            "종류": temp_kind(이름, False, False, "", 이름),
                            "항목": f"{단계} {이름}",
                            "값최소": to_num(m.group(1)),
                            "값최대": to_num(m.group(2) or m.group(1)),
                            "단위": "℃", "원문": f"{단계} ¦ {이름} ¦ {값}",
                            "출처파일": p.name, "위치": f"표{gi}/행{ri}/{ci}",
                        })

            # ④ 생리적특성 칸 — 문장형 온도가 여기 있다
            for ri, row in enumerate(g):
                if not row or "생리적특성" not in nospace(row[0]):
                    continue
                body = max(row[1:], key=len) if len(row) > 1 else ""
                _t, _s = temp_from_sentence(body, crop, p.name, f"표{gi}/행{ri}/생리적특성")
                temp += _t
                sumt += _s
                for si, sec in enumerate(
                    parse_sections(body, {"작물": crop, "구분": "생리적특성"})
                ):
                    if tidy(sec.get("내용", "")):
                        text.append({
                            **sec, "본문": tidy(sec["내용"])[:1000],
                            "출처파일": p.name, "위치": f"표{gi}/행{ri}/{si}",
                        })

            # ⑤ 기상재해·생리장해 대책표
            if head[:2] == ["항목", "내용"] or (head and "항" in head[0] and len(g) > 2):
                for ri, row in enumerate(g[1:], 1):
                    if len(row) < 2 or not row[0].strip():
                        continue
                    # ⚠ 서술문이라 지표·부등호·값이 안 나온다. mid_rule 은 규칙 표이므로
                    #   값 없는 행을 넣지 않는다. 본문 쪽(mid_text)으로 보낸다.
                    #   온도가 들어 있으면 문장에서 캐서 mid_temp 로도 보낸다.
                    항목, 내용 = tidy(row[0]), tidy(row[1])
                    text.append({
                        "작물": crop, "구분": "기상재해대책", "절": 항목,
                        "항목": "", "깊이": 3, "본문": 내용[:600],
                        "출처파일": p.name, "위치": f"표{gi}/행{ri}",
                    })
                    if "℃" in 내용:
                        _t, _s = temp_from_sentence(
                             내용, crop, p.name, f"표{gi}/행{ri}/대책")
                        temp += _t
                        sumt += _s
    return sched, temp, sumt, rule, text, table


def attach_body(cmap):
    """첨부 hwpx 의 **표 밖 서술**에서 온도를 캔다.

    ⚠ 예전에는 표와 '생리적특성' 칸만 읽었다. 그래서 이 문장이 통째로 빠졌다.
          ❍ 씨감자 싹은 5℃ 이상에서 자라기 시작함
      CLAUDE.md 가 "표만 읽으면 안 된다" 는 본보기로 드는 바로 그 문장이고,
      확정표 §B-2 가 감자 base_temp 5 를 confirmed=Y 로 적은 근거인데
      파이프라인에는 그 근거가 없었다. `안읽은것.md §4` 의 마지막 미완 항목이었다.

    ⚠ 재해예방정보 본문은 값이 없어 되돌렸지만 여기는 다르다.
      **농작업일정 첨부는 문서 하나가 작물 하나를 설명한다.** 작물을 헷갈릴 일이 없고
      본문도 21개 문서 합쳐 3,388줄뿐이다.

    ⚠ 읽기는 dump_raw 가 이미 했다. read_doc 캐시가 있어 값이 더 들지 않는다.
    """
    temp, sumt = [], []
    att = RAW / "농작업일정" / "첨부"
    if not att.exists():
        return temp, sumt
    byfile = {f: c for _no, (c, f) in cmap.items() if f}
    for p in sorted(att.iterdir()):
        if not p.is_file():
            continue
        crop = byfile.get(p.name)
        if crop is None:
            stem = re.sub(r"\s*농작업\s*일정.*$", "", p.stem)
            crop = next((c for _, (c, _f) in cmap.items()
                         if nospace(c).startswith(nospace(stem))), None)
        if crop is None:
            continue
        글, _표 = read_doc(p)
        for i, ln in enumerate(글.split("\n")):
            if "℃" not in ln:
                continue
            for 조각 in re.split(r"(?<=[.。])\s+|(?=[❍○ㅇ•▪*])", ln):
                조각 = tidy(조각)
                if "℃" not in 조각 or len(조각) < 8:
                    continue
                t, s = temp_from_sentence(조각, crop, p.name, f"본문줄{i}")
                temp += t
                sumt += s
    return temp, sumt


def 동해규칙(온도행들):
    """본문에서 캔 온도 중 **'얼어 죽는다'** 고 못 박은 것만 규칙으로 올린다.

        ※ 10℃ 이하에서 생육정지, -1.7℃ 이하에서 동사
                                  ↑ 이 절만 규칙이 된다

    ⚠ **'동해' 갈래만 올린다.** `단계별저온` 이나 `상한후보?` 까지 규칙으로 바꾸면
      뜻이 흐린 문장이 가짜 규칙이 된다. 실제로 이런 줄이 섞여 있다 —

        "35℃이하 유지(35℃ 이상에서는 수정률 감소)"   ← 관리 지침이지 저온 규칙이 아니다
        "10℃ 이하, 30℃ 이상"                      ← 무엇의 한계인지 줄에 안 적혀 있다

      그래서 문지기를 `common.FROST_DEAD` 한 곳에 두고, 여기서는 그 판정만 믿는다.
      넓히고 싶으면 그 정규식을 고칠 것 — 이 함수에 갈래를 더하지 말 것.

    ⚠ 생육단계는 비운다. 본문 문장에는 단계가 안 적혀 있다.
      없는 값은 비운다 — 작물 전체에 걸리는 규칙이 된다.
    """
    규칙 = []
    for t in 온도행들:
        if t.get("종류") != "동해":
            continue
        값 = t.get("값최소")
        if 값 == "" or 값 is None:
            continue
        규칙.append({
            "작물": t["작물"],
            "재해종류": "동해", "생육단계": "",
            "지표": "최저기온", "부등호": "<=", "값": 값, "단위": "℃",
            "지속일": "", "등급": "",
            "조건원문": (t.get("원문") or "")[:120],
            "출처": "재배법본문", "출처파일": t.get("출처파일", ""),
            "위치": t.get("위치", ""),
        })
    return 규칙


def run():
    """raw + 첨부 를 읽어 중간 CSV 여섯 종으로."""
    cmap = crop_map()
    sched = schedule_from_raw(cmap)
    text, tp0, sm0 = text_from_raw(cmap)
    s2, temp, sumt, rule, t2, table = from_farmwork_attach(cmap)
    temp += tp0          # 재배법 본문의 온도 (수박 base_temp 10℃ 가 여기 있다)
    sumt += sm0
    tp1, sm1 = attach_body(cmap)
    temp += tp1          # 첨부 표 밖 서술 (감자 base_temp 5℃ 가 여기 있다)
    sumt += sm1
    # 본문에 '동사' 로 적힌 것은 경보 규칙이다 (옥수수 -1.7℃).
    # 한계온도표에 줄이 없는 작물은 이 길로만 규칙이 생긴다.
    rule += 동해규칙(temp)
    return {
        "mid_schedule.csv": sched + s2,
        "mid_temp.csv": temp,
        "mid_sumtemp.csv": sumt,
        "mid_rule.csv": rule,
        "mid_text.csv": text + t2,
        "mid_table.csv": table,
    }


def 원본파일들():
    b = RAW / "농작업일정" / "첨부"
    return sorted(q for q in b.rglob("*") if q.is_file()) if b.exists() else []


def 계열(p):
    return ""


# 이 파일만 따로 돌릴 때 쓴다. extract.py 는 run() 을 바로 부른다.
NAME = "농작업일정"


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
