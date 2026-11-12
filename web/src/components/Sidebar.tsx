import type { Category } from '../types.ts'

const LOOK_BACK_OPTIONS = [
  { hours: 6, label: 'Last 6 hours' },
  { hours: 24, label: 'Last 24 hours' },
  { hours: 72, label: 'Last 3 days' },
] as const

const HEADLINE_LIMIT = { min: 10, max: 50, step: 5 } as const

interface SidebarProps {
  categories: Category[]
  category: string
  hours: number
  limit: number
  apiKey: string
  onCategoryChange: (category: string) => void
  onHoursChange: (hours: number) => void
  onLimitChange: (limit: number) => void
  onApiKeyChange: (apiKey: string) => void
  onRefresh: () => void
}

export default function Sidebar({
  categories,
  category,
  hours,
  limit,
  apiKey,
  onCategoryChange,
  onHoursChange,
  onLimitChange,
  onApiKeyChange,
  onRefresh,
}: SidebarProps) {
  return (
    <aside className="sidebar" aria-label="Briefing settings">
      <h2 className="sidebar-title">Your briefing</h2>

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

      <hr className="divider" />

      <h3 className="sidebar-subtitle">AI briefing</h3>
      <label className="field">
        <span className="field-label">OpenAI API key</span>
        <input
          type="password"
          value={apiKey}
          onChange={(event) => onApiKeyChange(event.target.value)}
          placeholder="sk-..."
          autoComplete="off"
          spellCheck={false}
        />
        <span className="field-help">Used only for this session. It is not saved by this app.</span>
      </label>
      <p className="caption">Headlines load without a key; it is only needed for the AI briefing.</p>

      <button type="button" className="button button-block" onClick={onRefresh}>
        Refresh headlines
      </button>
    </aside>
  )
}
