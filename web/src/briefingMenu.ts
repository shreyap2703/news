import { createContext, useContext, useEffect, type RefObject } from 'react'
import { flushSync } from 'react-dom'

/**
 * Screens on which the briefing settings live in a menu opened from the top bar instead of beside or above the
 * stories: phones, and phones held sideways. Keep in step with the matching media query in index.css.
 */
export const BRIEFING_MENU_QUERY = '(max-width: 640px), (max-width: 900px) and (max-height: 500px)'

/** The id of the briefing settings panel, which the menu button opens. */
export const BRIEFING_SETTINGS_ID = 'briefing-settings'

export interface BriefingMenuValue {
  /** Whether the briefing settings menu is open. It only opens on screens matching BRIEFING_MENU_QUERY. */
  open: boolean
  setOpen: (open: boolean) => void
  /** The menu button in the top bar, which gets the focus back when the menu closes. */
  buttonRef: RefObject<HTMLButtonElement | null>
  /** Whether the page shows briefing settings, so the top bar has a menu to open (see useBriefingSettingsMenu). */
  available: boolean
  setAvailable: (available: boolean) => void
}

export const BriefingMenuContext = createContext<BriefingMenuValue | null>(null)

export function useBriefingMenu(): BriefingMenuValue {
  const value = useContext(BriefingMenuContext)
  if (value === null) throw new Error('useBriefingMenu must be used inside <BriefingMenuProvider>.')
  return value
}

/**
 * For a page that shows the briefing settings (the Sidebar): offers the top bar's menu button while the page is on
 * screen, and closes the menu when it goes. Returns whether the menu is open, and how to close it.
 */
export function useBriefingSettingsMenu(): { menuOpen: boolean; closeMenu: () => void } {
  const { open, setOpen, buttonRef, setAvailable } = useBriefingMenu()

  useEffect(() => {
    setAvailable(true)
    return () => {
      setAvailable(false)
      setOpen(false)
    }
  }, [setAvailable, setOpen])

  const closeMenu = () => {
    // The top bar stops being inert once the menu has closed, and only then can its button take the focus back.
    flushSync(() => setOpen(false))
    buttonRef.current?.focus()
  }
  return { menuOpen: open, closeMenu }
}
