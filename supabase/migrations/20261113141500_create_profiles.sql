-- Profiles for The Daily Pulse accounts.
-- Run this once in your Supabase project: paste it into the SQL Editor and click Run, or use `supabase db push`.
-- Supabase Auth stores the email and password; this table stores the profile data the app shows and edits.

create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  full_name text constraint full_name_length check (char_length(full_name) <= 100),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.profiles is 'Profile data for each signed-up user of The Daily Pulse.';

-- Grant only what the app needs. Profiles are private, so signed-out visitors (anon) get no access.
revoke all on table public.profiles from anon, authenticated;
grant select, insert, update on table public.profiles to authenticated;
grant select, insert, update, delete on table public.profiles to service_role;

-- Row Level Security limits every signed-in user to their own row.
alter table public.profiles enable row level security;

create policy "Users can view their own profile"
  on public.profiles for select
  to authenticated
  using ((select auth.uid()) = id);

create policy "Users can create their own profile"
  on public.profiles for insert
  to authenticated
  with check ((select auth.uid()) = id);

create policy "Users can update their own profile"
  on public.profiles for update
  to authenticated
  using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);

-- Keep updated_at current.
create function public.handle_profile_updated()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

create trigger on_profile_updated
  before update on public.profiles
  for each row execute function public.handle_profile_updated();

-- Create a profile when someone signs up, using the name the sign-up form sends as user metadata.
-- The name is trimmed and shortened to fit, because an error here would block the sign-up itself.
create function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = ''
as $$
begin
  insert into public.profiles (id, full_name)
  values (new.id, nullif(left(trim(new.raw_user_meta_data ->> 'full_name'), 100), ''));
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Give users who signed up before this migration a profile too.
insert into public.profiles (id, full_name)
select id, nullif(left(trim(raw_user_meta_data ->> 'full_name'), 100), '')
from auth.users
on conflict (id) do nothing;
