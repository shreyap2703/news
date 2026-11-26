import { useEffect, useState } from 'react'
import { Link, NavLink, matchPath, useLocation, useNavigate } from 'react-router'
import { displayName, useAuth } from '../auth.ts'
import { BRIEFING_SETTINGS_ID, useBriefingMenu } from '../briefingMenu.ts'
import { searchFrom } from '../filters.ts'
import ProfileMenu from './ProfileMenu.tsx'

/** The log in and sign up forms have nothing to search, so the search bar is hidden there. */
const PAGES_WITHOUT_SEARCH = ['/login', '/signup']

export default function NavBar() {
  const { loading, user, profile } = useAuth()
  const location = useLocation()
  const { pathname } = location
  const navigate = useNavigate()
  const name = user ? displayName(user, profile) : ''
  const showSearch = !PAGES_WITHOUT_SEARCH.some((path) => matchPath(path, pathname))
  // The menu button (which phones show) opens the briefing settings of the page, on pages that have them.
  const {
    open: menuOpen,
    setOpen: setMenuOpen,
    buttonRef: menuButtonRef,
    available: showMenuButton,
  } = useBriefingMenu()
  const [searchValue, setSearchValue] = useState(() => searchFrom(location.state))
  const [searchPage, setSearchPage] = useState(pathname)
  const [scrolled, setScrolled] = useState(false)

  // The box shows the search on screen: it empties when another page opens, and shows the search that brought the
  // reader to the headlines page from another page.
  if (pathname !== searchPage) {
    setSearchPage(pathname)
    setSearchValue(searchFrom(location.state))
  }

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 12)
    handleScroll()
    window.addEventListener('scroll', handleScroll)
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  const handleSearch = () => {
    const trimmed = searchValue.trim()
    setSearchValue(trimmed)
    if (pathname === '/') {
      window.dispatchEvent(new CustomEvent('news-search', { detail: trimmed }))
    } else if (trimmed) {
      // Searches cover every section, so other pages show the results on the headlines page.
      navigate('/', { state: { search: trimmed } })
    }
  }

  return (
    // While the briefing menu is open, the bar sits behind its backdrop and is out of reach of the keyboard.
    <header className={`navbar ${scrolled ? 'is-scrolled' : ''}`} inert={menuOpen}>
      <nav className="navbar-links" aria-label="Main">
        <NavLink to="/" end className="navbar-link">
          Home
        </NavLink>
        <NavLink to="/recommendations" className="navbar-link">
          For you
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
            {showMenuButton && (
              <button
                ref={menuButtonRef}
                type="button"
                className="navbar-menu"
                aria-label="Briefing settings"
                aria-controls={BRIEFING_SETTINGS_ID}
                aria-expanded={menuOpen}
                onClick={() => setMenuOpen(!menuOpen)}
              >
                <span aria-hidden="true" />
                <span aria-hidden="true" />
                <span aria-hidden="true" />
              </button>
            )}
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
              <ProfileMenu name={name} email={user.email ?? ''} />
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
