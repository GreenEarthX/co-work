// The GEX administrator buttons and the two read-only parameter screens (20 Nov 2026).
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { UserRoleProvider } from '@/contexts/UserRoleContext'
import { TopBar } from '@/components/TopBar'
import { isPlatformAdmin } from '@/lib/authToken'
import { GabillonParametersPage } from '../GabillonParametersPage'
import { TeaParametersPage } from '../TeaParametersPage'

vi.mock('@/features/kyc/kycState', () => ({ initKyc: () => Promise.resolve() }))

function signIn(claims: Record<string, unknown>) {
  const token = `e30.${btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 1800, ...claims })).replace(/=+$/, '')}.sig`
  localStorage.setItem('gex_session_tier', 'authenticated')
  localStorage.setItem('gex_auth_session', JSON.stringify({ token, email: 'a@b.io' }))
}

const bar = () => render(<UserRoleProvider><MemoryRouter><TopBar /></MemoryRouter></UserRoleProvider>)

function answer(body: unknown, status = 200) {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(body), { status })))
}

beforeEach(() => localStorage.clear())
afterEach(() => vi.unstubAllGlobals())

describe('GEX administrator buttons', () => {
  it('a platform administrator sees Console, Gabillon and TEA parameters', () => {
    signIn({ sub: 'jean-marie_greenearthx_com', is_platform_admin: true })
    expect(isPlatformAdmin()).toBe(true)
    bar()
    const g = screen.getByTestId('gex-admin-buttons')
    for (const t of ['Console', 'Gabillon', 'TEA parameters']) expect(within(g).getByText(t)).toBeInTheDocument()
  })

  it('any other account sees none of them', () => {
    signIn({ sub: 'cfo_hamburgone_com', is_platform_admin: false })
    expect(isPlatformAdmin()).toBe(false)
    bar()
    expect(screen.queryByTestId('gex-admin-buttons')).toBeNull()
  })

  it('a malformed token is not an administrator', () => {
    localStorage.setItem('gex_auth_session', JSON.stringify({ token: 'not.a.jwt' }))
    expect(isPlatformAdmin()).toBe(false)
  })
})

describe('Gabillon parameters', () => {
  it('shows each molecule\'s parameters with its standing and the CEPCI forward rows', async () => {
    answer({
      molecules: [{ key: 'E_METHANOL', label: 'e-Methanol', unit: '€/t', calibration_status: 'SEED',
        params: { alpha: 0.65, sigma_s: 0.3, mu_equilibrium_eur_t: 800, n_observations: 0, last_calibrated: '2026-03-22' } }],
      cepci_forward: [{ ref_id: '317b8568-x', parameter_key: 'cepci_forward_2026', value_low: 749.2, value_base: 834.6,
        value_high: 925.8, state: 'approved', proposed_by: 'script', approved_by: 'jean-marie_greenearthx_com', approved_at: '2026-11-20T13:50' }],
      notes: ['Electricity has no Gabillon curve: power is not storable.'],
    })
    render(<MemoryRouter><GabillonParametersPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByTestId('gabillon-parameters')).toBeInTheDocument())
    expect(screen.getByText('SEED', { selector: 'td' })).toBeInTheDocument()
    expect(screen.getByText('0.65')).toBeInTheDocument()
    expect(within(screen.getByTestId('cepci-forward-rows')).getByText('834.6')).toBeInTheDocument()
    expect(screen.getByText(/power is not storable/)).toBeInTheDocument()
  })

  it('a refusal is shown as the server said it, never as an empty table', async () => {
    answer({ detail: { code: 'GEX_STAFF_ONLY', message: 'The GEX staff console is for GEX platform administrators.' } }, 403)
    render(<MemoryRouter><GabillonParametersPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByTestId('gabillon-error')).toHaveTextContent('GEX platform administrators'))
  })
})

describe('TEA parameters', () => {
  const body = {
    engine: {
      fingerprint: { openpytea_version: '3.2.3', correlations: 2, cepci_year_range: [1987, 2024], hash: 'sha256:abc' },
      renamed_categories: { 'Compressors & blowers': 'Compressors, fans, & blowers' },
      correlations: [
        { key: 'co2_compressor_manzolini_2011', category: 'Compressors, fans, & blowers', type: 'CO2 compressor', units: 'MWe', cost_year: '2011', source: 'Manzolini 2011' },
        { key: 'electrolyzer_nrel_2008', category: 'Electrolyzers & fuel cells', type: 'Electrolyzer (PEM / alkaline)', units: 'kW', cost_year: '2008', source: 'NREL 2008' },
      ],
      note: 'Pinned, not editable.',
    },
    equipment_spec: [{ spec_id: 's1', fuel_id: 'E_METHANOL', role: 'CO2 feed compressor', category: 'Compressors, fans, & blowers',
      equipment_type: 'CO2 compressor', material: 'Carbon steel', base_param: 6, base_param_unit: 'MWe', scale_exp: 0.65, state: 'approved',
      proposed_by: 'SEED_PROCESS_FUNCTIONS', approved_by: 'SEED_APPROVED_IN_FORCE' }],
    correlation_sets_seen: [{ set_hash: 'sha256:abc', openpytea_version: '3.2.3', correlations: 430, state: 'unreviewed' }],
    reference: [{ ref_id: 'r1', parameter_key: 'tea_fx_usd_to_eur', value_base: 0.9248, unit: 'EUR/USD', state: 'approved' }],
  }

  it('lists the pinned correlations, filters them, and names the retired categories', async () => {
    answer(body)
    render(<MemoryRouter><TeaParametersPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByTestId('tea-parameters')).toBeInTheDocument())
    expect(screen.getByTestId('correlations').querySelectorAll('tbody tr')).toHaveLength(2)
    fireEvent.change(screen.getByLabelText('Search correlations'), { target: { value: 'nrel' } })
    expect(screen.getByTestId('correlations').querySelectorAll('tbody tr')).toHaveLength(1)
    expect(screen.getByTestId('renamed-categories')).toHaveTextContent('Compressors & blowers')
    expect(within(screen.getByTestId('correlation-sets')).getByText(/\(running\)/)).toBeInTheDocument()
    expect(within(screen.getByTestId('equipment-spec')).getByText('SEED_PROCESS_FUNCTIONS / SEED_APPROVED_IN_FORCE')).toBeInTheDocument()
    expect(within(screen.getByTestId('tea-reference')).getByText('0.9248')).toBeInTheDocument()
  })
})
