/**
 * "Who verifies" (JML, 2026-10-21): everyone on the project sees its reviewers;
 * only GEX staff get the appointment form, and only because the SERVER says so
 * (can_appoint). The browser never decides who is GEX staff.
 */
import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ReviewersPanel } from '../ReviewersPanel'

const ROLES = { INDEPENDENT_ENGINEER: ['G0', 'G1', 'G3', 'G5', 'G6', 'G11'], INSURER: ['G7'] }

function stub(body: Record<string, unknown>) {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })))
}

afterEach(() => vi.unstubAllGlobals())

describe('ReviewersPanel', () => {
  it('says plainly that nothing can be verified while no reviewer is appointed', async () => {
    stub({ project_id: 'p', reviewers: [], can_appoint: false, roles: ROLES })
    render(<ReviewersPanel projectId="p" />)
    expect(await screen.findByText(/No reviewer is appointed yet/)).toBeTruthy()
    expect(screen.queryByText(/Appoint a reviewer/)).toBeNull()
  })

  it('lists reviewers with their gates, and offers no revoke to a non-staff caller', async () => {
    stub({ project_id: 'p', can_appoint: false, roles: ROLES, reviewers: [
      { user_id: 'u_ie', user_name: 'TEST Engineer', company_id: 'c', company_name: 'TEST Engineers',
        role: 'INDEPENDENT_ENGINEER', gates: ['G0', 'G1', 'G3', 'G5', 'G6', 'G11'] }] })
    render(<ReviewersPanel projectId="p" />)
    expect(await screen.findByText('TEST Engineer')).toBeTruthy()
    expect(screen.getByText('Independent engineer')).toBeTruthy()
    expect(screen.getByText('G0, G1, G3, G5, G6, G11')).toBeTruthy()
    expect(screen.queryByText('Revoke')).toBeNull()
  })

  it('offers the appointment form only when the server says the caller may appoint', async () => {
    stub({ project_id: 'p', reviewers: [], can_appoint: true, roles: ROLES })
    render(<ReviewersPanel projectId="p" />)
    expect(await screen.findByText(/Appoint a reviewer/)).toBeTruthy()
    expect(screen.getByRole('option', { name: 'Insurer — G7' })).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Appoint' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('shows a refusal rather than an empty panel', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(
      JSON.stringify({ detail: { code: 'NOT_ON_PROJECT', message: 'You are not a stakeholder or reviewer on this project.' } }),
      { status: 403 })))
    render(<ReviewersPanel projectId="p" />)
    expect(await screen.findByText(/not a stakeholder or reviewer/)).toBeTruthy()
  })
})
