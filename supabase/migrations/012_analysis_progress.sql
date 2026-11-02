-- 012 · 즉시 분석 진행 상황 — 관리자 웹에서 "지금 어느 단계인지" 폴링으로 보여주기 위한 칸
alter table public.analysis_requests add column if not exists progress_json jsonb not null default '{}'::jsonb;
