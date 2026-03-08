import { useEffect, useState } from 'react'

import type { ControlPanel, DashboardPage, MemoryPanel, WorkPanel } from '../lib/dashboardView'

const DASHBOARD_PAGES: DashboardPage[] = ['overview', 'work', 'inbox', 'discovery', 'memory', 'control']

function readInitialPage(): DashboardPage {
  const hash = window.location.hash.replace(/^#/, '').trim()
  if (hash.startsWith('page=')) {
    const candidate = hash.slice('page='.length) as DashboardPage
    if (DASHBOARD_PAGES.includes(candidate)) return candidate
  }
  return 'overview'
}

export function useDashboardNavigation() {
  const [activePage, setActivePage] = useState<DashboardPage>(() => readInitialPage())
  const [workPanel, setWorkPanel] = useState<WorkPanel>('tasks')
  const [memoryPanel, setMemoryPanel] = useState<MemoryPanel>('activity')
  const [controlPanel, setControlPanel] = useState<ControlPanel>('models')

  useEffect(() => {
    window.location.hash = `page=${activePage}`
  }, [activePage])

  return {
    activePage,
    controlPanel,
    memoryPanel,
    setActivePage,
    setControlPanel,
    setMemoryPanel,
    setWorkPanel,
    workPanel,
  }
}
