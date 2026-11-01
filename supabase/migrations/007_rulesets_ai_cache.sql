-- 007 · 규칙 세트(3.5) · AI 결과 캐시(3.6) · 추출 캐시 · 한국어 초안 캐시
-- rulesets 는 공용 참조(B: admin 쓰기)이되 생성 초안(draft) 은 누구나 넣을 수 있다. 나머지는 공용 수집(C).

create table if not exists public.rulesets (
  id                     bigserial primary key,
  source_id              text not null references public.sources(id) on delete cascade,
  canonical_category_id  text references public.canonical_categories(id) on delete cascade,  -- null = 소스 기본 세트
  kind                   text not null check (kind in ('extract', 'normalize', 'query', 'match_hints')),
  version                integer not null default 1,
  rules_json             jsonb not null,                       -- DSL: [{op, ...}]
  rationale_json         jsonb not null default '[]'::jsonb,   -- 규칙별 근거 한 줄
  sample_item_ids        bigint[] not null default '{}',
  coverage_json          jsonb not null default '{}'::jsonb,   -- {field: pct, ..., _overall: pct, _at: ts}
  status                 text not null default 'draft' check (status in ('draft', 'active', 'retired', 'needs_regen')),
  generated_by           text not null default 'llm' check (generated_by in ('llm', 'manual')),
  approved_by            uuid,
  created_by             uuid default auth.uid(),
  created_at             timestamptz not null default now()
);
-- (소스, 카테고리, 종류) 당 active 는 하나
create unique index if not exists rulesets_one_active
  on public.rulesets (source_id, coalesce(canonical_category_id, ''), kind) where status = 'active';

-- 모든 LLM 호출의 캐시. 같은 (용도@버전, 모델, 입력 해시) 면 호출하지 않는다.
create table if not exists public.ai_results (
  purpose       text not null,                                 -- 'logo_check@v1' 처럼 프롬프트 버전 포함
  model         text not null,
  input_hash    text not null,                                 -- sha256
  output_json   jsonb not null,
  est_cost_krw  numeric(10,2) not null default 0,
  hits          integer not null default 0,
  created_by    uuid default auth.uid(),
  created_at    timestamptz not null default now(),
  primary key (purpose, model, input_hash)
);

-- 미등록 사이트 즉시 분석의 추출 캐시 (URL + 페이지 텍스트 해시)
create table if not exists public.page_extracts (
  url           text not null,
  text_hash     text not null,
  raw_json      jsonb not null,                                -- RawDetail
  extracted_at  timestamptz not null default now(),
  created_by    uuid default auth.uid(),
  primary key (url, text_hash)
);

-- ⑦ 상품명·옵션 한국어 초안 (설명문은 개인)
create table if not exists public.source_item_ko_drafts (
  source_item_id    bigint primary key references public.source_items(id) on delete cascade,
  title_ko_options  text[] not null default '{}',
  options_ko_json   jsonb not null default '{}'::jsonb,
  generated_at      timestamptz not null default now(),
  created_by        uuid default auth.uid()
);

-- 캐시 적중 카운트 (RLS 아래에서 update 는 허용되지만 함수로 한 번에)
create or replace function public.ai_cache_hit(p_purpose text, p_model text, p_input_hash text) returns jsonb
language plpgsql as $$
declare out jsonb;
begin
  update public.ai_results set hits = hits + 1
    where purpose = p_purpose and model = p_model and input_hash = p_input_hash
    returning output_json into out;
  return out;   -- null 이면 미스
end $$;
grant execute on function public.ai_cache_hit(text, text, text) to authenticated;

-- RLS
do $$
declare t text;
begin
  foreach t in array array['ai_results', 'page_extracts', 'source_item_ko_drafts'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists read_all on public.%I', t);
    execute format('drop policy if exists worker_insert on public.%I', t);
    execute format('drop policy if exists worker_update on public.%I', t);
    execute format('drop policy if exists admin_delete on public.%I', t);
    execute format('create policy read_all on public.%I for select to authenticated using (true)', t);
    execute format('create policy worker_insert on public.%I for insert to authenticated with check (true)', t);
    execute format('create policy worker_update on public.%I for update to authenticated using (true) with check (true)', t);
    execute format('create policy admin_delete on public.%I for delete to authenticated using (public.is_admin())', t);
  end loop;
end $$;

alter table public.rulesets enable row level security;
drop policy if exists read_all on public.rulesets;
drop policy if exists draft_insert on public.rulesets;
drop policy if exists admin_rw on public.rulesets;
create policy read_all on public.rulesets for select to authenticated using (true);
create policy draft_insert on public.rulesets for insert to authenticated with check (status = 'draft');
create policy admin_rw on public.rulesets for all to authenticated using (public.is_admin()) with check (public.is_admin());
