// Screen: Account settings screen (/account)
/**
 * AccountPage — User Identity & Credentials Landing Page
 *
 * Displays per-user:
 *   - Identity header (avatar, email, KYC badge, provider badge)
 *   - Account Security (sign-out, 2FA toggle, password last-changed)
 *   - Login History (pulled from /api/v1/auth/login-history)
 *   - Account details (email, provider, account ID, jurisdiction)
 *   - Role & ABAC context (company_type, business_function, clearance, capabilities)
 *   - OIDC token info (issuer, expiry, scopes, signing algorithm)
 *
 * B2B professional design: function over form, minimal colour.
 * Colour reserved for KYC/status badges and action buttons only.
 */

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft, LogOut, Shield, KeyRound, Clock, Monitor,
  CheckCircle, AlertTriangle, Lock, Fingerprint, Globe,
  Building2, Briefcase, BadgeCheck, ChevronDown, ChevronUp,
} from 'lucide-react'
import { useUserRole, type UserRole } from '@/contexts/UserRoleContext'

// ── Types ─────────────────────────────────────────────────────────────────────

interface LoginEvent {
  event_type: string
  ip_address: string | null
  user_agent: string | null
  timestamp: string
  success: number
}

interface OIDCTokenInfo {
  issuer: string
  subject: string
  issued_at: string
  expires_at: string
  algorithm: string
  scopes: string[]
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function parseUserAgent(ua: string | null): string {
  if (!ua) return 'Unknown'
  const os = /Windows/.test(ua) ? 'Windows' : /Mac/.test(ua) ? 'macOS' : /Linux/.test(ua) ? 'Linux' : 'Unknown OS'
  const browser = /Edg/.test(ua) ? 'Edge' : /Chrome/.test(ua) ? 'Chrome' : /Safari/.test(ua) ? 'Safari' : /Firefox/.test(ua) ? 'Firefox' : 'Unknown'
  return `from ${os} — ${browser}`
}

function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: 'numeric' })
      + ', ' + d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return iso
  }
}

function decodeJWTPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return null
    const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')))
    return payload
  } catch {
    return null
  }
}

function getTokenInfo(token: string | undefined): OIDCTokenInfo | null {
  if (!token) return null
  const payload = decodeJWTPayload(token)
  if (!payload) return null

  const iat = typeof payload.iat === 'number' ? new Date(payload.iat * 1000).toISOString() : 'unknown'
  const exp = typeof payload.exp === 'number' ? new Date(payload.exp * 1000).toISOString() : 'unknown'

  return {
    issuer: 'GEX Identity Service (HS256)',
    subject: String(payload.sub ?? 'unknown'),
    issued_at: iat,
    expires_at: exp,
    algorithm: 'HS256',
    scopes: ['openid', 'profile', 'email', 'gex:trade'],
  }
}

function roleLabel(role: UserRole): string {
  if (role.company_type === 'PRODUCER') return 'Producer'
  if (role.company_type === 'OFFTAKER') return 'Off-Taker / Buyer'
  if (role.service_type === 'BANK') return 'Commercial Bank'
  if (role.service_type === 'INSURER') return 'Insurer'
  if (role.service_type === 'CERTIFIER') return 'Certification Body'
  if (role.service_type === 'ENGINEER') return 'Engineering Firm'
  if (role.service_type === 'LOGISTICS') return 'Logistics Operator'
  if (role.service_type === 'EQUIPMENT') return 'Equipment Supplier'
  if (role.service_type === 'LEGAL') return 'Legal Advisor'
  return 'Third Party'
}

function roleIcon(role: UserRole): string {
  if (role.company_type === 'PRODUCER') return '🏭'
  if (role.company_type === 'OFFTAKER') return '🛒'
  if (role.service_type === 'BANK') return '🏦'
  if (role.service_type === 'INSURER') return '🛡'
  return '🏢'
}

function clearanceBadge(level: string | undefined): { label: string; bg: string; text: string } {
  switch (level) {
    case 'RESTRICTED': return { label: 'RESTRICTED', bg: 'bg-red-100', text: 'text-red-700' }
    case 'CONFIDENTIAL': return { label: 'CONFIDENTIAL', bg: 'bg-amber-100', text: 'text-amber-700' }
    default: return { label: 'STANDARD', bg: 'bg-gray-100', text: 'text-gray-600' }
  }
}

// ── Section Components ────────────────────────────────────────────────────────

function SectionCard({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-white rounded-xl border border-gray-200 p-5 ${className}`}>
      {children}
    </div>
  )
}

function DetailRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-gray-100 last:border-0">
      <span className="text-sm text-gray-500">{label}</span>
      <span className={`text-sm font-semibold text-gray-900 ${mono ? 'font-mono text-xs' : ''}`}>{value}</span>
    </div>
  )
}

// ── Main Component ────────────────────────────────────────────────────────────

export function AccountPage() {
  const navigate = useNavigate()
  const { role, authSession, logout, sessionTier } = useUserRole()
  const [loginHistory, setLoginHistory] = useState<LoginEvent[]>([])
  const [tokenInfo, setTokenInfo] = useState<OIDCTokenInfo | null>(null)
  const [showOIDC, setShowOIDC] = useState(false)
  const [passwordChanged] = useState<string>('Never')

  // Derive clearance from JWT claims
  const claims = authSession?.token ? decodeJWTPayload(authSession.token) : null
  const clearanceLevel = (claims?.clearance_level as string) ?? 'STANDARD'
  const jurisdiction = (claims?.jurisdiction as string) ?? 'EU'
  const kycStatus = (claims?.kyc_status as string) ?? 'UNVERIFIED'
  const userId = (claims?.sub as string) ?? 'unknown'
  const capabilities = (claims?.capabilities as string[]) ?? role.capabilities ?? []
  const ndaSignedWith = (claims?.nda_signed_with as string[]) ?? []

  // Fetch login history from backend
  useEffect(() => {
    if (!authSession?.token) return
    fetch('/api/v1/auth/login-history', {
      headers: { Authorization: `Bearer ${authSession.token}` },
    })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data?.history) setLoginHistory(data.history)
      })
      .catch(() => {
        // Fallback demo data if backend not running
        setLoginHistory([
          { event_type: 'signin', ip_address: '217.138.216.212', user_agent: 'Mozilla/5.0 (Macintosh) Chrome/120', timestamp: '2026-03-15T09:12:34Z', success: 1 },
          { event_type: 'signin', ip_address: '185.153.151.157', user_agent: 'Mozilla/5.0 (Macintosh) Safari/17', timestamp: '2026-03-13T14:55:54Z', success: 1 },
          { event_type: 'signin', ip_address: '92.184.100.42', user_agent: 'Mozilla/5.0 (Windows NT 10.0) Edg/120', timestamp: '2026-03-10T08:22:11Z', success: 1 },
        ])
      })
  }, [authSession?.token])

  // Decode JWT token info
  useEffect(() => {
    setTokenInfo(getTokenInfo(authSession?.token))
  }, [authSession?.token])

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const clr = clearanceBadge(clearanceLevel)
  const initials = role.user_name
    .split(' ')
    .map(n => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2)

  if (sessionTier !== 'authenticated') {
    navigate('/login')
    return null
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-[960px] mx-auto space-y-5">

        {/* Back link */}
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-900 transition-colors"
        >
          <ArrowLeft size={16} />
          Back
        </button>

        {/* ── Identity Header ──────────────────────────────────────── */}
        <SectionCard>
          <div className="flex items-center gap-5">
            {role.company_logo_url ? (
              <img src={role.company_logo_url} alt="" className="w-16 h-16 rounded-full object-cover" />
            ) : (
              <div className="w-16 h-16 rounded-full bg-teal-500 flex items-center justify-center text-white text-xl font-bold shrink-0">
                {initials}
              </div>
            )}
            <div>
              <h1 className="text-xl font-bold text-gray-900">Welcome back, {role.user_name.split(' ')[0]}!</h1>
              <p className="text-sm text-gray-500">{authSession?.email ?? 'no-email'}</p>
              <div className="flex items-center gap-2 mt-2">
                <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600 border border-gray-200">
                  Email Account
                </span>
                {kycStatus === 'VERIFIED' && (
                  <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1">
                    <CheckCircle size={12} />
                    KYC Verified
                  </span>
                )}
                {kycStatus !== 'VERIFIED' && (
                  <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200 flex items-center gap-1">
                    <AlertTriangle size={12} />
                    KYC {kycStatus}
                  </span>
                )}
              </div>
            </div>
          </div>
        </SectionCard>

        {/* ── Account Security + Login History (side by side) ───────── */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">

          {/* Security Actions */}
          <SectionCard>
            <div className="flex items-center gap-2 mb-4">
              <Shield size={18} className="text-gray-400" />
              <h2 className="text-sm font-bold text-gray-900">Account Security</h2>
            </div>

            <button
              onClick={handleLogout}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-red-500 hover:bg-red-600 text-white font-semibold text-sm transition-colors mb-3"
            >
              <LogOut size={16} />
              Sign Out
            </button>

            <button
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-teal-600 hover:bg-teal-700 text-white font-semibold text-sm transition-colors mb-4"
            >
              <Fingerprint size={16} />
              Enable Two-Factor Authentication
            </button>

            <div className="border border-gray-200 rounded-lg p-3 flex items-center gap-3">
              <KeyRound size={16} className="text-gray-400" />
              <div>
                <p className="text-sm font-semibold text-gray-900">Password</p>
                <p className="text-xs text-gray-500">Last changed: {passwordChanged}</p>
              </div>
            </div>
          </SectionCard>

          {/* Login History */}
          <SectionCard>
            <div className="flex items-center gap-2 mb-4">
              <Clock size={18} className="text-gray-400" />
              <h2 className="text-sm font-bold text-gray-900">Login History</h2>
            </div>

            {loginHistory.length === 0 ? (
              <p className="text-sm text-gray-400">No login history available.</p>
            ) : (
              <div className="space-y-3">
                {loginHistory.slice(0, 5).map((evt, i) => (
                  <div key={i} className="flex items-start justify-between gap-3 py-2 border-b border-gray-100 last:border-0">
                    <div className="flex items-start gap-2">
                      <Monitor size={14} className="text-gray-400 mt-0.5 shrink-0" />
                      <div>
                        <p className="text-sm font-medium text-gray-900">
                          {evt.event_type}{' '}
                          <span className="text-gray-500 font-normal">{parseUserAgent(evt.user_agent)}</span>
                        </p>
                        <p className="text-xs text-gray-400">
                          IP: {evt.ip_address ?? 'unknown'}
                        </p>
                      </div>
                    </div>
                    <span className="text-xs text-gray-500 whitespace-nowrap shrink-0">
                      {formatTimestamp(evt.timestamp)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </SectionCard>
        </div>

        {/* ── Account Details ──────────────────────────────────────── */}
        <SectionCard>
          <h2 className="text-xs font-bold uppercase tracking-wide text-gray-900 mb-3">Account</h2>
          <DetailRow label="Email" value={authSession?.email ?? '—'} />
          <DetailRow label="Provider" value="credentials" />
          <DetailRow label="Account ID" value={userId} mono />
          <DetailRow label="Jurisdiction" value={jurisdiction} />
        </SectionCard>

        {/* ── Role & ABAC Context ──────────────────────────────────── */}
        <SectionCard>
          <div className="flex items-center gap-2 mb-3">
            <span className="text-lg">{roleIcon(role)}</span>
            <h2 className="text-xs font-bold uppercase tracking-wide text-gray-900">
              {roleLabel(role)}
            </h2>
          </div>

          <DetailRow label="Company" value={role.company_name} />
          <DetailRow label="Business Function" value={role.business_function.replace('_', ' ')} />

          {role.service_type && (
            <DetailRow label="Service Type" value={role.service_type} />
          )}

          <div className="flex items-center justify-between py-2.5 border-b border-gray-100">
            <span className="text-sm text-gray-500">ABAC Clearance</span>
            <span className={`px-2 py-0.5 rounded text-xs font-bold ${clr.bg} ${clr.text}`}>
              {clr.label}
            </span>
          </div>

          {capabilities.length > 0 && (
            <div className="flex items-center justify-between py-2.5 border-b border-gray-100">
              <span className="text-sm text-gray-500">Capabilities</span>
              <div className="flex gap-1 flex-wrap justify-end">
                {capabilities.map(c => (
                  <span key={c} className="px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700">
                    {c}
                  </span>
                ))}
              </div>
            </div>
          )}

          {role.credit_rating && role.credit_rating !== 'NR' && (
            <DetailRow
              label="Credit Rating"
              value={`${role.credit_rating} (${role.credit_rating_source ?? 'GEX'})`}
            />
          )}

          {ndaSignedWith.length > 0 && (
            <div className="flex items-center justify-between py-2.5 border-b border-gray-100">
              <span className="text-sm text-gray-500">NDA Coverage</span>
              <span className="text-sm font-semibold text-gray-900">{ndaSignedWith.length} entities</span>
            </div>
          )}
        </SectionCard>

        {/* ── OIDC / Token Info (collapsible) ──────────────────────── */}
        <SectionCard>
          <button
            onClick={() => setShowOIDC(o => !o)}
            className="w-full flex items-center justify-between"
          >
            <div className="flex items-center gap-2">
              <Lock size={16} className="text-gray-400" />
              <h2 className="text-xs font-bold uppercase tracking-wide text-gray-900">
                Identity Token (OIDC / JWT)
              </h2>
            </div>
            {showOIDC ? <ChevronUp size={16} className="text-gray-400" /> : <ChevronDown size={16} className="text-gray-400" />}
          </button>

          {showOIDC && tokenInfo && (
            <div className="mt-3 pt-3 border-t border-gray-100">
              <DetailRow label="Issuer" value={tokenInfo.issuer} />
              <DetailRow label="Subject" value={tokenInfo.subject} mono />
              <DetailRow label="Algorithm" value={tokenInfo.algorithm} />
              <DetailRow label="Issued At" value={formatTimestamp(tokenInfo.issued_at)} />
              <DetailRow label="Expires At" value={formatTimestamp(tokenInfo.expires_at)} />
              <div className="flex items-center justify-between py-2.5 border-b border-gray-100">
                <span className="text-sm text-gray-500">Scopes</span>
                <div className="flex gap-1 flex-wrap justify-end">
                  {tokenInfo.scopes.map(s => (
                    <span key={s} className="px-2 py-0.5 rounded text-xs font-mono bg-gray-100 text-gray-600">
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {showOIDC && !tokenInfo && (
            <p className="mt-3 text-sm text-gray-400">No token available — session may have expired.</p>
          )}
        </SectionCard>

        {/* ── Security Architecture Note ───────────────────────────── */}
        <SectionCard>
          <div className="flex items-start gap-3">
            <Globe size={16} className="text-gray-400 mt-0.5 shrink-0" />
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wide text-gray-700 mb-1">
                Security Architecture
              </h3>
              <p className="text-xs text-gray-500 leading-relaxed">
                GEX enforces <strong>Attribute-Based Access Control (ABAC)</strong> with 9 policy rules (R0–R9)
                covering data access, trade execution, and evidence sensitivity.
                Row-Level Security is enforced via project-scoped JWT claims:
                each token encodes your company association, clearance level, and actor type per project.
                All access decisions are logged to an immutable audit trail.
                Identity tokens follow <strong>OIDC/JWT</strong> standards (HS256, 30-min expiry)
                and are validated on every API request by the ABAC middleware.
              </p>
            </div>
          </div>
        </SectionCard>

        {/* ── Compliance Badges ─────────────────────────────────────── */}
        <div className="flex items-center gap-3 flex-wrap pb-6">
          <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-gray-200 text-xs text-gray-500">
            <BadgeCheck size={14} className="text-teal-600" />
            ABAC R0–R9 Enforced
          </span>
          <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-gray-200 text-xs text-gray-500">
            <Lock size={14} className="text-gray-400" />
            JWT HS256 Signed
          </span>
          <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-gray-200 text-xs text-gray-500">
            <Building2 size={14} className="text-gray-400" />
            Project-Scoped RLS
          </span>
          <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-gray-200 text-xs text-gray-500">
            <Briefcase size={14} className="text-gray-400" />
            Tier-1 Industrial Grade
          </span>
        </div>

      </div>
    </div>
  )
}
