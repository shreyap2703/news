import { useState } from 'react'
import type { Article } from '../types.ts'

const dateFormatter = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

function formatPublished(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : dateFormatter.format(date)
}

export default function StoryCarousel({ articles }: { articles: Article[] }) {
  const [index, setIndex] = useState(0)
  const total = articles.length
  // Like the original app, fall back to the first story when the list shrinks below the current position.
  const current = index < total ? index : 0
  const article = articles[current]

  const step = (offset: number) => setIndex((previous) => ((previous < total ? previous : 0) + offset + total) % total)

  return (
    <div className="carousel">
      <article className="news-card story">
        <p className="news-meta">
          {article.source} · {article.language}
          {article.published && (
            <>
              {' · '}
              <time dateTime={article.published}>{formatPublished(article.published)}</time>
            </>
          )}
        </p>
        <h3 className="story-title">{article.title}</h3>
        <p className="story-context">{article.context}</p>
        {article.url && (
          <a className="story-link" href={article.url} target="_blank" rel="noopener noreferrer">
            Open the original article ↗
          </a>
        )}
      </article>

      <div className="carousel-nav">
        <button type="button" className="button" onClick={() => step(-1)}>
          ← Previous
        </button>
        <button type="button" className="button" onClick={() => step(1)}>
          Next →
        </button>
      </div>

      <p className="caption" aria-live="polite">
        Story {current + 1} of {total}
      </p>
    </div>
  )
}
