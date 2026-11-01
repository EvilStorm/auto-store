# auto-store 시스템 설계서 (v3 · Supabase 공용/개인 데이터 · 발굴 우선)

여러 해외 도매 사이트(중국 1688·타오바오·알리익스프레스, 일본 NETSEA·슈퍼딜리버리 등, 그리고 관리자가 직접 등록하는 사이트)에서 상품을 수집해 국내 판매가와 비교하고, 마진이 나는 상품을 선별해 스마트스토어 등록 정보까지 자동 생성하는 구매대행 보조 시스템.

작성일: 2026-11-01 (v3). v2(2026-10-29, 멀티 소스)는 git 이력에 있다.
상태: 설계 확정 (구현은 v2 기준 "URL 즉시 분석 CLI" 1조각만 존재, 8-1장)
기준 문서: Figma "정리합시다" Page 3 보드가 업무 정의의 기준이다. **단, v3 변경분은 아직 Figma에 반영되지 않았으므로 반영 전까지는 이 문서를 따른다.**

### v3에서 바뀐 것 (요약)

| 축 | v2 | v3 |
|---|---|---|
| 데이터베이스 | 집 PC의 SQLite | **Supabase Postgres 하나.** 로컬 DB 없음. PC는 크롤링·추론·스케줄만 하는 "손과 눈" |
| 데이터 소유 | 단일 사용자, 구분 없음 | **공용(shared)**: 크롤링·분석에 쓰는 사실 데이터(사전·수집 상품·네이버 카드·매칭·환율) / **개인(personal)**: 계정별 설정·관심 카테고리·후보·판단·이력·주문. RLS로 계정에 묶임 |
| 계정 | 관리자 1명(.env) | **Supabase Auth 로그인.** PC를 바꿔도 같은 계정이면 같은 데이터. 지금은 본인 1계정, 계정이 늘어도 되는 구조 |
| 우선 범위 | 수집→등록→주문 전체 | **발굴(①~⑤) 먼저.** 등록·주문(⑥~⑩)은 그 다음 |
| AI 사용 | 상품 1건마다 LLM 3회 | **발굴 단계 0회/건.** 추출은 내장 어댑터, 정규화는 사전·규칙, 매칭은 CLIP 이미지 유사도·이미지 해시·속성 규칙. LLM은 카드로 나갈 N건의 로고 확인과 사전 미등록 표기 제안에만 |
| CLIP | 운영 후 개선 | **MVP.** 매칭의 주력 |
| 비밀값 보관 | .env 또는 화면(암호화) | 개인 시크릿은 계정 소유 행(RLS) + Supabase Vault. **service_role 키는 PC에 두지 않음**(시드·마이그레이션 전용) |
| AI 결과 재사용 | 없음 (호출마다 새로) | **입력 해시 캐시(공용 `ai_results`)**: 같은 입력이면 요청자가 달라도 재호출 없음. **규칙 세트(공용 `rulesets`)**: AI는 소스×카테고리별 추출·정규화 규칙을 1회 만들고, 실행은 규칙 엔진이 한다 (3.5 · 3.6) |

---

## 1. 확정된 결정 사항

| 항목 | 결정 |
|---|---|
| 사업 형태 | 해외 구매대행 (목록통관 기준, 구매자 명의 통관) |
| 데이터베이스 | **Supabase Postgres (+ pgvector, Auth, Storage).** 로컬 DB 없음. 상태는 전부 클라우드, PC는 무상태 워커 |
| 계정 | Supabase Auth(이메일+비밀번호; Google 로그인은 선택). 계정 = 데이터 소유 단위. 역할은 `admin`(공용 참조 데이터 관리) / `user` |
| 공용 데이터 | 크롤링·분석에 쓰는 사실: 표준 카테고리·별칭 사전·브랜드 블랙리스트·요건표·네이버 카테고리·소스 정의·수집 상품·정규화 결과·네이버 카드 캐시·이미지 해시/임베딩·매칭·시장 신호·환율. 읽기는 로그인 사용자 전원, 참조 데이터 쓰기는 admin, 수집 데이터 쓰기는 워커(로그인 사용자) |
| 개인 데이터 | 설정(비용·매칭·스케줄·예산)·시크릿(LLM 키·텔레그램)·배송 프로필·관심 소스/카테고리·제외 규칙·후보와 판단·거절 이력·즉시 분석 이력·콘텐츠·패키지·등록 상품·감시·주문·API 사용량·실행 로그. `user_id = auth.uid()` RLS |
| 수집 소스 | 사이트를 등록한다. 1688만이 아니라 중국·일본 등 여러 도매 사이트를 같은 파이프라인으로 처리. 소스 정의는 공용, "내가 켜둔 소스와 요청 정책"은 개인 |
| 사이트별 수집기 | 소스 어댑터 구조. 내장 어댑터(코드) / 범용 CSS 셀렉터 어댑터 / LLM 추출 어댑터. **발굴 MVP는 1688 내장 어댑터** |
| 표기 차이 흡수 | 표준 카테고리와 별칭 사전(과자 = 스넥 = 零食 = お菓子 = snack). **사전이 정규화의 주역이고 LLM은 사전에 없는 표기를 제안하는 보조** |
| 매칭 방법 | **CLIP 이미지 유사도(로컬 추론) + 속성 규칙(용량·치수 숫자 일치) + 이미지 해시(동일 사진 판매자 수).** LLM 판정은 카드로 나갈 N건에 선택적 재판정 |
| 매칭 노출 | 소스 상품 하위에 "정확 매칭"과 "유사 매칭" 두 층. 임계값은 프리셋(엄격/보통/넓게)으로 개인 설정 |
| 국내 비교 가격 | 네이버 통합검색 쇼핑 블록 크롤링(API 종료). 결과는 **공용 캐시**(nv_mid 키, TTL 7일)에 쌓여 같은 검색어는 재크롤링하지 않음. 평균/중앙값/최저가는 모두 저장하고 어느 것을 쓸지는 개인 설정 |
| 수요 신호 | 1차: 네이버 카드의 리뷰 수·찜 수·판매처 수(크롤링으로 이미 확보). 2차: 데이터랩 쇼핑인사이트 API(붙으면 가점에 반영). 둘 다 AI 아님 |
| 마진 기준 | 마진율(%). 개인 설정 |
| 소스 원가 기준 | 최소 주문 수량 구간의 단가 × 최소 수량. 통화는 소스별 |
| 옵션 처리 | 1차 수집은 대표 옵션 1개. 승인 후 상세 수집에서 전체 옵션 |
| 제외 필터 | 공용: 사전·요건표·브랜드 블랙리스트에서 나오는 제외(식품·화장품·브랜드 텍스트). 개인: 재질·품목·키워드 추가 제외 규칙 |
| 비용 항목 | 전부 포함(소스가, 현지 배송비, 대리구매 수수료, 배대지, 관부가세, 네이버·결제 수수료, 환차손 완충). 배대지 요율과 현지 배송비는 개인 배송 프로필 |
| 환율 | 자동 수집만. 수출입은행 API → 네이버 금융 → open.er-api.com → 마지막값. **공용 테이블**, 하루 1회 먼저 갱신한 워커의 값을 모두가 씀 |
| 무게 누락 | 0 + "무게 미확인" 플래그 |
| 승인 단계 | 2단계. 1차 "조사 가치 있음", 2차 "이대로 등록 가능". 텔레그램 |
| 상세페이지 | 새로 생성(승인된 상품만, 여기서 LLM 사용). 모드 A/B/C |
| 등록 | 네이버 일괄등록 엑셀 양식으로 산출. 이미지는 Supabase Storage 공개 URL |
| 실행 주기 | 하루 1회 배치. 시각은 개인 설정(기본 02:00 / 08:00). 같은 계정의 PC가 둘이면 **배치 잠금**으로 한 PC만 실행 |
| 하루 건수 | 세 가지를 구분한다. **수집 규모**(관심 카테고리별 페이지 수) / **분석 상한**(하루 네이버 조회·LLM 호출 상한) / **카드 건수 N**(기본 10). 전부 개인 설정 |
| 브랜드·모조품 | 1단계 텍스트(1688 "品牌" 속성·제목 vs 블랙리스트)는 규칙으로 전수 적용. 2단계 이미지 로고는 **카드로 나갈 N건에만 비전 LLM**. 결과는 이미지 pHash 키로 공용 캐시 → 판매자가 사진을 바꾸기 전까지 같은 이미지는 다시 안 본다 |
| AI 결과 캐시 | **모든 AI 호출은 (용도 · 모델 · 입력 해시)를 키로 공용 `ai_results`에 저장하고, 같은 키가 있으면 호출하지 않는다.** 요청자(계정)가 달라도 입력이 같으면 재사용. 이미지는 URL이 아니라 pHash로 키를 만든다. 지점별 자연 키(pHash · 표기 · URL+텍스트 해시)를 따로 두어 사람이 읽을 수 있게 한다 (3.6) |
| 규칙 세트 | **AI는 블랙박스(규칙 세트)를 만들고, 실행은 프로그램이 한다.** 소스×카테고리별로 샘플 몇 페이지를 AI가 1회 분석해 추출·정규화·검색어 규칙을 **선언적 DSL(JSON)** 로 생성 → 샘플로 검증(커버리지) → admin 승인 → 공용 `rulesets` 활성. 런타임은 규칙 엔진만 돈다. 커버리지가 떨어지면(사이트 개편) 재생성. **LLM이 쓴 코드는 실행하지 않는다** (3.5) |
| 식품 | 다루지 않음. item_type food 자동 제외 |
| AI 제공자 | 텍스트 LLM(OpenAI 기본 / Claude / Gemini)·이미지 생성 선택. 키는 개인 시크릿 |
| API 예산 | 월 예산(개인), 80% 경고, 100%에서 ⑦ 중단. 발굴 단계는 예산을 거의 쓰지 않음 |
| 등록 후 감시 | 포함. 주기·임계값은 개인 설정 |
| 실행 환경 | 사용자의 PC(윈도우·맥 어느 쪽이든). 로그인 1회 후 세션 유지. 1688 브라우저 로그인 프로필은 PC별로 1회 |
| 관리자 웹 | 각 PC에서 로컬 FastAPI로 띄우고 Supabase Auth로 로그인. 호스팅은 2차 |

### 설계자가 덧붙인 주의점

- **공용 데이터는 "사실"만, 개인 데이터는 "판단과 설정"만.** 같은 1688 상품의 가격·이미지·네이버 매칭은 누가 봐도 같으니 공용이다. 그 상품이 나에게 마진이 나는지, 내가 거절했는지는 개인이다. 경계가 헷갈리면 "내 배대지 요율을 바꾸면 값이 달라지는가?"로 가른다 — 달라지면 개인이다.
- **무게 0 처리**: 배대지 요금이 0으로 계산되어 마진이 좋아 보인다. 플래그를 붙이고 1차 승인 후 상세 수집에서 무게를 다시 찾는다.
- **상품 사진 생성 금지**: 상세페이지를 새로 만들어도 상품 실물 사진은 원본에서 잘라 쓴다.
- **service_role 키를 PC에 두지 않는다**: 워커와 관리자 웹은 anon 키 + 사용자 로그인 JWT로만 접근한다. RLS가 울타리다. service_role은 스키마 마이그레이션·시드 스크립트에서만 쓰고 그 PC에서도 작업 후 지운다.
- **공용 수집 데이터는 오염될 수 있다**: 여러 계정이 쓰면 누군가의 크롤러가 잘못 파싱한 카드가 공용 캐시에 들어갈 수 있다. 모든 공용 수집 행에 `created_by`·`fetched_at`을 남기고, admin이 지울 수 있게 한다. 참조 데이터(사전)는 admin만 쓴다.
- **사이트별 이용약관**: 소스별 하루 상한과 요청 지연을 두고, 차단 시 자동 중단한다.
- **일본 소스 특이점**: 사업자 회원 승인 필요, 현지 배송비 높음. 배송 프로필에서 따로 둔다.

---

## 1-1. 운영 범위: 1차 발굴 → 2차 등록·주문

"돌아가는 시스템"을 먼저 만든다. v3에서는 **발굴이 끝까지 돌아가는 것**이 1차 목표다.

### 1차: 아이템 발굴 (①~⑤) — 이 범위가 끝나면 매일 아침 후보 카드를 받기 시작한다

| 업무 | 기능 |
|---|---|
| 계정·데이터 | Supabase Auth 로그인, 공용/개인 스키마와 RLS, 시드(표준 카테고리·별칭·브랜드 블랙리스트·요건표·네이버 카테고리·스톱워드), 개인 설정 화면 |
| 소싱 | 1688 내장 어댑터(목록·상세, 로그인 프로필), 관심 카테고리 등록(1688 카테고리 URL + 표준 카테고리 + 한국어 검색 키워드 + 페이지 수), 요청 정책·차단 감지, 수집 상품 공용 적재 |
| 정규화 | 사전 기반(재질·품목·카테고리·브랜드 텍스트·스톱워드 제거·숫자/단위 추출), 공용 제외(식품·화장품·브랜드), 미등록 표기 확인 큐(LLM 제안은 하루 상한) |
| 국내 조회 | 네이버 통합검색 크롤링 + 공용 캐시(TTL), 썸네일 이미지 해시·CLIP 임베딩, CLIP·규칙 매칭(정확/유사), 동일 이미지 판매자 수, 시장 신호(정확/유사 수·리뷰·찜·판매처·가격 평균/중앙값/최저) |
| 상품성 판단 | 개인 원가·마진율(대리구매 수수료·환차손 완충 포함), 후보 점수(마진 + 경쟁 + 수요 대리값 − 리스크), 품목 요건 3단계, 150달러 경계, 거절 이력·중복 방지, 하루 후보 N |
| 알림 | 텔레그램 1차 카드(이미지·원가·마진·경쟁·리뷰·근거), N건 로고 비전 확인, [승인][거절][보류], 요약 메시지, 배치 스케줄·잠금·미실행 경고·차단 알림 |
| 즉시 분석 | URL 1건 입력(텔레그램·웹·CLI). 등록 소스면 어댑터 경로(AI 0회), 미등록 사이트면 범용 LLM 추출 경로. 이력은 개인 테이블 |
| 관리자 웹 | 로그인, 대시보드, 관심 카테고리, 후보 목록(후보·미전송·거절), 사전·확인 큐(admin), 비용·매칭·시스템 설정 |

### 2차: 등록·주문·감시 (⑥~⑩) — 발굴이 돌아간 뒤

| 업무 | 기능 |
|---|---|
| 등록 | 상세 수집, 상품명 키워드 조합, 네이버 카테고리 자동 추천, 옵션 정리, 고지·배송·반품 블록, 이미지 모드 A + 템플릿, 2차 카드, Supabase Storage 업로드, 엑셀 산출 |
| 주문·배송 | 주문 처리 화면, 개인통관고유부호 체크리스트, 예상 도착일 |
| 재고·가격 유지 | 등록 상품 소스 감시(⑩) |
| 정산 | 주문별 실제 원가, 월 손익 |
| 소싱 확장 | 알리익스프레스 내장 어댑터, 범용 CSS 어댑터 |

### 운영 후 개선

타오바오·일본 B2B·LLM 추출 어댑터, 소스 간 그룹핑(pgvector 유사도로 쿼리 한 줄), 국내→소스 역방향 발굴(공용 네이버 캐시에서 "리뷰 많고 판매처 적은 상품"을 골라 1688에서 찾기), 정확도 프리셋 세분화, 이미지 모드 B/C, 커머스 API 자동 등록, 데이터랩 수요 신호, 환율 급변 재계산, CS 자동 안내, 관리자 웹 호스팅, 회계 연동.

---

## 2. 전체 워크플로우

### 발굴 배치 (①~⑤) — AI 0회/건

```
[새벽 02:00 · 개인 설정 시각 · 배치 잠금을 얻은 PC 한 대가 실행]
   │
   ▼
⓪ 준비
   공용 환율 갱신(오늘 갱신된 행이 없을 때만) · 사전 버전 확인 · 개인 설정 로드
   │
   ▼
① 소스별 수집기 (Source Adapters)                              → 공용 source_items
   내 관심 카테고리(개인) × 소스 어댑터(공용 정의) 순회
   1688 내장 어댑터: 목록 페이지 카드에서 제목(원문)·가격 구간·최소수량·대표 이미지·상품 ID 추출 (셀렉터/내장 JSON, LLM 없음)
   이미 공용에 있는 상품은 가격·재고·last_seen 만 갱신 → 상세 재수집 안 함
   캡차/차단 시 건너뛰고 카운트, 연속 차단이면 그 소스만 당일 중단
   │
   ▼
② 사전 정규화기 (Dictionary Normalizer)                        → 공용 source_items_normalized
   제목: 스톱워드(跨境·爆款·新款·批发·厂家直销·연도…) 제거, 숫자+단위(500ml·40oz·1.18L·30cm) 추출
   재질·품목: 속성표(材质 등) → attribute_aliases 사전 → 코드
   카테고리: 관심 카테고리에 매핑된 표준 카테고리 상속, 상품 분류 표기는 category_aliases 로 재확인
   검색어: 표준 카테고리의 한국어 키워드 + 추출한 핵심 숫자/단위 (2~3개)
   브랜드 텍스트: "品牌" 속성·제목 vs brand_blacklist → brand_text_hit
   공용 제외: item_type food/cosmetics/medical, brand_text_hit → excluded_reason (누구에게나 같은 이유)
   사전에 없는 표기 → mapping_queue (LLM 제안은 하루 상한 안에서만, 없으면 "미확정"으로 대기)
   │
   ▼
③ 국내 조회기 (Domestic Lookup)                               → 공용 naver_queries · naver_items · images · matches · market_signals
   검색어별 공용 캐시 확인: TTL(7일) 안이면 크롤링 생략
   네이버 통합검색 크롤링(Playwright): 제목·최저가·배송비·평점·리뷰·찜·판매처 수·nv_mid·cat_id·썸네일 → naver_items upsert
   썸네일 내려받아 pHash + CLIP 임베딩 → images (nv_mid 당 1회)
   소스 대표 이미지도 pHash + CLIP → images
   매칭 = CLIP 코사인 유사도(소스 vs 후보 20장, 로컬 계산) + 속성 규칙(핵심 숫자 일치) → exact / similar / unrelated
   동일 이미지 판매자 수 = pHash 해밍 거리 ≤ 임계값인 카드의 몰 수
   시장 신호 = 정확/유사 수 · 리뷰 평균/최대 · 찜 · 판매처 최대 · 가격 평균/중앙값/최저 · 최빈 cat_id
   │
   ▼
④ 개인 원가·점수 (Scoring)                                     → 개인 candidates
   내 설정으로: 환율(공용) × 배송 프로필 × 수수료율 → 총원가, 마진율
   내 가격 방식(평균/중앙값/최저) 선택, 내 제외 규칙 적용, 내 거절 이력·등록 상품과 중복이면 제외
   점수 = 마진율×100 + 경쟁 가점 + 수요 대리값(리뷰·찜 구간) − 리스크(무게 미확인·150달러·요건 필요)
   │
   ▼
⑤ 1차 알림 (아침 08:00 · 개인 설정 시각)
   마진율 ≥ 기준 중 점수 상위 N건 선정
   **N건에만** 비전 LLM: 대표 이미지에 타사 로고가 보이는지 → 보이면 brand_detected, 카드에서 제외하고 다음 순위 승격
   텔레그램 카드(이미지 포함): 소스·원가·마진율·경쟁(정확 N·동일 이미지 판매자 N)·리뷰·근거(유사도·일치 속성) [승인][거절][보류]
   요약: 소스별 수집/차단, 공용 제외, 개인 제외, 후보, 확인 대기 표기 수, 오늘 LLM 호출 수
   나머지는 관리자 "후보(미전송)"에서 조회
```

**AI가 쓰이는 지점 (전체 목록) — 전부 공용 `ai_results` 캐시를 거친다 (같은 입력이면 호출 없음):**
1. **규칙 세트 생성·재생성** (3.5): 소스×카테고리당 설정 때 1회, 커버리지가 떨어졌을 때 1회. 상품마다가 아니다
2. ⑤ 카드로 나갈 N건의 이미지 로고 확인 (비전). 키 = 이미지 pHash → 같은 사진은 다음 날·다른 계정에서도 다시 안 봄
3. ② 규칙 세트와 사전 모두에 없는 표기의 표준 카테고리·코드 제안 (하루 상한, 묶어서 1회, `mapping_queue` 유니크로 같은 표기 재제안 없음). 승인되면 사전·규칙에 들어가 0에 수렴
4. ⑦ 승인된 상품의 한국어 상품명·상세 설명·옵션 정리 (승인 건수만큼). 상품명·옵션 초안은 source_item 키로 공용 캐시
5. 즉시 분석에서 **미등록 사이트** URL의 범용 추출. 키 = (URL, 페이지 텍스트 해시) → 페이지가 안 바뀌었으면 재추출 없음 (등록 소스는 어댑터 경로라 0회)
6. 선택: N건의 매칭 LLM 재판정 (개인 설정으로 on/off). 결과는 공용 `matches.method='llm'`

하루 발굴 200건 기준 **첫날** LLM 호출 ≈ 규칙 생성 1~2회 + 로고 N회 + 제안 1회 ≈ 10~30회(수백 원). **둘째 날부터**는 새로 나타난 상품 중 카드에 오르는 것의 로고 확인만 → 수 회. v2 설계의 600회/일 대비 1/20 이하.

### 승인 이후 (⑥~⑨) — v2와 동일, 승인된 상품만

```
⑥ 상세 수집기  전체 옵션 · 상세 이미지 · 속성표 · 무게 재확인 (어댑터 detail)
⑦ 콘텐츠 생성기  예산 확인 → 상품명 후보 3개 · 옵션 한국어 표준화 · 설명문 · 금지 문구 검사 · 고정 블록 · 이미지 모드 A/B/C   ← LLM 사용
⑧ 2차 알림  미리보기 · 상품명 · 판매가 · 옵션 요약  [등록 패키지 생성][수정 요청][폐기]
⑨ 패키지 생성기  Supabase Storage 업로드 → 공개 URL → 네이버 일괄등록 엑셀 행 (개인 packages)
```

### 등록 후: ⑩ 소스 감시 (별도 주기) — v2와 동일

listed/suspended 상품의 소스를 개인 설정 주기(기본 3일)로 재수집해 가격·품절·옵션·최소수량·삭제를 감지하고 텔레그램 변동 카드 [판매가 수정][판매 중지][무시]. 재수집 결과는 공용 source_items 에도 반영된다(모두에게 최신 가격).

### 별도 입구: URL 즉시 분석

```
입구 1  텔레그램: 봇에게 소스 상품 URL
입구 2  관리자 웹: 상단 입력창
입구 3  CLI: python -m app.instant <URL>   (지금 돌아가는 조각)
   │
   ▼
URL → 소스 판별 (공용 sources.base_url 매칭)
   등록 소스  → 어댑터 detail → ② 사전 정규화 → ③ 국내 조회 → ④ 개인 점수 → 카드   (AI 0회, 공용 캐시에 적재)
   미등록 사이트 → 범용 스냅샷 → LLM 추출·정규화 → ③ → ④ → 카드   (v2 CLI 경로, LLM 2~3회)
   │
   ▼
개인 analysis_requests 에 이력 · 같은 URL 재요청 시 이전 결과와 나란히 · 하루 상한(개인 설정)
미등록 사이트 재요청: 페이지 텍스트 해시가 같으면 공용 page_extracts 의 이전 추출을 재사용 (LLM 0회) · 가격만 바뀌었으면 추출만 다시
```

### 주문 이후: 주문 처리 · 정산 — v2와 동일 (개인 orders · order_costs)

---

## 3. 멀티 소스 구조

### 3.1 소스 정의(공용)와 내 소스 설정(개인)

| 공용 `sources` | 개인 `user_sources` |
|---|---|
| 이름, 국가, 통화, base_url | enabled |
| adapter_key (`1688` / `taobao` / `aliexpress` / `netsea` / `superdelivery` / `generic_css` / `llm_extract`) | browser_profile_name (PC별 프로필 폴더 이름; 로그인은 PC마다 1회) |
| adapter_config (범용 CSS 셀렉터, LLM 추출 힌트) | delay_min_s, delay_max_s, daily_cap, block_tolerance |
| auth_mode (없음 / 브라우저 로그인) | shipping_profile_id (내 배송 프로필) |
| created_by | last_ok_at, consecutive_failures (내 PC 기준 헬스) |

### 3.2 어댑터 인터페이스 (v2와 동일)

```
class SourceAdapter:
    key: str
    def open_session(source, user_source) -> Session        # Playwright 컨텍스트, 로그인 프로필 로드
    def list(session, source_category, page) -> list[RawListing]
    def detail(session, item_id) -> RawDetail
    def is_blocked(page) -> bool
    def next_page(session) -> bool

RawListing:  item_id, url, title_raw, lang, price_raw(구간), currency, moq, image_url, category_raw, attrs_raw, weight_raw
RawDetail:   RawListing + options[], images[], attrs_full, package_weight_raw
```

- **내장 어댑터**: 셀렉터는 `selectors/<key>.yaml`. 1688은 목록·상세 모두 페이지 내장 JSON이 있는 경우가 많아 먼저 그쪽을 시도하고 DOM 셀렉터는 보조로 둔다(구현 시 확인).
- **범용 CSS 어댑터**: 관리자가 셀렉터 입력 + 1페이지 테스트. 2차 범위.
- **LLM 추출 어댑터**: 셀렉터 없이 시작. 즉시 분석의 미등록 사이트 경로가 이것이다. 2차 범위.

### 3.3 표준 카테고리와 별칭 사전 — v3에서 정규화의 주역

- `canonical_categories`: 표준 분류 트리. 네이버 cat_id, item_type(food/electronics/kids/cosmetics/medical/general), 기본 무게, **한국어 검색 키워드 목록**(`search_keywords_ko`)을 가진다. 검색어는 이 키워드 + 상품에서 추출한 숫자·단위로 조합한다.
- `category_aliases`: 표기(zh/ja/ko/en) → 표준 카테고리. 1688 카테고리명·빵부스러기가 여기 들어온다.
- `attribute_aliases`: `(material, "不锈钢")` → `stainless`, `(color, "黑色")` → `black`. 제외 규칙은 코드 기준.
- `brand_blacklist`: 브랜드·캐릭터명(迪士尼/디즈니/Disney, 三丽鸥/산리오…). 제목·"品牌" 속성에 걸리면 brand_text_hit.
- `title_stopwords`: 1688 제목의 광고 접두어. 검색어 추출 전에 제거.
- `requirements`: item_type → pass / required / excluded + 사유 + 필요 서류.
- `naver_categories`: cat_id → 경로명. 크롤러는 id만 주므로 표시용.
- `mapping_queue`: 사전에 없는 표기. LLM 제안(있으면)과 함께 대기, admin 승인 시 사전에 추가되어 **모든 계정**이 다음부터 자동 처리.

사전은 `dict_version`(정수)을 가진다. 사전이 바뀌면 버전이 오르고, 정규화 결과(`source_items_normalized.dict_version`)가 낮은 상품은 다음 배치에서 재정규화된다. 재정규화는 LLM 없이 사전 재조회라 비용이 없다.

### 3.4 새 사이트를 붙이는 절차 (v2와 동일)

1. 소스 등록(admin, 공용) 2. 내 소스 켜기 + 로그인 프로필 저장(개인, PC별) 3. 관심 카테고리 등록(개인) 4. 1페이지 테스트 → **규칙 세트 생성**(3.5, LLM 1회) 5. 활성화

### 3.5 규칙 세트 — AI는 블랙박스를 만들고, 실행은 프로그램이 한다

상품마다 AI를 부르면 비용·속도·차단 셋 다 문제다. 그런데 한 사이트의 한 카테고리 안에서 표기 패턴은 반복된다(제목 앞의 광고어, 속성표의 열 이름, 가격 구간 표기, 옵션 표기). 그 패턴을 **한 번 배워 프로그램으로 굳히면** 이후 수백 건은 비용 0으로 돈다. v2의 "LLM 추출 어댑터 → 셀렉터 제안 → 범용 CSS로 승격"(3.2)이 이 생각의 특수 사례였고, v3는 추출뿐 아니라 정규화·검색어까지 같은 틀로 넓힌다.

**규칙 세트는 코드가 아니라 선언적 DSL(JSON)이다.** 연산은 고정된 몇 가지뿐이고 규칙 엔진(`taxonomy/engine.py`)이 해석한다. LLM이 쓴 파이썬을 실행하지 않는다 — 보안(임의 코드 실행), 디버깅(무엇이 왜 틀렸는지), 버전 관리(사이트가 바뀌면 어디를 고치나) 세 가지 이유다. 사람이 쓴 어댑터 코드(`sources/s1688.py`)는 코드로 두되, 그 안의 셀렉터·JSON 경로·정규식은 규칙 세트에서 읽는다.

| 연산 | 하는 일 | 예 |
|---|---|---|
| `select` | CSS 셀렉터 / JSON 경로로 값 추출 | `{"op":"select","path":"$.data.offerList[*].subject","as":"title_raw"}` |
| `regex` | 정규식 그룹 추출 (여러 패턴 순서대로) | 제목에서 용량 `(\d+(?:\.\d+)?)\s*(ml|L|oz)` → `capacity` |
| `unit` | 단위 정규화 | `40oz` → `1183ml`, `1.18L` → `1180ml` |
| `strip` | 스톱워드·광고어 제거 (공용 사전 + 카테고리 추가분) | `跨境 爆款 2025新款 不锈钢保温杯` → `不锈钢保温杯` |
| `map` | 사전 참조로 코드화 | `材质: 不锈钢` → `material_code = stainless` |
| `template` | 검색어 조합 | `"{keyword_ko} {capacity}"` → `"스테인리스 텀블러 1180ml"` |
| `default` | 카테고리 상속값 | `item_type`, `default_weight_g`, 요건 기본 |
| `flag` | 조건 플래그 | 제목에 `充电|电池|USB` → `maybe_electronics` |

**종류(kind)**: `extract`(목록·상세 셀렉터/JSON 경로) · `normalize`(제목 정리·속성 추출·재질/품목 코드·요건 기본) · `query`(검색어 템플릿 2~3개) · `match_hints`(매칭 때 비교할 핵심 숫자 속성: 용량·치수). **범위와 상속**: 소스 전체 기본 세트 → 카테고리별 오버라이드. 60개(2소스 × 30카테고리)를 전부 만들지 않고, 기본 세트의 커버리지가 모자란 카테고리만 덧씌운다.

**생성 흐름 (LLM 1회):**
1. 샘플 수집 — 관심 카테고리 2페이지 ≈ 40건 RawListing + 상세 3건 (어댑터의 "1페이지 테스트"가 이 샘플을 만든다)
2. LLM 호출 1회 — 샘플 + DSL 스키마 + 공용 사전의 코드 목록 + 상위 규칙 세트(있으면) → 규칙 세트 초안 + 각 규칙의 근거 한 줄. 이 호출도 `ai_results` 캐시를 거친다
3. 검증 — 엔진으로 샘플 전체를 실행해 **필드별 커버리지**(제목 정리 100%, 용량 추출 85%, 재질 코드 78%…)와 홀드아웃 1페이지 결과를 낸다. 규칙이 샘플에서 틀리면 그 자리에서 보인다
4. 승인 — admin이 커버리지 표와 실패 예시를 보고 승인(커버리지 ≥ 기준이면 자동 승인 옵션). `status = active`, `version + 1`, 이전 버전은 `retired`
5. 런타임 — ②는 active 규칙 세트만 쓴다. 규칙으로 못 잡은 표기는 사전(3.3) → 확인 큐 순서로 떨어진다

**드리프트(사이트 개편) 감지**: 배치마다 규칙 세트별 커버리지를 `rulesets.coverage_json`에 기록한다. 2회 연속 기준(기본 80%) 미달이면 `needs_regen` 플래그 + 관리자 알림 → 새 샘플로 재생성(LLM 1회). "셀렉터가 깨졌는데 며칠 모르고 지나가는" 사고를 이걸로 막는다.

**비용**: 소스×카테고리당 생성 1회 + 가끔 재생성. 하루 수백 건 정규화는 0. **한계**: 규칙은 "패턴"을 잡는다. 상품 개별 판단(이 둘이 같은 상품인가, 이 사진에 로고가 있나)은 규칙이 아니라 모델(CLIP)·비전 + 캐시(3.6)가 맡는다.

### 3.6 AI 결과 캐시 — 같은 입력에는 다시 묻지 않는다

**원칙**: 모든 AI 호출은 `(purpose, model, input_hash)`를 키로 공용 `ai_results`에 저장하고, 같은 키가 있으면 호출하지 않고 저장된 출력을 돌려준다. 요청한 계정이 달라도 같다 — "같은 입력이면 같은 답"은 사실이라 공용이 정당하다.

- **키 만들기**: `input_hash = sha256(purpose@프롬프트버전 | model | 정규화한 프롬프트 텍스트 | 이미지 pHash 목록)`. 이미지는 **URL이 아니라 pHash**로 넣는다 — 판매자가 사진을 바꾸지 않았으면 CDN 주소가 달라도, 다른 상품 페이지에 같은 사진이 쓰여도 같은 키다. 프롬프트 템플릿이 바뀌면 `purpose`의 버전을 올려 자연히 새 키가 된다.
- **구현 위치**: `adapters/llm/base.py`의 `complete_json`이 먼저 캐시를 보고, 적중이면 출력을 돌려주며 `hits + 1`, `api_usage`에는 비용 0으로 기록. 미스면 호출 후 저장. 파이프라인 코드는 캐시를 모른다.
- **자연 키**: 해시만으로는 사람이 못 읽으니 지점별로 읽을 수 있는 키를 함께 둔다.

| 지점 | 자연 키 | 저장 위치 |
|---|---|---|
| 로고 비전 확인 | 이미지 pHash | `images.logo_checked_at · logo_detected · logo_reason` |
| 규칙 세트 생성 | (source_id, category_id, 샘플 해시) | `rulesets` (version) |
| 표기 제안 | (kind, term, lang) | `mapping_queue` 유니크 |
| 미등록 사이트 추출 | (url, 텍스트 해시) | `page_extracts` |
| 상품명·옵션 한국어 초안 | source_item_id | `source_item_ko_drafts` |
| 매칭 재판정 | (source_item_id, 후보 nv_mid 집합 해시) | `matches.method = 'llm'` |

- **무효화**: TTL이 없다 — 입력이 같으면 답도 같다. 모델이나 프롬프트 버전이 바뀌면 키가 달라져 자연히 재계산된다. 판매자가 사진을 바꾸면 pHash가 바뀌어 재확인된다.
- **예산 귀속**: 캐시 적중은 공용 이득이지만 실제 호출 비용은 호출한 계정의 `api_usage`에만 쌓인다.
- **재분석이 다시 도는 조건은 네 가지뿐**: 소스 가격·옵션 변동, 사전 또는 규칙 세트 버전 상승, 네이버 캐시 TTL 만료, 대표 이미지 pHash 변화. 그 외에는 저장된 데이터로 ④ 점수만 다시 계산한다.

---

## 4. 시스템 구성

### 4.1 컴포넌트

```
┌─────────────────────────────────────┐        ┌──────────────────────────────────────────────┐
│  사용자 PC (윈도우 · 맥, 여러 대 가능)   │        │  Supabase 프로젝트                            │
│                                     │        │                                              │
│  app.auth   로그인 1회 → 세션 저장     │◀──────▶│  Auth        이메일 로그인, JWT, profiles.role  │
│  app.worker 배치 잠금 → ①~⑤ 실행      │ anon  │                                              │
│    · Playwright 크롤링 (1688 · 네이버)  │ key + │  Postgres    공용 스키마 (사전·수집·캐시·매칭)    │
│    · CLIP · pHash 로컬 추론            │ JWT   │              개인 스키마 (설정·후보·판단·주문)     │
│    · APScheduler                      │ (RLS) │              pgvector (이미지 임베딩)            │
│  app.admin  로컬 FastAPI 관리자 웹      │        │              RPC (유사도 검색 · 시크릿 · 잠금)   │
│  app.telegram 봇 폴링 (잠금 보유 PC만)   │        │                                              │
│                                     │        │  Storage     생성 이미지 공개 버킷               │
│  로컬에 남는 것: 세션 토큰, 1688 브라우저  │        │  Vault       개인 시크릿 (LLM 키 · 봇 토큰)      │
│  로그인 프로필, CLIP 모델 파일만          │        │                                              │
└─────────────────────────────────────┘        └──────────────────────────────────────────────┘
        │              │                  │                    │
    도매 사이트     네이버 통합검색      LLM 제공자(N건만)      환율 API · 텔레그램
```

- **PC는 무상태 워커**다. 분석 이력, 설정, 후보, 캐시 전부 Supabase에 있다. 다른 PC에서 로그인하면 그대로 이어진다.
- **PC에 남는 것** 세 가지: (1) 로그인 세션 토큰(`~/.auto-store/session.json`, 재로그인으로 재생성) (2) 1688 등 로그인이 필요한 소스의 브라우저 프로필(쿠키가 기기에 묶여 이식 불가, PC마다 1회 로그인) (3) CLIP 모델 파일(첫 실행 시 자동 다운로드). 그리고 접속 정보인 환경 파일 `.env.dev` / `.env.prd`(상태가 아니라 "어느 Supabase를 보는가"의 선택).
- **같은 계정의 PC 둘**: `batch_locks (user_id, run_date, kind)` 유니크 제약으로 먼저 insert한 PC가 실행. 텔레그램 폴링도 `worker_leases` 임대(heartbeat)를 가진 PC 하나만 한다(11장).

### 4.2 기술 스택

| 영역 | 선택 | 이유 |
|---|---|---|
| 언어 | Python 3.12 | 크롤링·이미지·LLM 라이브러리 |
| DB·인증·스토리지 | **Supabase** (Postgres + pgvector + Auth + Storage + Vault), `supabase-py` | 로컬 DB 제거, 계정별 RLS, 벡터 검색, 이미지 공개 URL을 한 곳에서 |
| DB 접근 | PostgREST(`supabase-py`) + SQL RPC 함수 | SQLAlchemy 제거. 복잡한 쿼리(유사도·집계)는 RPC로 |
| 크롤링 | Playwright (Chromium, 소스별 persistent context) | 로그인 유지, 봇 탐지 대응 |
| 이미지 유사도 | **CLIP (open_clip ViT-B/32, 로컬 CPU)** + `imagehash` pHash | 매칭 주력. 썸네일 20장 추론 1~2초. 모델 ~350MB, torch 포함 설치 ~2GB |
| 웹 프레임워크 | FastAPI + Jinja2 + HTMX (로컬) | 관리자 화면. Supabase Auth 세션으로 호출 |
| 스케줄러 | APScheduler (PC별) + DB 잠금 | 별도 데몬 불필요 |
| 텔레그램 | python-telegram-bot | 인라인 버튼 콜백. 봇 토큰은 개인 시크릿 |
| LLM | 제공자 선택형 어댑터: OpenAI (기본) / Claude / Gemini. `complete_json` 공통 인터페이스, 사용량은 개인 api_usage | 로고 확인 · 사전 제안 · 콘텐츠 생성 · 미등록 사이트 추출 |
| 이미지 생성 | Gemini / OpenAI | 모드 C만 |
| 엑셀 | openpyxl | 네이버 일괄등록 양식 |
| 환율 | 수출입은행 API → 네이버 금융 → open.er-api.com → 마지막값 | 공용 exchange_rates |

### 4.3 Supabase 무료 플랜 한도와 데이터 양

무료: DB 500MB, Storage 1GB, 일주일 무활동 시 프로젝트 일시 중지(매일 배치가 돌면 해당 없음).
하루 발굴 200건 × 검색어 2개 × 카드 20장에서 nv_mid 중복을 제거하면 신규 카드 1,000~2,000건/일로 추정, 행 1KB + 임베딩 2KB(512 float32) → **월 100MB 안팎**. 무료 한도는 서너 달. 대응: (1) 임베딩은 매칭에 쓰인 카드만 보존 (2) 60일 이상 어느 매칭에도 안 쓰인 naver_items 정리 (3) 그래도 넘으면 Pro($25/월, 8GB). 수치는 추정이며 운영 첫 달에 실측해 조정한다.

---

## 5. 데이터 모델

모든 테이블은 Supabase Postgres에 있다. **공용**은 `user_id`가 없고 `created_by`만 있다. **개인**은 `user_id uuid not null references auth.users` 가 있고 RLS로 `user_id = auth.uid()` 행만 보인다.

### 5.0 계정·권한

**profiles** (개인, 1행/계정)
| 컬럼 | 설명 |
|---|---|
| user_id (PK, = auth.users.id) | |
| display_name | |
| role | `admin` / `user`. 첫 계정은 시드로 admin |
| telegram_chat_id | 봇 메시지 라우팅 |
| created_at | |

RLS 정책 세 종류:
```sql
-- (A) 개인 테이블: 내 행만 읽고 쓴다
create policy own_rows on candidates for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());

-- (B) 공용 참조 데이터(사전·요건표·소스 정의): 전원 읽기, admin 만 쓰기
create policy read_all  on category_aliases for select to authenticated using (true);
create policy admin_rw  on category_aliases for all    to authenticated using (is_admin()) with check (is_admin());

-- (C) 공용 수집 데이터(수집 상품·네이버 카드·이미지·매칭·환율): 전원 읽기, 전원 추가·갱신, admin 만 삭제
create policy read_all      on naver_items for select to authenticated using (true);
create policy worker_insert on naver_items for insert to authenticated with check (created_by = auth.uid());
create policy worker_update on naver_items for update to authenticated using (true);
create policy admin_delete  on naver_items for delete to authenticated using (is_admin());
```
`is_admin()`은 `profiles.role = 'admin'`을 보는 `security definer` 함수. 개인 시크릿은 Vault에 두고 `get_my_secret(name)` / `set_my_secret(name, value)` RPC(security definer, `auth.uid()` 검사)로만 접근한다. 처음 구현에서는 RLS 보호 컬럼(`user_secrets`)으로 시작하고 Vault로 승격해도 된다.

### 5.1 공용 참조 데이터 (admin 관리, 시드)

| 테이블 | 핵심 컬럼 |
|---|---|
| **sources** | id, name, country, currency, base_url, adapter_key, adapter_config_json, auth_mode, created_by |
| **source_categories** | id, source_id, label_raw, url, canonical_category_id, created_by — "1688의 이 URL은 이 표준 카테고리"라는 사실 |
| **canonical_categories** | id, parent_id, path, naver_cat_id, item_type, default_weight_g, **search_keywords_ko[]** |
| **category_aliases** | term, lang, canonical_category_id, origin(seed/manual/llm), confidence |
| **attribute_aliases** | kind(material/color/item_type…), term, lang, code |
| **brand_blacklist** | name, lang, kind(brand/character), note |
| **title_stopwords** | term, lang |
| **requirements** | item_type, status(pass/required/excluded), reason, docs |
| **naver_categories** | cat_id, path, fetched_at |
| **mapping_queue** | kind, term, lang, source_id, sample_item_id, suggested_id_or_code, confidence, status(pending/approved/rejected), created_by — `unique(kind, term, lang)` 로 같은 표기 재제안 없음 |
| **dict_meta** | dict_version, updated_at — 사전 변경 시 +1 |
| **rulesets** | id, source_id, canonical_category_id(null = 소스 기본), kind(extract/normalize/query/match_hints), version, rules_json(DSL), rationale_json, sample_item_ids[], coverage_json(필드별 %), status(draft/active/retired/needs_regen), generated_by(llm/manual), approved_by, created_at — 3.5 |

### 5.2 공용 수집 데이터 (워커 적재)

| 테이블 | 핵심 컬럼 |
|---|---|
| **source_items** | id, source_id, source_item_id (유니크 쌍), url, title_raw, lang, price_tiers_json, currency, moq, main_image_url, category_raw, attrs_raw_json, weight_raw, first_seen_at, last_seen_at, last_price_src, sold_out, created_by |
| **source_items_normalized** | source_item_id (PK), dict_version, title_clean, key_numbers_json(용량·치수), material_code, item_type, canonical_category_id, search_queries[], brand_text_hit, excluded_reason(null/food/cosmetics/brand_text/…), mapping_pending(bool), normalized_at |
| **images** | id, kind(source/naver), ref_id(source_item_id 또는 nv_mid), url, phash(bigint), **clip vector(512)**, fetched_at, logo_checked_at, logo_detected, logo_reason — 로고 비전 결과는 pHash 키로 1회 |
| **naver_queries** | query (PK), fetched_at, nv_mids[], blocked, created_by — TTL 캐시 키 |
| **naver_items** | nv_mid (PK), title, price, shipping_krw, rating, review_count, wish_count, seller_count, mall, link, image_url, cat_id, kind(catalog/store), is_ad, fetched_at, created_by |
| **matches** | source_item_id, nv_mid, relation(exact/similar), method(clip/rule/llm), similarity, matched_numbers_json, reason, computed_at |
| **market_signals** | source_item_id (PK), exact_count, similar_count, total_results, same_image_sellers, review_avg, review_top, wish_top, seller_count_max, price_mean, price_median, price_min, basis_type(exact/similar), naver_cat_id, demand_trend_pct(null), computed_at |
| **source_item_details** | source_item_id (PK), options_json, images[], attrs_full_json, package_weight_g, fetched_at — ⑥에서 채움 |
| **exchange_rates** | currency, rate_krw, source, fetched_at (하루 1행/통화) |
| **ai_results** | purpose(버전 포함), model, input_hash (유니크), output_json, est_cost_krw, hits, created_by, created_at — 3.6. 모든 LLM 호출의 캐시 |
| **page_extracts** | url, text_hash (유니크 쌍), raw_json(RawDetail), extracted_at, created_by — 미등록 사이트 즉시 분석의 추출 캐시 |
| **source_item_ko_drafts** | source_item_id (PK), title_ko_options[], options_ko_json, generated_at — ⑦ 상품명·옵션 한국어 초안 (설명문은 개인) |

### 5.3 개인 데이터 (RLS `user_id = auth.uid()`)

| 테이블 | 핵심 컬럼 |
|---|---|
| **user_settings** | user_id (PK), 비용(proxy_fee_rate, customs_duty_rate, vat_rate, customs_limit_usd, customs_warn_usd, naver_fee_rate, payment_fee_rate, fx_buffer_rate, target_margin_rate, margin_threshold), 매칭(price_basis, match_preset, exact_threshold, similar_threshold, same_image_seller_cap, llm_rejudge_top_n), 건수(daily_candidate_n, daily_lookup_cap, daily_llm_cap, instant_daily_limit), 스케줄(collect_at, notify_at, days, monitor_interval_days, monitor_price_threshold), 예산(monthly_budget_krw, warn_ratio, exceeded_action), AI(llm_provider, llm_model, image_provider), 콘텐츠(image_mode, notice_template) |
| **user_secrets** (또는 Vault) | user_id, name(openai_api_key/anthropic_api_key/google_ai_api_key/telegram_bot_token/eximbank_api_key), value |
| **shipping_profiles** | id, user_id, name, country, currency, rate_table_json, local_shipping_default, proxy_fee_rate, lead_days |
| **user_sources** | user_id, source_id, enabled, browser_profile_name, delay_min_s, delay_max_s, daily_cap, block_tolerance, shipping_profile_id, last_ok_at, consecutive_failures |
| **user_watch_categories** | id, user_id, source_category_id, max_pages, enabled, extra_keywords_ko[], added_at — "내가 훑는 카테고리" |
| **user_exclusion_rules** | user_id, kind(material/item_type/keyword), code_or_term, enabled |
| **candidates** | id, user_id, source_item_id, run_date, cost_breakdown_json, margin_rate, suggested_price_krw, score, score_parts_json, flags[], status(아래 상태 머신), card_sent_at, decision, decided_at, brand_vision_checked, origin(batch/instant) |
| **rejections** | user_id, source_id, source_item_id, image_phash, reason, rejected_at, until |
| **analysis_requests** | id, user_id, requested_at, channel(telegram/web/cli), url, source_id, source_item_id, candidate_id, status, summary_json, decision, error |
| **generated_contents** | candidate_id, user_id, title_options[], title_chosen, description_html, options_ko_json, blocks_json, image_urls[], mode, llm_cost_krw, created_at |
| **packages** | candidate_id, user_id, excel_row_json, image_public_urls[], output_path, created_at |
| **listings** | candidate_id, user_id, store_product_no, sale_price_krw, listed_at, suspended_at, monitor_status, last_checked_at, consecutive_failures |
| **monitor_events** | listing_id, user_id, kind, before_json, after_json, recalculated_margin, notified_at, decision, decided_at |
| **orders** / **order_costs** | v2와 동일 + user_id |
| **api_usage** | user_id, provider, model, purpose, candidate_id, input_tokens, output_tokens, images, est_cost_krw, called_at |
| **run_logs** | user_id, run_date, kind(collect/lookup/score/notify/monitor/instant), source_id, stage, counts_json, error, pc_name, started_at, finished_at |
| **batch_locks** | user_id, run_date, kind, pc_name, acquired_at — `unique(user_id, run_date, kind)` |
| **worker_leases** | user_id, kind(telegram), pc_name, expires_at — heartbeat 임대 |

### 5.4 후보 상태 머신 (개인 `candidates.status`)

```
candidate ─▶ held / rejected_1
     ▶ approved_1 ─▶ detail_collected ─▶ content_generated ─▶ rejected_2 / revise
                                                            ▶ approved_2 ─▶ packaged ─▶ listed ─▶ suspended
```

v2의 `collected → normalized → filtered_out → matched → below_margin`은 공용 테이블의 **존재 여부와 컬럼**으로 표현된다: source_items(수집됨) → source_items_normalized(정규화됨, `excluded_reason`이 있으면 공용 제외, `mapping_pending`이면 확인 대기) → market_signals(조회됨). 마진 미달·개인 제외는 candidates 행을 만들지 않거나 `status = below_margin`으로 남겨 "후보(미전송)" 조회에 쓴다.

---

## 6. 단계별 상세 설계

### ⓪ 로그인·세션
- `python -m app.auth login`: 이메일·비밀번호 → Supabase Auth → access/refresh 토큰을 `~/.auto-store/session.json`(또는 OS 키링)에 저장. 이후 모든 명령은 세션을 복원해 anon 키 + JWT로 호출한다. 만료 시 refresh, 실패 시 재로그인 안내.
- 첫 로그인 시 `user_settings`가 없으면 `.env.{APP_ENV}`의 기본값으로 1행을 만든다(환경 파일은 접속 정보 + 부트스트랩 전용, 이후 화면에서 수정).

### ① 소스별 수집기
- 내 `user_watch_categories` × `user_sources.enabled` 를 순회. 어댑터는 공용 `sources` 정의로 만들고 로그인 프로필은 PC 로컬.
- RawListing → `source_items` upsert(`source_id, source_item_id`). 이미 있으면 가격·재고·last_seen만 갱신하고 ②③을 건너뛸 수 있는지 판단: 가격 변동 없고 정규화 `dict_version` 최신이고 market_signals 7일 이내면 **④로 직행**(내 설정으로 점수만 다시).
- 하루 상한: `user_sources.daily_cap`(소스 요청 수) + `user_settings.daily_lookup_cap`(네이버 조회 수). 둘 중 먼저 닿으면 당일 중단하고 요약에 표시.

### ② 사전 정규화기
- LLM 없이 결정적으로 돈다. 입력이 같고 규칙·사전이 같으면 결과가 같다 → 공용 저장이 정당하다.
- 실행 순서는 **규칙 세트(active, 카테고리 → 소스 기본 상속) → 공용 사전 → 확인 큐**다. 규칙 엔진이 `extract`·`normalize`·`query` 세트를 적용해 제목 정리·핵심 숫자·재질/품목 코드·검색어를 만들고, 규칙이 못 잡은 표기만 사전을 찾고, 사전에도 없으면 큐로 보낸다. 배치마다 규칙 세트별 커버리지를 기록해 드리프트를 본다(3.5).
- 숫자·단위 추출 정규식은 `taxonomy/units.py`에 모은다(ml/L/oz/cm/mm/inch/g/kg/W/mAh/매/개입 등). 추출 결과가 검색어와 매칭 규칙 둘 다에 쓰인다.
- 검색어 조합 규칙: `[표준 카테고리 키워드 1] + [핵심 숫자 1~2]`, `[키워드 2] + [재질 한국어]`. 관심 카테고리의 `extra_keywords_ko`가 있으면 우선. 최대 3개, 각 20자 이내.
- 사전에 없는 재질·분류 표기는 `mapping_queue`에 넣고 `mapping_pending = true`. **LLM 제안은 `daily_llm_cap` 안에서 하루 한 번 묶어서**(미등록 표기 20개를 한 호출에) 요청한다. 제안이 없어도 상품은 카테고리 상속값으로 ③까지 진행하되, item_type을 몰라 요건 판정이 불가하면 카드에 "요건 미확정" 배지.
- 공용 제외(`excluded_reason`)는 요건표·블랙리스트에서 나오므로 계정과 무관하다. 개인 제외는 ④에서.

### ③ 국내 조회기
- 캐시: `naver_queries.fetched_at`이 7일 이내면 `nv_mids`로 `naver_items`를 읽고 크롤링을 생략한다. 서로 다른 계정이 같은 카테고리를 보면 두 번째부터는 네이버 요청이 0이다.
- 크롤링: `app/adapters/naver_crawl.py`(구현 완료). 검색어 사이 1.5~3.5초, 차단 감지 시 그 상품은 "조회 생략"으로 두고 다음 배치에 재시도. 광고 카드 제외.
- 이미지: 썸네일(`?type=f300`)을 내려받아 pHash·CLIP. 이미 `images`에 있는 nv_mid는 건너뛴다. 소스 대표 이미지도 같은 테이블.
- 매칭 판정(개인 프리셋이 아니라 공용 기본 임계값으로 1회 계산, 개인 프리셋은 ④에서 relation을 다시 자름):
  - CLIP 코사인 ≥ 0.95 → exact 후보(거의 동일 사진), 0.70~0.95 → similar 후보, 미만 → unrelated. pHash 동일 사진은 코사인과 무관하게 exact. **실측상 CLIP 만으로는 같은 카테고리의 다른 상품을 가르지 못하므로(11장), 카드로 나가는 N건은 LLM 재판정으로 exact 를 확정한다**
  - 핵심 숫자(용량·치수)가 추출됐고 후보 제목에 다른 값이 명시되면 한 단계 강등(exact → similar)
  - 같은 결과에서 pHash 해밍 ≤ 6인 카드 수 = `same_image_sellers`
  - 임계값은 공용 `dict_meta`에 두고 실데이터로 조정(11장)
- `market_signals`에 평균·중앙값·최저를 모두 저장. `basis_type`은 exact가 있으면 exact.
- 20장 비교는 파이썬에서 바로 계산한다. pgvector는 "이 소스 이미지와 비슷한 다른 소스 상품"(그룹핑)과 "이 네이버 이미지를 쓰는 다른 소스 상품"처럼 **테이블 전체 검색**에 쓴다.

### ④ 개인 원가·점수
```
구매원가     = price_src(MOQ 구간) × moq × 환율(currency)            ← 공용 환율
현지배송     = local_shipping_src × 환율  (없으면 내 배송 프로필 기본값)
대리구매수수료 = (구매원가 + 현지배송) × 내 배송프로필.proxy_fee_rate
배대지요금   = 내 배송프로필.요율표[무게구간]  (무게 0 → 0 + weight_unknown)
과세가격USD  = (구매원가 + 현지배송) / USD환율
관부가세     = 과세가격 ≤ 150 ? 0 : (구매원가+현지배송) × (관세율 + 부가세율×(1+관세율))
네이버·결제수수료 = 국내비교가 × 내 수수료율
환차손완충   = 구매원가 × 내 완충율
총원가, 마진율 = (국내비교가 − 총원가) / 국내비교가
국내비교가   = market_signals 의 price_mean | price_median | price_min 중 내 설정
제안 판매가  = (총원가 − 수수료) ÷ (1 − 목표마진율 − 수수료율), 100원 올림
```
후보 점수:
```
점수 = 마진율×100
     + 경쟁: 정확 0~2건 +15, 3~5건 +5, 6건 이상 0 · 동일 이미지 판매자 ≥ cap −20 · 가격비교 판매처 ≥ 100곳 −10
     + 수요 대리값: 정확/유사 매칭의 리뷰 최대 ≥ 1,000 +10, 100~999 +5, 찜 ≥ 500 +5   (데이터랩 붙으면 추이 ±10으로 교체)
     − 리스크: 무게 미확인 −5, 150달러 경계 −5, 요건 필요 −10, 요건 미확정 −10
```
- 내 거절 이력(`rejections`: 같은 source_item_id 또는 pHash 해밍 ≤ 6)과 내 `listings`에 있으면 후보 제외.
- 내 `user_exclusion_rules`(재질·품목·키워드) 적용.
- 결과는 `candidates` 1행(run_date 당 상품 1건). 기준 미달은 `below_margin`.

### ⑤ 1차 알림
- 점수순 상위 N. **N건에만** 비전 LLM으로 로고 확인 — 단, 대표 이미지 pHash로 공용 `images.logo_*`를 먼저 보고, 이미 확인된 이미지면 호출 없이 그 결과를 쓴다(다음 날·다른 계정 모두). 결과는 `images`에 저장하고 후보에는 `brand_vision_checked = true`만 표시. 감지되면 `rejected_1(brand)` + `rejections`에 기록, 다음 순위 승격(최대 2N건까지 확인).
- 카드: 이미지 · `[1688 · CN]` 배지 · 원가(¥·₩) · 마진율 · 제안 판매가 · 경쟁(정확 N · 유사 N · 동일 이미지 판매자 N · 판매처 최대 N) · 리뷰(최대) · 근거("이미지 유사도 0.93 · 용량 500ml 일치") · 주의 플래그 · 네이버 링크 상위 2개.
- 요약에 "오늘 LLM 호출 N회 · 추정 비용 N원"을 넣어 AI 사용이 보이게 한다.

### ⑥~⑩ — v2와 동일
⑥ 상세 수집은 공용 `source_item_details`에 적재(한 번 수집하면 모두가 씀). ⑦은 개인 `generated_contents`, LLM 사용, 예산 체크. ⑧⑨ 개인. ⑩ 감시는 내 `listings` 대상이되 재수집 결과는 공용 `source_items`에도 반영.

---

## 7. 관리자 웹 화면

로컬 FastAPI(`localhost:8000`). 첫 화면은 **로그인**(Supabase Auth). 메뉴:

1. **대시보드**: 오늘 배치(잠금 보유 PC·단계·건수), 후보 N, 확인 대기 표기 수, LLM 호출·비용, 차단·오류, 수동 실행
2. **관심 카테고리** (개인): 소스 선택 → 1688 카테고리 URL · 표준 카테고리(사전이 추천) · 추가 한국어 키워드 · 페이지 수 · 사용 여부 · 1페이지 테스트
3. **후보 목록** (개인): 상단 "URL 즉시 분석" 입력창, 탭 = 오늘 카드 / 후보(미전송) / 보류 / 거절 / 승인 진행중, 상세(원가 내역·매칭 이미지 나열·근거·점수 분해), 재점수, 수동 승인/거절, 즉시 분석 이력
4. **내 소스** (개인): 켜기/끄기, 요청 정책, 배송 프로필 지정, 로그인 프로필 저장(브라우저 열기), 헬스
5. **비용 설정** (개인): 환율 현황(공용, 조회만), 배송 프로필 탭, 관세·부가세, 수수료, 마진 기준·목표
6. **매칭 설정** (개인): 가격 방식, 프리셋·임계값, 동일 이미지 cap, 하루 카드 N, 하루 조회 상한, LLM 재판정 on/off
7. **제외 규칙** (개인): 재질 / 품목 / 키워드 + 공용 제외 사유 보기(읽기)
8. **사전 관리** (admin): 표준 카테고리 트리·검색 키워드, 별칭, 속성 코드, 브랜드 블랙리스트, 스톱워드, 요건표, **확인 대기 큐 승인/거절**(승인 시 dict_version +1)
9. **소스 정의** (admin): 사이트 등록·어댑터·셀렉터·1페이지 테스트
10. **시스템 설정** (개인): AI 제공자·모델·키(시크릿)·연결 테스트, 월 예산, 배치 시각·요일, 감시 주기, 텔레그램 봇 토큰·chat_id·테스트 발송, 비밀번호 변경
11. **실행 로그** (개인): 날짜·단계·소스·건수·오류·PC
12. **주문 관리** (개인, 2차): v2와 동일

설정값의 출처: `.env.{APP_ENV}`(dev / prd)는 Supabase 접속 정보와, 첫 로그인 때 `user_settings`를 채우는 부트스트랩 기본값이다. 이후는 화면 값(DB)이 유일한 진실이고 PC를 바꿔도 같은 값이 나온다. dev와 prd는 서로 다른 Supabase 프로젝트를 가리키므로 설정도 환경별로 따로 쌓인다.

---

## 8. 프로젝트 구조

```
auto-store/
├── app/
│   ├── auth.py                   # 로그인·세션 저장·복원 (python -m app.auth login)
│   ├── db.py                     # supabase-py 클라이언트(anon + JWT), RPC 래퍼
│   ├── config.py                 # .env 부트스트랩 + user_settings 병합 → settings
│   ├── worker.py                 # 배치 진입점: 잠금 → ⓪~⑤ (python -m app.worker run | --stage lookup)
│   ├── instant.py                # URL 즉시 분석 (등록 소스 → 어댑터 경로 / 미등록 → 범용 LLM 경로)
│   ├── pipeline/
│   │   ├── collector.py              # ① 관심 카테고리 순회, source_items upsert
│   │   ├── normalizer.py             # ② 사전·규칙 정규화, mapping_queue
│   │   ├── domestic.py               # ③ 캐시 → 크롤링 → 이미지 → 매칭 → market_signals
│   │   ├── scoring.py                # ④ 개인 원가·점수 → candidates   (현 cost.py 를 승계)
│   │   ├── notify.py                 # ⑤ N건 선정 · 로고 비전 · 텔레그램 카드  (현 card.py 를 승계)
│   │   ├── detail_collector.py · content_generator.py · package_builder.py · monitor.py   # ⑥⑦⑨⑩ (2차)
│   │   └── extract.py                # 범용 LLM 추출·정규화 (미등록 사이트 즉시 분석 전용, 현 코드 유지)
│   ├── sources/
│   │   ├── base.py · fetch.py        # 어댑터 계약 · 범용 스냅샷(현 코드)
│   │   ├── s1688.py                  # 1688 내장 어댑터 (목록·상세·차단 감지)   ← 발굴 MVP 핵심
│   │   └── aliexpress.py · generic_css.py · llm_extract.py   (2차)
│   ├── taxonomy/                 # engine.py(규칙 세트 DSL 실행) · generate.py(샘플 → LLM 1회 → 규칙 세트 초안 · 커버리지 검증) · 사전 조회(캐시) · units.py(숫자·단위) · stopwords · 검색어 조합
│   ├── vision/                   # clip.py(임베딩·코사인), phash.py
│   ├── adapters/
│   │   ├── naver_crawl.py · exchange_rate.py     (현 코드)
│   │   ├── llm/                      # base(complete_json 이 ai_results 캐시를 먼저 봄) · openai_ · claude · gemini  (현 코드 + 캐시)
│   │   ├── telegram.py · storage.py · image_gen/
│   └── admin/                    # FastAPI 라우터·템플릿
├── supabase/
│   ├── migrations/               # 001_auth_profiles.sql · 002_shared_reference.sql · 003_shared_harvest.sql · 004_personal.sql · 005_rls.sql · 006_rpc.sql · 007_rulesets_ai_cache.sql
│   └── seed/                     # canonical_categories.csv · category_aliases.csv · attribute_aliases.csv · brand_blacklist.csv · title_stopwords.csv · requirements.csv · naver_categories.csv · shipping_profile_templates.json
├── selectors/1688.yaml
├── templates/ · output/
├── .env.example (→ .env.dev · .env.prd, APP_ENV 로 선택 · 둘 다 git 제외) · requirements.txt · DESIGN.md · README.md · SETUP.md
```

`data/`는 더 이상 상태 저장소가 아니다. 남는 로컬 파일은 `data/profiles/<name>/`(브라우저 프로필)와 CLIP 모델 캐시만.

---

## 9. 외부 의존성과 사전 준비

| 항목 | 필요한 것 | 비고 |
|---|---|---|
| Supabase | **dev · prd 프로젝트 2개**(`.env.dev` / `.env.prd`가 각각 가리킴). 각각 프로젝트 URL, **anon 키**(PC용), service_role 키(마이그레이션·시드 전용), 공개 버킷 | pgvector·Vault 확장 활성화. 이메일 로그인 활성화. 스키마 실험과 시드 재적재는 dev에서 |
| 계정 | 본인 이메일로 Auth 사용자 1명 생성, profiles.role = admin | 시드 스크립트가 처리 |
| 각 도매 사이트 | 로그인 계정 | PC별 최초 1회 수동 로그인 |
| 네이버 | 키 불필요(크롤링) | 데이터랩 붙일 때 NAVER API HUB 키 |
| 텔레그램 | 봇 토큰, 본인 chat_id | 개인 시크릿 |
| AI API | 선택 제공자 키 1개 | 개인 시크릿. 발굴 단계에서는 거의 안 씀 |
| CLIP | 첫 실행 시 모델 자동 다운로드(~350MB), torch 설치(~2GB) | 인터넷 필요. 회사망 프록시면 `HF_ENDPOINT`/`HTTPS_PROXY` |
| 환율 | 수출입은행 API 키(선택) | 없으면 open.er-api.com |

---

## 10. 구현 순서

각 단계 끝에 **실제 1688 카테고리 1개**로 끝까지 돌려본다.

1. **Supabase 뼈대**: 마이그레이션(공용·개인 스키마, RLS, RPC), 시드(사전 5종·요건표·네이버 카테고리·표준 카테고리 30개 안팎·배송 프로필 템플릿), `app.auth`·`app.db`·`config` 병합, 첫 로그인으로 user_settings 생성. 검증: 두 PC에서 로그인해 같은 설정이 보이는지
2. **1688 어댑터 + 수집**: `s1688.py` 목록·상세, 로그인 프로필, 차단 감지, `collector.py` → source_items. 검증: 카테고리 1개 2페이지가 공용 테이블에 들어가는지
3. **규칙 엔진 · 규칙 생성기 · 사전**: `taxonomy/engine.py`(DSL 실행), `taxonomy/generate.py`(2단계의 1페이지 테스트 샘플 → LLM 1회 → 규칙 세트 초안 → 커버리지 검증), `rulesets` 승인 화면(최소), `normalizer.py`(규칙 → 사전 → 큐), `adapters/llm/base.py`에 `ai_results` 캐시. 검증: 카테고리 1개의 규칙 세트를 생성해 **커버리지 ≥ 80%**, 같은 샘플로 두 번째 생성 요청이 캐시 적중(LLM 0회), 40건 정규화에 LLM 0회
4. **국내 조회·매칭**: `domestic.py` — 캐시, 크롤링(기존), `vision/`, matches, market_signals. 검증: 20건을 사람이 보고 exact/similar 오판율 측정 → 임계값 1차 조정
5. **점수·카드**: `scoring.py`(cost.py 승계), `notify.py`, 텔레그램 봇·콜백, 잠금, 스케줄, 로고 비전 N건. 검증: 아침 카드 수신, [승인][거절]이 candidates에 반영
6. **관리자 웹**: 로그인, 대시보드, 관심 카테고리, 후보 목록, 설정, 사전 관리
7. **즉시 분석 전환**: `instant.py`가 등록 소스는 어댑터 경로로, 이력은 analysis_requests로. 텔레그램 URL 입구
8. **2차: 등록 콘텐츠(⑥~⑨)** → **주문·정산·감시(⑩)** → 알리익스프레스·범용 CSS 어댑터
9. **운영 후 개선**: 1-1장 목록

---

## 11. 열어둔 질문

- **CLIP 임계값 — 2026-11-01 실측으로 전제가 바뀜.** ViT-B-32(openai) 로 텀블러 썸네일 5장을 재 보니 **같은 상품의 다른 컷 0.61, 다른 브랜드(킨토 vs 써모스)의 흰 배경 카탈로그 컷 0.85.** 이 모델은 촬영 스타일을 상품 정체성보다 크게 본다. 따라서 CLIP 코사인만으로 "정확"을 판정할 수 없다. 조치: 기본값을 정확 0.95(거의 동일 사진) / 유사 0.70 으로 바꿨고, **"정확"은 pHash 동일 사진 또는 상위 N건 LLM 재판정(`llm_rejudge_top_n`, 하루 ≈ N회 — 카드 N건 안에서의 추가 호출이라 AI 최소화 원칙 안)이 맡는다.** CLIP 은 "같은 종류의 상품을 넓게 모으는" 유사·참고치 역할. 다음 시도 후보: (1) 큰 모델(ViT-L-14, ~1.7GB) 재측정 (2) 썸네일 중앙 크롭·배경 제거 후 임베딩 (3) 제목 토큰 겹침을 세 번째 신호로. 4단계 운영 데이터 20~50건을 라벨링해 다시 정한다. 재현율 우선 원칙은 그대로.
- **검색어 품질**: 사전 기반 검색어는 LLM보다 넓게 잡힌다. 카테고리 등록 시 사용자가 키워드를 2~3개 직접 적는 과정이 품질을 좌우한다. 실패 사례(쇼핑 카드 0건)를 모아 키워드 사전을 보강한다.
- **1688 목록 페이지 구조**: 무한 스크롤·XHR형이면 셀렉터 대신 요청 가로채기나 내장 JSON을 쓴다. 로그인 프로필이 헤드리스에서 유지되는지, 하루 몇 페이지까지 차단 없이 되는지 2단계에서 측정.
- **텔레그램 폴링 단일화**: 같은 계정의 PC 둘이 같은 봇을 폴링하면 충돌(409). `worker_leases`로 임대를 가진 PC만 폴링하고 30초 heartbeat, 만료 시 다른 PC가 인수. 웹훅 전환은 관리자 웹 호스팅과 함께.
- **배치 잠금과 실패 복구**: 잠금을 얻은 PC가 중간에 죽으면 그날 배치가 안 돈다. 잠금에 `heartbeat_at`을 두고 10분 넘게 갱신이 없으면 다른 PC가 인수하도록 한다.
- **공용 수집 데이터 신뢰**: 계정이 늘면 오염 가능. `created_by`·`fetched_at`과 admin 삭제로 시작하고, 필요하면 "검증된 워커만 쓰기" 플래그를 추가한다.
- **개인 시크릿 보관**: Vault RPC vs RLS 컬럼. 처음엔 컬럼으로 시작해도 되지만, 공용 프로젝트에 다른 계정이 들어오기 전에 Vault로 옮긴다.
- **데이터 양**: 4.3의 추정을 첫 달에 실측. 임베딩 보존 정책과 캐시 정리 주기를 그때 정한다.
- **1688 로그인 프로필 비이식성**: 유일하게 PC에 묶이는 상태. 각 PC에서 1회 로그인하면 되지만, 로그인 만료 감지와 "다시 로그인하세요" 알림이 필요하다.
- **규칙 세트 DSL의 표현력**: 8가지 연산으로 1688·알리의 표기를 얼마나 덮는지는 3단계에서 실측한다. 모자라면 연산을 추가하되(예: `split`, `lookup_table`), "LLM이 쓴 코드를 실행하지 않는다"는 선은 지킨다. 자동 승인 커버리지 기준(80% 출발)과 드리프트 판정 횟수(2회)도 실측으로 조정.
- **규칙 세트 생성 품질**: LLM이 샘플에 과적합한 정규식을 만들 수 있다. 홀드아웃 1페이지 검증과 admin의 실패 예시 검토가 1차 방어, 운영 중 커버리지 하락이 2차 방어다.
- v2에서 이어지는 것: 소스 간 동일 상품 임계값, 일본 B2B 회원 등급별 가격, 범용 CSS로 안 되는 사이트, 모드 C 이미지 모델, 쿠팡 가격 비교.
