import { useEffect, useState } from 'react'
import { errorMessage, fetchCategories, fetchNews, type NewsQuery } from './api.ts'
import BriefingPanel from './components/BriefingPanel.tsx'
import Sidebar from './components/Sidebar.tsx'
import { Alert, Spinner } from './components/Status.tsx'
import StoryCarousel from './components/StoryCarousel.tsx'
import type { Category, NewsResponse } from './types.ts'

interface LoadedNews {
  data: NewsResponse
  /** Increments on every successful load so the AI briefing resets whenever the headlines change. */
  version: number
}

export default function App() {
  const [categories, setCategories] = useState<Category[]>([])
  const [categoriesError, setCategoriesError] = useState<string | null>(null)
  const [categoriesAttempt, setCategoriesAttempt] = useState(0)
  const [query, setQuery] = useState<NewsQuery>({ category: '', hours: 24, limit: 30 })
  const [apiKey, setApiKey] = useState('')
  const [news, setNews] = useState<LoadedNews | null>(null)
  const [newsError, setNewsError] = useState<string | null>(null)
  const [settledQuery, setSettledQuery] = useState<NewsQuery | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchCategories(controller.signal)
      .then((items) => {
        setCategories(items)
        setQuery((current) => (current.category || items.length === 0 ? current : { ...current, category: items[0].id }))
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setCategoriesError(errorMessage(error))
      })
    return () => controller.abort()
  }, [categoriesAttempt])

  useEffect(() => {
    if (!query.category) return
    const controller = new AbortController()
    fetchNews(query, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return
        setNews((previous) => ({ data, version: (previous?.version ?? 0) + 1 }))
        setNewsError(null)
        setSettledQuery(query)
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setNewsError(errorMessage(error))
        setSettledQuery(query)
      })
    return () => controller.abort()
  }, [query])

  // Previous results stay visible (dimmed) while a new request is in flight.
  const loading = query.category !== '' && settledQuery !== query
  const showNewsError = !loading && newsError !== null
  const openAiKey = apiKey.trim()
  const updateQuery = (changes: Partial<Omit<NewsQuery, 'refresh'>>) =>
    setQuery((current) => ({ ...current, ...changes, refresh: false }))

  const refresh = () => {
    if (categories.length === 0) {
      // The sections never loaded (for example, the API was down), so retry them too.
      setCategoriesError(null)
      setCategoriesAttempt((attempt) => attempt + 1)
    }
    setQuery((current) => ({ ...current, refresh: true }))
  }

  return (
    <div className="app">
      <Sidebar
        categories={categories}
        category={query.category}
        hours={query.hours}
        limit={query.limit}
        apiKey={apiKey}
        onCategoryChange={(category) => updateQuery({ category })}
        onHoursChange={(hours) => updateQuery({ hours })}
        onLimitChange={(limit) => updateQuery({ limit })}
        onApiKeyChange={setApiKey}
        onRefresh={refresh}
      />

      <main className="main">
        <header className="hero">
          <div className="hero-badge" aria-hidden="true">
            🌍
          </div>
          <h1>The Daily Pulse</h1>
        </header>
        <p className="caption">A global news and AI intelligence dashboard · headlines refreshed every 10 minutes</p>
        <div className="info-banner">
          Headlines are gathered from the public Google News RSS feed in English. We always recommend opening the
          original article for full context.
        </div>

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
                {openAiKey && (
                  <BriefingPanel
                    key={news.version}
                    apiKey={openAiKey}
                    category={news.data.category.id}
                    hours={news.data.hours}
                    limit={news.data.articles.length}
                  />
                )}
                <h2 className="section-title">{news.data.category.label} — latest headlines</h2>
                <StoryCarousel key={`${news.data.category.id}-${news.data.hours}`} articles={news.data.articles} />
              </>
            )}
          </section>
        )}

        <hr className="divider" />
        <p className="caption">
          The Daily Pulse is an independent news reader, not a publisher. It does not verify every claim
          automatically. Compare multiple reputable sources for major or breaking events.
        </p>
      </main>
    </div>
  )
}
