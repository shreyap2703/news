import type { User } from '@supabase/supabase-js'
import { useState, type FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router'
import { errorMessage } from '../api.ts'
import { MAX_NAME_LENGTH, signUpName, useAuth } from '../auth.ts'
import { Alert, Spinner } from '../components/Status.tsx'
import { saveProfile, type Profile } from '../supabase.ts'

const dateFormatter = new Intl.DateTimeFormat(undefined, { dateStyle: 'long' })

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : dateFormatter.format(date)
}

type SaveState = { status: 'idle' } | { status: 'saving' } | { status: 'saved' } | { status: 'error'; message: string }

function ProfileForm({ user, profile }: { user: User; profile: Profile | null }) {
  const { onProfileSaved } = useAuth()
  const [fullName, setFullName] = useState(profile?.full_name ?? signUpName(user))
  const [save, setSave] = useState<SaveState>({ status: 'idle' })
  const memberSince = profile?.created_at ?? user.created_at

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSave({ status: 'saving' })
    try {
      onProfileSaved(await saveProfile(user.id, fullName.trim()))
      setSave({ status: 'saved' })
    } catch (error) {
      setSave({ status: 'error', message: errorMessage(error) })
    }
  }

  return (
    <>
      <dl className="details">
        <div>
          <dt>Email</dt>
          <dd>{user.email}</dd>
        </div>
        <div>
          <dt>Member since</dt>
          <dd>
            <time dateTime={memberSince}>{formatDate(memberSince)}</time>
          </dd>
        </div>
      </dl>

      <form className="form" onSubmit={handleSubmit}>
        <label className="field">
          <span className="field-label">Full name</span>
          <input
            type="text"
            value={fullName}
            onChange={(event) => {
              setFullName(event.target.value)
              setSave({ status: 'idle' })
            }}
            autoComplete="name"
            maxLength={MAX_NAME_LENGTH}
            required
          />
        </label>
        {save.status === 'saved' && <Alert kind="success">Your profile was saved.</Alert>}
        {save.status === 'error' && <Alert kind="error">Could not save your profile: {save.message}</Alert>}
        <button type="submit" className="button button-block" disabled={save.status === 'saving'}>
          {save.status === 'saving' ? 'Saving...' : 'Save changes'}
        </button>
      </form>
    </>
  )
}

export default function ProfilePage() {
  const { loading, user, profile, reloadProfile } = useAuth()
  const location = useLocation()
  // Logging out from this page should lead to the headlines, while arriving signed out should lead to the login page.
  const [wasSignedIn, setWasSignedIn] = useState(user !== null)
  if (user && !wasSignedIn) setWasSignedIn(true)

  if (!loading && !user) {
    return wasSignedIn ? <Navigate to="/" replace /> : <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  return (
    <main className="page">
      <section className="card" aria-labelledby="profile-title">
        <h1 id="profile-title" className="page-title">
          Your profile
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
            {profile.status === 'ready' && <ProfileForm user={user} profile={profile.profile} />}
          </>
        )}
      </section>
    </main>
  )
}
