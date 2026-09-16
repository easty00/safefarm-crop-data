# 농작업일정에 작물을 하나씩 되살립니다. (176개 일괄 복원용이 아닙니다)
#
#     python pipeline/add_crop.py 오이 호박 참외        이름으로
#     python pipeline/add_crop.py 30636 30651          cntntsNo 로도 됨
#     python pipeline/add_crop.py --list                보관에 있는 176작물 보기
#     python pipeline/add_crop.py --list 상추           이름에 '상추' 가 든 것만
#     python pipeline/add_crop.py 오이 --dry            옮기지 않고 무엇을 할지만 보기
#
# ─────────────────────────────────────────────────────────────────────
# 무엇을 하나
#
# **작물 하나를 골라 되살립니다.** 176개를 한꺼번에 받는 스크립트가 아닙니다.
# 지금 21작물만 두는 것은 의도한 것이고, 필요할 때 하나씩 더하는 데 씁니다.
#
#     목록(lst_*.xml)에 있는 작물   176
#     원본/ 에 둔 것                21   ← 지금 다루는 것
#     보관/농작업일정/결과/          176   ← 자료는 전부 남아 있다
#
# ⚠ **다시 내려받지 않습니다.** 보관에서 그 작물의 네 파일만 옮깁니다.
#     erajson_<no>.xml   파종·수확 순(旬) 시기   ← 첨부에 없는 유일한 자료
#     dtl_<no>.xml       재배법 본문
#     era_<no>.xml       달력(대조용)
#     첨부 hwpx          온도 · 적산온도 · 작형표
#
# ⚠ 등록표(crops.py)에만 더하고 원본을 안 옮기면 그 작물은 조용히 빠집니다.
#   반대로 원본만 옮기고 등록을 안 해도 안 읽힙니다. 둘 다 해야 합니다.
#   이 스크립트가 옮기기를 하고, 등록표에 붙일 줄을 만들어 보여줍니다.
# ─────────────────────────────────────────────────────────────────────

import re
import shutil
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from crops import WANT, nospace  # noqa: E402

보관 = ROOT / "보관" / "농작업일정" / "결과"
원본 = ROOT / "원본" / "농작업일정"
CROPS_PY = HERE / "crops.py"


def 분류지도():
    """첨부파일명 → 분류. lst 응답의 분류 칸이 비어 있어 폴더 이름을 쓴다."""
    out = {}
    for p in (보관 / "첨부").rglob("*"):
        if p.is_file():
            out[p.name] = p.parent.name
    return out


def 목록():
    """보관 lst_*.xml 에서 cntntsNo → (이름, 분류, 첨부파일명)."""
    분류맵 = 분류지도()
    out = {}
    for p in sorted((보관 / "raw").glob("lst_*.xml")):
        for it in ET.parse(p).getroot().findall(".//item"):
            no = (it.findtext("cntntsNo") or "").strip()
            if not no:
                continue
            파일 = (it.findtext("orginlFileNm") or it.findtext("fileName") or "").strip()
            out[no] = (
                (it.findtext("sj") or "").strip(),
                (it.findtext("kidofcomdtySeCodeNm") or "").strip() or 분류맵.get(파일, ""),
                파일,
            )
    return out


def 찾기(말, 전체):
    """이름 일부 또는 cntntsNo 로 고른다."""
    if 말.isdigit():
        return [말] if 말 in 전체 else []
    키 = nospace(말)
    return [no for no, (nm, _c, _f) in 전체.items() if 키 in nospace(nm)]


def 첨부찾기(파일명):
    """보관 첨부는 분류 폴더 아래 있다. 이름으로 찾는다."""
    if not 파일명:
        return None
    for p in (보관 / "첨부").rglob("*"):
        if p.is_file() and p.name == 파일명:
            return p
    return None


def 옮기기(no, 전체, dry):
    이름, 분류, 첨부명 = 전체[no]
    한일 = []
    (원본 / "raw").mkdir(parents=True, exist_ok=True)
    (원본 / "첨부").mkdir(parents=True, exist_ok=True)

    for 종류 in ("erajson", "dtl", "era"):
        src = 보관 / "raw" / f"{종류}_{no}.xml"
        dst = 원본 / "raw" / f"{종류}_{no}.xml"
        if not src.exists():
            한일.append(f"     · {종류}_{no}.xml 보관에 없음")
            continue
        if dst.exists():
            한일.append(f"     · {종류} 이미 있음")
            continue
        if not dry:
            shutil.copy2(src, dst)
        한일.append(f"     ✓ {종류}_{no}.xml")

    src = 첨부찾기(첨부명)
    if src is None:
        한일.append(f"     ⚠ 첨부 없음 ({첨부명 or '목록에 파일명이 비어 있음'})")
        한일.append("        → raw 만으로는 온도·적산온도가 안 나옵니다")
    else:
        dst = 원본 / "첨부" / src.name
        if dst.exists():
            한일.append("     · 첨부 이미 있음")
        else:
            if not dry:
                shutil.copy2(src, dst)
            한일.append(f"     ✓ 첨부 {src.name}")
    return 이름, 분류, 첨부명, 한일


def 등록줄(no, 이름, 첨부명):
    """crops.py 에 넣을 한 줄을 만든다. 표준이름은 사람이 정해야 한다."""
    표준 = re.sub(r"\s*[(（].*$", "", 이름).strip()
    본선 = "False"
    return (f'    ("{표준}", {본선:>5}, [], '
            f'{{"{no}": ("{이름}", False)}}),')


def main():
    인자 = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry" in sys.argv
    전체 = 목록()

    if "--list" in sys.argv:
        키 = 인자[0] if 인자 else ""
        print(f"보관에 있는 농작업일정 작물 {len(전체)}개"
              + (f" — '{키}' 가 든 것" if 키 else "") + "\n")
        print(f"{'cntntsNo':9}{'작물':26}{'분류':10}{'등록':>4}{'첨부':>5}")
        for no, (nm, cat, fn) in sorted(전체.items(), key=lambda x: (x[1][1], x[1][0])):
            if 키 and nospace(키) not in nospace(nm):
                continue
            print(f"{no:9}{nm[:24]:26}{cat[:8]:10}"
                  f"{'Y' if no in WANT else '·':>4}{'Y' if fn else '·':>5}")
        return

    if not 인자:
        print(__doc__ or "")
        print("무엇을 되살릴지 적어주세요.  예)  python pipeline/add_crop.py 오이 호박")
        print("받을 수 있는 목록:      python pipeline/add_crop.py --list")
        return

    붙일줄 = []
    for 말 in 인자:
        찾음 = 찾기(말, 전체)
        if not 찾음:
            print(f"\n✗ '{말}' — 목록에 없습니다. --list 로 이름을 확인하세요")
            continue
        if len(찾음) > 1:
            print(f"\n? '{말}' 로 {len(찾음)}개가 걸립니다. 하나를 골라 cntntsNo 로 적어주세요")
            for no in 찾음:
                print(f"     {no}  {전체[no][0]}")
            continue
        no = 찾음[0]
        이름, 분류, 첨부명, 한일 = 옮기기(no, 전체, dry)
        print(f"\n[{no}] {이름}  ({분류})")
        for x in 한일:
            print(x)
        if no not in WANT:
            붙일줄.append(등록줄(no, 이름, 첨부명))

    if 붙일줄:
        print("\n" + "─" * 66)
        print("이제 pipeline/crops.py 의 CROPS 에 아래 줄을 더하세요.")
        print("⚠ 첫 칸(표준이름)과 둘째 칸(본선 True/False)은 **직접 고치세요.**")
        print("   같은 작물의 다른 작형이면 기존 줄의 문서 칸에 넣는 편이 낫습니다.")
        print("   예)  (\"무\", True, [], {\"30614\": (\"무\", True),")
        print("                          \"30615\": (\"무(고랭지재배)\", True)}),")
        print("─" * 66)
        for x in 붙일줄:
            print(x)
        print("─" * 66)
        print("\n그 다음 —")
        print("   python pipeline/src_farmwork.py      농작업일정만 다시 뽑기")
        print("   python pipeline/extract.py --merge   모으기")
    if dry:
        print("\n(--dry 라 아무것도 옮기지 않았습니다)")


if __name__ == "__main__":
    main()
