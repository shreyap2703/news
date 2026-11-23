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
  imageUrl?: string
}

export interface NewsResponse {
  category: Category
  hours: number
  articles: Article[]
  usingFallback: boolean
}

/** Which of the reader's interests a recommended story comes from. */
export interface RecommendationReason {
  kind: 'topic' | 'section' | 'city'
  /** The followed topic, the section's label, or the city. */
  label: string
  /** For sections, the section's id; empty for topics and the city. */
  sectionId: string
}

export interface RecommendedArticle extends Article {
  reason: RecommendationReason
}

export interface RecommendationsResponse {
  hours: number
  articles: RecommendedArticle[]
  usingFallback: boolean
}

export interface BriefingResponse {
  briefing: string
}

/** A question or answer in a conversation with Ask AI about an article. */
export interface ChatTurn {
  role: 'user' | 'assistant'
  content: string
}
