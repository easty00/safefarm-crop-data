# 한글 문서(.hwp / .hwpx) 안에 있는 글자를 꺼내서 .txt 파일로 저장해주는 스크립트입니다.
# 자세한 사용법은 "hwp_추출_사용법.md" 파일을 읽어주세요.

import re
import sys
import zlib
import struct
import zipfile
from pathlib import Path

import olefile

HWPTAG_PARA_TEXT = 67  # hwp 파일 안에서 "이건 글자다"라고 표시된 조각의 번호


def clean(text: str) -> str:
    # 표·그림 등을 표시하는 제어문자는 지우고 사람이 읽는 글자만 남깁니다.
    return "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)


def hwp_to_text(path: Path) -> str:
    """구형 .hwp (OLE 형식)"""
    ole = olefile.OleFileIO(str(path))

    header = ole.openstream("FileHeader").read()
    is_compressed = (header[36] & 1) == 1

    sections = sorted(
        int(entry[1][len("Section"):])
        for entry in ole.listdir()
        if entry[0] == "BodyText"
    )

    chunks = []
    for num in sections:
        raw = ole.openstream(f"BodyText/Section{num}").read()
        data = zlib.decompress(raw, -15) if is_compressed else raw

        pos, size = 0, len(data)
        while pos < size:
            record_header = struct.unpack_from("<I", data, pos)[0]
            rec_type = record_header & 0x3FF
            rec_len = (record_header >> 20) & 0xFFF

            if rec_type == HWPTAG_PARA_TEXT:
                payload = data[pos + 4: pos + 4 + rec_len]
                chunks.append(clean(payload.decode("utf-16le", errors="ignore")))

            pos += 4 + rec_len

    return "\n".join(chunks)


def hwpx_to_text(path: Path) -> str:
    """신형 .hwpx (ZIP + XML 형식). 구형과 달리 본문 전체가 나옵니다."""
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if re.fullmatch(r"Contents/section\d+\.xml", n))
        if not names:
            names = [n for n in z.namelist() if n == "Preview/PrvText.txt"]

        chunks = []
        for name in names:
            raw = z.read(name).decode("utf-8", errors="ignore")
            if name.endswith(".txt"):
                chunks.append(clean(raw))
                continue
            # 문단/줄 구분 태그를 줄바꿈으로 바꾼 뒤 나머지 태그를 제거합니다.
            raw = re.sub(r"</(hp:p|hp:tr|hp:tc)>", "\n", raw)
            raw = re.sub(r"<[^>]+>", "", raw)
            raw = (raw.replace("&lt;", "<").replace("&gt;", ">")
                      .replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&"))
            raw = re.sub(r"\n{3,}", "\n\n", raw)
            chunks.append(clean(raw))

    return "\n".join(chunks)


def extract(path: Path) -> str:
    if path.suffix.lower() == ".hwpx":
        return hwpx_to_text(path)
    return hwp_to_text(path)


def main():
    if len(sys.argv) < 2:
        print("사용법: python hwp_extract.py 파일이나폴더경로")
        print('예시1 (파일 하나): python hwp_extract.py "cropEbook/OpenAPI 활용 매뉴얼.hwp"')
        print("예시2 (폴더 전체): python hwp_extract.py .")
        return

    target = Path(sys.argv[1])
    if target.is_file():
        files = [target]
    else:
        files = sorted(p for p in target.rglob("*") if p.suffix.lower() in (".hwp", ".hwpx"))

    if not files:
        print("hwp/hwpx 파일을 찾지 못했습니다:", target)
        return

    for path in files:
        try:
            text = extract(path)
        except Exception as e:
            print(f"[실패] {path} -> {e}")
            continue

        out_path = path.with_suffix(".txt")
        out_path.write_text(text, encoding="utf-8")
        print(f"[완료] {path.name} -> {out_path.name} ({len(text):,}자)")


if __name__ == "__main__":
    main()
