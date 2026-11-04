// Screen: Shared layout component — all authenticated screens
/**
 * Shown on every screen while the signed-in account still uses a temporary
 * password chosen by GEX (GET /api/v1/auth/password-status). Says nothing when
 * the status cannot be read: the change-password screen states it there.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'
import { fetchPasswordStatus } from '@/features/account/ChangePasswordPage'

export function TemporaryPasswordBanner({ signedIn }: { signedIn: boolean }) {
  const [temporary, setTemporary] = useState(false)

  useEffect(() => {
    if (!signedIn) { setTemporary(false); return }
    let live = true
    fetchPasswordStatus().then(s => { if (live) setTemporary(s.temporary) }).catch(() => {})
    const cleared = () => setTemporary(false)
    window.addEventListener('gex-password-changed', cleared)
    return () => { live = false; window.removeEventListener('gex-password-changed', cleared) }
  }, [signedIn])

  if (!temporary) return null
  return (
    <div role="alert" className="mb-4 flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-500/30 dark:bg-amber-900/20 dark:text-amber-200">
      <AlertTriangle className="h-4 w-4 shrink-0" />
      <span>You are using a temporary password chosen by GEX.</span>
      <Link to="/account/password" className="font-semibold underline">Change it now</Link>
    </div>
  )
}
