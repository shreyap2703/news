import { createContext, useContext, type RefObject } from 'react'

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
}

export const BriefingMenuContext = createContext<BriefingMenuValue | null>(null)

export function useBriefingMenu(): BriefingMenuValue {
  const value = useContext(BriefingMenuContext)
  if (value === null) throw new Error('useBriefingMenu must be used inside <BriefingMenuProvider>.')
  return value
}
