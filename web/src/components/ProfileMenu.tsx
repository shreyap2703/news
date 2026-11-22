import { useEffect, useId, useRef, useState, type Ref } from 'react'
import { NavLink } from 'react-router'
import { avatarLetters } from '../auth.ts'
import { logOut } from '../supabase.ts'

// Leaving the button or the menu with the pointer closes the menu only after this long, so moving between them, or
// briefly off them, does not close it.
const HOVER_CLOSE_DELAY_MS = 250

/** How the menu was opened: by hovering (it closes when the pointer leaves) or by a click, tap, or key (it stays). */
type OpenedBy = 'hover' | 'click'

function handleLogOut() {
  logOut().catch((error: unknown) => console.error('Could not log out:', error))
}

function Icon({ path }: { path: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={path} />
    </svg>
  )
}

const PROFILE_ICON = 'M12 12.5a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM4.5 20c.9-3.4 3.9-5.5 7.5-5.5s6.6 2.1 7.5 5.5'
const SETTINGS_ICON = 'M4 7h9M17 7h3M4 17h3M11 17h9M15 9.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5ZM9 19.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z'
const LOG_OUT_ICON = 'M14 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4M9.5 16.5 5 12l4.5-4.5M5 12h10'

interface ProfileMenuProps {
  name: string
  email: string
}

/**
 * The signed-in user's round badge in the top bar, showing the first two letters of their name. Hovering over it, or
 * clicking or tapping it, opens a menu with the profile, the settings, and logging out.
 */
export default function ProfileMenu({ name, email }: ProfileMenuProps) {
  const [openedBy, setOpenedBy] = useState<OpenedBy | null>(null)
  const open = openedBy !== null
  const menuId = useId()
  const rootRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const closeTimer = useRef<number | undefined>(undefined)

  const close = () => {
    window.clearTimeout(closeTimer.current)
    setOpenedBy(null)
  }

  // A click or tap anywhere else closes the menu.
  useEffect(() => {
    if (!open) return
    const handlePointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpenedBy(null)
    }
    document.addEventListener('pointerdown', handlePointerDown)
    return () => document.removeEventListener('pointerdown', handlePointerDown)
  }, [open])

  useEffect(() => () => window.clearTimeout(closeTimer.current), [])

  return (
    <div
      ref={rootRef}
      className="profile-menu"
      onPointerEnter={(event) => {
        if (event.pointerType !== 'mouse') return
        window.clearTimeout(closeTimer.current)
        setOpenedBy((current) => current ?? 'hover')
      }}
      onPointerLeave={(event) => {
        if (event.pointerType !== 'mouse' || openedBy !== 'hover') return
        closeTimer.current = window.setTimeout(() => setOpenedBy(null), HOVER_CLOSE_DELAY_MS)
      }}
      onKeyDown={(event) => {
        if (event.key === 'Escape' && open) {
          close()
          buttonRef.current?.focus()
        }
      }}
      onBlur={(event) => {
        // Moving the keyboard focus out of the menu closes it.
        if (open && !rootRef.current?.contains(event.relatedTarget as Node | null)) close()
      }}
    >
      <ProfileButton
        ref={buttonRef}
        name={name}
        open={open}
        menuId={menuId}
        // A click keeps a menu opened by hovering open; a second click closes it.
        onClick={() => setOpenedBy((current) => (current === 'click' ? null : 'click'))}
      />
      {open && (
        <div id={menuId} className="profile-menu-panel">
          <div className="profile-menu-card">
            <p className="profile-menu-who">
              <span className="profile-menu-name">{name}</span>
              {email && email !== name && <span className="profile-menu-email">{email}</span>}
            </p>
            <ul className="profile-menu-items">
              <li>
                <NavLink to="/profile" className="profile-menu-item" onClick={close}>
                  <Icon path={PROFILE_ICON} />
                  Profile
                </NavLink>
              </li>
              <li>
                <NavLink to="/settings" className="profile-menu-item" onClick={close}>
                  <Icon path={SETTINGS_ICON} />
                  Settings
                </NavLink>
              </li>
              <li className="profile-menu-log-out">
                <button
                  type="button"
                  className="profile-menu-item"
                  onClick={() => {
                    close()
                    handleLogOut()
                  }}
                >
                  <Icon path={LOG_OUT_ICON} />
                  Log out
                </button>
              </li>
            </ul>
          </div>
        </div>
      )}
    </div>
  )
}

interface ProfileButtonProps {
  name: string
  open: boolean
  menuId: string
  onClick: () => void
  ref: Ref<HTMLButtonElement>
}

function ProfileButton({ name, open, menuId, onClick, ref }: ProfileButtonProps) {
  return (
    <button
      ref={ref}
      type="button"
      className="navbar-user"
      aria-label={`${name}, account menu`}
      aria-expanded={open}
      aria-controls={open ? menuId : undefined}
      onClick={onClick}
    >
      <span className="avatar" aria-hidden="true">
        {avatarLetters(name)}
      </span>
    </button>
  )
}
