import { Link, NavLink } from 'react-router'
import { displayName, useAuth } from '../auth.ts'
import { logOut } from '../supabase.ts'

function handleLogOut() {
  logOut().catch((error: unknown) => console.error('Could not log out:', error))
}

export default function NavBar() {
  const { loading, user, profile } = useAuth()
  const name = user ? displayName(user, profile) : ''

  return (
    <header className="navbar">
      <Link to="/" className="navbar-brand">
        <span className="navbar-logo" aria-hidden="true">
          🌍
        </span>
        <span className="navbar-brand-name">The Daily Pulse</span>
      </Link>

      <nav className="navbar-links" aria-label="Main">
        <NavLink to="/" end className="navbar-link">
          Headlines
        </NavLink>
      </nav>

      {/* Nothing is shown while the saved session is restored, so the buttons do not flicker. */}
      {!loading && (
        <div className="navbar-account">
          {user ? (
            <>
              <NavLink to="/profile" className="navbar-user" title="Your profile">
                <span className="avatar" aria-hidden="true">
                  {(Array.from(name)[0] ?? '?').toUpperCase()}
                </span>
                <span className="navbar-user-name">{name}</span>
              </NavLink>
              <button type="button" className="button button-ghost button-small" onClick={handleLogOut}>
                Log out
              </button>
            </>
          ) : (
            <>
              <NavLink to="/login" className="button button-ghost button-small">
                Log in
              </NavLink>
              <NavLink to="/signup" className="button button-small">
                Sign up
              </NavLink>
            </>
          )}
        </div>
      )}
    </header>
  )
}
