import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation } from 'react-router'
import { errorMessage } from '../api.ts'
import { MAX_NAME_LENGTH, useAuth } from '../auth.ts'
import { Alert, Spinner } from '../components/Status.tsx'
import { logIn, signUp, supabaseSetupProblem } from '../supabase.ts'

type AuthMode = 'login' | 'signup'

type SubmitState =
  | { status: 'idle' }
  | { status: 'submitting' }
  | { status: 'error'; message: string }
  | { status: 'check-email'; email: string }

const MIN_PASSWORD_LENGTH = 8

const TEXT = {
  login: {
    title: 'Log in',
    intro: 'Welcome back. Log in to your Daily Pulse account.',
    submit: 'Log in',
    submitting: 'Logging in...',
    switchPrompt: "Don't have an account?",
    switchLabel: 'Sign up',
    switchTo: '/signup',
  },
  signup: {
    title: 'Create your account',
    intro: 'Sign up to save your Daily Pulse profile. Headlines stay free to read without an account.',
    submit: 'Sign up',
    submitting: 'Creating your account...',
    switchPrompt: 'Already have an account?',
    switchLabel: 'Log in',
    switchTo: '/login',
  },
} as const

/** The page that sent the user to log in (see ProfilePage), or the headlines. */
function redirectTarget(state: unknown): string {
  if (state !== null && typeof state === 'object' && 'from' in state && typeof state.from === 'string') {
    return state.from
  }
  return '/'
}

export default function AuthPage({ mode }: { mode: AuthMode }) {
  const { loading, user } = useAuth()
  const location = useLocation()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submit, setSubmit] = useState<SubmitState>({ status: 'idle' })
  const text = TEXT[mode]

  // Signed-in users do not need this page. This also completes a successful login or sign-up: the auth listener
  // stores the new session, and this redirect runs on the next render.
  if (user) return <Navigate to={redirectTarget(location.state)} replace />

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmit({ status: 'submitting' })
    const trimmedEmail = email.trim()
    try {
      if (mode === 'login') {
        await logIn(trimmedEmail, password)
      } else {
        const signedIn = await signUp(trimmedEmail, password, fullName.trim())
        // Projects that require email confirmation do not sign the user in yet.
        if (!signedIn) setSubmit({ status: 'check-email', email: trimmedEmail })
      }
    } catch (error) {
      setSubmit({ status: 'error', message: errorMessage(error) })
    }
  }

  const submitting = submit.status === 'submitting'

  return (
    <main className="page">
      <section className="card" aria-labelledby="auth-title">
        <h1 id="auth-title" className="page-title">
          {text.title}
        </h1>

        {loading ? (
          <Spinner label="Checking your session..." />
        ) : submit.status === 'check-email' ? (
          <>
            <Alert kind="success">
              Almost there! We sent a confirmation link to <strong>{submit.email}</strong>. Open it to activate your
              account, then log in.
            </Alert>
            <Link to="/login" className="button button-block">
              Go to log in
            </Link>
          </>
        ) : (
          <>
            <p className="caption">{text.intro}</p>
            {supabaseSetupProblem && <Alert kind="warning">{supabaseSetupProblem}</Alert>}

            <form onSubmit={handleSubmit}>
              <fieldset className="form" disabled={supabaseSetupProblem !== null}>
                {mode === 'signup' && (
                  <label className="field">
                    <span className="field-label">Full name</span>
                    <input
                      type="text"
                      value={fullName}
                      onChange={(event) => setFullName(event.target.value)}
                      autoComplete="name"
                      maxLength={MAX_NAME_LENGTH}
                      required
                    />
                  </label>
                )}
                <label className="field">
                  <span className="field-label">Email</span>
                  <input
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    autoComplete="email"
                    spellCheck={false}
                    required
                  />
                </label>
                <label className="field">
                  <span className="field-label">Password</span>
                  <input
                    type="password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
                    minLength={mode === 'signup' ? MIN_PASSWORD_LENGTH : undefined}
                    required
                  />
                  {mode === 'signup' && (
                    <span className="field-help">At least {MIN_PASSWORD_LENGTH} characters.</span>
                  )}
                </label>

                {submit.status === 'error' && <Alert kind="error">{submit.message}</Alert>}

                <button type="submit" className="button button-block" disabled={submitting}>
                  {submitting ? text.submitting : text.submit}
                </button>
              </fieldset>
            </form>

            <p className="auth-switch">
              {text.switchPrompt}{' '}
              <Link to={text.switchTo} state={location.state} className="text-link">
                {text.switchLabel}
              </Link>
            </p>
          </>
        )}
      </section>
    </main>
  )
}
