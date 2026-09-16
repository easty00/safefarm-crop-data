# -*- coding: utf-8 -*-
"""
스캔 PDF·사진 첨부를 Windows 내장 OCR 로 글자화한다.

원본검수_2026-09-15.md §3 : 품종정보 첨부 1,140개 PDF 중 191개가 글자층이 없는 스캔본이라
본문 txt 가 200바이트 미만이다. 사진(JPEG) 14건은 본문 자체가 없다.
파싱 문제가 아니라 원본에 글자가 없는 것이라 OCR 말고는 방법이 없다.

Windows 10/11 의 Windows.Media.Ocr 을 쓴다(이 PC 에 한국어 인식기 있음을 확인함).
tesseract·torch 설치가 필요 없고 인터넷도 쓰지 않는다.

    python ocr.py             결과/ocr본문/ 에 저장. 원본 본문은 안 건드린다
    python ocr.py --반영       위 결과를 각 서비스의 본문/ 으로 덮어쓴다
    python ocr.py --골라 236307  파일 경로에 이 말이 든 것만
    python ocr.py --다시       이미 만든 것도 다시 (기본은 이어받기)
"""
import os
import sys
import io
import re
import csv
import time
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "보정", "결과", "ocr본문")
LOG = os.path.join(ROOT, "보정", "결과", "ocr_결과.csv")

MIN_BYTES = 200   # 이보다 작으면 "글자가 안 뽑힌 것" 으로 본다
DPI = 300
MAXPX = 4200      # 더 키워도 정확도가 안 오르고 느려지기만 한다

서비스들 = [
    ("품종정보", "첨부"),
    ("농작업일정", "첨부"),
    ("재해예방정보", "파일"),
    ("병해충발생정보", "파일"),
    ("주간농사정보", "첨부"),
]


def 앞바이트(p):
    """확장자를 믿지 않는다. 이름과 내용이 어긋난 파일이 실제로 있다."""
    with open(p, "rb") as f:
        h = f.read(8)
    if h[:4] == b"%PDF":
        return "PDF"
    if h[:2] == b"PK":
        return "hwpx"
    if h[:4] == b"\xd0\xcf\x11\xe0":
        return "hwp"
    if h[:4] == b"HWP ":
        return "HWP3"
    if h[:3] == b"\xff\xd8\xff":
        return "JPEG"
    if h[:8] == b"\x89PNG\r\n\x1a\n":
        return "PNG"
    if h[:3] == b"GIF":
        return "GIF"
    if h[:2] == b"BM":
        return "BMP"
    return "기타"


def 짝찾기(첨부폴더, 본문폴더):
    """첨부 ↔ 본문 txt 를 파일명 앞 숫자(cntntsNo)로 맞춘다.

    이름 뒷부분은 서로 다르다(첨부는 문서제목, 본문은 품종명).
    통째로 맞대면 2,471건이 "없음" 으로 잘못 나온다. 실제로 그렇게 헛다리를 짚었다.
    """
    def key(f):
        m = re.match(r"^(\d+)_", f)
        return m.group(1) if m else None

    첨부 = {}
    for r, _, fs in os.walk(첨부폴더):
        for f in fs:
            k = key(f)
            if k:
                첨부.setdefault(k, os.path.join(r, f))
    본문 = {}
    for r, _, fs in os.walk(본문폴더):
        for f in fs:
            k = key(f)
            if k:
                본문.setdefault(k, os.path.join(r, f))
    return 첨부, 본문


def 대상모으기():
    """OCR 이 필요한 첨부만 고른다 — 본문이 없거나 너무 짧은 것 중 그림 형식."""
    일감 = []
    for svc, sub in 서비스들:
        첨부폴더 = os.path.join(ROOT, svc, "결과", sub)
        본문폴더 = os.path.join(ROOT, svc, "결과", "본문")
        if not os.path.isdir(첨부폴더):
            continue
        첨부, 본문 = 짝찾기(첨부폴더, 본문폴더)
        for k, ap in sorted(첨부.items()):
            tp = 본문.get(k)
            크기 = os.path.getsize(tp) if tp else -1
            if 크기 >= MIN_BYTES:
                continue
            fmt = 앞바이트(ap)
            if fmt not in ("PDF", "JPEG", "PNG", "GIF", "BMP"):
                continue   # hwp/hwpx 가 비었다면 추출기를 고칠 일이지 OCR 할 일이 아니다
            기준 = tp if tp else ap
            상대 = os.path.relpath(기준, os.path.join(ROOT, svc, "결과"))
            일감.append(dict(서비스=svc, id=k, 첨부=ap, 형식=fmt, 크기=크기, 상대=상대))
    return 일감


def 그림들(경로, 형식):
    """PDF 는 쪽마다 그림으로 그리고, 사진은 그대로 넘긴다."""
    from PIL import Image

    if 형식 == "PDF":
        import pymupdf

        doc = pymupdf.open(경로)
        try:
            for i, pg in enumerate(doc):
                pix = pg.get_pixmap(dpi=DPI)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                if max(img.size) > MAXPX:
                    r = MAXPX / max(img.size)
                    img = img.resize((int(img.width * r), int(img.height * r)))
                yield i + 1, img
        finally:
            doc.close()
    else:
        img = Image.open(경로)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        if max(img.size) > MAXPX:
            r = MAXPX / max(img.size)
            img = img.resize((int(img.width * r), int(img.height * r)))
        yield 1, img


def 읽기(img, 언어="ko"):
    import winocr

    r = winocr.recognize_pil_sync(img, 언어)
    return r["text"] if isinstance(r, dict) else r.text


def 저장경로(w):
    p = os.path.join(OUT, w["서비스"], w["상대"])
    if not p.lower().endswith(".txt"):
        p = os.path.splitext(p)[0] + ".txt"
    return p


def 반영하기():
    """결과/ocr본문/ 을 각 서비스의 본문/ 으로 옮긴다.

    OCR 로 읽은 글임을 첫 줄에 적어 둔다. 사람이 값을 옮길 때 원문과 구분해야 한다.
    """
    옮김 = 0
    for r, _, fs in os.walk(OUT):
        for f in fs:
            src = os.path.join(r, f)
            if os.path.getsize(src) < MIN_BYTES:
                continue
            rel = os.path.relpath(src, OUT).split(os.sep)
            svc, 나머지 = rel[0], os.sep.join(rel[1:])
            dst = os.path.join(ROOT, svc, "결과", 나머지)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with io.open(src, encoding="utf-8") as a:
                글 = a.read()
            with io.open(dst, "w", encoding="utf-8", newline="") as b:
                b.write("(OCR 로 읽은 글입니다. 원본에 글자층이 없는 스캔본입니다.)\n\n" + 글)
            옮김 += 1
    print(f"본문/ 으로 반영 {옮김}건")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--반영", action="store_true", help="결과를 각 서비스 본문/ 으로 덮어쓴다")
    ap.add_argument("--다시", action="store_true", help="이미 만든 것도 다시 한다")
    ap.add_argument("--골라", default=None, help="첨부 경로에 이 말이 든 것만")
    ap.add_argument("--언어", default="ko")
    a = ap.parse_args()

    if a.반영 and not os.path.isdir(OUT):
        print("먼저 python ocr.py 를 돌려 결과를 만드십시오.")
        return

    일감 = 대상모으기()
    if a.골라:
        일감 = [w for w in 일감 if a.골라 in w["첨부"]]
    print(f"OCR 대상 {len(일감)}건")

    os.makedirs(OUT, exist_ok=True)
    기록 = []
    시작 = time.time()
    건너뜀 = 0
    for n, w in enumerate(일감, 1):
        저장 = 저장경로(w)
        os.makedirs(os.path.dirname(저장), exist_ok=True)
        if os.path.exists(저장) and os.path.getsize(저장) > 0 and not a.다시:
            건너뜀 += 1
            continue
        쪽들 = []
        try:
            for 쪽, img in 그림들(w["첨부"], w["형식"]):
                쪽들.append("===== p.%d =====\n%s" % (쪽, 읽기(img, a.언어)))
        except Exception as e:
            # 실패는 저장하지 않는다. 저장하면 다음 실행 때 건너뛰어 영영 모르게 된다.
            기록.append(dict(서비스=w["서비스"], id=w["id"], 첨부=os.path.basename(w["첨부"]),
                            형식=w["형식"], 원래크기=w["크기"], 쪽수=0, 글자수=0,
                            한글비율="", 결과="실패: %s" % e))
            print("  [%d/%d] 실패 %s : %s" % (n, len(일감), os.path.basename(w["첨부"])[:40], e))
            continue
        글 = "\n\n".join(쪽들)
        with io.open(저장, "w", encoding="utf-8", newline="") as f:
            f.write(글)
        한글 = sum(1 for c in 글 if "가" <= c <= "힣")
        기록.append(dict(서비스=w["서비스"], id=w["id"], 첨부=os.path.basename(w["첨부"]),
                        형식=w["형식"], 원래크기=w["크기"], 쪽수=len(쪽들), 글자수=len(글),
                        한글비율="%.2f" % (한글 / max(len(글), 1)), 결과="ok"))
        if n % 10 == 0 or n == len(일감):
            print("  [%d/%d] %s %d자 / 누적 %.0f초"
                  % (n, len(일감), os.path.basename(w["첨부"])[:38], len(글), time.time() - 시작))
            sys.stdout.flush()

    if 건너뜀:
        print("이미 되어 있어 건너뜀 %d건" % 건너뜀)
    if 기록:
        처음 = not os.path.exists(LOG)
        with io.open(LOG, "w" if 처음 else "a", encoding="utf-8-sig", newline="") as f:
            wr = csv.DictWriter(f, fieldnames=list(기록[0].keys()))
            if 처음:
                wr.writeheader()
            wr.writerows(기록)
        성공 = sum(1 for r in 기록 if r["결과"] == "ok")
        print("\n새로 읽은 것 %d건 (실패 %d) → %s" % (성공, len(기록) - 성공, LOG))

    if a.반영:
        반영하기()


if __name__ == "__main__":
    main()
