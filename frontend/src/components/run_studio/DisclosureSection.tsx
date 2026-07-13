import React, { useEffect, useId, useRef, useState } from 'react'

type Props = {
  title: string
  summary?: string
  badge?: number | string | null
  defaultOpen?: boolean
  persistKey?: string
  tone?: 'neutral' | 'attention' | 'ok'
  actions?: React.ReactNode
  children: React.ReactNode
}

function readStored(key: string, fallback: boolean): boolean {
  if (!key || typeof window === 'undefined') return fallback
  try {
    const raw = window.localStorage.getItem(`goc:disclosure:${key}`)
    if (raw === 'open') return true
    if (raw === 'closed') return false
  } catch {}
  return fallback
}

export default function DisclosureSection({
  title,
  summary = '',
  badge = null,
  defaultOpen = false,
  persistKey = '',
  tone = 'neutral',
  actions = null,
  children,
}: Props) {
  const contentId = useId()
  const [open, setOpen] = useState(() => readStored(persistKey, defaultOpen))
  const previousKey = useRef(persistKey)
  const skipNextWrite = useRef(false)

  useEffect(() => {
    if (previousKey.current === persistKey) return
    previousKey.current = persistKey
    skipNextWrite.current = true
    setOpen(readStored(persistKey, defaultOpen))
  }, [persistKey, defaultOpen])

  useEffect(() => {
    if (skipNextWrite.current) {
      skipNextWrite.current = false
      return
    }
    if (!persistKey || typeof window === 'undefined') return
    try {
      window.localStorage.setItem(`goc:disclosure:${persistKey}`, open ? 'open' : 'closed')
    } catch {}
  }, [open, persistKey])

  return (
    <section className={`roomDisclosure roomDisclosure--${tone} ${open ? 'isOpen' : ''}`}>
      <div className="roomDisclosureHeader">
        <button
          type="button"
          className="roomDisclosureToggle"
          aria-expanded={open}
          aria-controls={contentId}
          onClick={() => setOpen((value) => !value)}
        >
          <span className="roomDisclosureChevron" aria-hidden="true">›</span>
          <span className="roomDisclosureText">
            <b>{title}</b>
            {summary && <small>{summary}</small>}
          </span>
          {badge !== null && badge !== '' && <span className="roomDisclosureBadge">{badge}</span>}
        </button>
        {actions && <div className="roomDisclosureActions">{actions}</div>}
      </div>
      {open && <div id={contentId} className="roomDisclosureContent">{children}</div>}
    </section>
  )
}
