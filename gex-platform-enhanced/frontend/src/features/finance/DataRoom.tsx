// Screen: Data room screen (/data-room, /finance/data-room)
/**
 * DataRoom — the documents on file for the selected project.
 *
 * Real documents only (2026-10-25). This screen used to list ~40 invented
 * documents in 11 categories ("FEED Study Report - Technip Energies.pdf" …),
 * each with a hash generated from its name to look like a SHA-256, and a status
 * chosen per project — partly by Math.random(). Now it lists what was uploaded
 * (GET /api/v1/bankability/evidence/documents, PostgreSQL): the evidence item
 * each document supports, its real SHA-256, size, uploader and date, and a
 * download link. Missing evidence is on Gates & Evidence, which knows the rules.
 *
 * Deep links ?evidence=<key> highlight that item's documents.
 */
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { FolderOpen, FileText, Download, Hash } from 'lucide-react'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'
import { getAuthHeader } from '@/lib/authToken'

interface StoredDocument {
  evidence_key: string
  filename: string
  sha256: string
  size_bytes: number
  uploaded_by: string
  uploaded_at: string
}

const kb = (n: number) => (n >= 1_048_576 ? `${(n / 1_048_576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`)

export function DataRoom() {
  const { selectedProjectId } = useSelectedProject()
  const { projects: visibleProjects } = useVisibleProjects()
  const project = visibleProjects.find(p => p.id === selectedProjectId)
  const [searchParams] = useSearchParams()
  const focus = searchParams.get('evidence') ?? ''
  const [docs, setDocs] = useState<StoredDocument[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!selectedProjectId) { setDocs([]); return }
    setDocs(null); setError(null)
    fetch(`/api/v1/bankability/evidence/documents?project_id=${encodeURIComponent(selectedProjectId)}`,
      { headers: getAuthHeader() })
      .then(async r => { if (!r.ok) throw new Error(`The server answered ${r.status}.`); return r.json() })
      .then(d => setDocs(d.documents ?? []))
      .catch(e => setError(e.message))
  }, [selectedProjectId])

  const byItem = useMemo(() => {
    const m = new Map<string, StoredDocument[]>()
    for (const d of docs ?? []) m.set(d.evidence_key, [...(m.get(d.evidence_key) ?? []), d])
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [docs])

  const download = async (d: StoredDocument) => {
    const r = await fetch(`/api/v1/bankability/evidence/document/${d.sha256}/download`, { headers: getAuthHeader() })
    if (!r.ok) { setError(`Download refused (${r.status}).`); return }
    const url = URL.createObjectURL(await r.blob())
    const a = document.createElement('a')
    a.href = url; a.download = d.filename; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-5 animate-fade-in">
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-6 py-4 shadow-card">
        <h1 className="font-display text-2xl font-bold text-[var(--text-primary)] flex items-center gap-2">
          <FolderOpen className="w-6 h-6 text-[var(--brand)]" /> Data Room
        </h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          {project?.name ?? selectedProjectId ?? 'Select a project'} · documents on file, by evidence item
        </p>
      </div>

      {error && (
        <p className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">{error}</p>
      )}
      {!error && docs === null && <p className="text-sm text-[var(--text-muted)]">Loading…</p>}
      {!error && docs !== null && docs.length === 0 && (
        <p className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--text-muted)]">
          No document is on file for this project yet. Upload one against an evidence item on{' '}
          <a className="font-medium text-[var(--brand)] underline" href="/stage-gates">Gates &amp; Evidence</a>.
        </p>
      )}

      {byItem.map(([key, items]) => (
        <div key={key} className={`rounded-2xl border bg-[var(--surface)] shadow-card ${
          key === focus ? 'border-[var(--brand)]' : 'border-[var(--border)]'}`}>
          <div className="border-b border-[var(--border)] px-5 py-3 text-sm font-bold text-[var(--text-primary)]">
            {key.replace(/_/g, ' ')}
          </div>
          <div className="divide-y divide-[var(--border)]">
            {items.map(d => (
              <div key={d.sha256 + d.uploaded_at} className="flex items-center gap-3 px-5 py-3">
                <FileText className="w-4 h-4 text-[var(--text-muted)] shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-[var(--text-primary)] truncate">{d.filename}</p>
                  <p className="text-xs text-[var(--text-muted)] flex items-center gap-1">
                    <Hash className="w-3 h-3" /><span className="font-mono">{d.sha256.slice(0, 16)}…</span>
                    · {kb(d.size_bytes)} · {d.uploaded_by} · {new Date(d.uploaded_at).toLocaleDateString('en-GB')}
                  </p>
                </div>
                <button onClick={() => download(d)}
                  className="flex items-center gap-1 rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]">
                  <Download className="w-3 h-3" /> Download
                </button>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
