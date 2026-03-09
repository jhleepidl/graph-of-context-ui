import React, { useMemo } from 'react'

type Props = {
  nodes: any[]
  activeIds: string[]
}

function shortText(value: string, max = 220): string {
  const compact = (value || '').replace(/\s+/g, ' ').trim()
  if (!compact) return ''
  return compact.length > max ? `${compact.slice(0, max)}...` : compact
}

function parsePayload(raw: string | null | undefined): Record<string, any> {
  try {
    const parsed = JSON.parse(raw || '{}')
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed
  } catch {
    // ignore parse errors
  }
  return {}
}

export default function ArtifactsPanel({ nodes, activeIds }: Props) {
  const activeSet = useMemo(() => new Set(activeIds), [activeIds])
  const artifacts = useMemo(() => {
    return nodes
      .filter((node) => node.type === 'Artifact' || node.type === 'Resource')
      .map((node) => {
        const payload = parsePayload(node.payload_json)
        return {
          id: node.id as string,
          type: node.type as string,
          name: String(payload.name || payload.file_name || payload.uri || node.id).trim(),
          summary: shortText(String(payload.summary || node.text || '')),
          uri: String(payload.uri || '').trim(),
          resourceKind: String(payload.resource_kind || '').trim(),
          createdAt: String(node.created_at || ''),
          selected: activeSet.has(node.id),
        }
      })
      .sort((a, b) => a.createdAt.localeCompare(b.createdAt))
  }, [nodes, activeSet])

  return (
    <div className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <h3>Artifacts</h3>
        <span className="pill">count: {artifacts.length}</span>
      </div>

      {artifacts.length === 0 && (
        <div className="muted">No Artifact/Resource nodes yet.</div>
      )}

      <div className="runStudioList">
        {artifacts.map((item) => (
          <article key={item.id} className="runStudioListItem">
            <div className="row" style={{ marginBottom: 4 }}>
              <span className="pill">{item.type}</span>
              {item.resourceKind && <span className="pill">{item.resourceKind}</span>}
              {item.selected && <span className="pill">selected</span>}
            </div>
            <div><b>{item.name}</b></div>
            {item.summary && <div className="muted">{item.summary}</div>}
            {item.uri && <div className="muted">{item.uri}</div>}
          </article>
        ))}
      </div>
    </div>
  )
}
