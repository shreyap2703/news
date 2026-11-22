import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent, type Ref } from 'react'
import Markdown from 'react-markdown'
import { askAboutArticle, errorMessage } from '../api.ts'
import type { Article, ChatTurn } from '../types.ts'

const SUGGESTED_QUESTIONS = ['Summarize this article in three points', 'What are the key facts?', 'Why does this story matter?']
// The API accepts questions of up to 1,000 characters.
const MAX_QUESTION_LENGTH = 1000
// Earlier questions and answers sent with each question, so that follow-up questions make sense.
const HISTORY_MESSAGES = 8
// New text keeps the conversation scrolled to the bottom only while the reader is this close to it (in pixels).
const STICK_TO_BOTTOM_PX = 48

interface ChatMessage extends ChatTurn {
  /** For answers: still arriving, stopped by the reader, or failed (the content is then the error message). */
  status?: 'answering' | 'stopped' | 'failed'
}

// Story URL -> its conversation, so closing Ask AI or moving to another story does not lose it.
const conversations = new Map<string, ChatMessage[]>()

/** The answered questions so far, as the API expects them. */
function historyFor(messages: ChatMessage[]): ChatTurn[] {
  const turns: ChatTurn[] = []
  messages.forEach((message, index) => {
    const question = messages[index - 1]
    if (message.role === 'assistant' && message.status !== 'failed' && message.content && question?.role === 'user') {
      turns.push({ role: 'user', content: question.content }, { role: 'assistant', content: message.content })
    }
  })
  return turns.slice(-HISTORY_MESSAGES)
}

function SparkleIcon() {
  return (
    <svg className="ask-ai-icon" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">
      <path
        fill="currentColor"
        d="M10 2.5c.7 4.6 2.9 6.8 7.5 7.5-4.6.7-6.8 2.9-7.5 7.5-.7-4.6-2.9-6.8-7.5-7.5 4.6-.7 6.8-2.9 7.5-7.5Z"
      />
      <path
        fill="currentColor"
        opacity="0.75"
        d="M18.5 13.5c.35 2.1 1.4 3.15 3.5 3.5-2.1.35-3.15 1.4-3.5 3.5-.35-2.1-1.4-3.15-3.5-3.5 2.1-.35 3.15-1.4 3.5-3.5Z"
      />
      <path fill="currentColor" opacity="0.6" d="M19 2c.2 1.2.8 1.8 2 2-1.2.2-1.8.8-2 2-.2-1.2-.8-1.8-2-2 1.2-.2 1.8-.8 2-2Z" />
    </svg>
  )
}

interface AskAiButtonProps {
  expanded: boolean
  /** The id of the conversation panel that the button opens. */
  panelId: string
  onToggle: () => void
  ref?: Ref<HTMLButtonElement>
}

/** The Ask AI button, with a tooltip beside it that explains it on hover or keyboard focus. */
export function AskAiButton({ expanded, panelId, onToggle, ref }: AskAiButtonProps) {
  const tooltipId = useId()
  return (
    <span className="ask-ai">
      <button
        ref={ref}
        type="button"
        className="ask-ai-button"
        aria-expanded={expanded}
        aria-controls={expanded ? panelId : undefined}
        aria-describedby={tooltipId}
        onClick={onToggle}
      >
        <SparkleIcon />
        Ask AI
      </button>
      <span role="tooltip" id={tooltipId} className="ask-ai-tooltip">
        Ask any question related to this article
      </span>
    </span>
  )
}

function ChatBubble({ message }: { message: ChatMessage }) {
  if (message.role === 'user') {
    return (
      <div className="ask-ai-message ask-ai-question">
        <span className="ask-ai-sr">You asked: </span>
        {message.content}
      </div>
    )
  }
  if (message.status === 'failed') {
    return <div className="ask-ai-message ask-ai-error">{message.content}</div>
  }
  if (message.status === 'answering' && !message.content) {
    return (
      <div className="ask-ai-message ask-ai-answer ask-ai-thinking">
        <span className="ask-ai-dots" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
        Reading the article…
      </div>
    )
  }
  return (
    <div className="ask-ai-message ask-ai-answer">
      <span className="ask-ai-sr">Ask AI answered: </span>
      {message.content && (
        <div className="markdown">
          {/* Links and images are dropped: text in an article could lead the model to add misleading ones. */}
          <Markdown disallowedElements={['a', 'img']} unwrapDisallowed>
            {message.content}
          </Markdown>
        </div>
      )}
      {message.status === 'stopped' && (
        <p className="ask-ai-stopped">{message.content ? 'Stopped' : 'You stopped this answer.'}</p>
      )}
    </div>
  )
}

interface AskAiPanelProps {
  id: string
  article: Article
  onClose: () => void
}

/** The conversation with Ask AI about one article. Answers appear as the model writes them. */
export function AskAiPanel({ id, article, onClose }: AskAiPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>(() => conversations.get(article.url) ?? [])
  const [draft, setDraft] = useState('')
  const headingId = useId()
  const panelRef = useRef<HTMLElement>(null)
  const logRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  // Set while an answer is arriving, so a second question cannot start until it is done or stopped.
  const controllerRef = useRef<AbortController | null>(null)
  const stickToBottomRef = useRef(true)
  const answering = messages.at(-1)?.status === 'answering'

  useEffect(() => {
    panelRef.current?.scrollIntoView({ block: 'nearest' })
    inputRef.current?.focus({ preventScroll: true })
    return () => controllerRef.current?.abort()
  }, [])

  useEffect(() => {
    const log = logRef.current
    if (log && stickToBottomRef.current) log.scrollTop = log.scrollHeight
  }, [messages])

  useEffect(() => {
    if (!answering) conversations.set(article.url, messages)
  }, [answering, article.url, messages])

  async function ask(question: string) {
    const text = question.trim()
    if (!text || controllerRef.current) return
    const history = historyFor(messages)
    const controller = new AbortController()
    controllerRef.current = controller
    stickToBottomRef.current = true
    setDraft('')
    setMessages((previous) => [
      ...previous,
      { role: 'user', content: text },
      { role: 'assistant', content: '', status: 'answering' },
    ])
    // From here on only the answer, the last message, changes.
    const updateAnswer = (changes: Partial<ChatMessage>) =>
      setMessages((previous) => [...previous.slice(0, -1), { ...previous[previous.length - 1], ...changes }])
    try {
      const answer = await askAboutArticle(
        { url: article.url, question: text, history },
        (soFar) => updateAnswer({ content: soFar }),
        controller.signal,
      )
      updateAnswer({ content: answer, status: undefined })
    } catch (error) {
      updateAnswer(controller.signal.aborted ? { status: 'stopped' } : { content: errorMessage(error), status: 'failed' })
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void ask(draft)
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter asks the question; Shift+Enter starts a new line.
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      void ask(draft)
    }
  }

  return (
    <section
      id={id}
      ref={panelRef}
      className="ask-ai-panel"
      aria-labelledby={headingId}
      onKeyDown={(event) => {
        if (event.key === 'Escape') onClose()
      }}
    >
      <header className="ask-ai-header">
        <h4 id={headingId} className="ask-ai-title">
          <SparkleIcon />
          Ask AI about this article
        </h4>
        <button type="button" className="ask-ai-close" aria-label="Close Ask AI" onClick={onClose}>
          <span aria-hidden="true">×</span>
        </button>
      </header>

      <div
        ref={logRef}
        className="ask-ai-log"
        role="log"
        aria-label="Conversation with Ask AI"
        aria-busy={answering}
        onScroll={(event) => {
          const log = event.currentTarget
          stickToBottomRef.current = log.scrollHeight - log.scrollTop - log.clientHeight < STICK_TO_BOTTOM_PX
        }}
      >
        {messages.length === 0 ? (
          <div className="ask-ai-empty">
            <p>Ask anything about this story. Answers come from the article's own text.</p>
            <div className="ask-ai-suggestions">
              {SUGGESTED_QUESTIONS.map((question) => (
                <button key={question} type="button" className="ask-ai-suggestion" onClick={() => void ask(question)}>
                  {question}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((message, index) => <ChatBubble key={index} message={message} />)
        )}
      </div>

      <form className="ask-ai-form" onSubmit={handleSubmit}>
        <textarea
          ref={inputRef}
          className="ask-ai-input"
          rows={1}
          maxLength={MAX_QUESTION_LENGTH}
          placeholder="Ask a question about this article…"
          aria-label="Your question about this article"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleKeyDown}
        />
        {answering ? (
          <button type="button" className="button button-small ask-ai-send" onClick={() => controllerRef.current?.abort()}>
            Stop
          </button>
        ) : (
          <button type="submit" className="button button-small ask-ai-send" disabled={!draft.trim()}>
            Ask
          </button>
        )}
      </form>
    </section>
  )
}
