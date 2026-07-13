import { useEffect, useState } from 'react'

function currentVisibility(): boolean {
  if (typeof document === 'undefined') return true
  return document.visibilityState !== 'hidden'
}

export function usePageVisibility(): boolean {
  const [visible, setVisible] = useState(currentVisibility)

  useEffect(() => {
    const update = () => setVisible(currentVisibility())
    document.addEventListener('visibilitychange', update)
    window.addEventListener('focus', update)
    window.addEventListener('blur', update)
    return () => {
      document.removeEventListener('visibilitychange', update)
      window.removeEventListener('focus', update)
      window.removeEventListener('blur', update)
    }
  }, [])

  return visible
}
