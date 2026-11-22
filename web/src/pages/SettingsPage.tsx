import type { User } from '@supabase/supabase-js'
import { useState, type FormEvent } from 'react'
import { errorMessage } from '../api.ts'
import { MAX_NAME_LENGTH, signUpName, useAuth } from '../auth.ts'
import AccountPage from '../components/AccountPage.tsx'
import { Alert } from '../components/Status.tsx'
import { saveProfile, type Profile } from '../supabase.ts'

type SaveState = { status: 'idle' } | { status: 'saving' } | { status: 'saved' } | { status: 'error'; message: string }

function ProfileForm({ user, profile }: { user: User; profile: Profile | null }) {
  const { onProfileSaved } = useAuth()
  const [fullName, setFullName] = useState(profile?.full_name ?? signUpName(user))
  const [save, setSave] = useState<SaveState>({ status: 'idle' })

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
        <span className="field-help">Shown in the top bar and on your profile.</span>
      </label>
      {save.status === 'saved' && <Alert kind="success">Your profile was saved.</Alert>}
      {save.status === 'error' && <Alert kind="error">Could not save your profile: {save.message}</Alert>}
      <button type="submit" className="button button-block" disabled={save.status === 'saving'}>
        {save.status === 'saving' ? 'Saving...' : 'Save changes'}
      </button>
    </form>
  )
}

export default function SettingsPage() {
  return <AccountPage title="Settings">{(user, profile) => <ProfileForm user={user} profile={profile} />}</AccountPage>
}
