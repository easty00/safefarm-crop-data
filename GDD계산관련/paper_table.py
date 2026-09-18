"""Paredes et al. (2025) 논문 표에서 작물별 Tbase·Tupper 를 뽑는다.

    python GDD계산관련/paper_table.py              # 112작물 전량
    python GDD계산관련/paper_table.py Broccoli     # 이름으로 걸러 보기

확정표 §B-2 의 `논문` 근거가 이 스크립트의 출력이다. **값을 손으로 옮겨 적었으므로,
어떤 값이 어디서 왔는지 다시 확인하려면 이것을 돌린다.**

─────────────────────────────────────────────────────────────────────
왜 pypdf 의 layout 모드라야 하는가

이 논문은 2단 조판이고 표가 13개다. 기본 추출(`extract_text()`)로는 왼쪽 단과 오른쪽
단의 글이 줄마다 뒤섞여 **작물명과 값이 끊어진다.** `extraction_mode="layout"` 은
쪽의 좌표를 살려 2단을 나란히 펴므로 표가 이 모양으로 나온다.

    Sweet potato (Ipomoea batatas)
    8      30    AquaCrop CGM     Field trials   Full cycle   Various
    8.1    38    SPOTCOMS CGM     Field trials   Full cycle   Sree Arun

그래서 "작물명 줄(학명 괄호)을 만나면 현재 작물을 바꾸고, 그 아래 숫자 줄을 그 작물의
값으로 모은다" 는 단순한 규칙이 성립한다.

⚠ pymupdf 는 이 문서에서 표를 더 잘 읽지만(find_tables), 여기서는 쓰지 않는다.
  이 논문 표는 세로줄이 없는 편집 표라 find_tables 가 경계를 못 잡는다.
  반대로 농사로 hwpx·PDF 는 pymupdf 쪽이 맞다 — 문서마다 도구가 다르다.

⚠ 학명이 긴 작물은 이 파서가 놓친다. 실제로 Plum 이 그랬다 —
  `Plum (Prunus salicina (Japanese plum) and P. domestica (European plum))` 처럼
  괄호가 겹치면 CROP 정규식이 닫지 못한다. 놓친 작물은 아래 MANUAL 에 적어 둔다.
"""

from __future__ import annotations

import re
import statistics
import sys
from collections import OrderedDict
from pathlib import Path

from pypdf import PdfReader

PDF = Path(__file__).resolve().parent / "논문" / "1-s2.0-S037837742500469X-main.pdf"

# 작물명 줄: 들여쓰기 + 이름 + (학명). 'B. oleracea' 처럼 축약된 속명도 받는다
CROP = re.compile(r"^\s{1,8}([A-Z][A-Za-z'\-,()/ ]{2,45}?)\s+\(([A-Z][a-z]*\.?[^)]{2,60})\)\s*$")
# 값 줄: Tbase, Tupper 로 시작. 'n/r'(not reported) 은 값 없음, '*' 는 최고기온 표시
VAL = re.compile(r"^\s{1,10}(-?\d+(?:\.\d+)?|n/r)\s+(-?\d+(?:[.–-]\d+)?\*?|n/r)\s+\S")

# 파서가 놓치는 작물 — 위 ⚠ 참고. 쪽을 눈으로 읽고 옮긴 값이다
MANUAL = {
    "Plum": {
        "sci": "Prunus salicina / P. domestica",
        "vals": [(2.2, None), (5.0, None), (6.0, 25.0)],
        "note": "p.14. 학명 괄호가 겹쳐 CROP 정규식이 못 닫는다",
    },
}


def _num(tok: str) -> float | None:
    """'8.1' → 8.1 · 'n/r' → None · '34–38' → 34.0 · '24*' → 24.0"""
    if tok == "n/r":
        return None
    return float(re.split(r"[–-]", tok.replace("*", ""))[0])


def read_table() -> OrderedDict[str, dict]:
    """{작물명: {sci, vals:[(base, upper), …]}}"""
    reader = PdfReader(str(PDF))
    out: OrderedDict[str, dict] = OrderedDict()
    cur = None
    for page in reader.pages:
        for line in page.extract_text(extraction_mode="layout").split("\n"):
            m = CROP.match(line.rstrip())
            if m:
                cur = m.group(1).strip()
                out.setdefault(cur, {"sci": m.group(2).strip(), "vals": []})
                continue
            if cur:
                v = VAL.match(line.rstrip())
                if v:
                    out[cur]["vals"].append((_num(v.group(1)), _num(v.group(2))))
    for name, extra in MANUAL.items():
        out.setdefault(name, {"sci": extra["sci"], "vals": extra["vals"]})
    return out


def pick(values: list[float | None]) -> int | None:
    """확정표 §B-2 가 써 온 방식 — ① 다수 일치값 ② 없으면 중앙값 ③ 정수로.

    "논문 4 (3건 일치)" 가 ①, "논문 7~10 중앙" 이 ② 다.
    §B-2 채택값이 전부 정수라 반올림해 맞춘다.
    """
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    counts: dict[float, int] = {}
    for v in vals:
        counts[v] = counts.get(v, 0) + 1
    top = max(counts.values())
    if top >= 2:
        return int(round(min(v for v, c in counts.items() if c == top)))
    return int(round(statistics.median(vals)))


def main() -> None:
    if not PDF.exists():
        raise SystemExit(f"논문 PDF 가 없습니다: {PDF}\n  → 논문/ 은 git 에 올리지 않는다(Elsevier)")
    key = sys.argv[1].lower() if len(sys.argv) > 1 else None
    table = read_table()

    print(f"{'작물':<30} {'학명':<30} {'Tbase':>7} {'Tupper':>7}  건수  (원값)")
    shown = 0
    for name, info in table.items():
        if key and key not in name.lower():
            continue
        vals = info["vals"]
        if not vals:
            continue
        shown += 1
        base, upper = pick([b for b, _ in vals]), pick([u for _, u in vals])
        # 원값을 그대로 보여 준다 — pick() 이 무엇을 보고 골랐는지 눈으로 확인하려고
        raw = " ".join(
            f"{'-' if b is None else f'{b:g}'}/{'-' if u is None else f'{u:g}'}"
            for b, u in vals
        )
        print(
            f"  {name[:28]:<28} {info['sci'][:28]:<30}"
            f" {base if base is not None else '-':>7} {upper if upper is not None else '-':>7}"
            f"  {len(vals):>3}   {raw[:46]}"
        )
    print()
    print(f"{shown}작물 (전체 {len(table)}) · Tbase 는 위 pick() 규칙으로 고른 값")
    print("정본은 GDD계산관련/작물_확정표.md §B-2 다. 이 출력은 그 표의 근거다.")


if __name__ == "__main__":
    main()
