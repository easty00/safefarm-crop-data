# 원본 첨부 **전문**에서 낱말을 찾는다. 조사할 때마다 쓰는 도구.
#
#     PYTHONIOENCODING=utf-8 python feature/search_source.py 기준온도
#     python feature/search_source.py 적산온도 --서비스 농작업일정 --문맥 2
#     python feature/search_source.py 방임재배 --작물 호박
#     python feature/search_source.py 한계온도 --셈만        파일별 건수만
#
# ★ **이 파일은 실패 다섯 번의 결론이다.** 2026-09-18 세션에서 "국내 자료에 그 값이
#   없다" 는 결론을 다섯 번 냈는데 네 번은 **내가 안 읽은 것**이었다. 그때마다 조사
#   코드를 새로 짰고, 새로 짤 때마다 같은 함정을 다시 밟았다.
#
#     ① 본문/ 의 txt 변환본만 읽었다        hwpx 표 안의 "신장 : 10℃ 이상" 이 txt 에 없었다
#     ② 낱말과 ℃ 가 같은 줄에 있어야만 잡았다  머리글 행과 값 행이 갈려 있었다
#     ③ pypdf 로 읽었다                    같은 PDF 를 pymupdf 는 7배 읽었다(1,067 → 7,212자)
#     ④ 한 서비스만 뒤졌다                  찾던 값은 재해예방정보에 있었다
#     ⑤ grids_of(표만) 로 읽었다            품종정보 hwp 387개가 표 0개라 0자가 나왔다
#
#   그래서 이 도구는 **원본을 직접 읽고 · 앞뒤 줄을 같이 보여주고 · PDF 를 두 가지로
#   재보고 · 서비스를 안 고르면 전부 훑고 · 0자 파일을 세어 알린다.**
#
# ⚠ **0자 파일 수를 반드시 본다.** 맞은 줄이 0 이라도 0자 파일이 많으면 그것은
#   "없다" 가 아니라 "못 읽었다" 다. 둘을 가르지 못하면 또 헛결론이 난다.
#
# ⚠ 사진(JPEG)은 글자가 없는 게 맞다. 실패가 아니라 따로 센다 — 스캔 PDF 는
#   `feature/ocr.py` 가 따로 있다.

import argparse
import io
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
원본 = ROOT / "원본"
캐시 = ROOT / "pipeline" / "out" / "전문캐시"

sys.path.insert(0, str(HERE))
from hwpx_table import read_any  # noqa: E402

사진머리 = (b"\xff\xd8\xff", b"\x89PNG", b"GIF8", b"BM")


def pdf더읽기(경로: Path, 먼저: str) -> str:
    """pypdf 가 적게 읽은 PDF 를 pymupdf 로 다시 읽는다.

    ⚠ 둘 중 **긴 쪽**을 쓴다. 어느 하나가 늘 낫지 않다 — 2단 조판 논문은 pypdf 의
      layout 모드가 낫고(칸이 안 섞인다), 농사로 안내서는 pymupdf 가 훨씬 많이 읽는다.
    ⚠ pymupdf 가 없으면 조용히 pypdf 값을 쓴다. 없다고 멈추면 조사가 아예 못 돈다.
    """
    try:
        import pymupdf
    except ImportError:
        return 먼저
    try:
        with pymupdf.open(경로) as 문서:
            뒤 = "\n".join(쪽.get_text() for 쪽 in 문서)
    except Exception:  # noqa: BLE001
        return 먼저
    return 뒤 if len(뒤) > len(먼저) else 먼저


def 전문(경로: Path, 다시=False) -> str:
    """원본 한 개를 글자로. 두 번째부터는 캐시에서 꺼낸다.

    ⚠ 캐시 열쇠에 **크기와 수정시각**을 넣는다. 경로만으로 잡으면 원본을 다시 받아도
      옛 글자를 계속 쓰게 된다 — varieties.csv 가 낡아 73%가 빈 채로 있던 일과 같은 함정.
    """
    상대 = 경로.relative_to(원본)
    통계 = 경로.stat()
    자리 = 캐시 / 상대.parent / f"{상대.name}.{통계.st_size}_{int(통계.st_mtime)}.txt"
    if 자리.exists() and not 다시:
        return 자리.read_text(encoding="utf-8")

    머리 = 경로.read_bytes()[:4]
    if any(머리.startswith(m) for m in 사진머리):
        글 = ""
    else:
        글 = read_any(경로) or ""
        if 머리[:4] == b"%PDF":
            글 = pdf더읽기(경로, 글)
    자리.parent.mkdir(parents=True, exist_ok=True)
    자리.write_text(글, encoding="utf-8")
    return 글


def 파일들(서비스=None):
    """첨부 전부. 서비스마다 하위 구조가 달라 깊이를 가정하지 않는다(CLAUDE.md).

    농작업일정은 평평하고, 품종정보는 작물별, 병해충·주간농사는 연도별,
    재해예방정보는 계열/연도 **두 층**이다. `rglob` 로 통째로 훑는 까닭이다.
    """
    뿌리 = [원본 / 서비스] if 서비스 else sorted(p for p in 원본.iterdir() if p.is_dir())
    for 폴더 in 뿌리:
        붙임 = 폴더 / "첨부"
        if not 붙임.exists():
            continue
        for p in sorted(붙임.rglob("*")):
            if p.is_file():
                yield p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("낱말", nargs="+", help="찾을 낱말. 여럿이면 아무거나 걸리면 맞은 것")
    ap.add_argument("--서비스", help="농작업일정 · 품종정보 · 재해예방정보 · 주간농사정보 · 병해충발생정보")
    ap.add_argument("--작물", help="경로에 이 말이 든 파일만 (품종정보처럼 작물별 폴더일 때)")
    ap.add_argument("--문맥", type=int, default=1,
                    help="맞은 줄 앞뒤로 몇 줄을 같이 보일지. 기본 1 — 표는 머리글이 윗줄에 있다")
    ap.add_argument("--몇개", type=int, default=40, help="찍을 맞은 줄 수")
    ap.add_argument("--셈만", action="store_true", help="파일별 건수만")
    ap.add_argument("--다시", action="store_true", help="캐시를 무시하고 다시 읽는다")
    args = ap.parse_args()

    찾기 = re.compile("|".join(re.escape(w) for w in args.낱말))
    본것 = 빈것 = 사진 = 0
    맞은파일, 찍은줄 = [], 0

    for 경로 in 파일들(args.서비스):
        if args.작물 and args.작물 not in str(경로):
            continue
        머리 = 경로.read_bytes()[:4]
        if any(머리.startswith(m) for m in 사진머리):
            사진 += 1
            continue
        글 = 전문(경로, args.다시)
        if not 글.strip():
            빈것 += 1
            continue
        본것 += 1
        줄들 = 글.split("\n")
        맞음 = [i for i, ln in enumerate(줄들) if 찾기.search(ln)]
        if not 맞음:
            continue
        맞은파일.append((len(맞음), 경로))
        if args.셈만:
            continue
        for i in 맞음:
            if 찍은줄 >= args.몇개:
                break
            앞 = max(0, i - args.문맥)
            print(f"\n── {경로.relative_to(원본)}  줄 {i + 1}")
            for j in range(앞, min(len(줄들), i + args.문맥 + 1)):
                표시 = "▶" if j == i else " "
                print(f"  {표시} {줄들[j].strip()[:160]}")
            찍은줄 += 1

    if args.셈만 or 찍은줄 >= args.몇개:
        print()
        for n, 경로 in sorted(맞은파일, reverse=True)[:30]:
            print(f"  {n:>4}건  {경로.relative_to(원본)}")

    print(f"\n읽은 파일 {본것}개 · 맞은 파일 {len(맞은파일)}개"
          f" · 사진 {사진}개 · **0자 {빈것}개**")
    if 빈것:
        print("  ⚠ 0자 파일이 있다. 맞은 줄이 0 이어도 '없다' 라고 결론내지 말 것 —")
        print("    스캔 PDF 라면 feature/ocr.py, 한글3.0 이라면 feature/hwp3_pdf.py 다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
