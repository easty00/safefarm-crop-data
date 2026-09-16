# 농사로 작목별농업기술정보(cropEbook)의 본문 파일이 정말 못 받는지 다시 확인하는 스크립트입니다.
# 자세한 사용법은 "작목별기술정보_재확인_사용법.md" 를 읽어주세요.
#
# 로드맵 §2-5 는 "본문은 막혀 있다"고 적어뒀는데, 그 근거는 수박 한 건뿐입니다.
# 표본 1개로 내린 결론이라 작목 여러 개로 다시 확인합니다.
#
# 확인 방법: cropsEbookFile 주소로 실제로 받아보고, 돌아온 게
#   진짜 파일(PDF/ZIP)인지  오류 안내 HTML인지  를 앞 몇 바이트로 가른다.

import csv
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

BASE = "http://api.nongsaro.go.kr/service/cropEbook"
FILE_HOST = "https://www.nongsaro.go.kr"
HERE = Path(__file__).resolve().parent
OUT = HERE / "탐사결과" / "작목별기술정보"
RAW = OUT / "raw"
FILES = OUT / "받은파일"
WAIT = 0.4
BAD_CHARS = '\\/:*?"<>|'


def api_key() -> str:
    """.env 의 AGRI_API 값을 읽는다. 키를 코드에 적어두지 않기 위해서다."""
    env = HERE / ".env"
    if not env.exists():
        sys.exit(f".env 가 없습니다: {env}")
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("AGRI_API="):
            return line.split("=", 1)[1].strip()
    sys.exit(".env 안에서 AGRI_API 를 찾지 못했습니다.")


def safe(name: str) -> str:
    return "".join("_" if ch in BAD_CHARS else ch for ch in name).strip() or "이름없음"


def fetch(url: str) -> tuple[bytes, str]:
    """내용과 함께 서버가 말한 형식(Content-Type)도 받아온다.

    오류 안내 페이지도 200 으로 돌아오기 때문에, 상태코드만 봐서는 성공인지 알 수 없다.
    """
    with urllib.request.urlopen(url, timeout=120) as res:
        return res.read(), res.headers.get("Content-Type", "")


def call(operation: str, save_as: str, **params) -> ET.Element:
    """API 를 부르고 원문을 raw 에 저장한 뒤 파싱해 돌려준다. 이미 있으면 다시 안 부른다."""
    path = RAW / f"{safe(save_as)}.xml"
    if path.exists():
        return ET.fromstring(path.read_bytes())

    query = urllib.parse.urlencode({"apiKey": KEY, **params})
    data, _ = fetch(f"{BASE}/{operation}?{query}")

    root = ET.fromstring(data)
    code = root.findtext("./header/resultCode", "")
    if code != "00":
        raise RuntimeError(f"resultCode {code}: {root.findtext('./header/resultMsg', '')}")

    path.write_bytes(data)
    time.sleep(WAIT)
    return root


def rows(root: ET.Element) -> list[dict]:
    return [{child.tag: (child.text or "").strip() for child in item} for item in root.iter("item")]


def judge(data: bytes, content_type: str) -> tuple[str, str]:
    """받아온 것이 진짜 파일인지 오류 안내 페이지인지 가른다. (판정, 설명) 을 돌려준다."""
    head = data[:5]
    if head[:4] == b"%PDF":
        return "성공(PDF)", ""
    if head[:2] == b"PK":
        return "성공(ZIP/한글)", ""
    if head[:4] == b"\xd0\xcf\x11\xe0":
        return "성공(구형한글)", ""

    if not data:
        return "실패(빈응답)", "0바이트"

    # 오류는 대개 HTML 안내 페이지로 돌아온다
    text = data[:2000].decode("utf-8", errors="ignore")
    if not text.strip():
        # 내용은 있는데 글자로 안 읽힌다 = 우리가 모르는 바이너리. 실패로 단정하면 안 된다
        return "알수없음", f"{content_type} / 앞바이트 {data[:8]!r} / {len(data)}바이트"
    lowered = text.lower()
    if "<html" in lowered or "<!doctype" in lowered or "<script" in lowered:
        for mark in ["선택한 페이지를 찾을 수 없습니다", "페이지를 찾을 수 없",
                     "잘못된 접근", "오류", "error"]:
            if mark in text or mark in lowered:
                return "실패(안내페이지)", mark
        return "실패(HTML)", " ".join(text.split())[:80]
    return "알수없음", f"{content_type} / {data[:40]!r}"


def walk_crops(limit: int | None, only: str | None) -> list[dict]:
    """대분류 -> 중분류 -> 소분류(작목) 를 훑는다."""
    crops = []
    for main in rows(call("mainCategoryList", "main")):
        mcode, mnm = main.get("mainCategoryCode", ""), main.get("mainCategoryNm", "")
        if not mcode:
            continue
        middles = rows(call("middleCategoryList", f"middle_{mcode}", mainCategoryCode=mcode))
        print(f"  {mnm}({mcode}) 중분류 {len(middles)}개")
        for mid in middles:
            dcode, dnm = mid.get("middleCategoryCode", ""), mid.get("middleCategoryNm", "")
            if not dcode:
                continue
            subs = rows(call("subCategoryList", f"sub_{dcode}", middleCategoryCode=dcode))
            for sub in subs:
                crops.append({
                    "대분류": mnm, "중분류": dnm,
                    "작목코드": sub.get("subCategoryCode", ""),
                    "작목명": sub.get("subCategoryNm", ""),
                })
    if only:
        crops = [c for c in crops if only in c["작목명"]]
    return crops[:limit] if limit else crops


def try_ebooks(crops: list[dict]) -> list[dict]:
    """작목마다 길잡이 목록을 받고, 본문 파일을 실제로 받아본다."""
    FILES.mkdir(parents=True, exist_ok=True)
    attempts = []

    for i, crop in enumerate(crops, 1):
        code, name = crop["작목코드"], crop["작목명"]
        try:
            books = rows(call("ebookList", f"ebook_{code}", subCategoryCode=code))
        except Exception as err:
            print(f"  [{i}/{len(crops)}] {name} … 길잡이 목록 실패: {err}")
            continue

        crop["길잡이수"] = len(books)
        if not books:
            print(f"  [{i}/{len(crops)}] {name} … 길잡이 없음")
            continue

        for book in books:
            ebook_code = book.get("ebookCode", "")
            file_no = book.get("cropsEbookFileNo", "")
            url = (book.get("cropsEbookFile") or "").strip()
            row = {
                "작목": name, "작목코드": code,
                "ebookCode": ebook_code, "cropsEbookFileNo": file_no,
                "길잡이명": book.get("ebookName", ""),
                "파일명": book.get("orginlFileNm", ""),
                "주소": url,
                "판정": "", "크기": "", "비고": "",
            }

            # 목차는 되는지도 같이 본다 - 로드맵은 목차까지는 된다고 적어뒀다
            try:
                index = rows(call("cropIndexList", f"idx_{ebook_code}_{file_no}",
                                  ebookCode=ebook_code, cropsEbookFileNo=file_no))
                row["목차항목수"] = len(index)
            except Exception as err:
                row["목차항목수"] = f"실패: {err}"

            if not url:
                row["판정"] = "주소없음"
                attempts.append(row)
                print(f"  [{i}/{len(crops)}] {name} / {row['길잡이명'][:20]} … 주소 없음")
                continue

            full = url if url.startswith("http") else f"{FILE_HOST}/{url.lstrip('/')}"
            row["주소"] = full
            try:
                data, ctype = fetch(full)
                time.sleep(WAIT)
            except Exception as err:
                row["판정"], row["비고"] = "실패(요청오류)", str(err)[:120]
                attempts.append(row)
                print(f"  [{i}/{len(crops)}] {name} … 요청 실패: {err}")
                continue

            verdict, note = judge(data, ctype)
            row["판정"], row["크기"], row["비고"] = verdict, len(data), note
            if verdict.startswith("성공"):
                out = FILES / safe(f"{name}_{row['파일명'] or ebook_code}")
                out.write_bytes(data)
                row["비고"] = f"저장: {out.name}"
            attempts.append(row)
            print(f"  [{i}/{len(crops)}] {name} / {row['길잡이명'][:20]} … "
                  f"{verdict} ({len(data):,}바이트, 목차 {row['목차항목수']}개)")

    return attempts


def write_report(crops: list[dict], attempts: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    def dump(name: str, data: list[dict]) -> None:
        if not data:
            return
        keys = sorted({k for r in data for k in r})
        with open(OUT / name, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(data)

    dump("작목목록.csv", crops)
    dump("다운로드시도.csv", attempts)

    verdicts = Counter(a["판정"] for a in attempts)
    ok = [a for a in attempts if a["판정"].startswith("성공")]

    out = ["# 작목별농업기술정보(cropEbook) 재확인 결과", "",
           f"작목 {len(crops)}종 / 길잡이 파일 시도 {len(attempts)}건", "",
           "## 판정", ""]
    for v, n in verdicts.most_common():
        out.append(f"- {v} : {n}건")

    out += ["", "## 결론", ""]
    if ok:
        out.append(f"**본문 파일을 받을 수 있습니다 — {len(ok)}건 성공.** "
                   f"로드맵 §2-5 의 '본문은 막혀 있다'는 표본 1개에서 나온 잘못된 결론입니다.")
        out += ["", "### 성공한 것", ""]
        for a in ok[:30]:
            out.append(f"- {a['작목']} / {a['길잡이명']} — {a['판정']} {int(a['크기']):,}바이트 ({a['비고']})")
    else:
        out.append("**한 건도 못 받았습니다.** 로드맵 §2-5 의 판단이 맞습니다. "
                   "cropEbook 은 목차까지만 주고 본문은 주지 않습니다.")

    index_ok = [a for a in attempts if isinstance(a.get("목차항목수"), int) and a["목차항목수"] > 0]
    out += ["", "## 목차 조회(cropIndexList)", "",
            f"- 목차가 나온 길잡이 {len(index_ok)}건 / 시도 {len(attempts)}건"]
    for a in index_ok[:10]:
        out.append(f"  - {a['작목']} / {a['길잡이명']} : 목차 {a['목차항목수']}개")

    out += ["", "## 작목별 길잡이 수", ""]
    for c in crops:
        n = c.get("길잡이수", "-")
        out.append(f"- {c['대분류']} > {c['중분류']} > {c['작목명']} : {n}")

    (OUT / "요약.md").write_text("\n".join(out), encoding="utf-8")


def main() -> None:
    limit = 20
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    if "--all" in sys.argv:
        limit = None
    only = None
    if "--crop" in sys.argv:
        only = sys.argv[sys.argv.index("--crop") + 1]

    RAW.mkdir(parents=True, exist_ok=True)

    print("[1/2] 대분류 → 중분류 → 작목 을 훑습니다")
    crops = walk_crops(limit, only)
    print(f"  확인 대상 작목 {len(crops)}종\n")

    print("[2/2] 작목마다 길잡이 본문 파일을 실제로 받아봅니다")
    attempts = try_ebooks(crops)

    write_report(crops, attempts)
    print(f"\n끝났습니다. 결과: {OUT}")
    print("  요약.md 를 저에게 보여주시면 됩니다")


if __name__ == "__main__":
    KEY = api_key()
    main()
