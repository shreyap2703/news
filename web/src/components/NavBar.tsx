import { useEffect, useState } from 'react'
import { Link, NavLink, matchPath, useLocation } from 'react-router'
import { displayName, useAuth } from '../auth.ts'
import { logOut } from '../supabase.ts'

/** The log in and sign up forms have nothing to search, so the search bar is hidden there. */
const PAGES_WITHOUT_SEARCH = ['/login', '/signup']

function handleLogOut() {
  logOut().catch((error: unknown) => console.error('Could not log out:', error))
}

export default function NavBar() {
  const { loading, user, profile } = useAuth()
  const { pathname } = useLocation()
  const name = user ? displayName(user, profile) : ''
  const showSearch = !PAGES_WITHOUT_SEARCH.some((path) => matchPath(path, pathname))
  const [searchValue, setSearchValue] = useState('')
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 12)
    handleScroll()
    window.addEventListener('scroll', handleScroll)
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  const handleSearch = () => {
    const trimmed = searchValue.trim()
    setSearchValue(trimmed)
    window.dispatchEvent(new CustomEvent('news-search', { detail: trimmed }))
  }

  return (
    <header className={`navbar ${scrolled ? 'is-scrolled' : ''}`}>
      <nav className="navbar-links" aria-label="Main">
        <NavLink to="/" end className="navbar-link">
          Headlines
        </NavLink>
      </nav>

      <div className="navbar-brand-wrap">
        <Link to="/" className="navbar-brand">
          <span className="navbar-logo" aria-hidden="true">
            🌍
          </span>
          <span className="navbar-brand-name">The Daily Pulse</span>
        </Link>
      </div>

      <div className="navbar-actions">
        {showSearch && (
          <div className="navbar-search" role="search">
            <input
              type="text"
              value={searchValue}
              onChange={(event) => setSearchValue(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') handleSearch()
              }}
              placeholder="Search topics..."
              aria-label="Search news topics"
            />
            <button type="button" className="button button-small" onClick={handleSearch}>
              Search
            </button>
          </div>
        )}

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
      </div>
    </header>
  )
}
