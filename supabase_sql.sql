-- RPG_BOT / Supabase schema (clean + executable)
-- Generated: 2025-12-27
--
-- Goal
-- - Your existing schema dump is "context only" and includes mismatched column names.
-- - This script aligns the DB with what the current bot code (db.py) actually reads/writes.
--
-- How to apply
-- 1) Supabase Dashboard -> SQL Editor
-- 2) Run this whole file
--
-- Notes
-- - Safe-ish to re-run: uses CREATE TABLE IF NOT EXISTS / ALTER TABLE ADD COLUMN IF NOT EXISTS
-- - For constraints/indexes, uses DO blocks to avoid duplicate_object errors
-- - Does NOT enable RLS. If you enable RLS, add policies appropriate to your setup.

begin;

-- ============================================================
-- One-time cleanup (raid system removed)
-- ============================================================
-- These tables are no longer used by the bot.
-- Safe to keep if you want history, but you requested to DROP them.
-- NOTE: If you had views/policies depending on these tables, DROP may fail.

drop table if exists public.raid_contributions;
drop table if exists public.raid_bosses;
drop table if exists public.player_raid_stats;

-- ============================================================
-- Utilities
-- ============================================================

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ============================================================
-- players (core)
-- ============================================================
-- Used heavily by db.py via /rest/v1/players
-- We store adventure thread ids in milestone_flags to avoid schema churn.

alter table if exists public.players
  add column if not exists milestone_flags jsonb not null default '{}'::jsonb;

-- BAN state used by check_ban() + anti-cheat tooling
alter table if exists public.players
  add column if not exists is_banned boolean not null default false;

alter table if exists public.players
  add column if not exists ban_reason text;

-- Some deployments used bot_banned/web_banned; keep compatibility
alter table if exists public.players
  add column if not exists web_banned boolean not null default false;

-- ============================================================
-- guild_settings (server-scoped config for thread mode)
-- ============================================================
-- Used by: !set / !set off / !start

create table if not exists public.guild_settings (
  guild_id text primary key,
  adventure_parent_channel_id text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists guild_settings_set_updated_at on public.guild_settings;
create trigger guild_settings_set_updated_at
before update on public.guild_settings
for each row
execute function public.set_updated_at();

-- ============================================================
-- storage (item storage between runs)
-- ============================================================
-- Used by db.py: /rest/v1/storage

create table if not exists public.storage (
  id bigserial primary key,
  user_id text not null,
  item_name text not null,
  item_type text not null,
  stored_at timestamptz not null default now(),
  is_taken boolean not null default false,
  taken_at timestamptz
);

create index if not exists storage_user_id_idx on public.storage (user_id);
create index if not exists storage_user_taken_idx on public.storage (user_id, is_taken);

-- ============================================================
-- death_history (death logs)
-- ============================================================
-- Used by db.py: /rest/v1/death_history

create table if not exists public.death_history (
  id bigserial primary key,
  user_id text not null,
  enemy_name text not null,
  enemy_type text not null default 'normal',
  distance integer not null default 0,
  floor integer not null default 0,
  stage integer not null default 0,
  died_at timestamptz not null default now()
);

create index if not exists death_history_user_id_idx on public.death_history (user_id);
create index if not exists death_history_user_died_at_idx on public.death_history (user_id, died_at desc);

-- ============================================================
-- player_titles (title ownership)
-- ============================================================
-- Used by db.py: /rest/v1/player_titles

create table if not exists public.player_titles (
  id bigserial primary key,
  user_id text not null,
  title_id text not null,
  title_name text not null,
  unlocked_at timestamptz not null default now()
);

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'player_titles_user_title_unique'
      and conrelid = 'public.player_titles'::regclass
  ) then
    alter table public.player_titles
      add constraint player_titles_user_title_unique unique (user_id, title_id);
  end if;
end $$;

create index if not exists player_titles_user_id_idx on public.player_titles (user_id);

-- ============================================================
-- secret_weapons_global (global drop limits)
-- ============================================================
-- Used by db.py: /rest/v1/secret_weapons_global

create table if not exists public.secret_weapons_global (
  weapon_id integer primary key,
  total_dropped integer not null default 0,
  max_limit integer not null default 10,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists secret_weapons_global_set_updated_at on public.secret_weapons_global;
create trigger secret_weapons_global_set_updated_at
before update on public.secret_weapons_global
for each row
execute function public.set_updated_at();

-- ============================================================
-- player_vault_gold (vault)
-- ============================================================
-- Used by db.py: /rest/v1/player_vault_gold

create table if not exists public.player_vault_gold (
  id bigserial primary key,
  user_id text not null unique,
  vault_gold bigint not null default 0,
  total_deposited bigint not null default 0,
  total_withdrawn bigint not null default 0,
  last_updated timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists player_vault_gold_set_updated_at on public.player_vault_gold;
create trigger player_vault_gold_set_updated_at
before update on public.player_vault_gold
for each row
execute function public.set_updated_at();

-- ============================================================
-- command_logs (anti-cheat uses these)
-- ============================================================
-- NOTE: Your current schema uses command_name. The bot writes column `command`.
-- We add required columns.

create table if not exists public.command_logs (
  id bigserial primary key,
  user_id text not null,
  command text not null,
  success boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  timestamp timestamptz not null default now()
);

alter table if exists public.command_logs
  add column if not exists command text;

alter table if exists public.command_logs
  add column if not exists success boolean not null default true;

alter table if exists public.command_logs
  add column if not exists metadata jsonb not null default '{}'::jsonb;

create index if not exists command_logs_user_time_idx on public.command_logs (user_id, timestamp desc);

-- ============================================================
-- anti_cheat_logs
-- ============================================================
-- NOTE: Your current schema uses detection_type/score.
-- The bot writes event_type/anomaly_score.

create table if not exists public.anti_cheat_logs (
  id bigserial primary key,
  user_id text not null,
  event_type text not null,
  severity text not null,
  anomaly_score integer not null default 0,
  details jsonb not null default '{}'::jsonb,
  timestamp timestamptz not null default now()
);

alter table if exists public.anti_cheat_logs
  add column if not exists event_type text;

alter table if exists public.anti_cheat_logs
  add column if not exists anomaly_score integer not null default 0;

alter table if exists public.anti_cheat_logs
  add column if not exists details jsonb;

create index if not exists anti_cheat_logs_user_time_idx on public.anti_cheat_logs (user_id, timestamp desc);

-- ============================================================
-- user_behavior_stats (anti-cheat / admin views)
-- ============================================================
-- NOTE: Your schema is "stats"-heavy; the bot writes session-based fields.

create table if not exists public.user_behavior_stats (
  user_id text primary key,
  total_commands integer not null default 0,
  current_session_hours double precision not null default 0,
  unused_upgrade_points integer not null default 0,
  has_equipment boolean not null default false,
  last_active timestamptz,
  last_updated timestamptz not null default now()
);

alter table if exists public.user_behavior_stats
  add column if not exists current_session_hours double precision not null default 0;

alter table if exists public.user_behavior_stats
  add column if not exists unused_upgrade_points integer not null default 0;

alter table if exists public.user_behavior_stats
  add column if not exists has_equipment boolean not null default false;

alter table if exists public.user_behavior_stats
  add column if not exists last_active timestamptz;

alter table if exists public.user_behavior_stats
  add column if not exists last_updated timestamptz;

commit;

-- ============================================================
-- RLS (Optional)
-- ============================================================
-- If you enable RLS on these tables, ensure your bot uses service_role
-- or add appropriate policies.
