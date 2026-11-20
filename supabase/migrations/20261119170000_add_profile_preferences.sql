-- Reading preferences chosen on the welcome page after sign-up.
-- Run this once in your Supabase project after 20261113141500_create_profiles.sql: paste it into the SQL Editor and
-- click Run, or use `supabase db push`.
-- The column is null until the user finishes or skips the welcome page that opens after sign-up.

alter table public.profiles
  add column preferences jsonb
  constraint preferences_is_object check (preferences is null or jsonb_typeof(preferences) = 'object');

comment on column public.profiles.preferences is
  'Reading preferences from the welcome page (sections, topics, languages, theme, updates); null until set up.';
