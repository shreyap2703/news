import type { BriefingResponse, Category, NewsResponse } from './types.ts'

export interface NewsQuery {
  category: string
  hours: number
  limit: number
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

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
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
  return (await response.json()) as T
}

export function fetchCategories(signal?: AbortSignal): Promise<Category[]> {
  return request<Category[]>('/api/categories', { signal })
}

export function fetchNews({ category, hours, limit, refresh = false }: NewsQuery, signal?: AbortSignal): Promise<NewsResponse> {
  const params = new URLSearchParams({ category, hours: String(hours), limit: String(limit) })
  if (refresh) params.set('refresh', 'true')
  return request<NewsResponse>(`/api/news?${params}`, { signal })
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
