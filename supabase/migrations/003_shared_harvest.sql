-- 003 · 공용 수집 데이터 (로그인 사용자 누구나 추가·갱신, admin 삭제)
-- DESIGN.md 5.2

create table if not exists public.source_items (
  id                bigserial primary key,
  source_id         text not null references public.sources(id),
  source_item_id    text not null,
  url               text not null,
  title_raw         text not null,
  lang              text,
  price_tiers_json  jsonb not null default '[]'::jsonb,   -- [{min_qty, unit_price}]
  currency          text,
  moq               integer not null default 1,
  main_image_url    text,
  category_raw      text,
  attrs_raw_json    jsonb not null default '{}'::jsonb,
  weight_raw        text,
  sold_out          boolean not null default false,
  last_price_src    numeric,
  first_seen_at     timestamptz not null default now(),
  last_seen_at      timestamptz not null default now(),
  created_by        uuid default auth.uid(),
  unique (source_id, source_item_id)
);

create table if not exists public.source_items_normalized (
  source_item_id         bigint primary key references public.source_items(id) on delete cascade,
  dict_version           integer not null,
  ruleset_version        integer,
  title_clean            text,
  key_numbers_json       jsonb not null default '{}'::jsonb,  -- {capacity_ml, length_mm, …}
  material_code          text,
  item_type              text,
  canonical_category_id  text references public.canonical_categories(id),
  search_queries         text[] not null default '{}',
  brand_text_hit         text,
  excluded_reason        text,                                -- null · food · cosmetics · medical · brand_text · …
  mapping_pending        boolean not null default false,
  normalized_at          timestamptz not null default now()
);

-- 소스 대표 이미지 · 네이버 썸네일. pHash + CLIP. 로고 비전 결과도 여기(pHash 키로 1회, 3.6)
create table if not exists public.images (
  id                bigserial primary key,
  kind              text not null check (kind in ('source', 'naver')),
  ref_id            text not null,                            -- source_item_id(text) 또는 nv_mid
  url               text not null,
  phash             bigint,
  clip              vector(512),
  logo_checked_at   timestamptz,
  logo_detected     boolean,
  logo_reason       text,
  fetched_at        timestamptz not null default now(),
  created_by        uuid default auth.uid(),
  unique (kind, ref_id)
);
create index if not exists images_phash_idx on public.images (phash);
create index if not exists images_clip_hnsw on public.images using hnsw (clip vector_cosine_ops);

-- 네이버 검색어 캐시 (TTL 7일은 코드에서 판정)
create table if not exists public.naver_queries (
  query       text primary key,
  fetched_at  timestamptz not null default now(),
  nv_mids     text[] not null default '{}',
  blocked     boolean not null default false,
  created_by  uuid default auth.uid()
);

create table if not exists public.naver_items (
  nv_mid        text primary key,
  title         text not null,
  price         integer not null,
  shipping_krw  integer,
  rating        numeric(3,2),
  review_count  integer,
  wish_count    integer,
  seller_count  integer,
  mall          text,
  link          text,
  image_url     text,
  cat_id        text,
  kind          text check (kind in ('catalog', 'store')),
  is_ad         boolean not null default false,
  fetched_at    timestamptz not null default now(),
  created_by    uuid default auth.uid()
);
create index if not exists naver_items_cat_idx on public.naver_items (cat_id);

create table if not exists public.matches (
  source_item_id        bigint not null references public.source_items(id) on delete cascade,
  nv_mid                text not null references public.naver_items(nv_mid) on delete cascade,
  relation              text not null check (relation in ('exact', 'similar')),
  method                text not null check (method in ('clip', 'rule', 'llm')),
  similarity            numeric(4,3),
  matched_numbers_json  jsonb not null default '{}'::jsonb,
  reason                text,
  computed_at           timestamptz not null default now(),
  created_by            uuid default auth.uid(),
  primary key (source_item_id, nv_mid, method)
);

create table if not exists public.market_signals (
  source_item_id      bigint primary key references public.source_items(id) on delete cascade,
  exact_count         integer not null default 0,
  similar_count       integer not null default 0,
  total_results       integer not null default 0,
  same_image_sellers  integer,
  review_avg          integer,
  review_top          integer,
  wish_top            integer,
  seller_count_max    integer,
  price_mean          integer,
  price_median        integer,
  price_min           integer,
  basis_type          text check (basis_type in ('exact', 'similar')),
  naver_cat_id        text,
  demand_trend_pct    numeric(6,2),
  computed_at         timestamptz not null default now(),
  created_by          uuid default auth.uid()
);

create table if not exists public.source_item_details (
  source_item_id    bigint primary key references public.source_items(id) on delete cascade,
  options_json      jsonb not null default '[]'::jsonb,
  images            text[] not null default '{}',
  attrs_full_json   jsonb not null default '{}'::jsonb,
  package_weight_g  integer,
  fetched_at        timestamptz not null default now(),
  created_by        uuid default auth.uid()
);

create table if not exists public.exchange_rates (
  currency    text not null,
  rate_krw    numeric(12,4) not null,
  source      text not null,                                 -- eximbank_api · naver_finance · open_er_api · last_known
  fetched_at  timestamptz not null default now(),
  created_by  uuid default auth.uid(),
  primary key (currency, fetched_at)
);
create index if not exists exchange_rates_latest_idx on public.exchange_rates (currency, fetched_at desc);
