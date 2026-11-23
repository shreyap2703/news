import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { BRIEFING_MENU_QUERY, BriefingMenuContext } from '../briefingMenu.ts'

/** Shares the briefing settings menu between the top bar, which opens it, and the page that shows the settings. */
export default function BriefingMenuProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const [available, setAvailable] = useState(false)
  const buttonRef = useRef<HTMLButtonElement>(null)

  // On wider screens the settings are always shown, so the menu closes when the window grows past phone size.
  useEffect(() => {
    const query = window.matchMedia(BRIEFING_MENU_QUERY)
    const handleChange = () => {
      if (!query.matches) setOpen(false)
    }
    query.addEventListener('change', handleChange)
    return () => query.removeEventListener('change', handleChange)
  }, [])

  const value = useMemo(() => ({ open, setOpen, buttonRef, available, setAvailable }), [open, available])
  return <BriefingMenuContext value={value}>{children}</BriefingMenuContext>
}
