import React from 'react'
import { type MobileSection, type WorkspaceMainTab } from '../../hooks/useWorkspaceTabs'

type Props = {
  isMobileLayout: boolean
  mobileSection: MobileSection
  setMobileSection: (section: MobileSection) => void
  workspaceMainTab: WorkspaceMainTab
  workspaceMainTabLabel: string
  wrapRef: React.RefObject<HTMLDivElement>
  wrapStyle: React.CSSProperties
  showLeftPanel: boolean
  showCenterPanel: boolean
  showRightPanel: boolean
  onStartLeftResize: (evt: React.MouseEvent<HTMLDivElement>) => void
  onStartRightResize: (evt: React.MouseEvent<HTMLDivElement>) => void
  leftContent: React.ReactNode
  centerContent: React.ReactNode
  rightContent?: React.ReactNode
}

export default function WorkspaceShell({
  isMobileLayout,
  mobileSection,
  setMobileSection,
  workspaceMainTab,
  workspaceMainTabLabel,
  wrapRef,
  wrapStyle,
  showLeftPanel,
  showCenterPanel,
  showRightPanel,
  onStartLeftResize,
  onStartRightResize,
  leftContent,
  centerContent,
  rightContent,
}: Props) {
  const showRightColumn = workspaceMainTab === 'graph' && Boolean(rightContent)

  return (
    <div className="appShell">
      {isMobileLayout && (
        <div className="mobileSectionTabs card">
          <div className="row" style={{ marginBottom: 0 }}>
            <button className={mobileSection === 'center' ? 'primary' : ''} onClick={() => setMobileSection('center')}>
              {workspaceMainTabLabel}
            </button>
            <button className={mobileSection === 'left' ? 'primary' : ''} onClick={() => setMobileSection('left')}>
              Threads
            </button>
            <button
              className={mobileSection === 'right' ? 'primary' : ''}
              onClick={() => setMobileSection('right')}
              disabled={!showRightColumn}
            >
              Context
            </button>
          </div>
        </div>
      )}

      <div className={`wrap ${workspaceMainTab !== 'graph' ? 'wrapExecutionMode' : ''}`} ref={wrapRef} style={wrapStyle}>
        <div className={`col col-left ${showLeftPanel ? '' : 'isMobileHidden'}`}>
          {leftContent}
        </div>

        {!isMobileLayout && (
          <div
            className="panelResizer"
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize left panel"
            onMouseDown={onStartLeftResize}
          />
        )}

        <div className={`col col-center ${showCenterPanel ? '' : 'isMobileHidden'}`}>
          {centerContent}
        </div>

        {showRightColumn && !isMobileLayout && (
          <div
            className="panelResizer"
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize right panel"
            onMouseDown={onStartRightResize}
          />
        )}

        {showRightColumn && (
          <div className={`col col-right ${showRightPanel ? '' : 'isMobileHidden'}`}>
            {rightContent}
          </div>
        )}
      </div>
    </div>
  )
}
