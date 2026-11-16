// Screen: RFQs & Negotiation (/rfqs)
// The signed-in company's own requests for quotation, on the market engine
// (/api/v1/market). Other companies see an RFQ only as an anonymised listing on
// Market Discovery; the buyer's name is revealed to a seller only once matched.
// Before 2026-10-23 this screen was unrouted and called the API without a
// bearer token, so every request answered 401 (gap register G-04).
import { useCallback, useEffect, useState, useRef } from 'react';
import { Plus, CheckCircle, XCircle, Clock, FileText } from 'lucide-react';
import { marketAPI, type Commodity, type MarketRFQ, type RfqRequirements } from '@/api';
import { useMarketPolicy } from '@/lib/marketPolicy';
import { SupplyCandidates } from './SupplyCandidates';

// What the buyer may do from each state; 'matched' is set by the market.
const ACTIONS: Record<string, { to: string; label: string }[]> = {
  draft: [{ to: 'open', label: 'Publish' }, { to: 'cancelled', label: 'Cancel' }],
  open: [{ to: 'withdrawn', label: 'Withdraw' }],
};

const EMPTY_FORM = {
  molecule: '',
  volume_mtpd: '',
  max_price_eur_kg: '',
  delivery_start: '',
  delivery_end: '',
  location: '',
  buyer_contact: '',
  // Product requirements (alembic 117), all optional; "required" ones decide eligibility.
  max_ci: '',
  regimes: '',
  schemes: '',
  min_evidence: '',
  physical_form: '',
  incoterms: '',
  named_place: '',
  delivery_country: '',
  required: [] as string[],
};

const list = (v: string) => v.split(',').map((x) => x.trim()).filter(Boolean);

/** The requirements object the server validates (backend core/requirements.py); empty fields are left out. */
export function buildRequirements(f: typeof EMPTY_FORM): RfqRequirements {
  const r: RfqRequirements = {};
  if (f.max_ci) r.max_ci_gco2e_mj = parseFloat(f.max_ci);
  if (list(f.regimes).length) r.regimes = list(f.regimes);
  if (list(f.schemes).length) r.accepted_schemes = list(f.schemes);
  if (f.min_evidence) r.min_evidence_state = f.min_evidence as RfqRequirements['min_evidence_state'];
  if (f.physical_form) r.physical_form = f.physical_form;
  if (list(f.incoterms).length) r.incoterms = list(f.incoterms).map((i) => i.toUpperCase());
  if (f.named_place.trim()) r.named_place = f.named_place.trim();
  if (f.delivery_country.trim()) r.delivery_country = f.delivery_country.trim().toUpperCase();
  const mandatory = f.required.filter((k) => k in r);
  if (mandatory.length) r.mandatory = mandatory;
  return r;
}

function requirements(rfq: MarketRFQ): string[] {
  const raw = rfq.compliance_requirements as unknown;
  if (Array.isArray(raw)) return raw as string[];
  if (typeof raw === 'string') {
    try { return JSON.parse(raw) ?? []; } catch { return []; }
  }
  return [];
}

const RFQManagementPage: React.FC = () => {
  // D-B: Commercial raises RFQs (backend core/market_policy). Others see them, without the buttons.
  const { can } = useMarketPolicy();
  const [supplyFor, setSupplyFor] = useState<string | null>(null);
  const [rfqs, setRfqs] = useState<MarketRFQ[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [filter, setFilter] = useState<string>('all');
  const [formData, setFormData] = useState(EMPTY_FORM);
  // One Idempotency-Key per filled-in form: a double click or a retry returns the first RFQ
  // instead of creating a second (backend F12). A new key once the RFQ exists.
  const idemKey = useRef(crypto.randomUUID());
  // Molecules come from tb_commodity in PostgreSQL; matching compares the code exactly.
  const [commodities, setCommodities] = useState<Commodity[]>([]);
  useEffect(() => {
    marketAPI.commodities().then(({ commodities }) => setCommodities(commodities))
      .catch((e) => setError((e as Error).message));
  }, []);

  const fetchRFQs = useCallback(async () => {
    try {
      setRfqs((await marketAPI.myRFQs()).rfqs);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchRFQs(); }, [fetchRFQs]);

  const handleSubmit = async (e: React.FormEvent, publish: boolean) => {
    e.preventDefault();
    try {
      await marketAPI.createRFQ({
        molecule: formData.molecule,
        volume_mtpd: parseFloat(formData.volume_mtpd),
        max_price_eur_kg: formData.max_price_eur_kg ? parseFloat(formData.max_price_eur_kg) : null,
        delivery_start: formData.delivery_start,
        delivery_end: formData.delivery_end,
        location: formData.location || null,
        buyer_contact: formData.buyer_contact || null,
        status: publish ? 'open' : 'draft',
        requirements: buildRequirements(formData),
      }, idemKey.current);
      idemKey.current = crypto.randomUUID();
      setShowCreateModal(false);
      setFormData(EMPTY_FORM);
      fetchRFQs();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const transition = async (id: string, to: string) => {
    try {
      await marketAPI.setRFQStatus(id, to);
      fetchRFQs();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const getStatusBadge = (status: string) => {
    const badges: Record<string, { bg: string; text: string; icon: React.ReactNode }> = {
      draft: { bg: 'bg-gray-100', text: 'text-gray-700', icon: <FileText className="w-4 h-4" /> },
      open: { bg: 'bg-blue-100', text: 'text-blue-700', icon: <Clock className="w-4 h-4" /> },
      matched: { bg: 'bg-green-100', text: 'text-green-700', icon: <CheckCircle className="w-4 h-4" /> },
      cancelled: { bg: 'bg-gray-100', text: 'text-gray-500', icon: <XCircle className="w-4 h-4" /> },
      expired: { bg: 'bg-gray-100', text: 'text-gray-500', icon: <XCircle className="w-4 h-4" /> },
      withdrawn: { bg: 'bg-gray-100', text: 'text-gray-500', icon: <XCircle className="w-4 h-4" /> },
    };
    const badge = badges[status] || badges.draft;
    return (
      <span className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium ${badge.bg} ${badge.text}`}>
        {badge.icon}
        {status.charAt(0).toUpperCase() + status.slice(1)}
      </span>
    );
  };

  const shown = filter === 'all' ? rfqs : rfqs.filter(r => r.status === filter);
  const stats = {
    total: rfqs.length,
    draft: rfqs.filter(r => r.status === 'draft').length,
    open: rfqs.filter(r => r.status === 'open').length,
    matched: rfqs.filter(r => r.status === 'matched').length,
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">RFQs &amp; Negotiation</h1>
          <p className="text-gray-600 mt-1">
            Your company's requests. Sellers see them without your name until a match exists;
            a match needs both of you to accept.
          </p>
        </div>
        {can('rfq.create') ? (
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            <Plus className="w-5 h-5" />
            Create RFQ
          </button>
        ) : (
          <p className="max-w-xs text-right text-sm text-gray-500">RFQs are raised by Commercial in your company.</p>
        )}
      </div>

      {error && (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[
          ['Total RFQs', stats.total, 'text-gray-900'],
          ['Draft', stats.draft, 'text-gray-600'],
          ['Open', stats.open, 'text-blue-600'],
          ['Matched', stats.matched, 'text-green-600'],
        ].map(([label, value, color]) => (
          <div key={label as string} className="bg-white p-6 rounded-lg shadow-sm border">
            <div className={`text-sm font-medium ${color}`}>{label}</div>
            <div className={`text-3xl font-bold mt-2 ${color}`}>{value}</div>
          </div>
        ))}
      </div>

      <div className="flex gap-2">
        {['all', 'draft', 'open', 'matched', 'withdrawn', 'cancelled', 'expired'].map((status) => (
          <button
            key={status}
            onClick={() => setFilter(status)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              filter === status ? 'bg-blue-100 text-blue-700' : 'bg-white text-gray-600 hover:bg-gray-50'
            }`}
          >
            {status.charAt(0).toUpperCase() + status.slice(1)}
          </button>
        ))}
      </div>

      <div className="bg-white rounded-lg shadow-sm border">
        {loading ? (
          <div className="p-8 text-center text-gray-500">Loading RFQs...</div>
        ) : shown.length === 0 ? (
          <div className="p-8 text-center">
            <FileText className="w-12 h-12 text-gray-400 mx-auto mb-4" />
            <p className="text-gray-600">No RFQs found</p>
            {can('rfq.create') && <button onClick={() => setShowCreateModal(true)} className="mt-4 text-blue-600 hover:text-blue-700 font-medium">
              Create your first RFQ
            </button>}
          </div>
        ) : (
          <div className="divide-y">
            {shown.map((rfq) => (
              <div key={rfq.id} className="p-6 hover:bg-gray-50 transition-colors">
                <div className="flex justify-between items-start gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <h3 className="text-lg font-semibold text-gray-900">
                        {rfq.molecule} - {rfq.volume_mtpd} MTPD
                      </h3>
                      {getStatusBadge(rfq.status)}
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-3 text-sm">
                      <div>
                        <span className="text-gray-500">Max Price:</span>
                        <div className="font-medium text-gray-900">
                          {rfq.max_price_eur_kg != null ? `€${rfq.max_price_eur_kg.toFixed(2)}/kg` : 'Not specified'}
                        </div>
                      </div>
                      <div>
                        <span className="text-gray-500">Delivery:</span>
                        <div className="font-medium text-gray-900">{rfq.delivery_start} to {rfq.delivery_end}</div>
                      </div>
                      <div>
                        <span className="text-gray-500">Location:</span>
                        <div className="font-medium text-gray-900">{rfq.location || 'Any'}</div>
                      </div>
                      <div>
                        <span className="text-gray-500">Trail:</span>
                        <div className="font-mono text-xs text-gray-700">{rfq.correlation_id ?? '—'}</div>
                      </div>
                    </div>
                    {requirements(rfq).length > 0 && (
                      <div className="mt-3 flex gap-2">
                        {requirements(rfq).map((req) => (
                          <span key={req} className="px-2 py-1 bg-blue-50 text-blue-700 text-xs rounded">{req}</span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex shrink-0 gap-2">
                    {rfq.status === 'open' && (
                      <button onClick={() => setSupplyFor(supplyFor === rfq.id ? null : rfq.id)}
                              className="rounded-lg bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-800">
                        Find supply
                      </button>
                    )}
                    {(can('rfq.change') ? (ACTIONS[rfq.status] ?? []) : []).map((a) => (
                      <button
                        key={a.to}
                        onClick={() => transition(rfq.id, a.to)}
                        className="rounded-lg border px-3 py-1.5 text-sm font-medium hover:bg-gray-50"
                      >
                        {a.label}
                      </button>
                    ))}
                  </div>
                </div>
                {supplyFor === rfq.id && <SupplyCandidates rfqId={rfq.id} onClose={() => setSupplyFor(null)} />}
              </div>
            ))}
          </div>
        )}
      </div>

      {showCreateModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto p-6">
            <h2 className="text-xl font-bold mb-1">Create New RFQ</h2>
            <p className="mb-4 text-sm text-gray-600">Raised in your company's name — the signed-in account decides that, not this form.</p>
            <form onSubmit={(e) => handleSubmit(e, true)} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label htmlFor="rfq-molecule" className="block text-sm font-medium text-gray-700 mb-1">Molecule</label>
                  <select
                    id="rfq-molecule"
                    value={formData.molecule}
                    onChange={(e) => setFormData({ ...formData, molecule: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg"
                    required
                  >
                    <option value="" disabled>Choose a molecule</option>
                    {commodities.filter((c) => c.market_molecule).map((c) => (
                      <option key={c.code} value={c.market_molecule!}>{c.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="rfq-volume" className="block text-sm font-medium text-gray-700 mb-1">Volume (MTPD)</label>
                  <input
                    id="rfq-volume"
                    type="number"
                    step="0.1"
                    min="0.1"
                    value={formData.volume_mtpd}
                    onChange={(e) => setFormData({ ...formData, volume_mtpd: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg"
                    required
                  />
                </div>
              </div>
              <div>
                <label htmlFor="rfq-price" className="block text-sm font-medium text-gray-700 mb-1">Max Price (€/kg) - Optional</label>
                <input
                  id="rfq-price"
                  type="number"
                  step="0.01"
                  value={formData.max_price_eur_kg}
                  onChange={(e) => setFormData({ ...formData, max_price_eur_kg: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg"
                  placeholder="Leave empty for no limit"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label htmlFor="rfq-start" className="block text-sm font-medium text-gray-700 mb-1">Delivery Start</label>
                  <input
                    id="rfq-start"
                    type="date"
                    value={formData.delivery_start}
                    onChange={(e) => setFormData({ ...formData, delivery_start: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg"
                    required
                  />
                </div>
                <div>
                  <label htmlFor="rfq-end" className="block text-sm font-medium text-gray-700 mb-1">Delivery End</label>
                  <input
                    id="rfq-end"
                    type="date"
                    value={formData.delivery_end}
                    onChange={(e) => setFormData({ ...formData, delivery_end: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg"
                    required
                  />
                </div>
              </div>
              <div>
                <label htmlFor="rfq-location" className="block text-sm font-medium text-gray-700 mb-1">Delivery location - Optional, kept private (state a named place below to show one)</label>
                <input
                  id="rfq-location"
                  type="text"
                  value={formData.location}
                  onChange={(e) => setFormData({ ...formData, location: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg"
                  placeholder="e.g., Hamburg, Germany"
                />
              </div>
              <div>
                <label htmlFor="rfq-contact" className="block text-sm font-medium text-gray-700 mb-1">Contact - Optional, kept private until you choose to share it</label>
                <input
                  id="rfq-contact"
                  type="email"
                  value={formData.buyer_contact}
                  onChange={(e) => setFormData({ ...formData, buyer_contact: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg"
                  placeholder="email@company.com"
                />
              </div>
              <fieldset className="space-y-3 rounded-lg border p-3">
                <legend className="px-1 text-sm font-semibold text-gray-800">Product requirements (optional)</legend>
                <p className="text-xs text-gray-500">Sellers see these with your RFQ. Tick "required" for a limit a listing must meet.</p>
                {([
                  ['rfq-max-ci', 'Max carbon intensity (gCO₂e/MJ)', 'max_ci', 'max_ci_gco2e_mj', 'number', 'e.g. 28.2'],
                  ['rfq-regimes', 'Regimes (comma-separated)', 'regimes', 'regimes', 'text', 'e.g. RFNBO, RED III'],
                  ['rfq-schemes', 'Accepted schemes (comma-separated)', 'schemes', 'accepted_schemes', 'text', 'e.g. ISCC EU, CertifHy'],
                  ['rfq-incoterms', 'Incoterms (comma-separated)', 'incoterms', 'incoterms', 'text', 'e.g. FOB, CIF'],
                  ['rfq-place', 'Named place', 'named_place', null, 'text', 'e.g. Rotterdam'],
                  ['rfq-country', 'Delivery country (two letters)', 'delivery_country', 'delivery_country', 'text', 'e.g. NL'],
                ] as const).map(([id, label, field, key, type, ph]) => (
                  <div key={id} className="flex items-end gap-2">
                    <div className="flex-1">
                      <label htmlFor={id} className="block text-xs font-medium text-gray-700 mb-1">{label}</label>
                      <input id={id} type={type} step="any" placeholder={ph} value={formData[field]}
                             onChange={(e) => setFormData({ ...formData, [field]: e.target.value })}
                             className="w-full px-3 py-1.5 border rounded-lg text-sm" />
                    </div>
                    {key && (
                      <label className="flex items-center gap-1 pb-2 text-xs text-gray-600">
                        <input type="checkbox" checked={formData.required.includes(key)}
                               onChange={(e) => setFormData({ ...formData, required: e.target.checked
                                 ? [...formData.required, key] : formData.required.filter((k) => k !== key) })} />
                        required
                      </label>
                    )}
                  </div>
                ))}
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label htmlFor="rfq-evidence" className="block text-xs font-medium text-gray-700 mb-1">Minimum evidence</label>
                    <select id="rfq-evidence" value={formData.min_evidence}
                            onChange={(e) => setFormData({ ...formData, min_evidence: e.target.value })}
                            className="w-full px-2 py-1.5 border rounded-lg text-sm">
                      <option value="">Any</option>
                      <option value="submitted">Submitted or better</option>
                      <option value="verified">Verified only</option>
                    </select>
                  </div>
                  <div>
                    <label htmlFor="rfq-form" className="block text-xs font-medium text-gray-700 mb-1">Physical form</label>
                    <select id="rfq-form" value={formData.physical_form}
                            onChange={(e) => setFormData({ ...formData, physical_form: e.target.value })}
                            className="w-full px-2 py-1.5 border rounded-lg text-sm">
                      <option value="">Any</option>
                      <option value="gas">Gas</option>
                      <option value="compressed_gas">Compressed gas</option>
                      <option value="liquid">Liquid</option>
                      <option value="liquefied_gas">Liquefied gas</option>
                    </select>
                  </div>
                </div>
              </fieldset>
              <div className="flex gap-2 justify-end pt-4">
                <button type="button" onClick={() => setShowCreateModal(false)} className="px-4 py-2 border rounded-lg hover:bg-gray-50">
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={(e) => {
                    const form = e.currentTarget.form;
                    if (form && !form.reportValidity()) return;
                    handleSubmit(e as unknown as React.FormEvent, false);
                  }}
                  className="px-4 py-2 border rounded-lg hover:bg-gray-50"
                >
                  Save as draft
                </button>
                <button type="submit" className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                  Publish RFQ
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default RFQManagementPage;
