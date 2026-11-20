import type { Json } from './database.types.ts'

/** What the welcome page asks, as saved in profiles.preferences. */
export interface Preferences {
  /** Section ids from /api/categories, in the order picked; the first is shown when the app opens. */
  sections: string[]
  followTopics: string[]
  city: string
  languages: string[]
  summaryLength: 'quick' | 'standard'
  mutedTopics: string[]
  theme: 'dark' | 'light' | 'system'
  hiddenSources: string[]
  readingTime: 'morning' | 'lunch' | 'evening' | 'night'
  dailyEmail: boolean
  emailTime: string
  emailDays: 'every-day' | 'weekdays' | 'weekends'
  breakingNews: 'email' | 'browser' | 'none'
  hideOpenedStories: boolean
}

export const DEFAULT_PREFERENCES: Preferences = {
  sections: [],
  followTopics: [],
  city: '',
  languages: ['English'],
  summaryLength: 'standard',
  mutedTopics: [],
  theme: 'dark',
  hiddenSources: [],
  readingTime: 'morning',
  dailyEmail: false,
  emailTime: '08:00',
  emailDays: 'every-day',
  breakingNews: 'none',
  hideOpenedStories: false,
}

export const SECTION_ICONS: Record<string, string> = {
  world: '🌍',
  india: '🇮🇳',
  ipl: '🏏',
  'ai-technology': '🤖',
  'business-economy': '💼',
  'science-space': '🚀',
  'politics-geopolitics': '🏛️',
}

// IPL is not offered here: the welcome page lists broad interests only.
export const HIDDEN_WELCOME_SECTIONS = new Set(['ipl'])

export const SUGGESTED_TOPICS = ['OpenAI', 'Stock markets', 'ISRO', 'Climate']

export const MUTE_OPTIONS = ['Celebrity gossip', 'Crime', 'Crypto', 'Elections', 'Live blogs', 'Opinion pieces']

export const SOURCE_OPTIONS = [
  'BBC News',
  'The Hindu',
  'Times of India',
  'NDTV',
  'Al Jazeera',
  'The Guardian',
  'Politico',
  'CNBC',
]

export const LANGUAGE_OPTIONS = [
  'English',
  'हिन्दी Hindi',
  'తెలుగు Telugu',
  'தமிழ் Tamil',
  'मराठी Marathi',
  'ಕನ್ನಡ Kannada',
  'العربية Arabic',
  'বাংলা Bengali',
  '中文 Chinese',
  'Nederlands Dutch',
  'Français French',
  'Deutsch German',
  'ગુજરાતી Gujarati',
  'Bahasa Indonesia Indonesian',
  'Italiano Italian',
  '日本語 Japanese',
  '한국어 Korean',
  'മലയാളം Malayalam',
  'ਪੰਜਾਬੀ Punjabi',
  'Polski Polish',
  'Português Portuguese',
  'Русский Russian',
  'Español Spanish',
  'Kiswahili Swahili',
  'Türkçe Turkish',
  'Українська Ukrainian',
  'اردو Urdu',
  'Tiếng Việt Vietnamese',
]

export const CITY_SUGGESTIONS = [
  'Hyderabad, Telangana',
  'Mumbai, Maharashtra',
  'Bengaluru, Karnataka',
  'Delhi',
  'Chennai, Tamil Nadu',
]

function strings(value: unknown, fallback: string[]): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : fallback
}

function oneOf<T extends string>(value: unknown, options: readonly T[], fallback: T): T {
  return options.find((option) => option === value) ?? fallback
}

/** Reads saved preferences, using the defaults for anything missing or unrecognised; null if none were saved. */
export function parsePreferences(value: Json | null | undefined): Preferences | null {
  if (value === null || value === undefined || typeof value !== 'object' || Array.isArray(value)) return null
  const d = DEFAULT_PREFERENCES
  return {
    sections: strings(value.sections, d.sections),
    followTopics: strings(value.followTopics, d.followTopics),
    city: typeof value.city === 'string' ? value.city : d.city,
    languages: strings(value.languages, d.languages),
    summaryLength: oneOf(value.summaryLength, ['quick', 'standard'], d.summaryLength),
    mutedTopics: strings(value.mutedTopics, d.mutedTopics),
    theme: oneOf(value.theme, ['dark', 'light', 'system'], d.theme),
    hiddenSources: strings(value.hiddenSources, d.hiddenSources),
    readingTime: oneOf(value.readingTime, ['morning', 'lunch', 'evening', 'night'], d.readingTime),
    dailyEmail: typeof value.dailyEmail === 'boolean' ? value.dailyEmail : d.dailyEmail,
    emailTime: typeof value.emailTime === 'string' && /^\d\d:\d\d$/.test(value.emailTime) ? value.emailTime : d.emailTime,
    emailDays: oneOf(value.emailDays, ['every-day', 'weekdays', 'weekends'], d.emailDays),
    breakingNews: oneOf(value.breakingNews, ['email', 'browser', 'none'], d.breakingNews),
    hideOpenedStories: typeof value.hideOpenedStories === 'boolean' ? value.hideOpenedStories : d.hideOpenedStories,
  }
}

/** Puts the user's chosen sections first, in the order they picked them. */
export function orderSections<T extends { id: string }>(categories: T[], sections: string[]): T[] {
  const rank = (id: string) => {
    const index = sections.indexOf(id)
    return index < 0 ? sections.length : index
  }
  return [...categories].sort((a, b) => rank(a.id) - rank(b.id))
}
