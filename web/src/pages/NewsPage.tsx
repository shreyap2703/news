import { useEffect, useMemo, useState } from 'react'
import { flushSync } from 'react-dom'
import { errorMessage, fetchCategories, fetchNews, type NewsQuery } from '../api.ts'
import { useAuth } from '../auth.ts'
import { useBriefingMenu } from '../briefingMenu.ts'
import Sidebar from '../components/Sidebar.tsx'
import { Alert, Spinner } from '../components/Status.tsx'
import StoryCarousel from '../components/StoryCarousel.tsx'
import { loadFilters, saveFilters } from '../filters.ts'
import { orderSections, parsePreferences } from '../preferences.ts'
import type { Category, NewsResponse } from '../types.ts'

interface LoadedNews {
  data: NewsResponse
  /** Increments on every successful load so the AI briefing resets whenever the headlines change. */
  version: number
}

export default function NewsPage() {
  // Read once, so a page reload comes back to the section and filters chosen before it.
  const [savedFilters] = useState(loadFilters)
  const [categories, setCategories] = useState<Category[]>([])
  const [categoriesError, setCategoriesError] = useState<string | null>(null)
  const [categoriesAttempt, setCategoriesAttempt] = useState(0)
  // An empty category means "not picked yet": the default section below is used until the reader picks one.
  const [query, setQuery] = useState<NewsQuery>({ ...savedFilters, category: '' })
  const [submittedSearch, setSubmittedSearch] = useState('')
  const [searchVersion, setSearchVersion] = useState(0)
  const [news, setNews] = useState<LoadedNews | null>(null)
  const [newsError, setNewsError] = useState<string | null>(null)
  const [settledQuery, setSettledQuery] = useState<NewsQuery | null>(null)
  const { open: menuOpen, setOpen: setMenuOpen, buttonRef: menuButtonRef } = useBriefingMenu()
  const { profile } = useAuth()

  // The briefing menu belongs to this page, so it closes when the page is left.
  useEffect(() => () => setMenuOpen(false), [setMenuOpen])

  const closeMenu = () => {
    // The top bar stops being inert once the menu has closed, and only then can its button take the focus back.
    flushSync(() => setMenuOpen(false))
    menuButtonRef.current?.focus()
  }

  // Signed-in readers see the sections they chose on the welcome page first, and open on the first of them.
  const savedPreferences = profile.status === 'ready' ? profile.profile?.preferences : null
  const preferredSections = useMemo(() => parsePreferences(savedPreferences)?.sections ?? [], [savedPreferences])
  const orderedCategories = useMemo(() => orderSections(categories, preferredSections), [categories, preferredSections])
  // The section chosen earlier in this tab wins; one that no longer exists is never requested.
  const defaultCategory = categories.some((item) => item.id === savedFilters.category)
    ? savedFilters.category
    : (orderedCategories[0]?.id ?? '')
  const category = query.category || defaultCategory

  useEffect(() => {
    const controller = new AbortController()
    fetchCategories(controller.signal)
      .then(setCategories)
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setCategoriesError(errorMessage(error))
      })
    return () => controller.abort()
  }, [categoriesAttempt])

  useEffect(() => {
    // Nothing is saved until a section is known, so the saved choices survive the first render after a reload.
    if (category) saveFilters({ category, hours: query.hours, limit: query.limit })
  }, [category, query.hours, query.limit])

  useEffect(() => {
    const handleSearchFromNav = (event: Event) => {
      const detail = (event as CustomEvent<string | undefined>).detail ?? ''
      const next = String(detail).trim()
      setSubmittedSearch(next)
      setSearchVersion((value) => value + 1)
    }

    window.addEventListener('news-search', handleSearchFromNav)
    return () => window.removeEventListener('news-search', handleSearchFromNav)
  }, [])

  useEffect(() => {
    if (!category) return
    const controller = new AbortController()
    const activeSearch = submittedSearch.trim()
    const request = { ...query, category, search: activeSearch || undefined }
    fetchNews(request, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return
        setNews((previous) => ({ data, version: (previous?.version ?? 0) + 1 }))
        setNewsError(null)
        setSettledQuery(request)
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setNewsError(errorMessage(error))
        setSettledQuery(request)
      })
    return () => controller.abort()
  }, [query, category, submittedSearch, searchVersion])

  // Previous results stay visible (dimmed) while a new request is in flight.
  const loading =
    category !== '' &&
    (!settledQuery ||
      category !== settledQuery.category ||
      query.hours !== settledQuery.hours ||
      query.limit !== settledQuery.limit ||
      (submittedSearch || '') !== (settledQuery.search || '') ||
      Boolean(query.refresh) !== Boolean(settledQuery.refresh))
  const showNewsError = !loading && newsError !== null
  const updateQuery = (changes: Partial<Omit<NewsQuery, 'refresh'>>) =>
    setQuery((current) => ({ ...current, ...changes, refresh: false }))

  const handleCategoryChange = (category: string) => {
    setSubmittedSearch('')
    updateQuery({ category })
  }

  const refresh = () => {
    // On phones the settings are a menu; refreshing closes it so the headlines come into view.
    if (menuOpen) closeMenu()
    if (categories.length === 0) {
      setCategoriesError(null)
      setCategoriesAttempt((attempt) => attempt + 1)
    }
    setQuery((current) => ({ ...current, refresh: true }))
  }

  const activeSearch = submittedSearch.trim()
  // The no-break space keeps the dash on the first line when the title wraps on narrow screens.
  const sectionTitle = activeSearch
    ? `Latest headlines on ${activeSearch}`
    : `${news?.data.category.label ?? 'Latest'}\u00a0— latest headlines`

  return (
    <div className="dashboard">
      {menuOpen && <div className="sidebar-backdrop" aria-hidden="true" onClick={closeMenu} />}
      <Sidebar
        categories={orderedCategories}
        category={category}
        hours={query.hours}
        limit={query.limit}
        onCategoryChange={handleCategoryChange}
        onHoursChange={(hours) => updateQuery({ hours })}
        onLimitChange={(limit) => updateQuery({ limit })}
        onRefresh={refresh}
        menuOpen={menuOpen}
        onCloseMenu={closeMenu}
      />

      <main className="main" inert={menuOpen}>
        <header className="hero">
          <div className="hero-badge" aria-hidden="true">
            🌍
          </div>
          <h1>The Daily Pulse</h1>
        </header>
        <p className="caption">A global news and AI intelligence dashboard · headlines refreshed every 10 minutes</p>

        {categoriesError && <Alert kind="error">Could not load news sections: {categoriesError}</Alert>}
        {loading && <Spinner label="Gathering recent headlines..." />}
        {showNewsError && <Alert kind="error">Could not retrieve headlines right now: {newsError}</Alert>}

        {news && !showNewsError && (
          <section className={loading ? 'results is-loading' : 'results'} aria-busy={loading}>
            {news.data.usingFallback && (
              <p className="caption">Using backup headlines while the public news feed recovers.</p>
            )}
            {news.data.articles.length === 0 ? (
              <Alert kind="warning">No headlines were returned for this filter. Try a longer time window.</Alert>
            ) : (
              <>
                <h2 className="section-title">{sectionTitle}</h2>
                <StoryCarousel key={`${news.data.category.id}-${news.data.hours}`} articles={news.data.articles} />
              </>
            )}
          </section>
        )}
      </main>
    </div>
  )
}
