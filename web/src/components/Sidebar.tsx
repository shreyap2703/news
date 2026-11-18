import { useEffect, useRef } from 'react'
import { BRIEFING_SETTINGS_ID } from '../briefingMenu.ts'
import { HEADLINE_LIMIT, LOOK_BACK_OPTIONS } from '../filters.ts'
import type { Category } from '../types.ts'

interface SidebarProps {
  categories: Category[]
  category: string
  hours: number
  limit: number
  onCategoryChange: (category: string) => void
  onHoursChange: (hours: number) => void
  onLimitChange: (limit: number) => void
  onRefresh: () => void
  /** On phones the settings are a menu opened from the top bar: whether it is open. */
  menuOpen: boolean
  onCloseMenu: () => void
}

export default function Sidebar({
  categories,
  category,
  hours,
  limit,
  onCategoryChange,
  onHoursChange,
  onLimitChange,
  onRefresh,
  menuOpen,
  onCloseMenu,
}: SidebarProps) {
  const sidebarRef = useRef<HTMLElement>(null)

  // Opening the menu moves the focus into it, so keyboard and screen reader users land on the settings.
  useEffect(() => {
    if (menuOpen) sidebarRef.current?.focus()
  }, [menuOpen])

  return (
    <aside
      id={BRIEFING_SETTINGS_ID}
      ref={sidebarRef}
      className={menuOpen ? 'sidebar is-open' : 'sidebar'}
      aria-label="Briefing settings"
      role={menuOpen ? 'dialog' : undefined}
      aria-modal={menuOpen || undefined}
      tabIndex={-1}
      onKeyDown={(event) => {
        if (menuOpen && event.key === 'Escape') onCloseMenu()
      }}
    >
      <div className="sidebar-header">
        <h2 className="sidebar-title">Your briefing</h2>
        <button type="button" className="sidebar-close" aria-label="Close briefing settings" onClick={onCloseMenu}>
          <span aria-hidden="true">×</span>
        </button>
      </div>

      <label className="field">
        <span className="field-label">News section</span>
        <select
          value={category}
          onChange={(event) => onCategoryChange(event.target.value)}
          disabled={categories.length === 0}
        >
          {categories.map((item) => (
            <option key={item.id} value={item.id}>
              {item.label}
            </option>
          ))}
        </select>
      </label>

      <label className="field">
        <span className="field-label">Look back</span>
        <select value={hours} onChange={(event) => onHoursChange(Number(event.target.value))}>
          {LOOK_BACK_OPTIONS.map((option) => (
            <option key={option.hours} value={option.hours}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label className="field">
        <span className="field-label">
          Number of headlines <output className="field-value">{limit}</output>
        </span>
        <input
          type="range"
          min={HEADLINE_LIMIT.min}
          max={HEADLINE_LIMIT.max}
          step={HEADLINE_LIMIT.step}
          value={limit}
          onChange={(event) => onLimitChange(Number(event.target.value))}
        />
      </label>

      <span className="chip">English-only mode</span>

      <button type="button" className="button button-block" onClick={onRefresh}>
        Refresh headlines
      </button>
    </aside>
  )
}
