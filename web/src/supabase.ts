import type { PostgrestError, Session, SupabaseClient } from '@supabase/supabase-js'
import type { Database } from './database.types.ts'

export type Profile = Database['public']['Tables']['profiles']['Row']

const PROFILE_COLUMNS = 'id, full_name, created_at, updated_at'
const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL?.trim() ?? ''
const PUBLISHABLE_KEY = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY?.trim() ?? ''

function isHttpUrl(value: string): boolean {
  try {
    return ['http:', 'https:'].includes(new URL(value).protocol)
  } catch {
    return false
  }
}

function findSetupProblem(): string | null {
  if (!SUPABASE_URL || !PUBLISHABLE_KEY) {
    return (
      'Accounts are not set up yet. Add your Supabase project URL and publishable key to web/.env.local, then ' +
      'restart the dev server (or rebuild the app). See the README for the steps.'
    )
  }
  if (!isHttpUrl(SUPABASE_URL)) {
    return 'Accounts are unavailable because VITE_SUPABASE_URL in web/.env.local is not a valid http(s) URL.'
  }
  return null
}

/** Why accounts are unavailable, or null when Supabase is configured. Headlines work either way. */
export const supabaseSetupProblem = findSetupProblem()

let clientPromise: Promise<SupabaseClient<Database>> | undefined

/** Loads the Supabase library on first use, so the headlines page does not wait for it. */
function getSupabase(): Promise<SupabaseClient<Database>> {
  if (supabaseSetupProblem) return Promise.reject(new Error(supabaseSetupProblem))
  // A failed download is not retried: the session listener in AuthProvider could not start either, so a reload is
  // needed to get everything working again.
  clientPromise ??= import('@supabase/supabase-js').then(
    ({ createClient }) => createClient<Database>(SUPABASE_URL, PUBLISHABLE_KEY),
    (error: unknown) => {
      throw new Error('Could not load the account features. Check your internet connection and reload the page.', {
        cause: error,
      })
    },
  )
  return clientPromise
}

async function toAuthError(error: unknown): Promise<Error> {
  const { isAuthRetryableFetchError } = await import('@supabase/supabase-js')
  if (isAuthRetryableFetchError(error)) {
    return new Error('Could not reach Supabase. Check your internet connection and the Supabase URL in web/.env.local.')
  }
  return error instanceof Error ? error : new Error(String(error))
}

/**
 * Calls `onChange` with the current session, which Supabase restores from local storage, and again whenever it
 * changes (log in, log out, token refresh, or a change in another tab). Resolves to a function that stops watching.
 */
export async function watchSession(onChange: (session: Session | null) => void): Promise<() => void> {
  const supabase = await getSupabase()
  // Only pass the session on: awaiting other Supabase calls inside this callback can deadlock.
  const { data } = supabase.auth.onAuthStateChange((_event, session) => onChange(session))
  return () => data.subscription.unsubscribe()
}

export async function logIn(email: string, password: string): Promise<void> {
  const supabase = await getSupabase()
  const { error } = await supabase.auth.signInWithPassword({ email, password })
  if (error) throw await toAuthError(error)
}

/** Creates an account. Resolves to false when the user must confirm their email address before logging in. */
export async function signUp(email: string, password: string, fullName: string): Promise<boolean> {
  const supabase = await getSupabase()
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: {
      // The on_auth_user_created trigger copies the name into the user's new row in the profiles table.
      data: { full_name: fullName },
      emailRedirectTo: window.location.origin,
    },
  })
  if (error) throw await toAuthError(error)
  return data.session !== null
}

/** Signs out this browser only. That succeeds even if Supabase cannot be reached to revoke the session. */
export async function logOut(): Promise<void> {
  const supabase = await getSupabase()
  const { error } = await supabase.auth.signOut({ scope: 'local' })
  if (error) console.warn('Signed out locally, but Supabase could not revoke the session:', error.message)
}

function profileError(error: PostgrestError): Error {
  // PGRST205: the Data API cannot find the table; 42P01: Postgres reports it does not exist.
  if (error.code === 'PGRST205' || error.code === '42P01') {
    return new Error(
      'The profiles table was not found. Run the SQL in supabase/migrations in your Supabase project (see the README).',
    )
  }
  return new Error(error.message)
}

/** Returns the user's profile, or null if they do not have one yet. Row Level Security limits users to their own row. */
export async function fetchProfile(userId: string): Promise<Profile | null> {
  const supabase = await getSupabase()
  const { data, error } = await supabase.from('profiles').select(PROFILE_COLUMNS).eq('id', userId).maybeSingle()
  if (error) throw profileError(error)
  return data
}

/** Creates or updates the user's profile and returns the saved row. */
export async function saveProfile(userId: string, fullName: string): Promise<Profile> {
  const supabase = await getSupabase()
  const { data, error } = await supabase
    .from('profiles')
    .upsert({ id: userId, full_name: fullName })
    .select(PROFILE_COLUMNS)
    .single()
  if (error) throw profileError(error)
  return data
}
