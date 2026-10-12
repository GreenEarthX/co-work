/**
 * T6 — the login page's molecule count is the length of the list it names
 * (it once said "4 Fuel Molecules" beside a sentence naming five).
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { FUEL_MOLECULES, LoginPage } from '../LoginPage'

vi.mock('@/contexts/UserRoleContext', () => ({
  useUserRole: () => ({ login: vi.fn(), continueAsGuest: vi.fn() }),
}))

describe('LoginPage fuel molecules', () => {
  it('counts exactly the molecules it names', () => {
    render(<MemoryRouter><LoginPage /></MemoryRouter>)

    const count = screen.getByText('Fuel Molecules').previousElementSibling
    expect(count).toHaveTextContent(String(FUEL_MOLECULES.length))
    expect(FUEL_MOLECULES).toHaveLength(5)

    const sentence = screen.getByText(/Bankability assessment, capital structuring, and compliance/)
    for (const molecule of FUEL_MOLECULES) expect(sentence).toHaveTextContent(molecule)
    expect(sentence.textContent).not.toMatch(/\s,/)
  })
})
