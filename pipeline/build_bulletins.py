# 게시물(주 1회 · 반월 · 월) 본문 → 저쪽 게시물 표 계약 CSV.
#
#     python pipeline/build_bulletins.py            전부
#     python pipeline/build_bulletins.py weekly     하나만
#     → pipeline/out/게시/weekly_notes.csv · pest_bulletins.csv · disaster_bulletins.csv
#
# build.py(마스터, 연 1회)와 나눈 이유 — 갱신 주기가 다르다. 매주 이걸 돌린다고 마스터를
# 다시 만들지 않는다. 저쪽도 master_seed 가 아니라 seed_bulletins 가 받는다.
#
# ★ 파일 이름이 곧 테이블 이름이다 (build.py 와 같은 약속).
# ★ 자르지 않는다. 청킹은 저쪽 chunker.py 가 한다.

import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from crops import crops_in_line  # noqa: E402

원본 = HERE.parent / "원본"
게시 = HERE / "out" / "게시"

계약 = {
    "weekly_notes.csv": ["issue_year", "issue_no", "ordinal", "period_from", "period_to",
                         "topic", "crops", "body", "source_file"],
    "pest_alerts.csv": ["issue_year", "issue_no", "crop_group", "level", "kind",
                        "pest_name", "target_crops", "source_file"],
    "pest_bulletins.csv": ["issue_year", "issue_no", "ordinal", "period_from", "period_to",
                           "crop_group", "pest_name", "level", "crop_names", "body", "source_file"],
    # disaster_bulletins 는 그 교안에서 더한다
}

# 첨부를 글자로 펼 때 섞이는 것. 값이 아니다
_잡음 = re.compile(
    r"^\s*(그림입니다\.?|사각형입니다\.?|원본 그림의 (이름|크기):.*|.*HWPHYPERLINK.*|===== p\.\d+ =====|- \d+ -)\s*$"
)

# 줄 전체가 아니라 **문장 끝에 붙어** 나오는 그림 자리표시자.
# hwpx 에서 "…양생함그림입니다." 처럼 앞 문장과 한 줄로 이어진다 — 위 _잡음 은 줄 전체를
# 보므로 못 잡는다. 지운 자리에 공백을 넣지 않는다(앞 문장이 그대로 끝나야 한다)
_붙은그림 = re.compile(r"(그림입니다\.?|사각형입니다\.?)")


def 읽기(path):
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def 쓰기(이름, 행들):
    게시.mkdir(parents=True, exist_ok=True)
    with (게시 / 이름).open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=계약[이름], extrasaction="ignore")
        w.writeheader()
        w.writerows(행들)
    print(f"  {이름:24} {len(행들):5}행  → 게시/")


# ─────────────────────────────────────────────────────────────────────
# weekly_notes — 주간농사정보. 문서 단위 = "번호 + 제목" 주제 절
# ─────────────────────────────────────────────────────────────────────

# 파일명의 기간. 세 표기가 있다 — (2023.03.13.~03.19.) (2025.3.17.~3.23.) (2026.5.18._5.24.)
_기간 = re.compile(r"\((\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.?\s*[~_∼]\s*(?:(\d{4})\.)?\s*(\d{1,2})\.\s*(\d{1,2})")
# 연도가 없는 파일명 둘 — (4. 27.~5. 3.) — 폴더명(2026)에서 채운다
_기간_연도없음 = re.compile(r"\((\d{1,2})\.\s*(\d{1,2})\.?\s*[~_∼]\s*(\d{1,2})\.\s*(\d{1,2})")
_호수 = re.compile(r"(\d+)호_")
_번호줄 = re.compile(r"^\s*(\d{1,2})\s*$")
_불릿 = re.compile(r"^\s*❍")
_하위 = re.compile(r"^\s{2,}-\s")


def _기간읽기(name, folder_year):
    """파일명 → (from, to) 'YYYY-MM-DD'. 못 읽으면 (None, None)."""
    m = _기간.search(name)
    if m:
        y1, m1, d1, y2, m2, d2 = m.groups()
        y2 = y2 or (str(int(y1) + 1) if int(m2) < int(m1) else y1)   # 12월→1월 넘김
        return f"{y1}-{int(m1):02d}-{int(d1):02d}", f"{y2}-{int(m2):02d}-{int(d2):02d}"
    m = _기간_연도없음.search(name)
    if m and folder_year:
        m1, d1, m2, d2 = m.groups()
        return f"{folder_year}-{int(m1):02d}-{int(d1):02d}", f"{folder_year}-{int(m2):02d}-{int(d2):02d}"
    return None, None


def _절나누기(줄들):
    """[(topic, [본문 줄])]. 번호 줄 + 제목 줄이 절을 열고, 다음 번호 줄이 닫는다.

    ❍ 와 들여쓴 '- ' 만 본문으로 받는다. 요약 절의 '• (…)' 는 본문의 되풀이라 안 받는다.
    ❍ 가 하나도 없는 절(표 제목 '12 합계' 등)은 돌려주지 않는다.
    """
    절들, topic, body = [], None, []
    i = 0
    while i < len(줄들):
        s = 줄들[i].rstrip()
        if _번호줄.match(s):
            # 다음 비지 않은 줄이 제목이다. 불릿·숫자로 시작하면 제목이 아니다(표 조각)
            j = next((k for k in range(i + 1, min(i + 4, len(줄들))) if 줄들[k].strip()), None)
            title = 줄들[j].strip() if j is not None else ""
            if title and len(title) <= 14 and not re.match(r"[•❍\-\d]", title):
                if topic and body:
                    절들.append((topic, body))
                topic, body = title, []
                i = j + 1
                continue
        if topic and not _잡음.match(s) and (_불릿.match(s) or _하위.match(s)):
            깬 = _붙은그림.sub("", s).strip()
            if 깬:
                body.append(깬)
        i += 1
    if topic and body:
        절들.append((topic, body))
    return 절들

# 재배 지침이 아닌 절. 그해 기상 통계라 3년치가 섞이면 오히려 틀린 답이 나온다
# ('합계' 74행 — "시도별 누적 강수량('23.1.1.~'23.10.16.)" 꼴)
버릴주제 = frozenset({"합계"})
def weekly():
    행들 = []
    for path in sorted((원본 / "주간농사정보" / "본문").glob("*/*.txt")):
        folder_year = path.parent.name if path.parent.name.isdigit() else None
        pf, pt = _기간읽기(path.name, folder_year)
        m = _호수.search(path.name)
        no = int(m.group(1)) if m else None
        year = int(pf[:4]) if pf else (int(folder_year) if folder_year else None)
        if not (no and year):
            print(f"  ⚠ 호수·연도 못 읽음: {path.name}")
            continue
        for ordinal, (topic, body) in enumerate(_절나누기(읽기(path)), 1):
            if topic in 버릴주제:
                continue
            텍스트 = "\n".join(body)
            if len(텍스트) < 40:
                continue
            작물 = sorted(crops_in_line(topic + " " + 텍스트))
            행들.append({
                "issue_year": year, "issue_no": no, "ordinal": ordinal,
                "period_from": pf or "", "period_to": pt or "",
                "topic": topic, "crops": ",".join(작물),
                "body": 텍스트, "source_file": path.name,
            })
    return 행들


# ─────────────────────────────────────────────────────────────────────
# pest_alerts — 경보 등급. extract_pest_alert.py 의 산출을 계약 꼴로만 바꾼다
# ─────────────────────────────────────────────────────────────────────

def pest_alerts():
    src = HERE / "out" / "pest_alert.csv"
    with src.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    return [{
        "issue_year": r["연도"], "issue_no": r["호수"],
        "crop_group": r["작물군"], "level": r["등급"], "kind": r["구분"],
        "pest_name": r["병해충명"], "target_crops": r["대상작물"],
        "source_file": r["출처파일"],
    } for r in rows]


# ─────────────────────────────────────────────────────────────────────
# pest_bulletins — 해충별 설명. 문서 단위 = "N 병해충명 <등급>" 항목
# ─────────────────────────────────────────────────────────────────────

_병기간 = re.compile(r"〔제(\d+)호\s*/\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.?\s*[~∼]\s*(\d{1,2})\.\s*(\d{1,2})")
_병절 = re.compile(r"^\s*[Ⅰ-Ⅹ]+\.\s*(.+?)\s*$")
_병항목 = re.compile(r"^\s*(\d+)\s+(\S.*?)\s*<\s*(주의보|경보|예보)\s*>")
_병끝 = re.compile(r"^\s*[Ⅰ-Ⅹ]+\.\s*(시·도별|지역별|주요 부적합)")
_캡션 = re.compile(r"^\s*(【.*】\s*)+$")
_문장끝 = re.compile(r"[.。]\s*$|[다음함임됨요]\s*$")


def _줄잇기(줄들):
    """PDF 강제 줄바꿈 복원. 앞 줄이 문장 끝이 아니면 다음 줄을 붙인다.
    ❍ 나 '- ' 로 시작하는 줄은 새 문장이다 — 앞 줄이 안 끝났어도 붙이지 않는다."""
    out = []
    for s in 줄들:
        if out and not _문장끝.search(out[-1]) and not re.match(r"^\s*[❍\-]", s):
            out[-1] += s.strip()
        else:
            out.append(s.strip())
    return out


def pest_bulletins():
    행들 = []
    for path in sorted((원본 / "병해충발생정보" / "본문").glob("*/*.txt")):
        줄들 = 읽기(path)
        m = next((_병기간.search(l) for l in 줄들[:40] if _병기간.search(l)), None)
        if not m:
            print(f"  ⚠ 호수·기간 못 읽음: {path}")
            continue
        no, y, m1, d1, m2, d2 = m.groups()
        pf, pt = f"{y}-{int(m1):02d}-{int(d1):02d}", f"{y}-{int(m2):02d}-{int(d2):02d}"

        group, item, body, ordinal = "", None, [], 0
        def 닫기():
            nonlocal item, body, ordinal
            if item and body:
                텍스트 = "\n".join(_줄잇기(body))
                if len(텍스트) >= 40:
                    ordinal += 1
                    pest, level = item
                    행들.append({
                        "issue_year": int(y), "issue_no": int(no), "ordinal": ordinal,
                        "period_from": pf, "period_to": pt,
                        "crop_group": group, "pest_name": pest, "level": level,
                        "crop_names": ",".join(sorted(crops_in_line(pest + " " + 텍스트))),
                        "body": 텍스트, "source_file": path.name,
                    })
            item, body = None, []

        for s in 줄들:
            if _병끝.match(s):
                break                                  # 농약 잔류 통계부터는 안 읽는다
            if _잡음.match(s) or _캡션.match(s):
                continue
            g = _병절.match(s)
            if g:
                닫기(); group = "".join(g.group(1).split()); continue
            h = _병항목.match(s)
            if h:
                닫기(); item = (h.group(2).strip(), h.group(3)); continue
            if item and s.strip():
                body.append(s)
        닫기()
    return 행들


STEPS = {
    "weekly": ("weekly_notes.csv", weekly),
    "pest_alerts": ("pest_alerts.csv", pest_alerts),
    "pest": ("pest_bulletins.csv", pest_bulletins),
}


def main():
    고를것 = sys.argv[1:] or list(STEPS)
    for name in 고를것:
        파일, fn = STEPS[name]
        print(f"{name}")
        쓰기(파일, fn())


if __name__ == "__main__":
    main()
