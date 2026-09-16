# 옛 형식 문서를 글자로 바꾸는 도구입니다.
# hwpx·hwp·PDF 는 feature/hwpx_table.py 가 맡고, 이 파일은 그쪽에 없는 둘을 담습니다.
#
#   read_hwp3      한글 3.0 (파일 앞 4바이트가 "HWP ") — 2바이트 리틀엔디안 johab
#   read_page      PDF 를 쪽 단위로. 깨진 글자 되돌리기(fix_mojibake) 포함
#
# 출처 : 보관/품종정보/variety_stage.py
#
# ⚠ 한글 3.0 은 문단 구조까지 해석하지 않습니다. 글자로 읽히는 구간만 이어붙이는
#   "건져내기" 수준입니다. 이전 수집에서 3건 중 2건은 잘 나왔고 1건은 37자만 건졌습니다.
#
# 필요 : pip install pypdf

import struct
from pathlib import Path

def fix_mojibake(text: str) -> str:
    """CP949 를 라틴으로 잘못 읽어 깨진 글자를 되돌린다.

    1990년대 PDF 는 한글 CMap(`/KSCms-UHC-H`)을 쓰는데 pypdf 가 그걸 모른다.
    그래서 바이트를 그대로 라틴 글자로 내놓는다.

        ´ëÁß2Á¶ ´ë¸Æ1È£  →  대중2조 대맥1호

    바이트로 되돌린 뒤 cp949 로 다시 읽으면 살아난다. 한글 비율이 늘 때만 바꾼다.
    """
    if not text or not any("À" <= ch <= "ÿ" for ch in text):
        return text
    try:
        fixed = text.encode("latin-1", "ignore").decode("cp949", "ignore")
    except Exception:
        return text
    def hangul(s: str) -> int:
        return sum(1 for ch in s if "가" <= ch <= "힣")
    return fixed if hangul(fixed) > hangul(text) else text


def read_hwp3(path: Path) -> str:
    """한글 3.0. 2바이트 조합형으로 담긴 글자를 건져낸다."""
    b = path.read_bytes()

    def one(i: int) -> str | None:
        w = struct.unpack_from("<H", b, i)[0]
        if w in (0x0D, 0x0A, 0x09):
            return "\n"
        if 0x20 <= w < 0x7F:
            return chr(w)
        if w >= 0x8000:
            try:
                c = struct.pack(">H", w).decode("johab")
            except Exception:
                return None
            return c if "가" <= c <= "힣" else None
        return None

    runs, cur = [], []
    for i in range(0, len(b) - 1, 2):
        c = one(i)
        if c is None:
            if len(cur) >= 10:
                runs.append("".join(cur))
            cur = []
        else:
            cur.append(c)
    if len(cur) >= 10:
        runs.append("".join(cur))
    return "\n".join(runs)


def read_page(page, layout: bool) -> str:
    """쪽 하나를 읽는다. 옛 한글 CMap 을 모른다는 오류는 보통 방식으로 넘긴다."""
    try:
        text = page.extract_text(extraction_mode="layout") if layout else page.extract_text()
    except Exception:
        # "unknown encoding: /KSCms-UHC-H" — 1990년대 PDF. 자리 맞추기를 포기하고 읽는다
        try:
            text = page.extract_text()
        except Exception:
            return ""
    return fix_mojibake(text or "")
