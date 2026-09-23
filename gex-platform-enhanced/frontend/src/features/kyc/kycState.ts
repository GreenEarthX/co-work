/**
 * KYC/KYB state — backend-backed (/api/v1/kyc), cached in memory.
 *
 * WHAT CHANGED, AND WHY
 * ---------------------
 * This module used to persist the whole record to `localStorage`: ~45 profile
 * fields and the KYB record including legal name, registration number, VAT id,
 * registered address and beneficial owners. That meant regulated personal data
 * lived in one browser profile — lost on a new device, invisible to the
 * backend, and impossible for GEX to review, which is the entire purpose of
 * collecting it. Meanwhile `auth_users.kyc_status` said VERIFIED for 19 of 20
 * accounts, about evidence the database had never seen.
 *
 * Now: migration 051's `kyc_profiles` / `kyb_records` / `kyb_invitations`, with
 * PROVENANCE on every row — SEED, EXTERNAL_PRIOR (OSINT, publication, geomap),
 * CLIENT_ASSERTED, VERIFIED. Nothing here can write VERIFIED; that is a GEX
 * staff action through POST /kyc/verify/{user_id}, and editing a record clears
 * any verification it had.
 *
 * THE CACHE IS A CACHE
 * --------------------
 * `getKycState()` stays synchronous because `useSyncExternalStore` needs it to
 * be, so the server state is mirrored in memory and refreshed after every
 * write. What it does NOT do is fall back to invented values: before a
 * successful load the state is empty and `loaded` is false, so a screen can
 * tell "nothing yet" from "nothing on file". Rendering a plausible-looking
 * profile that nobody submitted is the failure mode this whole change exists
 * to remove.
 */
import {
  acceptInvitation,
  createInvitation,
  fetchKycState,
  importLocal,
  listInvitations,
  putKyb,
  putProfile,
  type Provenance,
} from './kycApi'

const LEGACY_KYC_KEY = 'gex_kyc_state'
const LEGACY_INVITES_KEY = 'gex_kyb_invitations'

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
  /** False until the server has answered once. Not the same as "nothing on file". */
  loaded: boolean
  /** Where the stored record came from. Null when there is no record. */
  provenance: { kyc: Provenance | null; kyb: Provenance | null }
  verifiedBy: string | null
}

const EMPTY: KycState = {
  kycCompleted: false, kycRole: null, kycProfile: null, company: null,
  kybStatus: 'none', kybData: null, loaded: false,
  provenance: { kyc: null, kyb: null }, verifiedBy: null,
}

let _state: KycState = EMPTY
let _invites: KybInvitation[] = []
const _listeners = new Set<() => void>()

function notify() { _listeners.forEach(cb => cb()) }

function fromRemote(r: Awaited<ReturnType<typeof fetchKycState>>): KycState {
  const kyb = r.kybData as Record<string, unknown> | null
  return {
    kycCompleted: !!r.kycCompleted,
    kycRole: (r.kycRole as KycRole) ?? null,
    kycProfile: (r.kycProfile as KycProfile) ?? null,
    company: r.company ?? null,
    kybStatus: r.kybStatus ?? 'none',
    // The server stores snake_case columns; the screens read camelCase.
    kybData: kyb ? {
      legalName: String(kyb.legal_name ?? ''),
      registrationNumber: String(kyb.registration_number ?? ''),
      country: String(kyb.country ?? ''),
      vatId: (kyb.vat_id as string) ?? undefined,
      registeredAddress: String(kyb.registered_address ?? ''),
      beneficialOwners: (kyb.beneficial_owners as string) ?? undefined,
      responsibleName: String(kyb.responsible_name ?? ''),
      responsibleEmail: String(kyb.responsible_email ?? ''),
      responsibleJobTitle: (kyb.responsible_job_title as string) ?? undefined,
    } : null,
    loaded: true,
    provenance: { kyc: r.provenance?.kyc ?? null, kyb: r.provenance?.kyb ?? null },
    verifiedBy: r.verified?.kyc_by ?? null,
  }
}

/** Refresh from the server. Failures leave the last known state and are
 *  surfaced by the caller — never replaced with invented values. */
export async function refreshKyc(): Promise<void> {
  const remote = await fetchKycState()
  _state = fromRemote(remote)
  notify()
}

/**
 * Move anything this browser still holds to the server, once, then delete it.
 *
 * The local copy is removed only after the import succeeds: a failed import
 * that had already cleared the browser would destroy the only copy of a KYB
 * record. Written as CLIENT_ASSERTED — the user typed it, but nobody checked it.
 */
async function migrateLegacyLocalState(): Promise<void> {
  let raw: string | null = null
  try { raw = localStorage.getItem(LEGACY_KYC_KEY) } catch { return }
  if (!raw) return
  try {
    await importLocal(JSON.parse(raw))
    localStorage.removeItem(LEGACY_KYC_KEY)
    localStorage.removeItem(LEGACY_INVITES_KEY)
  } catch (err) {
    // Keep the local copy and say so. Losing a KYB record to a failed import
    // would be worse than leaving it where it is for one more session.
    console.error('KYC: could not move this browser\'s stored record to the server', err)
  }
}

export async function initKyc(): Promise<void> {
  await migrateLegacyLocalState()
  await refreshKyc()
  try { _invites = (await listInvitations()) as unknown as KybInvitation[] } catch { _invites = [] }
  notify()
}

export function subscribeKyc(cb: () => void) {
  _listeners.add(cb)
  return () => { _listeners.delete(cb) }
}

export function getKycState(): KycState { return _state }

// ── Writers. Each persists to the server, then re-reads it. ────────────────
// They stay synchronous in signature so the pages are unchanged; the promise
// is handled here and failures are logged rather than silently swallowed.

function persistProfile(next: Partial<KycState>) {
  _state = { ..._state, ...next }
  notify()
  void putProfile({
    profile: (_state.kycProfile ?? {}) as Record<string, unknown>,
    kyc_role: _state.kycRole,
    completed: _state.kycCompleted,
  }).then(refreshKyc).catch(err => {
    console.error('KYC: profile save failed — the server does not have this yet', err)
  })
}

export function setKycCompleted() { persistProfile({ kycCompleted: true }) }
export function setKycRole(role: KycRole) { persistProfile({ kycRole: role }) }
export function setKycProfile(profile: KycProfile) { persistProfile({ kycProfile: profile }) }

export function setCompany(company: string) {
  // The company is the token's, not the browser's: the server ignores anything
  // sent here. Kept for the pages' call sites, which pass the typed company
  // name; it updates the local label only.
  _state = { ..._state, company }
  notify()
}

export function setKybStatus(status: KycState['kybStatus']) {
  _state = { ..._state, kybStatus: status }
  notify()
}

export function setKybCompleted(data: KybData) {
  _state = { ..._state, kybStatus: 'completed', kybData: data }
  notify()
  void putKyb({
    legal_name: data.legalName,
    registration_number: data.registrationNumber,
    country: data.country,
    vat_id: data.vatId ?? null,
    registered_address: data.registeredAddress,
    beneficial_owners: data.beneficialOwners ?? null,
    responsible_name: data.responsibleName,
    responsible_email: data.responsibleEmail,
    responsible_job_title: data.responsibleJobTitle ?? null,
    status: 'completed',
  }).then(refreshKyc).catch(err => {
    console.error('KYC: KYB save failed — the server does not have this yet', err)
  })
}

// ── KYB invitations ────────────────────────────────────────────────────────

export function inviteColleagueForKyb(inv: KybInvitation) {
  void createInvitation({
    email: inv.email,
    company_name: inv.companyName,
    company_domain: inv.companyDomain || null,
  }).then(async () => {
    _invites = (await listInvitations()) as unknown as KybInvitation[]
    notify()
  }).catch(err => console.error('KYC: invitation failed', err))
}

export function getKybInvitationFor(email: string | undefined): KybInvitation | null {
  if (!email) return null
  return _invites.find(i => String(i.email).toLowerCase() === email.toLowerCase()) ?? null
}

export function consumeKybInvitation(email: string) {
  // Accepted, not deleted: who invited whom, and when it was taken up, is part
  // of how a company's users came to exist.
  void acceptInvitation(email).then(async () => {
    _invites = (await listInvitations()) as unknown as KybInvitation[]
    notify()
  }).catch(err => console.error('KYC: accepting the invitation failed', err))
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
    refreshKyc,
  }
}
