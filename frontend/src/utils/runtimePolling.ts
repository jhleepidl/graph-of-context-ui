export function makeClientCommandId(prefix = 'cmd_goc'): string {
  const safePrefix = String(prefix || 'cmd_goc').replace(/[^a-zA-Z0-9_-]+/g, '_').slice(0, 40)
  const random = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID().replace(/-/g, '')
    : `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`
  return `${safePrefix}_${random.slice(0, 32)}`
}

export function runtimeCommandPollDelay(status: string, attempt: number, visible = true): number {
  if (!visible) return 10000
  const cleanStatus = String(status || '').trim().toLowerCase()
  if (cleanStatus === 'accepted') return Math.min(5000, 1200 + Math.max(0, attempt) * 250)
  if (cleanStatus === 'queued') return Math.min(3000, 500 + Math.max(0, attempt) * 180)
  return Math.min(5000, 800 + Math.max(0, attempt) * 220)
}

export function workspacePollDelay({ active = false, visible = true, rawTrace = false }: {
  active?: boolean
  visible?: boolean
  rawTrace?: boolean
}): number {
  if (!visible) return 30000
  if (rawTrace) return active ? 2500 : 6000
  return active ? 2000 : 10000
}
