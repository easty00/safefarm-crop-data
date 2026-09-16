# 본문(txt)을 **절 단위로 나누는** 도구입니다.
#
#   parse_sections   글머리표 계층으로 절을 나눈다  ■ → ❍ → -
#   walk_grid        표 격자를 훑어 항목-값 쌍을 만든다
#   grid_rows        표를 행 단위로 편다
#
# 출처 : 보관/농작업일정/attach.py
#
# ⚠ 왜 필요한가.
#   값이 표에만 있는 게 아닙니다. 감자 base_temp 는 표가 아니라 본문 문장에 있습니다.
#
#       ❍ 씨감자 싹은 5℃ 이상에서 자라기 시작함
#
#   표만 읽으면 이런 값을 통째로 놓칩니다. 옛 attach.py 가 `항목 : 값` 꼴만 잡아
#   본문 974개 중 372개(38%)만 CSV 로 보냈던 것이 이 실수입니다.
#   절로 나눠두면 "이 값이 어느 절에서 나왔는지" 도 같이 남길 수 있습니다.

import re

H1_RE = re.compile(r"^\s*[■□▣]\s*(\S.{0,30})$")
H2_RE = re.compile(r"^\s*[❍○●◦]\s*(\S.*)$")
H3_RE = re.compile(r"^\s*[-*※·]\s*(\S.*)$")


H2_RE = re.compile(r"^\s*[❍○●◦]\s*(\S.*)$")
H3_RE = re.compile(r"^\s*[-*※·]\s*(\S.*)$")


H3_RE = re.compile(r"^\s*[-*※·]\s*(\S.*)$")


def parse_sections(text: str, crop: dict) -> list[dict]:
    """■ / ❍ / - 계층을 살려 본문 절을 담는다. 버리는 줄 없이 전부 담는다."""
    out, h1, h2 = [], "", ""
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or set(line.strip()) <= {"|", " "}:
            continue
        m1 = H1_RE.match(line)
        if m1:
            h1, h2 = " ".join(m1.group(1).split()), ""
            continue
        m2 = H2_RE.match(line)
        if m2:
            h2 = " ".join(m2.group(1).split())
            out.append({**crop, "절": h1, "항목": h2, "깊이": 2, "내용": ""})
            continue
        m3 = H3_RE.match(line)
        depth = 3 if m3 else 4
        body = " ".join((m3.group(1) if m3 else line).split())
        out.append({**crop, "절": h1, "항목": h2, "깊이": depth, "내용": body})
    return out


def walk_grid(grid: list[list[str]]) -> list[tuple[str, str]]:
    """한 행에서 (항목 이름, 값) 쌍을 뽑는다.

    ⚠ 한 행에 쌍이 **두 개씩** 들어 있는 표가 있다. 실제 고추 표가 이렇다.

        생육온도 ¦ 발아적온 ¦ 25~32℃ ¦ 모 기르기 적온 ¦ 22~30℃

    마지막 칸만 값으로 보면 발아적온 25~32℃ 를 통째로 잃는다.
    처음에 그렇게 만들었다가 한 작물에서 온도 6개 중 3개를 놓쳤다.

    그래서 이렇게 센다. 병합으로 반복된 칸을 하나로 줄인 뒤,
    칸 수가 홀수면 맨 앞이 행 이름(생육온도)이고 나머지를 둘씩 짝짓는다.
    짝수면 앞에서부터 그냥 둘씩 짝짓는다.
    """
    out = []
    for row in grid:
        uniq = []
        for c in (x.strip() for x in row):
            if c and (not uniq or uniq[-1] != c):
                uniq.append(c)
        if len(uniq) < 2:
            continue
        head, rest = ("", uniq) if len(uniq) % 2 == 0 else (uniq[0], uniq[1:])
        for i in range(0, len(rest) - 1, 2):
            label = f"{head} > {rest[i]}" if head else rest[i]
            out.append((label, rest[i + 1]))
    return out


def grid_rows(grid: list[list[str]]) -> list[tuple[str, str]]:
    """머리행이 있는 표를 (머리, 값) 으로 편다.

    '작형별 출하시기' 처럼 열이 여럿인 표는 이름-값 짝으로는 제대로 안 읽힌다.

        작형   ¦ 씨뿌림      ¦ 아주심기   ¦ 수확기     ¦ 성출하기
        반촉성 ¦ 11월 하순~  ¦ 2월 중순~ ¦ 3월 상순~ ¦ 7월 상순~

    어느 쪽이 맞는 해석인지 표마다 다르므로 **두 가지로 다 뽑아 둔다.**
    격자 원본(첨부_표.csv)도 그대로 남으니 잃는 것은 없다.
    """
    if len(grid) < 2:
        return []
    header = [c.strip() for c in grid[0]]
    out = []
    for r, row in enumerate(grid[1:], 1):
        seen = set()
        for c, value in enumerate(row):
            value = value.strip()
            if not value:
                continue
            key = header[c] if c < len(header) and header[c] else f"열{c}"
            if (key, value) in seen:      # 병합으로 같은 값이 반복된 것
                continue
            seen.add((key, value))
            out.append((f"{r}행 {key}", value))
    return out
