import type { ReactNode } from 'react'

export function Spinner({ label }: { label: string }) {
  return (
    <p className="spinner" role="status">
      {label}
    </p>
  )
}

export function Alert({ kind, children }: { kind: 'warning' | 'error'; children: ReactNode }) {
  return (
    <div className={`alert alert-${kind}`} role={kind === 'error' ? 'alert' : 'status'}>
      {children}
    </div>
  )
}
