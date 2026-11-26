import { useEffect, useId, useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { errorMessage, fetchCategories, fetchRecommendations, type RecommendationsQuery } from '../api.ts'
import { useAuth } from '../auth.ts'
import { useBriefingSettingsMenu } from '../briefingMenu.ts'
import Sidebar from '../components/Sidebar.tsx'
import { Alert, Spinner } from '../components/Status.tsx'
import StoryCarousel from '../components/StoryCarousel.tsx'
import { loadFilters, saveFilters } from '../filters.ts'
import { SECTION_ICONS, parsePreferences, type Preferences } from '../preferences.ts'
import type { Category, RecommendationReason, RecommendationsResponse } from '../types.ts'

// The log in, sign-up, and preferences pages send the reader back here afterwards.
const RETURN_HERE = { from: '/recommendations' }
const TOPIC_ICON = '⭐'
const CITY_ICON = '📍'

/** The city or state the reader gave, without the state after a comma ("Hyderabad, Telangana" -> "Hyderabad"). */
function place(city: string): string {
  return city.split(',')[0].trim()
}

function hasInterests(preferences: Preferences): boolean {
  return preferences.sections.length > 0 || preferences.followTopics.some((topic) => topic.trim()) || place(preferences.city) !== ''
}

function reasonIcon(reason: RecommendationReason): string {
  if (reason.kind === 'topic') return TOPIC_ICON
  if (reason.kind === 'city') return CITY_ICON
  return SECTION_ICONS[reason.sectionId] ?? '📰'
}

function reasonText(reason: RecommendationReason): string {
  if (reason.kind === 'topic') return `Recommended because you follow ${reason.label}`
  if (reason.kind === 'city') return `Near you: local news from ${reason.label}`
  return `From ${reason.label}, one of your sections`
}

function ReasonTag({ reason }: { reason: RecommendationReason }) {
  return (
    <span className="news-reason" title={reasonText(reason)}>
      <span aria-hidden="true">
        {reasonIcon(reason)} {reason.label}
      </span>
      <span className="visually-hidden">{reasonText(reason)}</span>
    </span>
  )
}

/** A card in the middle of the page, like the log in and profile pages. */
function Notice({ title, children }: { title: string; children: ReactNode }) {
  const titleId = useId()
  return (
    <main className="page">
      <section className="card" aria-labelledby={titleId}>
        <h1 id={titleId} className="page-title">
          {title}
        </h1>
        {children}
      </section>
    </main>
  )
}

/**
 * Stories combined from the interests the reader chose after sign-up: followed topics first, then their sections and
 * local news. Readers who are not logged in are asked to log in first.
 */
export default function RecommendationsPage() {
  const { loading, user, profile, reloadProfile } = useAuth()
  const savedPreferences = profile.status === 'ready' ? profile.profile?.preferences : undefined
  const preferences = useMemo(() => parsePreferences(savedPreferences), [savedPreferences])

  if (!loading && !user) {
    return (
      <Notice title="Recommended for you">
        <p className="caption">
          Log in to see stories picked for you: the sections, topics, and city you chose when you signed up, combined
          in one feed.
        </p>
        <Link to="/login" state={RETURN_HERE} className="button button-block">
          Log in
        </Link>
        <p className="auth-switch">
          New here?{' '}
          <Link to="/signup" state={RETURN_HERE} className="text-link">
            Create an account
          </Link>
        </p>
      </Notice>
    )
  }

  if (!user || profile.status === 'loading') {
    return (
      <Notice title="Recommended for you">
        <Spinner label="Loading your interests..." />
      </Notice>
    )
  }

  if (profile.status === 'error') {
    return (
      <Notice title="Recommended for you">
        <Alert kind="error">Could not load your interests: {profile.message}</Alert>
        <button type="button" className="button button-block" onClick={reloadProfile}>
          Try again
        </button>
      </Notice>
    )
  }

  if (!preferences || !hasInterests(preferences)) {
    return (
      <Notice title="Recommended for you">
        <p className="caption">
          Tell us what you like to read. This page combines the sections, topics, and city you pick into one feed.
        </p>
        <Link to="/welcome" state={RETURN_HERE} className="button button-block">
          Choose your interests
        </Link>
      </Notice>
    )
  }

  return <RecommendationsFeed preferences={preferences} />
}

function RecommendationsFeed({ preferences }: { preferences: Preferences }) {
  const { menuOpen, closeMenu } = useBriefingSettingsMenu()
  // The look-back window and the number of stories are shared with the headlines page.
  const [savedFilters] = useState(loadFilters)
  const [settings, setSettings] = useState({ hours: savedFilters.hours, limit: savedFilters.limit, refresh: false })
  const [categories, setCategories] = useState<Category[]>([])
  const [data, setData] = useState<RecommendationsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [settled, setSettled] = useState<RecommendationsQuery | null>(null)

  const request = useMemo<RecommendationsQuery>(
    () => ({
      sections: preferences.sections,
      topics: preferences.followTopics,
      city: preferences.city,
      mutedTopics: preferences.mutedTopics,
      hiddenSources: preferences.hiddenSources,
      ...settings,
    }),
    [preferences, settings],
  )

  // Only the section names in the sidebar come from here, so a failure just leaves them out.
  useEffect(() => {
    const controller = new AbortController()
    fetchCategories(controller.signal)
      .then(setCategories)
      .catch(() => {})
    return () => controller.abort()
  }, [])

  useEffect(() => {
    saveFilters({ ...loadFilters(), hours: settings.hours, limit: settings.limit })
  }, [settings.hours, settings.limit])

  useEffect(() => {
    const controller = new AbortController()
    fetchRecommendations(request, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return
        setData(result)
        setError(null)
        setSettled(request)
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return
        setError(errorMessage(reason))
        setSettled(request)
      })
    return () => controller.abort()
  }, [request])

  // Previous stories stay visible (dimmed) while new ones load.
  const loading = settled !== request
  const showError = !loading && error !== null
  const update = (changes: Partial<Pick<typeof settings, 'hours' | 'limit'>>) =>
    setSettings((current) => ({ ...current, ...changes, refresh: false }))

  const refresh = () => {
    // On phones the settings are a menu; refreshing closes it so the stories come into view.
    if (menuOpen) closeMenu()
    setSettings((current) => ({ ...current, refresh: true }))
  }

  const sectionChips = preferences.sections.flatMap((id) => {
    const label = categories.find((item) => item.id === id)?.label
    return label ? [{ key: `section-${id}`, icon: SECTION_ICONS[id] ?? '📰', label }] : []
  })
  const topicChips = preferences.followTopics
    .filter((topic) => topic.trim())
    .map((topic) => ({ key: `topic-${topic}`, icon: TOPIC_ICON, label: topic }))
  const city = place(preferences.city)
  const chips = [...sectionChips, ...topicChips, ...(city ? [{ key: 'city', icon: CITY_ICON, label: city }] : [])]
  const leftOut = [...preferences.mutedTopics, ...preferences.hiddenSources]

  return (
    <div className="dashboard">
      {menuOpen && <div className="sidebar-backdrop" aria-hidden="true" onClick={closeMenu} />}
      <Sidebar
        title="Your interests"
        hours={settings.hours}
        limit={settings.limit}
        onHoursChange={(hours) => update({ hours })}
        onLimitChange={(limit) => update({ limit })}
        onRefresh={refresh}
        refreshLabel="Refresh recommendations"
        menuOpen={menuOpen}
        onCloseMenu={closeMenu}
      >
        <div className="sidebar-interests">
          <ul className="interest-chips" aria-label="Interests these stories come from">
            {chips.map((chip) => (
              <li key={chip.key} className="interest-chip">
                <span aria-hidden="true">{chip.icon}</span> {chip.label}
              </li>
            ))}
          </ul>
          {leftOut.length > 0 && <p className="field-help">Leaving out: {leftOut.join(', ')}</p>}
          <Link to="/welcome" state={RETURN_HERE} className="text-link">
            Edit your interests
          </Link>
        </div>
      </Sidebar>

      <main className="main" inert={menuOpen}>
        {loading && <Spinner label="Picking stories for you..." />}
        {showError && <Alert kind="error">Could not load your recommendations: {error}</Alert>}

        {data && !showError && (
          <section className={loading ? 'results is-loading' : 'results'} aria-busy={loading}>
            {data.usingFallback && (
              <p className="caption">Some of these are backup headlines while the public news feed recovers.</p>
            )}
            <h1 className="section-title">Recommended for you</h1>
            {data.articles.length === 0 ? (
              <Alert kind="warning">
                No stories matched your interests in this time window. Try a longer look-back, or{' '}
                <Link to="/welcome" state={RETURN_HERE} className="text-link">
                  add more interests
                </Link>
                .
              </Alert>
            ) : (
              <StoryCarousel
                key={data.hours}
                articles={data.articles}
                renderTag={(article) => <ReasonTag reason={article.reason} />}
              />
            )}
          </section>
        )}
      </main>
    </div>
  )
}
