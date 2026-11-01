-- 009 · 2차: ⑦ 생성 콘텐츠 · ⑨ 패키지 (개인) + Storage 공개 버킷과 정책
-- DESIGN.md 5.3 generated_contents · packages, 4.1 Storage

create table if not exists public.generated_contents (
  candidate_id      bigint primary key references public.candidates(id) on delete cascade,
  user_id           uuid not null references auth.users(id) on delete cascade,
  title_options     text[] not null default '{}',
  title_chosen      text,
  description_html  text,
  options_ko_json   jsonb not null default '[]'::jsonb,    -- [{name_raw, name_ko, price_src, sell: bool}]
  blocks_json       jsonb not null default '{}'::jsonb,    -- {notice, shipping, returns, customs}
  image_urls        text[] not null default '{}',          -- 소스 원본 (모드 A: 가공 없음)
  mode              text not null default 'A',
  forbidden_hits    text[] not null default '{}',
  revise_note       text,
  llm_cost_krw      numeric(10,2) not null default 0,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);
drop trigger if exists generated_contents_updated_at on public.generated_contents;
create trigger generated_contents_updated_at before update on public.generated_contents
  for each row execute function public.set_updated_at();

create table if not exists public.packages (
  candidate_id        bigint primary key references public.candidates(id) on delete cascade,
  user_id             uuid not null references auth.users(id) on delete cascade,
  excel_row_json      jsonb not null,
  image_public_urls   text[] not null default '{}',
  output_path         text,
  sale_price_krw      integer,
  created_at          timestamptz not null default now()
);

do $$
declare t text;
begin
  foreach t in array array['generated_contents', 'packages'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists own_rows on public.%I', t);
    execute format('create policy own_rows on public.%I for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid())', t);
  end loop;
end $$;

-- Storage: 공개 버킷 product-images. 읽기는 누구나(공개 URL), 쓰기는 로그인 사용자가 자기 폴더(<user_id>/...)에만
insert into storage.buckets (id, name, public) values ('product-images', 'product-images', true)
  on conflict (id) do update set public = true;

drop policy if exists "product-images public read" on storage.objects;
create policy "product-images public read" on storage.objects for select to public using (bucket_id = 'product-images');
drop policy if exists "product-images own write" on storage.objects;
create policy "product-images own write" on storage.objects for insert to authenticated
  with check (bucket_id = 'product-images' and (storage.foldername(name))[1] = auth.uid()::text);
drop policy if exists "product-images own update" on storage.objects;
create policy "product-images own update" on storage.objects for update to authenticated
  using (bucket_id = 'product-images' and (storage.foldername(name))[1] = auth.uid()::text);
drop policy if exists "product-images own delete" on storage.objects;
create policy "product-images own delete" on storage.objects for delete to authenticated
  using (bucket_id = 'product-images' and (storage.foldername(name))[1] = auth.uid()::text);
