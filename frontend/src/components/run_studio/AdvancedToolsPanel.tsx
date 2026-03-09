import React from 'react'

type Props = {
  onOpenGraph: () => void
  onOpenRawTrace: () => void
  onOpenAdvanced: () => void
}

export default function AdvancedToolsPanel({ onOpenGraph, onOpenRawTrace, onOpenAdvanced }: Props) {
  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <h3>Secondary Views</h3>
      </div>
      <div className="muted" style={{ marginBottom: 8 }}>
        Graph editing and copy/paste tools are preserved as power-user workflows.
      </div>
      <div className="row" style={{ marginBottom: 0 }}>
        <button onClick={onOpenGraph}>Open Graph</button>
        <button onClick={onOpenRawTrace}>Open Raw Trace</button>
        <button onClick={onOpenAdvanced}>Open Advanced Tools</button>
      </div>
    </section>
  )
}
