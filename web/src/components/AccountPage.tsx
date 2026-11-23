import type { User } from '@supabase/supabase-js'
import { useId, useState, type ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'
import { useAuth } from '../auth.ts'
import type { Profile } from '../supabase.ts'
import { Alert, Spinner } from './Status.tsx'

interface AccountPageProps {
  title: string
  /** The page's content, shown once the signed-in user's profile has loaded. */
  children: (user: User, profile: Profile | null) => ReactNode
}

/** The frame of the signed-in pages (Profile and Settings). Visitors who are not logged in go to the login page. */
export default function AccountPage({ title, children }: AccountPageProps) {
  const { loading, user, profile, reloadProfile } = useAuth()
  const location = useLocation()
  const titleId = useId()
  // Logging out from these pages should lead to the headlines, while arriving signed out should lead to the login page.
  const [wasSignedIn, setWasSignedIn] = useState(user !== null)
  if (user && !wasSignedIn) setWasSignedIn(true)

  if (!loading && !user) {
    return wasSignedIn ? <Navigate to="/" replace /> : <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  return (
    <main className="page">
      <section className="card" aria-labelledby={titleId}>
        <h1 id={titleId} className="page-title">
          {title}
        </h1>

        {!user ? (
          <Spinner label="Checking your session..." />
        ) : (
          <>
            <p className="caption">Your profile is stored in Supabase. Only you can view or change it.</p>
            {profile.status === 'loading' && <Spinner label="Loading your profile..." />}
            {profile.status === 'error' && (
              <>
                <Alert kind="error">Could not load your profile: {profile.message}</Alert>
                <button type="button" className="button button-block" onClick={reloadProfile}>
                  Try again
                </button>
              </>
            )}
            {profile.status === 'ready' && children(user, profile.profile)}
          </>
        )}
      </section>
    </main>
  )
}
