import type { User } from '@supabase/supabase-js'
import { useEffect, useState, type KeyboardEvent, type ReactNode } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router'
import { errorMessage, fetchCategories } from '../api.ts'
import { displayName, useAuth } from '../auth.ts'
import type { Json } from '../database.types.ts'
import { loadFilters, saveFilters } from '../filters.ts'
import {
  CITY_SUGGESTIONS,
  DEFAULT_PREFERENCES,
  HIDDEN_WELCOME_SECTIONS,
  LANGUAGE_OPTIONS,
  MUTE_OPTIONS,
  SECTION_ICONS,
  SOURCE_OPTIONS,
  SUGGESTED_TOPICS,
  parsePreferences,
  type Preferences,
} from '../preferences.ts'
import { Alert, Spinner } from '../components/Status.tsx'
import { savePreferences } from '../supabase.ts'
import type { Category } from '../types.ts'

const STEPS = ['Interests', 'Reading style', 'Updates'] as const

type SaveState = { status: 'idle' } | { status: 'saving' } | { status: 'error'; message: string }

function toggle(list: string[], item: string): string[] {
  return list.includes(item) ? list.filter((value) => value !== item) : [...list, item]
}

function Chip({ pressed, onClick, children }: { pressed: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" className="pref-chip" aria-pressed={pressed} onClick={onClick}>
      {children}
    </button>
  )
}

function Tile({ pressed, onClick, title, text }: { pressed: boolean; onClick: () => void; title: string; text: string }) {
  return (
    <button type="button" className="pref-tile" aria-pressed={pressed} onClick={onClick}>
      <strong>{title}</strong>
      <span>{text}</span>
    </button>
  )
}

function Switch({ checked, onChange, label }: { checked: boolean; onChange: (checked: boolean) => void; label: string }) {
  return (
    <label className="pref-switch">
      <input type="checkbox" role="switch" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span aria-hidden="true" />
      <span className="visually-hidden">{label}</span>
    </label>
  )
}

function Group({ title, hint, children }: { title: ReactNode; hint?: string; children: ReactNode }) {
  return (
    <div className="pref-group">
      <h3>{title}</h3>
      {hint && <p className="pref-hint">{hint}</p>}
      {children}
    </div>
  )
}

function PreferencesForm({ user, initial, firstVisit }: { user: User; initial: Preferences; firstVisit: boolean }) {
  const { profile, onProfileSaved } = useAuth()
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [prefs, setPrefs] = useState(initial)
  const [topicDraft, setTopicDraft] = useState('')
  const [categories, setCategories] = useState<Category[]>([])
  const [categoriesError, setCategoriesError] = useState<string | null>(null)
  const [save, setSave] = useState<SaveState>({ status: 'idle' })

  useEffect(() => {
    const controller = new AbortController()
    fetchCategories(controller.signal)
      .then((items) => {
        const offered = items.filter((item) => !HIDDEN_WELCOME_SECTIONS.has(item.id))
        setCategories(offered)
        // New users start with the first section picked, so Continue works straight away.
        if (firstVisit) setPrefs((current) => (current.sections.length ? current : { ...current, sections: [offered[0]?.id ?? ''].filter(Boolean) }))
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setCategoriesError(errorMessage(error))
      })
    return () => controller.abort()
  }, [firstVisit])

  const update = (changes: Partial<Preferences>) => setPrefs((current) => ({ ...current, ...changes }))

  async function finish(chosen: Preferences) {
    setSave({ status: 'saving' })
    try {
      const sections = chosen.sections.filter((id) => categories.some((category) => category.id === id))
      onProfileSaved(await savePreferences(user.id, { ...chosen, sections } as unknown as Json))
      // Open the headlines on the first section picked.
      if (sections[0]) saveFilters({ ...loadFilters(), category: sections[0] })
      navigate('/', { replace: true })
    } catch (error) {
      setSave({ status: 'error', message: errorMessage(error) })
    }
  }

  function addTopic(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key !== 'Enter') return
    event.preventDefault()
    const topic = topicDraft.trim()
    if (topic && !prefs.followTopics.some((item) => item.toLowerCase() === topic.toLowerCase())) {
      update({ followTopics: [...prefs.followTopics, topic] })
    }
    setTopicDraft('')
  }

  const name = displayName(user, profile).split(' ')[0]
  const sectionLabels = prefs.sections
    .map((id) => categories.find((category) => category.id === id)?.label)
    .filter(Boolean)
  const topicChoices = [...SUGGESTED_TOPICS, ...prefs.followTopics.filter((topic) => !SUGGESTED_TOPICS.includes(topic))]
  const remainingLanguages = LANGUAGE_OPTIONS.filter((language) => !prefs.languages.includes(language))
  const saving = save.status === 'saving'
  const canContinue = step !== 0 || prefs.sections.length > 0

  return (
    <>
      <div className="pref-welcome">
        <h1 className="page-title">{firstVisit ? `Welcome, ${name}! Let's set up your briefing.` : 'Your preferences'}</h1>
        <p className="caption">
          {firstVisit
            ? 'Three quick steps so your headlines start with what you care about. You can change any of this later from your profile.'
            : 'Change what your briefing shows. Your changes are saved when you finish.'}
        </p>
      </div>

      <div className="pref-progress" aria-hidden="true">
        {STEPS.map((label, index) => (
          <span key={label} className={index <= step ? 'done' : undefined} />
        ))}
      </div>
      <p className="pref-step-label">
        Step {step + 1} of {STEPS.length} · {STEPS[step]}
      </p>

      <section className="pref-card" key={step}>
        {step === 0 && (
          <>
            <h2>What do you want to read about?</h2>
            <p className="pref-hint">Pick at least one. Your first pick becomes the section you see when you open the app.</p>
            {categoriesError && <Alert kind="error">Could not load the news sections: {categoriesError}</Alert>}
            {!categoriesError && categories.length === 0 && <Spinner label="Loading sections..." />}
            <div className="pref-chips">
              {categories.map((category) => (
                <Chip
                  key={category.id}
                  pressed={prefs.sections.includes(category.id)}
                  onClick={() => update({ sections: toggle(prefs.sections, category.id) })}
                >
                  {SECTION_ICONS[category.id] && <span aria-hidden="true">{SECTION_ICONS[category.id]}</span>}
                  {category.label}
                </Chip>
              ))}
            </div>

            <Group title="Anything specific to follow?" hint="Teams, companies, people or topics. Stories that mention them are shown first.">
              <div className="pref-chips">
                {topicChoices.map((topic) => (
                  <Chip
                    key={topic}
                    pressed={prefs.followTopics.includes(topic)}
                    onClick={() => update({ followTopics: toggle(prefs.followTopics, topic) })}
                  >
                    {topic}
                  </Chip>
                ))}
              </div>
              <label className="field pref-field">
                <span className="visually-hidden">Add a topic to follow</span>
                <input
                  type="text"
                  value={topicDraft}
                  maxLength={60}
                  onChange={(event) => setTopicDraft(event.target.value)}
                  onKeyDown={addTopic}
                  placeholder="Add your own, e.g. Electric vehicles, then press Enter"
                />
              </label>
            </Group>

            <Group
              title={
                <>
                  Your city or state <span className="pref-optional">(optional)</span>
                </>
              }
              hint='Adds a "Near you" section with local news. We only use it to pick stories.'
            >
              <label className="field pref-field">
                <span className="visually-hidden">City or state</span>
                <input
                  type="text"
                  list="pref-cities"
                  value={prefs.city}
                  maxLength={80}
                  onChange={(event) => update({ city: event.target.value })}
                  placeholder="Start typing a city or state"
                />
              </label>
              <datalist id="pref-cities">
                {CITY_SUGGESTIONS.map((city) => (
                  <option key={city} value={city} />
                ))}
              </datalist>
            </Group>

            <Group
              title="Which language(s) do you read?"
              hint="Choose from the list; you can add more than one. Stories in these languages come from regional publishers."
            >
              <label className="field pref-field">
                <span className="field-label">Add a language</span>
                <select
                  value=""
                  onChange={(event) => event.target.value && update({ languages: [...prefs.languages, event.target.value] })}
                >
                  <option value="">Choose a language…</option>
                  {remainingLanguages.map((language) => (
                    <option key={language}>{language}</option>
                  ))}
                </select>
              </label>
              {prefs.languages.length > 0 && (
                <div className="pref-chips pref-tags">
                  {prefs.languages.map((language) => (
                    <Chip key={language} pressed onClick={() => update({ languages: toggle(prefs.languages, language) })}>
                      {language} <span aria-label="remove">✕</span>
                    </Chip>
                  ))}
                </div>
              )}
            </Group>
          </>
        )}

        {step === 1 && (
          <>
            <h2>How do you like to read?</h2>
            <p className="pref-hint">These become your defaults on the headlines page.</p>
            <Group title="Summary length">
              <div className="pref-tiles">
                <Tile
                  title="⚡ Quick"
                  text="About 50 words: the key facts in two or three sentences."
                  pressed={prefs.summaryLength === 'quick'}
                  onClick={() => update({ summaryLength: 'quick' })}
                />
                <Tile
                  title="📰 Standard"
                  text="About 100–120 words, combining several outlets' reports."
                  pressed={prefs.summaryLength === 'standard'}
                  onClick={() => update({ summaryLength: 'standard' })}
                />
              </div>
            </Group>

            <Group title="Anything you'd rather not see?" hint="Stories mainly about these topics are left out of your briefing.">
              <div className="pref-chips">
                {MUTE_OPTIONS.map((topic) => (
                  <Chip
                    key={topic}
                    pressed={prefs.mutedTopics.includes(topic)}
                    onClick={() => update({ mutedTopics: toggle(prefs.mutedTopics, topic) })}
                  >
                    {topic}
                  </Chip>
                ))}
              </div>
            </Group>

            <Group title="Theme">
              <div className="pref-tiles">
                <Tile title="🌙 Dark" text="Easy on the eyes at night." pressed={prefs.theme === 'dark'} onClick={() => update({ theme: 'dark' })} />
                <Tile title="☀️ Light" text="Classic newspaper look." pressed={prefs.theme === 'light'} onClick={() => update({ theme: 'light' })} />
                <Tile
                  title="💻 Match my device"
                  text="Switches with your phone or computer setting."
                  pressed={prefs.theme === 'system'}
                  onClick={() => update({ theme: 'system' })}
                />
              </div>
            </Group>

            <Group title="Sources" hint="Turn off publishers you don't want to see.">
              <div className="pref-chips">
                {SOURCE_OPTIONS.map((source) => (
                  <Chip
                    key={source}
                    pressed={!prefs.hiddenSources.includes(source)}
                    onClick={() => update({ hiddenSources: toggle(prefs.hiddenSources, source) })}
                  >
                    {source}
                  </Chip>
                ))}
              </div>
            </Group>
          </>
        )}

        {step === 2 && (
          <>
            <h2>Want us to keep you posted?</h2>
            <p className="pref-hint">All optional, and off unless you turn them on.</p>
            <Group title="When do you usually read?" hint="Your briefing email is sent just before then.">
              <div className="pref-chips">
                {(
                  [
                    ['morning', '🌅 Morning'],
                    ['lunch', '🍱 Lunch'],
                    ['evening', '🌆 Evening'],
                    ['night', '🌙 Late night'],
                  ] as const
                ).map(([value, label]) => (
                  <Chip key={value} pressed={prefs.readingTime === value} onClick={() => update({ readingTime: value })}>
                    {label}
                  </Chip>
                ))}
              </div>
            </Group>

            <div className="pref-toggle">
              <div>
                <strong>Daily briefing email</strong>
                <span>Your top stories, before you usually read.</span>
              </div>
              <Switch checked={prefs.dailyEmail} onChange={(dailyEmail) => update({ dailyEmail })} label="Daily briefing email" />
            </div>
            {prefs.dailyEmail && (
              <div className="pref-row">
                <label className="field">
                  <span className="field-label">Send it at</span>
                  <input type="time" value={prefs.emailTime} onChange={(event) => update({ emailTime: event.target.value || '08:00' })} />
                </label>
                <label className="field">
                  <span className="field-label">On</span>
                  <select value={prefs.emailDays} onChange={(event) => update({ emailDays: event.target.value as Preferences['emailDays'] })}>
                    <option value="every-day">Every day</option>
                    <option value="weekdays">Weekdays only</option>
                    <option value="weekends">Weekends only</option>
                  </select>
                </label>
              </div>
            )}

            <Group title="How should breaking news reach you?" hint="Only for major stories in the sections you picked.">
              <div className="pref-chips">
                {(
                  [
                    ['email', '📧 Email'],
                    ['browser', '🔔 Browser notification'],
                    ['none', "🔕 Don't notify me"],
                  ] as const
                ).map(([value, label]) => (
                  <Chip key={value} pressed={prefs.breakingNews === value} onClick={() => update({ breakingNews: value })}>
                    {label}
                  </Chip>
                ))}
              </div>
            </Group>

            <div className="pref-toggle">
              <div>
                <strong>Hide stories I've already opened</strong>
                <span>Keeps the carousel fresh when you come back.</span>
              </div>
              <Switch
                checked={prefs.hideOpenedStories}
                onChange={(hideOpenedStories) => update({ hideOpenedStories })}
                label="Hide stories I've already opened"
              />
            </div>

            <p className="pref-preview">
              ✨ Your briefing: <strong>{sectionLabels.join(', ') || 'Top World News'}</strong>
              {prefs.city.trim() && ` · Near you: ${prefs.city.trim()}`}
              {prefs.languages.length > 0 && ` · ${prefs.languages.map((language) => language.split(' ').pop()).join(' & ')}`}
              {` · ${prefs.summaryLength === 'quick' ? 'Quick' : 'Standard'} summaries`}
              {` · ${{ dark: 'Dark', light: 'Light', system: 'Device' }[prefs.theme]} theme`}
              {prefs.dailyEmail && ` · email at ${prefs.emailTime}`}
            </p>
          </>
        )}
      </section>

      {save.status === 'error' && <Alert kind="error">Could not save your preferences: {save.message}</Alert>}

      <div className="pref-actions">
        {firstVisit ? (
          <button type="button" className="pref-skip" disabled={saving} onClick={() => finish(DEFAULT_PREFERENCES)}>
            Skip for now
          </button>
        ) : (
          <button type="button" className="pref-skip" disabled={saving} onClick={() => navigate('/profile')}>
            Cancel
          </button>
        )}
        <div className="pref-buttons">
          {step > 0 && (
            <button type="button" className="button button-ghost" disabled={saving} onClick={() => setStep(step - 1)}>
              ← Back
            </button>
          )}
          <button
            type="button"
            className="button"
            disabled={saving || !canContinue}
            onClick={() => (step < STEPS.length - 1 ? setStep(step + 1) : finish(prefs))}
          >
            {saving ? 'Saving...' : step < STEPS.length - 1 ? 'Continue →' : firstVisit ? 'Start reading →' : 'Save preferences'}
          </button>
        </div>
      </div>
    </>
  )
}

/** The preferences page: shown right after sign-up, and from the profile page afterwards. */
export default function WelcomePage() {
  const { loading, user, profile, reloadProfile } = useAuth()
  const location = useLocation()

  if (!loading && !user) return <Navigate to="/login" replace state={{ from: location.pathname }} />

  const saved = profile.status === 'ready' ? parsePreferences(profile.profile?.preferences) : null

  return (
    <main className="page">
      <div className="pref-page">
        {!user || profile.status === 'loading' ? (
          <Spinner label="Loading your preferences..." />
        ) : profile.status === 'error' ? (
          <>
            <Alert kind="error">Could not load your preferences: {profile.message}</Alert>
            <button type="button" className="button" onClick={reloadProfile}>
              Try again
            </button>
          </>
        ) : (
          <PreferencesForm user={user} initial={saved ?? DEFAULT_PREFERENCES} firstVisit={saved === null} />
        )}
      </div>
    </main>
  )
}
