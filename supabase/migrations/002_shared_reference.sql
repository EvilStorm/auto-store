-- 002 · 공용 참조 데이터 (admin 만 쓰기, 시드로 시작)
-- DESIGN.md 5.1. 공용 테이블은 user_id 가 없고 created_by 만 둔다.

create table if not exists public.sources (
  id                  text primary key,                 -- '1688' · 'aliexpress' · 'taobao' · 'netsea' …
  name                text not null,
  country             text not null,                    -- CN · JP
  currency            text not null,                    -- CNY · JPY · USD · KRW
  base_url            text not null,
  adapter_key         text not null,                    -- 1688 · taobao · aliexpress · netsea · superdelivery · generic_css · llm_extract
  adapter_config_json jsonb not null default '{}'::jsonb,
  auth_mode           text not null default 'none' check (auth_mode in ('none', 'browser_profile')),
  created_by          uuid default auth.uid(),
  created_at          timestamptz not null default now()
);

create table if not exists public.canonical_categories (
  id                  text primary key,                 -- 'kitchen.tumbler' 같은 슬러그
  parent_id           text references public.canonical_categories(id),
  path                text not null,                    -- '주방 > 텀블러·보온병'
  naver_cat_id        text,
  item_type           text not null default 'general'
                      check (item_type in ('general', 'electronics', 'kids', 'food', 'cosmetics', 'medical', 'other')),
  default_weight_g    integer not null default 0,
  search_keywords_ko  text[] not null default '{}',     -- 검색어 조합의 재료 (3.3)
  created_at          timestamptz not null default now()
);

create table if not exists public.source_categories (
  id                     bigserial primary key,
  source_id              text not null references public.sources(id) on delete cascade,
  label_raw              text not null,                 -- 사이트 표기 (保温杯 · お菓子)
  url                    text not null,                 -- 목록 · 검색 URL
  canonical_category_id  text references public.canonical_categories(id),
  created_by             uuid default auth.uid(),
  created_at             timestamptz not null default now(),
  unique (source_id, url)
);

create table if not exists public.category_aliases (
  term                   text not null,
  lang                   text not null check (lang in ('ko', 'zh', 'ja', 'en')),
  canonical_category_id  text not null references public.canonical_categories(id) on delete cascade,
  origin                 text not null default 'seed' check (origin in ('seed', 'manual', 'llm')),
  confidence             numeric(3,2) not null default 1.00,
  primary key (term, lang)
);

create table if not exists public.attribute_aliases (
  kind        text not null,                             -- material · color · item_type …
  term        text not null,
  lang        text not null check (lang in ('ko', 'zh', 'ja', 'en')),
  code        text not null,                             -- stainless · glass · black …
  origin      text not null default 'seed' check (origin in ('seed', 'manual', 'llm')),
  primary key (kind, term, lang)
);

create table if not exists public.brand_blacklist (
  name        text not null,
  lang        text not null check (lang in ('ko', 'zh', 'ja', 'en')),
  kind        text not null default 'brand' check (kind in ('brand', 'character')),
  note        text,
  primary key (name, lang)
);

create table if not exists public.title_stopwords (
  term        text not null,
  lang        text not null check (lang in ('ko', 'zh', 'ja', 'en')),
  primary key (term, lang)
);

create table if not exists public.requirements (
  item_type   text primary key,
  status      text not null check (status in ('pass', 'required', 'excluded')),
  reason      text not null,
  docs        text
);

create table if not exists public.naver_categories (
  cat_id      text primary key,
  path        text not null,
  fetched_at  timestamptz not null default now()
);

-- 사전에 없는 표기의 확인 큐. unique(kind, term, lang) 으로 같은 표기는 한 번만 제안된다 (3.6).
create table if not exists public.mapping_queue (
  id                    bigserial primary key,
  kind                  text not null check (kind in ('category', 'material', 'item_type', 'color')),
  term                  text not null,
  lang                  text not null,
  source_id             text references public.sources(id),
  sample_item_id        bigint,
  suggested_id_or_code  text,
  confidence            numeric(3,2),
  status                text not null default 'pending' check (status in ('pending', 'approved', 'rejected')),
  created_by            uuid default auth.uid(),
  created_at            timestamptz not null default now(),
  decided_at            timestamptz,
  unique (kind, term, lang)
);

-- 사전 버전. 사전이 바뀌면 +1 → 정규화 결과가 낮은 버전이면 다음 배치에서 (LLM 없이) 재정규화
create table if not exists public.dict_meta (
  id            boolean primary key default true check (id),   -- 1행 고정
  dict_version  integer not null default 1,
  updated_at    timestamptz not null default now()
);
insert into public.dict_meta (id, dict_version) values (true, 1) on conflict (id) do nothing;

create or replace function public.bump_dict_version() returns integer
language sql security definer set search_path = public as $$
  update public.dict_meta set dict_version = dict_version + 1, updated_at = now() where id returning dict_version;
$$;
revoke all on function public.bump_dict_version() from public;
grant execute on function public.bump_dict_version() to authenticated;
