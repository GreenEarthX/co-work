import { describe, expect, it } from 'vitest'
import { submittedNote } from '../submittedNote'

describe('submittedNote', () => {
  it('says plainly that submitted items are not independently verified', () => {
    expect(submittedNote(3)).toBe(' · 3 submitted, not independently verified')
  })
  it('is empty when there are none or the server predates the field', () => {
    expect(submittedNote(0)).toBe('')
    expect(submittedNote(undefined)).toBe('')
    expect(submittedNote(null)).toBe('')
  })
})
