-- 005 · RLS 정책 3종 (DESIGN.md 5.0)
--   (A) 개인 테이블: user_id = auth.uid() 행만 읽고 쓴다
--   (B) 공용 참조: 전원 읽기 · admin 만 쓰기
--   (C) 공용 수집: 전원 읽기 · 전원 추가 · 전원 갱신 · admin 만 삭제
-- 여러 번 실행해도 안전 (drop policy if exists 후 재생성)

do $$
declare
  t text;
  personal text[] := array[
    'user_settings', 'user_secrets', 'shipping_profiles', 'user_sources', 'user_watch_categories',
    'user_exclusion_rules', 'candidates', 'rejections', 'analysis_requests', 'api_usage', 'run_logs',
    'batch_locks', 'worker_leases'
  ];
  reference text[] := array[
    'sources', 'source_categories', 'canonical_categories', 'category_aliases', 'attribute_aliases',
    'brand_blacklist', 'title_stopwords', 'requirements', 'naver_categories', 'dict_meta'
  ];
  harvest text[] := array[
    'source_items', 'source_items_normalized', 'images', 'naver_queries', 'naver_items', 'matches',
    'market_signals', 'source_item_details', 'exchange_rates', 'mapping_queue'
  ];
begin
  -- (A) 개인
  foreach t in array personal loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists own_rows on public.%I', t);
    execute format(
      'create policy own_rows on public.%I for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid())', t);
  end loop;

  -- (B) 공용 참조
  foreach t in array reference loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists read_all on public.%I', t);
    execute format('drop policy if exists admin_rw on public.%I', t);
    execute format('create policy read_all on public.%I for select to authenticated using (true)', t);
    execute format(
      'create policy admin_rw on public.%I for all to authenticated using (public.is_admin()) with check (public.is_admin())', t);
  end loop;

  -- (C) 공용 수집
  foreach t in array harvest loop
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

-- profiles: 내 행은 읽고 고치되 role 은 못 바꾼다(아래 트리거), admin 은 전원 조회
alter table public.profiles enable row level security;
drop policy if exists own_profile_select on public.profiles;
drop policy if exists own_profile_update on public.profiles;
drop policy if exists admin_profiles_select on public.profiles;
create policy own_profile_select on public.profiles for select to authenticated using (user_id = auth.uid());
create policy own_profile_update on public.profiles for update to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy admin_profiles_select on public.profiles for select to authenticated using (public.is_admin());

create or replace function public.protect_profile_role() returns trigger
language plpgsql as $$
begin
  if new.role <> old.role and not public.is_admin() then
    raise exception 'role 은 admin 만 바꿀 수 있습니다';
  end if;
  return new;
end $$;
drop trigger if exists profiles_protect_role on public.profiles;
create trigger profiles_protect_role before update on public.profiles
  for each row execute function public.protect_profile_role();

-- mapping_queue 는 수집(C)으로 분류했지만 승인·거절(update) 은 admin 만
drop policy if exists worker_update on public.mapping_queue;
create policy admin_update on public.mapping_queue for update to authenticated using (public.is_admin()) with check (public.is_admin());
