/**
 * KYC/KYB state management — localStorage-backed.
 *
 * Replaces Lovable's AuthContext KYC methods with a standalone module.
 * Persists KYC completion, KYB status, and KYB invitations to localStorage.
 */

const KYC_KEY = 'gex_kyc_state'
const KYB_INVITES_KEY = 'gex_kyb_invitations'

export type KycRole = 'production' | 'infrastructure' | 'offtaker'

export interface KycProfile {
  companyEmail?: string
  firstName?: string
  lastName?: string
  jobTitle?: string
  phoneNumber?: string
  companyName?: string
  companyWebsite?: string
  projectName?: string
  plantName?: string
  projectLifetime?: string
  roleInProject?: string
  primaryPathway?: string
  plantConfiguration?: string
  country?: string
  region?: string
  city?: string
  siteEnvironment?: string
  maturityStage?: string
  expectedCod?: string
  fuelTypesProduced?: string[]
  productionCapacity?: string
  infraType?: string
  facilityName?: string
  regulatoryLicense?: string
  throughputCapacity?: string
  connectedTo?: string
  ccusType?: string
  captureSource?: string
  storageMethod?: string
  annualCo2Capacity?: string
  procurementSector?: string
  annualVolume?: string
  fuelTypes?: string
  deliveryLocation?: string
  contractStatus?: string
  colleagueName?: string
  colleagueEmail?: string
  colleagueRole?: string
}

export interface KybData {
  legalName: string
  registrationNumber: string
  country: string
  vatId?: string
  registeredAddress: string
  beneficialOwners?: string
  responsibleName: string
  responsibleEmail: string
  responsibleJobTitle?: string
}

export interface KybInvitation {
  email: string
  companyName: string
  companyDomain: string
  invitedBy: string
  invitedByName: string
  createdAt: string
}

interface KycState {
  kycCompleted: boolean
  kycRole: KycRole | null
  kycProfile: KycProfile | null
  company: string | null
  kybStatus: 'none' | 'pending_colleague' | 'completed'
  kybData: KybData | null
}

function loadState(): KycState {
  try {
    const raw = localStorage.getItem(KYC_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return { kycCompleted: false, kycRole: null, kycProfile: null, company: null, kybStatus: 'none', kybData: null }
}

function saveState(s: KycState) {
  localStorage.setItem(KYC_KEY, JSON.stringify(s))
}

let _state = loadState()
const _listeners = new Set<() => void>()

function notify() {
  _listeners.forEach(cb => cb())
}

export function subscribeKyc(cb: () => void) {
  _listeners.add(cb)
  return () => { _listeners.delete(cb) }
}

export function getKycState(): KycState { return _state }

export function setKycCompleted() {
  _state = { ..._state, kycCompleted: true }
  saveState(_state)
  notify()
}

export function setKycRole(role: KycRole) {
  _state = { ..._state, kycRole: role }
  saveState(_state)
  notify()
}

export function setKycProfile(profile: KycProfile) {
  _state = { ..._state, kycProfile: profile }
  saveState(_state)
  notify()
}

export function setCompany(company: string) {
  _state = { ..._state, company }
  saveState(_state)
  notify()
}

export function setKybStatus(status: KycState['kybStatus']) {
  _state = { ..._state, kybStatus: status }
  saveState(_state)
  notify()
}

export function setKybCompleted(data: KybData) {
  _state = { ..._state, kybStatus: 'completed', kybData: data }
  saveState(_state)
  notify()
}

// ── KYB Invitations ──

function loadInvites(): KybInvitation[] {
  try {
    const raw = localStorage.getItem(KYB_INVITES_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return []
}

function saveInvites(inv: KybInvitation[]) {
  localStorage.setItem(KYB_INVITES_KEY, JSON.stringify(inv))
}

export function inviteColleagueForKyb(inv: KybInvitation) {
  const all = loadInvites()
  all.push(inv)
  saveInvites(all)
}

export function getKybInvitationFor(email: string | undefined): KybInvitation | null {
  if (!email) return null
  const all = loadInvites()
  return all.find(i => i.email.toLowerCase() === email.toLowerCase()) ?? null
}

export function consumeKybInvitation(email: string) {
  const all = loadInvites().filter(i => i.email.toLowerCase() !== email.toLowerCase())
  saveInvites(all)
}

// ── React hook ──

import { useSyncExternalStore } from 'react'

export function useKycState() {
  const state = useSyncExternalStore(subscribeKyc, getKycState, getKycState)
  return {
    ...state,
    setKycCompleted,
    setKycRole,
    setKycProfile,
    setCompany,
    setKybStatus,
    setKybCompleted,
  }
}
