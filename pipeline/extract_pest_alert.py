# 병해충 경보 등급을 뽑습니다.
#
#     python pipeline/extract_pest_alert.py
#     → pipeline/out/pest_alert.csv
#
# ─────────────────────────────────────────────────────────────────────
# 왜 extract.py 와 따로인가
#
# **성격이 다릅니다.** extract.py 는 작물 마스터 데이터를 만듭니다 —
# 배포할 때 한 번 시딩하고 해마다 한 번 갱신하는 값(base_temp·숙기·한계온도)입니다.
# 경보 등급은 그해 그 주의 상황입니다. 주 1회 다시 받아야 합니다.
#
# 담기는 곳도 다릅니다. `GDD계산관련/작물_확정표.md` §I 의 스키마 네 종
# (crops · crop_variants · crop_stages · disaster_rules) 어디에도 자리가 없습니다.
# extract.py 에 넣으면 build.py 가 읽지 않는 CSV 가 하나 생깁니다.
#
# 확정표 §E 도 `disaster_rules` 와 `병해충 경보` 를 이미 다른 칸으로 세고 있습니다.
#
# ⚠ **병해충 '온도 조건' 은 여기가 아니라 extract.py 가 맡습니다.**
#   흰가루병 15~28℃ 같은 값은 해마다 바뀌지 않는 정적 값이라 mid_rule 로 갑니다.
#   여기서 뽑는 것은 "올해 몇 호에 무엇이 무슨 등급으로 났나" 뿐입니다.
#
# ─────────────────────────────────────────────────────────────────────
# 무엇이 나오나
#
#     연도 · 호수 · 기간 · 작물군 · 등급 · 구분 · 병해충명 · 대상작물 · 원문
#
# 2023~2026 네 해 57개 호에서 1,300행쯤 나옵니다.
#     등급  경보 18 · 주의보 489 · 예보 832
#     구분  병 617 · 해충 607 · 바이러스 58
#
# ⚠ 요약표 모양이 네 가지로 섞여 있습니다. 한 호만 보고 파서를 만들었다가
#   2023~2024년을 절반 넘게 놓친 적이 있습니다 (269행 → 고친 뒤 1,339행).
#   그 경험과 파서는 `feature/pest_summary.py` 에 있습니다. 여기서는 부르기만 합니다.
# ─────────────────────────────────────────────────────────────────────

import csv
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "feature"))

from hwpx_table import read_any  # noqa: E402
from pest_summary import parse_summary  # noqa: E402

RAW = ROOT / "원본" / "병해충발생정보"
OUT = ROOT / "pipeline" / "out"

COLS = ["연도", "호수", "기간", "작물군", "등급", "구분",
        "병해충명", "대상작물", "출처파일", "원문"]


def plain_text(p: Path) -> str:
    """같은 PDF 를 줄 배치 없이 읽는다. layout 모드가 뒤엉킬 때 쓰는 두 번째 눈."""
    try:
        from pypdf import PdfReader
        return "\n".join(pg.extract_text() or "" for pg in PdfReader(str(p)).pages)
    except Exception:  # noqa: BLE001
        return ""


def 호정보():
    """raw 의 lst_*.xml 에서 호수와 기간을 읽는다.

    ⚠ 첨부 파일 이름에는 호수만 있고 기간이 없다.
      "병해충발생정보 제 15호 (2023.12.1.~12.31.)" 는 목록 응답에만 있다.
      기간이 없으면 그해 언제 난 경보인지 알 수 없다.
    """
    out = {}
    for p in sorted((RAW / "raw").glob("lst_*.xml")):
        for it in ET.parse(p).getroot().findall(".//item"):
            제목 = (it.findtext("cntntsSj") or "").strip()
            파일 = (it.findtext("rtnOrginlFileNm") or "").strip()
            m = re.search(r"제\s*(\d+)\s*호", 제목)
            기간 = re.search(r"[(（]\s*([^)）]*)\s*[)）]", 제목)
            out[파일] = {
                "연도": (it.findtext("pblicteYear") or "").strip(),
                "호수": m.group(1) if m else "",
                "기간": 기간.group(1) if 기간 else "",
            }
    return out


def main():
    base = RAW / "첨부"
    if not base.exists():
        print(f"원본이 없습니다: {base}")
        return
    meta = 호정보()
    rows, 빈것 = [], []
    파일들 = sorted(q for q in base.rglob("*") if q.is_file())
    print(f"병해충발생정보 {len(파일들)}개 (PDF 라 파일당 3초쯤 걸립니다)")

    for p in 파일들:
        글 = read_any(p)
        if not 글:
            빈것.append(p.name)
            continue
        r = meta.get(p.name) or {
            "연도": p.relative_to(base).parts[0],
            "호수": (re.match(r"(\d+)호", p.name) or ["", ""])[1],
            "기간": "",
        }
        새것 = parse_summary(글, r)
        if not 새것:
            # ⚠ PDF 판마다 글자 배치가 다르다. layout 모드로 못 읽히면 plain 으로 다시 본다.
            #   2026 제5호가 layout 에서는 이름과 괄호가 뒤엉켜 0행이었는데 plain 에서는 읽혔다.
            새것 = parse_summary(plain_text(p), r)
            if 새것:
                print(f"  · {p.name[:40]} — plain 모드로 다시 읽어 {len(새것)}행")
        for x in 새것:
            x["출처파일"] = p.name
        rows += 새것

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "pest_alert.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    print(f"\n  pest_alert.csv  {len(rows)}행")
    if 빈것:
        print(f"  ⚠ 글자가 안 나온 파일 {len(빈것)}개: {', '.join(빈것[:3])}")
        print("     스캔 PDF 일 수 있습니다. feature/ocr.py 를 쓰세요")

    # 한 호에서 너무 적게 나오면 요약 모양이 또 다른 것이다. 조용히 넘기면 안 된다.
    # ⚠ 0 만 보면 안 된다. 2026 제5호는 글자가 뒤엉켜 4행만 나왔는데 원본에는 25건쯤 있다.
    #   한 호에 보통 16~45행이 나온다. 그 아래면 의심한다.
    적다 = 8
    호별 = {}
    for x in rows:
        호별[x["출처파일"]] = 호별.get(x["출처파일"], 0) + 1
    의심 = [(p.name, 호별.get(p.name, 0)) for p in 파일들
            if 호별.get(p.name, 0) < 적다 and p.name not in 빈것]
    if 의심:
        print(f"  ⚠ 너무 적게 읽힌 호 {len(의심)}개 — 글자 배치가 또 다를 수 있습니다")
        for n, c in 의심[:5]:
            print(f"      {c:3}행  {n}")

    print("\n끝. 값이 이상하면 '출처파일' 과 '원문' 으로 원본을 찾으세요.")


if __name__ == "__main__":
    main()
