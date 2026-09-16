# 지금까지 수집·추출한 것을 기계적으로 점검하는 스크립트입니다.
# 자세한 사용법은 같은 폴더의 "사용법.md" 를 읽어주세요.
#
# 새로 내려받는 것은 없습니다. 이미 있는 결과만 읽습니다.
#
# 지금까지 놓쳤다가 뒤늦게 찾은 실수가 아홉 건인데, 원인이 거의 같습니다.
#
#   한 표본만 보고 형식을 단정했다.
#
# 그래서 일곱 가지를 봅니다.
#
#   ① 응답 칸 누락   raw XML 의 값이 CSV 어딘가에 살아 있나
#   ② 건수 어긋남     목록 수 = 받은 수 = 판독 수 인가
#   ③ 형식 편차       연도별로 추출량이 갑자기 떨어지는 구간이 있나
#   ④ 범위 벗어남     온도 -60~60, 월 1~24, 일수 1~400 을 넘는 숫자
#   ⑤ 버려진 표       격자로 뜯어놓고 아무 데도 안 쓴 표
#   ⑥ 검사 범위       결과 표를 하나도 안 본 채 넘어가지 않았나
#   ⑦ 뜻 검사        숫자가 범위 안이어도 뜻이 어긋난 것        ★ 나중에 덧붙임
#
# ⚠ **①~⑥ 만으로는 아무것도 못 잡는다는 걸 확인했습니다.**
# 사람이 원문을 읽어 찾은 잘못 다섯 건(생육일수가 대조 품종과의 차이값 · 제초제 살포
# 간격을 재배일수로 · 표 머리글을 값으로 · 추대 경보값을 목표 적산온도로 · 학명을
# 재해 대책으로)을 **한 건도 못 잡았습니다.** 숫자가 전부 범위 안이었기 때문입니다.
#
# 그래서 ⑦ 을 넣었습니다. 그래도 이 점검은 **읽을 곳을 좁혀줄 뿐**이고,
# "통과 = 자료가 옳다" 가 아닙니다. 판정은 원문을 읽어야 나옵니다.

import csv
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "결과"

# 서비스마다 (폴더, 목록 CSV, raw 폴더, 파일 폴더, 본문 폴더)
SERVICES = {
    "농작업일정": {"csv": "작물목록.csv", "raw": "raw", "files": "첨부", "texts": "본문"},
    "품종정보": {"csv": "품종목록.csv", "raw": "raw", "files": "첨부", "texts": "본문"},
    "재해예방정보": {"csv": "목록.csv", "raw": "raw", "files": "파일", "texts": "본문"},
    "주간농사정보": {"csv": "목록.csv", "raw": "raw", "files": "첨부", "texts": "본문"},
    "병해충발생정보": {"csv": "목록.csv", "raw": "raw", "files": "파일", "texts": "본문"},
}

# ④ 값이 이 범위를 벗어나면 의심한다
SANE = {
    "온도": (-60.0, 60.0),
    # 농사로는 **해를 넘기는 작업의 종료월을 13~18 로** 적는다(13=이듬해 1월).
    # 12 로 막으면 월동작물 94행이 전부 이상치로 걸린다. 진짜 오류만 잡게 24 까지 둔다
    "월": (1, 24),
    "일": (1, 31),
    "일수": (1, 400),
}


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def num(value: str):
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return None


def nospace(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


# ---------- ① 응답 칸 누락 ----------

def check_fields() -> list[dict]:
    """raw XML 의 값이 CSV 안에 살아 있는지 본다.

    예전에 농작업일정에서 응답 13칸 중 3칸만 쓰고 나머지를 버린 적이 있다.
    오류가 안 나기 때문에 세어보지 않으면 영영 모른다.

    ⚠ 태그 **이름**으로 맞대면 안 된다. 우리 스크립트는 칸 이름을 한글로 바꿔 담는다
    (`beginMon` → `시작월`). 이름으로 세면 멀쩡히 담긴 칸이 전부 '없음' 으로 나온다.
    실제로 그렇게 40개가 거짓으로 걸렸다.

    그래서 **값**을 본다. 태그마다 실제 값을 몇 개 뽑아 CSV 어딘가에 그 값이 있는지 센다.
    """
    out = []
    for name, cfg in SERVICES.items():
        base = ROOT / name / "결과"
        raw = base / cfg["raw"]
        if not raw.exists():
            continue

        # ⚠ 앞 파일에서만 표본을 뽑으면 안 된다. raw 에는 목록을 받은 해가 다 들어 있고
        # CSV 는 고른 해만 담는데, 표본이 전부 2011년에서 뽑히면 0/25 가 나와 오보가 된다.
        # 실제로 재해예방정보 다섯 칸이 그렇게 '누락' 으로 잘못 걸렸다. 파일마다 골고루 뽑는다
        per_file = defaultdict(lambda: defaultdict(list))
        counts = Counter()
        files = sorted(raw.glob("*.xml"))
        for x in files:
            try:
                root = ET.fromstring(x.read_bytes())
            except Exception:
                continue
            for item in root.iter("item"):
                for c in item:
                    v = (c.text or "").strip()
                    if not v:
                        continue
                    counts[c.tag] += 1
                    # 너무 짧은 값은 우연히 다른 칸에서 걸리므로 쓸모가 없다
                    if len(v) >= 3 and len(per_file[x.name][c.tag]) < 4:
                        if v not in per_file[x.name][c.tag]:
                            per_file[x.name][c.tag].append(v)

        # 파일 순서대로 채우면 앞 연도에서 40개가 다 차버린다. **번갈아** 뽑는다
        samples = defaultdict(list)     # 태그 → 값 표본
        names = list(per_file)
        for k in range(4):
            for fname in names:
                for tag, vals in per_file[fname].items():
                    if k < len(vals) and len(samples[tag]) < 40:
                        if vals[k] not in samples[tag]:
                            samples[tag].append(vals[k])
        if not counts:
            continue

        # 그 서비스의 모든 CSV 값을 한 덩어리로 모은다
        blob = set()
        for csvfile in base.rglob("*.csv"):
            for r in read_csv(csvfile):
                for v in r.values():
                    v = (v or "").strip()
                    if v:
                        blob.add(v)
        joined = "\n".join(blob)        # 잘려 담긴 값도 잡으려고 통글도 만든다

        # raw 에는 목록을 받은 해가 다 들어 있지만 CSV 는 우리가 고른 해만 담는다.
        # (재해예방정보 raw 16년치 ↔ CSV 4년치) 그래서 '일부만' 은 누락이 아니라 범위 차이다
        for tag, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            vals = samples[tag]
            if not vals:
                # 값이 두 글자 이하라 우연히 다른 칸에서 걸린다. 판정하지 않는다
                out.append({"서비스": name, "응답칸": tag, "값이있는건수": n,
                            "표본": 0, "CSV에서찾음": 0,
                            "판정": "-", "비고": "값이 짧아 확인 못함"})
                continue
            found = sum(1 for v in vals if v in blob or v[:60] in joined)
            ratio = found / len(vals)
            if ratio >= 0.5:
                verdict, note = "O", ""
            elif found > 0:
                verdict, note = "일부만", "받은 해·분류만 CSV 에 담겨 그럴 수 있음"
            else:
                verdict, note = "**없음**", ""
            out.append({"서비스": name, "응답칸": tag, "값이있는건수": n,
                        "표본": len(vals), "CSV에서찾음": found,
                        "판정": verdict, "비고": note})
    return out


# ---------- ② 건수 어긋남 ----------

def check_counts() -> list[dict]:
    out = []
    for name, cfg in SERVICES.items():
        base = ROOT / name / "결과"
        if not base.exists():
            continue
        rows = read_csv(base / cfg["csv"])
        files = [p for p in (base / cfg["files"]).rglob("*.*") if p.is_file()] \
            if (base / cfg["files"]).exists() else []
        texts = [p for p in (base / cfg["texts"]).rglob("*.txt")] \
            if (base / cfg["texts"]).exists() else []
        empty = [p for p in files if p.stat().st_size == 0]
        out.append({"서비스": name, "목록": len(rows), "받은파일": len(files),
                    "본문": len(texts), "0바이트": len(empty),
                    "용량MB": round(sum(p.stat().st_size for p in files) / 1e6)})
    return out


# ---------- 결과 파일 모으기 ----------

TOUCHED: set[str] = set()       # 어떤 검사든 한 번이라도 읽은 파일


def all_results() -> list[Path]:
    """`<폴더>/결과/*.csv` 를 전부 찾는다.

    ⚠ 예전에는 볼 파일을 손으로 적어뒀다. 그래서 결과 파일 39개 중 22개만 보고 있었고,
    적산온도·적응지역_온도·첨부_표행 처럼 **새로 만든 표가 생겨도 검사에 안 들어왔다.**
    이름을 적는 방식은 파일이 늘 때마다 잊는다. 그래서 찾아서 쓴다.
    """
    out = []
    for folder in sorted(ROOT.glob("*/결과")):
        if folder.parent.name == HERE.name:      # 검수 자신의 결과는 뺀다
            continue
        out += sorted(folder.glob("*.csv"))
    return out


def label(path: Path) -> tuple[str, str]:
    return path.parent.parent.name, path.name


# ---------- ③ 형식 편차 ----------

GROUP_COLS = ("연도", "분류명", "계열", "작물군", "구분")


def check_drift() -> list[dict]:
    """묶음 칸(연도·분류명 등)이 있는 표를 모두 찾아 구간별 행 수를 센다.

    병해충 요약표에서 2023년만 절반 넘게 빠졌던 적이 있다. 전체 합계만 보면 안 보인다.
    """
    out = []
    for path in all_results():
        try:
            rows = read_csv(path)
        except Exception:
            continue
        if not rows:
            continue
        svc, fname = label(path)
        key = next((c for c in GROUP_COLS if c in rows[0]), None)
        if not key:
            continue
        TOUCHED.add(str(path))
        per = Counter(r.get(key, "") for r in rows)
        if len(per) < 2:
            continue
        vals = sorted(per.values())
        mid = vals[len(vals) // 2]
        for k in sorted(per):
            n = per[k]
            # 연도만 판정한다. 해마다 비슷한 양이 나오는 게 정상이라 적으면 의심스럽다.
            # 분류·계열은 원래 크기가 제각각이라(버섯 4건 ↔ 채소 58건) 적다고 이상한 게 아니다.
            # 그걸 판정하면 오보가 38건씩 쏟아져 진짜 신호를 덮는다
            flag = "**적음**" if key == "연도" and mid and n < mid * 0.5 else ""
            out.append({"서비스": svc, "파일": fname, "구분": key, "값": k or "(빈칸)",
                        "행": n, "중앙값": mid, "판정": flag})
    return out


# ---------- ④ 값 이상치 ----------

# 칸 이름에 이 말이 들어가면 그 종류로 보고 범위를 검사한다
COL_KIND = (
    (("최저", "최고", "온도", "기온"), "온도"),
    (("월",), "월"),
    (("일",), "일"),
    (("일수", "재배일수"), "일수"),
)


def kind_of(col: str) -> str | None:
    c = nospace(col)
    if c in ("일수", "최소일", "최대일", "재배일수", "지속일"):
        return "일수"
    if c == "월" or c.endswith("월"):
        return "월"
    if c == "일":
        return "일"
    if any(w in c for w in ("최저", "최고", "온도", "기온")) and "일수" not in c:
        return "온도"
    return None


def check_values() -> list[dict]:
    """모든 결과 표에서 말이 안 되는 숫자를 찾는다. 칸 이름으로 종류를 짐작한다."""
    out = []
    for path in all_results():
        try:
            rows = read_csv(path)
        except Exception:
            continue
        if not rows:
            continue
        svc, fname = label(path)
        cols = {c: kind_of(c) for c in rows[0]}
        if not any(cols.values()):
            continue
        TOUCHED.add(str(path))
        for r in rows:
            for col, kind in cols.items():
                if not kind:
                    continue
                v = num(r.get(col, ""))
                if v is None:
                    continue
                lo, hi = SANE[kind]
                if not lo <= v <= hi:
                    out.append({"서비스": svc, "파일": fname,
                                "이유": f"{kind} 범위 밖 ({col})", "값": v,
                                "원문": (r.get("원문") or r.get("조건원문")
                                        or r.get("내용") or "")[:90]})
            # 최저가 최고보다 크면 뒤집힌 것이다
            lo, hi = num(r.get("최저")), num(r.get("최고"))
            if lo is not None and hi is not None and lo > hi:
                out.append({"서비스": svc, "파일": fname, "이유": "최저가 최고보다 큼",
                            "값": f"{lo} > {hi}", "원문": (r.get("원문") or "")[:90]})
            # 벼 출수기가 겨울이면 잘못 읽은 것이다
            if (r.get("항목") == "출수기" and r.get("작물명") == "논벼"
                    and num(r.get("월")) in (11.0, 12.0, 1.0, 2.0, 3.0)):
                out.append({"서비스": svc, "파일": fname, "이유": "논벼 출수기가 겨울",
                            "값": f"{r.get('월')}.{r.get('일')}",
                            "원문": (r.get("원문") or "")[:90]})
    return out


# ---------- ⑦ 뜻 검사 ----------

# 숫자 옆에 이 말이 있으면 그 값은 '대조 품종과의 차이' 일 수 있다
COMPARE_WORDS = ("짧", "길", "늦", "빠르", "이르", "보다", "대비", "같고", "비슷")
# 값이 아니라 작업 간격을 말하는 줄
INTERVAL_WORDS = ("제초제", "방제", "살포", "약제", "소독", "물떼기", "담수", "웃거름")
LABEL_COLS = ("항목", "구분", "작업명", "생육단계", "표제목", "절")


def grid_files() -> list[Path]:
    """행·열·값 꼴의 격자 CSV 만 고른다."""
    out = []
    for path in all_results():
        try:
            rows = read_csv(path)
        except Exception:
            continue
        if rows and {"행", "열", "값", "작물명"} <= set(rows[0]):
            out.append(path)
    return out


def check_grid_clash() -> list[dict]:
    """격자 표에서 **같은 것을 가리키는데 값이 다른 것**을 찾는다.

    ⚠ 격자 CSV 는 값이 `값` 칸에 글자로 들어 있어 ④ 범위 검사도 ⑦ 무리 검사도 못 본다.
    그래서 사각지대였다. 실제로 이런 게 묻혀 있었다.

        수박 성숙기 판정 · 만생종 열매달림 후 일수
            재배법_표.csv (API HTML)   40~45일
            첨부_표.csv  (첨부 hwpx)   45~50일       ← 같은 표인데 값이 다르다

    사람이 우연히 발견했는데, 기계가 잡을 수 있는 종류다.
    **같은 작물 · 같은 행의 첫 칸(이름) · 같은 열 번호**를 열쇠로 삼아
    파일마다 값이 갈리는지 본다. 행 순서가 어긋나도 이름으로 맞추므로 견딘다.
    """
    seen = defaultdict(dict)        # (작물, 행이름, 열) → {파일: 값}
    for path in grid_files():
        rows = read_csv(path)
        TOUCHED.add(str(path))
        svc, fname = label(path)
        byrow = defaultdict(dict)
        for r in rows:
            try:
                key = (r["작물명"], r.get("표번호", ""), int(r["행"]))
            except Exception:
                continue
            byrow[key][int(r["열"])] = (r["값"] or "").strip()
        for (crop, _, _), cols in byrow.items():
            if 0 not in cols or not cols[0]:
                continue
            name = nospace(cols[0])
            if len(name) < 2:
                continue
            for c, v in cols.items():
                if c == 0 or not v or not re.search(r"\d", v):
                    continue
                seen[(crop, name, c)][fname] = v

    out = []
    for (crop, name, col), files in seen.items():
        if len(files) < 2:
            continue
        # 쉼표·공백·단위 표기 차이는 불일치가 아니다. 2,000배 = 2000배
        norm = {f: re.sub(r"[,\s]", "", v) for f, v in files.items()}
        if len({v for v in norm.values()}) < 2:
            continue
        # 긴 글(대책문·사용요령)은 한쪽이 잘렸을 뿐인 경우가 대부분이라 뺀다.
        # 숫자 비교가 목적이므로 **숫자만 뽑아 견준다**
        digits = {f: tuple(re.findall(r"\d+(?:\.\d+)?", v)) for f, v in norm.items()}
        if any(len(v) > 24 for v in norm.values()):
            continue
        if not all(digits.values()):
            continue
        if len(set(digits.values())) < 2:
            continue
        out.append({"서비스": "", "파일": " / ".join(sorted(files)),
                    "종류": "격자 값 불일치",
                    "키": f"{crop} · {name} · {col}열",
                    "값": " vs ".join(f"{f.replace('.csv','')}={v}"
                                      for f, v in sorted(files.items())),
                    "원문": ""})
    return out


def check_meaning() -> list[dict]:
    """숫자가 **범위 안이라도 뜻이 틀린 것**을 찾는다.

    ⚠ ④ 범위 검사만으로는 아무것도 못 잡는다는 걸 확인했다. 손으로 찾은 다섯 건을
    검수가 **0건** 잡았다. 생육일수 1일도 1~400 안이고, 상추 1,400℃ 도 온도로는 멀쩡하다.

    그래서 세 가지를 본다. 전부 "같은 것끼리 견줘 보면 튀는 것" 을 찾는 방식이다.

      ㉮ 무리 안 이상치   같은 작물·항목인데 중앙값의 1/5 이하이거나 5배 이상
      ㉯ 비교문 숫자      숫자가 있는데 원문에 '짧·길·늦·보다' 가 있는 것
      ㉰ 파일 간 불일치   같은 작물·같은 이름인데 파일마다 값이 다른 것

    ㉰ 는 수박 만생종 일수가 API(40~45)와 첨부(45~50)에서 달랐던 것을 잡으려는 것이다.
    이건 사람이 우연히 발견했는데, 기계가 잡을 수 있는 종류다.
    """
    out = []
    groups = defaultdict(list)      # (작물, 항목) → [(값, 파일, 원문)]

    for path in all_results():
        try:
            rows = read_csv(path)
        except Exception:
            continue
        if not rows:
            continue
        svc, fname = label(path)
        cols = rows[0]
        crop_col = next((c for c in ("작물명", "작물", "_선정작물") if c in cols), None)
        lab_col = next((c for c in LABEL_COLS if c in cols), None)
        num_cols = [c for c in cols if kind_of(c) in ("일수", "온도")]
        if not num_cols:
            continue
        TOUCHED.add(str(path))

        for r in rows:
            src = (r.get("원문") or r.get("조건원문") or r.get("내용") or "")
            for c in num_cols:
                v = num(r.get(c, ""))
                if v is None:
                    continue
                # ㉯ 비교문에서 캐낸 숫자
                if src and any(w in src for w in COMPARE_WORDS) and kind_of(c) == "일수":
                    out.append({"서비스": svc, "파일": fname, "종류": "비교문 숫자",
                                "키": f"{r.get(crop_col,'')} {r.get(lab_col,'')}".strip(),
                                "값": v, "원문": src[:90]})
                elif src and any(w in src for w in INTERVAL_WORDS):
                    out.append({"서비스": svc, "파일": fname, "종류": "작업 간격",
                                "키": f"{r.get(crop_col,'')} {r.get(lab_col,'')}".strip(),
                                "값": v, "원문": src[:90]})
                if crop_col and lab_col:
                    key = (nospace(r.get(crop_col, "")), nospace(r.get(lab_col, "")), c)
                    if key[0] and key[1]:
                        groups[key].append((v, fname, src[:70]))

    out += check_grid_clash()

    for key, vals in groups.items():
        nums = sorted(v for v, _, _ in vals)
        if len(nums) < 3:
            # ㉰ 파일이 둘 이상인데 값이 다르면 어긋난 것이다
            files = {f for _, f, _ in vals}
            uniq = {v for v, _, _ in vals}
            if len(files) > 1 and len(uniq) > 1:
                out.append({"서비스": "", "파일": " / ".join(sorted(files)),
                            "종류": "파일 간 불일치", "키": f"{key[0]} {key[1]} [{key[2]}]",
                            "값": " vs ".join(str(x) for x in sorted(uniq)),
                            "원문": vals[0][2]})
            continue
        mid = nums[len(nums) // 2]
        if mid <= 0:
            continue
        for v, f, src in vals:
            if v < mid / 5 or v > mid * 5:
                out.append({"서비스": "", "파일": f, "종류": "무리 안 이상치",
                            "키": f"{key[0]} {key[1]} [{key[2]}]",
                            "값": f"{v} (중앙 {mid})", "원문": src})
    return out


# ---------- ⑤ 버려진 표 ----------

def check_unused() -> tuple[list[dict], list[dict]]:
    """뜯어놓고 아무 규칙에도 안 쓴 표가 얼마나 되는지 센다.

    재해규칙은 네 가지 표만 알아본다. 나머지에 무엇이 들었는지는 아직 아무도 안 봤다.
    여기서 '숫자가 든 표인데 안 쓰인 것' 만 골라 머리글을 보여준다.
    """
    rules = read_csv(ROOT / "재해규칙" / "결과" / "disaster_rules_전체.csv")
    used = {(r["출처파일"], r.get("표번호", "")) for r in rules}
    refs = read_csv(ROOT / "재해규칙" / "결과" / "참고수치표.csv")
    ref_keys = {(r["출처파일"], r.get("표번호", "")) for r in refs}

    heads = defaultdict(lambda: {"n": 0, "files": set()})
    for r in refs:
        key = (r["출처파일"], r.get("표번호", ""))
        if key in used:
            continue
        h = " ".join((r.get("표머리") or "").split())
        if not h:
            continue
        heads[h]["n"] += 1
        heads[h]["files"].add(r["출처파일"])

    unused = [{"표머리": h, "칸수": v["n"], "문서수": len(v["files"])}
              for h, v in sorted(heads.items(), key=lambda kv: -kv[1]["n"])]

    summary = [{"항목": "규칙으로 쓰인 표", "수": len(used)},
               {"항목": "참고표로만 담긴 표", "수": len(ref_keys - used)},
               {"항목": "참고표 칸 수", "수": len(refs)},
               {"항목": "안 쓰인 표 머리 종류", "수": len(unused)}]

    # 농작업일정 쪽도 같이 본다
    cells = read_csv(ROOT / "농작업일정" / "결과" / "첨부_표.csv")
    temps = read_csv(ROOT / "농작업일정" / "결과" / "첨부_온도.csv")
    tkeys = {(t["파일"],) for t in temps}
    all_files = {(c["파일"],) for c in cells}
    summary.append({"항목": "농작업일정 표가 있는 첨부", "수": len(all_files)})
    summary.append({"항목": "  그중 온도를 못 뽑은 첨부", "수": len(all_files - tkeys)})
    return unused, summary


# ---------- 결과 ----------

def dump(path: Path, data: list[dict]) -> None:
    if not data:
        return
    keys = list(dict.fromkeys(k for d in data for k in d))
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(data)


def check_coverage() -> list[dict]:
    """결과 표를 하나도 안 본 채로 넘어가지 않았는지 스스로 센다.

    ⚠ 이 검사가 이 스크립트에서 가장 중요할 수 있다. 검수 도구가 무엇을 **안 보는지**
    적어두지 않으면, 검수를 통과했다는 말이 무엇을 뜻하는지 알 수 없다.
    실제로 결과 39개 중 22개만 보면서 "이상 없음" 이라고 적을 뻔했다.
    """
    out = []
    for path in all_results():
        svc, fname = label(path)
        rows = read_csv(path)
        out.append({"서비스": svc, "파일": fname, "행": len(rows),
                    "칸": len(rows[0]) if rows else 0,
                    "검사함": "O" if str(path) in TOUCHED else "**안봄**"})
    return out


def write_report(fields, counts, drift, values, unused, unused_sum, coverage,
                 meaning) -> None:
    miss = [f for f in fields if f["판정"] == "**없음**"]
    partial = [f for f in fields if f["판정"] in ("일부만", "-")]
    low = [d for d in drift if d["판정"]]

    out = ["# 수집 결과 점검", "",
           "> ⚠ **이 점검을 통과했다고 자료가 옳은 것은 아닙니다.**",
           "> 여기서 보는 것은 개수·범위·형식이고, 값의 **뜻**은 ⑦ 에서만 일부 봅니다.",
           ">",
           "> 실제로 손으로 찾은 잘못 다섯 건(생육일수가 차이값·제초제 간격을 재배일수로·",
           "> 표 머리글을 값으로·추대 경보값을 목표값으로·학명을 재해대책으로)을",
           "> ①~⑥ 은 **한 건도 잡지 못했습니다.** 숫자가 전부 범위 안이었기 때문입니다.",
           ">",
           "> 판정은 원문을 읽어야 나옵니다. 이 문서는 **읽을 곳을 좁혀줄 뿐**입니다.", "",
           "| 점검 | 결과 |", "|---|---|",
           f"| ① 값이 CSV 에서 안 보이는 응답 칸 | **{len(miss)}개** / {len(fields)}개 |",
           f"| ② 건수가 어긋난 서비스 | **{sum(1 for c in counts if c['목록'] != c['받은파일'])}개** |",
           f"| ③ 추출량이 중앙값의 절반 미만인 구간 | **{len(low)}개** |",
           f"| ④ 범위를 벗어난 숫자 | **{len(values)}개** |",
           f"| ⑤ 안 쓰인 표 머리 종류 | **{len(unused)}개** |",
           f"| ⑥ 검사가 못 본 결과 표 | "
           f"**{sum(1 for c in coverage if c['검사함'] != 'O')}개** / {len(coverage)}개 |",
           f"| ⑦ 뜻이 의심스러운 값 | **{len(meaning)}개** |", ""]

    out += ["## ① 응답 칸 누락", ""]
    if miss:
        out += ["응답에는 값이 있는데 **그 값이 CSV 어디에서도 안 보이는** 칸입니다.", "칸 이름이 아니라 값으로 맞댄 결과입니다.", "",
                "| 서비스 | 응답 칸 | 값이 있는 건수 | 표본에서 찾음 |", "|---|---|---|---|"]
        for f in miss:
            out.append(f"| {f['서비스']} | `{f["응답칸"]}` | {f["값이있는건수"]:,} | {f["CSV에서찾음"]}/{f["표본"]} |")
    else:
        out.append("없습니다. 응답 값이 전부 CSV 어딘가에 살아 있습니다.")
    out += ["", f"판정이 애매한 칸 {len(partial)}개는 `응답칸점검.csv` 에 있습니다. "
            "값이 두 글자 이하라 확인할 수 없거나, 목록은 여러 해를 받았는데 "
            "CSV 에는 고른 해만 담겨서 일부만 맞는 경우입니다."]

    out += ["", "## ② 건수", "",
            "| 서비스 | 목록 | 받은 파일 | 본문 | 0바이트 | 용량 |", "|---|---|---|---|---|---|"]
    for c in counts:
        gap = "" if c["목록"] == c["받은파일"] else f" ⚠{c['목록'] - c['받은파일']:+d}"
        out.append(f"| {c['서비스']} | {c['목록']:,} | {c['받은파일']:,}{gap} | "
                   f"{c['본문']:,} | {c['0바이트']} | {c['용량MB']:,}MB |")
    out.append("")
    out.append("목록보다 받은 파일이 적은 것은 대부분 농사로에 첨부가 없는 건입니다. "
               "각 서비스 요약.md 의 실패 목록과 맞춰 보세요.")

    out += ["", "## ③ 형식 편차 — 추출량이 갑자기 적은 구간", ""]
    if low:
        out += ["같은 자료인데 어느 구간만 적게 뽑혔다면 **형식이 다른데 못 읽은 것**일 수 있습니다.",
                "", "| 서비스 | 파일 | 구분 | 값 | 행 | 중앙값 |", "|---|---|---|---|---|---|"]
        for d in low:
            out.append(f"| {d['서비스']} | {d['파일']} | {d['구분']} | {d['값']} | "
                       f"{d['행']:,} | {d['중앙값']:,} |")
    else:
        out.append("없습니다.")

    out += ["", "## ④ 범위를 벗어난 숫자", "",
            "온도 -60~60℃, 월 1~24, 일 1~31, 일수 1~400 을 벗어난 것만 봅니다.",
            "**범위 안이면 뜻이 틀려도 여기 안 걸립니다.** 그건 ⑦ 을 보세요.", ""]
    if values:
        out += ["| 서비스 | 파일 | 이유 | 값 | 원문 |", "|---|---|---|---|---|"]
        for v in values[:60]:
            out.append(f"| {v['서비스']} | {v['파일']} | {v['이유']} | {v['값']} | {v['원문'][:50]} |")
        if len(values) > 60:
            out.append(f"| … 외 {len(values)-60}개 | | | | |")
    else:
        out.append("없습니다.")

    out += ["", "## ⑤ 뜯어놓고 안 쓴 표", ""]
    for s in unused_sum:
        out.append(f"- {s['항목']} : {s['수']:,}")
    out += ["", "**여기가 가장 중요합니다.** 표를 뜯어는 놓았는데 규칙으로 옮기지 않은 것들입니다.",
            "쓸모가 없어서가 아니라 아직 아무도 안 봤기 때문입니다.", "",
            "| 표 머리 | 칸 수 | 문서 수 |", "|---|---|---|"]
    for u in unused[:60]:
        out.append(f"| {u['표머리'][:60]} | {u['칸수']:,} | {u['문서수']} |")
    if len(unused) > 60:
        out.append(f"| … 외 {len(unused)-60}종 | | |")

    (OUT / "점검결과.md").write_text("\n".join(out), encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("[1/7] 응답 칸이 CSV 에 다 들어갔는지 봅니다")
    fields = check_fields()
    miss = [f for f in fields if f["판정"] == "**없음**"]
    partial = [f for f in fields if f["판정"] in ("일부만", "-")]
    print(f"  응답 칸 {len(fields)}개 중 CSV 에 없는 것 {len(miss)}개")

    print("[2/7] 건수를 맞춰봅니다")
    counts = check_counts()
    for c in counts:
        print(f"  {c['서비스']:12} 목록 {c['목록']:>5,} · 파일 {c['받은파일']:>5,} · "
              f"본문 {c['본문']:>5,}")

    print("[3/7] 구간별로 추출량이 튀는 곳을 찾습니다")
    drift = check_drift()
    low = [d for d in drift if d["판정"]]
    print(f"  {len(low)}개 구간이 중앙값의 절반 미만")

    print("[4/7] 말이 안 되는 값을 찾습니다")
    values = check_values()
    print(f"  {len(values)}개")

    print("[5/7] 뜯어놓고 안 쓴 표를 셉니다")
    unused, unused_sum = check_unused()
    print(f"  머리 종류 {len(unused)}가지")

    dump(OUT / "응답칸점검.csv", fields)
    dump(OUT / "건수점검.csv", counts)
    dump(OUT / "구간편차.csv", drift)
    dump(OUT / "이상치.csv", values)
    print("[6/7] 뜻이 의심스러운 값을 찾습니다")
    meaning = check_meaning()
    print(f"  {len(meaning)}건")

    print("[7/7] 검사 범위를 셉니다")
    coverage = check_coverage()
    miss = [c for c in coverage if c["검사함"] != "O"]
    print(f"  결과 표 {len(coverage)}개 중 검사 못 한 것 {len(miss)}개")

    dump(OUT / "안쓴표.csv", unused)
    dump(OUT / "검사범위.csv", coverage)
    dump(OUT / "뜻검사.csv", meaning)
    write_report(fields, counts, drift, values, unused, unused_sum, coverage, meaning)

    print(f"\n끝났습니다. 결과: {OUT}")
    print("  점검결과.md 를 저에게 보여주시면 됩니다")


if __name__ == "__main__":
    main()
