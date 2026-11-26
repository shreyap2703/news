import type { NewsQuery } from './api.ts'

export const LOOK_BACK_OPTIONS = [
  { hours: 6, label: 'Last 6 hours' },
  { hours: 24, label: 'Last 24 hours' },
  { hours: 72, label: 'Last 3 days' },
] as const

export const HEADLINE_LIMIT = { min: 10, max: 50, step: 5 } as const

/** The sidebar choices. An empty category stands for the first section the API lists. */
export type NewsFilters = Pick<NewsQuery, 'category' | 'hours' | 'limit'>

const DEFAULT_FILTERS: NewsFilters = { category: '', hours: 24, limit: 30 }

// Session storage lasts as long as the browser tab, so reloading the page keeps the choices but a new tab starts fresh.
const STORAGE_KEY = 'daily-pulse:news-filters'

function isHeadlineLimit(value: unknown): value is number {
  return (
    typeof value === 'number' &&
    Number.isInteger(value) &&
    value >= HEADLINE_LIMIT.min &&
    value <= HEADLINE_LIMIT.max &&
    (value - HEADLINE_LIMIT.min) % HEADLINE_LIMIT.step === 0
  )
}

/** The filters last chosen in this tab, with the defaults for anything missing or no longer offered. */
export function loadFilters(): NewsFilters {
  let saved: Partial<Record<keyof NewsFilters, unknown>> = {}
  try {
    const parsed: unknown = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? '{}')
    if (parsed !== null && typeof parsed === 'object') saved = parsed
  } catch {
    // Storage is blocked or holds something other than JSON, so the defaults apply.
  }
  return {
    category: typeof saved.category === 'string' ? saved.category : DEFAULT_FILTERS.category,
    hours: LOOK_BACK_OPTIONS.find((option) => option.hours === saved.hours)?.hours ?? DEFAULT_FILTERS.hours,
    limit: isHeadlineLimit(saved.limit) ? saved.limit : DEFAULT_FILTERS.limit,
  }
}

export function saveFilters({ category, hours, limit }: NewsFilters): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ category, hours, limit }))
  } catch {
    // Without storage (for example, when the browser blocks it), a reload starts from the defaults again.
  }
}

/** The search typed in the top bar on another page, which opened the headlines page with `{ search }` as its state. */
export function searchFrom(state: unknown): string {
  if (state !== null && typeof state === 'object' && 'search' in state && typeof state.search === 'string') {
    return state.search.trim()
  }
  return ''
}
