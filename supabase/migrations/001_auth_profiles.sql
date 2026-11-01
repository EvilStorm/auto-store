-- 001 · 확장 · 계정(profiles) · is_admin() · 가입 시 프로필 자동 생성 (첫 계정은 admin)
-- DESIGN.md 5.0

create extension if not exists pgcrypto;
create extension if not exists vector;

-- updated_at 자동 갱신 공용 트리거 함수
create or replace function public.set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

create table if not exists public.profiles (
  user_id          uuid primary key references auth.users(id) on delete cascade,
  display_name     text,
  role             text not null default 'user' check (role in ('admin', 'user')),
  telegram_chat_id text,
  created_at       timestamptz not null default now()
);

-- RLS 정책과 RPC 가 쓰는 관리자 판정. security definer 라 profiles 의 RLS 를 우회해 읽는다.
create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.profiles where user_id = auth.uid() and role = 'admin');
$$;
revoke all on function public.is_admin() from public;
grant execute on function public.is_admin() to authenticated;

-- 가입(auth.users insert) 시 profiles 1행. 아직 프로필이 하나도 없으면 그 계정이 admin.
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (user_id, display_name, role)
  values (
    new.id,
    coalesce(new.raw_user_meta_data ->> 'display_name', split_part(coalesce(new.email, ''), '@', 1)),
    case when not exists (select 1 from public.profiles) then 'admin' else 'user' end
  )
  on conflict (user_id) do nothing;
  return new;
end $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
