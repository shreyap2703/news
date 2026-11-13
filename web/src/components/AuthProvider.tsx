import type { Session } from '@supabase/supabase-js'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { errorMessage } from '../api.ts'
import { AuthContext, type AuthContextValue, type ProfileState } from '../auth.ts'
import { fetchProfile, supabaseSetupProblem, watchSession, type Profile } from '../supabase.ts'

const PROFILE_LOADING: ProfileState = { status: 'loading' }

interface LoadedProfile {
  userId: string
  attempt: number
  state: ProfileState
}

/** Tracks the Supabase session (restored from local storage on page load) and the signed-in user's profile. */
export default function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(supabaseSetupProblem === null)
  const [attempt, setAttempt] = useState(0)
  const [loaded, setLoaded] = useState<LoadedProfile | null>(null)

  useEffect(() => {
    if (supabaseSetupProblem) return
    let active = true
    let stopWatching: (() => void) | undefined
    watchSession((nextSession) => {
      if (!active) return
      setSession(nextSession)
      setLoading(false)
    }).then(
      (stop) => {
        if (active) stopWatching = stop
        else stop()
      },
      (error: unknown) => {
        // For example, the Supabase library failed to download. Headlines still work; the forms report the problem.
        console.error('Could not start Supabase:', error)
        if (active) setLoading(false)
      },
    )
    return () => {
      active = false
      stopWatching?.()
    }
  }, [])

  const user = session?.user ?? null
  const userId = user?.id ?? null

  useEffect(() => {
    if (!userId) return
    let active = true
    fetchProfile(userId).then(
      (profile) => {
        if (active) setLoaded({ userId, attempt, state: { status: 'ready', profile } })
      },
      (error: unknown) => {
        if (active) setLoaded({ userId, attempt, state: { status: 'error', message: errorMessage(error) } })
      },
    )
    return () => {
      active = false
    }
  }, [userId, attempt])

  // A profile fetched for another user or an earlier attempt counts as still loading.
  const profile = loaded?.userId === userId && loaded.attempt === attempt ? loaded.state : PROFILE_LOADING

  const reloadProfile = useCallback(() => setAttempt((current) => current + 1), [])
  const onProfileSaved = useCallback(
    (saved: Profile) => setLoaded({ userId: saved.id, attempt, state: { status: 'ready', profile: saved } }),
    [attempt],
  )

  const value = useMemo<AuthContextValue>(
    () => ({ loading, user, profile, reloadProfile, onProfileSaved }),
    [loading, user, profile, reloadProfile, onProfileSaved],
  )

  return <AuthContext value={value}>{children}</AuthContext>
}
