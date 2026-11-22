import type { User } from '@supabase/supabase-js'
import { createContext, useContext } from 'react'
import type { Profile } from './supabase.ts'

export type ProfileState =
  | { status: 'loading' }
  | { status: 'ready'; profile: Profile | null }
  | { status: 'error'; message: string }

export interface AuthContextValue {
  /** True until Supabase has restored the saved session, if there is one. */
  loading: boolean
  user: User | null
  /** The signed-in user's row in the Supabase profiles table. */
  profile: ProfileState
  reloadProfile: () => void
  onProfileSaved: (profile: Profile) => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (value === null) throw new Error('useAuth must be used inside <AuthProvider>.')
  return value
}

/** Matches the length check on profiles.full_name in supabase/migrations. */
export const MAX_NAME_LENGTH = 100

/** The name entered on the sign-up form, which Supabase keeps in the user's metadata. */
export function signUpName(user: User): string {
  const name: unknown = user.user_metadata.full_name
  return typeof name === 'string' ? name.trim() : ''
}

export function displayName(user: User, profile: ProfileState): string {
  const profileName = profile.status === 'ready' ? profile.profile?.full_name?.trim() : undefined
  return profileName || signUpName(user) || user.email || 'Your account'
}

/** The first two letters (or digits) of a name, in capitals, for the round badge in the top bar. */
export function avatarLetters(name: string): string {
  const characters = Array.from(name.trim())
  // Spaces and punctuation are skipped, so "A. Kumar" gives "AK" and an email address gives its first two letters.
  const letters = characters.filter((character) => /[\p{L}\p{N}]/u.test(character))
  return (letters.length > 0 ? letters : characters).slice(0, 2).join('').toUpperCase() || '?'
}
