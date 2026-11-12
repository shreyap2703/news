export interface Category {
  id: string
  label: string
}

export interface Article {
  title: string
  source: string
  /** ISO 8601 UTC timestamp when the feed provides a parseable date. */
  published: string
  url: string
  language: string
  context: string
}

export interface NewsResponse {
  category: Category
  hours: number
  articles: Article[]
  usingFallback: boolean
}

export interface BriefingResponse {
  briefing: string
}
