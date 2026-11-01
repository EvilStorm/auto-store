-- 004 · 개인 데이터 (RLS: user_id = auth.uid()). 1차 발굴 범위. 2차(콘텐츠·패키지·등록·주문)는 그때 추가.
-- DESIGN.md 5.3

create table if not exists public.user_settings (
  user_id                 uuid primary key references auth.users(id) on delete cascade,
  -- 비용
  proxy_fee_rate          numeric(5,4) not null default 0.05,
  local_shipping_cny      numeric(10,2) not null default 8,
  customs_duty_rate       numeric(5,4) not null default 0.08,
  vat_rate                numeric(5,4) not null default 0.10,
  customs_limit_usd       numeric(10,2) not null default 150,
  customs_warn_usd        numeric(10,2) not null default 130,
  naver_fee_rate          numeric(5,4) not null default 0.055,
  payment_fee_rate        numeric(5,4) not null default 0.02,
  fx_buffer_rate          numeric(5,4) not null default 0.02,
  target_margin_rate      numeric(5,4) not null default 0.30,
  margin_threshold        numeric(5,4) not null default 0.30,
  forwarder_rates         text not null default '0.5:6000,1:7500,1.5:9000,2:10500,3:13500,5:19500,10:34500',
  -- 매칭
  price_basis             text not null default 'mean' check (price_basis in ('mean', 'median', 'min')),
  match_preset            text not null default 'normal' check (match_preset in ('strict', 'normal', 'wide')),
  exact_threshold         numeric(4,3) not null default 0.900,
  similar_threshold       numeric(4,3) not null default 0.800,
  same_image_seller_cap   integer not null default 5,
  llm_rejudge_top_n       integer not null default 0,
  naver_top_n             integer not null default 10,
  -- 건수 세 가지
  daily_candidate_n       integer not null default 10,
  daily_lookup_cap        integer not null default 300,
  daily_llm_cap           integer not null default 50,
  instant_daily_limit     integer not null default 50,
  -- 스케줄
  collect_at              text not null default '02:00',
  notify_at               text not null default '08:00',
  days                    text not null default 'mon,tue,wed,thu,fri,sat,sun',
  monitor_interval_days   integer not null default 3,
  monitor_price_threshold numeric(5,4) not null default 0.05,
  -- 예산
  monthly_budget_krw      integer not null default 50000,
  budget_warn_ratio       numeric(4,3) not null default 0.800,
  budget_exceeded_action  text not null default 'stop_content' check (budget_exceeded_action in ('stop_content', 'warn_only')),
  -- AI · 콘텐츠
  llm_provider            text not null default 'openai',
  llm_model               text not null default '',
  image_provider          text not null default 'none',
  image_mode              text not null default 'A',
  notice_template         text,
  updated_at              timestamptz not null default now()
);
drop trigger if exists user_settings_updated_at on public.user_settings;
create trigger user_settings_updated_at before update on public.user_settings
  for each row execute function public.set_updated_at();

-- 개인 시크릿. 처음엔 RLS 보호 컬럼으로 시작, Vault RPC 로 승격 (DESIGN 5.0)
create table if not exists public.user_secrets (
  user_id     uuid not null references auth.users(id) on delete cascade,
  name        text not null,                     -- openai_api_key · anthropic_api_key · google_ai_api_key · telegram_bot_token · eximbank_api_key
  value       text not null,
  updated_at  timestamptz not null default now(),
  primary key (user_id, name)
);

create table if not exists public.shipping_profiles (
  id                      bigserial primary key,
  user_id                 uuid not null references auth.users(id) on delete cascade,
  name                    text not null,
  country                 text not null,
  currency                text not null,
  rate_table_json         jsonb not null default '[]'::jsonb,   -- [{kg_max, won}]
  local_shipping_default  numeric(10,2) not null default 0,
  proxy_fee_rate          numeric(5,4) not null default 0.05,
  lead_days               integer not null default 12,
  created_at              timestamptz not null default now()
);

create table if not exists public.user_sources (
  user_id               uuid not null references auth.users(id) on delete cascade,
  source_id             text not null references public.sources(id) on delete cascade,
  enabled               boolean not null default true,
  browser_profile_name  text,
  delay_min_s           numeric(5,2) not null default 2,
  delay_max_s           numeric(5,2) not null default 6,
  daily_cap             integer not null default 300,
  block_tolerance       integer not null default 3,
  shipping_profile_id   bigint references public.shipping_profiles(id),
  last_ok_at            timestamptz,
  consecutive_failures  integer not null default 0,
  primary key (user_id, source_id)
);

create table if not exists public.user_watch_categories (
  id                   bigserial primary key,
  user_id              uuid not null references auth.users(id) on delete cascade,
  source_category_id   bigint not null references public.source_categories(id) on delete cascade,
  max_pages            integer not null default 2,
  enabled              boolean not null default true,
  extra_keywords_ko    text[] not null default '{}',
  added_at             timestamptz not null default now(),
  unique (user_id, source_category_id)
);

create table if not exists public.user_exclusion_rules (
  id            bigserial primary key,
  user_id       uuid not null references auth.users(id) on delete cascade,
  kind          text not null check (kind in ('material', 'item_type', 'keyword')),
  code_or_term  text not null,
  enabled       boolean not null default true,
  unique (user_id, kind, code_or_term)
);

create table if not exists public.candidates (
  id                    bigserial primary key,
  user_id               uuid not null references auth.users(id) on delete cascade,
  source_item_id        bigint not null references public.source_items(id) on delete cascade,
  run_date              date not null,
  origin                text not null default 'batch' check (origin in ('batch', 'instant')),
  cost_breakdown_json   jsonb not null default '{}'::jsonb,
  domestic_price_krw    integer,
  margin_rate           numeric(6,4),
  suggested_price_krw   integer,
  score                 numeric(7,2),
  score_parts_json      jsonb not null default '{}'::jsonb,
  flags                 text[] not null default '{}',
  status                text not null default 'candidate' check (status in (
                          'below_margin', 'candidate', 'held', 'rejected_1', 'approved_1',
                          'detail_collected', 'content_generated', 'rejected_2', 'revise',
                          'approved_2', 'packaged', 'listed', 'suspended')),
  brand_vision_checked  boolean not null default false,
  card_sent_at          timestamptz,
  decision              text,
  decided_at            timestamptz,
  created_at            timestamptz not null default now(),
  unique (user_id, source_item_id, run_date)
);
create index if not exists candidates_user_status_idx on public.candidates (user_id, status, run_date desc);

create table if not exists public.rejections (
  id              bigserial primary key,
  user_id         uuid not null references auth.users(id) on delete cascade,
  source_id       text references public.sources(id),
  source_item_id  text,
  image_phash     bigint,
  reason          text not null check (reason in ('margin', 'quality', 'brand', 'duplicate', 'other')),
  rejected_at     timestamptz not null default now(),
  until           timestamptz not null default now() + interval '90 days'
);
create index if not exists rejections_user_item_idx on public.rejections (user_id, source_id, source_item_id);
create index if not exists rejections_user_phash_idx on public.rejections (user_id, image_phash);

create table if not exists public.analysis_requests (
  id              bigserial primary key,
  user_id         uuid not null references auth.users(id) on delete cascade,
  requested_at    timestamptz not null default now(),
  channel         text not null check (channel in ('telegram', 'web', 'cli')),
  url             text not null,
  source_id       text references public.sources(id),
  source_item_id  bigint references public.source_items(id),
  candidate_id    bigint references public.candidates(id),
  status          text not null default 'queued' check (status in ('queued', 'running', 'done', 'failed', 'unsupported_source', 'fetched')),
  summary_json    jsonb not null default '{}'::jsonb,
  decision        text not null default 'none',
  error           text
);

create table if not exists public.api_usage (
  id             bigserial primary key,
  user_id        uuid not null references auth.users(id) on delete cascade,
  provider       text not null,
  model          text not null,
  purpose        text not null,
  candidate_id   bigint,
  input_tokens   integer not null default 0,
  output_tokens  integer not null default 0,
  images         integer not null default 0,
  est_cost_krw   numeric(10,2) not null default 0,
  cache_hit      boolean not null default false,
  called_at      timestamptz not null default now()
);
create index if not exists api_usage_user_month_idx on public.api_usage (user_id, called_at desc);

create table if not exists public.run_logs (
  id           bigserial primary key,
  user_id      uuid not null references auth.users(id) on delete cascade,
  run_date     date not null,
  kind         text not null,                     -- collect · normalize · lookup · score · notify · monitor · instant
  source_id    text,
  stage        text,
  counts_json  jsonb not null default '{}'::jsonb,
  error        text,
  pc_name      text,
  started_at   timestamptz not null default now(),
  finished_at  timestamptz
);

-- 같은 계정 PC 둘: 먼저 insert 한 PC 가 그날 배치를 가진다 (unique 가 잠금)
create table if not exists public.batch_locks (
  user_id       uuid not null references auth.users(id) on delete cascade,
  run_date      date not null,
  kind          text not null,
  pc_name       text not null,
  acquired_at   timestamptz not null default now(),
  heartbeat_at  timestamptz not null default now(),
  primary key (user_id, run_date, kind)
);

-- 텔레그램 폴링 등 "한 PC 만" 해야 하는 일의 임대
create table if not exists public.worker_leases (
  user_id     uuid not null references auth.users(id) on delete cascade,
  kind        text not null,
  pc_name     text not null,
  expires_at  timestamptz not null,
  primary key (user_id, kind)
);
