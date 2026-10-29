# Figma 기획 보드 반영 스크립트 (v2 멀티 소스)

대상 파일: Figma "정리합시다" (fileKey `GyRht7DCujol5Trh8VQf8r`), Page 3 (node `112:2`)
URL: https://www.figma.com/design/GyRht7DCujol5Trh8VQf8r/?node-id=112-2

2026-10-29 기준 Figma Starter 플랜의 MCP 호출 한도(월 20회)가 소진되어 아래 스크립트는 **아직 실행되지 않았다**.
DESIGN.md v2의 내용을 보드에 반영하며, Figma 커뮤니티 플러그인 **Scripter**로 Page 3에서 직접 실행할 수 있다.

| 순서 | 파일 | 하는 일 | 건드리는 섹션 |
|---|---|---|---|
| 1 | `01_ia_and_multisource_boards.js` | 04 IA 보드를 메뉴 11개(소스 관리·카테고리 매핑·시스템 설정 추가)로 재작성, 07 멀티 소스 구조 보드와 08 등록 상품 감시 보드 신규 | 04 삭제 후 재생성, 07·08 신규 |
| 2 | `03_update_existing_boards.js` | 01 프로세스·02 상태 머신·03 구성도 문구를 v2로 갱신(환율 자동 수집, ⑩ 감시 띠, 등록 후 상태 체인, Supabase 카드), 소스 어댑터 띠 추가 | 01, 02, 03 |
| 3 | `04_regenerate_admin_screens_v2.js` | 05 와이어프레임 섹션을 **삭제하고** v2 기준 9화면으로 재생성: 로그인, 대시보드(소스별·API 비용), 소스 관리, 카테고리 매핑, 수집 카테고리(소스 축), 제외 규칙(브랜드 로고 탭), 비용 설정(환율 자동·배송 프로필·정확도 프리셋·후보 수), 상품 목록(소스·그룹 비교), **시스템 설정**(AI 제공자·예산·스케줄·Supabase·텔레그램) | 05 삭제 후 재생성 |

2026-10-29 저녁 추가 반영: 메뉴 11개(시스템 설정), 브랜드 로고 자동 제외, 하루 후보 수 N, 정확도 프리셋, 배치 시각 설정, API 월 예산·경고, AI 제공자 선택(Claude/Gemini/OpenAI), Supabase 이미지 스토리지. 환경 변수 목록은 프로젝트 루트의 `.env.example` 참고.

| 4 | `05_fix_chain_and_hide_layer_names.js` | (1) 02 보드의 "등록 후" 체인을 지우고 선이 카드를 지나지 않게 다시 그림 (2) 모든 섹션의 요소를 투명 프레임 "보드" 하나로 감싸 캔버스에 뜨는 회색 레이어 이름을 보드당 하나로 줄임. **항상 마지막에 실행**, 여러 번 실행해도 안전 | 02 수정, 전체 섹션 감싸기 |

예전 `02_wireframes_source_and_mapping.js`는 04 스크립트에 흡수되어 삭제했다. 둘을 같이 돌리면 화면이 중복된다.
03을 이미 실행한 뒤 체인이 깨져 보였다면 05만 실행하면 된다(03을 다시 돌리지 말 것). 01이나 04를 나중에 다시 돌리면 새 섹션은 감싸지지 않은 상태이므로 05를 한 번 더 실행한다.

회색 레이어 이름 참고: Figma는 페이지나 섹션 바로 아래에 있는 프레임의 이름을 캔버스에 표시하고, 이 표시를 끄는 설정은 없다. 그래서 05가 요소들을 프레임 하나로 감싼다. 남는 "보드" 글자 하나도 거슬리면 Figma에서 그 프레임 이름을 공백으로 바꾸면 된다.

## Scripter 실행 방법
1. Figma 데스크톱에서 파일을 열고 Page 3로 이동
2. Plugins → Scripter 실행 → New script → 파일 내용 전체 붙여넣기 → Run (Ctrl+Enter)
3. 위 순서대로 **각 파일을 한 번씩만** 실행 (03, 04는 다시 돌리면 중복 생성)
4. 중간 오류 시 Ctrl+Z로 되돌린 뒤 원인 수정 후 재실행

### 오류가 나면
- `Illegal return statement` → 파일 마지막 줄 `return {...};` 삭제
- `setCurrentPageAsync is not a function` → `await figma.setCurrentPageAsync(page);` 를 `figma.currentPage = page;` 로 교체
- `Cannot write to node with unloaded font` → Noto Sans KR 사용 가능 여부 확인 후 처음부터 재실행
- `The node with id ... does not exist` → 03 스크립트가 참조하는 섹션(526:2, 526:191, 526:303)이 삭제된 경우. ID만 바꿔 다시 받으면 된다

## 실행 후 확인할 것
- 04 보드: 메뉴 10개, 신규 2개에 NEW 뱃지
- 07 보드: 소스 6개 → 어댑터 3종 → RawListing → ② 정규화기 → 표준 상품 → ③ 이후, 아래에 "식품 > 과자" 별칭 예시와 새 사이트 추가 절차
- 05 보드: 8화면. 비용 설정의 환율 패널에 수동 입력이 없고 출처·갱신 시각만 있는지, 배송 프로필 탭이 있는지, 상품 목록에 소스 열과 "다른 소스 비교"가 있는지
- 01/03 보드: ①②, 외부 서비스, 환율, 어댑터 띠 문구가 바뀌었는지

## Claude 세션에서 실행할 때
Figma 커넥터 `use_figma`의 `code`로 넘긴다. `fileKey`는 위 값, `skillNames`는 `resource:figma-use,resource:figma-generate-design`.
04 스크립트는 50KB 제한에 가까우므로 use_figma로 보낼 때는 화면 4개씩 두 번에 나눠 보낸다(첫 번째 호출만 섹션 삭제·생성, 두 번째는 `figma.currentPage.children`에서 "05 "로 시작하는 섹션을 찾아 이어 붙인다).
