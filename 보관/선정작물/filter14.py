# 뽑아둔 결과 표 전부를 **선정 14작물**로 거릅니다.
# 자세한 설명은 같은 폴더의 "14작물거르기_사용법.md" 를 읽어주세요.
#
# 새로 내려받는 것은 없습니다. `*/결과/*.csv` 를 읽어 14작물 행만 따로 모읍니다.
#
# 결과 표가 39개 · 63,264행인데 14작물 밖이 대부분입니다. 전부 읽을 수는 없고
# 읽을 범위를 먼저 좁혀야 합니다. 그 범위를 만드는 것이 이 스크립트입니다.
#
# ⚠ 이름 맞추기가 이 일의 전부입니다. 부분일치로 하면 이런 게 걸립니다.
#
#     무   ← 무화과 · 무궁화
#     파   ← 파프리카 · 파슬리(향미나리) · 파드득나물
#     배추 ← 양배추 · 브로콜리(녹색꽃양배추)
#     벼   ← 사료용벼 · 밭벼
#
# 그래서 작물마다 **넣을 것(alias)과 뺄 것(exclude)** 을 눈으로 확인해 적어둡니다.
# 어떤 원본 이름이 어느 작물로 갔는지는 `매칭표.csv` 에 전부 남깁니다.

import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "결과" / "14작물"

# 작물 → (넣을 이름 조각, 뺄 이름 조각)
# 실제로 표에 나온 이름 34종을 세어보고 적은 것이다. 추측이 아니다.
CROPS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "벼":      (("벼", "논벼", "벼등"), ("사료용", "총체", "밭벼", "줄무늬잎마름")),
    "배추":    (("배추",), ("양배추", "꽃양배추", "브로콜리", "컬리플라워")),
    "무":      (("무",), ("무화과", "무궁화", "파드득", "고구마", "참다래")),
    "고추":    (("고추",), ("꽈리", "촉성")),          # 보통재배만. 촉성·반촉성은 시설
    "감자":    (("감자",), ("고구마", "돼지감자")),
    "상추":    (("상추",), ("결구상추", "양상추")),     # 결구상추(양상추)는 다른 작물
    "시금치":  (("시금치",), ()),
    "당근":    (("당근",), ()),
    "양파":    (("양파",), ()),
    "마늘":    (("마늘",), ("잎마늘",)),               # 잎마늘은 쓰임새가 다르다
    "파":      (("파",), ("파프리카", "파슬리", "파드득", "쪽파", "대파무",
                          "양파", "파인애플")),
    "수박":    (("수박",), ()),
    "가지":    (("가지",), ("감가지", "나뭇가지")),
    "방울토마토": (("방울토마토", "토마토"), ()),        # '토마토,방울토마토' 합본도 받는다
}

# 작물 이름이 들어 있는 칸. 표마다 이름이 다르다
NAME_COLS = ("작물명", "작물", "대상작물")
# 여러 작물이 한 칸에 쉼표로 들어오는 표가 있다 (병해충 대상작물)
SPLIT_RE = re.compile(r"[,、·／/]")


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def hit(piece: str, alias: str) -> bool:
    """이름 조각이 들어 있는지 본다.

    ⚠ **한 글자 이름은 부분일치로 찾으면 안 된다.** 뺄 목록으로도 못 막는다.

        무 → 꽃사과나무 · 천마균류(뽕나무버섯류) · 키다리병,깨씨무늬병등 · 포도(무가온)
        파 → 아스파라거스 · 벼 직파재배
        벼 → 벼줄무늬잎마름병

    실제로 이렇게 걸렸다. 그래서 한 글자는 **앞뒤에 한글이 붙지 않은 것**만 받는다.
    '무(고랭지재배)' 는 뒤가 괄호라 통과하고, '꽃사과나무' 는 앞이 '나' 라 걸러진다.
    """
    if len(alias) == 1:
        return re.search(rf"(?<![가-힣]){re.escape(alias)}(?![가-힣])", piece) is not None
    return alias in piece


def match(raw: str) -> list[str]:
    """원본 이름 하나가 어느 작물에 해당하는지 돌려준다. 여럿일 수 있다."""
    found = []
    for piece in SPLIT_RE.split(raw):
        piece = piece.strip()
        if not piece:
            continue
        for crop, (aliases, bad) in CROPS.items():
            if any(b in piece for b in bad):
                continue
            if any(hit(piece, a) for a in aliases):
                if crop not in found:
                    found.append(crop)
    return found


def targets() -> list[Path]:
    out = []
    for folder in sorted(ROOT.glob("*/결과")):
        if folder.parent.name in (HERE.name, "검수"):
            continue
        out += sorted(folder.glob("*.csv"))
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    summary, mapping, no_col = [], [], []

    for path in targets():
        svc, fname = path.parent.parent.name, path.name
        try:
            rows = read_csv(path)
        except Exception as err:
            summary.append({"서비스": svc, "파일": fname, "전체": 0, "남은행": 0,
                            "작물수": 0, "비고": f"못 읽음: {err}"})
            continue
        if not rows:
            continue
        col = next((c for c in NAME_COLS if c in rows[0]), None)
        if not col:
            # 작물 칸이 없는 표. 거를 수가 없으니 통째로 남겨둔다는 뜻이다
            no_col.append({"서비스": svc, "파일": fname, "행": len(rows),
                           "칸": ", ".join(list(rows[0])[:8])})
            summary.append({"서비스": svc, "파일": fname, "전체": len(rows),
                            "남은행": len(rows), "작물수": 0, "비고": "작물 칸 없음 — 전량"})
            continue

        kept, seen = [], defaultdict(Counter)
        for r in rows:
            raw = (r.get(col) or "").strip()
            if not raw:
                continue
            hits = match(raw)
            if not hits:
                continue
            for crop in hits:
                seen[crop][raw] += 1
            out = dict(r)
            out["_선정작물"] = " | ".join(hits)
            kept.append(out)

        if kept:
            dest = OUT / f"{svc}_{fname}"
            keys = list(dict.fromkeys(k for d in kept for k in d))
            with open(dest, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=keys)
                w.writeheader()
                w.writerows(kept)
        for crop, names in seen.items():
            for raw, n in names.items():
                mapping.append({"서비스": svc, "파일": fname, "선정작물": crop,
                                "원본이름": raw, "행": n})
        summary.append({"서비스": svc, "파일": fname, "전체": len(rows),
                        "남은행": len(kept), "작물수": len(seen),
                        "비고": f"{len(kept)/len(rows)*100:.0f}%"})
        print(f"  {svc:12}{fname:26}{len(rows):>7,} → {len(kept):>6,}  작물 {len(seen)}")

    for name, data in (("요약.csv", summary), ("매칭표.csv", mapping),
                       ("작물칸없음.csv", no_col)):
        if not data:
            continue
        keys = list(dict.fromkeys(k for d in data for k in d))
        with open(HERE / "결과" / name, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(data)

    # 사람이 읽을 요약
    tot = sum(s["전체"] for s in summary)
    kept_tot = sum(s["남은행"] for s in summary if s["작물수"])
    md = ["# 14작물로 거른 결과", "",
          f"결과 표 {len(summary)}개 · 전체 {tot:,}행",
          f"작물 칸이 있는 표에서 **14작물 {kept_tot:,}행**", "",
          "## 표별", "", "| 서비스 | 파일 | 전체 | 14작물 | 비율 |", "|---|---|---|---|---|"]
    for s in sorted(summary, key=lambda x: -x["남은행"]):
        if not s["작물수"]:
            continue
        md.append(f"| {s['서비스']} | {s['파일']} | {s['전체']:,} | "
                  f"{s['남은행']:,} | {s['비고']} |")

    md += ["", "## 작물별 행 수", "", "| 작물 | 행 | 표 수 |", "|---|---|---|"]
    per = defaultdict(lambda: [0, set()])
    for m in mapping:
        per[m["선정작물"]][0] += m["행"]
        per[m["선정작물"]][1].add(m["파일"])
    for crop in CROPS:
        n, files = per[crop]
        md.append(f"| {crop} | {n:,} | {len(files)} |")

    md += ["", "## ⚠ 이름이 이렇게 맞춰졌다 — 눈으로 확인할 것", "",
           "부분일치라 엉뚱한 게 붙을 수 있습니다. 이상한 짝이 보이면 알려주세요.", "",
           "| 선정작물 | 원본 이름 |", "|---|---|"]
    names = defaultdict(set)
    for m in mapping:
        names[m["선정작물"]].add(m["원본이름"])
    for crop in CROPS:
        md.append(f"| {crop} | {' · '.join(sorted(names[crop])[:14])} |")

    if no_col:
        md += ["", "## 작물 칸이 없어 못 거른 표", "",
               "작물별로 나뉘지 않는 표입니다. 통째로 봐야 합니다.", "",
               "| 서비스 | 파일 | 행 |", "|---|---|---|"]
        for x in no_col:
            md.append(f"| {x['서비스']} | {x['파일']} | {x['행']:,} |")

    (HERE / "결과" / "14작물_요약.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\n전체 {tot:,}행 → 14작물 {kept_tot:,}행")
    print(f"결과: {OUT}")


if __name__ == "__main__":
    main()
