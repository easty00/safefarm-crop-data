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
    "disaster_bulletins.csv": ["issue_year", "issue_month", "ordinal", "hazard", "crop_names",
                               "phase", "body", "source_file"],
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
#
# ⚠ **이름을 하나씩 적는다. 정규식으로 긁지 말 것.** topic 에 '기상' 이 든 186건 중
#    34건은 지침이다('여름철 기상재해 관리요령' 18 · '기상재해 대비 사전관리' 11 …).
#    한 줄로 지우면 재해 대책을 같이 날린다 — 재해예방정보에서 예측보고를 버릴 때
#    월간회보를 같이 버리지 않으려고 파일 이름으로 갈랐던 것과 같은 이유다
버릴주제 = frozenset({
    "합계",
    "기상 상황 및 전망",       # 133건. 기온·강수량·일조시간 통계뿐
    "기상 정보",               # 14건. 위와 같은 내용, 호에 따라 제목만 다르다
    "저수율 및 강수량 현황",    # 5건. 시도별 누적 강수량 표
})
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
    행들 = [{
        "issue_year": r["연도"], "issue_no": r["호수"],
        "crop_group": r["작물군"], "level": r["등급"], "kind": r["구분"],
        "pest_name": r["병해충명"], "target_crops": r["대상작물"],
        "source_file": r["출처파일"],
    } for r in rows]

    # 같은 경보가 요약과 본문에 두 번 실린다. 저쪽 자연키가 겹쳐
    # ON CONFLICT DO UPDATE 가 "한 문장에서 같은 행을 두 번 건드릴 수 없다" 로 죽는다.
    #
    # ⚠ 뒤엣것으로 덮지 않는다. 한쪽에만 대상작물이 붙어 있어서다 —
    #   '2023 9호 멸강나방' 은 본문에 '옥수수', 요약에 빈 칸이다. 채워진 쪽을 남긴다
    접음 = {}
    for r in 행들:
        열쇠 = (r["issue_year"], r["issue_no"], r["crop_group"],
                r["level"], r["kind"], r["pest_name"])
        앞 = 접음.get(열쇠)
        if 앞 is None or (not 앞["target_crops"].strip() and r["target_crops"].strip()):
            접음[열쇠] = r
    return list(접음.values())


# ─────────────────────────────────────────────────────────────────────
# pest_bulletins — 해충별 설명. 문서 단위 = "N 병해충명 <등급>" 항목
# ─────────────────────────────────────────────────────────────────────

_병기간 = re.compile(r"〔제(\d+)호\s*/\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.?\s*[~∼]\s*(\d{1,2})\.\s*(\d{1,2})")
_병절 = re.compile(r"^\s*[Ⅰ-Ⅹ]+\.\s*(.+?)\s*$")
_병항목 = re.compile(r"^\s*(\d+)\s+(\S.*?)\s*<\s*(주의보|경보|예보)\s*>")
_병끝 = re.compile(r"^\s*[Ⅰ-Ⅹ]+\.\s*(시·도별|지역별|주요 부적합)")
# 등록약제 표. "갓 Dinotefuran 0.1 0.1 당해성분 …" 꼴 — 작물명 · 영문 성분 · 잔류기준 둘.
# 본문이 아니라 부록이고, 여기 작물명이 crops_in_line 에 걸려 과수화상병에 감자·배추가 붙었다(26행, 2026-09-18 실측)
_약제표 = re.compile(r"[A-Z][a-z]{3,}\s+\d\.\d+\s+\d\.\d+")
_캡션 = re.compile(r"^\s*(【.*】\s*)+$")
_문장끝 = re.compile(r"[.。]\s*$|[다음함임됨요]\s*$")

# 문서 하나의 상한. 넘으면 잘라서 여러 문서로 낸다.
#
# ⚠ 쪼개는 기준을 '< 이름 >' 으로 삼으면 안 된다 — 그건 하위 항목이 아니라 **그림 캡션**이다
#   ('< 갈색날개매미충 >' 은 그림 안 라벨이라 쪼개면 한 줄짜리 문서가 생긴다).
#   전체에 31개뿐이고 14,229자짜리에도 둘밖에 없어 쪼개지지도 않는다.
#
# 큰 덩이가 생기는 진짜 이유는 **그 호의 마지막 항목**이라 다음 제목이 없어서다
# (2024/5호 '7 과수해충' 뒤로 농약 잔류 절까지 통째). 그래서 길이로 자른다.
# 2,000자는 body 중앙값 270자의 7배 — 1,021행 중 56행(5.5%)만 걸린다
문서상한 = 2000

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

def _토막내기(줄들, 상한):
    """
    # summary
    줄 목록을 상한 이하 덩이로 나눈다. **줄 경계에서만** 자른다 — 문장 가운데를 끊으면
    그 조각만으로는 뜻이 안 통한다.

    # params
    줄들: _줄잇기 를 거친 줄 목록<br>
    상한: 한 덩이의 최대 글자 수. 한 줄이 그보다 길면 그 줄은 혼자 한 덩이가 된다<br>

    # returns
    '\\n' 으로 이은 문자열 목록. 원문 순서를 지킨다. 줄들이 비면 빈 리스트

    # examples
        _토막내기(['가' * 1500, '나' * 1500], 2000)  -> ['가...', '나...']   # 둘로
    """
    덩이, 모음, 길이 = [], [], 0
    for 줄 in 줄들:
        if 모음 and 길이 + len(줄) > 상한:
            덩이.append("\n".join(모음))
            모음, 길이 = [], 0
        모음.append(줄)
        길이 += len(줄) + 1
    if 모음:
        덩이.append("\n".join(모음))
    return 덩이


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
                줄들 = _줄잇기(body)
                pest, level = item
                # '(무․배추) 뿌리혹병, 무름병' → '뿌리혹병, 무름병'. 작물 괄호는 crop_names 가 따로 든다.
                # 이름을 접지 않으면 같은 병이 호마다 다른 pest_name 으로 갈려 148종이 된다(실제 109종)
                pest = re.sub(r"\([^)]*\)", "", pest).strip(" ,·‧․")
                # 상한을 넘으면 줄 경계에서 잘라 여러 문서로 낸다. 한 문서가 14,229자면
                # chunker 가 조각 10여 개로 나누는데 title 이 전부 같아 구분이 안 된다
                for 조각 in _토막내기(줄들, 문서상한):
                    if len(조각) < 40:
                        continue
                    ordinal += 1
                    행들.append({
                        "issue_year": int(y), "issue_no": int(no), "ordinal": ordinal,
                        "period_from": pf, "period_to": pt,
                        "crop_group": group, "pest_name": pest, "level": level,
                        "crop_names": ",".join(sorted(crops_in_line(pest + " " + 조각))),
                        "body": 조각, "source_file": path.name,
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
            if item and s.strip() and not _약제표.search(s):
                body.append(s)
        닫기()
    return 행들


# ─────────────────────────────────────────────────────────────────────
# disaster_bulletins — 재해예방 월간회보의 대책 블록. 예측보고는 읽지 않는다 (문장이 없다)
#
# ★ 제목 계층을 따라가지 않는다. 44호가 네 서식으로 쓰여 있어서 '절 → 소절 → 블록' 을
#   맞히려 들면 호마다 규칙이 하나씩 붙는다(실측: 37/44 파일만 읽히고 hazard 62% 가 빈칸).
#   그래서 **블록 경계만 찾고 라벨은 근처에서 역으로 뽑는다** — hazard 는 블록 위로
#   거슬러 가장 가까운 재해 낱말, crop 은 블록 위 25줄의 작물 이름.
#   번호가 '1' 이든 '가' 이든, 제목이 한 줄이든 두 줄이든 이 방식은 상관하지 않는다.
# ─────────────────────────────────────────────────────────────────────

_회보호수 = re.compile(r"제(\d+)호")
# Ⅱ장 머리. 'Ⅱ' 단독줄(구형)과 'Ⅱ  농작물 피해 예방 관리기술'(2026 신형)을 둘 다 받는다
_Ⅱ장 = re.compile(r"^\s*Ⅱ(\s*$|[.\s]\s*농작물)")
_Ⅲ장 = re.compile(r"^\s*Ⅲ(\s|\.|$)")

# 블록 머리 두 꼴. 【사전대책】(구형) · (가) 사전대책(2026 제3·4호는 【】 를 아예 안 쓴다)
_블록꼴 = (
    re.compile(r"^\s*【\s*(.+?)\s*】\s*$"),
    re.compile(r"^\s*\([가나다라마]\)\s*(.{1,20}?)\s*$"),
)
# 블록 이름에 이 말이 있어야 대책 단계다. 【최근 10년 특보 현황】 같은 표 제목을 거른다
_단계말 = re.compile(r"사전\s*대책|사후\s*대책|발생\s*전|발생\s*시|발생\s*후|종료\s*후|예방|대책")
_본문줄 = re.compile(r"^\s*[○◦•\-–※]")

# 재해 이름을 열 가지로 닫는다. 왼쪽이 저장값, 오른쪽은 본문에 나오는 말들.
# 닫지 않으면 '작물별관리대책' 같은 절 제목이 그대로 hazard 가 된다(실측 30건).
# '동해' 에 저온·서리·한파를 몰아넣은 것은 crop_disaster_rules 의 rule_kind 와
# 맞추기 위해서다 — 저쪽은 frost/heat 두 갈래다
_재해표 = {
    "집중호우": ("집중호우", "호우", "침수", "침관수", "폭우"),
    "태풍": ("태풍",),
    "강풍": ("강풍", "돌풍"),
    "폭염": ("폭염", "고온해", "고온"),
    "대설": ("대설", "폭설"),
    "동해": ("동해", "언 피해", "언피해", "서릿발", "한파", "저온", "냉해", "서리"),
    "우박": ("우박",),
    "황사": ("황사",),
    "일조부족": ("일조부족", "일조 부족"),
    "가뭄": ("가뭄", "한발"),
}


def _재해(줄):
    """
    # summary
    한 줄에서 재해 하나를 찾는다. 공백을 지우고 견준다 — 원본이 '언 피해' 처럼 띄운다.

    # params
    줄: 검사할 줄. 제목이든 본문이든 상관없다<br>

    # returns
    _재해표 의 정본 이름. 없으면 None
    """
    평 = "".join(줄.split())
    for 정본, 별칭들 in _재해표.items():
        if any("".join(a.split()) in 평 for a in 별칭들):
            return 정본
    return None


def _단계(이름):
    """
    # summary
    블록 이름을 여섯 단계로 접는다. '강풍발생 전' → '발생전'.

    # params
    이름: 블록 머리에서 꺼낸 이름<br>

    # returns
    사전대책 · 사후대책 · 발생전 · 발생시 · 발생후 · 종료후 중 하나. 값이 닫혀 있어야
    나중에 phase 로 거를 수 있다
    """
    평 = "".join(이름.split())
    for k in ("사전대책", "사후대책", "발생전", "발생시", "발생후", "종료후"):
        if k in 평:
            return k
    return "사전대책" if "예방" in 평 else "사후대책"


def disaster_bulletins():
    """
    # summary
    월간회보 44호의 Ⅱ장에서 대책 블록을 뽑는다. 블록 하나가 문서 하나다.

    # params
    없다. 원본 경로는 모듈 상수 `원본` 에서 읽는다 — 원본/재해예방정보/본문/*월간회보*.txt<br>

    # returns
    계약("disaster_bulletins.csv") 순서의 dict 목록. 호마다 ordinal 이 1부터 다시 센다

    # examples
        len(disaster_bulletins())  -> 1881   (44호 · 2023~2026)
    """
    행들 = []
    for path in sorted((원본 / "재해예방정보" / "본문").glob("*월간회보*.txt")):
        m = _회보호수.search(path.name)
        if not m:
            print(f"  ⚠ 호수 못 읽음: {path.name}")
            continue
        year, month = int(path.name[:4]), int(m.group(1))

        # 빈 줄과 잡음을 먼저 걷어낸다. 아래 규칙이 '몇 줄 위' 를 세므로 여기서 한 번에 치운다.
        # 옛 코드가 37/44 에서 멈춘 것도 번호줄과 제목줄 사이의 빈 줄 때문이었다
        줄들 = [l for l in 읽기(path) if l.strip() and not _잡음.match(l)]

        # Ⅱ장 머리는 목차에도 있다. **마지막** 것이 본문이다 — 목차는 언제나 앞에 온다
        후보 = [i for i, l in enumerate(줄들) if _Ⅱ장.match(l)]
        if not 후보:
            print(f"  ⚠ Ⅱ장 못 찾음: {path.name}")
            continue
        시작 = 후보[-1]
        끝 = next((i for i in range(시작 + 1, len(줄들)) if _Ⅲ장.match(줄들[i])), len(줄들))
        본 = 줄들[시작:끝]

        # ① 블록 경계만 모은다. 서식에 기대는 곳은 여기 하나뿐이다
        경계 = []
        for i, s in enumerate(본):
            for 꼴 in _블록꼴:
                g = 꼴.match(s)
                if g and _단계말.search(g.group(1)):
                    경계.append((i, g.group(1)))
                    break

        ordinal = 0
        for n, (i, 이름) in enumerate(경계):
            j = 경계[n + 1][0] if n + 1 < len(경계) else len(본)
            줄모음 = [t.strip() for t in 본[i + 1:j]
                      if _본문줄.match(t) or len(t.strip()) >= 15]
            if not 줄모음:
                continue

            # ② hazard — 블록에서 위로 거슬러 가장 가까운 재해 낱말. 절 제목이 대개 여기 걸린다.
            #    120줄은 한 블록이 앞 제목에서 떨어질 수 있는 거리다(표·그림 캡션이 사이에 낀다)
            hazard = next(
                (_재해(본[k]) for k in range(i, max(i - 120, -1), -1) if _재해(본[k])), None
            )

            # ③ crop — 블록 위 25줄에서 가까운 것부터. 작물 소절이 '1) 배' 든 '가  사과' 든
            #    '【사 과】' 든 이름만 있으면 crops_in_line 이 찾는다
            crops = set()
            for k in range(i, max(i - 25, -1), -1):
                crops = crops_in_line(본[k])
                if crops:
                    break

            phase = _단계(이름)
            # 상한을 넘으면 줄 경계에서 잘라 여러 문서로 낸다(pest_bulletins 와 같은 이유 —
            # 한 문서가 길면 chunker 가 만든 조각들의 title 이 전부 같아 구분이 안 된다)
            for 조각 in _토막내기(줄모음, 문서상한):
                if len(조각) < 40:
                    continue
                if hazard is None:
                    hazard = _재해(조각[:300])
                if not crops:
                    crops = crops_in_line(조각[:200])
                ordinal += 1
                행들.append({
                    "issue_year": year, "issue_month": month, "ordinal": ordinal,
                    "hazard": hazard or "", "crop_names": ",".join(sorted(crops)),
                    "phase": phase, "body": 조각, "source_file": path.name,
                })
    return 행들


STEPS = {
    "weekly": ("weekly_notes.csv", weekly),
    "pest_alerts": ("pest_alerts.csv", pest_alerts),
    "pest": ("pest_bulletins.csv", pest_bulletins),
}
STEPS["disaster"] = ("disaster_bulletins.csv", disaster_bulletins)


def main():
    고를것 = sys.argv[1:] or list(STEPS)
    for name in 고를것:
        파일, fn = STEPS[name]
        print(f"{name}")
        쓰기(파일, fn())


if __name__ == "__main__":
    main()
