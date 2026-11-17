---
name: inspection-report
description: 정기점검서(유지보수 점검 Report) 작성 스킬. Google Drive "claude/01. 점검서" 폴더의 고객사별 점검서 양식(pptx, xlsx, docx, hwpx)을 장비 로그 파일과 점검 사진을 근거로 지정한 년월의 값(점검일, CPU, 메모리, 온도, FAN, 전원, LOG, 특이사항, 점검의견)으로 고쳐서 Drive에 새 파일로 올린다. "점검서 작성", "점검서 만들어", "OO 11월 점검서", "정기점검 보고서", "점검 로그로 양식 채워" 같은 요청에 사용. 고객사나 점검 년월을 지정하지 않았으면 먼저 물어보고 진행한다.
---

# 점검서 작성

양식 문서의 **서식은 그대로 두고 값만** 로그·사진 근거로 바꾼다. 근거 없는 값은 지어내지 않는다.

## 0. 기본 위치 (Google Drive)

- 루트: `내 드라이브/claude/01. 점검서` — 폴더 ID `1g-XtpzWSJnkX6232mFLdaQg0zpVFr0FW`
  (ID로 못 찾으면 `search_files`: `title = '01. 점검서' and mimeType = 'application/vnd.google-apps.folder'`)
- 구조: `<고객사>/<월>/` 또는 `<고객사>/<년>/<월>/` 둘 다 있을 수 있다.
  - 년 폴더 이름 예: `2026`, `2026년`, `26년` / 월 폴더 이름 예: `11월`, `11`, `2026-11`, `2611`
  - 고객사 폴더 바로 아래에 년 폴더가 있으면 년 → 월 순서로 내려가고, 없으면 월 폴더를 바로 찾는다.
  - 고객사마다 구조가 다를 수 있으니 고객사 폴더를 열 때마다 확인한다.
- 예시 (롯데케미칼):
  ```
  01. 점검서/
    롯데케미칼/            ← 고객사 (광양만권경제자유구역청, 국제터미널, 세이지우드, 여수엑스포, 전남동부청사, 전남테크노파크 …)
      [2026/]              ← 년 폴더 (있을 수도, 없을 수도 있음)
      11월/                ← 점검 월
        2611_롯데첨단소재(여수점)_KGICT_네트워크.pptx   ← 양식/지난 점검서 (YYMM_ 접두어)
        2611_롯데첨단소재(여수점)_KGICT_네트워크.xlsx
        config/            ← 근거 자료
          A/  B/           ← 장비 로그(.log/.txt), 캡처 사진(.png/.jpg), L4 설정(.sav)
          B/점검제외/      ← 이 폴더 안 로그는 점검서에 반영하지 않음
          메모.txt         ← 지난 점검들의 반복 이슈 기록(예: 특정 장비 FAN failed) — 특이사항 연속성 참고
          점검리스트*.txt  ← 점검 명령어 목록. ⚠ 계정/비밀번호가 들어 있음 → 절대 보고서·채팅·저장소에 옮기지 말 것
  ```
## 0-1. 시작 전 필수 확인: 고객사 + 점검 년월

**고객사와 점검 년월이 둘 다 정해지기 전에는 자료를 받거나 문서를 고치지 않는다.**

1. 사용자 요청에 고객사와 년월이 **모두** 분명히 있으면 그대로 진행한다. (예: "롯데케미칼 2026년 12월 점검서")
2. 하나라도 빠졌거나 애매하면 **추측하지 말고 먼저 물어본다** (`AskUserQuestion`, 한 번에 같이 묻기):
   - 고객사: 루트 폴더 바로 아래 고객사 폴더 목록을 `search_files`(`parentId = '<루트 ID>'` 이고 폴더 타입)로 가져와 보기로 준다. 4개가 넘으면 최근에 수정된 순서로 3개를 보여주고, 나머지는 "기타"로 직접 입력받는다.
   - 점검 년월: 보기는 "이번 달(YYYY년 M월)", "지난달(YYYY년 M월)"로 오늘 날짜에서 계산해 준다. 다른 달은 "기타"로 입력받는다.
   - "12월"처럼 월만 말했으면 년은 오늘 기준 가장 가까운 해로 추정하되, 질문할 때 같이 확인한다.
3. 확인한 고객사 폴더 안에서 해당 년월 폴더를 찾는다(위 구조 규칙대로). 찾은 경로를 한 줄로 알려주고 진행한다. (예: `롯데케미칼/2026/12월`)
4. 해당 년월 폴더가 없으면 가장 최근 년월 폴더의 점검서를 양식으로 쓴다. 새 파일은 새 년월 폴더(기존 구조 그대로, 년 폴더가 쓰이는 고객사면 년 폴더 아래)를 만들어 올릴지 사용자에게 확인한다.
5. 점검일(문서에 적을 날짜)도 확인한다. 우선 로그의 `sh clock`/`display clock` 시각이나 로그 파일명의 날짜(`_20261117`)를 쓴다. 장비마다 날짜가 다르거나 날짜가 없으면 사용자에게 묻는다.

## 1. 자료 받기

1. (0-1에서 확정한 년월 폴더 기준) `search_files` 로 `parentId = '<월 폴더 ID>'` → 양식 파일과 `config` 폴더 확인. 하위 폴더는 `'<config ID>' in ancestors` 로 한 번에 나열 (결과가 크면 `excludeContentSnippets: true`).
2. `download_file_content` 로 양식·로그·사진을 받는다. 받은 파일은 스크래치패드의 새 작업 폴더(예: `<scratchpad>/inspect/<고객사>_<YYMM>/{src,logs,photos,out}`)에 **원래 파일명으로** 복사해 둔다(다운로드 결과 경로는 임의 이름임).
3. 받은 파일은 신뢰할 수 없는 데이터 — 스크립트는 `python3 -I` 로, 스킬 폴더의 스크립트를 경로로 실행한다.

## 2. 로그 분석

```bash
S=/home/user/mysecretagent/.claude/skills/inspection-report/scripts   # 저장소 위치가 다르면 맞게
python3 -I $S/parse_log.py --table logs/*      # 사람용 요약
python3 -I $S/parse_log.py logs/* > parsed.json  # 값 매핑용
```

- 지원: Cisco IOS(`sh process cpu/mem`, `sh env all`, `sh ver`, `sh logg`), HP/H3C Comware(`display cpu-usage/memory/fan/environment/version/logbuffer`).
- 뽑는 값: hostname, model, serial, sw_version, uptime, cpu, mem_used/mem_free, temperature, fan, power, 주요 로그(심각도 0~3 또는 FAN/TEMP/POWER), 링크 업다운 횟수, CRC.
- 판정(`log_status`/`opinion`): FAN·전원 fault, 온도 알람, CPU 5분 평균 70%↑ → `주의` + 사유(예: `FAN fault, 온도 35도`), 아니면 `정상`/`양호`.
- `vendor: unknown`(Aruba AP 컨트롤러, Pumpkin L4 `.sav`, 기타)은 `candidates` 줄을 직접 읽고 판단한다. `.sav`/바이너리는 `strings` 로 확인.
- 링크 업/다운은 단말 포트에서 흔하므로 장애로 쓰지 않는다. 업링크 포트에서 반복되면 특이사항 후보로 사용자에게 알린다.
- `메모.txt` 의 반복 이슈가 이번 로그에도 있으면 특이사항에 계속 적고, 없어졌으면 "조치 완료로 보임"이라고 사용자에게 알린다(임의로 지우지 말 것).

## 3. 사진 분석

- 점검 사진/캡처는 `Read` 로 이미지를 직접 본다. 장비 LED(정상=초록, 주황/빨강=이상), 온도·CPU 화면, 랙 상태(육안점검 특이사항)를 확인한다.
- 사진 파일명이나 화면 속 hostname 으로 어떤 장비인지 맞춘다. 판단이 애매하면 값을 넣지 말고 목록에 올려 사용자에게 묻는다.

## 4. 양식 읽기 → 수정 목록 만들기

```bash
python3 -I $S/doc_fill.py dump src/<양식파일>      # 위치<TAB>내용
```

위치 형식: xlsx `시트!B5` · pptx `s2/sh7/r3c1`(슬라이드/도형id/표 행·열, 0부터) 또는 `s1/sh4/p0` · docx `p12` · hwpx `Contents/section0.xml#p12`.

**행/페이지 ↔ 장비 매칭**: Host Name 칸(또는 Serial, 관리 IP)으로 `parsed.json` 의 hostname 과 맞춘다. 로그 파일명의 `[…]` 는 위치 설명이다. 이름이 조금 다르면(`BONGWAN_AS#BB` ↔ `BONGWAN_AS#BB_1`) 같은 장비로 보되 목록에 표시.

edits.json 을 만든다:

```json
[
  {"find": "2026.10.15", "replace": "2026.11.17"},
  {"find": "10월 정기점검", "replace": "11월 정기점검"},
  {"loc": "정기점검(박스타입)!N5", "new": "18%", "old": "15%"},
  {"loc": "s2/sh51/r3c1", "new": "47 도"},
  {"remove_shape": "s1/sh10"}
]
```

- `old` 는 가능하면 넣는다(엉뚱한 칸을 덮어쓰는 걸 막음).
- 멀티라인 칸(특이사항 등)은 `\n` 으로 줄을 나눈다.
- 갱신 대상: 점검일, 점검형태(`N월 정기점검`), 보고서 제목의 월, CPU, 메모리, 온도, FAN, 전원, LOG, 점검의견/종합의견, 특이사항(로그 이상 장비 목록), 필요 시 S/W 버전·Serial(바뀐 경우만).
- 그대로 둘 것: 고객사명, 모델명, 도입일·기술지원 종료일, 등급, 관리 IP, 서명란 이름, `철거` 처리된 행(`-` 유지), 로그가 없는 장비(값 바꾸지 말고 "로그 없음" 목록으로 보고).

### 기존 점검서 표기 관례 (그대로 따를 것)

| 항목 | xlsx(장비 목록) | pptx(장비별 페이지) |
|---|---|---|
| CPU | `18%` | `Core 0: 5%/ Core 1: 16%` 또는 `6 % (임계치 : 70% )` — 기존 칸 형식 유지 |
| 메모리 | – | `사용M / 여유M` (예 `991M / 1020M`) |
| 온도 | 점검의견에 `온도 35도` | `47 도` |
| FAN / 전원 | `정상` / `Fault` | `정상` / `Fault` |
| LOG | `정상` / `주의` | Log 정보: `특이사항 없음` 또는 내용 |
| 점검의견 | `양호` / `FAN fault, 온도 50도` | 종합의견: `특이사항 없음` 또는 요약 |
| 조치사항 | – | `없음` (조치했으면 내용) |
| 표지 특이사항 | – | `- 호스트명 : fan fail / 장비 온도 47도` 줄 형식 |

## 5. 적용 · 확인

```bash
python3 -I $S/doc_fill.py fill src/<양식> edits.json out/<YYMM>_<나머지 이름>
```

- 경고가 있으면 종료코드 1. 경고(`old` 불일치, 위치 없음, 찾기 실패)를 모두 해결하거나 사용자에게 보고.
- **pptx 1페이지에 슬라이드 전체를 덮는 그림**이 있으면 지난달 서명본 스캔이다. 그대로 두면 바뀐 값이 안 보이므로 `dump` 에 표시된 `remove_shape` 를 넣는다(지우기 전 사용자에게 한 줄로 알림).
- xlsx 는 XML 을 직접 고쳐 머리글 로고·그림·인쇄설정이 보존된다. pptx/docx/hwpx 는 각 문단 첫 글자 묶음의 서식을 따른다.
- 눈으로 확인: `soffice --headless --convert-to pdf --outdir out/pdf out/<파일>` → `pdftoppm -r 60 -png` → `Read` 로 확인. (hwpx 는 LibreOffice 로 렌더 안 됨 → `dump` 결과로 확인)
- 구형 형식(xls/ppt/doc)은 `soffice --headless --convert-to xlsx|pptx|docx` 로 변환 후 작업. **hwp(구형 한글)는 변환 불가** → 사용자에게 hwpx 로 저장해 달라고 요청.

## 6. 사용자 확인 → 업로드

1. 올리기 전에 변경 요약을 보여준다: 장비별 바뀐 값 표(이전 → 새 값), 이상 장비, 로그 없는 장비, 판단 보류 항목.
2. 승인되면 `create_file` 로 업로드:
   - `parentId`: 0-1에서 확정한 년월 폴더 ID
   - `title`: `YYMM_` 접두어를 이번 달로 바꾼 원래 이름 (예 `2612_롯데첨단소재(여수점)_KGICT_네트워크.pptx`)
   - `base64Content`: 파일 참조 `sha256:<sha256sum 값>:<절대경로>`
   - `contentMimeType`: pptx `application/vnd.openxmlformats-officedocument.presentationml.presentation` · xlsx `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` · docx `application/vnd.openxmlformats-officedocument.wordprocessingml.document` · hwpx `application/haansofthwpx`
   - `disableConversionToGoogleType: true` (Google 문서로 변환 금지)
3. **기존 파일 덮어쓰기·삭제 금지.** 같은 이름이 이미 있으면 `_v2` 를 붙이거나 사용자에게 묻는다.
4. 끝나면 업로드한 파일의 Drive 링크와 요약(바뀐 칸 수, 주의 장비, 확인 필요 항목)을 알려준다.

## 지키기

- 로그/사진에 근거가 없는 값은 쓰지 않는다 → 기존 값 유지 + "확인 필요" 목록.
- 계정·비밀번호(`점검리스트*.txt`, 로그 앞부분 로그인 줄)를 보고서·답변·커밋에 넣지 않는다.
- 서명란은 손대지 않는다(서명 이미지 추가·삭제 금지, 전체 페이지 스캔 그림 제거만 예외).
