# 테스트 환경 준비 & 실행 순서 (윈도우 / 맥)

집(맥)과 회사(윈도우)를 오가며 이어서 테스트할 때 쓰는 체크리스트다.
위에서 아래로 순서대로 실행하면 된다. 환경 파일(`.env.dev` / `.env.prd`)과 `data/` 는 git 에 올라가지 않으므로 **PC마다 따로 만든다**.

> 지금 돌아가는 기능은 **URL 즉시 분석 CLI** 하나다. 구조 설명은 [README.md](README.md) 8-1, 설계는 [DESIGN.md](DESIGN.md).

---

## 0. 새 PC에서 처음 받을 때 (공통)

```bash
git clone https://github.com/EvilStorm/auto-store.git
cd auto-store
```

이미 받아둔 PC라면 시작 전에 항상 최신으로 맞춘다.

```bash
git pull
```

---

## 1. 윈도우 (회사)

PowerShell 기준. `python` 이 없으면 Microsoft Store 스텁이 잡히니 1-1 부터 한다.

### 1-1. Python 3.12 설치 (최초 1회)

```powershell
winget install Python.Python.3.12
```

설치 후 **PowerShell 을 새로 연다.** 확인:

```powershell
python --version
```

`Python 3.12.x` 가 아니라 Store 창이 뜨거나 오류가 나면, `설정 → 앱 → 고급 앱 설정 → 앱 실행 별칭` 에서 `python.exe` / `python3.exe` 를 끈다.

### 1-2. 가상환경 + 패키지 + 브라우저 (최초 1회)

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -U pip
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m playwright install chromium
```

- `activate` 는 쓰지 않아도 된다. 모든 명령을 `.venv\Scripts\python ...` 으로 실행하면 실행 정책 문제도 피할 수 있다.
- `playwright` 명령을 못 찾는다고 나오면 전역이 아니라 venv 안에만 있어서 그렇다. 위처럼 `python -m playwright` 로 실행한다.
- `install-deps` / `--with-deps` 는 리눅스용이라 윈도우에서 실패한다. `install chromium` 만 하면 된다.
- Chromium 은 `%LOCALAPPDATA%\ms-playwright\` 에 설치된다.

### 1-3. 환경 파일 (최초 1회)

개발·운영을 `.env.dev` / `.env.prd` 두 파일로 나눈다. 실행할 환경은 `APP_ENV` 로 고르고, 비우면 `dev` 다.

```powershell
copy .env.example .env.dev
notepad .env.dev
```

운영 Supabase 프로젝트가 준비되면 같은 방법으로 `.env.prd` 를 만든다. 채울 값은 [3. .env.dev / .env.prd 에 채울 것](#3-envdev--envprd-에-채울-것) 참고.

### 1-4. 동작 확인

```powershell
# 환경 확인 (APP_ENV=dev · 읽은 파일 .env.dev 가 나오면 됨. 키는 채워짐/비어 있음만 표시)
.venv\Scripts\python -m app.config

# 브라우저 실행 확인 (chromium ok 가 나오면 됨)
.venv\Scripts\python -c "from playwright.sync_api import sync_playwright as s; p=s().start(); b=p.chromium.launch(); print('chromium ok', b.version); b.close(); p.stop()"

# 환율 수집 확인 (open.er-api.com 경로로 CNY/JPY 환율이 찍히면 됨)
.venv\Scripts\python -m app.adapters.exchange_rate

# 네이버 통합검색 크롤러 확인 (상품 카드 10건 안팎이 찍히면 됨)
.venv\Scripts\python -m app.adapters.naver_crawl

# 페이지 수집만 확인 (LLM 키 없이 됨)
.venv\Scripts\python -m app.instant --fetch-only https://ko.aliexpress.com/item/1005013478517865.html
```

### 1-5. 전체 분석 실행 (OPENAI_API_KEY 필요)

```powershell
.venv\Scripts\python -m app.instant https://ko.aliexpress.com/item/1005013478517865.html
.venv\Scripts\python -m app.instant --recent 10
.venv\Scripts\python -m app.instant --show 20261030-091200

# 운영 환경(.env.prd)으로 실행할 때 — 그 PowerShell 창에서만 유효
$env:APP_ENV="prd"; .venv\Scripts\python -m app.instant <URL>
```

### 1-6. 1688 처럼 로그인이 필요한 소스

창을 띄워 직접 로그인하면 프로필이 `data\profiles\1688` 에 저장되고 다음부터는 헤드리스로 재사용한다.

```powershell
.venv\Scripts\python -m app.instant --headed --profile 1688 https://detail.1688.com/offer/XXXXXXXX.html
```

### 윈도우에서 자주 나는 오류

| 증상 | 원인 | 해결 |
|---|---|---|
| 3.12 를 설치했는데 `python --version` 이 여전히 3.10 | **시스템 PATH** 에 남은 `...\Python310` 항목. Windows 는 시스템 PATH 를 사용자 PATH 보다 먼저 보므로 사용자 PATH 맨 앞의 3.12 가 밀린다 | `시스템 변수 → Path` 에서 Python310 항목 삭제(관리자 권한) 후 새 창. 또는 PATH 를 안 고치고 `py -3.12 -m venv .venv` 로 venv 만 만들면 이후는 `.venv\Scripts\python` 이라 상관없다 |
| `이 시스템에서 스크립트를 실행할 수 없으므로` | `Activate.ps1` 실행 정책 | activate 없이 `.venv\Scripts\python` 직접 사용, 또는 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `APP_ENV 는 dev \| prd 중 하나여야 합니다` | 오타 (`prod`, `production` 등) | `$env:APP_ENV="prd"` 또는 `Remove-Item Env:APP_ENV` (dev 로 복귀) |
| 한글이 `?` 나 깨진 글자로 출력 | 콘솔 cp949 | CLI 가 utf-8 로 바꿔 출력하지만, 그래도 깨지면 `$env:PYTHONIOENCODING="utf-8"` 후 실행 |
| `Download failed` / `ECONNRESET` (playwright install) | 회사망 프록시·방화벽 | `$env:HTTPS_PROXY="http://프록시:포트"` 지정 후 재시도 |
| 다른 python 에 설치됨 | 전역 `python -m playwright` 실행 | 항상 `.venv\Scripts\python` 을 앞에 붙인다 |

---

## 2. 맥 (집)

터미널(zsh) 기준.

### 2-1. Python 3.12 설치 (최초 1회)

Homebrew 가 없으면 먼저 https://brew.sh 안내대로 설치한다.

```bash
brew install python@3.12
python3.12 --version
```

### 2-2. 가상환경 + 패키지 + 브라우저 (최초 1회)

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
```

- Chromium 은 `~/Library/Caches/ms-playwright/` 에 설치된다.
- Apple Silicon 에서도 별도 설정 없이 된다. 처음 헤드풀(`--headed`) 실행 시 "개발자를 확인할 수 없음" 경고가 뜨면 `시스템 설정 → 개인정보 보호 및 보안` 에서 허용한다.
- 원하면 `source .venv/bin/activate` 로 활성화해도 되지만, 아래 명령은 활성화 없이 쓰는 형태로 적었다.

### 2-3. 환경 파일 (최초 1회)

```bash
cp .env.example .env.dev
open -e .env.dev        # 또는 nano .env.dev
```

운영용은 같은 방법으로 `.env.prd`. 채울 값은 [3. .env.dev / .env.prd 에 채울 것](#3-envdev--envprd-에-채울-것) 참고.

### 2-4. 동작 확인

```bash
# 환경 확인 (APP_ENV=dev · 읽은 파일 .env.dev)
.venv/bin/python -m app.config

# 브라우저 실행 확인
.venv/bin/python -c "from playwright.sync_api import sync_playwright as s; p=s().start(); b=p.chromium.launch(); print('chromium ok', b.version); b.close(); p.stop()"

# 환율 수집 확인
.venv/bin/python -m app.adapters.exchange_rate

# 네이버 통합검색 크롤러 확인
.venv/bin/python -m app.adapters.naver_crawl

# 페이지 수집만 확인 (LLM 키 없이 됨)
.venv/bin/python -m app.instant --fetch-only https://ko.aliexpress.com/item/1005013478517865.html
```

### 2-5. 전체 분석 실행 (OPENAI_API_KEY 필요)

```bash
.venv/bin/python -m app.instant https://ko.aliexpress.com/item/1005013478517865.html
.venv/bin/python -m app.instant --recent 10
.venv/bin/python -m app.instant --show 20261030-091200

# 운영 환경(.env.prd)으로 실행할 때
APP_ENV=prd .venv/bin/python -m app.instant <URL>
```

### 2-6. 1688 처럼 로그인이 필요한 소스

```bash
.venv/bin/python -m app.instant --headed --profile 1688 https://detail.1688.com/offer/XXXXXXXX.html
```

### 맥에서 자주 나는 오류

| 증상 | 원인 | 해결 |
|---|---|---|
| `command not found: python` | 맥 기본엔 `python` 별칭이 없음 | `python3.12` 또는 `.venv/bin/python` 사용 |
| `externally-managed-environment` (pip) | 시스템 python 에 직접 설치 시도 | 반드시 venv 안의 `.venv/bin/python -m pip` 로 설치 |
| `xcrun: error: invalid active developer path` | 커맨드라인 도구 없음 | `xcode-select --install` |
| 헤드풀 창이 안 뜨고 멈춤 | 보안 경고 대기 | 시스템 설정 → 개인정보 보호 및 보안에서 허용 후 재실행 |

---

## 3. .env.dev / .env.prd 에 채울 것

`.env.example` 을 `.env.dev` 로 복사한 뒤 아래만 채우면 지금 기능은 다 돈다. 나머지는 기본값 그대로 둬도 된다.

**dev 와 prd 의 차이**: 두 파일은 키 목록이 같고 값만 다르다. 핵심은 **Supabase 프로젝트가 다르다**는 것(스키마 실험·시드 재적재가 운영 데이터를 건드리지 않게). 그 밖에 dev 는 `LLM_MODEL=gpt-5-mini`, `MONTHLY_BUDGET_KRW=10000`, `DAILY_CANDIDATE_LIMIT=3`, `INSTANT_ANALYSIS_DAILY_LIMIT=10`, 테스트용 텔레그램 봇을 권장한다. `.env.example` 안의 "dev 권장 / prd 권장" 주석이 그 항목들이다. 환경 파일이 있으면 그것만 읽고 다른 환경 파일을 섞지 않으므로, `.env.prd` 에 비워둔 키는 비어 있는 채로 동작한다(dev 키가 운영으로 새지 않는다).

| 키 | 필요 여부 | 설명 |
|---|---|---|
| `APP_ENV` | 선택 (OS 환경변수) | `dev` \| `prd`. 파일 안이 아니라 **실행하는 셸에서** 지정한다. 비우면 `dev` |
| `OPENAI_API_KEY` | **필수** | LLM 추출·정규화·매칭 판정. 없으면 `--fetch-only` 만 된다 |
| `LLM_PROVIDER` / `LLM_MODEL` | 선택 | 기본 `openai` / `gpt-5`. Claude 로 바꾸려면 `claude` + `ANTHROPIC_API_KEY` |
| `EXIMBANK_API_KEY` | 선택 | 없으면 open.er-api.com 으로 자동 대체 |
| `NAVER_CLIENT_ID/SECRET` | 불필요 | 쇼핑 검색 API 가 종료되어 크롤링을 쓴다. 비워둔다 |
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` | v3 구현 1단계부터 | 환경별로 다른 프로젝트. `SUPABASE_SERVICE_KEY` 는 마이그레이션·시드 때만 |
| `TELEGRAM_*` | 아직 불필요 | 다음 단계에서 사용. dev 와 prd 는 다른 봇 |

- API 키는 `.env.dev` / `.env.prd` 에만 넣는다. 채팅·커밋·스크린샷에 올리지 않는다. `.gitignore` 가 `.env*` 를 통째로 막고 `.env.example` 만 예외다 — `.env copy` 같은 복사본도 안전하다.
- 두 PC 의 환경 파일은 각자 관리한다. 키를 옮길 때는 비밀번호 관리자나 암호화 메모로 옮긴다.
- 예전 방식의 `.env` 하나만 있는 PC 에서도 돌아간다(`.env.{APP_ENV}` 가 없을 때의 폴백). 새로 세팅할 때는 `.env.dev` 로 시작한다.

---

## 4. 테스트할 때 보는 순서

1. `git pull` 로 최신 코드 받기
2. `--fetch-only` 로 페이지가 읽히는지 (제목·텍스트 길이·이미지 수·`blocked_hint`)
3. 전체 분석 돌려 카드 확인
   - `[원시 추출]` 의 통화·가격·MOQ 가 페이지와 맞는지 (알리 한국어 페이지는 ₩ = KRW)
   - `[정규화]` 의 한국어 제목·검색어·재질·요건 판정이 말이 되는지
   - `[경쟁]` 에 "쇼핑 결과 없음" 이 뜨면 네이버 페이지 구조가 바뀐 것 → 알려주기
   - 마진율·제안 판매가가 상식적인지
4. `--recent` 로 이력이 쌓였는지
5. 이상하면 `data/analyses/<id>.json` 을 열어 `raw`, `normalized`, `match`, `llm_usage` 를 확인

### 테스트용 URL

| 소스 | URL | 비고 |
|---|---|---|
| AliExpress (한국어) | `https://ko.aliexpress.com/item/1005013478517865.html` | 로그인 없이 읽힘, 가격이 ₩ 로 표시 |
| 1688 | 상세 페이지 URL 아무거나 | 헤드리스는 로그인으로 튕김 → `--headed --profile 1688` 로 1회 로그인 필요 |

---

## 5. Supabase 1단계 적용 (v3 · 프로젝트당 최초 1회)

v3 구현 1단계(DESIGN.md 10장). 스키마·RLS·시드·첫 계정을 만든다. **dev 프로젝트에서 먼저** 하고, 운영 프로젝트는 `.env.prd` + `$env:APP_ENV="prd"` 로 같은 순서를 반복한다. 윈도우는 `.venv\Scripts\python`, 맥은 `.venv/bin/python` 으로 읽으면 된다.

### 5-1. 대시보드에서 (브라우저)
1. **Database → Extensions** 에서 `vector` 켜기 (001 이 `create extension` 하지만 권한에 따라 대시보드가 필요할 수 있음)
2. **Authentication → Providers → Email** 켜기. 테스트 중엔 "Confirm email" 을 끄거나, 아래 부트스트랩 스크립트가 `email_confirm=True` 로 만드니 그대로 둬도 됨
3. **Project Settings → Database → Connection string → URI** 복사 → `.env.dev` 의 `SUPABASE_DB_URL`. (비밀번호가 들어가므로 적용 후 지워도 됨)
4. **Project Settings → API** 의 `anon` 키 → `SUPABASE_ANON_KEY`, `service_role` 키 → `SUPABASE_SERVICE_KEY` (service_role 은 5-2·5-3 에서만 쓴다)

### 5-2. 마이그레이션 · 시드
```powershell
.venv\Scripts\python scripts\migrate.py --status     # 미적용 목록
.venv\Scripts\python scripts\migrate.py              # 001 ~ 007 적용 (schema_migrations 에 기록, 재실행 안전)
.venv\Scripts\python scripts\seed.py                 # 사전 · 표준 카테고리 · 요건표 · 소스 정의 upsert, dict_version +1
```
`SUPABASE_DB_URL` 을 넣고 싶지 않으면 `migrate.py --print` 로 출력한 SQL 을 대시보드 **SQL Editor** 에 붙여 넣어 실행해도 된다(그 경우 `schema_migrations` 기록은 안 남는다).

### 5-3. 첫 계정 (admin)
```powershell
.venv\Scripts\python scripts\bootstrap_admin.py --email you@example.com
```
비밀번호는 프롬프트로 두 번 입력. 001 트리거가 **첫 계정을 admin** 으로 만들고, 개인 배송 프로필 2개(중국·일본 템플릿)가 생긴다.

### 5-4. 로그인 · 확인
```powershell
.venv\Scripts\python -m app.auth login --email you@example.com
.venv\Scripts\python -m app.auth status
```
`status` 에 `role admin`, `user_settings: 방금 .env 기본값으로 생성`, `표준 카테고리 45개` 가 나오면 1단계 완료. 세션은 `~\.auto-store\session.dev.json` 에 남고, **다른 PC 에서도 같은 계정으로 login 하면 같은 설정이 보인다**(이것이 1단계의 검증 기준).

### 5-5. 끝나면
- `.env.dev` 에서 `SUPABASE_DB_URL` 과 `SUPABASE_SERVICE_KEY` 를 지워도 된다. 일상 실행(워커 · CLI · 관리자 웹)은 anon 키 + 로그인 세션만 쓴다.
- 시드를 고쳤으면 `scripts/seed.py` 를 다시 돌린다(upsert · dict_version +1). 마이그레이션을 추가하면 `008_*.sql` 로 번호를 이어 `migrate.py`.

| 증상 | 원인 | 해결 |
|---|---|---|
| `permission denied to create extension "vector"` | 확장 권한 | 5-1 ① 대시보드에서 켠 뒤 재실행 |
| `relation "auth.users" does not exist` | DB URL 이 Supabase 가 아님 | URI 를 다시 복사 (포트 5432 Direct 또는 6543 Pooler) |
| `로그인 실패` / `Invalid login credentials` | 이메일 미확인 또는 비번 | 5-1 ② 또는 bootstrap 재실행(기존 계정은 건너뜀) |
| `status` 에 `role (없음 …)` | 001 트리거 전에 만든 계정 | SQL Editor 에서 `insert into profiles(user_id, role) values ('<uid>','admin')` |

## 6. 작업 끝낼 때

```bash
git status
git add -A
git commit -m "작업 내용"
git push
```

`data/`, `.env*`(`.env.example` 제외), `.venv/` 는 `.gitignore` 에 있어서 올라가지 않는다. `git add -A` 전에 `git status` 로 한 번 확인하는 습관을 둔다. 분석 이력(`data/analyses/`)은 아직 PC마다 따로 쌓인다(v3 7단계에서 Supabase 로 이전).
