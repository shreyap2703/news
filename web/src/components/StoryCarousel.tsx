import { useEffect, useId, useRef, useState } from 'react'
import { fetchStorySummary } from '../api.ts'
import type { Article } from '../types.ts'
import { AskAiButton, AskAiPanel } from './AskAi.tsx'
import { Spinner } from './Status.tsx'

const dateFormatter = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

// Shared by every carousel, so returning to a section reuses the summaries that were already built.
const summaryLookups = new Map<string, Promise<Article | null>>()

function lookUpSummary(url: string): Promise<Article | null> {
  let lookup = summaryLookups.get(url)
  if (!lookup) {
    lookup = fetchStorySummary(url).then(
      (story) => {
        // Only summaries with text are kept: when a story's pages could not be read, the next visit asks again.
        if (!story.context) summaryLookups.delete(url)
        return story
      },
      () => {
        summaryLookups.delete(url)
        return null
      },
    )
    summaryLookups.set(url, lookup)
  }
  return lookup
}

function formatPublished(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : dateFormatter.format(date)
}

export default function StoryCarousel({ articles }: { articles: Article[] }) {
  const [index, setIndex] = useState(0)
  // Story URL -> the story with its combined summary, or null when none could be built.
  const [summaries, setSummaries] = useState<Partial<Record<string, Article | null>>>({})
  // Image URLs that failed to load, so the card drops the empty picture frame instead of showing a broken image.
  const [brokenImages, setBrokenImages] = useState<ReadonlySet<string>>(() => new Set())
  // The story whose Ask AI conversation is open, if any.
  const [chatUrl, setChatUrl] = useState<string | null>(null)
  const chatPanelId = useId()
  const askButtonRef = useRef<HTMLButtonElement>(null)
  const total = articles.length
  useEffect(() => {
    setIndex(0)
  }, [articles])

  const current = index < total ? index : 0
  const article = articles[current]
  const nextArticle = total > 1 ? articles[(current + 1) % total] : undefined

  // Summarize the open story, and the next one so that it is ready when the reader moves on.
  useEffect(() => {
    for (const story of [article, nextArticle]) {
      if (!story?.url) continue
      lookUpSummary(story.url).then((summary) => {
        setSummaries((previous) => (previous[story.url] === summary ? previous : { ...previous, [story.url]: summary }))
      })
    }
  }, [article, nextArticle])

  if (!article) return null

  const step = (offset: number) => {
    setChatUrl(null)
    setIndex((previous) => ((previous < total ? previous : 0) + offset + total) % total)
  }
  const chatOpen = chatUrl === article.url
  const summary = summaries[article.url]
  const shown = summary ?? article
  const summarizing = article.url !== '' && summary === undefined
  const imageUrl = shown.imageUrl && !brokenImages.has(shown.imageUrl) ? shown.imageUrl : ''
  // While the summary loads, a placeholder holds the picture's place so the layout does not jump when it arrives.
  const hasMedia = imageUrl !== '' || summarizing

  return (
    <div className="carousel">
      <div className="carousel-nav">
        <button type="button" className="button button-ghost carousel-nav-button" onClick={() => step(-1)}>
          ← Previous
        </button>
        <p className="carousel-count" aria-live="polite">
          Story {current + 1} of {total}
        </p>
        <button type="button" className="button carousel-nav-button" onClick={() => step(1)}>
          Next →
        </button>
      </div>

      {/* Keyed by story so each one gets a fresh card and its entrance animation. */}
      <article key={article.url || current} className={hasMedia ? 'news-card story has-media' : 'news-card story'}>
        <p className="news-meta">
          <span className="news-source">{article.source}</span>
          {article.language && <span className="news-lang">{article.language}</span>}
          {article.published && <time dateTime={article.published}>{formatPublished(article.published)}</time>}
        </p>
        <h3 className="story-title">{article.title}</h3>
        {imageUrl ? (
          <img
            className="story-image"
            src={imageUrl}
            alt={article.title}
            loading="lazy"
            onError={() => setBrokenImages((previous) => new Set(previous).add(imageUrl))}
          />
        ) : (
          summarizing && <div className="story-image story-image-placeholder" aria-hidden="true" />
        )}
        {summarizing ? (
          <Spinner label="Reading this story's coverage from several outlets…" />
        ) : (
          shown.context && <p className="story-context">{shown.context}</p>
        )}
        {article.url && (
          <div className="story-actions">
            <a className="story-link" href={article.url} target="_blank" rel="noopener noreferrer">
              Open the original article <span aria-hidden="true">↗</span>
            </a>
            <AskAiButton
              ref={askButtonRef}
              expanded={chatOpen}
              panelId={chatPanelId}
              onToggle={() => setChatUrl(chatOpen ? null : article.url)}
            />
          </div>
        )}
        {chatOpen && (
          <AskAiPanel
            id={chatPanelId}
            article={article}
            onClose={() => {
              setChatUrl(null)
              askButtonRef.current?.focus()
            }}
          />
        )}
      </article>
    </div>
  )
}
