// Screen: CFO/CEO report screen (/cfo-report)
/**
 * CFO / CEO portfolio report — the signed-in organisation's visible projects.
 *
 * Real data only (2026-10-25). Until then every figure here was a fixed sample
 * portfolio written into the code (Le Havre "BANKABLE 94", WACC 10.78 %, DSCR
 * 0.98–1.58, €553M senior debt, ranked risks, decisions, a Gantt), labelled as
 * illustrative. Now each row is a project the server lets the caller see, with
 * its recorded gate completion and next milestone; the profile's verification
 * state is shown. Portfolio WACC, DSCR and contracted revenue are not recorded
 * across projects, so they are not shown.
 */
import { useState } from 'react'
import { Printer } from 'lucide-react'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'

export function CFOReport() {
  const { projects, isLoading: loading } = useVisibleProjects()
  const [generatedAt] = useState(() => new Date().toLocaleString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  }))

  const rows = projects.map(p => {
    const gates = p.bankability?.gates ?? []
    const next = gates.find(g => !g.is_complete)
    return {
      id: p.id, name: p.name, molecule: p.molecule, status: p.status,
      completion: p.bankability?.overall_completion ?? null,
      nextGate: next ? (next.name ?? next.id) : gates.length ? 'All gates complete' : '—',
      milestone: p.bankability?.next_milestone || '—',
    }
  })
  const measured = rows.filter(r => r.completion !== null)
  const avg = measured.length ? Math.round(measured.reduce((s, r) => s + (r.completion ?? 0), 0) / measured.length) : null

  return (
    <div className="min-h-screen p-6" style={{ backgroundColor: 'var(--surface, #f8fafc)', color: 'var(--text, #0f172a)' }}>
      <div className="flex items-center justify-between mb-6 print:hidden">
        <span className="px-3 py-1 text-xs font-bold rounded-full bg-red-100 text-red-700 uppercase tracking-widest border border-red-300">
          Internal — Strictly Confidential
        </span>
        <button
          onClick={() => window.print()}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white hover:opacity-90"
          style={{ backgroundColor: 'var(--brand, #0ea5e9)' }}
        >
          <Printer size={16} /> Print Report
        </button>
      </div>

      <div className="mb-6 pb-4" style={{ borderBottom: '2px solid var(--border, #e2e8f0)' }}>
        <p className="text-xs font-semibold uppercase tracking-widest mb-1" style={{ color: 'var(--brand, #0ea5e9)' }}>
          GreenEarthX — Executive Report
        </p>
        <h1 className="text-2xl font-bold mb-0.5">Portfolio Report</h1>
        <p className="text-sm" style={{ color: 'var(--text-muted, #64748b)' }}>Generated {generatedAt}</p>
      </div>

      <div className="grid grid-cols-3 gap-3 mb-6">
        {[
          { label: 'Projects', value: String(rows.length) },
          { label: 'Average gate completion', value: avg !== null ? `${avg}%` : '—' },
          { label: 'Portfolio WACC / DSCR', value: 'Not recorded' },
        ].map(k => (
          <div key={k.label} className="rounded-xl border border-[var(--border,#e2e8f0)] bg-white px-4 py-3">
            <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400">{k.label}</div>
            <div className="mt-1 text-xl font-black text-gray-900">{k.value}</div>
          </div>
        ))}
      </div>

      <section>
        <h2 className="text-base font-bold uppercase tracking-wide mb-3" style={{ color: 'var(--brand, #0ea5e9)' }}>
          Portfolio Status
        </h2>
        {loading ? (
          <p className="text-sm text-gray-400">Loading…</p>
        ) : rows.length === 0 ? (
          <p className="text-sm text-gray-500">No projects are visible to your organisation.</p>
        ) : (
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-gray-500 border-b">
                {['Project', 'Molecule', 'Status', 'Gate completion', 'Next gate', 'Next milestone'].map(h =>
                  <th key={h} className="py-2 pr-3 font-semibold">{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-b border-gray-100">
                  <td className="py-2 pr-3 font-semibold">{r.name}</td>
                  <td className="py-2 pr-3">{r.molecule}</td>
                  <td className="py-2 pr-3">{r.status}</td>
                  <td className="py-2 pr-3 tabular-nums">{r.completion !== null ? `${Math.round(r.completion)}%` : '—'}</td>
                  <td className="py-2 pr-3">{r.nextGate}</td>
                  <td className="py-2 pr-3 text-gray-600">{r.milestone}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
