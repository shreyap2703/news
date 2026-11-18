import type { Article, BriefingResponse, Category, ChatTurn, NewsResponse } from './types.ts'

export interface NewsQuery {
  category: string
  hours: number
  limit: number
  search?: string
  /** Ask the API to clear its 10-minute cache before fetching. */
  refresh?: boolean
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json()
    if (body !== null && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string') {
      return body.detail
    }
  } catch {
    // Non-JSON error bodies (for example from a proxy) fall through to the generic message.
  }
  const status = `${response.status} ${response.statusText}`.trim()
  if (response.status >= 502 && response.status <= 504) {
    return `The news API is unavailable (${status}). Make sure the backend server is running.`
  }
  return `The news API responded with ${status}.`
}

async function send(path: string, init: RequestInit = {}): Promise<Response> {
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      headers: { Accept: 'application/json', ...(init.body ? { 'Content-Type': 'application/json' } : {}) },
    })
  } catch (error) {
    if (init.signal?.aborted) throw error
    throw new Error('Could not reach the news API. Make sure the backend server is running.', { cause: error })
  }
  if (!response.ok) {
    throw new Error(await readErrorDetail(response))
  }
  return response
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await send(path, init)
  return (await response.json()) as T
}

export function fetchCategories(signal?: AbortSignal): Promise<Category[]> {
  return request<Category[]>('/api/categories', { signal })
}

export function fetchNews({ category, hours, limit, search, refresh = false }: NewsQuery, signal?: AbortSignal): Promise<NewsResponse> {
  const params = new URLSearchParams({ category, hours: String(hours), limit: String(limit) })
  if (search && search.trim()) params.set('q', search.trim())
  if (refresh) params.set('refresh', 'true')
  return request<NewsResponse>(`/api/news?${params}`, { signal })
}

/** Returns the story with a short summary built from several outlets' coverage of it. */
export function fetchStorySummary(url: string, signal?: AbortSignal): Promise<Article> {
  return request<Article>(`/api/news/summary?${new URLSearchParams({ url })}`, { signal })
}

export function createBriefing(
  { category, hours, limit, apiKey }: Omit<NewsQuery, 'refresh'> & { apiKey: string },
  signal?: AbortSignal,
): Promise<BriefingResponse> {
  return request<BriefingResponse>('/api/briefing', {
    method: 'POST',
    body: JSON.stringify({ category, hours, limit, apiKey }),
    signal,
  })
}

export interface ArticleQuestion {
  /** The article's `url` from a recent /api/news response. */
  url: string
  question: string
  /** Earlier questions and answers about the article, oldest first. */
  history: ChatTurn[]
}

/**
 * Asks Ask AI a question about an article. The answer streams in: `onText` receives the answer so far each time more
 * of it arrives, and the promise resolves to the whole answer.
 */
export async function askAboutArticle(
  { url, question, history }: ArticleQuestion,
  onText: (answer: string) => void,
  signal?: AbortSignal,
): Promise<string> {
  const response = await send('/api/news/ask', {
    method: 'POST',
    body: JSON.stringify({ url, question, history }),
    signal,
  })
  let answer = ''
  try {
    if (!response.body) {
      answer = await response.text()
      onText(answer)
      return answer
    }
    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
    for (;;) {
      const { done, value } = await reader.read()
      if (done) return answer
      answer += value
      onText(answer)
    }
  } catch (error) {
    if (signal?.aborted) throw error
    throw new Error('The connection to the news API was lost while the answer was arriving. Please ask again.', {
      cause: error,
    })
  }
}
