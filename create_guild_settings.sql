-- Guild-level settings for RPG_BOT
-- Run this on Supabase (SQL Editor) before enabling `!set` thread mode.

create table if not exists public.guild_settings (
  guild_id text primary key,
  adventure_parent_channel_id text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Optional: keep updated_at fresh
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists guild_settings_set_updated_at on public.guild_settings;
create trigger guild_settings_set_updated_at
before update on public.guild_settings
for each row
execute function public.set_updated_at();

-- If you use RLS, add appropriate policies for your service role/key.
