-- Add shield equipment slot to players table
-- Run this in Supabase SQL editor

ALTER TABLE public.players
ADD COLUMN IF NOT EXISTS equipped_shield text;
