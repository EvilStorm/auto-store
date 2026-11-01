-- 011 · matches 에 '무관(unrelated)' 도 저장 — 비교는 했는데 결과가 안 보이는 문제. 시장 신호 집계는 exact/similar 만 쓴다.
alter table public.matches drop constraint if exists matches_relation_check;
alter table public.matches add constraint matches_relation_check check (relation in ('exact', 'similar', 'unrelated'));
