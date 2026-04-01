/**
 * MoleculeGatingAlert — molecule-specific safety & regulatory gate status block.
 * Surfaces HAZOP/Seveso for NH3 and HAZOP/ASTM for SAF.
 * Designed to be rendered as a priority alert above standard stage gates.
 */
import { AlertTriangle, CheckCircle2, Clock, ShieldAlert } from 'lucide-react'
import type { CustomerProject } from '@/data/customerProjects'

interface MoleculeGatingAlertProps {
  project: CustomerProject
}

interface GateField {
  key: string
  label: string
  description: string
  passed: boolean
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM'
}

function statusIcon(passed: boolean) {
  return passed
    ? <CheckCircle2 className="w-4 h-4 text-green-600 shrink-0" />
    : <AlertTriangle className="w-4 h-4 text-red-500 shrink-0" />
}

function buildNH3Gates(mg: NonNullable<CustomerProject['molecule_gating']>): GateField[] {
  const sevesoPassed = mg.seveso_tier === 'LOWER' || mg.seveso_tier === 'UPPER'
  return [
    {
      key: 'hazop',
      label: 'HAZOP Study',
      description: 'IEC 61882 compliant HAZOP completed and signed off',
      passed: !!mg.hazop_completed,
      severity: 'CRITICAL',
    },
    {
      key: 'seveso',
      label: 'Seveso III Tier Classification',
      description: `Classified under Seveso III Directive (Annex I — ammonia ≥ 50 t). Status: ${mg.seveso_tier ?? 'PENDING'}`,
      passed: sevesoPassed,
      severity: 'CRITICAL',
    },
    {
      key: 'terminal',
      label: 'Terminal Interface Agreement',
      description: 'Signed TIA with receiving port / FSU operator',
      passed: !!mg.terminal_interface_signed,
      severity: 'HIGH',
    },
    {
      key: 'mol_ins',
      label: 'NH₃ Molecule Insurance',
      description: 'Specialist environmental impairment / pollution liability placed',
      passed: !!mg.molecule_insurance_placed,
      severity: 'HIGH',
    },
  ]
}

function buildSAFGates(mg: NonNullable<CustomerProject['molecule_gating']>): GateField[] {
  const astmPassed = mg.astm_cert_status === 'CERTIFIED'
  return [
    {
      key: 'hazop',
      label: 'Process Hazard Review',
      description: 'HAZOP / What-If analysis for FT / ATJ synthesis unit',
      passed: !!mg.process_hazard_review,
      severity: 'CRITICAL',
    },
    {
      key: 'astm',
      label: 'ASTM D7566 Certification',
      description: `Fuel specification approval under ASTM D7566 Annex. Status: ${mg.astm_cert_status ?? 'NONE'}`,
      passed: astmPassed,
      severity: 'CRITICAL',
    },
    {
      key: 'mol_ins',
      label: 'SAF Molecule Insurance',
      description: 'Aviation product liability & blending risk placed',
      passed: !!mg.molecule_insurance_placed,
      severity: 'HIGH',
    },
  ]
}

export function MoleculeGatingAlert({ project }: MoleculeGatingAlertProps) {
  const { molecule, molecule_gating: mg } = project

  const isNH3 = molecule === 'NH3'
  const isSAF = molecule === 'SAF'

  if (!mg || (!isNH3 && !isSAF)) return null

  const gates = isNH3 ? buildNH3Gates(mg) : buildSAFGates(mg)
  const failing = gates.filter(g => !g.passed)
  const allPassed = failing.length === 0
  const criticalFailing = failing.filter(g => g.severity === 'CRITICAL').length

  if (allPassed) {
    return (
      <div className="flex items-center gap-3 px-4 py-3 bg-green-50 border border-green-200 rounded-xl">
        <CheckCircle2 className="w-5 h-5 text-green-600 shrink-0" />
        <div>
          <span className="text-sm font-bold text-green-800">
            {isNH3 ? 'NH₃ ' : 'SAF '} molecule gates — all cleared
          </span>
          <p className="text-xs text-green-700">HAZOP, regulatory classification and specialist insurance confirmed.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-red-200 bg-red-50 overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 bg-red-100 border-b border-red-200">
        <ShieldAlert className="w-5 h-5 text-red-600 shrink-0" />
        <div className="flex-1">
          <span className="text-sm font-black text-red-800">
            {isNH3 ? 'NH₃ Hazmat' : 'SAF Compliance'} Gates — {criticalFailing > 0 ? `${criticalFailing} Critical` : `${failing.length} High`} Blocking
          </span>
          <p className="text-xs text-red-700">
            {isNH3
              ? 'Ammonia is a Seveso III Annex I substance. These gates must clear before insurer sign-off.'
              : 'SAF requires ASTM D7566 and process hazard sign-off before offtake certification.'}
          </p>
        </div>
      </div>

      {/* Gate rows */}
      <div className="divide-y divide-red-100">
        {gates.map(gate => (
          <div key={gate.key} className="flex items-start gap-3 px-4 py-2.5">
            {gate.passed
              ? <CheckCircle2 className="w-4 h-4 text-green-600 mt-0.5 shrink-0" />
              : gate.severity === 'CRITICAL'
                ? <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 shrink-0" />
                : <Clock className="w-4 h-4 text-amber-500 mt-0.5 shrink-0" />
            }
            <div>
              <div className="flex items-center gap-2">
                <span className={`text-xs font-bold ${gate.passed ? 'text-green-800' : gate.severity === 'CRITICAL' ? 'text-red-800' : 'text-amber-800'}`}>
                  {gate.label}
                </span>
                {!gate.passed && (
                  <span className={`text-xs px-1.5 py-0.5 rounded font-semibold ${
                    gate.severity === 'CRITICAL' ? 'bg-red-200 text-red-700' : 'bg-amber-100 text-amber-700'
                  }`}>
                    {gate.severity}
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-600">{gate.description}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
