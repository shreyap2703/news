import { useEffect, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import { createBriefing, errorMessage } from '../api.ts'
import { Alert, Spinner } from './Status.tsx'

interface BriefingPanelProps {
  apiKey: string
  category: string
  hours: number
  limit: number
}

type BriefingState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; briefing: string }
  | { status: 'error'; message: string }

export default function BriefingPanel({ apiKey, category, hours, limit }: BriefingPanelProps) {
  const [state, setState] = useState<BriefingState>({ status: 'idle' })
  const controllerRef = useRef<AbortController | null>(null)

  useEffect(() => () => controllerRef.current?.abort(), [])

  async function generate() {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    setState({ status: 'loading' })
    try {
      const { briefing } = await createBriefing({ category, hours, limit, apiKey }, controller.signal)
      setState({ status: 'ready', briefing })
    } catch (error) {
      if (!controller.signal.aborted) setState({ status: 'error', message: errorMessage(error) })
    }
  }

  return (
    <section className="briefing" aria-label="AI briefing">
      <button type="button" className="button button-block" onClick={generate} disabled={state.status === 'loading'}>
        Generate AI briefing
      </button>
      {state.status === 'loading' && <Spinner label="Summarizing headlines..." />}
      {state.status === 'error' && <Alert kind="error">{state.message}</Alert>}
      {state.status === 'ready' && (
        <div className="briefing-output">
          <h2 className="section-title">Your AI briefing</h2>
          <div className="markdown">
            <Markdown>{state.briefing}</Markdown>
          </div>
        </div>
      )}
    </section>
  )
}
