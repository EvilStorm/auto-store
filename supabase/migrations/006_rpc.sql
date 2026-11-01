-- 006 · RPC (DESIGN.md 4.1 · 6-③ · 11장)
-- 전부 security invoker 라 호출자의 RLS 가 그대로 적용된다. 시크릿 Vault RPC 는 승격 때 추가.

-- 배치 잠금. 그날 (user, kind) 를 먼저 insert 한 PC 가 true. 같은 PC 의 재호출도 true (heartbeat 갱신).
-- 다른 PC 가 가진 잠금은 heartbeat 가 p_stale_minutes 넘게 끊겼을 때만 인수한다.
create or replace function public.acquire_batch_lock(
  p_run_date date, p_kind text, p_pc_name text, p_stale_minutes integer default 10
) returns boolean
language plpgsql as $$
declare
  uid uuid := auth.uid();
  holder text;
  hb timestamptz;
begin
  if uid is null then raise exception '로그인 필요'; end if;
  insert into public.batch_locks (user_id, run_date, kind, pc_name)
  values (uid, p_run_date, p_kind, p_pc_name)
  on conflict (user_id, run_date, kind) do nothing;
  select pc_name, heartbeat_at into holder, hb
    from public.batch_locks where user_id = uid and run_date = p_run_date and kind = p_kind;
  if holder = p_pc_name then
    update public.batch_locks set heartbeat_at = now()
      where user_id = uid and run_date = p_run_date and kind = p_kind;
    return true;
  end if;
  if hb < now() - make_interval(mins => p_stale_minutes) then
    update public.batch_locks set pc_name = p_pc_name, acquired_at = now(), heartbeat_at = now()
      where user_id = uid and run_date = p_run_date and kind = p_kind;
    return true;
  end if;
  return false;
end $$;

-- 워커 임대 (텔레그램 폴링 등 "한 PC 만"). 비어 있거나 만료됐거나 내 것이면 갱신하고 true.
create or replace function public.renew_worker_lease(
  p_kind text, p_pc_name text, p_ttl_seconds integer default 90
) returns boolean
language plpgsql as $$
declare
  uid uuid := auth.uid();
  cur_pc text;
  cur_exp timestamptz;
begin
  if uid is null then raise exception '로그인 필요'; end if;
  select pc_name, expires_at into cur_pc, cur_exp from public.worker_leases where user_id = uid and kind = p_kind;
  if cur_pc is null or cur_pc = p_pc_name or cur_exp < now() then
    insert into public.worker_leases (user_id, kind, pc_name, expires_at)
    values (uid, p_kind, p_pc_name, now() + make_interval(secs => p_ttl_seconds))
    on conflict (user_id, kind) do update set pc_name = excluded.pc_name, expires_at = excluded.expires_at;
    return true;
  end if;
  return false;
end $$;

-- 이미지 유사도 검색 (테이블 전체 대상: 소스 간 그룹핑 · 동일 이미지 전체 검색). 20장 비교는 파이썬에서.
create or replace function public.match_images(
  p_query vector(512), p_kind text default 'naver', p_k integer default 20, p_min_similarity numeric default 0.70
) returns table (id bigint, kind text, ref_id text, url text, similarity numeric)
language sql stable as $$
  select i.id, i.kind, i.ref_id, i.url, (1 - (i.clip <=> p_query))::numeric(5,4) as similarity
  from public.images i
  where i.clip is not null and (p_kind is null or i.kind = p_kind)
    and (1 - (i.clip <=> p_query)) >= p_min_similarity
  order by i.clip <=> p_query
  limit p_k;
$$;

-- 현재 사전 버전
create or replace function public.current_dict_version() returns integer
language sql stable as $$ select dict_version from public.dict_meta where id; $$;

-- 통화별 최신 환율 1행씩
create or replace function public.latest_exchange_rates() returns table (currency text, rate_krw numeric, source text, fetched_at timestamptz)
language sql stable as $$
  select distinct on (currency) currency, rate_krw, source, fetched_at
  from public.exchange_rates order by currency, fetched_at desc;
$$;

-- 이번 달 API 비용 합계 (내 것)
create or replace function public.my_month_api_cost(p_month date default date_trunc('month', now())::date) returns numeric
language sql stable as $$
  select coalesce(sum(est_cost_krw), 0) from public.api_usage
  where user_id = auth.uid() and called_at >= p_month and called_at < (p_month + interval '1 month');
$$;

grant execute on function public.acquire_batch_lock(date, text, text, integer) to authenticated;
grant execute on function public.renew_worker_lease(text, text, integer) to authenticated;
grant execute on function public.match_images(vector, text, integer, numeric) to authenticated;
grant execute on function public.current_dict_version() to authenticated;
grant execute on function public.latest_exchange_rates() to authenticated;
grant execute on function public.my_month_api_cost(date) to authenticated;
