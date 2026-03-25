/**
 * OfftakerSupplyTable — R8 (Architectural Reform v6.0)
 *
 * 4-column table replacing the 9D radar chart for offtaker persona.
 *
 * Columns:
 *   DELIVERY    — plant operational status (OPERATING / CONSTRUCTION / DEVELOPMENT)
 *   CERTIFICATION — cert pathway status (ISSUED / APPLIED / ASSESSED / ASPIRATIONAL)
 *   LOGISTICS   — route + terminal feasibility to delivery point
 *   COMMITMENT  — offer firmness (BINDING / HEADS_OF_TERMS / INDICATIVE)
 *
 * Colour logic: GREEN = proceed, AMBER = conditional, RED = skip or flag
 * No score. No radar. Four columns. If all four green → call them.
 *
 * The Trader workspace detects actor_type = OFFTAKER via ABAC and renders
 * this table instead of the radar-based MarketDiscoveryPage.
 */

import { CheckCircle, AlertTriangle, XCircle, ExternalLink } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

// ─── Types ────────────────────────────────────────────────────────────────────

type PlantStatus   = 'OPERATING' | 'CONSTRUCTION' | 'DEVELOPMENT'
type CertStatus    = 'ISSUED' | 'APPLIED' | 'ASSESSED' | 'ASPIRATIONAL'
type LogisticsStatus = 'CONFIRMED' | 'ROUTE_EXISTS' | 'UNKNOWN'
type OfferFirmness = 'BINDING' | 'HEADS_OF_TERMS' | 'INDICATIVE'

type CellState = 'GREEN' | 'AMBER' | 'RED'

interface SupplyOffer {
  id:                   string
  producer:             string
  molecule:             string
  volume_mt_pa:         number
  price_eur_per_mt:     number
  delivery_window:      string
  delivery_point:       string
  plant_status:         PlantStatus
  plant_cod:            string | null    // expected COD if CONSTRUCTION/DEVELOPMENT
  cert_status:          CertStatus
  cert_scheme:          string           // e.g. RFNBO, ISCC, CORSiA
  logistics_status:     LogisticsStatus
  logistics_detail:     string           // one line: confirmed route or pending info
  offer_firmness:       OfferFirmness
  expires_at:           string | null
}

// ─── Cell state logic ─────────────────────────────────────────────────────────

function deliveryState(s: PlantStatus): CellState {
  if (s === 'OPERATING') return 'GREEN'
  if (s === 'CONSTRUCTION') return 'AMBER'
  return 'RED'
}

function certState(s: CertStatus): CellState {
  if (s === 'ISSUED') return 'GREEN'
  if (s === 'APPLIED' || s === 'ASSESSED') return 'AMBER'
  return 'RED'
}

function logisticsState(s: LogisticsStatus): CellState {
  if (s === 'CONFIRMED') return 'GREEN'
  if (s === 'ROUTE_EXISTS') return 'AMBER'
  return 'RED'
}

function firmnessState(s: OfferFirmness): CellState {
  if (s === 'BINDING') return 'GREEN'
  if (s === 'HEADS_OF_TERMS') return 'AMBER'
  return 'RED'
}

function overallState(offer: SupplyOffer): CellState {
  const states = [
    deliveryState(offer.plant_status),
    certState(offer.cert_status),
    logisticsState(offer.logistics_status),
    firmnessState(offer.offer_firmness),
  ]
  if (states.some(s => s === 'RED')) return 'RED'
  if (states.some(s => s === 'AMBER')) return 'AMBER'
  return 'GREEN'
}

// ─── Cell component ───────────────────────────────────────────────────────────

const CELL_CONFIG: Record<CellState, { bg: string; text: string; Icon: React.ElementType }> = {
  GREEN: { bg: 'bg-green-50', text: 'text-green-800', Icon: CheckCircle },
  AMBER: { bg: 'bg-amber-50', text: 'text-amber-800', Icon: AlertTriangle },
  RED:   { bg: 'bg-red-50',   text: 'text-red-800',   Icon: XCircle },
}

function Cell({ state, label, detail }: { state: CellState; label: string; detail: string }) {
  const { bg, text, Icon } = CELL_CONFIG[state]
  return (
    <td className={`px-3 py-3 ${bg}`}>
      <div className={`flex items-start gap-1.5 ${text}`}>
        <Icon className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
        <div>
          <div className="text-xs font-semibold">{label}</div>
          <div className="text-[10px] opacity-75 mt-0.5">{detail}</div>
        </div>
      </div>
    </td>
  )
}

// ─── Demo data ────────────────────────────────────────────────────────────────

const DEMO_OFFERS: SupplyOffer[] = [
  {
    id: 'offer_001',
    producer: 'Nordic H2 Solutions AS',
    molecule: 'e-Methanol',
    volume_mt_pa: 8000,
    price_eur_per_mt: 1250,
    delivery_window: 'Q1 2027 – Q4 2031',
    delivery_point: 'Hamburg (HPA-approved terminal)',
    plant_status: 'OPERATING',
    plant_cod: null,
    cert_status: 'ISSUED',
    cert_scheme: 'RFNBO (RED III)',
    logistics_status: 'CONFIRMED',
    logistics_detail: 'Ship — confirmed terminal agreement at HPA Terminal 4',
    offer_firmness: 'BINDING',
    expires_at: '2026-06-30',
  },
  {
    id: 'offer_002',
    producer: 'Iberian Green Fuels SL',
    molecule: 'e-Methanol',
    volume_mt_pa: 12000,
    price_eur_per_mt: 1080,
    delivery_window: 'Q3 2027 – Q2 2032',
    delivery_point: 'Rotterdam / Hamburg',
    plant_status: 'CONSTRUCTION',
    plant_cod: 'Q2 2027',
    cert_status: 'ASSESSED',
    cert_scheme: 'RFNBO pre-cert (Clarity)',
    logistics_status: 'ROUTE_EXISTS',
    logistics_detail: 'Ship — route exists, terminal agreement pending at Hamburg',
    offer_firmness: 'HEADS_OF_TERMS',
    expires_at: '2026-09-30',
  },
  {
    id: 'offer_003',
    producer: 'AtlanticMet GmbH',
    molecule: 'e-Methanol',
    volume_mt_pa: 5000,
    price_eur_per_mt: 950,
    delivery_window: 'H2 2028 – H1 2033',
    delivery_point: 'TBD',
    plant_status: 'DEVELOPMENT',
    plant_cod: 'H1 2028',
    cert_status: 'ASPIRATIONAL',
    cert_scheme: 'RFNBO pathway unconfirmed',
    logistics_status: 'UNKNOWN',
    logistics_detail: 'No logistics agreement. Delivery route not yet defined.',
    offer_firmness: 'INDICATIVE',
    expires_at: null,
  },
]

// ─── Main component ───────────────────────────────────────────────────────────

interface OfftakerSupplyTableProps {
  molecule?:        string
  deliveryPoint?:   string
  offers?:          SupplyOffer[]
}

export function OfftakerSupplyTable({
  molecule = 'e-Methanol',
  deliveryPoint = 'Hamburg',
  offers = DEMO_OFFERS,
}: OfftakerSupplyTableProps) {
  const navigate = useNavigate()

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-bold text-gray-800">
            Supply offers — {molecule} → {deliveryPoint}
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">
            All four columns must be GREEN before sending an RFQ.
            AMBER = conditional — verify before proceeding. RED = skip or escalate.
          </p>
        </div>
        <span className="text-xs text-gray-400">{offers.length} offer{offers.length !== 1 ? 's' : ''}</span>
      </div>

      {/* Table */}
      <div className="rounded-lg border border-gray-200 overflow-hidden">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50">
              <th className="text-left px-3 py-2.5 font-semibold text-gray-600">Producer / Offer</th>
              <th className="text-left px-3 py-2.5 font-semibold text-gray-600">DELIVERY</th>
              <th className="text-left px-3 py-2.5 font-semibold text-gray-600">CERTIFICATION</th>
              <th className="text-left px-3 py-2.5 font-semibold text-gray-600">LOGISTICS</th>
              <th className="text-left px-3 py-2.5 font-semibold text-gray-600">COMMITMENT</th>
              <th className="text-left px-3 py-2.5 font-semibold text-gray-600">Action</th>
            </tr>
          </thead>
          <tbody>
            {offers.map((offer, idx) => {
              const overall = overallState(offer)
              return (
                <tr
                  key={offer.id}
                  className={`border-b border-gray-100 last:border-0 ${idx % 2 === 1 ? 'bg-gray-50/50' : ''}`}
                >
                  {/* Producer / offer summary */}
                  <td className="px-3 py-3">
                    <div className="font-semibold text-gray-800">{offer.producer}</div>
                    <div className="text-gray-500">{offer.volume_mt_pa.toLocaleString()} MT/yr · €{offer.price_eur_per_mt.toLocaleString()}/MT</div>
                    <div className="text-gray-400 mt-0.5">{offer.delivery_window}</div>
                    {offer.expires_at && (
                      <div className="text-amber-600 mt-0.5">Expires {offer.expires_at}</div>
                    )}
                  </td>

                  <Cell
                    state={deliveryState(offer.plant_status)}
                    label={offer.plant_status}
                    detail={offer.plant_cod ? `COD: ${offer.plant_cod}` : 'Currently operating'}
                  />
                  <Cell
                    state={certState(offer.cert_status)}
                    label={offer.cert_status}
                    detail={offer.cert_scheme}
                  />
                  <Cell
                    state={logisticsState(offer.logistics_status)}
                    label={offer.logistics_status.replace('_', ' ')}
                    detail={offer.logistics_detail}
                  />
                  <Cell
                    state={firmnessState(offer.offer_firmness)}
                    label={offer.offer_firmness.replace('_', ' ')}
                    detail={offer.offer_firmness === 'INDICATIVE' ? 'No binding commitment' : 'Legally binding or HoT signed'}
                  />

                  {/* Action */}
                  <td className="px-3 py-3">
                    {overall === 'GREEN' ? (
                      <button
                        onClick={() => navigate(`/trader/rfqs?offer=${offer.id}`)}
                        className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md bg-green-600 text-white text-xs font-semibold hover:bg-green-700 transition-colors"
                      >
                        Send RFQ
                      </button>
                    ) : overall === 'AMBER' ? (
                      <button
                        onClick={() => navigate(`/trader/market?offer=${offer.id}`)}
                        className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md border border-amber-300 bg-amber-50 text-amber-700 text-xs font-semibold hover:bg-amber-100 transition-colors"
                      >
                        Verify <ExternalLink className="w-3 h-3" />
                      </button>
                    ) : (
                      <span className="text-xs text-gray-400 italic">Skip — red flag</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <p className="text-[10px] text-gray-400">
        RFQ can only be sent against BINDING or HEADS_OF_TERMS offers from OPERATING or CONSTRUCTION
        plants with confirmed or assessed certification. INDICATIVE offers require commercial confirmation
        before RFQ submission.
      </p>
    </div>
  )
}
