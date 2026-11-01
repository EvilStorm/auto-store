-- 008 · profiles.role 보호 트리거 보정: service_role · 직접 SQL(auth.uid() 가 null) 은 관리자 작업으로 보고 허용.
-- 005 의 버전은 auth.uid() 가 null 이면 is_admin() 이 false 라 service_role 의 role 변경까지 막았다 (계정 승격 불가).

create or replace function public.protect_profile_role() returns trigger
language plpgsql as $$
begin
  if new.role <> old.role and auth.uid() is not null and not public.is_admin() then
    raise exception 'role 은 admin 만 바꿀 수 있습니다';
  end if;
  return new;
end $$;

-- 관리자가 쓰는 승격 RPC (admin 또는 service_role 만). 두 번째 계정부터는 이걸로 admin 을 늘린다.
create or replace function public.set_profile_role(p_user_id uuid, p_role text) returns void
language plpgsql security definer set search_path = public as $$
begin
  if p_role not in ('admin', 'user') then raise exception 'role 은 admin | user'; end if;
  if auth.uid() is not null and not public.is_admin() then raise exception 'admin 만 가능'; end if;
  update public.profiles set role = p_role where user_id = p_user_id;
end $$;
revoke all on function public.set_profile_role(uuid, text) from public;
grant execute on function public.set_profile_role(uuid, text) to authenticated, service_role;
