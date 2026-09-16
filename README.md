# safefarm-crop-data

세이프팜 **작물 마스터 데이터의 생산 레포**.
농사로 OpenAPI 원본 문서에서 14작물의 생육단계·적산온도·재해기준을 뽑는다.

서비스 레포는 [`pj002321/Safe-farm`](https://github.com/pj002321/Safe-farm) 이다.
이 레포는 **산출 CSV 만** 그쪽 `ai-service/data/master/` 로 넘기고 코드는 넘기지 않는다.
원본이 4.8GB라 그쪽에서는 재현할 수 없기 때문이다.

## 값을 만지기 전에

    CLAUDE.md               ★ 규칙 · 데이터 흐름 · 파싱 함정. 먼저 읽는다
    GDD계산관련/작물_확정표.md  ★★ 계산 파라미터의 정본. CSV 와 갈리면 이쪽이 맞다
    확인필요.md              값이 갈리거나 판단이 남은 미결 항목
    출처.txt                자료 출처 + 이용조건 미확인 항목
    숙기데이터_확인.md        숙기(조·중·만생) 검증 기록

특히 두 가지는 틀리기 쉬워 CLAUDE.md 에 절을 따로 뒀다.

- **한계온도 ≠ 기준온도.** 재해 경보용 값을 적산온도 계산에 쓰면 전부 어긋난다
- **적산온도는 축이 둘.** 누적 방식(①②③)과 고온 상한은 독립이다. ②로 적힌
  원문 목표값을 ③(GDD)으로 그대로 옮기면 안 된다

## 돌리기

    python pipeline/extract.py   # 원본 5종 → out/mid_*.csv
    python pipeline/build.py     # 중간 CSV + 확정표 상수 → out/스키마/
    python pipeline/verify.py    # 빈칸·범위·제약 검사

Windows cp949라 한글이 깨지면 `PYTHONIOENCODING=utf-8` 를 앞에 붙인다.
자세한 옵션과 원본별 함정은 `pipeline/사용법.md`.

## 산출물

`pipeline/out/스키마/` 에 나온다. **추적하지 않는다** — 코드에서 다시 만든다.

    crops.csv               작물 공통. name · base_temp · difficulty
    crop_variants.csv       숙기별. gdd_target · days_to_harvest
    crop_stages.csv         단계별. gdd_from · gdd_to · water_need_mm · guide_text
    crop_disaster_rules.csv 재해 한계값. hazard · metric · threshold_c · severity
    근거/                   위 네 개의 출처 추적본. 숫자마다 어느 문서 몇 쪽인지

Safe-farm 으로는 앞의 셋만 간다. 출처 컬럼은 그쪽 ORM 에 자리가 없어 떨어뜨린다 —
**추적은 이 레포의 `근거/` 가 맡는다.**

⚠ `crop_disaster_rules` 는 Safe-farm 의 `disaster_rules` 와 **다른 테이블**이다.
그쪽은 기상청 절기재해 통계(관측소 × 절기)고 이쪽은 작물별 한계값이다. 이름을 합치지 말 것.

## 추적하지 않는 것

    원본/**/raw/ 첨부/       4.8GB   농사로 API 로 다시 받는다
    보관/**/결과/            7.7GB   전수수집 시절 산출물. 대조용
    pipeline/out/            99MB    코드에서 다시 만든다
    GDD계산관련/논문/                 Elsevier 저널. 재배포 금지
    .env                             실제 API 키

원본을 다시 받는 법은 `원본/<서비스>/<이름>사용법.md`.
**오래 걸리고 정부 서버라 몰아 치면 차단된다. 구멍이 났을 때만 돌린다.**

## 이용조건

농사로 매뉴얼·문서의 이용조건이 **아직 확인되지 않았다** (`출처.txt §6`).
확인 전까지 이 레포를 공개하지 않는다. LICENSE 파일을 두지 않은 이유다.

계산 파라미터 일부는 Paredes et al. (2025), *Agric. Water Manag.* 319:109755 에서 왔다.
Elsevier 저널이라 본문을 이 레포에 두지 않는다. 인용 정보는 `출처.txt §3-1`.
