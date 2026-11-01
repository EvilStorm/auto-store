-- 010 · 2차: 등록 상품 · 감시 이벤트 · 주문 · 실제 원가 (개인). DESIGN.md 5.1 listings · monitor_events, 5.3 orders · order_costs

create table if not exists public.listings (
  candidate_id          bigint primary key references public.candidates(id) on delete cascade,
  user_id               uuid not null references auth.users(id) on delete cascade,
  source_item_id        bigint not null references public.source_items(id),
  store_product_no      text,
  sale_price_krw        integer not null,
  listed_at             timestamptz not null default now(),
  suspended_at          timestamptz,
  monitor_status        text not null default 'ok' check (monitor_status in ('ok', 'changed', 'soldout', 'removed', 'check_needed')),
  last_checked_at       timestamptz,
  consecutive_failures  integer not null default 0,
  baseline_json         jsonb not null default '{}'::jsonb      -- 등록 시점 소스 스냅샷 {unit_price, moq, options_soldout[], sold_out}
);

create table if not exists public.monitor_events (
  id                   bigserial primary key,
  candidate_id         bigint not null references public.candidates(id) on delete cascade,
  user_id              uuid not null references auth.users(id) on delete cascade,
  kind                 text not null check (kind in ('price', 'soldout', 'option_soldout', 'moq', 'removed', 'restored')),
  before_json          jsonb not null default '{}'::jsonb,
  after_json           jsonb not null default '{}'::jsonb,
  recalculated_margin  numeric(6,4),
  suggested_price_krw  integer,
  notified_at          timestamptz,
  decision             text check (decision in ('reprice', 'suspend', 'ignore')),
  decided_at           timestamptz,
  created_at           timestamptz not null default now()
);
create index if not exists monitor_events_open_idx on public.monitor_events (user_id, candidate_id, kind) where decision is null;

create table if not exists public.orders (
  id                 bigserial primary key,
  user_id            uuid not null references auth.users(id) on delete cascade,
  store_order_no     text not null,
  ordered_at         timestamptz not null default now(),
  candidate_id       bigint references public.candidates(id),
  option_name        text,
  qty                integer not null default 1,
  paid_krw           integer not null default 0,
  buyer_pccc_ok      boolean not null default false,
  source_order_no    text,
  source_ordered_at  date,
  status             text not null default 'new' check (status in ('new', 'pccc_check', 'source_ordered', 'at_forwarder', 'shipped', 'customs', 'delivered', 'canceled')),
  tracking_no        text,
  eta_date           date,
  memo               text,
  updated_at         timestamptz not null default now(),
  unique (user_id, store_order_no)
);
drop trigger if exists orders_updated_at on public.orders;
create trigger orders_updated_at before update on public.orders for each row execute function public.set_updated_at();

create table if not exists public.order_costs (
  order_id            bigint primary key references public.orders(id) on delete cascade,
  user_id             uuid not null references auth.users(id) on delete cascade,
  source_paid_src     numeric(12,2) not null default 0,
  currency            text not null default 'CNY',
  rate                numeric(12,4) not null default 0,
  proxy_fee_krw       integer not null default 0,
  forwarder_fee_krw   integer not null default 0,
  customs_krw         integer not null default 0,
  other_krw           integer not null default 0,
  total_actual_krw    integer not null default 0,
  estimated_krw       integer,
  updated_at          timestamptz not null default now()
);

do $$
declare t text;
begin
  foreach t in array array['listings', 'monitor_events', 'orders', 'order_costs'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists own_rows on public.%I', t);
    execute format('create policy own_rows on public.%I for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid())', t);
  end loop;
end $$;

-- 월 손익: 매출 − 실제 원가 − 네이버 · 결제 수수료 − API 비용 (내 것만)
create or replace function public.my_month_pnl(p_month date default date_trunc('month', now())::date)
returns table (revenue_krw bigint, actual_cost_krw bigint, fee_krw bigint, api_cost_krw numeric, orders_count bigint)
language sql stable as $$
  with o as (
    select o.id, o.paid_krw, coalesce(oc.total_actual_krw, 0) as actual
    from public.orders o left join public.order_costs oc on oc.order_id = o.id
    where o.user_id = auth.uid() and o.status <> 'canceled' and o.ordered_at >= p_month and o.ordered_at < p_month + interval '1 month'
  ), s as (select coalesce(naver_fee_rate, 0.055) + coalesce(payment_fee_rate, 0.02) as fee_rate from public.user_settings where user_id = auth.uid())
  select coalesce(sum(o.paid_krw), 0)::bigint, coalesce(sum(o.actual), 0)::bigint,
         coalesce(round(sum(o.paid_krw) * (select fee_rate from s)), 0)::bigint,
         (select coalesce(sum(est_cost_krw), 0) from public.api_usage where user_id = auth.uid() and called_at >= p_month and called_at < p_month + interval '1 month'),
         count(*)::bigint
  from o;
$$;
grant execute on function public.my_month_pnl(date) to authenticated;
