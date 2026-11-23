import { Link } from 'react-router'
import { signUpName } from '../auth.ts'
import AccountPage from '../components/AccountPage.tsx'

const dateFormatter = new Intl.DateTimeFormat(undefined, { dateStyle: 'long' })

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : dateFormatter.format(date)
}

/** The signed-in user's details. The name is changed on the Settings page, reading preferences on the welcome page. */
export default function ProfilePage() {
  return (
    <AccountPage title="Your profile">
      {(user, profile) => {
        const fullName = profile?.full_name?.trim() || signUpName(user)
        const memberSince = profile?.created_at ?? user.created_at
        return (
          <>
            <dl className="details">
              <div>
                <dt>Full name</dt>
                <dd>{fullName || 'Not set'}</dd>
              </div>
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
            <Link to="/settings" className="button button-block">
              Edit in Settings
            </Link>
            <p className="auth-switch">
              Want different headlines?{' '}
              <Link to="/welcome" className="text-link">
                Edit your reading preferences
              </Link>
            </p>
          </>
        )
      }}
    </AccountPage>
  )
}
